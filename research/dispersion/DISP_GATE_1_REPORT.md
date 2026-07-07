# DISP-GATE-1 Descriptive Report

**Experiment:** disp_gate_1  
**Design authority:** research/dispersion/L3_PREREG.md (frozen 2026-07-05)  
**Program:** CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md §6.2  
**Run date:** 2026-07-06  
**Status:** Descriptive-only. Frozen PASS thresholds (L3_PREREG) are NOT evaluated here — they are read only at a later verdict batch.  
**Cumulative pooled replay trial count:** 31 (SUM basis). TrialLedger max()-basis reports 15 — see §0.5.6 note below.

---

## In plain English

We asked: when the stock market is in a "low dispersion / high correlation" regime
(names move together, macro drives returns — what we call lean_out), do our signal
fires enter worse situations than when the market is in a "high dispersion" state
(lean_in, where individual selection pays)?

The short answer is: **yes, lean_out fires look worse by the stop-5 metric** — but
the lean_out cohort on the primary (expanding) basis has only 289 fires (122 episode
clusters). That is thin enough that we flag it as sparse and report without bootstrap
confidence intervals. The trailing-252d basis has 11,191 lean_out fires and tells a
more moderate story.

A key finding is the **non-stationarity of the two bases**: 34.8% of fire dates flip
regime assignment between the expanding-window and trailing-252d methods. This exceeds
the L3_PREREG 15% threshold. Per the prereg, the study proceeds descriptively on the
primary (expanding) basis only; no promotion gate is evaluated in this batch.

The SPY 21d contemporaneous drawdown covariate shows that all 289 lean_out (expanding)
fires occurred during "flat" market tape (SPY 21d return between -5% and +5%). There
are zero lean_out fires in the "down" or "up" terciles. This means the covariate
control cannot be applied — the lean_out effect cannot be separated from the "flat tape"
effect on the expanding basis. The confound L3_PREREG warned about is active.

---

## 1. Data reach and feasibility gate (§0.5.7 / §6.2)

| Item | Value |
|---|---|
| Panel source | massive_stock_day (20,476 tickers) |
| Panel date range | 2021-07-06 to 2026-07-02 |
| Panel bars | 1,254 trading days |
| Fire cohort (verdict_grade=True fires) | 49,939 total |
| **Fires excluded (DATA-REACH GATE: <252 prior bars)** | **200 fires (3 fire dates: 2022-06-30, 2022-07-01, 2022-07-05)** |
| Fires remaining after gate | 49,739 |
| Exclusion rate | 0.4% |

The gate excluded only 0.4% of fires. The thin-cohort DEFER outcome (per §6.2) was
considered — the 49,739 remaining fires are sufficient for a descriptive run. However,
the expanding lean_out cell is very sparse (see §3).

---

## 2. Basis comparison (L3_PREREG design obligation 1)

| Metric | Value |
|---|---|
| Fire dates with regime assigned | 1,002 |
| Fire dates where expanding ≠ trailing-252d state | 349 (34.8%) |
| L3_PREREG non-stationarity threshold | 15% |
| **NON-STATIONARITY FLAG** | **RAISED — 34.8% > 15%** |

Per L3_PREREG design obligation 1: when the bases disagree on >15% of fire dates,
the study proceeds descriptively on the primary (expanding) basis only. No promotion
gate is triggered until a stationary basis is evaluated.

The flip rate is high because the expanding window is non-stationary by design: an
identical absolute CSD level maps to different percentile values at different history
lengths. The trailing-252d window is more stationary by construction.

---

## 3. Per-cell results (primary metric: stop5 and dead_money at 21d)

**stop5** = fraction of fires with intra-period maximum adverse excursion ≥ 5% within 21d  
**dead_money** = fraction of fires with |21d return| < 2%  
**wr** = fraction of fires with positive 21d return

### Expanding-window basis (primary, PIT-correct)

| Cell | n fires | n clusters | stop5 | dead_money | WR | mean ret 21d |
|---|---|---|---|---|---|---|
| lean_in | 29,797 | 13,206 | **0.360** | 0.176 | 0.601 | +2.58% |
| neutral | 19,653 | 8,582 | 0.447 | 0.194 | 0.539 | +0.90% |
| lean_out | **289** | **122** | 0.550 | 0.215 | 0.502 | +0.49% |

Note: lean_out n=289 (122 clusters) is SPARSE relative to the production cohort.
L3_PREREG floor for bootstrap CIs is 25 episode clusters — met technically, but
the cohort is only 1% of the total production fire count. All 289 lean_out fires
fall in the "flat" SPY tercile (see §4).

Raw stop5 gap (lean_out vs lean_in): **+19.0pp**. This would nominally clear the
L3_PREREG frozen PASS threshold of ≥8pp — but the covariate control in §4 cannot
be applied (all lean_out fires in one tercile), so the gap is uncontrolled.

### Trailing-252d basis (sensitivity)

