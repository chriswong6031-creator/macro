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

## 3. Terminal private-state plane

**PENDING** — first census ran against a stale July-13 working tree (local HEAD 687da219 vs origin e89ebda4 2026-09-04, which predates A1A/A1B merges) and is void for current-state claims. Re-census against `origin/main` via git plumbing in flight. Stale-census facts retained only as *July baseline*: Supabase 0001 schema (profiles, watchlists, watchlist_symbols, chart_layouts, saved_scripts, alerts, favorites), `ingest/alerts_engine.py` 5-min cron (signal/regime/price/rsi conditions, one-shot fire, `active=eq.true` idempotent-fire guard, poll-only), `mm.wls` localStorage guest fallback, bare-ticker join keys.

## 4. Open items toward the first return

- Terminal re-census at origin (in flight): portfolio_positions schema, A1B route, owner-scoping, delivery, upstreams.ts/R2 contracts, identity keys.
- Architecture freeze drafts: identity/time/null/dedup/correction/notification; alert authority + replay/idempotency (extend `alert_time.py` three-clock + typed-read + push_sent patterns; add last-attempt/last-success law).
- Real-data compositions (desktop/tablet/mobile) incl. calm-empty/stale/outage/partial-identity/notification-failure/duplicate-event/resolved/replay states.
- Ordered verticals + cross-compute assignments per root routing; hostile tests; two-user/production proof plan.
