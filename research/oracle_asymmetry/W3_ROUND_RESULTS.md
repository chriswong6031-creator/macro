# OTA W3 — Round 1 Results (2026-07-05, corrected 2026-07-05)

**Status: PENDING FABLE ADJUDICATION**

Executed 2026-07-05 under grammar v1.2.0 (`GRAMMAR_VERSION = "1.2.0"`), frozen gates (`ORACLE_REVERSION_GATE_PREREG.md`), panel_s reconciled against A15 positive control. All 11 specs from `w3_round_batch.json` screened. Results corrected after fixing two bugs: (1) `oracle_ingest_brainstorm.py` was silently dropping `cooldown_sessions` so the prior run evaluated every spec cooldown-free — wrong entry sets for all 11 specs; (2) `_apply_cooldown` was counting Mon–Fri calendar business days via `pd.bdate_range` instead of positional trading-session gaps, which miscounts near market holidays. The prior DEST_OPP_OUT_LEADER PASS was an artifact of the cooldown-stripped run; under the corrected semantics the sole legs-1–4 passer is **SEQ_TLT_RELIEF_WASHOUT**.

## A15 Positive Control (panel reconciliation)

A15_WASHOUT_OPP_OUT_2NODE re-screened under grammar v1.2.0 to confirm panel and grammar regression. A15 is a v1.1 compound — no cooldown, no sequence — so the v1.2 additions are additive and leave its entry set byte-identical.

| total_fires | mature_n | WR | ret_exit | MFE | MAE | asym |
|---|---|---|---|---|---|---|
| 2367 | 2357 | 0.737 | +3.05% | +7.15% | -3.90% | 1.83 |

