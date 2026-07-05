# P1.4 Recall Audit — RESULTS

**Run date:** 2026-07-05  
**Memo:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)  
**Primary window:** 2022-06-30 → 2026-07-02  
**Input:** data/replay/replay_boarded.parquet (961,656 rows; never replay_2*.parquet parts)  
**Trial family:** p1_4_recall_audit — T1-T5 registered before computation  
**Post-hoc trials recorded:** none  

## Verdict (lead)

The funnel FIRED on **0.25%** of all verified durable-low events (Denominator A, n=8,242) and on **5.54%** of all +20%/60d large-move events (Denominator B, n=25,545) in the primary window (2022-06-30 → 2026-07-02).  

NEVER-TRIGGERED fraction: **0.00%** (Denom A), **0.00%** (Denom B).  

This is a purely descriptive census (no pre-registered pass/fail threshold). Wilson 95% CIs are confidence intervals for proportions, not hypothesis tests. Escalation conditions are checked below; QRN_A / QRN_B are the frozen quarterly KPI definitions.

## ESCALATION FLAGS — Fable review required before downstream action

- **ESC-1: funnel fires+near_miss on only 0.3% of durable-low events (<15%). R7 precision-stacking concern.**

## In Plain English

> Imagine the funnel as a net. The precision studies (P1.1-P1.3) test whether the fish it catches are
> good fish. This study counts how many fish swam through the net at all — the ones it caught, the
> ones it nearly caught, the ones it consciously rejected, and the ones it never even saw. The two
> yardsticks are: every time a stock made a genuine durable low (a low that held for 60 trading days
> without being undercut by 5%), and every time a stock went up 20%+ over the next 60 trading days.
> Against both yardsticks, we split the funnel's behavior into four buckets: fired (it rang the bell),
> near-missed (it tried but one condition blocked it), rejected (it evaluated and said no), or
> never-triggered (it didn't even look). No single bucket is bad on its own — a high rejection rate
> might be correct discipline. But a very high never-triggered rate is a structural gap: the funnel
> is being precision-stacked toward a tiny slice of the universe and missing most of the action.
> This census runs quarterly so the program never claims good entries without showing what it passed on.

## 1. Era and Conformance

- Primary window: **2022-06-30 → 2026-07-02** (effective; 250-bar Massive warmup per memo §6.1)
- All 961,656 replay rows: `survivor_bias=False` (Massive-sourced per §APPROVAL substrate v1.1)
- Survivor-stamped rows in artifact: **0** (none — all rows are 2022-06-30+ Massive-sourced)
- `horizon_censored` rows excluded per-horizon per memo §1.1(2)

**Mandatory stamp text (memo §2.3):**
> survivor-biased panel: 31.3% of member-months lack price history for the 2012-2020 era; delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade. (No such rows present in this artifact — all rows Massive-sourced, `survivor_bias=False`.)

## 2. Denominator Sizes

- **Denominator A** (durable-low events): **8,242** unique (ticker, date) events after 5-bday dedup
  - Definition: 60-day rolling min, not undercut 5% in 60 fwd bars, ATR(14) depth floor ≥1.0×ATR
- **Denominator B** (+20%/60d large-move events): **25,545** unique (ticker, date) events after 5-bday dedup
  - Definition: adjusted close +20% over 60 forward trading days
- **Overlap** (events in both A and B): **943**

### By Year

| Year | Denom A | Denom B |
|------|--------:|--------:|
| 2022 | 1,141 | 3,329 |
| 2023 | 2,446 | 6,778 |
| 2024 | 1,828 | 5,879 |
| 2025 | 2,209 | 7,371 |
| 2026 | 618 | 2,188 |

## 3. T1: Funnel-Verdict Partition — Denominator A (Durable-Low Events)

**n = 8,242**

| Category | Count | Fraction | 95% Wilson CI |
|----------|------:|---------:|---------------|
| FIRED | 21 | 0.25% | [0.17%, 0.39%] |
| NEAR-MISSED | 5 | 0.06% | [0.03%, 0.14%] |
| REJECTED | 8,216 | 99.68% | [99.54%, 99.78%] |
| NEVER-TRIGGERED | 0 | 0.00% | [0.00%, 0.05%] |

## 4. T2: Funnel-Verdict Partition — Denominator B (+20%/60d Moves)

**n = 25,545**

| Category | Count | Fraction | 95% Wilson CI |
|----------|------:|---------:|---------------|
| FIRED | 1,414 | 5.54% | [5.26%, 5.82%] |
| NEAR-MISSED | 451 | 1.77% | [1.61%, 1.93%] |
| REJECTED | 23,680 | 92.70% | [92.37%, 93.01%] |
| NEVER-TRIGGERED | 0 | 0.00% | [0.00%, 0.02%] |

## 5. T3: Near-Miss Sub-Breakdown by Reason

### Denominator A

| Reason | Count | % of near-misses |
|--------|------:|----------------:|
| not_topped_veto | 3 | 60.00% |
| freshness_expired | 2 | 40.00% |

### Denominator B

| Reason | Count | % of near-misses |
|--------|------:|----------------:|
| not_topped_veto | 243 | 53.88% |
| freshness_expired | 208 | 46.12% |

## 6. T4: Rejected Sub-Breakdown by Reason

### Denominator A

| Reason | Count | % of rejections |
|--------|------:|----------------:|
| no_signal | 7,738 | 94.18% |
| not_topped_veto | 299 | 3.64% |
| hygiene_screen | 118 | 1.44% |
| board_rank_cutoff | 61 | 0.74% |

### Denominator B

| Reason | Count | % of rejections |
|--------|------:|----------------:|
| no_signal | 20,595 | 86.97% |
| not_topped_veto | 2,427 | 10.25% |
| board_rank_cutoff | 464 | 1.96% |
| hygiene_screen | 194 | 0.82% |

## 7. T5: Fired Tier Sub-Breakdown

### Denominator A

| Tier | Count | % of fires |
|------|------:|-----------:|
| T1 | 14 | 66.67% |
| T2 | 7 | 33.33% |

### Denominator B

| Tier | Count | % of fires |
|------|------:|-----------:|
| T2 | 685 | 48.44% |
| T1 | 672 | 47.52% |
| T3 | 57 | 4.03% |

## 8. Standing Quarterly Recall Numbers

**Trailing 252 trading bars:** 2025-07-15 → 2026-07-02

| Metric | Rate | n | Fired | Wilson 95% CI |
|--------|-----:|--:|------:|---------------|
| QRN_A (durable-low) | 0.18% | 1,713 | 3 | [0.06%, 0.51%] |
| QRN_B (+20%/60d) | 4.43% | 5,706 | 253 | [3.93%, 5.00%] |

QRN definition (frozen per PREREG): FIRE-only fraction against trailing 252 trading bars, primary era only. Does not measure entry quality — that is P1.1-P1.3.

## 9. Survivor-Stamp Context Appendix

**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**

Survivor-stamped rows in artifact: **0**  
No survivor-stamped rows present. All 961,656 rows are Massive-sourced (`survivor_bias=False`) per §APPROVAL substrate v1.1. No context appendix required.

## 10. Measurement Limitations

- **ATR waiver:** depth-floor waived (ATR=NaN or 0) for any candidate bar. No global waiver count tracked per ticker; waiver is applied bar-level.
- **Deduplication:** 5-business-day window via `np.busday_count`; first event in cluster retained (PREREG-frozen).
- **Forward-bar exclusion:** any event within 60 bars of the last available Massive bar is excluded (no forward bar available). This slightly under-counts events near ERA_END.
- **In-universe check:** per-date membership from replay (ticker, date) presence in `replay_boarded.parquet`. All 1,007 replay tickers confirmed present in Massive store.
- **Never-triggered:** (ticker, date) events with no replay row for that exact date. A ticker with zero replay rows ever is excluded from the denominator entirely.
- **Denom B vectorization:** the `safe_b` array indexes era bars with sufficient forward bars; `c[safe_b + LFM_FWD]` reads the 60th-forward bar directly. Forward return is computed vectorized; the implementation uses `big_move_idx` for the final filtered index.

## 11. Trial Ledger Confirmation

Family: `p1_4_recall_audit`  
Registered trials (before computation): **T1, T2, T3, T4, T5**  
Post-hoc trials: **none**  
Future variations beyond T1-T5 must be logged as T6+ per PREREG §8.  
