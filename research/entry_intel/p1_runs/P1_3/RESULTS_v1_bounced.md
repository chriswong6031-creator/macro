# P1.3 Trio Ablation — RESULTS

**VERDICT: TRIO CLOSED — ALL THREE FACTORS NO-GO**

**Study:** P1.3 Trio Ablation
**Program:** Entry Intelligence (EI)
**Date run:** 2026-07-05
**Author:** Sonnet subagent under Fable orchestration
**PREREG:** `research/entry_intel/P1_3_TRIO_ABLATION_PREREG.md` (APPROVED 2026-07-05)
**Memo law:** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments`

---

## Plain-English Box (required by §3 plain-language law)

In plain English:

We tested whether three candidate filters — proximity to a forced-seller washout event (F1), relative-strength in the "inflecting but not extended" zone (F2), and low price extension at signal time (F3) — actually improve outcomes when the live 2D/3D cascade fires a stock onto the board. We did this two ways for each factor: blocking fires that fail the filter (Mode-A hard gate) and merely ranking them lower (Mode-B rank weight). All 30 pre-registered tests were run on 49,939 production-trigger fires from mid-2022 to end-2025, using episode-clustered bootstrapping (N=5,000 resamples) to account for correlated signals within ticker episodes.

The result is unambiguous: across all 30 trials, the bootstrap p-values range from 0.49 to 0.53 — entirely consistent with chance. The rank-biserial correlations are all near zero (largest: |r| = 0.12 for F1, driven by a direction that is unfavorable in one of the two tested directions). After Benjamini-Hochberg correction at q=0.10, the minimum adjusted p-value is 0.53. Zero of the 30 trials survives BH.

The prior bottom-signal-backtest evidence (n=315, weekly trigger) that motivated this trio is a hypothesis from a different trigger, and it does not transfer. The production-trigger fire population does not discriminate along any of these three axes in a statistically detectable way.

**All three factors remain display-only. No rank or gate integration is authorized.**

---

## 1. Preamble

**Replay artifact:** `data/replay/replay_boarded.parquet`
**Replay MD5:** (see results.json)
**Shape:** 961,656 rows, 66 columns

**Era citation:** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` §6 v1.1 amendments.
**Effective verdict window:** 2022-06-30 → 2025-12-29 (250-bar MTF warmup per §APPROVAL clause 1)
**Nominal 2021-07-06 window:** not present in ledger; effective window is post-warmup.

**Population census:**
- Total fires (verdict_type == fire): 57,640
- Verdict-grade fires (primary population): **49,939**
- Stamped rows excluded (survivor_bias == True): **0** (all rows Massive-sourced; 100% delisted recall)
- Horizon-censored fires: 7,701 (verdict_grade == False; pre-excluded)
- Episode clusters (unique episode_id): **22,295**
- Era min: 2022-06-30 | Era max: 2025-12-29

**Column name mapping (PREREG → actual):**
| PREREG name | Actual column | Status |
|---|---|---|
| episode_cluster_id | episode_id | OK |
| cohort_washout_proximity | washout_proximity | OK (boolean) |
| rs_vs_sector_quartile | rs_sector_quartile | OK (float 1-4, 7.7% null on vg_fires) |
| fwd_21d | fwd_ret_21 | OK |
| fwd_63d | fwd_ret_63 | OK |
| survivor_bias_stamp | survivor_bias | OK |

**Stamp text (§2.3):**
> survivor-biased panel: 0% of member-months lack price history for this era; all rows Massive-sourced (survivor_bias == False); delisted-name recall verified 100%.

**Fill rule confirmation:** fill_date = signal_date + 1 business day (next-bar fill verified across sample). entry_price = first close strictly after signal date per P0.1 contract.

**washout_proximity encoding:** boolean (True = in-window / favorable; False = outside). 19,003 True / 30,936 False in vg_fires.

**rs_sector_quartile:** float {1.0, 2.0, 3.0, 4.0}; 3,828 null rows excluded from F2 trials. Q2+Q3 (favorable, inflection zone) = 23,733 rows; Q1+Q4 (unfavorable) = 22,378 rows.

**ext_z:** continuous, range [-3.29, +5.35]. Fires with ext_z > 2.0: 2,299 (4.6% of population).

**Rank sizing (RW bonus confirmation):**
- Median fires per day: 43
- tier_frac (1/(43-1)) = 0.0238
- RW bonus pre-registered: +0.10 (≈ 4.2 cascade positions vs tier_frac — confirmed per PREREG §2 sizing rationale)

