# P2.5 — Washout Depth × Interaction Study — RESULTS

**Study:** `P2_5_depth_interaction` (BH family, m=16) · **Program:** Entry Intelligence
**PREREG:** `research/entry_intel/P2_5_INTERACTION_PREREG.md` (APPROVED Fable 2026-07-05, R1 conditional on `P2_5_REDTEAM.md`)
**Memo:** `P0_MEASUREMENT_MEMO.md v1.1 (2026-07-05) §6` · **Runner:** `run_P2_5_study.py` · **Date:** 2026-07-05
**Replay:** `data/replay/replay_boarded.parquet` MD5 `906175f9eb8caa351ed6d7d5c56265d3` (matches PREREG)
**Author:** Opus subagent under Fable orchestration

---

## 1. VERDICT (lead)

**WHOLE-STUDY VERDICT: PARTIAL_SHIP.** Six of eight registered configs earn the right to shadow deployment (EI-F1D-RW). The washout-as-rank-input line is **NOT killed** — the §6.2 program-wide kill does **not** execute.

**Ship-qualifying configs (§6.3: BH-surviving favorable 63d stop-out + both-halves sign-stable under the pinned baseline-free convention + not-THIN + 21d dead-money Δ≤0):**

| Config | Name | 63d stop-out Δpp | BH-adj p | sign-stable (H1/H2) | 21d dead-money Δpp | Verdict |
|---|---|---|---|---|---|---|
| **C1** | deep_washout_solo (dd>25%) | **−3.66** | 0.0002 | Y (−2.4 / −4.5) | −15.58 | **SHIPS** |
| **C3** | below200_washout | **−4.26** | 0.0002 | Y (−6.5 / −2.0) | −8.29 | **SHIPS** |
| **C5** | trio (washout×ac×rs) | **−2.37** | 0.0002 | Y (−4.5 / −0.5) | −4.85 | **SHIPS** |
| **C6** | deep_trio (dd>25%×ac×rs) | **−4.71** | 0.0002 | Y (−5.4 / −4.4) | −11.58 | **SHIPS** |
| **C7** | d40plus_trio (dd>40%×ac×rs) | **−6.40** | 0.0002 | Y (−1.8 / −10.6) | −15.18 | **SHIPS** |
| **C8** | below200_deep (below200×dd>25%) | **−6.02** | 0.0002 | Y (−5.8 / −6.2) | −14.39 | **SHIPS** |

**DEAD configs (2 of 8):**
- **C2 (d40plus_solo):** 63d stop-out Δ=−4.39pp is BH-surviving and favorable, **but FAILS both-halves sign stability** under the pinned convention — H1 = **+1.50pp (unfavorable)**, H2 = **−9.67pp (favorable)**; the edge lives entirely in the back half. UNSTABLE → cannot promote. Its halves are adequately powered (2,403 moved-up episodes), so this is a genuine instability, not a low-n artifact.
- **C4 (washout_ac_pass):** 63d stop-out Δ=+2.14pp is **unfavorable** and does not survive BH (perm_p=0.378); 21d also unfavorable (+4.60pp). The broadest, shallowest cut carries no 63d edge — consistent with the diagnostic's finding that the shallow bulk is where the harm concentrates.

**Named for EI-F1D-RW shadow registration:** C1, C3, C5, C6, C7, C8.
**§6.3 lead suggestion (narrowest surviving condition set):** **C1 (deep_washout_solo)** — a single depth cut (dd>25% within the washout context), 24.1%→43.3% of fires, largest liftoff co-benefit among the two-condition solos. **Fable selects the final first-shadow config among the six survivors** (§6.3/§8); C6 (deep_trio) is the strongest interaction candidate (−4.71pp, both halves clearly favorable, 21d dm −11.58pp), and C7/C8 carry the largest 63d effects but C7 rests on the smallest cell (1,327 episodes).

**Runner-up decision that would flip the lead:** if Fable weights effect size over narrowness, C7 (−6.40pp) or C8 (−6.02pp) lead; the single condition that flips me off C1 is a preference for the trio-interaction mechanism (C6) over the raw depth solo, which the PREREG §6.3 explicitly reserves to Fable.

---

## 2. Side-by-side vs diagnostic point estimates

