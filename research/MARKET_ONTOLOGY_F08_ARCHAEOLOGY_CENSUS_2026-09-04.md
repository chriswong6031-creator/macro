# F08 Portfolio / Alerts / Monitoring — READ_ONLY_ARCHAEOLOGY census (working draft)

**Operation:** `marketontology-f08-portfolio-alerts-20260826-fable-001` · Slack root `C0BSBM78V1N/1788510682.177519` · git carrier macro#6819 · Linear MAS-149
**State:** READ_ONLY_ARCHAEOLOGY — zero source effect. PICKUP_ACK `1788578664.952659`, START `1788578680.715949` (2026-09-04).
**Principal:** Claude3/U0BSLFRGA79 seat, live-verified (amendment 1788511854 forbids app-install labels as auth proof).

## 1. Governance / capability ledger (verified 2026-09-04)

Authoritative row state = `research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv` (newest of three generations: 08-26 baseline → 08-28 F00B crosswalk → 09-02 F00C closure).

| Row | Capability | State | Disposition | Adjudicated next bounded child |
|---|---|---|---|---|
| MO-PAID-027 | Alerts and monitoring | PARTIAL | UPGRADE_EXISTING_OWNER | F08 owns the **delivery-path build**; acceptance: a held position generates a material-change alert reaching a delivery channel |
| MO-PAID-028 | Portfolio exposure / event-to-portfolio | NOT_BUILT | PROJECTION_ONLY | ONE child with **MO-DELTA-042** (event→position mapping incl. direction/mechanism/timeframe/invalidation schema); acceptance: an event object resolves to the user positions it touches on a routed page |
| MO-PAID-036 | Full Portfolio Management / risk | PARTIAL | PROJECTION_ONLY | ONE child with **MO-DELTA-014** (user-portfolio metric/risk projection over canonical holdings); acceptance: a user's actual holdings produce a concentration/factor/liquidity readout |
| MO-PAID-085 | Notifications / alerts settings | NOT_BUILT | UPGRADE_EXISTING_OWNER | F08 delivery-path child includes prefs + `app/mailer.py` wiring (email unwired, **not rights-blocked**); acceptance: a set preference causes an actual send on the next matching alert |

Authority ceilings: 027/085 `notification_only`; 028 `context_and_user_decision_support`; 036 `decision_support_only`.

