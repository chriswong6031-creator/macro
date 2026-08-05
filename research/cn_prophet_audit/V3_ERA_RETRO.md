# V3 ERA RETRO — the stand-in race verdict

> Retro-application of the complete `cn_prophet_v3` selection to the V1 era, graded against the v2-rule selection and the actual logged board. **PRELIMINARY STAND-IN** for the forward v3-vs-v2 shadow race — it replaces nothing; the forward race remains the decider.

## DECISION-RELEVANT SUMMARY

1. **Verdict: on this era the v3 rule BEATS the v2 rule.** Win 62.2% → 89.2% (+27.0pp), median excess +3.99 → +6.35 (+2.36pp), catastrophic (abs ≤ −15%) 16.2% → 1.5% (-14.7pp). All three metrics move the same way.
2. Shelf sizes: v2 n=37 vs v3 n=65 matured episodes. v3 admits the patience cohort, so it is the WIDER shelf — the gain is not a selectivity artefact of showing fewer names.
3. Base rate: the actual logged board over the same window ran 75.9% win / +5.41 median / 6.6% catastrophic on n=257. v2 sits BELOW its own board's base rate on every metric; v3 sits above it.
4. **The delta is R1, and almost nothing else.** Decomposed: the R1 entry-set widening alone (prime window, no ticks demotion, no relay demotion) takes 62.2% → 81.8% (+19.6pp, n=77); the R1 confirmed-late demotion adds +7.4pp on top (81.8% → 89.2%) and cuts catastrophic 5.2% → 1.5%. R2 and R3 contribute nothing measurable (lines 5-6) — this era tests R1, not the R-slate.
5. **R3 (relay-late) is INERT on this era, and what it touched was a winner.** The guard demoted 14 admission rows across the window; 1 of them was the entry row of a matured episode on the v2 shelf — and it WON (+15.52 excess). Switching the guard off leaves the capped v3 shelf statistically identical (n=65, 89.2%), because the row it admits does not clear the cap anyway. This era can neither support nor refute R3; PR #4506's 12-month relay ladder remains its only evidence.
6. **R2 (theme_timing) does not help here — it is very slightly NEGATIVE.** Re-walking the caps with theme_timing zeroed gives n=72 / 90.3% / +6.41 vs the full score's n=65 / 89.2% / +6.35. Its only channel is cap ordering, the difference is well inside noise at this n, and the direction is not the one R2 predicts — printed, not hidden.
7. **What v3 ADDS** (n=54, disjoint): 92.6% win, +6.31 median, 0.0% catastrophic — the patience cohort (bounce_wait / wait_pullback / hold) v2 excluded.
8. **What v3 DROPS** (n=26, disjoint): 57.7% win, +3.87 median, 19.2% catastrophic. The confirmed-late slice (16 episodes) is the costly one v2 kept: 43.8% win, -2.68 median.
9. Uncapped, the comparison holds: v2 60.5% / +3.87 (n=38) vs v3 88.2% / +6.11 (n=119) — the caps are not doing the work.
10. **Reconstruction cross-checks (asserted, not just reported).** The v2 arm reproduces `v1_loser_audit_results.json`'s independently-computed v2 gate retro exactly — covered n 257, covered win 0.759, featured-like n 38 at 0.605 (masterplan §2.3's 60.5% receipt). The reconstructed narrative level agrees with the logged curated tag on 97.9% of the 234 rows that carry one.
11. **The effective sample is 8 BOARD DAYS, not 65 episodes.** Only entries up to 2026-07-17 have 10 forward sessions in the store, so six of the fourteen window dates grade nothing yet. Resampling whole board days (`track_scoring.date_block_ci`) widens the win interval to v3 [77.6, 96.5] vs v2 [45.2, 80.6] — still separated, but that is the interval to quote, not the Wilson one.
12. **This is IN-SAMPLE and close to circular.** R1's entry ladder was fitted to this era's §2.3 table; re-scoring the same era with it is internal consistency, not confirmation. The shelves also share 11 episodes, so the two arms are not independent draws.
13. **One falling tape, and an approximated selection**: CSI300's forward-10 was negative on most graded entry dates; micro fillability, the ADV liquidity floor and signal freshness are not retro-testable, and the cap score's runway/reversal legs are partial or zero. Both arms carry the same omissions, so the comparison is fair; the absolute levels are not a production forecast. The theme reconstruction also carries the THS membership lookahead (PR #4506: 7.7% of member-slots drifted in 8 days); curated membership is PIT-dated.
14. Window 2026-07-07–2026-07-29 (14 board dates, 842 admission rows), frozen-replay pinned at **2026-08-03** (without the pin the store's nightly bar re-opens the maturity gate and the shipped headline stops reproducing — 441/70.52% on 2026-08-04). The 150 matured episodes before the window carry no entry gauge and are excluded from ALL arms. P0 gate PASSED: 584 episodes / 407 matured / 68.55% win / 128 losers.
15. **Decision**: a preliminary read for the operator's fast-track question, not a promotion and not a gauntlet pass. It supports R1 staying live and says the era-retro carries NO information about R2 or R3. Nothing here changes the G0.8 tripwire, which still grades the FORWARD race at ≥60 matured episodes.

## Headline table — the stand-in race

| Shelf | n | board days | win % | 95% Wilson | 95% date-blocked | loser % | median excess | mean excess | catastrophic |
|---|---|---|---|---|---|---|---|---|---|
| **V3-RULE (capped 24/4)** | 65 | 8 | 89.2% | [79.4–94.7] | [77.6–96.5] | 10.8% | +6.35 | +6.99 | 1.5% (1) |
| **V2-RULE (capped 24/4)** | 37 | 8 | 62.2% | [46.1–75.9] | [45.2–80.6] | 37.8% | +3.99 | +1.77 | 16.2% (6) |
| ACTUAL logged board | 257 | 8 | 75.9% | [70.3–80.7] | [65.5–87.0] | 24.1% | +5.41 | +3.93 | 6.6% (17) |
| V3-RULE (uncapped) | 119 | 8 | 88.2% | [81.2–92.9] | [79.1–93.8] | 11.8% | +6.11 | +6.28 | 1.7% (2) |
| V2-RULE (uncapped) | 38 | 8 | 60.5% | [44.7–74.4] | [43.6–80.6] | 39.5% | +3.87 | +1.49 | 15.8% (6) |

Excess is CSI300-relative percent at the H=10 forced verdict from the T+1 fill; catastrophic is ABSOLUTE P&L ≤ −15%.

## Leg attribution — which R-item earns the delta

Each row is the full v3 rule with exactly one leg switched off, capped identically. A headline gap is only decision-relevant if you know what produced it.

| Rule variant | n | board days | win % | 95% Wilson | 95% date-blocked | loser % | median excess | mean excess | catastrophic |
|---|---|---|---|---|---|---|---|---|---|
| v3_rule (all legs) | 65 | 8 | 89.2% | [79.4–94.7] | [77.6–96.5] | 10.8% | +6.35 | +6.99 | 1.5% (1) |
| R1 entry set only (no confirmed_late, no relay_late) | 77 | 8 | 81.8% | [71.8–88.8] | [64.9–93.9] | 18.2% | +6.27 | +5.56 | 5.2% (4) |
| v3 minus confirmed_late | 76 | 8 | 81.6% | [71.4–88.7] | [64.3–93.8] | 18.4% | +6.26 | +5.13 | 5.3% (4) |
| v3 minus relay_late | 65 | 8 | 89.2% | [79.4–94.7] | [77.6–96.5] | 10.8% | +6.35 | +6.99 | 1.5% (1) |
| v2 entry set + confirmed_late | 21 | 8 | 76.2% | [54.9–89.4] | [63.2–90.9] | 23.8% | +6.11 | +5.39 | 9.5% (2) |
| v2_rule (all legs off) | 37 | 8 | 62.2% | [46.1–75.9] | [45.2–80.6] | 37.8% | +3.99 | +1.77 | 16.2% (6) |
| v3 with theme_timing zeroed in the cap ordering | 72 | 8 | 90.3% | [81.3–95.2] | [78.5–97.0] | 9.7% | +6.41 | +7.11 | 1.4% (1) |

## Marginal cohorts (disjoint — the sharper statement)

| Cohort | n | board days | win % | 95% Wilson | 95% date-blocked | loser % | median excess | mean excess | catastrophic |
|---|---|---|---|---|---|---|---|---|---|
| v3 ADDS (v2 excluded these) | 54 | 8 | 92.6% | [82.4–97.1] | [83.3–97.6] | 7.4% | +6.31 | +7.47 | 0.0% (0) |
| v3 DROPS (v2 featured these) | 26 | 8 | 57.7% | [38.9–74.5] | [35.3–77.4] | 42.3% | +3.87 | +0.56 | 19.2% (5) |
| on BOTH shelves | 11 | 5 | 72.7% | [43.4–90.3] | [58.3–100.0] | 27.3% | +7.24 | +4.63 | 9.1% (1) |

### v3 ADDS, by entry status

| entry_status | n | board days | win % | 95% Wilson | 95% date-blocked | loser % | median excess | mean excess | catastrophic |
|---|---|---|---|---|---|---|---|---|---|
| `bounce_wait` | 35 | 4 | 94.3% | [81.4–98.4] | [87.5–100.0] | 5.7% | +6.35 | +7.13 | 0.0% (0) |
| `hold` | 9 | 6 | 88.9% | [56.5–98.0] | [70.0–100.0] | 11.1% | +4.76 | +6.21 | 0.0% (0) |
| `wait_pullback` | 10 | 4 | 90.0% | [59.6–98.2] | [78.6–100.0] | 10.0% | +6.90 | +9.81 | 0.0% (0) |

### v3 DROPS, by reason

| reason | n | board days | win % | 95% Wilson | 95% date-blocked | loser % | median excess | mean excess | catastrophic |
|---|---|---|---|---|---|---|---|---|---|
| `confirmed_late` | 16 | 7 | 43.8% | [23.1–66.8] | [18.2–70.0] | 56.2% | -2.68 | -2.98 | 25.0% (4) |
| `displaced_by_cap` | 9 | 4 | 77.8% | [45.3–93.7] | [60.0–100.0] | 22.2% | +5.46 | +5.19 | 11.1% (1) |
| `relay_late` | 1 | 1 | 100.0% | [20.7–100.0] | n/a (<2 board days) | 0.0% | +15.52 | +15.52 | 0.0% (0) |

## Per-date blocks

| date | CSI300 fwd-10 | actual n/win/med | v2 n/win/med | v3 n/win/med |
|---|---|---|---|---|
| 2026-07-07 | -0.69% | 43 / 58.1% / +3.0 | 6 / 50.0% / -1.4 | 7 / 57.1% / +0.1 |
| 2026-07-08 | -2.62% | 30 / 83.3% / +8.7 | 6 / 66.7% / +11.2 | 2 / 100.0% / +10.8 |
| 2026-07-10 | +0.19% | 38 / 52.6% / +1.7 | 7 / 28.6% / -11.8 | 3 / 66.7% / +7.4 |
| 2026-07-13 | -4.34% | 33 / 81.8% / +6.6 | 3 / 100.0% / +8.4 | 6 / 83.3% / +7.7 |
| 2026-07-14 | -3.74% | 28 / 96.4% / +6.4 | 6 / 83.3% / +5.7 | 13 / 100.0% / +6.4 |
| 2026-07-15 | -3.11% | 26 / 92.3% / +4.8 | 4 / 75.0% / +5.4 | 11 / 100.0% / +4.9 |
| 2026-07-16 | +1.39% | 31 / 74.2% / +3.3 | 3 / 33.3% / -0.2 | 11 / 90.9% / +7.8 |
| 2026-07-17 | -1.10% | 28 / 85.7% / +6.7 | 2 / 100.0% / +6.5 | 12 / 91.7% / +6.8 |
| 2026-07-21 | — | 0 / — / — | 0 / — / — | 0 / — / — |
| 2026-07-23 | — | 0 / — / — | 0 / — / — | 0 / — / — |
| 2026-07-24 | — | 0 / — / — | 0 / — / — | 0 / — / — |
| 2026-07-27 | — | 0 / — / — | 0 / — / — | 0 / — / — |
| 2026-07-28 | — | 0 / — / — | 0 / — / — | 0 / — / — |
| 2026-07-29 | — | 0 / — / — | 0 / — / — | 0 / — / — |

## Reconstruction diagnostics

- theme_timing buckets (rows): {'0.0': 17, '0.25': 526, '0.6': 138, '1.0': 161}
- narrative reconstruction vs the logged curated-only tag: 229/234 agree (97.9%); the reconstruction tags 230 rows in total (curated ∪ THS).
- chase composite fired on 61 rows (27 of them on an admission-day limit close); 3261 limit closes across the basket universe.
- relay: 512 rows positioned (early 372 / mid 78 / late 62), 330 unpositioned (no basket membership); 14 rows took the `relay_late` demotion.
- shelf rows: {'actual_all_admissions': 842, 'v3_rule_uncapped': 529, 'v3_rule_capped': 273, 'v2_rule_uncapped': 147, 'v2_rule_capped': 145, 'r1_entry_set_only_uncapped': 616, 'r1_entry_set_only_capped': 298, 'v3_minus_confirmed_late_uncapped': 609, 'v3_minus_confirmed_late_capped': 296, 'v3_minus_relay_late_uncapped': 535, 'v3_minus_relay_late_capped': 274, 'v2_plus_confirmed_late_uncapped': 66, 'v2_plus_confirmed_late_capped': 66, 'v3_rule_capped_theme_timing_off': 273}
- shelf matured episodes: {'actual_all_admissions': 257, 'v3_rule_uncapped': 119, 'v3_rule_capped': 65, 'v2_rule_uncapped': 38, 'v2_rule_capped': 37, 'r1_entry_set_only_uncapped': 137, 'r1_entry_set_only_capped': 77, 'v3_minus_confirmed_late_uncapped': 135, 'v3_minus_confirmed_late_capped': 76, 'v3_minus_relay_late_uncapped': 120, 'v3_minus_relay_late_capped': 65, 'v2_plus_confirmed_late_uncapped': 21, 'v2_plus_confirmed_late_capped': 21, 'v3_rule_capped_theme_timing_off': 72}

## Honesty block

- IN-SAMPLE. The v3 rule was designed FROM this era (masterplan §2.3's entry-status inversion is this era's own table), so a v3 win here is consistency, not confirmation. The forward shadow race is the decider.
- ONE ERA, ONE TAPE. CSI300's forward-10 window was negative on 10 of 12 graded entry dates; the whole comparison lives inside a falling tape.
- SELECTION IS APPROXIMATED. Three production featured gates are not retro-testable from the legacy schema: microstructure fillability/chase freshness, the ADV liquidity floor, and signal recency. BOTH arms omit them identically, so the comparison is fair; neither arm's ABSOLUTE level is a production forecast.
- SCORE IS APPROXIMATED. The cap ordering uses a v3-weight score whose runway leg is partial (the extension half is logged, the `fuel` half is not), whose reversal_member leg is zero, whose bottom_quality 0.4 `washout_ctx` rung is unreachable on the legacy schema, and whose T3 bars_to_cross haircut is unavailable. The score affects ONLY which qualified rows survive the caps — the uncapped tables isolate it.
- THEME RECONSTRUCTION CARRIES THE THS LOOKAHEAD. Curated membership is PIT-dated (all members added 2021-06-15, none removed — the PIT filter is a no-op over this era). THS membership is a single 2026-07-08 snapshot applied backward; PR #4506 measured two available THS snapshots differing by 7.7% of member-slots in 8 days. Every THS-sourced theme tag, and every relay count computed over a THS basket, inherits that.
- V1 LOGGED ONLY THE TOP 60 rows per night of a ~110-row buy pool (§2.7), so each shelf is 'of the 60 logged rows, which would v3/v2 feature' — the featured cap of 24 is applied inside that 60, not inside the full pool.
- OVERLAPPING ARMS. The two shelves share most of their episodes, so the Wilson intervals below overstate the independence of the DIFFERENCE. Read the marginal cohorts (v3-adds / v3-drops), which are disjoint, as the sharper statement.
- FROZEN REPLAY, PINNED AT 2026-08-03. Every price series is truncated at that date before grading. The pin is load-bearing, not cosmetic: the stores accrue a bar nightly, more episodes clear the H=10 maturity gate, and the shipped V1 headline stops being reproducible. Measured on 2026-08-04 with the pin removed: 441 matured / 70.52% win against the shipped 407 / 68.55%. Re-running this instrument against a later snapshot is a DIFFERENT measurement and needs its own pin.
- EFFECTIVE SAMPLE IS BOARD DAYS. Only entries through 2026-07-17 have ten forward sessions inside the pin, so six of the fourteen window dates grade nothing. Every table prints n_board_days next to n and a date-blocked interval next to the Wilson one; the date-blocked interval is the honest one (track_scoring's rule: one board night is one bet, not N).

## Method

- **Base frame**: the 1,082 legacy rows of `data/china_standout_track/board.parquet` (18 dates). Episodes via `engine.track_scoring.build_episodes` (contiguous runs), T+1 fill via `engine.china_standout_track._t1_fill` (locked-limit bars unfillable), H=10 forced verdict, CSI300-relative excess. P0 gate asserts the shipped 584/407/68.55%/128 headline before any new number is computed.
- **Grain**: an episode belongs to a shelf when its ENTRY-date board row qualifies.
- **V2-RULE**: `entry_status ∈ {buy_now, partial}` ∧ ¬extended.
- **V3-RULE**: `entry_status ∈ {bounce_wait, wait_pullback, hold, buy_now, partial}` ∧ ¬(status ∈ {buy_now, partial} ∧ ticks > 1) ∧ ¬extended ∧ ¬(chase ∧ relay late).
- **Caps**: featured 24 / sector 4 per date, walked in v3-score order, applied identically to BOTH arms (as `_partition` does).
- **theme_timing**: `_theme_timing_value` over reconstructed narrative level (HOT/WARMING per `engine.china_narrative_tags` thresholds, curated ∪ THS, rel20 and breadth rounded before the threshold test) and the `china_sector_cycles` forward-log basket phase/oscillator (newest row ≤ admission date, best-rs_rank basket per name).
- **chase / relay**: admission-day limit close (`close == high` ∧ day return ≥ 0.95 × the name's own band via `engine.china_microstructure.limit_width_for_date`, with the unmerged 302xxx ChiNext fix replicated), trail-21d ≥ 25%, run-5d ≥ 15%; `relay_count_3d` = distinct OTHER members of the name's baskets printing a limit close inside [d−2, d]; early ≤1 / mid 2–3 / late ≥4.

Frozen results: `research/cn_prophet_audit/v3_era_retro_results.json`. Regenerate: `python3 research/cn_prophet_audit/v3_era_retro.py`.