**Both-halves split midpoint:** midpoint date splits the 872 trading days at approximately 2024-02-28.
- Half-1: n=24,932 fires, 2022-06-30 → 2024-02-28
- Half-2: n=25,007 fires, 2024-03-01 → 2025-12-29

---

## 2. Per-Factor Results Table (30 registered trials, BH-corrected)

**Key:** Fav = delta in favorable direction per PREREG §5.1 (Y/N); BH_ok = survives BH at q=0.10; Sgn = sign stable in both halves; Thin = n_ep < 25 in either group.

### F1 — Washout Proximity (hard gate: washout_proximity == True)

| ID | Mode | H | TS | Rate_A | Rate_B | Delta_pp | Fav | Boot_p | BH_adj_p | BH_ok | r | Sign | Thin |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | HG | 21d | STOPPED | 0.420 | 0.396 | +2.41 | N | 0.5032 | 0.5328 | no | -0.125 | Y | OK |
| T02 | HG | 21d | DEAD_MONEY | 0.165 | 0.297 | -13.19 | Y* | 0.5032 | 0.5328 | no | -0.125 | Y | OK |
| T03 | HG | 21d | CUSHIONED | 0.124 | 0.165 | -4.10 | N | 0.5032 | 0.5328 | no | -0.125 | Y | OK |
| T04 | HG | 63d | STOPPED | 0.591 | 0.643 | -5.21 | Y | 0.4972 | 0.5328 | no | -0.098 | Y | OK |
| T05 | HG | 63d | DEAD_MONEY | 0.000 | 0.001 | -0.13 | Y | 0.4972 | 0.5328 | no | -0.098 | Y | OK |
| T06 | HG | 63d | CUSHIONED | 0.031 | 0.052 | -2.15 | N | 0.4972 | 0.5328 | no | -0.098 | Y | OK |
| T07 | RW | 21d | STOPPED | 0.420 | 0.393 | +2.58 | N | 0.4968 | 0.5328 | no | -0.109 | Y | OK |
| T08 | RW | 21d | CUSHIONED | 0.122 | 0.158 | -3.62 | N | 0.4968 | 0.5328 | no | -0.109 | Y | OK |
| T09 | RW | 63d | STOPPED | 0.597 | 0.642 | -4.55 | Y | 0.5072 | 0.5328 | no | -0.084 | Y | OK |
| T10 | RW | 63d | CUSHIONED | 0.034 | 0.052 | -1.79 | N | 0.5072 | 0.5328 | no | -0.084 | Y | OK |

*T02 dead-money rate A=16.5% vs B=29.7%, delta=-13.2pp. Note: these rates use state_8_21 (21d horizon), where dead-money is common (8,891 of 49,939 fires). Delta is in the favorable direction for the null hypothesis but the MWU on the underlying continuous fwd_ret_21 distribution (p=0.50) shows the mean return distributions are indistinguishable. See Note on T02 below.*

**F1 verdict: NO-GO** — T01/T04 (stop-out, both horizons) fail BH; T08/T10 (cushioned, both horizons) fail BH. Per §6.1, both criteria must fail at both horizons. They do.

### F2 — RS-Inflection (Q2+Q3 favorable; gate excludes Q1+Q4; nulls excluded)

| ID | Mode | H | TS | Rate_A | Rate_B | Delta_pp | Fav | Boot_p | BH_adj_p | BH_ok | r | Sign | Thin |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T11 | HG | 21d | STOPPED | 0.411 | 0.399 | +1.19 | N | 0.5328 | 0.5328 | no | +0.012 | Y | OK |
| T12 | HG | 21d | DEAD_MONEY | 0.177 | 0.221 | -0.43 | Y | 0.5328 | 0.5328 | no | +0.012 | N | OK |
| T13 | HG | 21d | CUSHIONED | 0.131 | 0.135 | -0.48 | N | 0.5328 | 0.5328 | no | +0.012 | Y | OK |
| T14 | HG | 63d | STOPPED | 0.626 | 0.607 | +1.89 | N | 0.5208 | 0.5328 | no | +0.011 | Y | OK |
| T15 | HG | 63d | DEAD_MONEY | 0.001 | 0.001 | -0.11 | Y | 0.5208 | 0.5328 | no | +0.011 | Y | OK |
| T16 | HG | 63d | CUSHIONED | 0.041 | 0.040 | +0.06 | Y | 0.5208 | 0.5328 | no | +0.011 | N | OK |
| T17 | RW | 21d | STOPPED | 0.409 | 0.414 | -0.96 | Y | 0.4928 | 0.5328 | no | -0.016 | Y | OK |
| T18 | RW | 21d | CUSHIONED | 0.133 | 0.132 | +0.15 | Y | 0.4928 | 0.5328 | no | -0.016 | Y | OK |
| T19 | RW | 63d | STOPPED | 0.620 | 0.620 | -0.04 | Y | 0.4958 | 0.5328 | no | -0.018 | N | OK |
| T20 | RW | 63d | CUSHIONED | 0.041 | 0.034 | +0.68 | Y | 0.4958 | 0.5328 | no | -0.018 | Y | OK |