**Binding constraints:**
- WS:MARKET-OS do_not_redo: no second Portfolio/Watchlist/event/identity/risk/brief store; never merge Watchlist attention membership into Portfolio ownership semantics; LLM never originates signal/rank/gate/size/forecast/trade.
- F08 handoff do_not_redo: no second holdings store, portfolio state model, risk engine, alert scheduler/lifecycle, or local offline truth; research portfolio weights never become execution/sizing authority.
- A1A = Portfolio Population Truth + State Authority, DONE/PROVEN_LIVE (`DEC:MARKET-OS-A1A-ACCEPTED-IN-PRODUCTION`); A1B = Portfolio Fast Start Import, single canonical paste→write path via `portfolio_positions`, DONE/PROVEN_LIVE (`DEC:MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION`, PRs #6335/#6508). Neither may be reopened or duplicated.
- No DNR §1–4 kill forbids F08 surfaces. `DNR:KILL-FUSED-COMPOSITE` Amendment 2 (2026-08-03) explicitly **permits** the display-tier Portfolio Health Score + sub-scores on watchlist/portfolio surfaces + digest emails per `PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md` §3.1.2.
- Landmines: authenticated-cloud-fail-never-falls-to-local-book; A1B exclusively owns import; no second count/state store (#6510 repair).

## 2. Macro alert plane (verified 2026-09-04, macro-main @ origin/main 509c7894)

**Two divergent lineages, no shared library, no central alert registry:**
- Parquet `log_and_dedup` keyed `(date, rule[, message])`: `engine/alerts.py` (US macro, `data/alerts/alerts_log.parquet`), `engine/china_alerts.py`, `engine/hk_alerts.py`. Same-day re-run idempotent.
- Jsonl state-diff + append+dedup by engine-minted id: `btc_alerts`, `commodity_alerts`, `forex_alerts`, `bonds_alerts`, `theme_alerts`, `allocation_alerts`, `altdata_alerts`, `demand_alerts`, `emergence_alerts`, `subsector_rotation_alerts`, `ticker_alerts`, `engine/oracle/alerts.py` (id scheme `type:node:bucket`). First-run silent seed; ~90d retention; no cross-engine ID namespace.

**Aggregation:** `engine/alert_triage.py` (pure assembler, 1731 lines) is the SOLE owner of `site/alerts.html` (via `scripts/build_site.py::build_alerts_page` → `templates/alerts.html.j2`) + machine feeds `site/factordata/alerts_triage.json`, `site/alertsdata/feed.json`. Typed per-source reads: `READ_OK / READ_OK_ZERO / READ_NO_COVERAGE / READ_UNAVAILABLE` — a crash during triage read is typed, never folded into "no alerts".

**Time contract:** `engine/alert_time.py` — three clocks (`event_date/event_ts`, `source_asof`, `recorded_at`), `board_date()` NY projection. Historical stale-labeled-as-today defect (subsector) is governed by it.

**Delivery:** NOT render-only. `alert_triage.push_priority_alerts()` → Telegram/Discord via `scripts/notify.py`, **config-gated OFF** (`alert_push.enabled=false` default; dag node `push_alerts` a no-op until operator enables). Send-dedup via `push_sent.jsonl` + 6h same-`(source,type,asset)` silence window — closest existing replay protection. `push_ops_alert()` is dispatch-always for ops liveness. No email delivery wired: `engine/portfolio_digest.py` states "THE SEND PATH IS NOT WIRED, DELIBERATELY"; `app/mailer.py` exists, unwired for alerts, not rights-blocked. `app/account_prefs.py` holds only theme/lang/brain_depth — no alert prefs.

**Scheduler:** none — scheduling is entirely `config/dag.yml`; per-domain engines run inside builder scripts (build_bonds/build_forex/…) which are the dag nodes.

**Known integrity gap (F08-relevant):** no engine keeps `last_attempt` distinct from last-success. Evidenced: `scripts/build_bonds.py:1433-1440` falls back `rebuild_with_credit → rebuild → load_events()` (last persisted state) with no failure flag — a failed nightly renders yesterday's alert state as current at the per-domain page level. This violates the F08 law "alert failure masquerading clear/current" and is a primary freeze target.

**Watchlist sentinel:** `engine/watchlist_alerts.py` is a pure reader over `data/alerts/watchlist_alerts.jsonl` written by `scripts/run_watchlist_sentinel.py`; returns `[]` on missing file — cannot distinguish "never ran" from "ran, nothing found".

**Per-domain surfaces:** bonds/forex/allocation/china/hk/commodities/baskets pages render their own local alert timelines independent of the triage board; `templates/_us_act_now_board.html.j2` is a separate board-like surface (data source untraced — gap).

**HOUSE vs user:** `engine/portfolio.py` is HOUSE cross-asset risk-budgeting, NOT user-portfolio; user holdings truth lives in A1A/A1B (Terminal-side).

## 3. Terminal private-state plane (verified 2026-09-04 at charting-app origin/master e89ebda4 via git plumbing — local checkout was July-stale and was NOT used)

**A1A portfolio truth store — `portfolio_positions` (Supabase), CONFIRMED LIVE:**
- Schema (`supabase/migrations/0007_portfolio_positions.sql`): `id uuid pk gen_random_uuid()`, `user_id → auth.users on delete cascade`, `ticker text`, `shares numeric`, `entry_price numeric`, `entry_date date`, `notes text`, `status text default 'open'`, `created_at/updated_at`. RLS enabled with four own-row policies (`auth.uid() = user_id`).
- Service `terminal/lib/portfolio.ts`: belt-and-braces owner scoping (RLS + explicit `.eq("user_id", userId)`); **TWO-ORGANISMS LAW (UWP-R2)** in module doc — holdings never feed signal/score/ranker/alerts; display tier only.
- Route `terminal/app/api/portfolio/route.ts`: GET distinguishes 401 signed-out / 200 empty / 503 store-unreadable (empty ≠ outage — typed). POST `create/update/close/reopen/delete`; `user_id` never read from body; foreign ids 404 via ownership re-resolution.
- Write semantics: server-generated uuid, **no client idempotency key, no upsert-by-natural-key** (multiple rows per ticker legal); `status` writer-enforced only (no DB CHECK).
- **No local fallback for authenticated users** (`TerminalShell.tsx:1012-1013`: portfolio rows only from `/api/portfolio`; never folded into `lists`/`mm.wls`/watchlist sync).

**A1B import path — lives MACRO-side, not in charting-app:** verified absent from Terminal at origin (no paste/bulk route or component). The canonical paste→write path is the macro dashboard client: `templates/portfolio.js` ("paste a book on the Portfolio tab") + `templates/watchstore.js:1008-1030` writing to the SAME Supabase `portfolio_positions` (insert with one-shot local→cloud fold guarded by `pfFoldMarkerKey`; empty local book never consumes the fold). Macro server reads open positions in `app/main.py:1612,1641`. Schema also mirrored in `templates/uwp_supabase.sql`. **One shared store, two product surfaces** — macro side keeps a signed-out localStorage book with one-shot fold; Terminal side has no local book at all.

**Watchlist at origin:** `terminal/app/api/watchlist/route.ts` — GET full inventory; POST list CRUD (`createList/renameList/deleteList`, W1b) + symbol ops (`addSymbols/removeSymbols/moveSymbols`); destructive ops require explicit resolved target. `mm.wls` persists as an optimistic cache demoted after one-time migration (`mm.wls.migrated.v1`/`.deleted.v1` markers; prior cross-user-leak bug covered by `watchlist-ownership.spec.ts`). `0009_watchlist_symbol_unique.sql` exists (unread). **Watchlist/portfolio separation explicit and tested** — no FK between them; "adding to a watchlist leaves portfolio_positions unchanged."

**Alerts at origin:** `terminal/app/api/alerts/route.ts` grew ~35→191 lines since July: typed GET errors (503 on read failure, no longer silent `[]`), condition allow-list `LEGACY={signal,regime,price,rsi}` + 8 `opt_*` options types + `suite_event/suite_sequence` (`terminal/lib/suiteAlerts.ts`), entitlement gating (`isPaidTier/isProTier`, fails closed), `MAX_ALERTS_PER_USER=50`, and options-identity canonicalization on write (`canonicalizeOptAlertIdentity`, `terminal/lib/optionsAlerts.ts:647-660` — persisted `symbol` derived from `condition.root`; market-wide kinds → sentinel `MARKET`). `ingest/alerts_engine.py` +925/-20 lines since July (body unread — gap). **Delivery: still NONE — poll-only** (grep for smtp/sendgrid/resend/webhook/push/notif across ingest+terminal returned zero delivery channels).

**Cross-origin contracts:** `terminal/lib/upstreams.ts` — `R2_BASE` (public R2 CDN), `FLOW_BACKEND` (Quote-Hub sidecar, R2 fallback), `ISSUE_DESK_API_BASE` (www.mastermind-x.com), `NW_BASE` (neuralwebdata). `company-intelligence/[symbol]` BFF resolves from R2 (`resolveCompanyIntelligenceFromR2`).

**Identity join keys:** portfolio/watchlist = bare normalized ticker (`normalizeTicker`: trim/upper/≤128/control-rejected); options alerts carry the richer canonical identity above. No CIK/internal-id join anywhere in private state.

**F08-relevant integrity notes:** Terminal alerts one-shot fire with `active=eq.true` idempotent-fire guard (July baseline; engine body re-read pending); alert "delivery" today = UI poll of `GET /api/alerts`; alert prefs do not exist on either side; the two alert planes (macro engine-file alerts vs Terminal user-condition alerts) are fully disjoint systems with no shared registry — composition, not unification, is the F08 job.

## 4. Open items toward the first return

- Read `ingest/alerts_engine.py` current body at origin (+925 lines since July) — evaluator condition dispatch + fire semantics.
- Architecture freeze drafts: identity/time/null/dedup/correction/notification; alert authority + replay/idempotency (extend `alert_time.py` three-clock + typed-read + push_sent patterns; add last-attempt/last-success law).
- Real-data compositions (desktop/tablet/mobile) incl. calm-empty/stale/outage/partial-identity/notification-failure/duplicate-event/resolved/replay states.
- Ordered verticals + cross-compute assignments per root routing; hostile tests; two-user/production proof plan.
