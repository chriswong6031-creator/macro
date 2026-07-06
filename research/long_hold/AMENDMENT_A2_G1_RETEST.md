# OBJECTIVE.md — AMENDMENT A2: G1-RETEST pre-registration (OOS-2 roster)

**Status:** REGISTERED 2026-07-06 (operator + Fable), per the G1 ruling (`W1_KILLTEST_RESULTS.md §12`: "pre-register as Amendment A2 before any further feature-outcome contact") and LH-R11 (ratified 2026-07-06).
**Lock semantics:** this document registers the roster and the retest terms. Per LH-R11.1 the roster FREEZES at the commit of the A2 OOS-analysis script — not at this document. Families may be added/dropped only by amendment before that commit. **No feature-outcome statistics may be computed on OOS-2 before the analysis script commits.**

## 1. OOS-2 definition (unchanged from the G1 ruling)

- Cohort: 2025+ honest fires (Massive live accrual, survivorship-correct per day), `gate_fires_baskets.parquet` population, labels per `long_hold_labels.parquet` conventions (schema v1).
- Ratifying contrast: `missed_hold` (= label `compounder`) vs `tactical_only` at 252d.
- Evaluation trigger: honest compounder episode-clusters ≥ **25** (LH-R4 floor). Projected ~2027-H2 at the observed ~14 clusters/year accrual.
- Inference frame: OBJECTIVE §6.3/§6.4 unchanged — episode-clustering (name × macro-regime, ±10d), Mann-Whitney U / rank-biserial for continuous features, Fisher exact for binary, within-regime label-reshuffle null (1,000 permutations, seed 42), survivorship stamps per LH-R3.
- Ratifying correction: program-wide HLZ / BH-FDR q=0.10 over Σ registered hypotheses across all roster families (LH-R11.2). Within-family q is descriptive. `program_fdr_marginal=True` routes to NOT-SURVIVE.

## 2. Registered roster (Σ = 29 ≤ 40 per LH-R12)

| # | Family (sub-fdr id) | m | Feature list authority | Notes |
|---|---|---|---|---|
| F1 | `long_hold.fundamental` | 9 | OBJECTIVE §5 (frozen W1 list) | Coverage-restored per the retest prep list: `op_income` un-aliases quality_z ≡ profitability_z; `interest_exp` restores interest_coverage; `insider_cmp` restored via F4's data lane (remains an F1 hypothesis, m unchanged); `archetype` joined from history parquet. Dropped-for-coverage features stay in Σ |
| F2 | `long_hold.washout_tf` | 10 | `WASHOUT_TIMEFRAME_HYPOTHESIS.md` | Admitted per LH-R11 application §4. R11.3 stamps apply: depth features carry `restricted_range`; positive survivor-only depth results route to DEFERRED. B1 data block acknowledged (monthly-bar maturity); may DEFER alongside F1 |
| F3 | `long_hold.expect_drift` | 7 | `EXPECT_DRIFT_FAMILY_PREREG.md` | New (LT-2). Coordinates with species S9 per LH-R10 |
| F4 | `long_hold.insider_sponsor_lh` | 3 | `INSIDER_SPONSOR_LH_FAMILY_PREREG.md` | New (LT-3). Entry-ruler insider tests remain with ESX Amendment 2 RUL-26 — different program, different ruler, no shared claims |

## 3. Retest prep list (carried from W1 §12; wave LT-1/LT-3 deliverables)

1. `op_income`, `interest_exp`, `capex` added to `fundamentals_panel.parquet` (frames/companyfacts lane).
2. `statements.parquet` repair: `period_end` populated per row (PIT gate currently fails open), shares extraction fixed, depreciation/SBC/R&D backfilled, not-yet-filed FY rows purged.
3. Sector→ticker mapping expanded 503 → ~2,589 (fixes `sector_laggard_winner` benchmark artifact; enables per-fire sector-relative S(f) per Amendment A1-to-spec).
4. Insider fire-date join (2006q1→ panel) restoring `insider_cmp` coverage.
5. Committed dead-name coverage probe script replacing the estimated ~95% post-anchor figure.

## 4. Contact rules until the freeze

- Ruler-P studies (LH-R14) operate ONLY on fires with fire_date ≤ 2023-12-31 (`cheap_trap` vs `tactical_only`), survivorship-stamped, display-ceiling. The 2024+ cohorts are untouched by any feature-outcome computation until the A2 analysis script commits.
- Forward accrual (labels maturing, panels advancing) is not "contact" — the nightly label panel advances blindly; no feature joins against 2024+ outcomes are computed or inspected.
- Feature panels (expect_drift, insider) MAY be computed for all fire dates (features are at-entry, outcome-blind); only the join to 2024+ outcomes is forbidden pre-freeze.
