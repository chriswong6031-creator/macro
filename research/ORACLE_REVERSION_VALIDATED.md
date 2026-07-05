# Oracle Reversion — Validated Base (growing)

Signals that PASS all 6 legs of the frozen reversion gauntlet (`research/ORACLE_REVERSION_GATE_PREREG.md`) on the **time-exit** (21 sessions ≈ operator's ~20-30d hold). Display-only; apply a transaction-cost haircut before any live weight. Append new full-passes here (id · rule · asym/WR/ret/n · OOS · date · source-batch).

| id | entry_rule | asym | WR | ret_exit | n | OOS holdout | date | batch |
|---|---|---|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | washout_w>0 ∧ ep(out/onset/opposite/w20/min2) | 1.83 | 0.74 | +3.05% | 2357 | +4.60% / WR .78 | 2026-07-05 | (screen leads) |
| B4_WASHOUT_DOLLAR_RELIEF | washout_w>0 ∧ dollar_chg_10d↓0 ∧ rs>−0.04 | 1.55 | 0.68 | +2.07% | 641 | +3.57% / WR .73 | 2026-07-05 | batch4 |
| B4_EP_SAME_OUT_CREDIT_EASE | ep(out/onset/same/w20/min1) ∧ hy_oas_chg_10d↓0 ∧ stochrsi_w_k<60 | 1.56 | 0.72 | +2.12% | 392 | +2.28% / WR .72 | 2026-07-05 | batch4 |

**Winning shape:** capitulation/washout + macro-relief timer (credit-spread peaking `hy_oas_chg_10d crossed_below 0`, dollar/oil/rate relief) or oscillator turn from oversold in a mid-VIX band. Note the cross-asset columns (dollar/credit) that were dead on the 63d ruler are LIVE here.

**Open near-miss to monitor:** `B4_EP_OUT_TLT_RELIEF_STOCH30` — asym 2.80 / WR 0.73 but n=77 (fails leg-1 n≥100); would be the safest of all if it accrues entries.

**Caveat (exit sensitivity):** all passes are on the 21d time-exit. On the tighter first-2D-StochRSI-cross exit (~12d hold) WR drops ~0.10 and these fall below the 0.62 bar — the operator's real hold (~20-30d) is closer to the time-exit, so the time-exit verdict stands, but confirm the true exit before live sizing.
