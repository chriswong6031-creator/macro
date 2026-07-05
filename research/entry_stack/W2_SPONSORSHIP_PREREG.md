# W2 — Subsector Rotation Sponsorship: Pre-Registration (SRSS Phase 1)

**Status: DEFERRED — accrual-blocked. This document freezes the study design; it does
NOT authorize running the study for a promotion-grade verdict today.**

Source research: `research/SUBSECTOR_ROTATION_SPONSORSHIP_NEURAL_WEB_RESEARCH.md` §5,
§8.5. Phase 0 harness: `research/entry_stack/sponsorship_phase0.py`. Phase 0 output:
`research/entry_stack/_out/sponsorship_phase0.parquet`.

---

## 1. Status header — why this is frozen but not running

Phase 0 joined `data/research/gate_fires_deep.parquet` (38,250 stock-level gate fires,
1962–2026) to the point-in-time subsector-rotation ledger
`data/subsector_rotation/snapshots.jsonl` on a strict nearest-prior-date-only basis
(no future leak, per source doc §8.5 timing-mismatch rule). The live run result:

```
total events:               38,250
events with rotation match: 24 (0.06%)
distinct subsectors matched: (see Phase 0 run log)
sponsorship_state, matched subset only:
  TAILWIND               8
  CONFIRMED_LEADERSHIP   6
  NEUTRAL                8
  HEADWIND               2
  EARLY_REPAIR           0
  ROLLOVER               0
```

The rotation ledger (`data/subsector_rotation/snapshots.jsonl`) has **6 distinct
trading days of history** (2026-06-28 through 2026-07-05). Its own track-record
verdict is `accruing`, `any_matured: false` (source doc §1.3). This is not a
data-quality bug — the ledger is young by construction, and 0.06% coverage is the
direct, expected consequence of joining 64 years of stock fires to 6 days of PIT
rotation state.

**Two of the six frozen contrasts (B1 EARLY_REPAIR, B4 ROLLOVER) have zero matched
observations at all as of this run.** There is no n to report for those arms, let
alone a rate to project forward from.

### Rough accrual projection (order-of-magnitude only — expect this to be wrong)

Observed rate: 24 matched events / 6 trading days ≈ **4.0 matched events/day**,
across whichever sponsorship states happen to fire that day. Two components:

- **Optimistic case** (assumes the 4/day rate eventually spreads roughly evenly
  across all six states as more subsectors churn through more quadrants):
  ~4/day ÷ 6 states ≈ 0.67 events/day/state → `400 / 0.67 ≈ 600 trading days`
  ≈ **~2.4 years** (using ~252 trading days/year) to reach n=400 for a
  representative arm.
- **Conservative case** (uses the actual weakest *observed* non-zero arm,
  HEADWIND, at 2 matches in 6 days ≈ 0.33/day): `400 / 0.33 ≈ 1,200 trading
  days` ≈ **~4.8 years**.
- **EARLY_REPAIR (B1) and ROLLOVER (B4)**: zero observations in 6 days means
  there is currently no basis to estimate a rate at all. These two contrasts
  cannot be scheduled on a timeline yet — they are unknown, not merely slow.

**This projection is a straight-line extrapolation from a 6-day sample and should
be treated as almost certainly wrong.** Rotation quadrant transitions cluster with
market regime (a rally concentrates `improving`/`leading` days; a broad drawdown
concentrates `weakening`/`lagging` days), so the true arrival process is bursty,
not Poisson-uniform. The honest takeaway is not "~2.5–5 years," it is "**not
computable as a reliable date; re-estimate the rate every time the ledger doubles
in length** (12 days, 24 days, 48 days, …) rather than trusting this extrapolation."

---

## 2. Primary research questions

Adapted from source doc §5.1, unchanged:

1. **Bottom-fire lift.** Conditional on an existing stock bottom fire, do
   TAILWIND / EARLY_REPAIR sponsorship states improve 21D bottom-capture outcomes
   versus neutral/headwind states, after controlling for date effects and
   baseline stock signal tier?
2. **Top-risk lift.** Conditional on an existing stock top-risk/extended fire, do
   ROLLOVER / HEADWIND sponsorship states improve top-risk outcomes versus
   neutral or tailwind states?

Both questions are conditional — sponsorship is never proposed as a standalone
stock signal (source doc §3.1, §4.1).

---

## 3. Frozen contrasts (B1–B6)

No arms may be added mid-run without increasing the registered trial count
(source doc §5.5, restated as a hard rule here).

| ID | Contrast | Fire population | Status as of this run |
|----|----------|------------------|------------------------|
| B1 | EARLY_REPAIR vs all others | bottom fires | **0 matched events** — unscheduled |
| B2 | TAILWIND vs all others | bottom fires | 8 matched events |
| B3 | HEADWIND vs all others | bottom fires | 2 matched events |
| B4 | ROLLOVER vs all others | extended/top-risk fires | **0 matched events** — unscheduled |
| B5 | continuous `sponsorship_score` deciles | bottom fires | 24 matched events total (score deciles not meaningfully populated) |
| B6 | continuous `sponsorship_score` deciles | top-risk fires | not yet separated from B5 population in Phase 0 output |

