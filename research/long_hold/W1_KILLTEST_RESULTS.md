# Long-Hold Thesis Layer — W1 Kill-Test Results

**Wave:** W1 PR-F
**Pre-registration:** `research/long_hold/OBJECTIVE.md` (LOCKED, including Amendment A1)
**FDR family:** `long_hold` (isolated per LH-R5)
**Fable rulings:** LH-W1-1, LH-W1-2, LH-W1-3

> This document is produced by `scripts/research/missed_hold_study.py`. Results are printed as observed. The document does NOT declare the program's fate. See final section.

## 1. Feature Coverage (nine frozen features per OBJECTIVE.md §5)

Coverage computed on the kill-test subset (compounder + tactical_only fires).
Features with < 20% non-null coverage are dropped per §5 drop rule.

| Feature | Coverage | Status | Notes |
|---------|----------|--------|-------|
| `piotroski_f` | 52.3% | retained | Computed by label harness; from fundamentals_panel raw rows |
| `quality_z` | 56.7% | retained | ROA + CFO/assets composite; cross-sectional z-score |
| `profitability_z` | 56.7% | retained | NI/assets + CFO/assets; cross-sectional z-score (same inputs as quality_z — note: op_income unavailable from panel) |
| `sue` | 51.8% | retained | Standardized unexpected earnings: (ni - ni_prior) / assets_prior |
| `insider_cmp` | 0.0% | DROPPED (< 20% coverage) | NOT COMPUTABLE from fundamentals_panel (no insider filing data) |
| `interest_coverage` | 0.0% | DROPPED (< 20% coverage) | NOT COMPUTABLE from fundamentals_panel (interest_exp absent from panel) |
| `dilution_flag` | 52.3% | retained | shares YoY > +3% threshold; from fundamentals_panel shares column |
| `gross_margin_trend` | 20.1% | retained | 3-year OLS slope of gross_profit/revenue; last 3 PIT rows |
| `archetype` | 0.0% | DROPPED (< 20% coverage) | NOT PRE-COMPUTED in any parquet (no archetype field in fundamentals_panel) |

**Retained for analysis:** `piotroski_f`, `quality_z`, `profitability_z`, `sue`, `dilution_flag`, `gross_margin_trend`

**Dropped (< 20% coverage or not computable):** `insider_cmp`, `interest_coverage`, `archetype`

## 2. Kill-Test Population Summary

| Cohort | Fires | compounder | tactical_only |
|--------|-------|-----------|--------------|
| All (2014-2026) | 4601 | 195 | 4406 |
| Fit 2014-2019 (UPPER BOUND) | — | 26 dedup | 381 dedup |
| OOS 2020-2023 honest | 265 | 4 | 261 |
| OOS 2020-2023 all (biased) | 2383 | 98 | 2285 |

## 3. Inference Design

Per OBJECTIVE.md §6 (frozen at registration):

- **Test statistic:** Mann-Whitney rank-biserial correlation (RBC)
- **BH-FDR:** q ≤ 0.10 across all retained features simultaneously (§6.1)
- **CIs:** cluster-robust (ticker × macro_regime) + block-bootstrap; wider CI governs (§6.2)
  - _Deviation from §6.2_: spec requires (ticker_SECTOR × macro_regime); implemented as (ticker × macro_regime) because the labels parquet has no sector-category column (only sector_rel_252d as a float). Ticker-level clustering is finer than sector-level and may produce slightly narrow CIs. The block-bootstrap fallback (which governs when wider) partially mitigates this.
- **Episode-cluster floor:** n ≥ 25 independent (ticker × macro_regime) clusters per group (§6.3)
  - _Deviation from §6.3_: spec says ±10 TRADING days; implemented as ±14 CALENDAR days (≈10 trading days). Impact on the DEFERRED verdict is nil (4 compounders regardless of dedup window).
- **Reshuffle null:** 1,000 within-(cohort_year × macro_regime) permutations; 90th percentile threshold (§6.4); seed=42 (LOCKED in pre-registration)
- **Bootstrap seeds:** block-bootstrap uses seed=43; cluster-bootstrap uses seed=44 (distinct from reshuffle seed=42 to avoid correlated draws across independent inference gates)
- **G1 criterion:** a feature must clear ALL THREE gates (BH-FDR + reshuffle + n-floor) on the OOS honest cohort

## 4. Fit Period Results (2014-2019) — UPPER BOUND Explorer

> **UPPER BOUND — survivor-only.** Pre-2021-07 cohorts are survivorship-biased (estimated 200-500 bps/yr overstatement). These results are direction-finding ONLY. The G1 decision cell is §5 (OOS honest cohort).

### fit_2014-2019_UPPER_BOUND

