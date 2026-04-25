"""
Unified Message Processor — Kafka consumer + AI agent orchestrator.

Flow per message:
  1. Deserialize NormalizedTicketEvent from fte.tickets.incoming
  2. Resolve or create Customer record        → app.db.queries
  3. Get or create Conversation               → app.db.queries
  4. Store inbound Message                    → app.db.queries
  5. Pre-agent guardrail check (pricing / refund / legal / sentiment)
  6. Load conversation history for agent      → app.db.queries
  7. Set ProcessingContext (contextvars)
  8. Run customer_success_agent via Runner
  9. Record latency metric                    → app.db.queries
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from aiokafka import AIOKafkaConsumer

from app.agents.customer_success_agent import customer_success_agent, init_agent
from app.agents.tools import ProcessingContext, set_processing_context
from app.db.queries import (
    create_escalation_ticket,
    get_or_create_conversation,
    load_history,
    record_latency_metric,
    resolve_customer,
    store_inbound_message,
    update_conversation_escalated,
)
from app.db.session import get_db_pool, init_db_pool

try:
    from agents import Runner
except ImportError as exc:
    raise ImportError("Install the openai-agents package: pip install openai-agents") from exc

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

TOPIC = "fte.tickets.incoming"
GROUP_ID = "fte-message-processor"

# ---------------------------------------------------------------------------
# Guardrail keyword sets (pre-LLM, O(1) checks)
# ---------------------------------------------------------------------------
_PRICING_KEYWORDS = {"price", "pricing", "cost", "costs", "how much", "fee", "fees", "subscription", "plan", "plans", "quote"}
_REFUND_KEYWORDS = {"refund", "refunds", "money back", "chargeback", "reimburse", "reimbursement"}
_LEGAL_KEYWORDS = {"lawyer", "attorney", "legal", "sue", "lawsuit", "court"}
_HUMAN_REQUEST_KEYWORDS = {"human", "agent", "person", "representative", "speak to someone"}
_PROFANITY_KEYWORDS = {"fuck", "shit", "asshole", "bastard", "damn", "crap"}


def _check_guardrails(content: str) -> tuple[bool, str]:
    """
    Fast pre-agent guardrail scan.
    Returns (should_escalate: bool, reason: str).
    """
    lowered = content.lower()

    if any(kw in lowered for kw in _PRICING_KEYWORDS):
        return True, "pricing_inquiry"
    if any(kw in lowered for kw in _REFUND_KEYWORDS):
        return True, "refund_request"
    if any(kw in lowered for kw in _LEGAL_KEYWORDS):
        return True, "legal_threat"
    if any(kw in lowered for kw in _HUMAN_REQUEST_KEYWORDS):
        return True, "customer_requested_human"
    if any(kw in lowered for kw in _PROFANITY_KEYWORDS):
        return True, "aggressive_language"

    return False, ""


# ---------------------------------------------------------------------------
# Core message handler
# ---------------------------------------------------------------------------

async def process_message(raw_message: dict) -> None:
    start_time = datetime.now(timezone.utc)

    channel = raw_message.get("channel", "web_form")
    content = raw_message.get("content", "")
    subject = raw_message.get("subject") or raw_message.get("ticket_subject", "Support Request")

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("SET search_path TO public")

        # ── 1. Resolve customer ──────────────────────────────────────────
        try:
            customer_id = await resolve_customer(conn, raw_message)
        except ValueError as exc:
            logger.error("Customer resolution failed: %s", exc)
            return

        # ── 2. Get / create conversation ─────────────────────────────────
        conversation_id = await get_or_create_conversation(conn, customer_id, channel)

        # ── 3. Store inbound message ─────────────────────────────────────
        await store_inbound_message(
            conn,
            conversation_id,
            channel,
            content,
            raw_message.get("channel_message_id"),
        )

        # ── 4. Pre-agent guardrail check ─────────────────────────────────
        should_escalate, reason = _check_guardrails(content)
        if should_escalate:
            logger.info("Guardrail triggered: channel=%s reason=%s", channel, reason)
            ticket_id = await create_escalation_ticket(conn, conversation_id, customer_id, channel)
            await update_conversation_escalated(conn, conversation_id)
            logger.info("Auto-escalated ticket %s | reason=%s", ticket_id, reason)
            return

        # ── 5. Load conversation history for agent ───────────────────────
        history = await load_history(conn, conversation_id)

    # ── 6. Set processing context (contextvars) ──────────────────────────
    ctx = ProcessingContext(
        customer_id=customer_id,
        conversation_id=conversation_id,
        channel=channel,
        ticket_subject=subject,
        customer_email=raw_message.get("customer_email"),
        customer_phone=raw_message.get("customer_phone"),
        gmail_thread_id=raw_message.get("metadata", {}).get("thread_id"),
    )
    set_processing_context(ctx)

    # Append current inbound message for the agent
    history.append({"role": "user", "content": content})

    # ── 7. Run agent (up to 3 attempts — Groq tool_use_failed is intermittent) ──
    result = None
    for attempt in range(1, 4):
        try:
            result = await Runner.run(customer_success_agent, input=history)
            logger.info("Agent completed | channel=%s attempt=%d output_len=%d",
                        channel, attempt, len(result.final_output or ""))
            break
        except Exception as exc:
            logger.warning("Agent attempt %d/3 failed: %s", attempt, exc)
            if attempt == 3:
                logger.error("Agent run failed after 3 attempts — dropping message.")
                return
            await asyncio.sleep(2 ** attempt)   # 2s, 4s backoff

    # ── 8. Record latency metric ──────────────────────────────────────────
    latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await record_latency_metric(conn, latency_ms, channel)
    logger.info("Message processed | channel=%s latency=%dms", channel, latency_ms)


# ---------------------------------------------------------------------------
# Kafka consumer loop
# ---------------------------------------------------------------------------

async def main() -> None:
    """Entry point for the worker process."""
    await init_db_pool()
    init_agent()   # registers Groq client with the Agents SDK

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=bootstrap,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    logger.info("Worker started — listening on %s", TOPIC)

    try:
        async for msg in consumer:
            try:
                await process_message(msg.value)
            except Exception as exc:
                import traceback
                logger.error("Unhandled error processing message: %s\n%s", exc, traceback.format_exc())
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
