"""
tests/test_agent.py
-------------------
Unit tests for the AI agent guardrail logic and edge-case handling.

Tests use the pre-agent guardrail function directly — no DB or LLM calls
needed. This makes them fast, deterministic, and safe to run in CI.

PDF Reference: Pages 15-16 (edge case test requirements)
"""

import pytest

from app.worker.message_processor import _check_guardrails


# ---------------------------------------------------------------------------
# test_edge_case_pricing_escalation
# ---------------------------------------------------------------------------

class TestPricingEscalation:
    """Pricing-related messages must ALWAYS escalate before reaching the LLM."""

    def test_direct_pricing_keyword(self):
        """'pricing' keyword triggers escalation."""
        should_escalate, reason = _check_guardrails("What is your pricing for the A100 GPU?")
        assert should_escalate is True
        assert reason == "pricing_inquiry"

    def test_cost_keyword(self):
        """'cost' keyword triggers pricing escalation."""
        should_escalate, reason = _check_guardrails("How much does a gpu.h100.1 instance cost per month?")
        assert should_escalate is True
        assert reason == "pricing_inquiry"

    def test_subscription_keyword(self):
        """'subscription' keyword triggers pricing escalation."""
        should_escalate, reason = _check_guardrails("I want to upgrade my subscription to Business plan.")
        assert should_escalate is True
        assert reason == "pricing_inquiry"

    def test_fee_keyword(self):
        """'fee' keyword triggers pricing escalation."""
        should_escalate, reason = _check_guardrails("Are there any hidden fees for egress traffic?")
        assert should_escalate is True
        assert reason == "pricing_inquiry"

    def test_quote_keyword(self):
        """'quote' keyword triggers pricing escalation."""
        should_escalate, reason = _check_guardrails("Can you send me a quote for 8x H100 reserved instances?")
        assert should_escalate is True
        assert reason == "pricing_inquiry"

    def test_case_insensitive(self):
        """Guardrail is case-insensitive — 'PRICING' should still trigger."""
        should_escalate, reason = _check_guardrails("WHAT IS THE PRICING FOR ENTERPRISE?")
        assert should_escalate is True
        assert reason == "pricing_inquiry"

    def test_technical_question_no_trigger(self):
        """Pure technical question must NOT trigger pricing escalation."""
        should_escalate, reason = _check_guardrails("My instance is stuck in PENDING state for 20 minutes.")
        assert should_escalate is False
        assert reason == ""


# ---------------------------------------------------------------------------
# test_edge_case_angry_customer
# ---------------------------------------------------------------------------

class TestAngryCustomer:
    """Aggressive or profanity-containing messages must escalate immediately."""

    def test_profanity_triggers_escalation(self):
        """Profanity keyword triggers aggressive_language escalation."""
        should_escalate, reason = _check_guardrails("This is bullshit, my data is gone and nobody is helping me!")
        # 'shit' is in _PROFANITY_KEYWORDS
        assert should_escalate is True
        assert reason == "aggressive_language"

    def test_legal_threat_triggers_escalation(self):
        """Legal threat triggers legal_threat escalation, not profanity bucket."""
        should_escalate, reason = _check_guardrails("I will sue your company if this is not resolved today.")
        assert should_escalate is True
        assert reason == "legal_threat"

    def test_lawyer_keyword(self):
        """'lawyer' keyword triggers legal_threat escalation."""
        should_escalate, reason = _check_guardrails("I'm getting my lawyer involved.")
        assert should_escalate is True
        assert reason == "legal_threat"

    def test_refund_demand(self):
        """Refund demand triggers refund_request escalation."""
        should_escalate, reason = _check_guardrails("I demand a full refund for this month's invoice immediately.")
        assert should_escalate is True
        assert reason == "refund_request"

    def test_chargeback_threat(self):
        """Chargeback threat triggers refund_request escalation."""
        should_escalate, reason = _check_guardrails("I'm filing a chargeback with my bank right now.")
        assert should_escalate is True
        assert reason == "refund_request"

    def test_human_request(self):
        """Customer explicitly requesting a human triggers escalation."""
        should_escalate, reason = _check_guardrails("I want to speak to a human agent please.")
        assert should_escalate is True
        assert reason == "customer_requested_human"

    def test_frustrated_but_no_keywords(self):
        """Frustrated tone without trigger keywords must NOT auto-escalate (LLM handles it)."""
        should_escalate, reason = _check_guardrails(
            "This is completely unacceptable! My instance has been down for 3 hours."
        )
        assert should_escalate is False
        assert reason == ""


# ---------------------------------------------------------------------------
# test_edge_case_empty_message
# ---------------------------------------------------------------------------

class TestEmptyMessage:
    """Empty or whitespace-only messages must not crash the guardrail or agent."""

    def test_empty_string_no_escalation(self):
        """Empty string does not trigger any guardrail."""
        should_escalate, reason = _check_guardrails("")
        assert should_escalate is False
        assert reason == ""

    def test_whitespace_only_no_escalation(self):
        """Whitespace-only message does not trigger any guardrail."""
        should_escalate, reason = _check_guardrails("   \n\t  ")
        assert should_escalate is False
        assert reason == ""

    def test_single_character_no_escalation(self):
        """Single character message does not trigger guardrails."""
        should_escalate, reason = _check_guardrails("?")
        assert should_escalate is False
        assert reason == ""

    def test_returns_tuple(self):
        """Guardrail always returns a (bool, str) tuple, never raises."""
        result = _check_guardrails("")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_none_safe(self):
        """Guardrail handles content that evaluates to empty after .lower()."""
        should_escalate, reason = _check_guardrails("Hello, I need help.")
        assert should_escalate is False
        assert reason == ""
