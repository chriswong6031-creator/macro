# P2_5_DIAGNOSTIC — RESULTS

**Study:** `P2_5_depth_gradient_diagnostic`
**Program:** Entry Intelligence (EI)
**Label:** DIAGNOSTIC — IN-SAMPLE, NO VERDICTS; hypotheses feed P2_5 PREREG
**Date:** 2026-07-05 · **Author:** Subagent under Fable orchestration
**Population:** 49,939 verdict-grade fires (47,182 with production washout defined)
**Replay MD5:** `906175f9eb8caa351ed6d7d5c56265d3` — matches F1 reprobe artifact [ADVISORY C: corrected typo — original printed `...56215d3`, correct value is `...56265d3` per results.json `replay_md5` field and PREREG provenance line]

---

## In plain English (lead finding)

> The central question was: does the stop-out delta from washout change sign depending on
> how deep the washout is? The answer is yes — and the gradient is the clearest structural
> signal in this diagnostic.
>
> Shallow washouts (15–25% drawdown, ~44% of washout-True fires) are *less* stopped out
> at 21 days (−1.4pp vs baseline) but *more* stopped out at 63 days (+2.0pp). Deep
> washouts (>40%, ~15% of washout-True fires) show the opposite short-term pattern:
> +6.9pp stop-out at 21 days but −3.6pp at 63 days. This is exactly the sign-flip the
> Fable mechanism hypothesis predicted: shallow pullbacks (intact trend) are less
> immediately toxic but resolve poorly long-term; deep capitulations are immediately
> painful but clean out faster.
>
> The dead-money effect is monotonic with depth: shallower washouts show more dead money
> (+4pp at 21d), deeper washouts show less (−7 to −14pp at 21d). This is consistent —
> deep capitulations resolve faster even when they initially stop out more.
>
> No single partition shows a large, sign-consistent, favorable stop-out delta at both
> horizons. The closest candidates are: deep washout × anti-chase FAIL (which is
> directionally favorable at 63d but the anti-chase fail group is small and
> operationally excluded), and the deep-trio (dd>25% + ac_pass + rs_fav, n=11,371)
> which shows −3.3pp at 63d but +2.0pp at 21d (sign splits).

---

## Baselines (unconditioned, defined population)

| | n | Episodes | 21d stop-out | 21d dead-money | 21d liftoff | 63d stop-out | 63d dead-money | 63d liftoff |
|---|---|---|---|---|---|---|---|---|
| Unconditioned | 47,182 | 21,053 | 38.48% | 18.26% | 30.37% | 62.31% | 0.09% | 32.94% |
| Washout = True | 36,734 | 15,699 | 39.55% | 14.92% | 30.57% | 62.77% | 0.09% | 32.78% |
| Washout = False | 10,448 | 5,013 | 34.71% | 29.50% | 29.77% | 62.35% | 0.09% | 33.70% |

Washout=True fires have **higher** 21d stop-out (+1.07pp) but similar 63d stop-out
vs washout=False. This reflects the F1 reprobe sign reversal: production washout is not
a favorable signal at the cohort level.

---

## Partition (a): DEPTH GRADIENT

**Central question: does the stop-out delta's sign depend on depth?**

| Bucket | n fires | n episodes | 21d stop-out | 21d Δpp | 21d dm Δpp | 63d stop-out | 63d Δpp | 63d dm Δpp |
|---|---|---|---|---|---|---|---|---|
| d15_25% | 16,326 | 7,305 | 37.04% | **−1.44** | +4.08 | 64.63% | +1.96 | −0.05 |
| d25_40% | 14,710 | 6,362 | 40.07% | **+1.59** | −7.43 | 61.40% | **−1.27** | −0.09 |
| d40plus% | 5,698 | 2,503 | 45.42% | **+6.94** | −14.09 | 59.10% | **−3.57** | −0.03 |
| proxy-equiv (washout_proximity=T) | 21,099 | 8,765 | 40.06% | +1.58 | −7.04 | 59.61% | **−3.06** | −0.07 |

**All baselines are unconditioned (47,182 fires). Δpp = cell rate minus baseline rate × 100.**

### Depth gradient findings (descriptive):

1. **Sign flips at the 21d horizon as depth increases.** The 15–25% bucket is the only
   depth tier with a favorable (negative) 21d stop-out delta (−1.44pp). The 25–40%
   bucket turns positive (+1.59pp). The >40% bucket is the most unfavorable short-term
   (+6.94pp). This is the key gradient: fixed-percent stops at 21 days discriminate by
   depth because deeper washouts are not yet recovered.

2. **At the 63d horizon, the gradient reverses.** d40plus shows the largest favorable
   delta (−3.57pp). d25_40 shows a modest −1.27pp. d15_25 is unfavorable at 63d
   (+1.96pp). Deeper washouts recover more cleanly over a longer window.

