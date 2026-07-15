# CCW Study S1 — Pre-Registration (FROZEN)

**Status:** FROZEN 2026-07-15, BEFORE any relationship between construction and outcome
was computed. Written from field-guide priors (`CCW_CREDIT_FIELD_GUIDE.md` §4) and the
masterplan §3-P7 pre-registration — NOT from inspecting the CCW data's velocity-vs-outcome
relationship. Data *availability* (series present, date ranges) was checked; the *edge*
was not. This document is the ruler; the RESULTS doc reports against it and never rewrites
it (release-forecast RESULTS append idiom).

**Authority:** display/context. This is a descriptive study — it produces a printed
verdict, promotes nothing, gates nothing. A NULL is a valid, publishable outcome (cf. the
oscillator crosses DEMOTED by the W3 sanity study).

---

## 1. The question

The credit desk (W4) ships **spread-velocity percentile** as the PRIMARY read on every
spread series — the construction that *replaced* the oscillator crosses after W3's sanity
study demoted them. S1 asks the obvious accountability question on the deepest history we
own: **does a rising spread-velocity percentile actually lead equity drawdowns and
further credit widening — and is that lead era-robust, or an artifact of one or two
crises?**

Field-guide license (§4): credit leads equity (ABX led the 2007 SPX top ~4 months; CDS
leads cash bonds, Blanco et al 2005); the predictive content of spreads is the
risk-appetite residual (Gilchrist-Zakrajšek 2012). S1 tests whether *our specific
construction* carries that documented signal.

## 2. Series (owned, deep history — availability confirmed 2026-07-15)

| Role | Series | Source | Span |
|---|---|---|---|
| Spread (primary) | `hy_oas` (BAMLH0A0HYM2, broad HY OAS) | `data/archive` combine_first | 1996-12-31 → |
| Spread (secondary) | `ig_oas` (BAMLC0A0CM, broad IG OAS) | archive | 1996-12-31 → |
| Spread (secondary, deepest) | `moodys_spread` = DBAA − DAAA (Baa−Aaa) | `data/fred` | 1986-01-02 → |
| Equity outcome | `SPX` (`_GSPC` close) | `data/yahoo` | deep |

Rating-ladder buckets and theme series are OUT of S1 (only ~3y / accruing history) —
those are S1b (backfill-gated) and S2/S3 (accrual-gated), explicitly deferred.

## 3. Constructions under test (the desk's reads, frozen)

For each spread series `s` (daily, business-day indexed, ffill ≤2 days for holidays):

- **V21** = `s.diff(21)` (21-trading-day change in spread, bp).
- **V21_pctile(t)** = percentile rank of V21(t) within the **trailing** window
  `[t−2520, t−1]` (10y, business days). Trailing-only — no future bar enters the rank.
  Warm-up: require ≥504 prior observations (2y) or the percentile is NULL (row dropped
  from that cell, count reported).
- **V63** and **V63_pctile** — identical with a 63-day change.

The desk's live threshold is **V21_pctile ≥ 85** ("velocity in the top 15% of the last
decade"). That exact threshold is the frozen condition.

## 4. Outcomes (strictly forward — no look-ahead)

For horizon `h` ∈ {21, 63, 126} trading days:

- **SPX_dd_h(t)** = `min_{1≤i≤h} ( SPX(t+i) / SPX(t) − 1 )` — worst equity drawdown over
  the next h days (≤ 0; more negative = worse). Rows with < h future bars dropped.
- **SPRD_fwd_h(t)** = `s(t+h) − s(t)` — further spread change over the next h days
  (> 0 = further widening).

## 5. PRIMARY frozen hypothesis (ONE pre-declared cell)

> **H1.** On `hy_oas`, full sample 1996-2026: trading days with **V21_pctile ≥ 85** are
> followed by a **worse mean SPX_dd_63** than the unconditional base rate.

