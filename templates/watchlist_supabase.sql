-- Watchlist cloud sync — Supabase schema + Row Level Security.
-- Run ONCE in the Supabase project (SQL editor) to enable account sync.
-- The whole watchlist blob (the same shape stored in localStorage under
-- `mdash.watchlist.v1`) is stored as a single jsonb document per user.
--
-- SECURITY: the anon/publishable key shipped in the client is PUBLIC by design.
-- Per-user isolation is enforced ENTIRELY by the RLS policies below against the
-- caller's JWT (auth.uid()). The service_role key must NEVER be put in the site.
-- After running this, verify with a throwaway user that one account cannot read
-- or write another's row, and that the anon key alone (no JWT) returns nothing.

create table if not exists public.watchlists (
  user_id    uuid        primary key references auth.users (id) on delete cascade,
  doc        jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.watchlists enable row level security;

-- a user may only ever touch their OWN row
drop policy if exists "watchlist_select_own" on public.watchlists;
create policy "watchlist_select_own" on public.watchlists
  for select using (auth.uid() = user_id);

drop policy if exists "watchlist_insert_own" on public.watchlists;
create policy "watchlist_insert_own" on public.watchlists
  for insert with check (auth.uid() = user_id);

drop policy if exists "watchlist_update_own" on public.watchlists;
create policy "watchlist_update_own" on public.watchlists
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "watchlist_delete_own" on public.watchlists;
create policy "watchlist_delete_own" on public.watchlists
  for delete using (auth.uid() = user_id);

-- Optional keep-alive: free Supabase projects pause after ~7 days of inactivity.
-- Have the existing nightly GitHub Action issue one tiny authenticated query so
-- the project never sleeps. Example step for .github/workflows/daily.yml:
--
--   - name: supabase keep-alive
--     run: |
--       curl -s "$SUPABASE_URL/rest/v1/watchlists?select=user_id&limit=1" \
--         -H "apikey: $SUPABASE_ANON_KEY" -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
--         >/dev/null || echo "::warning::supabase keep-alive failed"
--     env:
--       SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
--       SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
