# Support & Email Estate — Masterplan (by Fable)

Status: **CHARTERED 2026-07-25** (operator ask: support dashboard + contact/ticket form; billing/Stripe
confirmation emails; email-marketing flow; all-users email list ready for future campaigns).
Program owner: Fable main loop (plan/adjudicate/merge). Build: Opus `builder` lanes. Design: Opus `designer`.

---

## §0 ACCEPTANCE GATES (program is NOT DONE unless…)

**G1 — Ticket round-trip, live.** A visitor (signed-out AND signed-in) submits the form at
`https://www.mastermind-x.com/support.html` → row appears in Supabase `support_tickets` → ticket is
visible with correct metadata (email, topic, tier for signed-in users) in the admin panel Support tab at
`admin.mastermind-x.com` → operator reply from the admin panel transitions status and (once SMTP creds are
live) sends the reply email. Verified live post-merge with a real test submission, not curl-status theater.

**G2 — Billing emails fire idempotently.** Stripe webhook events (checkout completed / upgrade /
payment failed / cancellation) each produce exactly ONE ledgered send per (event, template) — replaying the
same webhook event does NOT double-send (email_log idempotency proven by test). With SMTP unconfigured, the
system runs in mail-off mode: ledger rows written with status `skipped_no_smtp`, webhook never 5xxs because
of mail. Proven by unit tests + a `stripe listen`-forwarded test event or admin test-send.

**G3 — Marketing list one click away.** Admin Email page shows the all-users roster with segments
(all / free / trialing / paid tier / canceled / marketing-eligible) and a working CSV export whose
marketing-eligible segment EXCLUDES suppressed + opted-out addresses by construction. Numbers foot against
the existing Users page counts.

**G4 — Compliance spine exists before any marketing send.** Public unsubscribe endpoint (tokenized,
no login required) + email_prefs/suppression tables + List-Unsubscribe + List-Unsubscribe-Post headers on
every marketing-class send; transactional class exempt. A suppressed address is provably skipped by the
campaign sender (test).

**G5 — Bilingual + doctrine-compliant surfaces.** /support.html is EN/ZH dual-language via the house
`t()` macro + `data-lang` toggle, follows DESIGN_DOCTRINE (Tier-1 plain words, stance-first microcopy), and
was built from a designer-pinned spec (committed mockup), not builder improvisation. Emails render
dual-language (EN primary, ZH secondary) in v1.

