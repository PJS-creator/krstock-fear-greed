CREATE TABLE IF NOT EXISTS public.portfolio_snapshots (
  id BIGSERIAL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  portfolio_name TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT portfolio_snapshots_owner_name_unique UNIQUE (owner_id, portfolio_name)
);

CREATE INDEX IF NOT EXISTS portfolio_snapshots_owner_id_idx
  ON public.portfolio_snapshots (owner_id);