3. **Dead-money is monotonically negatively correlated with depth.** Shallow washouts
   accumulate more dead-money (+4.08pp at 21d); deeper washouts shed it faster (−7 to
   −14pp at 21d). This makes mechanical sense: a stock down 40% from its high has less
   room to drift sideways.

4. **The proxy-equivalent bucket (washout_proximity=True) clusters behaviorally near
   d25_40 and d40plus** — consistent with the proxy capturing deeper washouts better than
   shallow ones (price ≤ 0.9×200DMA is a ≥10% distance threshold which maps onto the
   upper part of the depth distribution).

5. **dd_pct distribution (washout=True, n=36,734):**
   - p25 = 20.4% · p50 = 26.4% · p75 = 34.6% · p90 = 44.4% · p95 = 52.1%
   - The median washout fire is a 26% drawdown. The 15–25% bucket contains ~44% of fires.

---

## Partition (b): TREND CONTEXT — washout × above_200

| Cell | n fires | n ep | 21d stop Δpp | 21d dm Δpp | 63d stop Δpp |
|---|---|---|---|---|---|
| washout=T, above_200 | 12,954 | 6,487 | **+1.44** | −1.04 | **+3.55** |
| washout=T, below_200 | 23,780 | 10,266 | **+0.87** | −4.60 | **−2.23** |
| washout=F, above_200 | 9,083 | 4,475 | −3.65 | +10.01 | +0.65 |
| washout=F, below_200 | 1,365 | 661 | −4.56 | +23.42 | +0.84 |

**Fable mechanism hypothesis partially confirmed here:** washout=True fires *above* the
200DMA (shallow-pullback-in-uptrend) are the most unfavorable at both horizons
(+1.44pp at 21d, +3.55pp at 63d). Washout=True fires *below* the 200DMA (trend-broken)
are less bad at 21d (+0.87pp) and turn favorable at 63d (−2.23pp). This is consistent
with the hypothesis that trend-broken deep washouts are the target population, not
intact-trend pullbacks.

---

## Partition (c): PAIRLETS

### [c1] washout × anti-chase-pass (ext_z ≤ 2.0)

| Cell | n fires | n ep | 21d stop Δpp | 21d dm Δpp | 63d stop Δpp |
|---|---|---|---|---|---|
| wash=T, ac_pass | 35,079 | 15,431 | +1.00 | −3.35 | −0.50 |
| wash=T, ac_fail | 1,655 | 915 | +2.67 | −3.16 | +6.27 |
| wash=F, ac_pass | 9,854 | 4,772 | −3.54 | +11.24 | +0.56 |
| wash=F, ac_fail | 594 | 327 | −7.50 | +20.46 | +2.50 |

Anti-chase pass provides modest differentiation within washout=True: the ac_fail group
has notably worse 63d outcomes (+6.27pp), but the group is small (n=1,655). The
anti-chase pass alone does not generate a favorable stop-out delta within washout fires.

### [c2] washout × RS-quartile (Q1/Q2 favorable vs Q3/Q4)

| Cell | n fires | n ep | 21d stop Δpp | 63d stop Δpp |
|---|---|---|---|---|
| wash=T, rs_Q1Q2 | 20,146 | 8,882 | +0.02 | −1.10 |
| wash=T, rs_Q3Q4 | 16,588 | 7,943 | +2.35 | +0.91 |
| wash=F, rs_Q1Q2 | 4,042 | 2,002 | −4.04 | +0.45 |
| wash=F, rs_Q3Q4 | 6,406 | 3,265 | −3.59 | +0.81 |

RS-quartile does differentiate within washout=True: Q1/Q2 fires are favorable at 63d
(−1.10pp) while Q3/Q4 fires are unfavorable (+0.91pp). The 21d pattern is flat for Q1Q2
(+0.02pp near-zero). This suggests RS is a useful separator at 63d but not 21d.

### [c3] deep-washout (dd>25% or proxy-equiv) × anti-chase-pass

| Cell | n fires | n ep | 21d stop Δpp | 21d dm Δpp | 63d stop Δpp |
|---|---|---|---|---|---|
| deep + ac_pass | 25,077 | 10,759 | +1.65 | −6.70 | −1.94 |
| deep + ac_fail | 991 | 550 | +4.81 | −8.37 | +5.29 |

Deep washout + anti-chase pass produces a modest favorable 63d delta (−1.94pp) with
a large favorable dead-money reduction (−6.70pp at 21d). The ac_fail group is small and
operationally excluded by the existing anti-chase gate.

---

## Partition (d): TRIO — washout × anti-chase-pass × favorable-RS

