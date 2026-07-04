from pathlib import Path


def test_journal_notes_migration_is_additive_and_rls_protected():
    sql = Path("docs/supabase_migration_v6_journal_notes.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists public.journal_notes" in sql
    assert "alter table public.journal_notes enable row level security" in sql
    assert "grant select, insert, update, delete on public.journal_notes to authenticated" in sql
    assert "auth.uid() = user_id" in sql
    assert "drop table" not in sql
