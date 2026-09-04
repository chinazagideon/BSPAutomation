-- ============================================================================
-- ENTERPRISE SCHEMA EVOLUTION: CENTRALIZED KNOWLEDGE BASE & AI WALLETS (ADR-0039, ADR-0040)
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS knowledge;

-- 1. Unified Knowledge Entries Table (Polymorphic, Tri-Modal)
CREATE TABLE IF NOT EXISTS knowledge.entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id UUID REFERENCES core.merchants(id) ON DELETE CASCADE, -- NULL indicates global system knowledge
  entry_type VARCHAR(32) NOT NULL DEFAULT 'FAQ',                   -- CATALOG, POLICY, FAQ, SLANG_EXPRESSION, DOC_CHUNK
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigram index for sub-millisecond phrase & slang matching
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_trgm_content
  ON knowledge.entries USING gin (content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_trgm_title
  ON knowledge.entries USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_merchant_type
  ON knowledge.entries (merchant_id, entry_type);

-- 2. Centralized AI Wallets Table in Core
CREATE TABLE IF NOT EXISTS core.ai_wallets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id UUID NOT NULL UNIQUE REFERENCES core.merchants(id) ON DELETE CASCADE,
  balance_kobo BIGINT NOT NULL DEFAULT 0,
  monthly_hard_cap_kobo BIGINT NOT NULL DEFAULT 1000000, -- ₦10,000 default cap
  bundled_tokens_remaining INTEGER NOT NULL DEFAULT 10000,
  total_tokens_consumed BIGINT NOT NULL DEFAULT 0,
  total_kobo_spent BIGINT NOT NULL DEFAULT 0,
  estimated_kobo_saved BIGINT NOT NULL DEFAULT 0,
  is_locked BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Centralized AI Token Ledger Table with Source Context Attribution
CREATE TABLE IF NOT EXISTS core.ai_token_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  source_context VARCHAR(32) NOT NULL DEFAULT 'INGRESS', -- INGRESS, DESK, RESERVATIONS, CHECKOUT
  task_priority VARCHAR(32) NOT NULL DEFAULT 'CUSTOMER_FACING', -- CUSTOMER_FACING, INTERNAL_ADMIN
  tokens_consumed INTEGER NOT NULL,
  kobo_cost BIGINT NOT NULL DEFAULT 0,
  model_name VARCHAR(64) NOT NULL DEFAULT 'gemini-3.7-flash',
  reference_id VARCHAR(128),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_token_ledger_merchant_source
  ON core.ai_token_ledger (merchant_id, source_context);

-- 4. Multi-Tenant Row-Level Security (RLS)
ALTER TABLE knowledge.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.ai_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.ai_token_ledger ENABLE ROW LEVEL SECURITY;

-- Knowledge Entries Policy:
-- Merchants can SELECT their own entries AND global system entries (merchant_id IS NULL)
CREATE POLICY tenant_isolation_knowledge_select ON knowledge.entries
  FOR SELECT USING (merchant_id = core.current_tenant_id() OR merchant_id IS NULL);

-- Merchants can only INSERT, UPDATE, DELETE their own entries
CREATE POLICY tenant_isolation_knowledge_write ON knowledge.entries
  FOR ALL USING (merchant_id = core.current_tenant_id())
  WITH CHECK (merchant_id = core.current_tenant_id());

-- AI Wallets Policy:
CREATE POLICY tenant_isolation_core_ai_wallets ON core.ai_wallets
  FOR ALL USING (merchant_id = core.current_tenant_id());

-- Token Ledger Policy:
CREATE POLICY tenant_isolation_core_token_ledger ON core.ai_token_ledger
  FOR ALL USING (merchant_id = core.current_tenant_id());
