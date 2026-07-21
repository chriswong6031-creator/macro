-- Billing spine entitlement store (MNZ W2, masterplan §3.2).
-- Purely additive + idempotent: CREATE TABLE IF NOT EXISTS, drop/create policies, ENABLE RLS.
-- Safe to re-run. Run once in the Supabase SQL editor (see docs/ops/stripe-setup.md).
--
-- READ path already lives in engine/neuralweb/brain_gateway.py::_resolve_tier (service-role
-- PostgREST). WRITE path is the Stripe webhook / reconciler in app/billing.py (service-role,
-- which bypasses RLS). Clients may only SELECT their own row; they can never write.

create table if not exists public.user_entitlements (
  user_id             uuid primary key references auth.users(id) on delete cascade,
  -- NOT unique on purpose: a Stripe-side customer merge could briefly map one customer to two
  -- user rows; a unique constraint would turn that into an upsert-conflict 500 and wedge the
  -- webhook into an infinite Stripe retry loop. Lookups tolerate a rare duplicate (they take the
  -- first row); the index below serves customer->user resolution.
  stripe_customer_id  text,
  tier                text not null default 'free',   -- 'free' | 'insider' | 'pro'
  features            text[] not null default '{}',   -- mirror of Stripe active entitlements
  status              text not null default 'none',   -- 'active'|'trialing'|'past_due'|'canceled'|'none'
  source              text not null default 'stripe', -- 'stripe' | 'substack' | 'comp'
  current_period_end  timestamptz,
  updated_at          timestamptz not null default now()
);
create index if not exists user_entitlements_customer on public.user_entitlements (stripe_customer_id) where stripe_customer_id is not null;
create index if not exists user_entitlements_status   on public.user_entitlements (status);

alter table public.user_entitlements enable row level security;

-- The ONLY client-facing grant: a signed-in user may read their own entitlement row (so the
-- browser can show the current plan without a round-trip to macro-api). No INSERT/UPDATE/DELETE
-- policy exists, so RLS denies every client write; only the service-role key (webhook/reconciler/
-- substack sync) writes, and it bypasses RLS entirely.
drop policy if exists user_entitlements_select_own on public.user_entitlements;
create policy user_entitlements_select_own
  on public.user_entitlements for select
  using (auth.uid() = user_id);

-- Webhook idempotency ledger: every processed Stripe event id is recorded here with
-- `insert ... on conflict do nothing`; a zero-row insert means "already handled" and the
-- webhook short-circuits. Deny-all RLS — only the service-role touches it.
create table if not exists public.stripe_events (
  id           text primary key,
  type         text,
  received_at  timestamptz not null default now()
);
alter table public.stripe_events enable row level security;
