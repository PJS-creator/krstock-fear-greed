CREATE TABLE IF NOT EXISTS public.historical_holding_schedules (
  id BIGSERIAL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  schedule_name TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT historical_holding_schedules_owner_name_unique UNIQUE (owner_id, schedule_name)
);

CREATE INDEX IF NOT EXISTS historical_holding_schedules_owner_id_idx
  ON public.historical_holding_schedules (owner_id);
