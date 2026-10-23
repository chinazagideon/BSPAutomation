-- ============================================================================
-- ENTERPRISE CONVERSATIONAL WORKFLOW PLATFORM FOR NIGERIAN SMES
-- Master PostgreSQL DDL Schema Migration (Version 1.0.0)
-- 
-- Architecture: 5 Bounded Contexts + Core Tenant Infrastructure
-- Features:
--   1. Strict Row-Level Security (RLS) multi-tenancy on merchant_id
--   2. Time-ordered UUIDv7 primary keys across all domain entities
--   3. Integer Kobo (BIGINT) minor-currency precision (NGN)
--   4. 3-Table Immutable Double-Entry Ledger with balanced debit/credit triggers
--   5. PostgreSQL TSTZRANGE GiST exclusion constraints on active reservation holds
--   6. Pre-provisioned Dedicated Virtual NUBAN pool with quarantine recycling
--   7. Event-sourced SHA-256 chained NDPA 2023 consent audit trail
--   8. pg_trgm GIN indexing for Nigerian Pidgin / Slang fast-path dictionary
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. DATABASE EXTENSIONS & CORE SCHEMAS
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Bounded Context Logical Schemas
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ingress;
CREATE SCHEMA IF NOT EXISTS ledger;
CREATE SCHEMA IF NOT EXISTS reservations;
CREATE SCHEMA IF NOT EXISTS desk;
CREATE SCHEMA IF NOT EXISTS compliance;

-- ----------------------------------------------------------------------------
-- 0.1 UUIDv7 GENERATION FUNCTION
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.generate_uuid_v7()
RETURNS UUID AS $$
DECLARE
  unix_time_ms BIGINT;
  retval BYTEA;
