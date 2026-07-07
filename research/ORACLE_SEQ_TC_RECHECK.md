# SEQ_TLT_RELIEF_WASHOUT Episode-Cluster CIs + Time-Shift Placebo (OTA-RC-2)

**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**

Date: 2026-07-07  |  Seed: 20260705  |  Draws: 2000  |  Signal: SEQ_TLT_RELIEF_WASHOUT

---

## Reproduction Gate

Signal definition, fire set, exit convention (W=25, E=21, time-exit), all six leg
thresholds, and the dev/holdout split (2019-12-31) are frozen.

| Metric | Reproduced | Shipped | Match |
|---|---|---|---|
| n | 745 | 745 | YES |
| WR | 0.6725 | 0.6720 | YES |
| asym | 1.7474 | 1.7470 | YES |
| ret_exit | +2.37% | +2.37% | YES |
| holdout n | 267 | 267 | YES |
| holdout WR | 0.6891 | 0.6890 | YES |
| holdout ret_exit | +3.71% | +3.71% | YES |

**Reproduction gate: PASS**

---

## Step 1 — Episode Collapse

Clustering rule: same node, entry dates within ≤10 trading-day gaps
chain into one episode (gap approximated as calendar days × 5/7, rounded).

### Coverage stamp

| Metric | Value |
|---|---|
| Total fires | 745 |
| Episodes (all) | 610 |
| Calendar months touched | 157 (2002-10 to 2026-05) |
| Fires/episode: min / mean / median / max | 1 / 1.22 / 1.00 / 4 |
| Episodes (dev, ≤2019-12-31) | 414 over 104 months |
| Episodes (holdout, >2019-12-31) | 196 over 53 months |

---

## Step 2 — Episode-Cluster Bootstrap CIs

Method: resample episodes with replacement (2000 draws, seed 20260705),
all fires within a drawn episode move together. 95% CI = [2.5th, 97.5th] percentile
of draw distribution.

### 2a — Full set

| Metric | Point | CI lo | CI hi | Bar | Lower bound clears bar? |
|---|---|---|---|---|---|
| WR | 0.6725 | 0.6368 | 0.7072 | ≥0.62 (Leg 2) | YES |
| ret_exit | +2.37% | +1.86% | +2.88% | >0 | YES |
| asym | 1.7474 | 1.5025 | 2.0405 | ≥1.5 (Leg 3) | YES |

### 2b — Holdout subset

| Metric | Point | CI lo | CI hi | Bar | Lower bound clears bar? |
|---|---|---|---|---|---|
| WR | 0.6891 | 0.6308 | 0.7436 | ≥0.58 (Leg 5) | YES |
| ret_exit | +3.71% | +2.59% | +4.92% | >0 | YES |

(Holdout: 267 fires across 196 episodes)

---

## Step 3 — Leg-6 Placebo: Shipped vs Time-Shift Side-by-Side

Shipped Leg-6 (oracle_reversion_screen.py :747+): per node, independently sample
count-matched outcomes from the full realizable-outcome pool — does not preserve
temporal clustering.

Time-shift placebo (this re-check, mirrors oracle_compound_tc_recheck.py):
for each draw, shift each node's real entry-date sequence by one shared uniform
random integer offset (mod pool_size), preserving inter-fire spacing exactly.
Count-matched by construction.

| Method | Draws | p95 | Observed ret_exit | Clears bar? |
|---|---|---|---|---|
| Shipped published | 500 | +1.16% | +2.37% | YES |
| Reproduced shipped (independent draws) | 500 | +1.19% | +2.37% | YES |
| Time-shift (this re-check) | 2000 | +3.75% | +2.37% | NO |

---

## Summary — All new inference side-by-side

| Test | Shipped point | New CI / bar | Status |
|---|---|---|---|
| Leg-2 WR (full) | 0.6720 | CI lo = 0.6368 vs ≥0.62 | CI LOWER CLEARS |
| Leg-5 WR (holdout) | 0.6890 | CI lo = 0.6308 vs ≥0.58 | CI LOWER CLEARS |
| Leg-6 placebo (shipped) | real > p95=+1.16% -> PASS | — | — |
| Leg-6 time-shift (new) | +2.37% | p95=+3.75% | TIME-SHIFT FAIL |
| ret_exit 95% CI | +2.37% | [+1.86%, +2.88%] | CI EXCLUDES zero |
| asym 95% CI | 1.7470 | [1.5025, 2.0405] | CI lo ≥ 1.5 bar |

---

*RE-CHECK artifact. No verdict is changed. Adjudication pending (Fable).*
*Script: scripts/research/oracle_seq_tc_recheck.py  |  Seed: 20260705  |  n_draws: 2000*
