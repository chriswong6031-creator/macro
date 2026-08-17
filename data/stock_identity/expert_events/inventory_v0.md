# Stock Identity W2 — expert event inventory v0

Counts only. **This file publishes no ruler metric** — no lead/lag, distance, MAE, capture, recall, precision, composite, fit, rank or best appears here or in any artifact this wave produces; those are PR-3's object (registration §0.1). Every artifact carries the five-key all-false authority block, and a `scored_authority` flag on a row records what the EMITTER's authority was — a fact about the past, never a grant.

* pilot cohort: 22 names (`AEM`, `AG`, `B`, `BABA`, `CBRS`, `FFAI`, `GOLD`, `HL`, `KO`, `KRUS`, `MCD`, `MCK`, `META`, `MSFT`, `NEM`, `NVDA`, `PAAS`, `REGN`, `UEC`, `WMT`, `WPM`, `YELP`)
* universe as-of: 2026-08-13
* total events: **31,119** · typed edges: **64**

## Family inventory

| family_key | class | era pin(s) | first available | events | names | fixtures |
|---|---|---|---|---:|---:|---|
| `grey_dot_macro` | R | `sq-abs-session-2026-08-06` | — | 730 | 21 | green |
| `grey_dot_terminal` | B | `gc_v2_wo2` | — | 2,719 | 21 | green |
| `confirmed_buy` | R | `sq-abs-session-2026-08-06` | — | 1,839 | 21 | green |
| `rebuy` | R | `sq-abs-session-2026-08-06` | — | 87 | 9 | green |
| `reclaim_waiver` | R | `us_prophet_v2` | 2026-08-13 | 0 | 0 | green |
| `weekly_washout_turn` | R | `washout_turn.v1` | 2026-08-05 | 652 | 20 | green (+1 declared exemption) |
| `sea_event_classes` | R | `pre2010`, `post2010` | — | 10,384 | 15 | green |
| `bottom_watch_terminal` | B | `gc_v2_wo2` | — | 206 | 20 | green |
| `starter_signature` | R | `union-admission-v1-2026-08-11` | — | 2,559 | 21 | green |
| `tier_cascade_t1` | B | `abs-session-2026-08-06` | — | 2,122 | 21 | green |
| `tier_cascade_t2` | B | `abs-session-2026-08-06` | — | 236 | 21 | green |
| `tier_cascade_t3` | B | `abs-session-2026-08-06` | — | 28 | 14 | green |
| `tier_cascade_t4` | B | `abs-session-2026-08-06` | — | 47 | 16 | green |
| `rsi30_cross` | R | `si-naive-comparators-v0-2026-08-14` | — | 1,480 | 22 | green |
| `low20d_bounce` | R | `si-naive-comparators-v0-2026-08-14` | — | 7,437 | 22 | green |
| `stoch2w_cross` | R | `si-naive-comparators-v0-2026-08-14` | — | 593 | 21 | green |
| `starter_pending` | P | `union-admission-v1-2026-08-11` | — | 0 | 0 | n/a (zero rows by law) |
| `starter_failed` | P | `union-admission-v1-2026-08-11` | — | 0 | 0 | n/a (zero rows by law) |
| `starter_converted` | P | `union-admission-v1-2026-08-11` | — | 0 | 0 | n/a (zero rows by law) |
| `amber_early` | P | `terminal-935389d4-2026-08-11` | 2026-08-11 | 0 | 0 | n/a (zero rows by law) |
| `door_r_rearm` | P | `prospective-only by charter` | — | 0 | 0 | n/a (zero rows by law) |
| `turn_watch_deck` | P | `nightly artifact only` | — | 0 | 0 | n/a (zero rows by law) |
| `gc_v2_scores` | P | `per-request computation` | — | 0 | 0 | n/a (zero rows by law) |
| `radar_c1_c2` | P | `live-forward only` | — | 0 | 0 | n/a (zero rows by law) |

### Provenance split

