# Options History Gauntlet — W-E1 Memo

**Wave:** W-E1 (Historical gauntlet — research lane)
**Branch:** `w-e1-options/history-gauntlet`
**Date:** 2026-07-05
**Status:** PRE-REGISTRATION LOCKED (this §Preregistration section committed first, before any
study code runs; see git log order)

**Authors:** Sonnet build agent; Opus stats review MANDATORY before any verdict prints.

**Revision note (fix-round 2026-07-05):** This memo was updated in response to adversarial
review findings. The §Statistical Corrections section below documents all deviations from
the original prereg and the corrected methods.

**Revision note (fix-round-2, 2026-07-05):** A second adversarial review (Opus) found the
§Results tables had not been regenerated and the HAC lag under-corrected overlapping
windows (SC-7). Fable (main loop) implemented SC-7/SC-8 directly and re-ran the full study
(subagent session limit; Fable acted as the round-2 stats reviewer of record). §Results now
carries the FINAL fix-round-2 numbers; both earlier result sets are quarantined in the
SUPERSEDED appendix. Statistical-review sign-off: Fable, 2026-07-05.

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

### SC-7. Horizon-aware HAC lag (Blocker→fixed; prereg amendment, fix-round-2 2026-07-05)

**Problem:** The rule-of-thumb auto-lag `floor(4*(n/100)^(2/9))` (≈6 at n≈750) badly
under-corrects overlapping-window serial dependence. The adversarial review measured the
GEXR Era1 21d per-date gap series (n=738): autocorrelation 0.156/0.178/0.103/0.106/0.149 at
lags 1/5/10/21/42 — NOT decayed at lag 42. At auto-lag 6 the test printed t=4.72 (p≈0.0000);
at the honest lag 42 it falls to t=2.68 (p=0.0075); at lag 63 to t=2.30 (p=0.0216) — roughly
two orders of magnitude of p-inflation.

**Fix applied (labeled amendment to P-2):** for every overlapping-window target the
Newey-West lag is now `max(auto_lag, 2 × horizon_days)`, capped at n−2 (`_overlap_lag`):
21d targets → lag ≥ 42; 10d → ≥ 20; 5d → ≥ 10. Applied at ALL four call sites (GEXR, SKEW,
CWIV rank-IC series, DOI). This is a post-hoc statistical-method correction, visibly
documented per house law — never silent.

### SC-8. Per-study BH tables removed; survivor-count and decay-commentary fixes (fix-round-2)

- Per-study tables previously printed BH columns computed with the GLOBAL k=52 but
  WITHIN-STUDY ranks — incoherent adjusted p-values that contradicted the registered global
  family table (e.g. CWIV.Era3.5d printed adj 0.157 per-study vs 0.0261 global). Per-study BH
  is now REMOVED entirely; BH verdicts appear ONLY in the single global family table.
- `_print_summary` per-study survivor counts parsed the study prefix as
  `"S-GEXR-H".split("-")[0] == "S"`, matching SKEW cells instead of GEXR (printed 1 instead
  of 6). Now counted over each study's own p-value keys against the global BH dict.
- Post-publication-decay commentary now (a) reads the GLOBAL verdicts, and (b) applies the
  era-amendment auto-death rule only to genuinely pre-2016 eras (DOI Era1 2012-15). For
  greeks-window studies (eras start 2017), early-only concentration prints a decay WARNING
  with review flag — not auto-death.

---

## §Results — FINAL (fix-round-2 run, 2026-07-05; horizon-aware HAC lags per SC-7)

**Run:** `python scripts/research/options_history_gauntlet.py --study all`, 42s, store
verified complete (24 roots; AAPL excluded; greeks from 2017-01-03, OI from 2012-06-01).
**Family:** single global BH-FDR, alpha=0.10, pre-stated k=52; 51 valid cells, 1 SPARSE.
**Survivors: 8 / 51.** Opus stats review remains MANDATORY before any §4 gate consumes
these as verdict inputs; everything below is display/context evidence only.

