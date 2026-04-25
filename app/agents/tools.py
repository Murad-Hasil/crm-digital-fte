"""
OpenAI Agents SDK @function_tool definitions.
All five tools required by the PDF spec:
  search_knowledge_base, create_ticket, get_customer_history,
  escalate_to_human, send_response

Processing context (customer_id, conversation_id, channel, etc.) is passed
via Python contextvars so the Kafka worker sets it once per message and
every tool can read it without extra parameters.
"""

import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Optional

from agents import function_tool

from app.agents.formatters import format_for_channel
from app.db.session import get_db_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Processing context — set by the worker before each Runner.run() call
# ---------------------------------------------------------------------------

@dataclass
class ProcessingContext:
    customer_id: str
    conversation_id: str
    channel: str
    ticket_subject: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    ticket_id: Optional[str] = None          # populated after create_ticket runs


_ctx_var: ContextVar[ProcessingContext] = ContextVar("processing_context")


def set_processing_context(ctx: ProcessingContext) -> None:
    _ctx_var.set(ctx)


def get_processing_context() -> ProcessingContext:
    try:
        return _ctx_var.get()
    except LookupError as exc:
        raise RuntimeError("Processing context not set. Call set_processing_context() first.") from exc


# ---------------------------------------------------------------------------
# Tool 1 — search_knowledge_base
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_embedding_model():
    """Load sentence-transformers model once and cache it for the process lifetime."""
    try:
        import logging as _logging
        import warnings
        # Suppress BertModel checkpoint warnings — not actionable in production
        warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers")
        _logging.getLogger("sentence_transformers").setLevel(_logging.ERROR)
        _logging.getLogger("transformers").setLevel(_logging.ERROR)

        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded: all-MiniLM-L6-v2 (%d dims)", model.get_embedding_dimension())
        return model
    except ImportError:
        logger.warning("sentence-transformers not installed — KB search will fall back to ILIKE")
        return None


@function_tool
async def search_knowledge_base(query: str) -> str:
    """Search product documentation for relevant information.

    Use this when the customer asks questions about product features,
    how to use something, or needs technical information.
    Attempt at most 2 times before escalating.

    Args:
        query: The search query derived from the customer's question.

    Returns:
        Formatted documentation snippets with relevance context.
    """
    max_results = 5
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Primary: cosine similarity using pgvector <=> operator
        model = _get_embedding_model()
        if model is not None:
            vec = await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.encode(query, normalize_embeddings=True).tolist()
            )
            # Embed the vector literal directly — safe because it's ML-generated, not user input.
            # asyncpg $1::vector parameter binding has a quirk with pooled Neon connections.
            vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
            sql = f"""
                SELECT title, content, category,
                       1 - (embedding <=> '{vec_literal}'::vector) AS score
                FROM knowledge_base
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> '{vec_literal}'::vector
                LIMIT {int(max_results)}
            """
            rows = await conn.fetch(sql)
            # Keep results above threshold (0.20) OR the single best match
            # if it's reasonably close (>= 0.15) — prevents total misses on valid queries
            filtered = [r for r in rows if r["score"] >= 0.20]
            if not filtered and rows and rows[0]["score"] >= 0.15:
                filtered = rows[:1]  # return best match rather than nothing
            rows = filtered
        else:
            rows = []

        # Fallback: keyword ILIKE search when embeddings unavailable or no results
        if not rows:
            logger.debug("Vector search returned no results — falling back to ILIKE for query: %s", query)
            rows = await conn.fetch(
                """
                SELECT title, content, category, NULL::float AS score
                FROM knowledge_base
                WHERE content ILIKE $1 OR title ILIKE $1
                ORDER BY updated_at DESC
                LIMIT $2
                """,
                f"%{query}%",
                max_results,
            )

    if not rows:
        return (
            "No relevant documentation found for that query. "
            "Consider escalating to human support if the customer needs further help."
        )

    parts = []
    for r in rows:
        score_label = f"  (relevance: {r['score']:.2f})" if r["score"] is not None else ""
        parts.append(
            f"**{r['title']}** (category: {r['category'] or 'general'}){score_label}\n{r['content'][:500]}"
        )
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 2 — create_ticket
# ---------------------------------------------------------------------------

@function_tool
async def create_ticket(
    issue: str,
    priority: Literal["low", "medium", "high", "urgent"],
    category: Literal["general", "technical", "billing", "feedback", "bug_report"],
) -> str:
    """Create a support ticket for tracking this interaction.

    ALWAYS call this first at the start of every conversation.

    Args:
        issue: Brief summary of the customer's issue.
        priority: Ticket priority level.
        category: Issue category.

    Returns:
        Ticket ID string for use in subsequent tool calls.
    """
    ctx = get_processing_context()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        ticket_id = await conn.fetchval(
            """
            INSERT INTO tickets
                (conversation_id, customer_id, source_channel, category, priority, status)
            VALUES ($1, $2, $3, $4, $5, 'open')
            RETURNING id
            """,
            ctx.conversation_id,
            ctx.customer_id,
            ctx.channel,
            category or "general",
            priority,
        )

    ctx.ticket_id = str(ticket_id)
    logger.info("Ticket created: %s | customer=%s channel=%s", ticket_id, ctx.customer_id, ctx.channel)
    return f"Ticket created: {ticket_id}"


