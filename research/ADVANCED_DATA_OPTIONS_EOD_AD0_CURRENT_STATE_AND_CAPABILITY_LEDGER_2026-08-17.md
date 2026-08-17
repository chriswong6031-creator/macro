# Advanced Data: Options EOD + Off-Exchange — AD-0 Current State and Capability Ledger
## Recovery archaeology + production truth · 2026-08-17

**Program:** Advanced Data / Options EOD / Off-Exchange Intelligence (owning registry program: `options-intelligence`, `config/mastermind_programs.yml`)
**Wave:** AD-0 (research/production-truth only; no runtime change)
**Governing north star:** `ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md` (operator-held)
**Companion deliverable:** `research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md`
**Audit head (`main_at_start`):** `7a6a6656e2898cbe12ee3610729e2b5b5726543c` (origin/main, "feat(agents): enforce semantic routing and worker contracts (#5823)")
**Production probe time:** 2026-08-17 07:43 EDT (Monday, pre-open; last completed US session Friday 2026-08-14)

Evidence convention: every claim below cites a repo path (at `main_at_start`), a production URL probe, a `gh` query, or a host probe run on the Mac Studio on 2026-08-17. The prior "options_inventory" starter bundle was machine-generated against an EMPTY head (its own ledger records `Repository HEAD audited: ""`, 0 artifacts, 0 probes) and was treated as an intent document only; nothing below relies on it.

---

## 0. Verdict in one paragraph

The options estate is a large, mostly honest **data-and-display asset with one narrow proven machine consumer**, not a completed intelligence lobe. The EOD spine (Polygon chain snapshot → session-stamped parquet → Options Workspace) is PROVEN_LIVE and current to the last settled session; the darkpool desk is PROVEN_LIVE with direction lawfully withheld by design; exactly one options-derived input (`gex_confirm_verdict`) lawfully reaches live Prophet rank via C1 fusion; Neural Web consumption is live but context-only; Sector consumption is zero; Terminal is a consumer of Macro exports, never a source. Meanwhile the entire host-side intraday options fleet (15 launchd units, including the sparse-selector canary, options hub, chain snapshots, live flow poller, NBBO cohort) is **not loaded on the host as of 2026-08-17** — a whole stratum of prior effort is currently dark in production. The product's failure to meet the Chairman bar is precisely located: every user-facing card stops at *attention* ("watch — don't chase", "direction approximate") and no surface anywhere emits horizon, asymmetry, confidence, trigger, invalidation, fresh-until, or Prophet state per name. That composed decision layer is `NOT_BUILT`; nearly everything beneath it is salvageable.

---

## 1. Production identity and source sessions

| Field | Value | Evidence |
|---|---|---|
| `main_at_start` | `7a6a6656e289` | `git log -1 origin/main` |
| Production checkout SHA | `7a6a6656e28` (= main tip) | `GET https://www.mastermind-x.com/api/health` → `{"status":"ok","commit":"16874921e63","checkout":"7a6a6656e28"}` |
| Production API commit (app binary) | `16874921e63` ("feat(fif-1r): hermetic golden financial intelligence packet (#5809)") | same probe; semantic "last app restart build" is inferred, not documented — see §11 risks |
| EOD options latest completed source session | chains through **2026-08-14** (Friday), collected by the Friday daily lane; Workspace displays settled session **2026-08-13** with "Positions counted 2026-08-14" (OI clock) | served `options.html` (Last-Modified `Sat, 15 Aug 2026 00:45:21 GMT`); `data/polygon_gex/chains/` session-stamped store |
| Off-exchange latest completed source session | **2026-08-13** (`asof` in `darkpool_eod.v2`) | served `darkpool.html` inline payload + `git show origin/main:site/darkpool_eod.json` (identical) |
| Page build timestamps | options.html `2026-08-15 00:45:21 GMT`; darkpool.html `2026-08-14 22:33:07 GMT`; advanced.html `2026-08-14 11:30:17 GMT` | `curl -sI` Last-Modified headers |
| Last successful nightly (`daily.yml`) | `2026-08-16T23:42:37Z` success (head `e7cdfa2573`); prior failures 08-15T22:49Z / 08-15T09:16Z, success 08-15T23:42Z | `gh run list --workflow daily.yml --limit 5` |
| Last `closing-bell.yml` run in 5-row window | `2026-08-14T21:25:04Z` success (Friday 17:25 ET) | `gh run list --workflow closing-bell.yml --limit 5` |
| Data-plane JSON access | ALL options/darkpool JSON endpoints auth-gated in production: HTTP 401 `{"locked":true,"reason":"authentication_required"}`; page HTML carries the data server-rendered inline | curl probes of `darkpool_eod.json`, `flow_desk.json`, `flowdata/cohorts.json`, `flowleaders/leaders.json`, `screenerdata/rows.json`, `live_flow/tide_current.json`, `options_dislocation.json` |
| `flow_leaders.html` / `options_screener.html` | redirect stubs (0-second meta-refresh into `options.html#leaders` / `#scanner`) — consolidated into the one Workspace | curl body reads |

### 1.1 Freshness-trap audit (handoff §5.2)

No surface exhibited the strict trap (*fresh render over stale source*): the stale surfaces are stale together (render **and** source both pre-weekend). The real findings are adjacent and named:

