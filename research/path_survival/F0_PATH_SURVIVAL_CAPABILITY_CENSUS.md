# F0 — Path Survival / Holdability Capability Census

**Commission:** MASTERMIND GROK-F0  
**As-of:** 2026-08-18  
**Tree:** `origin/main` @ `3d12412e561e`  
**Status:** read-only census. No model was fit. No rank/gate/size/execution was changed.

**Verdict (strongest true claim):** The estate already has **three** close/path graders — `engine/grading.py` (canonical Outcome Spine), `engine/track_scoring.py` (forced-H=10 board episodes, including `capture` = realised/MFE), and `engine/entry_radar/replay/outcomes.py` (OHLC + ATR, Radar-only). Path Survival must extend the first and make the others callers. A fourth grader would be a second grading system.

Evidence tags used below: **CODE VERIFIED**, **PRODUCTION VERIFIED**, **PRIMARY SOURCE VERIFIED**, **INFERRED**, **UNKNOWN**.

---

## 1. What "canonical grader" already is

`engine/grading.py` is the house Outcome Spine v2 (Setup-Species masterplan §1.1 / §5.1). It is a library, not a runner.

Four honesty axes (module docstring, lines 11–48) **CODE VERIFIED**:

1. Next-bar fill (`fill_index`: first bar strictly after the signal bar).
2. Survivorship (`as_of_panel` + `sp1500_pit_membership.parquet` + cold-start stamp).
3. Dual return basis (`total_return` vs `price_return`); most US stores only expose TR.
4. Delisting terminals (`resolve_series` + `data/edgar/dead_name_prices.parquet`).

Path primitives already in the spine **CODE VERIFIED**:

| Primitive | Function | What it actually measures |
|---|---|---|
| MFE | `forward_metrics` → `fwd_mfe_{H}` | `max(0, max(close[fill+1..fill+H]) / entry − 1)` |
| MAE (named MDD) | `forward_metrics` → `fwd_mdd_{H}` | `min(0, min(close[fill+1..fill+H]) / entry − 1)` |
| Horizon return | `fwd_ret_{H}` | `close[fill+H] / entry − 1` |
| Target-before-stop | `terminal_state` | close-basis sequential race: −5% vs +5% vs liftoff |
| Time to stop / cushion / liftoff | `stopped_at_bar`, `cushion_at_bar`, `liftoff_at_bar` | 1-indexed bars from fill |
| Cushion incidence | `cushion_incidence` | % of ALL fires cushioned by day k; stop is competing risk |
| Post-cushion breach | `post_cushion_breach` | after +5%, did any later close fall back below entry? |
| Short-side mirror | `terminal_state_short` | adverse +5% vs favorable −8%/−15%; no cushion/dead-money split |

**Not** in the spine: high/low first-passage, ATR-scaled barriers, gap-through-stop, false-start (Radar clause A/B), close-location-of-range, overnight-vs-RTH, post-entry time-underwater. Path-efficiency analogue `capture` lives on `track_scoring`, not on the spine. `stopped_at_bar` / `cushion_at_bar` are computed but **not persisted** on live `track_record` / `grade_us_board` rows (state string only).

Price basis of the spine **CODE VERIFIED** (`grading.py` 32–40, 132–133, 315–317):

- Expected input = dividend-adjusted total-return **close**.
- Barriers are ratios to the fill-bar close, so the adjustment cancels in the percentage.
- High/low are never read. Same-bar target/stop tie is **close-only**: stop is checked first on that close (`grading.py` 361–364). The high/low straddle rule is pre-registered in prose only (`SETUP_SPECIES_MASTERPLAN` §1.1: "stop wins on a straddle bar") and is **not wired**.

Fill default **CODE VERIFIED**: next-bar close. `same_bar=True` exists only for shadow A/B and is documented as biased.

Horizons **CODE VERIFIED**: `SPINE_HORIZONS = (5, 10, 21, 63, 126)`; `DEFAULT_HORIZONS = (20, 60, 180)` for older track-record callers.

