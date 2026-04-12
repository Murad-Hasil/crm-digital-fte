"""
MCP Server — CloudScale AI Customer Success FTE
Incubation Phase · Exercise 1.4 (PDF Page 6-7)

Exposes 5 core tools over the Model Context Protocol so that any
MCP-compatible host (Claude Desktop, Cursor, custom client) can drive
the Customer Success agent without touching the Kafka/FastAPI layer.

This implementation uses MOCK data appropriate for the Incubation Phase.
The same tool names and signatures are used in production (app/agents/tools.py)
so the switch is a drop-in: replace mock logic with real DB/API calls.

Run:
    python mcp_server.py

Requirements:
    pip install mcp>=1.0.0
"""

import json
import logging
import random
import string
import uuid
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    name="cloudscale-ai-customer-success",
    instructions=(
        "You are a Customer Success agent for CloudScale AI. "
        "Use the tools in this order: search_knowledge_base → create_ticket → "
        "(optionally get_customer_history) → (escalate_to_human if needed) → send_response."
    ),
)

# ---------------------------------------------------------------------------
# Shared in-memory state (mock store for incubation phase)
# ---------------------------------------------------------------------------

_TICKETS: dict[str, dict] = {}
_HISTORY: dict[str, list] = {}  # customer_id → list of past interactions
_KNOWLEDGE_BASE: list[dict] = [
    {
        "title": "Getting Started with CloudScale AI",
        "category": "onboarding",
        "content": (
            "Welcome to CloudScale AI! After signing up, navigate to the Dashboard "
            "and click 'New Project'. You can invite team members under Settings → Team. "
            "Free tier includes 1,000 API calls/month."
        ),
    },
    {
        "title": "API Rate Limits",
        "category": "technical",
        "content": (
            "Free tier: 60 requests/minute. Pro tier: 600 requests/minute. "
            "Enterprise: custom limits. If you hit a 429 error, implement exponential "
            "backoff starting at 1 second. Headers X-RateLimit-Remaining and "
            "X-RateLimit-Reset are included in every response."
        ),
    },
    {
        "title": "Billing & Subscription Plans",
        "category": "billing",
        "content": (
            "Plans: Free ($0/mo, 1K calls), Pro ($49/mo, 100K calls), "
            "Enterprise (custom pricing). Billing is monthly. Upgrade/downgrade "
            "takes effect immediately. Refunds are handled by the finance team — "
            "please escalate billing queries to a human agent."
        ),
    },
    {
        "title": "SSO / OAuth Integration",
        "category": "technical",
        "content": (
            "CloudScale AI supports SAML 2.0 and OAuth 2.0. Configure SSO under "
            "Settings → Security → SSO. You will need your IdP metadata URL. "
            "Google Workspace and Okta are pre-configured; other providers require "
            "manual XML upload."
        ),
    },
    {
        "title": "Data Retention & Privacy",
        "category": "compliance",
        "content": (
            "Customer data is retained for 90 days by default. Enterprise customers "
            "can configure custom retention windows. All data is encrypted at rest "
            "(AES-256) and in transit (TLS 1.3). We are SOC 2 Type II and GDPR compliant."
        ),
    },
    {
        "title": "Escalation Policy",
        "category": "internal",
        "content": (
            "Escalate to human if: customer mentions legal action, requests refund > $500, "
            "sentiment score < 0.3, or the issue cannot be resolved within 2 KB searches. "
            "SLA: human agent responds within 4 hours on business days."
        ),
    },
]


def _generate_id(prefix: str = "") -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}{suffix}" if prefix else suffix


# ---------------------------------------------------------------------------
# Tool 1 — search_knowledge_base
# ---------------------------------------------------------------------------

@mcp.tool()
def search_knowledge_base(query: str, max_results: int = 3) -> str:
    """Search the CloudScale AI knowledge base for relevant documentation.

    Use this first when the customer asks a product or technical question.
    Attempt at most 2 searches before escalating to a human agent.

    Args:
        query: Natural-language search query from the customer's message.
        max_results: Maximum number of results to return (default 3).

    Returns:
        Formatted documentation snippets relevant to the query.
    """
    query_lower = query.lower()
    scored: list[tuple[int, dict]] = []

    for doc in _KNOWLEDGE_BASE:
        score = 0
        for word in query_lower.split():
            if len(word) < 3:
                continue
            if word in doc["title"].lower():
                score += 3
            if word in doc["content"].lower():
                score += 1
            if word in (doc.get("category") or ""):
                score += 2
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [doc for _, doc in scored[:max_results]]

    if not results:
        logger.info("KB search: no results for query='%s'", query)
        return (
            "No relevant documentation found. "
            "Consider escalating to a human agent if the customer needs further help."
        )

    parts = []
    for doc in results:
        parts.append(
            f"**{doc['title']}** (category: {doc['category']})\n{doc['content']}"
        )

    logger.info("KB search: %d result(s) for query='%s'", len(results), query)
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 2 — create_ticket
# ---------------------------------------------------------------------------

@mcp.tool()
def create_ticket(
    customer_id: str,
    issue: str,
    priority: str = "medium",
    channel: str = "web_form",
) -> str:
    """Create a support ticket to track this customer interaction.

    ALWAYS call this at the start of every conversation before any other action.

    Args:
        customer_id: Unique identifier for the customer (email or UUID).
        issue: Brief summary of the customer's issue or question.
        priority: 'low', 'medium', 'high', or 'urgent'.
        channel: Source channel — 'email', 'whatsapp', or 'web_form'.

    Returns:
        Ticket ID string for use in subsequent tool calls.
    """
    ticket_id = _generate_id("TKT-")
    ticket = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "issue": issue,
        "priority": priority,
        "channel": channel,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TICKETS[ticket_id] = ticket

    # Seed a starter history entry for this customer
    if customer_id not in _HISTORY:
        _HISTORY[customer_id] = []

    logger.info("Ticket created: %s | customer=%s channel=%s priority=%s",
                ticket_id, customer_id, channel, priority)
    return f"Ticket created: {ticket_id}"


