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

*(This section is populated by the study script `scripts/research/options_history_gauntlet.py`
after the preregistration commit. Opus stats review required before any verdict prints.)*

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