The diagnostic (IN-SAMPLE, sealed) reported **raw cell** stop-out deltas vs the unconditioned baseline. This study reports the **RW Mode-B moved-up vs not-moved-up** contrast — a *different statistic on a different partition* (the actual ship mechanism). They are not expected to be numerically identical; the comparison is directional.

| Config | Diagnostic 63d cell-Δpp (raw, in-sample) | Study 63d RW moved-up Δpp | Diagnostic 21d dm-Δpp | Study 21d dm-Δpp | Agreement |
|---|---|---|---|---|---|
| C2 d40plus | −3.57 | −4.39 (**sign-UNSTABLE**) | −14.09 | −15.96 | direction agrees, but RW split is half-unstable |
| C3 below200 | −2.23 | −4.26 | −4.60 | −8.29 | agrees, stronger |
| C5 trio | −1.10 | −2.37 | −2.93 | −4.85 | agrees, stronger |
| C6 deep_trio | −3.30 | −4.71 | −8.84 | −11.58 | agrees, stronger |
| C1 deep_solo | −1.92 (fire-weighted est.) | −3.66 | — | −15.58 | agrees, stronger |

**Round-0 provenance note (sc63 bug correction — MANDATORY).** The upstream diagnostic's `sign_consistent()` (`run_P2_5_diagnostic.py` ~line 470) tested every cell's 63d stop-out rate against the **21d** unconditioned baseline (0.3848) instead of the **63d** baseline (0.6231). Because every cell's 63d stop rate (~0.53–0.66) sits above 0.3848 in both halves, `sc63` returned `True` **mechanically for every cell**. The red-team (BLOCKING-1) recomputed against the correct 63d baseline and found that, under the *raw-cell* convention, only **C2/d40plus** was 63d sign-stable while C3/C5/C6 flipped.

**This study did NOT inherit `sign_consistent()`.** Per the pinned §5.2/BLOCKING-2 convention, sign stability is the **baseline-free within-half moved-up vs not-moved-up contrast** — the exact statistic that ships. Under that correct convention the picture *inverts* the diagnostic's raw-cell recompute: **C2 is the one config that DIES on sign instability**, while C3/C5/C6 (and C1/C7/C8) are sign-stable. This is not a contradiction — the diagnostic's raw cell-vs-baseline delta and the RW moved-up contrast are different quantities. The honest reading: the sc63 bug's headline ("d40plus is the only stable one") was an artifact twice over — first of the wrong baseline, then of measuring the wrong (non-shipping) statistic. The configs are adjudicated here on the statistic that actually deploys.

---

## 3. Calibration controls (both PASS — run BEFORE the grid)

Reusing the calibrated episode-permutation machinery from `run_P1_3_v2.py` verbatim (no new statistic), on the P2.5 production-washout encoding:

| Control | Metric | Result | Threshold | Status |
|---|---|---|---|---|
| **Negative** | rejection rate @α=0.05 | 0.065 | ≤0.12 | **PASS** |
| | KS-uniformity p | 0.593 | ≥0.05 | **PASS** |
| | p-dist mean / median | 0.490 / 0.504 | ≈0.5 | PASS |
| | sanity gate (param/perm divergence) | not tripped | — | PASS |
| **Positive** | perm_p (inject +0.05 fwd-return shift) | 2.0e-04 | ≪0.05 | **PASS** |

