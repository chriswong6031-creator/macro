# Narrative-Realign Phase-0 — D7 Salvage

**Verdict: RETIRE both families.** Reproduce: `python scripts/narrative_realign_phase0.py`

## The question

Gate A (`narrative_regime_phase0.py`, 2026-06) falsified EPU+GPR on forward realized
volatility incremental over VIX. D7 grants **one salvage pass** on targets that VIX
cannot price, then retire-or-license permanently.

**Signals tested:**

- **NDI_resid** — VIX-orthogonal residual of the text-uncertainty index `TU` (0.5 ×
  expanding-z log EPU + 0.5 × expanding-z log GPR-threat), after OLS residualization
  on [VIX, RVnow(21)]. This strips VIX-priced vol content; what remains is narrative
  elevation that the options market has NOT already priced.
- **SFED_resid** — VIX-orthogonal residual of the SF-Fed Daily News Sentiment Index
  (Bybee et al., `data/frbsf/news_sentiment.parquet`), same PIT expanding-z and OLS
  residualization. Independent construction lineage from the EPU/GPR family.

**Targets (VIX-blind by construction):**

| Target | Definition | VIX baseline IC |
|---|---|---|
| `cs_dispH` | std across 9 SPDR sector ETF (XLB/E/F/I/K/P/U/V/Y) h-day forward cumulative log-returns | +0.39 at h=21d — VIX picks up crisis co-movement but leaves rotation-dispersion unpriced |
| `comp_fadeH` | binary 1 when h-day forward SPY log-return < trailing 6-month SPY daily-return mean | −0.002 at h=21d — VIX is essentially orthogonal to this timing target |

**Statistical discipline** (identical to `narrative_regime_phase0.py`):

- PIT: expanding-z with 252-day burn-in; no look-ahead.
- VIX-orthogonal residual: OLS residual of signal on [VIX, RVnow(21)].
- Block-bootstrap CIs (block=63, B=2000, SEED=7).
- BH-FDR across all (signal × target × horizon) tests, q ≤ 0.10.
- Split-half sign-stability (sign must be consistent in both halves of the sample).

**Sample:** 1999-01-04 → 2026-07-01, ~6,900 trading days. Sector ETF availability
(1998-12-22 + 252-day burn-in) gates the start; EPU/GPR from 1985, SFED from 1980,
VIX from 1990 all cover the window.

## Results

### Target A — Forward cross-sectional sector dispersion

| Signal | h | IC | 90% CI | p | excl0 | half-split | FDR q |
|---|---|---|---|---|---|---|---|
| NDI_resid | 5  | +0.0728 | [+0.0056, +0.1384] | 0.076 | True | **−0.010 / +0.206** | 0.405 |
| NDI_resid | 10 | +0.0750 | [+0.0092, +0.1422] | 0.065 | True | +0.000 / +0.193 | 0.520 |
| NDI_resid | 21 | +0.0838 | [+0.0109, +0.1544] | 0.052 | True | **−0.031 / +0.217** | 0.832 |
| NDI_resid | 63 | +0.0668 | [−0.0169, +0.1420] | 0.217 | False | −0.044 / +0.198 | 0.694 |
| SFED_resid | 5  | +0.0010 | [−0.0963, +0.0842] | 0.873 | False | −0.037 / +0.049 | 0.931 |
| SFED_resid | 10 | +0.0162 | [−0.0859, +0.1020] | 0.869 | False | −0.047 / +0.089 | 0.993 |
| SFED_resid | 21 | +0.0501 | [−0.0456, +0.1385] | 0.441 | False | −0.023 / +0.132 | 0.706 |
| SFED_resid | 63 | −0.0654 | [−0.1822, +0.0382] | 0.288 | False | −0.141 / +0.012 | 0.658 |

### Target B — Complacency-fade timing