**Survivorship stamp:** UPPER BOUND — survivor-only cohort. All pre-2021-07 fires have survivorship_biased=True. Estimated bias: 200-500 bps/yr overstatement in absolute returns. This split is exploration only; the G1 decision cell is OOS 2020-2023.

| Metric | Value |
|--------|-------|
| Episode-cluster count | 407 |
| missed_hold clusters | 26 |
| tactical_only clusters | 381 |
| n-floor met (≥25) | YES |
| G1 status (this split) | **SURVIVE** |

#### Per-feature results

| Feature | n MH covered | n TO covered | RBC | 95% CI | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle null | Reshuffle null p90 |
|---------|-------------|-------------|-----|--------|---------|------------|----------------|----------------------|-------------------|
| piotroski_f | 26 | 223 | 0.8142 | [0.0333, 0.8787] | 0.0000 | 0.0000 | YES* | YES* | 0.2730 |
| quality_z | 26 | 286 | 0.4541 | [-0.1667, 0.6667] | 0.0001 | 0.0003 | YES* | YES* | 0.1790 |
| profitability_z | 26 | 286 | 0.4541 | [-0.1667, 0.6667] | 0.0001 | 0.0003 | YES* | YES* | 0.1790 |
| sue | 26 | 236 | 0.3809 | [-0.3000, 0.6000] | 0.0014 | 0.0022 | YES* | YES* | 0.2459 |
| dilution_flag | 26 | 274 | 0.0261 | [-0.2667, 0.2667] | 0.8259 | 0.8259 | no | no | 0.0682 |
| gross_margin_trend | 17 | 75 | 0.2933 | [0.0688, 1.0000] | 0.0599 | 0.0719 | YES* | no | 0.3202 |

**G1 survivors (pass both BH-FDR and reshuffle null):** piotroski_f, quality_z, profitability_z, sue


## 5. OOS Honest Cohort Results (2020-2023) — G1 Decision Cell

> **This is the pre-registered G1 decision cell.** Only fires with survivorship_biased=False are included. Per OBJECTIVE.md §8 pre-registration: if the OOS honest n-floor is not met, the G1 criterion cannot fire from honest data alone → routed to survivorship-deferral path.

### oos_2020-2023_honest

**Survivorship stamp:** OOS honest cohort: survivorship_biased=False only. These fires have resolvable price paths from the Massive whole-market store or Yahoo, with dead-name coverage from Polygon REST (post-anchor era; ESTIMATED/UNVERIFIED — dead_name_probe_results.json self-describes as 'PARTIALLY ESTIMATED — no raw probe script or sampled price bars were retained; ~95% post-anchor coverage figure is an estimate, not a measured sample; treat as estimated/unverified pending a committed probe script with sampled bars'). This is the pre-registered G1 decision cell.

| Metric | Value |
|--------|-------|
| Episode-cluster count | 265 |
| missed_hold clusters | 4 |
| tactical_only clusters | 261 |
| n-floor met (≥25) | NO |
| G1 status (this split) | **DEFERRED_N_FLOOR** |

> **REFUSED:** n-floor NOT MET: missed_hold clusters=4, tactical_only clusters=261. Floor requires ≥25 per group. Results for this split are REFUSED per OBJECTIVE.md §6.3 and routed to survivorship-deferral path per §8.


## 6. Sensitivity: fund_unchecked Excluded (Mandatory per §2.4)

Fires with `fund_unchecked=True` excluded from the contrast. Per §2.4: if primary and fund_unchecked-excluded results disagree in direction, primary is marked 'coverage-sensitive'.

### oos_2020-2023_honest_fund_unchecked_excluded

**Survivorship stamp:** OOS honest cohort with fund_unchecked=True fires EXCLUDED (mandatory sensitivity per OBJECTIVE.md §2.4). fund_unchecked fires are compounders assigned without confirmed F-score>=6.

| Metric | Value |
|--------|-------|
| Episode-cluster count | 265 |
| missed_hold clusters | 4 |
| tactical_only clusters | 261 |
| n-floor met (≥25) | NO |
| G1 status (this split) | **DEFERRED_N_FLOOR** |

> **REFUSED:** n-floor NOT MET: missed_hold clusters=4, tactical_only clusters=261. Floor requires ≥25 per group. Results for this split are REFUSED per OBJECTIVE.md §6.3 and routed to survivorship-deferral path per §8.


## 7. Amendment A1: Market-Benchmark Reassignment

