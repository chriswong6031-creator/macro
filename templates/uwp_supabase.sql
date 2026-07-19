-- uwp_supabase.sql — UWP W1: RLS policies for portfolio_positions.
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