| Signal | h | IC | 90% CI | p | excl0 | FDR q |
|---|---|---|---|---|---|---|
| NDI_resid | 5  | −0.0105 | [−0.0351, +0.0187] | 0.623 | False | 0.830 |
| NDI_resid | 10 | −0.0230 | [−0.0616, +0.0192] | 0.382 | False | 0.679 |
| NDI_resid | 21 | −0.0349 | [−0.0831, +0.0207] | 0.346 | False | 0.692 |
| NDI_resid | 63 | −0.0582 | [−0.1244, +0.0186] | 0.238 | False | 0.635 |
| SFED_resid | 5  | −0.0106 | [−0.0500, +0.0266] | 0.621 | False | 0.903 |
| SFED_resid | 10 | +0.0024 | [−0.0510, +0.0569] | 0.962 | False | 0.962 |
| SFED_resid | 21 | −0.0080 | [−0.0807, +0.0618] | 0.818 | False | 1.000 |
| SFED_resid | 63 | −0.0899 | [−0.1925, +0.0175] | 0.172 | False | 0.688 |

## Reading

**NDI_resid vs Target A** is the single closest to passing: the full-sample IC is
positive and Bootstrap-excludes zero at h=5, 10, 21d. But it fails the license gate
on two independent grounds:

1. **Sign-unstable across halves.** The first-half IC is *negative* at h=5d (−0.010)
   and h=21d (−0.031) while the second half is strongly positive (+0.206, +0.217).
   This is the hallmark of a spurious positive full-sample IC driven entirely by the
   post-2012 period, where high-uncertainty regimes coincide with idiosyncratic
   rotation (e.g., pandemic-era sector splits). The signal is not stable over the
   pre-2012 half, where it is if anything a noise-level negative read.

2. **FDR fails across the grid.** Best q = 0.41 (at h=5d), well above the 0.10
   threshold. Across 16 tests the BH procedure rejects nothing.

**NDI_resid vs Target B:** all ICs near-zero, no excl0 at any horizon. VIX is
similarly uninformative about this target (IC = −0.002), confirming the target
is genuinely VIX-blind — but the NDI residual carries no timing edge there either.

**SFED_resid** is null across both targets at all horizons. The SF-Fed index is a
daily news tone composite; after residualizing on VIX+RVnow, no cross-sectional or
complacency-timing edge survives. SFED's cross-asset display value (it is part of the
conditions snapshot) is unaffected — the retirement applies only to its candidacy as
a qledger SHADOW confirmer.

## Decision

| Family | Target A | Target B | Verdict |
|---|---|---|---|
| NDI (EPU+GPR) residual | FAIL (sign-unstable, FDR q≥0.41) | FAIL (null ICs) | **RETIRE** |
| SFED sentiment residual | FAIL (all ICs null, no excl0) | FAIL (null ICs) | **RETIRE** |

**Both families RETIRED.**

The retirement is implemented in `engine/narrative_regime.py`:
- `_FAMILY_RETIRED = True` (machine-readable flag, tested in CI).
- `gate_status` changed from `"pinned_off"` to `"retired"`.
- `gate_multiplier` remains hard-pinned to `1.0` (unchanged — it was already a no-op).
- A full retirement record is embedded in the module docstring and propagated through
  `compute()` as `retire_date` / `retire_reason`.

**Revival bar:** The D7 data (1999–2026) is now in-sample. A future revival attempt
must use a pre-registered harness on genuinely out-of-sample data and clear the same
four-condition license gate (excl0 + FDR-reject + sign-stable halves + directional
IC). The framework's standing rule (D7 spec) is "one shot each; no perpetual deferral"
— this is the shot, and it was spent.

## What survives unaffected

- **NDI display banner** (`engine/narrative_regime.py`): the EPU/GPR/VIX composite
  0–100 read is still rendered as a context banner. Retirement blocks promotion to a
  *scored* conditioner; display is not affected.
- **SF-Fed Daily News Sentiment** in conditions snapshot (`engine/conditions.py`):
  `news_sentiment` and `news_sentiment_z` remain in the conditions frame as display
  signals. This retirement only blocks its qledger SHADOW claim candidacy.
- **The qledger/qbus infrastructure** and all other claim families are unaffected.
