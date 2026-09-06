# Flow Observatory V2 — Masterplan, Design Freeze, and Wave Plan (by Fable)

`operation_key: macro-flow-observatory-v2-program-20260902-sol-001`
`f0_child: macro-flow-observatory-v2-f0-freeze-20260902-fable-001`
`status: F0 FROZEN — implementation waves W1..W7 + final acceptance authorized`
`owner: WS:FLOW-OBSERVATORY-V2 (program: china-system)`
`authority: context_only — this program may not create predictive, ranking, sizing, gating, or trade authority`
`frozen_at_base: origin/main 2a1c871d0a6d7345e864b37f6d1d88a399c0f1ce (2026-09-02)`

This document is the single durable home for the Flow Observatory V2 program: the
Chairman-approved outcome, the current-state archaeology, the architecture freeze, the
frozen data/semantics/experience contracts, and the child-wave implementation plan. A cold
worker must be able to execute any wave from this file plus the cited owners, without the
commissioning conversation.

---

## §0 Program acceptance gates (not done unless)

The program is complete only when ALL hold, in production, with receipts:

1. **Truth**: every source leg shows identity, source kind, effective date, coverage, and
   quality state on the page; stale/missing/degraded data cannot render as current/neutral;
   absolute flow and relative pressure are separate fields AND separate user-facing labels;
   curated themes are never presented as official sectors; corrections append, never
   overwrite.
2. **Fixture truths** (verified against real data at freeze, see §2.1): the Autos-class
   case (absolute 4wk flow negative, relative pressure positive) renders as
   "still selling, pressure easing" semantics — never unqualified inflow; the
   Southbound-class case (+¥7.1B 1m absolute, −1.52σ relative) shows both numbers
   non-contradictorily; neutral and unscored populations are explicit counts.
3. **Product**: trust strip → what-changed → absolute-vs-relative read → drilldown →
   research follow-up all work; the twelve final-acceptance fixtures of the program packet
   pass; dark/light are separately art-directed; EN/ZH parity; 1440/390 proof; zero console
   errors; no horizontal page scroll.
4. **Method**: the shipped relative-flow method and thresholds carry a committed,
   preregistered descriptive evaluation; the #3561 causal-demean benchmark remains
   reproducible; authority stays context_only (group-flow forecast weights stay zero).
5. **Delivery**: every wave merged to origin/main through green concluded CI, live bytes
   verified on the VPS, Agent OS records current, and the parent program closed with a
   terminal evidence RESULT on the commissioning carrier.

No wave may ship a fused composite score (DNR:KILL-FUSED-COMPOSITE), a regime scorecard
(DNR:KILL-REGIME-SCORECARD), an un-gauntleted directional call (DNR:KILL-FORCED-CALLS), a
revived per-stock Northbound accumulation product (WS-CHINA-ALPHA-INTELLIGENCE do_not_redo),
a second membership truth store, a second alert/analytics plane, or a runtime CSS system in
JS. The engine's in-code honesty gate (per-name CN fund-flow rank-IC ≈ −0.008, never scored
into allocation — engine/flow_velocity.py:31-35) survives every wave verbatim.

---

## §1 Outcome and thesis (Chairman-approved)

Transform `flow_velocity.html` from an attractive but semantically overstated normalized-flow
dashboard into a production-proven **Flow Observatory** for serious China/HK market users: a
source-separated, correction-safe, point-in-time, coverage-aware flow context surface. A user
lands after the close and answers within one screen: Is the source current? What changed?
Is the market/group actually receiving net money, or merely less-negative than its own norm?
How broad, how persistent, how concentrated? Which names drove it? What should I investigate
next? — with real data, honest nulls, and no predictive overclaim.

Primary persona: self-directed investor / analyst / portfolio researcher monitoring
A-shares + HK. Machine job: a flow context object downstream products can consume without
confusing order-size proxies with investor identity, absolute flow with relative pressure,
curated themes with official sectors, source recency with build recency, missing with
neutral, or descriptive context with predictive authority. The moat is the lawful
combination of A-share large-order proxy history, Connect aggregates, Southbound per-name
holdings, event-selected Dragon-Tiger seat context, PIT membership + overlap disclosure,
correction-safe history, contribution/episode analysis, and visible receipts.

---

## §2 Current-state archaeology (measured 2026-09-02 at 2a1c871d0a6d)

### 2.1 Live fixture measurements (acceptance fixtures for semantics, not permanent facts)

Committed `site/flowdata/desk.json`:

```text
top-level as_of 2026-09-01 · ashare legs 2026-09-01 · hk_names 2026-08-31 (divergence live now)
northbound frozen 2024-08-16 (HISTORICAL_ONLY)
southbound: flow_1m_b=+7.1 (¥B), vel 1m=−1.52, accel=−0.042, state="accelerating out"/加速流出
cn_autos: vel=+2.58, accel=−0.009, rate_4wk=−0.9, rate_norm=−2.8, rate_rel=+1.9,
          state="inflow cooling"/流入降温  ← absolute-negative + relative-positive conflation
sector states: 6 accelerating in · 4 inflow cooling · 11 balanced · 1 accelerating out (n=22)
names: n=1518 scored; unscored names silently dropped (no n_unscored anywhere)
```

