# cycle-ladder absolute session anchor — blast radius

Era `cyc-abs-session-2026-08-06` · ruling `research/CYCLES_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`

Generated 2026-08-07T01:47Z · store as-of dates are per-universe (read from the stores, never the wall clock).

Every number is measured through `cycles.analyze()` — the path the nightly libraries, the standout strip's `bottoming-alignment` key and the ladder log actually read — with the retired `resample` construction frozen verbatim in this script and monkeypatched in for the OLD pass.

## 1. Old → new, per production loader

| universe | graded | state flips | signal_date re-keys | tier flips | admission flips | score moves | store as-of |
|---|---:|---:|---:|---:|---:|---:|---|
| data/stocks (deep US) | 238 | 7 (2.9%) | 6 | 9 | 6 | 7 | 2026-08-05 |
| data/baskets/ohlcv (2014-start US) | 2698 | 89 (3.3%) | 109 | 98 | 50 | 89 | 2026-08-05 |
| breadth _closes_cache (~345-bar rolling) | 500 | 6 (1.2%) | 12 | 27 | 13 | 6 | 2026-07-31 |
| china_search closes (2021-start CN) | 1744 | 21 (1.2%) | 28 | 37 | 31 | 21 | 2026-08-06 |
| data/hk index store (HK) | 9 | 0 (0.0%) | 0 | 0 | 0 | 0 | 2026-08-06 |
| data/canada index store (CA) | 16 | 1 (6.2%) | 1 | 1 | 1 | 1 | 2026-08-06 |

`state flips` = the ladder's headline read re-draws ONCE at cutover (R-CY4's disclosed cost). `signal_date re-keys` = same standing state, walk-back date moved — the phantom-row class the R-CY5 seam guard suppresses at ingestion. `admission flips` = the standout-strip SELECTION verdict (`aligned`) changed — the board-surface stake that made this the highest-priority sibling.

- **data/stocks (deep US)** state-flip examples: ANET TURN SIGNALED→FRESH BUY; CRWD TOP WATCH→FRESH BUY; EQR TURN SIGNALED→TOP WATCH; EQT COUNTERTREND BOUNCE→TURN SIGNALED; EXR FRESH BUY→TURN SIGNALED; JPM TOP WATCH→TURN SIGNALED; PPG TURN SIGNALED→RALLY ON
- **data/stocks (deep US)** admission-flip examples: AZO PRIME→APPROACHING; EQT —→PRIME; EXR ARMED→APPROACHING; MCD PRIME→APPROACHING; MS ARMED→APPROACHING; PG ARMED→APPROACHING
- **data/baskets/ohlcv (2014-start US)** state-flip examples: AIT TOP WATCH→TURN SIGNALED; ALK FRESH BUY→TURN SIGNALED; AMCX TURN SIGNALED→FRESH BUY; AME TOP WATCH→FRESH BUY; ANET TURN SIGNALED→FRESH BUY; APOG FRESH BUY→TURN SIGNALED; BKD TURN SIGNALED→COUNTERTREND BOUNCE; BLZE TOP WATCH→TURN SIGNALED
- **data/baskets/ohlcv (2014-start US)** admission-flip examples: ADNT —→PRIME; AURA PRIME→—; AVNT ARMED→APPROACHING; AZO PRIME→APPROACHING; BLBD ARMED→APPROACHING; BMI APPROACHING→ARMED; CIX ARMED→—; CMT PRIME→APPROACHING
- **breadth _closes_cache (~345-bar rolling)** state-flip examples: F TURN SIGNALED→COUNTERTREND BOUNCE; GE COUNTERTREND BOUNCE→TURN SIGNALED; HST FRESH BUY→TOP WATCH; XOM TOP WATCH→COUNTERTREND BOUNCE; IEX TURN SIGNALED→FRESH BUY; NTAP TOP WATCH→FRESH BUY
- **breadth _closes_cache (~345-bar rolling)** admission-flip examples: AZO PRIME→APPROACHING; DAL APPROACHING→ARMED; FANG —→PRIME; EQT —→PRIME; EXR APPROACHING→ARMED; F ARMED→—; GE —→ARMED; ORLY PRIME→—
- **china_search closes (2021-start CN)** state-flip examples: 300750.SZ TURN SIGNALED→COUNTERTREND BOUNCE; 601233.SS FRESH BUY→TURN SIGNALED; 688336.SS TURN SIGNALED→COUNTERTREND BOUNCE; 000933.SZ TURN SIGNALED→FRESH BUY; 600219.SS COUNTERTREND BOUNCE→TURN SIGNALED; 000921.SZ COUNTERTREND BOUNCE→TURN SIGNALED; 600157.SS FRESH BUY→TURN SIGNALED; 002779.SZ COUNTERTREND BOUNCE→TURN SIGNALED
- **china_search closes (2021-start CN)** admission-flip examples: 600919.SS APPROACHING→ARMED; 601898.SS —→PRIME; 605117.SS PRIME→APPROACHING; 600027.SS —→PRIME; 688336.SS PRIME→—; 600219.SS —→PRIME; 601216.SS APPROACHING→PRIME; 000921.SZ —→ARMED
- **data/canada index store (CA)** state-flip examples: XIC.TO TURN SIGNALED→TOP WATCH
- **data/canada index store (CA)** admission-flip examples: XEG.TO APPROACHING→PRIME