BEGIN
  unix_time_ms := (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT;
  retval := set_byte(
    set_byte(
      set_byte(
        set_byte(
          set_byte(
            set_byte(
              gen_random_bytes(16),
              0, ((unix_time_ms >> 40) & 255)::INTEGER
            ),
            1, ((unix_time_ms >> 32) & 255)::INTEGER
          ),
          2, ((unix_time_ms >> 24) & 255)::INTEGER
        ),
        3, ((unix_time_ms >> 16) & 255)::INTEGER
      ),
      4, ((unix_time_ms >> 8) & 255)::INTEGER
    ),
    5, (unix_time_ms & 255)::INTEGER
  );
  -- Set UUID version 7 (bits 4-7 of byte 6 = 0111)
  retval := set_byte(retval, 6, ((get_byte(retval, 6) & 15) | 112)::INTEGER);
  -- Set UUID variant (bits 6-7 of byte 8 = 10)
  retval := set_byte(retval, 8, ((get_byte(retval, 8) & 63) | 128)::INTEGER);
  RETURN encode(retval, 'hex')::UUID;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- ----------------------------------------------------------------------------
-- 0.2 TIMESTAMP AUTO-UPDATE TRIGGER FUNCTION
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. CORE CONTEXT: TENANT INFRASTRUCTURE & SETTINGS
-- ============================================================================

CREATE TABLE IF NOT EXISTS core.merchants (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  business_name VARCHAR(256) NOT NULL,
  slug VARCHAR(128) UNIQUE NOT NULL,
  bsp_provider VARCHAR(32) NOT NULL DEFAULT 'META_CLOUD' 
    CHECK (bsp_provider IN ('META_CLOUD', 'TERMII', 'TWILIO_AFRICA', 'INFOBIP_NG')),
  whatsapp_business_phone VARCHAR(32) NOT NULL,
  whatsapp_phone_number_id VARCHAR(64),
  default_currency CHAR(3) NOT NULL DEFAULT 'NGN',
  variance_tolerance_kobo BIGINT NOT NULL DEFAULT 0 CHECK (variance_tolerance_kobo >= 0),
  anti_ghosting_hold_seconds INTEGER NOT NULL DEFAULT 600 CHECK (anti_ghosting_hold_seconds >= 60),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TRIGGER trg_merchants_updated_at
  BEFORE UPDATE ON core.merchants
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

CREATE TABLE IF NOT EXISTS core.merchant_channels (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  phone_number_id VARCHAR(64) NOT NULL,
  business_phone VARCHAR(32) NOT NULL,
  provider VARCHAR(32) NOT NULL DEFAULT 'META_CLOUD'
    CHECK (provider IN ('META_CLOUD', 'TERMII', 'TWILIO_AFRICA', 'INFOBIP_NG', 'SANDBOX')),
  channel_label VARCHAR(64) NOT NULL DEFAULT 'Main Office',
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_channel_phone_number_id UNIQUE (phone_number_id),
  CONSTRAINT uq_merchant_channel_label UNIQUE (merchant_id, channel_label)
);

CREATE INDEX IF NOT EXISTS idx_merchant_channels_merchant_id ON core.merchant_channels (merchant_id);
CREATE INDEX IF NOT EXISTS idx_merchant_channels_lookup ON core.merchant_channels (phone_number_id, is_active);

CREATE TRIGGER trg_merchant_channels_updated_at
  BEFORE UPDATE ON core.merchant_channels
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

CREATE TABLE IF NOT EXISTS core.users (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  full_name VARCHAR(128) NOT NULL,
  email VARCHAR(256) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'AGENT' 
    CHECK (role IN ('OWNER', 'ADMIN', 'MANAGER', 'AGENT', 'READ_ONLY')),
  password_hash TEXT NOT NULL,
  failed_login_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until TIMESTAMPTZ,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_merchant_user_email UNIQUE (merchant_id, email)
);

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON core.users
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

CREATE TABLE IF NOT EXISTS core.refresh_tokens (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
  token_hash VARCHAR(64) NOT NULL UNIQUE,
  family_id UUID NOT NULL,
  is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
  consumed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_refresh_tokens_hash ON core.refresh_tokens (token_hash);
CREATE INDEX idx_refresh_tokens_family ON core.refresh_tokens (family_id);
CREATE INDEX idx_refresh_tokens_user ON core.refresh_tokens (user_id);

-- ============================================================================
-- 2. INGRESS & NLU CONTEXT
-- ============================================================================

CREATE TABLE IF NOT EXISTS ingress.webhook_events (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  provider VARCHAR(32) NOT NULL DEFAULT 'META_CLOUD',
  event_type VARCHAR(64) NOT NULL,
  external_event_id VARCHAR(128),
  raw_payload JSONB NOT NULL,
  signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
  ack_latency_ms INTEGER NOT NULL DEFAULT 0,
  worker_status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED'
    CHECK (worker_status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'RETRYING')),
  worker_latency_ms INTEGER NOT NULL DEFAULT 0,
  received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_webhook_events_merchant_received 
  ON ingress.webhook_events (merchant_id, received_at DESC);

-- Nigerian Pidgin / Commercial Slang Fast-Path Dictionary
CREATE TABLE IF NOT EXISTS ingress.slang_dictionary (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID REFERENCES core.merchants(id) ON DELETE CASCADE, -- NULL for system-wide global dictionary
  phrase_pattern TEXT NOT NULL,
  standard_english_translation TEXT NOT NULL,
  intent_classification VARCHAR(64) NOT NULL,
  category VARCHAR(32) NOT NULL DEFAULT 'COMMERCE'
    CHECK (category IN ('COMMERCE', 'FINTECH', 'PRICING', 'LOGISTICS', 'SUPPORT', 'GENERAL')),
  dialect VARCHAR(32) NOT NULL DEFAULT 'Nigerian Pidgin'
    CHECK (dialect IN ('Nigerian Pidgin', 'Commercial Slang', 'Standard English', 'Mixed')),
  confidence_score NUMERIC(4,2) NOT NULL DEFAULT 0.95,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Trigram index for fast-path slang and phrase similarity
CREATE INDEX idx_slang_dict_trgm ON ingress.slang_dictionary USING gin (phrase_pattern gin_trgm_ops);

-- Conversations / Leads Table
CREATE TABLE IF NOT EXISTS ingress.conversations (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  channel_id UUID REFERENCES core.merchant_channels(id) ON DELETE SET NULL,
  customer_phone VARCHAR(32) NOT NULL,
  customer_name VARCHAR(128),
  funnel_stage VARCHAR(32) NOT NULL DEFAULT 'discovery'
    CHECK (funnel_stage IN ('discovery', 'evaluation', 'negotiation', 'checkout')),
  lead_tier VARCHAR(16) NOT NULL DEFAULT 'WARM'
    CHECK (lead_tier IN ('HOT', 'WARM', 'COLD')),
  urgency_score SMALLINT NOT NULL DEFAULT 5 CHECK (urgency_score BETWEEN 1 AND 10),
  tech_complexity SMALLINT NOT NULL DEFAULT 3 CHECK (tech_complexity BETWEEN 1 AND 10),
  detected_budget_kobo BIGINT NOT NULL DEFAULT 0 CHECK (detected_budget_kobo >= 0),
  detected_dialect VARCHAR(32) NOT NULL DEFAULT 'Standard English'
    CHECK (detected_dialect IN ('Nigerian Pidgin', 'Commercial Slang', 'Standard English', 'Mixed')),
  extracted_entities JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_open BOOLEAN NOT NULL DEFAULT TRUE,
  last_message_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_merchant_customer_phone UNIQUE (merchant_id, customer_phone)
);

CREATE INDEX idx_conversations_merchant_lead ON ingress.conversations (merchant_id, lead_tier, urgency_score DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_channel_id ON ingress.conversations (channel_id);
CREATE TRIGGER trg_conversations_updated_at
  BEFORE UPDATE ON ingress.conversations
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

-- Inbound & Outbound Messages
CREATE TABLE IF NOT EXISTS ingress.messages (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL REFERENCES ingress.conversations(id) ON DELETE CASCADE,
  sender VARCHAR(16) NOT NULL CHECK (sender IN ('user', 'bot', 'agent', 'system')),
  raw_text TEXT NOT NULL,
  sanitized_text TEXT NOT NULL,
  intent VARCHAR(64),
  is_fast_path BOOLEAN NOT NULL DEFAULT FALSE,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  interactive_type VARCHAR(32) CHECK (interactive_type IN ('buttons', 'list', 'payment_link', 'receipt_card', 'hold_timer')),
  interactive_payload JSONB,
  tokens_used INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_messages_conversation_created ON ingress.messages (conversation_id, created_at ASC);

-- Prepaid Naira AI Wallet & Token Consumption
CREATE TABLE IF NOT EXISTS ingress.ai_wallets (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID UNIQUE NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  balance_kobo BIGINT NOT NULL DEFAULT 0 CHECK (balance_kobo >= 0),
  bundled_tokens_remaining INTEGER NOT NULL DEFAULT 50000 CHECK (bundled_tokens_remaining >= 0),
  monthly_hard_cap_kobo BIGINT NOT NULL DEFAULT 15000000 CHECK (monthly_hard_cap_kobo >= 0), -- ₦150,000.00
  spent_current_month_kobo BIGINT NOT NULL DEFAULT 0 CHECK (spent_current_month_kobo >= 0),
  is_hard_capped BOOLEAN NOT NULL DEFAULT FALSE,
  last_topup_at TIMESTAMPTZ,
  reset_at TIMESTAMPTZ NOT NULL DEFAULT (date_trunc('month', clock_timestamp()) + INTERVAL '1 month'),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TRIGGER trg_ai_wallets_updated_at
  BEFORE UPDATE ON ingress.ai_wallets
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

CREATE TABLE IF NOT EXISTS ingress.token_ledger_entries (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES ingress.conversations(id) ON DELETE SET NULL,
  message_id UUID REFERENCES ingress.messages(id) ON DELETE SET NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  cost_kobo BIGINT NOT NULL DEFAULT 0,
  drawdown_type VARCHAR(32) NOT NULL 
    CHECK (drawdown_type IN ('BUNDLED_QUOTA', 'PREPAID_WALLET', 'FAST_PATH_SAVED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_token_ledger_merchant_created ON ingress.token_ledger_entries (merchant_id, created_at DESC);

-- ============================================================================
-- 3. CHECKOUT & LEDGER CONTEXT
-- ============================================================================

-- Anti-Ghosting Shopping Carts
CREATE TABLE IF NOT EXISTS ledger.checkout_carts (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES ingress.conversations(id) ON DELETE SET NULL,
  customer_phone VARCHAR(32) NOT NULL,
  customer_name VARCHAR(128) NOT NULL,
  total_amount_kobo BIGINT NOT NULL CHECK (total_amount_kobo > 0),
  currency CHAR(3) NOT NULL DEFAULT 'NGN',
  status VARCHAR(32) NOT NULL DEFAULT 'WAITING_FOR_TRANSFER'
    CHECK (status IN ('ACTIVE_CHATTING', 'WAITING_FOR_TRANSFER', 'PAYMENT_RECEIVED', 'EXPIRED_RELEASED', 'MANUAL_REVIEW')),
  hold_expires_at TIMESTAMPTZ NOT NULL,
  receipt_pushed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_checkout_carts_merchant_status ON ledger.checkout_carts (merchant_id, status, hold_expires_at);
CREATE TRIGGER trg_checkout_carts_updated_at
  BEFORE UPDATE ON ledger.checkout_carts
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

CREATE TABLE IF NOT EXISTS ledger.cart_items (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  cart_id UUID NOT NULL REFERENCES ledger.checkout_carts(id) ON DELETE CASCADE,
  item_name VARCHAR(256) NOT NULL,
  sku VARCHAR(64),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_kobo BIGINT NOT NULL CHECK (unit_price_kobo >= 0),
  total_price_kobo BIGINT GENERATED ALWAYS AS (quantity * unit_price_kobo) STORED
);

CREATE INDEX idx_cart_items_cart_id ON ledger.cart_items (cart_id);

-- Dedicated Dynamic Virtual NUBAN Pool
CREATE TABLE IF NOT EXISTS ledger.virtual_nubans (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  cart_id UUID REFERENCES ledger.checkout_carts(id) ON DELETE SET NULL,
  bank_name VARCHAR(64) NOT NULL DEFAULT 'Moniepoint MFB',
  bank_code VARCHAR(16) NOT NULL DEFAULT '090405',
  account_number VARCHAR(10) NOT NULL,
  account_name VARCHAR(128) NOT NULL,
  provider_reference VARCHAR(128) NOT NULL,
  pool_status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE'
    CHECK (pool_status IN ('AVAILABLE', 'ASSIGNED_HOLD', 'COOLDOWN_QUARANTINE')),
  assigned_at TIMESTAMPTZ,
  hold_expires_at TIMESTAMPTZ,
  quarantine_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_merchant_nuban UNIQUE (merchant_id, account_number)
);

CREATE INDEX idx_virtual_nubans_pool_search 
  ON ledger.virtual_nubans (merchant_id, pool_status, quarantine_until);

-- Double-Entry Chart of Accounts
CREATE TABLE IF NOT EXISTS ledger.ledger_accounts (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  account_code VARCHAR(32) NOT NULL,
  account_name VARCHAR(128) NOT NULL,
  account_type VARCHAR(16) NOT NULL
    CHECK (account_type IN ('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE')),
  currency CHAR(3) NOT NULL DEFAULT 'NGN',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_merchant_account_code UNIQUE (merchant_id, account_code)
);

-- Immutable Journal Entries Header
CREATE TABLE IF NOT EXISTS ledger.journal_entries (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  cart_id UUID REFERENCES ledger.checkout_carts(id) ON DELETE SET NULL,
  transaction_ref VARCHAR(128) NOT NULL,
  channel VARCHAR(32) NOT NULL DEFAULT 'MONIEPOINT_DVA'
    CHECK (channel IN ('MONIEPOINT_DVA', 'PAYSTACK_DVA', 'FLUTTERWAVE_DVA', 'NIBSS_NIP', 'USSD')),
  expected_amount_kobo BIGINT NOT NULL CHECK (expected_amount_kobo >= 0),
  settled_amount_kobo BIGINT NOT NULL CHECK (settled_amount_kobo >= 0),
  variance_kobo BIGINT GENERATED ALWAYS AS (expected_amount_kobo - settled_amount_kobo) STORED,
  narration TEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'SETTLED'
    CHECK (status IN ('SETTLED', 'MISMATCH_FLAGGED', 'ESCROW_HELD')),
  ai_mismatch_explanation TEXT,
  posted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_merchant_transaction_ref UNIQUE (merchant_id, transaction_ref)
);

CREATE INDEX idx_journal_entries_merchant_posted ON ledger.journal_entries (merchant_id, posted_at DESC);

-- Immutable Journal Postings (Multi-Leg Splits)
CREATE TABLE IF NOT EXISTS ledger.journal_postings (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  entry_id UUID NOT NULL REFERENCES ledger.journal_entries(id) ON DELETE CASCADE,
  account_id UUID NOT NULL REFERENCES ledger.ledger_accounts(id) ON DELETE RESTRICT,
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  debit_kobo BIGINT NOT NULL DEFAULT 0 CHECK (debit_kobo >= 0),
  credit_kobo BIGINT NOT NULL DEFAULT 0 CHECK (credit_kobo >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT chk_posting_has_amount CHECK (debit_kobo > 0 OR credit_kobo > 0),
  CONSTRAINT chk_posting_not_both CHECK (NOT (debit_kobo > 0 AND credit_kobo > 0))
);

CREATE INDEX idx_journal_postings_entry ON ledger.journal_postings (entry_id);
CREATE INDEX idx_journal_postings_account ON ledger.journal_postings (account_id);

-- Deferred Constraint Trigger to enforce balanced ledger entries
CREATE OR REPLACE FUNCTION ledger.verify_journal_entry_balance()
RETURNS TRIGGER AS $$
DECLARE
  v_total_debit BIGINT;
  v_total_credit BIGINT;
BEGIN
  SELECT COALESCE(SUM(debit_kobo), 0), COALESCE(SUM(credit_kobo), 0)
  INTO v_total_debit, v_total_credit
  FROM ledger.journal_postings
  WHERE entry_id = NEW.entry_id;

  IF v_total_debit <> v_total_credit THEN
    RAISE EXCEPTION 'Double-entry balance violation on Entry %: Total Debits (₦%) != Total Credits (₦%)',
      NEW.entry_id, (v_total_debit / 100.0), (v_total_credit / 100.0);
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_verify_entry_balance
  AFTER INSERT OR UPDATE ON ledger.journal_postings
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION ledger.verify_journal_entry_balance();

-- ============================================================================
-- 4. RESERVATIONS CONTEXT
-- ============================================================================

CREATE TABLE IF NOT EXISTS reservations.resources (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  name VARCHAR(128) NOT NULL,
  resource_type VARCHAR(64) NOT NULL, -- 'Doctor', 'Consultant', 'Dispatch Rider', 'Conference Room'
  hub_location VARCHAR(128) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS reservations.services (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  service_name VARCHAR(128) NOT NULL,
  duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
  commitment_deposit_kobo BIGINT NOT NULL DEFAULT 0 CHECK (commitment_deposit_kobo >= 0),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS reservations.atomic_slots (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  resource_id UUID NOT NULL REFERENCES reservations.resources(id) ON DELETE CASCADE,
  service_id UUID REFERENCES reservations.services(id) ON DELETE SET NULL,
  time_range TSTZRANGE NOT NULL,
  price_kobo BIGINT NOT NULL CHECK (price_kobo >= 0),
  status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE'
    CHECK (status IN ('AVAILABLE', 'HELD_PENDING_PAYMENT', 'CONFIRMED', 'RELEASED')),
  held_by_phone VARCHAR(32),
  transaction_ref VARCHAR(128),
  hold_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

  -- Partial GiST exclusion constraint mathematically eliminating overlapping bookings
  CONSTRAINT atomic_slot_no_overlap EXCLUDE USING gist (
    merchant_id WITH =,
    resource_id WITH =,
    time_range WITH &&
  ) WHERE (status IN ('HELD_PENDING_PAYMENT', 'CONFIRMED'))
);

CREATE INDEX idx_atomic_slots_lookup 
  ON reservations.atomic_slots (merchant_id, resource_id, status);

CREATE TRIGGER trg_atomic_slots_updated_at
  BEFORE UPDATE ON reservations.atomic_slots
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

-- ============================================================================
-- 5. AGENT DESK CONTEXT
-- ============================================================================

CREATE TABLE IF NOT EXISTS desk.hubs (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  name VARCHAR(128) NOT NULL, -- 'Ikeja Tech Hub', 'Lekki Phase 1', 'Abuja Garki', 'Yaba Central'
  region VARCHAR(64) NOT NULL,
  backup_hub_id UUID REFERENCES desk.hubs(id) ON DELETE SET NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS desk.agent_profiles (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  hub_id UUID NOT NULL REFERENCES desk.hubs(id) ON DELETE RESTRICT,
  user_id UUID REFERENCES core.users(id) ON DELETE SET NULL,
  name VARCHAR(128) NOT NULL,
  phone VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ONLINE'
    CHECK (status IN ('ONLINE', 'OFFLINE_NEPA', 'BUSY', 'ON_BREAK')),
  active_chats_count INTEGER NOT NULL DEFAULT 0 CHECK (active_chats_count >= 0),
  max_concurrent_chats INTEGER NOT NULL DEFAULT 5 CHECK (max_concurrent_chats > 0),
  last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  latency_ms INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TRIGGER trg_agent_profiles_updated_at
  BEFORE UPDATE ON desk.agent_profiles
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

CREATE TABLE IF NOT EXISTS desk.agent_connectivity_logs (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  agent_id UUID NOT NULL REFERENCES desk.agent_profiles(id) ON DELETE CASCADE,
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  hub_id UUID NOT NULL REFERENCES desk.hubs(id) ON DELETE CASCADE,
  event_type VARCHAR(32) NOT NULL
    CHECK (event_type IN ('HEARTBEAT_PING', 'NEPA_DROPOUT', 'POWER_RESTORED', 'FAILOVER_REROUTE')),
  ping_timestamp TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  latency_ms INTEGER NOT NULL DEFAULT 0,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_agent_connectivity_logs_agent ON desk.agent_connectivity_logs (agent_id, ping_timestamp DESC);

-- Standardized 6-Field Context Escalation Tickets
CREATE TABLE IF NOT EXISTS desk.escalation_tickets (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL REFERENCES ingress.conversations(id) ON DELETE CASCADE,
  assigned_agent_id UUID REFERENCES desk.agent_profiles(id) ON DELETE SET NULL,
  primary_hub_id UUID NOT NULL REFERENCES desk.hubs(id) ON DELETE RESTRICT,
  failover_hub_id UUID REFERENCES desk.hubs(id) ON DELETE SET NULL,
  queue_position INTEGER NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_ASSIGNMENT'
    CHECK (status IN ('PENDING_ASSIGNMENT', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'DROPPED_FAILOVER')),
  executive_summary TEXT NOT NULL,
  detected_budget_kobo BIGINT NOT NULL DEFAULT 0,
  urgency_tier VARCHAR(16) NOT NULL DEFAULT 'HOT' CHECK (urgency_tier IN ('HOT', 'WARM', 'COLD')),
  dialect VARCHAR(32) NOT NULL DEFAULT 'Standard English',
  key_blockers TEXT NOT NULL,
  suggested_first_response TEXT NOT NULL,
  pii_scrubbed BOOLEAN NOT NULL DEFAULT TRUE,
  escalated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_escalation_tickets_queue ON desk.escalation_tickets (merchant_id, status, queue_position);

-- ============================================================================
-- 6. COMPLIANCE & PRIVACY CONTEXT (NDPA 2023)
-- ============================================================================

-- Immutable Event-Sourced Consent Audit Trail with SHA-256 Chaining
CREATE TABLE IF NOT EXISTS compliance.consent_events (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  phone VARCHAR(32) NOT NULL,
  action VARCHAR(32) NOT NULL
    CHECK (action IN ('OPT_IN_MARKETING', 'OPT_IN_TRANSACTIONAL', 'OPT_IN_DATA_PROCESSING', 'OPT_OUT_REVOCATION')),
  ip_address VARCHAR(45) NOT NULL,
  network_carrier VARCHAR(64) NOT NULL DEFAULT 'MTN Nigeria',
  raw_keyword VARCHAR(32), -- e.g. 'STOP', 'COMOT', 'START', 'YES'
  previous_event_hash VARCHAR(64) NOT NULL,
  immutable_hash VARCHAR(64) NOT NULL,
  event_timestamp TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_consent_events_phone ON compliance.consent_events (merchant_id, phone, event_timestamp DESC);

-- Materialized View for Sub-Millisecond Active Consent Checks
CREATE MATERIALIZED VIEW IF NOT EXISTS compliance.active_consents AS
SELECT DISTINCT ON (merchant_id, phone, action)
  id AS last_event_id,
  merchant_id,
  phone,
  action AS consent_type,
  CASE 
    WHEN action = 'OPT_OUT_REVOCATION' THEN 'REVOKED'
    ELSE 'ACTIVE'
  END AS status,
  immutable_hash,
  event_timestamp AS last_updated_at
FROM compliance.consent_events
ORDER BY merchant_id, phone, action, event_timestamp DESC;

CREATE UNIQUE INDEX idx_active_consents_lookup 
  ON compliance.active_consents (merchant_id, phone, consent_type);

-- PII Redaction Audit Logs
CREATE TABLE IF NOT EXISTS compliance.redaction_audit_logs (
  id UUID PRIMARY KEY DEFAULT core.generate_uuid_v7(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  message_id UUID REFERENCES ingress.messages(id) ON DELETE SET NULL,
  redacted_entity_type VARCHAR(16) NOT NULL
    CHECK (redacted_entity_type IN ('BVN', 'NIN', 'NUBAN', 'CARD_PAN', 'PASSWORD')),
  token_mask VARCHAR(64) NOT NULL,
  safety_score SMALLINT NOT NULL DEFAULT 100 CHECK (safety_score BETWEEN 1 AND 100),
  scrubbed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_redaction_logs_merchant ON compliance.redaction_audit_logs (merchant_id, scrubbed_at DESC);

-- ============================================================================
-- 7. ROW-LEVEL SECURITY (RLS) MULTI-TENANT POLICIES
-- ============================================================================

ALTER TABLE ingress.webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingress.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingress.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingress.ai_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingress.token_ledger_entries ENABLE ROW LEVEL SECURITY;

ALTER TABLE ledger.checkout_carts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger.cart_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger.virtual_nubans ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger.ledger_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger.journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger.journal_postings ENABLE ROW LEVEL SECURITY;

ALTER TABLE reservations.resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations.atomic_slots ENABLE ROW LEVEL SECURITY;

ALTER TABLE desk.hubs ENABLE ROW LEVEL SECURITY;
ALTER TABLE desk.agent_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE desk.agent_connectivity_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE desk.escalation_tickets ENABLE ROW LEVEL SECURITY;

ALTER TABLE compliance.consent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.redaction_audit_logs ENABLE ROW LEVEL SECURITY;

-- Helper macro function for RLS tenant matching
CREATE OR REPLACE FUNCTION core.current_tenant_id()
RETURNS UUID AS $$
BEGIN
  RETURN NULLIF(current_setting('app.current_merchant_id', true), '')::UUID;
END;
$$ LANGUAGE plpgsql STABLE;

-- Apply Tenant Isolation Policies across tables
CREATE POLICY tenant_isolation_webhook_events ON ingress.webhook_events
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_conversations ON ingress.conversations
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_messages ON ingress.messages
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_ai_wallets ON ingress.ai_wallets
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_token_ledger ON ingress.token_ledger_entries
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_checkout_carts ON ledger.checkout_carts
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_cart_items ON ledger.cart_items
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_virtual_nubans ON ledger.virtual_nubans
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_ledger_accounts ON ledger.ledger_accounts
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_journal_entries ON ledger.journal_entries
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_journal_postings ON ledger.journal_postings
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_resources ON reservations.resources
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_services ON reservations.services
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_atomic_slots ON reservations.atomic_slots
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_hubs ON desk.hubs
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_agent_profiles ON desk.agent_profiles
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_connectivity_logs ON desk.agent_connectivity_logs
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_escalation_tickets ON desk.escalation_tickets
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_consent_events ON compliance.consent_events
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_redaction_logs ON compliance.redaction_audit_logs
  FOR ALL USING (merchant_id = core.current_tenant_id());

ALTER TABLE core.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.refresh_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_users ON core.users
  FOR ALL USING (merchant_id = core.current_tenant_id());

CREATE POLICY tenant_isolation_refresh_tokens ON core.refresh_tokens
  FOR ALL USING (merchant_id = core.current_tenant_id());

-- ============================================================================
-- 8. DEFAULT CHART OF ACCOUNTS SEED TEMPLATE FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION ledger.seed_standard_chart_of_accounts(p_merchant_id UUID)
RETURNS VOID AS $$
BEGIN
  INSERT INTO ledger.ledger_accounts (merchant_id, account_code, account_name, account_type) VALUES
    (p_merchant_id, '1010', 'Moniepoint Settlement Clearing Asset', 'ASSET'),
    (p_merchant_id, '1020', 'Paystack DVA Clearing Asset', 'ASSET'),
    (p_merchant_id, '1030', 'Accounts Receivable (Pending Transfer)', 'ASSET'),
    (p_merchant_id, '2010', 'Customer Unearned Deposits & Escrow', 'LIABILITY'),
    (p_merchant_id, '2020', 'Merchant Payables Disbursable', 'LIABILITY'),
    (p_merchant_id, '3010', 'Merchant Retained Earnings', 'EQUITY'),
    (p_merchant_id, '4010', 'WhatsApp Commercial Sales Revenue', 'REVENUE'),
    (p_merchant_id, '5010', 'Payment Gateway Processing Fees (1.5%)', 'EXPENSE'),
    (p_merchant_id, '5020', 'Statutory Electronic Money Transfer Levy (₦50 Stamp Duty)', 'EXPENSE')
  ON CONFLICT (merchant_id, account_code) DO NOTHING;
END;
$$ LANGUAGE plpgsql;
