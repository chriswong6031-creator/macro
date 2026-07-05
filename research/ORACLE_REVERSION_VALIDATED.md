# Oracle Reversion — Validated Base (growing)

Signals that PASS all 6 legs of the frozen reversion gauntlet (`research/ORACLE_REVERSION_GATE_PREREG.md`) on the **time-exit** (21 sessions ≈ operator's ~20-25d hold). Display-only; apply a transaction-cost haircut before any live weight. Append new full-passes here (id · rule · asym/WR/ret/n · OOS · date · source-batch).

**PUBLISHED:** all rows below are landed in the durable compound registry (`data/oracle/compounds/registry.jsonl`) with a `reversion` validation block (gauntlet=PASS + per-regime + OOS + placebo, re-verified on a fresh panel rebuild 2026-07-05). Status stays `screened` — the durable registry is the publish target; promotion to any live/escalating surface still requires Fable adjudication (and the existing 63d promotion_scan is the *wrong* ruler for these, so a reversion promotion track is a separate build).

| id | entry_rule | asym | WR | ret_exit | n | OOS holdout | date | batch |
|---|---|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | washout_w>0 ∧ ep(out/onset/opposite/w20/min2) | 1.83 | 0.74 | +3.05% | 2357 | +4.60% / WR .78 | 2026-07-05 | (screen leads) |
| B4_WASHOUT_DOLLAR_RELIEF | washout_w>0 ∧ dollar_chg_10d↓0 ∧ rs>−0.04 | 1.55 | 0.68 | +2.07% | 641 | +3.57% / WR .73 | 2026-07-05 | batch4 |
| B4_EP_SAME_OUT_CREDIT_EASE | ep(out/onset/same/w20/min1) ∧ hy_oas_chg_10d↓0 ∧ stochrsi_w_k<60 | 1.56 | 0.72 | +2.12% | 392 | +2.28% / WR .72 | 2026-07-05 | batch4 |
| R16_VBOT_ACCELZ_NEG2_K_LOW | accel_z↑−2 ∧ stochrsi_w_k<30 | 1.58 | 0.68 | +2.70% | 442 | +3.62% / WR .67 | 2026-07-05 | round1 (auto) |

**Winning shapes:** (1) capitulation/washout + macro-relief timer (credit-spread peaking `hy_oas_chg_10d crossed_below 0`, dollar/oil/rate relief) — the cross-asset columns that were dead on the 63d ruler are LIVE here. (2) **NEW family (R16): V-bottom without washout** — the trend's *second derivative* repairs from a statistical extreme (`accel_z crossed_above -2`) while StochRSI is still oversold (`<30`). R16 is mechanism-distinct from the washout cluster, so it genuinely diversifies the base rather than re-milling the same shape.

**Open near-misses to monitor (elite asym/WR, fail only on n):** `B4_EP_OUT_TLT_RELIEF_STOCH30` (asym 2.80 / WR 0.73, n=77); `R27_CURVE_YC_CROSS0_K_LOW` (yield-curve un-inversion + K<40: asym 2.01 / WR .73, n=62); `R31_VOL_BAND_K20_VIX_MID` (K↑20 in mid-VIX band: WR .73 / asym 1.82 dev-set, killed by OOS n=74<100). All would clear the gate if a looser threshold grows n above the OOS floor — top of the Round-2 list.

**Exit horizon (operator-ratified 2026-07-05):** the operator confirmed **~20-25 sessions is the optimal hold** ("weekly cycles last 20-25 days"); exits are holistic (signs of topping / failed cycle), not a mechanical 2D-StochRSI cross. So the **21d time-exit is the correct primary ruler**, not merely "closer." The tighter first-2D-StochRSI-cross exit (~12d) clips WR ~0.10 because it exits *before* the operator's cycle completes — it is a sensitivity check, not the target. Costs still bite short-horizon signals: apply a transaction-cost haircut before live sizing.
