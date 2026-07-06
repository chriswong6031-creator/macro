# P1.5 Continuation Partition — RESULTS (v2, ROUND 2 — DEFECT-CORRECTED RE-RUN)

**PRIMARY VERDICT: H-MISLABEL**

*|Δ|=0.0279 < 5pp (not materially different) — H-MISLABEL first disjunct.*

---

## In plain English

Some names reach the buy board because their weekly trend already turned up weeks ago (a continuation move), not because they are at a fresh bottom. This study asks whether those continuation names are good, bad, or just mislabeled entries. Reading the production replay log on the correct alignment-tier column, continuation names (ARMED tier, weekly already rising) hit the clean-liftoff target — up 8% before dropping 5% within 21 trading days — 30.7% of the time, versus 33.4% for fresh-bottom PRIME entries. That is a gap of -2.8 percentage points — smaller than the 5-point bar the pre-registration set for a material difference. So these names are NOT worse entries; they are just labeled the same as fresh-bottom setups. The registered fix is a label, not a gate or rank change: give continuation names an explicit 'continuation' lane on the board so users see they are a different structural type. No name is removed (additive-lanes law R7).

---

## Round-1 defect and fix

**Round-1 (Sonnet) run was BOUNCED by conformance review (BLOCKING finding B1).**

- **Defect:** the round-1 script built the partition arms on the `tier_cascade` column (confluence cascade, values `T1/T2/T3`) with a silent, undocumented remap `T1 → PRIME`, `T2 → ARMED`. The PREREG §3/§9 registers the arms on the **alignment tier** whose literal values are `PRIME / ARMED / APPROACHING` — in this parquet that is the **`align_tier`** column (canonical in sibling study P1.1, ordinal APPROACHING=0/ARMED=1/PRIME=2). The two columns do **not** map (see calibration crosstab).
- **Consequence:** round-1 reported Δ=−5.49pp on the mis-specified arms, hit a case the §6 table does not cover, and escalated a **manufactured** 'PREREG decision-table gap' as an AMBIGUOUS blocker to Fable. That gap does not exist on the registered column.
- **Fix (this v2 run):** partition on `align_tier` with its literal values; identify ARMED-admitted continuation fires exactly as registered (`align_tier=='ARMED'` AND `weekly_phase=='rising'`); re-run T1–T5 and BH (m=5); re-apply the §6 decision table verbatim.
- All statistical machinery (Wilson CI, episode-clustered block bootstrap n=5000, BH) is carried over unchanged — the reviewer verified the round-1 arithmetic reproduced to <0.01%; only the partition INPUTS were wrong.

---

## Calibration — align_tier × tier_cascade crosstab (verdict-grade fires)

The two tier columns are structurally different constructs. `tier_cascade` T1 holds 620 ARMED + 1,075 APPROACHING rows; T2 holds 1,745 PRIME rows — the round-1 remap was wrong. The arms in this study are defined on `align_tier` (the row axis below).

| align_tier \ tier_cascade | T1 | T2 | T3 |
|---|---|---|---|
| **APPROACHING** | 1075 | 2100 | 991 |
| **ARMED** | 620 | 883 | 249 |
| **PRIME** | 3625 | 1745 | 78 |
| **nan** | 17696 | 19497 | 1380 |

*Rows with `align_tier` NaN (38,573 fires) are board-non-relevant fires and are outside both PREREG arms by construction (arms require `align_tier ∈ {ARMED, PRIME}`).*

---

## Preamble (conformance)

- Run label: **round 2 — defect-corrected re-run**
- Era law: **P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)** + §6 v1.1 amendments (2026-07-05)
- Partition axis: **`align_tier`** (literal PRIME/ARMED/APPROACHING) — PREREG §3/§9
- Effective verdict window (replay-data boundary): **2022-06-30 → 2026-07-02** (§6 amdt 1: 250-bar MTF warmup)
- Last-graded fire signal_date: **2025-12-29** (fires stop ~6mo before the data boundary because the 21-day forward horizon must fit — A2 reconciliation)
- Canonical input: `data/replay/replay_boarded.parquet`
- survivor_bias=False rows (unstamped, all Massive-sourced): 961,656
- survivor_bias=True rows excluded: 0 (none — pre-2021 rows absent from this parquet)
- horizon_censored fires excluded from primary: 0
- verdict_grade=True fires total (after horizon_censored exclusion): 49,939
- Unstamped price_source census: {'massive': 961656}

