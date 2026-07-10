# EI-PM0 Price-Memory Bundle — Results

**Study:** EI-PM0 Price-Memory Bundle phase-0
**Pre-registration:** `research/entry_intel/PM0_PRICE_MEMORY_BUNDLE_PREREG.md` (APPROVED 2026-07-06 r3)
**Primary machinery amendment:** `research/entry_intel/PM0_R4_PRIMARY_AMENDMENT.md` (r4, registered 2026-07-10)
**Era stamp:** Effective verdict window **2022-06-30 → 2026-07-02** (P0_MEASUREMENT_MEMO.md v1.1)
**Bundle verdict:** BUNDLE_OPEN (1 survivor(s))

> **DannyTrades provenance box:** The anchor's own pullback/DCA-adjacent evidence FAILED its gate
> (DT-R7: CI includes 0, payoff ≈ 0, tail worse). This study tests the price-memory features
> derived from DT principles — not DT's own system. Printed as the honest prior, labeled:
> **HYPOTHESIS SOURCE — NOT EVIDENCE.**

> **Plain-English box:** This study asks whether a stock 'remembers' where volume traded
> before a setup fires. Five features were tested: distance above the anchored VWAP (PM1),
> volume shelf density at entry (PM2), absence of overhead gaps (PM3), fraction of recent
> volume traded above current price (PM4), and float turnover (PM5, pre-blocked).
> The test is made month-by-month to remove calendar composition effects (DT-R14).
> A survivor earns display-only context status and a separate promotion prereg only.
> Nothing here may ever instruct a price level for action.

---

## §1 — Preamble

- **Primary machinery (r4):** within-month episode-label permutation
  (`research/entry_intel/PM0_R4_PRIMARY_AMENDMENT.md`, registered 2026-07-10 before any real trial p-value).
  The r3 month-block bootstrap was demoted to a labeled CI diagnostic after failing §7 calibration twice:
  run 1 (row-month grouping, pre-EX-8) PM2 KS-p 0.0333; run 2 (EX-8 episode-month fix) PM2 KS-p 0.0412.
  Both failed runs are preserved in `calibration_run1_FAILED.log` and the run-2 log.
  The month-block bootstrap CI is printed per trial below as a DIAGNOSTIC only; it NEVER feeds BH or verdicts.
- Replay MD5: `906175f9eb8caa351ed6d7d5c56265d3`
- Features MD5: `0f19938c3393f909c8795bbed7f64bf1`
- Statements MD5: `92b37713811a2e618b4595f3167e116b`
- VG fires: 49,939
- Episode clusters: 22,295
- Survivor-stamped: 0
- Signal date range: 2022-06-30 → 2025-12-29
- m declared: 20  m active: 20
- Excluded trials: []

**Medians (vg fires, outcome-blind, computed by builder before any outcome join):**
- pm2 median: 0.16057472505964107  (n=49239)
- pm4 median: 0.5507388878262659  (n=49239)
- pm5 median: 0.49462000384089194  (n=27623) [data_blocked, for reference]

**QA outcomes:**
- Gate 1 (PIT audit): True
- Gate 5 (Determinism): True
- Overall: True

**Column map / enums / censoring:**
- Frozen prereg §1 column list resolved 1:1 against the replay (no aliases needed); state enums verified {STOPPED, DEAD_MONEY, CUSHIONED, CLEAN_LIFTOFF} on both grids:
- Grid A counts: {'STOPPED': 19105, 'CLEAN_LIFTOFF': 15498, 'DEAD_MONEY': 8891, 'CUSHIONED': 6445}
- Grid B counts: {'STOPPED': 31372, 'CLEAN_LIFTOFF': 16549, 'CUSHIONED': 1975, 'DEAD_MONEY': 43}
- horizon_censored rows in the vg-fire population: 0 (per-grid exclusion counts therefore 0 on both grids; guard retained for regeneration)

**Floors (checked pre-p-value):**
- Event floor (≥50 events/trial, ≥10 per group) and month floor (≥24 qualifying months): NO decrement — m stayed 20 → 20; excluded trials: none