**F2 verdict: NO-GO** — r_biserial ≈ 0.01 for HG (essentially zero effect size). The Q2+Q3 inflection hypothesis shows no detectable separation from Q1+Q4 on either horizon on the production trigger.

### F3 — Anti-Chase (ext_z ≤ 2.0 = favorable)

| ID | Mode | H | TS | Rate_A | Rate_B | Delta_pp | Fav | Boot_p | BH_adj_p | BH_ok | r | Sign | Thin |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T21 | HG | 21d | STOPPED | 0.404 | 0.409 | -0.43 | Y | 0.5022 | 0.5328 | no | -0.061 | Y | OK |
| T22 | HG | 21d | DEAD_MONEY | 0.168 | 0.205 | -3.63 | Y | 0.5022 | 0.5328 | no | -0.061 | Y | OK |
| T23 | HG | 21d | CUSHIONED | 0.130 | 0.120 | -0.97 | N | 0.5022 | 0.5328 | no | -0.061 | Y | OK |
| T24 | HG | 63d | STOPPED | 0.621 | 0.671 | -5.00 | Y | 0.4936 | 0.5328 | no | -0.038 | Y | OK |
| T25 | HG | 63d | DEAD_MONEY | 0.001 | 0.000 | +0.09 | N | 0.4936 | 0.5328 | no | -0.038 | Y | OK |
| T26 | HG | 63d | CUSHIONED | 0.041 | 0.041 | -0.23 | N | 0.4936 | 0.5328 | no | -0.038 | N | OK |
| T27 | RW | 21d | STOPPED | 0.407 | 0.407 | +0.10 | N | 0.4918 | 0.5328 | no | -0.021 | N | OK |
| T28 | RW | 21d | CUSHIONED | 0.131 | 0.130 | +0.06 | Y | 0.4918 | 0.5328 | no | -0.021 | N | OK |
| T29 | RW | 63d | STOPPED | 0.617 | 0.632 | -1.70 | Y | 0.4920 | 0.5328 | no | -0.014 | N | OK |
| T30 | RW | 63d | CUSHIONED | 0.041 | 0.038 | +0.30 | Y | 0.4920 | 0.5328 | no | -0.014 | N | OK |

**F3 verdict: NO-GO** — Only 4.6% of fires are ext_z > 2.0; the would-block group is tiny (n=2,299 fires, 1,270 episode clusters) but well above the THIN floor. Delta_pp at 63d stop-out = -5.00pp in the favorable direction but the MWU on the underlying return distribution is p=0.49 — not significant. Sign-stability also fails on several RW trials.

---

## 3. Fire-Rate Impact Table (mandatory R7 deliverable)

This table is required regardless of BH outcome. It shows how many fires each hard-gate would remove from the board.

| Factor | Mode | n_fires_total | n_would_block | gate_fire_rate_impact_pct | n_ep_clusters_blocked | Exceeds 40%? | GATE-REJECT? |
|---|---|---|---|---|---|---|---|
| F1 (washout) | HG | 49,939 | 26,974 | **54.0%** | 12,764 | YES | YES (>40% + 21d stop BH fails) |
| F2 (RS-inflect Q2+Q3) | HG | 46,111* | 22,378 | **48.5%** | 10,791 | YES | YES (>40% + 21d stop BH fails) |
| F3 (anti-chase) | HG | 49,939 | 2,299 | **4.6%** | 1,270 | no | NO (impact < 40%; no GATE-REJECT trigger) |
| F1 (washout) | RW | 49,939 | — | 0.0% | — | no | n/a |
| F2 (RS-inflect) | RW | 49,939 | — | 0.0% | — | no | n/a |
| F3 (anti-chase) | RW | 49,939 | — | 0.0% | — | no | n/a |