| family_key | field_origin | events |
|---|---|---:|
| `bottom_watch_terminal` | `replay_recomputed` | 206 |
| `confirmed_buy` | `ledger_recorded` | 367 |
| `confirmed_buy` | `replay_recomputed` | 1,472 |
| `grey_dot_macro` | `replay_recomputed` | 730 |
| `grey_dot_terminal` | `replay_recomputed` | 2,719 |
| `low20d_bounce` | `replay_recomputed` | 7,437 |
| `rebuy` | `ledger_recorded` | 87 |
| `rsi30_cross` | `replay_recomputed` | 1,480 |
| `sea_event_classes` | `ledger_recorded` | 10,384 |
| `starter_signature` | `replay_recomputed` | 2,559 |
| `stoch2w_cross` | `replay_recomputed` | 593 |
| `tier_cascade_t1` | `replay_recomputed` | 2,122 |
| `tier_cascade_t2` | `replay_recomputed` | 236 |
| `tier_cascade_t3` | `replay_recomputed` | 28 |
| `tier_cascade_t4` | `replay_recomputed` | 47 |
| `weekly_washout_turn` | `ledger_recorded` | 12 |
| `weekly_washout_turn` | `replay_recomputed` | 640 |

### Era split (`DNR:LAW-ERA-SPLIT` — never pooled across the 2010 break)

| family_key | pre2010 | post2010 |
|---|---:|---:|
| `bottom_watch_terminal` | 95 | 111 |
| `confirmed_buy` | 909 | 930 |
| `grey_dot_macro` | 335 | 395 |
| `grey_dot_terminal` | 1,310 | 1,409 |
| `low20d_bounce` | 3,404 | 4,033 |
| `rebuy` | 46 | 41 |
| `rsi30_cross` | 646 | 834 |
| `sea_event_classes` | 5,224 | 5,160 |
| `starter_signature` | 1,205 | 1,354 |
| `stoch2w_cross` | 282 | 311 |
| `tier_cascade_t1` | 979 | 1,143 |
| `tier_cascade_t2` | 111 | 125 |
| `tier_cascade_t3` | 13 | 15 |
| `tier_cascade_t4` | 25 | 22 |
| `weekly_washout_turn` | 262 | 390 |

## Grey-dot twin parity (counts, not a verdict)

The two implementations stay SEPARATE families regardless of what these counts say (registration §3). Dates are compared on `signal_known_ts` — the decision date both sides key on.

* agreeing fire dates: **654**
* macro-only: **76** · terminal-only: **2,065**
* totals: macro 730 · terminal 2,719 over 21 names

| name | agree | macro-only | terminal-only | macro total | terminal total |
|---|---:|---:|---:|---:|---:|
| AEM | 24 | 3 | 36 | 27 | 60 |
| AG | 17 | 1 | 46 | 18 | 63 |
| B | 57 | 7 | 163 | 64 | 220 |
| BABA | 14 | 2 | 44 | 16 | 58 |
| FFAI | 5 | 0 | 27 | 5 | 32 |
| GOLD | 14 | 3 | 45 | 17 | 59 |
| HL | 14 | 2 | 50 | 16 | 64 |
| KO | 66 | 5 | 253 | 71 | 319 |
| KRUS | 8 | 0 | 29 | 8 | 37 |
| MCD | 67 | 8 | 235 | 75 | 302 |
| MCK | 38 | 4 | 118 | 42 | 156 |
| META | 16 | 1 | 42 | 17 | 58 |
| MSFT | 50 | 4 | 146 | 54 | 196 |
| NEM | 59 | 10 | 170 | 69 | 229 |
| NVDA | 31 | 4 | 107 | 35 | 138 |
| PAAS | 10 | 0 | 56 | 10 | 66 |
| REGN | 46 | 9 | 137 | 55 | 183 |
| UEC | 12 | 4 | 46 | 16 | 58 |
| WMT | 65 | 4 | 199 | 69 | 264 |
| WPM | 22 | 4 | 75 | 26 | 97 |
| YELP | 19 | 1 | 41 | 20 | 60 |

## Grey-dot dual series (as-recorded / as-restated)

