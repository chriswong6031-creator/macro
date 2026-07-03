# C1 — Commodity→Sector Transmission — PRE-REGISTRATION

**Battery:** C1 (HK/Canada masterplan §4.1). **Wave:** W2. **Branch:** `hkca-w2-c1`.
**Author:** quant research agent. **Status:** PRE-REGISTERED — committed BEFORE any run.
**Constitution:** masterplan §6 (pre-reg first; HAC; BH-FDR within family; program-level DSR
`n_trials=30`; split-half sign-stability; effective-N = independent episodes; DSR≥0.90 the only
door to a GO; survivorship bounds; suspension-honest fills; verdicts GO/NO-GO/KILL/ACCRUE).

This pre-reg answers the red-team CRITIC:ca demands verbatim (HK_CANADA_REDTEAM_FINDINGS.md
lines 22-24, 78-80, 99-101, 118-123): the raw replication (XEG 4w t=+2.00 n=43; XGD 4w t=+2.42
n=50, **uncorrected on overlapping windows**) is the CEILING, not the expectation. The critic's
core demand is an **episode-honest** statistic: a pre-registered regime-episode definition with
min-duration + hysteresis that de-clusters autocorrelated slope-sign flips into INDEPENDENT
episodes (~6-12/commodity), **non-overlapping** episode returns, HAC + `bootstrap_effective_t`,
and DSR at the program `n_trials=30`.

---

## 1. Hypotheses

**H1 (primary, one-sided long).** After a commodity enters a *positive* (bull) trend regime, the
matched Canadian sector ETF earns POSITIVE excess return vs the broad Canadian market (`_GSPTSE`)
over the forward 2–8 week window, measured on NON-OVERLAPPING episode returns.
Direction pre-registered POSITIVE (transmission = sector re-rates when its commodity turns up).

**H0.** Mean episode excess return = 0 (no transmission edge net of overlap/autocorrelation).

**Exploratory, NON-GATED, labelled (H1-neg).** After a *negative* (bear) regime flip, does the
sector de-rate (negative forward excess)? Reported for the drawdown-side use if the long side
fails. NOT counted in the GO family, NOT FDR-corrected against H1, NOT DSR-gated.

---

## 2. Constructions (exact, frozen)

### 2.1 Data (all in-tree, no network)
- Commodities (`data/yahoo/*.parquet`, `close` = continuous adjusted series; futures roll-adjusted,
  used for a consistent trend state): `CL_F` (WTI oil, 2000-08→), `GC_F` (gold, 2000-08→),
  `HG_F` (copper, 2000-08→).
- Sector ETFs (`data/canada/*.parquet`, `close` = dividend-adjusted total return):
  `XEG.TO` (energy, 2001-03→), `XGD.TO` (gold miners, 2001-03→), `XBM.TO` (base metals, **2012-01→**),
  `XMA.TO` (materials, **2005-12→**, pre-registered copper-adjacent SECONDARY per masterplan §4.1).
- Benchmark: `_GSPTSE.parquet` (`close`) — S&P/TSX Composite.
- Yahoo/yfinance `close` is dividend-ADJUSTED total return (memory: yahoo-close-is-total-return);
  excess is ETF_TR − GSPTSE_TR so both legs are on the same total-return basis. Benchmark is a
  price index (no dividend), a small conservative drag on measured excess — stated, not corrected.

### 2.2 Regime-episode definition (the critic's core demand — frozen here)
Trend state of each commodity from a **slope_z** of the log-price:
1. `logp = log(close)`. Rolling OLS slope of `logp` on a time index over a **W = 63-trading-day**
   (≈13wk) window → `slope`. Standardize: `slope_z = (slope − mean) / std` over a rolling
   **252-day** window (min 200 obs). (63/252 mirrors the in-house slope_z convention.)
3. **Hysteresis (dual threshold, de-whipsaw):** enter BULL when `slope_z` crosses **above +0.5**;
   exit BULL (→ neutral) only when it falls **below −0.5**. Symmetric for BEAR (below −0.5 / above +0.5).
   The dead-band ±0.5 is the hysteresis band; a state persists until the opposite threshold is hit.
4. **Min-duration:** a regime must hold **≥ 20 trading days (4 weeks)** to count as an episode.
   Sub-20-day excursions are absorbed into the prior state (debounce). This matches the critic's
   ">=4wk hold" debounce that produced 43 oil / 50 gold turns as the acceptable UPPER basis.
5. **Positive regime flip (H1 event) = the first day of a NEW confirmed BULL episode** (transition
   day, neutral/bear → bull). One event per bull episode.
