# BD Phase-0b — S4-/S5-/S13- Species Batch Tape Report

**Authority:** `research/short_side/BD_PHASE0B_PREREG.md` (FROZEN; thresholds/windows read from prereg)
**Governing:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md` §5.4, RUL-U4, RUL-U3a
**Contamination stamp:** `derived_from_surface: bd_phase0_tape` — this batch is a re-read of the Phase-0 tape period; any future prereg on this tape must declare this as a contamination surface.
**Status:** RUN COMPLETE 2026-07-06. Runtime: 372.4s. Universe: 1,007 tickers (replay_boarded fires). BD-6 sector coverage: 961 tickers.

---

## In Plain English

Three additional price-based breakdown patterns (BD-4 Two-Clock Rollover, BD-5 Coiled Breakdown, BD-6 Within-Sector Leader Fade) were run through the Phase-0 apparatus verbatim — same universe, same liquidity floor, same era window (2021-07-06+), same paired two-sided grading and seeded controls as BD-1/2/3. This is a descriptive study: it measures whether these patterns are associated with meaningfully worse forward outcomes than matched random bars from the same ticker and year. No signal is promoted; no site surface is modified.

All three definitions cleared the 100-episode powering floor. BD-4 (616 episodes) and BD-6 (444 episodes) show no stop-rate elevation versus controls: BD-4 delta = −12.45pp (stop rate LOWER than controls at 21d), BD-6 delta = −0.76pp (null). BD-5 (6,282 episodes) also shows no elevation: delta = −1.69pp. Per the §6 reading guide, none of BD-4/5/6 clear the ≥5pp CI-excluding-zero threshold required for a Phase-1 prereg; all three are parked at observe-and-continue unless signal accumulates.

The BD-4 × BD-3 near-overlap share is 37.5% (231/616 BD-4 episodes within ±21 bars of a BD-3 episode), below the 50% redundancy threshold. BD-4 is not a BD-3 variant at this sample size.

---

## §1. Budget (RUL-U3a)

`TrialLedger.log_declared_budget(3, family='short_side')` logged BEFORE this run (Phase-0b).
Phase-0 budget (3 definitions) logged previously.
Family `literal_n` (distinct configs logged): **12** (BD-1 through BD-6 = 6 definitions × 2 runs Phase-0/0b, deduplicated by config hash — actual distinct config entries = 6 new Phase-0b + 6 Phase-0 re-logged = 12).

**max()-semantics note:** `log_declared_budget` keeps a per-family **max()** floor, not a cumulative sum. Each declared_budget=3 is a within-study BH floor for its own definition set; cross-study multiplicity within `short_side` is NOT captured by the declared budget. This is tolerable because both Phase-0 and Phase-0b are descriptive/research-only (no DSR).

---

## §2. Per-Definition Episode Counts and Base Rates

Universe: 1,007 tickers. ERA window: 2021-07-06 to 2026-07-06. Liquidity floor: $5M 21d median ADV, price ≥$3.

### BD-4 — S4- Two-Clock Rollover

| Field | Value |
|---|---|
| N episodes | 616 |
| Per year | 2022: 51, 2023: 117, 2024: 216, 2025: 134, 2026: 98 |
| Long stop rate (clean8_21, 21d) | 29.21% (n_matured=606) |
| Long stop rate (clean15_126, 126d) | 63.69% (n_matured=515) |
| Short favorable rate (short21) | 13.20% (adverse=41.42%, n_matured=606) |
| Short favorable rate (short126) | 15.34% (adverse=77.67%, n_matured=515) |
| Control long stop rate (clean8_21) | 41.66% (n=99,881) |
| Control long stop rate (clean15_126) | 66.01% (n=88,094) |
| vs control delta (clean8_21) | **−12.45pp** (event stop LOWER than control) |
| vs control delta (clean15_126) | **−2.32pp** |
| Powering note | 616 episodes — powered |

**BD-4 x BD-3 Overlap (REQUIRED check per prereg §1):**
- Exact-date overlap: 0 episodes (share_exact=0.0)
- Near-overlap share (±21 bars, same ticker): **231/616 = 37.5%** (share_near=0.375)
- Redundancy flag (>50%): **False** — BD-4 is NOT a BD-3 variant at this sample size.
- Note: 37.5% near-overlap is non-trivial; if future data pushes this above 50%, the redundancy flag triggers at Phase-1 stage.

### BD-5 — S5- Coiled Breakdown

| Field | Value |
|---|---|
| N episodes | 6,282 |
| Per year | 2022: 512, 2023: 2,186, 2024: 1,605, 2025: 1,420, 2026: 559 |
| Long stop rate (clean8_21, 21d) | 39.97% (n_matured=6,197) |
| Long stop rate (clean15_126, 126d) | 63.84% (n_matured=5,663) |
| Short favorable rate (short21) | 21.98% (adverse=46.17%, n_matured=6,197) |
| Short favorable rate (short126) | 19.42% (adverse=77.31%, n_matured=5,663) |
| Control long stop rate (clean8_21) | 41.66% (n=99,881) |
| Control long stop rate (clean15_126) | 66.01% (n=88,094) |
| vs control delta (clean8_21) | **−1.69pp** (null — event stop marginally lower than control) |
| vs control delta (clean15_126) | **−2.17pp** |
| Powering note | 6,282 episodes — well powered |

### BD-6 — S13- Within-Sector Leader Fade

**Declared limitation:** a current-date sector map applied to historical bars is an anachronism, accepted because sector membership is slow-moving (same declaration as L6-P0 §2.5.4).

**Sector map source:** `data/breadth/ticker_sectors.parquet` (git-tracked, 1,516 rows, 2026-07-06). Tickers with sector coverage: 961.

| Field | Value |
|---|---|
| Sector map artifact as_of | 2026-07-06 |
| N tickers with sector coverage | 961 |
| N episodes | 444 |
| Per year | 2022: 56, 2023: 112, 2024: 100, 2025: 110, 2026: 66 |
| Long stop rate (clean8_21, 21d) | 40.90% (n_matured=423) |
| Long stop rate (clean15_126, 126d) | 67.99% (n_matured=378) |
| Short favorable rate (short21) | 21.28% (adverse=46.34%, n_matured=423) |
| Short favorable rate (short126) | 21.16% (adverse=76.19%, n_matured=378) |
| Control long stop rate (clean8_21) | 41.66% (n=99,881) |
| Control long stop rate (clean15_126) | 66.01% (n=88,094) |
| vs control delta (clean8_21) | **−0.76pp** (null) |
| vs control delta (clean15_126) | **+1.98pp** (small positive; below ≥5pp threshold) |
| Powering note | 444 episodes — powered |

---

## §3. Paired Asymmetry Deltas (Episode-Clustered CIs)

*Cluster variable: ticker×year. Bootstrap iterations: 5,000. Horizon pairing: short21↔clean8_21; short126↔clean15_126.*
*Positive = short-favorable dominates long-stopped; negative = long-stopped dominates.*

| Definition | Horizon | Mean paired diff (pp) | CI95 (pp) | n matured |
|---|---|---|---|---|
| BD-4 | 21d (clean8_21 × short21) | −16.01 | [−19.01, −13.10] | 606 |
| BD-4 | 126d (clean15_126 × short126) | −48.35 | [−52.66, −43.97] | 515 |
| BD-5 | 21d (clean8_21 × short21) | −17.99 | [−18.97, −17.07] | 6,197 |
| BD-5 | 126d (clean15_126 × short126) | −44.41 | [−45.69, −43.08] | 5,663 |
| BD-6 | 21d (clean8_21 × short21) | −19.62 | [−23.46, −15.85] | 423 |
| BD-6 | 126d (clean15_126 × short126) | −46.83 | [−51.85, −41.71] | 378 |

All three definitions show strongly negative paired diffs (long-stopped dominates short-favorable), consistent with the Phase-0 definitions and the general short-side null: these patterns do not exhibit short-side edge over the measured horizons.

---

## §4. Control Comparison (Between-Group, 21d clean8_21)

| Definition | Event stop rate | Control stop rate | Delta (pp) | n events | n controls |
|---|---|---|---|---|---|
| BD-1 (Phase-0 ref) | 42.38% | 41.66% | +0.72pp | — | 99,881 |
| BD-2 (Phase-0 ref) | 51.46% | 41.66% | +9.80pp | — | 99,881 |
| BD-3 (Phase-0 ref) | 58.61% | 41.66% | +16.95pp | — | 99,881 |
| BD-4 | 29.21% | 41.66% | **−12.45pp** | 606 | 99,881 |
| BD-5 | 39.97% | 41.66% | **−1.69pp** | 6,197 | 99,881 |
| BD-6 | 40.90% | 41.66% | **−0.76pp** | 423 | 99,881 |

Phase-0 reference row (126d clean15_126, for completeness):

| Definition | Event stop rate | Control stop rate | Delta (pp) | n events | n controls |
|---|---|---|---|---|---|
| BD-3 | 74.07% | 66.01% | +8.06pp | — | 88,094 |
| BD-4 | 63.69% | 66.01% | −2.32pp | 515 | 88,094 |
| BD-5 | 63.84% | 66.01% | −2.17pp | 5,663 | 88,094 |
| BD-6 | 67.99% | 66.01% | +1.98pp | 378 | 88,094 |

---

## §5. Six-Way Overlap Matrix (Exact-Date, Same Ticker)

|  | BD-1 | BD-2 | BD-3 | BD-4 | BD-5 | BD-6 |
|---|---|---|---|---|---|---|
| **BD-1** | 1,330 | 27 | 13 | 0 | 3 | 0 |
| **BD-2** | 27 | 19,891 | 238 | 16 | 238 | 15 |
| **BD-3** | 13 | 238 | 5,553 | 0 | 72 | 4 |
| **BD-4** | 0 | 16 | 0 | 616 | 0 | 2 |
| **BD-5** | 3 | 238 | 72 | 0 | 6,282 | 11 |
| **BD-6** | 0 | 15 | 4 | 2 | 11 | 444 |

**BD-4 × BD-3 near-overlap (±21 bars, same ticker — REQUIRED per BD_PHASE0B_PREREG §1):**
- n_bd4=616, n_bd3=5,553
- Exact overlap: 0 episodes
- Near-overlap (≤21 business days): **231 episodes** (37.5% of BD-4)
- Redundancy flag: **False** (threshold = 50%)

BD-5 × BD-2 has non-trivial exact overlap (238/19,891 = 1.2% of BD-2 episodes). All other cross-definition overlaps are sparse.

---

## §6. Reading Guide (from BD_PHASE0_PREREG §6 + RUL-U4 amendment)

Pre-committed reading guide (NOT gates):
- A definition is **worth a Phase-1 prereg** if its long-side stop rate exceeds the matched control's by ≥5pp with a CI excluding 0 at the paired-cluster level.
- It is **avoid-only** if long-side degrades but short-side favorable rate does not exceed control.
- A definition with **<100 episodes is PARKED** as underpowered regardless of point estimates.

**RUL-U4 amendment:** any Phase-1 forward prereg arising from Phase-0b must carry a compensating gate at least as strict as BD-AVOID-1's ≥8pp (this tape will have been read once).

### §6.1 Verdicts per Reading Guide

**BD-4 (616 episodes, clean8_21 delta = −12.45pp):** Long stop rate is LOWER than controls at 21d. Does not clear ≥5pp threshold in the positive direction. **PARKED** — no Phase-1 prereg warranted. Observe-and-continue.

**BD-5 (6,282 episodes, clean8_21 delta = −1.69pp):** Long stop rate is essentially flat vs. controls (null). Does not clear threshold. **PARKED** — no Phase-1 prereg warranted. Observe-and-continue.

**BD-6 (444 episodes, clean8_21 delta = −0.76pp; clean15_126 delta = +1.98pp):** 21d null; 126d marginally positive but below ≥5pp threshold. **PARKED** — no Phase-1 prereg warranted. Observe-and-continue.

No cross-definition selection statistic is computed. No promotion. No site surface.

---

## §7. Seeding Contract

**CORRECTED from draft stub.** The seeding contract was restructured as part of this run to enforce byte-identity of BD-1/2/3 rows and their control draws vs. a Phase-0-only run:

- **BD-1/2/3 controls:** drawn from the global `rng=np.random.default_rng(42)` passed per-ticker, using ONLY the BD-1/2/3 event pool. BD-4/5/6 events do NOT enter this pool. BD-1/2/3 event rows AND their control draws are byte-identical to any Phase-0-only run using the same code and data.
- **BD-4/5/6 controls:** each definition uses its OWN declared per-definition seed constant (BD4=7891, BD5=13421, BD6=19937), XOR-ed with a ticker hash for per-ticker variation. This is a SEPARATE RNG pass that does not advance the global rng state.
- **Preservation verified:** BD-1/2/3 event rows in the new tape are exactly identical (NaN-safe comparison, 0 diffs across all key columns) to the Phase-0-only tape backup.

Note: control row differences between this tape and the old Phase-0 tape are expected (the old tape used a prior seeding path; the invariant is Phase-0b == hypothetical Phase-0-only run using the *current* code and same data — proved by the TestSeedingStability test suite, 89 tests passing).

---

## §8. What This Does NOT Show

Same as BD_PHASE0_PREREG §7. Additionally: BD-4/5/6 base rates say nothing about BD-2/BD-3 (already registered forward via BD-AVOID-1); nothing here re-reads or amends the Phase-0 definitions; no cross-definition selection statistic.

---

## Amendments

*(none)*
