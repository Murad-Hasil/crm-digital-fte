"""
Channel intake webhooks — Gmail and WhatsApp.

Routes:
  POST /webhooks/gmail            — Gmail Pub/Sub push notification
  POST /webhooks/whatsapp         — Twilio WhatsApp inbound message
  POST /webhooks/whatsapp/status  — Twilio delivery status callback

Web Form routes live in app/channels/web_form_handler.py.
"""

import base64
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response

from app.api.models import (
    GmailPushNotification,
    NormalizedTicketEvent,
    WhatsAppWebhookForm,
)
from app.core.kafka import kafka_producer, TOPIC_TICKETS_INCOMING

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _publish(event: NormalizedTicketEvent, background_tasks: BackgroundTasks) -> None:
    """Push the normalized event to Kafka as a background task so the webhook
    can return immediately (< 200 ms acknowledgement to external services)."""
    background_tasks.add_task(
        kafka_producer.publish_ticket,
        event.model_dump(),
    )


# ---------------------------------------------------------------------------
# Gmail (Google Pub/Sub push)
# ---------------------------------------------------------------------------

@router.post("/webhooks/gmail")
async def gmail_webhook(
    notification: GmailPushNotification,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Receive Gmail push notifications via Google Cloud Pub/Sub.
    The Pub/Sub message.data field is base64-encoded JSON containing
    the Gmail historyId. Full message fetch happens in the background task.
    """
    try:
        raw = base64.urlsafe_b64decode(notification.message.data + "==")
        payload = json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to decode Pub/Sub payload: %s", exc)
        # Return 200 so Pub/Sub does not retry a malformed message
        return {"status": "ignored", "reason": "decode_error"}

    history_id: str = payload.get("historyId", "")
    email_address: str = payload.get("emailAddress", "")

    event = NormalizedTicketEvent(
        channel="email",
        channel_message_id=notification.message.messageId,
        customer_email=email_address,
        content=f"[Gmail push] historyId={history_id} — full fetch pending",
        received_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "history_id": history_id,
            "pubsub_message_id": notification.message.messageId,
            "subscription": notification.subscription,
        },
    )
    await _publish(event, background_tasks)

    logger.info("Gmail notification queued: historyId=%s", history_id)
    return {"status": "processed", "history_id": history_id}


# ---------------------------------------------------------------------------
# WhatsApp / Twilio
# ---------------------------------------------------------------------------

async def _parse_twilio_form(request: Request) -> WhatsAppWebhookForm:
    """Parse Twilio's form-encoded body into the WhatsAppWebhookForm model."""
    form = await request.form()
    data = dict(form)
    try:
        return WhatsAppWebhookForm(**data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _validate_twilio_signature(request: Request) -> None:
    """
    Validate the X-Twilio-Signature header.
    Skipped in development; enforced in production.
    """
    import os
    if os.getenv("ENVIRONMENT", "development") == "development":
        return

    try:
        from twilio.request_validator import RequestValidator
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        validator = RequestValidator(auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        form = dict(await request.form())
        url = str(request.url)
        if not validator.validate(url, form, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    except ImportError:
        logger.warning("twilio package not installed — skipping signature validation")


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    Receive inbound WhatsApp messages from Twilio.
    Returns an empty TwiML response so Twilio does not auto-reply.
    The agent worker sends the actual reply asynchronously.
    """
    await _validate_twilio_signature(request)
    form = await _parse_twilio_form(request)
    event = form.to_ticket_event()
    await _publish(event, background_tasks)

    logger.info(
        "WhatsApp message queued: sid=%s from=%s",
        form.MessageSid,
        form.From,
    )
    # Empty TwiML — agent sends its own reply via Twilio REST API
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@router.post("/webhooks/whatsapp/status")
async def whatsapp_status_webhook(request: Request) -> dict:
    """
    Receive Twilio delivery status callbacks (sent, delivered, failed).
    """
    form = dict(await request.form())
    message_sid = form.get("MessageSid", "")
    status = form.get("MessageStatus", "unknown")
    logger.info("WhatsApp delivery status: sid=%s status=%s", message_sid, status)
    return {"status": "received"}