| Cell | n fires | n clusters | stop5 | dead_money | WR | mean ret 21d |
|---|---|---|---|---|---|---|
| lean_in | 25,147 | 11,086 | **0.346** | 0.172 | 0.624 | +3.12% |
| neutral | 13,401 | 5,821 | 0.454 | 0.194 | 0.507 | +0.33% |
| lean_out | 11,191 | 4,841 | 0.437 | 0.198 | 0.551 | +1.05% |

On the trailing-252d basis, lean_out fires (11,191) show stop5=0.437 vs lean_in
stop5=0.346 — a gap of +9.1pp. The lean_out cohort is much larger here (23% of
total), and the pattern is weaker. Trailing-252d lean_out still has lower WR
(0.551) vs lean_in (0.624) but is closer to lean_in than the expanding basis suggests.

Dead_money sign check (L3_PREREG criterion 5): lean_out > lean_in on both bases —
sign consistent.

---

## 4. SPY 21d contemporaneous drawdown covariate (L3_PREREG design obligation 2)

Covariate terciles: down (<-5%), flat (-5% to +5%), up (>+5%), measured at fire date.

### Expanding-window basis — covariate split

| Regime / Tercile | n | stop5 | dead_money | WR |
|---|---|---|---|---|
| **lean_in / down** | 1,589 | 0.335 | 0.115 | 0.726 |
| **lean_in / flat** | 21,794 | 0.363 | 0.179 | 0.588 |
| **lean_in / up** | 6,414 | 0.355 | 0.182 | 0.612 |
| neutral / down | 1,261 | 0.565 | 0.144 | 0.517 |
| neutral / flat | 17,188 | 0.435 | 0.198 | 0.546 |
| neutral / up | 1,204 | 0.492 | 0.190 | 0.459 |
| **lean_out / flat** | **289** | **0.550** | 0.215 | 0.502 |
| lean_out / down | 0 | — | — | — |
| lean_out / up | 0 | — | — | — |

**Critical finding:** All 289 lean_out (expanding) fires occur in the "flat" SPY
tercile. The covariate control required by L3_PREREG design obligation 2 cannot be
applied — there are zero lean_out fires in the "down" or "up" tercile. This means
the lean_out vs lean_in gap cannot be assessed within any drawdown tercile.

Within the "flat" tercile: lean_out stop5 = 0.550 vs lean_in stop5 = 0.363, gap = +18.7pp.
But this within-tercile comparison has no lean_in vs lean_out pairing in the other
two terciles, so the gap's independence from tape backdrop cannot be assessed.

**Conclusion on confound:** The L3_PREREG design obligation 2 test cannot be
completed on the expanding basis. The regime-as-outcome confound (lean_out coincides
with a specific tape environment) is unresolvable with this cohort.

### Trailing-252d basis — covariate split

| Regime / Tercile | n | stop5 | dead_money | WR |
|---|---|---|---|---|
| **lean_in / down** | 1,725 | 0.314 | 0.112 | 0.737 |
| **lean_in / flat** | 17,705 | 0.350 | 0.175 | 0.607 |
| **lean_in / up** | 5,717 | 0.341 | 0.180 | 0.642 |
| neutral / down | 1,005 | 0.621 | 0.148 | 0.492 |
| neutral / flat | 11,075 | 0.439 | 0.199 | 0.516 |
| neutral / up | 1,321 | 0.453 | 0.191 | 0.440 |
| lean_out / down | 120 | 0.658 | 0.183 | 0.333 |
| lean_out / flat | 10,491 | 0.428 | 0.199 | 0.562 |
| lean_out / up | 580 | 0.552 | 0.200 | 0.391 |

On the trailing-252d basis, lean_out fires appear in all three SPY terciles.
Within each tercile:
- **down**: lean_out stop5 (0.658) > lean_in stop5 (0.314), gap = +34.4pp
- **flat**: lean_out stop5 (0.428) > lean_in stop5 (0.350), gap = +7.8pp
- **up**: lean_out stop5 (0.552) > lean_in stop5 (0.341), gap = +21.1pp

The lean_out vs lean_in gap persists across all three SPY terciles on the trailing-252d
basis. The gap is absorbed by >50% in none of the terciles (the L3_PREREG "absorbed"
criterion requires the gap to narrow by >50%, which would mean it reflects tape
backdrop alone). The gap persists meaningfully in 3/3 terciles.

However: this is on the SENSITIVITY basis (trailing-252d), not the primary (expanding)
basis. Per the non-stationarity flag, no promotion gate is triggered on the sensitivity
basis alone.

---

## 5. Pooled trial count

- Pre-B2 cumulative pooled sum: 25 (exit_grid_v1 = 15, wait_grid_v1 = 10)
- DISP-GATE-1 declared budget: 6
- **Post-B2 cumulative pooled sum: 31**
- TrialLedger max()-basis reports: 15 (largest declared budget in `replay` family)
- Both numbers are printed per §0.5.6. The honest FDR-accounting SUM is 31.

---

## 6. Episode clustering