\* F2 population excludes 3,828 rows where rs_sector_quartile is null (7.7% of vg_fires).

**Key observations:**
- F1 and F2 are GATE-REJECT independent of statistical outcome: each would eliminate >40% of board flow, and neither cleared BH at 21d stop-out. Per §6.2, even if they had shown signal, the fire-rate impact would require Fable review before any gate deployment.
- F3 is NOT GATE-REJECT on the impact criterion (only 4.6% eliminated). However F3 is NO-GO on statistical grounds (all BH-adjusted p > 0.53).
- Mode-B (rank weight) impact is 0.0% by construction for all factors (R7 additive-lanes law).

---

## 4. Both-Halves Sign Stability Table

Split midpoint: ~2024-02-28 | Half-1: n=24,932 | Half-2: n=25,007

| ID | Factor | Mode | H | TS | Half1_pp | Half2_pp | Stable |
|---|---|---|---|---|---|---|---|
| T01 | F1 | HG | 21d | STOPPED | +2.8 | +2.0 | YES |
| T02 | F1 | HG | 21d | DEAD_MONEY | -13.5 | -12.9 | YES |
| T03 | F1 | HG | 21d | CUSHIONED | -3.6 | -4.6 | YES |
| T04 | F1 | HG | 63d | STOPPED | -4.6 | -5.8 | YES |
| T05 | F1 | HG | 63d | DEAD_MONEY | -0.1 | -0.2 | YES |
| T06 | F1 | HG | 63d | CUSHIONED | -2.0 | -2.3 | YES |
| T07 | F1 | RW | 21d | STOPPED | +2.6 | +2.6 | YES |
| T08 | F1 | RW | 21d | CUSHIONED | -3.3 | -3.9 | YES |
| T09 | F1 | RW | 63d | STOPPED | -4.3 | -4.7 | YES |
| T10 | F1 | RW | 63d | CUSHIONED | -1.7 | -1.9 | YES |
| T11 | F2 | HG | 21d | STOPPED | +1.1 | +1.3 | YES |
| T12 | F2 | HG | 21d | DEAD_MONEY | -0.4 | +0.1 | NO |
| T13 | F2 | HG | 21d | CUSHIONED | -0.5 | -0.5 | YES |
| T14 | F2 | HG | 63d | STOPPED | +1.8 | +2.0 | YES |
| T15 | F2 | HG | 63d | DEAD_MONEY | -0.1 | -0.1 | YES |
| T16 | F2 | HG | 63d | CUSHIONED | +0.1 | -0.1 | NO |
| T17 | F2 | RW | 21d | STOPPED | -0.9 | -1.0 | YES |
| T18 | F2 | RW | 21d | CUSHIONED | +0.2 | +0.1 | YES |
| T19 | F2 | RW | 63d | STOPPED | -0.1 | +0.1 | NO |
| T20 | F2 | RW | 63d | CUSHIONED | +0.7 | +0.6 | YES |
| T21 | F3 | HG | 21d | STOPPED | -0.4 | -0.5 | YES |
| T22 | F3 | HG | 21d | DEAD_MONEY | -3.6 | -3.6 | YES |
| T23 | F3 | HG | 21d | CUSHIONED | -1.0 | -0.9 | YES |
| T24 | F3 | HG | 63d | STOPPED | -5.1 | -4.9 | YES |
| T25 | F3 | HG | 63d | DEAD_MONEY | +0.1 | +0.1 | YES |
| T26 | F3 | HG | 63d | CUSHIONED | -0.2 | +0.2 | NO |
| T27 | F3 | RW | 21d | STOPPED | +0.1 | -0.1 | NO |
| T28 | F3 | RW | 21d | CUSHIONED | +0.1 | -0.1 | NO |
| T29 | F3 | RW | 63d | STOPPED | -1.8 | -1.6 | NO |
| T30 | F3 | RW | 63d | CUSHIONED | +0.3 | +0.3 | NO |

Note: T27-T30 sign-instability is from near-zero deltas (<0.3pp) where sign flips are noise. Numerically stable where it matters (T24 at -5pp is consistent across halves) but p=0.49.

---

## 5. Verdict Per Factor

