# R-ORTH Preregistration — Covariance & Orthogonality Rail

Frozen 2026-07-06 by Fable. Governs the display-only R-ORTH program ratified in `R_ORTH_MASTERPLAN_BY_FABLE.md`. Amendments require a new dated section; no in-place edits after freeze.

## 1. What is preregistered

R-ORTH is a **rail** (context/infrastructure), not a signal. Nothing in this prereg creates scoring, sizing, gating, or ranking authority. This document freezes:

1. The artifact contract (`neuralweb.covariance_spine.v1`) and its no-authority fields.
2. The null-calibration law (RUL-ORTH-8): every orthogonality/stability statistic ships with its within-window contiguous-block null (≥200 draws) and is displayed as a percentile vs that null.
3. The measurement floors: lobe-pair correlation requires ≥30 shared engine-week observations; co-fire Jaccard requires ≥10 co-fire events; below floor the pair is `null` with the floor printed.
4. The deferred experiment queue (§3) and the deferred DISP-EIGEN-1 family (§4).

## 2. Falsifiers for the rail itself

The rail is descriptive, so its falsifiers are about honesty, not alpha:

- **F-ORTH-1 (coverage honesty):** if `effective_independent_lobes` is ever displayed without `n_lobes_measurable`/`n_lobes_total`, that surface is in violation and must be fixed or removed.
- **F-ORTH-2 (null honesty):** if any OOS/stability metric is displayed as a raw threshold without its null percentile, violation.
- **F-ORTH-3 (authority creep):** if any consumer reads covariance_spine fields into a gate, rank, sizing, or alert path, the read-gate consumer declaration plus this prereg make it a hard violation; the consumer is reverted.
- **F-ORTH-4 (stability):** if lobe cluster assignments flip for >50% of measurable pairs across two consecutive months (membership Jaccard < 0.5), the lobe block is marked `unstable` on all surfaces until the estimator is repaired and re-frozen.

## 3. Deferred experiment queue (runs require R1 replay registration; flat `replay` FDR family)

| ID | Hypothesis | Pre-declared null | Horizon/ruler |
|---|---|---|---|
| RORTH-RV-CURVE-1 | PC-neutral Treasury curve residual z mean-reverts | No forward edge net of cost/carry | 5–20d, absolute |
| RORTH-RV-SECTOR-1 | Sector-neutral equity residual dislocation improves entry quality | No lift after existing Entry/Oracle evidence | 21d, excess |
| RORTH-RV-FACTOR-1 | Factor-PC residual support improves hold/trim decisions | No improvement in forward drawdown or exit timing | 21–63d |
| RORTH-RV-DISP-1 | Eigen-dispersion predicts selection payoff | Existing dispersion percentile fully explains outcome | 21d |

Charter bar (RUL-ORTH-7): a Residual Relative-Value lobe may be drafted only if ALL FOUR pass net-of-cost, FDR-pooled, incremental to existing lobes, and outside-crisis. Any single failure closes the question for two quarters.

## 4. DISP-EIGEN-1 (registered, activation DEFERRED)

Family: `disp_eigen`. Blocked on: DISP-GATE-1 basis non-stationarity resolution (34.8% expanding-vs-trailing state-flip rate as of 2026-07-06). Descriptive eigen fields ship on fixed trailing-252d basis only; no percentile-typed field may use an expanding window. Candidate gate tests (frozen, to be run only after unblock):

1. `residual_dispersion` predicts wider cross-sectional spread of forward residual returns (rank IC, 21d).
2. `effective_universe_bets_pr` predicts better realized selection payoff for existing board/Oracle fires.
3. `dominant_equity_pc_share` identifies periods where confluence co-fire lift is inflated (same-bet periods).
4. All lifts survive sector/beta/vol/liquidity controls, rolling windows, and the pooled family FDR.

`gross_mult_live` remains 1.0 regardless of any outcome in this prereg (US_BOARD_MEASUREMENT ruling carries).

## 5. Display bands

Per RUL-ORTH-8 and masterplan §4: descriptive display only; "elevated" labels only above the null p90; no advisory bands before 6 months of accrued history plus an R1 replay.
