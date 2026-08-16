# P-B2 — matched precursor discrimination (2026-08-14)

Authority: `none_research_display_only`. Tier: display / research tier — a matched, split-disciplined, WITHIN-SESSION CROSS-SECTIONAL discrimination study; not a promotion, not a gate, not a ranker, not a sizing input, and no production consumer exists or is proposed

**The pre-registration is the contract and it was frozen before this run.** `PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md` (sha256 `043a85d69f76ea86…`) was committed before the first outcome run of this instrument; the commit order in history is the proof. Every definition, stratum, floor and gate below is read from it. Deviations are numbered amendments (§10) — there are 4.

Governing ruling: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`. Program home: `research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md (sec.3, the P-B2 row)`. Pinned definitions: `washout_onset_w1.py` (W-P0) and `pb_case_decomposition.py` (P-B), **imported — not re-derived**.

> **Estimand scope, which bounds every verdict below.** All strata are within-session, so every P-B2 verdict is a **within-session cross-sectional** statement: does the footprint separate names on the same tape on the same day. A NULL here says nothing about market-wide or regime-timing information in the same family. Instrument verdicts are not market verdicts.

---

## 1. What was read

One store, one panel: `data/china_stocks_raw` through W-P0's own `build_panel()` + `attach_conditioners(panel, None)` over W-P0's own window **2011-01-01 → 2026-08-07** — 4,840,077 live bars, 1,779 names, 3,786 sessions. No third implementation of any definition exists.

**Anchor universes** (a row = one (ticker, session) panel bar). Honest-N first, always.

| universe | board | FIT | HOLDOUT | AUDIT |
|---|---|---|---|---|
| U0 | main | 3117 sess / 1202 nm / 2,486,812 r | 570 sess / 1219 nm / 579,745 r | 19 sess / 1047 nm / 16,687 r |
| U0 | chinext10 | 2320 sess / 221 nm / 215,447 r | 0 sess / 0 nm / 0 r | 0 sess / 0 nm / 0 r |
| U0 | chinext20 | 795 sess / 304 nm / 196,119 r | 570 sess / 336 nm / 171,612 r | 19 sess / 326 nm / 5,765 r |
| U0 | star | 862 sess / 184 nm / 80,947 r | 570 sess / 224 nm / 115,559 r | 19 sess / 219 nm / 3,640 r |
| U1 | main | 3115 sess / 1201 nm / 1,657,970 r | 570 sess / 1213 nm / 318,910 r | 19 sess / 955 nm / 14,208 r |
| U1 | chinext10 | 2287 sess / 220 nm / 150,093 r | 0 sess / 0 nm / 0 r | 0 sess / 0 nm / 0 r |
| U1 | chinext20 | 795 sess / 304 nm / 151,016 r | 570 sess / 336 nm / 123,822 r | 19 sess / 300 nm / 4,516 r |
| U1 | star | 862 sess / 182 nm / 64,200 r | 570 sess / 224 nm / 77,126 r | 19 sess / 186 nm / 2,308 r |

U0 = cold ∧ split assigned ∧ dd250 finite. U1 = U0 ∧ dd250 ≤ −20%. Cold rows excluded for carrying no split (W-P0's 20-session embargo): **114,863**; excluded for an unmeasurable drawdown (`na` band, under 200 bars of history): **139,207**. Neither is silently folded anywhere.

## 2. Labels, censoring, and what censoring is never allowed to become

POSITIVE = `fb_H`. NEGATIVE = `win_ok_H` ∧ ¬`fb_H`. CENSORED = ¬`win_ok_H` — **censored rows enter neither class and are never scored as misses.** The partition is exact everywhere (`verify.censoring_partition`).

| H | board | split | pos episodes | sessions | positives | negatives | censored | partition exact | board visible in broken window | % of positives |
|---|---|---|---|---|---|---|---|---|---|---|
| 10 | main | FIT | 11221 | 3115 | 91,366 | 1,510,653 | 55,951 | yes | 9,778 | 10.702% |
| 10 | main | HOLDOUT | 2960 | 570 | 24,116 | 289,680 | 5,114 | yes | 472 | 1.957% |
| 10 | chinext10 | FIT | 1564 | 2287 | 12,542 | 132,772 | 4,779 | yes | 1,141 | 9.097% |
| 10 | chinext20 | FIT | 291 | 795 | 2,361 | 148,369 | 286 | yes | 10 | 0.424% |
| 10 | chinext20 | HOLDOUT | 423 | 570 | 3,527 | 119,634 | 661 | yes | 41 | 1.162% |
| 10 | star | FIT | 84 | 862 | 736 | 63,424 | 40 | yes | 0 | 0.0% |
| 10 | star | HOLDOUT | 246 | 570 | 1,934 | 72,315 | 2,877 | yes | 21 | 1.086% |
| 5 | main | FIT | 10817 | 3115 | 48,277 | 1,581,091 | 28,602 | yes | 4,289 | 8.884% |
| 5 | main | HOLDOUT | 2768 | 570 | 12,244 | 304,090 | 2,576 | yes | 168 | 1.372% |
| 5 | chinext10 | FIT | 1498 | 2287 | 6,623 | 141,062 | 2,408 | yes | 497 | 7.504% |
| 5 | chinext20 | FIT | 265 | 795 | 1,175 | 149,694 | 147 | yes | 5 | 0.426% |
| 5 | chinext20 | HOLDOUT | 385 | 570 | 1,689 | 121,764 | 369 | yes | 18 | 1.066% |
| 5 | star | FIT | 80 | 862 | 365 | 63,815 | 20 | yes | 0 | 0.0% |
| 5 | star | HOLDOUT | 221 | 570 | 933 | 74,664 | 1,529 | yes | 3 | 0.322% |

**The censoring diagnostic must be discussed, and here it is.** The prereg requires that if the count of rows where a board is visible inside a broken window exceeds 1% of positives on any board, the receipt discuss it. **5 of the 14 board × split cells above sit under that 1% trigger** (H10 chinext20 FIT 0.424%, H10 star FIT 0.0%, H5 chinext20 FIT 0.426%, H5 star FIT 0.0%, H5 star HOLDOUT 0.322%); the other 9 run from 1.066% to 10.702% and are the cells the prereg requires discussed. The 4 largest are H10 main FIT 10.702%, H10 chinext10 FIT 9.097%, H5 main FIT 8.884%, H5 chinext10 FIT 7.504% — every one of them a FIT cell, where the suspension-broken windows are denser. The mechanism is W-P0's closure-tolerant completeness rule — a row whose forward chain breaks (a suspension gap over 21 calendar days) fails `win_ok_H` even when a tolerant board is visible inside the nominal window. Those rows are **censored, not negative**, which is the conservative direction for a discrimination study: they are removed from both classes rather than counted as misses. Because the removal is not guaranteed to be balanced across F-classes, the per-F-class censored counts are in the JSON for every footprint, and every DISCRIMINATOR carries the coarse Manski bound below.

**How unbalanced that removal actually is.** Censoring is not guaranteed even across F-classes, so the measurement is printed rather than only stored. In the primary family (`H10|M1|main|FIT`), as each class's own censored share, the widest imbalance is **SECT** (4.22% of F=TRUE rows vs 2.82% of F=FALSE, ratio 1.49) and the widest in the other direction is **QB** (ratio 0.80); every footprint in that family:

| footprint | censored share of F=TRUE rows | censored share of F=FALSE rows | ratio T/F |
|---|---|---|---|
| DD35 | 3.63% | 3.16% | 1.15 |
| MA200 | 3.34% | 3.53% | 0.94 |
| CONF | 3.23% | 3.58% | 0.90 |
| CB | 3.23% | 3.39% | 0.95 |
| SECT | 4.22% | 2.82% | 1.49 |
| QB | 2.98% | 3.72% | 0.80 |
| VZ | 3.43% | 3.36% | 1.02 |

The same counts for every other cell — every footprint, board, split, arm and horizon, in the primary and placebo batteries alike — are in the JSON under `primary.*.censored_rows_F_true` / `censored_rows_F_false` beside each cell's `honest_n_F_true` / `honest_n_F_false`. No DISCRIMINATOR stands here, so no Manski bound was triggered; the asymmetry is printed anyway because it bounds how a future verdict on this substrate would have to be read.

**Episode identity cross-check.** A positive row's episode key is its realised board. By W-P0's ladder-0 lemma every such board should also be a cold-eve first board in P-B's own `extract_events` cohort; the overlap is printed, not asserted — `H10|U1|main|FIT` 100.0%, `H10|U1|chinext10|FIT` 100.0%, `H10|U1|chinext20|FIT` 100.0%, `H10|U1|star|FIT` 100.0%. The cold rule guarantees every positive is a genuine 0->1 ignition (W-P0 sec.5 ladder-0 lemma), so a positive row's realised board is a cold-eve first board. P-B's cohort additionally requires the eve->event pair to sit inside the 21-day closure-tolerant step rule, which is why the overlap is reported as a count and not asserted to be 100%.

## 3. Measurability — unmeasurable is never FALSE

P-B's boolean derivation codes missing as FALSE. Leaving that in the F=FALSE class would estimate the counterfactual from a mixture of measured negatives and unmeasurables, so a row enters footprint F's analysis only if F is measurable on it.

| code | footprint | mask | U0 rows excluded | % of U0 |
|---|---|---|---|---|
| DD20 | dd_le_m20 | u_eligibility | 0 | 0.0% |
| DD35 | dd_le_m35 | u_eligibility | 0 | 0.0% |
| MA200 | under_ma200 | ma200_finite | 0 | 0.0% |
| CONF | confluence_long | all_u_rows | 0 | 0.0% |
| CB | cb_recent | all_u_rows | 0 | 0.0% |
| SECT | sector_deep35_ge40 | sector_known | 268,573 | 6.936% |
| QB | quiet_base | rv_rank_finite | 17,286 | 0.446% |
| VZ | volz_gt1 | volz_measurable | 714 | 0.018% |

CONF and CB are treated measurable on all U rows — a **declared approximation** (prereg §4): their indicator warm-up is covered by the 200-bar dd-finiteness floor. MA200 and the below-gradient use the same covering, and it is *measured* rather than assumed: across 64 sampled names, 233,381 dd-finite bars carried **0** bars with a non-finite 200DMA (raw store non-finite closes: 0, highs: 0). See reading note R2.

## 4. G1 board floors — which boards can receive a verdict at all

| H | arm | board | FIT pos episodes | HOLDOUT pos episodes | status |
|---|---|---|---|---|---|
| 10 | M0 | main | 15782 | 4385 | VERDICT_ELIGIBLE |
| 10 | M0 | chinext10 | 2129 | 0 | DESCRIPTIVE_ONLY |
| 10 | M0 | chinext20 | 381 | 561 | VERDICT_ELIGIBLE |
| 10 | M0 | star | 100 | 347 | DESCRIPTIVE_ONLY |
| 10 | M1 | main | 11221 | 2960 | VERDICT_ELIGIBLE |
| 10 | M1 | chinext10 | 1564 | 0 | DESCRIPTIVE_ONLY |
| 10 | M1 | chinext20 | 291 | 423 | VERDICT_ELIGIBLE |
| 10 | M1 | star | 84 | 246 | DESCRIPTIVE_ONLY |
| 5 | M0 | main | 15809 | 4351 | VERDICT_ELIGIBLE |
| 5 | M0 | chinext10 | 2135 | 0 | DESCRIPTIVE_ONLY |
| 5 | M0 | chinext20 | 382 | 556 | VERDICT_ELIGIBLE |
| 5 | M0 | star | 99 | 341 | DESCRIPTIVE_ONLY |
| 5 | M1 | main | 10817 | 2768 | VERDICT_ELIGIBLE |
| 5 | M1 | chinext10 | 1498 | 0 | DESCRIPTIVE_ONLY |
| 5 | M1 | chinext20 | 265 | 385 | VERDICT_ELIGIBLE |
| 5 | M1 | star | 80 | 221 | DESCRIPTIVE_ONLY |

Floors: ≥ 200 distinct positive episodes in FIT **and** ≥ 60 in HOLDOUT. `chinext10` is DESCRIPTIVE_ONLY **by construction** — the board key exists only before 2020-08-24, so it has zero HOLDOUT rows, forever. The prereg's frozen expectation was that `star` fails the FIT floor and the realistic gated ceiling is ≤ 8 footprints × 2 boards × 2 horizons = 32; the measured outcome is **31 gated cells** on main, chinext20.

## 5. Verdicts

**DISCRIMINATOR** requires G1 floors ∧ G2 (FIT |z₂ᵥᵥ| ≥ 2.81) ∧ G3 (thinned-anchor sign) ∧ G4 (sign agrees in ≥ ⅔ of measurable FIT eras) ∧ G5 (HOLDOUT same sign and one-sided z ≥ 1.28). **SUGGESTIVE** = G1 met, |z| ≥ 1.96, ≥ 1 of G3/G4/G5 failed. **NULL** = G1 met and neither. A dead feature prints **NOT_EVALUABLE**, never NULL.

### H = 10 (primary)

| board | footprint | arm | honest-N (F=TRUE, retained) | FIT excess pp | FIT z₂ᵥᵥ | HOLD excess pp | HOLD z | G1..G5 | verdict | Holm p (ref) | placebo max\|excess\| pp | placebo max\|z\| |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main | DD20 | M0 | 11120 ep / 1,574,779 r | +1.043 | 4.14 | +2.451 | 3.67 | ✓✓✓✓✓ | SUGGESTIVE | 0.0001 | 1.408 | 5.83 |
| main | DD35 | M1 | 6858 ep / 725,412 r | +2.954 | 10.42 | +4.965 | 5.15 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 1.263 | 3.90 |
| main | MA200 | M1 | 6215 ep / 733,003 r | -2.747 | -8.67 | -4.605 | -5.11 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.385 | 1.47 |
| main | CONF | M1 | 6357 ep / 825,497 r | +0.216 | 1.03 | +0.157 | 0.32 | ✓·✓·· | NULL | 0.9072 | 0.170 | 1.03 |
| main | CB | M1 | 2177 ep / 179,832 r | +0.120 | 0.55 | +0.937 | 1.70 | ✓·✓·✓ | NULL | 1.0000 | 0.149 | 0.67 |
| main | SECT | M1 | 3580 ep / 358,281 r | +0.048 | 0.11 | +1.051 | 1.23 | ✓·✓·· | NULL | 1.0000 | 0.505 | 1.36 |
| main | QB | M1 | 5399 ep / 765,652 r | -1.464 | -6.78 | -1.677 | -2.75 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.195 | 0.99 |
| main | VZ | M1 | 6691 ep / 237,278 r | +1.406 | 8.47 | +2.759 | 4.69 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.089 | 0.74 |
| chinext20 | DD20 | M0 | 285 ep / 140,001 r | -0.499 | -1.52 | -0.166 | -0.36 | ✓·✓·· | NULL | 0.3861 | 0.916 | 3.11 |
| chinext20 | DD35 | M1 | 165 ep / 83,701 r | +0.140 | 0.46 | +1.278 | 2.89 | ✓···✓ | NULL | 1.0000 | 0.701 | 2.19 |
| chinext20 | MA200 | M1 | 111 ep / 38,809 r | -0.762 | -2.45 | -2.317 | -2.68 | ✓·✓✓✓ | SUGGESTIVE | 0.0708 | 0.604 | 1.96 |
| chinext20 | CONF | M1 | 159 ep / 56,985 r | +0.620 | 2.64 | +0.684 | 1.83 | ✓·✓✓✓ | SUGGESTIVE | 0.0498 | 0.206 | 0.77 |
| chinext20 | CB | M1 | 64 ep / 15,965 r | +0.716 | 1.90 | +0.824 | 1.64 | ✓·✓✓✓ | NULL | 0.2293 | 0.530 | 1.01 |
| chinext20 | SECT | M1 | 81 ep / 27,130 r | -0.104 | -0.27 | -0.131 | -0.15 | ✓·✓·· | NULL | 1.0000 | 0.241 | 0.65 |
| chinext20 | QB | M1 | 129 ep / 70,837 r | -0.742 | -2.77 | -0.432 | -0.84 | ✓·✓✓· | SUGGESTIVE | 0.0388 | 0.479 | 1.52 |
| chinext20 | VZ | M1 | 167 ep / 20,901 r | +0.726 | 2.93 | +0.933 | 1.78 | ✓✓✓✓✓ | SUGGESTIVE | 0.0275 | 0.346 | 1.41 |

### H = 5 (secondary)

| board | footprint | arm | honest-N (F=TRUE, retained) | FIT excess pp | FIT z₂ᵥᵥ | HOLD excess pp | HOLD z | G1..G5 | verdict | Holm p (ref) | placebo max\|excess\| pp | placebo max\|z\| |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main | DD20 | M0 | 10659 ep / 1,602,146 r | +0.532 | 3.83 | +1.267 | 3.14 | ✓✓✓✓✓ | SUGGESTIVE | 0.0005 | 0.748 | 5.91 |
| main | DD35 | M1 | 6545 ep / 738,775 r | +1.568 | 8.94 | +2.649 | 4.59 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.673 | 4.03 |
| main | MA200 | M1 | 5241 ep / 747,321 r | -1.614 | -8.47 | -2.550 | -5.63 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.222 | 1.49 |
| main | CONF | M1 | 5760 ep / 840,356 r | +0.104 | 0.94 | +0.239 | 0.95 | ✓·✓·· | NULL | 1.0000 | 0.097 | 1.09 |
| main | CB | M1 | 1629 ep / 182,740 r | +0.102 | 0.77 | +0.655 | 1.85 | ✓··✓✓ | NULL | 1.0000 | 0.038 | 0.28 |
| main | SECT | M1 | 2993 ep / 366,948 r | -0.049 | -0.24 | +0.334 | 0.50 | ✓·✓·· | NULL | 1.0000 | 0.325 | 1.72 |
| main | QB | M1 | 4515 ep / 777,286 r | -0.889 | -7.73 | -1.030 | -3.30 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.116 | 1.05 |
| main | VZ | M1 | 5154 ep / 241,184 r | +1.013 | 7.99 | +2.276 | 4.64 | ✓✓✓✓✓ | SUGGESTIVE | 0.0000 | 0.024 | 0.33 |
| chinext20 | DD20 | M0 | 257 ep / 140,129 r | -0.359 | -1.91 | -0.323 | -1.18 | ✓·✓·· | NULL | 0.2798 | 0.413 | 2.64 |
| chinext20 | DD35 | M1 | 149 ep / 83,805 r | +0.045 | 0.25 | +0.485 | 2.47 | ✓···✓ | NULL | 1.0000 | 0.394 | 2.34 |
| chinext20 | MA200 | M1 | 81 ep / 38,850 r | -0.308 | -1.79 | -1.184 | -2.15 | ✓·✓✓✓ | NULL | 0.2798 | 0.361 | 2.17 |
| chinext20 | CONF | M1 | 132 ep / 57,068 r | +0.264 | 1.91 | +0.296 | 1.48 | ✓·✓✓✓ | NULL | 0.2798 | 0.119 | 0.86 |
| chinext20 | CB | M1 | 44 ep / 15,982 r | — | — | — | — | ····· | NOT_EVALUABLE | — | 0.359 | 1.34 |
| chinext20 | SECT | M1 | 61 ep / 27,156 r | -0.029 | -0.15 | +0.539 | 1.11 | ✓···· | NULL | 1.0000 | 0.070 | 0.25 |
| chinext20 | QB | M1 | 104 ep / 70,926 r | -0.426 | -2.84 | -0.230 | -0.87 | ✓✓✓✓· | SUGGESTIVE | 0.0319 | 0.296 | 1.52 |
| chinext20 | VZ | M1 | 127 ep / 20,928 r | +0.467 | 2.72 | +0.404 | 0.94 | ✓·✓✓· | SUGGESTIVE | 0.0392 | 0.223 | 1.19 |

The two placebo columns are the maximum over the three §6.3 shifts (S ∈ {250, 500, 1000}) **for that exact cell** — the same footprint, arm, board and horizon, on the shifted panel where no alignment with outcomes survives. They are printed beside each verdict because a family-level calibration rate cannot tell a reader which cells carried it; `—` means the placebo cell was not computed there. Read the DD rows against their own FIT columns.

**Coincident-indicator stamps, which travel with every verdict on them.** **VZ** — COINCIDENT INDICATOR — median arming lead 1 session (P-B sec.5). This is a same-bar volume surprise, not an early precursor, and is never described as one. **CB** — NEAR-COINCIDENT INDICATOR — median arming lead 5 sessions (P-B sec.5). Never described as a precursor.

**VZ no-vol-stratum sensitivity** (prereg §5.3 — VZ keeps the vol decile; this is printed beside it, and the verdict stays on the vol-stratified arm): `H10|main|FIT` +1.311 pp, `H10|main|HOLDOUT` +2.647 pp, `H10|chinext20|FIT` +0.695 pp, `H10|chinext20|HOLDOUT` +0.954 pp, `H5|main|FIT` +0.974 pp, `H5|main|HOLDOUT` +2.164 pp, `H5|chinext20|FIT` +0.431 pp, `H5|chinext20|HOLDOUT` +0.475 pp.

Gate glyphs are `G1_footprint · G2 · G3 · G4 · G5`; `✓` passed, `·` failed. A `(dX)` beside a footprint is the **band-local** label — over 80% of the retained F=TRUE mass sits in that single depth band, which the prereg predicted for MA200 and SECT and which the verdict must say out loud. Holm-adjusted p is a reference column inside each (board, horizon) family and changes no gate.

**11 of the 31 gated cells cleared G1–G5** — H10 main DD20/DD35/MA200/QB/VZ; H10 chinext20 VZ; H5 main DD20/DD35/MA200/QB/VZ — and **every one of them was downgraded by the frozen §6.3 family consequence**, which is why **no DISCRIMINATOR verdict stands anywhere**. No Manski bound is therefore required; a null is a valid ship (prereg §14) and it ships as one.

**What that null is, stated precisely.** prereg §14 frames the disposition on the precondition that *the footprints mostly fail these gates against matched controls*. That precondition did **not** obtain on `main`: 5 of the 8 footprints at H=10 and 5 of the 8 footprints at H=5 cleared every gate there, at honest-N in the millions of rows and thousands of episodes. What removed those verdicts was the §6.3 calibration failure of the inference machinery in the same families — so the shipped null is a **calibration-governed null, not a measured absence of structure**. §6 states what the calibration failure is evidence of and what it is not; the consequence is applied as frozen either way.

## 6. Placebo-feature calibration — the measured false-positive guard

The entire footprint panel is shifted forward by S ∈ {250, 500, 1000} sessions along each name's own axis — within-name persistence, cross-sectional prevalence and session structure all survive; only the alignment with outcomes is broken — and the full primary battery is re-run per shift.

| family (board · H) | cells tested | rejections at the G2 bar | realised rate | fail bar (5× nominal) | calibration |
|---|---|---|---|---|---|
| main · H10 | 48 | 11 | 22.92% | 2.5% | **FAILED** |
| chinext20 · H10 | 48 | 2 | 4.17% | 2.5% | **FAILED** |
| main · H5 | 48 | 12 | 25.00% | 2.5% | **FAILED** |
| chinext20 · H5 | 48 | 1 | 2.08% | 2.5% | passed |

**Every rejection, individually.** A family rate is an average over its cells; these are the cells that produced it. `excess pp` is the matched excess measured on the SHIFTED panel, where no alignment with outcomes is supposed to survive.

| family (board · H) | shift S | footprint | arm | excess pp | z₂ᵥᵥ |
|---|---|---|---|---|---|
| main · H10 | 250 | DD20 | M0 | +1.042 | 5.28 |
| main · H10 | 250 | DD35 | M0 | +1.187 | 6.17 |
| main · H10 | 250 | DD35 | M1 | +0.855 | 3.54 |
| main · H10 | 500 | DD20 | M0 | +1.408 | 5.83 |
| main · H10 | 500 | DD35 | M0 | +1.491 | 5.51 |
| main · H10 | 500 | DD20 | M1 | +1.024 | 3.77 |
| main · H10 | 500 | DD35 | M1 | +1.077 | 3.22 |
| main · H10 | 1000 | DD20 | M0 | +1.103 | 4.04 |
| main · H10 | 1000 | DD35 | M0 | +1.342 | 4.71 |
| main · H10 | 1000 | DD20 | M1 | +1.098 | 3.56 |
| main · H10 | 1000 | DD35 | M1 | +1.263 | 3.90 |
| chinext20 · H10 | 500 | DD20 | M0 | +0.916 | 3.11 |
| chinext20 · H10 | 500 | DD35 | M0 | +1.061 | 3.13 |
| main · H5 | 250 | DD20 | M0 | +0.522 | 4.81 |
| main · H5 | 250 | DD35 | M0 | +0.622 | 6.31 |
| main · H5 | 250 | DD35 | M1 | +0.451 | 3.47 |
| main · H5 | 500 | DD20 | M0 | +0.748 | 5.91 |
| main · H5 | 500 | DD35 | M0 | +0.802 | 5.69 |
| main · H5 | 500 | MA200 | M0 | +0.363 | 2.84 |
| main · H5 | 500 | DD20 | M1 | +0.545 | 3.73 |
| main · H5 | 500 | DD35 | M1 | +0.564 | 3.09 |
| main · H5 | 1000 | DD20 | M0 | +0.562 | 3.74 |
| main · H5 | 1000 | DD35 | M0 | +0.733 | 4.84 |
| main · H5 | 1000 | DD20 | M1 | +0.592 | 3.41 |
| main · H5 | 1000 | DD35 | M1 | +0.673 | 4.03 |
| chinext20 · H5 | 500 | DD35 | M0 | +0.591 | 3.25 |

**What the failure is, measured.** The signature is not the shape of a broken standard error. All **26 of the 26** placebo rejections are **positive-signed**, and **25 of 26** sit in the DD family (`DD20` / `DD35`); across every non-DD footprint the realised rejection rate is **1/144 = 0.69%**, inside the 2.5% bar. The magnitudes say the same thing: on `main` at H=10, DD20's placebo excess (+1.042, +1.408, +1.103 pp at S = 250, 500, 1000) **reproduces its real excess** (+1.043 pp) essentially in full, and DD35's reproduces 29–43% of its real +2.954 pp. And the sensitivity control agrees: a label planted EQUAL TO THE OUTCOME prints z = 48.83 unshifted and still carries z = 2.687 / 1.540 / 2.361 **after** shifting — non-zero residual leak, under the soft ceiling max(G2 = 2.81, |z₀|/10) = 4.88 the check is measured against.

**The reading.** That is the signature of **residual feature–outcome alignment for multi-year persistent states**: `dd250` at t−250, t−500 and even t−1000 is still correlated with `dd250` at t on the same name, so shifting the tape does not break the alignment it is designed to break. For a persistent feature the placebo **null itself is false**, and a rejection under it is not a false positive in the sense the guard assumes. What this is **not**: it is not evidence of a symmetric standard-error failure — a broken SE would reject in both signs and across footprints, and neither happened — and on the non-DD footprints the same machinery measured calibrated at nominal. That bounds the failure; it does not repair it, and it changes no verdict here.

**The SUGGESTIVE bar inherits this.** Inside a family that failed calibration at the G2 bar (|z| ≥ 2.81), the SUGGESTIVE bar (|z| ≥ 1.96) is a **lower** bar on the same statistic and is therefore **at least as uncalibrated**. Every SUGGESTIVE printed in a failed family carries that; none of them is a weaker but sounder verdict.

**The placebo subsample shrinks with S, and that is disclosed rather than absorbed.** A shifted row whose source bar falls before its own name's first bar carries no footprint value and is excluded and counted, so a name shorter than S vanishes entirely. On `H10|M0|main|FIT|DD20` the rows excluded as unmeasurable run 0 → 235,742 → 481,161 → 926,729 at S = 0 (unshifted), 250, 500, 1000. The direction is conservative for a false-positive guard: a smaller subsample means a larger standard error and therefore FEWER rejections, so the measured rejection rate is if anything an understatement of the miscalibration, never an inflation of it.

A (board, horizon) family whose realised rejection rate at the G2 bar exceeds 5x nominal (> 2.5%) has NO DISCRIMINATOR: every one downgrades to SUGGESTIVE and the receipt states that the inference machinery failed its own calibration. The consequence is applied as frozen; the mechanism evidence above bounds what the failure means, and does not soften what it costs.

## 7. Retention — contrast-bearing strata are a biased subset, and this says how

Strata are sparse at these densities, and the `exp` leg collapses first. A cell retaining **< 50%** of its F=TRUE positive episodes is **NOT_EVALUABLE** — never NULL, never a verdict.

| board | footprint | arm | contrast strata | F=TRUE rows kept | F=TRUE pos episodes kept | F=FALSE rows kept | top retained dd_band | band-local |
|---|---|---|---|---|---|---|---|---|
| main | DD20 | M0 | 29,475/32,920 | 98.3% | 99.1% | 98.18% | d1_m20_m35 55.18% | — |
| main | DD35 | M1 | 28,545/32,078 | 99.59% | 99.65% | 98.8% | d2_m35_m50 74.25% | — |
| main | MA200 | M1 | 61,453/168,559 | 56.69% | 72.12% | 86.44% | d1_m20_m35 71.63% | — |
| main | CONF | M1 | 91,564/168,559 | 88.77% | 94.64% | 88.6% | d1_m20_m35 54.21% | — |
| main | CB | M1 | 54,398/168,559 | 96.86% | 98.46% | 60.95% | d1_m20_m35 53.66% | — |
| main | SECT | M1 | 47,593/165,477 | 62.94% | 69.25% | 44.87% | d2_m35_m50 48.66% | — |
| main | QB | M1 | 19,982/27,543 | 99.24% | 99.47% | 94.09% | d1_m20_m35 54.91% | — |
| main | VZ | M1 | 69,684/168,530 | 96.0% | 96.96% | 75.52% | d1_m20_m35 55.79% | — |
| chinext20 | DD20 | M0 | 7,508/8,632 | 92.88% | 97.94% | 99.77% | d1_m20_m35 45.0% | — |
| chinext20 | DD35 | M1 | 7,675/8,579 | 98.56% | 98.8% | 98.09% | d2_m35_m50 71.12% | — |
| chinext20 | MA200 | M1 | 11,099/42,888 | 35.45% | 62.01% | 59.16% | d1_m20_m35 57.78% | — |
| chinext20 | CONF | M1 | 17,077/42,888 | 64.42% | 79.9% | 70.54% | d2_m35_m50 43.38% | — |
| chinext20 | CB | M1 | 9,715/42,888 | 87.96% | 86.49% | 34.99% | d1_m20_m35 43.37% | — |
| chinext20 | SECT | M1 | 9,093/41,871 | 48.92% | 66.39% | 27.78% | d2_m35_m50 54.89% | — |
| chinext20 | QB | M1 | 5,547/7,517 | 98.04% | 98.47% | 93.39% | d2_m35_m50 42.87% | — |
| chinext20 | VZ | M1 | 12,216/42,888 | 87.18% | 91.26% | 45.25% | d1_m20_m35 43.99% | — |

## 8. Two-speed lead curves (secondary, descriptive, gates nothing)

coldness at lead <= 20 is IMPLIED by the event's own cold eve (COLD_LOOKBACK_K = 20), so cold-driven exclusions are ~0 through lead 20 and jump at lead 21 — exactly the [6,20] -> [21,60] window boundary. NO comparison may be made across that boundary on the full-cohort curve; the boundary is a COLD_LOOKBACK_K artifact, not a signal.

printed ONLY for under_ma200, confluence_long, cb_recent, sector_deep35_ge40, quiet_base, volz_gt1. It is NOT interpretable for the DD / depth / duration families — U1-eligibility at every lead IS the DD condition, so their constant-cohort curves are tautologically flat — and is therefore not printed for them. Its absence there is deliberate, not an omission.

**What the N columns are.** `eligible cases (cohort)` and `eligible controls (cohort)` are the (board, split) cohort's own counts at that lead — every U1-eligible case anchor and every verified-quiet control on that board and split, **before** any footprint's measurability mask and **before** matching. They are NOT any one footprint's N: each footprint then drops the rows its mask cannot measure, and the estimator keeps only rows landing in a stratum that carries both classes. `excluded` is this cohort's own per-lead exclusion count, not the cohort-wide one.

**The gap is large enough to name.** `main · FIT`, ℓ = 1, SECT: **10,584** cohort-eligible case anchors → **9,858** measurable for that footprint → **8,630** actually matched into a contrast-bearing stratum. Every footprint's matched N at every lead is in the JSON as `lead_curves.curves.<board>|<split>|<footprint>|<mode>.<lead>.matched_case_anchors`, beside its own `case_anchors`.

**main · FIT** — excess prevalence of the footprint among case anchors vs matched quiet controls, pp, with a session-block 95% CI.

| lead ℓ | eligible cases (cohort) | eligible controls (cohort) | excluded | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10,584 | 1,172,209 | 1 | +0.0 (+0.0,+0.0) | +13.5 (+11.4,+15.7) | -8.2 (-9.5,-7.0) | +0.5 (-0.8,+1.8) | +0.6 (-0.2,+1.5) | +0.1 (-0.8,+1.0) | -7.3 (-8.8,-6.0) | +10.4 (+8.9,+11.9) |
| 2 | 10,196 | 1,172,209 | 390 | +0.0 (+0.0,+0.0) | +14.3 (+12.7,+15.9) | -6.9 (-8.3,-5.1) | +0.3 (-0.8,+1.5) | +0.3 (-0.6,+1.1) | +0.4 (-0.5,+1.3) | -6.4 (-7.7,-5.1) | +5.6 (+4.4,+6.7) |
| 3 | 9,901 | 1,172,209 | 690 | +0.0 (+0.0,+0.0) | +15.9 (+14.2,+17.9) | -6.0 (-8.0,-3.0) | +0.2 (-1.1,+1.4) | +0.5 (-0.4,+1.4) | +0.2 (-0.8,+1.0) | -6.5 (-7.9,-5.0) | +3.9 (+2.7,+5.2) |
| 5 | 9,490 | 1,172,209 | 1,110 | +0.0 (+0.0,+0.0) | +16.8 (+14.4,+19.8) | -5.1 (-6.7,-3.0) | +0.4 (-1.0,+1.7) | +0.2 (-0.6,+1.0) | +0.3 (-1.0,+1.6) | -4.6 (-5.9,-3.5) | +2.6 (+1.8,+3.5) |
| 7 | 9,033 | 1,172,209 | 1,573 | +0.0 (+0.0,+0.0) | +16.4 (+15.1,+17.9) | -4.9 (-6.0,-3.8) | -0.4 (-1.7,+0.8) | +0.0 (-1.0,+1.0) | +1.0 (-0.2,+2.2) | -4.3 (-5.7,-3.0) | +3.0 (+1.9,+4.2) |
| 10 | 8,449 | 1,172,209 | 2,175 | +0.0 (+0.0,+0.0) | +16.8 (+15.2,+18.3) | -4.2 (-5.3,-3.1) | -0.6 (-1.8,+0.7) | +0.3 (-0.5,+1.0) | +1.1 (+0.2,+2.2) | -3.9 (-5.4,-2.6) | +1.0 (+0.1,+1.9) |
| 15 | 7,766 | 1,172,209 | 2,874 | +0.0 (+0.0,+0.0) | +16.7 (+15.3,+18.1) | -3.9 (-4.9,-3.0) | -0.8 (-2.3,+0.5) | +0.3 (-0.4,+1.1) | +0.4 (-0.7,+1.3) | -3.3 (-4.6,-2.1) | +1.8 (+0.9,+2.6) |
| 20 | 7,248 | 1,172,209 | 3,429 | +0.0 (+0.0,+0.0) | +16.9 (+15.4,+18.6) | -3.6 (-4.6,-2.6) | -0.9 (-2.5,+0.4) | +0.3 (-0.8,+1.5) | +0.2 (-1.0,+1.5) | -2.3 (-3.7,-0.8) | +0.9 (-0.1,+1.8) |
| 30 | 6,877 | 1,172,209 | 3,810 | +0.0 (+0.0,+0.0) | +18.2 (+16.7,+19.7) | -2.4 (-3.5,-1.3) | -1.0 (-2.3,+0.3) | +0.3 (-0.6,+1.3) | +1.1 (+0.1,+2.1) | -2.1 (-3.5,-0.8) | +1.0 (-0.1,+2.1) |
| 40 | 6,626 | 1,172,209 | 4,091 | +0.0 (+0.0,+0.0) | +18.9 (+17.2,+20.7) | -2.7 (-3.6,-1.8) | -1.6 (-2.9,-0.4) | -0.4 (-1.3,+0.5) | +1.4 (+0.5,+2.5) | -1.8 (-3.2,-0.5) | +1.0 (-0.0,+2.0) |
| 60 | 6,437 | 1,172,209 | 4,437 | +0.0 (+0.0,+0.0) | +17.3 (+15.5,+18.7) | -2.5 (-3.4,-1.7) | -0.8 (-2.1,+0.5) | +0.5 (-0.4,+1.3) | +0.3 (-0.8,+1.5) | -1.5 (-3.0,-0.0) | -0.0 (-1.0,+1.0) |

**main · FIT, constant cohort** — the SAME events at every lead (an event enters only if it is U1-eligible at all 11 grid leads), so the curve's shape cannot be a composition change. Printed for the 6 eligible footprints only; see the scope note above for why the DD / depth / duration families are absent.

| lead ℓ | eligible cases (constant cohort) | eligible controls (cohort) | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|
| 1 | 3,874 | 1,172,209 | -3.3 (-4.6,-2.0) | +6.9 (+5.1,+8.5) | +2.1 (+0.5,+3.6) | +0.7 (-0.9,+2.1) | -6.8 (-8.6,-5.1) | +15.3 (+13.6,+17.0) |
| 2 | 3,874 | 1,172,209 | -2.0 (-3.3,-0.8) | +6.2 (+4.5,+8.0) | +2.0 (+0.6,+3.4) | +0.8 (-0.5,+2.3) | -5.9 (-7.6,-4.2) | +8.9 (+7.2,+10.6) |
| 3 | 3,874 | 1,172,209 | -2.0 (-3.1,-0.9) | +6.2 (+4.4,+8.1) | +2.3 (+0.9,+3.6) | +0.3 (-1.3,+1.8) | -6.2 (-8.0,-4.6) | +7.1 (+5.7,+8.5) |
| 5 | 3,874 | 1,172,209 | -1.0 (-1.9,-0.0) | +6.4 (+4.4,+8.3) | +2.5 (+1.1,+4.0) | +0.5 (-1.1,+2.1) | -4.4 (-6.2,-2.7) | +4.5 (+3.4,+5.9) |
| 7 | 3,874 | 1,172,209 | -0.9 (-2.1,+0.1) | +5.4 (+3.7,+7.2) | +2.0 (+0.7,+3.4) | +0.6 (-0.9,+2.2) | -3.4 (-5.0,-1.6) | +5.1 (+3.6,+6.6) |
| 10 | 3,874 | 1,172,209 | -0.6 (-1.8,+0.5) | +5.5 (+3.7,+7.2) | +2.2 (+1.1,+3.2) | +1.2 (-0.1,+2.6) | -2.3 (-3.8,-0.6) | +3.8 (+2.2,+5.2) |
| 15 | 3,874 | 1,172,209 | -0.2 (-1.1,+0.7) | +4.0 (+2.2,+5.9) | +2.0 (+0.8,+3.2) | +0.6 (-0.8,+2.0) | -0.5 (-2.2,+1.2) | +3.7 (+2.5,+4.9) |
| 20 | 3,874 | 1,172,209 | +0.0 (-0.8,+0.8) | +3.0 (+1.0,+5.0) | +2.4 (+1.0,+3.8) | +0.4 (-1.3,+1.8) | +0.1 (-1.6,+2.0) | +2.3 (+1.1,+3.3) |
| 30 | 3,874 | 1,172,209 | +1.1 (+0.2,+2.2) | +0.8 (-0.9,+2.2) | +2.0 (+0.9,+3.2) | +1.1 (-0.3,+2.7) | +0.5 (-1.0,+2.1) | +1.7 (+0.2,+3.2) |
| 40 | 3,874 | 1,172,209 | +0.1 (-0.9,+1.0) | -0.0 (-1.8,+2.0) | +0.7 (-0.5,+1.9) | +1.8 (+0.5,+3.2) | +1.0 (-0.7,+2.8) | +1.8 (+0.6,+3.0) |
| 60 | 3,874 | 1,172,209 | -0.8 (-1.7,+0.1) | -0.4 (-1.7,+1.0) | +0.2 (-0.7,+1.2) | +0.4 (-0.9,+1.8) | -0.2 (-2.0,+1.7) | -0.1 (-1.4,+1.3) |

**main · HOLDOUT** — excess prevalence of the footprint among case anchors vs matched quiet controls, pp, with a session-block 95% CI.

| lead ℓ | eligible cases (cohort) | eligible controls (cohort) | excluded | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2,437 | 198,818 | 2 | +0.0 (+0.0,+0.0) | +17.2 (+12.0,+21.4) | -14.1 (-18.9,-10.1) | +0.7 (-2.7,+4.1) | +0.7 (-1.7,+3.7) | +0.7 (-1.0,+2.6) | -5.8 (-8.8,-3.2) | +11.1 (+9.2,+12.9) |
| 2 | 2,352 | 198,818 | 92 | +0.0 (+0.0,+0.0) | +20.0 (+14.5,+24.5) | -11.0 (-15.9,-7.3) | +0.9 (-2.7,+4.4) | +0.9 (-2.1,+3.9) | +1.0 (-0.2,+2.2) | -4.3 (-6.9,-1.6) | +7.5 (+5.2,+10.2) |
| 3 | 2,295 | 198,818 | 150 | +0.0 (+0.0,+0.0) | +21.3 (+15.1,+27.1) | -10.9 (-16.3,-7.2) | +0.4 (-2.7,+3.7) | +0.8 (-1.8,+4.1) | +1.3 (-0.3,+2.8) | -4.4 (-7.8,-1.2) | +5.6 (+3.5,+7.7) |
| 5 | 2,203 | 198,818 | 252 | +0.0 (+0.0,+0.0) | +21.4 (+14.7,+28.1) | -8.9 (-13.5,-5.5) | -0.4 (-4.4,+3.2) | +0.6 (-1.6,+3.6) | +0.8 (-1.3,+2.7) | -4.0 (-7.4,-0.6) | +5.6 (+3.0,+8.3) |
| 7 | 2,140 | 198,818 | 327 | +0.0 (+0.0,+0.0) | +22.3 (+16.2,+29.7) | -8.1 (-12.2,-5.3) | -0.7 (-4.8,+3.1) | +0.9 (-1.2,+3.1) | +1.9 (-0.1,+3.8) | -4.0 (-7.7,-0.4) | +1.3 (-1.4,+4.1) |
| 10 | 2,049 | 198,818 | 425 | +0.0 (+0.0,+0.0) | +21.5 (+15.2,+28.0) | -8.3 (-12.6,-5.2) | -1.5 (-4.8,+1.8) | +0.3 (-1.2,+1.8) | +2.5 (-0.4,+4.8) | -3.3 (-6.8,+0.1) | +2.7 (+1.1,+4.2) |
| 15 | 1,917 | 198,818 | 574 | +0.0 (+0.0,+0.0) | +22.3 (+15.7,+29.8) | -6.4 (-10.1,-3.9) | -2.1 (-5.6,+0.9) | +0.1 (-1.6,+2.0) | +2.9 (+0.7,+4.5) | -2.1 (-4.8,+0.6) | +0.9 (-1.8,+3.4) |
| 20 | 1,795 | 198,818 | 721 | +0.0 (+0.0,+0.0) | +22.5 (+14.5,+31.0) | -5.7 (-9.5,-3.1) | -1.7 (-5.4,+1.6) | -0.1 (-1.7,+1.4) | +4.0 (+0.9,+6.9) | -2.8 (-6.7,+1.6) | +0.6 (-1.4,+3.3) |
| 30 | 1,580 | 198,818 | 952 | +0.0 (+0.0,+0.0) | +23.3 (+16.0,+30.2) | -5.5 (-9.2,-3.0) | +0.7 (-2.5,+3.3) | -0.1 (-1.7,+1.9) | +1.2 (-1.0,+3.3) | -3.5 (-6.9,+0.7) | -0.6 (-2.3,+1.4) |
| 40 | 1,554 | 198,818 | 1,005 | +0.0 (+0.0,+0.0) | +23.1 (+15.6,+29.9) | -6.6 (-10.4,-3.8) | -0.6 (-3.4,+1.7) | -0.8 (-2.5,+1.1) | +1.4 (-1.1,+3.8) | -3.0 (-5.5,+0.1) | +0.3 (-2.0,+2.0) |
| 60 | 1,461 | 198,818 | 995 | +0.0 (+0.0,+0.0) | +22.7 (+17.2,+27.5) | -4.9 (-7.6,-2.7) | -1.3 (-5.3,+1.7) | -1.8 (-3.4,-0.6) | +1.2 (-0.7,+2.9) | -0.2 (-2.7,+1.8) | +1.0 (-1.4,+3.0) |

**main · HOLDOUT, constant cohort** — the SAME events at every lead (an event enters only if it is U1-eligible at all 11 grid leads), so the curve's shape cannot be a composition change. Printed for the 6 eligible footprints only; see the scope note above for why the DD / depth / duration families are absent.

| lead ℓ | eligible cases (constant cohort) | eligible controls (cohort) | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|
| 1 | 747 | 198,818 | -10.4 (-15.1,-5.6) | +10.4 (+6.1,+14.5) | +1.1 (-3.2,+6.8) | -0.5 (-1.7,+0.7) | -9.0 (-12.1,-4.5) | +17.3 (+14.5,+20.0) |
| 2 | 747 | 198,818 | -6.3 (-10.3,-3.3) | +11.0 (+6.4,+15.6) | +2.3 (-3.5,+8.8) | -1.3 (-3.8,+0.3) | -7.9 (-10.1,-5.1) | +11.9 (+7.9,+16.4) |
| 3 | 747 | 198,818 | -5.4 (-10.2,-1.1) | +9.5 (+6.4,+13.1) | +1.7 (-2.1,+7.7) | -0.4 (-2.8,+1.3) | -9.1 (-12.5,-4.0) | +8.0 (+5.3,+10.0) |
| 5 | 747 | 198,818 | -3.7 (-7.4,-1.0) | +7.7 (+4.8,+10.4) | +0.8 (-1.7,+4.5) | +1.0 (-2.1,+3.1) | -7.2 (-10.3,-2.2) | +11.0 (+6.7,+15.8) |
| 7 | 747 | 198,818 | -2.1 (-5.0,+0.1) | +9.0 (+4.7,+12.3) | +3.3 (+0.5,+5.9) | +2.3 (-0.3,+4.0) | -7.2 (-12.1,-0.4) | +4.6 (+3.1,+7.1) |
| 10 | 747 | 198,818 | -2.9 (-6.0,-1.1) | +7.4 (+4.1,+10.9) | +2.9 (+0.4,+5.2) | +1.4 (-3.0,+4.2) | -7.1 (-10.6,-1.6) | +4.4 (+2.6,+7.0) |
| 15 | 747 | 198,818 | -2.3 (-5.6,-0.3) | +5.1 (+1.1,+9.7) | +1.6 (-0.1,+4.3) | +2.1 (-0.7,+4.0) | -3.9 (-9.3,+3.1) | +3.5 (+0.8,+5.3) |
| 20 | 747 | 198,818 | -0.3 (-3.5,+2.0) | +4.2 (-1.3,+8.3) | +1.9 (-0.0,+4.8) | +4.1 (+1.2,+6.6) | -3.9 (-9.0,+3.6) | +1.4 (-1.3,+3.4) |
| 30 | 747 | 198,818 | +1.3 (-1.5,+4.1) | +3.7 (-2.4,+7.6) | +1.8 (-0.6,+5.1) | +1.4 (-0.4,+5.3) | -3.7 (-7.7,+3.1) | -0.1 (-1.7,+1.9) |
| 40 | 747 | 198,818 | -0.4 (-3.2,+2.0) | -1.1 (-7.7,+2.6) | -1.4 (-3.5,+0.8) | +2.4 (-1.5,+5.2) | -1.7 (-6.0,+4.9) | +0.4 (-2.0,+2.5) |
| 60 | 747 | 198,818 | -1.8 (-4.8,+0.1) | +0.8 (-5.5,+4.7) | -1.3 (-3.2,+0.2) | +2.3 (+0.0,+5.2) | +0.9 (-1.6,+3.9) | +1.1 (-3.4,+3.9) |

**chinext20 · FIT** — excess prevalence of the footprint among case anchors vs matched quiet controls, pp, with a session-block 95% CI.

| lead ℓ | eligible cases (cohort) | eligible controls (cohort) | excluded | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 228 | 136,813 | 0 | +0.0 (+0.0,+0.0) | +3.9 (-3.5,+11.2) | -9.8 (-14.7,-5.2) | +5.6 (-0.1,+11.9) | +4.2 (-0.1,+9.0) | -0.6 (-8.2,+7.2) | -15.5 (-20.9,-9.8) | +13.1 (+4.4,+21.5) |
| 2 | 220 | 136,813 | 8 | +0.0 (+0.0,+0.0) | +6.5 (-2.3,+14.2) | -6.2 (-9.9,-2.5) | +7.2 (+0.6,+13.4) | +5.8 (-0.7,+13.5) | -5.7 (-14.8,+3.5) | -10.7 (-17.6,-3.6) | +10.8 (+3.3,+19.2) |
| 3 | 217 | 136,813 | 11 | +0.0 (+0.0,+0.0) | +4.2 (-4.1,+12.0) | -5.4 (-10.2,-0.4) | +6.1 (-1.2,+13.1) | +7.5 (+2.9,+12.6) | -3.7 (-8.1,+1.7) | -13.3 (-25.0,-2.2) | +4.0 (-1.4,+9.9) |
| 5 | 212 | 136,813 | 16 | +0.0 (+0.0,+0.0) | +4.3 (-2.6,+12.2) | -5.6 (-11.7,+0.8) | +9.2 (+5.0,+14.1) | +5.9 (-2.8,+12.8) | -1.9 (-5.9,+1.5) | -11.7 (-23.0,-2.7) | +8.1 (+2.1,+14.8) |
| 7 | 207 | 136,813 | 20 | +0.0 (+0.0,+0.0) | +8.3 (+2.7,+14.5) | -9.5 (-12.6,-7.1) | +6.4 (+2.4,+11.0) | -0.2 (-5.8,+4.7) | -1.9 (-6.9,+3.7) | -8.5 (-17.3,-0.7) | -1.8 (-7.6,+6.1) |
| 10 | 203 | 136,813 | 26 | +0.0 (+0.0,+0.0) | +11.2 (+3.4,+18.3) | -5.1 (-8.3,-2.1) | +1.5 (-4.0,+6.7) | +3.6 (-2.0,+9.0) | -5.2 (-10.5,+1.4) | -9.8 (-15.1,-5.2) | +2.9 (-3.2,+7.3) |
| 15 | 198 | 136,813 | 30 | +0.0 (+0.0,+0.0) | +9.2 (+0.6,+18.4) | -4.5 (-10.8,+1.0) | +0.7 (-3.0,+4.8) | +5.4 (+1.7,+9.7) | -1.4 (-5.0,+2.5) | -6.2 (-11.4,-2.3) | +3.3 (-4.7,+9.9) |
| 20 | 193 | 136,813 | 37 | +0.0 (+0.0,+0.0) | +12.0 (+5.5,+19.3) | -4.1 (-8.5,+0.8) | -3.6 (-8.9,+2.0) | -0.5 (-5.3,+4.5) | -3.8 (-11.3,+5.7) | -11.1 (-17.5,-5.7) | +2.0 (-4.4,+9.0) |
| 30 | 178 | 136,813 | 50 | +0.0 (+0.0,+0.0) | +12.8 (+2.6,+21.8) | +1.2 (-3.9,+6.3) | -7.4 (-12.6,-3.5) | +1.1 (-3.4,+6.7) | -3.6 (-12.8,+5.4) | -6.0 (-10.3,-2.2) | -2.5 (-6.8,+2.3) |
| 40 | 176 | 136,813 | 51 | +0.0 (+0.0,+0.0) | +19.4 (+13.4,+24.9) | -1.9 (-6.7,+2.6) | -2.9 (-14.2,+9.1) | +2.8 (-1.3,+9.2) | -2.8 (-9.8,+4.5) | -4.8 (-10.8,+1.9) | +1.5 (-2.1,+6.3) |
| 60 | 194 | 136,813 | 52 | +0.0 (+0.0,+0.0) | +15.4 (+8.3,+23.3) | -2.7 (-7.2,+1.9) | +3.7 (-5.5,+13.0) | -0.9 (-6.5,+3.8) | +0.3 (-9.2,+10.2) | +0.0 (-7.8,+6.7) | -2.3 (-6.5,+3.0) |

**chinext20 · FIT, constant cohort** — the SAME events at every lead (an event enters only if it is U1-eligible at all 11 grid leads), so the curve's shape cannot be a composition change. Printed for the 6 eligible footprints only; see the scope note above for why the DD / depth / duration families are absent.

| lead ℓ | eligible cases (constant cohort) | eligible controls (cohort) | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|
| 1 | 132 | 136,813 | -4.4 (-9.5,-0.2) | +12.7 (+6.4,+17.0) | +2.3 (-2.1,+8.1) | -0.3 (-6.9,+7.5) | -13.3 (-20.4,-6.1) | +16.4 (+6.7,+25.0) |
| 2 | 132 | 136,813 | -2.2 (-6.0,+2.2) | +13.0 (+8.9,+16.5) | +5.4 (-0.7,+10.5) | -6.2 (-18.0,+5.7) | -7.9 (-14.9,-1.0) | +11.5 (+3.7,+22.7) |
| 3 | 132 | 136,813 | -0.2 (-4.7,+5.4) | +12.1 (+4.2,+22.1) | +4.6 (-4.7,+14.4) | -3.7 (-15.8,+10.8) | -11.7 (-20.0,-3.2) | +4.4 (-5.0,+15.9) |
| 5 | 132 | 136,813 | -3.6 (-10.2,+0.6) | +13.8 (+8.4,+20.1) | +6.5 (-1.0,+16.8) | -0.1 (-8.2,+7.8) | -10.2 (-19.1,-0.1) | +10.3 (+4.2,+15.3) |
| 7 | 132 | 136,813 | -7.7 (-12.0,-4.4) | +14.0 (+3.2,+20.9) | +0.5 (-6.7,+7.1) | +1.4 (-5.8,+8.7) | -9.9 (-18.6,-1.0) | +2.9 (-1.2,+6.8) |
| 10 | 132 | 136,813 | -2.4 (-5.1,+0.3) | +9.6 (+1.2,+19.1) | +6.4 (-1.0,+12.9) | -6.5 (-23.2,+8.7) | -8.5 (-15.5,-0.8) | -2.8 (-5.5,+0.2) |
| 15 | 132 | 136,813 | -2.9 (-13.0,+4.5) | +7.9 (+1.4,+16.5) | +6.6 (+1.3,+12.8) | -2.1 (-15.3,+8.2) | -3.9 (-12.4,+2.7) | +0.6 (-11.1,+6.9) |
| 20 | 132 | 136,813 | -1.3 (-5.2,+2.6) | -0.7 (-11.0,+10.1) | +0.4 (-5.3,+6.1) | -8.5 (-11.8,+1.1) | -9.7 (-19.1,-2.7) | +5.2 (-0.5,+11.0) |
| 30 | 132 | 136,813 | +4.6 (+1.7,+8.6) | -0.8 (-10.0,+10.5) | +2.8 (-2.9,+10.3) | -2.7 (-9.3,+5.2) | -5.6 (-13.9,+1.7) | -1.1 (-6.7,+5.5) |
| 40 | 132 | 136,813 | -1.0 (-8.0,+4.5) | +0.9 (-4.9,+7.3) | +5.0 (+2.8,+7.3) | -2.6 (-10.7,+4.7) | -0.4 (-10.0,+9.2) | +3.8 (-5.5,+16.2) |
| 60 | 132 | 136,813 | +1.8 (-1.1,+5.6) | +6.9 (+1.7,+10.1) | +0.5 (-2.7,+4.2) | -3.4 (-11.4,+8.2) | +1.8 (-3.1,+5.6) | -3.1 (-10.4,+3.8) |

**chinext20 · HOLDOUT** — excess prevalence of the footprint among case anchors vs matched quiet controls, pp, with a session-block 95% CI.

| lead ℓ | eligible cases (cohort) | eligible controls (cohort) | excluded | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 296 | 101,642 | 0 | +0.0 (+0.0,+0.0) | +8.1 (+2.6,+16.3) | -9.8 (-15.3,-3.4) | +6.3 (+2.8,+11.9) | +4.7 (+1.0,+10.5) | +0.4 (-1.5,+2.6) | -4.5 (-11.8,+1.1) | +14.9 (+9.7,+22.3) |
| 2 | 287 | 101,642 | 10 | +0.0 (+0.0,+0.0) | +14.6 (+6.6,+21.4) | -8.5 (-15.3,-3.6) | +3.0 (-1.2,+7.8) | +1.3 (-4.7,+7.0) | +5.3 (+0.5,+9.5) | -3.5 (-11.2,+1.7) | +10.0 (+2.6,+16.2) |
| 3 | 284 | 101,642 | 13 | +0.0 (+0.0,+0.0) | +16.5 (+6.9,+23.4) | -7.4 (-14.5,-0.3) | +5.0 (+2.7,+7.3) | +5.1 (+1.3,+9.0) | +5.3 (+2.0,+7.4) | -0.4 (-5.7,+5.0) | +7.2 (+1.6,+12.8) |
| 5 | 278 | 101,642 | 19 | +0.0 (+0.0,+0.0) | +20.0 (+10.7,+27.4) | -6.5 (-10.7,-1.4) | +4.3 (-3.7,+11.1) | +5.2 (+0.5,+9.1) | +1.0 (-0.8,+3.7) | +0.2 (-4.2,+5.9) | +3.0 (-5.7,+11.0) |
| 7 | 274 | 101,642 | 24 | +0.0 (+0.0,+0.0) | +21.5 (+14.1,+28.5) | -6.9 (-11.4,-3.6) | +5.8 (+3.8,+8.7) | +4.7 (+2.3,+6.7) | +0.7 (-0.2,+2.2) | -1.9 (-8.1,+2.8) | +1.0 (-4.3,+4.5) |
| 10 | 274 | 101,642 | 25 | +0.0 (+0.0,+0.0) | +22.8 (+15.8,+28.0) | -5.0 (-10.6,-0.2) | +2.3 (-1.9,+5.2) | +3.1 (-1.9,+6.5) | +0.5 (-2.4,+2.4) | -1.4 (-8.6,+5.2) | +14.4 (+8.2,+20.4) |
| 15 | 264 | 101,642 | 37 | +0.0 (+0.0,+0.0) | +20.7 (+11.4,+27.2) | -5.4 (-11.7,-0.4) | -2.5 (-6.8,+0.3) | +0.9 (-1.5,+2.4) | +1.6 (-1.4,+6.9) | +0.3 (-5.0,+4.2) | +7.2 (+4.6,+9.7) |
| 20 | 259 | 101,642 | 46 | +0.0 (+0.0,+0.0) | +23.6 (+20.0,+26.4) | -2.8 (-7.9,+2.8) | -0.8 (-6.8,+4.0) | +1.9 (-2.4,+4.6) | -1.1 (-2.7,+1.3) | +1.2 (-4.3,+5.5) | +3.5 (-1.1,+7.1) |
| 30 | 254 | 101,642 | 54 | +0.0 (+0.0,+0.0) | +19.3 (+13.9,+23.2) | -3.9 (-6.6,-1.8) | +0.2 (-7.2,+5.3) | -0.2 (-6.0,+7.5) | +1.1 (-1.7,+5.5) | -1.9 (-6.9,+2.1) | +0.2 (-4.9,+6.9) |
| 40 | 253 | 101,642 | 59 | +0.0 (+0.0,+0.0) | +20.0 (+14.0,+24.2) | -4.2 (-8.0,-1.3) | +5.4 (+0.8,+9.2) | +1.8 (-2.8,+6.5) | +6.9 (-4.3,+14.0) | -1.9 (-7.2,+3.0) | -4.2 (-9.0,-0.0) |
| 60 | 221 | 101,642 | 78 | +0.0 (+0.0,+0.0) | +20.5 (+10.1,+26.7) | -5.7 (-14.4,-0.3) | +6.1 (+1.7,+13.5) | +3.0 (-1.4,+8.8) | +2.2 (-2.7,+5.7) | -4.4 (-10.4,-0.7) | +2.8 (-1.7,+9.8) |

**chinext20 · HOLDOUT, constant cohort** — the SAME events at every lead (an event enters only if it is U1-eligible at all 11 grid leads), so the curve's shape cannot be a composition change. Printed for the 6 eligible footprints only; see the scope note above for why the DD / depth / duration families are absent.

| lead ℓ | eligible cases (constant cohort) | eligible controls (cohort) | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|
| 1 | 162 | 101,642 | -9.7 (-14.2,-1.7) | +11.6 (+6.8,+21.6) | +5.9 (-1.5,+16.6) | -0.4 (-1.1,+0.6) | -5.4 (-10.9,+4.1) | +16.4 (+9.5,+27.5) |
| 2 | 162 | 101,642 | -5.3 (-14.0,-0.3) | +6.2 (+2.7,+12.5) | +1.8 (-5.7,+11.9) | +5.0 (-6.7,+13.3) | -4.3 (-8.7,+3.3) | +15.0 (+10.7,+22.1) |
| 3 | 162 | 101,642 | -4.8 (-8.7,-2.8) | +8.7 (+7.1,+12.9) | +8.0 (+4.1,+12.6) | +4.5 (-1.9,+9.3) | -0.9 (-8.9,+9.6) | +8.1 (+5.6,+11.6) |
| 5 | 162 | 101,642 | -4.8 (-7.5,-0.4) | +9.5 (+1.7,+16.7) | +8.1 (-3.7,+17.6) | -1.7 (-2.6,-0.2) | +0.3 (-6.7,+13.2) | +8.4 (+0.5,+13.2) |
| 7 | 162 | 101,642 | -6.4 (-12.4,-3.2) | +9.4 (+6.2,+17.2) | +6.6 (-0.0,+14.1) | -1.6 (-5.6,+1.1) | -3.3 (-10.1,+7.5) | +2.2 (-9.7,+7.5) |
| 10 | 162 | 101,642 | -3.2 (-8.9,-0.7) | +5.3 (-3.0,+8.8) | +4.0 (-7.7,+9.2) | +1.0 (+0.0,+2.7) | -1.5 (-7.6,+5.4) | +14.8 (+12.5,+17.5) |
| 15 | 162 | 101,642 | -2.6 (-7.1,+0.3) | +2.0 (-5.0,+5.0) | +0.1 (-4.4,+2.0) | -0.6 (-2.3,+3.1) | +2.5 (-4.5,+7.5) | +8.0 (+6.3,+10.0) |
| 20 | 162 | 101,642 | -0.2 (-1.0,+2.4) | +2.1 (-8.5,+11.0) | +3.2 (-5.0,+9.0) | -1.6 (-5.1,-0.2) | -1.9 (-10.1,+5.2) | +6.1 (-0.5,+9.3) |
| 30 | 162 | 101,642 | -0.7 (-5.6,+3.4) | +1.8 (-5.6,+7.3) | -1.2 (-5.9,+6.8) | -2.5 (-5.3,+0.7) | -0.1 (-9.4,+4.8) | -3.4 (-8.5,+2.2) |
| 40 | 162 | 101,642 | -3.1 (-10.6,+1.8) | +5.3 (-8.6,+12.2) | +3.1 (-1.0,+7.1) | +11.1 (+0.0,+18.1) | +0.3 (-3.8,+7.6) | -3.8 (-10.9,+0.0) |
| 60 | 162 | 101,642 | -1.4 (-5.2,+2.7) | +3.9 (-1.5,+16.1) | -0.6 (-3.8,+7.0) | +4.5 (+0.0,+6.7) | -3.1 (-6.1,+3.1) | +0.3 (-2.5,+6.6) |

`eligibility_per_lead` is the GLOBAL series over the whole cohort. `eligibility_per_lead_by_board_split` is the same accounting re-scoped to each (board, split) cohort, and it is what the curve tables print. EXCLUSIONS are keyed on the EVENT's own board and split — an excluded event either has no anchor bar at that lead, or has one that is not U1-eligible and may therefore carry no split assignment at all, so the event's own split is the only defined key. CASE ANCHOR counts are keyed on the ANCHOR's own split (reading note R3), which is the set the curves actually use. The two keys disagree only for an anchor that crosses a split boundary, so a cohort's rows are not required to sum exactly to its event count.

**Reading these curves (descriptive — no gate, no statistic, `main · FIT`).** DD35 is flat-to-RISING with lead **inside** the pre-break window: +13.5 pp at ℓ = 1 against +16.9 pp at ℓ = 20. That is the shape of a **persistent state**, not of a precursor turning on before ignition — the same multi-year persistence §6 measures defeating the placebo shift, seen from the other side. (Read on its own, the structural window sits at the same level — +18.2 pp at ℓ = 30, +17.3 pp at ℓ = 60 — but that is a level, **not** a continuation of the series above: the ℓ = 21 composition break forbids reading across it.) MA200 runs the other way, and entirely inside the same window: its deficit DEEPENS toward ignition (-3.6 pp at ℓ = 20 → -8.2 pp at ℓ = 1), so the reclaim is the fast leg — and the constant-cohort curve, whose composition cannot change with lead at all, moves the same way (+0.0 → -3.3 pp). VZ spikes only at ℓ ≤ 2 (+10.4 pp at ℓ = 1, +5.6 at ℓ = 2, +3.9 at ℓ = 3) — coincident, exactly as its stamp says. **No reading here compares across the ℓ = 21 boundary**; the mechanical composition break above forbids it, and none of these three statements needs it.

## 9. Flagged-set diagnostics (descriptive — explicitly not a ranker)

| board | split | footprint | universe | pos episodes | flag rate | precision P(fb₁₀|F) | capture P(F|fb₁₀) | flagged/session med [IQR] |
|---|---|---|---|---|---|---|---|---|
| main | FIT | DD20 | U0 | 15782 | 66.638% | 5.703% | 65.403% | 544 [395,645] |
| main | HOLDOUT | DD20 | U0 | 4385 | 54.89% | 7.685% | 59.822% | 551 [393,672] |
| main | FIT | DD35 | U1 | 11221 | 45.467% | 7.233% | 57.661% | 215 [123,316] |
| main | HOLDOUT | DD35 | U1 | 2960 | 30.702% | 11.042% | 44.112% | 110 [60,267] |
| main | FIT | MA200 | U1 | 11221 | 80.709% | 5.16% | 73.016% | 427 [299,543] |
| main | HOLDOUT | MA200 | U1 | 2960 | 74.183% | 6.767% | 65.318% | 366 [224,550] |
| main | FIT | CONF | U1 | 11221 | 58.048% | 5.395% | 54.914% | 296 [200,396] |
| main | HOLDOUT | CONF | U1 | 2960 | 53.618% | 7.685% | 53.616% | 276 [198,363] |
| main | FIT | CB | U1 | 11221 | 11.59% | 5.489% | 11.155% | 39 [13,87] |
| main | HOLDOUT | CB | U1 | 2960 | 11.135% | 8.154% | 11.814% | 42 [21,92] |
| main | FIT | SECT | U1 | 10450 | 38.049% | 6.563% | 43.882% | 49 [0,340] |
| main | HOLDOUT | SECT | U1 | 2698 | 24.852% | 10.282% | 33.759% | 0 [0,152] |
| main | FIT | QB | U1 | 11164 | 48.355% | 4.477% | 38.024% | 230 [120,372] |
| main | HOLDOUT | QB | U1 | 2959 | 41.47% | 6.598% | 35.593% | 214 [114,338] |
| main | FIT | VZ | U1 | 11208 | 15.43% | 7.25% | 19.622% | 62 [34,101] |
| main | HOLDOUT | VZ | U1 | 2960 | 16.014% | 11.693% | 24.366% | 64 [38,99] |
| chinext20 | FIT | DD20 | U0 | 381 | 77.004% | 1.566% | 64.473% | 193 [158,224] |
| chinext20 | HOLDOUT | DD20 | U0 | 561 | 72.125% | 2.864% | 65.606% | 222 [175,261] |
| chinext20 | FIT | DD35 | U1 | 291 | 56.339% | 1.589% | 57.137% | 105 [74,142] |
| chinext20 | HOLDOUT | DD35 | U1 | 423 | 45.594% | 3.624% | 57.698% | 76 [41,162] |
| chinext20 | FIT | MA200 | U1 | 291 | 72.633% | 1.259% | 58.365% | 142 [96,178] |
| chinext20 | HOLDOUT | MA200 | U1 | 423 | 63.005% | 2.817% | 61.979% | 120 [63,217] |
| chinext20 | FIT | CONF | U1 | 291 | 58.69% | 1.693% | 63.448% | 105 [75,137] |
| chinext20 | HOLDOUT | CONF | U1 | 423 | 52.185% | 3.309% | 60.306% | 101 [76,144] |
| chinext20 | FIT | CB | U1 | 291 | 12.042% | 1.961% | 15.078% | 16 [10,27] |
| chinext20 | HOLDOUT | CB | U1 | 423 | 10.973% | 3.84% | 14.715% | 14 [6,32] |
| chinext20 | FIT | SECT | U1 | 265 | 39.941% | 1.533% | 39.664% | 41 [0,124] |
| chinext20 | HOLDOUT | SECT | U1 | 384 | 29.682% | 4.212% | 44.441% | 0 [0,111] |
| chinext20 | FIT | QB | U1 | 287 | 48.343% | 1.041% | 32.316% | 89 [63,119] |
| chinext20 | HOLDOUT | QB | U1 | 421 | 38.224% | 2.733% | 36.361% | 80 [37,126] |
| chinext20 | FIT | VZ | U1 | 291 | 15.906% | 2.219% | 22.533% | 25 [16,37] |
| chinext20 | HOLDOUT | VZ | U1 | 423 | 16.349% | 5.229% | 29.855% | 27 [16,42] |

DESCRIPTIVE ONLY — no threshold tuned, nothing combined or ranked, no per-name selection (DNR:KILL-OUTCOME-AUDITION respected). None of these numbers is a strategy result and none may be quoted as one.

## 10. Amendments and reading notes

**A1 — `se_row` is computed as the EXACT closed-form standard deviation of the fixed-design row bootstrap instead of simulating N_BOOT_ROW = 2000 draws. N_BOOT_ROW is still used — by the verification control that validates the closed form.**

*Why:* On the frozen sufficient-statistic table the row bootstrap draws k_F1(z) ~ Bin(n_F1(z), p1(z)) and k_F0(z) ~ Bin(n_F0(z), p0(z)) independently across strata, so the standardised excess is a linear combination of independent binomials and its bootstrap variance is available in closed form with ZERO Monte Carlo error. Simulating it instead costs 2 x n_strata x 2000 variates per cell — measured at 11.4 s for a single M1 main cell, i.e. over an hour across the primary and placebo batteries — which is precisely the whole-matrix cost prereg sec.12 forbids.

*Risk controlled by:* `verify.se_row_closed_form_matches_simulation` runs the literal 2000-draw simulation on sampled cells and requires agreement inside 5% (the Monte Carlo error of a 2000-draw SE is itself ~1.6%); its probe inflates the closed form by 50% and must be detected.

**A2 — The diagnostic within-stratum permutation is computed for the PRIMARY horizon (H=10) FIT cells on verdict-eligible boards, in both arms — not for every cell in the receipt.**

*Why:* prereg sec.6.2 says 'where computed' and stamps the permutation as DIAGNOSTIC ONLY that NEVER gates. A fixed-margin hypergeometric draw over M1's stratum count costs ~5.4 s per cell; spending it on cells no gate reads buys nothing and would push the run past its budget.

*Risk controlled by:* the permutation gates nothing by construction, the scope is printed on every table that carries one, and `verify.permutation_recomputes_exp` still runs against a real computed cell.

**A3 — The three cluster bootstraps are computed only for cells whose BOARD passes the frozen G1 board floor; boards that fail it are DESCRIPTIVE_ONLY and carry point estimates, honest-N and retention diagnostics but no SE.**

*Why:* A DESCRIPTIVE_ONLY board can receive no verdict under prereg sec.8, so its z-statistic is unreadable by any gate. The floor is a FROZEN, pre-registered rule and skipping inference behind it is not a post-hoc selection.

*Risk controlled by:* the floor result is printed for every board x horizon x arm including the ones it excludes, with the episode counts that decided it, so the exclusion is auditable rather than silent.

**A4 — receipt-presentation repairs adjudicated by the round-2 adversarial review; no verdict, gate or estimator changed**

- **Per-cell placebo visibility (sec.5, sec.6).** The verdict tables gained `placebo max|excess| pp` and `placebo max|z|` — the maximum over the three sec.6.3 shifts for that exact cell — and sec.6 now prints every rejection individually (shift, footprint, arm, excess, z) instead of only the per-family count. The family rate was the only placebo number a reader could see, so a family-level FAILED could not be read down to the cells that caused it.
- **Mechanism evidence for the calibration failure (sec.6).** The measured signature of the 26 rejections is printed and read, so the failure is bounded rather than left as an unexplained machine fault.
- **Headline fairness (sec.5).** The section now states how many gated cells cleared G1-G5 and that every one was downgraded by the frozen sec.6.3 consequence, BEFORE it states that no DISCRIMINATOR stands, and records that sec.14's disposition precondition did not obtain on `main`.
- **The SUGGESTIVE bar inherits the miscalibration (sec.6, sec.12).** Stated explicitly: inside a family that failed calibration at the G2 bar, the |z| >= 1.96 bar is at least as uncalibrated.
- **Lead-curve exclusions re-scoped (sec.8).** The per-lead exclusion counts are computed inside each (board, split) cohort. The identical global series had been printed under all four tables, whose case and control sets are already per (board, split).
- **Constant-cohort curves printed (sec.8).** They existed only in the JSON; the six eligible footprints now carry a printed constant-cohort table beneath each board x split full-cohort table. The DD-family absence statement is unchanged.
- **Matched-N honesty in the lead curves (sec.8).** The `cases` / `controls` columns were DD20's numbers standing in for every footprint; they are relabelled `eligible cases (cohort)` / `eligible controls (cohort)`, computed for the cohort itself, with the per-footprint matched N named in the JSON and one worked example of the gap printed.
- **R4's scope named (sec.10).** The reading note now names the exactly two cells its convention moves, the direction of the move, and their H=5 fragility.
- **Placebo subsample shrinkage disclosed (sec.6).** The shifted panel loses rows as S grows (a name shorter than S vanishes); the series is printed and its direction stated.
- **Per-F-class censoring asymmetry printed (sec.2).** The counts were in the JSON only; the widest imbalances are now printed with the JSON pointer kept.
- **The sec.2 censoring-magnitude sentence corrected.** 'The values above are of order several per cent' described neither the cells under the 1% trigger nor the spread of the ones over it; the measured distribution replaces it.
- **Survivorship stamp attributed (footer).** The kept-name count for THIS run is printed, and W-P0's percentages are attributed to W-P0's own store snapshot rather than reading as this run's N.
- **Two-speed READING paragraph (sec.8).** A descriptive reading of the printed curves — it gates nothing, adds no statistic, and does not cross the lead-21 composition break.

*Why:* The round-2 adversarial review found the receipt under-reporting its own evidence rather than mis-computing it: per-cell placebo behaviour was aggregated away behind four family rates, the null was stated in an order that read as absence of structure, three bookkeeping series were printed at the wrong scope or under the wrong label, and several quantities that existed in the JSON were never surfaced. Each item is a presentation or bookkeeping repair to what the receipt SAYS about numbers it already computed.

*Risk controlled by:* nothing in the statistical machinery is touched: no stratum, gate, floor, SE, placebo draw or verdict rule moved, the frozen sec.6.3 consequence sentence is printed verbatim and applied as frozen, and the corrected counts are the ones this amendment names. The run is byte-deterministic, so the whole pass is auditable as a diff against the pre-A4 build in which every verdict, gate glyph, excess, z, Holm p and honest-N is identical. (The `A4 GUARD` string in the instrument's provenance check is prereg sec.11.16's own A4/A5 label and is unrelated to this amendment.)

Reading notes record where the prereg admitted more than one reading; each names its materiality so the choice is adjudicable rather than silent.

**R1** — prereg sec.4 freezes the reported gradient families at FOUR (`below_band`, `dur_band`, `sect35_band`, `volz_band`), while sec.5.3 names 'the depth gradient and the duration gradient' when stating the DD/duration ONE-SERIES carve-out.

*Reading taken:* sec.4's explicit enumeration governs what is REPORTED; sec.5.3 is a rule about which strata a family may be evaluated inside, and it applies to whatever is reported. `dur_band` is the DD/duration-family gradient and therefore drops BOTH M1 dd factors. The sec.5.3-named DEPTH gradient (`dd_band`) is computed with the same carve-out and emitted to the JSON under `depth_gradient_reference` so the numbers exist, but it is absent from every MD gradient table because sec.4 froze the reported list at four. *Materiality:* NIL for every verdict — gradients receive no verdicts under sec.5.5 and are excluded from the constant-cohort curve under sec.9 either way. Flagged here so the reading is adjudicable rather than silent.

**R2** — prereg sec.4 lists the MA200 measurability mask as `isfinite(ma200)`, but W-P0 keeps `under_ma` and does not export `ma200`.

*Reading taken:* The mask is implemented as U-eligibility and the covering implication is MEASURED, not assumed: ma200 rides min_periods = 150 and dd250 rides min_periods = 200 on the SAME per-name bar axis, and the raw store carries no non-finite close or high, so dd250-finite implies ma200-finite exactly. `verify.missing_not_false.ma200_covering_lemma` reports the measurement. *Materiality:* NIL — the sec.4 mask is satisfied identically, not approximated.

**R3** — prereg sec.9 does not say which split a lead-curve case anchor belongs to.

*Reading taken:* The ANCHOR's own split. Controls are same-session rows, so cases and controls share a split by construction and the comparison is never across a split boundary. *Materiality:* Stated on the curves themselves.

**R4** — prereg sec.8 defines SUGGESTIVE as 'G1 met, FIT |z| >= 1.96, but fails >= 1 of G3/G4/G5' and NULL as 'G1 met and neither'. A cell with 1.96 <= |z| < 2.81 that passes G3, G4 and G5 fits neither sentence literally: it fails G2, so it is not a DISCRIMINATOR, but it fails none of G3/G4/G5.

*Reading taken:* SUGGESTIVE. The SUGGESTIVE bar in the frozen text is |z| >= 1.96 and this cell clears it; calling it NULL would contradict NULL's own definition ('neither'), since it is not a DISCRIMINATOR and it is above the SUGGESTIVE bar. Implemented as: DISCRIMINATOR iff every gate passes, else SUGGESTIVE iff |z| >= 1.96, else NULL. *Materiality:* Affects only cells in the 1.96-2.81 band that pass all of G3/G4/G5; the gate columns are printed per cell so any such row can be re-read under the other convention.

*Cells this convention actually moves — computed, not asserted:* exactly 2, `H10 · chinext20 · MA200` (FIT z = -2.45 → SUGGESTIVE), `H10 · chinext20 · CONF` (FIT z = 2.64 → SUGGESTIVE). The move is **upward only**: each is SUGGESTIVE under the reading taken and NULL under the literal alternative, and no other cell in the receipt sits in the 1.96–2.81 band with G3, G4 and G5 all passed. They are fragile at the secondary horizon — the same cells at H = 5 print `MA200` z = -1.79 → NULL, `CONF` z = 1.91 → NULL, below the SUGGESTIVE bar and therefore NULL under either reading.

## 11. Verification battery — every check paired with a mutation it must detect

**17/17 prereg §11 checks passed; 17/17 mutation probes detected.** Plus 1 amendment control (1 passed, 1 probe detected).

| check | result | probe | mutation applied |
|---|---|---|---|
| label_identity | PASS | detected | off-by-one the panel-axis re-derivation (distance <= H+1) |
| no_lookahead | PASS | detected | scale a two-year slab INSIDE the pre-cut history instead of the post-cut tail (must move the footprints) |
| stratum_outcome_independence | PASS | detected | leak the permuted label into the stratum key |
| cold_universe | PASS | detected | plant the same board 25 sessions back — OUTSIDE the prior-20 window, where the anchor must stay cold (so the check fails) |
| censoring_partition | PASS | detected | fold censored rows into the analysed set as negatives |
| board_era_disjointness | PASS | detected | inject a pooled ALL_BOARDS row into an output table |
| feature_liveness | PASS | detected | swap one degenerate column for a LIVE one, which must stop printing NOT_EVALUABLE (so the check fails) |
| carveout_applied | PASS | detected | flip the QB carve-out entry so the vol decile is no longer dropped |
| concentration_guard | PASS | detected | duplicate one name's positive rows 40x so it dominates the episode count |
| placebo_sensitivity | PASS | detected | put shift 0 (the planted leak itself) into the calibration set and assert it is calibrated |
| missing_not_false | PASS | detected | re-admit unmeasurable rows into the F=FALSE class |
| control_completeness | PASS | detected | admit controls whose 60-session forward chain is incomplete |
| permutation_recomputes_exp | PASS | detected | hold exp fixed across draws |
| stop_ship_reference_scan | PASS | detected | introduce a withdrawn-artifact reference into a scanned surface |
| detector_vs_zt_pool | PASS | detected | switch off 5% of the detector's board flags |
| provenance | PASS | detected | assert a non-ancestor stamp passes (a real local commit off the build head's ancestry) |
| lead_anchor_position | PASS | detected | off-by-one the lead offset |
| se_row_closed_form_matches_simulation | PASS | detected | inflate the closed form by 50% |

A check that cannot fail is a defect. Every check above is paired with a mutation it MUST detect; `detected: false` anywhere means the check is vacuous and the run is not evidence.

## 12. What this does NOT establish

- WITHIN-SESSION CROSS-SECTIONAL SCOPE, WHICH BOUNDS EVERY VERDICT HERE. All strata are within-session, so each verdict answers only: does this footprint separate names on the SAME tape on the SAME day. A NULL says nothing about market-wide or regime-timing information in the same family — a 'boards cluster when the whole tape is washed out' mechanism is removed by the session stratum by construction. Instrument verdicts are not market verdicts.
- NO PRODUCTION USE, NO RANKER, NO THRESHOLD. Nothing here ranks names, tunes a threshold, sizes, gates, alerts or trades. There is no P-B2 production consumer and none is proposed; the sec.10 flagged-set diagnostics are descriptive and end inside this receipt (DNR:KILL-OUTCOME-AUDITION respected).
- NO CAUSALITY. A matched excess is a statement about two conditional rates inside the same session and volatility stratum. It is not evidence that the footprint produced the board, nor that either would recur.
- NO EXPECTANCY, NO RETURN, NO ENTRY BOOK. The outcome is a BOOLEAN — a first tolerant limit-up close inside H sessions. No price, return, slippage or fill is modelled, and a precision figure is not a strategy result.
- NOT A CONTINUATION OR AN INTRADAY CLAIM. The label is a FIRST board out of a cold state. An intraday touch, a generic big day and a continuation board after a prior board are different physical objects and none of them is the label.
- SURVIVORS ONLY, LARGE-CAP SLICE. W-P0's curated universe: delisted names are absent, so every rate is measured on names that lived. Nothing supports a claim about small caps or the delisted in either direction.
- BACK-ADJUSTED BASIS. A tolerant-detector cohort, not an exchange-exact legal-limit cohort. The residual is MEASURED in verify.detector_vs_zt_pool, not assumed away.
- CURRENT SECTOR MEMBERSHIP applied to 15 years of history — the sector-washout footprint is not a point-in-time statistic and eras are not comparable on it without that qualifier.
- THE PERMUTATION IS NOT A P-VALUE YOU MAY QUOTE. It is stamped anticonservative and gates nothing: one episode contributes ~10 positive anchor rows, so a row-exchangeable null understates the null SD by roughly sqrt(10).
- A NORMAL APPROXIMATION IS DOING WORK. The gates read z on a CGM two-way clustered SE under the normal approximation, stamped as such. The sec.6.3 placebo calibration is the empirical guard on that approximation, and a family that fails it has no DISCRIMINATOR.
- RETAINED SAMPLES ARE NOT THE FULL SAMPLE. Contrast-bearing strata are a non-random, density-biased subset; the retained fractions and their composition are printed on every cell, and a cell retaining under half of its F=TRUE positive episodes is NOT_EVALUABLE rather than a verdict.
- VZ AND CB ARE COINCIDENT INDICATORS, NOT PRECURSORS. Median arming leads of 1 and 5 sessions (P-B sec.5). Any verdict on them carries that stamp and neither is ever described as an early precursor.
- NOTHING ABOUT THE WITHDRAWN EARLIER-WAVE CONSTRUCTIONS. No number and no artifact from them is cited (grep-verified in verify.stop_ship_reference_scan).
- A SUGGESTIVE INSIDE AN UNCALIBRATED FAMILY IS NOT A WEAKER VERDICT. Where a (board, horizon) family failed its sec.6.3 placebo calibration at the G2 bar, the SUGGESTIVE bar (|z| >= 1.96) is a LOWER bar on the same statistic and is therefore at least as uncalibrated. Nothing in this receipt supports reading a SUGGESTIVE in a failed family as a small, safe version of a DISCRIMINATOR.

## 13. Ore ledger — what was deliberately not built

- MARKET-TIMING / REGIME FORMS OF THE SAME FAMILIES. Every stratum here is within-session, so a 'boards cluster when the whole tape is washed out' mechanism is removed BY CONSTRUCTION. That form is untested here and a null here is not evidence against it. It is the single largest reserved question and it needs its own preregistration.
- CONJUNCTIONS. P-D owns stacking; W-P0's S6 conjunction masks are deliberately not re-read here and no pair, triple or grid search of the eight booleans exists.
- DEEPER LAWFUL DATA (P-C). Auction demand, seal-time structure and chip-concentration shifts cannot enter this instrument because the histories do not exist in this checkout.
- LIQUIDITY / SIZE MATCHING. Omitted with reason: on a back-adjusted store, cross-name turnover ranks inherit per-name adjustment factors and are not a lawful liquidity measure. Full-A `daily_basic` is the future fix; the vol-decile stratum is the only wildness control M0 claims.
- THE EXACT LEGAL-LIMIT PLANE. Untouched. This is a tolerant-detector cohort on a back-adjusted store and the reopen chain is unmodified (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT).
- THE CENSORING MECHANISM ITSELF. Broken windows are counted, bounded (Manski) and printed, never modelled. A suspension-aware forward-chain model is reserved.

---

Vintage: base `106f3b22461b`, head `cd3489d77a2a`, raw store `2c39d8afca95`, W-P0 pin `11ac61de71f0f595…`, P-B pin `f42b0566beb60bec…`, prereg `043a85d69f76ea86…`. no wall-clock, runtime or hostname enters either receipt; the artifact date is a frozen constant and every random stream is keyed by a sha256 of its own identity rather than by visit order. Two consecutive TZ=UTC full runs at the same commit are byte-identical.

Survivorship, measured on THIS run: **1,779 names kept of 1,847 files** in `data/china_stocks_raw` — 1 skipped as ST, 67 as thin or unreadable — carrying 4,840,077 live bars over 3,786 sessions. W-P0's stamp follows verbatim; its counts and **every percentage in it were measured by W-P0 on W-P0's OWN store snapshot of 1,842 curated names**, not on this run's 1,779, and are quoted as W-P0 measured them rather than re-derived here. The qualitative claim is what carries across — a large-cap, survivors-only slice — and it carries at either N.

W-P0's stamp: LARGE-CAP SLICE, SURVIVORS ONLY. The 1,842 curated names are 35.37% of active SH/SZ, 0 of 329 BSE, median cached cap 187.7 yi vs 37.85 yi omitted, and 36.09% of canonicalised zt-pool names. Delisted names are absent, so every rate here is measured on names that lived. NOTHING in this file supports extrapolation to small caps; that remains a sampling-gap prior, never proven alpha.