**Coverage table (defined fraction per feature):**
- vg_fires: pm1 49,239/49,939 (98.6%), pm2 49,239/49,939 (98.6%), pm3 49,239/49,939 (98.6%), pm4 49,239/49,939 (98.6%), pm5 27,623/49,939 (55.3%), poc_dist_126 49,239/49,939 (98.6%)
- all_fires: pm1 56,678/57,640 (98.3%), pm2 56,678/57,640 (98.3%), pm3 56,678/57,640 (98.3%), pm4 56,678/57,640 (98.3%), pm5 31,941/57,640 (55.4%), poc_dist_126 56,678/57,640 (98.3%)
- vg_near_miss: pm1 14,841/15,053 (98.6%), pm2 14,841/15,053 (98.6%), pm3 14,841/15,053 (98.6%), pm4 14,841/15,053 (98.6%), pm5 8,253/15,053 (54.8%), poc_dist_126 14,841/15,053 (98.6%)
- PM5 vg-fire coverage 55.3% vs 60% floor → data_blocked (pre-declared, coverage < 60%)

**Month census (pre-outcome-join; per-month group sizes recorded in preamble.json):**
- pm1: 43 qualifying months of 43
- pm2: 43 qualifying months of 43
- pm3: 43 qualifying months of 43
- pm4: 43 qualifying months of 43
- Episode ISO-week month-straddle count (episodes whose rows span months; assigned to first-row month per EX-8): 854

**QA gates 2–4 (from qa_report.json):**
- Gate 2 split-fence census: {'gate': 'fence_census', 'per_feature': {'pm1': {'ok': 71519, 'split_suspect': 1174}, 'pm2': {'ok': 71519, 'split_suspect': 1174}, 'pm3': {'ok': 71519, 'split_suspect': 1174}, 'pm4': {'ok': 71519, 'split_suspect': 1174}, 'poc_dist_126': {'ok': 71519, 'split_suspect': 1174}}, 'n_gaps_ignored_total': 515, 'so_split_suspect': 0, 'so_prehistory': 0, 'so_corrupt': 0, 'so_stale': 7721, 'so_missing': 23604, 'pass': True}
- Gate 4 anchor sanity: {'gate': 'anchor_sanity', 'n_defined': 49239, 'n_degenerate_anchor': 75, 'distribution': {'min': 0.0, 'p25': 20.0, 'median': 127.0, 'p75': 212.0, 'max': 249.0}, 'pass': True}
- Gate 3 coverage: rendered above
- Mixed-label episode fractions (negative-control instruments): {'PM1': 0.0636, 'PM2': 0.0846, 'PM3': 0.0762, 'PM4': 0.044}

---

## §2 — Per-Trial Table

**Pre-registered favorable directions:** Δ̂ < 0 favorable for STOPPED and DEAD_MONEY; Δ̂ > 0 favorable for CUSHIONED (Δ̂ = favorable-group incidence − unfavorable-group incidence, pp). A significant p in the UNFAVORABLE direction is mechanism-contradicting evidence, never a survival credit.

