"""
Customer Success FTE — OpenAI Agents SDK agent definition.

Primary agent  : Groq LLaMA 3.3 70B  (fast, free tier)
Fallback agent : OpenAI GPT-4o-mini   (activates when OPENAI_API_KEY is set
                                       and Groq daily quota is exhausted)

Call init_agent() once at application startup.
"""

from agents import Agent, set_default_openai_client
from agents.models.openai_responses import OpenAIResponsesModel

from app.agents.prompts import CUSTOMER_SUCCESS_SYSTEM_PROMPT
from app.agents.tools import (
    create_ticket,
    escalate_to_human,
    get_customer_history,
    search_knowledge_base,
    send_response,
)
from app.core.ai_client import (
    MODEL_NAME,
    OPENAI_FALLBACK_MODEL,
    ai_client,
    openai_fallback_client,
)

_TOOLS = [
    create_ticket,
    get_customer_history,
    search_knowledge_base,
    escalate_to_human,
    send_response,
]


def init_agent() -> None:
    """Register the Groq client as the SDK default."""
    set_default_openai_client(ai_client)


# ── Primary: Groq ─────────────────────────────────────────────────────────────
customer_success_agent = Agent(
    name="Customer Success FTE",
    model=MODEL_NAME,
    instructions=CUSTOMER_SUCCESS_SYSTEM_PROMPT,
    tools=_TOOLS,
)

# ── Fallback: OpenAI ──────────────────────────────────────────────────────────
# Uses an explicit per-agent client so the global Groq default is not touched.
# Will be None if OPENAI_API_KEY is not configured.
customer_success_agent_openai: Agent | None = (
    Agent(
        name="Customer Success FTE (OpenAI Fallback)",
        model=OpenAIResponsesModel(
            model=OPENAI_FALLBACK_MODEL,
            openai_client=openai_fallback_client,
        ),
        instructions=CUSTOMER_SUCCESS_SYSTEM_PROMPT,
        tools=_TOOLS,
    )
    if openai_fallback_client
    else None
)
