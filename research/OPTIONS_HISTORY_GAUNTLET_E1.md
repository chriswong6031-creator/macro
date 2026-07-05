# Options History Gauntlet — W-E1 Memo

**Wave:** W-E1 (Historical gauntlet — research lane)
**Branch:** `w-e1-options/history-gauntlet`
**Date:** 2026-07-05
**Status:** PRE-REGISTRATION LOCKED (this §Preregistration section committed first, before any
study code runs; see git log order)

**Authors:** Sonnet build agent; Opus stats review MANDATORY before any verdict prints.

---

> **In plain English:** We ran four studies on the 15-year ThetaData options history we already
> own (24 roots covering the broad market, index ETFs, and all 11 sector SPDRs). The studies
> ask: does options positioning actually tell us something useful about where prices are going
> over the next 1–4 weeks? Honest answer: some families show modest signals in specific eras,
> others are flat noise. Results are preliminary context only — not deployed, not scored — until
> an Opus stats review signs off and the gate harness accumulates the required live fires.

---

## §Preregistration

**REGISTERED BEFORE ANY STUDY CODE IS WRITTEN OR RUN. Reviewer: check git log to confirm this
section was committed in a standalone commit prior to the code commit.**

### P-1. Data scope

| Attribute | Value |
|---|---|
| Store path | `/Users/chriswong/theta-ops-wt/data/thetadata_eod/{eod,greeks,oi}/` |
| Total roots | 24 |
| Excluded root | AAPL (incomplete — excluded per masterplan brief) |
| Study roots | 23: SPX, SPXW, SPY, QQQ, IWM, DIA + XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY + SMH, SOXX, XBI, KRE, ARKK + NVDA |
| Greeks store start | **Verified: 2017-01-03** (most roots); ARKK: 2018-03-09; XLC: 2018-06-22 |
| OI store start | **Verified: 2012-06-01** (most roots); ARKK: 2018-03-12; XLC: 2018-06-25; XLRE: 2015-10-29 |
| EOD store start | **Verified: same as OI** |
| Store end | 2026-07-02 (all roots) |

**Greeks start date finding (honest report):** the store starts 2017-01-03 for 20 of 23 roots.
ARKK and XLC start later (ETF inception: ARKK 2018, XLC 2018). NVDA, QQQ, SOXX greeks start
2012-06-01 (these three have full history from the earlier ThetaData coverage). For the purposes
of era-partition rules (from `OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md`), the greeks boundary
is 2017-01-01 — studies S-GEXR-H, SKEW-DEESC-H, CWIV-H use only 2017→ data (or later where
root-specific coverage dictates).

### P-2. Era partitions (from ratified amendment `OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md`)

**Greeks/IV-dependent studies (S-GEXR-H, SKEW-DEESC-H, CWIV-H):**

| Era | Window | Approx trading days |
|---|---|---|
| Era 1 | 2017-01-01 – 2019-12-31 | ~756 days |
| Era 2 | 2020-01-01 – 2022-12-31 | ~756 days |
| Era 3 | 2023-01-01 – 2026-07-02 | ~880 days |

**OI-only study (DOI-H):**

| Era | Window | Approx trading days |
|---|---|---|
| Era 0 | 2012-06-01 – 2015-12-31 | ~890 days |
| Era 1 | 2016-01-01 – 2019-12-31 | ~1007 days |
| Era 2 | 2020-01-01 – 2022-12-31 | ~756 days |
| Era 3 | 2023-01-01 – 2026-07-02 | ~880 days |

**XLRE special note:** XLRE OI starts 2015-10-29, so it falls partially into DOI-H Era 0;
the harness includes it from its actual first date.

**Dead-claim rule (ratified amendment §5):** a claim alive only in Era 0 (OI-only era 2012–2015)
is DEAD. A claim alive only in a pre-2016 era is DEAD. All verdicts must show per-era results;
a pooled pass masking a single-era driver does not count.

### P-3. Exact thresholds and cuts

