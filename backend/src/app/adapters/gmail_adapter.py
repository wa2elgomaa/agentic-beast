"""Gmail adapter for fetching analytics report emails."""

import base64
import re
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.adapters.base import AdapterHealthStatus, AdapterStatus, DataAdapter
from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


# Custom exceptions for credential handling
class CredentialExpiredError(Exception):
    """Raised when refresh token is invalid/expired (invalid_grant)."""
    pass


class TemporaryAuthError(Exception):
    """Raised for transient auth errors (network, rate limit, etc)."""
    pass


# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]


class GmailAdapter(DataAdapter):
    """Adapter for fetching analytics reports from Gmail."""

    def __init__(
        self,
        oauth_config: Optional[Dict[str, Any]] = None,
        credential_service: Optional[Any] = None,
        task_id: Optional[str] = None,
    ):
        """Initialize Gmail adapter.
        
        Args:
            oauth_config: OAuth configuration dict
            credential_service: Optional GmailCredentialService for status tracking
            task_id: Optional task UUID for credential tracking
        """
        super().__init__(name="gmail_adapter")
        self.service = None
        self.credentials = None
        self.oauth_config = oauth_config or {}
        self.credential_service = credential_service
        self.task_id = task_id

    async def connect(self, max_retries: int = 2) -> None:
        """Establish connection to Gmail API with retry logic.
        
        Args:
            max_retries: Number of retries for transient errors
            
        Raises:
            CredentialExpiredError: If refresh token is invalid (invalid_grant)
            TemporaryAuthError: If transient error occurs (retries exhausted)
        """
        import asyncio
        from google.auth.exceptions import RefreshError
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "Connecting to Gmail API",
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1,
                )

                refresh_token = self.oauth_config.get("refresh_token")
                if not refresh_token:
                    raise ValueError("Missing Gmail OAuth refresh_token in task adaptor_config.gmail_oauth")

                client_id = self.oauth_config.get("client_id") or settings.gmail_oauth_client_id
                client_secret = self.oauth_config.get("client_secret") or settings.gmail_oauth_client_secret
                token_uri = self.oauth_config.get("token_uri") or settings.gmail_oauth_token_uri
                scopes = self.oauth_config.get("scopes") or GMAIL_SCOPES

                if not client_id or not client_secret:
                    raise ValueError("Missing Gmail OAuth client credentials")

                self.credentials = Credentials(
                    token=self.oauth_config.get("access_token"),
                    refresh_token=refresh_token,
                    token_uri=token_uri,
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=scopes,
                )

                # Token refresh with error detection
                if not self.credentials.valid:
                    try:
                        self.credentials.refresh(Request())
                    except RefreshError as e:
                        error_msg = str(e).lower()
                        
                        # Permanent failure: invalid_grant
                        if "invalid_grant" in error_msg:
                            logger.error(
                                "Gmail token invalid or revoked",
                                error=str(e),
                                task_id=self.task_id,
                            )
                            
                            # Record in credential service if available
                            if self.credential_service and self.task_id:
                                from app.services.gmail_credential_service import (
                                    GmailCredentialHealthStatus,
                                    ErrorCode,
                                )
                                
                                await self.credential_service.update_credential_status(
                                    task_id=self.task_id,
                                    status=GmailCredentialHealthStatus.INVALID,
                                    error_code=ErrorCode.INVALID_GRANT,
                                    error_message="Refresh token is invalid or revoked",
                                )
                            
                            raise CredentialExpiredError(
                                "Gmail refresh token invalid/expired. User must re-authenticate."
                            ) from e
                        
                        # Transient error: retry
                        if attempt < max_retries:
                            backoff = 2 ** attempt
                            logger.warning(
                                f"Token refresh failed (attempt {attempt + 1}), retrying in {backoff}s...",
                                error=str(e),
                            )
                            await asyncio.sleep(backoff)
                            continue
                        else:
                            # Retries exhausted
                            logger.error(
                                "Token refresh failed after retries",
                                error=str(e),
                                attempts=attempt + 1,
                            )
                            
                            if self.credential_service and self.task_id:
                                count = await self.credential_service.increment_failure_count(
                                    self.task_id
                                )
                                logger.warning(
                                    "Incremented credential failure count",
                                    task_id=self.task_id,
                                    consecutive_failures=count,
                                )
                            
                            raise TemporaryAuthError(
                                f"Token refresh failed after {max_retries + 1} attempts"
                            ) from e

                # Build Gmail service
                self.service = build("gmail", "v1", credentials=self.credentials)

                # Test connection
                profile = self.service.users().getProfile(userId="me").execute()
                email_address = profile.get("emailAddress")
                logger.info(
                    "Gmail connection successful",
                    email_address=email_address,
                    task_id=self.task_id,
                )

                # Record success in credential service
                if self.credential_service and self.task_id:
                    from app.services.gmail_credential_service import GmailCredentialHealthStatus
                    
                    await self.credential_service.update_credential_status(
                        task_id=self.task_id,
                        status=GmailCredentialHealthStatus.ACTIVE,
                        account_email=email_address,
                    )
                    await self.credential_service.reset_failure_count(self.task_id)

                self.health_status = AdapterHealthStatus(status=AdapterStatus.CONNECTED)
                return

            except (CredentialExpiredError, TemporaryAuthError):
                # Re-raise our custom exceptions
                raise
            except Exception as e:
                error_msg = str(e)
                logger.error(
                    "Gmail connection failed",
                    error=error_msg,
                    attempt=attempt + 1,
                    task_id=self.task_id,
                )
                
                if attempt == max_retries:
                    # Last attempt failed
                    self.health_status = AdapterHealthStatus(
                        status=AdapterStatus.ERROR,
                        error_message=error_msg,
                    )
                    raise TemporaryAuthError(f"Gmail connection error: {error_msg}") from e

    async def disconnect(self) -> None:
        """Close Gmail connection."""
        self.service = None
        self.credentials = None
        self.health_status = AdapterHealthStatus(status=AdapterStatus.DISCONNECTED)
        logger.info("Gmail connection closed")

    async def mark_email_as_read(self, message_id: str) -> bool:
        """Mark a Gmail message as read by removing the UNREAD label.

        Args:
            message_id: Gmail message ID to mark as read

        Returns:
            True if successful, False if failed
        """
        if not self.service:
            logger.warning("Gmail adapter not connected, cannot mark email as read", message_id=message_id)
            return False

        try:
            import asyncio

            # Run the synchronous Gmail API call in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()
            )
            logger.info("Email marked as read", message_id=message_id)
            return True
        except Exception as e:
            logger.warning(
                "Failed to mark email as read",
                message_id=message_id,
                error=str(e),
            )
            return False

    def get_oauth_config(self) -> Optional[Dict[str, Any]]:
        """Return updated OAuth config with potentially refreshed token.
        
        Returns:
            Updated oauth_config dict with latest access_token/refresh_token
        """
        if not self.credentials:
            return None

        return {
            "access_token": self.credentials.token,
            "refresh_token": self.credentials.refresh_token,
            "token_uri": self.credentials.token_uri,
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
            "scopes": list(self.credentials.scopes or []),
        }

    async def fetch_data(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch emails with Excel attachments.

        Returns:
            List of email records with attachment data.
        """
        if not self.service:
            raise RuntimeError("Gmail adapter not connected")

        logger.info("Fetching emails with attachments")

        try:
            self.health_status = AdapterHealthStatus(status=AdapterStatus.FETCHING)

            base_query = kwargs.get("query") or settings.gmail_inbox_query or "in:inbox"  # Default to inbox emails if no query specified
            sender_filter = kwargs.get("sender_filter")
            subject_pattern = kwargs.get("subject_pattern")
            max_results = int(kwargs.get("max_results") or 10)
            source_type = kwargs.get("source_type", "attachment")
            link_regex = kwargs.get("link_regex") or r"https?://\S+"
            allowed_extensions = kwargs.get("allowed_extensions")  # List of file extensions to allow (e.g., ['xlsx', 'csv'])

            query_parts = [base_query]
            if sender_filter:
                query_parts.append(f'from:"{sender_filter}"')
            query = " ".join(part for part in query_parts if part).strip()
            
            logger.info("Gmail API query", query=query, max_results=max_results, sender_filter=sender_filter)

            results = self.service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
            
            logger.info("Gmail API response", total_results=results.get("resultSizeEstimate", 0), message_count=len(results.get("messages", [])))

            messages = results.get("messages", [])
            email_records = []

            for message in messages:
                msg_id = message["id"]
                msg_data = self.service.users().messages().get(userId="me", id=msg_id, format="full").execute()

                # Extract email metadata
                headers = msg_data["payload"].get("headers", [])
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
                from_addr = next((h["value"] for h in headers if h["name"] == "From"), "")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "")

                if subject_pattern and not self._subject_matches(subject, subject_pattern):
                    continue

                if source_type == "download_link":
                    html_body, text_body = self._get_raw_body(msg_data.get("payload", {}))
                    download_links = self._extract_links_from_body(html_body, text_body, link_regex)
                    if download_links:
                        email_records.append(
                            {
                                "message_id": msg_id,
                                "subject": subject,
                                "from": from_addr,
                                "date": date,
                                "download_links": download_links,
                            }
                        )
                        self.health_status.records_processed += 1
                    else:
                        logger.warning("No download links found in email", subject=subject)
                else:
                    # Default: attachment mode
                    attachments = await self._extract_attachments(msg_id, msg_data.get("payload", {}), allowed_extensions)
                    if attachments:
                        email_records.append(
                            {
                                "message_id": msg_id,
                                "subject": subject,
                                "from": from_addr,
                                "date": date,
                                "attachments": attachments,
                            }
                        )
                    self.health_status.records_processed += 1

            self.health_status = AdapterHealthStatus(status=AdapterStatus.CONNECTED)
            logger.info("Emails fetched successfully", count=len(email_records))

            return email_records

        except Exception as e:
            logger.error("Error fetching emails", error=str(e))
            self.health_status = AdapterHealthStatus(
                status=AdapterStatus.ERROR,
                error_message=str(e),
            )
            raise

    def _get_raw_body(self, payload: Dict) -> tuple:
        """Extract (html_body, text_body) from an email payload, recursing through parts."""
        html_body = ""
        text_body = ""

        def _recurse(part: Dict) -> None:
            nonlocal html_body, text_body
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if data:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                if mime == "text/html" and not html_body:
                    html_body = decoded
                elif mime == "text/plain" and not text_body:
                    text_body = decoded
            for subpart in part.get("parts", []):
                _recurse(subpart)

        _recurse(payload)
        return html_body, text_body

    @staticmethod
    def _extract_links_from_body(html_body: str, text_body: str, link_regex: str) -> List[str]:
        """Find URLs in the email body, unwrap Safe Links, and filter by regex.

        If link_regex is invalid, falls back to accepting any HTTP(S) URL.
        """
        html_body = html_body or ""
        text_body = text_body or ""

        raw_candidates: List[str] = []
        href_matches = re.findall(r'href=["\']([^"\']+)["\']', html_body, flags=re.IGNORECASE)
        raw_candidates.extend(href_matches)
        raw_candidates.extend(re.findall(r"https?://[^\s<>'\"]+", html_body, flags=re.IGNORECASE))
        raw_candidates.extend(re.findall(r"https?://[^\s<>'\"]+", text_body, flags=re.IGNORECASE))

        try:
            url_filter = re.compile(link_regex, flags=re.IGNORECASE)
        except re.error:
            logger.warning("Invalid link_regex, using generic URL filter", link_regex=link_regex)
            url_filter = re.compile(r"https?://\S+", flags=re.IGNORECASE)

        seen: set[str] = set()
        unique: List[str] = []
        for candidate in raw_candidates:
            url = GmailAdapter._normalize_email_url(candidate)
            if not url or not url_filter.search(url):
                continue
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    @staticmethod
    def _normalize_email_url(url: str) -> str:
        """Clean email URLs and unwrap Outlook Safe Links to the actual target URL."""
        cleaned = unescape((url or "").strip()).rstrip(">\"')].,;")
        if not cleaned.lower().startswith(("http://", "https://")):
            return ""

        parsed = urlparse(cleaned)
        host = parsed.netloc.lower()
        if host.endswith("safelinks.protection.outlook.com"):
            wrapped = parse_qs(parsed.query).get("url", [])
            if wrapped:
                cleaned = unquote(wrapped[0]).strip()
                cleaned = unescape(cleaned).rstrip(">\"')].,;")
        return cleaned

    @staticmethod
    def _subject_matches(subject: str, pattern: str) -> bool:
        """Return True if subject matches pattern.

        Uses case-insensitive regex. If regex is invalid, falls back to case-insensitive substring.
        """
        if not pattern:
            return True

        try:
            return re.search(pattern, subject or "", flags=re.IGNORECASE) is not None
        except re.error:
            return pattern.lower() in (subject or "").lower()

    async def _extract_attachments(self, message_id: str, payload: Dict, allowed_extensions: List[str] = None) -> List[Dict[str, Any]]:
        """Extract attachments from a message payload, optionally filtered by extension.

        Args:
            message_id: Gmail message ID.
            payload: Message payload dict.
            allowed_extensions: List of file extensions to include (e.g., ['xlsx', 'csv']). None = all files.

        Returns:
            List of attachment dicts with data.
        """
        import os
        if allowed_extensions:
            allowed_extensions = [ext.lower().lstrip('.') for ext in allowed_extensions]
        service = self.service
        if service is None:
            raise RuntimeError("Gmail adapter not connected")

        attachments = []

        parts = payload.get("parts", [])
        for part in parts:
            if part["filename"]:
                filename = part["filename"]
                # Check extension filter if provided
                if allowed_extensions:
                    file_ext = os.path.splitext(filename)[1].lower().lstrip('.')
                    if file_ext not in allowed_extensions:
                        logger.info("Attachment skipped - extension not allowed", filename=filename, extension=file_ext)
                        continue
                attachment_id = part["body"].get("attachmentId")

                if attachment_id:
                    try:
                        # Get attachment data
                        attachment_data = (
                            service.users()
                            .messages()
                            .attachments()
                            .get(userId="me", messageId=message_id, id=attachment_id)
                            .execute()
                        )

                        file_data = base64.urlsafe_b64decode(attachment_data.get("data", b""))

                        attachments.append(
                            {
                                "filename": filename,
                                "mimetype": part.get("mimeType", ""),
                                "data": file_data,
                            }
                        )

                        logger.info("Attachment extracted", filename=filename)

                    except Exception as e:
                        logger.error("Failed to extract attachment", filename=filename, error=str(e))
                        self.health_status.records_failed += 1

        return attachments

    async def fetch_single_email(
        self,
        message_id: str,
        source_type: str = "attachment",
        link_regex: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single email by message_id for retry processing.

        Used when retrying a failed email. Fetches the email again following the
        same retrieval logic as fetch_data.

        Args:
            message_id: Gmail message ID
            source_type: "attachment" or "download_link"
            link_regex: Regex pattern for link extraction
            allowed_extensions: List of allowed file extensions

        Returns:
            Email record dict, or None if email not found or no attachments/links
        """
        if not self.service:
            raise RuntimeError("Gmail adapter not connected")

        logger.info("Fetching single email for retry", message_id=message_id)

        try:
            # Fetch the message
            msg_data = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()

            # Extract email metadata
            headers = msg_data["payload"].get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            from_addr = next((h["value"] for h in headers if h["name"] == "From"), "")
            date = next((h["value"] for h in headers if h["name"] == "Date"), "")

            if source_type == "download_link":
                html_body, text_body = self._get_raw_body(msg_data.get("payload", {}))
                link_regex = link_regex or r"https?://\S+"
                download_links = self._extract_links_from_body(html_body, text_body, link_regex)

                if download_links:
                    return {
                        "message_id": message_id,
                        "subject": subject,
                        "from": from_addr,
                        "date": date,
                        "download_links": download_links,
                    }
                return None
            else:
                # Default: attachment mode
                attachments = await self._extract_attachments(
                    message_id, msg_data.get("payload", {}), allowed_extensions
                )

                if attachments:
                    return {
                        "message_id": message_id,
                        "subject": subject,
                        "from": from_addr,
                        "date": date,
                        "attachments": attachments,
                    }
                return None

        except Exception as e:
            logger.error(
                "Error fetching single email for retry",
                message_id=message_id,
                error=str(e),
            )
            self.health_status = AdapterHealthStatus(
                status=AdapterStatus.ERROR,
                error_message=str(e),
            )
            raise

    async def get_status(self) -> AdapterHealthStatus:
        """Get adapter health status."""
        return self.health_status
