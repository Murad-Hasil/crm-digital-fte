"""
tests/test_e2e.py
-----------------
End-to-end pipeline tests: Webhook payload → process_message() → DB writes → Agent run.

These tests mock the DB pool and the AI Runner so they run without
live infrastructure (no Kafka, no Neon, no Groq API calls required in CI).
The real logic under test is the orchestration in process_message().

PDF Reference: Pages 17-18 (end-to-end test requirements)
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.worker.message_processor import process_message


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

def _make_message(
    channel: str = "web_form",
    content: str = "How do I attach a volume to my instance?",
    email: str = "customer@example.com",
    subject: str = "Volume attachment help",
    channel_message_id: str = None,
) -> dict:
    """Build a NormalizedTicketEvent-style dict for process_message()."""
    return {
        "channel": channel,
        "content": content,
        "customer_email": email,
        "customer_name": "Test Customer",
        "ticket_subject": subject,
        "channel_message_id": channel_message_id or str(uuid.uuid4()),
        "received_at": "2026-04-12T10:00:00Z",
        "metadata": {},
    }


def _make_mock_conn(customer_id=None, conversation_id=None):
    """Build a mock asyncpg connection with pre-set return values."""
    cid = customer_id or str(uuid.uuid4())
    conv_id = conversation_id or str(uuid.uuid4())
    ticket_id = str(uuid.uuid4())

    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    # fetchrow: customer lookup returns None (new customer)
    conn.fetchrow = AsyncMock(return_value=None)

    # fetchval: INSERT RETURNING id — returns UUID for customer, then conversation
    conn.fetchval = AsyncMock(side_effect=[cid, conv_id, ticket_id])

    # fetch: conversation lookup + history — return empty (new conversation, no history)
    conn.fetch = AsyncMock(return_value=[])

    return conn, cid, conv_id


def _make_mock_pool(conn):
    """Build a mock asyncpg pool whose acquire() context manager yields conn."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


# ---------------------------------------------------------------------------
# Test 1: Normal web_form message flows through full pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_web_form_message_creates_records():
    """
    Pipeline: web_form message → customer created → conversation created →
    message stored → agent runs → latency recorded.
    """
    conn, cid, conv_id = _make_mock_conn()
    pool = _make_mock_pool(conn)

    mock_result = MagicMock()
    mock_result.final_output = "To attach a volume, run: cs volume attach vol_id --instance inst_id"

    with patch("app.worker.message_processor.get_db_pool", AsyncMock(return_value=pool)), \
         patch("app.worker.message_processor.Runner.run", AsyncMock(return_value=mock_result)), \
         patch("app.agents.tools.get_db_pool", AsyncMock(return_value=pool)):

        await process_message(_make_message(channel="web_form"))

    # DB must have been touched (execute called for message insert, metric, etc.)
    assert conn.execute.called
    # fetchval called to create customer + conversation
    assert conn.fetchval.called


# ---------------------------------------------------------------------------
# Test 2: Pricing message escalates — Runner.run() is NEVER called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_pricing_message_escalates_without_llm():
    """
    Pricing keyword in content must trigger guardrail escalation.
    The LLM (Runner.run) must NOT be called — guardrail fires first.
    """
    conn, cid, conv_id = _make_mock_conn()
    # fetchval returns customer_id, conv_id, ticket_id for escalation INSERT
    conn.fetchval = AsyncMock(side_effect=[cid, conv_id, str(uuid.uuid4())])
    pool = _make_mock_pool(conn)

    runner_mock = AsyncMock()

    with patch("app.worker.message_processor.get_db_pool", AsyncMock(return_value=pool)), \
         patch("app.worker.message_processor.Runner.run", runner_mock):

        await process_message(_make_message(
            content="What is the pricing for the H100 reserved instance plan?"
        ))

    # Runner.run must NOT have been called
    runner_mock.assert_not_called()
    # DB execute must have been called (escalated ticket created)
    assert conn.execute.called


# ---------------------------------------------------------------------------
# Test 3: Legal threat escalates — Runner.run() is NEVER called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_legal_threat_escalates_without_llm():
    """
    Legal keyword must escalate before LLM is invoked.
    """
    conn, cid, conv_id = _make_mock_conn()
    conn.fetchval = AsyncMock(side_effect=[cid, conv_id, str(uuid.uuid4())])
    pool = _make_mock_pool(conn)

    runner_mock = AsyncMock()

    with patch("app.worker.message_processor.get_db_pool", AsyncMock(return_value=pool)), \
         patch("app.worker.message_processor.Runner.run", runner_mock):

        await process_message(_make_message(
            content="I am going to sue CloudScale AI for this data loss."
        ))

    runner_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: Empty message — pipeline does not crash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_empty_message_handled_gracefully():
    """
    Empty content must not raise an exception.
    Guardrail returns False → agent runs normally.
    """
    conn, cid, conv_id = _make_mock_conn()
    pool = _make_mock_pool(conn)

    mock_result = MagicMock()
    mock_result.final_output = "Hello! How can I help you today?"

    runner_mock = AsyncMock(return_value=mock_result)

    with patch("app.worker.message_processor.get_db_pool", AsyncMock(return_value=pool)), \
         patch("app.worker.message_processor.Runner.run", runner_mock), \
         patch("app.agents.tools.get_db_pool", AsyncMock(return_value=pool)):

        # Must not raise
        await process_message(_make_message(content=""))

    # Agent was called (no guardrail triggered on empty)
    runner_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: Customer resolution fails gracefully (no email, no phone)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_missing_customer_identifier_returns_early():
    """
    Message with no email and no phone must log error and return early.
    Runner.run must NOT be called.
    """
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    pool = _make_mock_pool(conn)

    runner_mock = AsyncMock()

    bad_message = {
        "channel": "web_form",
        "content": "My instance is down.",
        "ticket_subject": "Help",
        "metadata": {},
        # No customer_email, no customer_phone
    }

    with patch("app.worker.message_processor.get_db_pool", AsyncMock(return_value=pool)), \
         patch("app.worker.message_processor.Runner.run", runner_mock):

        await process_message(bad_message)   # must not raise

    runner_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: WhatsApp message pipeline (phone-based customer)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_whatsapp_message_resolves_phone_customer():
    """
    WhatsApp message (phone identifier, no email) must resolve customer
    via phone and reach the agent.
    """
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # fetchrow: customer_identifiers lookup returns None (new customer)
    conn.fetchrow = AsyncMock(return_value=None)
    cid = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    conn.fetchval = AsyncMock(side_effect=[cid, conv_id])
    conn.fetch = AsyncMock(return_value=[])
    pool = _make_mock_pool(conn)

    mock_result = MagicMock()
    mock_result.final_output = "Hi! I can help you with your WhatsApp query."
    runner_mock = AsyncMock(return_value=mock_result)

    whatsapp_message = {
        "channel": "whatsapp",
        "content": "How do I enable CDN on my storage bucket?",
        "customer_phone": "+14155550199",
        "ticket_subject": "CDN setup",
        "channel_message_id": "SM" + str(uuid.uuid4()).replace("-", ""),
        "metadata": {},
    }

    with patch("app.worker.message_processor.get_db_pool", AsyncMock(return_value=pool)), \
         patch("app.worker.message_processor.Runner.run", runner_mock), \
         patch("app.agents.tools.get_db_pool", AsyncMock(return_value=pool)):

        await process_message(whatsapp_message)

    runner_mock.assert_called_once()
