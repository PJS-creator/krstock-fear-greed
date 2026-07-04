-- Optional journal notes table for user-authenticated public portfolio app.
-- This migration is additive and does not modify existing portfolio data.

create extension if not exists pgcrypto;

create table if not exists public.journal_notes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    portfolio_id text not null default 'main',
    note_date date not null,
    title text not null,
    body text,
    symbol text,
    market text,
    linked_transaction_id uuid,
    linked_cash_ledger_id uuid,
    tags text[],
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists journal_notes_user_portfolio_date_idx
    on public.journal_notes (user_id, portfolio_id, note_date desc);

alter table public.journal_notes enable row level security;

grant select, insert, update, delete on public.journal_notes to authenticated;

drop policy if exists "journal_notes_select_own" on public.journal_notes;
create policy "journal_notes_select_own"
    on public.journal_notes
    for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "journal_notes_insert_own" on public.journal_notes;
create policy "journal_notes_insert_own"
    on public.journal_notes
    for insert
    to authenticated
    with check (auth.uid() = user_id);

drop policy if exists "journal_notes_update_own" on public.journal_notes;
create policy "journal_notes_update_own"
    on public.journal_notes
    for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists "journal_notes_delete_own" on public.journal_notes;
create policy "journal_notes_delete_own"
    on public.journal_notes
    for delete
    to authenticated
    using (auth.uid() = user_id);
