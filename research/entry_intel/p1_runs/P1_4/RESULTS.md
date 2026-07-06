# P1.4 Recall Audit — RESULTS (v2, round 2 — defect-corrected re-run)

**Run date:** 2026-07-05  
**Round:** 2 — defect-corrected re-run of the registered P1.4 grid (round 1 bounced by conformance review).  
**Memo:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments (2026-07-05)  
**Primary window:** 2022-06-30 → 2026-07-02  
**Input:** data/replay/replay_boarded.parquet (961,656 rows; never replay_2*.parquet parts)  
**Trial family:** p1_4_recall_audit — T1-T5 registered before computation  
**Post-hoc trials recorded:** none  

## Verdict (lead)

The funnel FIRED on **0.24%** of all verified durable-low events (Denominator A, n=8,242) and on **5.12%** of all +20%/60d large-move events (Denominator B, n=25,545) in the primary window (2022-06-30 → 2026-07-02).  

**NEVER-TRIGGERED fraction: 7.79% (Denom A, 642 events) and 8.93% (Denom B, 2,281 events).**  

This corrects the round-1 lead ('NEVER-TRIGGERED = 0'), which was an artifact of counting the 127,389 horizon-censored (verdict_grade==False) replay rows as resolved verdicts. Under the primary-stats law, a significant event whose (ticker, date) has NO verdict-grade replay row is NEVER-TRIGGERED — even if a censored (unresolved) row exists. Of the 642 never-triggered Denom-A events, 642 sit on a censored-only pair and 0 have no replay row at all; for Denom B, 2,281 censored-only and 0 absent. So the coverage gap is NOT purely in momentum gates: a real slice of significant events either were never resolved to a verdict-grade outcome or never produced a candidate row at all.

This is a purely descriptive census (no pre-registered pass/fail threshold). Wilson 95% CIs are confidence intervals for proportions, not hypothesis tests. Escalation conditions are checked below; QRN_A / QRN_B are the frozen quarterly KPI definitions.

## Round-1 defect and fix

**Defect (bounced by conformance REVIEW.md, CHECK-2/CHECK-3 BLOCKING):** the round-1 run built the funnel-verdict lookup and the in-universe set from ALL 961,656 replay rows. The 127,389 `verdict_grade==False` rows — identical to the `horizon_censored==True` partition — were counted as resolved FIRED / NEAR-MISSED / REJECTED verdicts. This violated the program primary-stats law ('primary statistics on verdict_grade==True rows only') and the PREREG §5 checklist item ('`horizon_censored` rows excluded per-horizon, tracked separately'). Because every (ticker, date) pair is unique and 127,389 of them are censored-only, those pairs absorbed the events that should have surfaced as NEVER-TRIGGERED — making the round-1 lead 'NEVER-TRIGGERED = 0' an artifact.

**Fix:** the verdict lookup is rebuilt on `verdict_grade==True` rows ONLY. In-universe candidate membership (PREREG denominator condition 4 — 'appears as a candidate row … any verdict') still uses full replay presence, so the DENOMINATORS are unchanged. A denominator event whose (ticker, date) has no verdict-grade row is now honestly counted NEVER-TRIGGERED, and its censored-vs-absent split is reported. Censored rows are reported explicitly as unresolved, never as resolved verdicts. The denominator event-detection machinery, Wilson math, and QRN logic are byte-for-byte the round-1 code (the review confirmed they reproduce exactly); only the lookup row set and the honesty reporting changed.

### Round-1 vs round-2 reconciliation (delta = censored-row exclusion)

