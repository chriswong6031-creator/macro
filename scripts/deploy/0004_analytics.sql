-- First-party analytics tables (mirror of the Terminal repo's supabase/migrations/0004_analytics.sql).
-- Purely additive: CREATE TABLE IF NOT EXISTS + indexes + ENABLE RLS (deny-all). Idempotent.
create table if not exists public.analytics_events (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  client_ts   timestamptz,
  type        text not null check (char_length(type) <= 32),
  site        text not null default '' check (char_length(site) <= 16),
  path        text          check (char_length(path) <= 512),
  ref         text          check (char_length(ref) <= 512),
  ticker      text          check (char_length(ticker) <= 64),
  dwell_ms    integer       check (dwell_ms is null or dwell_ms between 0 and 86400000),
  scroll      smallint      check (scroll is null or scroll between 0 and 100),
  fp          text          check (char_length(fp) <= 64),
  session_id  text          check (char_length(session_id) <= 64),
  visitor_id  text          check (char_length(visitor_id) <= 64),
  user_id     uuid references auth.users(id) on delete set null,
  ip          text          check (char_length(ip) <= 64),
  ua          text          check (char_length(ua) <= 256),
  meta        jsonb
);
create index if not exists analytics_events_created on public.analytics_events (created_at desc);
create index if not exists analytics_events_visitor on public.analytics_events (visitor_id, created_at desc) where visitor_id is not null;
create index if not exists analytics_events_session on public.analytics_events (session_id, created_at) where session_id is not null;
create index if not exists analytics_events_type    on public.analytics_events (type, created_at desc);
create index if not exists analytics_events_ticker  on public.analytics_events (ticker, created_at desc) where ticker is not null;
create index if not exists analytics_events_site    on public.analytics_events (site, created_at desc);
create index if not exists analytics_events_ip      on public.analytics_events (ip) where ip is not null;
alter table public.analytics_events enable row level security;

create table if not exists public.ip_geo (
  ip           text primary key check (char_length(ip) <= 64),
  country text, country_code text, region text, city text,
  lat double precision, lon double precision, asn text, org text,
  is_vpn boolean, is_proxy boolean, is_tor boolean, is_hosting boolean, is_abuser boolean,
  fetched_at   timestamptz not null default now()
);
create index if not exists ip_geo_country on public.ip_geo (country_code);
alter table public.ip_geo enable row level security;