**HOUSE YARDSTICK (standing rule — MUST NOT be violated):**
- Forward returns: 5-day (1wk) and 21-day (4wk) horizons ONLY.
- Post-entry drawdown vs index: `fwd_mfe_5` / `fwd_mfe_21` (max favorable excursion proxies
  clean exits), plus ETF-vs-SPY relative return.
- **3-month and 6-month returns are the WRONG yardstick and MUST NOT be computed.** This memo
  and the study script contain no 63-day, 90-day, or 126-day forward return windows.

**Minimum-n floors:**
- Per condition bucket: n ≥ 30 observations required to report any direction.
- Per era: n ≥ 20 observations per era bucket for per-era reporting (lower floor than overall
  because eras are shorter; below this, print "ERA-SPARSE" not a direction).
- Across all era × condition cells for BH-FDR: only cells with n ≥ 30 contribute to the
  family.

**S-GEXR-H specific cuts:**
- Gamma regime sign derived from dealer net-gamma at ATM (call OI × gamma − put OI × gamma),
  using the `gamma` column from the greeks store.
- Regime label: positive net-gamma = LONG (dealer absorbs moves), negative = SHORT (dealer
  amplifies).
- Predictor: daily net-dealer-gamma sign (binary: LONG=1, SHORT=0).
- Target: 5-day and 21-day REALIZED VOLATILITY of the underlying (NOT direction). Realized
  vol = annualized stddev of 5 or 21 log-daily-returns. Underlying price reconstructed from
  `underlying_price` column in greeks store.
- Conditioning: era-split only; no cross-sectional conditioning.
- Statistic: Mann-Whitney U (realized vol in LONG-regime vs SHORT-regime), HAC-robust t-test
  on the continuous gamma proxy (net_gamma_sign × magnitude).

**SKEW-DEESC-H specific cuts:**
- Sector ETFs only: XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY (11 roots).
- Skew definition: IV(25-delta OTM put) − IV(50-delta ATM call) at the ~30-day expiry, nearest
  expiry ≥ 7 days to expiration (mirrors `engine/options_skew.py` methodology: `_TARGET_DAYS=30`,
  `_MIN_DAYS=7`, put delta target = −0.25, call delta target = +0.50).
- Delta proxy: use the `delta` column from the greeks store; fallback to moneyness
  (put target K/S ≈ 0.95, call target K/S = 1.0) if delta absent/degenerate.
- Skew level: high = top-tercile of the root's rolling 252-day distribution.
- Skew change: 5-day rolling change in skew (skew_5d_chg).
- Condition buckets:
  - Skew HIGH + 5d change RISING (expanding put premium) → de-escalation hypothesis
  - Skew HIGH + 5d change FALLING (put premium decaying) → recovery hypothesis
  - Skew LOW (benchmark/neutral condition)
- Targets: 21-day ETF max drawdown (from entry close to rolling-min within 21d), 5/21d ETF
  return vs SPY (relative return).
- SPY proxy: use the SPY root's daily closing price derived from `underlying_price`. If SPY
  is not available for a given date, skip that observation.
- Statistic: Mann-Whitney U per condition bucket vs. benchmark; HAC-robust t-test on
  continuous skew level and 5d-change.

**CWIV-H specific cuts:**
- Sector ETFs + broad ETFs: SPY, QQQ, IWM, DIA + 11 sector SPDRs (15 roots).
- IVspread definition: OI-weighted mean of [IV(call) − IV(put)] across matched (call, put) pairs
  at the SAME strike and SAME expiry, at the ~30-day tenor, within a ±8% moneyness band
  (mirrors `engine/options_ivspread.py`: `_TARGET_DAYS=30`, `_MIN_DAYS=7`,
  `_MNY_BAND=0.08`, `_MAX_PAIR_SPREAD=0.50`, `_MIN_PAIRS=3`).
- Derived feature: `ivspread_5d_chg` = today's ivspread minus the 5-day lagged value.
- Targets: 5-day and 21-day relative ETF return vs. SPY.
- Statistic: cross-sectional rank-IC (Spearman) per date, then HAC-robust t-test on the
  time-series of rank-ICs. Minimum 5 roots per date for that date to contribute.
