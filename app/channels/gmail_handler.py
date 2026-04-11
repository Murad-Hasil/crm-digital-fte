"""
Gmail channel handler — send replies via the Gmail API (google-api-python-client).
Receiving is handled by the Pub/Sub webhook in app/api/webhooks.py.
"""

import base64
import logging
import os
import re
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class GmailHandler:
    """Thin wrapper around the Gmail v1 REST API for sending replies."""

    def __init__(self) -> None:
        self._service = None

    def _get_service(self):
        """Lazy-load the Gmail API service using stored OAuth2 credentials."""
        if self._service:
            return self._service
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json")
            creds = Credentials.from_authorized_user_file(creds_path)
            self._service = build("gmail", "v1", credentials=creds)
        except Exception as exc:
            logger.error("Failed to initialise Gmail service: %s", exc)
            raise
        return self._service

    def send_reply(
        self,
        to_email: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
    ) -> dict:
        """Send an email reply. Runs synchronously (wrap in run_in_executor for async)."""
        service = self._get_service()

        mime_message = MIMEText(body)
        mime_message["to"] = to_email
        mime_message["subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"

        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")
        send_body: dict = {"raw": raw}
        if thread_id:
            send_body["threadId"] = thread_id

        result = service.users().messages().send(userId="me", body=send_body).execute()
        logger.info("Gmail reply sent: message_id=%s to=%s", result.get("id"), to_email)
        return {"channel_message_id": result["id"], "delivery_status": "sent"}

    @staticmethod
    def extract_email(from_header: str) -> str:
        """Extract bare email address from a 'From' header value."""
        match = re.search(r"<(.+?)>", from_header)
        return match.group(1) if match else from_header
