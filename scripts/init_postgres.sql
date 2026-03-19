-- ─────────────────────────────────────────────────
-- FinAgent — PostgreSQL Initialization
-- Runs once when the container starts for the first time
-- ─────────────────────────────────────────────────

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- for similarity() function (duplicate detection)
CREATE EXTENSION IF NOT EXISTS "unaccent";  -- for accent-insensitive search

-- Core tables (shared across all tenants)
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    business_name VARCHAR(255),
    plan VARCHAR(20) DEFAULT 'free',
    whatsapp_number VARCHAR(30) UNIQUE,
    telegram_chat_id VARCHAR(50) UNIQUE,
    agent_id UUID,
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    avatar_url VARCHAR(500),
    whatsapp_number VARCHAR(30),
    telegram_username VARCHAR(100),
    personality JSONB NOT NULL DEFAULT '{}',
    backstory TEXT NOT NULL DEFAULT '',
    greeting_templates JSONB DEFAULT '[]',
    confirmation_style VARCHAR(50) DEFAULT 'brief',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS imported_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    document_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA256 of file content
    filename VARCHAR(500),
    document_type VARCHAR(50),   -- bank_statement | receipt | invoice
    bank_name VARCHAR(100),
    transactions_imported INTEGER DEFAULT 0,
    duplicates_found INTEGER DEFAULT 0,
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────
-- Function to create per-tenant schemas
-- Called when a new client is registered
-- ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION create_tenant_schemas(p_tenant_id TEXT)
RETURNS VOID AS $$
DECLARE
    fin_schema TEXT := 'tenant_' || REPLACE(p_tenant_id, '-', '_') || '_financial';
    ctx_schema TEXT := 'tenant_' || REPLACE(p_tenant_id, '-', '_') || '_context';
BEGIN
    -- ── FINANCIAL SCHEMA ──────────────────────────
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', fin_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.accounts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(255) NOT NULL,
            type VARCHAR(50) DEFAULT ''checking'',
            currency VARCHAR(3) DEFAULT ''BRL'',
            initial_balance DECIMAL(15,2) DEFAULT 0,
            current_balance DECIMAL(15,2) DEFAULT 0,
            bank_name VARCHAR(100),
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', fin_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.categories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(255) NOT NULL,
            type VARCHAR(20) DEFAULT ''expense'',
            parent_id UUID,
            icon VARCHAR(50),
            color VARCHAR(7),
            is_system BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', fin_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.transactions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            account_id UUID,
            category_id UUID,
            type VARCHAR(20) NOT NULL,
            amount DECIMAL(15,2) NOT NULL,
            description TEXT NOT NULL,
            notes TEXT,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            due_date DATE,
            status VARCHAR(20) DEFAULT ''paid'',
            attachments JSONB DEFAULT ''[]'',
            tags TEXT[] DEFAULT ''{}'',
            source_channel VARCHAR(30) DEFAULT ''web'',
            document_hash VARCHAR(64),
            ai_confidence FLOAT,
            raw_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )', fin_schema);

    -- Index for duplicate detection
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%s_tx_dedup ON %I.transactions
        (date, amount, status)', replace(fin_schema, '.', '_'), fin_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.alerts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            type VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,
            condition JSONB DEFAULT ''{}'',
            message TEXT NOT NULL,
            channels TEXT[] DEFAULT ''{whatsapp}'',
            is_active BOOLEAN DEFAULT true,
            last_triggered TIMESTAMPTZ,
            trigger_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', fin_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.reports (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            type VARCHAR(50) NOT NULL,
            period_start DATE,
            period_end DATE,
            data JSONB DEFAULT ''{}'',
            generated_by VARCHAR(20) DEFAULT ''ai'',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', fin_schema);

    -- ── CONTEXT SCHEMA ────────────────────────────
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', ctx_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.conversation_history (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            agent_id UUID NOT NULL,
            session_id VARCHAR(100),
            channel VARCHAR(20) DEFAULT ''whatsapp'',
            role VARCHAR(20) NOT NULL,
            content TEXT,
            tool_calls JSONB,
            tool_results JSONB,
            model_used VARCHAR(100),
            tokens_used INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', ctx_schema);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%s_conv_agent ON %I.conversation_history
        (agent_id, created_at DESC)', replace(ctx_schema, '.', '_'), ctx_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.key_moments (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            agent_id UUID NOT NULL,
            type VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            importance INTEGER DEFAULT 3,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', ctx_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.agent_promises (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            agent_id UUID NOT NULL,
            promise TEXT NOT NULL,
            due_date TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) DEFAULT ''pending'',
            fulfilled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', ctx_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.behavioral_profiles (
            agent_id UUID PRIMARY KEY,
            profile_data JSONB NOT NULL DEFAULT ''{}'',
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )', ctx_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.embeddings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            agent_id UUID NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            entity_id UUID,
            content_text TEXT NOT NULL,
            embedding vector(1536),
            metadata JSONB DEFAULT ''{}'',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', ctx_schema);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%s_emb_vector ON %I.embeddings
        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)',
        replace(ctx_schema, '.', '_'), ctx_schema);

END;
$$ LANGUAGE plpgsql;
