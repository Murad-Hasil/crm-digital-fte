"""
Unified Message Processor — Kafka consumer + AI agent orchestrator.

Flow per message:
  1. Deserialize NormalizedTicketEvent from fte.tickets.incoming
  2. Resolve or create Customer record
  3. Get or create Conversation
  4. Store inbound Message
  5. Pre-agent guardrail check  (pricing / refund / legal / sentiment)
  6. Load conversation history for agent
  7. Set ProcessingContext (contextvars)
  8. Run customer_success_agent via Runner
  9. Record latency metric
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
# Customer & Conversation resolution
# ---------------------------------------------------------------------------

async def _resolve_customer(conn, message: dict) -> str:
    """Return existing customer_id or create a new customer record."""
    email = message.get("customer_email")
    phone = message.get("customer_phone")

    if email:
        row = await conn.fetchrow("SELECT id FROM public.customers WHERE email = $1", email)
        if row:
            return str(row["id"])
        cid = await conn.fetchval(
            "INSERT INTO public.customers (email, name) VALUES ($1, $2) RETURNING id",
            email,
            message.get("customer_name", ""),
        )
        return str(cid)

    if phone:
        row = await conn.fetchrow(
            """
            SELECT customer_id FROM public.customer_identifiers
            WHERE identifier_type = 'whatsapp' AND identifier_value = $1
            """,
            phone,
        )
        if row:
            return str(row["customer_id"])
        cid = await conn.fetchval(
            "INSERT INTO public.customers (phone) VALUES ($1) RETURNING id", phone
        )
        await conn.execute(
            """
            INSERT INTO public.customer_identifiers (customer_id, identifier_type, identifier_value)
            VALUES ($1, 'whatsapp', $2)
            """,
            cid,
            phone,
        )
        return str(cid)

    raise ValueError("Cannot resolve customer: no email or phone in message.")


async def _get_or_create_conversation(conn, customer_id: str, channel: str) -> str:
    """Return an active conversation (last 24 h) or create a new one."""
    row = await conn.fetchrow(
        """
        SELECT id FROM public.conversations
        WHERE customer_id = $1
          AND status = 'active'
          AND started_at > NOW() - INTERVAL '24 hours'
        ORDER BY started_at DESC
        LIMIT 1
        """,
        customer_id,
    )
    if row:
        return str(row["id"])

    conv_id = await conn.fetchval(
        """
        INSERT INTO public.conversations (customer_id, initial_channel, status)
        VALUES ($1, $2, 'active')
        RETURNING id
        """,
        customer_id,
        channel,
    )
    return str(conv_id)


async def _load_history(conn, conversation_id: str) -> list[dict]:
    """Load messages for the current conversation as OpenAI-style message dicts."""
    rows = await conn.fetch(
        """
        SELECT role, content FROM public.messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        """,
        conversation_id,
    )
    role_map = {"agent": "assistant", "customer": "user"}
    return [{"role": role_map.get(r["role"], r["role"]), "content": r["content"]} for r in rows]


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
            customer_id = await _resolve_customer(conn, raw_message)
        except ValueError as exc:
            logger.error("Customer resolution failed: %s", exc)
            return

        # ── 2. Get / create conversation ─────────────────────────────────
        conversation_id = await _get_or_create_conversation(conn, customer_id, channel)

        # ── 3. Store inbound message ─────────────────────────────────────
        await conn.execute(
            """
            INSERT INTO public.messages
                (conversation_id, channel, direction, role, content,
                 channel_message_id, delivery_status)
            VALUES ($1, $2, 'inbound', 'user', $3, $4, 'delivered')
            """,
            conversation_id,
            channel,
            content,
            raw_message.get("channel_message_id"),
        )

        # ── 4. Pre-agent guardrail check ─────────────────────────────────
        should_escalate, reason = _check_guardrails(content)
        if should_escalate:
            logger.info("Guardrail triggered: channel=%s reason=%s", channel, reason)
            ticket_id = await conn.fetchval(
                """
                INSERT INTO public.tickets
                    (conversation_id, customer_id, source_channel, category, priority, status)
                VALUES ($1, $2, $3, 'escalated', 'high', 'escalated')
                RETURNING id
                """,
                conversation_id,
                customer_id,
                channel,
            )
            await conn.execute(
                "UPDATE public.conversations SET status = 'escalated', escalated_to = 'human_agent' WHERE id = $1",
                conversation_id,
            )
            logger.info("Auto-escalated ticket %s | reason=%s", ticket_id, reason)
            return

        # ── 5. Load conversation history for agent ───────────────────────
        history = await _load_history(conn, conversation_id)

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

    # ── 7. Run agent ──────────────────────────────────────────────────────
    try:
        result = await Runner.run(customer_success_agent, input=history)
        logger.info("Agent completed | channel=%s output_len=%d", channel, len(result.final_output or ""))
    except Exception as exc:
        logger.error("Agent run failed: %s", exc)
        return

    # ── 8. Record latency metric ──────────────────────────────────────────
    latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.agent_metrics (metric_name, metric_value, channel)
            VALUES ('response_latency_ms', $1, $2)
            """,
            latency_ms,
            channel,
        )
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