| Headline number | Round-1 (bounced) | Round-2 (corrected) | Delta | Attribution |
|---|--:|--:|--:|---|
| Denom A n | 8,242 | 8,242 | +0 | unchanged (event detection unaffected) |
| Denom B n | 25,545 | 25,545 | +0 | unchanged |
| Overlap A∩B | 943 | 943 | +0 | unchanged |
| A FIRED | 21 | 20 | -1 | censored fires no longer counted resolved |
| A NEAR-MISSED | 5 | 5 | +0 | censored near-misses excluded |
| A REJECTED | 8,216 | 7,575 | -641 | censored rejections excluded |
| A NEVER-TRIGGERED | 0 | 642 | +642 | **the defect surfaces here** |
| B FIRED | 1,414 | 1,308 | -106 | censored fires no longer counted resolved |
| B NEAR-MISSED | 451 | 414 | -37 | censored near-misses excluded |
| B REJECTED | 23,680 | 21,542 | -2,138 | censored rejections excluded |
| B NEVER-TRIGGERED | 0 | 2,281 | +2,281 | **the defect surfaces here** |
| QRN_A fired/n | 3/1,713 (0.18%) | 2/1,713 (0.12%) | -1 fires | censored fires excluded from trailing-252 |
| QRN_B fired/n | 253/5,706 (4.43%) | 149/5,706 (2.61%) | -104 fires | censored fires excluded from trailing-252 |

