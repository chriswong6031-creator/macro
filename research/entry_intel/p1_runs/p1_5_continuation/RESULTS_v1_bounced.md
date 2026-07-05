# P1.5 Continuation Partition — RESULTS

**PRIMARY VERDICT: AMBIGUOUS**

*GAP CASE: Δ=-0.0549 (<-5pp, material), BH q=0.0000 (significant), sign stable both halves, majority pass (0.622). BUT stop-out delta = +0.0060 (<+5pp), so H-EXCLUDE's stop-out criterion is NOT met. H-MISLABEL requires |Δ| < 5pp (not met: |Δ|=0.0549). No pre-registered branch covers: liftoff material+significant+stable but stop-out immaterial. PREREG decision table has a gap. Returning blocker to Fable per program law.*

---

## In plain English

The data reveals a real and reliable gap: names admitted via the 'weekly already rising' continuation path hit the clean-liftoff target only 27.9% of the time, versus 33.4% for fresh-bottom entries — a -5.5% gap that is statistically significant (BH q≈0) and carries the same sign in both halves of the window. Per-name majority confirms it. However, the stop-out rate for continuation fires is only +0.6% higher than PRIME — well below the 5pp threshold that the pre-registration requires for H-EXCLUDE. So the underperformance shows up as more DEAD_MONEY / CUSHIONED outcomes, not as stop-outs. The PREREG's decision table has a gap: it does not specify what to conclude when liftoff is materially worse but stop-out is not materially different. Under program law (ambiguity = blocker, never improvisation), this study returns AMBIGUOUS and awaits Fable ruling.

---

## Preamble (conformance)

- Era law: **P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)**
- Effective verdict window: **2022-06-30 → 2026-07-02** (§6 amendment 1: 250-bar MTF warmup)
- Canonical input: `data/replay/replay_boarded.parquet`
- survivor_bias=False rows (unstamped): 961,656 (all rows in this parquet)
- survivor_bias=True rows excluded: 0 (none — pre-2021 rows absent from this parquet)
- horizon_censored fires excluded from primary: 0
- verdict_grade=True fires total: 49,939
- Missing-fraction stamp (2012-2020 era, context only): 31.3% of member-months

---

## T1 Primary Comparison — ARMED-continuation vs PRIME bottoming

| Arm | n fires | n episodes | P(clean8_21) | Wilson 95% CI | Δ |
|-----|---------|------------|-------------|---------------|---|
| ARMED-continuation (T2+rising) | 10,521 | 5,838 | 0.2790 | [0.2705, 0.2876] | -0.0549 |
| PRIME bottoming (T1+bottoming)  | 15,145 | 7,312 | 0.3338 | [0.3264, 0.3414] | — |

- Bootstrap p-value (block, episode-clustered, n_boot=5000): **0.0000**
- BH q-value (m=5 family): **0.0000** (significant at α=0.10)
- Both-halves sign stability: **STABLE**
  - H1 Δ = -0.0513 (n_arm=4757, n_ref=6655)
  - H2 Δ = -0.0598 (n_arm=5764, n_ref=8490)
- Per-name majority: 594/955 names agree in direction (0.622) — **PASS**

### Secondary context (NEVER verdict)

| Arm | STOPPED | DEAD_MONEY | CUSHIONED | CLEAN_LIFTOFF | MAE_21d | MFE_21d | ret_5d | ret_21d | ret_63d |
|-----|---------|------------|-----------|---------------|---------|---------|--------|---------|---------|
| ARMED-cont | 0.388 | 0.197 | 0.136 | 0.279 | -0.0556 | 0.0708 | 0.0002 | 0.0144 | 0.0364 |
| PRIME      | 0.382 | 0.162 | 0.122 | 0.334 | -0.0522 | 0.0758 | 0.0042 | 0.0245 | 0.0562 |
| Stop-out Δ (ARMED-PRIME) | +0.006 | | | | | | | | |

---

## T2–T5 Sub-partition tables (diagnostic context within ARMED-continuation)

*ARMED-continuation rows with non-null rs_sector_quartile: 9,647 (excluded null: 874)*