# ---------------------------------------------------------------------------
# Tool 3 — get_customer_history
# ---------------------------------------------------------------------------

@mcp.tool()
def get_customer_history(customer_id: str) -> str:
    """Retrieve the customer's past interaction history across all channels.

    Use this to understand recurring issues or previous resolutions before
    crafting your response.

    Args:
        customer_id: The customer's unique identifier (same as used in create_ticket).

    Returns:
        Chronological list of past interactions, newest first.
    """
    history = _HISTORY.get(customer_id, [])

    # Add mock historical data for demo/incubation purposes
    mock_history = [
        {
            "date": "2026-03-15",
            "channel": "email",
            "role": "customer",
            "content": "Asked about API rate limits for the Pro tier.",
            "resolution": "Resolved — pointed to rate limit docs.",
        },
        {
            "date": "2026-02-28",
            "channel": "whatsapp",
            "role": "customer",
            "content": "Trouble with SSO configuration (Okta).",
            "resolution": "Resolved — shared SSO setup guide.",
        },
    ]

    all_interactions = mock_history + history
    if not all_interactions:
        return f"No previous interactions found for customer: {customer_id}"

    lines = []
    for item in all_interactions:
        lines.append(
            f"[{item.get('date', 'N/A')} | {item.get('channel', 'unknown')}] "
            f"{item.get('content', '')} → {item.get('resolution', 'pending')}"
        )

    logger.info("History retrieved for customer=%s (%d entries)", customer_id, len(all_interactions))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — escalate_to_human
# ---------------------------------------------------------------------------

@mcp.tool()
def escalate_to_human(ticket_id: str, reason: str, urgency: str = "normal") -> str:
    """Escalate the conversation to a human support agent.

    Use when:
    - Customer asks about pricing, refunds, or contract changes
    - Customer sentiment is negative or language is aggressive
    - Knowledge base search fails twice
    - Customer explicitly requests human help
    - Legal terms are mentioned ("lawyer", "sue", "legal", "attorney")

    Args:
        ticket_id: The ticket ID returned by create_ticket.
        reason: Specific reason (e.g. 'pricing_inquiry', 'refund_request', 'legal_threat').
        urgency: 'normal' or 'urgent'.

    Returns:
        Escalation confirmation with reference number.
    """
    if ticket_id in _TICKETS:
        _TICKETS[ticket_id]["status"] = "escalated"
        _TICKETS[ticket_id]["escalation_reason"] = reason
        _TICKETS[ticket_id]["urgency"] = urgency
    else:
        logger.warning("escalate_to_human: ticket %s not found in mock store", ticket_id)

    escalation_ref = _generate_id("ESC-")
    sla = "1 hour" if urgency == "urgent" else "4 hours"

    logger.info("Escalation: ticket=%s ref=%s reason=%s urgency=%s",
                ticket_id, escalation_ref, reason, urgency)
    return (
        f"Escalated to human support. Escalation reference: {escalation_ref}. "
        f"Ticket: {ticket_id}. Reason: {reason}. "
        f"A human agent will respond within {sla} on business days."
    )


# ---------------------------------------------------------------------------
# Tool 5 — send_response
# ---------------------------------------------------------------------------

@mcp.tool()
def send_response(ticket_id: str, message: str, channel: str = "web_form") -> str:
    """Send the final response to the customer via their original channel.

    ALWAYS call this as the last action. Do not reply directly — always use this tool.
    The message is automatically formatted for the channel:
    - email: formal, with greeting and signature
    - whatsapp: concise, ≤ 300 characters
    - web_form: semi-formal, balanced detail

    Args:
        ticket_id: The ticket ID returned by create_ticket.
        message: The raw response text to send.
        channel: Delivery channel — 'email', 'whatsapp', or 'web_form'.

    Returns:
        Delivery status confirmation.
    """
    # Channel-specific formatting (mirrors production formatters.py)
    if channel == "email":
        formatted = (
            f"Dear Valued Customer,\n\n"
            f"{message}\n\n"
            f"Best regards,\nCloudScale AI Customer Success Team\n"
            f"Reference: {ticket_id}"
        )
    elif channel == "whatsapp":
        # WhatsApp: truncate to 300 chars
        truncated = message[:297] + "..." if len(message) > 300 else message
        formatted = f"{truncated}\n\nRef: {ticket_id}"
    else:
        # web_form
        formatted = f"{message}\n\nYour ticket reference: {ticket_id}"

    # Update mock ticket status
    if ticket_id in _TICKETS:
        _TICKETS[ticket_id]["status"] = "resolved"
        _TICKETS[ticket_id]["response"] = formatted

    logger.info("Response sent | ticket=%s channel=%s chars=%d",
                ticket_id, channel, len(formatted))
    return f"Response sent via {channel}: delivered (ticket {ticket_id} → resolved)"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logger.info("Starting CloudScale AI MCP Server (Incubation Phase)")
    logger.info("5 tools registered: search_knowledge_base, create_ticket, "
                "get_customer_history, escalate_to_human, send_response")

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport=transport)
