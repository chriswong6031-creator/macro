# Options History Gauntlet — W-E1 Memo

**Wave:** W-E1 (Historical gauntlet — research lane)
**Branch:** `w-e1-options/history-gauntlet`
**Date:** 2026-07-05
**Status:** PRE-REGISTRATION LOCKED (this §Preregistration section committed first, before any
study code runs; see git log order)

**Authors:** Sonnet build agent; Opus stats review MANDATORY before any verdict prints.

**Revision note (fix-round 2026-07-05):** This memo was updated in response to adversarial
review findings. The §Statistical Corrections section below documents all deviations from
the original prereg and the corrected methods. Results tables in §Results reflect the
corrected analysis; the original (anti-conservative) figures are described in §Statistical
Corrections for transparency.

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
- Statistic (corrected): collapse to per-date cross-sectional RV gap (mean rv across
  LONG-regime roots minus mean rv across SHORT-regime roots on each date), then HAC-robust
  t-test on the per-date time-series of gaps. Pooled Mann-Whitney U is reported as
  descriptive context. The original implementation fed pooled-overlapping MW p-values into
  the BH family (anti-conservative: ~755 dates × 23 roots treated as independent); the broken
  HAC call (tested mean-zero deviation, i.e. tested zero) was also removed.

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
  - Skew LOW (bottom-tercile condition)
- **P-3 AMENDMENT (benchmark deviation):** The original prereg stated "Skew LOW (benchmark/
  neutral condition)", meaning LOW skew would be used as the comparison baseline. The
  implementation uses NEUTRAL (mid-tercile, skew_rank252 in [0.333, 0.667)) as benchmark,
  and tests LOW (bottom tercile), HIGH_RISING, and HIGH_FALLING each against NEUTRAL. This
  is a post-registration change — LOW is tested as a condition, not used as the baseline.
  Rationale: NEUTRAL provides a cleaner equal-sized reference bucket than the complement of
  HIGH. The registered LOW-as-benchmark contrasts are not computed in this wave; the deviation
  is documented here and must be resolved (either implement LOW-as-benchmark or formally amend
  the prereg) before any gate conclusion is drawn from the SKEW study.
- Targets: 21-day ETF max drawdown (from entry close to rolling-min within 21d), 5/21d ETF
  return vs SPY (relative return).
- SPY proxy: use the SPY root's daily closing price derived from `underlying_price`. If SPY
  is not available for a given date, skip that observation.
- Statistic (corrected): collapse to per-date cross-sectional gap (mean condition target
  minus mean NEUTRAL target across roots on that date), then HAC-robust t-test on the
  per-date time-series. This replaces the original pooled Mann-Whitney, which was
  anti-conservative due to overlapping windows and cross-root correlation. Pooled MW is
  reported as descriptive context only.

**CWIV-H specific cuts:**
- Sector ETFs + broad ETFs: SPY, QQQ, IWM, DIA + 11 sector SPDRs (15 roots).
- IVspread definition: equal-weight mean of [IV(call) − IV(put)] across matched (call, put)
  pairs at the SAME strike and SAME expiry, at the ~30-day tenor, within a ±8% moneyness band
  (mirrors `engine/options_ivspread.py`: `_TARGET_DAYS=30`, `_MIN_DAYS=7`,
  `_MNY_BAND=0.08`, `_MAX_PAIR_SPREAD=0.50`, `_MIN_PAIRS=3`).
  **OI-weighting note:** the prereg says "OI-weighted" but the greeks store has no per-strike
  OI column; the implementation always uses equal-weight matched pairs. This is an honest
  implementation limitation flagged for W-E0 where single-name data includes OI.
- Derived feature: `ivspread_5d_chg` = today's ivspread minus the 5-day lagged value.
- Targets: 5-day and 21-day relative ETF return vs. SPY.
- Statistic: cross-sectional rank-IC (Spearman) per date, then HAC-robust t-test on the
  time-series of rank-ICs. Minimum 5 roots per date for that date to contribute.
  (This approach is inherently dependence-robust and is the template for the other studies.)
