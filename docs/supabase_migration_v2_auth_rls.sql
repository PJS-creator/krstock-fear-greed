-- External-user app hardening for Supabase Auth.
-- This migration keeps legacy public_accounts data in place and protects
-- portfolio tables with owner_id = auth.uid()::text policies.

CREATE TABLE IF NOT EXISTS public.portfolio_snapshots (
  id BIGSERIAL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  portfolio_name TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT portfolio_snapshots_owner_name_unique UNIQUE (owner_id, portfolio_name)
);

CREATE TABLE IF NOT EXISTS public.portfolio_value_history (
  id BIGSERIAL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  portfolio_name TEXT NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type TEXT NOT NULL,
  total_value_krw DOUBLE PRECISION NOT NULL,
  total_position_value_krw DOUBLE PRECISION NOT NULL,
  cash_krw DOUBLE PRECISION NOT NULL DEFAULT 0,
  cash_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
  cash_total_krw DOUBLE PRECISION NOT NULL DEFAULT 0,
  usd_krw DOUBLE PRECISION NOT NULL,
  day_change_krw DOUBLE PRECISION,
  day_change_pct DOUBLE PRECISION,
  holdings_count INTEGER NOT NULL DEFAULT 0,
  stale_quote_count INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL,
  fingerprint TEXT NOT NULL,
  CONSTRAINT portfolio_value_history_event_type_check
    CHECK (event_type IN ('price_refresh', 'portfolio_save', 'manual_capture', 'holdings_changed'))
);

CREATE TABLE IF NOT EXISTS public.historical_holding_schedules (
  id BIGSERIAL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  schedule_name TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT historical_holding_schedules_owner_name_unique UNIQUE (owner_id, schedule_name)
);

ALTER TABLE public.portfolio_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_value_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.historical_holding_schedules ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.portfolio_snapshots TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.portfolio_value_history TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.historical_holding_schedules TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

CREATE INDEX IF NOT EXISTS portfolio_snapshots_owner_name_idx
  ON public.portfolio_snapshots (owner_id, portfolio_name);

CREATE INDEX IF NOT EXISTS portfolio_snapshots_owner_id_idx
  ON public.portfolio_snapshots (owner_id);

CREATE INDEX IF NOT EXISTS portfolio_value_history_owner_name_idx
  ON public.portfolio_value_history (owner_id, portfolio_name);

CREATE INDEX IF NOT EXISTS portfolio_value_history_owner_portfolio_captured_idx
  ON public.portfolio_value_history (owner_id, portfolio_name, captured_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS portfolio_value_history_fingerprint_idx
  ON public.portfolio_value_history (owner_id, portfolio_name, fingerprint);

CREATE INDEX IF NOT EXISTS historical_holding_schedules_owner_name_idx
  ON public.historical_holding_schedules (owner_id, schedule_name);

CREATE INDEX IF NOT EXISTS historical_holding_schedules_owner_id_idx
  ON public.historical_holding_schedules (owner_id);

DROP POLICY IF EXISTS "portfolio_snapshots_select_own" ON public.portfolio_snapshots;
CREATE POLICY "portfolio_snapshots_select_own"
  ON public.portfolio_snapshots
  FOR SELECT
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_snapshots_insert_own" ON public.portfolio_snapshots;
CREATE POLICY "portfolio_snapshots_insert_own"
  ON public.portfolio_snapshots
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_snapshots_update_own" ON public.portfolio_snapshots;
CREATE POLICY "portfolio_snapshots_update_own"
  ON public.portfolio_snapshots
  FOR UPDATE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text)
  WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_snapshots_delete_own" ON public.portfolio_snapshots;
CREATE POLICY "portfolio_snapshots_delete_own"
  ON public.portfolio_snapshots
  FOR DELETE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_value_history_select_own" ON public.portfolio_value_history;
CREATE POLICY "portfolio_value_history_select_own"
  ON public.portfolio_value_history
  FOR SELECT
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_value_history_insert_own" ON public.portfolio_value_history;
CREATE POLICY "portfolio_value_history_insert_own"
  ON public.portfolio_value_history
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_value_history_update_own" ON public.portfolio_value_history;
CREATE POLICY "portfolio_value_history_update_own"
  ON public.portfolio_value_history
  FOR UPDATE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text)
  WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "portfolio_value_history_delete_own" ON public.portfolio_value_history;
CREATE POLICY "portfolio_value_history_delete_own"
  ON public.portfolio_value_history
  FOR DELETE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "historical_holding_schedules_select_own" ON public.historical_holding_schedules;
CREATE POLICY "historical_holding_schedules_select_own"
  ON public.historical_holding_schedules
  FOR SELECT
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "historical_holding_schedules_insert_own" ON public.historical_holding_schedules;
CREATE POLICY "historical_holding_schedules_insert_own"
  ON public.historical_holding_schedules
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "historical_holding_schedules_update_own" ON public.historical_holding_schedules;
CREATE POLICY "historical_holding_schedules_update_own"
  ON public.historical_holding_schedules
  FOR UPDATE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text)
  WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);

DROP POLICY IF EXISTS "historical_holding_schedules_delete_own" ON public.historical_holding_schedules;
CREATE POLICY "historical_holding_schedules_delete_own"
  ON public.historical_holding_schedules
  FOR DELETE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND owner_id = auth.uid()::text);