1. **Weekend settle gap (PARTIAL defect, not repaired in AD-0).** On Monday pre-open a user sees the **Thursday 08-13** settled board ("SESSION CLOSED 2026-08-13") even though Friday's chains were collected Friday evening and Friday's OI published Saturday morning. No weekend lane advances the Workspace to Friday-settled; `closing-bell.yml` (16:05 ET Mon–Fri) is the only advancer of the settled board and it had not yet run. Displayed staleness at probe time: 2 sessions of wall-clock, 1 settled session.
2. **Darkpool permanent T+1 display.** `build_darkpool_desk` runs in the 16:05–17:25 ET closing-bell lane, *before* FINRA's ~18:00 ET CNMS publication, so the desk's `asof` is structurally one session behind at every render, although the source itself is T+0-evening. Weekend adds two days on top (Monday user sees Thursday).
3. **`site/options_prophet/index.json`: `as_of: "2026-08-11"` with `built_at: "2026-08-14T04:19Z"`** — a build 3 sessions newer than its as-of. Its own contract claims `cadence: event_driven_every_few_sessions`, so this is *documented* lag, but it is exactly the shape §5.2 warns about and its UI/receipt story is unproven (see ledger).
4. One `"asof":"2026-08-04"` row inside the served darkpool payload (single stale row amid 2026-08-13 rows) — un-root-caused; recorded as a data-quality defect observation.

---

## 2. Maturity ledger

Labels are exactly the eight required states. "Owner" = accountable program/seat, not a session. Fields not listed on a row are covered by the referenced section. Consolidated per-component details (producer path, source, clock, consumers, proof, defects, salvage) follow in §§3–4 and §8; this table is the authoritative classification.

### 2.1 PROVEN_LIVE (current or bounded production chain shown)

| # | Component | Chain proof (input → producer → artifact → consumer → output → receipt) | Defects |
|---|---|---|---|
| P1 | **EOD options chain collection** | Polygon snapshot API (`POLYGON_API_KEY`) → `collectors/polygon_options.py` + `scripts/build_polygon_gex.py::accrue` (invoked `scripts/collect.py:841` in `daily.yml`, cron 22:30/23:30 UTC ≈ 18:30 ET) → `data/polygon_gex/chains/{session}.parquet` (session-stamped, `_resolve_session` `build_polygon_gex.py:38-50`) + `summary_{SYM}.parquet` → Workspace/GEX consumers → served `options.html` with "Positions counted 2026-08-14" | none current; OI is PIT non-backfillable by construction |
| P2 | **Options Workspace product surface** (`options.html`) | store artifacts → `scripts/build_options_command.py` (closing-bell + engine-render + daily + render lanes) → `templates/options.html.j2` → served page (LM 08-15 00:45 GMT), session/coverage/quality stamps in first viewport ("SESSION CLOSED 2026-08-13", "372/408", "Partial") | weekend settle gap (§1.1-1); decision layer absent (§5) |
| P3 | **Darkpool desk** | FINRA CNMS daily short volume + FINRA OTC ATS weekly (keyless) → `collectors/finra_short_volume.py` / `finra_ats_transparency.py` → `data/finra_short_volume/panel*.parquet`, `data/finra_ats/` → `scripts/build_darkpool_desk.py` (closing-bell) → `site/darkpool_eod.json` (`darkpool_eod.v2`) → served `darkpool.html` (asof 08-13, ATS/non-ATS split, named venues) | structural T+1 display (§1.1-2); one 08-04 row (§1.1-4) |
| P4 | **Options flow accrual + Flow desk** | massive.com OPRA minute/day aggs (`collectors/massive_flatfiles.py`) → `scripts/build_options_flow.py` → `data/options_flow/summary_{SYM}.parquet` → `scripts/build_flow_desk.py` → `site/flow_desk.json` (asof 08-13 / built_utc 08-14T23:55Z, committed == served) | direction is inferred tick-rule (~77–83% sign accuracy, `engine/options_flow.py:22-25`) — honestly disclosed |
| P5 | **GEX board + dealer-confirm chain** (the strongest machine chain) | chains → `scripts/build_gex_board.py` (closing-bell/engine-render/render) + `engine/gex_confirm.py` → dealer tiles on `options.html` ("S&P DEALERS: Absorbing · 10 days in this state") + `gex_confirm_verdict` → **live Prophet C1 fusion** (P7) + Terminal export (P9) | GEX is modeled proxy under sign assumptions (see §6.4) — disclosed in program law |
| P6 | **Options signal episode + outcome ledgers** | R2 `live_flow/events/{date}.jsonl` → `scripts/build_options_signal_episode.py` + `build_options_signal_campaign.py` (`daily.yml:3647-3694`, gated by `engine/ledger_lane.py::nightly_advance_enabled`) → `data/options_signal_episode/{episodes,outcomes_h60,outcomes_session}.jsonl`, `data/options_signal_campaign/` (v2) → consumer = coverage grader `scripts/audit_options_episode_outcome_coverage.py` + calibration audits | authority intentionally zero ("Nothing here ranks, gates, sizes, escalates, or originates"); no product consumer — research accrual chain only |
| P7 | **Prophet options input — `gex_confirm_verdict`** | `engine/gex_confirm.py` → `engine/us_prophet_fusion.py:255-268` (REGISTERED_SIGNS, family `F5_FLOW_POSITIONING`, sign +1, `{confirm:1.0, neutral:0.0, caution:-1.0}`) → `engine/us_board_rank.py:1155-1420` — C1 fusion is "the canonical rank authority (US)" since the Chairman override of 2026-08-15 | the ONLY options-derived member of the 8-sign registry; lawful solely via `DNR:KILL-POSITIONING-FUSION` Amendment 1 (`DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY`) scoped to the Prophet-US conditional-fusion arena |
| P8 | **Neural Web options context** | `engine/neuralweb/options_plane.py::options_structure_block` → `engine/neuralweb/mastermind_context.py:70-71,3175` (live chat/context builder); `engine/neuralweb/cortex.py:712-713` renders `gex_confirm_verdict` as "(display-only)" prose | charter: "Context, never a gate"; context-only by design, not a defect |
| P9 | **Macro→Terminal export bridge** | `scripts/export_signal_contracts.py:195-217` → `site/stockdata/<SYM>.json` incl. `gex`, `gex_confirm` fields; manifest-declared consumers `terminal:pull_macro_intel`, `bot:conviction`; `scripts/build_flow_surface.py` output feeds Terminal Flow Surface contract | flow-surface *standalone lane* is dark (D-fleet) — the export chain named here is the stockdata one |
| P10 | **Skew / IV-spread / structure display artifacts** | chains → `build_options_skew.py` / `build_options_ivspread.py` (closing-bell/engine-render/render) → `site/options_skew/`, `site/options_ivspread/`, `site/options_structure/` (last re-render 2026-08-15 scope=all) | display-tier; no decision composition on top |

