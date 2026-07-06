# BD Phase-0b — S4-/S5-/S13- Species Batch Tape Report

**Authority:** `research/short_side/BD_PHASE0B_PREREG.md` (FROZEN; thresholds/windows read from prereg)
**Governing:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md` §5.4, RUL-U4, RUL-U3a
**Contamination stamp:** `derived_from_surface: bd_phase0_tape` — this batch is a re-read of the Phase-0 tape period; any future prereg on this tape must declare this as a contamination surface.
**Status:** RUN PENDING — populate with actual results after running `scripts/research/dump_breakdown_events.py` Mac-locally.

---

## In Plain English

Three additional price-based breakdown patterns (BD-4 Two-Clock Rollover, BD-5 Coiled Breakdown, BD-6 Within-Sector Leader Fade) were run through the Phase-0 apparatus verbatim — same universe, same liquidity floor, same era window, same paired two-sided grading and seeded controls as BD-1/2/3. This is a descriptive study: it measures whether these patterns are associated with meaningfully worse forward outcomes than matched random bars. No signal is promoted; no site surface is modified.

For each definition, the table below shows: how many episodes fired in the ERA window (2021-07-06 to present), the annual breakdown, how often the pattern led to a long-side stop vs. a short-side favorable outcome, and how that compares to matched random bars from the same ticker and year. A definition is worth a Phase-1 prereg only if its long-stop rate exceeds the control by ≥5pp with a CI excluding zero. Fewer than 100 episodes means the estimate is underpowered and the result is parked regardless of the point estimate.

---

## §1. Budget (RUL-U3a)

`TrialLedger.log_declared_budget(3, family='short_side')` logged BEFORE this run (Phase-0b).
Phase-0 budget (3 definitions) logged previously.

**max()-semantics note:** `log_declared_budget` keeps a per-family **max()** floor, not a cumulative sum. Each declared_budget=3 is a within-study BH floor for its own definition set; cross-study multiplicity within `short_side` is NOT captured by the declared budget. This is tolerable because both Phase-0 and Phase-0b are descriptive/research-only (no DSR). Family `literal_n` (distinct configs logged) is printed in the run output and recorded in `breakdown_events_summary.json` ("family_literal_n").

---

## §2. Per-Definition Episode Counts and Base Rates

*Populated from `data/research/breakdown_events_summary.json` after Mac-local run.*

### BD-4 — S4- Two-Clock Rollover

| Field | Value |
|---|---|
| N episodes | RUN PENDING |
| Per year | RUN PENDING |
| Long stop rate (clean8_21) | RUN PENDING |
| Long stop rate (clean15_126) | RUN PENDING |
| Short favorable rate (short21) | RUN PENDING |
| Short favorable rate (short126) | RUN PENDING |
| Control long stop rate | RUN PENDING |
| Control long stop rate CI | RUN PENDING |
| Powering note | RUN PENDING — if < 100 episodes, PARKED |

**BD-4 x BD-3 Overlap (REQUIRED check per prereg §1):**
- Near-overlap share (±21 bars, same ticker): RUN PENDING
- Redundancy flag (>50%): RUN PENDING
- If redundancy_flag=True: BD-4 is treated as a BD-3 variant at Phase-1, not an independent species.

### BD-5 — S5- Coiled Breakdown

| Field | Value |
|---|---|
| N episodes | RUN PENDING |
| Per year | RUN PENDING |
| Long stop rate (clean8_21) | RUN PENDING |
| Long stop rate (clean15_126) | RUN PENDING |
| Short favorable rate (short21) | RUN PENDING |
| Short favorable rate (short126) | RUN PENDING |
| Control long stop rate | RUN PENDING |
| Control long stop rate CI | RUN PENDING |
| Powering note | RUN PENDING — if < 100 episodes, PARKED |

### BD-6 — S13- Within-Sector Leader Fade

**Declared limitation:** a current-date sector map applied to historical bars is an anachronism, accepted because sector membership is slow-moving (same declaration as L6-P0 §2.5.4).

**Sector map source:** `data/breadth/ticker_sectors.parquet` (output of `scripts/build_sector_map.py`). If absent, BD-6 yields 0 events and this section is vacuous.

| Field | Value |
|---|---|
| Sector map artifact as_of | RUN PENDING |
| N tickers with sector coverage | RUN PENDING |
| N episodes | RUN PENDING |
| Per year | RUN PENDING |
| Long stop rate (clean8_21) | RUN PENDING |
| Long stop rate (clean15_126) | RUN PENDING |
| Short favorable rate (short21) | RUN PENDING |
| Short favorable rate (short126) | RUN PENDING |
| Control long stop rate | RUN PENDING |
| Powering note | RUN PENDING — if < 100 episodes, PARKED |

---

## §3. Paired Asymmetry Deltas (Episode-Clustered CIs)

*Cluster variable: ticker×year. Bootstrap iterations: 5,000. Horizon pairing: short21↔clean8_21; short126↔clean15_126.*

| Definition | Horizon | Mean paired diff (pp) | CI95 (pp) | n matured |
|---|---|---|---|---|
| BD-4 | 21d | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-4 | 126d | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-5 | 21d | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-5 | 126d | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-6 | 21d | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-6 | 126d | RUN PENDING | RUN PENDING | RUN PENDING |

Interpretation: positive = short-favorable dominates long-stopped; negative = long-stopped dominates.

---

## §4. Control Comparison (Between-Group)

| Definition | Event stop rate | Control stop rate | Delta (pp) | n events | n controls |
|---|---|---|---|---|---|
| BD-4 | RUN PENDING | RUN PENDING | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-5 | RUN PENDING | RUN PENDING | RUN PENDING | RUN PENDING | RUN PENDING |
| BD-6 | RUN PENDING | RUN PENDING | RUN PENDING | RUN PENDING | RUN PENDING |

---

## §5. Six-Way Overlap Matrix

*Exact-date overlap (same ticker, same event_date) across all six definitions.*

*RUN PENDING — see `overlap_matrix.matrix` in breakdown_events_summary.json.*

BD-4 x BD-3 near-overlap (±21 bars): RUN PENDING

---

## §6. Reading Guide (from BD_PHASE0_PREREG §6 + RUL-U4 amendment)

Pre-committed reading guide (NOT gates):
- A definition is **worth a Phase-1 prereg** if its long-side stop rate exceeds the matched control's by ≥5pp with a CI excluding 0 at the paired-cluster level.
- It is **avoid-only** if long-side degrades but short-side favorable rate does not exceed control.
- A definition with **<100 episodes is PARKED** as underpowered regardless of point estimates.

**RUL-U4 amendment:** any Phase-1 forward prereg arising from Phase-0b must carry a compensating gate at least as strict as BD-AVOID-1's ≥8pp (this tape will have been read once).

No cross-definition selection statistic is computed. No promotion. No site surface.

---

## §7. Seeding Contract

- BD-1/2/3 controls: drawn from the global `rng=np.random.default_rng(42)` passed per-ticker. BD-4/5/6 events are appended to the event pool before controls are drawn, so control pairings for tickers with BD-4/5/6 events differ from Phase-0-only runs. BD-1/2/3 **event rows** (graded observations) are unchanged.
- BD-4/5/6 share the same pooled control draw (shared CONTROL rows cover all six definitions).
- Separate seeds (7891/13421/19937) are declared for BD-4/5/6 in the module constants but are not currently used for separate per-definition draws (all definitions use the shared pool). These are reserved for future use.

---

## §8. What This Does NOT Show

Same as BD_PHASE0_PREREG §7. Additionally: BD-4/5/6 base rates say nothing about BD-2/BD-3 (already registered forward via BD-AVOID-1); nothing here re-reads or amends the Phase-0 definitions; no cross-definition selection statistic.

---

## Amendments

*(none)*
