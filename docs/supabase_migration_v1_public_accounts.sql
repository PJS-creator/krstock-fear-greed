CREATE TABLE IF NOT EXISTS public.public_accounts (
  id BIGSERIAL PRIMARY KEY,
  account_id TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  password_algorithm TEXT NOT NULL DEFAULT 'pbkdf2_sha256',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT public_accounts_account_id_unique UNIQUE (account_id),
  CONSTRAINT public_accounts_owner_id_unique UNIQUE (owner_id)
);

CREATE INDEX IF NOT EXISTS public_accounts_owner_id_idx
  ON public.public_accounts (owner_id);

ALTER TABLE public.public_accounts ENABLE ROW LEVEL SECURITY;
