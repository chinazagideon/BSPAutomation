-- ============================================================================
-- ENTERPRISE SCHEMA EVOLUTION: PERSISTENT CUSTOMER ORDER LEDGER
-- ============================================================================

CREATE TABLE IF NOT EXISTS ledger.customer_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id UUID NOT NULL REFERENCES core.merchants(id) ON DELETE CASCADE,
  cart_id UUID REFERENCES ledger.checkout_carts(id) ON DELETE SET NULL,
  customer_phone VARCHAR(32) NOT NULL,
  order_summary TEXT NOT NULL,
  delivery_zone VARCHAR(128),
  fulfillment_type VARCHAR(64) NOT NULL DEFAULT 'EXPRESS_DELIVERY',
  total_kobo BIGINT NOT NULL DEFAULT 0,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_customer_orders_lookup
  ON ledger.customer_orders (merchant_id, customer_phone, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_customer_orders_cart_id
  ON ledger.customer_orders (cart_id);

-- Row-Level Security
ALTER TABLE ledger.customer_orders ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS customer_orders_tenant_isolation ON ledger.customer_orders;
CREATE POLICY customer_orders_tenant_isolation ON ledger.customer_orders
  AS RESTRICTIVE
  USING (
    merchant_id = NULLIF(current_setting('app.current_merchant_id', true), '')::UUID
    OR current_setting('app.bypass_rls', true) = 'on'
  );
