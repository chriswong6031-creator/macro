# SaaS MVP build plan — from daily static site to a live, paywalled web app

**Status:** plan (2026-06-27). Supersedes nothing — extends `research/LIVE_DATA_ARCHITECTURE.md`
(the live-overlay design) and the removed-but-recoverable `MIGRATION.md` (the single-box
deployment runbook, git ref `819b4c22e9`). Those cover *making the dashboard live*; this covers
*turning it into a multi-tenant product you sell*.

**TL;DR:** The MVP is an **additive serving tier**, not a rewrite. The ~206k-LOC engine is
*wrapped, not rewritten*; the nightly GitHub Actions batch keeps running unchanged; a new
DigitalOcean box + the **already-wired Supabase auth** + Stripe sit *beside* the existing pipeline
and read its build artifacts. Because the MVP uses **shared global signals** (every subscriber sees
the same computed dashboard) + Supabase for per-user state, we never touch the 77-file
`lib/store.py` seam — which is precisely why **feature development continues in parallel, no freeze
required**. Realistic build: **~3–8M Claude tokens across ~15–30 sessions over ~6–12 weeks** of
human-supervised work. The binding constraints are *not* engineering — they are (1) per-vendor
data-**redistribution** clause verification, (2) securities-law / disclaimer review, and (3) honest
product positioning given the engine's own validated finding that the edge is regime/drawdown
control, not live trade calls.

---

## 1. Scope — what the MVP is, and is not

**Is:** a paywalled **derived-analytics research dashboard**. Subscribers sign up, log in, pick a
tier, and get *your computed* macro regime, conviction, sector/stock signals, allocation books, and
commentary across **US + China/HK** — the existing site, behind auth, with live price ticks and the
intraday fast-leaf overlay on the paid tier.

**Is not (for the MVP):**
- **Not a quote terminal.** You sell *derived analytics* (your regime/signals/marks), not a
  re-stream of raw exchange ticks. This is both the legally-clean posture (§4) and the honest one (§9).
- **Not per-tenant compute.** Signals are **global** — everyone sees the same dashboard. Only
  watchlist / preferences / entitlements are per-user (Supabase, already built). This deliberately
  avoids threading `tenant_id` through `lib/store.py` + ~357 engine files (the single biggest token
  sink and the only refactor that would force a feature freeze).
- **Not an SPA rewrite.** The existing **progressive-enhancement** model (static HTML + `live.js`
  patching live values in) already works. We auth-gate the static pages and keep `live.js`. No
  React/Vue migration of the 285 pages.
- **Not mainland-China-hosted.** DigitalOcean has no China region and is GFW-flaky. The MVP is
  global/HK-reachable; true mainland reachability (ICP / China CDN) is deferred.

**Geographic/data scope:** **US + China/HK included from launch** — China/HK is the differentiator,
and you have *licensed* feeds for it (Tushare), so we are not dropping it. The China/HK tier ships
as **derived analytics over EOD/daily data** (which is what Tushare already is), keeping its
redistribution posture light.

---

## 2. The architecture — additive, wrap-don't-rewrite

```
EXISTING — unchanged, stays on GitHub Actions (free CI):
  daily.yml        ──► builds site/ + data/  ──► commits to main      ◄── you keep shipping here
  live-quotes.yml  ──► quotes.json ──► live-data branch (keyless)      ◄── already live
                                  │
                                  │  the SaaS box git-pulls these artifacts (nightly + on-tick)
                                  ▼
NEW — built alongside in a top-level app/ dir; imports engine, never modifies it:
  DigitalOcean Droplet  (your domain, HTTPS via Caddy/Let's Encrypt)
    ├─ nginx / Caddy : serves the built site/ behind an AUTH GATE (verifies Supabase JWT)
    └─ FastAPI app/  : /api/* wraps existing engine fns + serves data/ + overlay.json,
                       gated by tier (free=EOD, paid=intraday/full)
  Supabase  (ALREADY WIRED — site/auth.js, live project)  : auth (magic link) + per-user
                       state (watchlists, prefs, entitlements) via Row-Level-Security
  Stripe                                                   : subscription → tier claim → gate
```

**Why this shape:** the serving tier and the build pipeline are decoupled by the **artifact
contract** — `data/`, `site/stockdata/*.json`, `site/live/overlay.json`, `masterminds_latest.json`.
The batch produces them; the app reads them. They meet nowhere else.

### The parallel-work contract (answers "can we keep building?")
**Yes — keep building.** The only coordination rule:

> If a feature changes the **shape** of an artifact the app consumes (a `stockdata` JSON field,
> `overlay.json`, `masterminds_latest.json`, or a `data/` group layout), bump its schema/version
> and flag it so the app stays in sync. **Purely additive** changes (new signals, new pages,
> threshold tuning) need zero coordination.

