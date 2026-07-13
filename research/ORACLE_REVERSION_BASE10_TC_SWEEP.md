# Oracle Reversion Base (10 non-SEQ rows) — Time-Shift Placebo Sweep + Episode-Cluster CIs

**RE-CHECK — ADJUDICATED 2026-07-13: RC-RUL-6 (`research/TIME_CONFOUND_RECHECK_ADJUDICATION.md`). No verdict was changed by this document; see the adjudication postscript at the bottom.**

Date: 2026-07-07  |  Seed: 20260705  |  Draws: 2000  |  Script: `scripts/research/oracle_reversion_base10_tc_sweep.py`

**Authority:** RC-RUL-5 items 4+5 (`research/TIME_CONFOUND_RECHECK_ADJUDICATION.md`): the
reversion screen's Leg-6 independent-draw placebo is retired as a verdict instrument;
the 10 non-SEQ rows of the published reversion base (`research/ORACLE_REVERSION_VALIDATED.md`)
were graded by that retired machinery. This sweep re-expresses each row's Leg-6 read with the
time-preserving circular time-shift placebo (per the DT-R14 rubric,
`research/TIME_CONFOUND_EXPOSURE_AUDIT.md` §1) and adds episode-cluster CIs on WR/ret_exit/asym.
Events, thresholds, exit convention (W=25, E=21, time-exit), and dev/holdout splits are frozen;
inference machinery only. **Registry display statuses stay `screened` regardless of anything in
this document. This sweep is the pre-condition for any future promotion, not a promotion.**

---

## Reproduction gate (published numbers, registry `reversion` blocks, asof 2026-07-05)

Gate: n exact; WR and ret_exit within 1pp. Rows failing the gate get no new inference.

| row | tier | n | WR | asym | ret_exit | holdout n | holdout WR | holdout ret | match |
|---|---|---|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | s | 2357 / 2357 | 0.737 / 0.737 | 1.835 / 1.835 | +3.05% / +3.05% | 669 / 669 | 0.782 / 0.782 | +4.60% / +4.60% | yes |
| B4_WASHOUT_DOLLAR_RELIEF | s | 641 / 641 | 0.683 / 0.683 | 1.549 / 1.549 | +2.07% / +2.07% | 244 / 244 | 0.734 / 0.734 | +3.57% / +3.57% | yes |
| B4_EP_SAME_OUT_CREDIT_EASE | s | 392 / 392 | 0.725 / 0.724 | 1.560 / 1.561 | +2.12% / +2.12% | 134 / 134 | 0.716 / 0.716 | +2.28% / +2.28% | yes |
| R16_VBOT_ACCELZ_NEG2_K_LOW | s | 442 / 442 | 0.683 / 0.683 | 1.579 / 1.579 | +2.70% / +2.70% | 112 / 112 | 0.670 / 0.670 | +3.62% / +3.62% | yes |
| E_DOLLAR_EASE_TLT_POS_K25 | s | 416 / 416 | 0.692 / 0.692 | 1.838 / 1.838 | +2.31% / +2.31% | 149 / 149 | 0.718 / 0.718 | +2.77% / +2.77% | yes |
| R3_B2_ACCELZ_NEG15_K20 | s | 565 / 565 | 0.710 / 0.710 | 1.688 / 1.688 | +2.79% / +2.79% | 146 / 146 | 0.719 / 0.719 | +4.36% / +4.36% | yes |
| R4_E10_OIL_EASE_K30_VIX40 | s | 765 / 765 | 0.685 / 0.685 | 1.516 / 1.516 | +2.70% / +2.70% | 226 / 226 | 0.748 / 0.748 | +3.71% / +3.71% | yes |
| M1_OIL_DOWN_K30_RS_NEG | m | 674 / 674 | 0.690 / 0.690 | 3.397 / 3.397 | +12.24% / +12.24% | 407 / 407 | 0.649 / 0.649 | +12.55% / +12.55% | yes |
| SRM_BEARTAPE_ACCEL_K20 | m | 1403 / 1403 | 0.679 / 0.679 | 1.864 / 1.864 | +5.57% / +5.57% | 547 / 547 | 0.801 / 0.801 | +11.60% / +11.60% | yes |
| RSLAG_OVERSOLD_K20 | m | 1004 / 1004 | 0.625 / 0.625 | 2.742 / 2.742 | +9.79% / +9.79% | 593 / 593 | 0.653 / 0.653 | +12.76% / +12.76% | yes |

