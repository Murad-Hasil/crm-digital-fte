# Discovery Log — CRM Digital FTE Factory
## CloudScale AI · Customer Success Agent

**Project:** Hackathon 5 — AI Customer Success FTE  
**Author:** Murad Hasil  
**Incubation Period:** 2026-03-01 → 2026-04-12  
**Status:** Crystallized → Production-Ready

---

## Purpose

This log records every architectural decision, constraint discovery, and requirement clarification made during the incubation phase. Each entry explains *what* was decided, *why*, and the *alternatives considered*. This document serves as the authoritative "why we built it this way" reference for future maintainers.

---

## Discovery #001 — Multi-Channel Normalization Strategy

**Date:** 2026-03-02  
**Decision:** Normalize all inbound channels (Email, WhatsApp, Web Form) into a single `NormalizedTicketEvent` Pydantic model before queuing.

**Problem:** Gmail, Twilio WhatsApp, and Web Form each deliver messages in completely different formats (JSON body, form-encoded, Pub/Sub wrapper). Letting the agent deal with raw channel payloads would couple business logic to integration details.

**Decision:** Create a channel-agnostic `NormalizedTicketEvent` at the webhook boundary. Each channel handler is responsible for translating its own payload. Downstream (Kafka → worker → agent) sees a uniform structure.

**Alternatives Considered:**
- Per-channel agent variants → rejected: triplicates agent logic
- Raw payload forwarding → rejected: couples worker to channel format changes

**Impact:** `app/api/models.py` defines the canonical schema. All 3 channel handlers (`webhooks.py`, `web_form_handler.py`) convert to this schema before publishing.

---

## Discovery #002 — Message Broker Selection (Kafka vs RabbitMQ vs Redis Streams)

**Date:** 2026-03-03  
**Decision:** Apache Kafka 3.7.0 via Docker.

**Problem:** Need a durable, ordered queue between webhook receipt and agent processing. Webhook endpoints must return < 200 ms; agent runs take 2–10 seconds.

**Kafka chosen because:**
- Durable log: messages survive worker crashes and can be replayed
- Consumer group offset management: exactly-once processing semantics
- Native `aiokafka` Python async library (no threading overhead)
- Replay capability for debugging failed agent runs

**Alternatives Considered:**
- RabbitMQ → adequate but lacks replay; no native async Python client as clean as aiokafka
- Redis Streams → operational simplicity, but no persistence guarantees for hackathon demo
- Direct async task queue (asyncio.Queue) → no durability; crashes lose messages

**Topic:** `fte.tickets.incoming`  
**Consumer Group:** `fte-message-processor`

---

## Discovery #003 — AI Provider Selection (Groq vs OpenAI vs Anthropic)

**Date:** 2026-03-04  
**Decision:** Groq API with `llama-3.3-70b-versatile` model.

**Problem:** Need an LLM for customer-facing responses. Requirements: fast response, tool-calling support, OpenAI SDK compatible.

**Groq chosen because:**
- Sub-second inference via LPU hardware (< 500 ms typical)
- OpenAI-compatible API: drop-in with `OPENAI_BASE_URL=https://api.groq.com/openai/v1`
- `llama-3.3-70b-versatile` supports structured tool calling (required for 5-tool agent)
- Free tier sufficient for hackathon volume