### 2.2 PARTIAL

| # | Component | State | Why not higher |
|---|---|---|---|
| Q1 | **Options Workspace freshness advance** | settle-session advance runs only on the closing-bell clock | weekend/holiday gap (§1.1-1); the page honestly *labels* its session, so it is a cadence defect, not a lie |
| Q2 | **Options dislocation** | `build_options_dislocation.py` live (closing-bell/engine-render); artifact current (`as_of 2026-08-13`, `generated_utc 08-14T22:15Z`) | self-gated: `gate_status: "insufficient_history (have 41/120 dates, 392/15 names)"` — an accruing display-tier gauge, not yet an intelligence output |
| Q3 | **Options Prophet shadow projection** (`options.prophet_shadow/v1`) | produced nightly inside `daily.yml` via `scripts/ci/daily_engine_regime_dashboard.sh:183` (`build_options_prophet`, `AUTHORITY="display_only"`, `promotion_ready:false`, abstention-first), mirrored to R2 (`scripts/mirror_flow_idx.py --options-prophet`, `daily.yml:3792`) | its only coded consumer (`engine/options_issue_desk.py:599`) is UNSCHEDULED; `as_of` lags build by 3 sessions (§1.1-3); no UI or consumer receipt found → producer live, consumption unproven |
| Q4 | **Market Memory options context (upstream path)** | `engine/options_market_memory_context.py` + `engine/options_market_memory_receipt_store.py` exist with durable receipt design («atomic HEAD.json») | no scheduled lane invokes the producer (no dag node, no workflow, launchd option-hub/NBBO units not loaded); freshness on host: `~/.mastermind_private/options_nbbo_cohort_v1` last write 2026-08-12 08:35 |

### 2.3 DARK_OR_DISCONNECTED

