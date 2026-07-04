-- Cash ledger migration for account-level cash balance accounting.
-- Run after docs/supabase_migration_v2_auth_rls.sql.
-- This migration is additive: legacy portfolio_snapshots cash_balances stay intact.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.cash_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  portfolio_id TEXT NOT NULL DEFAULT 'main',
  event_date DATE NOT NULL,
  currency TEXT NOT NULL,
  event_type TEXT NOT NULL,
  amount NUMERIC NOT NULL,
  linked_transaction_id UUID,
  fx_rate_to_krw NUMERIC,
  memo TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT cash_ledger_currency_check
    CHECK (currency IN ('KRW', 'USD')),
  CONSTRAINT cash_ledger_event_type_check
    CHECK (
      event_type IN (
        'opening_balance',
        'deposit',
        'withdrawal',
        'buy_settlement',
        'sell_settlement',
        'dividend',
        'interest',
        'fee',
        'tax',
        'fx_conversion_in',
        'fx_conversion_out',
        'manual_adjustment'
      )
    )
);

ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS portfolio_id TEXT DEFAULT 'main';
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS event_date DATE;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS event_type TEXT;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS amount NUMERIC;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS linked_transaction_id UUID;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS fx_rate_to_krw NUMERIC;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS memo TEXT;
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.cash_ledger ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

ALTER TABLE public.cash_ledger ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.cash_ledger TO authenticated;

CREATE INDEX IF NOT EXISTS cash_ledger_user_portfolio_date_idx
  ON public.cash_ledger (user_id, portfolio_id, event_date DESC);

CREATE INDEX IF NOT EXISTS cash_ledger_user_currency_idx
  ON public.cash_ledger (user_id, currency);

CREATE INDEX IF NOT EXISTS cash_ledger_linked_transaction_idx
  ON public.cash_ledger (linked_transaction_id)
  WHERE linked_transaction_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS cash_ledger_opening_balance_unique_idx
  ON public.cash_ledger (user_id, portfolio_id, currency, event_type)
  WHERE event_type = 'opening_balance' AND linked_transaction_id IS NULL;

DROP POLICY IF EXISTS "cash_ledger_select_own" ON public.cash_ledger;
CREATE POLICY "cash_ledger_select_own"
  ON public.cash_ledger
  FOR SELECT
  TO authenticated
  USING (auth.uid() IS NOT NULL AND user_id = auth.uid());

DROP POLICY IF EXISTS "cash_ledger_insert_own" ON public.cash_ledger;
CREATE POLICY "cash_ledger_insert_own"
  ON public.cash_ledger
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() IS NOT NULL AND user_id = auth.uid());

DROP POLICY IF EXISTS "cash_ledger_update_own" ON public.cash_ledger;
CREATE POLICY "cash_ledger_update_own"
  ON public.cash_ledger
  FOR UPDATE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND user_id = auth.uid())
  WITH CHECK (auth.uid() IS NOT NULL AND user_id = auth.uid());

DROP POLICY IF EXISTS "cash_ledger_delete_own" ON public.cash_ledger;
CREATE POLICY "cash_ledger_delete_own"
  ON public.cash_ledger
  FOR DELETE
  TO authenticated
  USING (auth.uid() IS NOT NULL AND user_id = auth.uid());

CREATE OR REPLACE FUNCTION public.set_cash_ledger_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS cash_ledger_set_updated_at ON public.cash_ledger;
CREATE TRIGGER cash_ledger_set_updated_at
  BEFORE UPDATE ON public.cash_ledger
  FOR EACH ROW
  EXECUTE FUNCTION public.set_cash_ledger_updated_at();

-- One-time backfill path for legacy manual cash balances stored in portfolio_snapshots.payload_json.
-- Re-running this block is safe because it skips existing opening_balance rows.
WITH latest_snapshots AS (
  SELECT DISTINCT ON (owner_id, portfolio_name)
    owner_id,
    portfolio_name,
    payload_json,
    COALESCE(updated_at, created_at, now())::date AS event_date
  FROM public.portfolio_snapshots
  WHERE owner_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  ORDER BY owner_id, portfolio_name, updated_at DESC NULLS LAST, created_at DESC NULLS LAST
),
legacy_cash AS (
  SELECT
    owner_id::uuid AS user_id,
    portfolio_name AS portfolio_id,
    event_date,
    'KRW'::text AS currency,
    payload_json #>> '{cash_balances,KRW}' AS amount_text
  FROM latest_snapshots
  UNION ALL
  SELECT
    owner_id::uuid AS user_id,
    portfolio_name AS portfolio_id,
    event_date,
    'USD'::text AS currency,
    payload_json #>> '{cash_balances,USD}' AS amount_text
  FROM latest_snapshots
),
opening_rows AS (
  SELECT
    user_id,
    portfolio_id,
    event_date,
    currency,
    amount_text::numeric AS amount
  FROM legacy_cash
  WHERE amount_text ~ '^-?[0-9]+(\.[0-9]+)?$'
)
INSERT INTO public.cash_ledger (
  user_id,
  portfolio_id,
  event_date,
  currency,
  event_type,
  amount,
  memo
)
SELECT
  user_id,
  portfolio_id,
  event_date,
  currency,
  'opening_balance',
  amount,
  'Backfilled from legacy portfolio_snapshots.cash_balances'
FROM opening_rows
WHERE amount <> 0
  AND NOT EXISTS (
    SELECT 1
    FROM public.cash_ledger existing
    WHERE existing.user_id = opening_rows.user_id
      AND existing.portfolio_id = opening_rows.portfolio_id
      AND existing.currency = opening_rows.currency
      AND existing.event_type = 'opening_balance'
      AND existing.linked_transaction_id IS NULL
  )
ON CONFLICT DO NOTHING;