---

## T1 Primary Comparison — ARMED-continuation vs PRIME bottoming

| Arm | n fires | n episodes | P(clean8_21) | Wilson 95% CI | Δ |
|-----|---------|------------|-------------|---------------|---|
| ARMED-continuation (align_tier=ARMED & rising) | 1,752 | 1,322 | 0.3065 | [0.2854, 0.3285] | -0.0279 |
| PRIME bottoming (align_tier=PRIME & bottoming) | 5,448 | 3,846 | 0.3344 | [0.3220, 0.3471] | — |

- Bootstrap p-value (block, episode-clustered, n_boot=5000): **0.0490**
- BH q-value (m=5 family): **0.1225** (not significant at α=0.10)
- Both-halves sign stability: **STABLE**
  - H1 Δ = -0.0146 (n_arm=900, n_ref=2477)
  - H2 Δ = -0.0539 (n_arm=852, n_ref=2971)
- Per-name majority: 410/642 names agree in direction (0.639) — **PASS**
- Materiality: |Δ|=2.79pp vs 5pp bar → **IMMATERIAL**

### Secondary context (NEVER verdict)

| Arm | STOPPED | DEAD_MONEY | CUSHIONED | CLEAN_LIFTOFF | MAE_21d* | MFE_21d | ret_5d | ret_21d | ret_63d |
|-----|---------|------------|-----------|---------------|---------|---------|--------|---------|---------|
| ARMED-cont | 0.405 | 0.176 | 0.113 | 0.307 | -0.0579 | 0.0743 | 0.0022 | 0.0143 | 0.0406 |
| PRIME | 0.394 | 0.153 | 0.119 | 0.334 | -0.0533 | 0.0783 | 0.0029 | 0.0266 | 0.0634 |
| Stop-out Δ (ARMED−PRIME) | +0.011 | | | | | | | | |

*`MAE_21d` uses `fwd_mdd_21` (max drawdown) as the operational proxy for the PREREG's `fwd_mae_21d`; secondary/context only, never verdict (A4 stamp).

---

## T2–T5 Sub-partition tables (diagnostic context within ARMED-continuation)

*ARMED-continuation rows with non-null rs_sector_quartile: 1,593 (excluded null: 159)*

| Trial | Axis | n_arm | P_arm | n_ref | P_ref | Δ | p-val | BH q |
|-------|------|-------|-------|-------|-------|---|-------|------|
| T2 | Q1 vs Q2-Q4 | 208 | 0.3462 | 1,385 | 0.2866 | +0.0595 | 0.1352 | 0.2253 |
| T3 | Q1-Q2 vs Q3-Q4 | 637 | 0.2920 | 956 | 0.2960 | -0.0040 | 0.8822 | 0.8822 |
| T4 | above_200=True vs False | 890 | 0.2472 | 862 | 0.3677 | -0.1206 | 0.0000 | 0.0000 |
| T5 | Q1+above vs others | 57 | 0.3860 | 1,536 | 0.2910 | +0.0949 | 0.2160 | 0.2700 |

---

## BH Family Summary (m=5)

| Trial | p-value | BH q-value | Significant (q≤0.10) |
|-------|---------|------------|---------------------|
| T1 | 0.0490 | 0.1225 | NO |
| T2 | 0.1352 | 0.2253 | NO |
| T3 | 0.8822 | 0.8822 | NO |
| T4 | 0.0000 | 0.0000 | YES |
| T5 | 0.2160 | 0.2700 | NO |

---

## Both-Halves Sign Stability Grid

Window (last-graded fire): 2022-06-30 → 2025-12-29, midpoint: 2024-03-30

| Half | ARMED-cont P(clean8_21) | PRIME P(clean8_21) | Δ | Sign |
|------|------------------------|-------------------|---|------|
| H1 (before 2024-03-30) | 0.3733 | 0.3880 | -0.0146 | - |
| H2 (from 2024-03-30) | 0.2359 | 0.2898 | -0.0539 | - |
| **Stability** | | | | **STABLE** |