| Cell | n fires | n ep | 21d stop Δpp | 21d dm Δpp | 21d liftoff Δpp | 63d stop Δpp | 63d dm Δpp | 63d liftoff Δpp |
|---|---|---|---|---|---|---|---|---|
| **trio (all three)** | **20,146** | **8,882** | **+0.02** | **−2.93** | **+3.18** | **−1.10** | **−0.08** | **+2.11** |
| deep-trio (dd>25%+all) | 11,371 | 4,946 | +2.00 | −8.84 | +2.21 | **−3.30** | −0.09 | +3.28 |
| trio complement | 27,036 | 12,914 | −0.01 | +2.18 | −1.88 | +0.82 | +0.06 | −1.16 |

**POWER CHECK:** trio n=20,146 — **ABOVE 1,000 floor. Adequately powered.**
Deep-trio n=11,371 — also above 1,000 floor.

### Trio findings:

1. **21d stop-out:** Trio fires are nearly flat vs baseline (+0.02pp). This is the
   safest short-term profile among all partitions tested: neither materially better
   nor worse than random.

2. **63d stop-out:** Trio fires are −1.10pp favorable. Deep-trio (dd>25%) is
   −3.30pp favorable at 63d — the largest favorable 63d stop-out delta among all
   adequately-powered cells.

3. **Dead-money:** Trio shows −2.93pp at 21d (favorable), consistent with washout
   clearing dead-money. Deep-trio shows −8.84pp at 21d — large favorable effect.

4. **Clean liftoff:** Trio fires show +3.18pp clean liftoff at 21d and +2.11pp at 63d.
   Deep-trio +2.21pp / +3.28pp. These are the largest liftoff deltas in the partition.

5. **Sign pattern:** The trio has a split sign at 21d (+stop, +liftoff) vs 63d (−stop,
   +liftoff). This is consistent with the 63d window being the correct discriminator for
   deep washouts.

---

## Ranking by |stop-out delta| × sign-consistency

(Top 10 cells, ranked by max(|so21Δ|, |so63Δ|). sc=sign-consistent across H1/H2. dmSurv=dm63Δ<0.)

| Rank | Cell | n | so21Δpp | so63Δpp | dm63Δpp | sc21 | sc63 | dmSurv |
|---|---|---|---|---|---|---|---|---|
| 1 | wash_F_ac_fail | 594 | −7.5 | +2.5 | −0.1 | Y | Y | Y |
| 2 | **d40plus** | **5,698** | **+6.9** | **−3.6** | **−0.0** | **Y** | **Y** | **Y** |
| 3 | wash_T_ac_fail | 1,655 | +2.7 | +6.3 | −0.1 | N | Y | Y |
| 4 | deep_washout_ac_fail | 991 | +4.8 | +5.3 | −0.1 | N | Y | Y |
| 5 | washout_false_below_200 | 1,365 | −4.6 | +0.8 | +1.3 | Y | Y | N |
| 6 | wash_F_rs_Q1Q2 | 4,042 | −4.0 | +0.5 | +0.1 | Y | Y | N |
| 7 | washout_false_above_200 | 9,083 | −3.6 | +0.7 | +0.0 | Y | Y | N |
| 8 | wash_F_rs_Q3Q4 | 6,406 | −3.6 | +0.8 | +0.3 | N | Y | N |
| 9 | **washout_true_above_200** | **12,954** | **+1.4** | **+3.5** | **−0.1** | **N** | **Y** | **Y** |
| 10 | wash_F_ac_pass | 9,854 | −3.5 | +0.6 | +0.2 | Y | Y | N |
| 11 | **deep_washout_ac_pass_rs_fav** | **11,371** | **+2.0** | **−3.3** | **−0.1** | **N** | **Y** | **Y** |
| 12 | **proxy_equiv** | **21,099** | **+1.6** | **−3.1** | **−0.1** | **N** | **Y** | **Y** |

Bold = adequately powered cells (n≥1,000) with dm benefit surviving at 63d.
sc21=N means H1/H2 disagree in the 21d direction — unreliable short-horizon split.

### Key ranking observations:

- **d40plus** is the highest-ranked adequately-powered cell with a favorable 63d delta
  AND sign-consistent 63d pattern (Y). It has the largest magnitude stop-out movement of
  any large cell. The 21d unfavorability (+6.9pp) is a cost of the stop being too tight
  for deep capitulations.

- **The deep-trio (deep_washout_ac_pass_rs_fav)** is the best candidate for favorable
  63d stop-out reduction (−3.3pp) among cells that combine all three production-gate
  conditions. It is adequately powered (n=11,371). The 21d sign is unfavorable (+2.0pp),
  which suggests 21d stops fire through recovery at this depth.