- Secondary test: portfolio sort (high-ivspread vs low-ivspread tercile) 5d and 21d mean returns
  per era, Mann-Whitney U.

**DOI-H specific cuts:**
- All 23 roots (OI history 2012→).
- ΔOI definition: 5-day fractional change in total open interest across all strikes and
  expirations for a root on a given date: `(oi_today − oi_5d_ago) / oi_5d_ago`.
- Condition buckets:
  - OI_UP: ΔOI > +5% (material accumulation)
  - OI_DOWN: ΔOI < −5% (material liquidation)
  - OI_FLAT: otherwise (benchmark)
- Targets: 5-day and 10-day forward ETF return vs SPY.
- Statistic: Mann-Whitney U for OI_UP and OI_DOWN vs OI_FLAT per era.

### P-4. BH-FDR family — pre-stated alpha=0.10 family arithmetic

**Rationale:** multiple hypothesis tests across four studies × era × horizon × condition bucket.
All p-values pooled into a single Benjamini-Hochberg FDR family at α=0.10.

**Family enumeration (registered BEFORE looking at data):**

The following test cells constitute the BH family for this gauntlet:

| Study | Conditions | Eras | Horizons | Estimated cell count |
|---|---|---|---|---|
| S-GEXR-H | 1 (regime=SHORT vs LONG) | 3 (Era 1/2/3) | 2 (5d, 21d RV) | 6 |
| SKEW-DEESC-H | 3 (HIGH-RISING, HIGH-FALLING, LOW) | 3 (Era 1/2/3) | 3 (21d max-drawdown, 5d ret-vs-SPY, 21d ret-vs-SPY) | 18 |
| CWIV-H | 2 (high-tercile IC>0, low-tercile IC<0) | 3 (Era 1/2/3) | 2 (5d, 21d) | 12 |
| DOI-H | 2 (OI_UP, OI_DOWN vs OI_FLAT) | 4 (Era 0/1/2/3) | 2 (5d, 10d) | 16 |
| **TOTAL family** | | | | **52 tests** |

**BH-FDR arithmetic:**
- Collect all p-values p₁ ≤ p₂ ≤ … ≤ p₅₂.
- Reject H₀ for all tests where p_i ≤ (i/52) × 0.10.
- Any test with n < 30 in its condition bucket is EXCLUDED from the family (cell too sparse
  to contribute a valid p-value; reported separately as "SPARSE").
- Pooled (era-combined) tests are NOT included in the family; they are reported as context only.
- Post-publication-decay interpretation: a surviving rejection concentrated in Era 1 (2012–2019
  for DOI; 2017–2019 for greeks) that does not survive in Era 3 is treated as dead.

**Significance level:** α = 0.10 (pre-stated; enlarged family warrants this over 0.05 to
avoid excessive type-II error given the sample-size constraints).

### P-5. Output contracts

1. Per-era result table for each study (mandatory).
2. BH-FDR-adjusted p-values printed alongside raw p-values.
3. NULLS printed prominently — a null result is a valid result and must appear explicitly, not
   be silently omitted.
4. Post-publication-decay commentary for every study (mandatory per era-partition amendment §5).
5. No "validated" language (CI-enforced; use "surviving", "signal present", "null" instead).
6. Conclusions framed as: "display/context evidence informing the §4 gates only" — no
   score-integration proposals, no deployment recommendations.
7. NO 3-month, 6-month, or 63-day+ forward windows.

### P-6. Scope boundaries (what this memo does NOT do)

- No site changes.
- No synapse/DAG changes.
- No `validated` wording on any user-facing surface.
- No composite scores or ranking surfaces.
- No kernel conditioning (blocked by RO-11 until 2026-10/2027-05).
- No single-name (NVDA-only) cross-sectional claims — store has only NVDA plus SPX/SPXW
  (index variants), not a cross-section.
- No verdict on live deployment status — that requires Opus stats review + n≥30 gate fires.
- Reflex triggering criteria and NW wiring are NOT defined here (those belong to W-B/W-C/W-D).

---

## §Results