PIT **CODE VERIFIED**: next-bar fill cannot peek at the signal bar; forward window is strictly `(fill, fill+H]`; immature horizons stay `None`. Membership as-of is PIT from 2026-06-13 (`universe_history`) else `pit` else `cold-start`.

Live-forward **PRODUCTION VERIFIED** (workflow text, not a live URL check): `.github/workflows/daily.yml` runs `python -m scripts.grade_us_board --nightly` and `scripts.build_track_record`. Both write spine columns via `engine.grading`.

---

## 2. Per-metric record

For each commissioned metric: owner, implementation, price basis, adj/unadj, fill, same-bar tie, gap handling, horizons, PIT, live-forward.

### 2.1 MFE

| Field | Canonical spine | Radar replay | Mastermind bot |
|---|---|---|---|
| Owner | `engine/grading.py` | `engine/entry_radar/replay/outcomes.py` | `portfolio/held_risk.py` |
| Impl | `forward_metrics` → `fwd_mfe_{H}` | `attach()` `mfe = max(0, path_high/P0 − 1)` | `_lane_extension_giveback` `mfe_pct = (post_entry_high − entry)/entry` |
| Price basis | daily **close** max | daily **high** max (+ optional LIVE day-0 samples) | live `post_entry_high` (INFERRED: last print / daily high, not a shared primitive) |
| Adj | TR close (Yahoo/stocks convention) | vendor plane of the episode (`p0_basis` stamped) | UNKNOWN (whatever the bot's mark is) |
| Fill | next-bar close | P0: `sampled_last_trade_at_decision` / `first_trade_after_known_at` / `next_session_close` | actual entry price of the book |
| Tie | n/a (excursion, not a race) | n/a | n/a |
| Gap | close-only: a gap is invisible except as the next close | high/low see the print; open used only for gap-through-invalidation | UNKNOWN |
| Horizons | 5/10/21/63/126 (and 20/60/180) | primary H=10; secondary 3/5/21 | since-entry, no horizon |
| PIT | yes (strictly forward) | yes (W5 prereg; FIT/TEST/holdout) | live marks; not a research grader |
| Live-forward | yes, via `grade_us_board` / `track_record` | **no** — local `data/entry_radar/ledger_state.json` is `WAITING_FOR_LIVE_SOURCE`, `forward_rows_total=0` **PRODUCTION VERIFIED** 2026-08-18 | yes, operational |

QLedger: **does not compute MFE**. `grade_claim` writes `subject_ret` / `excess` / `hit` only **CODE VERIFIED** (`engine/qledger.py` 2660–2778).

Setup Species: does not compute MFE itself. It **mandates** MFE as a context metric (`SETUP_SPECIES_MASTERPLAN` §1.1) and consumes the spine via board/track-record ledgers. `engine/species_registry.py` is display-only metadata. `docs/GRADING_CLOSURE.md` marks `species_registry` **GRADER-STARVED** (21 logged, 0 graded) **PRIMARY SOURCE VERIFIED**.

Stock Identity: no trade MFE. Episode fields are `depth_pct` / `depth_atr` plus two **close** recovery stats — `post_trough_63d_atr` and `sessions_to_50pct_retrace` — **CODE VERIFIED** (`engine/stock_identity/episodes.py` 95–115, 315–329). W2 **strips** ledger `fwd_mfe_*` / `terminal_state_*`. W3 localization ruler (MAE/MFE/cushion/stop) is `todo`.

### 2.2 MAE

| Field | Canonical spine | Radar replay | Mastermind bot |
|---|---|---|---|
| Owner | `engine/grading.py` | `outcomes.attach` | none dedicated |
| Impl | `fwd_mdd_{H}` (min close, capped ≤ 0) | `mae = min(0, path_low/P0 − 1)` | giveback is *after* MFE, not MAE |
| Price basis | close min | **low** min (+ day-0) | n/a |
| Fill / PIT / horizons | same as MFE | same as MFE | n/a |

Naming hazard **CODE VERIFIED**: the spine calls the close-min excursion `fwd_mdd`, not `mae`. Radar calls the high/low excursion `mae`. They are **not the same statistic**. Path Survival must not merge the names.

### 2.3 Target-before-stop

Three **different** races already exist. Do not collapse them.

1. **Spine terminal_state** — fixed % barriers vs fill close: stop 0.95, cushion 1.05, liftoff 1.08@21 or 1.15@126. Close-sequential; stop wins on the same close. **CODE VERIFIED** `grading.py` 271–427.
2. **Radar target_before_invalidation** — ATR-scaled: target = P0 + 1.00×A0, invalid = P0 − 1.25×A0. First-touch on **highs/lows** (day-0 samples then sessions). Equal-position tie is **adverse-first**. **CODE VERIFIED** `outcomes.py` 165–179 and `prereg.py` 67–72.
3. **Mastermind brain/outcomes.py** — close triple-barrier +15% / −10% / time. Target checked **before** stop on the same close (target-wins, opposite of the spine). Anchor = last close on/before `state_asof` (same-bar-ish, not next-bar). **CODE VERIFIED** `brain/outcomes.py` 24–27, 108–120.

China standout track computes the *same named states* as (1) but on a **T+1 HL2 fill**, never via `grading.fill_index` **CODE VERIFIED** (`engine/china_standout_track.py` 42–57, 356–373).

### 2.4 Cushion incidence

**Owner:** `engine.grading.cushion_incidence` only.

- Denominator = ALL gradable fires, never reachers. Stop is competing risk. k ∈ {5,10,21} default.
- Close-basis. Next-bar fill.
- Live-forward: available as a library call; nightly board rows carry per-fire `cushion_at_bar` only via `terminal_state`, not the aggregate incidence table. **INFERRED** from `grade_us_board` writing `terminal_state_*` and `post_cushion_breach`, not `cushion_incidence`.

Radar does not compute cushion incidence. Its analogue is false-start rate (ATR, high/low).

### 2.5 Post-cushion breach

**Owner:** `engine.grading.post_cushion_breach` (per fire) and the aggregate rate inside `cushion_incidence`.

- Semantics: cushioned, then any later close < entry inside the window. Cushioned-then-stopped is True by definition.
- Written onto US board rows by `scripts/grade_us_board.py` at horizon=21 **CODE VERIFIED** (lines 1075–1170).
- CN board: `engine/cn_prophet_audit.py` treats it as a three-valued COST flag **CODE VERIFIED**.

Mastermind `giveback_pct_of_mfe` is related but **not the same**: it is (high − now) / (high − entry) after MFE, not "did we lose the +5% cushion."

### 2.6 False starts

**Not in the canonical grader.**

| System | What "false start" means | Status |
|---|---|---|
| Live Entry Radar | Clause A: MAE ≥ 1.25×A0 before MFE ≥ 1.00×A0 (high/low first-touch, adverse-first). Clause B: confirmed StochRSI K<20 AND low below washout low. Close-proxy ATR excluded (None). | **CODE VERIFIED** `outcomes._false_start` |
| Oracle onset | `false_start_rate` of onset-tier *alerts* before 5-day confirmation | different object; not a trade path |
| Setup Species | "BASED chip" = passive survival predicate, falsified | different object |
| Stock Identity | calibrator mentions a false-start threshold when choosing N,k,z | not a shipped path metric |
| Spine / QLedger / Mastermind bot | absent | — |

### 2.7 Gap-through-stop

**Not in the canonical grader.** Close-only spine cannot see an open that gaps through a barrier.

Radar implements `gap_through_invalidation`: `open < invalid AND prior_close >= invalid` **CODE VERIFIED** `outcomes.py` 180–181. Requires an `open` column.

Stock Identity: `data/stocks` has **no open** (~240 deepest names). Gap family is excluded on that plane rather than masked **CODE VERIFIED** `engine/stock_identity/plane.py` 21–25.

Setup Species: high/low (hence gap) "becomes binding the day full-universe high/low history is wired" **PRIMARY SOURCE VERIFIED** masterplan §1.1. Not wired in `grading.py`.

`entry_primitives.gap_hold_events` exists but is **DORMANT** (appendix-locked) and is a setup detector, not a post-entry path metric **CODE VERIFIED** `entry_primitives.py` 651–666.

### 2.8 Time to failure

| System | Field | Clock |
|---|---|---|
| Spine | `stopped_at_bar` | trading bars from fill, close-touch of 0.95× |
| Radar | `time_to_failure` | 0 = day-0 sample; else session index+1 of first adverse ATR touch or washout-low break |
| Mastermind outcomes | `exit_date` when `barrier=="stop"` | calendar date of first close ≤ −10% |
| Stock Identity | `duration_sessions` | episode length, not post-entry failure |

### 2.9 Time to cushion

Spine: `cushion_at_bar` (first close ≥ 1.05×). Radar: `time_to_positive` (first close > P0) and `time_to_mfe` (argmax of highs). These are not interchangeable.

### 2.10 Time underwater

**Not a post-entry path metric anywhere.**

`engine.entry_primitives.time_underwater_series` = bars since the trailing-252 **close** high. Used by `engine/neuralweb/bottom_sensors.py` as an *entry-context* / de-escalation feature, not as "bars the position has been below fill" **CODE VERIFIED**.

### 2.11 Path efficiency (`capture`)

**Not absent.** `engine/track_scoring.py` already ships `capture` = realised PnL / MFE, median over matured episodes, with `MFE_FLOOR` so a never-green path is `n_capture_undefined` rather than a flattering ratio **CODE VERIFIED** (`track_scoring.py` 79–87, 399–417). Units are **percent**, forced verdict at `DEFAULT_HORIZON=10`, close-path only.

`engine/grading.py` does **not** emit capture. Radar outcomes do **not**. `track_record` Kaufman ER is a **pre-entry** regime feature, not this statistic. The contract draft should reuse `capture`, not invent `path_efficiency`.

### 2.12 Close-location

**Absent as a post-entry path statistic.**

Near-misses (different questions):

- `entry_primitives.donchian_pos_series` — where close sits in a 20-bar high/low channel (entry feature).
- Mastermind `entry_quality._fast_metrics` — 60d close range percentile (advisory pre-entry).

Neither is "where the close printed inside [low, high] on each post-entry bar."

### 2.13 Reversal frequency

No post-entry reversal-count on the spine.

Radar clause B is one reversal *definition* (K re-entry + washout-low break). Stock Identity *is* a reversal-process catalog (`reset_decline` / `reclaim` / `failed_breakdown`) but it labels historical paths, not trades. Setup Species is a trigger taxonomy, not a reversal-frequency grader.

### 2.14 Overnight versus regular-session contribution

**Absent as a graded split** on the spine and on QLedger.

Radar LIVE episodes *declare* `day0_samples` (session-D remainder after T) as position 0 in MFE/MAE/false-start. **CODE VERIFIED gap:** `outcomes.attach` reads `episode.extra["day0_samples"]`, but no producer under `engine/entry_radar/` sets it (grep = the one reader). Production attach therefore grades **D+1…D+H daily H/L only** unless a caller injects the extra. The secondary minute-path outcome table named in `outcomes.py` 8–10 is **not implemented**.

Minutes themselves are not a durable store. `engine/entry_radar/vendor_minutes.py` fetches Polygon aggregates `adjusted=true` per episode window, caches completed sessions only, and is used for C3 4H buckets — not for overnight/RTH PnL split **CODE VERIFIED**.

`data/tushare` has no minute partitions on this checkout. `collectors/tushare_minutes_plane.py` is a gated CN nominal-minute plane; `data/tushare_minutes` does not exist here **CODE VERIFIED**.

---

## 3. System-by-system owners

| System | Role vs path quality | Reuses `engine.grading`? |
|---|---|---|
| `engine/grading.py` | Canonical close-path spine | — |
| `engine/track_scoring.py` | Forced-H=10 board-episode MFE/MAE/`capture`/stop/early-exit | **no** (parallel close-path scorer; US next-bar close, CN T+1 open) |
| Setup Species | Declares the spine; registry is metadata; ledgers GRADER-STARVED; S7 harness has a research-only H/L MAE | yes, via board/track-record — not via `species_registry` |
| Live Entry Radar | Third grader (OHLC + ATR) for W5 replay; W4 live eval is outcome-blind | **no** |
| Stock Identity | Path-*anchored episode catalog* + close recovery stats; W3 ruler still `todo` | **no** (W2 strips spine columns) |
| Evaluation OS / QLedger | Horizon-end signed excess + hit; clock/promotion law | fill *semantics* migrated toward next-bar; does **not** call `forward_metrics` / `terminal_state` |
| Mastermind `held_risk` | Live holdability / giveback flags (heuristic v0); close-path `mae_pct` written and **unused** | **no** |
| Mastermind `entry_quality` | Advisory *pre-entry* stretch/chase | **no** |
| Mastermind `brain/outcomes` | Thesis triple-barrier + rel_return | **no** (reads Macro yahoo closes via `equity_alloc.index_close`) |
| CN standout track | Same named spine states, market-native T+1 HL2 fill | constants only, not `fill_index` |

---

## 4. Candidate / episode stores

| Store | Path | What it holds | Path metrics on the row? |
|---|---|---|---|
| US board grades | written by `scripts/grade_us_board.py` | per-fire spine cols | `fwd_mfe_*`, `terminal_state_*`, `post_cushion_breach` |
| Signal archive | `data/signal_archive/track_record.parquet` | track-record spine | same family (W0.1a) |
| QLedger claims/grades | `data/qledger/{claims,grades}.jsonl` | horizon-end excess/hit | no MFE/MAE/cushion |
| Radar live ledger | `data/entry_radar/ledger_state.json` | W5 state machine | **0 forward rows** locally |
| Radar replay outcomes | in-memory `OutcomeRow` / W5 result tables under `research/live_entry_radar/` | full OHLC path set | yes |
| SI episodes | `engine/stock_identity/episodes.py` → `data/stock_identity/` | decline/reclaim/failed_breakdown | depth/duration, not MFE/MAE |
| Species registry | `data/species/registry.json` | metadata | none |
| Mastermind theses | Mastermind `brain/ledger` | rel_return + barrier | close triple-barrier |

---

## 5. What this census refuses to infer

- That Radar MFE equals spine `fwd_mfe` (high vs close; P0 vs next-bar close).
- That Mastermind giveback is post-cushion breach.
- That "false start" is one house definition.
- That minute coverage exists for a first-passage study. It does not, as a store.
- That QLedger will grow path columns. Eval-OS `do_not_redo` and promotion law are horizon-end / clock / control-leg work.

---

## Search bounds (absence claims)

- `engine/grading.py` read in full (997 lines).
- `engine/entry_radar/replay/outcomes.py` + `prereg.py` read in full / head.
- `engine/qledger.py` `grade_claim` / `_fwd_ret` / `_fill_entry`.
- `engine/stock_identity/{episodes,plane}.py`.
- `engine/species_registry.py` header + `docs/GRADING_CLOSURE.md`.
- Mastermind `portfolio/held_risk.py`, `portfolio/entry_quality.py`, `brain/outcomes.py`.
- Greps: `path.?efficien`, `close.?location`, `gap.?through`, `false.?start`, `time.?underwater`, `fwd_mfe`, `terminal_state`, `cushion_incidence` over `engine/` and Mastermind `portfolio/`+`brain/`.
- Not searched: every research notebook, every CN collector partition, live VPS `data/entry_radar/forward.parquet` (absent locally).