---

## Side-by-side — old Leg-6 bar vs time-shift p95 vs observed (per row)

Old bar = the shipped Leg-6 placebo p95 (independent per-node count-matched draws;
for the single-regime row †, the shipped Leg-6' regime-matched variant). Retired for
verdict use by RC-RUL-5. Reproduced = same machinery re-run as-is (500 draws, seed 42).
Time-shift = circular per-node offset placebo (this sweep, 2000 draws), which preserves
inter-fire spacing/clustering; for † the shift pool is restricted to operating-regime
(risk_off) dates, the time-preserving analog of Leg-6'.

| row | observed ret_exit | old bar p95 (published) | old bar p95 (reproduced) | time-shift p95 | time-shift p | observed > time-shift p95? |
|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | +3.05% | +1.05% | +1.05% | +4.96% | 0.1840 | NO |
| B4_WASHOUT_DOLLAR_RELIEF | +2.07% | +1.19% | +1.19% | +3.80% | 0.2575 | NO |
| B4_EP_SAME_OUT_CREDIT_EASE | +2.12% | +1.27% | +1.27% | +4.18% | 0.2830 | NO |
| R16_VBOT_ACCELZ_NEG2_K_LOW | +2.70% | +1.29% | +1.29% | +3.84% | 0.1425 | NO |
| E_DOLLAR_EASE_TLT_POS_K25 | +2.31% | +1.34% | +1.34% | +3.96% | 0.2200 | NO |
| R3_B2_ACCELZ_NEG15_K20 | +2.79% | +1.22% | +1.22% | +3.69% | 0.1435 | NO |
| R4_E10_OIL_EASE_K30_VIX40 | +2.70% | +1.16% | +1.16% | +3.79% | 0.1495 | NO |
| M1_OIL_DOWN_K30_RS_NEG | +12.24% | +6.13% | +6.13% | +11.38% | 0.0410 | yes |
| SRM_BEARTAPE_ACCEL_K20 † | +5.57% | +3.18% | +3.18% | +4.35% | 0.0190 | yes |
| RSLAG_OVERSOLD_K20 | +9.79% | +5.57% | +5.57% | +10.28% | 0.0580 | NO |

† single-regime row (Amendment-1 path): both the old bar and the time-shift pool are
regime-matched (risk_off dates only).

Interpretation discipline (RC-RUL-5 ruling 2, applies here unchanged, both ways): the
single-offset circular shift has low effective null degrees of freedom — each draw is one
fully-correlated portfolio — so this is a wide, conservative bar. A row that does not clear
it is not thereby shown to be calendar luck; the affirmative timing evidence is simply not
established on a time-preserving null. A row that does clear it has timing evidence that
survives temporal-structure preservation.

---

## Episode-cluster CIs (2000 draws; episodes = same-node fires chained at gaps ≤10 td)

| row | episodes | months | fires/ep mean | WR CI (LB vs 0.62) | ret_exit CI (LB vs 0) | asym CI (LB vs 1.5) |
|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | 190 | 88 | 12.41 | [0.689, 0.784] ≥ 0.62 | [+2.12%, +3.94%] > 0 | [1.439, 2.354] < 1.5 |
| B4_WASHOUT_DOLLAR_RELIEF | 440 | 116 | 1.46 | [0.643, 0.724] ≥ 0.62 | [+1.47%, +2.67%] > 0 | [1.288, 1.867] < 1.5 |
| B4_EP_SAME_OUT_CREDIT_EASE | 301 | 110 | 1.3 | [0.672, 0.776] ≥ 0.62 | [+1.48%, +2.76%] > 0 | [1.268, 1.962] < 1.5 |
| R16_VBOT_ACCELZ_NEG2_K_LOW | 335 | 114 | 1.32 | [0.633, 0.734] ≥ 0.62 | [+1.79%, +3.59%] > 0 | [1.282, 1.962] < 1.5 |
| E_DOLLAR_EASE_TLT_POS_K25 | 340 | 82 | 1.22 | [0.639, 0.742] ≥ 0.62 | [+1.65%, +2.96%] > 0 | [1.471, 2.355] < 1.5 |
| R3_B2_ACCELZ_NEG15_K20 | 415 | 143 | 1.36 | [0.664, 0.752] ≥ 0.62 | [+1.99%, +3.51%] > 0 | [1.383, 2.066] < 1.5 |
| R4_E10_OIL_EASE_K30_VIX40 | 527 | 118 | 1.45 | [0.645, 0.723] ≥ 0.62 | [+2.14%, +3.21%] > 0 | [1.292, 1.771] < 1.5 |
| M1_OIL_DOWN_K30_RS_NEG | 522 | 45 | 1.29 | [0.644, 0.732] ≥ 0.62 | [+8.21%, +16.97%] > 0 | [2.573, 4.471] ≥ 1.5 |
| SRM_BEARTAPE_ACCEL_K20 | 1079 | 16 | 1.3 | [0.651, 0.706] ≥ 0.62 | [+4.84%, +6.29%] > 0 | [1.700, 2.044] ≥ 1.5 |
| RSLAG_OVERSOLD_K20 | 703 | 50 | 1.43 | [0.591, 0.661] < 0.62 | [+5.68%, +16.03%] > 0 | [1.940, 4.453] ≥ 1.5 |

### Holdout subset (Leg-5 bar 0.58; split per tier: s=2019-12-31, m=2023-12-31)

| row | holdout fires | holdout episodes | holdout WR CI (LB vs 0.58) | holdout ret_exit CI |
|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | 669 | 53 | [0.705, 0.856] ≥ 0.58 | [+3.27%, +6.05%] |
| B4_WASHOUT_DOLLAR_RELIEF | 244 | 164 | [0.671, 0.790] ≥ 0.58 | [+2.52%, +4.65%] |
| B4_EP_SAME_OUT_CREDIT_EASE | 134 | 109 | [0.630, 0.794] ≥ 0.58 | [+0.79%, +3.53%] |
| R16_VBOT_ACCELZ_NEG2_K_LOW | 112 | 83 | [0.571, 0.760] < 0.58 | [+1.62%, +5.59%] |
| E_DOLLAR_EASE_TLT_POS_K25 | 149 | 131 | [0.635, 0.793] ≥ 0.58 | [+1.40%, +4.08%] |
| R3_B2_ACCELZ_NEG15_K20 | 146 | 110 | [0.633, 0.798] ≥ 0.58 | [+2.84%, +5.84%] |
| R4_E10_OIL_EASE_K30_VIX40 | 226 | 171 | [0.683, 0.803] ≥ 0.58 | [+2.73%, +4.60%] |
| M1_OIL_DOWN_K30_RS_NEG | 407 | 307 | [0.588, 0.708] ≥ 0.58 | [+6.90%, +19.98%] |
| SRM_BEARTAPE_ACCEL_K20 | 547 | 402 | [0.764, 0.836] ≥ 0.58 | [+10.53%, +12.68%] |
| RSLAG_OVERSOLD_K20 | 593 | 420 | [0.608, 0.695] ≥ 0.58 | [+6.19%, +23.34%] |

---

## Method notes

- Fire sets come from `get_entry_dates` on the frozen registry specs; outcomes from
  `_compute_entry_metrics` (W=25, E=21, time-exit, absolute returns) — the gauntlet's own
  machinery, unchanged.
- Episode chaining (≤10 trading-day gaps within a node, 5/7 calendar approximation) is the
  same rule used by OTA-RC-1 (gap ≤10 td) and OTA-RC-2; it is a re-check convention, not a
  new signal parameter.
- The circular time-shift placebo mirrors `scripts/research/oracle_compound_tc_recheck.py`
  (canonized for gauntlet use by RC-RUL-3 ruling 5) via
  `scripts/research/oracle_seq_tc_recheck.py`, which this script generalizes.
- Scope caveat (for the adjudicator): the episode unit is within-node (same convention as
  OTA-RC-1/OTA-RC-2), so cross-node co-firing in the same macro window is not collapsed, and
  per-node time-shift offsets are drawn independently across nodes. On tier-M (354 nodes) the
  episode counts therefore overstate independent time — the months column is the conservative
  independent-time read (tier-M rows touch only 45 / 16 / 50 calendar months). Same-instrument
  trade-off as the canonized re-checks; noted, not corrected, here.
- Per-row RNG streams are seeded deterministically from (seed, row-index) so single rows can
  be re-run without disturbing the others.
- Heavy panels are read from the main checkout's `data/` (gitignored stores; asof 2026-07-05,
  the same stores the published blocks were re-verified against).