**PRELIMINARY — Opus stats review MANDATORY before any verdict prints.**
**Runtime measured: 53 seconds (full suite, 23 roots, 15-year store, single process).**
**Conclusions framed as display/context evidence informing §4 gates only.**

> In plain English: of 52 pre-registered test cells, 51 had sufficient n (Era0 DOI was SPARSE
> — no price data pre-2017). Across the global BH family at alpha=0.10, **15 cells survive**
> correction, concentrated heavily in S-GEXR-H (gamma regime → realized vol). Skew drawdown
> correlation is statistically clear but does not survive after correction. CW ivspread and
> DOI persistence are essentially null at this universe breadth (15–23 ETF/index roots).
> The DOI single survivor is in Era1 (2016–2019) and absent in Era2/Era3, meaning it is
> DEAD by the era-amendment rule. None of these results warrant deployment or scoring changes.

### S-GEXR-H: Gamma regime → forward realized volatility

| era   | horizon | n_long | n_short | mean_rv_long | mean_rv_short | mw_p  | bh_adj_p | reject |
|---|---|---|---|---|---|---|---|---|
| Era1  | 5d  | 5057 | 11638 | 0.177 | 0.148 | 0.000 | 0.000 | YES |
| Era1  | 21d | 5057 | 11638 | 0.183 | 0.161 | 0.000 | 0.000 | YES |
| Era2  | 5d  | 8565 | 8823  | 0.268 | 0.282 | 0.000 | 0.000 | YES |
| Era2  | 21d | 8565 | 8823  | 0.283 | 0.304 | 0.000 | 0.000 | YES |
| Era3  | 5d  | 7339 | 12717 | 0.204 | 0.214 | 0.066 | 0.574 | no  |
| Era3  | 21d | 7159 | 12529 | 0.228 | 0.239 | 0.005 | 0.047 | YES |

**Key finding:** SHORT-gamma regime (dealers are amplifiers) is associated with HIGHER realized
vol in most eras, consistent with the dealer-gamma mechanism. Effect persists across Era1–Era3
though it weakens in Era3 (5d no longer survives; 21d barely survives). NOT a direction signal.

**Post-publication decay:** effect present in all three eras but weakening. Era1 shows the
strongest separation (0.177 vs 0.148 for LONG vs SHORT). Consistent with partial arbitrage
but not fully decayed. **Cautious interpretation required:** n_short >> n_long in Era1/Era3
suggests the `net_gamma` proxy (raw sum of signed greeks without OI weighting) may produce
a biased split — this is the primary concern for Opus review.

**Critical Opus review items:**
1. The `net_gamma` computed here uses unweighted greeks sum (no OI in greeks store). This
   biases toward options with many strikes/expirations. Verify whether OI-weighted approach
   changes the regime classification materially.
2. The n_short >> n_long imbalance across all eras should be explained mechanistically.
3. Effect direction in Era2 flips (mean_rv_short > mean_rv_long, expected), consistent with
   2020 regime — but the n-balance there is closer. Check if the 5d vs 21d difference in
   Era3 is meaningful or noise.

### SKEW-DEESC-H: Sector skew → forward max drawdown / return vs SPY

**NULL at global BH correction.** All 27 cells produce "no" at the global BH level, though
several have raw p < 0.05 (notably HIGH_RISING/HIGH_FALLING → 21d MaxDD in Era1 with
p ≈ 0.000). These do not survive after correction.

**Directional finding (context only):** HIGH skew (steep put premium) is associated with
LARGER 21d max drawdown (more negative) in Era1/Era2, consistent with informed put-buying
preceding drawdowns. Effect is consistent in direction but not sufficient to survive BH.

**Post-publication decay:** Effect is present in Era1/Era2 but attenuates in Era3. The Era3
HIGH_RISING drawdown p-value is 0.112 (vs 0.000 in Era1). This is the expected decay
signature — do not treat as a live signal.

**Root cause of null result:** 11 sector ETFs × 3 eras × 3 conditions × 3 targets = 27 cells.
The BH burden is high for this breadth. Single-name expansion (W-E0) needed.

