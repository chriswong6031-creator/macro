# Monetization & Access Program (MNZ) — masterplan (W0)

**Status:** CHARTERED 2026-07-18 by operator order ("full deep brainstorming of a Plans page,
paid access with tiers, trial plan, Stripe integration, sign-up/sign-in/users process,
Supabase assessment, Substack integration, research-report gating, premium gating, native
LLM with per-tier token caps").
**Authority:** program charter + rulings MNZ-R1..R12. Waves land as separate PRs citing this doc.
**Relationship to prior work:**
- Supersedes the build slices (§5) of `research/SAAS_MVP_PLAN.md` (2026-06-27); inherits its
  licensing posture (§4), cadence contract (§7), non-code gates (§8), and product-truth
  positioning (§9) unchanged — those sections remain law.
- Implements the "missing commercial infrastructure" identified by
  `research/NEURAL_WEB_AUTONOMOUS_MARKETING_LOBE_GRANDMASTER_PLAN_FOR_FABLE.md`
  (billing, entitlement, subscription-state, free-to-paid journey). Tier design aligns with its
  product hierarchy: public intelligence → personal workspace → paid desk.
- Checked against `research/DO_NOT_REBUILD.md` (no conflicts) and `docs/ACTIVE_BUILD_MAP.md`
  (no open-PR collisions as of 2026-07-18).

---

## 0. TL;DR

Ship a paywall as an **additive serving-tier program** on infrastructure that mostly already
exists: Supabase auth is live on all 285 pages (email+Google, cross-subdomain cookie SSO),
macro-api (FastAPI) already verifies Supabase JWTs (`require_user`), Caddy already routes every
HTML request through a gate check, and `/api/ask` + `/api/ask/stream` already exist as the seed
of the native LLM. What is net-new: a **Stripe billing spine** (2 paid tiers + trial +
Customer Portal + Entitlements), a **fail-closed premium gate** over HTML *and* JSON,
a **Plans page**, a **Substack→entitlement bridge** keyed on verified email, and a
**tiered, token-metered Mastermind Chat** (Haiku/Sonnet/Opus by tier).

**Verdict on Supabase: KEEP, upgrade to Pro ($25/mo).** Migration to Clerk/Auth0 would rewire
285 pages for zero user-visible gain; the real gaps (production SMTP, email verification,
mainland-China reachability) are fixed by config + a Caddy auth proxy, not by switching vendors.

**Three hard blockers before anything is gated** (W1): the GitHub Pages mirror serves the full
site publicly (from `daily.yml`/`weekly.yml`, not just `pages.yml`) and must be stubbed; email
verification is currently OFF (Substack matching and billing identity both require verified
emails); and the Terminal subdomain serves data on the shared SSO cookie with no entitlement
check — a day-one paywall bypass unless closed first.

Build: 7 waves + a parallel operator legal track. Rough order: harden → billing → wall →
plans page → (Substack ∥ chat) → CN payments.

---

## 1. Current state (verified in-repo 2026-07-18)

| Layer | State | Key facts |
|---|---|---|
| Serving | ✅ live | EdgeOne CDN → Caddy (VPS) → `site.served/` static + macro-api :8000. HTML already routed through `/api/gate/check` (IP/country gate, fail-open). HTML edge-cached 60s. |
| Auth | ✅ live | Supabase project `fsldfzlxyavsuwqbceod`; email+password (confirmation **OFF**), Google OAuth, PKCE; ~390-day chunked cookie scoped to `.mastermind-x.com` (SSO with Terminal); self-hosted supabase-js (GFW-safe). `require_user` in `app/main.py:439` verifies bearer tokens server-side with no secret. |
| Per-user state | ✅ live | `watchlists` table + RLS; analytics events stamped with `user_id` (`_mm_verify_uid_cached`, `app/main.py:203`). |
| Account UI | ⚠ partial | `templates/account.js` already renders `plan_label || 'Free'` and a **disabled "Upgrade to Pro" card** — but it calls `https://app.mastermind-x.com/api/account*` (Terminal repo, not this one). |
| Billing | ❌ none | No Stripe code, no entitlement table anywhere. |
| Gating | ⚠ wrong kind | `app/gate.py` is IP/country, deliberately fail-open, HTML-only. 3,570 JSON artifacts under `site/` are served ungated. |
| LLM | ⚠ seed | `/api/ask` + `/api/ask/stream` behind `require_user` with **global** env-var quotas (`ASK_BRAIN_HOURLY_QUOTA=10`, `ASK_BRAIN_DAILY_QUOTA=200`) — not tier-aware. `lib/ai_costs.py` ledger exists (internal). |
| Leaks | 🔴 three | (1) GitHub Pages mirror `chriswong6031-creator.github.io/macro` republishes the **entire site** on every nightly (deploy steps live in `daily.yml`/`weekly.yml`), ungated, and its origin is in the Supabase redirect allow-list. (2) `firewall-cloudflare.sh` grey-cloud escape hatch leaves :80/:443 open to the whole internet — direct hits still pass through Caddy so a cookie-based entitlement gate holds, but the `EO-*` geo/IP headers both gates trust are fully attacker-controlled on that path (spoofable) until Caddy strips them on non-CDN connections. (3) Terminal `app.mastermind-x.com` serves `/data/*` straight from disk with no gate and honors the shared SSO cookie with no entitlement concept. |
| Admin | ✅ live | admin console reads `auth.users` via Management-API PAT (`admin/users.py`) — subscriber views are one panel away. |

The load-bearing conclusion: **the paywall is an extension of macro-api + Caddy + Supabase,
not a new system.** Every wave below is measured against that.

---

## 2. Product & tier design

### 2.1 Tiers (recommended; names/prices are operator placeholders — MNZ-OD1)

| | **Free** (signed-in) | **Insider** — paid tier 1 | **Pro** — paid tier 2 |
|---|---|---|---|
| Price (placeholder) | $0 | ~$19.99/mo · ~$199/yr | ~$49.99/mo · ~$499/yr |
| Dashboards | Glance tier: `macro.html`, `index.html`, news pages, `methodology.html`, one sample report | All markets, all desks, heatmaps, baskets, sector central, options/flow, smart money, cycle, vector… | Everything in Insider |
| Research reports | 1 sample (`report_second_act.html` teaser or one full report) | All `report_*.html`, `reports.html`, `state_of_themes.html`, `intelligence_hub.html` | Everything |
| Committee / NW / aibrief / track record | ✕ (teaser) | ✓ | ✓ |
| Mastermind Chat | ~10 msgs/mo on **Haiku 4.5** (taste) | **Sonnet 4.6**, 2M tokens/mo | **Opus 4.8**, 2M tokens/mo + Sonnet 4.6, 5M tokens/mo |
| Watchlist sync | ✓ (existing) | ✓ | ✓ |
| Trial | — | 7-day card-required trial | 7-day card-required trial |

Design rationale:
- **Two paid tiers** (operator's lean) but every entitlement is a **feature flag**, so collapsing
  to one paid tier (marketing-lobe recommendation for launch) is a Stripe-dashboard change, not
  a code change. The tier *split* is: Insider = the full site; Pro = the full site **plus the
  frontier chat**. This is the cleanest honest split we have — the site content is one coherent
  product, and Opus-grade chat is a real marginal cost that justifies a real price step.
- **Free tier = glance, paid = depth** matches the design doctrine (glance tier answers
  "so what do I do"; depth desks are where the moat is) and matches SAAS_MVP_PLAN §9
  (the honest product is regime/risk context, and the free glance page IS that hook).
- Chat cost at list prices (Opus 4.8 $5/$25 per MTok): full 2M Pro usage at a 75/25 in/out
  split is **$20 raw**, and the honest worst case is higher — cold-cache first turns, tool-call
  turns re-reading context, output-heavy sessions can push a maxed-out Pro user to ~$25–35/mo.
  The $49 price still clears it, but the margin depends on prompt-cache hit rate — so the
  initial Opus budget ships at **1.5M/mo** (config, MNZ-R12) and moves up once measured cache
  economics land in the admin cost panel. Insider Sonnet 2M ≈ $12–18 worst case. Budgets are
  per-calendar-month, no rollover.

### 2.2 Free/paid split by page family (from the full content census)

Path-gateable static HTML everywhere; the JSON each page fetches inherits the page family's tier
(§3.3). Recommended split (operator can move rows — the manifest makes this a one-line change):

- **Free:** `index.html`, `macro.html` (+ its regime timeline JSON — the hook), `news.html`,
  `china_news.html`, `methodology.html`, `coming-soon`, one designated sample report, `plans.html`.
- **Insider+:** everything else — us_stocks/lab, sector central + cycles + heatmaps, baskets (all
  markets), china/hk/canada/intl families, options & flow (gex, screener, flow desk, darkpool),
  leader radar, commodities/forex/bonds/vector, cycle/markets/measurement, reports + hub +
  state_of_themes, committee, aibrief, ai_desk, us_track_record, smart money/etfs/congress,
  policy watch, signal/tech lab, alerts, fund dossiers, allocation pages, strategies.
- **Never public:** admin/status/QA pages (already unlisted; add to the deny-manifest anyway).

### 2.3 Trial

Card-required 7-day trial via Stripe Checkout `subscription_data.trial_period_days: 7`
(card-required converts 2–3× better than cardless; the generous Free tier already serves the
no-card audience). Dunning handled by Stripe defaults + Customer Portal.

---

## 3. Architecture

### 3.1 Identity & auth — Supabase verdict and hardening

**MNZ-R7: stay on Supabase; upgrade to Pro ($25/mo).** Grounds: 100k MAU included (≥20× our
horizon), already wired into every page + Terminal SSO, alternatives cost more (Clerk ~$400/mo
at 5k MAU) and solve nothing we lack. Revisit only at ≥100k MAU or when an uptime SLA is needed
(Supabase has none below Enterprise; 2025-26 incident history is real — mitigate with a
grace-period: an unreachable auth endpoint must degrade paid users to *cached* entitlement,
never lock them out; see MNZ-R1 carve-out).

Hardening (W1, all config-or-small-code):
1. **Custom SMTP** (Resend/SES) — the built-in 2-emails/hour sender is dev-only and blocks any
   real signup flow.
2. **Email verification ON.** Currently OFF. Billing identity and Substack matching both bind
   to email; unverified email + paid entitlements = account-takeover-by-typo. Existing accounts
   grandfathered; Substack linking additionally requires a verified email (MNZ-R4).
3. **Attack protection** (rate limiting + Turnstile CAPTCHA) — anon key is public by design.
4. **CN reachability:** Supabase custom-domain add-on ($10/mo) *or* a Caddy reverse-proxy route
   `auth.mastermind-x.com/* → fsldfzlxyavsuwqbceod.supabase.co` on our ICP-reachable VPS, with
   `config.yml → watchlist.supabase.url` re-pointed. The Caddy route is $0 and keeps every
   hostname we control; prefer it, verify GoTrue behaves behind a proxy host, fall back to the
   paid custom domain if not.
5. Fix the Terminal-standalone `account.js` jsdelivr SDK load (GFW-dead) → self-hosted copy.

### 3.2 Billing spine (Stripe)

Object model (2 products × 2 prices + features via **Stripe Entitlements**, GA):

```
Product "Insider"  → features: site_full
Product "Pro"      → features: site_full, chat_opus
Prices: insider_monthly / insider_annual / pro_monthly / pro_annual (+ CN one-time annual, §3.6)
```

Flow: `plans.html` → `POST /api/billing/checkout` (macro-api creates a Checkout Session,
`customer_email` prefilled from the Supabase session, `client_reference_id = user_id`) →
Stripe-hosted Checkout (+ Stripe Tax enabled) → webhook `POST /api/billing/webhook`
(signature-verified, idempotent on `event.id`) consumes:
`checkout.session.completed`, `customer.subscription.created/updated/deleted`,
`invoice.payment_failed/succeeded`, and — primary — 
`entitlements.active_entitlement_summary.updated` → upsert into Supabase:

```sql
create table user_entitlements (
  user_id uuid primary key references auth.users(id),
  stripe_customer_id text unique,
  tier text not null default 'free',          -- 'free' | 'insider' | 'pro'
  features text[] not null default '{}',      -- mirror of Stripe active entitlements
  status text not null default 'none',        -- 'active'|'trialing'|'past_due'|'canceled'|'none'
  source text not null default 'stripe',      -- 'stripe' | 'substack' | 'comp'
  current_period_end timestamptz,
  updated_at timestamptz default now()
);
-- RLS: user can SELECT own row; ONLY service-role writes (webhook/reconciler/substack sync).
```

Hot path never calls Stripe: macro-api reads this table (in-process cache, ~60s TTL).
Reconciler: nightly + on-webhook-failure `GET /v1/entitlements/active_entitlements` re-sync.
Self-serve upgrades/downgrades/cancel = Stripe **Customer Portal** (`/api/billing/portal`).
**Negative propagation is first-class:** `customer.subscription.updated/deleted`,
`charge.dispute.created`, and `charge.refunded` all bust the entitlement cache for that
user_id immediately (max premium persistence after revocation ≈ one cache TTL, not 24h — the
MNZ-R1 grace applies only to *store outages*, and never to rows in `past_due`/`canceled`).
Upgrade mid-session (Insider→Pro) rides the same cache-bust, so Pro chat routing applies within
seconds of payment. **Account deletion** (`/api/account/delete` flow) cancels the Stripe
subscription first, then removes the user; the `user_entitlements` FK cascades — no orphaned
live subscriptions billing deleted accounts.
Secrets live in `/etc/macro-api.env` (existing pattern); never in the repo.
Fees to expect: 2.9%+30¢ card + 0.7% Billing + 0.5% Tax where registered.

`/api/me` grows: `{tier, features, status, current_period_end, chat_budget: {...}}` — and the
existing `account.js` "Upgrade to Pro" dead card comes alive pointed at `plans.html`
(macro-api grows its own `/api/account` so the macro site stops depending on the Terminal repo
for plan display — MNZ-OD4 covers Terminal parity).

### 3.3 The wall — fail-closed premium gate over HTML and JSON

**MNZ-R1: the premium gate is fail-CLOSED** — the exact inverse of the site gate. `app/gate.py`
(IP/country, fail-open) is untouched and stays first; a new `app/paywall.py` runs behind it.
CSP-R1 ("never fail dark") still governs the *free* tier and overall site availability; a paid
575-page never silently degrades to public on an error — it degrades to the paywall interstitial.
Carve-out: if the **entitlement store itself** is unreachable, users with a *recently-cached*
positive entitlement stay in (grace ≤ 24h); anonymous/unknown users see the interstitial.

Mechanism (opus red-team pass 2026-07-18 folded in — findings 1/2/4/5/9/12/18):
1. **Tier manifest at build time — two halves, honestly separated.** HTML: `write_page()`
   (`lib/pages.py`, the genuine shared bottleneck across ~83 builders) grows a `tier=` kwarg;
   call sites annotated once. JSON: the 3,570 artifacts do **NOT** flow through `write_page` —
   their tiers come from a **curated prefix table** (`config/gate_prefixes.yml`: `prophet/`,
   `neuralwebdata/`, `basketdata/`, `factordata/`, `flowdata/`, `funddata/`,
   `master_brief.json`, …) merged into `site/gate_manifest.json` at build. A CI guard fails
   when a JSON prefix under `site/` is absent from the table (**unmapped = fail the build**,
   not fail-open at serve time) — new engines cannot silently ship premium JSON ungated.
   Watchlist/auth/analytics endpoints are explicitly listed `free`. Pages also get
   `<html data-tier>` via `_seo_head` for client chrome (lock badges), but **enforcement is
   server-side only** (MNZ-R6).
2. **Caddy** routes are widened: today only `/` + `*.html` consult the gate; premium-prefix JSON
   paths (matcher snippet generated from the manifest, committed in-repo — macro-update
   auto-reinstalls the Caddyfile) route through the same check. Free-path JSON stays on the
   fast static path. **The premium matcher gets its own `handle_errors`:** today's block serves
   the requested file with a forced 200 when macro-api is down (correct for the free tier /
   IP gate, catastrophic for premium) — on premium paths, gate-upstream failure serves the
   static interstitial stub, never the file. Additionally, Caddy **strips `EO-*`/`CF-*`/
   `True-Client-IP` headers on connections not from EdgeOne source ranges** — the grey-cloud
   escape hatch leaves the origin open to direct hits, and a direct client must not be able to
   spoof geo/IP headers that either gate trusts.
3. **macro-api check — a distinct fail-closed code path** (`app/paywall.py`), NOT an extension
   inheriting `/api/gate/check`'s 204-allow defaults: module-import failure, manifest-load
   failure, or any unhandled exception on a premium path ⇒ deny (interstitial), while the IP
   gate keeps its fail-open defaults. Flow: IP gate allows → manifest lookup; `free` → 204;
   premium → parse the Supabase session cookie, **verify the access token fresh** (the existing
   10-min `_mm_verify_uid_cached` cache is fine for analytics, too stale for a paywall — the
   paywall verifies token validity with a short negative-path cache ≤60s), resolve tier from
   the `user_entitlements` in-process cache (~60s); entitled → 204 + `Cache-Control: private,
   no-store`; not entitled → 403 + bilingual **paywall interstitial** (page title + blurred
   hero + tier table CTA; `coming-soon.html` self-contained pattern); JSON callers get
   `403 {"locked": true, "tier": "insider"}` so panels render an explicit lock (MNZ-R6).
   The composite worst-case staleness window (token TTL + caches) is documented and bounded
   ≤ ~2 min in the negative direction.
4. **Premium `/api/*` endpoints are a second enforcement surface.** Caddy proxies `/api/*`
   before the gate matcher, so the manifest route cannot cover them — premium API endpoints
   (`/api/ask*`, any entitled data feeds) enforce tier via an **in-process FastAPI dependency**
   reading the same entitlement cache. Two mechanisms, one authority table, both mandatory.
5. **EdgeOne:** cache rule — bypass cache for premium paths on **both schemes** (the cache key
   ignores scheme; the 2026-07-11 `:80→:443` poisoning incident class applies — `no-store` from
   origin + explicit bypass rule + the `:80` mirror block covered; `Vary: Cookie` is NOT
   trusted). Also enable the real-client-IP header rule while in the console (known gap).
6. **Leak closure (W1 blockers):** the mirror deploys live in **`daily.yml` / `weekly.yml`
   deploy-pages steps** (not just `pages.yml`) — those steps switch to deploying the stub (or
   free subset, MNZ-OD3); the Pages origin is **removed from Supabase redirect URLs**
   (`ACCOUNTS_SETUP.md` allow-list) so auth can no longer round-trip through it; premium pages
   `noindex` re-checked; sitemap regenerated free-only (SEO impact: see MNZ-OD7).

Perf note: the gate adds one localhost round-trip per premium HTML/JSON request; the IP gate
already pays this on HTML today and renders fine within budget. JSON fan-out pages (some fetch
10–20 artifacts) ride the same in-process manifest + entitlement cache — no per-request DB hit.

### 3.4 Substack bridge

Goal: a paying Substack subscriber gets matching Mastermind access for as long as their
Substack sub is paid ("matched by email, mirrored in time").

Mechanism ladder (from the 2026-07 research pass, ranked; take the first that works):
1. **Stripe-direct (gold, test first — 1 hour):** Substack runs on Stripe Connect against the
   publisher's own Stripe account. If the operator's Stripe dashboard shows Substack-created
   `Customers`/`Subscriptions`, we read them with our own key: nightly
   `subscriptions.list(status=active)` → upsert; plus `customer.subscription.updated/deleted`
   webhooks for real-time revoke. Fields: `customer.email`, `status`, `current_period_end`,
   `price.interval`. Zero ToS risk.
2. **Official Substack Publisher API** (`publisher-api.substack.com/v1`, key from the
   publication dashboard): `get_subscriber(email)` on-demand + nightly sweep of linked emails.
   Response schema is undocumented — probe before committing.
3. **CSV export + email-parse fallback:** weekly dashboard export (`email,is_paid,expiry,…`)
   imported via an admin upload panel; Substack's "new paid subscriber" notification emails
   parsed for day-to-day freshness.

```sql
create table substack_entitlements (
  email text primary key,          -- lowercased
  is_paid boolean, subscription_type text, paid_through timestamptz,
  status text, source text, last_verified_at timestamptz
);
```

Linking flow: signed-in user → Account → "Link Substack" → **fresh OTP challenge to that email,
bound to this specific link request** — for ALL accounts, not just pre-confirmation ones
(a stale `email_confirmed` flag is not sufficient: confirmation was OFF historically, so
attacker-registered accounts on victim emails exist by construction; MNZ-R4) → OTP pass +
lookup in `substack_entitlements` (miss → live check via mechanism 1/2) + entitlement write
happen in **one transaction** (no verify→relink TOCTOU) → hit ⇒ `user_entitlements` row with
`source='substack'`, tier = **Insider** (operator may map annual/founding → Pro, MNZ-OD2),
`current_period_end = paid_through`. Nightly sync extends or expires, and re-checks that the
linked email still belongs to the account (email changes unlink). Stripe-sourced rows always
win over Substack-sourced rows for the same user (no double-grant; a user who upgrades to Pro
on Stripe keeps Pro).

### 3.5 Mastermind Chat — the native LLM, tiered and token-metered

Build on the existing `/api/ask` seed, not beside it.

- **Models by tier** (per-tier routing in macro-api): Free → `claude-haiku-4-5` (message-capped);
  Insider → `claude-sonnet-4-6`; Pro → `claude-opus-4-8` with automatic Sonnet fallback when
  the Opus budget is spent. Model IDs current as of 2026-07 (claude-api skill).
- **Metering:** `user_token_usage (user_id, period_start, model_class, tokens_prompt,
  tokens_completion, hard_limit)` keyed by `date_trunc('month', now())` — auto-shards monthly,
  no reset cron. Pre-call: 402 + upgrade CTA when spent; pass
  `max_tokens = min(request, remaining)` so a stream cannot overrun. Post-call: update from
  `response.usage` (never estimate); `cache_read_input_tokens` counted at 10% weight.
  90% threshold → soft-warning header → UI meter turns amber. Direct Anthropic SDK calls from
  FastAPI (no LiteLLM sidecar at this scale — revisit if multi-provider routing appears).
  Every call also appends to the existing `lib/ai_costs.py` ledger (admin cost hub joins free).
- **Streaming:** SSE (the `/api/ask/stream` shape), `thinking: {type:"adaptive"}`, prompt-cache
  the stable system prompt + nightly context bundle (`cache_control` breakpoint after the
  context block; per-user question after it) — this is what makes Opus-tier serving cheap.
- **Tier is re-resolved server-side on every chat call** (never from anything the client sends
  or from a prior `/api/me` response), and the chat's **retrieval tools run at the user's tier
  against the same gate manifest as the wall, with no service-role reads in the chat path** —
  a Free user cannot prompt-inject their way to Insider JSON content. This is a W6 acceptance
  test, not an assumption (the current `ask_brain` read-tools do not consult any manifest yet).
  **Interim rule: until W6 lands, the existing `/api/ask*` endpoints are feature-flagged off or
  tier-gated in W2** — they must not remain the least-protected, most-expensive surface while
  billing exists.
- **Epistemics (MNZ-R5, restating house law):** the chat is a **read surface over calibrated
  artifacts** — it retrieves and explains what the engines already computed (NW keys, board
  states, report text, receipts with links), it never originates signals, scores, or
  escalations, and it answers "what does the dashboard say and why" — not "what should I buy".
  System prompt carries the same disclaimer surface as the site. Killed-adjacent designs
  (LLM-originated escalation, numeric confidence) are already FORBIDDEN in the registry.
- **Surface:** `chat.html` (Pro/Insider) + a compact dialog launcher in the nav; budget meter,
  bilingual, receipts as links into the site. Free tier sees the surface with 10 Haiku
  messages/mo — the taste that sells the tier.

### 3.6 China reachability & payments

- Reachability: §3.1 item 4 (auth proxy) + everything else is already same-origin/GFW-safe.
- Payments: **WeChat Pay has no recurring; Stripe Alipay recurring is invite-only.** Pattern:
  CN users get an **annual one-time price** payable by Alipay/WeChat via Checkout; webhook
  writes `user_entitlements` with `current_period_end = +365d`, `source='stripe'`; T-30/T-7
  renewal emails link a fresh Checkout session. Detect via Checkout locale/payment-method,
  not IP guessing. (Merchant-of-record alternatives like Paddle deferred — MNZ-OD5.)

---

## 4. Rulings (MNZ-R1..R12)

| # | Ruling |
|---|---|
| MNZ-R1 | Premium gate is **fail-closed** at every layer — `app/paywall.py` is a distinct code path whose exception/unavailable default is deny, and the premium Caddy matcher's `handle_errors` serves the interstitial, never the file (today's forced-200 handler stays free-tier-only). Carve-out: **entitlement-store outage only** honors cached positive entitlements ≤24h — never rows in `past_due`/`canceled`, and never auth-token failures. CSP-R1 continues to govern free-tier availability. |
| MNZ-R2 | **No content is gated until** (a) the **`daily.yml`/`weekly.yml` deploy-pages steps** (the real mirror publishers, not just `pages.yml`) ship the stub, (b) the Pages origin is removed from Supabase redirect URLs, and (c) EdgeOne premium-path cache-bypass rules are verified live on both schemes. W1 gates W3. |
| MNZ-R3 | `user_entitlements` is the **single source of authority** for access; written only by the Stripe webhook/reconciler, the Substack sync, and operator comps via admin. Nothing else writes it; LLMs never touch it. |
| MNZ-R4 | Substack matching binds to **verified email only**. No verification, no link — regardless of what the entitlement table says about that address. |
| MNZ-R5 | Mastermind Chat is a read/explain surface over calibrated artifacts. It may de-escalate/contextualize; it never originates signals, scores, escalations, or numeric confidence (restates CLAUDE.md §Epistemics + TI-R1/CHF-R14 family). |
| MNZ-R6 | Locked content is **explicitly locked, never silently absent** (no-silent-caps law applied to the paywall): JSON 403s carry `{"locked":true,tier}`, panels render a lock + CTA. Client `data-tier` is chrome; enforcement is server-side only. |
| MNZ-R7 | Stay on Supabase; Pro plan. Re-open only at ≥100k MAU or SLA requirement. |
| MNZ-R8 | Tier assignments live in the build-time manifest (`write_page(tier=…)` → `gate_manifest.json`); moving a page between tiers is a manifest edit, never ad-hoc Caddy/CDN rules. |
| MNZ-R9 | Trials are card-required, 7 days, Stripe-native. No hand-rolled trial state. |
| MNZ-R10 | Chat budgets are enforced pre-call (`max_tokens` capped by remainder) and settled from `response.usage`; client-reported counts are never trusted. |
| MNZ-R11 | Stripe > Substack precedence on conflicting entitlements for the same user; entitlement `source` is always recorded. |
| MNZ-R12 | All prices/quotas ship as config (env/`config.yml`), not literals — repricing is an ops change, not a PR. |

---

## 5. Waves

Each wave = one PR-sized lane (or 2 small PRs), sonnet-built, opus-reviewed, same-day merged.
Estimates assume the SAAS_MVP_PLAN calibration (verification against a 206k-LOC repo dominates).

| Wave | Scope | Acceptance | Est |
|---|---|---|---|
| **W1 — Foundation hardening** (blocker wave) | Stub the mirror **in `daily.yml`/`weekly.yml` deploy-pages steps** (marketing page or free-subset — MNZ-OD3) + remove the Pages origin from Supabase redirect URLs; Supabase → Pro + custom SMTP + email confirmation ON + CAPTCHA; Caddy auth-proxy route for CN + config repoint; Caddy strips `EO-*`/`CF-*`/`True-Client-IP` on non-EdgeOne connections; **interim tier-gate or feature-flag on `/api/ask*`**; **Terminal hole closed**: `app.mastermind-x.com` `/data/*` + premium routes firewalled or entitlement-checked (shared cookie must not unlock Terminal data the macro wall would refuse — the Terminal-repo lane is a hard dependency, not an option); fix Terminal account.js jsdelivr load + schedule its implicit-flow → PKCE fix; EdgeOne console: premium cache-bypass rule groups (both schemes) + real-IP header (ops checklist doc). | Mirror no longer serves premium HTML; Pages origin absent from redirect allow-list; new signup receives verification email via custom SMTP; auth works via proxied hostname from a CN vantage (or fallback decision recorded); direct-origin request with forged `EO-Client-IPCountry` does not alter gate behavior; Terminal `/data/*` refuses an unentitled session. | ~400–600k tok, 2 sessions + ops |
| **W2 — Billing spine** | Stripe products/prices/features (scripted via API, idempotent); `app/billing.py` (checkout, webhook, portal, reconciler); `user_entitlements` + RLS migration; `/api/me` + `/api/account` on macro-api; admin Subscribers panel (join into existing users panel); Stripe Tax on. | Test-mode checkout → webhook → row appears → `/api/me` reflects tier; portal cancel → row downgrades; replay/idempotency test green. | ~400–700k, 1–2 sessions |
| **W3 — The wall** | `write_page(tier=…)` HTML sweep + curated `config/gate_prefixes.yml` for JSON + merged `gate_manifest.json` + CI unmapped-prefix guard; `app/paywall.py` distinct fail-closed path (+ store-outage grace); Caddy premium routing snippet incl. premium-scoped `handle_errors` → interstitial; FastAPI entitlement dependency on premium `/api/*`; bilingual paywall interstitial; lock-state JSON contract + minimal client lock chrome; sitemap/noindex free-only (status code per MNZ-OD7). | Signed-out fetch of premium HTML **and** premium JSON → interstitial/lock JSON; free pages byte-identical + still edge-cached; entitled user passes; **macro-api-down drill: premium returns interstitial, not content**; **paywall-module-import-failure drill: same**; **scheme-crossed CDN poisoning probe** (`http://` fetch must not prime the `https://` cache) on 3 premium paths; unmapped-JSON CI guard red on a synthetic new prefix. | ~500–800k, 2 sessions |
| **W4 — Plans page + account UX** | `plans.html` (doctrine pass: glance-tier plain words, bilingual, glass aesthetic, tier table, trial CTA, FAQ incl. disclaimer surface); nav + account-modal wiring (`account.js` upgrade card live); locked-panel CTAs; upgrade nudges. | Full journey clicks end-to-end in test mode: locked page → plans → checkout → unlocked on return. Design-doctrine review passes (banned-vocab lint). | ~300–500k, 1 session |
| **W5 — Substack bridge** | Step 0 Stripe-account probe (operator, 1h, decides mechanism); sync lane (nightly on VPS cron, NOT on the render path); `substack_entitlements` + link-flow UI + OTP re-verify; admin panel + CSV-upload fallback. | A real paid-subscriber email links and unlocks Insider; lapse in source revokes on next sync; unverified email refused. | ~300–600k, 1–2 sessions |
| **W6 — Mastermind Chat** | `/api/ask` v2: tier routing (Haiku/Sonnet/Opus), `user_token_usage` metering per MNZ-R10, prompt-cached context bundle, SSE; retrieval tools made tier-aware (gate manifest consulted; no service-role in the chat path); `chat.html` + nav dialog (budget meter, receipts, bilingual); ai_costs join + admin chat-cost panel; abuse rails (per-msg max_tokens, concurrency 1/user). | Budget exhaustion → 402 + CTA mid-month; usage row matches `response.usage` sums; Opus→Sonnet fallback fires at cap; cache-read verified >0 on second message; **exfiltration test: Free-tier chat cannot surface Insider-gated JSON content under adversarial prompting**. | ~500–800k, 2 sessions |
| **W7 — CN payments + polish** | Annual one-time Alipay/WeChat price + webhook path; renewal T-30/T-7 emails; zh plans/paywall copy audit; analytics funnels (plans views → checkout → paid) on the first-party beacon. | Test Alipay flow provisions 365d; renewal email fires in staging clock. | ~200–400k, 1 session |
| **W-LEGAL** (parallel, operator, non-code) | SAAS_MVP_PLAN §8 executed: vendor redistribution emails (Polygon/Tushare), securities-disclaimer + ToS/privacy review, business entity for Stripe live-mode, tax registrations. | **Gates Stripe live-mode**, not the build — all waves run in test mode until cleared. | $ + days, no tokens |

Order: W1 → W2 → W3 → W4 → (W5 ∥ W6) → W7. W-LEGAL starts day one.
Program total ≈ **2.6–4.3M tokens, 9–12 sessions**, infra +$25–40/mo (Supabase Pro, SMTP, GeoIP
unchanged) + Stripe percentages + chat API spend (bounded by tier budgets ≈ cost-positive).

---

## 6. Risk register

| Risk | Sev | Mitigation |
|---|---|---|
| Mirror or CDN cache leaks premium content post-gate | HIGH | MNZ-R2 blocker ordering (daily/weekly deploy steps + redirect allow-list named explicitly); W3 acceptance includes cold-cache AND scheme-crossed CDN probes |
| Terminal shared-cookie hole (premium data on sibling subdomain, no entitlement check) | HIGH | W1 closes it (firewall or entitlement check on `/data/*` + app routes) before anything is gated; implicit-flow fixation risk on `account.js` fixed before Terminal joins a paid tier |
| Webhook loss → stale entitlements (paid user locked out) | HIGH | Idempotent webhook + nightly reconciler + on-403-with-active-cookie re-check path; support "refresh my access" button calling reconciler for self |
| Revocation lag (cancel/downgrade/chargeback keeps premium open across devices) | MED | Negative-path cache-bust on `subscription.updated/deleted` + `charge.dispute.created` + `charge.refunded`; composite staleness bounded ≤ ~2 min; grace never applies to `past_due`/`canceled` |
| Supabase outage locks out paying users | MED | MNZ-R1 grace cache (24h); entitlement cache is in-process at origin, not per-request Supabase |
| Substack fields unavailable (destination-charge model, no Stripe visibility, undocumented API) | MED | Mechanism ladder §3.4; CSV/email-parse floor always works; W5 starts with the 1-hour probe before any code |
| Chat cost blowout | MED | Hard per-tier budgets, pre-call cap, Opus→Sonnet fallback, admin cost panel day-one; prices config (MNZ-R12) |
| Prompt-injection against chat (exfiltrate premium JSON to free users) | MED | Chat runs at the *user's* tier for retrieval — the tool layer enforces the same manifest as the wall; no service-role reads in the chat path |
| Regulatory (investment-advice surface) | MED | W-LEGAL gates live-mode; chat + reports keep research/education framing per SAAS_MVP_PLAN §9 |
| EdgeOne edge-function limitations (if origin-check latency ever matters) | LOW | Origin check is localhost; edge JWT verification kept as a *later* optimization, not a dependency |
| Render-budget impact | NONE | All gating is serve-time; build adds only the manifest write (~seconds). Substack sync + billing live on the VPS, off the render path |

---

## 7. Open operator decisions (MNZ-OD)

1. **OD1 — Pricing & names.** $19.99/$49.99 are placeholders; decide before W4 copy.
2. **OD2 — Substack tier mapping.** Default: any paid Substack → Insider. Map founding/annual → Pro?
3. **OD3 — Mirror fate.** Pure marketing stub vs free-tier subset on Pages (subset = SEO retained, more moving parts).
4. **OD4 — Terminal (app.mastermind-x.com) tier placement.** Whether Terminal is an Insider or Pro feature is open; that it must be *gated* is NOT open — W1 closes the shared-cookie hole regardless (see W1 scope), and the Terminal's implicit-flow → PKCE fix is a prerequisite of bundling it into a paid tier.
5. **OD5 — Merchant of record** (Paddle/LemonSqueezy) instead of Stripe if W-LEGAL tax burden proves heavy. Default: Stripe + Stripe Tax.
6. **OD6 — Trial without card** as a later experiment (marketing-lobe "value-moment" preview idea) once baseline conversion is measured.
7. **OD7 — Paywall HTTP status vs SEO.** The site was deliberately opened to indexing (robots + sitemap shipped); walling ~90% of pages behind hard 403s de-indexes them and burns existing backlinks. Options: hard 403 (clean, loses ranking) vs 200 soft-paywall with structured-data preview (Google flexible-sampling pattern, retains ranking, more build work). Default recommendation: 403 at W3, revisit with real traffic data.

---

## 8. Research appendix (2026-07-18 pass; details in agent transcripts)

- **Substack:** no OAuth/"sign in with Substack"; no webhooks/Zapier; official Publisher API
  exists (key from dashboard) with `get_subscriber(email)` but undocumented response schema;
  CSV export includes `email,is_paid,expiry,type,interval`; Substack runs Stripe **Connect** —
  whether subscriptions are visible in the publisher's own Stripe account (direct-charge) vs
  platform-held (destination-charge) is empirically testable in 1h and decides the mechanism.
- **Stripe 2026:** Checkout hosted + Customer Portal + **Entitlements API GA**
  (`entitlements.active_entitlement_summary.updated` is the canonical sync event); Billing fee
  0.7%; Tax 0.5%; trials via `trial_period_days`; plain webhook→Postgres preferred over
  stripe-sync-engine at this scale. Alipay recurring = invite-only; WeChat Pay = no recurring.
- **Supabase 2026:** Free pauses after 7d idle + 2 emails/h built-in SMTP (dev-only) → Pro
  $25/mo, 100k MAU, no pausing; custom domain +$10/mo; GFW: `*.supabase.co` unreliable from
  mainland — proxy or custom domain; reliability incidents ongoing, no SLA below Enterprise.
- **Claude API (via claude-api skill, cached 2026-06):** Opus 4.8 `claude-opus-4-8` $5/$25 per
  MTok; Sonnet 4.6 $3/$15; Haiku 4.5 $1/$5; adaptive thinking; prompt caching reads ~0.1×;
  streaming SSE; usage in `response.usage` incl. cache fields.
- **CDN gating:** never cache gated HTML in shared edge cache (`no-store` + explicit bypass;
  `Vary: Cookie` untrustworthy); EdgeOne supports edge functions/remote-auth if origin check
  ever needs to move edgeward.
