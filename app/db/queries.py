"""
app/db/queries.py
-----------------
Centralised DB access layer for the message processor.

All functions accept an asyncpg Connection (not a pool) so callers
control transaction boundaries. Each function sets search_path to
public to stay schema-explicit.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Customer resolution
# ---------------------------------------------------------------------------

async def resolve_customer(conn, message: dict) -> str:
    """Return existing customer_id or create a new customer record.

    Matches on email first, then WhatsApp phone number.
    Raises ValueError if neither identifier is present.
    """
    email: Optional[str] = message.get("customer_email")
    phone: Optional[str] = message.get("customer_phone")

    if email:
        row = await conn.fetchrow(
            "SELECT id FROM public.customers WHERE email = $1", email
        )
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
            INSERT INTO public.customer_identifiers
                (customer_id, identifier_type, identifier_value)
            VALUES ($1, 'whatsapp', $2)
            """,
            cid,
            phone,
        )
        return str(cid)

    raise ValueError("Cannot resolve customer: no email or phone in message.")


# ---------------------------------------------------------------------------
# Conversation management
# ---------------------------------------------------------------------------

async def get_or_create_conversation(conn, customer_id: str, channel: str) -> str:
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


async def update_conversation_escalated(conn, conversation_id: str) -> None:
    """Mark a conversation as escalated to human agent."""
    await conn.execute(
        """
        UPDATE public.conversations
        SET status = 'escalated', escalated_to = 'human_agent'
        WHERE id = $1
        """,
        conversation_id,
    )


# ---------------------------------------------------------------------------
# Message storage
# ---------------------------------------------------------------------------

async def store_inbound_message(
    conn,
    conversation_id: str,
    channel: str,
    content: str,
    channel_message_id: Optional[str] = None,
) -> None:
    """Persist an inbound customer message."""
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
        channel_message_id,
    )


async def load_history(conn, conversation_id: str) -> list[dict]:
    """Load messages for a conversation as OpenAI-style message dicts."""
    rows = await conn.fetch(
        """
        SELECT role, content FROM public.messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        """,
        conversation_id,
    )
    role_map = {"agent": "assistant", "customer": "user"}
    return [
        {"role": role_map.get(r["role"], r["role"]), "content": r["content"]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Ticket management
# ---------------------------------------------------------------------------

async def create_escalation_ticket(
    conn, conversation_id: str, customer_id: str, channel: str
) -> str:
    """Create an escalated ticket and return its ID."""
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
    return str(ticket_id)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

async def record_latency_metric(conn, latency_ms: int, channel: str) -> None:
    """Append a response_latency_ms data point to agent_metrics."""
    await conn.execute(
        """
        INSERT INTO public.agent_metrics (metric_name, metric_value, channel)
        VALUES ('response_latency_ms', $1, $2)
        """,
        latency_ms,
        channel,
    )