| Trial | Feature | Grid | State | Δ̂ (pp) | dir | perm_p (r4 PRIMARY) | BH_adj_p | boot CI DIAGNOSTIC [2.5%,97.5%] | pooled_Δ | pooled−within div | ep_perm_p (NOT TIME-CONTROLLED) | MWU_r (NOT TIME-CONTROLLED) | qual_months | n_fav | n_unfav | ep_fav | ep_unfav | THIN | sign_stable |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | pm1 | state_8_21 | STOPPED | -0.439 | fav | 0.5975 | 0.7469 | [-2.926, 1.798] | -1.505 | -1.066 | 0.0155 | 0.0152 | 43 | 39542 | 9697 | 18491 | 4876 | False | False |
| T02 | pm1 | state_8_21 | DEAD_MONEY | 1.369 | UNFAV | 0.0372 | 0.0744 | [-0.131, 2.804] | 1.845 | 0.477 | 0.0965 | 0.0152 | 43 | 39542 | 9697 | 18491 | 4876 | False | True |
| T03 | pm1 | state_8_21 | CUSHIONED | 0.142 | fav | 0.7912 | 0.8792 | [-1.082, 1.438] | 0.388 | 0.246 | 0.2399 | 0.0152 | 43 | 39542 | 9697 | 18491 | 4876 | False | True |
| T04 | pm1 | state_15_126 | STOPPED | -0.098 | fav | 0.9074 | 0.9074 | [-2.031, 1.813] | 0.263 | 0.361 | 0.5992 | -0.0085 | 43 | 39542 | 9697 | 18491 | 4876 | False | False |
| T05 | pm1 | state_15_126 | CUSHIONED | 0.458 | fav | 0.1886 | 0.2694 | [-0.317, 1.190] | 0.578 | 0.119 | 0.1584 | -0.0085 | 43 | 39542 | 9697 | 18491 | 4876 | False | True |
| T06 | pm2 | state_8_21 | STOPPED | -5.762 | fav | 0.0002 | 0.0005 | [-7.956, -3.435] | -4.059 | 1.703 | 0.0005 | 0.0647 | 43 | 24620 | 24619 | 11949 | 11879 | False | True |
| T07 | pm2 | state_8_21 | DEAD_MONEY | 7.031 | UNFAV | 0.0002 | 0.0005 | [5.369, 8.843] | 8.919 | 1.888 | 0.0005 | 0.0647 | 43 | 24620 | 24619 | 11949 | 11879 | False | True |
| T08 | pm2 | state_8_21 | CUSHIONED | 4.090 | fav | 0.0002 | 0.0005 | [2.795, 5.296] | 4.305 | 0.215 | 0.0005 | 0.0647 | 43 | 24620 | 24619 | 11949 | 11879 | False | True |
| T09 | pm2 | state_15_126 | STOPPED | -0.917 | fav | 0.1490 | 0.2292 | [-3.131, 1.288] | 1.756 | 2.674 | 0.0420 | 0.0387 | 43 | 24620 | 24619 | 11949 | 11879 | False | True |
| T10 | pm2 | state_15_126 | CUSHIONED | 2.947 | fav | 0.0002 | 0.0005 | [2.140, 3.786] | 2.859 | -0.088 | 0.0005 | 0.0387 | 43 | 24620 | 24619 | 11949 | 11879 | False | True |
| T11 | pm3 | state_8_21 | STOPPED | 1.330 | UNFAV | 0.0436 | 0.0793 | [-0.889, 3.466] | 3.651 | 2.321 | 0.0005 | 0.0801 | 43 | 31721 | 17518 | 15213 | 8431 | False | True |
| T12 | pm3 | state_8_21 | DEAD_MONEY | 0.809 | UNFAV | 0.1294 | 0.2156 | [-0.447, 2.015] | 2.419 | 1.610 | 0.0005 | 0.0801 | 43 | 31721 | 17518 | 15213 | 8431 | False | True |
| T13 | pm3 | state_8_21 | CUSHIONED | 0.055 | fav | 0.8980 | 0.9074 | [-0.764, 0.966] | 0.317 | 0.263 | 0.4943 | 0.0801 | 43 | 31721 | 17518 | 15213 | 8431 | False | False |
| T14 | pm3 | state_15_126 | STOPPED | 2.207 | UNFAV | 0.0014 | 0.0031 | [0.397, 3.816] | 4.434 | 2.227 | 0.0005 | 0.0183 | 43 | 31721 | 17518 | 15213 | 8431 | False | True |
| T15 | pm3 | state_15_126 | CUSHIONED | 0.348 | fav | 0.2214 | 0.2951 | [-0.234, 0.965] | 0.481 | 0.133 | 0.1909 | 0.0183 | 43 | 31721 | 17518 | 15213 | 8431 | False | True |
| T16 | pm4 | state_8_21 | STOPPED | -3.433 | fav | 0.0002 | 0.0005 | [-6.062, -0.769] | -1.289 | 2.144 | 0.0275 | 0.0811 | 43 | 24620 | 24619 | 12092 | 10843 | False | True |
| T17 | pm4 | state_8_21 | DEAD_MONEY | 5.306 | UNFAV | 0.0002 | 0.0005 | [3.900, 6.761] | 7.587 | 2.281 | 0.0005 | 0.0811 | 43 | 24620 | 24619 | 12092 | 10843 | False | True |
| T18 | pm4 | state_8_21 | CUSHIONED | 2.553 | fav | 0.0002 | 0.0005 | [1.310, 3.770] | 2.989 | 0.436 | 0.0005 | 0.0811 | 43 | 24620 | 24619 | 12092 | 10843 | False | True |
| T19 | pm4 | state_15_126 | STOPPED | 0.273 | UNFAV | 0.6777 | 0.7973 | [-2.626, 3.255] | 3.860 | 3.587 | 0.0005 | 0.0134 | 43 | 24620 | 24619 | 12092 | 10843 | False | False |
| T20 | pm4 | state_15_126 | CUSHIONED | 1.239 | fav | 0.0002 | 0.0005 | [0.399, 1.930] | 1.088 | -0.151 | 0.0005 | 0.0134 | 43 | 24620 | 24619 | 12092 | 10843 | False | True |