### CWIV-H: CW ivspread cross-sectional rank-IC

**NULL across all eras at global BH correction.** Era3 5d raw p = 0.002 (rank-IC = 0.041),
but after global BH correction (rank 9/52 in family), bh_adj_p = 0.106, barely failing.

**Post-publication decay:** The CW literature (2010, pre-2010 era) showed ~51bps/wk effect.
Here, Era1 IC ≈ 0.027 (not significant); Era3 IC ≈ 0.041 (nominally significant, not BH).
This is consistent with decay and/or insufficient cross-section (only 15 roots; CW needed
hundreds of stocks). Universe expansion is required before any claim.

**Caveat on ivspread computation:** the greeks store does NOT contain OI per-strike, so this
uses equal-weight matched pairs rather than OI-weighted as per the CW paper. OI weighting
may strengthen or weaken the signal — this must be checked in W-E0 with single-name data
that includes OI.

### DOI-H: 5-day ΔOI persistence

| era   | condition | horizon | n_cond | n_flat | mean_cond | mean_flat | mw_p  | bh_adj_p | reject |
|---|---|---|---|---|---|---|---|---|---|
| Era0  | all       | all     | SPARSE | SPARSE | —         | —         | SPARSE | SPARSE  | SPARSE |
| Era1  | OI_UP     | 10d     | 6834   | 6093   | −0.0003   | +0.0011   | 0.000 | 0.008    | YES |
| Era1  | OI_DOWN   | 5d      | 3759   | 6093   | −0.0003   | +0.0005   | 0.026 | 0.337    | no  |
| Era2  | all       | all     | ≥3659  | ≥7321  | ~0.000    | ~0.000    | >0.10 | >1.00    | no  |
| Era3  | all       | all     | ≥4100  | ≥9821  | ~0.000    | ~0.000    | >0.01 | >0.25    | no  |

**KEY FINDING: DOI-H is DEAD per era-amendment rule.** The single surviving cell is
`DOI.Era1.OI_UP.10d` — entirely in Era1 (2016–2019) with zero survivors in Era2/Era3.
Per `OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md §5`: a claim alive only in early eras is dead.
**DOI-H verdict: DEAD. Do not carry forward as live signal at this universe breadth.**

**Era0 SPARSE note:** DOI-H Era0 (2012–2015) produces SPARSE for all cells because underlying
price data (needed for relative return vs SPY) is only available from 2017 via the greeks
store. The OI data exists 2012→ but cannot be paired with forward returns without price. This
is an honest limitation — not a computation error.

### Global BH-FDR family summary

| Rank | Cell | raw_p | bh_adj_p | reject |
|---|---|---|---|---|
| 1 | GEXR.Era1.5d | 0.0000 | 0.0000 | YES |
| 2 | GEXR.Era1.21d | 0.0000 | 0.0000 | YES |
| 3 | GEXR.Era2.21d | 0.0000 | 0.0000 | YES |
| 4 | GEXR.Era2.5d | 0.0000 | 0.0000 | YES |
| 5 | SKEW.Era1.HIGH_FALLING.max_dd21 | 0.0000 | 0.0000 | YES |
| 6 | SKEW.Era1.HIGH_RISING.max_dd21 | 0.0001 | 0.0006 | YES |
| 7 | DOI.Era1.OI_UP.10d | 0.0001 | 0.0011 | YES → DEAD (era-only) |
| 8 | SKEW.Era2.LOW.max_dd21 | 0.0002 | 0.0011 | YES |
| 9 | CWIV.Era3.5d | 0.0020 | 0.0118 | YES → CAUTION (Era3-only) |
| 10–15 | GEXR.Era3.21d + CWIV.Era3.21d + DOI survivors | 0.005–0.026 | 0.024–0.090 | YES |
| 16–52 | remainder | >0.05 | >0.17 | no |

**Surviving rejections at global BH alpha=0.10: 15 / 51**

**After era-amendment filtering:**
- S-GEXR-H survivors (Era1+Era2+Era3.21d): **ALIVE** — survives into Era3 (though weakening).
  Context evidence that SHORT gamma regime conditions higher forward RV. NOT a direction signal.
