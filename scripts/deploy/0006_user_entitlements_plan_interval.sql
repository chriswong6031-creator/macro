-- Record the billing interval on the entitlement row (authui upgrade-matrix lane).
-- Purely additive + idempotent: ADD COLUMN IF NOT EXISTS. Safe to re-run.
--
-- Already applied on prod via the Supabase Management API; this file is the repo record so a
-- fresh Supabase project (or `scripts/deploy/*.sql` replay) reaches the same schema. Run once in
-- the Supabase SQL editor (see docs/ops/stripe-setup.md).
--
-- WHY: the upgrade matrix (Insider/Pro × monthly/annual) needs the current cadence to decide the
-- legal next step and to render "Insider · annual" in the account card. WRITE path is
-- app/billing.py::_upsert_entitlement (service-role, bypasses RLS); READ path is
-- read_entitlement -> /api/me + /api/account. Nullable on purpose: free rows and pre-migration
-- rows carry NULL (no cadence), and comp passes may omit it.

alter table public.user_entitlements
  add column if not exists plan_interval text
  check (plan_interval in ('monthly', 'annual'));