**Note:** ep_perm_p and MWU_r are episode-level diagnostics, NOT TIME-CONTROLLED. They do not feed into verdicts (DT-R14). perm_p (r4 PRIMARY) is the registered primary statistic (within-month episode-label permutation, PM0_R4_PRIMARY_AMENDMENT.md). Boot CI DIAGNOSTIC = MONTH-BLOCK BOOTSTRAP — DIAGNOSTIC (anticonservative-in-tail at m=43 per §7 record); shown for effect-size context only, NEVER feeds BH or verdicts.

**Significant-but-UNFAVORABLE trials (mechanism-contradicting texture, no survival credit): T02 (pm1 state_8_21 DEAD_MONEY, Δ̂ +1.37pp, BH 0.0744); T07 (pm2 state_8_21 DEAD_MONEY, Δ̂ +7.03pp, BH 0.0005); T11 (pm3 state_8_21 STOPPED, Δ̂ +1.33pp, BH 0.0793); T14 (pm3 state_15_126 STOPPED, Δ̂ +2.21pp, BH 0.0031); T17 (pm4 state_8_21 DEAD_MONEY, Δ̂ +5.31pp, BH 0.0005).** Notably these include the favorable-shelf DEAD_MONEY excess (thick shelves stop out less and cushion more, but go dead-money more) and the gap-map direction reversal (clean-sky fires stop out MORE than gap-overhead fires).

---

## §3 — Redundancy Matrix

**Correlation |ρ| ≥ 0.80 vs reference set ⇒ REDUNDANT (promotion blocked regardless of p)**

| Feature | ext_z | ext_atr | dist_to_52wh | near_52wh | rs_63d_return | align_quality | washout_proximity | poc_dist_126 |
|---|---|---|---|---|---|---|---|---|
| pm1 | 0.5667 | 0.6881 | 0.4963 | 0.4963 | 0.6185 | -0.3118 | -0.4313 | 0.719 |
| pm2 | 0.0475 | 0.1233 | 0.2516 | 0.2516 | 0.1142 | 0.0504 | -0.3245 | 0.1185 |
| pm3 | -0.1982 | -0.2814 | -0.263 | -0.263 | -0.2194 | 0.0675 | 0.2085 | -0.255 |
| pm4 | -0.6369 | -0.9527 | -0.8745 | -0.8745 | -0.7499 | 0.2828 | 0.781 | -0.8842 |
| pm5 | -0.1152 | -0.233 | -0.4157 | -0.4157 | -0.1767 | 0.009 | 0.3177 | -0.2025 |

**Within-bundle correlations:**
- pm1_vs_pm2: ρ=-0.3139
- pm1_vs_pm3: ρ=-0.2396
- pm1_vs_pm4: ρ=-0.6462
- pm1_vs_pm5: ρ=-0.0075
- pm2_vs_pm3: ρ=0.0805
- pm2_vs_pm4: ρ=-0.1471
- pm2_vs_pm5: ρ=-0.292
- pm3_vs_pm4: ρ=0.2898
- pm3_vs_pm5: ρ=0.002
- pm4_vs_pm5: ρ=0.2371

**Redundant features:**
- pm4: REDUNDANT with ['ext_atr', 'dist_to_52wh', 'near_52wh', 'poc_dist_126']

---

## §4 — Verdicts Per Sub-Component

### PM1: **NO-GO**
- Detail: no BH-significant favorable sign-stable trial

### PM2: **SURVIVES**
- Detail: surviving_trials:['T06', 'T08', 'T10']
- Surviving trials: ['T06', 'T08', 'T10']
- Ceiling: display-only context chip only (DT-R7); separate promotion PREREG required

### PM3: **NO-GO**
- Detail: no BH-significant favorable sign-stable trial

### PM4: **REDUNDANT**
- Detail: redundant_with:['ext_atr', 'dist_to_52wh', 'near_52wh', 'poc_dist_126']

### PM5: **data_blocked**
- Detail: pre-declared; coverage < 60% floor (see prereg §2/PM5)
- **FLOAT-PROXY** label applies to all pm5 outputs (shares outstanding, not free float)
- **PARTIAL-COVERAGE**: 50.2% of vg fires have a valid pm5 value (< 60% floor)
- Unblock condition: EDGAR panel covers ≥ 60% of 992-ticker fire universe

---

## §5 — Bundle Verdict

**BUNDLE_OPEN (1 survivor(s))**

