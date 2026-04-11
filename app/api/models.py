"""
Pydantic request / response models for all channel intake endpoints.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class NormalizedTicketEvent(BaseModel):
    """
    Canonical schema published to Kafka topic fte.tickets.incoming.
    Every channel handler produces this shape.
    """
    channel: str                        # 'web_form' | 'email' | 'whatsapp'
    channel_message_id: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
    subject: Optional[str] = None
    content: str
    category: Optional[str] = None
    priority: str = "medium"
    received_at: str                    # ISO-8601
    metadata: dict = {}


# ---------------------------------------------------------------------------
# Web Form
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {"general", "technical", "billing", "feedback", "bug_report"}
VALID_PRIORITIES = {"low", "medium", "high"}


class WebFormSubmission(BaseModel):
    name: str
    email: EmailStr
    subject: str
    category: str = "general"
    priority: str = "medium"
    message: str
    attachments: list[str] = []         # Base64-encoded files or URLs

    @field_validator("name")
    @classmethod
    def name_min_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return v

    @field_validator("subject")
    @classmethod
    def subject_min_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Subject must be at least 5 characters.")
        return v

    @field_validator("message")
    @classmethod
    def message_min_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters.")
        return v

    @field_validator("category")
    @classmethod
    def category_valid(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {VALID_CATEGORIES}")
        return v

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"Priority must be one of: {VALID_PRIORITIES}")
        return v

    def to_ticket_event(self, ticket_id: str) -> NormalizedTicketEvent:
        return NormalizedTicketEvent(
            channel="web_form",
            channel_message_id=ticket_id,
            customer_email=str(self.email),
            customer_name=self.name,
            subject=self.subject,
            content=self.message,
            category=self.category,
            priority=self.priority,
            received_at=datetime.now(timezone.utc).isoformat(),
            metadata={"form_version": "1.0", "attachments": self.attachments},
        )


class WebFormResponse(BaseModel):
    ticket_id: str
    message: str
    estimated_response_time: str


# ---------------------------------------------------------------------------
# Gmail (Google Pub/Sub push notification)
# ---------------------------------------------------------------------------

class PubSubMessage(BaseModel):
    data: str           # Base64-encoded Gmail history notification
    messageId: str
    publishTime: Optional[str] = None


class GmailPushNotification(BaseModel):
    message: PubSubMessage
    subscription: str


# ---------------------------------------------------------------------------
# WhatsApp / Twilio
# ---------------------------------------------------------------------------

class WhatsAppWebhookForm(BaseModel):
    """
    Mirrors Twilio's form-encoded webhook payload.
    Fields are declared with Twilio's exact casing.
    """
    MessageSid: str
    From: str           # e.g. 'whatsapp:+1234567890'
    Body: str
    ProfileName: Optional[str] = None
    NumMedia: str = "0"
    WaId: Optional[str] = None
    SmsStatus: Optional[str] = None

    def to_ticket_event(self) -> NormalizedTicketEvent:
        phone = self.From.replace("whatsapp:", "")
        return NormalizedTicketEvent(
            channel="whatsapp",
            channel_message_id=self.MessageSid,
            customer_phone=phone,
            customer_name=self.ProfileName,
            content=self.Body,
            received_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "num_media": self.NumMedia,
                "wa_id": self.WaId,
                "status": self.SmsStatus,
            },
        )
