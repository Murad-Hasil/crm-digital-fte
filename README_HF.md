---
title: CRM Digital FTE — CloudScale AI Customer Success
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# CloudScale AI Customer Success FTE

24/7 AI-powered customer support backend — Email, WhatsApp, and Web Form channels.

## API Endpoints

- `GET /health` — System health check
- `POST /webhooks/webform` — Web form submission
- `GET /support/ticket/{id}` — Ticket status
- `POST /webhooks/gmail` — Gmail Pub/Sub push
- `POST /webhooks/whatsapp` — Twilio WhatsApp webhook

## Required Secrets

Set these in Space Settings → Repository secrets:

- `DATABASE_URL` — Neon PostgreSQL connection string
- `GROQ_API_KEY` — Groq API key
- `TWILIO_ACCOUNT_SID` — Twilio account SID
- `TWILIO_AUTH_TOKEN` — Twilio auth token
- `TWILIO_WHATSAPP_NUMBER` — e.g. `whatsapp:+14155238886`
- `GMAIL_CREDENTIALS_JSON` — Full contents of `gmail_credentials.json`
- `CORS_ORIGINS` — Comma-separated allowed origins (e.g. your Vercel URL)
