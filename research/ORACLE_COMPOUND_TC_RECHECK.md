# Oracle Compound + P3 Secondary — Time-Confound Re-Check (ORC-RC-1)

**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**

Date: 2026-07-07  |  Seed: 20260704  |  Draws: 2000 per part

---

## Part 1 — Compound Gauntlet: Circular Time-Shift Placebo

### Methodology

Shipped G3 (`_run_placebo`, oracle_gauntlet_compound.py :228-252): for each
draw, independently resample count-matched outcomes per node from the full
realizable-outcome pool.  Does not preserve temporal clustering — real onsets
that concentrate in regimes get shuffled against random-regime draws.

Circular time-shift: for each draw, each node's full real onset-date sequence is
shifted by one uniform random integer offset in [0, pool_size) mod pool_size,
landing each onset at pool_dates[(pool_position + offset) % pool_size].  Inter-
onset spacing and temporal clustering are preserved exactly; count is matched
by construction.  Pool built with the same entry→exec→exit logic as oracle_screen
(vectorized for efficiency; excess values are identical).

### Reproduction gate

G1 full-history OOS (split 2019-12-31):

| ID | n | eff₆₃ | dev eff | hold n | hold eff | hold hit | G1 |
|---|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | 2351 | +1.30% | +1.35% | 663 | +1.19% | +53.39% | PASS |
| A9_WASHOUT_SAME_OUTFLOW_DENSE | 438 | +1.06% | +0.13% | 191 | +2.27% | +65.45% | PASS |
| A17_WASHOUT_SAME_OUT_NEG_VEL | 262 | +1.68% | -0.03% | 116 | +3.83% | +71.55% | FAIL |

Reference (ORACLE_COMPOUND_GAUNTLET_R1.md):
- A15: n=2351 eff=+1.30%, holdout +1.19%/53.4%/n=663, G1 PASS
- A9: n=438 eff=+1.06%, holdout +2.27%/65.4%/n=191, G1 PASS
- A17 full-history: dev=−0.03%, G1 FAIL (expected; modern-regime edge)

### G3 side-by-side: shipped independent draws vs circular time-shift

| ID | scope | shipped p (n=500) | time-shift p (n=2000) | shipped G3 | time-shift G3 |
|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | full | 0.0000 | 0.0095 | PASS | PASS |
| A9_WASHOUT_SAME_OUTFLOW_DENSE | full | 0.0000 | 0.1390 | PASS | FAIL |
| A17_WASHOUT_SAME_OUT_NEG_VEL | full | 0.0000 | 0.1050 | PASS | FAIL |
| A17 (modern 2015+) | modern | 0.0000 | 0.0130 | PASS | PASS |

### A17 modern-regime detail

- Modern window (2015+): n=145, eff63=+3.78%, hit=+71.72%
- Within-modern OOS (dev≤2020-12-31, hold>2020): hold n=73, eff=+5.05%, hit=+84.93%
- G1 within-modern: FAIL
- Shipped G3 (modern subset, n=500): p=0.0000
- Time-shift G3 (modern subset, n=2000): p=0.0130

---

## Part 2 — P3 Secondary ep_in_onset_21d: Calendar-Month Block Bootstrap

### Context

The sole BH-rejected secondary from P3 is ep_in_onset_21d (raw p=0.0075, n=355).
The shipped CI used 21-consecutive-episode blocks in detection order.
Calendar-month blocks are a tighter temporal control: all episodes whose onset
falls in the same (year, month) move together in each bootstrap draw.

### Coverage stamp

- Episodes: 355 (in-direction, 21d mature outcome)
- Calendar months: 142 (1999-08 to 2026-04)
- Episodes/month: min=1, max=10, mean=2.5, median=2.0

### Side-by-side: shipped episode-block vs calendar-month block

| Method | Bootstrap 95% CI | One-sided p (H1: mean>0) |
|---|---|---|
| Shipped (21-episode-block, n=2000) | [+0.13%, +1.16%] | 0.0075 |
| Month-block (n=2000) | [+0.15%, +1.11%] | 0.0045 |

Real mean: +0.6181%

---

*RE-CHECK artifact. Verdicts remain pending Fable adjudication.*
*Script: scripts/research/oracle_compound_tc_recheck.py  |  Seed: 20260704*
