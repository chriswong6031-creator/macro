# Citrini Intelligence Desk — ingestion architecture (recon-grounded build spec)

**Status:** DESIGN (recon complete 2026-07-09 via authenticated Chrome session); build gated on §6 operator items
**Parent:** `research/THEMATIC_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §7 (CITR family). This doc replaces the paper design of §7.2 with the verified transport/auth/data model and the operator's expanded directive: **mirror the Citrindex data into our own backend + build our own UI + analysis layer on top + feed consolidated metrics into Neural Web** (not per-day re-fetch on demand).
**Authorization basis:** operator holds CitriniResearch Institutional ($50k/yr) **with redistribution rights**; ingestion is of the operator's own authorized account for internal synthesis + NW. Runner reads an **operator-placed session** — no credential handling by any agent.

## 1. Recon findings (verified in-session, 2026-07-09)

**Transport — there is no JSON API.** Every data surface is Next.js App Router **React Server Components** (`content-type: text/x-component` flight payloads). All REST/tRPC probes 404 (`/api/trpc`, `/api/portfolios`, `/api/changes` → 404); the only live `/api/*` are `auth/get-session` and `market-status`. Data is delivered inside the route flight and hydrated into client state; "Export to Excel" is a **client-side** generator (no server href), confirming the full dataset is present client-side after render.

**Auth — BetterAuth session cookie.** `/api/auth/get-session` returns `{session, user}`; user carries `stripeCustomerId` (BetterAuth + Stripe billing pattern). The runner needs the **operator-placed session cookie** (or a persisted logged-in browser profile). Sessions expire → need a 401/redirect detector that alerts the operator to re-place, never auto-auth.

**Deploy-versioned flight.** Every asset URL carries a deploy hash (`dpl_B1YStTqsZzpceAAb2zB3aEFKzdxC`). The RSC flight serialization is Next-version/deploy-specific → **direct flight-parsing is brittle across their deploys.** Robust path = **headless render + DOM/client-state extraction**, not raw flight parsing.

**URL map.**
```
/dashboard/charts | /realtime | /macro-trades | /baskets | /baskets-ranking | /watchlists
/dashboard/portfolios                       → portfolio library (2 portfolios)
/dashboard/portfolios/{id}/{tab}            tab ∈ performance | chart | holdings | changes | contribution
  portfolios: ndqEpbNI = "Citrindex" (flagship, inception 2023-05-31, +271% total)
              Ia-Dh2Hg = "26TF26"   (inception 2025-12-17, +26% total)
/dashboard/baskets/{basketId}               (188 baskets in library)
```

**Data model (per portfolio).**
- **Holdings** (dated snapshot): exposure rollup (net/long/short/cash/gross), per-basket allocation + basket-level long/short/net breakdown, per-security weights (incl. options overlays, e.g. `FSLY 07/17/26 C20`, `QQQ P700`).
- **Changes** (date-range): two views — *Weight Changes* (start weight, end weight, weight change, **active change** = discretionary vs drift) per position; *Change Logs*.
- **Contribution** / **Chart** / **Performance** (multi-horizon: 1M/3M/6M/1Y/YTD/MTD/Since-Inception).
- **Intraday Alerts** (on Performance view) — **THIS IS THE TEAM FEED** the operator described as "a private chat updated by their team directly." Each alert: timestamp (intraday), status (COMPLETED), theme/basket, **Message** (free-text rationale — the qualitative thesis, e.g. *"Growthy defense tech has meaningfully outperformed the primes… Rotating into primes for a relative value reversal with tighter downside"*), and an **Actions table**: ticker → action tag (`Initiate Long`, `Decrease Long`, `Increase Short`, `Close`, `Adjust Cash`, …).

**Update cadence (answers the operator's direct question).**
- **Daily snapshot finalizes at market close, 4:00 PM ET** (Realtime page stamp "Last updated at 04:00 PM"; Holdings dated to prior close `2026-07-08`).
- **Intraday trade alerts fire ad hoc during market hours** (observed 12:56 PM, 12:58 PM), tagged `COMPLETED` on execution — these are event-driven, not scheduled.
- **Changelog is date-range queryable** → clean incremental key.
- **Pull schedule:** nightly **full snapshot after 4:15 PM ET** (post-close settle) + an **intraday poller** (~every 15–30 min during 09:30–16:00 ET) to catch alerts near-live for NW.

## 2. Ingestion architecture — mirror, don't re-fetch

```
 operator-placed session profile (Mac Studio runner, local; NEVER in git)
        │
        ▼
 collectors/citrini_crawler.py         (headless Playwright/Chromium; stored profile)
   • full crawl  : all portfolios × tabs + 188 baskets + rankings + macro-trades + watchlists
   • incremental : Changes(since=last) + Intraday Alerts(new) + close snapshot
   • extraction  : DOM/client-state → normalized rows (resilient to flight-format churn)
        │  raw HTML/state snapshots → R2 (audit/replay), never git
        ▼
 engine/citrini/normalize.py           → our canonical schema (mirror of their model)
        │
        ▼
 data/citrini/ (git, small structured) ── PIT tape, append-only:
   portfolios.jsonl · holdings/{date}.parquet · weight_changes.jsonl
   change_logs.jsonl · intraday_alerts.jsonl · baskets/{id}.jsonl · rankings.jsonl
        │
        ├─►  engine/citrini/events.py     deterministic change events + action-tag stream
        ├─►  engine/citrini/crosswalk.py  their 188 baskets ↔ theme_crosswalk.yml ids
        ├─►  engine/citrini/metrics.py    derived reads (derisk/conviction/theme-migration/…)
        ▼
 site/citrini/*.html (operator-auth)   OUR rebuilt dashboard + analysis features
        ▼
 NW: thematic_state `citrini` block · ask_brain read_citrini_book · mastermind_context · contradiction records
        ▲
 engine/citrini/substack.py  (§6 pending) LLM extraction (R-TIL-5 exact-substring citations) → W1 thesis ledger
```

Everything Citrini-derived: **display/context tier**, positioning never fused into scores (Signal Commons law), source graded before believed (DannyTrades law), raw content not republished (operator-auth scope per operator directive).

## 3. Derived analysis layer (metrics we compute on their book → NW)

Deterministic reads over the mirrored PIT tape — the "what are they actually doing" intelligence:
- **De-risking detector:** net/gross/cash trend + hedge-overlay (index puts) additions over a window.
- **Conviction:** basket weight × intra-basket concentration; Δconviction week/week.
- **Theme-weight migration:** which themes gaining/shedding portfolio weight; rotation velocity across themes.
- **Add/trim ledger:** exact tickers + action tags + size per theme, aggregated (initiate/increase vs decrease/close counts).
- **New-theme detection:** first appearance of a basket in the portfolio (expansion signal).
- **Active-vs-drift split:** their "active change" column already separates discretionary moves from price drift — a clean intent signal.
- **Alert-to-snapshot reconciliation:** intraday action tags → next close weight delta (did the alert land at the size implied).
- **House-vs-Citrini contradiction:** their adds into a theme our foresight desk stages `GLUT-RISK`, or vice versa → confluence contradiction record + investigation packet.

## 4. Forward grading (per R-TIL-6/7 — they get graded, not trusted)
Every change event + extracted call → qledger `citrini_*` claim families, standard horizons, per-basket/theme calibrated track record. Two registered future studies once ~90d tape accrues:
- **Lead-lag:** do their adds precede our phase transitions, or do we lead them? (front-run receipts, both directions)
- **Retro-benchmark:** grade our discovery engines against their 188 basket inception dates — "would we have flagged GLP-1 / AI-materials before their basket existed?"

## 5. Wave revision (supersedes masterplan §7.2)
| Wave | Contents | Gate |
|---|---|---|
| CITR-0 | `citrini_crawler.py` (headless, stored profile) + `normalize.py` + `data/citrini/` schema + **initial full pull** of current state (all portfolios/baskets/tabs) | §6.1 session placement |
| CITR-1 | Incremental daily (Changes-since + Intraday Alerts + 4:15 PM snapshot) + intraday poller + `events.py` action-tag stream + session-expiry alerting | CITR-0 |
| CITR-2 | `crosswalk.py` (188 baskets ↔ our theme ids) + their memberships as `source: citrini` edges into TIL W2 graph; holdings-vs-our-basket diffs → operator-reviewed membership candidates | TIL W2 + CITR-0 |
| CITR-3 | `metrics.py` derived analysis (§3) + **our rebuilt UI** `site/citrini/` (operator-auth) with mirror views + analysis features | CITR-1 |
| CITR-4 | Substack LLM extraction (R-TIL-5) → W1 thesis ledger `source: citrini` + thesis-change events | §6.2 substack access |
| CITR-5 | NW wiring: `citrini` block in thematic_state + `read_citrini_book` ask_brain tool + mastermind_context + contradiction records + qledger `citrini_*` grading | TIL W5 + CITR-1..3 |

## 6. Operator-gated items (build starts on these; no agent handles credentials)
1. **Session placement (CITR-0 blocker):** operator logs into citrindex.com on the Mac Studio runner (or exports the BetterAuth session cookie) into a runner-local profile path we agree on (e.g. `~/.citrini/session`, gitignored, env `CITRINI_SESSION_DIR`). We build the reader; operator places the value. Re-place on expiry alert.
2. **Substack access mechanism (CITR-4 blocker):** citriniresearch.com Substack is a **different domain** from citrindex.com — the Citrindex session will NOT authenticate it. Need the path: (a) same institutional login on the substack domain (separate stored session), (b) full-text email → polled mailbox, or (c) manual HTML drop. Operator to choose.
3. **Team-feed confirmation:** the in-app **Intraday Alerts** feed carries the team's rationale + action-tagged trades — this appears to BE the "private chat updated by their team." Confirm whether that is the channel, or whether there is ALSO a separate off-platform channel (Discord/Telegram/Slack) to ingest.
4. **Docsend:** treated as **skip** (Citrindex is the structured superset we mirror). Flag if docsend carries commentary absent from Citrindex.
5. **Display scope:** **operator-auth surfaces + NW synthesis only** (per operator: "we don't plan to just directly offer their content publicly"). Derived metrics/analysis may surface more freely than verbatim content.

## 7. Fences & ops
- No agent enters credentials or the session value; runner reads operator-placed profile.
- Raw crawl snapshots → R2 (audit/replay), never git; only normalized structured rows → `data/citrini/` (small).
- Off the render critical path (crawler is its own launchd/cron lane, not the 67-min nightly render).
- Positioning never fused; display/context tier; `not a signal` authority blocks; LLM extraction-only with exact-substring citations.
- ToS/rate: authorized account, redistribution rights held; crawl politely (serialized, backoff), mirror to our store so NW reads our copy — not their site — on every use.