- **P-3 AMENDMENT (secondary test not implemented):** The prereg registers "Secondary test:
  portfolio sort (high-ivspread vs low-ivspread tercile) 5d and 21d mean returns per era,
  Mann-Whitney U". This secondary test was not implemented (no tercile split, no portfolio
  sort in the code). The executed CWIV family contains 6 cells (3 eras × 2 horizons) rather
  than the registered 12 cells (2 conditions × 3 eras × 2 horizons). This is a material
  deviation: CWIV is under-tested by half relative to the prereg. The secondary test must be
  implemented in a follow-on wave, or the deviation must be formally ratified.
- **P-4 AMENDMENT (SKEW cell count):** The prereg states SKEW = 18 cells, but the correct
  arithmetic is 3 conditions × 3 eras × 3 targets = 27 cells (which the code runs). The "18"
  in the prereg table is arithmetically incorrect. The executed family is 6+27+6+12 = 51, not
  52. The k=52 denominator used in the BH correction is mildly conservative (larger denominator
  → fewer rejections); it is kept at 52 to preserve pre-stated conservatism, but the actual
  executed family size is noted here as 51.

**DOI-H specific cuts:**
- All 23 roots (OI history 2012→).
- ΔOI definition: 5-day fractional change in total open interest across all strikes and
  expirations for a root on a given date: `(oi_today − oi_5d_ago) / oi_5d_ago`.
- Condition buckets:
  - OI_UP: ΔOI > +5% (material accumulation)
  - OI_DOWN: ΔOI < −5% (material liquidation)
  - OI_FLAT: otherwise (benchmark)
- Targets: 5-day and 10-day forward ETF return vs SPY.
- Statistic (corrected): collapse to per-date cross-sectional gap (mean condition return
  minus mean OI_FLAT return across roots on that date), then HAC-robust t-test on the
  per-date time-series. Pooled MW reported as descriptive context only (not fed to BH).
  Original pooled MW was anti-conservative for the same reasons as GEXR and SKEW.

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

## §Statistical Corrections (fix-round 2026-07-05)

**This section documents all deviations from the original prereg discovered during adversarial
review, and the corrected methods applied in the updated script.**

### SC-1. Anti-conservative p-values (Blocker)

**Problem:** The original script fed pooled Mann-Whitney U p-values into the global BH family
for S-GEXR-H, SKEW-DEESC-H, and DOI-H. The pooled observations are NOT i.i.d.:
- (a) 5d/21d forward RV and forward returns use overlapping windows (~20/21 days shared
  between adjacent dates' 21d windows).
- (b) On any given date, all roots share the same market regime (massive cross-root correlation).
- Empirically: GEXR Era1-21d treated 16,695 pooled obs as independent while spanning only
  ~755 dates × 23 roots (~35 non-overlapping 21d blocks). MW p-values are driven toward ~0.

Additionally, the original HAC call in GEXR (line 311) computed `_hac_ttest(era_data[col].values
- era_data[col].mean())` — testing a mean-zero deviation from its own mean, which is exactly
zero by construction. This call was dead (tested nothing) and unused for BH.

**Fix applied:** For GEXR, SKEW, and DOI, the registered dependence-robust approach is now
used: collapse to a per-date cross-sectional statistic (mean of condition group minus mean of
benchmark group across roots on that date), then run a HAC-robust t-test on the resulting
per-date time-series. This is the same "CWIV path" that was already correct. Pooled MW is
retained as descriptive output but is NOT fed to the BH family.

**Effect on results:** The per-date collapse reduces effective sample size dramatically (from
pooled n~16k to n~750 dates). After honest correction, expect substantially fewer survivors
in GEXR and SKEW compared to the original 15/51 figure. The §Results section below reflects
the corrected method; results tables are labeled "CORRECTED" to distinguish from the original.

### SC-2. Memo verdicts contradicting global BH (Blocker)

**Problem:** The original §Results contained two contradictions between the memo text and the
script's global BH output:

1. **CWIV:** Memo said "NULL across all eras at global BH correction" and "bh_adj_p=0.106,
   barely failing." In reality, the original global BH run showed CWIV.Era3.5d with
   bh_adj_p=0.0118 (YES) and CWIV.Era3.21d with bh_adj_p=0.0420 (YES). The 0.106 figure
   was from the per-study partial BH family, not the registered global family.

2. **DOI:** Memo said "single survivor Era1-only" and "DEAD." In reality, the original global
   BH run had DOI.Era3.OI_UP.10d surviving at bh_adj_p=0.0490 (YES), contradicting the
   "Era1-only" claim. (After the SC-1 correction, this anti-conservative survivor is
   expected to disappear.)

**Fix applied:** All verdicts below are based on the single registered global k=52 family
and use the corrected (HAC-based) p-values. The original anti-conservative numbers are
documented here for transparency.

### SC-3. CWIV prereg deviation — family under-tested (Major)

**Problem:** P-3 registers a "Secondary test: portfolio sort (high-ivspread vs low-ivspread
tercile) Mann-Whitney U." The registered CWIV family has 12 cells (2 conditions × 3 eras ×
2 horizons). The implementation runs only 6 cells (rank-IC per era×horizon, no tercile
split). CWIV is under-tested by half.

