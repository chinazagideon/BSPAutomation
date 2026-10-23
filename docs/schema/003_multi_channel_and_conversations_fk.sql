-- ============================================================================
-- ENTERPRISE SCHEMA EVOLUTION: 1:N MERCHANT CHANNELS & CONVERSATION CHANNEL FK (ADR-0048)
-- ============================================================================

-- 1. 1:N Merchant WhatsApp Channels Table
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

CREATE INDEX IF NOT EXISTS idx_merchant_channels_merchant_id
  ON core.merchant_channels (merchant_id);

CREATE INDEX IF NOT EXISTS idx_merchant_channels_lookup
  ON core.merchant_channels (phone_number_id, is_active);

DROP TRIGGER IF EXISTS trg_merchant_channels_updated_at ON core.merchant_channels;
CREATE TRIGGER trg_merchant_channels_updated_at
  BEFORE UPDATE ON core.merchant_channels
  FOR EACH ROW EXECUTE FUNCTION core.update_timestamp();

-- 2. Add channel_id FK to ingress.conversations for active channel backtracking
ALTER TABLE ingress.conversations
  ADD COLUMN IF NOT EXISTS channel_id UUID REFERENCES core.merchant_channels(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_channel_id
  ON ingress.conversations (channel_id);