- **Test statistic:** Δ = mean(SPX_dd_63 | V21_pctile ≥ 85) − mean(SPX_dd_63 | all).
  H1 predicts Δ < 0 (conditional drawdowns deeper). One-sided.
- **Null & significance (overlap-safe, house-law-compliant):** the h=63 forward windows
  overlap, so naive t-stats are anti-conservative. Use a **circular block permutation of
  the condition-label series** (the V21_pctile ≥ 85 indicator), block length = 63 (= the
  outcome horizon, to preserve outcome autocorrelation under the null), **2000
  permutations**; one-sided p = fraction of permuted Δ ≤ observed Δ. This is a
  **time-preserving null** — the month-block bootstrap and ticker-cluster idioms are NOT
  used (both are banned/anti-conservative per house law). Pass = p < 0.05 **and** Δ < 0.
- **Base rate is always printed** beside the conditional (never a bare conditional).

## 6. Secondary cells (exploratory — printed, NOT the gate)

Run the same machinery across the grid, clearly labeled exploratory (no cherry-pick):
- Series: `ig_oas`, `moodys_spread`; Construction: `V63_pctile`;
- Outcome: `SPRD_fwd_h` (widening continuation) as well as `SPX_dd_h`; `h` ∈ {21, 126}.
- **Rank-IC:** Spearman(V21_pctile, forward outcome) with the same block-permutation null.
- Report Δ, base rate, conditional n, permutation p for every cell.

## 7. Era split (MANDATORY on every cell)

Three eras, pre-declared: **pre-2010** (1996-2009, incl. dot-com + GFC), **2010-2020**
(QE + COVID), **2021→** (hiking + AI cycle). H1 is "era-robust" only if Δ < 0 in **all
three** eras (sign-stable), regardless of per-era significance (small-era power is weak —
sign-stability is the bar, not per-era p).

## 8. Verdict rubric (frozen)

- **LEADS** — H1 passes (p<0.05, Δ<0) AND era-sign-robust (Δ<0 in all 3 eras).
- **MIXED** — H1 passes on full sample but sign flips in ≥1 era (crisis-concentrated), OR
  Δ<0 but p≥0.05 with a large point estimate. The velocity read carries information but
  not dependably across regimes → keep as PRIMARY *context*, not a standalone trigger.
- **NULL** — H1 fails (Δ≥0 or p≥0.05 with small effect). Then the desk's velocity read is
  descriptive-only, and that is stated in plain words on the surface (the DEMOTED
  precedent). No hiding.

Whatever the verdict, it is printed to `data/corp_bonds/study_s1.json` + the RESULTS doc,
and the credit desk's velocity-read caveat copy is set to match (LEADS → "has led
past stress"; MIXED → "has led some past stress, not every regime"; NULL →
"context only — no dependable lead in history").

## 9. Anti-look-ahead checklist (verified in the build, asserted in tests)

1. Percentile window is `[t−2520, t−1]` — strictly prior; assert the rank never sees `t`
   or later.
2. Outcomes use only bars `> t`; assert first outcome bar is `t+1`.
3. Warm-up rows (percentile NULL) excluded from every cell; counts printed.
4. SPX aligned to spread dates by **as-of merge (last SPX on-or-before the spread date)** —
   never a future SPX; Monday/holiday safe.
5. Era boundaries are calendar-fixed, not fit to the data.
6. The permutation shuffles labels only; the outcome series is never re-drawn.

## 10. Deferred (stated, not hidden)

- **S1b** (rating-ladder CCC−BB lead/lag, era-split): the ladder has only ~2023→ owned
  history — an era-split is impossible today. Gated on the W5 TRACE-HISTORIC backfill
  (not available at the free Public tier — see W5) or ~2y forward accrual (~2028-H1).
- **S2** (tranche-level theme dispersion → index widening): accrual-gated; theme series
  began 2026-07. First feasible read after ~1y accrual.
- **S3** (issuer-level spread momentum vs equity drawdown, theme universe): accrual-gated,
  post-S2.