* as-recorded fires: **730**
* of which in washout context (today's rule would carve these to `amber_early`): **61**
* as-restated raw-dot reading: **669**

The carve-out is expressed as `promoted_by` edges; **no row is deleted**, so both readings come out of one store. `amber_early` itself remains Class P with zero rows — the flag above is what the rule WOULD have done, never that family's history.

## Attribution join coverage (the only published aggregate)

| family_key | events | attributed | unattributed | coverage |
|---|---:|---:|---:|---:|
| `bottom_watch_terminal` | 206 | 107 | 99 | 51.9% |
| `confirmed_buy` | 1,839 | 436 | 1,403 | 23.7% |
| `grey_dot_macro` | 730 | 353 | 377 | 48.4% |
| `grey_dot_terminal` | 2,719 | 1,153 | 1,566 | 42.4% |
| `low20d_bounce` | 7,437 | 4,418 | 3,019 | 59.4% |
| `rebuy` | 87 | 19 | 68 | 21.8% |
| `rsi30_cross` | 1,480 | 1,056 | 424 | 71.4% |
| `sea_event_classes` | 10,384 | 3,037 | 7,347 | 29.2% |
| `starter_signature` | 2,559 | 1,265 | 1,294 | 49.4% |
| `stoch2w_cross` | 593 | 178 | 415 | 30.0% |
| `tier_cascade_t1` | 2,122 | 486 | 1,636 | 22.9% |
| `tier_cascade_t2` | 236 | 69 | 167 | 29.2% |
| `tier_cascade_t3` | 28 | 8 | 20 | 28.6% |
| `tier_cascade_t4` | 47 | 13 | 34 | 27.7% |
| `weekly_washout_turn` | 652 | 245 | 407 | 37.6% |

Unattributed events are **RETAINED**, carrying a null episode edge: the §7.3 unconditional block needs them at PR-3, because an expert that fires 500 times a year with 5 fires inside episodes would look perfectly localized while being worthless live — and that arithmetic is only possible if the other 495 are still in the store.

## STARTER consequence matrix

**Verdict: `NOT_PIT_RECONSTRUCTABLE`**

Both context artifacts are nightly-overwritten single-vintage JSON keyed by basket/ticker with one as_of; neither is a dated series and no dated basket-state store exists under data/. PIT membership DOES exist (membership_history.parquet's added/removed intervals) but membership is not what licenses a STARTER — the basket's washout STATE on the fire date is, and recomputing that over history would be a new construction with its own gates, not a read of a committed artifact.

*Consequence applied:* starter_pending/starter_failed/starter_converted RECLASSIFY to Class P (zero rows, no synthetic context, no backfill); the admission SIGNATURE ships separately as starter_signature (Class R)

| artifact | role | present | carries a dated history | as_of |
|---|---|:--:|:--:|---|
| `site/basketdata/us_basket_turn.json` | basket_state | yes | NO | 2026-08-13 |
| `site/anticipationdata/us_leader_pullback.json` | leader_pullback_state | yes | NO | 2026-08-13 |
| `data/baskets/membership.json` | membership_current | yes | n/a | — |
| `data/baskets/membership_history.parquet` | membership_history | yes | 1 snapshot date(s) | — |

## Reclaim-waiver era receipts

A zero here is a **structural absence** — the nightly state artifact is overwritten and no historical vintage exists — never evidence that the waiver does nothing.

| name | state available | as_of | qualifies at notch | markers in window | waived |
|---|:--:|---|:--:|---:|---:|
| AEM | yes | 2026-08-13 | yes | 0 | 0 |
| AG | yes | 2026-08-13 | yes | 0 | 0 |
| B | yes | 2026-08-13 | no | 0 | 0 |
| BABA | yes | 2026-08-13 | no | 0 | 0 |
| CBRS | yes | 2026-08-13 | no | 0 | 0 |
| FFAI | yes | 2026-08-13 | no | 0 | 0 |
| GOLD | yes | 2026-08-13 | yes | 0 | 0 |
| HL | yes | 2026-08-13 | yes | 0 | 0 |
| KO | yes | 2026-08-13 | no | 0 | 0 |
| KRUS | yes | 2026-08-13 | no | 0 | 0 |
| MCD | yes | 2026-08-13 | no | 0 | 0 |
| MCK | yes | 2026-08-13 | no | 0 | 0 |
| META | yes | 2026-08-13 | no | 0 | 0 |
| MSFT | yes | 2026-08-13 | no | 0 | 0 |
| NEM | yes | 2026-08-13 | yes | 0 | 0 |
| NVDA | yes | 2026-08-13 | no | 0 | 0 |
| PAAS | yes | 2026-08-13 | yes | 0 | 0 |
| REGN | yes | 2026-08-13 | no | 0 | 0 |
| UEC | yes | 2026-08-13 | yes | 0 | 0 |
| WMT | yes | 2026-08-13 | no | 0 | 0 |
| WPM | yes | 2026-08-13 | no | 0 | 0 |
| YELP | yes | 2026-08-13 | no | 0 | 0 |

## Ledger extraction coverage (counts)

* `data/signal_archive/track_record.parquet` -> `confirmed_buy`, `rebuy`: **454** emitted of **1,160** in store
  * a §7 marker is labelled with its 3D bucket's OPEN date. Rows minted before the sq-abs-session-2026-08-06 anchor era carry labels from the RETIRED 3B resample, whose synthetic left-edge bins are not labels of the current absolute-anchor grid; signal_quality.marker_last_session refuses them and a guessed known_ts would break the known-ts law, so they are counted here instead of stamped. Measured: 100% of era-stamped rows resolve, 32.3% of pre-era-stamp rows do.
  * ledger era `pre-era-stamp`: 1,043 row(s)
  * ledger era `sq-abs-session-2026-08-06`: 117 row(s)
* `data/washout_turn/ledger.jsonl` -> `weekly_washout_turn`: **12** emitted of **13** in store
  * the organ's transitions ledger records the full US universe; only pilot names are extracted, and only the two states this family recognises
* `data/stock_events/events_backfill.parquet ∪ data/stock_events/live` -> `sea_event_classes`: **10,384** emitted of **10,384** in store
  * pure filter, keep-FIRST on the store's own key; a name absent from the SEA universe contributes no rows

## Class P families — enumerated with zero rows

Structural absence is never negative evidence. None of these zeros says the family does nothing; each says its history was never recorded or never existed.

| family_key | first available | why there is no history |
|---|---|---|
| `starter_pending` | — | Class C resolved by the registration §3 consequence matrix: starter_pending/starter_failed/starter_converted RECLASSIFY to Class P (zero rows, no synthetic context, no backfill); the admission SIGNATURE ships separately as starter_signature (Class R) The signature half ships separately as starter_signature; the trio is never merged with it and never partially faked. |
| `starter_failed` | — | Class C resolved by the registration §3 consequence matrix: starter_pending/starter_failed/starter_converted RECLASSIFY to Class P (zero rows, no synthetic context, no backfill); the admission SIGNATURE ships separately as starter_signature (Class R) The signature half ships separately as starter_signature; the trio is never merged with it and never partially faked. |
| `starter_converted` | — | Class C resolved by the registration §3 consequence matrix: starter_pending/starter_failed/starter_converted RECLASSIFY to Class P (zero rows, no synthetic context, no backfill); the admission SIGNATURE ships separately as starter_signature (Class R) The signature half ships separately as starter_signature; the trio is never merged with it and never partially faked. |
| `amber_early` | 2026-08-11 | the family was CREATED on 2026-08-11 when the Terminal began promoting a washout-context grey dot to an amber EARLY marker. It has no history before that date because it did not exist. The as-restated grey-dot reading (the in_washout_context flag on grey_dot_macro) is how W2 shows what WOULD have been carved out — it is not this family's history and is never labelled as it. |
| `door_r_rearm` | — | the organ's own charter forbids historical backfill — every row must be a real forward call. Replaying it would violate the charter that created it. |
| `turn_watch_deck` | — | the deck publishes a nightly artifact and keeps no fire ledger, so no past fire was ever recorded and none can be recovered from a committed artifact. |
| `gc_v2_scores` | — | computed per request with no persistence located in either repo, and its cited source lab (harness/e_factors.py) does not exist in either repo — so there is neither a store to read nor a specification to port. |
| `radar_c1_c2` | — | the Radar contract §5 replay rule: historical replay of a LIVE-state input requires minute reconstruction of what the indicator showed at the decision timestamp. No U.S. equity intraday bars exist in-repo, so these detectors are live-forward only and may never be backfilled from EOD values. |

## Leak fixtures (registration §7)

A row marked **exempt** is a property the producer genuinely does not have, with the mechanism named — never a loosened ceiling. There is exactly one.

| family group | fixture | name | verdict | detail |
|---|---|---|:--:|---|
| bottom_watch | `truncation_invariance` | NVDA | yes | 7 event(s) identical on the truncated prefix |
| bottom_watch | `shift_audit_start_invariance` | NVDA | yes | 12 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| bottom_watch | `shift_audit_forming_bar` | NVDA | yes | 12 completed event(s) unchanged by an in-progress bar |
| bottom_watch | `feed_truncation` | NVDA | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| bottom_watch | `truncation_invariance` | AEM | yes | 0 event(s) identical on the truncated prefix |
| bottom_watch | `shift_audit_start_invariance` | AEM | yes | 1 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| bottom_watch | `shift_audit_forming_bar` | AEM | yes | 1 completed event(s) unchanged by an in-progress bar |
| bottom_watch | `feed_truncation` | AEM | yes | 1 probe event(s) vanished when the feed stopped at their signal_ts |
| confirmed_buy | `truncation_invariance` | NVDA | yes | 52 event(s) identical on the truncated prefix |
| confirmed_buy | `shift_audit_start_invariance` | NVDA | yes | 86 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| confirmed_buy | `shift_audit_forming_bar` | NVDA | yes | 88 completed event(s) unchanged by an in-progress bar |
| confirmed_buy | `feed_truncation` | NVDA | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| confirmed_buy | `append_only_conformance` | NVDA | yes | 24 row(s) all present in the store; keep-FIRST dropped 0 duplicate(s) |
| confirmed_buy | `truncation_invariance` | AEM | yes | 24 event(s) identical on the truncated prefix |
| confirmed_buy | `shift_audit_start_invariance` | AEM | yes | 35 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| confirmed_buy | `shift_audit_forming_bar` | AEM | yes | 38 completed event(s) unchanged by an in-progress bar |
| confirmed_buy | `feed_truncation` | AEM | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| confirmed_buy | `append_only_conformance` | AEM | yes | store is empty |
| grey_dot | `truncation_invariance` | NVDA | yes | 110 event(s) identical on the truncated prefix |
| grey_dot | `shift_audit_start_invariance` | NVDA | yes | 162 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| grey_dot | `shift_audit_forming_bar` | NVDA | yes | 173 completed event(s) unchanged by an in-progress bar |
| grey_dot | `feed_truncation` | NVDA | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| grey_dot | `truncation_invariance` | AEM | yes | 53 event(s) identical on the truncated prefix |
| grey_dot | `shift_audit_start_invariance` | AEM | yes | 80 event(s) compared after dropping 37 leading session(s); 4 differ (5.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| grey_dot | `shift_audit_forming_bar` | AEM | yes | 87 completed event(s) unchanged by an in-progress bar |
| grey_dot | `feed_truncation` | AEM | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| naive | `truncation_invariance` | NVDA | yes | 300 event(s) identical on the truncated prefix |
| naive | `shift_audit_start_invariance` | NVDA | yes | 429 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| naive | `shift_audit_forming_bar` | NVDA | yes | 449 completed event(s) unchanged by an in-progress bar |
| naive | `feed_truncation` | NVDA | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| naive | `truncation_invariance` | AEM | yes | 126 event(s) identical on the truncated prefix |
| naive | `shift_audit_start_invariance` | AEM | yes | 170 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| naive | `shift_audit_forming_bar` | AEM | yes | 209 completed event(s) unchanged by an in-progress bar |
| naive | `feed_truncation` | AEM | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| reclaim_waiver | `truncation_invariance` | NVDA | yes | 0 event(s) identical on the truncated prefix |
| reclaim_waiver | `shift_audit_start_invariance` | NVDA | yes | 0 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| reclaim_waiver | `shift_audit_forming_bar` | NVDA | yes | no events on this frame |
| reclaim_waiver | `feed_truncation` | NVDA | yes | no event on this frame becomes knowable after its own signal_ts (1D-grain family: signal_ts == known_ts by construction) |
| reclaim_waiver | `truncation_invariance` | AEM | yes | 0 event(s) identical on the truncated prefix |
| reclaim_waiver | `shift_audit_start_invariance` | AEM | yes | 0 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| reclaim_waiver | `shift_audit_forming_bar` | AEM | yes | no events on this frame |
| reclaim_waiver | `feed_truncation` | AEM | yes | no event on this frame becomes knowable after its own signal_ts (1D-grain family: signal_ts == known_ts by construction) |
| sea | `append_only_conformance` | NVDA | yes | 677 row(s) all present in the store; keep-FIRST dropped 0 duplicate(s) |
| sea | `append_only_conformance` | AEM | yes | 328 row(s) all present in the store; keep-FIRST dropped 0 duplicate(s) |
| starter | `truncation_invariance` | NVDA | yes | 79 event(s) identical on the truncated prefix |
| starter | `shift_audit_start_invariance` | NVDA | yes | 112 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| starter | `shift_audit_forming_bar` | NVDA | yes | 120 completed event(s) unchanged by an in-progress bar |
| starter | `feed_truncation` | NVDA | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| starter | `truncation_invariance` | AEM | yes | 43 event(s) identical on the truncated prefix |
| starter | `shift_audit_start_invariance` | AEM | yes | 64 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| starter | `shift_audit_forming_bar` | AEM | yes | 71 completed event(s) unchanged by an in-progress bar |
| starter | `feed_truncation` | AEM | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| tiers | `truncation_invariance` | NVDA | yes | 66 event(s) identical on the truncated prefix |
| tiers | `shift_audit_start_invariance` | NVDA | yes | 104 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| tiers | `shift_audit_forming_bar` | NVDA | yes | 111 completed event(s) unchanged by an in-progress bar |
| tiers | `feed_truncation` | NVDA | yes | no event on this frame becomes knowable after its own signal_ts (1D-grain family: signal_ts == known_ts by construction) |
| tiers | `truncation_invariance` | AEM | yes | 36 event(s) identical on the truncated prefix |
| tiers | `shift_audit_start_invariance` | AEM | yes | 53 event(s) compared after dropping 37 leading session(s); 0 differ (0.00%, ceiling 5% / floor 1) — producer warm-up sensitivity, not a window dependence |
| tiers | `shift_audit_forming_bar` | AEM | yes | 58 completed event(s) unchanged by an in-progress bar |
| tiers | `feed_truncation` | AEM | yes | no event on this frame becomes knowable after its own signal_ts (1D-grain family: signal_ts == known_ts by construction) |
| washout_turn | `truncation_invariance` | AEM | yes | 6 event(s) identical on the truncated prefix |
| washout_turn | `shift_audit_start_invariance` | AEM | **exempt** | NOT APPLICABLE, mechanism named: engine.washout_turn's depth percentile is a declared WHOLE-SAMPLE statistic — its own _evaluate documents it as 'percent of the FULL weekly line history strictly BELOW bar j'. The reference distribution therefore legitimately depends on how much history exists, so a cross sitting near the 15th-percentile gate flips when leading history is dropped (measured on a synthetic tape: 8/18 events, 44%). This is PAST-data window dependence, not future leakage: the organ's three leak fixtures (truncation invariance, forming bar, feed truncation) are green, and the replay always walks one fixed full per-name prefix chain, so the window is constant across the whole extraction. |
| washout_turn | `shift_audit_forming_bar` | AEM | yes | 10 completed event(s) unchanged by an in-progress bar |
| washout_turn | `feed_truncation` | AEM | yes | 3 probe event(s) vanished when the feed stopped at their signal_ts |
| washout_turn | `append_only_conformance` | AEM | yes | 2 row(s) all present in the store; keep-FIRST dropped 0 duplicate(s) |

