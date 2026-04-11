"""
Customer Success FTE — OpenAI Agents SDK agent definition.
Configured for Groq via AsyncOpenAI base_url override.

Call init_agent() once at application startup (sets the default client).
"""

import os

from agents import Agent, set_default_openai_client

from app.agents.prompts import CUSTOMER_SUCCESS_SYSTEM_PROMPT
from app.agents.tools import (
    create_ticket,
    escalate_to_human,
    get_customer_history,
    search_knowledge_base,
    send_response,
)
from app.core.ai_client import MODEL_NAME, ai_client


def init_agent() -> None:
    """
    Register the Groq-backed AsyncOpenAI client as the SDK default.
    Must be called before any Runner.run() invocation.
    """
    set_default_openai_client(ai_client)


# Agent is defined at module level; safe to import anywhere after init_agent().
customer_success_agent = Agent(
    name="Customer Success FTE",
    model=MODEL_NAME,                        # llama-3.3-70b-versatile (Groq)
    instructions=CUSTOMER_SUCCESS_SYSTEM_PROMPT,
    tools=[
        create_ticket,          # Tool 1 — always first
        get_customer_history,   # Tool 2
        search_knowledge_base,  # Tool 3
        escalate_to_human,      # Tool 4
        send_response,          # Tool 5 — always last
    ],
)
