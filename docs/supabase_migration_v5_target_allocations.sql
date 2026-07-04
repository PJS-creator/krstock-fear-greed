-- Optional normalized target allocation table for rebalancing.
-- The app stores target allocations in portfolio_snapshots.payload_json today.
-- This additive table is a future-safe path for moving allocations into rows.

CREATE TABLE IF NOT EXISTS public.target_allocations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  portfolio_id TEXT NOT NULL DEFAULT 'main',
  asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'cash')),
  symbol TEXT,
  market TEXT CHECK (market IN ('KR', 'US') OR market IS NULL),
  currency TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
  display_name TEXT,
  target_weight_pct NUMERIC NOT NULL CHECK (target_weight_pct >= 0 AND target_weight_pct <= 100),
  current_price NUMERIC CHECK (current_price IS NULL OR current_price >= 0),
  is_enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS portfolio_id TEXT DEFAULT 'main';
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS asset_type TEXT;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS symbol TEXT;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS market TEXT;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS target_weight_pct NUMERIC;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS current_price NUMERIC;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS is_enabled BOOLEAN DEFAULT true;
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.target_allocations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS target_allocations_user_portfolio_idx
  ON public.target_allocations (user_id, portfolio_id);

CREATE INDEX IF NOT EXISTS target_allocations_user_enabled_idx
  ON public.target_allocations (user_id, is_enabled);

ALTER TABLE public.target_allocations ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.target_allocations TO authenticated;

DROP POLICY IF EXISTS "target_allocations_select_own" ON public.target_allocations;
CREATE POLICY "target_allocations_select_own"
  ON public.target_allocations
  FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "target_allocations_insert_own" ON public.target_allocations;
CREATE POLICY "target_allocations_insert_own"
  ON public.target_allocations
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "target_allocations_update_own" ON public.target_allocations;
CREATE POLICY "target_allocations_update_own"
  ON public.target_allocations
  FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "target_allocations_delete_own" ON public.target_allocations;
CREATE POLICY "target_allocations_delete_own"
  ON public.target_allocations
  FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);
