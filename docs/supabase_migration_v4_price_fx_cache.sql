-- Shared market data cache for price and FX transparency.
-- This migration stores only public market data. It does not include user IDs,
-- portfolio names, holdings, transactions, or other user-owned data.

CREATE TABLE IF NOT EXISTS public.price_cache (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  currency TEXT NOT NULL,
  price NUMERIC NOT NULL,
  previous_close NUMERIC,
  price_date DATE,
  as_of_timestamp TIMESTAMPTZ,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT price_cache_market_check
    CHECK (market IN ('KR', 'US')),
  CONSTRAINT price_cache_currency_check
    CHECK (currency IN ('KRW', 'USD')),
  CONSTRAINT price_cache_status_check
    CHECK (
      status IN (
        '정상_장중',
        '정상_최근종가',
        '시장휴장',
        '이전저장값사용',
        '수동입력값',
        '조회실패',
        '티커미확인',
        '환율실패_기존값유지',
        'updated',
        'cached',
        'stale',
        'failed',
        'missing',
        'manual'
      )
    )
);

ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS symbol TEXT;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS market TEXT;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS price NUMERIC;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS previous_close NUMERIC;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS price_date DATE;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS as_of_timestamp TIMESTAMPTZ;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.price_cache ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.fx_rates (
  id BIGSERIAL PRIMARY KEY,
  from_currency TEXT NOT NULL,
  to_currency TEXT NOT NULL,
  rate NUMERIC NOT NULL,
  rate_date DATE,
  as_of_timestamp TIMESTAMPTZ,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fx_rates_currency_pair_check
    CHECK (from_currency IN ('USD', 'KRW') AND to_currency IN ('USD', 'KRW') AND from_currency <> to_currency),
  CONSTRAINT fx_rates_status_check
    CHECK (
      status IN (
        '정상_장중',
        '정상_최근종가',
        '시장휴장',
        '이전저장값사용',
        '수동입력값',
        '조회실패',
        '티커미확인',
        '환율실패_기존값유지',
        'updated',
        'cached',
        'stale',
        'failed',
        'missing',
        'manual'
      )
    )
);

ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS from_currency TEXT;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS to_currency TEXT;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS rate NUMERIC;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS rate_date DATE;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS as_of_timestamp TIMESTAMPTZ;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.fx_rates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS price_cache_symbol_market_fetched_idx
  ON public.price_cache (symbol, market, fetched_at DESC);

CREATE INDEX IF NOT EXISTS price_cache_market_status_idx
  ON public.price_cache (market, status);

CREATE INDEX IF NOT EXISTS fx_rates_pair_fetched_idx
  ON public.fx_rates (from_currency, to_currency, fetched_at DESC);

ALTER TABLE public.price_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fx_rates ENABLE ROW LEVEL SECURITY;

GRANT SELECT ON public.price_cache TO authenticated;
GRANT SELECT ON public.fx_rates TO authenticated;

DROP POLICY IF EXISTS "price_cache_read_market_data" ON public.price_cache;
CREATE POLICY "price_cache_read_market_data"
  ON public.price_cache
  FOR SELECT
  TO authenticated
  USING (true);

DROP POLICY IF EXISTS "fx_rates_read_market_data" ON public.fx_rates;
CREATE POLICY "fx_rates_read_market_data"
  ON public.fx_rates
  FOR SELECT
  TO authenticated
  USING (true);
