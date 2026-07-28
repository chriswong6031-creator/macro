-- Prophet Trade Memory private user-data plane.
-- Additive + idempotent. Apply through the Supabase SQL editor or Management API.
--
-- Privacy contract:
--   * every row belongs to auth.users and RLS is enabled;
--   * browser clients can only read/write their own episodes;
--   * exact position size, account value, and dollar P&L have no columns;
--   * nightly Prophet uses the service role plus SUPABASE_OPERATOR_USER_ID;
--   * autopsies/patterns remain private and are never snapshotted into git.

create table if not exists public.trade_episodes (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete cascade,
  schema              text not null default 'prophet.trade_episode/v1',
  source              text not null check (source in ('operator','prophet','historical_replay')),
  ticker              text not null check (ticker ~ '^[A-Z0-9][A-Z0-9._-]{0,19}$'),
  market              text not null default 'us',
  side                text not null default 'long' check (side in ('long','short')),
  entry_date          date not null,
  exit_date           date,
  entry_price         numeric check (entry_price is null or entry_price > 0),
  exit_price          numeric check (exit_price is null or exit_price > 0),
  outcome             text not null default 'open' check (outcome in ('open','win','loss','flat')),
  thesis_at_entry     text not null default '',
  observed_result     text not null default '',
  prophet_pick_ref    text,
  evidence_packet     jsonb,
  autopsy             jsonb,
  autopsy_state       text not null default 'waiting_close'
                      check (autopsy_state in ('waiting_close','pending','running','retry','complete')),
  autopsy_model       text,
  autopsy_error       text,
  autopsied_at        timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  check (exit_date is null or exit_date >= entry_date),
  check (
    (entry_price is null and exit_price is null)
    or (entry_price is not null and exit_price is not null)
  )
);
create index if not exists trade_episodes_owner_date
  on public.trade_episodes (user_id, entry_date desc);
create index if not exists trade_episodes_autopsy_queue
  on public.trade_episodes (user_id, autopsy_state, created_at)
  where autopsy_state in ('pending','retry');

alter table public.trade_episodes enable row level security;

drop policy if exists trade_episodes_owner_select on public.trade_episodes;
create policy trade_episodes_owner_select on public.trade_episodes
  for select using (auth.uid() = user_id);
drop policy if exists trade_episodes_owner_insert on public.trade_episodes;
create policy trade_episodes_owner_insert on public.trade_episodes
  for insert with check (auth.uid() = user_id);
drop policy if exists trade_episodes_owner_update on public.trade_episodes;
create policy trade_episodes_owner_update on public.trade_episodes
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists trade_episodes_owner_delete on public.trade_episodes;
create policy trade_episodes_owner_delete on public.trade_episodes
  for delete using (auth.uid() = user_id);

-- Rebuildable private materialized view of repeated hypotheses. The nightly service
-- role is the only writer; clients may read their own rows but cannot promote them.
create table if not exists public.trade_memory_patterns (
  user_id       uuid not null references auth.users(id) on delete cascade,
  feature_key   text not null,
  status        text not null default 'accruing'
                check (status in ('accruing','ready_for_prereg')),
  pattern       jsonb not null,
  updated_at    timestamptz not null default now(),
  primary key (user_id, feature_key)
);

alter table public.trade_memory_patterns enable row level security;
drop policy if exists trade_memory_patterns_owner_select on public.trade_memory_patterns;
create policy trade_memory_patterns_owner_select on public.trade_memory_patterns
  for select using (auth.uid() = user_id);
drop policy if exists trade_memory_patterns_owner_write on public.trade_memory_patterns;