- **Washout=True + above_200** is a negative finding: even with washout defined, if the
  stock is above the 200DMA the 63d stop-out is worse (+3.55pp). This is the shallow-
  pullback-in-uptrend population the mechanism hypothesis predicted would be harmful.

---

## Hypotheses for P2_5 PREREG

These hypotheses are inferred from this diagnostic and must be pre-registered before
being tested on the full population. They are NOT verdicts.

**H1 (depth gradient):** The favorable stop-out effect at 63d is concentrated in fires
with dd_pct > 25% (d25_40 + d40plus). Shallow washouts (d15_25) are unfavorable at 63d.
Proposed grid: three depth tiers × {21d, 63d}.

**H2 (trend context):** Washout=True fires above the 200DMA are harmful at both
horizons. The favorable 63d effect (if any) lives in the below_200 sub-population.
Proposed test: washout × above_200 interaction, 63d horizon.

**H3 (trio at 63d):** The trio (washout + anti-chase + rs_fav) shows a modest favorable
63d stop-out delta (−1.10pp) driven by the deep-washout sub-group (−3.30pp at 63d).
The 21d horizon is uninformative (flat). Proposed: pre-register the 63d trio as the
primary test, with depth as a sub-group.

**H4 (horizon mismatch):** Fixed-percent stops at 21 days are the discriminator that
makes depth the wrong gate: deep washouts need more recovery time. A longer stop window
(63d or event-based) would remove the 21d cost. This is design-level — not a test.

---

## Integrity note

- Computation path: verbatim from `run_P2_1B_F1_reprobe.py`
- Replay MD5 matches concordance artifact
- n_washout_true=36,734 / n_washout_false=10,448 / n_none=2,757 — matches F1 reprobe exactly
- All outputs labelled DIAGNOSTIC — IN-SAMPLE, NO VERDICTS

---

## Files

- Script: `research/entry_intel/p1_runs/P2_5_DIAGNOSTIC/run_P2_5_diagnostic.py`
- Results JSON: `research/entry_intel/p1_runs/P2_5_DIAGNOSTIC/results.json`

---

## Correction note (appended 2026-07-05, P2_5_REDTEAM.md audit — do not alter data tables above)

**[BLOCKING-1 upstream — sc63 bug in `sign_consistent()`]**

The `sign_consistent()` function in `run_P2_5_diagnostic.py` (line ~470) computes 63d sign-consistency by testing both halves' 63d stop-out rate against `baseline_21["stop_out"]` (0.3848) — the **21d baseline** — instead of the 63d baseline (0.6231). Because all cells' 63d stop-out rates lie above 0.3848 in both halves, `sc63` is `True` mechanically for every cell. The `sc63=Y` labels in the ranking table above are **not** evidence of genuine 63d half-stability.

**Recomputed `sc63` against the correct 63d baseline (0.6231) — correction only, data tables unchanged:**

| Cell | H1 63d stop-out | H2 63d stop-out | Corrected sc63 |
|---|---|---|---|
| d40plus (C2) | 0.5928 (H1 −3.0pp) | 0.5824 (H2 −4.1pp) | **True** — both halves favorable |
| deep_washout_ac_pass_rs_fav (C6) | 0.5411 (H1 −8.2pp) | 0.6321 (H2 +0.9pp) | **False** — H2 reverses |
| washout_ac_pass_rs_fav (C5) | 0.5555 (H1 −6.8pp) | 0.6634 (H2 +4.0pp) | **False** — H2 reverses |
| washout_true_below_200 (C3) | 0.5416 (H1 −8.2pp) | 0.6561 (H2 +3.3pp) | **False** — H2 reverses |
| proxy_equiv | 0.5287 (H1 −9.4pp) | 0.6523 (H2 +2.9pp) | **False** — H2 reverses |

The H1 effects for C3/C5/C6 are strongly favorable at 63d; H2 reverses. Only **C2 (d40plus) is genuinely 63d sign-stable** pre-registration. The PREREG's §5.2 gate (with the correct baseline-free convention specified per BLOCKING-2) will adjudicate C3/C5/C6 at run time.

**[ADVISORY B — episode count]** The baseline table above (now corrected) originally printed 20,703 episodes for the unconditioned population; the correct value from `results.json` is **21,053**.

**[ADVISORY C — MD5 typo]** The MD5 field in the original header printed `...56215d3`; corrected to `...56265d3` (matching `results.json` and the PREREG provenance line).

**[ADVISORY A — 63d baseline]** The baseline table originally printed 62.67% for the unconditioned 63d stop-out; corrected to 62.31% (0.62314 per `results.json`). The deltas in the partition tables were computed against 62.31% internally and are unchanged.
