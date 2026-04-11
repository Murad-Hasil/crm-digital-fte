"""
Async OpenAI client configured for Groq compatibility.
Uses AsyncOpenAI with a custom base_url so the OpenAI Agents SDK
transparently routes all requests through Groq's API.

Import `ai_client` and `MODEL_NAME` wherever LLM calls are needed.
"""

import os
from openai import AsyncOpenAI

ai_client = AsyncOpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
)

MODEL_NAME: str = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")
