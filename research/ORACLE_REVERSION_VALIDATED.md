# Oracle Reversion — Validated Base (growing)

Signals that PASS all 6 legs of the frozen reversion gauntlet (`research/ORACLE_REVERSION_GATE_PREREG.md`) on the **time-exit** (21 sessions ≈ operator's ~20-25d hold). Display-only; apply a transaction-cost haircut before any live weight. Append new full-passes here (id · rule · asym/WR/ret/n · OOS · date · source-batch).

**PUBLISHED:** all rows below are landed in the durable compound registry (`data/oracle/compounds/registry.jsonl`) with a `reversion` validation block (gauntlet=PASS + per-regime + OOS + placebo, re-verified on a fresh panel rebuild 2026-07-05). Status stays `screened` — the durable registry is the publish target; promotion to any live/escalating surface still requires Fable adjudication (and the existing 63d promotion_scan is the *wrong* ruler for these, so a reversion promotion track is a separate build).

| id | entry_rule | asym | WR | ret_exit | n | OOS holdout | date | batch |
|---|---|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | washout_w>0 ∧ ep(out/onset/opposite/w20/min2) | 1.83 | 0.74 | +3.05% | 2357 | +4.60% / WR .78 | 2026-07-05 | (screen leads) |
| B4_WASHOUT_DOLLAR_RELIEF | washout_w>0 ∧ dollar_chg_10d↓0 ∧ rs>−0.04 | 1.55 | 0.68 | +2.07% | 641 | +3.57% / WR .73 | 2026-07-05 | batch4 |
| B4_EP_SAME_OUT_CREDIT_EASE | ep(out/onset/same/w20/min1) ∧ hy_oas_chg_10d↓0 ∧ stochrsi_w_k<60 | 1.56 | 0.72 | +2.12% | 392 | +2.28% / WR .72 | 2026-07-05 | batch4 |
| R16_VBOT_ACCELZ_NEG2_K_LOW | accel_z↑−2 ∧ stochrsi_w_k<30 | 1.58 | 0.68 | +2.70% | 442 | +3.62% / WR .67 | 2026-07-05 | round1 (auto) |
| E_DOLLAR_EASE_TLT_POS_K25 † | dollar_chg_10d↓0 ∧ tlt_ret_10d>0 ∧ stochrsi_w_k<25 | 1.84 | 0.69 | +2.31% | 416 | +2.77% / WR .72 | 2026-07-05 | round2 (auto) |

† **Correlated, not independent.** E_DOLLAR_EASE_TLT_POS_K25 shares ~67% of its entries with B4_WASHOUT_DOLLAR_RELIEF (same `dollar_chg_10d↓0` root); its additive value is the ~33% of dual dollar+rate-relief entries that are *not* washouts. Count it as a member of the **dollar-relief cluster** {B4_WASHOUT_DOLLAR_RELIEF, E_DOLLAR_EASE_TLT_POS_K25}, ~1.3 independent bets — do NOT treat the 5-row base as 5 orthogonal signals when sizing.

**Winning shapes (independent mechanisms):** (1) **washout + episode-routing** (A15) — capitulation with cross-complex displacement; (2) **washout/oscillator + macro-relief timer** — dollar-relief cluster (B4_WASHOUT_DOLLAR_RELIEF, E_...K25) and credit-relief (B4_EP_SAME_OUT_CREDIT_EASE); the cross-asset columns dead on the 63d ruler are LIVE here; (3) **V-bottom without washout** (R16) — the trend's *second derivative* repairs from a statistical extreme (`accel_z↑-2`) while StochRSI still oversold. The genuinely orthogonal spine is A15 / R16 / credit-relief; the dollar-relief pair is one mechanism.

**Redundancy audit (R2, 2026-07-05):** `E_DOLLAR_EASE_TLT_POS_WASHOUT` (`dollar↓0 ∧ tlt>0 ∧ washout_w>0`) *passed the gauntlet* (n=311, asym 1.86, WR .68, OOS +3.35%) but is a **100% subset of B4_WASHOUT_DOLLAR_RELIEF** (312/313 entries inside it) — the TLT leg confirms B4 but adds zero new entries, so it is **NOT published** (would inflate apparent breadth). Overlap is measured on `get_entry_dates`, the same entry definition the gauntlet uses. Lesson: gauntlet-PASS ≠ additive — audit entry-overlap vs the live base before publishing.

**Open near-misses for Round 3 (elite asym/WR, fail only on n / one leg):** `R27/C_CURVE_YC0_K50` (yield-curve un-inversion + K<50: asym 1.74 / WR .69, n=85 — un-inversion is structurally rare, needs macro-conditioning not just a looser K); `B_DEEP_ACCELZ_NEG15_K30` (accel_z↑-1.5 + K<30: asym 1.48 — 0.02 under the floor, n=746; add a VIX-regime gate to lift asym); `E_HY_OAS_PEAK_VEL_NEG_K20` (credit peak + vel<0 + K<20: asym 1.48, risk_off asym 1.52). Diversification priority for R3: **orthogonal** mechanisms (curve, credit, bear-tape regime-flip), NOT more dollar-relief variants.

**Exit horizon (operator-ratified 2026-07-05):** the operator confirmed **~20-25 sessions is the optimal hold** ("weekly cycles last 20-25 days"); exits are holistic (signs of topping / failed cycle), not a mechanical 2D-StochRSI cross. So the **21d time-exit is the correct primary ruler**, not merely "closer." The tighter first-2D-StochRSI-cross exit (~12d) clips WR ~0.10 because it exits *before* the operator's cycle completes — it is a sensitivity check, not the target. Costs still bite short-horizon signals: apply a transaction-cost haircut before live sizing.
