# CRM Digital FTE — AI Customer Success Agent

A production-grade AI-powered customer support system built for **Hackathon 5** of the CRM Digital FTE Factory program. The system acts as a 24/7 autonomous AI employee handling customer support across three channels simultaneously: **Email (Gmail)**, **WhatsApp**, and a **Web Support Form**.

---

## What It Does

A customer sends a support request via any channel. The AI agent:
1. Creates a support ticket in the database
2. Retrieves the customer's history
3. Searches the knowledge base for relevant solutions
4. Responds in a channel-appropriate tone and format
5. Escalates to a human agent when needed (pricing, refunds, legal, profanity)

All of this happens automatically, in real time, with no human in the loop.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTAKE CHANNELS                          │
│                                                                 │
│   Gmail Inbox          WhatsApp           Web Support Form      │
│       │                    │                     │              │
│  Google Pub/Sub       Twilio API            Next.js UI          │
└───────┼────────────────────┼─────────────────────┼─────────────┘
        │                    │                     │
        ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI (Python)                             │
│                                                                 │
│   POST /webhooks/gmail    POST /webhooks/whatsapp               │
│   POST /webhooks/webform  GET  /health                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Normalize → Kafka
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Apache Kafka  (fte.tickets.incoming)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Consume
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Message Processor (Worker)                   │
│                                                                 │
│   1. Resolve / create customer                                  │
│   2. Get or create conversation                                 │
│   3. Store inbound message                                      │
│   4. Guardrail check (pricing, legal, profanity)                │
│   5. Load conversation history                                  │
│   6. Run AI Agent (OpenAI Agents SDK → Groq)                    │
│   7. Send reply via channel handler                             │
│   8. Log latency metric                                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         Gmail API     Twilio API    Web Response
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Neon PostgreSQL + pgvector                         │
│  customers │ conversations │ messages │ tickets │ knowledge_base │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | OpenAI Agents SDK (configured for Groq) |
| LLM | `llama-3.3-70b-versatile` via Groq API |
| Backend API | FastAPI (Python, async) |
| Message Queue | Apache Kafka (aiokafka) |
| Database | Neon PostgreSQL + pgvector |
| Email | Gmail API + Google Pub/Sub webhooks |
| WhatsApp | Twilio WhatsApp Sandbox |
| Web Form | Next.js 15 + Tailwind CSS (glassmorphism UI) |
| Tunnel | ngrok (local webhook exposure) |
| Infrastructure | Docker (Kafka), Kubernetes manifests included |

---

## Agent Tools

The AI agent has 5 tools registered via the OpenAI Agents SDK:

| Tool | Description |
|------|-------------|
| `create_ticket` | Always called first — creates a ticket in PostgreSQL |
| `get_customer_history` | Fetches cross-channel conversation history |
| `search_knowledge_base` | Semantic search over product docs via pgvector |
| `escalate_to_human` | Routes to human agent with reason + urgency |
| `send_response` | Always called last — sends channel-appropriate reply |

### Agent Behavior Rules
- **Always:** `create_ticket` → `get_customer_history` → `search_knowledge_base` → `send_response`
- **Auto-escalate** on: pricing inquiries, refund requests, legal threats, profanity, explicit human request
- **Email:** formal tone, up to 500 words, greeting + signature
- **WhatsApp:** max 300 chars, conversational
- **Web Form:** semi-formal, up to 300 words

---

## Channel Flow Details

### Gmail
```
Email received → Gmail API → Google Pub/Sub notification →
ngrok → POST /webhooks/gmail → Kafka → Worker → 
Groq AI Agent → Gmail API send_reply
```

### WhatsApp
```
WhatsApp message → Twilio → ngrok → POST /webhooks/whatsapp →
Kafka → Worker → Groq AI Agent → Twilio send_message
```

### Web Form
```
User submits form → Next.js → POST /webhooks/webform →
Kafka → Worker → Groq AI Agent → ticket stored in DB
```

---

## Database Schema

8 tables in Neon PostgreSQL:

- `customers` — unified customer records (email as primary key)
- `customer_identifiers` — cross-channel matching (email, phone, whatsapp)
- `conversations` — per-channel conversation sessions
- `messages` — individual messages with role tracking
- `tickets` — support tickets with full lifecycle
- `knowledge_base` — product docs with 1536-dim vector embeddings
- `channel_configs` — per-channel settings
- `agent_metrics` — response latency tracking

---

## Kafka Topics

| Topic | Purpose |
|-------|---------|
| `fte.tickets.incoming` | Unified inbound queue (all channels) |
| `fte.channels.email.inbound/outbound` | Email channel events |
| `fte.channels.whatsapp.inbound/outbound` | WhatsApp channel events |
| `fte.escalations` | Escalation events |
| `fte.metrics` | Performance metrics |
| `fte.dlq` | Dead letter queue |

---

## Project Structure

```
CRM-Digital-FTE/
├── app/
│   ├── agents/
│   │   ├── customer_success_agent.py   # OpenAI Agents SDK agent
│   │   ├── tools.py                    # @function_tool definitions
│   │   ├── prompts.py                  # System prompts
│   │   └── formatters.py              # Channel-specific formatting
│   ├── api/
│   │   ├── main.py                    # FastAPI app + lifespan
│   │   ├── webhooks.py                # All channel webhooks
│   │   └── models.py                  # Pydantic models
│   ├── channels/
│   │   ├── gmail_handler.py           # Gmail API send/receive
│   │   └── whatsapp_handler.py        # Twilio WhatsApp
│   ├── core/
│   │   ├── ai_client.py               # Groq client setup
│   │   ├── config.py                  # App configuration
│   │   └── kafka.py                   # Kafka producer
│   ├── db/
│   │   └── session.py                 # asyncpg connection pool
│   └── worker/
│       ├── message_processor.py       # Kafka consumer + agent runner
│       └── metrics_collector.py       # Performance metrics
├── web-form/                          # Next.js support form
├── database/
│   └── schema.sql                    # PostgreSQL + pgvector schema
├── k8s/                              # Kubernetes manifests
├── credentials/
│   ├── client_secret.json            # Google OAuth2 client (gitignored)
│   └── gmail_credentials.json        # OAuth2 token (gitignored)
├── setup_gmail_auth.py               # One-time Gmail OAuth2 setup
├── Dockerfile
├── requirements.txt
└── .env                              # Environment variables (gitignored)
```

---

## Setup Guide

### Prerequisites
- Python 3.11+ (tested on 3.14)
- Node.js 20+
- Docker
- PostgreSQL client (`psql`)
- ngrok account (free)
- Groq API key (free at console.groq.com)
- Google Cloud project with Gmail API enabled
- Twilio account with WhatsApp Sandbox

### 1. Clone & Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd web-form && npm install && cd ..
```

### 2. Environment Variables

Copy and fill `.env`:

```bash
# Database (Neon or local PostgreSQL)
DATABASE_URL=postgresql://user:password@host/dbname

# Groq API
GROQ_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
MODEL_NAME=llama-3.3-70b-versatile
OPENAI_AGENTS_DISABLE_TRACING=1

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Gmail
GMAIL_CREDENTIALS_PATH=credentials/gmail_credentials.json
GMAIL_PUBSUB_TOPIC=projects/YOUR_PROJECT_ID/topics/gmail-push

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

### 3. Gmail OAuth2 Setup (one-time)

```bash
# Download client_secret.json from Google Cloud Console
# APIs & Services → Credentials → OAuth 2.0 Client ID → Desktop App

mv ~/Downloads/client_secret_*.json credentials/client_secret.json
python setup_gmail_auth.py
# Browser opens → login → allow → token saved automatically
```

### 4. Google Pub/Sub Setup

