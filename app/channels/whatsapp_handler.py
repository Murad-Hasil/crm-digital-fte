"""
WhatsApp channel handler — send messages via the Twilio WhatsApp API.
Receiving is handled by the Twilio webhook in app/api/webhooks.py.
"""

import logging
import os

logger = logging.getLogger(__name__)

_WHATSAPP_MAX_LENGTH = 1600


class WhatsAppHandler:
    """Async wrapper around the Twilio REST client for WhatsApp delivery."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        """Lazy-load the Twilio client from environment credentials."""
        if self._client:
            return self._client
        try:
            from twilio.rest import Client
            self._client = Client(
                os.environ["TWILIO_ACCOUNT_SID"],
                os.environ["TWILIO_AUTH_TOKEN"],
            )
        except Exception as exc:
            logger.error("Failed to initialise Twilio client: %s", exc)
            raise
        return self._client

    async def send_message(self, to_phone: str, body: str) -> dict:
        """Send a WhatsApp message via Twilio. Splits messages > 1600 chars."""
        client = self._get_client()
        from_number = os.environ["TWILIO_WHATSAPP_NUMBER"]  # e.g. 'whatsapp:+14155238886'

        if not to_phone.startswith("whatsapp:"):
            to_phone = f"whatsapp:{to_phone}"

        results = []
        for chunk in self._split(body):
            msg = client.messages.create(body=chunk, from_=from_number, to=to_phone)
            results.append({"channel_message_id": msg.sid, "delivery_status": msg.status})
            logger.info("WhatsApp message sent: sid=%s to=%s", msg.sid, to_phone)

        return results[0] if len(results) == 1 else {"chunks": results}

    @staticmethod
    def _split(text: str, max_len: int = _WHATSAPP_MAX_LENGTH) -> list[str]:
        """Split a long message at sentence boundaries."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            cut = text.rfind(". ", 0, max_len)
            if cut == -1:
                cut = text.rfind(" ", 0, max_len)
            if cut == -1:
                cut = max_len
            chunks.append(text[: cut + 1].strip())
            text = text[cut + 1 :].strip()
        return chunks