All CIs and cluster counts use the `episode_id` column from replay_boarded (not the
ticker×year fallback). Episode clusters are contiguous calendar-time groups of related
fires. The expanding lean_out cell has 122 episode clusters — above the L3_PREREG
minimum of 25, but sparse relative to the 13,206 clusters in the lean_in cell.

---

## 7. Summary of findings

| Finding | Status |
|---|---|
| Panel reaches ≥252 bars before earliest fires | YES (2021-07-06 → 2022-06) |
| Fires excluded by data reach gate | 200 (0.4%) |
| Non-stationarity flag (>15% basis flip rate) | RAISED (34.8%) |
| Expanding lean_out cohort sufficiency | SPARSE (289 fires / 122 clusters) |
| Raw stop5 gap (lean_out > lean_in, expanding) | +19.0pp (above 8pp threshold) |
| Covariate control feasible (expanding) | NO — all lean_out in "flat" tercile |
| Trailing-252d lean_out cohort sufficiency | YES (11,191 fires / 4,841 clusters) |
| Trailing-252d gap persists after covariate split | YES — 3/3 terciles |
| Dead_money sign consistent (lean_out > lean_in) | YES — both bases |
| Verdict evaluated this batch | NO — descriptive-only per §6.2 |
| gross_mult_live change | NONE — remains 1.0 (hard constraint) |
| Sizing recommendation | NONE — display/measurement only |

---

## 8. Conclusion and next steps

This descriptive run establishes the feasibility baseline for DISP-GATE-1.

The non-stationarity finding is the key result: the two bases disagree on 34.8% of
fire dates, indicating the expanding-window percentile is not a stable signal over
the 2022-2025 period. This must be resolved (e.g. by choosing a fixed-denominator
basis or by waiting for a longer history on the trailing-252d basis) before a verdict
batch is registered.

The expanding lean_out cohort (289 fires) is concentrated entirely in "flat" SPY tape
environments. The confound test required by L3_PREREG cannot be completed on this
basis. The trailing-252d basis produces a more complete picture (lean_out fires across
all three SPY terciles, gap persists in all three).

Come-back for verdict evaluation: after non-stationarity is resolved AND after the
trailing-252d lean_out cohort has enough OOS fires (the current run is fully in-sample
relative to the L3_PREREG registration date of 2026-07-05; all fires pre-date the
registration).

No action recommended this batch. This report is the descriptive surface that a future
verdict batch must cite as `derived_from_surface: disp_gate_1`.

---

## 9. Addendum (2026-07-06, PR-F3.2b hardening): independent replication + caveats

A second, independently-built DISP-GATE-1 harness (superseded PR #1705, Final-3 program
lane — closed to avoid double-registering the 6 cells) ran the same frozen prereg design
on a DIFFERENT panel (the survivor-backfilled deep-closes store, history to 1962, vs this
report's massive_stock_day panel). It reproduced the headline conclusion independently:

| Metric | This report (massive panel) | Replication (deep-closes panel) |
|---|---|---|
| Basis flip rate | 34.8% | 31.4% |
| lean_out − lean_in stop5 gap (expanding) | positive | +13.5pp |
| lean_out − lean_in stop5 gap (trailing-252) | positive | +6.1pp |
| Overall outcome | DEFER (non-stationarity) | DEFER (non-stationarity) |

The DEFER conclusion is therefore robust to panel construction: on both panels the
lean_out>lean_in stop5 gap has a stable SIGN on both bases, but the regime assignments
themselves are basis-unstable well beyond the frozen 15% flag. Note the two harnesses
disagreed materially on cohort composition per state (e.g. expanding lean_out n=289 here
vs a much larger lean_out cohort on the deep panel) — further evidence that the expanding
percentile is panel- and inception-sensitive, which is the non-stationarity finding itself.

**Panel survivorship caveat (applies to this report's panel too).** The massive_stock_day
panel carries the massive-era delisted-name recall floor (dead-name price coverage
≈38.3% per `data/edgar/_dead_name_coverage.json`), so the CSD percentile denominator is
partially survivor-tilted; the replication panel was fully survivor-backfilled (zero
inactive tickers) and showed the same DEFER. Neither panel is a delisted-complete
universe. Any future verdict batch should state its panel's dead-name coverage explicitly.

**Episode-clustering sensitivity.** This report clusters on the `episode_id` column
(granular; thousands of clusters). The frozen prereg's Standing Notes describe clustering
as "contiguous blocks within ±30d" — under a strict tape-time block reading, the
2022–2025 fire tape collapses to ~41 global clusters and the per-arm counts fall BELOW
the 25-cluster floor (replication measured expanding lean_in=17, lean_out=20 blocks).
Consequence: bootstrap CIs computed on granular episode_id clustering are NARROWER than
the prereg's block reading would produce, and under the strict reading no arm currently
clears the CI floor at all. A future verdict batch must resolve this clustering-definition
ambiguity in its registration BEFORE computing CIs, and disclose both counts.

*This addendum changes no numbers in §1–§8 and evaluates no gate. Display-only.*
