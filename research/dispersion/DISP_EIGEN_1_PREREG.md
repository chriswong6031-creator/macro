# DISP-EIGEN-1 Preregistration — registered, activation DEFERRED

**Date frozen:** 2026-07-06
**Status:** PRE-REGISTERED. Descriptive fields ship on fixed trailing-252d basis
(RUL-ORTH-6); gated tests listed below are frozen but NOT yet run.
**Family:** disp_eigen
**Design authority:** research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md
(lives on a companion branch; referenced by path).

---

## Activation gate

DISP-EIGEN-1 is **DEFERRED** pending resolution of the basis non-stationarity issue
documented in DISP-GATE-1 (L3_PREREG.md). As of 2026-07-06, the expanding-vs-trailing
flip rate across historical dates is **34.8%** — i.e. more than one-third of fire dates
would receive a different regime label depending on which percentile basis is used.

Until the primary DISP-GATE-1 study resolves which basis is PIT-stable (or concludes
non-stationarity is structural), no eigen-derived gate, filter, or conditioning on
existing board/Oracle fires may be activated. The descriptive fields
(`dominant_equity_pc_share`, `effective_universe_bets_pr`, `idio_dispersion_share`)
are emitted in `data/dispersion/regime.json` as display-only fields at the top level
and excluded from rolling history rows.

---

## Descriptive fields (shipped, display-only)

All three fields are computed in `engine/dispersion._compute_eigen_block()` on a
**fixed trailing 252-day window** (per RUL-ORTH-6; no expanding-window percentile
for any new field).

| Field | Description | Precision |
|---|---|---|
| `dominant_equity_pc_share` | Share of total variance explained by PC1 (shares[0] = λ₁/Σλ) | 4dp |
| `effective_universe_bets_pr` | Participation ratio = (Σλ)² / Σλ² — effective number of independent bets | 2dp |
| `idio_dispersion_share` | Share of recent (21d) cross-sectional dispersion that is idiosyncratic (residual after top-3 PCs), clipped [0,1] | 4dp |

`sector_pc_loadings` is deferred: emitted as `null` with note `"sector map not wired
(deferred)"`. A sector mapping requires a sector registry integration that is out of
scope for this PR.

Block invariants:
- `"basis": "trailing_252d_fixed"` — always present; confirms RUL-ORTH-6 compliance.
- `"display_only": true` — always present; no consumer may use these fields for
  sizing, gating, ranking, or originating trades.
- Minimum panel: 120 days × 20 names (after 80% non-null coverage filter +
  zero-std name drop); returns `None` if not met.

---

## Hard invariants (carry through any outcome)

1. **`gross_mult_live = 1.0` unconditionally** — the US_BOARD_MEASUREMENT ruling
   (§Study 3) carries. No eigen field finding can change the live gross multiplier.
   This is not a gate condition; it is permanent until a survivorship-clean
   selection-IR edge is separately measured and promoted via its own PR.

2. **`null_calibration_law` (RUL-ORTH-8)** — any stability statistic derived from
   these fields must be accompanied by a null-calibration run (iid shuffle). A
   statistic that passes its own threshold on shuffled data is not informative.

3. **No word "validated"** in any output from the harness (epistemics house law;
   `scripts/check_validated_claims.py` CI guard).

4. **Nulls printed, not hidden** — if n floors are not met, the block is `None`
   and the emitted JSON carries `"eigen": null`, not a fallback estimate.

---

## Frozen candidate gate tests (to be run after DISP-GATE-1 resolution)

These tests are frozen PRE-OBSERVATION. Running them before DISP-GATE-1 resolves
is NOT permitted.

**Test (a) — idio_dispersion_share predicts wider forward residual return spread**
- Metric: rank IC of idio_dispersion_share at date t vs cross-sectional std of
  forward 21d residual returns (residual = each name's return minus EW market).
- Minimum n: 60 non-overlapping 21d windows.
- Pass criterion: IC positive, 90% bootstrap CI (block-bootstrap, 21d blocks)
  excludes 0 (one-sided).

**Test (b) — effective_universe_bets_pr predicts better realized selection payoff**
- Metric: within existing board/Oracle fires, sort dates by effective_universe_bets_pr
  at fire_date; compare WR (win-rate at 21d time-exit) in top vs bottom tercile.
- Minimum n: 25 episode-clusters per tercile.
- Pass criterion: top-tercile WR exceeds bottom by ≥5pp; episode-clustered
  bootstrap 90% CI for the gap excludes 0.

**Test (c) — dominant_equity_pc_share identifies inflated confluence co-fire lift**
- Metric: within periods where dominant_equity_pc_share > 0.50, measure whether
  multi-signal co-fire lift is anomalously large (>1.5× single-signal lift) vs
  periods where dominant_equity_pc_share ≤ 0.35.
- Minimum n: 20 co-fire events in each bucket.
- Pass criterion: lift ratio significantly higher in high-dominance periods
  (episode-clustered bootstrap 90% CI for the lift-ratio gap excludes 0).

**Test (d) — survival of sector/beta/vol/liquidity controls + FDR**
All (a)-(c) pass signals must survive:
- Sector-controlled: results hold within each GICS sector (not driven by one sector).
- Beta-controlled: regression of outcome on signal with SPY-beta covariate; signal
  coefficient remains positive and significant.
- Vol-controlled: VIX tercile stratification; signal relationship not confined to
  high-VIX tercile only.
- Liquidity-controlled: large-cap / mid-cap / small-cap breakdowns; signal not
  confined to one liquidity bucket.
- Rolling-window robustness: 3-year rolling windows show consistent sign direction
  in ≥ 70% of windows.
- Pooled-family FDR (Benjamini-Hochberg) across all three tests (a)-(c) at α=0.10;
  the disp_eigen family must have ≥1 survivor.

**PASS = all of (a) ∧ (b) ∧ (c) ∧ (d).** Partial pass enables descriptive annotation
only; no conditioning of fires permitted on partial pass. Full pass enables a
display annotation on the dispersion chip (not a sizing change — gross_mult_live
stays 1.0 per hard invariant 1 above).

---

## Reference

- DISP-GATE-1 gate + basis reconciliation: `research/dispersion/L3_PREREG.md`
- Design authority (PCA / orthogonality rationale): `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
- RUL-ORTH-6 ruling (fixed trailing-252d basis, gross_mult_live = 1.0
  unconditionally): same document.
- RUL-ORTH-8 null-calibration law: same document.
- US_BOARD_MEASUREMENT §Study 3 (gross_mult_live hard constraint): `research/US_BOARD_MEASUREMENT.md`