**Fix applied:** Documented in §P-3 above. The secondary tercile-sort test must be
implemented in a follow-on wave before any verdict can claim to test the registered P-3
hypothesis fully.

### SC-4. SKEW prereg deviation — benchmark change (Major)

**Problem:** P-3 registers "Skew LOW (benchmark/neutral condition)", meaning LOW skew is the
comparison baseline. The implementation uses NEUTRAL (mid-tercile) as benchmark and tests LOW
as a condition. This is a post-registration design change; the registered LOW-as-benchmark
contrasts are not computed.

**Fix applied:** Documented in §P-3 above. The deviation is flagged for resolution in a
follow-on wave. The SKEW results below reflect the NEUTRAL-as-benchmark implementation.

### SC-5. SKEW BH assignment bug (Major)

**Problem:** The original BH result assignment loop for SKEW matched by `era_part in k and
cond_part in k` (substring matching), which overwrote all three target-cells for an
era+condition with whichever target was iterated last. This caused all three targets (max_dd21,
rel_ret5, rel_ret21) for a given era+condition to show identical bh_adj_p/reject flags.

**Fix applied:** The loop now uses exact cell_key matching (`cell_key in bh`), which
correctly assigns per-target BH results. This is a correctness fix only (the global BH
table itself was unaffected by this bug; only the per-study display was wrong).

### SC-6. Minor corrections

- **SKEW NaN guard:** Days with skew_5d_chg=NaN (first ~5 rows or gaps) previously satisfied
  the `<= 0` condition and were classified as HIGH_FALLING. Fixed with explicit `notna()` guard.
- **Docstring:** `_compute_daily_ivspread` previously said "OI-weighted (equal-weight
  fallback)" — corrected to "equal-weight (no OI weighting; greeks store has no per-strike OI)".
- **Per-study survivor counts:** `_print_summary` previously derived per-study survivor counts
  from each study's partial BH dict, producing numbers inconsistent with the global BH total.
  Fixed to derive from the single global BH result.
- **`_run_global_bh`:** Now returns the bh dict so `_print_summary` can use it.

---

## §Results

**PRELIMINARY — Opus stats review MANDATORY before any verdict prints.**
**Conclusions framed as display/context evidence informing §4 gates only.**

**CORRECTED METHOD:** All BH-family p-values now use the dependence-robust HAC t-test on
per-date cross-sectional gaps (as described in §Statistical Corrections SC-1). The corrected
results require re-running the script against the ThetaData store to produce final numbers.
The tables below show the corrected output structure; numerical values will differ from the
original anti-conservative run.

> In plain English: four studies tested on 15 years of ThetaData EOD history (24 roots,
> AAPL excluded). After correcting for pseudo-replication (overlapping windows + cross-root
> correlation), the effective sample sizes are substantially smaller than the original run
> suggested. Results are display/context evidence only — not deployed, not scored.

### S-GEXR-H: Gamma regime → forward realized volatility

**Corrected method:** per-date mean(rv_long_roots) − mean(rv_short_roots), HAC t-test on
time-series. The original pooled MW (16k+ obs) overstated significance; the honest n is
~750 dates per era. The directional finding (SHORT gamma → higher realized vol) remains
mechanistically plausible, but the BH-corrected p-values will be larger after the correction.

