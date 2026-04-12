"""
tests/test_channels.py
----------------------
Unit tests for channel-specific response formatters.

Verifies that format_for_channel() applies the correct structure,
length constraints, and required elements for each channel.

PDF Reference: Pages 16-17 (channel formatting requirements)
"""

import pytest

from app.agents.formatters import format_for_channel, _WHATSAPP_MAX


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SHORT_RESPONSE = "Your instance is stuck because the region is at capacity. Try us-west-2."
LONG_RESPONSE = (
    "To resolve the AccessDenied error when uploading to your S3-compatible bucket, "
    "you need to check three things: First, verify that your API key has write permissions "
    "on the bucket. You can check this in the dashboard under API Keys → Permissions. "
    "Second, make sure your bucket policy allows PutObject actions for your key. "
    "Third, confirm the endpoint URL is correct: https://storage.cloudscale.ai. "
    "Here is a working boto3 example: import boto3; s3 = boto3.client('s3', "
    "endpoint_url='https://storage.cloudscale.ai', aws_access_key_id='cs_key_...', "
    "aws_secret_access_key='cs_secret_...'); s3.upload_file('file.txt', 'my-bucket', 'file.txt'). "
    "If the issue persists after these steps, please reply with your bucket name and we "
    "will investigate further on our end."
)


# ---------------------------------------------------------------------------
# test_channel_response_length_email
# ---------------------------------------------------------------------------

class TestEmailFormatting:
    """Email responses must have greeting, body, and professional sign-off."""

    def test_email_has_greeting(self):
        """Email response must start with 'Dear Customer'."""
        result = format_for_channel(SHORT_RESPONSE, "email")
        assert result.startswith("Dear Customer,")

    def test_email_has_signoff(self):
        """Email response must contain a professional sign-off."""
        result = format_for_channel(SHORT_RESPONSE, "email")
        assert "Best regards," in result

    def test_email_has_support_team_name(self):
        """Email response must identify the support team."""
        result = format_for_channel(SHORT_RESPONSE, "email")
        assert "Support" in result

    def test_email_contains_original_response(self):
        """Email wrapper must preserve the original agent response."""
        result = format_for_channel(SHORT_RESPONSE, "email")
        assert SHORT_RESPONSE in result

    def test_email_has_no_length_restriction(self):
        """Email channel imposes no character limit — long responses must be preserved."""
        result = format_for_channel(LONG_RESPONSE, "email")
        assert LONG_RESPONSE in result

    def test_email_includes_ticket_reference_when_provided(self):
        """Ticket ID must appear in email when supplied."""
        result = format_for_channel(SHORT_RESPONSE, "email", ticket_id="TKT-001")
        assert "TKT-001" in result

    def test_email_no_ticket_reference_when_omitted(self):
        """No 'Ticket Reference:' line when ticket_id is empty string."""
        result = format_for_channel(SHORT_RESPONSE, "email", ticket_id="")
        assert "Ticket Reference:" not in result

    def test_email_ai_disclaimer_present(self):
        """Email must include AI disclaimer for transparency."""
        result = format_for_channel(SHORT_RESPONSE, "email")
        assert "AI" in result or "ai" in result.lower()

    def test_email_longer_than_raw_response(self):
        """Formatted email must be longer than the raw response (wrapper added)."""
        result = format_for_channel(SHORT_RESPONSE, "email")
        assert len(result) > len(SHORT_RESPONSE)


# ---------------------------------------------------------------------------
# test_channel_response_length_whatsapp
# ---------------------------------------------------------------------------

class TestWhatsAppFormatting:
    """WhatsApp responses must stay within the _WHATSAPP_MAX character limit."""

    def test_whatsapp_max_constant_is_defined(self):
        """_WHATSAPP_MAX constant must be defined and reasonable."""
        assert isinstance(_WHATSAPP_MAX, int)
        assert 100 <= _WHATSAPP_MAX <= 1000

    def test_short_response_within_limit(self):
        """Short response fits within WhatsApp limit after formatting."""
        result = format_for_channel(SHORT_RESPONSE, "whatsapp")
        assert len(result) <= _WHATSAPP_MAX + 60  # allow for the footer suffix

    def test_long_response_is_truncated(self):
        """Response exceeding _WHATSAPP_MAX must be truncated."""
        result = format_for_channel(LONG_RESPONSE, "whatsapp")
        # The core message part must be truncated
        core = result.split("\n\n")[0]
        assert len(core) <= _WHATSAPP_MAX

    def test_truncated_response_ends_with_ellipsis(self):
        """Truncated WhatsApp message must end with '...' before the footer."""
        result = format_for_channel(LONG_RESPONSE, "whatsapp")
        core = result.split("\n\n")[0]
        assert core.endswith("...")

    def test_whatsapp_has_help_footer(self):
        """WhatsApp response must include a 'reply for help' footer."""
        result = format_for_channel(SHORT_RESPONSE, "whatsapp")
        assert "Reply" in result or "reply" in result

    def test_whatsapp_human_escalation_hint(self):
        """WhatsApp footer must hint at human escalation ('human' keyword)."""
        result = format_for_channel(SHORT_RESPONSE, "whatsapp")
        assert "human" in result.lower()

    def test_whatsapp_short_response_not_truncated(self):
        """Short response (under limit) must NOT be truncated."""
        result = format_for_channel(SHORT_RESPONSE, "whatsapp")
        assert SHORT_RESPONSE in result

    def test_whatsapp_max_is_300(self):
        """_WHATSAPP_MAX must be 300 as defined in formatters.py."""
        assert _WHATSAPP_MAX == 300


# ---------------------------------------------------------------------------
# Web Form (bonus — ensures default channel works correctly)
# ---------------------------------------------------------------------------

class TestWebFormFormatting:
    """Web form is the default channel — no character limit, simple footer."""

    def test_web_form_contains_response(self):
        """Web form output must contain the original agent response."""
        result = format_for_channel(SHORT_RESPONSE, "web_form")
        assert SHORT_RESPONSE in result

    def test_web_form_has_support_footer(self):
        """Web form must include a support portal link hint."""
        result = format_for_channel(SHORT_RESPONSE, "web_form")
        assert "support" in result.lower()

    def test_unknown_channel_defaults_to_web_form(self):
        """Unknown channel name must fall through to web_form formatter."""
        result_unknown = format_for_channel(SHORT_RESPONSE, "unknown_channel")
        result_web = format_for_channel(SHORT_RESPONSE, "web_form")
        assert result_unknown == result_web
