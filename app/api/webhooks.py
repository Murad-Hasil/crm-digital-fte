"""
Channel intake webhooks.

Routes:
  POST /webhooks/webform          — Web support form submission
  GET  /support/ticket/{id}       — Ticket status check
  POST /webhooks/gmail            — Gmail Pub/Sub push notification
  POST /webhooks/whatsapp         — Twilio WhatsApp webhook
  POST /webhooks/whatsapp/status  — Twilio delivery status callback
"""

import base64
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import Response

from app.api.models import (
    GmailPushNotification,
    NormalizedTicketEvent,
    WebFormResponse,
    WebFormSubmission,
    WhatsAppWebhookForm,
)
from app.core.kafka import kafka_producer, TOPIC_TICKETS_INCOMING

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _publish(event: NormalizedTicketEvent, background_tasks: BackgroundTasks) -> None:
    """Push the normalized event to Kafka as a background task so the webhook
    can return immediately (< 200 ms acknowledgement to external services)."""
    background_tasks.add_task(
        kafka_producer.publish_ticket,
        event.model_dump(),
    )


# ---------------------------------------------------------------------------
# Web Form
# ---------------------------------------------------------------------------

@router.post("/webhooks/webform", response_model=WebFormResponse)
async def submit_web_form(
    submission: WebFormSubmission,
    background_tasks: BackgroundTasks,
) -> WebFormResponse:
    """
    Accept a Web Support Form submission.
    1. Validate via Pydantic.
    2. Generate ticket_id.
    3. Publish normalized event to Kafka.
    4. Return confirmation immediately.
    """
    ticket_id = str(uuid.uuid4())
    event = submission.to_ticket_event(ticket_id)
    await _publish(event, background_tasks)

    logger.info("WebForm ticket queued: ticket_id=%s email=%s", ticket_id, submission.email)
    return WebFormResponse(
        ticket_id=ticket_id,
        message="Thank you for contacting us! Our AI assistant will respond shortly.",
        estimated_response_time="Usually within 5 minutes",
    )


@router.get("/support/ticket/{ticket_id}")
async def get_ticket_status(ticket_id: str) -> dict:
    """
    Return the current status of a ticket.
    Full DB lookup wired in Step 7 (agent worker); returns pending state for now.
    """
    return {
        "ticket_id": ticket_id,
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


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
    DB update wired in Step 7.
    """
    form = dict(await request.form())
    message_sid = form.get("MessageSid", "")
    status = form.get("MessageStatus", "unknown")
    logger.info("WhatsApp delivery status: sid=%s status=%s", message_sid, status)
    return {"status": "received"}