| Trial | Axis | n_arm | P_arm | n_ref | P_ref | Δ | p-val | BH q |
|-------|------|-------|-------|-------|-------|---|-------|------|
| T2 | Q1 vs Q2-Q4 | 993 | 0.2941 | 8,654 | 0.2711 | +0.0230 | 0.2262 | 0.3080 |
| T3 | Q1-Q2 vs Q3-Q4 | 3,293 | 0.2715 | 6,354 | 0.2745 | -0.0030 | 0.8184 | 0.8184 |
| T4 | above_200=True vs False | 6,509 | 0.2532 | 4,012 | 0.3208 | -0.0676 | 0.0000 | 0.0000 |
| T5 | Q1+above vs others | 245 | 0.2367 | 9,402 | 0.2744 | -0.0377 | 0.2464 | 0.3080 |

---

## BH Family Summary (m=5)

| Trial | p-value | BH q-value | Significant (q≤0.10) |
|-------|---------|------------|---------------------|
| T1 | 0.0000 | 0.0000 | YES |
| T2 | 0.2262 | 0.3080 | NO |
| T3 | 0.8184 | 0.8184 | NO |
| T4 | 0.0000 | 0.0000 | YES |
| T5 | 0.2464 | 0.3080 | NO |

---

## Both-Halves Sign Stability Grid

Window: 2022-06-30 → 2025-12-29, midpoint: 2024-03-30

| Half | ARMED-cont P(clean8_21) | PRIME P(clean8_21) | Δ | Sign |
|------|------------------------|-------------------|---|------|
| H1 (before 2024-03-30) | 0.3292 | 0.3805 | -0.0513 | - |
| H2 (from 2024-03-30) | 0.2375 | 0.2973 | -0.0598 | - |
| **Stability** | | | | **STABLE** |

---

## Per-Name Majority Check

- PRIME reference P(clean8_21): 0.3338
- ARMED-continuation tickers with per-name P < PRIME: 594/955 = 0.622
- Majority check: **PASS**

---

## Coverage / Survivor-Stamp Line

- Total fire rows (verdict_grade=True): 49,939
- survivor_biased excluded (stamped): 0 (all rows in this parquet are 2022+ Massive-sourced, unstamped)
- horizon_censored fires excluded: 0
- Effective verdict-grade fires: 49,939
- Effective episode clusters (fires): 22,295
- ARMED-continuation episode clusters: 5,838
- PRIME bottoming episode clusters: 7,312

---

## Diagnostic: Other ARMED fires (non-primary)

| Arm | n | P(clean8_21) | CI | STOPPED | LIFT |
|-----|---|-------------|-----|---------|------|
| Other ARMED (T2+non-rising) | 13,704 | 0.3352 | [0.3273,0.3431] | 0.3579 | 0.3352 |

---

## Leak-Audit Section

- **Fill rule:** entry = first close strictly after signal date (fill_date > signal_date). Same-bar fill is not used. Column `fill_offset` confirms.
- **Era-table source:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) §1.
- **weekly_phase:** logged at signal time in the replay harness (engine/cycles.py mtf_alignment), not look-ahead.
- **rs_sector_quartile:** logged at signal time in the replay harness (current-GICS snapshot, 928-label constituents map per §APPROVAL). Not look-ahead.
- **above_200:** logged at signal time in the replay harness signal_gate / frozen features. Not look-ahead.

---

## Decision Rule Outcome

**AMBIGUOUS** — GAP CASE: Δ=-0.0549 (<-5pp, material), BH q=0.0000 (significant), sign stable both halves, majority pass (0.622). BUT stop-out delta = +0.0060 (<+5pp), so H-EXCLUDE's stop-out criterion is NOT met. H-MISLABEL requires |Δ| < 5pp (not met: |Δ|=0.0549). No pre-registered branch covers: liftoff material+significant+stable but stop-out immaterial. PREREG decision table has a gap. Returning blocker to Fable per program law.

### Action mapping per PREREG §6:
- AMBIGUOUS — return structured report to Fable. No mechanical action.

---

## Mandatory stamp text (§2.3)

> survivor-biased panel: 31.3% of member-months lack price history for 2012-2020 era; delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade. (Pre-2021 rows are NOT present in this parquet — all rows are 2022+ Massive-sourced.)

---

*§8 row in the masterplan to be appended by Fable after Opus verdict review.*