---

## 4. Endpoints

### 4.1 Bottom endpoints (primary)

| Endpoint | Definition |
|---|---|
| `stop5` | Hits −5% before +5% within the horizon. |
| `mae21` | Maximum adverse excursion in the first 21 trading days. |
| `clean8_21` | Hits +8% before invalidation/stop within 21 trading days. |
| `zone_held_21` | Vol-scaled entry zone held through 21 trading days (no stop-out). |
| `days_to_10` | Trading days to +10% return, capped at horizon or null if not reached. |

### 4.2 Top endpoints (primary)

| Endpoint | Definition |
|---|---|
| `drawdown_21` | Max drawdown in the 21 trading days after a top-risk warning fires. |
| `failed_breakout_21` | Breaks below the 21D low or below the trigger-date low within 21 days. |
| `relative_underperformance_21` | Stock return minus group (subsector) or SPY return over 21 days. |
| `giveback_21` | Percentage of the prior 21D/63D run surrendered after the warning. |

### 4.3 Computability today — what exists vs what needs new work

Checked against `data/research/gate_fires_deep.parquet` (columns: `ticker`, `date`,
`tier`, `sub`, `ticks`, `not_topped`, `eligible`, `panel`) and
`data/neuralweb/spine_index.parquet` (columns include `fwd_mfe_5/10/21/63/126`,
`outcome_excess`, `outcome_graded`, `terminal_state_clean8_21`,
`terminal_state_clean15_126`, `quad_hard_label`, `direction`, `score`).

| Endpoint | Computable now? | Notes |
|---|---|---|
| `clean8_21` | **Yes, directly** | `spine_index.terminal_state_clean8_21` already exists as a graded terminal state — reuse, do not recompute. |
| `mae21` | **New computation needed** | Neither table carries a raw MAE column; `fwd_mfe_21` is *favorable* excursion, not adverse. Would need a fresh MAE pass off price data (same plumbing as `derived_dist_proxy` in Phase 0, i.e. `engine.ai_desk._close_series`). |
| `stop5` | **New computation needed** | Not present as a named field on either table; derivable from raw forward price paths, not from `fwd_mfe_*` alone (those are single-sided max-favorable, not path-dependent barrier hits). |
| `zone_held_21` | **New computation needed** | No existing "zone" concept on these two tables; would require the entry-zone definition from the entry-quality/durable-bottom stack (not yet joined here). |
| `days_to_10` | **New computation needed**, but cheap | Derivable from the same forward-return series used for `fwd_mfe_21`/`fwd_mfe_63` if the underlying daily path (not just the horizon-max) is retained. |
| `drawdown_21` | **New computation needed** | Same gap as `mae21` — needs adverse-excursion computation, not currently on either table. |
| `failed_breakout_21` | **New computation needed** | Needs the trigger-date low and a break-check against subsequent lows; not on either table. |
| `relative_underperformance_21` | **Partially computable** | `spine_index.outcome_excess` already appears to be an excess-return field (excess vs a benchmark) — needs a one-line check that its benchmark matches "group or SPY" before reuse; do not assume without verifying the benchmark definition used to build it. |
| `giveback_21` | **New computation needed** | Needs both the prior-run magnitude and the retracement since top — not on either table. |

**Bottom line:** only `clean8_21` is a clean reuse from `spine_index`, and
`outcome_excess` is a probable-but-unverified reuse for
`relative_underperformance_21`. The remaining seven endpoints require new
forward-return computation before Phase 1 can run — this is additional build
work not yet scoped or estimated, and it is blocked anyway by the 0.06%
match-coverage problem above (no endpoint computation fixes a sample-size
problem).

---

## 5. Controls

Minimum controls (source doc §5.6), with Phase-0-confirmed field names:

- **Date fixed effects** — or same-date cross-sectional estimator.
- **Signal tier** — `gate_fires_deep.tier` (T1–T4).
- **Freshness** — `derived_freshness` in Phase 0 output, which is a direct reuse
  of `gate_fires_deep.ticks` (ticks-since-fire). This is an existing, already-
  vetted field, not a new proxy.
- **Distance-from-low** — `derived_dist_proxy` in Phase 0 output. **This is
  explicitly a proxy, not a validated field.** It is computed as
  `close / rolling_21d_low(shift 1) − 1` via `engine.ai_desk._close_series`,
  because no `dist_21d_low_pct` (or equivalent) column exists anywhere in
  `engine/` or `scripts/` today — that field is only a *planned* future column
  per `research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md`. Any Phase 1 run
  must carry this proxy-status label through to the report, not silently
  present it as the eventual production field.

Secondary controls per source doc §5.6 (sector/regime, event blackout, thin-group
flag) remain as specified there and are not restated here.

---

## 6. Promotion bar — must clear the actual Neural Web Article-3 gate