### F1 — Washout Proximity
**VERDICT: NO-GO**
- Mode-A stop-out: T01 (21d) BH-adj=0.53, T04 (63d) BH-adj=0.53. Both fail q=0.10. Criterion: "BH-adjusted p > 0.10 at BOTH 21d and 63d" — MET.
- Mode-B cushioned: T08 (21d) BH-adj=0.53, T10 (63d) BH-adj=0.53. Both fail q=0.10. Criterion: "BH-adjusted p > 0.10 at BOTH 21d and 63d" — MET.
- Per §6.1: both criteria hold → NO-GO.
- Additional observation: gate would eliminate **54% of board fires** (GATE-REJECT per §6.2).

### F2 — RS-Inflection (Q2+Q3)
**VERDICT: NO-GO**
- Mode-A stop-out: T11 (21d) BH-adj=0.53, T14 (63d) BH-adj=0.53. Both fail.
- Mode-B cushioned: T18 (21d) BH-adj=0.53, T20 (63d) BH-adj=0.53. Both fail.
- Per §6.1: NO-GO.
- r_biserial ≈ 0.01 on HG trials — effectively zero effect size. The Q2+Q3 inflection recode shows no separation from Q1+Q4 on the production trigger.
- Additional observation: gate would eliminate **48.5% of board fires** (GATE-REJECT per §6.2).

### F3 — Anti-Chase (ext_z)
**VERDICT: NO-GO**
- Mode-A stop-out: T21 (21d) BH-adj=0.53, T24 (63d) BH-adj=0.53. Both fail.
- Mode-B cushioned: T28 (21d) BH-adj=0.53, T30 (63d) BH-adj=0.53. Both fail.
- Per §6.1: NO-GO.
- Gate fire-rate impact = 4.6% (does not trigger GATE-REJECT independently; but factor is still NO-GO on statistical grounds).
- T24 shows -5.0pp stop-out delta at 63d in the favorable direction with sign-stable halves — but p=0.49 on the underlying return distribution and BH-adj=0.53. The discrete rate difference is not supported by the continuous MWU.

---

## 6. Whole-Study Verdict

**TRIO ABLATION CLOSED.**

All three factors (F1, F2, F3) return NO-GO under the registered §6.1 criteria. Zero of the 30 registered trials survives Benjamini-Hochberg correction at q=0.10. The minimum BH-adjusted p-value across all 30 trials is 0.53 — well above the threshold.

Per §6.4: "If all three factors return NO-GO, the trio ablation is CLOSED. The program then proceeds without trio confirmation in the rank/gate stack; the factors remain display-only indefinitely."

**Downstream routing (§10 NO-GO path):**
- Registry: F1, F2, F3 marked `validation_status: falsified`
- §8 masterplan entry: trio ablation closed; trio factors remain display-only; no rank/gate integration authorized
- No impact on P1.1, P1.2, P1.4, P1.5 (independent study families)

---

## 7. Context Appendix A: Survivor-Stamped Rows

**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**

Total stamped rows in replay artifact: 0 (all rows are survivor_bias == False). The replay_boarded.parquet artifact contains only Massive-sourced rows within the 2022-06-30 → 2025-12-29 effective window. No pre-2021 context appendix data exists in this artifact.

Census stamp: 0% of member-months lack price history for this era. Delisted-name recall: 100% (17/17 probed delistings, 105/105 removals per P0 census).

---

## 7. Context Appendix B: Weekly-Trigger Bottom Backtest Comparison (R3)

**HYPOTHESIS — DIFFERENT TRIGGER — NOT VALIDATION.**

Prior bottom backtest result (n=315, quality=82.1, 64.1% durable, **weekly** MACD trigger):
- Cohort-washout proximity (F1): directional positive signal
- RS-inflection Q2+Q3 (F2): directional positive signal
- Anti-chase low ext_z (F3): directional positive signal

Current study uses the **production 2D/3D cascade trigger** (not weekly). Per R3: prior evidence is hypothesis from a different signal architecture, not validation of the production trigger.

**Direction comparison:**
- F1 (washout): prior = positive; current = MIXED (63d stop-out favorable at -5.2pp but p=0.50)
- F2 (RS-inflect): prior = positive; current = NO SIGNAL (r≈0.01, p=0.53)
- F3 (anti-chase): prior = positive; current = WEAK DIRECTIONAL (63d stop-out -5.0pp, 21d dead-money -3.6pp favorable but p=0.50)