total_fires=2367 (get_entry_dates sum; used in redundancy audit); mature_n=2357 (after forward-trim removing entries within the last W=25 sessions from panel end; used for WR/asym/ret metrics). Grammar v1.2.0 regression confirmed byte-identical (additive diff; A15's all/episode_event code path is untouched).

## Leg 1-4 Screen Results (all 11 specs, `--all-pending`, with cooldown applied)

Frozen gates: Leg 1 n≥100 / Leg 2 WR≥0.62 / Leg 3 asym≥1.5 / Leg 4 ret_exit≥+1.0% AND >0 in BOTH risk_on and risk_off.

| id | family | n | WR | asym | ret_exit | ret_on | ret_off | L1 | L2 | L3 | L4 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SEQ_WASHOUT_THEN_KXD | F-SEQ | 1017 | 0.631 | 1.26 | +1.41% | +1.11% | +1.71% | P | P | **F** | P | **FAIL** |
| SEQ_VBOTTOM_ACCEL | F-SEQ | 2838 | 0.604 | 1.12 | +0.85% | +0.92% | +0.78% | P | **F** | **F** | **F** | **FAIL** |
| SEQ_CAPITULATION_PERSIST | F-SEQ | 222 | 0.568 | 0.99 | +0.44% | +1.53% | +0.02% | P | **F** | **F** | **F** | **FAIL** |
| SEQ_MTF_CONFLUENCE | F-SEQ | 1158 | 0.643 | 1.36 | +1.59% | +1.32% | +1.86% | P | P | **F** | P | **FAIL** |
| SEQ_RELIEF_THEN_TURN | F-SEQ | 587 | 0.658 | 1.37 | +1.79% | +1.21% | +2.55% | P | P | **F** | P | **FAIL** |
| **SEQ_TLT_RELIEF_WASHOUT** | **F-SEQ** | **745** | **0.672** | **1.75** | **+2.37%** | **+1.39%** | **+3.39%** | **P** | **P** | **P** | **P** | **PASS** |
| SEQ_DIP_RESUME | F-DIP | 324 | 0.543 | 0.93 | +0.15% | -0.78% | +0.84% | P | **F** | **F** | **F** | **FAIL** |
| DIP_IN_EPISODE_K40 | F-DIP | 13 | 0.538 | 0.86 | -0.31% | -2.65% | +1.16% | **F** | **F** | **F** | **F** | **FAIL** |
| DIP_IN_CONFIRMED_RET | F-DIP | 416 | 0.577 | 1.04 | +0.39% | -0.92% | +0.95% | P | **F** | **F** | **F** | **FAIL** |
| DEST_OPP_OUT_LEADER | F-DEST | 281 | 0.662 | 1.09 | +1.65% | +2.25% | +1.44% | P | P | **F** | P | **FAIL** |
| DEST_OPP_OUT_TURN | F-DEST | 378 | 0.656 | 1.24 | +1.69% | +2.00% | +1.53% | P | P | **F** | P | **FAIL** |

Regime splits (all-regime / risk_on / risk_off) for all 11 specs:

| id | all: MFE / MAE | risk_on: n / WR | risk_off: n / WR |
|---|---|---|---|
| SEQ_WASHOUT_THEN_KXD | +5.00% / −3.98% | 508 / 0.604 | 509 / 0.658 |
| SEQ_VBOTTOM_ACCEL | +4.60% / −4.11% | 1472 / 0.631 | 1366 / 0.575 |
| SEQ_CAPITULATION_PERSIST | +6.17% / −6.21% | 62 / 0.581 | 160 / 0.562 |
| SEQ_MTF_CONFLUENCE | +5.23% / −3.86% | 566 / 0.641 | 592 / 0.645 |
| SEQ_RELIEF_THEN_TURN | +4.94% / −3.61% | 333 / 0.628 | 254 / 0.697 |
| SEQ_TLT_RELIEF_WASHOUT | +5.69% / −3.26% | 381 / 0.659 | 364 / 0.687 |
| SEQ_DIP_RESUME | +4.63% / −4.95% | 139 / 0.453 | 185 / 0.611 |
| DIP_IN_EPISODE_K40 | +3.97% / −4.62% | 5 / 0.400 | 8 / 0.625 |
| DIP_IN_CONFIRMED_RET | +5.73% / −5.52% | 124 / 0.476 | 292 / 0.620 |
| DEST_OPP_OUT_LEADER | +5.88% / −5.40% | 72 / 0.764 | 209 / 0.627 |
| DEST_OPP_OUT_TURN | +5.48% / −4.42% | 130 / 0.700 | 248 / 0.633 |

## Gauntlet Legs 5-6 — SEQ_TLT_RELIEF_WASHOUT (full report)

```
PATH: STANDARD dual-regime (n_on=381, n_off=364)
Leg 1  n=745 >= 100:                PASS
Leg 2  WR=0.672 >= 0.62:           PASS
Leg 3  asym=1.747 >= 1.5:         PASS
Leg 4  ret_exit=+2.37% >= +1.0% AND on=+1.39%>0 AND off=+3.39%>0:  PASS
Leg 5  OOS holdout (split=2019-12-31): holdout_n=267 >= 100: Y, WR=0.689 >= 0.58: Y,
        sign match (dev_ret=+1.62%, hold_ret=+3.71%): Y  => PASS
Leg 6  Timing placebo (500 draws): real=+2.37% > p95=+1.16%  => PASS

Power context (W4.b — reporting only, gates untouched):
  n=745  sigma=+6.52%  MDE@80%(α=0.05)=+0.59%

*** REVERSION GAUNTLET PASS ***
```

**PENDING FABLE ADJUDICATION — not published to registry or ORACLE_REVERSION_VALIDATED.md.**

## Redundancy Audit — SEQ_TLT_RELIEF_WASHOUT

Entry-set overlap vs every published base signal (ORACLE_REVERSION_VALIDATED.md compounds), computed via `get_entry_dates` on panel_s, keyed `(node, str(date.date()))`.

SEQ_TLT_RELIEF_WASHOUT total entries: 752

| base signal | n_base | overlap | new∩base/new (contained%) | new∩base/base | verdict |
|---|---|---|---|---|---|
| A15_WASHOUT_OPP_OUT_2NODE | 2367 | 170 | **22.6%** | 7.2% | additive |
| B4_WASHOUT_DOLLAR_RELIEF | 643 | 48 | 6.4% | 7.5% | additive |
| B4_EP_SAME_OUT_CREDIT_EASE | 398 | 5 | 0.7% | 1.3% | additive |

**Maximum containment: 22.6% vs A15_WASHOUT_OPP_OUT_2NODE.** Novel fraction ≥ 77.4%. The ≥85% REDUNDANT threshold is not met for any single base signal. SEQ_TLT_RELIEF_WASHOUT is **ADDITIVE** — genuinely new entries not already covered by any single existing signal. **PENDING FABLE ADJUDICATION.**

The 22.6% overlap with A15 makes structural sense: both are rate-relief or macro-relief signals combined with sector washout, but A15 requires the washout simultaneously with ≥2 opposite-complex outflow episodes (a pure condition AND-gate), while SEQ_TLT_RELIEF_WASHOUT sequences them causally (TLT rally FIRST, then washout within 10 sessions, with cooldown=10). The sequence construction selects a distinct subset of washout entries — those that follow a rate rally — rather than the simultaneous overlap.

## W4.b MDE@80% + UNDERPOWERED-ACCRUING Classes — Failing Specs

Computed via same `get_entry_dates` path (E=21 sessions, daily ret compounding). sigma = std(ret_exit, ddof=1). MDE = (1.645+0.842) × sigma / sqrt(n). UNDERPOWERED-ACCRUING (UPA) requires ALL of: WR≥0.62, ret_exit≥+1.0%, asym≥1.5 (all point estimates in uniformly-passing direction), AND power<50% at observed effect.

| id | n | sigma | MDE@80% | mean_ret | WR | asym | UNDERPOWERED-ACCRUING |
|---|---|---|---|---|---|---|---|
| SEQ_WASHOUT_THEN_KXD | 1017 | 6.30% | 0.49% | +1.41% | 0.631 | 1.26 | NO — asym<1.5 |
| SEQ_VBOTTOM_ACCEL | 2838 | 6.35% | 0.30% | +0.85% | 0.604 | 1.12 | NO — WR<0.62, ret<1%, asym<1.5 |
| SEQ_CAPITULATION_PERSIST | 222 | 8.54% | 1.43% | +0.44% | 0.568 | 0.99 | NO — WR<0.62, ret<1%, asym<1.5 |
| SEQ_MTF_CONFLUENCE | 1158 | 6.86% | 0.50% | +1.59% | 0.643 | 1.36 | NO — asym<1.5 |
| SEQ_RELIEF_THEN_TURN | 587 | 5.61% | 0.58% | +1.79% | 0.658 | 1.37 | NO — asym<1.5 |
| SEQ_DIP_RESUME | 324 | 6.93% | 0.96% | +0.15% | 0.543 | 0.93 | NO — WR<0.62, ret<1%, asym<1.5 |
| DIP_IN_EPISODE_K40 | 13 | 5.33% | 3.68% | −0.31% | 0.538 | 0.86 | NO — n=13, all estimates below gate |
| DIP_IN_CONFIRMED_RET | 416 | 8.18% | 1.00% | +0.39% | 0.577 | 1.04 | NO — WR<0.62, ret<1%, asym<1.5 |
| DEST_OPP_OUT_LEADER | 281 | 7.95% | 1.18% | +1.65% | 0.662 | 1.09 | NO — asym<1.5 |
| DEST_OPP_OUT_TURN | 378 | 6.98% | 0.89% | +1.69% | 0.656 | 1.24 | NO — asym<1.5 |

**Zero UNDERPOWERED-ACCRUING specs.** All failing specs fail primarily on asym<1.5 (the safety gate). Point estimates are NOT uniformly above all three gate thresholds for any failing spec — the failures are substantive, not power-limited.

Key structural finding: under correct cooldown, the F-SEQ family's n drops dramatically (SEQ_WASHOUT_THEN_KXD: 8114→1017; SEQ_TLT_RELIEF_WASHOUT: 5192→745), confirming the cooldown was the dominant suppressor. The asym gate remains the binding constraint for the remaining F-SEQ fails; the sequence construction lifts WR in some cases but not the upside/downside ratio. SEQ_TLT_RELIEF_WASHOUT is the exception — it achieves asym=1.75 by causal ordering of rate-relief → washout, which concentrates entries at a more selective subset of washout events.

## Trial-Ledger Conformance

Per W3_SPEC §2: "every screen appends trial-ledger rows (mining legal because counted)." The reversion screener now writes machine-appendable rows to `reversion_trial_ledger.jsonl` alongside `registry.jsonl` in the compounds dir. The W3 batch screen (11 compounds) appended 11 rows to this file. Each row records: compound_id, grammar_version, params_hash, screened_at, window, exit_sessions, n, WR, asym, ret_exit, per-leg PASS/FAIL verdicts. The trial ledger is append-only; subsequent rounds add rows without overwriting. The tier-1 `trial_ledger.jsonl` (63d promotion pipeline) is not touched.

## Summary

| category | count | ids |
|---|---|---|
| Screened | 11 | all W3 batch specs |
| Legs 1-4 PASS | 1 | SEQ_TLT_RELIEF_WASHOUT |
| Gauntlet PASS | 1 | SEQ_TLT_RELIEF_WASHOUT |
| Redundancy audit ADDITIVE | 1 | SEQ_TLT_RELIEF_WASHOUT (max 22.6% vs A15) |
| UNDERPOWERED-ACCRUING | 0 | — |
| Primary fail gate | asym<1.5 | 8 of 10 failing specs (all F-SEQ excl. passer + both F-DEST) |

**PENDING FABLE ADJUDICATION.** Publication to `data/oracle/compounds/registry.jsonl` (reversion block) and `ORACLE_REVERSION_VALIDATED.md` requires Fable adjudication per the loop discipline. This agent does NOT publish; it does NOT modify the registry or the validated doc.

## Corrections from Prior Run

The initial W3_ROUND_RESULTS.md (2026-07-05) was void — it reported results from a cooldown-free evaluation due to two bugs:

1. **Blocker (ingest drops cooldown):** `scripts/oracle_ingest_brainstorm.py` L137 built the row dict without carrying `cooldown_sessions`. Result: all 11 specs evaluated with n_effective = no-cooldown n. Fixed: carry `cooldown_sessions` through ingest.

2. **Major (bdate_range vs sessions):** `_apply_cooldown` used `pd.bdate_range` to count business days, which counts market holidays as trading sessions. Fixed: count positional gap within the node's own panel date index via `searchsorted`.

Prior headline result (DEST_OPP_OUT_LEADER PASS) is void. The corrected sole passer is SEQ_TLT_RELIEF_WASHOUT (mechanism: rate-relief FIRST, then sector washout — ordered causally with cooldown=10).

**Rebuttal — finding "DIP_IN_CONFIRMED_RET entry count mismatch (n=641 vs 647)":** The auditor's 641 was computed using `confirmed_date <= t <= exhausted_date` (restricting to still-active episodes). Adding an `exhausted_date` filter to the `confirmed` tier would change A3_OPP_OUT_RS_REPAIR and A4_SAME_OUT_SURVIVOR entry sets, violating the W3_SPEC §1.3 byte-identity requirement for v1.1 compounds. The grammar docstring specifies `within_sessions` as the lookback window for episode onset; there is no "episode must still be active" clause in the v1.2 grammar. The delta of 6 is from the auditor applying a stricter (non-spec-mandated) filter. The current implementation is internally consistent and correct per the grammar. Finding rebutted; no code change.