Your existing signal-contract gate (`SCHEMA.json` + `validate_signals.py`) already enforces most of
this discipline. Keep all SaaS work on its own branch(es)/PRs and in a new `app/` directory that
*imports* `engine` but never edits `engine`/`scripts`, and the two streams cannot collide.

---

## 3. What already exists vs what's net-new

| Piece | Status |
|---|---|
| **Auth + per-user state** — `site/auth.js` (magic-link), live Supabase project, `watchlists` table, RLS (`templates/watchlist_supabase.sql`) | ✅ **built** — extend, don't build from scratch |
| **Live price layer** — `live-quotes.yml` (keyless `quotes.json` → `live-data` branch), `site/live.js` (progressive enhancement) | ✅ **built + running** |
| **Fast-leaf overlay** — `engine/live_overlay.py`, `engine/live_quotes.py`, `scripts/build_live_overlay.py` (pure, importable, unit-tested) | ✅ **built**, needs an intraday scheduler |
| **The 285-page dashboard + ~206k-LOC engine** | ✅ **built** — wrapped, not rewritten |
| **Licensed data** — Tushare CN (¥500/yr, EOD), Polygon US (incl. intraday bars + options OI) | ✅ **integrated** |
| **`lib/store.py`** — clean 119-line seam (read/upsert/last_date/status), 77 importers | ✅ — left untouched in MVP (shared-global signals) |
| Web server (FastAPI) + auth-gate middleware | ❌ net-new (small — wraps existing fns) |
| Stripe billing + subscription tiers + entitlement claims | ❌ net-new |
| Entitlement gate (free=EOD / paid=intraday) on `/api` + page rendering | ❌ net-new |
| Intraday scheduler for `build_live_overlay.py` on the box | ❌ net-new (small) |
| DO Droplet + domain + HTTPS + nginx auth gate | ❌ net-new (ops) |
| US real-time feed (Alpaca $99/mo) | ⚠️ optional swap, **not yet integrated** |
| Observability / monitoring / on-call | ❌ net-new |
| ToS / privacy / disclaimers / RIA review | ❌ net-new (legal, §8) |

---

## 4. Data & licensing posture (recalibrated)

**You have licensed feeds — this is NOT the "illegal scrape" wall from the first assessment.** That
concern was about `yfinance`/`akshare` scrapes; you depend on paid Tushare (CN, EOD) + Polygon (US).
The real, narrower question that remains:

> **"Licensed for my own use" ≠ "licensed to redistribute to my paying customers."** Most
> market-data agreements separate internal/display use from third-party redistribution, and for
> **real-time exchange** data the exchanges add per-"professional-subscriber" fees regardless of
> vendor.

**The clean path (matches the product):** serve **derived analytics** (your regime/conviction/
signals), not raw re-streamed exchange quotes. Derived/EOD content carries a far lighter
redistribution posture than live raw ticks. Your richest differentiated data (Tushare A-share
intelligence) is *already* EOD + display-only — the easy tier.

**Pre-launch verification checklist (days, ~$0 — a contract read + one email per vendor):**
- [ ] **Polygon** — does your plan permit displaying derived data / delayed quotes to external paying users? Real-time raw quote redistribution tier + cost?
- [ ] **Alpaca** ($99/mo, if adopted for US real-time) — non-professional vs professional subscriber status; redistribution / external-display terms; SIP exchange fees if re-streaming raw.
- [ ] **Tushare** — commercial redistribution clause for serving its data (even derived) to third parties; per-seat vs per-app; any CN-specific restriction. (Currently A-share EOD; **confirm HK coverage** if HK quotes are promised.)
- [ ] Decide the bright line: **customers see derived signals + delayed/EOD prices on free tier; real-time raw ticks (if any) only where a redistribution license explicitly allows.**

Treat these as launch-gating *checkboxes*, not a blocker that drops China/HK.

---

## 5. Build slices (each single-session-sized, de-risking order)

| # | Slice | Scope | New files (in `app/`) | Claude tokens | Sessions |
|---|---|---|---|---|---|
| 0 | **This plan** | architecture, scope, sequence, gates | `research/SAAS_MVP_PLAN.md` | done | — |
| 1 | **Deploy + auth wall** | DO Droplet, domain, HTTPS, nginx/Caddy serving `site/` behind a Supabase-JWT gate; add origin to Supabase redirect URLs | deploy config, gate middleware | ~150–400k | 1 |
| 2 | **FastAPI `/api` shell** | serve `data/` + `overlay.json`; wrap `live_overlay`/a few engine fns; same JWT gate; git-pull sync of artifacts | `app/main.py`, routers | ~300–700k | 1–2 |
| 3 | **Stripe tiers + entitlements** | Stripe checkout + webhook → `tier` claim in Supabase; entitlement gate on `/api` + page rendering (free=EOD, paid=intraday/full) | `app/billing.py`, webhook, RLS update | ~300–700k | 1–2 |
| 4 | **Intraday scheduler + live tier** | cron `build_live_overlay.py` on the box (session-gated); paid tier gets the fast-leaf overlay + divergence chips live | scheduler unit, systemd | ~300–800k | 1–2 |
| 5 | **(Optional) US real-time** | swap/augment to Alpaca $99/mo for real-time US *if* redistribution clause clears; keep derived-only otherwise | `collectors/alpaca_quotes.py`, route | ~400k–1M | 1–2 |

