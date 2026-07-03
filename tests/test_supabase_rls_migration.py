from pathlib import Path


def test_auth_rls_migration_protects_all_public_user_tables():
    sql = Path("docs/supabase_migration_v2_auth_rls.sql").read_text(encoding="utf-8").lower()

    for table in ("portfolio_snapshots", "portfolio_value_history", "historical_holding_schedules"):
        assert f"alter table public.{table} enable row level security" in sql
        assert f"grant select, insert, update, delete on public.{table} to authenticated" in sql
        assert f"on public.{table}" in sql

    assert "auth.uid() is not null" in sql
    assert "owner_id = auth.uid()::text" in sql
    assert "public_accounts" in sql