---

## Per-Name Majority Check

- PRIME reference P(clean8_21): 0.3344
- Δ direction = **lower**; ARMED-continuation names agreeing: 410/642 = 0.639
- Majority check: **PASS**

---

## Coverage / Survivor-Stamp Line

- Total fire rows (verdict_grade=True, incl. horizon_censored): 49,939
- survivor_biased excluded (stamped): 0 (all rows 2022+ Massive-sourced, unstamped)
- horizon_censored fires excluded: 0
- Effective verdict-grade fires: 49,939
- Effective episode clusters (all fires): 22,295
- ARMED-continuation episode clusters: 1,322 (K1 floor 100 — PASS)
- PRIME bottoming episode clusters: 3,846
- ARMED rows with null weekly_phase excluded: 0

---

## Diagnostic: Other ARMED fires (non-primary)

**Other ARMED (align_tier=='ARMED' & non-rising): n = 0.** Every `align_tier=='ARMED'` fire carries `weekly_phase=='rising'` — the ARMED tier admits exactly the continuation profile the masterplan flagged. No edge-case aside to report.

---

## board_rank_unresolved (descriptive — memo §6.3 / §APPROVAL cl.4)

- ARMED-continuation fires with `board_reason=='board_rank_unresolved'`: **418**
- PRIME bottoming fires with `board_reason=='board_rank_unresolved'`: **1321**
- Treatment: descriptive only. This study issues no keep/demote/flip verdict on any row; `board_rank_unresolved` rows are left untouched (they are a labeled board-selection limitation, not a study partition axis).

---

## Leak-Audit Section

- **Fill rule:** entry = first close strictly after signal date (`fill_date > signal_date`); same-bar fill not used (`fill_offset` confirms).
- **Era-table source:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) §1 + §6 v1.1.
- **Partition column:** `align_tier` (logged at signal time; canonical alignment tier, sibling study P1.1). NOT `tier_cascade` (the confluence cascade the round-1 run mis-used).
- **weekly_phase:** logged at signal time (engine/cycles.py mtf_alignment), not look-ahead.
- **rs_sector_quartile:** logged at signal time (current-GICS snapshot, 928-label map, §APPROVAL). Not look-ahead.
- **above_200:** logged at signal time (signal_gate / frozen features). Not look-ahead.
- **MAE proxy (A4):** `fwd_mae_21d` (PREREG §1) rendered via `fwd_mdd_21` (max drawdown); secondary/context only.
- **Window (A2):** data boundary 2026-07-02 vs last-graded fire 2025-12-29 reconciled explicitly; fires stop earlier so the 21-day forward horizon fits.

---

## Decision Rule Outcome

**H-MISLABEL** — |Δ|=0.0279 < 5pp (not materially different) — H-MISLABEL first disjunct.

### Decision-table evaluation (PREREG §6):
- Δ (ARMED-cont − PRIME) = **-0.0279** → |Δ|=2.79pp vs 5pp bar → **immaterial**
- BH q(T1) = **0.1225** → not significant at α=0.10
- Both-halves sign stable = **True**; per-name majority = **True**
- Stop-out Δ = **+0.0106** → <5pp (immaterial)

### Action mapping per PREREG §6:
- **H-MISLABEL** governs: ARMED-continuation fires are NOT materially worse than PRIME.
- Relabel them into an explicit **'continuation' lane** on the board (additive-lanes law R7 — they are NOT removed).
- **No gate change. No rank change.** The `rising` weekly-phase penalty stays as-is (no H-UNDERRANK trigger).
- T2–T5 sub-partitions are diagnostic context only and do not override the T1 verdict (PREREG §6 sub-partition clause).

---

## Mandatory stamp text (§2.3)

> survivor-biased panel: 31.3% of member-months lack price history for the 2012-2020 era; delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade. (Pre-2021 rows are NOT present in this parquet — all rows are 2022+ Massive-sourced, survivor_bias=False.)

---

*§8 row in the masterplan to be appended by Fable after Opus verdict review.*