"""
AI client configuration.

Primary  : Groq (LLaMA 3.3 70B) — fast and free tier
Fallback : OpenAI (GPT-4o-mini) — used when Groq daily quota is exhausted

Set OPENAI_API_KEY in env/secrets to enable the fallback.
"""

import os
from openai import AsyncOpenAI

# ── Primary: Groq ────────────────────────────────────────────────────────────
ai_client = AsyncOpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
)
MODEL_NAME: str = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")

# ── Fallback: OpenAI ─────────────────────────────────────────────────────────
# Only constructed when OPENAI_API_KEY is present — no key = no fallback.
_openai_key = os.getenv("OPENAI_API_KEY", "")
openai_fallback_client: AsyncOpenAI | None = (
    AsyncOpenAI(api_key=_openai_key) if _openai_key else None
)
OPENAI_FALLBACK_MODEL: str = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