**MVP total:** **~3–8M tokens / ~15–30 sessions / ~6–12 weeks** human-supervised. (The wide range is
verification + regression loops against a 206k-LOC repo, not feature complexity.) Tokens are the
**cheapest input** here — do not optimize that axis over the legal/licensing/positioning gates.

---

## 6. Hosting topology + cost

| Item | Choice | Cost |
|---|---|---|
| Compute / serving | **DO Droplet** (4 GB / 2 vCPU; runs FastAPI + git-pull + occasional engine calls — heavy nightly stays on GH Actions) | ~$24/mo |
| Users / auth / billing-state | **Supabase** (already wired; Postgres + auth + RLS) — free tier → Pro when needed | $0 → $25/mo |
| Payments | **Stripe** | per-txn % |
| Domain + HTTPS | your registrar + Let's Encrypt | ~$12/yr / $0 |
| US data | existing Polygon; **optional** Alpaca real-time | existing / +$99/mo |
| CN/HK data | existing Tushare (¥500/yr) | existing |

**MVP infra ≈ $25–50/mo** (+$99/mo only if real-time US is turned on). Do **not** stand up a separate
DO Managed Postgres for the MVP — Supabase *is* Postgres and it's already integrated.

---

## 7. Cadence contract (carry the validated design — do not violate it)

From `research/LIVE_DATA_ARCHITECTURE.md`, enforced in `engine/regime.py` (hysteresis) + masterminds
(weekly rebal):
- **Intraday-live (paid tier):** prices, fast leaves (RSI/MACD/MA-distance, %-off-52w-high), the
  per-ticker divergence flag. ~15% of the signal surface.
- **Daily-by-design (all tiers):** regime quad, conviction ranks, theme scores, GTAA allocation —
  hysteresis-gated; **must not** recompute on ticks (whipsaw + transaction-cost). The product
  *flags* when a live move breaches the nightly cone; it does not re-score the slow brain.

Market the live tier as "live prices + fast-leaf timing + divergence alerts," **not** "live
regime/allocation." Misrepresenting the slow brain as intraday is both technically wrong and a
product-honesty problem.

---

## 8. Non-code gates (parallel tracks — start now, they don't consume Claude tokens)

1. **Vendor redistribution clauses** (§4 checklist) — days, ~$0. *Gates the data scope of launch.*
2. **Securities-law / disclaimer surface** — selling TAKE/BLOCK/CUT/REBUY markers + allocation
   weights risks investment-adviser classification (US RIA/Form ADV publisher's-exemption analysis;
   per-jurisdiction for CN/HK/EU). Securities lawyer ~$5–20k one-time; ToS, privacy, liability
   disclaimers, E&O insurance. *Gates taking money.*
3. **Business + payments setup** — entity for Stripe, tax. Days.
4. **Solo-operator reality** — one person cannot run multi-tenant on-call + scraper maintenance +
   support + the build. Decide: stay small/manual at MVP, or plan a hire before scaling past a
   handful of paying users.

---

## 9. Product-truth positioning (load-bearing)

The repo's own FDR-validated findings: momentum dead, anticipation is a *drawdown-control* lever not
return-alpha, base-scanner anti-predictive, single-name direction a coin-flip; the one robust edge is
**regime / drawdown control**. The repo culture explicitly "refuses fabricated precision."

→ The honest, defensible value proposition is a **macro-regime + risk/drawdown-control + research
dashboard** (with China/HK depth as the moat), **not** "live buy/sell signals." Position, price, and
disclaim accordingly. This also reduces the securities-law surface (research/commentary vs
personalized advice).

---

## 10. Open decisions (owner: you)

- Free-tier line: how much EOD content is free vs paywalled?
- Pricing / tiers (e.g., Free EOD · Pro intraday · ?).
- Real-time US now (Alpaca $99/mo) or derived/delayed-only at launch?
- HK quotes: confirm Tushare HK coverage or source separately.
- Public site: move fully behind the wall, or keep a free marketing/sample surface (GitHub Pages)
  in front of the paywalled app?

## 11. Recommended sequence

Slice 1 → 2 → 3 → 4, with §8 legal/licensing tracks running in parallel from day one (they gate
*launch*, not *build*). Turn on Slice 5 only if a redistribution clause clears. **The nightly
GitHub Actions build never changes; feature development never stops.**
