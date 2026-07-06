# P2.5 STUDY — FRESH CONFORMANCE REVIEW

**Reviewer:** Opus subagent (fresh, independent) under Fable orchestration
**Date:** 2026-07-05
**Target:** `research/entry_intel/p1_runs/P2_5_STUDY/` (results.json, _run.log, RESULTS.md, run_P2_5_study.py)
**Method:** independent from-scratch reproduction from `data/replay/replay_boarded.parquet` (MD5 `906175f9…65d3`, confirmed), NOT trust of the runner report or a copy of the runner's stat functions.

## VERDICT: **CLEAN**

The P2.5 study conforms to the PREREG and the red-team's two BLOCKING edits. The twice-seen 21d-baseline sign bug is **NOT present a third time** — verified by from-scratch reimplementation *and* by a counterfactual that shows the bugged convention would produce numerically different (and less stringent) results. All headline numbers, the calibration controls, the BH correction, the depth PIT population, and the §6 ship/kill mechanics reproduce independently. `sign_convention_verified = TRUE`.

---

## MANDATORY CHECK RESULTS

### (1) SIGN CONVENTION — VERIFIED baseline-free; NOT the 21d-baseline bug ✓ (load-bearing)

I reimplemented the per-half delta from the parquet (no copy of the runner's `half_delta_baseline_free`) as `stop_out(moved_up_in_half) − stop_out(not_moved_up_in_half)` within each half, and independently rebuilt the Mode-B `moved_up` columns. Reproduced per-half 63d deltas match results.json to <0.01pp:

| Config | my H1/H2 (63d, baseline-free) | json H1/H2 | match |
|---|---|---|---|
| C1 (lead) | −2.42 / −4.47 | −2.417 / −4.473 | ✓ |
| C6 (deep_trio) | −5.38 / −4.38 | −5.384 / −4.380 | ✓ |
| C8 | −5.78 / −6.24 | −5.779 / −6.244 | ✓ |
| **C2 (DEAD)** | **+1.50 / −9.67 (UNSTABLE)** | +1.503 / −9.669 | ✓ |

**Counterfactual proof the bug is absent.** I recomputed the SAME halves under the 21d-baseline-bug convention (moved_up stop rate − 0.3848, both horizons). Under the bug, every config's 63d per-half deltas become large POSITIVE numbers in both halves (C1: +17.6/+25.3; C2: +20.4/+19.5 — "stable positive"). The shipped numbers are numerically incompatible with that convention. Decisively: under the bug, **C2 would read sign-STABLE** (both positive); under the pinned convention it reads sign-UNSTABLE and dies. The pinned convention is strictly more stringent here — the runner did not launder C2 through.

**Second, independent line:** the runner's own `_assert_baseline_free()` self-check (run_P2_5_study.py:400-420) returns 0.0 on an identical-group probe; a baseline-anchored (bugged) implementation returns +11.52pp on the same probe, which trips the runner's `abs(d)>1e-9` HALT. The runner would have aborted a bugged run.

### (2) NEGATIVE + POSITIVE calibration controls — reproduced independently ✓
- **Negative** (reviewer seed 9999, 60 draws, my own MWU-permutation loop): rejection=0.100 (≤0.12 ✓), KS_p=0.942 (≥0.05 ✓), mean=0.496. PASS. (Runner's 200-draw run: rej=0.065, KS_p=0.593 — also PASS.)
- **Positive** (+0.05 return injection): perm_p=2.0e-4, r_biserial=−0.29 for the up-shifted group. PASS. Confirms the direction convention **negative r = group A stochastically larger/better** that RESULTS.md relies on.

### (3) TRIAL-GRID ADHERENCE ✓
m=16, all 8 configs × 2 horizons, no thin decrement (smallest cell C7=1,327 episodes ≫ floor 25). `active_configs`=8, `excluded_thin`=[]. No 9th config; exactly the PREREG §3/§4 grid. m as declared post-thin-check.

### (4) HEADLINE RECOMPUTE (≥3, incl. lead stop-out + BH-adj p) ✓
Reproduced from scratch, all exact vs results.json:
- **C1 (lead) 63d stop-out Δ = −3.66pp** ✓ ; **BH-adj p = 0.0002285** ✓ (perm_p floored at 1/(N_PERM+1)=1.9996e-4; BH·16/rank reproduces 0.00022853).
- C6 63d Δ=−4.71, C8 63d Δ=−6.02, C3 63d Δ=−4.26, C7 63d Δ=−6.40 — all exact.
- All eight 21d dead-money Δ exact (C1 −15.58 … C8 −14.39).
- n_survive_BH=15/16 (only C4-63d fails, BH-adj=0.3779) — reproduced.

### (5) §5.3 21d DEAD-MONEY CO-BENEFIT applied in ship-qualifying ✓
The gate `dm21 ≤ 0` binds all 6 ship configs (C1 −15.58, C3 −8.29, C5 −4.85, C6 −11.58, C7 −15.18, C8 −14.39 — all ≤0). 63d dead-money is vacuous (baseline 0.08%; only 1,031 DEAD_MONEY rows at 63d in the whole panel) — 21d is correctly the binding horizon per ADVISORY E. I traced the runner's gate: it requires 63d-or-21d BH-favorable-sign-stable AND 21d-dm≤0; my independent recomputation of the gate matches all 8 ship/kill decisions.

### (6) DEPTH VALUES PIT ✓
The runner's `washout_depth_pit` is byte-faithful to `engine/coiled.py:washout_ctx` (identical constants `_WASH_CTX_A=217`/`_WASH_CTX_B=91`, identical capit_pos/prior_max/`dd≤−0.15`), extended to expose `dd_pos=−dd`. PIT slice `price[price.index ≤ signal_date]` is causal. My from-scratch depth rebuild reproduced the population **exactly** (n_defined=47,182, washout_true=36,734, dd_pct defined=47,182) — i.e. all 47,182 name-dates reproduce against the engine algorithm, far exceeding the 10-spot-check floor.

### (7) VERDICT FOLLOWS §6 MECHANICALLY ✓
Binary outcome, nothing in between. 6 ships (C1,C3,C5,C6,C7,C8) named for EI-F1D-RW shadow; §6.2 program-wide kill correctly does NOT fire (≥1 config ships). Every ship rides the **63d** horizon (all 21d stop deltas unfavorable except C5's tiny −0.47, itself 21d-sign-unstable). C2 dies on 63d sign-instability (its only favorable horizon); C4 dies with no favorable BH-surviving trial. All reproduced.

### (8) HONESTY SURFACES ✓
In-sample provenance statement (§9, verbatim, names the selection sin), plain-English box (§11), leak audit (§12, next-bar fill + PIT freeze + 0 survivor-stamped rows), and the sc63/round-0 provenance note are all present in RESULTS.md and results.json.

---

## ADVISORY (non-blocking) — for shadow monitoring, not conformance

- **A1 — half-concentrated survivors.** Two survivors carry their 63d edge almost entirely in one half: **C5** (H1 −4.51 / H2 −0.54 — H2 barely favorable) and **C7** (H1 −1.75 / H2 −10.55 — front-half thin; C7 also rests on the smallest cell, 1,327 episodes). Both pass the pre-registered *sign* test legitimately, but their both-halves support is asymmetric. Recommend the forward ledger watch C5/C7 most closely; the flip-criterion (Wilson_upper(D_f)<0) is the right guard.
- **A2 — perm_p is a floor, not a point estimate.** 15/16 trials report perm_p=1/(N_PERM+1); the true effects exceed 5,000-perm resolution. Honest and correctly BH-adjusted, but the BH-adj p (0.00023) is a ceiling on significance, not a measured value. No action; noted for downstream readers.
- **A3 — mechanism coherence, not a flag.** All six survivors share a deep-washout or below-200 core; C4 (broadest, no depth cut) is the sole non-depth config and dies. This is consistent with the "depth gradient is real; pooling shallow+deep cancels" thesis, not a red flag.

## PROVENANCE NOTE (in-sample)
This is an in-sample-selected grid (depth threshold and 8 configs chosen on the same 47,182-fire panel). Six survivors on an in-sample grid is exactly the pattern most needing OOS confirmation. The study authorizes the **SHADOW rung only**; forward ledger + CN/HK/CA passports are the sole true OOS. The review confirms conformance, not out-of-sample validity.

## PLAIN-ENGLISH
The study did what it said it would. I re-did its most error-prone number (the "does the effect hold in both time-halves?" test) from raw data with my own code, and got the same answer — and I proved it did NOT repeat the arithmetic mistake that snuck into this program twice before (using the wrong 3-month vs 1-month yardstick). The two recipes it threw out really do fail; the six it kept really do pass the pre-set bars. The verdict — six recipes to a shadow track, no program-wide shutdown — is the mechanically correct read of its own rules.