> **SPEC-INFEASIBILITY — A1 results are APPROXIMATE SENSITIVITY ONLY.**
> The pre-registered S(f) constituent set (OBJECTIVE.md Amendment A1) requires
> "every ticker in the fire tape whose 252d fill-anchored forward price path
> is fully resolvable at that fire's own fire_date." This is NOT computable
> from long_hold_labels.parquet alone: the parquet has total_return_252d=null
> for all 34,604 tactical_only_fail fires and 65,723 unlabeled fires.
> The benchmark below uses ONLY the ~13,215 tactical-win rows with non-null
> 252d returns — a WINNER-SELECTED, UPWARD-BIASED pool that excludes all
> fires that never achieved tactical liftoff.
>
> Consequence: the 2021 cohort-year benchmark is 0.0178 (1.78%), computed from
> the winner pool. The 128 no-benchmark SLW fires in the OOS honest window
> (all strong performers, total_return_252d ranging 0.116–2.548) flip to
> compounder against this low bar, inflating the A1-honest compounder count
> from 4 to 132 and producing the A1 SURVIVE result. The A1 SURVIVE verdict
> **is NOT reported as evidence on the pre-registered S(f) specification.**
> It is an approximate sensitivity result and is labelled as such.
> The combined routing (§9) correctly gates on the primary DEFERRED verdict.

N fires reassigned from no-sector-benchmark: **3098**  | After A1: compounder=1456, tactical_only=2353

> **Benchmark approximation (winner-selected pool):** cohort-year equal-weight mean of total_return_252d (approximation of full per-fire S(f) computation; documented in A1 spec)

> **Survivorship caveat (A1):** Pre-2021 cohorts: S(f) is survivor-upward-biased → market benchmark depressed → excess Label G assignment direction documented per A1 spec.

### oos_2020-2023_honest_A1_market_benchmark

**Survivorship stamp:** Amendment A1: OOS honest cohort with market-benchmark reassignment of no-sector-benchmark fires. All null sector_rel_252d replaced with market_rel_252d (cohort-year EW mean approximation — see A1 spec). This is the pre-registered mandatory sensitivity run.

| Metric | Value |
|--------|-------|
| Episode-cluster count | 393 |
| missed_hold clusters | 132 |
| tactical_only clusters | 261 |
| n-floor met (≥25) | YES |
| G1 status (this split) | **SURVIVE** |

#### Per-feature results

| Feature | n MH covered | n TO covered | RBC | 95% CI | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle null | Reshuffle null p90 |
|---------|-------------|-------------|-----|--------|---------|------------|----------------|----------------------|-------------------|
| piotroski_f | 12 | 116 | 0.8103 | [0.7957, 0.8696] | 0.0000 | 0.0000 | YES* | YES* | 0.6494 |
| quality_z | 4 | 123 | 0.5041 | [0.2174, 0.5667] | 0.0870 | 0.1347 | no | YES* | 0.3984 |
| profitability_z | 4 | 123 | 0.5041 | [0.2174, 0.5667] | 0.0870 | 0.1347 | no | YES* | 0.3984 |
| sue | 4 | 116 | 0.4741 | [-0.1304, 0.6201] | 0.1078 | 0.1347 | no | no | 0.4851 |
| dilution_flag | 4 | 111 | -0.1351 | [-0.1818, -0.1236] | 0.6470 | 0.6470 | no | no | 0.1239 |
| gross_margin_trend | — | — | — | — | — | — | — | — | — |  _insufficient_coverage_ |

**G1 survivors (pass both BH-FDR and reshuffle null):** piotroski_f


## 8. OOS All-Fires Context (Survivorship-Biased; NOT G1 Cell)

> **NOT the G1 decision cell.** Included for directional context only. Acquisition-premium bias in compounder label documented above.

### oos_2020-2023_all_SURVIVORSHIP_BIASED

**Survivorship stamp:** Full OOS 2020-2023 including survivorship-biased fires. Includes pre-anchor fires where dead names are missing → compounder label is over-represented (acquisitions look like compounders). This is NOT the G1 decision cell. Reported for context and direction-finding.

| Metric | Value |
|--------|-------|
| Episode-cluster count | 2383 |
| missed_hold clusters | 98 |
| tactical_only clusters | 2285 |
| n-floor met (≥25) | YES |
| G1 status (this split) | **SURVIVE** |

#### Per-feature results

| Feature | n MH covered | n TO covered | RBC | 95% CI | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle null | Reshuffle null p90 |
|---------|-------------|-------------|-----|--------|---------|------------|----------------|----------------------|-------------------|
| piotroski_f | 98 | 1129 | 0.7481 | [0.1833, 0.8085] | 0.0000 | 0.0000 | YES* | YES* | 0.1304 |
| quality_z | 98 | 1212 | 0.4124 | [-0.2333, 0.5395] | 0.0000 | 0.0000 | YES* | YES* | 0.0987 |
| profitability_z | 98 | 1212 | 0.4124 | [-0.2333, 0.5395] | 0.0000 | 0.0000 | YES* | YES* | 0.0987 |
| sue | 95 | 1103 | 0.3453 | [-0.2241, 0.4577] | 0.0000 | 0.0000 | YES* | YES* | 0.1152 |
| dilution_flag | 97 | 1108 | -0.1166 | [-0.1478, 0.1000] | 0.0567 | 0.0680 | YES* | no | 0.0404 |
| gross_margin_trend | 61 | 458 | 0.1028 | [-0.3827, 0.3382] | 0.1917 | 0.1917 | no | YES* | 0.0971 |

