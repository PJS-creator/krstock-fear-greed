from pathlib import Path


def test_price_fx_cache_migration_adds_public_market_data_tables():
    sql = Path("docs/supabase_migration_v4_price_fx_cache.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists public.price_cache" in sql
    assert "create table if not exists public.fx_rates" in sql
    for column in ("price_date", "as_of_timestamp", "source", "status", "error_message", "fetched_at"):
        assert column in sql
    assert "alter table public.price_cache enable row level security" in sql
    assert "alter table public.fx_rates enable row level security" in sql
    assert "grant select on public.price_cache to authenticated" in sql
    assert "grant select on public.fx_rates to authenticated" in sql
    assert "for select" in sql
    assert "using (true)" in sql
    assert "정상_최근종가" in sql
    assert "이전저장값사용" in sql
    assert "환율실패_기존값유지" in sql
