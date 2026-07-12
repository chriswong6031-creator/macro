# Flow Continuity — live + EOD options net-flow as one layer, wired to turn surfaces

Status: ADJUDICATED MASTERPLAN (Fable, 2026-07-11). Operator-initiated: "deeply integrate
both live options flow data and EOD options flow data … better able to detect changes in
net inflow outflows and integrate this data into our cycle lobes and engines … get live
signal turns in our systems on a more live and faster way."

Parent context: `research/MAG7_COMMAND_MASTERPLAN_BY_FABLE.md` (#2273) and
`MAG7_TURN_POSTMORTEM_BY_FABLE.md` (companion; numbers below are its recompute-verified
values). The 2026-06-26 episode is the design case: the cohort net premium over our own
Lee-Ready-signed pilot store ran −24.9 → −33.8 → −51.8 → **+146.8 (06-25)** → +60.6
(06-26, the low) → +121.9 → +85.2 → +187.5 (07-01, the META call spike) → +15.6 $M,
while MU stayed put-heavy on 06-23→06-26 and 07-01/02 — a generals-bid / memory-hedge
split that no surface could show because (a) nothing aggregates flow at basket/cohort
level, (b) the EOD summary store was born 07-02, (c) the live poller was TCC-dead until
07-06, and (d) GICS grouping conflates both flows inside "Information Technology".
Honesty bound (red-team, binding on all copy): this is coincident-to-at-most-one-session
-leading — "flow led price" is NOT established, direction signing has not passed its
gate, and every cohort surface built here is visibility, not a signal.

## 0. Census facts of record (2026-07-11, lanes verified against live stores)

| Layer | Store | Universe | History | State |
|---|---|---|---|---|
| EOD Polygon OPRA | `data/options_flow/summary_*.parquet` | 369 names | **born 07-02** (2 rows/ticker) | nightly (cl_gex band); store has no z columns — flow_desk computes z at build with `z_raw_fallback` (<20 obs); direction SOFT (0.41 bar-sign recovery) |
| EOD tape-signed pilot | `data/options_tape_signed/*.parquet` | 20 names (all Mag7; no MU/SNDK) | 2026-01-09 → | Lee-Ready NBBO; per-trade agreement 0.88; session gate still failing → direction_reliable=false |
| EOD tape rich schema | `data/tape_flow/daily/` | SPY+KRE only | 06-30/07-02 | forward accrual just bootstrapped; DTE/moneyness buckets, signed_delta_notional |
| Raw OPRA minute | `data/massive_options_day/` | full OPRA | **2024-07-02 →** | backfill feedstock exists for the whole episode window |
| Live tape | `~/liveflow-ops-wt/` live_flow feed/heat/tide | 122 roots (top-40 published) | day_state since **07-07** (TCC fix 07-06); R2 archives pruned at 48h | cycle measured **~35 min** (full_day mode) vs 120s target; baselines: 18 ETF roots only |
| ETF fund flows | `data/flows/etf_flow_proxy.parquet` | 11 SPDRs | 06-09 → | creation/redemption proxy, not options |
| Surfaces | `site/flow_desk.html` (EOD, display-only) · Terminal live panel · `site/intraday_flow.html` + 30-min fastpath → `site/live/flow_pulse.json` (#2167/#2173, in main since 07-10; pulse shows `mode=no_data` as of 07-10 — FL-C investigates) | — | — | site/flow asof stuck 07-06 (nightly failures 07-08/09 + 07-11 collect cancellation) |

## 1. Case law this build is bound by (census: options-signal rulings)

- Direction is **soft everywhere**: bar-level signing permanently failed (0.41); tape
  signing SUSPENDED for production until ≥5 calibration sessions pass (RUL-F3.12).
  Every direction read ships with the `~`/"direction approx" idiom. No gate, score,
  rank, or escalation may consume signed direction.
- **No composites** (RO-2 / Signal Commons R3): no fused "flow score". Per-leg panels only.
- **DOI is DEAD as a signal** (W-E1): ΔOI put/call renders as descriptive positioning
  context (as flow_desk already does), never as a confluence leg.
- Skew-decel-bullish UNSUPPORTED; signed-charm KILLED; shock-day beneficiary routing
  KILLED; washout×turn standalone KILLED — none may reappear here.
- **W-F is PARKED**: nothing from this program routes into Oracle confluence/NW edges
  until ≥20 sessions of sector-aggregate accrual (~2026-08-01) AND the episode-conditioning
  prereg exist. This program feeds DISPLAY surfaces and forward ledgers only.
- Options→kernel blocked until the 2026-10 clocks. LLMs originate nothing.
- Legal shapes available now: unsigned magnitude (premium z, gross), P/C and call/put
  volume splits, vol>OI bursts, chain-heat persistence, binary flags in turn organs
  (FT-R3), percentile tiers (Flow-Intelligence-v2 pattern), OI_CONFIRMED t+1 join,
  de-escalation-only edges, forward-graded expected-null ledgers (FT-R9).

## 2. Rulings

- **FC-R1 (scope/boundary).** One continuous net-flow layer: per-name and per-cohort,
  intraday (live_flow) + EOD (summary/tape stores), display-tier only. Flow Leaders desk
  (#2216/#2224) keeps the picks/boards lens; FC owns the flow SERIES, cohort aggregation,
  and turn-surface chips. Ratio Lens/Leader Radar/mag7_regime are consumers, not owners.
- **FC-R2 (honesty).** Magnitude, P/C, call/put volume split, gross, zerodte_share are
  the reliable primitives; net-signed values always render soft (`~`). ΔOI = context only.
  The signing gate is never bypassed; when `direction_reliable=false` (now), cohort tiles
  lead with magnitude + P/C and demote soft-net to the hover receipt.
- **FC-R3 (cohort aggregation — the 06-26 lesson).** Basket-membership-keyed flow
  aggregation for `mag7`, `memory_storage`, `ai_semiconductors`, `ai_software` (+GICS
  retained): EOD from the summary store; intraday as a live_flow heat extension keyed on
  `data/baskets/membership.json`. Emits gross, soft-net, P/C, call/put ΔOI, zerodte, and
  a members-covered honesty count (live tape publishes top-40 by premium; memory names
  below MU may be absent — print coverage, never fake it).
- **FC-R4 (backfill).** Backfill `summary_*.parquet` from `massive_options_day`
  (2024-07→): off-render one-shot on the Mac Studio, chunked per-day iteration with
  bounded memory (the 46GB-load freeze is the standing hazard — stream day files, never
  concat years), then z-scores/percentile tiers activate (20-obs minimum met ~25×
  over). The 06-26 episode becomes replayable at EOD grain.
- **FC-R5 (turn confluence, display-tier).** Flow chips on turn surfaces, consuming the
  cohort store fail-open: mag7_regime panel ("options tape: call-tilted 4 of last 5
  sessions ~approx"), basket turn-watch cohort chip, ignition radar (later). Binary /
  persistence framing; de-escalation-capable; NEVER an escalating gate; no composite.
  Forward ledger `cohort_flow.v1` registered expected-null (FT-R9), nightly-advanced.
- **FC-R6 (live latency).** The 35-min full_day cycle is the binding constraint on "live
  signal turns". Remediation is measured, not estimated: test time-window support on the
  installed Terminal, raise `max_concurrent` (currently 2), and if full-day repull is
  irreducible, adopt two-tier cadence (ETF anchors + Mag7 + memory members every cycle;
  long tail rotated). Success metric: p50 event-to-publish ≤ 5 min for tier-1 roots.
- **FC-R7 (baselines).** Extend EOD-252 baselines from 18 ETF roots to the full poll
  universe (explicitly Mag7 + memory members) from `thetadata_eod` — bounded-memory job;
  prem_z stops being null for single names.
- **FC-R8 (persistence).** Stop losing intraday history: a compact per-day
  end-of-session summary (per-name + per-cohort: gross, soft-net, P/C, minutes-of-data,
  data-quality flags) written to `data/live_flow_daily/` by the nightly (sole advancer;
  idempotent). Raw archives keep the 48h R2 TTL; the summary is permanent. Retroactive
  replay of 06-26 stays impossible — that loss is accepted and documented.
- **FC-R9 (statement tape — conditions-framing only).** A deterministic administration
  market-statement event tape: extend the existing whitehouse lane pattern (it already
  LLM-scores whitehouse.gov posts for banner activation — sanctioned curation) with a
  curated, source-linked registry of dated public market statements (Truth Social /
  transcripts; collector if a reliable free source exists, else operator/session-appended
  registry file like ONE_OFF_CLOSURES). PS-R1 stands: NO intent prediction, NO timing
  forecast, NO LLM-emitted probabilities. The "presidential buy-endorsement" history
  (2018-12-26 durable low; 2025-04-09 durable low, statement hours before policy action;
  2020-03-13 ten days early, −10% further first) ships as a field-guide exhibit with the
  honest n≈3 base — an event catalog, not a signal.
- **FC-R10 (signing calibration ops).** Schedule the ≥5 calibration sessions the
  suspension requires (harness exists, RUL-F3.12; sessions must span calm + high-VIX).
  Operator-visible clock; direction promotion happens through the gate or not at all.
- **FC-R11 (freshness).** site/flow asof stuck at 07-06 while today is 07-11: the flow
  builder gets the same staleness ::warning idiom as build_baskets (Mag-7 Command PR-A),
  and the post-incident root cause is documented in the lane PR.
- **FC-R12 (W-F non-circumvention).** Cohort aggregates feed display + ledgers only.
  The sector-episode prereg (W-F precondition 2) may be drafted as its own document on
  its own clock — it is NOT this program and nothing here waits on it.

## 3. Build lanes (all display-tier; file-disjoint; fail-open ordering)

| PR | Lane | Contents |
|---|---|---|
| FL-A | EOD backfill + z | backfill script over massive_options_day (off-render one-shot, memory-bounded), z/percentile activation, site/flow staleness warning (FC-R4/R11) |
| FL-B | cohort flow engine + desk strip | `engine/flow_cohorts.py` EOD rollup keyed on membership.json → `data/options_flow/cohorts.parquet` + `site/flowdata/cohorts.json`; flow_desk.html "Cohorts" strip (Mag 7 / Memory / AI chips / Software tiles: gross, P/C, soft-net~, ΔOI context, coverage count); synapse/DAG reg; doctrine copy (FC-R2/R3) |
| FL-C | live lane ops | poller latency remediation measured (FC-R6), baselines extension (FC-R7), tier-1 root guarantee (Mag7+memory always published), permanent per-day summary store (FC-R8), calibration-session scheduling note (FC-R10) |
| FL-D | turn-confluence chips | mag7_regime artifact + panel flow block, basket turn-watch cohort chip, `cohort_flow.v1` expected-null forward ledger (FC-R5) — **dispatch AFTER Mag-7 Command PR-D merges** (template collision) |
| FL-E | statement tape + exhibit | whitehouse-lane extension / curated statement registry + collector feasibility, field-guide exhibit with the 3-case catalog (FC-R9) |

Ordering: FL-A/B/C/E parallel now; FL-B ships with raw-magnitude fallback until FL-A's
backfill lands (same z_raw_fallback idiom flow_desk already uses). FL-D held for the
Mag-7 Command surfaces merge.

## 4. What this does NOT do

No signed-direction gates, no flow composites, no Oracle/NW wiring (W-F parked), no
kernel conditioning, no DOI/skew-decel/charm revivals, no LLM-originated signals, no
claim that flow "predicts" turns — the cohort layer is context + disclosure
infrastructure whose forward ledger will say, in time, whether any construction earns a
promotion prereg.

## 5. Clocks

- 2026-07-14: FL-A backfill complete; z tiers live; first cohort tiles on flow_desk.
- 2026-07-18: live-lane latency remediation measured result (FC-R6 metric).
- 2026-08-01: W-F precondition (1) accrual read (context only; separate program).
- 2026-08-15: first `cohort_flow.v1` ledger read (descriptive).
- 2026-10-15: promotion decision window (with Mag-7 Command clocks).
