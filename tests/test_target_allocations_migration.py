from pathlib import Path


def test_target_allocations_migration_adds_rls_policies():
    sql = Path("docs/supabase_migration_v5_target_allocations.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists public.target_allocations" in sql
    assert "asset_type text not null check (asset_type in ('stock', 'cash'))" in sql
    assert "target_weight_pct numeric not null" in sql
    assert "alter table public.target_allocations enable row level security" in sql
    assert "grant select, insert, update, delete on public.target_allocations to authenticated" in sql
    assert "auth.uid() = user_id" in sql