**G6 — Boundary + CI green.** `config/site_access.yml` + `app/deploy/Caddyfile` (@reg_html AND the
PUBLIC-BOUNDARY asset block) + `app/regwall.py` all updated in the SAME PR as the page
(tests/test_site_access_boundary.py green); new Python modules carry tests registered in `ci.yml`
path triggers (a suite that CI never runs is rot — see #3509/#3511 precedent). Site page live-verified
(200 + content) after render-lane pickup; every PR squash-merged same-day.

**G7 — No secrets, fail-soft everywhere.** No credentials committed. Every new runtime feature degrades
gracefully when its env is absent (mailer → mail-off ledger mode; admin tabs → clear "not configured"
panel state, never a stack trace). VPS checkout is ephemeral — NOTHING durable is written to VPS-local
files; all state lives in Supabase.

---

## §1 Charter

Four deliverables, one estate:

1. **Support system** — public bilingual contact/ticket page; tickets stored durably; operator Support
   dashboard (list / detail / status transitions / reply-by-email) inside the existing admin panel.
2. **Transactional billing emails** — Stripe-webhook-driven: purchase/trial confirmation, plan upgrade,
   payment failed, cancellation; later renewal reminders (T-30/T-7 was already scoped in the monetization
   masterplan W7).
3. **Email marketing foundation** — behavior-triggered lifecycle (welcome; trial-ending), campaign queue
   skeleton with throttle, suppression/consent spine, segments.
4. **All-users email list** — segments + CSV export layered on the existing admin users/entitlements
   roster (#3354), marketing-eligibility aware.

## §2 Estate facts (census digest, 2026-07-25 — receipts inline)

- **One Stripe integration**, in THIS repo: `app/billing.py` (webhook `/api/billing/webhook`, checkout,
  Elements subscribe, upgrade matrix, portal), entitlements in Supabase `public.user_entitlements`
  (migrations `scripts/deploy/0005/0006`), idempotency ledger `public.stripe_events`, nightly
  `--reconcile` cron. Terminal repo is a thin proxy — **no cross-repo billing work needed**.
- **No email transport exists.** No templates, no SMTP/provider code anywhere in the estate. Supabase
  auth email = dev-only (2/hr). Monetization masterplan + WATCHLIST.md + onboarding masterplan all name
  "custom SMTP (Resend/SES/Postmark)" as the pre-paid-launch P0. Outbound port 25 is blocked on the
  droplet — direct self-hosted send is a dead end. The live house pattern is greydeercapital
  `server/intake.py`: stdlib `smtplib` STARTTLS submission to env-configured relay, mail-off default,
  persist-first. The dormant "Email Client" (Mailu) repo is NOT a usable transport (zero commits, stubs).
- **Users**: ONE shared Supabase project for www + app.mastermind-x.com (shared SSO). `auth.users` is the
  list. Admin already reads it via Management-API SQL PAT (`admin/users.py`, `admin/entitlements.py`
  list/filter/pagination). **No CSV export, no locale column, no consent/unsubscribe fields anywhere.**
  Terminal keeps lang in localStorage; `templates/account.js` calls `POST /api/account/prefs` which
  **does not exist server-side** (dead client call — we ship it).
- **Admin panel**: `admin/` in this repo (Python stdlib http.server + vanilla-JS SPA), deployed
  admin.mastermind-x.com, VPS 3-min cron pull, GitHub Contents API for deployed-mode writes. House
  patterns to clone: `admin/entitlements.py` (paginated roster), `admin/allies_store.py` (status
  state-machine), `admin/actions.py` (ledger). Nav = `NAV_GROUPS` in `admin/static/app.js` (~line 164);
  RENDER dispatch table; routes in `admin/server.py` if/elif chains.
- **Site**: zero existing support/contact surfaces; no shared footer partial (landing footer
  `templates/index.html` ~1507-1534 has Product/Resources columns — insertion point); bilingual via
  per-template `t(en, zh)` macro + `html[data-lang]`; new page recipe = template + `build_<name>_page()`
  + `write_page()` in `scripts/build_site.py` + **3-place access boundary edit** (site_access.yml public,
  Caddyfile @reg_html + PUBLIC-BOUNDARY block, regwall.py mirrors) guarded by
  `tests/test_site_access_boundary.py`; sitemap auto-globs public pages.
- **Binding prior rulings**: marketing grandmaster plan L1582 — *no generic drip sequences detached from
  behavior* (lifecycle sends must be behavior-triggered); design doctrine + design-lane routing;
  main-nav edits ON HOLD (support entry goes in footers + plans, not the nav).

## §3 Rulings

**R1 — Transport: provider SMTP submission, env-gated, ships dark.** New `app/mailer.py`:
stdlib `smtplib` + `email.message.EmailMessage`, STARTTLS (587) / SSL (465), env
`MAIL_SMTP_HOST/PORT/USER/PASS`, `MAIL_FROM` (e.g. `Mastermind <no-reply@mastermind-x.com>`),
`MAIL_SUPPORT_TO` (operator inbox), `MAIL_REPLY_TO` (support@). Resend is the named default provider
candidate (three prior docs agree); the abstraction is provider-agnostic SMTP so the operator may swap
(Postmark/SES) without code. Mail-off mode when unconfigured: every send is still ledgered
(`email_log.status='skipped_no_smtp'`) and callers NEVER raise. Creds ride the existing
`deploy-api-secrets.yml` SSH lane into `/etc/macro-api.env`. The SAME creds later go into Supabase Auth
SMTP (operator dashboard step — runbook §6). DNS SPF/DKIM/DMARC records = runbook §6, operator-side.
**Never** send from the ephemeral VPS checkout's own identity; never write durable state VPS-local (G7).

**R2 — Ticket storage: Supabase, service-role writer, Management-SQL reader.**
`support_tickets` + `support_ticket_messages` (§5). Writer = macro-api (`app/support.py`) via the same
PostgREST service-role pattern as `app/billing.py::_pg()`. Admin reads via the existing Management-API SQL
lane (`admin/users.py` style) → new `admin/support_tickets.py`. Public POST is abuse-hardened: honeypot
field + minimum-fill-time + per-IP in-process rate limit + payload caps + strict field allowlist; optional
Bearer token attaches user_id/tier (verified server-side against Supabase auth, same as billing routes).
No attachments in v1 (attack surface). Anti-spam counters are in-process only (restart resets — accepted).

**R3 — Email idempotency: ledger-first.** `email_log` row (with unique `idem_key`) is inserted BEFORE any
SMTP attempt; unique-violation ⇒ skip (already sent/attempted). Webhook-driven sends key
`stripe:{event_id}:{template}`; lifecycle sends key `{kind}:{user_id}` (welcome) or
`{kind}:{user_id}:{period_end_date}` (trial/renewal reminders — re-armable per period); campaign sends key
`campaign:{campaign_id}:{user_id}`. This closes the crash-retry double-send hole (stripe_events records
only after successful handling, so email sends cannot rely on it).

**R4 — Bilingual v1: dual-language bodies.** No reliable per-user locale exists in the DB. Emails render
EN primary + 中文 secondary in one body (matches the site's dual-render philosophy; honest and
zero-heuristics). We ADD the preference plumbing now: `email_prefs.lang` + ship the missing
`POST /api/account/prefs` (writes `{lang, theme}` to auth user_metadata + mirrors lang into email_prefs),
so single-language sends become possible later without a migration. Fixes the dead client call in
`templates/account.js` as a bonus.

**R5 — Marketing compliance spine (before ANY campaign send).**
- `email_prefs.marketing_opt_out` (user-keyed) + `email_suppression` (address-keyed: unsubscribes from
  non-users, hard bounces, complaints; manual admin add).
- Public tokenized unsubscribe: `GET /unsubscribe.html?t=<token>` (public page, boundary-listed) →
  `POST /api/email/unsubscribe` — token = HMAC(user_id|email, MAIL_UNSUB_SECRET), no login required,
  one-click semantics; also honored as `List-Unsubscribe: <mailto:…>, <https://…>` +
  `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers on every marketing-class send.
- Class discipline: `transactional` (receipts, ticket replies, payment-failed, trial-ending) NEVER
  suppressed by marketing opt-out; `marketing` (welcome extras, campaigns) ALWAYS checks opt-out +
  suppression at send time inside `mailer.send(...)`, not at queue time.
- Anti-drip ruling honored: lifecycle sends are behavior-triggered only (signup → welcome; trialing &
  period_end−2d → trial-ending). No calendar drip chains.

**R6 — Surface placement: funnel-first, nav-hold respected.** `/support.html` public page (also linked
from `plans.html` and the landing footer's Resources column + a new minimal "Support" line in internal
page footers only where trivially safe). NO `_navlinks.html.j2` edits (nav hold). NO terminal-repo changes
in v1 (terminal already deep-links to www for billing; support follows the same funnel). Page copy follows
doctrine: Tier-1 plain words, response-time expectation stated honestly, billing/account/bug/data/other
topics, ticket-received state on submit.

**R7 — Admin surfaces: clone house idioms.** New "Support" nav group in `NAV_GROUPS`:
`support_tickets` ("Support Tickets") + `email_center` ("Email Center"). Support tab = entitlements-style
paginated list (status filter chips, tier badge via user_entitlements join) + detail thread + status
state-machine (`open → pending → resolved → closed`, allies_store `is_legal()` pattern) + reply box
(sends via mailer, appends message row). Email Center tab = roster segments + CSV export + suppression
manager + campaign composer/queue (W3) + SMTP status card (shows mail-off vs configured, last 20
email_log rows). Deployed-mode writes that mutate repo state are N/A here — all state is Supabase, so
the Contents-API lane is not needed by these tabs.

**R8 — Stripe stays the receipt-of-record OFF.** We send our own branded receipts; runbook notes the
Stripe Dashboard "Customer emails" toggles stay OFF to avoid double receipts (their state is
dashboard-side and currently test-mode anyway).

## §4 Waves (PR lanes; every PR completes the full ship loop same-day)

**W-D — Design pins (Opus `designer`, standalone PR, merges first).**
Deliverables committed under `mockups/support_email/`: (1) support page static mockup
(desktop+mobile, light+dark, EN+ZH) in the macro-site idiom; (2) email visual system — base HTML
template (table-layout, inline CSS, ≤600px, dark-mode-safe, text-wordmark brand, footer with company
line + unsubscribe slot) + per-template content specs (receipt, upgrade, payment-failed, cancellation,
trial-ending, welcome, ticket-ack, ticket-reply, campaign shell); (3) a one-page PIN.md spec naming
exact tokens (colors/type/spacing) both builders must consume. Doctrine + frontend-design skill loaded;
doctrine wins on conflict.

**W1 — Spine (Opus `builder`, PR-A; starts in parallel with W-D).**
`scripts/deploy/0007_support_email.sql` (§5, idempotent, deny-all RLS, service-role only) ·
`app/mailer.py` (R1, R3, R5 send-time gates; plain functional fallback template until W-D lands) ·
`app/support.py` (`POST /api/support/ticket` public + abuse-hardened; operator notification email on
create) · mount in `app/main.py` try/except like billing · `admin/support_tickets.py` + routes in
`admin/server.py` + `NAV_GROUPS`/`RENDER.support_tickets` in `admin/static/app.js` (list/detail/
status/reply; reply sends via mailer + appends message) · tests (`tests/test_mailer.py`,
`test_support_api.py`, `test_admin_support_tickets.py`) + ci.yml path registration · runbook
`docs/ops/email-support-setup.md` (§6 content). Caddy: verify `/api/support/*` reaches macro-api through
the www origin (billing-route precedent; #3418 pattern if a matcher edit is needed — include in-PR).

**W2 — Support page goes public (Opus `builder`, PR-B; after W-D + W1 merge).**
`templates/support.html.j2` from the pinned mockup (t() macro, `_site_nav` include, `write_page`
via new `build_support_page()` in `scripts/build_site.py` main()) · ticket-ack email to submitter using
the designed base (swap W1's fallback base to the pinned one repo-wide) · 3-place access boundary +
regwall mirrors (G6) · footer links (landing Resources column + plans.html) · commit the locally-baked
`site/support.html` so the page is servable at merge; confirm render-lane coverage; live-verify
`https://www.mastermind-x.com/support.html` (200 + content + EN/ZH toggle) post-merge.

**W3 — Billing emails (Opus `builder`, PR-C; after W1 merge, parallel with W2).**
Hook `app/billing.py::_handle_event` AFTER entitlement upsert: event→template map
(`checkout.session.completed`→purchase/trial confirmation with plan/interval/amount/period;
`customer.subscription.updated` with tier-rank increase→upgrade-confirmation (the /upgrade route also
passes through here — webhook is the single email trigger, so portal-driven changes are covered too);
`invoice.payment_failed`→payment-failed with portal link; `customer.subscription.deleted`→cancellation).
Amounts/plan names read from the live Stripe objects + `config/plans.yml` names, never hardcoded ·
email_log idempotency per R3 (webhook replay test MUST prove single-send) · lifecycle sweeper
(in-process asyncio task in macro-api, env-gated `MAIL_LIFECYCLE_ENABLED`, cursor-free — idempotent via
email_log): trial-ending T-2 from `user_entitlements` (status=trialing, period_end within 2d) ·
`POST /api/account/prefs` (R4) · tests incl. replay + sweeper idempotency + prefs route; ci.yml
registration.

**W4 — Marketing foundation (Opus `builder`, PR-D; after W1+W3 merge).**
`admin/email_center.py` + Email Center tab (R7): segments roster (joins auth.users ⟕ user_entitlements ⟕
email_prefs ⟕ suppression; counts foot vs Users page) · `GET /api/email/export.csv?segment=…` (streamed
CSV; marketing-eligible excludes opt-out/suppressed/unconfirmed-bounced) · suppression manager (list/add/
remove with reason) · unsubscribe spine (R5): `site/unsubscribe.html` public page + token endpoint +
List-Unsubscribe headers wired into mailer marketing class · welcome email on signup (sweeper detects new
auth.users rows via email_log absence; marketing-class, suppression-aware) · campaign skeleton:
`email_campaigns` + composer in Email Center (subject + body → designed campaign shell; segment pick;
queue) → sweeper drains queue at `MAIL_THROTTLE_PER_MIN` (default 30) with per-send suppression re-check;
campaign status card (queued/sent/skipped/failed) · tests: suppression-skip proof (G4), export
correctness, token round-trip; ci.yml registration.

**W5 (follow-on, NOT this program): ** renewal T-30/T-7 reminders (monetization W7 alignment), Supabase
Auth SMTP cutover + email-confirmation ON (P0 pre-paid-launch checklist), terminal nav Support link,
comp-grant emails, admin reply templates/macros, CSAT ping.

Merge order: W-D → (W1) → W2 ∥ W3 → W4. Each PR branches off fresh origin/main AFTER its dependency
merges (never stacked). Reviewer (Opus) passes each PR before merge; main session owns merges + live
verification (spawn-handoff law #4: no builder self-merge of the user-facing W2 without the visual
artifact posted in the PR body).

## §5 Data contracts (migration `scripts/deploy/0007_support_email.sql` — idempotent, RLS deny-all,
service-role only unless noted)

```sql
create table if not exists public.support_tickets (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  email text not null,                -- submitter (verified session email when signed in)
  user_id uuid references auth.users(id),   -- null for signed-out submitters
  topic text not null check (topic in ('billing','account','bug','data','feature','other')),
  subject text not null,              -- length-capped app-side
  status text not null default 'open' check (status in ('open','pending','resolved','closed')),
  lang text,                          -- 'en'|'zh' page-lang at submit (email localization hint)
  tier text,                          -- entitlement tier snapshot at submit (admin display)
  meta jsonb not null default '{}'::jsonb   -- ua, path, ip-hash — never raw secrets
);
create table if not exists public.support_ticket_messages (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.support_tickets(id) on delete cascade,
  created_at timestamptz not null default now(),
  author text not null check (author in ('user','operator')),
  body text not null,
  emailed boolean not null default false     -- operator replies: whether the email send was attempted
);
create table if not exists public.email_log (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  idem_key text not null unique,      -- R3 keys
  template text not null,
  class text not null check (class in ('transactional','marketing')),
  to_email text not null,
  user_id uuid,
  status text not null check (status in ('sent','failed','skipped_no_smtp','suppressed','queued')),
  detail text                          -- smtp error class / suppression reason; never message bodies
);
create table if not exists public.email_prefs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  lang text check (lang in ('en','zh')),
  marketing_opt_out boolean not null default false,
  updated_at timestamptz not null default now()
);
create table if not exists public.email_suppression (
  email text primary key,
  reason text not null check (reason in ('unsubscribe','bounce','complaint','manual')),
  created_at timestamptz not null default now()
);
create table if not exists public.email_campaigns (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  subject text not null, body_md text not null, segment text not null,
  status text not null default 'draft' check (status in ('draft','queued','sending','done','aborted')),
  queued_n int, sent_n int default 0, skipped_n int default 0, failed_n int default 0
);
```
Indexes: tickets(status, created_at desc), messages(ticket_id), email_log(to_email, created_at desc),
email_log(template) — builder adds `create index if not exists`. RLS: enable + deny-all on ALL SIX (no
client policies; macro-api service-role + admin Management-SQL only). Operator applies via Supabase SQL
editor (runbook step, same as 0005/0006 precedent).

## §6 Ops runbook (`docs/ops/email-support-setup.md`, shipped in W1)

1. Provider: create Resend (or equivalent) account → SMTP creds; domain `mastermind-x.com` sender
   verification → add SPF include + DKIM CNAMEs + DMARC (start `p=none`, tighten later) at the DNS host.
   (Apex already carries MX — ADD records only, never replace MX.)
2. Secrets → `/etc/macro-api.env` via `deploy-api-secrets.yml` lane (extend its allowlist with the new
   MAIL_* names): `MAIL_SMTP_HOST/PORT/USER/PASS`, `MAIL_FROM`, `MAIL_REPLY_TO`, `MAIL_SUPPORT_TO`,
   `MAIL_UNSUB_SECRET`, `MAIL_LIFECYCLE_ENABLED`, `MAIL_THROTTLE_PER_MIN` → `systemctl restart macro-api`.
3. Apply `scripts/deploy/0007_support_email.sql` in the Supabase SQL editor.
4. Admin Email Center → SMTP status card shows configured + test-send button → send to operator inbox.
5. Later (paid-launch checklist): plug the same SMTP into Supabase Auth; turn email confirmation ON;
   keep Stripe Dashboard customer emails OFF (R8).

## §7 Model routing (this program)

Fable main loop: this plan, adjudications, merges, live verification. `designer` (opus): W-D.
`builder` (opus): W1–W4. `reviewer` (opus): every PR pre-merge. Sonnet: was recon only (done).
No fable spawns anticipated (nothing here fails the draft-and-review test); if one becomes needed it goes
through the orchestrator+FABLE-WHY gate.
