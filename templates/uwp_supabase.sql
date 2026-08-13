-- uwp_supabase.sql — UWP W1: RLS policies for portfolio_positions.
--
-- ============================================================================
-- SCHEMA AUTHORITY NOTICE (W1a, 2026-08-12)
--
-- The database schema for the shared Supabase project `fsldfzlxyavsuwqbceod` is
-- recorded in the mastermind-terminal repo, under `supabase/migrations/`:
--
--   * `watchlists` + `watchlist_symbols` (and their owner/via-parent RLS policies)
--     have always lived there — `supabase/migrations/0001_init.sql`. This repo has
--     never owned them, and must not re-declare them.
--   * `portfolio_positions` DDL is recorded there too, by the W1b lane. Its table
--     was created by hand against live prod and its DDL was never committed
--     anywhere; the recorded migration matches the introspected live shape.
--
-- This file therefore stays what it is — the four own-row RLS policies for
-- portfolio_positions, applied by hand in the Supabase SQL editor — and is NOT the
-- place to add tables or columns. New schema goes to the terminal repo's migrations.
--
-- (Some older docs pointed at a `templates/watchlist_supabase.sql`. No such file
-- exists or has existed in this tree; those references were corrected in W1a.)
-- ============================================================================
--
-- IMPORTANT: Apply this file manually in the Supabase SQL editor BEFORE UWP W2 merges.
-- The watchlists and watchlist_symbols policies already exist (Terminal-owned, applied
-- prior to this program). This file covers only portfolio_positions.
--
-- Run this file idempotently; it uses DROP POLICY IF EXISTS before each CREATE POLICY.
-- Safe to re-run after any policy change.
--
-- SECURITY: the anon/publishable key shipped in the client is PUBLIC by design.
-- Per-user isolation is enforced ENTIRELY by RLS against the caller's JWT (auth.uid()).
-- The service_role key must NEVER reach the client.

-- Enable RLS (idempotent)
alter table public.portfolio_positions enable row level security;

-- SELECT: owner only
drop policy if exists "portfolio_select_own" on public.portfolio_positions;
create policy "portfolio_select_own" on public.portfolio_positions
  for select using (auth.uid() = user_id);

-- INSERT: owner only
drop policy if exists "portfolio_insert_own" on public.portfolio_positions;
create policy "portfolio_insert_own" on public.portfolio_positions
  for insert with check (auth.uid() = user_id);

-- UPDATE: owner only
drop policy if exists "portfolio_update_own" on public.portfolio_positions;
create policy "portfolio_update_own" on public.portfolio_positions
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- DELETE: owner only
drop policy if exists "portfolio_delete_own" on public.portfolio_positions;
create policy "portfolio_delete_own" on public.portfolio_positions
  for delete using (auth.uid() = user_id);
