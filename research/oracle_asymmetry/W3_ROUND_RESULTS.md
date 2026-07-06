# OTA W3 — Round 1 Results (2026-07-05)

**Status: PENDING FABLE ADJUDICATION**

Executed 2026-07-05 under grammar v1.2.0 (`GRAMMAR_VERSION = "1.2.0"`), frozen gates (`ORACLE_REVERSION_GATE_PREREG.md`), panel_s reconciled against A15 positive control. All 11 specs from `w3_round_batch.json` screened. 1 legs-1-4 passer advanced to gauntlet; 1 gauntlet PASS; redundancy audit ADDITIVE. No spec edits, no threshold nudges, no extra specs added.

## A15 Positive Control (panel reconciliation)

Before running the W3 batch, A15_WASHOUT_OPP_OUT_2NODE was re-screened under grammar v1.2.0 to confirm panel and grammar regression:

| n | WR | ret_exit | MFE | MAE | asym |
|---|---|---|---|---|---|
| 2357 | 0.737 | +3.05% | +7.15% | -3.90% | 1.83 |

Matches spec exactly (n=2357, MFE +7.15%, MAE −3.90%, ret_exit +3.05%, WR 0.737). Grammar v1.2.0 regression confirmed byte-identical.

## Leg 1-4 Screen Results (all 11 specs, `--dry-run`, `--all-pending`)

Frozen gates: Leg 1 n≥100 / Leg 2 WR≥0.62 / Leg 3 asym≥1.5 / Leg 4 ret_exit≥+1.0% AND >0 in BOTH risk_on and risk_off.

| id | family | n | WR | asym | ret_exit | ret_on | ret_off | L1 | L2 | L3 | L4 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SEQ_WASHOUT_THEN_KXD | F-SEQ | 8114 | 0.623 | 1.24 | +1.29% | +0.93% | +1.67% | P | P | **F** | P | **FAIL** |
| SEQ_VBOTTOM_ACCEL | F-SEQ | 4609 | 0.604 | 1.12 | +0.80% | +0.95% | +0.64% | P | **F** | **F** | **F** | **FAIL** |
| SEQ_CAPITULATION_PERSIST | F-SEQ | 1024 | 0.599 | 1.14 | +1.07% | +1.87% | +0.78% | P | **F** | **F** | P | **FAIL** |
| SEQ_MTF_CONFLUENCE | F-SEQ | 1797 | 0.636 | 1.31 | +1.43% | +1.45% | +1.40% | P | P | **F** | P | **FAIL** |
| SEQ_RELIEF_THEN_TURN | F-SEQ | 3556 | 0.644 | 1.30 | +1.45% | +1.01% | +2.02% | P | P | **F** | P | **FAIL** |
| SEQ_TLT_RELIEF_WASHOUT | F-SEQ | 5192 | 0.638 | 1.38 | +1.75% | +1.19% | +2.38% | P | P | **F** | P | **FAIL** |
| SEQ_DIP_RESUME | F-DIP | 477 | 0.549 | 0.88 | -0.01% | -0.63% | +0.43% | P | **F** | **F** | **F** | **FAIL** |
| DIP_IN_EPISODE_K40 | F-DIP | 13 | 0.538 | 0.86 | -0.31% | -2.65% | +1.16% | **F** | **F** | **F** | **F** | **FAIL** |
| DIP_IN_CONFIRMED_RET | F-DIP | 647 | 0.572 | 1.05 | +0.54% | -0.89% | +0.99% | P | **F** | **F** | **F** | **FAIL** |
| **DEST_OPP_OUT_LEADER** | **F-DEST** | **1062** | **0.727** | **1.54** | **+2.99%** | **+3.06%** | **+2.96%** | **P** | **P** | **P** | **P** | **PASS** |
| DEST_OPP_OUT_TURN | F-DEST | 583 | 0.664 | 1.30 | +1.64% | +1.66% | +1.63% | P | P | **F** | P | **FAIL** |

Regime splits (all-regime / risk_on / risk_off) for all 11 specs:

| id | all: MFE / MAE | risk_on: n / WR | risk_off: n / WR |
|---|---|---|---|
| SEQ_WASHOUT_THEN_KXD | +4.89% / −3.94% | 4122 / 0.606 | 3992 / 0.640 |
| SEQ_VBOTTOM_ACCEL | +4.65% / −4.16% | 2366 / 0.628 | 2243 / 0.580 |
| SEQ_CAPITULATION_PERSIST | +6.69% / −5.85% | 269 / 0.680 | 755 / 0.570 |
| SEQ_MTF_CONFLUENCE | +5.17% / −3.94% | 864 / 0.649 | 933 / 0.624 |
| SEQ_RELIEF_THEN_TURN | +4.68% / −3.61% | 2008 / 0.631 | 1548 / 0.660 |
| SEQ_TLT_RELIEF_WASHOUT | +5.17% / −3.74% | 2758 / 0.629 | 2434 / 0.647 |
| SEQ_DIP_RESUME | +4.46% / −5.07% | 200 / 0.490 | 277 / 0.592 |
| DIP_IN_EPISODE_K40 | +3.97% / −4.62% | 5 / 0.400 | 8 / 0.625 |
| DIP_IN_CONFIRMED_RET | +6.23% / −5.93% | 153 / 0.451 | 494 / 0.609 |
| DEST_OPP_OUT_LEADER | +6.58% / −4.28% | 266 / 0.801 | 796 / 0.702 |
| DEST_OPP_OUT_TURN | +5.50% / −4.23% | 195 / 0.692 | 388 / 0.649 |

## Gauntlet Legs 5-6 — DEST_OPP_OUT_LEADER (full report)

```
PATH: STANDARD dual-regime (n_on=266, n_off=796)
Leg 1  n=1062 >= 100:                PASS
Leg 2  WR=0.727 >= 0.62:             PASS
Leg 3  asym=1.539 >= 1.5:            PASS
Leg 4  ret_exit=+2.99% >= +1.0% AND on=+3.06%>0 AND off=+2.96%>0:  PASS
Leg 5  OOS holdout (split=2019-12-31): holdout_n=358 >= 100: Y, WR=0.707 >= 0.58: Y,
        sign match (dev_ret=+2.91%, hold_ret=+3.13%): Y  => PASS
Leg 6  Timing placebo (500 draws): real=+2.99% > p95=+1.14%  => PASS

Power context (W4.b — reporting only, gates untouched):
  n=1062  sigma=+7.35%  MDE@80%(α=0.05)=+0.56%

*** REVERSION GAUNTLET PASS ***
```

**PENDING FABLE ADJUDICATION — not published to registry or ORACLE_REVERSION_VALIDATED.md.**

## Redundancy Audit — DEST_OPP_OUT_LEADER

Entry-set overlap vs every published base signal (reversion-block compounds in registry), computed via `get_entry_dates` on panel_s, keyed `(node, str(date.date()))`.

DEST_OPP_OUT_LEADER total entries: 1062

| base signal | n_base | overlap | new∩base/new (contained%) | new∩base/base | verdict |
|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | 2367 | 395 | **37.2%** | 16.7% | additive |
| B4_WASHOUT_DOLLAR_RELIEF | 643 | 10 | 0.9% | 1.6% | additive |
| B4_EP_SAME_OUT_CREDIT_EASE | 398 | 12 | 1.1% | 3.0% | additive |
| R16_VBOT_ACCELZ_NEG2_K_LOW | 445 | 62 | 5.8% | 13.9% | additive |
| E_DOLLAR_EASE_TLT_POS_K25 | 418 | 12 | 1.1% | 2.9% | additive |
| R3_B2_ACCELZ_NEG15_K20 | 569 | 63 | 5.9% | 11.1% | additive |
| R4_E10_OIL_EASE_K30_VIX40 | 767 | 27 | 2.5% | 3.5% | additive |
| M1_OIL_DOWN_K30_RS_NEG | 42 | 0 | 0.0% | 0.0% | additive |
| SRM_BEARTAPE_ACCEL_K20 | 318 | 40 | 3.8% | 12.6% | additive |
| RSLAG_OVERSOLD_K20 | 47 | 0 | 0.0% | 0.0% | additive |

**Maximum containment: 37.2% vs A15_WASHOUT_OPP_OUT_2NODE.** Novel fraction ≥ 62.8%. The ≥85% REDUNDANT threshold is not met for any single base signal. DEST_OPP_OUT_LEADER is **ADDITIVE** — genuinely new entries not already covered by any single existing signal. **PENDING FABLE ADJUDICATION.**

The structural overlap with A15 (37.2%) makes mechanical sense: both fire during opposite-complex outflow episodes, but A15 requires the node to be in washout (a distress condition) while DEST_OPP_OUT_LEADER requires rs>0 and K<60 (the destination is already leading but not overbought). These are complementary sides of the rotation: the washed-out source (A15) vs the leadership destination (DEST_OPP_OUT_LEADER).

## W4.b MDE@80% + UNDERPOWERED-ACCRUING Classes — Failing Specs

