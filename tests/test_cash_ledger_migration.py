from pathlib import Path


def test_cash_ledger_migration_adds_rls_and_backfill_path():
    sql = Path("docs/supabase_migration_v3_cash_ledger.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists public.cash_ledger" in sql
    assert "alter table public.cash_ledger enable row level security" in sql
    assert "grant select, insert, update, delete on public.cash_ledger to authenticated" in sql
    assert "user_id = auth.uid()" in sql
    assert "event_type in" in sql
    assert "opening_balance" in sql
    assert "buy_settlement" in sql
    assert "sell_settlement" in sql
    assert "portfolio_snapshots" in sql
    assert "payload_json #>> '{cash_balances,krw}'" in sql
    assert "payload_json #>> '{cash_balances,usd}'" in sql
    assert "on conflict do nothing" in sql