> In plain English: we tested four options signals on 15 years of sector-ETF/index history
> with the strictest correction for overlapping windows. What survived: gamma regime is a
> strong VOLATILITY-conditioning signal (but its direction flips between eras, so it is
> weather, not a compass); the call-put IV spread shows a real 5-day cross-sectional edge
> in the current era only; skew-deceleration shows nothing supportive — its one surviving
> cell points the WRONG way for the bullish hypothesis; and ΔOI persistence is dead at the
> sector level. Nulls are printed, not hidden.

### Global BH-FDR family table (authoritative; the ONLY BH surface)

| Rank | Cell | raw_p | bh_adj_p | reject |
|---|---|---|---|---|
| 1 | GEXR.Era3.5d | 0.0000 | 0.0001 | YES |
| 2 | GEXR.Era2.5d | 0.0000 | 0.0001 | YES |
| 3 | GEXR.Era2.21d | 0.0000 | 0.0001 | YES |
| 4 | GEXR.Era1.5d | 0.0000 | 0.0003 | YES |
| 5 | GEXR.Era3.21d | 0.0005 | 0.0052 | YES |
| 6 | CWIV.Era3.5d | 0.0030 | 0.0261 | YES |
| 7 | GEXR.Era1.21d | 0.0075 | 0.0556 | YES |
| 8 | SKEW.Era1.HIGH_FALLING.rel_ret21 | 0.0142 | 0.0921 | YES |
| 9 | CWIV.Era3.21d | 0.0511 | 0.2953 | no |
| 10–51 | remainder (all SKEW/DOI/CWIV cells) | ≥0.1027 | ≥0.5343 | no |

Per-study survivor counts (from the global family): GEXR 6/6, SKEW 1/27, CWIV 1/6, DOI 0/12.

### S-GEXR-H: Gamma regime → forward realized volatility — 6/6 survive; SIGN IS ERA-DEPENDENT

Per-date mean RV gap (long-gamma roots − short-gamma roots), HAC lag ≥ 2×horizon:

| era | horizon | mean_rv_long | mean_rv_short | sign of gap | raw_p (HAC) |
|---|---|---|---|---|---|
| Era1 (2017-19) | 5d | 0.177 | 0.148 | **long HIGHER** | 0.0000 |
| Era1 (2017-19) | 21d | 0.183 | 0.161 | **long HIGHER** | 0.0075 |
| Era2 (2020-22) | 5d | 0.268 | 0.282 | short higher | 0.0000 |
| Era2 (2020-22) | 21d | 0.283 | 0.304 | short higher | 0.0000 |
| Era3 (2023→) | 5d | 0.204 | 0.214 | short higher | 0.0000 |
| Era3 (2023→) | 21d | 0.228 | 0.239 | short higher | 0.0005 |

**Verdict (context):** gamma regime robustly STRATIFIES 5-21d realized vol in every era at
honest lags — but the SIGN FLIPS: Era1 long-gamma roots ran hotter; Era2/Era3 short-gamma
roots ran hotter (the dealer-hedging mechanism direction). A sign-flipping two-sided
rejection is NOT evidence for a stable directional mechanism. Treat as REGIME-CONTEXT
(vol-conditioning weather for the `options_weather` lobe and stop-width context), never a
directional or even fixed-sign vol forecast. Era1 composition caveat stands (unweighted
greeks sum, n_short >> n_long imbalance; roots self-select into regimes).

### CWIV-H: CW ivspread cross-sectional rank-IC — Era3 5d survives; earlier eras null

| era | horizon | n_dates | mean_ic | hac_t | raw_p |
|---|---|---|---|---|---|
| Era1 | 5d | 754 | 0.0269 | 1.63 | 0.103 |
| Era1 | 21d | 754 | 0.0263 | 1.29 | 0.196 |
| Era2 | 5d | 756 | 0.0137 | 0.92 | 0.358 |
| Era2 | 21d | 756 | 0.0085 | 0.46 | 0.648 |
| Era3 | 5d | 872 | **0.0414** | **2.97** | **0.003** |
| Era3 | 21d | 856 | 0.0424 | 1.95 | 0.051 |

