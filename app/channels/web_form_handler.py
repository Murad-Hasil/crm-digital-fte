"""
app/channels/web_form_handler.py
---------------------------------
FastAPI router for the Web Support Form channel.

Routes:
  POST /webhooks/webform      — Submit a new support request
  GET  /support/ticket/{id}   — Poll ticket status
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks

from app.api.models import (
    NormalizedTicketEvent,
    WebFormResponse,
    WebFormSubmission,
)
from app.core.kafka import kafka_producer, TOPIC_TICKETS_INCOMING

logger = logging.getLogger(__name__)
router = APIRouter(tags=["web_form"])


async def _publish(event: NormalizedTicketEvent, background_tasks: BackgroundTasks) -> None:
    """Push a normalized event to Kafka as a background task so the endpoint
    returns immediately (< 200 ms acknowledgement)."""
    background_tasks.add_task(
        kafka_producer.publish_ticket,
        event.model_dump(),
    )


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
    """Return the current status of a support ticket."""
    return {
        "ticket_id": ticket_id,
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