6. **Episode independence for the return statistic:** the forward window of one event may not
   overlap the entry of the next. We enforce NON-OVERLAP by construction (§2.3), which is the
   binding effective-N control (not the raw event count).

**Pre-registered expected episode counts** (honesty check; the critic's guidance ~6-12 independent
cycles/commodity over 25y, with 43-50 debounced turns the acceptable UPPER basis on NON-overlapping
returns): with the +0.5/−0.5 hysteresis + 20d min-duration on a 63/252 slope_z, we EXPECT roughly
**8-16 positive-flip episodes per commodity** over ~25y (oil/gold), FEWER for XBM (2012→, ~5-9) and
XMA (2005→). If the realized count falls far outside (e.g. >30 or <4 for a full-history commodity),
that is a construction surprise to be reported, not silently accepted. Pooled positive-flip episodes
across the primary three pairs expected **~20-40** before the non-overlap filter, collapsing further
after it. Effective-N is reported as (a) the raw flip count, (b) the NON-OVERLAPPING episode count,
and (c) `bootstrap_effective_t` `t_eff` on the daily excess return stream — the honest floor.

### 2.3 Forward return construction (non-overlapping, next-bar fill)
- **Fill:** entry at the **next bar's close** after the flip-confirmation day (NEXT-BAR fill, no
  look-ahead; the slope_z at day *t* is known at *t*'s close, we enter at *t+1* close).
- **Horizon family:** forward **2, 4, 6, 8 weeks** (10, 20, 30, 40 trading days). Primary reported
  horizon = **4 weeks (20d)** to match the critic's replication; 2/6/8w are robustness rows within
  the SAME test (not separate FDR slots — the horizon is a nuisance dimension, reported as a curve,
  primary pre-committed to 4w).
- **Episode excess return** = cumulative ETF total-return over the window − cumulative GSPTSE return
  over the SAME calendar window (buy-and-hold, next-bar-to-next-bar+H).
- **NON-OVERLAP filter:** episodes are taken greedily in time order; once an episode's [entry,
  entry+H] window is claimed, any later flip whose entry falls before the current window closes is
  DROPPED. This yields strictly non-overlapping episode returns → the HAC/DSR statistic is not
  inflated by window overlap. Applied per-horizon (a longer H drops more episodes — reported).
