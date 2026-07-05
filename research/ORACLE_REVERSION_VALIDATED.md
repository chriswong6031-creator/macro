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
| R3_B2_ACCELZ_NEG15_K20 ‡ | accel_z↑−1.5 ∧ stochrsi_w_k<20 | 1.69 | 0.71 | +2.79% | 565 | +4.36% / WR .72 | 2026-07-05 | round3 (auto) |

† **Correlated, not independent.** E_DOLLAR_EASE_TLT_POS_K25 shares ~67% of its entries with B4_WASHOUT_DOLLAR_RELIEF (same `dollar_chg_10d↓0` root); its additive value is the ~33% of dual dollar+rate-relief entries that are *not* washouts. Count it as the **dollar-relief cluster** {B4_WASHOUT_DOLLAR_RELIEF, E_DOLLAR_EASE_TLT_POS_K25} ≈ 1.3 independent bets.

‡ **V-bottom family sibling.** R3_B2_ACCELZ_NEG15_K20 shares ~42% of its entries with R16 (same accel V-bottom mechanism; looser accel −1.5, deeper K<20) but ~46% are novel — additive, not a subset. Count {R16, R3_B2} as the **V-bottom cluster** ≈ 1.5 independent bets. → Net: the 6-row base is ≈ **4 independent mechanisms** (episode-routing · dollar-relief · credit-relief · V-bottom). Do NOT size as 6 orthogonal signals.

**Winning shapes (independent mechanisms):** (1) **washout + episode-routing** (A15) — capitulation with cross-complex displacement; (2) **washout/oscillator + macro-relief timer** — dollar-relief cluster and credit-relief (B4_EP_SAME_OUT_CREDIT_EASE); the cross-asset columns dead on the 63d ruler are LIVE here; (3) **V-bottom without washout** (R16, R3_B2) — the trend's *second derivative* repairs from an extreme (`accel_z↑`) while StochRSI still oversold. Genuinely orthogonal spine: A15 / V-bottom / credit-relief; the dollar-relief pair is one mechanism.

**Redundancy audits (gauntlet-PASS ≠ additive — measured on `get_entry_dates`, the gauntlet's own entry definition):**
- *R2:* `E_DOLLAR_EASE_TLT_POS_WASHOUT` passed (n=311, asym 1.86, OOS +3.35%) but is a **100% subset of B4_WASHOUT_DOLLAR_RELIEF** (312/313 inside it) → NOT published.
- *R3:* `R3_B6_ACCELZ_NEG2_K30_VIX40` passed (n=394, asym 1.54) but is a **100% subset of R16** (the VIX>0.40 gate only removes R16 entries) → NOT published. `R3_B2` passed and is **additive** (46% novel) → published. The novelty-vs-base audit is now an in-loop step every round.

**Open near-misses for Round 4 (fail only on Leg-5 holdout n<100, elite OOS WR + sign):** `R3_A4_YC_UNINVERT_K50` (yield-curve un-inversion + K<50: asym 1.91 / WR .75, holdout n=30 — un-inversion is structurally rare post-2019; likely an OOS-capped NULL, worth one broader-trigger try); `R3_B8_ACCELZ_NEG2_K20` (asym 1.75 / WR .71, holdout n=81 — try K<25); `R3_C5_HY_OAS_PEAK_VEL_NEG_K15` (credit peak + vel<0 + K<15: asym 1.62 / WR .71, holdout n=82 — try K<20); oil-relief (`oil_ret_10d↓0 ∧ K<30`: asym 1.47, just under floor). **R4 priority = get a CURVE / CREDIT / OIL signal over the n-floor (orthogonal, under-represented), NOT more V-bottom variants** (that family already has R16 + R3_B2).

**⚠ Gate-design question — PENDING human/Fable ruling (do NOT amend the gate unilaterally):** the **bear-tape family** (`spy_above_200d==0 ∧ …`) is risk-off-ONLY *by construction* (risk_off ⊇ spy_above_200d==0), so it can never satisfy Leg 4's dual-regime requirement (ret>0 in BOTH regimes) — not because it fails in risk-on, but because it has zero risk-on entries by definition. R3's 10-spec D-family (WR .62–.69) was categorically blocked here. Admitting structurally-single-regime signals — e.g. by leaning on Leg-6's timing placebo as the within-regime control instead of Leg-4's dual-regime — is a pre-registration amendment, i.e. an escalation-enabling change. Per house law (gates sacred; LLMs never originate escalations) that is a human/Fable decision. Family stays **blocked** until ruled.

**Exit horizon (operator-ratified 2026-07-05):** the operator confirmed **~20-25 sessions is the optimal hold** ("weekly cycles last 20-25 days"); exits are holistic (signs of topping / failed cycle), not a mechanical 2D-StochRSI cross. So the **21d time-exit is the correct primary ruler**, not merely "closer." The tighter first-2D-StochRSI-cross exit (~12d) clips WR ~0.10 because it exits *before* the operator's cycle completes — it is a sensitivity check, not the target. Costs still bite short-horizon signals: apply a transaction-cost haircut before live sizing.
