"""SMTP email service."""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """Service to send transactional emails via SMTP."""

    async def send_password_reset_email(self, to_email: str, reset_token: str, username: str) -> bool:
        """Send a password reset email with a tokenized reset link."""
        try:
            reset_link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={reset_token}"
            subject = "Password Reset Request - Agentic Beast"
            text_content = (
                f"Hello {username},\\n\\n"
                "You requested a password reset.\\n"
                f"Use this link to reset your password: {reset_link}\\n\\n"
                f"This link expires in {settings.password_reset_token_ttl_minutes} minutes.\\n"
                "If you did not request this, ignore this email."
            )

            html_content = f"""
<html>
  <body style=\"font-family: Arial, sans-serif; color: #1f2937;\">
    <p>Hello {username},</p>
    <p>You requested a password reset.</p>
    <p><a href=\"{reset_link}\">Reset Password</a></p>
    <p>This link expires in {settings.password_reset_token_ttl_minutes} minutes.</p>
    <p>If you did not request this, ignore this email.</p>
  </body>
</html>
"""

            await asyncio.to_thread(
                self._send,
                to_email,
                subject,
                text_content,
                html_content,
            )
            logger.info("Password reset email sent", to_email=to_email)
            return True
        except Exception as e:
            logger.error("Failed to send password reset email", to_email=to_email, error=str(e))
            return False

    def _send(self, to_email: str, subject: str, text_content: str, html_content: str) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        message["To"] = to_email

        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)


_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """Get singleton email service."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
