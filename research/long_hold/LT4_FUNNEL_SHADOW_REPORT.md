# LT-4 Thesis Funnel Shadow — Build Report

**Program:** LT External Foundation  
**Wave:** LT-4  
**Date:** 2026-07-06  
**Status:** SHIPPED — display/research tier, zero behavioral authority  
**Ruling:** LH-R2 (transparent AND-gate; no composite, no behavioral surface)

---

## In plain English

This is a display-only process label.  The funnel shows which stocks passed a set of independent survival checks — nothing more.  It has no authority over board ordering, alert triage, entry gates, or any scored surface.  It cannot promote, demote, or affect any signal.

The gate is a simple AND-conjunction.  If a stock fails any one of four survival checks it is labelled "not eligible."  If it passes all four survival checks and also has a Piotroski F-score of 6 or higher and is not flagged as dilutive, it is labelled "shadow candidate."  Everything else is "watching."

There is no active thesis tier.  The ceiling is "shadow candidate."  The W3/W4 waves that would unlock the active thesis are deferred per the G1 ruling.

**What the study context says (explicitly NOT a gate input):**  
Per the corrected Ruler-P record (#1642, re-run on the #1610-fixed panel): the only descriptive pass in the expectation-drift family is ED-2 `sue_streak` (protective sign, RBC = −0.061, q = 0.068 — a very small effect); the earlier ED-7 "confirmed absorption" pass was a substrate artifact and is NULL (see EXPECT_DRIFT_RULER_P_RESULTS.md, revision note). Neither of these study results feeds the funnel.  The funnel gates are entirely based on accounting survival checks, not on any earnings-momentum or drift study result.

---

## Universe counts (initial snapshot)

The snapshot script (`scripts/research/build_thesis_funnel_snapshot.py`) was run against the current fundamentals universe.  State counts are printed by the script; paste the output here after each run.

| State | Count |
|---|---|
| not_eligible | 1,002 |
| watch_for_thesis | 255 |
| thesis_candidate_shadow | 246 |
| unavailable | 0 |
| **Total** | **1,503** |

_Run date: 2026-07-06.  Universe: 1,503 tickers from `fundamentals_panel.parquet`.  Elapsed: 15.5s._

---

## Gate definition (frozen v1)

### Survival flags

| Flag | Rule | Source |
|---|---|---|
| s1_dilution | shares_yoy_change >= +3% | engine/capital_allocation.py `_DILUTIVE_SHARES_CHANGE_PCT` (= 3.0); matched to scripts/research/missed_hold_study.py |
| s2_moat_falsifier | any of 4 moat sensors firing on latest adjacent-FY pair | engine/moat_falsifiers.py `compute_moat_falsifiers()` |
| s3_solvency | Altman Z < 1.81 | engine/stock_fundamentals.py `_altman()` |
| s4_coverage | fewer than 2 of {shares_yoy, moat sensors, altman_z} computable | engine/thesis_funnel.py `_coverage_check()` |

### State machine

```
s4_coverage fires → not_eligible
s1_dilution fires → not_eligible
s2_moat_falsifier fires → not_eligible
s3_solvency fires → not_eligible

all survival pass AND piotroski_f >= 6 AND capital_allocation_delta != 'dilutive'
  → thesis_candidate_shadow

all survival pass AND (piotroski_f < 6 OR piotroski unavailable OR capital_allocation_delta == 'dilutive')
  → watch_for_thesis
```

**Note on capital_allocation_delta:** `'unavailable'` does NOT disqualify.  Only `'dilutive'` disqualifies from thesis_candidate_shadow.  A company with no repurchase data is not penalised for the gap.

### Ceiling

The ceiling is `thesis_candidate_shadow`.  No `active_thesis` state exists anywhere in this module or in any template.  This ceiling is W3-locked per the G1-DEFERRED ruling 2026-07-06.

---

## Context references (NOT gate inputs)

The following are included in the per-stock output for display transparency, but they do NOT affect the funnel state:

- **expectation_state** (from engine/expectation_state.py): per the corrected record (#1642), ED-2 sue_streak is the family's only descriptive pass (protective, tiny effect RBC = −0.061); the ED-7 pass was a substrate artifact → NULL (EXPECT_DRIFT_RULER_P_RESULTS.md, revision note).  These study results are explicitly excluded from the gate.
- **capital_allocation_delta** (from engine/capital_allocation.py): shown as context; only the `'dilutive'` value feeds the candidate upgrade test.
- **insider context** (from positioning.insider block): printed for transparency only.

---

## Display language constraints

- State labels use neutral process vocabulary: "Survival gate: passed — watching", "Not eligible: dilution flag"
- Chinese copy equally neutral
- The word "validated" is forbidden in any user-facing copy (CI-enforced)
- No claim of predictive power: phrases like "likely compounder" are forbidden
- Tooltips list the AND-gate inputs and their values for full transparency

---

## Artifacts

| Artifact | Path |
|---|---|
| Snapshot parquet | `data/research/thesis_funnel_states.parquet` |
| Snapshot manifest | `data/research/thesis_funnel_states_manifest.json` |
| Per-stock panel block | `site/stockdata/<TICKER>.json` → key `thesis_funnel` |
| Engine module | `engine/thesis_funnel.py` |
| Build script | `scripts/research/build_thesis_funnel_snapshot.py` |
| Synapse registration | `config/synapse.yml` → `long-hold-thesis-funnel-states`, `long-hold-thesis-funnel-states-manifest`, `long-hold-thesis-funnel-panel` |
| Experiments clock | `data/experiments/registry_seed.json` → `thesis-funnel-shadow` (come_back 2026-10-01) |

---

## Experiment clock

`data/experiments/registry_seed.json` entry `thesis-funnel-shadow`:

- **kind:** track_record
- **come_back_on:** 2026-10-01
- **protocol:** snapshot comparison (no longitudinal store yet — the snapshot script overwrites its parquet and is on-demand).  At come-back, re-run `build_thesis_funnel_snapshot.py` and compare state counts against the 2026-07-06 baseline (1,002 / 255 / 246, total 1,503).  Investigate any state-proportion drift >5pp; audit data coverage changes (LT-1 backfill, period_end PIT gate) before reading drift as real.  If longitudinal tracking is wanted sooner, wire an append/archive hook into nightly first (sole-advancer law).

---

## Standing clocks

- **W3 unlock** (active_thesis tier): deferred, ~2027-H2 per G1-Retest schedule
- **thesis-funnel-shadow stability check**: 2026-10-01
- **piotroski / altman retest**: bundled with W1 killtest re-evaluation (LH-R14 Ruler-H)