Registry rows (DRAFT — applied to registry by Fable in same PR):
- `EI-PM1-AVWAP` (pm1): falsified (phase-0)
- `EI-PM2-SHELF` (pm2): phase0_passed (display-only ceiling, DT-R7)
- `EI-PM3-GAP` (pm3): falsified (phase-0)
- `EI-PM4-OVERHEAD` (pm4): redundant — redundant_with:['ext_atr', 'dist_to_52wh', 'near_52wh', 'poc_dist_126']
- `EI-PM5-FLOATTURN` (pm5): data_blocked — unblock: EDGAR coverage >= 60% of vg fire universe

Signal Commons resolution: Signal Commons §4 parked row: PM0 price-memory bundle dispatched -> BUNDLE_OPEN (1 survivor(s)). PM5 data_blocked (unblock condition printed in RESULTS.md).
DT-R7 clock: DT-R7 routing come-back 2026-07-20 CLOSED by this run. Display-only ceiling (DT-R7) and forbidden-key law (DT-R2/DT-R7) remain permanent on this family and all descendants.

---

## §6 — Context Appendix (§8 items)

*(NOT verdict-feeding, NOT BH'd)*

**Grid-B DEAD_MONEY:** Grid-B DEAD_MONEY: 43 events (substrate limitation, 43 expected; no test registered)

**CLEAN_LIFTOFF rates by favorable/unfavorable group (context, not tested):**
- pm1: grid_A_fav_cl_pct=30.694  grid_A_unfav_cl_pct=31.422  grid_B_fav_cl_pct=32.833  grid_B_unfav_cl_pct=33.681
- pm2: grid_A_fav_cl_pct=26.255  grid_A_unfav_cl_pct=35.42  grid_B_fav_cl_pct=30.621  grid_B_unfav_cl_pct=35.379
- pm3: grid_A_fav_cl_pct=28.565  grid_A_unfav_cl_pct=34.953  grid_B_fav_cl_pct=31.229  grid_B_unfav_cl_pct=36.208
- pm4: grid_A_fav_cl_pct=26.194  grid_A_unfav_cl_pct=35.481  grid_B_fav_cl_pct=30.524  grid_B_unfav_cl_pct=35.477

**Median MAE/MFE (fwd_mdd_21 / fwd_mfe_21) by group — risk texture:**
- pm1 fav: median_mdd_21=-0.0357 median_mfe_21=0.0517 (n=39542)
- pm1 unfav: median_mdd_21=-0.0366 median_mfe_21=0.0528 (n=9697)
- pm2 fav: median_mdd_21=-0.0336 median_mfe_21=0.0451 (n=24620)
- pm2 unfav: median_mdd_21=-0.0384 median_mfe_21=0.0605 (n=24619)
- pm3 fav: median_mdd_21=-0.0376 median_mfe_21=0.0489 (n=31721)
- pm3 unfav: median_mdd_21=-0.0325 median_mfe_21=0.0581 (n=17518)
- pm4 fav: median_mdd_21=-0.0356 median_mfe_21=0.0459 (n=24620)
- pm4 unfav: median_mdd_21=-0.0361 median_mfe_21=0.0596 (n=24619)

**Feature distributions (deciles, vg fires; pm3 = binary incidence; pm5 = FLOAT-PROXY/PARTIAL-COVERAGE):**
- pm1 (n=49239): q00=-0.4258 q10=-0.0301 q20=0.0007 q30=0.0169 q40=0.0299 q50=0.0433 q60=0.0599 q70=0.0805 q80=0.1114 q90=0.1653 q100=1.4994
- pm2 (n=49239): q00=0.0 q10=0.0418 q20=0.0706 q30=0.0995 q40=0.1285 q50=0.1606 q60=0.1963 q70=0.2365 q80=0.285 q90=0.3598 q100=1.0
- pm4 (n=49239): q00=0.0 q10=0.019 q20=0.1074 q30=0.2461 q40=0.4037 q50=0.5507 q60=0.6774 q70=0.7923 q80=0.8849 q90=0.9346 q100=1.0
- pm5 (n=27623) [FLOAT-PROXY/PARTIAL-COVERAGE]: q00=0.0054 q10=0.2834 q20=0.3422 q30=0.3889 q40=0.4355 q50=0.4946 q60=0.5657 q70=0.6602 q80=0.8036 q90=1.084 q100=9.5445
- poc_dist_126 (n=49239): q00=-0.5407 q10=-0.1321 q20=-0.086 q30=-0.0557 q40=-0.0288 q50=-0.0028 q60=0.0232 q70=0.0489 q80=0.0781 q90=0.1227 q100=1.2004
- pm3: pct(pm3==1)=35.58% (n=49239)

**Sector composition of favorable vs unfavorable groups (top sectors, % of group):**
- pm1 fav: Industrials 17.42%, Financials 15.08%, Information Technology 13.47%
- pm1 unfav: Industrials 16.59%, Financials 13.12%, Consumer Discretionary 11.88%
- pm2 fav: Industrials 17.64%, Financials 15.57%, Information Technology 10.3%
- pm2 unfav: Industrials 16.86%, Information Technology 16.05%, Financials 13.77%
- pm3 fav: Industrials 17.49%, Financials 14.68%, Information Technology 12.59%
- pm3 unfav: Industrials 16.83%, Financials 14.72%, Information Technology 14.03%
- pm4 fav: Industrials 19.22%, Financials 16.86%, Information Technology 13.6%
- pm4 unfav: Industrials 15.16%, Information Technology 12.56%, Financials 12.37%

**Survivor-stamped appendix (SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE):** 0 rows in the verdict-grade fire population carry the stamp — appendix empty.

**Near-miss context read (descriptive only, no test; pm5 = FLOAT-PROXY/PARTIAL-COVERAGE):**
- pm1: n_defined=14841 mean=0.1053 median=0.0779
- pm2: n_defined=14841 mean=0.1809 median=0.1544
- pm3: n_defined=14841 mean=0.2588 median=0.0
- pm4: n_defined=14841 mean=0.3314 median=0.2381
- pm5: n_defined=8253 mean=0.6124 median=0.47 [FLOAT-PROXY/PARTIAL-COVERAGE]

---

## §7 — Leak-Audit Section

- **Signal-close vs next-close:** PM features use signal-bar adjusted close (pre-entry, PIT-safe); fill law uses next close. No lookahead.
- **PIT spot-audit:** True (gate 1 of §4.4)
- **Determinism:** True (gate 5 of §4.4)
- **Split-fence census:** see qa_report.json gate2_fence_census
- **Era boundary:** signal dates 2022-06-30 → 2025-12-29 (verdict window 2022-06-30 → 2026-07-02)
- **PM5 SO staleness:** see qa_report.json for so_stale / so_missing counts
- **EX-2 disclosure:** gaps whose pre-gap bar falls before the 250-bar window are not scanned
- **r4 calibration scope (Opus A1):** the §7 negative control permutes labels within month and therefore CANNOT certify calibration against an episode-size↔label↔outcome confound (the permutation erases the size↔label pairing it would need to detect). A passing control validates the machinery under within-month label exchangeability only; the size-exchangeability assumption is disclosed in PM0_R4_PRIMARY_AMENDMENT.md §2 and mitigated (harmonic weights, blocking, floors, direction requirement, bootstrap CI printed beside every verdict-feeding p).

---

## §8 — Registry + Ledger Rows (DRAFT)

*(Applied to registry/masterplan docs by Fable in same PR)*

**EI masterplan §9:** EI-PM0 Price-Memory Bundle phase-0 complete. Bundle verdict: BUNDLE_OPEN (1 survivor(s)). See RESULTS.md for full trial table and component verdicts.
**Signal Commons:** Signal Commons §4 parked row: PM0 price-memory bundle dispatched -> BUNDLE_OPEN (1 survivor(s)). PM5 data_blocked (unblock condition printed in RESULTS.md).
**DT-R7:** DT-R7 routing come-back 2026-07-20 CLOSED by this run. Display-only ceiling (DT-R7) and forbidden-key law (DT-R2/DT-R7) remain permanent on this family and all descendants.

---

## §9 — Plain-English Box

The price-memory bundle asked whether the chart's history of volume predicts outcome for
production fires, using five measures: anchored VWAP distance (where does price sit relative
to the post-low buyer base?), shelf density (is there prior ownership at this level?), gap-fill
map (is there an unfilled seller cohort overhead?), overhead supply (how much prior volume traded
above current price?), and float turnover (has the register churned to fresh holders?).

Tests are made month-by-month to prevent calendar composition from masquerading as signal
(DT-R14 law, applied because bear markets load all stocks with overhead supply simultaneously).
Float turnover (PM5) could not be tested: the EDGAR panel covers only 50% of our fire universe,
below the registered 60% floor. It is pre-blocked with a printed unblock condition.

Survivors — if any — earn display-only context status and eligibility for a separate promotion
study. Nothing here may ever specify a price level as an instruction to act (DT-R2/DT-R7).
No promotion-tier language is used anywhere in this document.