## 2. Cross-loader agreement on AS-OF-ALIGNED reads — the live symptom

Both sides of each pair are truncated to that name's SHARED last date before reading. That alignment is load-bearing: the rolling breadth cache is rebuilt on its own schedule and was measured ending 2026-07-31 while the deep store ran through 08-06, so an unaligned comparison reports a 4-session LAG as loader disagreement (a first pass of this script did exactly that — 143 phantom 'disagreements'). Depth still differs by design and is reported.

| pair | aligned names | depth differs | state disagreements BEFORE | AFTER | tier disagreements BEFORE | AFTER |
|---|---:|---:|---:|---:|---:|---:|
| deep ∩ data/baskets/ohlcv (2014-start US) | 237 | 215 | 7 | 1 | 6 | 0 |
| deep ∩ breadth _closes_cache (~345-bar rolling) | 235 | 235 | 8 | 5 | 7 | 2 |

A residual AFTER is never a GRID disagreement: the anchor guarantees one grid per name, but it cannot make two stores agree about what a close WAS, and it does not touch the parts of the ladder that legitimately read depth. The breadth-cache pair keeps the larger residual for that second reason — at ~345 bars `cycle_state`'s trough history and `signal_age`'s 600-bar walk-back are genuinely truncated, so a state can differ from the deep store's on the same night without any bin-phase involvement (a DEPTH effect, disclosed, not silently 'fixed' here — the R8/R-CY9 precedent).

## 3. calibrate_ladder — intra-run re-anchoring healed (R-CY6)

Fixed-vs-slid window ladder-state agreement over 12 deep names (600- vs 590-bar windows at 50-bar eval steps): **OLD 97.46%** (2034/2087) → **NEW 100.0%** (2087/2087). The residual under NEW is daily-indicator EWM warm-up (window-length sensitivity, pre-existing and unchanged), not bin phase.

Per-state table drift — 40 deep names × their trailing 4000 sessions, the IDENTICAL panel through both passes (old → new). A drift comparison, not a shipping calibration:

| state | n | hit_pct | avg_fwd_pct | dd_med_pct |
|---|---|---|---|---|
| BOTTOM WATCH | 1821 | 59.0 | 1.85 | -2.76 |
| BOTTOM WATCH +early-bull | 60 | 63.3 | 2.81 | -2.33 |
| BOTTOM WATCH no-early | 1761 | 58.9 | 1.82 | -2.78 |
| COUNTERTREND BOUNCE | 6763 → 6750 | 59.6 → 59.5 | 1.83 | -2.95 |
| DECLINE | 3340 | 63.1 | 2.44 | -3.26 |
| FRESH BUY | 1888 → 1877 | 61.4 → 61.2 | 1.59 → 1.6 | -2.63 → -2.69 |
| RALLY ON | 1878 → 1882 | 59.1 | 1.88 | -2.53 |
| ROLLING OVER | 131 | 58.8 | 1.84 | -2.31 |
| TOP WATCH | 5549 → 5569 | 57.3 → 57.2 | 1.13 | -2.79 |
| TURN SIGNALED | 7724 | 58.3 → 58.6 | 1.51 → 1.5 | -2.88 → -2.87 |

The shipped `ladder_calibration.json` files are PRE-era measurements re-baked on their normal schedule (`recalibrate.py`, `calibrate_china.py`, `calibrate_hk.py`) — cells now carry `anchor_era` so a consumer can tell which grid measured them (R-CY4).

## 4. The ladder-log cutover (R-CY5), simulated on a store copy

Seed: real_store_copy (27257 rows). Tonight's post-era batch: 238 candidate rows. Ingested twice — once with the seam guard live, once with it disabled — so the guard's own contribution is measured, not asserted:

* **5 phantom rows prevented** — same asset, same standing state, `signal_date` moved with the grid. Without the guard each would have rendered as a second 'Signal: X' card days after the first, forever, and dedup on `(asset, signal_date, state)` cannot suppress it.
* 6 appended (genuine state re-draws + the fresh transitions any nightly build appends under any era),
* 227 already-present exact keys (skipped pre-era too).

The real store was read from a copy and never written.

## 5. Start-invariance under the NEW anchor (must be 0)

0 / 238 deep US names move ANY of (state, signal_date, tier, aligned, score) on a 1-3 leading-bar drop.

## 6. Repaired in the same era, evidenced by the battery rather than here

Two surfaces ride this era but are not re-measured across the loaders above, because neither reaches an admission gate or an accruing ledger — synthetic start-invariance is the proportionate evidence, and `tests/test_cycles_anchor_invariance.py` carries it:

* `leader_lifecycle.tf_state_2d` (2B → absolute) — the leader-radar oscillator chip, rebuilt nightly with no marker key. The sibling triage measured it at 93/99 deep US names flipping on one dropped leading bar (mod-2 fingerprint); it now reads the same absolute grid as everything else.
* `commodity_mtf._long_timeframes`' 2W chip (R-CY8) — W-FRI weeks are calendar-absolute but their PAIRING into fortnights phased to the series start, the same defect the R6 ruling repaired for the cascade's HTF badges.

Universes measured in this checkout; an absent universe is announced with a `::warning`, never silently skipped (the A5 precedent).