The source doc §5.8 suggested an ad hoc bar (`n >= 400 fires per primary arm`,
`effect CI excludes zero`, `post-2020 sign agrees`, `thin-share printed`). **That
bespoke rule is superseded here.** Per house law, any authority grant (including
promoting SRSS from display/shadow to a priority modulator, an A2/A5-level move)
must clear the actual Article-3 gate implemented in
`engine/neuralweb/constitution.py::grant_authority`, not a separately invented
threshold. Reading that file directly, the gate is:

1. **Sample-size floors** (caller-supplied `floors` dict, not hardcoded in the
   module): `n >= floors['min_n']` **and** `hits >= floors['min_events']`.
2. **Wilson CI lower-bound lift threshold**: `wilson_lower(hits, n, z=1.645) /
   base_rate > 1.25` — quoting the module directly:
   > "Gate 2 — Wilson CI lower-bound lift > 1.25 ... Threshold 1.25 matches the
   > retired point-estimate floor (MIN_FORCE_LIFT=1.25). Because wilson_lb <=
   > point_estimate always, the CI gate is strictly tighter everywhere — zero
   > grant-more cases across a full k/n/base sweep."
   The Wilson lower bound itself is the 90%-one-sided bound, `z=1.645`
   (`wilson_lower(k, n, z=1.645)`), wrapping `engine.qledger.wilson_ci_low`.
3. **Evidence freshness**: `evidence_asof` must be within `max_staleness_days`
   (default **120** days) of `now`; grants lapse (return `granted=False,
   reason='stale'`) once evidence goes stale — "authority never persists on
   silence."
4. **Article 1 hard stop, unconditional**: if `target_level is
   AuthorityLevel.A7_ORIGINATE`, the grant is refused before any evidence is
   evaluated — SRSS can never originate a signal regardless of how clean the
   stratification looks; it can at most reach A2 (ATTEND) or A3 (DE-ESCALATE)
   framing, never A7.

SRSS's own `min_n` / `min_events` floors are not yet chosen — that is a Phase 1
design decision to make when the ledger has enough history to make floor choice
meaningful, not something to invent now while n=24 total and n=0 for two of six
arms. Any Phase 1 report must state the evidence dict (`hits`, `n`, `base_rate`,
`evidence_asof`) and run it through `grant_authority` directly rather than
eyeballing a pass/fail.

---

## 7. Kill rules

Adapted from source doc §5.7. SRSS is killed or held at display-only if any of
the following hold, checked per contrast:

- It improves precision only by destroying recall (e.g., a "cleaner" win rate
  bought by discarding most of the bottom-fire population as NEUTRAL/no-match).
- It only works for a thin sample (`confidence_tier` in `{none, low}`, i.e.
  `n_members < 6`) and disappears once medium/high-confidence groups are
  isolated.
- It fails a post-2020 holdout split (sign reversal or loss of significance).
- It shows no incremental lift once stock tier (`tier`) and distance-from-low
  proxy (`derived_dist_proxy`) are already controlled for — i.e. sponsorship
  adds nothing beyond what the existing stock-level fields already explain.
- The sign inverts between sector-level and subsector-level joins without a
  clear, pre-specified mechanism explaining why.
- The endpoint return looks better while `stop5`/`mae21` is *worse* — a "win"
  that trades away downside protection is not a win per house epistemics.

---

## 8. Interim status / next checkpoint

**This document is display/shadow-tier context only. It is never a decision
input** until the conditions below are met.

Phase 1 (the six-contrast stratification run) does not execute against a
promotion-grade verdict until:

1. **Phase 2 (shadow forward ledger)** is built — `data/neuralweb/
   subsector_sponsorship.parquet`, `data/subsector_sponsorship/snapshots.jsonl`,
   forward grader — per source doc §6 Phase 2. This is the decisive live
   evidence source per source doc §8.5 ("forward ledger is the decisive live
   evidence"), not the historical current-membership join Phase 0 performed.
2. **Numeric accrual floor for the weakest contrast**: B1 (EARLY_REPAIR) and B4
   (ROLLOVER) — currently at **n=0** — must each reach a minimum matched-event
   count before *any* contrast in this pre-registration is evaluated for
   promotion. Per §6 above, the exact `min_n`/`min_events` floor is a Phase 1
   design choice, but as a floor for even opening exploratory analysis (not
   promotion), this document sets: **do not attempt Phase 1 analysis on any
   arm with fewer than 30 matched events** (the same `min_n` order-of-magnitude
   already used elsewhere in this codebase's Article-3 evidence floors,
   e.g. the `risk_radar_review` `min_graded=30` self-gate cited in
   `constitution.py`'s A6 lane docs) — and do not treat 30 as anywhere near
   the promotion bar in §6, only as the floor for opening exploratory
   description.
3. Until both (1) and (2) hold, re-run Phase 0's coverage report periodically
   (each time `data/subsector_rotation/snapshots.jsonl` roughly doubles in
   length) to re-estimate the accrual rate in §1, since the current 6-day
   sample is too short to trust.

No code changes accompany this document. It is a design freeze only.