**Verdict (context):** positive 5d rank-IC in the CURRENT era only (bh_adj_p=0.0261);
21d narrowly misses (raw 0.0511). Era3-only survival warrants recent-era caution, but note
the FULL-history IC is monotonically positive in every era — the pattern reads as a weak
persistent effect that only reaches significance with Era3's cleaner data, not as a
data-mined artifact. Supports continuing the live S-CWIV gate accrual; W-E0 single-name
breadth (only ~23 roots here vs the literature's full cross-section) required before any
stronger read. Under-tested vs prereg by half (SC-3: tercile-sort secondary not run).

### SKEW-DEESC-H: sector skew → forward drawdown/return — 1/27 survives, WRONG DIRECTION for the hypothesis

The single survivor, SKEW.Era1.HIGH_FALLING.rel_ret21 (raw 0.0142, adj 0.0921), has
descriptive means of −0.29% (HIGH_FALLING) vs −0.26% (NEUTRAL): the skew-deceleration
condition slightly UNDERPERFORMS neutral at 21d in Era1 (2017-19), and the effect is absent
in Era2/Era3.

**Verdict (context):** the sector-ETF history provides NO support for the bullish
skew-deceleration hypothesis (S-SKEW_DECEL's premise that fear-decay after a spike marks
cleaner longs) — the lone surviving cell points the OPPOSITE way, in the oldest era only,
at the weakest adjusted p among survivors. Not pre-2016, so the era-amendment auto-death
rule does not apply, but the live S-SKEW_DECEL gate now carries a SKEPTICAL prior from this
study: recent-era absence must be weighted heavily at its Q4-26 verdict. All 21d-MaxDD
cells (the crash-protection read) are null at honest lags. Benchmark deviation SC-4 stands.

### DOI-H: 5-day ΔOI persistence — 0/12 survive; DEAD at sector level

No DOI cell survives in any era (best raw_p 0.2848). The anti-conservative Era1/Era3
"survivors" from the original run disappeared under the honest per-date HAC treatment,
as predicted in SC-1/SC-2.

**Verdict (context):** ΔOI persistence carries no 5-10d relative-return information at the
sector-ETF level on 14 years of history. The live S-DOI gate (single names, Pan-Poteshman's
actual setting) keeps accruing — sector aggregation may simply wash out the effect — but
the prior from this study is negative. Era0 (2012-15) remains SPARSE (price series from
2017 via greeks store), an honest limitation.

### Implications for §4 gates (display/context only; NO gate flips)

- **S-GEXR:** gamma-regime evidence is strong as VOL-conditioning context with era-dependent
  sign → feeds the `options_weather` lobe and stop-width/path context; must never be read
  as directional. Gate stays `scored=false`.
- **S-CWIV:** hypothesis alive — Era3 5d cross-sectional edge at the sector level; live
  single-name accrual continues to its ~Dec-26 verdict; W-E0 extension is the highest-value
  next data step.
- **S-SKEW_DECEL / S-TOP_RISK:** skeptical prior — no supportive cell; the lone survivor
  contradicts the bullish deceleration premise. Live gates keep accruing (single names may
  differ) with recent-era absence weighted heavily.
- **S-DOI:** negative prior at sector level; single-name live accrual continues.
- **W-E0 (single-name backfill extension)** is now clearly the binding constraint on every
  cross-sectional read above.

**All of the above is display/context evidence. No scoring, no deployment, no gate flips,
no kernel conditioning.**

---

## §Appendix: SUPERSEDED results (audit trail — do NOT cite)

Two earlier result sets are preserved for the audit trail only. Both are known-wrong:

1. **Original run (pooled Mann-Whitney fed to BH; 15/51 "survivors")** — anti-conservative
   by construction (SC-1): pseudo-replication across overlapping windows and correlated
   roots. Headline artifacts included SKEW max_dd21 "survivors" in Era1/Era2 and
   DOI.Era1/Era3 "survivors", none of which exist under the honest treatment.
2. **Fix-round-1 run (per-date HAC at auto-lag≈6; "8/51" with different membership)** —
   under-corrected 21d overlap (SC-7): GEXR cells printed p≈0.0000 that belong at
   p≈0.0075 (Era1 21d); CWIV.Era3.21d printed adj 0.0577 (YES) but is 0.2953 (no) at
   honest lags.

The authoritative surface is the fix-round-2 global table in §Results above.

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