**G1 survivors (pass both BH-FDR and reshuffle null):** piotroski_f, quality_z, profitability_z, sue


## 9. Combined Routing (Primary × A1 per Amendment A1 rules)

| Leg | G1 status |
|-----|-----------|
| Primary (OOS honest) | DEFERRED_N_FLOOR |
| A1 (market benchmark) | SURVIVE |
| **Combined** | **DEFERRED** |

Routing interpretation per Amendment A1 table: DEFERRED if either leg is DEFERRED_N_FLOOR; AGREED_KILL if both KILL; AGREED_SURVIVE if both SURVIVE; DISAGREE_REMEDIATION if one KILL and one SURVIVE (no deferral).

> **Note on A1 SURVIVE:** the A1 SURVIVE result is computed on a non-spec benchmark (winner-selected cohort-year mean, not the pre-registered per-fire S(f)). Per §7 above, it is not reportable as evidence on the pre-registered specification. The combined routing is correctly DEFERRED (driven by the primary leg's DEFERRED_N_FLOOR). The A1 SURVIVE cell does not alter this routing and is not presented as a reprieve.

## 10. In Plain English

> **What this study measured:**
> We asked one question: when a stock fires our entry signal and then becomes
> a multi-year winner (what we call a 'compounder'), could we have known that
> at the moment of the signal — before the stock moved — using quality metrics
> we already track (Piotroski score, quality z-score, earnings surprise, etc.)?
> The contrast is: compounders (multi-year winners from entry) vs tactical-only
> fires (bounced and faded within a year).
>
> **What the data constraint means (LH-W1-3 verified forward-leg source):**
> The honest test requires a survivorship-correct price source so that companies
> that eventually failed or were delisted are represented. Dead-name forward legs
> ARE present in the honest cell: data/edgar/dead_name_prices.parquet was built
> from Polygon REST (415 tickers, continuous coverage 2021-07-06→2026-06-02,
> source='polygon'). This covers the entire honest OOS window
> (2021-07-06→2021-10-22); all 271 honest fires have gap_leg_crossed=False
> and full 252d returns, confirming the Polygon dead-name build fills the gap.
> COVERAGE CAVEAT: the ~95% post-anchor coverage figure from
> dead_name_probe_results.json is ESTIMATED — no committed probe script with
> sampled price bars was retained; treat coverage as estimated/unverified.
>
> **Why the test is deferred — window length, not missing dead names:**
> The honest OOS window is approximately 3.5 months (2021-07-06→2021-10-22)
> because the 1,165-day Massive store gap begins 2021-10-25. In that window,
> only 4 compounder episode-clusters fired vs the required minimum of
> 25. The DEFERRED verdict is driven SOLELY by this window-length
> constraint (too few compounders in 3.5 months), NOT by absent or
> survivorship-biased forward legs. You cannot run a reliable statistical test
> on 4 examples, regardless of how complete the price data is.
>
> **What this means for the program:**
> We cannot answer the core question from honest data yet — the honest cohort
> is too small because the fire window is only 3.5 months. The test can be
> run on survivorship-biased data (the full OOS 2020-2023 set), but that
> biases the result toward finding a false signal (companies acquired at a
> premium look like 'compounders' when they just got bought out). The null
> or positive result from biased data does not resolve the question.
>
> **What needs to happen next:**
> The dead-name spike (PR-G) expands the dead-name price store to cover the
> full 1,165-day gap period (2021-10-25→2025-01-02). Once that gap is filled,
> post-gap fires (2025+) will mature to full 252d, creating a larger honest
> cohort. The pre-registered deferral path in OBJECTIVE.md §8 is activated
> because the n-floor was not met — not because dead-name prices are absent.

## 11. Registry and Firewall

Results artifact: `data/research/missed_hold_study_results.parquet`
Registered in `config/synapse.yml` with:
- `horizon_role: hold_thesis`
- `tier: display`
- `scored_path_surfaces: []`
- `fdr_family: long_hold` (isolated from entry-desk FDR batches per LH-R5)

**Firewall:** this artifact MUST NOT feed entry-stack z-scores, board ordering, top-setups gates, alert triage, or push floor. Wrong-ruler firewall per OBJECTIVE.md §9.

---

**G1 ratification: PENDING FABLE RULING**

_This document prints the analysis results. It does not declare the program alive or dead. The G1 kill criterion requires Fable adjudication of the combined routing outcome above, including the survivorship-deferral path interpretation per OBJECTIVE.md §8._