Every delta is attributable to a single root cause: excluding the 127,389 horizon-censored (verdict_grade==False) rows from the verdict lookup. Denominators, overlap, year breakdown, and Wilson/QRN machinery are unchanged.

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
> never-triggered (it didn't even look — or never reached a settled verdict). No single bucket is bad
> on its own — a high rejection rate might be correct discipline. But a very high never-triggered rate
> is a structural gap: the funnel is being precision-stacked toward a tiny slice of the universe and
> missing most of the action. This census runs quarterly so the program never claims good entries
> without showing what it passed on.
>
> **Round-2 note:** the first run of this census mistakenly treated events whose outcome window had
> not finished ('horizon-censored') as if the funnel had settled a verdict on them. That hid the
> never-triggered bucket at zero. Fixed, roughly 8-9% of significant events had no settled verdict —
> the honest never-triggered rate — while the funnel still fires on well under 1% of durable lows.

## 1. Era and Conformance

- Primary window: **2022-06-30 → 2026-07-02** (effective; 250-bar Massive warmup per memo §6.1)
- Total replay rows: **961,656**; all `survivor_bias=False` (Massive-sourced per §APPROVAL substrate v1.1)
- Survivor-stamped rows in artifact: **0** (none — all rows are 2022-06-30+ Massive-sourced)
- `verdict_grade==True` rows (LOOKUP source): **834,267**
- `horizon_censored==True` rows EXCLUDED from the verdict lookup (censored ≠ resolved): **127,389** (13.25% of all rows)
  - Censored rows carried (unresolved) provisional verdict_type: rejection=117,154, fire=7,701, near_miss=2,534 — none of these are treated as resolved verdicts.
- `verdict_grade==False` ≡ `horizon_censored==True` (verified identical partitions; 127,389 rows).

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
| FIRED | 20 | 0.24% | [0.16%, 0.37%] |
| NEAR-MISSED | 5 | 0.06% | [0.03%, 0.14%] |
| REJECTED | 7,575 | 91.91% | [91.30%, 92.48%] |
| NEVER-TRIGGERED | 642 | 7.79% | [7.23%, 8.39%] |

NEVER-TRIGGERED split: 642 on censored-only pairs (candidate row exists but horizon-censored, no settled verdict) + 0 with no replay row at all.

## 4. T2: Funnel-Verdict Partition — Denominator B (+20%/60d Moves)

**n = 25,545**

| Category | Count | Fraction | 95% Wilson CI |
|----------|------:|---------:|---------------|
| FIRED | 1,308 | 5.12% | [4.86%, 5.40%] |
| NEAR-MISSED | 414 | 1.62% | [1.47%, 1.78%] |
| REJECTED | 21,542 | 84.33% | [83.88%, 84.77%] |
| NEVER-TRIGGERED | 2,281 | 8.93% | [8.59%, 9.29%] |

NEVER-TRIGGERED split: 2,281 on censored-only pairs + 0 with no replay row at all.

## 5. T3: Near-Miss Sub-Breakdown by Reason

### Denominator A

| Reason | Count | % of near-misses |
|--------|------:|----------------:|
| not_topped_veto | 3 | 60.00% |
| freshness_expired | 2 | 40.00% |

### Denominator B

| Reason | Count | % of near-misses |
|--------|------:|----------------:|
| not_topped_veto | 231 | 55.80% |
| freshness_expired | 183 | 44.20% |

## 6. T4: Rejected Sub-Breakdown by Reason

### Denominator A

| Reason | Count | % of rejections |
|--------|------:|----------------:|
| no_signal | 7,136 | 94.20% |
| not_topped_veto | 268 | 3.54% |
| hygiene_screen | 117 | 1.54% |
| board_rank_cutoff | 54 | 0.71% |

### Denominator B

| Reason | Count | % of rejections |
|--------|------:|----------------:|
| no_signal | 18,682 | 86.72% |
| not_topped_veto | 2,246 | 10.43% |
| board_rank_cutoff | 424 | 1.97% |
| hygiene_screen | 190 | 0.88% |

## 7. T5: Fired Tier Sub-Breakdown

### Denominator A

| Tier | Count | % of fires |
|------|------:|-----------:|
| T1 | 13 | 65.00% |
| T2 | 7 | 35.00% |

### Denominator B

| Tier | Count | % of fires |
|------|------:|-----------:|
| T2 | 636 | 48.62% |
| T1 | 621 | 47.48% |
| T3 | 51 | 3.90% |

## 8. Standing Quarterly Recall Numbers

**Trailing 252 trading bars:** 2025-07-15 → 2026-07-02

| Metric | Rate | n | Fired | Wilson 95% CI |
|--------|-----:|--:|------:|---------------|
| QRN_A (durable-low) | 0.12% | 1,713 | 2 | [0.03%, 0.42%] |
| QRN_B (+20%/60d) | 2.61% | 5,706 | 149 | [2.23%, 3.06%] |

QRN definition (frozen per PREREG): FIRE-only fraction against trailing 252 trading bars, primary era only, verdict-grade fires only. Does not measure entry quality — that is P1.1-P1.3.

## 9. Survivor-Stamp Context Appendix

**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**

Survivor-stamped rows in artifact: **0**  
No survivor-stamped rows present. All 961,656 rows are Massive-sourced (`survivor_bias=False`) per §APPROVAL substrate v1.1. No context appendix required.

## 10. Measurement Limitations

- **Censored-row handling (round-2 core fix):** the 127,389 `horizon_censored`/`verdict_grade==False` rows are excluded from the verdict lookup. They remain in the in-universe candidate set (a censored pair was still a candidate that day), so an event on a censored-only pair is NEVER-TRIGGERED (in-universe, no settled verdict), not silently dropped. This is the honest treatment the PREREG §5 checklist requires.
- **ATR waiver:** depth-floor waived (ATR=NaN or 0) for any candidate bar; waiver applied bar-level.
- **Deduplication:** 5-business-day window via `np.busday_count`; first event in cluster retained (PREREG-frozen).
- **Forward-bar exclusion:** any event within 60 bars of the last available Massive bar is excluded (no forward bar available). This slightly under-counts events near ERA_END.
- **In-universe check:** per-date membership from full replay (ticker, date) presence in `replay_boarded.parquet` (any verdict, incl. censored). All replay tickers confirmed present in Massive store.
- **Never-triggered:** (ticker, date) events with no verdict-grade replay row for that exact date. A ticker with zero replay rows ever is excluded from the denominator entirely.

## 11. Trial Ledger Confirmation

Family: `p1_4_recall_audit`  
Registered trials (before computation): **T1, T2, T3, T4, T5**  
Post-hoc trials: **none** (defect-corrected re-run of the same registered grid, not a new trial)  
Future variations beyond T1-T5 must be logged as T6+ per PREREG §8.  
