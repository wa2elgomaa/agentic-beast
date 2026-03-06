"""Gmail adapter for fetching analytics report emails."""

import base64
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.adapters.base import AdapterHealthStatus, AdapterStatus, DataAdapter
from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]


class GmailAdapter(DataAdapter):
    """Adapter for fetching analytics reports from Gmail."""

    def __init__(self):
        """Initialize Gmail adapter."""
        super().__init__(name="gmail_adapter")
        self.service = None
        self.credentials = None

    async def connect(self) -> None:
        """Establish connection to Gmail API."""
        try:
            logger.info("Connecting to Gmail API", credentials_path=settings.gmail_credentials_path)

            # Load service account credentials
            self.credentials = Credentials.from_service_account_file(
                settings.gmail_credentials_path,
                scopes=GMAIL_SCOPES,
            )

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

            # Search for emails with attachments
            query = settings.gmail_inbox_query
            results = self.service.users().messages().list(userId="me", q=query, maxResults=10).execute()

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

                # Extract attachments
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

    async def _extract_attachments(self, message_id: str, payload: Dict) -> List[Dict[str, Any]]:
        """Extract attachments from a message payload.

        Args:
            message_id: Gmail message ID.
            payload: Message payload dict.

        Returns:
            List of attachment dicts with data.
        """
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
                            self.service.users()
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
