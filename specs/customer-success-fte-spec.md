# Customer Success FTE — Crystallization Specification
## CloudScale AI · AI-Powered Support Agent

**Document Type:** Full Crystallization Spec (PDF Page 8 Template)  
**Version:** 1.0.0  
**Author:** Murad Hasil  
**Date:** 2026-04-12  
**Status:** APPROVED — Production-Ready

---

## 1. Executive Summary

This document is the authoritative specification for the **CloudScale AI Customer Success FTE** — a production-grade, AI-powered customer support agent that operates 24/7 across three channels: Email, WhatsApp, and Web Form.

The agent replaces Tier-1 human support for technical, billing-clarification, and general inquiries. It escalates Tier-2 cases (pricing negotiations, refunds, legal threats, low-sentiment conversations) to human agents with full context preserved.

---

## 2. Problem Statement

CloudScale AI's support team handles 200+ tickets per day across three channels. 68% of tickets are Tier-1 (how-to, error codes, general product questions) that follow a predictable resolution pattern from product documentation. Manual handling costs:

- **4-hour average response time** on Business plan (SLA target: 4 hours)
- **Human error** in escalation routing (wrong team assigned 23% of the time)
- **No cross-channel continuity** — customers who emailed and then sent a WhatsApp had to repeat context

**Solution:** An AI FTE that handles Tier-1 instantly, routes Tier-2 accurately, and maintains full cross-channel conversation context.

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    INBOUND CHANNELS                      │
│                                                          │
│  Gmail (OAuth2)    WhatsApp (Twilio)    Web Form         │
│       │                  │               │               │
│       └──────────────────┴───────────────┘               │
│                          │                               │
│               FastAPI Webhook Layer                       │
│         (NormalizedTicketEvent normalization)            │
└──────────────────────────┬──────────────────────────────┘
                           │
                    Apache Kafka
                  Topic: fte.tickets.incoming
                           │
┌──────────────────────────┴──────────────────────────────┐
│                   MESSAGE PROCESSOR                       │
│                                                          │
│   1. resolve_customer()      → Neon PostgreSQL           │
│   2. get_or_create_conversation()                        │
│   3. store_inbound_message()                             │
│   4. _check_guardrails()     → keyword scan (O(1))       │
│   5. load_history()          → conversation context      │
│   6. Runner.run()            → Groq LLaMA 3.3 70B        │
│   7. record_latency_metric()                             │
└──────────────────────────┬──────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            │        Agent Tools          │
            │                             │
            │  search_knowledge_base()    │ ← pgvector RAG
            │  create_ticket()            │ ← Neon PostgreSQL
            │  get_customer_history()     │ ← Neon PostgreSQL
            │  escalate_to_human()        │ ← DB + alert
            │  send_response()            │ ← Gmail/Twilio/JSON
            └─────────────────────────────┘