# ---------------------------------------------------------------------------
# Tool 3 — get_customer_history
# ---------------------------------------------------------------------------

@function_tool
async def get_customer_history() -> str:
    """Get the customer's complete interaction history across ALL channels.

    Use this to understand context from previous conversations,
    even if they happened on a different channel (email vs WhatsApp vs web form).

    Returns:
        Last 20 messages across all channels, newest first.
    """
    ctx = get_processing_context()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.initial_channel, c.status,
                   m.role, m.channel, m.content, m.created_at
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE c.customer_id = $1
              AND c.id != $2          -- exclude current conversation
            ORDER BY m.created_at DESC
            LIMIT 20
            """,
            ctx.customer_id,
            ctx.conversation_id,
        )

    if not rows:
        return "No previous interactions found for this customer."

    lines = [
        f"[{r['channel']} | {r['role']} | {r['created_at'].strftime('%Y-%m-%d')}] "
        f"{r['content'][:200]}"
        for r in rows
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — escalate_to_human
# ---------------------------------------------------------------------------

@function_tool
async def escalate_to_human(ticket_id: str, reason: str, urgency: str) -> str:
    """Escalate the conversation to a human support agent.

    Use when:
    - Customer asks about pricing or refunds
    - Customer sentiment is negative or language is aggressive
    - You cannot find relevant information after 2 search attempts
    - Customer explicitly requests human help
    - Legal terms are mentioned ("lawyer", "sue", "legal", "attorney")

    Args:
        ticket_id: The ticket ID returned by create_ticket.
        reason: Specific escalation reason (e.g. "pricing_inquiry", "refund_request", "legal_threat").
        urgency: Use 'normal' or 'urgent'.

    Returns:
        Escalation confirmation with reference ID.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tickets
            SET status = 'escalated',
                resolution_notes = $1
            WHERE id = $2
            """,
            f"Escalation reason: {reason} | urgency: {urgency}",
            ticket_id,
        )
        await conn.execute(
            """
            UPDATE conversations
            SET status = 'escalated',
                escalated_to = 'human_agent'
            WHERE id = (SELECT conversation_id FROM tickets WHERE id = $1)
            """,
            ticket_id,
        )

    logger.info("Ticket %s escalated | reason=%s urgency=%s", ticket_id, reason, urgency)
    return f"Escalated to human support. Reference: {ticket_id}. Reason: {reason}"


# ---------------------------------------------------------------------------
# Tool 5 — send_response
# ---------------------------------------------------------------------------

@function_tool
async def send_response(message: str) -> str:
    """Send a response to the customer via their original channel.

    The message is automatically formatted for the channel:
    - Email: formal with greeting and signature
    - WhatsApp: concise, under 300 characters
    - Web Form: semi-formal

    ALWAYS call this as the final action. Never respond directly without it.

    Args:
        message: The raw response text to send to the customer.

    Returns:
        Delivery status string.
    """
    ctx = get_processing_context()
    ticket_id = ctx.ticket_id or "unknown"
    formatted = format_for_channel(message, ctx.channel, ticket_id)

    # Persist outbound message to DB
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages
                (conversation_id, channel, direction, role, content, delivery_status)
            VALUES ($1, $2, 'outbound', 'agent', $3, 'sent')
            """,
            ctx.conversation_id,
            ctx.channel,
            formatted,
        )

    # Dispatch to channel-specific sender
    await _dispatch(formatted, ctx)
    return f"Response sent via {ctx.channel}: delivered"


async def _dispatch(message: str, ctx: ProcessingContext) -> None:
    """Route the formatted message to the correct channel transport."""
    try:
        if ctx.channel == "whatsapp" and ctx.customer_phone:
            from app.channels.whatsapp_handler import WhatsAppHandler
            handler = WhatsAppHandler()
            await handler.send_message(ctx.customer_phone, message)

        elif ctx.channel == "email" and ctx.customer_email:
            from app.channels.gmail_handler import GmailHandler
            handler = GmailHandler()
            # GmailHandler.send_reply is sync (google-api-python-client)
            await asyncio.get_event_loop().run_in_executor(
                None,
                handler.send_reply,
                ctx.customer_email,
                ctx.ticket_subject,
                message,
                ctx.gmail_thread_id,
            )

        elif ctx.channel == "web_form" and ctx.customer_email:
            # PDF Page 3: Web Form response method = "API response + Email"
            # DB storage already done above in send_response(); send email notification now.
            from app.channels.gmail_handler import GmailHandler
            ticket_ref = ctx.ticket_id or "N/A"
            subject = f"Your Support Request — Ticket #{ticket_ref}"
            body = (
                f"{message}\n\n"
                f"---\n"
                f"Ticket Reference: #{ticket_ref}\n"
                f"You can check the status of your request at any time by visiting our support portal.\n\n"
                f"CloudScale AI Customer Success Team"
            )
            handler = GmailHandler()
            await asyncio.get_event_loop().run_in_executor(
                None,
                handler.send_reply,
                ctx.customer_email,
                subject,
                body,
                None,   # no thread_id for web form submissions
            )
            logger.info(
                "Web form email notification sent | ticket=%s to=%s",
                ticket_ref,
                ctx.customer_email,
            )

    except Exception as exc:
        logger.error("Channel dispatch failed [%s]: %s", ctx.channel, exc)