| # | Component | Evidence |
|---|---|---|
| D1 | **Entire host-side intraday options fleet — 15 launchd units** (`com.mastermind.chainsnapshots`, `com.mastermind.liveflow`, `com.mastermind.optionshub`, `com.macro.optionsmatrix`, `com.mastermind.optionsnbbocohort`, `com.mastermind.prophetmarks`, `com.macro.indexgexhistory`, `com.macro.unusualbaseline`, `com.mastermind.flowenrich`, `com.macro.theme-options-witness`, `com.mastermind.gexstate-mirror`, `com.macro.chainheat`, `com.macro.extquotes`, `com.macro.thetadata-r2sync`, `com.mastermind.optionssparseselector`) | Host probe 2026-08-17: `launchctl list \| grep -iE 'macro\|mastermind'` shows NONE of them; `launchctl print gui/501/<unit>` and `system/<unit>` → "Could not find service" for every unit checked; `~/Library/LaunchAgents/` contains only `optionsnbbocohort` (installed, NOT loaded) and `liveflow` **as `.bak` files only**. The plists exist in-repo (`ops/launchd/`) but nothing runs them. Downstream builders that depend on the pollers (`build_flow_surface`, `build_flow_archive`, `build_flow_enrich`, `build_options_structure_intraday`, `build_live_flow_baselines`, `build_options_matrix`, `build_options_hub_nightly`, `build_index_gex_history` standalone lanes) are dark with them. |
| D2 | **Sparse-selector canary (whole path)** | Unit not loaded (above); receipt roots `~/.mastermind_private/options_sparse_selector_v1/` and `_ops_v2/` DO NOT EXIST on host (listing 2026-08-17); `config/dag.yml:4651-4680` marks the node launchd-owned with host-private writes, activation expiring `2026-08-21T20:00:00Z`, "proposal capability is false … only lawful settled result is an evidence-bound abstention," and NO consumer of any kind. PR archaeology: #5747 (docs handoff, merged 08-15), #5694 (canary activation, merged 08-14), #5696 (sealed runtime v2, merged 08-14), #5708 (import-pin waiver + DEC, merged 08-15), #5711 (closed unmerged duplicate of #5708). The 08-15 handoff's "installed and recurring… 124 normal launchd runs" claim is **no longer true on the host**; the canary produced no selector state before going inert. |
| D3 | **W1A local receipt modules** (#5790 verifier `engine/options_market_memory_local_receipts.py`, #5801 replica `engine/options_market_memory_local_replica.py`, merged 08-16) | imported by NOTHING except their own tests and each other (`git grep` negative); no scripts wrapper, no dag node, no workflow, no W1A-C continuation doc anywhere on main |
| D4 | **Options issue desk** (`scripts/build_options_issue_desk.py`, `engine/options_issue_desk.py`) | declared in `config/dag.yml` but dag.yml is a conformance registry, not an executor; zero workflow/launchd invocation; it is also the only coded consumer of Q3 |
| D5 | **Focused quote** (`build_options_focused_quote.py`) | zero invocation sites anywhere (workflows, scripts/ci, scripts, engine, dag) |
| D6 | **Standalone lanes:** `build_tape_flow` (superseded by LIVE `build_tape_flow_daily`), `build_flow_archive`, `build_flow_enrich`, `build_live_flow_baselines`, `build_index_gex_history`, `build_options_matrix`, `build_options_hub_nightly`, `build_options_structure_intraday`, `build_prophet_option_shadow_lifecycle`, `build_options_sparse_selector_prereg` | absent from all workflows AND from `scripts/ci/*.sh` (re-checked after the `build_options_prophet` false-dark was caught hiding in `daily_engine_regime_dashboard.sh:183`); several remain *library-imported* by live builders (e.g. `build_options_matrix` imported by LIVE `scripts/build_prophet.py`; `build_options_hub_nightly` imported by `build_levels`/others) — functions may execute inside live callers even though the standalone product lanes are dark; per-function liveness was not adjudicated in AD-0 |

### 2.4 Other states

| Label | Components |
|---|---|
| **BUILT_NOT_PROVEN** | `options.prophet_shadow` consumption story (Q3's consumer half); ThetaData per-trade+NBBO collector (`collectors/thetadata.py::trade_quote` — entitled and coded, explicitly NOT wired into `engine/options_flow.py`, whose docstring defers "true trade-level flow classification (sweep/block, open/close attribution, buyer/seller-initiated)" to future work); Market Memory capture modules `engine/neuralweb/market_memory_option_oi_{observation,store}.py`, `market_memory_options_episode_capture.py` (present, no confirmed live call site) |
| **BROKEN** | none demonstrated at the component level on current main. (Transient: two failed `daily.yml` runs on 08-15 followed by success; the 08-04 darkpool row, §1.1-4.) |
| **SPEC_ONLY** | `options_events` Neural-Web nerve — registered in `config/synapse.yml` with the comment "options_events deferred (producer not live yet)"; the AD masterplan's signal/observation contracts (§6) — no implementation exists |
| **NOT_BUILT** | **The decision layer itself**: per-name signal cards with direction/horizon/asymmetry/confidence/trigger/invalidation/fresh-until/Prophet-state; event-pricing board (implied vs event-conditioned move); ranked anticipation board with `NO_SIGNAL` law; correction/supersession propagation for options signals; a dedicated **option-contract identity plane** (`engine/options_universe.py` resolves underlyings only); Prophet shadow *consumer receipts* (AD-5 shape); off-exchange direction-qualified clustering (withheld by design today — see next row) |
| **REJECTED_BY_DESIGN** | Darkpool directional accumulation/distribution labels — v2 removed direction after a null walk-forward (t-stats 0.33/−0.63/−0.05 across 1/5/10d; `engine/darkpool_context.py:20-32`) and `DNR:PSS-AF1` forbids off-exchange share as a standalone direction signal; **positioning-key fusion into any non-Prophet-US score** (`DNR:KILL-POSITIONING-FUSION`); delta-OI directional family (`DNR:KILL-DOI-FAMILY`); skew-deceleration-bullish (`DNR:KILL-SKEW-DECELERATION`); owner-set narrowing on the options context audit (`DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION`); W-F options wave parked (`DNR:HOLD-WF-OPTIONS`); rebuilding Terminal intraday flow inside this lobe; any second identity/event/queue/state/publication plane |

---

## 3. Producer → consumer map (current, live paths only)

```text
Polygon snapshot (18:30 ET, daily.yml) ──► data/polygon_gex/chains + summaries
massive.com OPRA aggs ─────────────────► data/options_flow/summary_* ──► flow_desk.json ──► options.html (Flow tab)
FINRA CNMS + ATS (closing-bell) ───────► data/finra_* ──► darkpool_eod.json ──► darkpool.html
chains ──► build_gex_board / gex_confirm ──► dealer tiles (options.html)
                                        ├──► gex_confirm_verdict ──► us_prophet_fusion (C1, LIVE RANK)
                                        ├──► neuralweb options_plane ──► Mastermind chat (context-only)
                                        └──► stockdata/<SYM>.json ──► Terminal pull_macro_intel / bot:conviction
chains ──► skew / ivspread / structure / dislocation display artifacts
R2 live_flow events ──► options_signal_episode + campaign v2 ledgers (nightly, zero authority) ──► coverage audits
build_options_prophet (nightly) ──► site/options_prophet/index.json ──► R2 mirror ──► (no live consumer)
```

Sector Intelligence: **no options input of any kind** (negative grep across all 16 `engine/sector*` files).
Terminal→Macro: **no ingestion path exists** (Macro produces; the Terminal consumes).

---

## 4. Source and rights matrix

| Source | Family | Entitlement (evidenced) | Clock / latency | Coverage | Cost class | Current use | Required for AD-1? | Known gap |
|---|---|---|---|---|---|---|---|---|
| **Polygon.io** options snapshot | per-contract EOD chain: OI, IV, greeks (gamma/delta), volume | `POLYGON_API_KEY` (daily.yml:323) | collected ~18:30 ET T+0; **OI is next-morning PIT** (positions-counted date on page); session-stamped, non-backfillable | 408-name universe, 372 covered on 08-13 ("Partial") | paid API | P1/P5/P10 chains | **YES — primary** | no per-trade/NBBO; multiplier/adjusted-contract semantics unadjudicated (§6.1) |
| **massive.com** flatfiles (Polygon-compatible S3) | OPRA `minute_aggs_v1`, `day_aggs_v1`; `us_stocks_sip/day_aggs_v1` | S3 creds (`MASSIVE_S3_*`); explicitly **NOT entitled**: `trades_v1`, `quotes_v1` (403, `collectors/massive_flatfiles.py:10-12`) | EOD/T+1 file drops | full OPRA aggregate | paid | P4 flow accrual | yes (flow features) | **no aggressor/NBBO ⇒ direction permanently inferred** on this source |
| **ThetaData** | per-trade + NBBO quote (`trade_quote`) | collector coded + r2sync unit exists (unit not loaded) | intraday | — | paid | **unwired** (BUILT_NOT_PROVEN) | no (AD-1); candidate for later waves | wiring + calibration debt; F7 tape-signing suspend governs (Options Confluence law 15) |
| **FINRA** CNMS daily short volume | off-exchange (TRF facility) daily per-name | keyless public CDN | published ~18:00 ET T+0; **collected 16:05–17:25 ET ⇒ effective T+1** | 300-name desk panel, 762 sessions | free | P3 darkpool | AD-3, not AD-1 | timing mismatch is self-inflicted (§1.1-2) |
| **FINRA** OTC Transparency | per-ATS weekly venue breakdown | keyless API | weekly, ~T+2wk | ATS + non-ATS split, named venues | free | P3 venue attribution | AD-3 | weekly lag; venue-unknown residual ("14% unattributed" shown honestly) |
| **Cboe** delayed chain | 1-row/day GEX summary | free delayed | EOD | legacy | free | legacy adapter, superseded by Polygon | no | discards per-strike chain |
| Redistribution / derived-display rights | — | **UNKNOWN — not evidenced in-repo for any paid source**; display is auth-gated in production (data JSONs 401) which is consistent with a subscriber-display posture | — | — | — | — | — | rights matrix needs operator/vendor confirmation before any public-tier expansion (flagged §11) |

No new vendor is needed for AD-1; no purchase is recommended (Polygon chain + existing price/event planes cover every AD-1 feature family — §12.4 of the AD-1 handoff).

---

## 5. User-experience archaeology (live page, anonymous view, 2026-08-17)

First viewport of `options.html` (screenshot taken; verbatim text preserved): masthead "Options — One workspace for the settled close — brief, scanner, per-name, leaders"; session block "SESSION CLOSED 2026-08-13 · Thursday · closed 16:00 ET / Positions counted 2026-08-14 / Names covered 372/408 / Data quality Partial"; four regime tiles (Whole market: "Risk-on backdrop · VIX 14.6"; S&P dealers: "Absorbing · 10 days in this state"; Today's tape: "Average · $21.8B traded"; Same-day bets: "11% of premium expiring the same day") with the caption "Four readings, shown side by side and never averaged into one score"; then tabs (Daily Brief / Flow 12 / Scanner 408 / Ticker / Leaders 2) and "What changed → Tape held steady · Watch — don't chase — Nothing here is a trade on its own — these are the day's deltas, not signals."

Answers to the 16 required questions:

1. **Before scrolling:** session identity + data quality, four market-level regime readings, and a "what changed" delta strip. No per-name signal.
2. **Single most important item:** not designated. The regime tiles share equal weight; no ranked lead item exists.
3. **Why it matters:** partially — tiles carry plain-word stances ("Calm — moves get damped", "Dips tend to get bought here") with one-line mechanics.
4. **Horizon:** absent everywhere (nearest proxy: "levels hold until tomorrow's data run").
5. **Direction:** market-level yes (regime stance); per-name only "call-leaning/put-leaning … direction approximate."
6. **Asymmetry:** absent.
7. **Confidence:** absent (only data-quality "Partial" and "tone: not reliable alone" caveats).
8. **Trigger:** absent (closest: "a move through a level intraday does not count until it closes there").
9. **Invalidation:** absent.
10. **Freshness:** YES — session date, positions-counted date, coverage fraction, per-module date stamps (notably the brief mixes 2026-08-13 and 2026-08-14-stamped modules on one board).
11. **No-signal state:** YES in spirit — "Watch — don't chase" is pervasive; but it is a *disclaimer on attention lists*, not a per-name `NO_SIGNAL` verdict on complete data.
12. **Prophet context:** absent from the entire surface.
13. **Correction/degraded state:** partial — coverage/quality stamps exist; no degraded/withheld-signal semantics.
14. **Observed vs inferred:** YES, consistently ("direction approximate", "buying ~", darkpool "the tape cannot say who"). This is a genuine strength to preserve.
15. **"Dark pool" overstatement:** headline says "Dark Pool" but the body is honest: "FINRA-facility off-exchange volume," ATS vs internalized split, "14% unattributed," "hides who is trading, so it cannot call a direction on its own." Terminology slightly overstates venue certainty; content does not.
16. **Raw contracts/prints as primary product:** No raw chains in the first viewport (scanner/workbench are tabs), but the *decision* content stops at attention lists ("Biggest single bets — attention, not conviction"; "a research list, not a buy list"). The user still performs all interpretation that would lead to action — which is precisely the Chairman's complaint.

Darkpool first viewport: verdict sentence ("65 names trading unusually dark; in 29 the hidden volume showed up while the price was rising"), as-of stamp, market gauge (41.5% off-exchange share), "what changed" deltas, three conjunction groups (falling/rising/flat) each with an explicit epistemic statement and a "watching for…" condition, then standout cards with per-name venue attribution. Direction withheld throughout — lawful and correct under the v2 ruling.

**No redesign performed in AD-0** (per handoff §6).

---

## 6. Data-semantic audit

### 6.1 Contract identity
Chains are stored on Polygon per-contract tickers (OCC-style symbol embedded in vendor ticker); there is **no dedicated option-contract identity plane** — no adjusted-contract, special-deliverable, multiplier, or corporate-action-remap handling was found in the chain store or its consumers. Underlying mapping runs through `engine/options_universe.py` (underlying set resolution only) and `engine/stock_identity/` (security identity, LIVE, general-purpose). **Adjudication: AD-1 operates at (underlying, vendor contract ticker) grain, must treat adjusted/nonstandard contracts as a named exclusion with a test, and must not silently aggregate across them.** A formal contract-identity plane is a later-wave item; building one in AD-1 would violate the smallest-slice rule.

### 6.2 Timing (per source field)
- **OI:** market-effective = prior session close of positions; provider publication = next morning; ingestion = 18:30 ET snapshot stamps *the session it describes* (`build_polygon_gex.py:38-50` fixed this); first lawful model use = next session (the Workspace's "positions counted" date is exactly this clock, and the Options Confluence law "no same-day OI" already binds). ΔOI compares to the immediately prior distinct snapshot day (`build_options_flow.py:65-84`).
- **Volume/premium aggregates:** market-effective intraday, ingested EOD (massive) — same-evening lawful.
- **Off-exchange:** CNMS published ~18:00 ET T+0 (collected T+1-effective, §1.1-2); ATS weekly ~T+2wk. Corrections: no correction-ingestion path exists for any options/off-exchange source (correction machinery overall = NOT_BUILT; masterplan assigns it to AD-2).
- **`available_to_model_at`:** the masterplan's observation contract is not implemented anywhere; the closest existing practice is the episode ledger's PIT stance and the `options.prophet_shadow` contract's honest `pit_provenance` block (`promotion_ready: false` because "Current Pick Lab fires expose exact artifact availability … but not an exact decision clock").

### 6.3 Options observation limits (what current code lawfully infers)
Direction from volume/premium is **inferred**, and the code says so: minute tick-rule signing at ~77–83% sign accuracy vs ~81–84% full Lee–Ready, "errors roughly symmetric so they wash in daily aggregates" (`engine/options_flow.py:22-25`). Tone labels derive from signed put/call ratio thresholds (>1.3 bearish/hedging, <0.7 bullish) with net-signed-premium fallback (`engine/options_flow.py:370-397`). Opening/closing state and aggressor side are **unavailable** on entitled sources (massive `trades_v1`/`quotes_v1` 403; ThetaData unwired); "calls opening = bullish lean" on ΔOI is an intent assumption on net-new OI, not a measurement — flagged as such in code. No "sweep" labeling ships (screener direction is "labeled 'notable/unusual heuristic', never 'signal'"). F7 keeps flow direction permanently soft (0.41 calibration; tape signing under active suspend). **These inference limits are the binding constraint on every AD-1 direction claim.**

### 6.4 Positioning models
GEX/dealer surfaces are conventional-sign proxy models (Options Confluence binding laws: "GEX = proxy under assumed sign; positive GEX ≠ upward pressure"). The Workspace presents outputs in plain-stance language over flip/floor/ceiling levels; `gex_confirm` maps to a 3-state verdict. Vanna/charm families exist only as registered stamp columns (`opt_vanna_relief`, `opt_front7_charm_share` — silent-null-guarded via `engine/options_stamp.DISPLAY_TWIN_COLS`) with their directional narratives killed (`OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION`: signed-charm, charm-intensity, DOI-directional, skew-decel kills bind every feature list). UI presents model output as *stance with mechanism*, not as observed dealer inventory — compliant; AD-1 must keep scenario framing.

### 6.5 Off-exchange semantics
Inputs are **FINRA facility aggregates** (ATS weekly + TRF daily short-volume), never print-level, venue known only at ATS granularity with an explicit unattributed residual. Direction logic: none, by design (v2 removed it after a null result; conjunction-with-price grouping replaced it). Condition-code handling: N/A at aggregate grain. "Dark pool" page naming slightly overstates the source (see §5 Q15).

---

## 7. What is useful versus theater (§C adjudication)

- **Act-on-now:** regime tiles, dealer levels with stance, darkpool conjunction groups, "names worth a look" lists — *orientation* value, honestly framed.
- **Still requires manual interpretation:** every step from attention to action (no horizon/trigger/invalidation/asymmetry/Prophet state anywhere).
- **Raw completeness (substrate, not product):** 408-name scanner, per-name workbench, big-bet tables, skew/ivspread/structure artifacts.
- **Unexplained heuristics:** none front-facing (tone thresholds are internal and hedged); the screener's "unusual" label is explicitly heuristic.
- **Display-only scores:** `options.prophet_shadow`, dislocation (self-gated).
- **Real forward-outcome contract:** episode/campaign ledgers (zero authority, correctly).
- **Real consumers:** C1 fusion (`gex_confirm_verdict`), Terminal stockdata pull, NW chat context.
- **Dark:** the entire host intraday fleet, issue desk, focused quote, sparse selector, W1A modules (§2.3).
- **Duplicating another Mastermind system:** none found — no second identity/event/queue/state/publication plane exists in the options estate (the sparse-selector's host-private roots were its own explicit sandbox, not a parallel plane).

---

## 8. Salvage / replace / retire matrix

| Disposition | Component (exact paths) | Reason / target consumer / risk / required proof |
|---|---|---|
| SALVAGE_AS_IS | P1 chain spine (`collectors/polygon_options.py`, `scripts/build_polygon_gex.py`, `data/polygon_gex/*`); P3 darkpool desk (`collectors/finra_*`, `scripts/build_darkpool_desk.py`); P4 flow accrual; P5 GEX/`gex_confirm` chain; P2 Workspace + lanes; P8 NW plane; P9 stockdata export; `engine/ledger_lane.py` gate; `config/synapse.yml` registrations | AD-1's substrate and consumers. Risk: none new. Proof: already live (§2.1). |
| SALVAGE_WITH_ADAPTER | P6 episode/outcome machinery (`engine/options_signal_episode.py`, `scripts/build_options_signal_*`) — reuse the ledger *pattern* + `ledger_lane` gate for AD signal families; do NOT graft AD-1 signals onto existing episode families | target: AD-2/AD-6 calibration. Risk: contract semantics tied to current signal families; adapter must mint a new family id, keep zero authority. Proof: schema review at AD-2. |
| SALVAGE_WITH_ADAPTER | Q3 `scripts/build_options_prophet.py` + `site/options_prophet/index.json` | becomes the seed of the AD-5 Prophet shadow-intake shape (it already models `authority/mode/pit_provenance/abstention`); risk: as_of cadence; proof: a real consumer receipt in AD-5. |
| SALVAGE_WITH_ADAPTER | P10 skew/ivspread/structure artifacts | feature inputs to AD-1 families; risk: display schemas not feature schemas; proof: AD-1 feature tests. |
| KEEP_RESEARCH_ONLY | Sparse-selector estate (`engine/options_sparse_selector.py`, `scripts/run_options_sparse_selector.py`, `ops/launchd/com.mastermind.optionssparseselector.plist`, `ops/launchd/run_options_sparse_selector*`, `research/options_estate/OPTIONS_SPARSE_SELECTOR_*`); W1A modules (`engine/options_market_memory_local_receipts.py`, `engine/options_market_memory_local_replica.py`) | bounded experiment, activation expired/expiring, proposal authority code-closed, zero consumers, receipt roots absent on host. No AD-1 role. The W1A receipt-verifier design may inform AD-2 provenance work — as reading, not as runtime. Risk of salvaging now: resurrecting a governance sandbox as production plumbing. Required proof to ever revive: a masterplan-level ruling + a real consumer. |
| RETIRE (recommend; operator ratifies) | `scripts/build_options_focused_quote.py` (zero invocation sites); `scripts/build_tape_flow.py` standalone lane (superseded by `build_tape_flow_daily.py`); frozen campaign-v1 cohort (`data/options_signal_episode/campaigns.jsonl` — already frozen, formalize); `~/Library/LaunchAgents` stale `.bak`/`.disabled` plists | dead weight that misleads future archaeology. Risk: low (nothing consumes them). Proof: the negative-invocation greps recorded in §2.3. |
| UNKNOWN_PENDING_PROOF | Host intraday fleet re-arm (D1) — whether chainsnapshots/liveflow/optionshub/matrix/NBBO-cohort *should* return under Macro at all, given masterplan law 10 assigns intraday options-flow authority to Terminal | Chairman decision. Required proof either way: a ruling on where intraday lives (AD-9 frames it); until then the units stay uninstalled and unowned. |
| REJECT_DUPLICATE_PLANE | any revival of darkpool direction labels, off-exchange standalone direction, DOI-directional, skew-decel-bullish, second event/identity/queue/state/publication planes | already killed by DNR rows quoted in §2.4. |

Prior session investment was given zero weight in these dispositions (handoff §9 law).

---

## 9. No-rebuild matrix (canonical planes AD-1 must extend)

| Plane | Canonical implementation AD-1 must reuse | Status |
|---|---|---|
| Security identity | `engine/stock_identity/` (authority, census, dossier, episodes, fingerprint, plane, replay) | LIVE |
| Option contract identity | **NONE dedicated** — vendor contract tickers + `engine/options_universe.py` underlying resolution; see §6.1 adjudication | gap, named |
| Event envelope | `engine/neuralweb/envelope.py` (canonical sibling keys: `schema_version, produced_by, produced_at, inputs_hash`, …) | LIVE |
| Source/provenance receipt | `engine/options_market_memory_receipt_store.py` pattern (atomic HEAD pointer) + episode `PRICE_RECEIPT_SCHEMA` (`engine/options_signal_episode.py`) | LIVE pattern |
| Queue / delivery | **NONE distinct** — R2 stage discovery inside `build_options_signal_episode.py` is the only delivery shape; do not invent one for AD-1 (artifact hand-off via render/R2 is the house pattern) | gap, named |
| State / watermarks / degraded | `engine/ledger_lane.py::nightly_advance_enabled()` (forward-ledger advance gate); `engine/research_vault/watermark.py` exists as a watermark pattern (not options-wired) | LIVE |
| Publication | nightly/closing-bell builders → `site/` render lanes (`render.yml`/`engine-render.yml`) → VPS 3-min pull; R2 mirror via `scripts/mirror_flow_idx.py` | LIVE |
| Outcome labels | `data/options_signal_episode/outcomes_h60.jsonl` + `outcomes_session.jsonl` contracts | LIVE (adapter per §8) |
| Prophet shadow intake | `options.prophet_shadow/v1` contract (`scripts/build_options_prophet.py`) + the C1 fusion registry (`engine/us_prophet_fusion.py`) as the only lawful eventual authority door | LIVE producer / gap on consumer receipts |
| Terminal intraday summary | Terminal owns intraday (masterplan law 10); Macro's export contract is `scripts/export_signal_contracts.py` → `site/stockdata/<SYM>.json` | LIVE (export direction) |
| Sector taxonomy | `engine/sector*` / `engine/sector_intelligence/` | LIVE, zero options coupling today |
| Neural Web graph | `config/synapse.yml` registry + `engine/neuralweb/options_plane.py` | LIVE |

---

## 10. The 25 final questions (handoff §17)

1. **Canonical EOD options source:** Polygon.io snapshot (`collectors/polygon_options.py`), massive.com OPRA aggregates for flow; Cboe adapter is legacy.
2. **Current completed source session in production:** chains through 2026-08-14; settled/OI-complete session displayed 2026-08-13 (positions counted 08-14); off-exchange 2026-08-13.
3. **Is the page using that session:** yes — and it says so on its face; the defect is cadence (weekend advance), not honesty (§1.1-1).
4. **Useful before drill-down:** for orientation, yes; for decisions, no — the decision layer is absent (§5, §7).
5. **What labels activity unusual/bullish/bearish:** `engine/options_flow.py:370-397` (signed P/C thresholds + net-premium fallback); ΔOI lean assumptions; screener "notable/unusual heuristic."
6. **Defensible inferences:** market-level tone and ΔOI-based lean with disclosed error bars — yes, as displayed (hedged). Any *per-name directional conviction* is NOT defensible on current sources (no aggressor, no open/close) — the code says so itself.
7. **Canonical off-exchange source:** FINRA CNMS daily + FINRA OTC ATS weekly, keyless.
8. **Does "dark pool" match the source:** content yes, page title slightly overstates (§5 Q15).
9. **Off-exchange direction logic:** none — withheld by design (v2 null result + `DNR:PSS-AF1`).
10. **Options artifacts reaching Prophet today:** `gex_confirm_verdict` (C1 fusion, LIVE); GEX-wall prose post-selection (cannot change rank); `options.prophet_shadow` projection (display-only, no consumer).
11. **Do they affect rank:** yes — exactly one sign of eight in the canonical fusion rank authority.
12. **Shadow vs live:** live = `gex_confirm_verdict` only; everything else shadow/display.
13. **Reaching Neural Web:** `options_structure_block` context + `gex-state-history` display nerve; `options_events` nerve SPEC_ONLY.
14. **Reaching Sector Intelligence:** nothing.
15. **Terminal:** Macro→Terminal `stockdata` gex/gex_confirm + flow-surface contract; Terminal→Macro: nothing.
16. **Receipt/provenance machinery to reuse:** §9 rows 4, 6, 8.
17. **Sparse-selector components still operationally relevant:** none — inert on host, zero consumers, activation expiring 2026-08-21 (§2.3 D2).
18. **Artifacts to retire:** §8 RETIRE row.
19. **Canonical AD-1 output contract:** masterplan §6.2 signal contract projected onto the existing publication plane — exact shape frozen in the AD-1 handoff §5.
20. **Exact production proof for AD-1:** AD-1 handoff §7 (deployed SHA, real session/watermark, algorithm-selected ranked signal, liquid `NO_SIGNAL`, degraded case, receipt, UI/API parity, freshness display).
21. **Paths AD-1 may touch:** AD-1 handoff §2.
22. **Paths AD-1 must not touch:** AD-1 handoff §3.
23. **Smallest useful first slice:** the Daily EOD Options Intelligence Brief as a new first-viewport board on the existing Workspace + one machine projection — AD-1 handoff §1.
24. **Evidence that would fail AD-1 closed:** stale source session, coverage below threshold, missing OI PIT clock, missing `NO_SIGNAL` on a liquid complete-data name, non-algorithmic proof symbol, missing degraded case (AD-1 handoff §§4,6,7).
25. **Any blocker severe enough to hold AD-1:** **No.** AD-1 is READY. Named risks that AD-1 must design around (not blockers): weekend settle cadence (Q1), no contract-identity plane (§6.1), auth-gated JSON proof path (§1), rights-matrix confirmation for any *new public-tier* display (§4).

---

## 11. Open risks

1. **Rights/redistribution posture is unevidenced in-repo** for Polygon/massive-derived displays (current auth-gated posture is consistent but unconfirmed). Confirm before any public-tier expansion.
2. **`/api/health` `commit` vs `checkout` semantics** (16874921e63 vs 7a6a6656e28) inferred, not documented; a deploy-truth doc would remove ambiguity from every future production audit.
3. **Dark-fleet ambiguity compounds:** 15 uninstalled launchd units whose plists remain in-repo will keep reading as "live machinery" to every future census until §8's UNKNOWN_PENDING_PROOF ruling is taken.
4. **Q3 shadow projection** publishes nightly to R2 with no consumer — shadow artifacts without evaluation are exactly masterplan §16.7's discard case; AD-5 must either consume it or retire it.
5. **Friday-close `closing-bell` visibility:** the 5-row `gh` window could not prove whether a Friday-evening run beyond 17:25 ET exists; unproven, bounded query recorded (§1).
6. **Library-imported dark builders** (§2.3 D6): function-level liveness inside live callers was not adjudicated; any retirement action on those files must first check importer call graphs.

---

## 12. AD-0 scope compliance

No collector, workflow, unit, timer, schema, page, template, JS, Prophet, Neural Web, Sector, or Terminal file was modified. No data regenerated, no backfill, no repair. Host probes were read-only (`launchctl list/print`, directory listings). Production probes were read-only HTTP GETs; no credentials minted; auth-gated surfaces recorded as UNPROVEN rather than accessed. Defects found (§1.1, §11) are documented and classified, not fixed.
