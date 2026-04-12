# Agent Skills Manifest — CloudScale AI Customer Success FTE
## Exercise 1.5: Agent Skills Definition

**Document Type:** Incubation Phase Skills Crystallization (PDF Page 7)  
**Version:** 1.0.0  
**Author:** Murad Hasil  
**Date:** 2026-04-12

---

## Purpose

Agent Skills are the reusable, composable capabilities that the Customer Success FTE
can invoke autonomously. This manifest defines each skill — when to use it, its inputs,
its outputs, and how it maps from the incubation prototype to the production implementation.

---

## Skill 1: Knowledge Retrieval

**When to use:** Customer asks a product or technical question that may be answered
from documentation (features, APIs, how-to guides, configuration).

**Trigger:** After `create_ticket`, before forming a response — if a product question is detected.

| Property | Detail |
|----------|--------|
| Inputs | `query` (str) — natural-language question extracted from customer message |
| Outputs | Ranked documentation snippets with relevance scores |
| Max attempts | 2 (escalate to human if 2 attempts yield no relevant result) |
| Fallback | ILIKE keyword search when vector similarity returns 0 results |

**Incubation implementation:** Simple string matching against in-memory docs  
**Production implementation:** `search_knowledge_base()` in `app/agents/tools.py`  
→ pgvector cosine similarity (`all-MiniLM-L6-v2`, 384-dim) on Neon PostgreSQL

---

## Skill 2: Sentiment Analysis

**When to use:** Every inbound customer message — run before LLM invocation to detect
hostile or distressed sentiment.

**Trigger:** Pre-agent, on every message (implemented as guardrail scan).

| Property | Detail |
|----------|--------|
| Inputs | `content` (str) — raw customer message text |
| Outputs | `should_escalate` (bool), `reason` (str), sentiment bucket |
| Escalation threshold | Profanity detected OR legal language detected |
| Confidence | O(1) keyword-set intersection — deterministic, not probabilistic |

**5 sentiment buckets:**
- `pricing_inquiry` — price/cost/fee/subscription/quote keywords
- `refund_request` — refund/chargeback/reimburse keywords
- `legal_threat` — lawyer/attorney/sue/lawsuit/court keywords
- `customer_requested_human` — human/agent/representative keywords
- `aggressive_language` — profanity keywords

**Incubation implementation:** Simple keyword scan  
**Production implementation:** `_check_guardrails()` in `app/worker/message_processor.py`

---

## Skill 3: Escalation Decision

**When to use:** After generating a response, if any escalation condition is met
(guardrail or agent-detected).

**Trigger:** Guardrail fires pre-LLM OR agent calls `escalate_to_human` tool after KB search fails twice.

| Property | Detail |
|----------|--------|
| Inputs | `ticket_id` (str), `reason` (str), `urgency` (str: 'normal' \| 'urgent') |
| Outputs | Escalation reference ID, SLA confirmation |
| DB writes | Ticket `status → escalated`, conversation `escalated_to → human_agent` |

**Escalation rules (from `context/escalation-rules.md`):**
1. Pricing or refund inquiry → immediate escalation
2. Legal language → immediate escalation (urgent)
3. Profanity / aggressive tone → escalation after empathetic response attempt
4. KB search fails twice → escalation with search context attached
5. Customer explicitly requests human → immediate escalation
6. Sentiment < 0.3 (future: LLM-scored) → escalation
7. Complex technical issue beyond KB scope → escalation

**Incubation implementation:** If/else rule tree  
**Production implementation:** `escalate_to_human()` in `app/agents/tools.py`

---

## Skill 4: Channel Adaptation

**When to use:** Before every outbound message — format the raw agent response
for the target channel's constraints and communication style.

**Trigger:** Always — called inside `send_response()` before any dispatch.

| Property | Detail |
|----------|--------|
| Inputs | `response` (str), `channel` (str: email \| whatsapp \| web_form), `ticket_id` (str) |
| Outputs | Formatted message string ready for channel transport |

**Channel rules:**

| Channel | Style | Max Length | Required Elements |
|---------|-------|-----------|-------------------|
| `email` | Formal, detailed | 500 words | Greeting, sign-off, ticket ref, AI disclaimer |
| `whatsapp` | Conversational, concise | 300 chars | Truncation with `...`, escalation hint |
| `web_form` | Semi-formal | 300 words | Support portal footer |

**Incubation implementation:** Inline f-string formatting  
**Production implementation:** `format_for_channel()` in `app/agents/formatters.py`

---

## Skill 5: Customer Identification

**When to use:** On every incoming message — resolve or create the unified customer record
before processing begins.

**Trigger:** First step in `process_message()`, before any agent interaction.

| Property | Detail |
|----------|--------|
| Inputs | Raw message dict with `customer_email` or `customer_phone` |
| Outputs | `customer_id` (UUID) — unified cross-channel identity |
| Deduplication | Same email from Email + Web Form → same customer record |
| Cross-channel | WhatsApp phone → linked to same customer as email conversations |

**Resolution logic:**
1. Look up `customer_identifiers` table by email or phone
2. If found → return existing `customer_id`
3. If not found → INSERT new `customers` record + `customer_identifiers` entry
4. Conversation created or retrieved for this `(customer_id, channel)` pair

**Incubation implementation:** Dict lookup with email as key  
**Production implementation:** `resolve_customer()` in `app/db/queries.py`

---

## Skills → Production Tools Mapping

| Incubation Skill | Production Component | File |
|-----------------|---------------------|------|
| Knowledge Retrieval | `search_knowledge_base` @function_tool | `app/agents/tools.py` |
| Sentiment Analysis | `_check_guardrails()` | `app/worker/message_processor.py` |
| Escalation Decision | `escalate_to_human` @function_tool | `app/agents/tools.py` |
| Channel Adaptation | `format_for_channel()` | `app/agents/formatters.py` |
| Customer Identification | `resolve_customer()` | `app/db/queries.py` |

---

## Skills Test Coverage

| Skill | Test File | Test Count | Status |
|-------|-----------|------------|--------|
| Knowledge Retrieval | `tests/test_channels.py` | 3 (web_form formatter) | ✅ |
| Sentiment Analysis | `tests/test_agent.py` | 18 | ✅ |
| Escalation Decision | `tests/test_agent.py` + `tests/test_e2e.py` | 11 | ✅ |
| Channel Adaptation | `tests/test_channels.py` | 17 | ✅ |
| Customer Identification | `tests/test_e2e.py` | 6 | ✅ |
| **Total** | | **45** | **✅ All passing** |