```

### 3.2 Technology Stack

| Component | Technology | Version | Purpose |
|---|---|---|---|
| API Framework | FastAPI | 0.115+ | Webhook endpoints, health check |
| Message Broker | Apache Kafka | 3.7.0 | Async message queuing |
| AI Model | Groq `llama-3.3-70b-versatile` | — | Agent reasoning + responses |
| Agent SDK | OpenAI Agents SDK | 0.0.14+ | Tool orchestration, Runner |
| Database | Neon PostgreSQL | pg 16 | All persistent state |
| Vector Search | pgvector | 0.7+ | Semantic KB search (`VECTOR(384)`) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | 384 dims | Local, no API key |
| Email | Gmail API + Google Pub/Sub | v1 | Push notifications, OAuth2 |
| WhatsApp | Twilio Messaging API | 9.0+ | Inbound/outbound messages |
| Runtime | Python | 3.14 | All application code |
| Tunneling (Dev) | ngrok | — | Local webhook exposure |

---

## 4. Functional Requirements

### FR-01: Multi-Channel Intake
- System MUST accept inbound messages from Gmail, WhatsApp (Twilio), and Web Form
- Each channel webhook MUST return HTTP 200 within 200 ms
- All channels MUST normalize to `NormalizedTicketEvent` before queuing

### FR-02: Customer Identity Resolution
- System MUST resolve returning customers by email (primary) or WhatsApp phone (secondary)
- System MUST create new customer records for first-time contacts
- System MUST link cross-channel contacts to the same customer record

### FR-03: Conversation Continuity
- System MUST maintain conversation context within a 24-hour window
- Agent MUST retrieve prior messages before responding
- Agent MUST acknowledge prior cross-channel contact when relevant

### FR-04: Agent Tool Workflow (Mandatory Order)
1. `create_ticket` — ALWAYS first
2. `get_customer_history` — ALWAYS second
3. `search_knowledge_base` — when product question detected (max 2 attempts)
4. `escalate_to_human` — when escalation rule triggered
5. `send_response` — ALWAYS last; the only way a reply is sent

### FR-05: Pre-Agent Guardrails
System MUST escalate WITHOUT invoking the LLM when any of these are detected:
- Pricing keywords: `price`, `pricing`, `cost`, `fee`, `subscription`, `plan`, `quote`
- Refund keywords: `refund`, `chargeback`, `reimburse`, `money back`
- Legal keywords: `lawyer`, `attorney`, `sue`, `lawsuit`
- Human request: `human`, `agent`, `person`, `representative`
- Profanity: flagged keywords list

### FR-06: Knowledge Base RAG
- System MUST search `knowledge_base` table using cosine similarity (`pgvector`)
- Minimum relevance threshold: 0.20 cosine similarity
- If top result ≥ 0.15 but < 0.20, return best match rather than empty
- ILIKE full-text fallback when vector search returns no results

### FR-07: Escalation Handling
- Escalated tickets MUST have `priority=high`, `status=escalated`
- Conversation MUST be marked `escalated_to=human_agent`
- Escalation reason MUST be logged in ticket record

### FR-08: Channel-Specific Response Formatting
- **Email:** Full HTML-friendly response with greeting and sign-off
- **WhatsApp:** ≤ 500 characters; numbered steps for multi-part answers
- **Web Form:** Structured JSON response; no character limit

### FR-09: Metrics Collection
- System MUST record `response_latency_ms` per message in `agent_metrics`
- Metrics MUST include `channel` dimension for per-channel analysis

---

## 5. Non-Functional Requirements

| Requirement | Target | Current Status |
|---|---|---|
| Webhook response time | < 200 ms | ✅ (Kafka offloads processing) |
| Agent response time (E2E) | < 15 seconds | ✅ (Groq ~2-4s, typical) |
| Uptime | 99.9% | ✅ (Neon + Groq SLAs) |
| Knowledge base search | < 100 ms | ✅ (pgvector ivfflat index) |
| Concurrent messages | 10+ | ✅ (Kafka consumer group) |
| Data retention | 90 days messages | ✅ (Neon storage) |

---

## 6. Data Model Summary

### Core Tables

```sql
customers           -- id, email, phone, name, metadata
customer_identifiers -- id, customer_id, type (email/whatsapp/phone), value
conversations       -- id, customer_id, channel, status, sentiment_score
messages            -- id, conversation_id, channel, direction, role, content
tickets             -- id, conversation_id, customer_id, category, priority, status
knowledge_base      -- id, title, content, category, embedding VECTOR(384)
channel_configs     -- id, channel, enabled, config (JSONB)
agent_metrics       -- id, metric_name, metric_value, channel, recorded_at
```

### Key Indexes
- `idx_customers_email` — email lookup O(log n)
- `idx_knowledge_embedding` — ivfflat cosine similarity (lists=10)
- `idx_conversations_status` — active conversation lookup
- `idx_messages_conversation` — history retrieval

---

## 7. File Structure (PDF Page 12 Compliant)

```
CRM-Digital-FTE/
├── app/
│   ├── agents/
│   │   ├── customer_success_agent.py   # Agent definition + tool registry
│   │   ├── tools.py                    # 5 @function_tool definitions
│   │   ├── prompts.py                  # System prompt with workflow rules
│   │   └── formatters.py              # Channel-specific response formatters
│   ├── api/
│   │   ├── main.py                    # FastAPI app + lifespan
│   │   ├── webhooks.py                # Gmail + WhatsApp routers
│   │   └── models.py                  # Pydantic schemas
│   ├── channels/
│   │   ├── web_form_handler.py        # Web Form router (POST /webhooks/webform)
│   │   ├── gmail_handler.py           # Gmail OAuth2 + message fetch
│   │   └── whatsapp_handler.py        # Twilio response sender
│   ├── core/
│   │   ├── ai_client.py               # Groq client configuration
│   │   ├── kafka.py                   # AIOKafka producer wrapper
│   │   └── config.py                  # Environment config
│   ├── db/
│   │   ├── session.py                 # asyncpg pool management
│   │   └── queries.py                 # All DB access functions (centralized)
│   └── worker/
│       └── message_processor.py       # Kafka consumer + agent orchestrator
├── context/
│   ├── company-profile.md             # CloudScale AI company profile
│   ├── product-docs.md               # Technical docs for RAG (26 KB chunks)
│   ├── sample-tickets.json           # 55 representative tickets
│   ├── escalation-rules.md           # 7 escalation rules with thresholds
│   └── brand-voice.md                # Tone and communication guidelines
├── database/
│   ├── schema.sql                    # Current schema (reference copy)
│   └── migrations/
│       └── 001_initial_schema.sql    # Versioned migration
├── scripts/
│   └── seed_kb.py                    # KB seeding with embeddings
├── specs/                            # THIS FOLDER
│   ├── discovery-log.md
│   ├── customer-success-fte-spec.md
│   └── transition-checklist.md
├── tests/
│   ├── test_agent.py
│   ├── test_channels.py
│   └── test_e2e.py
├── web-form/                         # Next.js support form UI
├── k8s/                              # Kubernetes manifests
├── Dockerfile
└── requirements.txt
```

---

## 8. Agent Behavior Specification

### 8.1 System Prompt Rules (Enforced)

```
NEVER discuss pricing → escalate_to_human(reason="pricing_inquiry")
NEVER promise refunds → escalate_to_human(reason="refund_request")
NEVER respond without send_response tool
ALWAYS create_ticket first
ALWAYS get_customer_history second
search_knowledge_base max 2 attempts before escalating
```

### 8.2 Escalation Decision Tree

```
Inbound message
    │
    ├─ Guardrail match? ──YES──► Escalate (no LLM call)
    │
    └─ NO → LLM runs
              │
              ├─ Sentiment < 0.3? ──YES──► escalate_to_human()
              │
              ├─ Legal/refund/pricing mention? ──YES──► escalate_to_human()
              │
              ├─ KB search failed 2x? ──YES──► escalate_to_human()
              │
              └─ Resolved → send_response()
```

### 8.3 Channel Response Constraints

| Channel | Max Length | Format | Sign-off |
|---|---|---|---|
| Email | None | Full paragraphs + headers | "Best regards, CloudScale AI Support" |
| WhatsApp | 500 chars | Numbered lists | None (semi-formal) |
| Web Form | None | Structured JSON | Neutral professional |

---

## 9. Security Considerations

- Gmail credentials stored in `credentials/gmail_credentials.json` — excluded from git via `.gitignore`
- Twilio signature validation enforced in `ENVIRONMENT=production`
- Database credentials via environment variables only — never hardcoded
- `channel_binding=require` on Neon connection string
- No user-supplied data is embedded raw in SQL (vector literals are ML-generated floats only)

---

## 10. Known Limitations (v1.0)

1. **Gmail Watch expires every 7 days** — manual renewal required (cron job planned for v1.1)
2. **Single Kafka partition** — sufficient for current volume; partitioning needed at > 100 msg/s
3. **No retry queue** — failed agent runs are logged but not retried (dead-letter queue planned)
4. **Knowledge base is static** — requires manual `seed_kb.py` re-run when docs change
5. **No admin dashboard** — metrics only accessible via raw DB queries