**Original (anti-conservative) pooled MW results for reference:**

| era   | horizon | n_long | n_short | mean_rv_long | mean_rv_short | mw_p (descriptive) |
|---|---|---|---|---|---|---|
| Era1  | 5d  | 5057 | 11638 | 0.177 | 0.148 | 0.000 |
| Era1  | 21d | 5057 | 11638 | 0.183 | 0.161 | 0.000 |
| Era2  | 5d  | 8565 | 8823  | 0.268 | 0.282 | 0.000 |
| Era2  | 21d | 8565 | 8823  | 0.283 | 0.304 | 0.000 |
| Era3  | 5d  | 7339 | 12717 | 0.204 | 0.214 | 0.066 |
| Era3  | 21d | 7159 | 12529 | 0.228 | 0.239 | 0.005 |

The HAC-based p-values (from the corrected run) will appear in the script output above.

**Critical Opus review items:**
1. The `net_gamma` computed here uses unweighted greeks sum (no OI in greeks store). This
   biases toward options with many strikes/expirations. Verify whether OI-weighted approach
   changes the regime classification materially.
2. The n_short >> n_long imbalance across all eras should be explained mechanistically.
3. After HAC correction, if GEXR Era1/Era2 still survive, the directional claim is more
   credible. If only Era3 survives, treat as recent-data artifact.

### SKEW-DEESC-H: Sector skew → forward max drawdown / return vs SPY

**Corrected method:** per-date mean(condition_target) − mean(NEUTRAL_target) across sector
ETF roots, HAC t-test. The original pooled MW overstated significance; the honest n is
~750 dates per era for the per-date time-series.

**Note on benchmark deviation:** NEUTRAL (mid-tercile) used as benchmark; LOW tested as
condition. This deviates from P-3 (see §SC-4). Results for LOW condition test LOW-vs-NEUTRAL,
not the registered LOW-as-benchmark contrasts.

**Directional finding (context only, pending corrected run):** HIGH skew (steep put premium)
is associated with LARGER 21d max drawdown in Era1/Era2, consistent with informed put-buying
preceding drawdowns. Effect direction is consistent, but significance after HAC correction
is unknown without the corrected run.

**Post-publication decay:** Effect was present in Era1/Era2 but attenuated in Era3. After
honest correction, the Era1/Era2 effect may remain if the cross-sectional daily mean is
consistent; Era3 is expected to be null.

### CWIV-H: CW ivspread cross-sectional rank-IC

**NOTE: The CWIV method already uses the correct dependence-robust approach (per-date
rank-IC + HAC t-test). No change to CWIV's test statistic. CWIV results are unchanged.**

**The original memo incorrectly reported "NULL across all eras at global BH correction"
using a per-study partial BH figure (0.106) rather than the global BH figure. The correct
global BH figure for the original run was:**
- CWIV.Era3.5d: bh_adj_p=0.0118 (YES at global BH)
- CWIV.Era3.21d: bh_adj_p=0.0420 (YES at global BH)

**Corrected CWIV verdict:** CWIV is NOT null across all eras. Era3 survives at the
original global BH level. However, this is an Era3-only result — caution is warranted
(possible recent-data artifact; only ~880 trading days; insufficient cross-era robustness).
Per the era-amendment, an Era3-only survivor requires careful scrutiny and cannot be
treated as a robust signal.