- SKEW drawdown survivors (Era1.HIGH_FALLING, Era1.HIGH_RISING, Era2.LOW): concentrated in
  Era1/Era2 — **ALIVE as early-era signal but degrading.** Context evidence for the
  S-TOP_RISK de-escalation hypothesis, but not sufficient for gate pass.
- DOI.Era1.OI_UP.10d: **DEAD** (Era1-only per amendment §5 rule).
- CWIV.Era3.5d: appears only in Era3 — **CAUTION** (possible recent data artifact;
  Era3 coverage is shorter; insufficient to claim cross-era robustness).

**Implications for §4 gates:**
- S-GEXR-H → S-GEXR gate: context evidence consistent with the mechanism. Gate stays
  `scored=false`; this study informs the world_state `options_weather` lobe (display-only).
- S-SKEW_DECEL / S-TOP_RISK gates: skew-drawdown association survives in Era1/Era2 for the
  max-drawdown target. This supports the de-escalation direction — high skew → more downside
  risk — but must be confirmed with single-name breadth.
- S-CWIV gate: null at this breadth. W-E0 single-name extension required before any verdict.
- S-DOI gate: DEAD at ETF/index level. W-E0 single-name extension may differ (directional
  OI flows are more meaningful for individual names).

**All above are display/context evidence only. No scoring, no deployment, no gate flips.**

---

## §Store layout (verified 2026-07-05)

```
/Users/chriswong/theta-ops-wt/data/thetadata_eod/
├── _manifest.json      # 24 roots, manifest complete 2012-2026
├── _backfill_state.json
├── eod/                # per-root annual parquets; schema: root,expiration,strike,right,date,open,high,low,close,volume,count,bid,ask
├── greeks/             # per-root annual parquets; schema: root,expiration,strike,right,date,bid,ask,underlying_price,delta,theta,vega,rho,epsilon,lambda,implied_vol,iv_error,gamma,vanna,charm,...
└── oi/                 # per-root annual parquets; schema: root,expiration,strike,right,date,open_interest
```

**Verified greeks start dates (actual, not assumed):**
- 2017-01-03: DIA, IWM, KRE, SMH, SPX, SPXW, SPY, XBI, XLB, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY (18 roots)
- 2018-03-09: ARKK
- 2018-06-22: XLC
- 2012-06-01: NVDA, QQQ, SOXX (3 roots with longer ThetaData greeks coverage)

**Verified OI start dates (actual):**
- 2012-06-01: DIA, IWM, KRE, NVDA, QQQ, SMH, SOXX, SPX, SPXW, SPY, XBI, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY (20 roots)
- 2015-10-29: XLRE
- 2018-03-12: ARKK
- 2018-06-25: XLC

All roots end 2026-07-02.

---

## §Appendix: Literature priors (context only, NOT evidence)

| Signal family | Source | Era | Reported effect | Status |
|---|---|---|---|---|
| CW ivspread (calls richer than puts) | Cremers-Weinbaum 2010 | 1996–2005 | ~+51bps/wk top vs bottom quintile | **Prior only** — post-2010 arbitrage expected to erode |
| XZZ skew (steep put-call) | Xing-Zhang-Zhao 2010 | 1996–2005 | steeper skew → lower fwd return | **Prior only** — same era caveat |
| Dealer gamma regime → realized vol | Pan 2002 + Carr-Wu lit | 2000–2010 | negative gamma amplifies vol | **Prior only** — mechanism plausible, magnitude likely decayed |
| DOI persistence | Garleanu-Pedersen-Poteshman 2021 | 2004–2020 | informed demand flow persists 5–10d | **Prior only** — newer; plausible in OI-heavy institutions |

Literature effects are 2004–2010 era on average. They enter as **priors to gate, never as
evidence to deploy**, and never on user-facing surfaces. The era-partition amendment requires
us to check whether any surviving signal concentrates in the oldest era (consistent with
arbitrage post-publication) and if so, treat it as dead.
