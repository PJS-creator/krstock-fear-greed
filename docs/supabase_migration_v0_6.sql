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

CREATE INDEX IF NOT EXISTS portfolio_value_history_owner_portfolio_captured_idx
  ON public.portfolio_value_history (owner_id, portfolio_name, captured_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS portfolio_value_history_fingerprint_idx
  ON public.portfolio_value_history (owner_id, portfolio_name, fingerprint);