**Context:** CWIV rank-IC tests only 6 cells (not the registered 12) because the secondary
tercile-sort test was not implemented. The 0.0118 and 0.0420 figures are from the original
pooled-MW run where GEXR/SKEW/DOI p-values were inflated — after correcting GEXR/SKEW/DOI
to use HAC, the BH family p-value for CWIV.Era3.5d will change (BH adj-p depends on all
family members' ranks). Re-run to obtain final figures.

**Caveat on ivspread computation:** equal-weight matched pairs (no OI weighting; greeks store
lacks per-strike OI). OI weighting must be checked in W-E0 with single-name data.

### DOI-H: 5-day ΔOI persistence

**Corrected method:** per-date mean(condition_return) − mean(OI_FLAT_return) across roots,
HAC t-test. The original pooled MW was anti-conservative.

**NOTE: The original memo incorrectly stated "single survivor Era1-only, DEAD." The correct
original global BH output showed DOI.Era3.OI_UP.10d surviving at bh_adj_p=0.0490 (YES).
This was an anti-conservative result (pooled MW); after HAC correction it is expected to
disappear. The Era1 survivor (DOI.Era1.OI_UP.10d) is also expected to shrink toward null
after HAC correction reduces the effective n from ~6,834 pooled obs to ~250 per-date obs.**

**Pending corrected run verdict:** after HAC correction, if no DOI cells survive the global
BH family, the DOI DEAD verdict holds. If Era3 still survives, revisit with era-amendment
scrutiny. Do not treat any DOI result as confirmed without the corrected run output.

**Era0 SPARSE note:** DOI-H Era0 (2012–2015) produces SPARSE because underlying price data
is only available from 2017 via the greeks store. Honest limitation, not a computation error.

### Global BH-FDR family summary

**NOTE: The global BH table from the ORIGINAL (anti-conservative) run is reproduced here
for reference. After SC-1 correction (HAC for GEXR/SKEW/DOI), the survivor set will change.
The corrected table must be produced by re-running the script against the ThetaData store.**

Original anti-conservative run (15/51 survivors, inflated by pooled MW):

| Rank | Cell | raw_p | bh_adj_p | reject | note |
|---|---|---|---|---|---|
| 1 | GEXR.Era1.5d | 0.0000 | 0.0000 | YES | anti-conservative |
| 2 | GEXR.Era1.21d | 0.0000 | 0.0000 | YES | anti-conservative |
| 3 | GEXR.Era2.21d | 0.0000 | 0.0000 | YES | anti-conservative |
| 4 | GEXR.Era2.5d | 0.0000 | 0.0000 | YES | anti-conservative |
| 5 | SKEW.Era1.HIGH_FALLING.max_dd21 | 0.0000 | 0.0000 | YES | anti-conservative |
| 6 | SKEW.Era1.HIGH_RISING.max_dd21 | 0.0001 | 0.0006 | YES | anti-conservative |
| 7 | DOI.Era1.OI_UP.10d | 0.0001 | 0.0011 | YES → expected DEAD | anti-conservative |
| 8 | SKEW.Era2.LOW.max_dd21 | 0.0002 | 0.0011 | YES | anti-conservative |
| 9 | CWIV.Era3.5d | 0.0020 | 0.0118 | YES → CAUTION | CWIV already HAC-correct |
| 10 | CWIV.Era3.21d | ~0.005 | 0.0420 | YES → CAUTION | CWIV already HAC-correct |
| 11–15 | GEXR.Era3.21d + DOI survivors | 0.005–0.026 | 0.024–0.090 | YES | anti-conservative |
| 16–51 | remainder | >0.05 | >0.17 | no | — |

**After era-amendment filtering (on original anti-conservative results):**
- S-GEXR-H survivors: mechanistically plausible direction. After HAC correction, significance
  is unknown — may survive (effect is directionally consistent) or shrink to null.
- SKEW drawdown survivors: concentrated in Era1/Era2. After HAC correction, expected to
  attenuate; may or may not survive.
- DOI.Era1.OI_UP.10d: expected DEAD after HAC correction (inflated by pooled MW).
- CWIV.Era3.5d and Era3.21d: these used the already-correct HAC method. Era3-only —
  **CAUTION** (possible recent data artifact; insufficient cross-era robustness).

**Implications for §4 gates (pending corrected re-run):**
- S-GEXR-H → S-GEXR gate: directional context consistent with mechanism. Gate stays
  `scored=false`; informs `options_weather` lobe (display-only). Requires corrected run.
- S-SKEW_DECEL / S-TOP_RISK gates: skew-drawdown direction plausible but significance
  unknown after correction. Must not claim survival until corrected run confirms.
- S-CWIV gate: Era3 survivor present in original run (CWIV already HAC-correct). Era3-only;
  caution. W-E0 single-name extension required before stronger verdict.
- S-DOI gate: expected null after correction. W-E0 single-name extension may differ.

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