---

## Adjudication postscript (RC-RUL-6, 2026-07-13)

Adjudicated by Fable after independent implementation review and statistical red-team. Full
ruling text: `research/TIME_CONFOUND_RECHECK_ADJUDICATION.md` RC-RUL-6. Outcome: all 10 rows
stay `screened`; affirmative time-preserving timing evidence NOT ESTABLISHED for 8/10 rows
(7 tier-S + RSLAG p=.058); M1 (p=.041) and SRM (p=.019) clears are promotion-ENABLING only,
with M1 ranked first for any future prereg; promotion stays blocked for all 10 pending a
pre-registered adequately-powered time-preserving placebo.

### Holdout coverage disclosure (RC-RUL-6 ruling 6 — required alongside any holdout CI)

The holdout table above prints episode counts but suppressed the independent-time columns the
JSON artifact carries. Corrective disclosure (holdout calendar months from
`episode_coverage.n_months_hold`):

| row | holdout episodes | holdout months |
|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | 53 | 26 |
| B4_WASHOUT_DOLLAR_RELIEF | 164 | 42 |
| B4_EP_SAME_OUT_CREDIT_EASE | 109 | 36 |
| R16_VBOT_ACCELZ_NEG2_K_LOW | 83 | 26 |
| E_DOLLAR_EASE_TLT_POS_K25 | 131 | 29 |
| R3_B2_ACCELZ_NEG15_K20 | 110 | 35 |
| R4_E10_OIL_EASE_K30_VIX40 | 171 | 40 |
| M1_OIL_DOWN_K30_RS_NEG | 307 | 25 |
| SRM_BEARTAPE_ACCEL_K20 | 402 | **4** |
| RSLAG_OVERSOLD_K20 | 420 | 28 |

**SRM_BEARTAPE_ACCEL_K20 in particular:** its holdout WR CI [0.764, 0.836] is bootstrapped
over 402 node-episodes spanning **4 calendar months / 23 distinct risk-off dates** (median 11
nodes co-firing per date, per registry `reversion.oos_holdout`). Read as 402 independent units
it is drastically anti-conservative; it must never be cited without this coverage line.

*RE-CHECK artifact, adjudicated (RC-RUL-6). No verdict was changed. Display statuses stay
`screened`. Per RC-RUL-5 ruling 5 and the time-preserving-null standing law, this sweep is the
pre-condition for any future promotion of these rows beyond display — and per RC-RUL-6 it does
not itself authorize any.*