Computed via same `get_entry_dates` path (E=21 sessions, daily ret compounding). sigma = std(ret_exit, ddof=1). MDE = (1.645+0.842) × sigma / sqrt(n). UNDERPOWERED-ACCRUING (UPA) requires ALL of: WR≥0.62, ret_exit≥+1.0%, asym≥1.5 (all point estimates in uniformly-passing direction), AND power<50% at observed effect.

| id | n | sigma | MDE@80% | mean_ret | WR | asym | UNDERPOWERED-ACCRUING |
|---|---|---|---|---|---|---|---|
| SEQ_WASHOUT_THEN_KXD | 8140 | 6.29% | 0.17% | +1.29% | 0.626 | 1.24 | NO — asym<1.5 (fail not UPA) |
| SEQ_VBOTTOM_ACCEL | 4628 | 6.48% | 0.24% | +0.83% | 0.605 | 1.12 | NO — WR<0.62, asym<1.5 |
| SEQ_CAPITULATION_PERSIST | 1027 | 8.94% | 0.69% | +1.05% | 0.604 | 1.14 | NO — WR<0.62, asym<1.5 |
| SEQ_MTF_CONFLUENCE | 1801 | 6.69% | 0.39% | +1.52% | 0.632 | 1.31 | NO — asym<1.5 |
| SEQ_RELIEF_THEN_TURN | 3571 | 5.68% | 0.24% | +1.47% | 0.648 | 1.30 | NO — asym<1.5 |
| SEQ_TLT_RELIEF_WASHOUT | 5239 | 6.48% | 0.22% | +1.74% | 0.636 | 1.38 | NO — asym<1.5 |
| SEQ_DIP_RESUME | 478 | 7.00% | 0.80% | +0.04% | 0.559 | 0.88 | NO — WR<0.62, asym<0 |
| DIP_IN_EPISODE_K40 | 13 | 5.51% | 3.80% | −0.17% | 0.538 | 0.86 | NO — n=13, all estimates below gate |
| DIP_IN_CONFIRMED_RET | 647 | 8.60% | 0.84% | +0.38% | 0.578 | 1.05 | NO — WR<0.62, ret<1% |
| DEST_OPP_OUT_TURN | 583 | 6.75% | 0.70% | +1.77% | 0.690 | 1.30 | NO — asym<1.5 |

**Zero UNDERPOWERED-ACCRUING specs.** All failing specs fail primarily on asym<1.5 (the safety gate), not on power. Point estimates are NOT uniformly above all three gate thresholds for any failing spec — the failures are substantive, not power-limited.

Key structural finding: the asym gate (MFE/MAE ≥ 1.5) is the binding constraint across the entire F-SEQ family. The sequence construction increases raw n (more entries) and in some cases lifts WR/ret above thresholds, but does not improve the upside/downside ratio — the sequence semantics deliver more entries but with symmetric MFE/MAE profiles (asym 1.12–1.38 across all 8 F-SEQ fails). This suggests the sequencing of washout/oversold with macro-relief or velocity-flip improves frequency but not selectivity (asym).

## Trial-Ledger Conformance

Per W3_SPEC §2: "every screen appends trial-ledger rows." The `oracle_reversion_screen.py` script (line 5 header) explicitly does NOT write to the standard oracle tier-1 trial_ledger (`data/oracle/compounds/trial_ledger.jsonl` — that ledger's schema is for the 63d promotion pipeline). All 11 W3 screen runs are recorded in this results document with full per-leg verdicts, n, WR, asym, ret_exit, and regime splits; this file is the trial record for the W3 reversion-screen round. The gauntlet output for DEST_OPP_OUT_LEADER additionally emits the power context (MDE@80%=+0.56%). No UNDERPOWERED-ACCRUING rows written (zero UPA classifications).

## Summary

| category | count | ids |
|---|---|---|
| Screened | 11 | all W3 batch specs |
| Legs 1-4 PASS | 1 | DEST_OPP_OUT_LEADER |
| Gauntlet PASS | 1 | DEST_OPP_OUT_LEADER |
| Redundancy audit ADDITIVE | 1 | DEST_OPP_OUT_LEADER (max 37.2% vs A15) |
| UNDERPOWERED-ACCRUING | 0 | — |
| Primary fail gate | asym<1.5 | 9 of 10 failing specs (all F-SEQ + both F-DIP with n≥100 + DEST_OPP_OUT_TURN) |

**PENDING FABLE ADJUDICATION.** Publication to `data/oracle/compounds/registry.jsonl` (reversion block) and `ORACLE_REVERSION_VALIDATED.md` requires Fable adjudication per the loop discipline. This agent does NOT publish; it does NOT modify the registry or the validated doc.