- **Suspension / halt / missing-bar rule (mandatory):** ETF or benchmark bars are used as-is from
  the parquet; if the forward window would run past the last available bar, the episode is DROPPED
  (no partial/ffill'd window). If any trading day inside a window is missing on ONE leg but present
  on the other, we align on the intersection of available dates and compute cumulative return over
  present bars only (no ffill THROUGH a gap — memory: no silent ffill through halts). Canadian ETFs
  do not halt for weeks (unlike HK), but the rule is stated and enforced for auditability.

### 2.4 Survivorship stamp / bound
- Commodity futures and broad-market/sector ETFs are **index/ETF-level series** — NOT a
  cross-sectional name panel. There is NO name-level survivorship problem here (the masterplan
  drops the C1 name tier entirely). The only survivorship exposure is ETF discontinuation, which
  did not occur for these four ETFs over the window (all live to 2026-06-30). **Survivorship
  bound: NONE material at the ETF level; stamped as index-level, no delisted-name imputation
  required.** (Contrast with the HK/CA name panels which carry current-constituent survivorship.)

---

## 3. Trials & families (frozen trial list)

**GATED FAMILY (C1 primary) — 3 trials, one BH-FDR family:**
| Trial | Commodity → ETF | History | Primary horizon | Note |
|---|---|---|---|---|
| T1 | oil `CL_F` → `XEG.TO` | 2001-03→ | 4w | full history |
| T2 | gold `GC_F` → `XGD.TO` | 2001-03→ | 4w | full history |
| T3 | copper `HG_F` → `XBM.TO` | **2012-01→** | 4w | **LOW-n** (state inception; ~40% less history) |

**PRE-REGISTERED SECONDARY (copper-adjacent), reported but NOT added to the gated FDR family
(kept out to avoid inflating the primary family; DSR still uses program n_trials=30 which already
counts it):**
| T3b | copper `HG_F` → `XMA.TO` (materials) | 2005-12→ | 4w | longer copper-adjacent proxy |

**EXPLORATORY NON-GATED (labelled, not in any FDR family, not DSR-gated):**
- T1n/T2n/T3n: the NEGATIVE-flip de-rate side for each of oil/gold/copper (drawdown-side signal).

Every variant counts toward the PROGRAM trial ledger. Per masterplan §6 the program-level DSR
`n_trials = 30` (counts every config across both markets, not just this family). We use **n_trials=30**.

---

## 4. Statistics (frozen)

For the GATED family (T1, T2, T3), primary horizon 4w:
1. **HAC t** (`newey_west_tstat`, lags=4) on the NON-OVERLAPPING episode excess returns.
   (Non-overlapping by construction, so HAC is belt-and-suspenders; lags=4 covers residual
   autocorrelation from adjacent-but-non-overlapping episodes.) Report mean, HAC se, t, p.
2. **BH-FDR** (`benjamini_hochberg`, alpha=0.10) across the 3 gated p-values (within-family control).
3. **`bootstrap_effective_t`** on the DAILY excess-return stream while IN a post-flip window
   (block=21) → `t_eff`, the autocorrelation-honest effective-N floor.
4. **DSR** (`deflated_sharpe`) at **n_trials=30**, using the episode-return Sharpe, its skew/kurt,
   T = non-overlapping episode count, and `t_eff` passed through. DSR≥0.90 is the ONLY door to GO.
5. **`block_bootstrap_ci`** on the episode returns for a distribution-free mean CI (block=4,
   since episodes are already near-independent; report 90% CI).
6. **Split-half sign-stability:** split episodes at **2013-01-01** (pre/post). Require the mean
   excess return SAME SIGN in both halves for a GO. (2013 chosen a priori: ~midpoint of the
   2001-2026 full-history pairs; also XBM's inception is 2012 so its pre-half is tiny — stated,
   XBM split-half is INFORMATIONAL only given its short pre-2013 window.)

---

## 5. Pre-registered GATES & verdict rule (frozen)

Honest prior (masterplan + critic): **GO-or-ACCRUE, borderline by construction.** The raw ceiling
is t≈2.0-2.5 on overlapping windows; the honest (non-overlapping + DSR-haircut at n=30) statistic
is EXPECTED to be weaker. A marginal result is ACCRUE, not a tortured GO.

Per-trial verdict (applied to each of T1/T2/T3):
- **GO** — ALL of: HAC t ≥ **+2.0** (one-sided direction pre-registered positive) AND passes
  BH-FDR at 0.10 within the family AND **DSR ≥ 0.90** at n_trials=30 AND split-half SAME-SIGN AND
  non-overlapping episode N ≥ 8 (minimum power floor).
- **ACCRUE** — mean excess POSITIVE and (HAC t in [+1.0, +2.0) OR DSR in [0.50, 0.90) OR split-half
  sign-consistent but sub-threshold t). A real-but-underpowered signal → register + come back.
- **NO-GO** — mean excess ≤ 0 at 4w, OR split-half SIGN-FLIPS, OR HAC t < 1.0 with DSR < 0.50.
- **KILL** — mean excess significantly NEGATIVE (HAC t ≤ −2.0) at the primary horizon (transmission
  is backwards → the leg is dead, not merely weak).

Battery-level verdict = the set of per-trial verdicts (one per hypothesis/commodity). A single
GO among {oil, gold} is a battery GO for that pair; XBM low-n GO is provisional (state n).

**No wiring.** Reports only (masterplan W2 acceptance). NOTHING is wired into any live engine or board.

---

## 6. Effective-N honesty (pre-stated)

Effective-N is the **non-overlapping independent-episode count**, NOT the row count and NOT the raw
slope-flip count. We report all three (raw flips / non-overlapping episodes / `t_eff`). We EXPECT
the non-overlapping 4w-episode count to be **~8-16 per full-history commodity** and materially fewer
for XBM (2012→). At these N, DSR≥0.90 is a HIGH bar and several trials may resolve ACCRUE — this is
the pre-registered honest prior, not a post-hoc excuse.

## 7. What this test does NOT show (pre-committed)

- Not a name-level edge (name tier dropped; empirical sign against per critic — GDX-XGD t+1 −0.06).
- Not a tradeable strategy net of costs/slippage/capacity (episode buy-and-hold gross excess only).
- Not causal identification (regime flips correlate with macro states that also move TSX sectors).
- Not out-of-sample in the walk-forward sense (split-half is in-sample sign-stability, not OOS).
- Survivorship: index/ETF-level, no name-panel survivorship; bound = none material (stamped §2.4).

---

## 8. Registry

Experiment id `hkca_c1_commodity_sector`, maturation = report-date (in-tree backtest, no forward
ledger), come_back_on set for a re-run when the copper history (XBM) lengthens. Registered in
`data/experiments/registry_seed.json`.