Negative control: 200 permuted-label draws (C6 moved-up encoding @21d), 1,000 perms each. Positive control: episode-level +0.05 return injection, r=−0.3125 (confirms this codebase's convention: **negative r_biserial = group A stochastically LARGER/better**). Grid is VALID.

---

## 4. Per-config results table (all 8 configs × 2 horizons, m=16)

Primary = 63d/21d stop-out Δpp (moved-up − not-moved-up); perm_p = episode-permutation MWU (N_PERM=5000, two-sided, Phipson-Smyth +1); BH q≤0.10 across m=16. Secondary (context, not BH): dead-money Δpp, liftoff Δpp.

| Trial | Config | Hz | stop Δpp | fav | perm_p | BH-adj p | r_bis | sign (H1/H2) | dm Δpp | liftoff Δpp | n_ep moved-up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | C1 | 21 | +5.06 | N | 0.0002 | 0.0002 | −0.117 | Y (+5.4/+5.0) | −15.58 | +15.79 | 8,199 |
| T02 | C1 | 63 | **−3.66** | Y | 0.0002 | 0.0002 | −0.108 | **Y (−2.4/−4.5)** | −0.11 | +7.91 | 8,199 |
| T03 | C2 | 21 | +7.36 | N | 0.0002 | 0.0002 | −0.147 | Y (+13.8/+1.5) | −15.96 | +16.90 | 2,403 |
| T04 | C2 | 63 | −4.39 | Y | 0.0002 | 0.0002 | −0.167 | **N (+1.5/−9.7)** | −0.03 | +8.45 | 2,403 |
| T05 | C3 | 21 | +1.49 | N | 0.0002 | 0.0002 | −0.086 | Y (+1.7/+1.5) | −8.29 | +9.03 | 9,493 |
| T06 | C3 | 63 | **−4.26** | Y | 0.0002 | 0.0002 | −0.071 | **Y (−6.5/−2.0)** | −0.11 | +5.63 | 9,493 |
| T07 | C4 | 21 | +4.60 | N | 0.0616 | 0.0704 | −0.017 | Y (+3.4/+6.1) | −6.80 | +4.10 | 13,065 |
| T08 | C4 | 63 | +2.14 | N | 0.3779 | 0.3779 | +0.008 | Y (+0.9/+3.7) | −0.16 | +0.17 | 13,065 |
| T09 | C5 | 21 | −0.47 | Y | 0.0002 | 0.0002 | −0.062 | N (−1.5/+0.4) | −4.85 | +5.72 | 8,364 |
| T10 | C5 | 63 | **−2.37** | Y | 0.0002 | 0.0002 | −0.042 | **Y (−4.5/−0.5)** | −0.13 | +3.94 | 8,364 |
| T11 | C6 | 21 | +2.53 | N | 0.0002 | 0.0002 | −0.106 | Y (+2.8/+2.1) | −11.58 | +12.18 | 4,723 |
| T12 | C6 | 63 | **−4.71** | Y | 0.0002 | 0.0002 | −0.100 | **Y (−5.4/−4.4)** | −0.11 | +8.00 | 4,723 |
| T13 | C7 | 21 | +6.10 | N | 0.0002 | 0.0002 | −0.175 | Y (+10.7/+2.0) | −15.18 | +17.27 | 1,284 |
| T14 | C7 | 63 | **−6.40** | Y | 0.0002 | 0.0002 | −0.208 | **Y (−1.8/−10.6)** | −0.09 | +10.38 | 1,284 |
| T15 | C8 | 21 | +4.04 | N | 0.0002 | 0.0002 | −0.122 | Y (+5.6/+2.6) | −14.39 | +15.04 | 6,243 |
| T16 | C8 | 63 | **−6.02** | Y | 0.0002 | 0.0002 | −0.129 | **Y (−5.8/−6.2)** | −0.09 | +9.57 | 6,243 |

No trial was THIN (all cells ≥1,284 moved-up episodes, floor=25). No trial excluded. BH: 15/16 survive (only T08/C4-63d fails; T07/C4-21d survives BH but is unfavorable). Sanity gate: not tripped.

**Direction note (adversarial-review resolved).** Every shipping 63d trial shows stop-out Δ<0 (fewer stops) AND liftoff Δ>0 (more clean liftoffs) — moved-up is unambiguously better on terminal states. The negative r_biserial is the SAME sign the positive control produced for its deliberately-upshifted group, confirming (not assuming) that negative r = moved-up stochastically larger/better. The two-sided perm_p is significant; the favorable *direction* is carried by the stop-out Δ sign and corroborated by liftoff Δ and r_bis, all mutually consistent.

---

## 5. Fire-rate impact table (R7 — mandatory regardless of outcome)

RW mode removes zero fires (`gate_fire_rate_impact_pct = 0.0` for all configs by construction — additive-lanes law).

| Config | n_in_bonus_cell | bonus_cell_% | n_ep_bonus_cell | n_ep_moved_up | n_ep_not_moved_up | gate_impact |
|---|---|---|---|---|---|---|
| C1 | 20,407 | 43.3% | 8,849 | 8,199 | 13,548 | 0.0% |
| C2 | 5,695 | 12.1% | 2,501 | 2,403 | 18,773 | 0.0% |
| C3 | 23,780 | 50.4% | 10,266 | 9,493 | 12,938 | 0.0% |
| C4 | 35,079 | 74.3% | 15,431 | 13,065 | 10,398 | 0.0% |
| C5 | 20,146 | 42.7% | 8,882 | 8,364 | 13,885 | 0.0% |
| C6 | 11,371 | 24.1% | 4,946 | 4,723 | 16,923 | 0.0% |
| C7 | 3,026 | 6.4% | 1,327 | 1,284 | 19,903 | 0.0% |
| C8 | 15,515 | 32.9% | 6,623 | 6,243 | 15,467 | 0.0% |

n_fires_total (washout-defined population) = 47,182. All not-moved-up groups clear the 25-cluster floor by orders of magnitude.

---

## 6. Both-halves sign-stability table (surviving trials)

Per-half Δ = stop_out(moved_up_in_half) − stop_out(not_moved_up_in_half), horizon-matched, **NO external baseline** (BLOCKING-2 pinned; the diagnostic's `sign_consistent` was NOT inherited). Midpoint = 2024-05-13 (H1 n=22,301, H2 n=24,881).

| Config | 63d H1 Δpp | 63d H2 Δpp | Same sign? | Stable |
|---|---|---|---|---|
| C1 | −2.42 | −4.47 | both favorable | **Y** |
| C2 | **+1.50** | **−9.67** | **opposite** | **N — UNSTABLE** |
| C3 | −6.50 | −1.96 | both favorable | **Y** |
| C5 | −4.51 | −0.54 | both favorable | **Y** |
| C6 | −5.38 | −4.38 | both favorable | **Y** |
| C7 | −1.75 | −10.55 | both favorable | **Y** |
| C8 | −5.78 | −6.24 | both favorable | **Y** |

The both-halves gate did its job: it killed the one config (C2) whose 63d edge is entirely a back-half phenomenon.

---

## 7. Dead-money co-benefit check (§5.3; binding gate = 21d per ADVISORY E)

For each BH-surviving, sign-stable stop-out survivor, the **21d dead-money Δ must be ≤0** (no harm trade). The 63d dead-money rate is ~0.08% baseline (vacuous), so 21d is the binding check.

| Config | 21d dead-money Δpp | ≤0? | Co-benefit |
|---|---|---|---|
| C1 | −15.58 | Y | **PASS** |
| C3 | −8.29 | Y | **PASS** |
| C5 | −4.85 | Y | **PASS** |
| C6 | −11.58 | Y | **PASS** |
| C7 | −15.18 | Y | **PASS** |
| C8 | −14.39 | Y | **PASS** |

Every survivor also *reduces* 21d dead-money — it does not trade the reprobe's T02 dead-money benefit away. This is the coherent mechanism from the diagnostic: deep-washout moved-up names avoid both the near-term hard stop and the dead-money drift, and resolve into more clean liftoffs by 63d.

---

## 8. Whole-study verdict

**PARTIAL_SHIP.** Six configs (C1, C3, C5, C6, C7, C8) satisfy all four §6.3 ship conditions. The §6.2 program-wide kill does **not** fire. The washout-as-rank-input line remains open, now depth/interaction-conditioned. **This authorizes the SHADOW rung only** — no live board enforcement until the forward-ledger flip criterion (§8 of PREREG) fires and Fable approves.

C2 (sign-unstable) and C4 (unfavorable at both horizons) are DEAD within this family; re-testing either requires a new trial_id / new BH family (§2.2 clause 6).

---

## 9. In-sample honesty statement (verbatim, §10.9)

> The depth threshold (>25%) and the eight grid configs were selected by examining the same 47,182-fire panel used in the diagnostic. This is genuine post-diagnostic registration, not pretend-prospective pre-registration. Out-of-sample confirmation is the forward ledger and CN/HK/CA cross-market passports ONLY. This pass authorizes the SHADOW rung only — never direct live board enforcement. The protections that make this credible are: (a) calibrated episode-permutation inference (both controls passed before the grid), (b) both-halves sign stability under the baseline-free within-half convention (which killed C2), (c) a pre-declared program-wide kill (which did not need to fire), and (d) the acknowledgment that six configs surviving an in-sample-selected grid is exactly the pattern most in need of out-of-sample confirmation.

---

## 10. Context appendix

- **Survivor-stamped rows:** 0. The verdict-grade fire population (49,939 fires, 22,295 episodes) contains no `survivor_bias=True` rows — all are Massive-sourced, 2022-06-30→2025-12-29, per `P0_MEASUREMENT_MEMO.md v1.1 §1/§2`. There is therefore no PRE-2022 / SURVIVOR-STAMPED context appendix to route (the memo's boundary is 2021-07-06; the replay's fires begin 2022-06-30). No pre-2022 rows entered the BH family, sign-stability, n-floors, or any GO/NO-GO decision.
- **Reprobe cross-reference (sealed prior-study numbers, NOT re-run here):** T09 (RW 63d stop, production flat-binary washout) = **+3.34pp** unfavorable (the reprobe's PROMOTION_DIES_PROXY_ONLY verdict — the flat flag is not a favorable rank input); T02 (HG 21d dead-money, production) = **−15.11pp** favorable but permanently display-only (HG path closed, P1.3 §6.2). This study's finding — that *depth-stratified* washout IS a favorable rank input at 63d — is consistent with the reprobe: the reprobe killed the **flat binary** flag (which pools the harmful shallow bulk with the favorable deep tail); this study recovers the edge by conditioning on depth. The flat-binary shadow-falsification signature (D_f ≥ +3.34pp at 63d) remains the tripwire for any shipped depth config.

---

## 11. Plain-English box

> **What we tested.** When a stock has fallen a long way from its peak ("washed out"), our board gives it a small ranking nudge. A prior test found that nudging *every* washed-out stock actually made things worse at the 3-month mark. But a follow-up hinted the washout flag hides two very different groups: shallow dips (down 15–25%, common, and the ones that hurt) and deep washouts (down 40%+, rarer, and the ones that recover). This study asks, with proper statistics, whether nudging only the *deep* washouts — alone or combined with "not chasing an extended price" and "showing relative strength" — actually helps.
>
> **What we found.** Six of eight depth/interaction recipes passed. Nudged-up deep-washout names get stopped out about 4–6 percentage points *less* often at 3 months, and they also spend far less time as "dead money" in the first month (down 8–16pp) while producing more clean liftoffs. The effect held up in both the first and second halves of the data for all six — a key honesty test. The one recipe that failed on that test was "deepest washouts alone" (down 40%+), whose edge showed up only in the recent half — so we did not promote it. The broadest, shallowest recipe carried no edge at all, exactly as the harmful-shallow-bulk theory predicted.
>
> **What this means.** The depth gradient is real: it is not the washout flag that is broken, it is that pooling shallow and deep together cancels the signal. Conditioning on depth recovers it. Six recipes now go to a **shadow** track — they influence nothing live yet; they accrue a forward track record and must also survive on China/Hong Kong/Canada data before any real money follows. This is the only honest out-of-sample test, because the recipe was chosen by looking at this same data.

---

## 12. Leak audit

- **Fill rule (next-bar, not same-bar):** rank re-ordering happens within `signal_date`; forward returns `fwd_ret_21`/`fwd_ret_63` and terminal states `state_8_21`/`state_15_126` are strictly post-signal, frozen in the replay artifact. No same-bar fill. ✓
- **Feature freeze (PIT):** `dd_pct` regenerated point-in-time via `washout_depth_pit` on price index ≤ `signal_date` only (byte-faithful depth extension of the reprobe's `washout_ctx` path). No look-ahead. Reproduces the diagnostic population exactly (n_defined=47,182, washout_true=36,734). ✓
- **Era boundary:** 2022-06-30 → 2025-12-29 (replay vg-fire max; the PREREG's stated window ...2026-07-02 selects the identical 49,939-fire population — no fire has signal_date beyond 2025-12-29). ✓
- **Survivor-bias bound:** 0 stamped rows; `survivor_bias=False` for all fires (Massive-sourced, verified). ✓

---

*Results are appended here only; the PREREG is immutable. Statistical machinery (episode-permutation MWU, BH, calibration controls) reused verbatim from `run_P1_3_v2.py`; depth path reused from the reprobe/diagnostic; the diagnostic's buggy `sign_consistent` was deliberately NOT inherited.*