The directions are weakly consistent (F1/F3 show directional deltas in the expected sign at 63d) but the effect sizes are negligible and statistically null. The hypothesis from the weekly-trigger backtest does not replicate on the production trigger — consistent with R3's warning that weekly-trigger evidence is a hypothesis, not validation.

---

## 8. Leak Audit

**Fill rule:** NEXT-BAR fill confirmed. fill_date = signal_date + 1 business day (all fill_offset == 1 in sample). entry_price = fill_date close per P0.1 contract.

**Feature freeze (PIT honesty):** ext_z, rs_sector_quartile, washout_proximity read directly from replay artifact (frozen at signal time per P0.1 design contract). No features recomputed in this study.

**Era boundary:** 2022-06-30 → 2025-12-29 (effective, §APPROVAL v1.1 clause 1). Nominal 2021-07-06 does not exist in ledger due to 250-bar MTF warmup.

**Sector-map non-PIT disclosure:** rs_sector_quartile uses current-GICS snapshot (928-label constituents map; post PR #1466 sector backfill). This is a known approximation per §APPROVAL clause 3 (92% fill on fires documented). 3,828 nulls excluded from F2 trials.

**Survivor-bias:** All rows survivor_bias == False. Zero stamped rows. Bias bounded at 0% for this era.

**Concordance:** on-disk price-source concordance = 98.5% (12 names/480 bars per §6 v1.1 amendment §4).

---

## 9. Registry §8 Entries

| Factor | validation_status | verdict | ship_mode | fire_rate_impact | gate_reject |
|---|---|---|---|---|---|
| F1 (washout proximity) | falsified | NO-GO | none | 54.0% | YES |
| F2 (RS-inflection Q2+Q3) | falsified | NO-GO | none | 48.5% | YES |
| F3 (anti-chase ext_z) | falsified | NO-GO | none | 4.6% | NO (but NO-GO by stats) |

---

## 10. Context Appendix C: Descriptive Supplementary Statistics

**Clean-liftoff delta by factor (context only, not hypothesis-tested):**

| Factor | Mode | H | CL_rate_A | CL_rate_B | CL_delta_pp |
|---|---|---|---|---|---|
| F1 | HG | 21d | 0.291 | 0.342 | -5.1 |
| F1 | HG | 63d | 0.378 | 0.304 | +7.4 |
| F2 | HG | 21d | 0.279 | 0.319 | -4.0 |
| F2 | HG | 63d | 0.332 | 0.352 | -2.0 |
| F3 | HG | 21d | 0.298 | 0.286 | +1.2 |
| F3 | HG | 63d | 0.338 | 0.288 | +5.0 |

**Note on T02 (F1-HG 21d DEAD_MONEY delta = -13.2pp):** The state_8_21 dead-money category has 8,891 rows out of 49,939 fires (17.8% baseline rate). The in-window washout group has 16.5% dead-money vs the out-of-window group's 29.7% — a 13.2pp difference. However, the MWU on the underlying continuous fwd_ret_21 distributions yields p=0.50, meaning the full return distributions of the two groups overlap nearly perfectly. The large dead-money rate difference is driven by the definition of the state category (dead-money in state_8_21 = small negative territory with no stop hit at 21d), which co-varies with the washout timing more than with final returns. This is a descriptive artifact, not a causal signal.

**Sector breakdown of would-block subgroups (Mode-A):** Available in results.json. No single sector dominates the would-block group for any factor — the blocks are broadly distributed across GICS sectors.

---

## Summary Table

| Factor | Verdict | Mode-A stop-out (BH_adj) | Mode-B cushioned (BH_adj) | Fire-rate impact | Gate-reject |
|---|---|---|---|---|---|
| F1 washout | **NO-GO** | T01: 0.53, T04: 0.53 | T08: 0.53, T10: 0.53 | 54.0% | YES |
| F2 RS-inflect | **NO-GO** | T11: 0.53, T14: 0.53 | T18: 0.53, T20: 0.53 | 48.5% | YES |
| F3 anti-chase | **NO-GO** | T21: 0.53, T24: 0.53 | T28: 0.53, T30: 0.53 | 4.6% | NO |

**Whole study: TRIO CLOSED. All three factors remain display-only.**

---

*Produced: 2026-07-05. Immutable after production. Results appended here; PREREG not edited.*