**Constraint Discovered:** Groq does not provide an embeddings API. This required a separate embedding solution for the RAG knowledge base (see Discovery #007).

**Configuration:** `openai-agents` SDK used with `OPENAI_BASE_URL` override — zero code changes required to swap providers later.

---

## Discovery #004 — Database Design (pgvector on Neon)

**Date:** 2026-03-05  
**Decision:** Neon Serverless PostgreSQL with `pgvector` extension.

**Problem:** Need persistent storage for customers, conversations, messages, tickets, knowledge base, and metrics. Knowledge base requires vector similarity search for RAG.

**Neon chosen because:**
- Managed PostgreSQL: no ops overhead for hackathon
- `pgvector` extension available natively (vector cosine similarity with `<=>` operator)
- Serverless scaling: free tier handles hackathon traffic
- Connection pooling built-in (pgBouncer)

**8 tables designed:**
1. `customers` — unified cross-channel identity
2. `customer_identifiers` — channel-specific identifiers (email, whatsapp)
3. `conversations` — session-level context with sentiment tracking
4. `messages` — full message history with direction and role
5. `tickets` — support ticket lifecycle
6. `knowledge_base` — RAG documents with `VECTOR(384)` embeddings
7. `channel_configs` — per-channel runtime configuration
8. `agent_metrics` — latency and performance time-series

**ivfflat index** on `knowledge_base.embedding` for sub-millisecond cosine similarity search.

---

## Discovery #005 — Agent Architecture (OpenAI Agents SDK)

**Date:** 2026-03-07  
**Decision:** OpenAI Agents SDK (`openai-agents`) with 5 defined tools.

**Problem:** Need a structured agent that follows a deterministic workflow (always create ticket first, always use send_response last) while allowing LLM reasoning in between.

**Tools defined:**
1. `search_knowledge_base` — RAG lookup against product docs
2. `create_ticket` — always called first; creates DB record
3. `get_customer_history` — cross-channel context retrieval
4. `escalate_to_human` — human handoff with reason logging
5. `send_response` — always called last; sends reply to channel

**Workflow enforced in system prompt:** Agent cannot skip tool steps. `send_response` is the only way a message gets sent — prevents hallucinated replies.

**`contextvars` pattern:** `ProcessingContext` (customer_id, conversation_id, channel, etc.) is injected into a Python `ContextVar` before each `Runner.run()` call so all tools share session state without parameter threading.

---

## Discovery #006 — Gmail Integration (Pub/Sub Push vs Polling)

**Date:** 2026-03-09  
**Decision:** Gmail Watch API with Google Cloud Pub/Sub push webhooks.

**Problem:** Need real-time email notification without polling.

**Gmail Watch + Pub/Sub chosen because:**
- Push model: Google calls our webhook (ngrok in dev, production URL in prod)
- < 10 second latency from email arrival to webhook fire
- No polling loop consuming resources

**Constraint Discovered:** Gmail Watch subscription expires every 7 days. Renewal cron required in production.

**Renewal command documented** in project README and `project_progress.md` memory.

**OAuth2 flow:** `credentials/gmail_credentials.json` stores refresh token. Script `setup_gmail_auth.py` handles initial auth.

---

## Discovery #007 — RAG Embedding Strategy (sentence-transformers, no Groq embeddings)

**Date:** 2026-03-15 (revisited 2026-04-12)  
**Decision:** Local `sentence-transformers` with `all-MiniLM-L6-v2` (384 dimensions).

**Problem:** Knowledge base requires embedding vectors for semantic search. Groq does not provide an embeddings API.

**Options evaluated:**
1. OpenAI `text-embedding-3-small` (1536 dims) → requires separate OpenAI API key and billing
2. `fastembed` (ONNX-based) → installed initially, then uninstalled; `sentence-transformers` preferred for ecosystem consistency
3. `sentence-transformers all-MiniLM-L6-v2` (384 dims, local) → **selected**

**`sentence-transformers` chosen because:**
- Runs fully locally — no API key, no cost, no latency to external service
- 384-dim model is sufficient for technical documentation retrieval
- Cached after first load: `_get_embedding_model()` uses `@lru_cache(maxsize=1)` — loaded once per worker process

**DB column adjusted:** `VECTOR(1536)` → `VECTOR(384)` (migration handled by `scripts/seed_kb.py`)

**Constraint Discovered (Python 3.14):** PyTorch's `triton` package fails on Python 3.14 in first install attempt. Resolved by reinstalling cleanly. Noted for Docker image build.

**asyncpg vector binding quirk:** `$1::vector` parameter binding returns empty results on Neon pooled connections. Workaround: embed normalized float vector as literal string directly in SQL. Safe because vectors are ML-generated, not user input.

---

## Discovery #008 — Pre-Agent Guardrails

**Date:** 2026-03-18  
**Decision:** Keyword-based guardrail scan before every `Runner.run()` call.

**Problem:** Some message categories (pricing, refunds, legal threats) should never reach the LLM — they require human handling regardless of AI capability. LLM call costs latency and tokens.

**Implementation:** `_check_guardrails(content)` — O(1) set intersection, runs in microseconds.

**5 escalation buckets:**
- `pricing_inquiry` — price/cost/fee/subscription keywords
- `refund_request` — refund/chargeback/reimburse
- `legal_threat` — lawyer/attorney/sue/lawsuit
- `customer_requested_human` — human/agent/person/representative
- `aggressive_language` — profanity detection

**If triggered:** Ticket created with `status=escalated`, conversation marked `escalated_to=human_agent`, Kafka message acknowledged, agent never invoked.

---

## Discovery #009 — Structural Refactoring (PDF Compliance)

**Date:** 2026-04-12  
**Decision:** Separate concerns as required by PDF page 12 file structure.

**Changes made:**
- `app/db/queries.py` created — all DB access functions centralized (was inline in `message_processor.py`)
- `app/channels/web_form_handler.py` created — Web Form routes extracted from `webhooks.py`
- `database/migrations/001_initial_schema.sql` created — schema versioned under migrations/

**Why:** Testability — individual DB functions can now be tested with a mock connection. Single-responsibility — `message_processor.py` now only orchestrates, does not contain SQL.

---

## Open Items / Future Discoveries

| ID | Issue | Priority |
|----|-------|----------|
| OI-001 | Gmail Watch renewal not automated — needs cron job | High |
| OI-002 | `search_knowledge_base` ILIKE fallback has no ranking | Medium |
| OI-003 | No rate limiting on `/webhooks/webform` endpoint | Medium |
| OI-004 | `channel_configs` table populated manually — no admin UI | Low |
| OI-005 | Neon free tier: max 10 connections — pool maxsize=10 hits limit under load | Medium |
