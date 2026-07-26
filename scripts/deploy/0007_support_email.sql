-- Support + Email estate spine (SEE W1, masterplan §5).
-- Purely additive + idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS,
-- drop/create policies, ENABLE RLS. Safe to re-run.
--
-- APPLIED MANUALLY via the Supabase SQL editor (the 0005/0006 precedent — there is no
-- migration runner on the render path). See docs/ops/email-support-setup.md §3.
--
-- Six tables, all DENY-ALL under RLS: no client policy exists on any of them, so the
-- browser can neither read nor write. Every reader/writer is server-side and privileged:
--   * app/support.py   — public ticket intake, service-role PostgREST (RLS-bypassing).
--   * app/mailer.py    — the email ledger + suppression/preference checks, service-role.
--   * admin/support_tickets.py — operator console, Supabase Management-API SQL (PAT).
-- A support ticket carries a free-text body written by an unauthenticated stranger; giving
-- clients ANY policy here would be a read surface over other people's support threads, so
-- the deny-all is the product boundary, not an oversight.

-- ---------------------------------------------------------------------------
-- support_tickets — one row per submitted support request.
-- `email` is the reply address: server-verified when the submitter was signed in
-- (app/support.py overrides the body value from the Bearer token), client-claimed
-- otherwise. `tier` and `lang` are SNAPSHOTS taken at submission time so the operator
-- list needs no join and stays honest about what the user's plan was when they wrote in.
-- ---------------------------------------------------------------------------
create table if not exists public.support_tickets (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  email       text not null,
  -- Nullable on purpose: signed-out submissions are first-class (the contact form is
  -- public). ON DELETE SET NULL, not CASCADE — deleting an account must not silently
  -- destroy the operator's record of a billing dispute.
  user_id     uuid references auth.users(id) on delete set null,
  topic       text check (topic in ('billing','account','bug','data','feature','other')),
  subject     text not null,
  status      text not null default 'open' check (status in ('open','pending','resolved','closed')),
  lang        text,
  tier        text,
  -- ua + a TRUNCATED SHA-256 of the client IP. Never the raw IP: an abuse-rate signal
  -- does not need to be a stored identifier (app/support.py hashes before insert).
  meta        jsonb not null default '{}'
);
create index if not exists support_tickets_status_created
  on public.support_tickets (status, created_at desc);

alter table public.support_tickets enable row level security;

-- ---------------------------------------------------------------------------
-- support_ticket_messages — the thread. author='user' rows come from the public
-- intake; author='operator' rows from the admin reply action. `emailed` records
-- whether an operator reply actually left the building (mailer returned 'sent'),
-- so a mail-off window is visible in the thread instead of being silently lost.
-- ---------------------------------------------------------------------------
create table if not exists public.support_ticket_messages (
  id          uuid primary key default gen_random_uuid(),
  ticket_id   uuid not null references public.support_tickets(id) on delete cascade,
  created_at  timestamptz not null default now(),
  author      text check (author in ('user','operator')),
  body        text not null,
  emailed     boolean not null default false
);
create index if not exists support_ticket_messages_ticket
  on public.support_ticket_messages (ticket_id);

alter table public.support_ticket_messages enable row level security;

-- ---------------------------------------------------------------------------
-- email_log — the send ledger AND the idempotency gate (SEE-R3, ledger-first).
-- app/mailer.py INSERTs status='queued' keyed on a caller-supplied idem_key BEFORE
-- touching SMTP; the UNIQUE constraint is what makes a duplicate send impossible.
-- A 409 from PostgREST on that insert means "already handled" and the send is skipped.
-- `detail` carries an exception CLASS name or a suppression reason — never a body,
-- never a credential.
-- ---------------------------------------------------------------------------
create table if not exists public.email_log (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  idem_key    text not null unique,
  template    text,
  class       text check (class in ('transactional','marketing')),
  to_email    text,
  user_id     uuid,
  status      text check (status in ('sent','failed','skipped_no_smtp','suppressed','queued')),
  detail      text
);
create index if not exists email_log_to_created
  on public.email_log (to_email, created_at desc);

alter table public.email_log enable row level security;

-- ---------------------------------------------------------------------------
-- email_prefs — per-user email preferences. `marketing_opt_out` is consulted ONLY for
-- class='marketing'; transactional mail (ticket replies, receipts) never checks it,
-- because a user who opted out of marketing has not opted out of being answered.
-- ---------------------------------------------------------------------------
create table if not exists public.email_prefs (
  user_id             uuid primary key references auth.users(id) on delete cascade,
  lang                text check (lang in ('en','zh')),
  marketing_opt_out   boolean not null default false,
  updated_at          timestamptz not null default now()
);

alter table public.email_prefs enable row level security;

-- ---------------------------------------------------------------------------
-- email_suppression — address-level kill list (unsubscribe / bounce / complaint /
-- manual). Keyed on the ADDRESS, not the user, so it also covers people who never
-- registered. Same class rule as email_prefs: marketing only.
-- ---------------------------------------------------------------------------
create table if not exists public.email_suppression (
  email       text primary key,
  reason      text check (reason in ('unsubscribe','bounce','complaint','manual')),
  created_at  timestamptz not null default now()
);

alter table public.email_suppression enable row level security;

-- ---------------------------------------------------------------------------
-- email_campaigns — operator broadcast records (W4 drives these; the table ships now
-- so the schema lands in one reviewed migration). The four counters are the honest
-- outcome census of a send: queued/sent/skipped/failed, never a bare "done".
-- ---------------------------------------------------------------------------
create table if not exists public.email_campaigns (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  subject     text,
  body_md     text,
  segment     text,
  status      text not null default 'draft' check (status in ('draft','queued','sending','done','aborted')),
  queued_n    integer not null default 0,
  sent_n      integer not null default 0,
  skipped_n   integer not null default 0,
  failed_n    integer not null default 0
);

alter table public.email_campaigns enable row level security;

-- ---------------------------------------------------------------------------
-- DENY-ALL confirmation. RLS with zero policies denies every anon/authenticated
-- request by default; these DROPs exist so a re-run after someone experimented with
-- a client policy in the SQL editor converges back to the deny-all contract.
-- ---------------------------------------------------------------------------
drop policy if exists support_tickets_client          on public.support_tickets;
drop policy if exists support_ticket_messages_client  on public.support_ticket_messages;
drop policy if exists email_log_client                on public.email_log;
drop policy if exists email_prefs_client              on public.email_prefs;
drop policy if exists email_suppression_client        on public.email_suppression;
drop policy if exists email_campaigns_client          on public.email_campaigns;
