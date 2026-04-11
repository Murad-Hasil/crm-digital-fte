-- =============================================================================
-- CUSTOMER SUCCESS FTE - CRM / TICKET MANAGEMENT SYSTEM
-- =============================================================================
-- This PostgreSQL schema is the complete CRM for tracking:
--   - Customers (unified across all channels)
--   - Conversations and message history
--   - Support tickets and their lifecycle
--   - Knowledge base for AI/RAG responses
--   - Channel configurations
--   - Agent performance metrics
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector for semantic search

-- =============================================================================
-- CUSTOMERS
-- Unified customer record across all channels.
-- Primary identifier is email; phone used for WhatsApp cross-matching.
-- =============================================================================
CREATE TABLE customers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) UNIQUE,
    phone       VARCHAR(50),
    name        VARCHAR(255),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata    JSONB DEFAULT '{}'
);

-- =============================================================================
-- CUSTOMER IDENTIFIERS
-- Maps channel-specific identifiers (email, phone, whatsapp) to a customer.
-- Enables cross-channel customer resolution.
-- =============================================================================
CREATE TABLE customer_identifiers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id      UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    identifier_type  VARCHAR(50) NOT NULL,  -- 'email', 'phone', 'whatsapp'
    identifier_value VARCHAR(255) NOT NULL,
    verified         BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (identifier_type, identifier_value)
);

-- =============================================================================
-- CONVERSATIONS
-- One conversation per customer session. Tracks sentiment and escalation state.
-- =============================================================================
CREATE TABLE conversations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id      UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    initial_channel  VARCHAR(50) NOT NULL,  -- 'email', 'whatsapp', 'web_form'
    started_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at         TIMESTAMP WITH TIME ZONE,
    status           VARCHAR(50) DEFAULT 'active',  -- 'active', 'resolved', 'escalated', 'closed'
    sentiment_score  DECIMAL(3, 2),                 -- 0.00 to 1.00
    resolution_type  VARCHAR(50),
    escalated_to     VARCHAR(255),
    metadata         JSONB DEFAULT '{}'
);

-- =============================================================================
-- MESSAGES
-- Individual messages within a conversation. Tracks direction, role, latency,
-- tool calls, and the external message ID for each channel.
-- =============================================================================
CREATE TABLE messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    channel             VARCHAR(50) NOT NULL,   -- 'email', 'whatsapp', 'web_form'
    direction           VARCHAR(20) NOT NULL,   -- 'inbound', 'outbound'
    role                VARCHAR(20) NOT NULL,   -- 'customer', 'agent', 'system'
    content             TEXT NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tokens_used         INTEGER,
    latency_ms          INTEGER,
    tool_calls          JSONB DEFAULT '[]',
    channel_message_id  VARCHAR(255),           -- Gmail message ID, Twilio SID, etc.
    delivery_status     VARCHAR(50) DEFAULT 'pending'  -- 'pending', 'sent', 'delivered', 'failed'
);

-- =============================================================================
-- TICKETS
-- Support ticket linked to a conversation. Tracks category, priority, status,
-- source channel, and resolution.
-- =============================================================================
CREATE TABLE tickets (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id   UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    customer_id       UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    source_channel    VARCHAR(50) NOT NULL,
    category          VARCHAR(100),
    priority          VARCHAR(20) DEFAULT 'medium',  -- 'low', 'medium', 'high', 'urgent'
    status            VARCHAR(50) DEFAULT 'open',    -- 'open', 'processing', 'resolved', 'escalated', 'closed'
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at       TIMESTAMP WITH TIME ZONE,
    resolution_notes  TEXT
);

-- =============================================================================
-- KNOWLEDGE BASE
-- Product documentation entries with vector embeddings for semantic (RAG) search.
-- embedding uses VECTOR(1536) to be compatible with OpenAI/Groq embedding models.
-- =============================================================================
CREATE TABLE knowledge_base (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(500) NOT NULL,
    content     TEXT NOT NULL,
    category    VARCHAR(100),
    embedding   VECTOR(1536),  -- Semantic search via pgvector cosine similarity
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- CHANNEL CONFIGS
-- Per-channel runtime configuration: API keys, webhook URLs, response templates,
-- and character limits. Stored as JSONB for flexibility.
-- =============================================================================
CREATE TABLE channel_configs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel              VARCHAR(50) UNIQUE NOT NULL,  -- 'email', 'whatsapp', 'web_form'
    enabled              BOOLEAN DEFAULT TRUE,
    config               JSONB NOT NULL DEFAULT '{}',  -- API keys, webhook URLs, etc.
    response_template    TEXT,
    max_response_length  INTEGER,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- AGENT METRICS
-- Time-series performance metrics per channel.
-- Tracks latency, escalation rate, accuracy, token usage, etc.
-- =============================================================================
CREATE TABLE agent_metrics (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name   VARCHAR(100) NOT NULL,
    metric_value  DECIMAL(10, 4) NOT NULL,
    channel       VARCHAR(50),               -- Optional channel dimension
    dimensions    JSONB DEFAULT '{}',        -- Additional key/value dimensions
    recorded_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- As specified in PDF page 24.
-- =============================================================================

-- Customer lookups
CREATE INDEX idx_customers_email
    ON customers(email);

CREATE INDEX idx_customer_identifiers_value
    ON customer_identifiers(identifier_value);

-- Conversation lookups
CREATE INDEX idx_conversations_customer
    ON conversations(customer_id);

CREATE INDEX idx_conversations_status
    ON conversations(status);

CREATE INDEX idx_conversations_channel
    ON conversations(initial_channel);

-- Message lookups
CREATE INDEX idx_messages_conversation
    ON messages(conversation_id);

CREATE INDEX idx_messages_channel
    ON messages(channel);

-- Ticket lookups
CREATE INDEX idx_tickets_status
    ON tickets(status);

CREATE INDEX idx_tickets_channel
    ON tickets(source_channel);

CREATE INDEX idx_tickets_customer
    ON tickets(customer_id);

-- Knowledge base: vector similarity search (cosine)
CREATE INDEX idx_knowledge_embedding
    ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops);