```bash
# In Google Cloud Console:
# 1. Pub/Sub → Topics → Create Topic → ID: gmail-push
# 2. Subscriptions → gmail-push-sub → Edit → Delivery: Push
#    Push URL: https://YOUR_NGROK_URL/webhooks/gmail
# 3. Topics → gmail-push → Permissions → Add Principal:
#    gmail-api-push@system.gserviceaccount.com → Role: Pub/Sub Publisher

# Then activate Gmail watch:
python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
creds = Credentials.from_authorized_user_file('credentials/gmail_credentials.json')
service = build('gmail', 'v1', credentials=creds)
result = service.users().watch(userId='me', body={
    'topicName': 'projects/YOUR_PROJECT_ID/topics/gmail-push',
    'labelIds': ['INBOX']
}).execute()
print(result)
"
```

### 5. Database Schema

```bash
psql \$DATABASE_URL -f database/schema.sql
```

### 6. Kafka (Docker)

```bash
docker run -d --name kafka \
  -p 9092:9092 \
  -e KAFKA_NODE_ID=1 \
  -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
  -e KAFKA_LOG_DIRS=/tmp/kraft-combined-logs \
  apache/kafka:3.7.0
```

### 7. Twilio WhatsApp Sandbox

```
Twilio Console → Messaging → Try it out → Send a WhatsApp message
→ Sandbox Settings → When a message comes in:
   https://YOUR_NGROK_URL/webhooks/whatsapp
```

---

## Running the System

Open 4 terminals:

```bash
# Terminal 1 — FastAPI Backend
source venv/bin/activate
uvicorn app.api.main:app --reload
# → http://127.0.0.1:8000
# → http://127.0.0.1:8000/docs (Swagger UI)

# Terminal 2 — Message Worker
source venv/bin/activate
python -m app.worker.message_processor

# Terminal 3 — Web Support Form
cd web-form && npm run dev
# → http://localhost:3000

# Terminal 4 — ngrok tunnel (for webhooks)
ngrok http 8000
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | System health check |
| `POST` | `/webhooks/webform` | Web form submission |
| `GET` | `/support/ticket/{id}` | Ticket status |
| `POST` | `/webhooks/gmail` | Gmail Pub/Sub push |
| `POST` | `/webhooks/whatsapp` | Twilio WhatsApp webhook |
| `POST` | `/webhooks/whatsapp/status` | WhatsApp delivery status |

Full interactive docs: `http://127.0.0.1:8000/docs`

---

## Kubernetes

Manifests included in `k8s/` for production deployment:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/hpa.yaml
```

---

## Key Engineering Decisions

**Why Groq instead of OpenAI?**
Free tier with `llama-3.3-70b-versatile` is fast enough for hackathon demo. The OpenAI Agents SDK works with any OpenAI-compatible API via `base_url` override.

**Why Kafka for a prototype?**
Decouples webhook response time from AI processing time. Webhooks return in <200ms; AI takes 5-20 seconds. Without Kafka, Twilio and Gmail would timeout waiting for the response.

**Why Neon PostgreSQL?**
Serverless, free tier, built-in pgvector support. No infrastructure to manage.

**Why asyncpg over psycopg2?**
Full async support for FastAPI and the worker's async Kafka consumer loop.

---

## Challenges & Fixes

| Challenge | Fix |
|-----------|-----|
| asyncpg `search_path` not applying (Python 3.14 bug) | Used `public.tablename` fully qualified names in all queries |
| Gmail watch returning 403 | Added `gmail-api-push@system.gserviceaccount.com` as Pub/Sub Publisher |
| Groq rejecting `'customer'` and `'agent'` roles | Mapped to `'user'` and `'assistant'` in history loader |
| `google-auth-oauthlib` missing | Added to `requirements.txt` |
| DATABASE_URL pointing to Neon, schema on localhost | Re-ran schema against Neon cloud database |
| Kafka not installed | Ran via Docker single-node KRaft mode |

---

## Live Demo Flow

1. Open `http://localhost:3000` — fill the support form → submit
2. Check Terminal 2 — watch ticket creation + AI response
3. Send email to your Gmail inbox — watch Pub/Sub → AI → auto-reply
4. Send WhatsApp to Twilio sandbox → watch AI respond
5. Open `http://127.0.0.1:8000/docs` — explore all endpoints

---

## Built By

**Murad Hasil** — Hackathon 5, CRM Digital FTE Factory Program

> Building AI systems that work at 3 AM so humans don't have to.