The two headline defects are live: Southbound's hero chip says "accelerating out" with the
+¥7.1B absolute sum visible only on a card below (no reconciliation); Autos' board figure is
`rate_rel=+1.9%` in inflow color while raw 4wk flow is −0.9% (raw visible only in a hover).

### 2.2 Pipeline map (owners to extend — verified by line)

- **Engine**: `engine/flow_velocity.py` (644 lines) — velocity = slope_z on causally
  demeaned cumulative flow (126d names/sectors, 252d aggregate) with 0.25× expanding-std
  vol floor (#3561); `_classify()` vocabulary at :147-156; true-count contracts in
  `momentum()`/`confluence()`; `snapshot()` gates on any-leg-present (:588-590);
  single top-level as_of fallthrough at :599-606.
- **Builder**: `scripts/build_flow_velocity.py` (148 lines) — fully additive, every stage
  try/excepted, never red (:8, :92-138). Staleness via `lib/desk_guard.stale_legs`
  (LEG_LAG_MAX_DAYS=4, DESK_MAX_AGE_DAYS=10) → `::warning` annotations ONLY; no page
  branch renders staleness (only northbound `live=False` special case, template :755-757).
- **Template**: `templates/flow_velocity.html.j2` (852 lines) — zones: hero (:422),
  rotation board (:502), momentum (:548), confluence (:584), flow map drilldown (:620),
  Stock-Connect channels (:729). i18n `t(en,zh)` macro; JS-off graceful; server-rendered;
  sparklines are build-time SVG. Committed page carries post-render externalized CSS
  (`assets/css/*.css?v=`) — the canonical artifact is builder output + `lib/pages.py`
  asset sweeps; never hand-commit raw builder output as site truth.
- **Sources** (5 legs): `data/china_connect/{southbound,northbound}.parquet` (Eastmoney
  aggregate; southbound 2014→, northbound frozen), `data/tushare/flow_hist.parquet`
  (Tushare moneyflow_dc 主力 large+super-large order net-rate grid, ~260d contiguous daily
  tail, min_obs=90, TUSHARE_TOKEN-gated), `data/china_lhb/detail.parquet` (Dragon-Tiger
  机构专用 anonymous seats, append-only PIT, latest snapshot consumed),
  `data/hk_southbound/holdings.parquet` (per-name holdings deltas, depth=503 sessions).
- **Workflows**: asia-close.yml `brun flow_velocity` (:534) + daily.yml ORDER list; both
  resilient wrappers.
- **Tests**: `tests/test_flow_velocity.py` (10 tests — measure-null/vol-floor/true-count/
  rate-vs-σ-consistency class), `tests/test_flow_desk_staleness.py` (16 tests — desk_guard
  budgets, holiday suppression, wall-clock backstop, annotation shapes).
- **Downstream desk.json consumers**: `engine/cn_theme_tape.py` reads
  `ashare_sectors.rows[].state/state_zh` verbatim (:247-249, :460-467; FLOW_MAX_AGE_DAYS=7)
  and `tests/test_cn_theme_tape.py:110-111` pins "accelerating in"/"加速流入"/"balanced"/
  "均衡" — **any vocabulary change must update this consumer + tests in the same wave**.
  ~15 additional grep-hit files (admin/brief.py, scripts/build_ai_desk_page.py,
  scripts/oracle_nightly.py …) are unverified consumers: W1 must run a consumer sweep
  before changing any existing field's meaning (additive evolution preferred everywhere).

### 2.3 Adjacent organs (extend, never duplicate)

- **Curated membership truth**: `engine/baskets_china.py::_membership()` ←
  `data/baskets_china/membership.json` (22 baskets, hindsight-curated, per-member
  added/removed dates, overlap real: 5 tickers in 2 baskets). HK sibling
  `engine/baskets_hk.py` ← `data/baskets_hk/membership.json` (17 baskets). THS sibling
  store exists (`data/baskets_china_ths/`). These stay the curated-theme truth.
- **Official sectors**: `collectors/china_sectors.py` — Shenwan L1 INDEX family (31 codes,
  akshare, keyless): index OHLCV + valuation ONLY. **Constituent-level official membership
  is NOT_BUILT** (zero index_member/index_classify/sw_index_cons hits repo-wide;
  `engine/group_flow.py:252-253` states no PIT membership outside US). Tushare point-tier
  for membership endpoints: never evaluated in-repo.
- **Price-plane sibling**: `engine/group_flow.py` — rotation fingerprint on price returns
  over the same 22 baskets; display-only; `data/group_flow/validation_meta.json` keeps
  forecast weights at zero. Flow Observatory owns the money-flow plane; group_flow keeps
  the price plane; neither absorbs the other.
- **Ledger patterns** (reuse for W3): interval PIT membership
  (`data/breadth/sp1500_pit_membership.parquet` — ticker/start_date/end_date rows);
  append-only nightly-guarded episode ledger (`data/group_pulse/episodes.parquet` via
  `engine.ledger_lane.nightly_advance_enabled`); JSONL forward ledgers
  (`data/trial_ledger.jsonl`, `data/alerts/watchlist_alerts.jsonl`).
- **Calendars**: `lib/cn_calendar.py` (SSE/SZSE, Golden Week Oct 1-7, Spring Festival) and
  `lib/hk_calendar.py` (HKEX observance) — two owners, correctly separate.
- **Alert/watchlist owners**: `engine/watchlist_sentinel.py` (pure logic, ENTER-only,
  cooldown) → `data/alerts/watchlist_alerts.jsonl` → `engine/alert_triage.py`; client
  `templates/watchstore.js`.
- **Analytics owners**: Umami (pageview, theme.js:88-105) + first-party `/api/collect`
  beacon (theme.js:111-150+, GFW-safe, feeds `analytics_events`). W7 uses `/api/collect`.
- **Identity**: `lib/dataos/identity.py` spine; tickers `.SS/.SZ` (CN) join across stores.
- **Market-cap**: `total_mv`/`circ_mv` collected daily in the Tushare spine
  (collectors/china_tushare_spine.py:233-237) — cap-weighted views are data-feasible;
  no basket organ cap-weights today.

### 2.4 Capability ledger (reclassified at freeze)

| Capability | State | Evidence |
|---|---|---|
| Daily generated page + artifact | PROVEN_LIVE | builds reproduced locally from real data (22 sectors/1518 names/341KB) |
| Normalized velocity math | BUILT_NOT_PROVEN | #3561 mechanics tested; economic thresholds uncalibrated (W5) |
| Honest source/investor semantics | BROKEN | "big money"/"Institutions" sites mapped §2.2; proxies overstated |
| Absolute-vs-relative separation | PARTIAL | fields exist; primary copy blurs (Autos/Southbound live fixtures) |
| Source-specific freshness display | PARTIAL | per-leg as_of in JSON; HK date never rendered; hero shows one date |
| Fail-visible stale publication | BROKEN | advisory ::warning only; 12-day freeze precedent (#4676); no page branch |
| Curated-theme breadth | PARTIAL | real; overlap (5 dupes) and unscored population undisclosed |
| Official/non-overlapping sector breadth | NOT_BUILT | index-level SW L1 only; no constituent membership anywhere |
| Identified institutional ownership | NOT_BUILT | anonymous seats + size tiers only — stays NOT_BUILT by design |
| PIT observation/revision history | PARTIAL | source stores PIT-ish; no product-level state/transition ledger |
| Contribution/sensitivity | PARTIAL | top-8 members exist; no concentration/without-top1 contract |
| History/compare/watch workflow | PARTIAL | drilldowns exist; no episodes, compare, or watch integration |
| Predictive/trading authority | REJECTED_BY_DESIGN | validation_meta weights zero; stays zero |
| Product-learning instrumentation | PARTIAL | pageview only; no typed interaction events |

---

## §3 Source taxonomy freeze

Six legs, each with a stable `source_id`, `source_kind`, and per-source freshness budget
measured in the OWNING market's trading days (calendar owners §2.3):

| source_id | source_kind | provider | market | cadence / budget | notes |
|---|---|---|---|---|---|
| `cn_large_order_proxy` | large_order_size_proxy | Tushare moneyflow_dc (主力 = super-large+large order tiers) | CN | T+0 after CN close; STALE > 1 CN trading day behind newest CN session (calibrate W2) | 1,518 names; NEVER "institutions"/"big money" unqualified |
| `sb_aggregate` | official_connect_aggregate | Eastmoney RPT_MUTUAL_DEAL_HISTORY | HK | T+0; STALE > 1 HK trading day (calibrate W2) | deep (2014→) |
| `hk_sb_holdings` | official_connect_holdings | Eastmoney RPT_MUTUAL_STOCK_HOLDRANKS | HK | **expected T−1**; STALE > 2 HK trading days (calibrate W2) | per-name holdings deltas; coverage n_sized/n |
| `nb_aggregate` | official_connect_aggregate | Eastmoney (discontinued disclosure) | CN | HISTORICAL_ONLY, frozen 2024-08-16 | never rebuilt (do_not_redo) |
| `lhb_inst_seats` | event_selected_institution_seat | Eastmoney 龙虎榜 机构专用 | CN | event-window snapshot | anonymous seats; event-selected sample; never a market-wide census |
| `sw_l1_sectors` | official_sector_aggregate | Shenwan L1 via akshare (`collectors/china_sectors.py`) | CN | daily index; constituent membership = W4 forward accrual | current-only membership until history accrues; honest unavailable before that |

Curated themes (`baskets_china` 22, `baskets_hk` 17) are aggregation LENSES over
`cn_large_order_proxy` / `hk_sb_holdings`, kind `curated_theme_aggregate`, overlap_allowed
= true, membership_as_of = the store's dated rows. They are not sources and never named
"sectors" in user copy.

---

## §4 Data contract freeze — `flow_observatory.v2`

**Home**: `site/flowdata/desk.json` evolves ADDITIVELY in place — it is the existing
product artifact with existing consumers; a second artifact for the same data is a
duplicate system. Adaptations of the program packet's schema to this home:

- New top-level keys (W1→W3, additive): `schema: "flow_observatory.v2"`,
  `authority: "context_only"`, `generated_at` (build instant — never a source time),
  `market_session` (newest valid CN session or null), `publication_state`
  (HEALTHY|DEGRADED|STALE|UNAVAILABLE|HISTORICAL_ONLY|REVISED — worst-of live legs, W2),
  `sources: []` (per-leg blocks: source_id/kind/provider/market/effective_date/observed_at/
  ingested_at/first_known_at/revision_id/status/expected_availability/coverage
  {n_eligible,n_observed,n_sized,pct_names}/null_reason/receipt_ref — W1 dates+coverage,
  W2 status+receipts), `market_read` (absolute_breadth, relative_breadth,
  acceleration_breadth — each positive/negative/neutral/missing/denominator — W1) and
  `change_summary` (previous_valid_session, material_change, transitions[], rank_movers[],
  source_revisions[] — W1 minimal, W3 full).
- Per-group rows (ashare_sectors.rows[], hk boards) gain additively: `abs`
  {period:"20d", value, unit, direction}, `rel` {value, unit:"sigma", direction,
  reference_window}, `quadrant` (§6 enum), `quadrant_en/zh`, `state_started`,
  `state_age_sessions`, `prior_state`, `rank`, `rank_change`, `n_covered`,
  `coverage_pct`, `overlap_count` (W4), `concentration` {top1_share, top3_share,
  without_top1_direction} (W4), `quality` {status, confidence, reasons} (W2).
- Existing keys are preserved through the transition. **Vocabulary exception**: the
  existing `state`/`state_zh` strings are themselves the conflation (absolute words on a
  relative measure), so W1 re-vocabularizes them (§6) and updates the known consumer
  (`engine/cn_theme_tape.py` + `tests/test_cn_theme_tape.py`) in the same PR, after a
  consumer sweep of the ~15 grep-hit files (§2.2).

Contract laws (binding every wave): unknown/missing ≠ zero; stale ≠ neutral; build time ≠
source time; one top-level date never implies shared leg dates; absolute and relative are
separate fields AND labels; every cross-sectional statistic declares denominator +
coverage; theme overlap explicit; corrections append revisions (§5); replay reconstructs
knowable-at-time state (W3); no LLM writes any deterministic value or state.

Schema validation lives in `engine/flow_observatory/contract.py` (new, W1) — pure
assembly/validation, no I/O; builder composes through it.

**Module layout freeze**: `engine/flow_velocity.py` keeps velocity math + panel builders.
New focused package `engine/flow_observatory/`: `contract.py` (W1), `quality.py` (W2),
`changes.py` (W1 minimal, W3 full), `history.py` (W3), `groups.py` (W4). Builder entry
stays `scripts/build_flow_velocity.py`; route stays `flow_velocity.html`; no second page.

---

## §5 Time, freshness, null, and correction freeze

**Clocks kept distinct** (fields in §4): market effective date (`effective_date`), source
observation time (`observed_at`, where the feed exposes one), ingestion time
(`ingested_at`), first-known time (`first_known_at` — when OUR pipeline first held the
value), build instant (`generated_at`), revision time (`revised_at` on revision rows).

**Source state machine** (deterministic, per leg, W2 — `engine/flow_observatory/quality.py`):

- `HEALTHY`: within the leg's §3 budget in ITS market's trading days, readable shape,
  coverage within normal band.
- `DEGRADED`: current enough to use, but coverage/row-count/completeness below the leg's
  calibrated normal band (e.g. scored-name collapse vs trailing median — thresholds
  calibrated in W2 against measured history, committed as constants with rationale).
- `STALE`: beyond budget; last-good values may render ONLY with unmistakable watermark.
- `UNAVAILABLE`: no usable observation (absent/unreadable/sub-min_obs).
- `HISTORICAL_ONLY`: deliberately discontinued (northbound); never counted stale.
- `REVISED`: a previously published effective observation changed; revision receipt shown.

Budgets use `lib/cn_calendar` / `lib/hk_calendar` — never wall-clock day counts alone
(Golden Week must not fire); the existing wall-clock desk backstop (DESK_MAX_AGE_DAYS=10)
is retained as the total-freeze catch-all. The existing `lib/desk_guard` thresholds are the
starting points; W2 calibrates each leg's budget against measured source behavior and
records the evidence in the W2 PR (a budget is never preserved merely because it existed).

**Publication behavior** (W2): builder computes per-leg status BEFORE render; page always
renders (an outage never yields an empty "no flow" page) with first-screen trust state;
`publication_state` = worst-of-live-legs; expected T−1 (hk_sb_holdings) is HEALTHY with an
"expected T−1" chip, not DEGRADED; a missing source renders "unavailable — not zero flow";
machine receipts land in `sources[]`; `::warning`/`::error` annotations stay; persistent
degradation (≥2 consecutive sessions) escalates to `::error` + job-summary line in the
asia-close lane (the lane's existing ops surface); one optional leg never takes down
healthy legs (engine's additive shape preserved); source dates are never rewritten to
build dates.

**Corrections** (W3): append-only. `data/flow_observatory/observations.parquet` holds one
row per (entity, effective_session, revision_id) with first_known_at/revised_at; original
rows are never mutated; current view = latest valid revision; replay(t) = rows with
first_known_at ≤ t; product recomputation marks affected sessions `REVISED` in
change_summary. Advancement is guarded by the `engine.ledger_lane` pattern (group_pulse
precedent) — the asia-close/nightly lane advances; intraday/manual lanes cannot; duplicate
advancement is idempotent by key. W1 ships the minimal precursor
`data/flow_observatory/state_log.jsonl` (one line per valid session: per-group
state/rank/velocity/abs summary, idempotent per session) so change/onset/age accrue from
W1 forward with honest "first tracked session" nulls; W3 subsumes it into the parquet
ledger and keeps the JSONL as a derived compact view or retires it explicitly (no silent
second truth store).

---

## §6 Source semantics and frozen user-facing vocabulary

**Language law** (per source, binding all copy, EN and ZH):

- `cn_large_order_proxy`: "large-order pressure" / "large & super-large order-size proxy" /
  "main-force order-size classification" (主力大单净流, 大单口径). BANNED unqualified: "big
  money", "institutions are buying", "institutional accumulation", "smart money",
  "大资金", "机构买入". The page hero/section titles using 大资金 (template :434-444, :506)
  are re-copied in W1.
- `lhb_inst_seats`: "Dragon-Tiger institutional-seat confirmation on recent event-selected
  names" (龙虎榜机构席位·事件样本); always disclose event-selection, window, overlap count;
  never "N institutions" or a market-wide vote.
- `sb_aggregate`: always show absolute cumulative amount AND relative pace AND direction of
  change together (worked example §7).
- Curated themes: "N of 22 tracked themes above their own relative-flow threshold; M
  neutral; K below" — never "N China sectors drawing money".

**Quadrant enum** (per group/aggregate, from `abs.direction` × `rel.direction`, W1):

| enum | EN (Tier 1) | ZH (Tier 1) |
|---|---|---|
| `true_accumulation` | real inflow, above norm | 真实流入·高于常态 |
| `improving_but_still_selling` | still selling, pressure easing | 仍净流出·压力改善 |
| `weakening_but_still_buying` | still buying, pace fading | 仍净流入·动能转弱 |
| `true_distribution` | real outflow, below norm | 真实流出·低于常态 |
| `neutral_or_unknown` | quiet / insufficient data | 平静 / 数据不足 |

Near-threshold, below coverage floor, stale, or missing → `neutral_or_unknown` (honest
neutral band; thresholds from W5, provisional ±0.5σ / |abs| below a calibrated de-minimis
until then).

**Relative-axis vocabulary v2** (replaces the current `state` strings, which use absolute
words for a relative measure; consumer update in the same W1 PR — §4):

| old (engine :147-156) | new EN | new ZH |
|---|---|---|
| accelerating in | above norm, rising | 高于常态·升温 |
| inflow cooling | above norm, cooling | 高于常态·降温 |
| accelerating out | below norm, worsening | 低于常态·加剧 |
| outflow easing | below norm, easing | 低于常态·趋缓 |
| balanced | near its norm | 接近常态 |
| n/a | no data | 无数据 |

Breadth gauge vocabulary ("broad inflow"/"broad outflow"/"mixed") splits into two labelled
axes (W1): relative breadth ("pressure above norm in X of N") and absolute breadth ("net
money actually positive in Y of N") — the current single gauge is the packet's named
conflation and does not survive.

**Worked fixture copy** (frozen semantics, exact strings tunable within them at W1 design
review): Southbound hero: "Southbound still bought +¥7.1B over the last month — but the
pace is 1.5σ below its own norm and fading." (南向近一月仍净买入 71亿, 但节奏低于常态
1.5σ且转弱。) Autos row: quadrant label "still selling, pressure easing" with the raw abs rate
(e.g. −0.9%) and the σ velocity (e.g. +2.6σ) shown as separate figures at rest, not
tooltip-only. (Corrected 2026-09-04: the original text wrote "+1.9σ", conflating the
demeaned percent rate_rel with the σ velocity — the shipped page is the correct form.)

Falsifier/refutation language never appears front-facing (house law, #3821); degraded
states use plain words ("source behind — showing last good data from Sep 1" / 数据滞后 ·
显示9月1日最近有效值).

---

## §7 Experience architecture freeze

**Archetype**: `intelligence_desk` (E) — L1 budget 6, identity device = dated brief cards
with graded source chips (MASTER_PRODUCT_DESIGN_SYSTEM §10). Same route, same shared nav
(`_site_nav` family), tokens extend theme.css only, LENS tooltips, `.dtp` freshness family,
illus for any new chart; no third header, no runtime stylesheet, no Plotly.

**L1 composition** (6 sections, order fixed; everything else demotes to LENS/drilldown):

1. **Desk header + verdict** — one plain-language market read generated from BOTH axes
   (e.g. "Large-order pressure improved vs norm in 10 of 22 themes, but only N saw
   positive absolute 20-day flow — no material transition since Sep 1."), one `.dtp`
   session stamp, stance vocabulary (typically "Watch — don't chase" family).
2. **Trust strip** (the E-archetype source-chip device, W1 dates/coverage + W2 states):
   one chip per §3 leg — plain name, kind in plain words, effective date, expected
   cadence, coverage, status; LENS receipt with method/provider detail. Trust renders
   BEFORE the verdict band on first paint (source state precedes market claims).
3. **What changed today** (W1 minimal vs previous valid session; W3 full) — material
   transitions, threshold crossings, rank movers, revisions, new degradation; explicit
   quiet state: "No material flow-state transition since the previous valid session."
4. **Absolute × relative market read** — the two-axis quadrant (groups plotted abs-20d ×
   rel-σ) with table alternative + accessible text; independent absolute/relative/
   acceleration breadth counts including neutral, missing, and unscored populations.
5. **Groups board** (rotation board evolved) — per-group row: quadrant label, abs figure,
   rel figure, acceleration, coverage, rank change, state age; official-sector lens
   SEPARATED from curated-theme lens (W4 tabset within the section; official tab honest-
   unavailable until membership accrues); drill to members (existing accordion) with
   contribution/concentration/without-top1 (W4).
6. **Cross-border channels** (existing section, truth-repaired) — Southbound abs+rel+accel
   together; Northbound HISTORICAL_ONLY card unchanged in spirit; HK holdings leg shows
   its OWN date + expected-T−1 chip.

Deeper (Tier 2/3, behind LENS/drilldowns/`<details>`): momentum/confluence panels
(demoted into groups board + LENS receipts), 60-session histories + state bands +
revision markers (W6), group compare + prior episodes (W6), per-name Terminal links (W6),
method/receipts tooltips (every panel).

**Failure/empty states are designed states** (design system §9.12): all-healthy, expected
T−1, degraded-coverage, stale-with-last-good (watermark + "showing last good" line),
unavailable leg, HISTORICAL_ONLY, no-material-change, no qualifying groups, insufficient
coverage, revised source, official-lens-unavailable, long-ZH labels, 390px narrow. Each has
an explicit design in the W1/W2 PRs' evidence matrices — never a bare "—", never pipeline
telemetry in customer copy.

**Theme art direction** (TP-0 law): dark = command-center (luminance depth, restrained
glow; degraded/stale = desaturated amber watermark band + dimmed panel treatment); light =
research workspace (white material, hairline discipline, shadow not glow; degraded/stale =
tinted paper + 3px rail + deepened ink — designed independently, not token-swapped). Every
material-UI PR ships the evidence matrix dark/light × EN/ZH × 1440/390 plus interaction
proof, zero console errors, no clipped dates/labels, no horizontal page scroll. Design
choices happen in the main loop or `designer` (opus) — never a sonnet builder (design
lane law); builders implement fully specified specs.

---

## §8 Statistical method and calibration freeze (W5)

Benchmark preserved: causal demeaned slope_z with 0.25× expanding vol floor and 20/65/126/
252-day windows (#3561) — it stays reproducible whatever wins. Candidates evaluated
against it on PIT history: (a) current method; (b) winsorized mean/vol demeaning;
(c) median/MAD location-scale; (d) causal empirical percentile vs own trailing window.
Preregistration (`research/flow_observatory/W5_PREREG.md`) commits BEFORE evaluation runs:
hypotheses, windows, metrics, decision rule. Metrics: state distribution (no verdict
>80% of days, both extremes reachable — the #3561 null-construction test generalized),
one-day flip rate, state persistence/duration, outlier sensitivity (quiet-series and
spike fixtures), denominator/coverage-change sensitivity, revision sensitivity,
concordance between official aggregate and proxy legs where they overlap, and
interpretability. Threshold calibration (±0.5σ velocity, ±25 breadth tilt, quadrant
de-minimis, coverage floor) selects for meaningful separation from normal + stable
duration + controlled false flips + honest neutral mass — never for attractive balance or
frequent movement, never against future returns. All causal/PIT; heavy replay runs off
the render path (scripts/research_* + committed report + machine-readable summary);
forward-return exploration, if any, is preregistered, PIT, autocorrelation-and-multiplicity
controlled, and CANNOT change product authority (context_only; a positive result is not
promotion — separate program required).

---

## §9 Official-sector / curated-theme boundary ruling (W4)

- Curated themes stay the `baskets_china`/`baskets_hk` stores — overlapping, disclosed
  ("overlaps N other themes" per member; theme board carries overlap counts and
  membership_as_of). Never renamed "sectors".
- Official lens = Shenwan L1. W4 extends `collectors/china_sectors.py` (the existing
  official-sector owner — NOT a second collector family) with constituent membership via
  akshare's keyless SW constituent endpoint if it proves available at implementation time;
  storage follows the interval PIT pattern (`data/china_sectors/membership.parquet`,
  ticker/l1_code/start_date/end_date), seeded current-snapshot, accruing forward. The lens
  ships labeled "official sectors (申万一级) — current membership; history accrues from
  first collection"; historical official-sector replay is refused (honest unavailable)
  until real accrued history covers the window. (Superseded 2026-09-04 for the W6
  history drawers: disclosed replay under the pinned current-membership caption is the
  ratified form — DEC:FLOW-OBSERVATORY-V2-OFFICIAL-LENS-REPLAY-DISCLOSED; the
  published-record tier stays accrual-gated.) If no lawful keyless endpoint exists, the
  lens ships as designed-unavailable with the exact gap recorded — curated baskets are
  NEVER relabeled as the official lens, and no paid dataset is purchased in this program.
- Coverage law (both lenses): every group statistic declares n_members/n_covered/
  coverage_pct; below the calibrated coverage floor → `insufficient_coverage`, never a
  survivor-biased read. Equal-weight stays primary; cap-weighted variant (total_mv from
  the Tushare spine) may ship as a clearly-labelled secondary view where data supports it.
- Contribution contract (W4): per group top-positive/top-negative contributors, top1/top3
  share, without-top1 direction flip, contributors reconcile to the aggregate within
  tolerance, excluded/missing members visible.

---

## §10 History, corrections, and replay (W3) — see §5

Deterministic replay test vector: same inputs → byte-identical ledger tail; replay at
historical first_known excludes later revisions; onset survives same-state sessions;
missing session ≠ false transition; stale session does not advance state age; rank changes
compare a consistent eligible universe; duplicate advance idempotent; non-owner lane
cannot mutate. UI: state age ("3rd session in this state"), prior state, revision markers
in change history.

---

## §11 Research workflow (W6) and product learning (W7) — owners

W6 uses existing owners only: watch/alert through the watchlist store + sentinel + triage
pattern (alerts fire on state ONSET / quadrant transition / material change — never daily
values; dedup/cooldown per the sentinel's existing contract; stale data cannot fire; a
correction produces a revision notice, not a duplicate alert); Terminal deep links through
the existing ticker-identity contract; compare/episodes server-rendered from the W3
ledger. If a workflow owner is not live for some action, ship the lawful subset and record
the dependency — no parallel alert engine. W7 instruments through the existing
`/api/collect` first-party beacon envelope only (typed `flowobs_*` events: trust-strip
open, what-changed expand, quadrant/group select, drilldown, Terminal handoff, watch
create), documented + deduplicated, no PII/holdings, no new transport, no effect on flow
state; live canary receipt required.

---

## §12 Wave graph (frozen decomposition — one PR, one observable capability each)

Serial execution, each wave: fresh worktree off fresh origin/main, `claude/<child>` branch,
failing tests first, canonical rebuild, PR with §16-packet body, concluded-green CI,
independent review where consequential, same-day squash-merge, live verification, Agent OS
update. Child keys per program packet §13.

| Wave | Observable capability | Primary paths |
|---|---|---|
| **F0** (this PR) | Durable freeze: masterplan + WS/DEC/handoff records merged | research/, agentos/ |
| **W1** | Trust strip (dates/coverage), truthful two-axis labels + quadrants, re-copied proxy language, minimal what-changed + state_log, market_read breadth (incl. neutral/unscored), consumer-safe vocabulary migration | engine/flow_velocity.py, engine/flow_observatory/{contract,changes}.py, scripts/build_flow_velocity.py, templates/flow_velocity.html.j2, engine/cn_theme_tape.py, data/flow_observatory/state_log.jsonl, docs/site_semantics/china.md, tests/* |
| **W2** | Binding per-leg quality states + fail-visible publication + watermarks + calendar-aware budgets + receipts + ops escalation | engine/flow_observatory/quality.py, lib/desk_guard.py, scripts/build_flow_velocity.py, scripts/check_tushare_freshness.py, template, .github/workflows/asia-close.yml, tests |
| **W3** | Append-only product ledger, revisions, replay, full change/transition/onset/age | engine/flow_observatory/history.py + changes.py, data/flow_observatory/observations.parquet, tests |
| **W4** | Official-vs-curated lenses, coverage floors, contribution/concentration/sensitivity, overlap disclosure | engine/flow_observatory/groups.py, collectors/china_sectors.py, data/china_sectors/membership.parquet, template, tests |
| **W5** | Preregistered method/threshold evaluation + calibrated constants + committed report | research/flow_observatory/W5_PREREG.md, scripts/research_flow_observatory_methods.py, reports/, engine constants (only on evidence), tests |
| **W6** | Histories, compare, episodes, drilldown-to-Terminal, watch/alert via existing owners | template, engine/flow_observatory/history.py, alert owners, tests |
| **W7** | Typed product-learning events via /api/collect + live canary | templates (page JS), docs, tests |
| **Final** | Independent adversarial review vs the 12 program fixtures + terminal RESULT | — |

Per-wave test obligations are the program packet §14 lists (failing-first + mutation
checks: temporarily restore the conflated labels/the silent-stale render and confirm the
new tests fail). Every wave's PR body carries: mission, base receipt, changed paths,
contract behavior, before/after, tests, mutation evidence, real-data proof, visual matrix
(when UI), performance note, limitations, authority boundary.

---

## §13 No-rebuild boundaries (binding)

Forbidden in every wave: second flow collector for an existing source; second market
calendar; second membership truth store; page family duplicating Group Reads/China
Intelligence; second alert/analytics/provenance/correction/queue/scheduler/identity/
publication plane; a "Flow Observatory database" beyond the §5 ledger pattern; composite
flow/conviction score or cross-source rank (DNR:KILL-FUSED-COMPOSITE,
DNR:KILL-REGIME-SCORECARD, GROUP_READS G0-2); LLM-originated states; runtime CSS-in-JS;
Northbound rebuild; beneficial-owner inference from size buckets; US/other-market ports;
navigation redesign; trade/allocation authority (DNR:KILL-FORCED-CALLS; validation_meta
weights stay zero).

---

## §14 Disagreement ledger and rulings (with rejected alternatives)

1. **Contract home** — RULED additive desk.json evolution. Rejected: parallel
   observatory.json (duplicate artifact, split consumers).
2. **Vocabulary migration** — RULED replace `state` strings with relative-explicit
   vocabulary + same-PR consumer updates (cn_theme_tape + pinned tests + consumer sweep).
   Rejected: keep old strings + parallel new field (leaves the live conflation shipping
   indefinitely on china.html's theme tape).
3. **W1 change-comparison source** — RULED minimal state_log.jsonl precursor, subsumed by
   W3. Rejected: waiting for W3 (W1 would ship no change read); git-history reads at build
   time (runtime dependency on VCS — brittle, unlawful on runners).
4. **Official sector lens** — RULED SW L1 forward-accrual via existing collector +
   honest current-only labeling. Rejected: relabeling curated baskets (forbidden);
   hindsight backfill (violates PIT law); Tushare membership endpoints (entitlement
   never evaluated, token-gated — unnecessary when a keyless owner extension exists;
   re-evaluate inside W4 only if akshare lacks the endpoint).
5. **Program ownership** — RULED new WS-FLOW-OBSERVATORY-V2 under program china-system
   (no existing WS owns the surface; china-alpha is Prophet-ordering; intraday-flow is a
   different page; international-risk fences out China). Rejected: new program/lobe
   (duplicate architecture); absorbing into WS-CHINA-ALPHA-INTELLIGENCE (disjoint scope,
   different landmines).
6. **Museum risk** — the current page's 6 zones + W1-W6 additions exceed the archetype-E
   L1 budget; RULED the §7 six-section composition with momentum/confluence demoted into
   the groups board + LENS. Rejected: keeping all current sections + adding new ones
   (13-section museum, the census-measured estate defect).
7. **desk_guard budgets** — current LEG_LAG_MAX_DAYS=4 counts calendar days; RULED W2
   re-bases budgets on per-market trading days with holiday suppression preserved
   (existing tests keep passing or are updated with evidence). Disagreement preserved:
   the 4-day calendar budget has NOT misfired on record (holiday test exists) — W2 must
   measure before replacing.

Known open questions deliberately deferred INTO waves (not placeholders — each has an
owner wave + decision rule): exact quality-band constants (W2, calibrated + evidenced),
akshare SW-constituent endpoint availability (W4, with designed-unavailable fallback),
method/threshold selection (W5, preregistered), alert-owner integration depth (W6, lawful
subset rule §11).

---

## §15 Collision and path-ownership map (at freeze)

Zero open PRs / remote branches touch the owned paths (searched: flow_velocity, flowdata,
desk_guard, tushare collectors, group_flow, baskets_china; branches
claude/trumpflow-promote and codex/hk-sector-flow-rotation-research verified zero
owned-path overlap). Owned paths for this program: `engine/flow_velocity.py`,
`engine/flow_observatory/**`, `scripts/build_flow_velocity.py`,
`templates/flow_velocity.html.j2`, `site/flow_velocity.html`, `site/flowdata/**`,
`data/flow_observatory/**`, `lib/desk_guard.py`, `scripts/check_tushare_freshness.py`,
`data/china_sectors/membership.parquet` (W4), flow tests. Shared-touch paths (coordinate,
don't own): `engine/cn_theme_tape.py`, `collectors/china_sectors.py`,
`docs/site_semantics/china.md`, asia-close/ci workflows. Collision search repeats before
every wave PR (fast-moving repo).
