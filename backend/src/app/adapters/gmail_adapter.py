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

# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]


class GmailAdapter(DataAdapter):
    """Adapter for fetching analytics reports from Gmail."""

    def __init__(self, oauth_config: Optional[Dict[str, Any]] = None):
        """Initialize Gmail adapter."""
        super().__init__(name="gmail_adapter")
        self.service = None
        self.credentials = None
        self.oauth_config = oauth_config or {}

    async def connect(self) -> None:
        """Establish connection to Gmail API."""
        try:
            logger.info("Connecting to Gmail API using OAuth user credentials")

            refresh_token = self.oauth_config.get("refresh_token")
            if not refresh_token:
                raise ValueError("Missing Gmail OAuth refresh_token in task adaptor_config.gmail_oauth")

            client_id = self.oauth_config.get("client_id") or settings.gmail_oauth_client_id
            client_secret = self.oauth_config.get("client_secret") or settings.gmail_oauth_client_secret
            token_uri = self.oauth_config.get("token_uri") or settings.gmail_oauth_token_uri
            scopes = self.oauth_config.get("scopes") or GMAIL_SCOPES

            if not client_id or not client_secret:
                raise ValueError("Missing Gmail OAuth client credentials (gmail_oauth_client_id/client_secret)")

            self.credentials = Credentials(
                token=self.oauth_config.get("access_token"),
                refresh_token=refresh_token,
                token_uri=token_uri,
                client_id=client_id,
                client_secret=client_secret,
                scopes=scopes,
            )

            # Ensure an access token is available and refreshed.
            if not self.credentials.valid:
                self.credentials.refresh(Request())

            # Build Gmail service
            self.service = build("gmail", "v1", credentials=self.credentials)

            # Test connection
            profile = self.service.users().getProfile(userId="me").execute()
            logger.info("Gmail connection successful", email_address=profile.get("emailAddress"))

            self.health_status = AdapterHealthStatus(status=AdapterStatus.CONNECTED)

        except Exception as e:
            logger.error("Failed to connect to Gmail API", error=str(e))
            self.health_status = AdapterHealthStatus(
                status=AdapterStatus.ERROR,
                error_message=str(e),
            )
            raise

    async def disconnect(self) -> None:
        """Close Gmail connection."""
        self.service = None
        self.credentials = None
        self.health_status = AdapterHealthStatus(status=AdapterStatus.DISCONNECTED)
        logger.info("Gmail connection closed")

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

            base_query = kwargs.get("query") or settings.gmail_inbox_query
            sender_filter = kwargs.get("sender_filter")
            subject_pattern = kwargs.get("subject_pattern")
            max_results = int(kwargs.get("max_results") or 10)
            source_type = kwargs.get("source_type", "attachment")
            link_regex = kwargs.get("link_regex") or r"https?://\S+"

            query_parts = [base_query]
            if sender_filter:
                query_parts.append(f'from:"{sender_filter}"')
            query = " ".join(part for part in query_parts if part).strip()

            results = self.service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()

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
                    attachments = await self._extract_attachments(msg_id, msg_data.get("payload", {}))
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

    def get_oauth_config(self) -> Dict[str, Any]:
        """Get refreshed OAuth config from active credentials."""
        if not self.credentials:
            return dict(self.oauth_config)
        return {
            "access_token": self.credentials.token,
            "refresh_token": self.credentials.refresh_token,
            "token_uri": self.credentials.token_uri,
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret or self.oauth_config.get("client_secret"),
            "scopes": list(self.credentials.scopes or []),
        }

    @staticmethod
    def _get_raw_body(payload: Dict) -> tuple:
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

    async def _extract_attachments(self, message_id: str, payload: Dict) -> List[Dict[str, Any]]:
        """Extract attachments from a message payload.

        Args:
            message_id: Gmail message ID.
            payload: Message payload dict.

        Returns:
            List of attachment dicts with data.
        """
        service = self.service
        if service is None:
            raise RuntimeError("Gmail adapter not connected")

        attachments = []

        parts = payload.get("parts", [])
        for part in parts:
            if part["filename"]:
                filename = part["filename"]
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

    async def get_status(self) -> AdapterHealthStatus:
        """Get adapter health status."""
        return self.health_status
