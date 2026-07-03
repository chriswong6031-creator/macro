# W0.2 + W0.3 — Tier+Stage-Stratified Grading + Dead Grader Fix

**Wave:** W0 (Repair + Honesty)
**Items:** W0.2 (tier+stage-stratified forward grading), W0.3 (fix dead validation grader)
**Author:** Sonnet executor (2026-07-03)
**Status:** COMPLETE — 37/37 tests pass

---

## W0.3 — Dead Grader Diagnosis and Fix

### Finding

The masterplan (F9, §W0.3) says the "older forward grader is structurally dead (0/120 board tickers resolve)".
Two candidate graders were inspected:

**Candidate 1: `engine/china_standout_track.py`** — ALREADY FIXED in commit `d266f19638`
(2026-07-01, "W6-CN CN-1: grader/ledger truth pass").
- The `_price_frame()` function now reads `("china_stocks", "china")` in order.
- **Empirical proof (post-fix):** 5/5 board tickers sampled from `data/china_standout_track/board.parquet`
  resolve via `china_stocks`: 603129.SS (2150 rows), 300725.SZ (2095 rows), 688235.SS (1101 rows),
  002335.SZ (3997 rows), 688306.SS (1038 rows). 0/5 resolve via `china` alone (the old broken path).
- `n_graded=0` today because the ledger started 2026-06-30 (3 days ago); the 21d horizon matures
  ~2026-07-29. This is honest accrual, NOT a bug.

**Candidate 2: `engine/name_score_grader.py` (per-name POTENTIAL score grader)** — DEAD, FIXED HERE.
- `_FWD_GROUP["CN"]` was `"china"` (single group = ~30 ETF parquets in data/china).
- Per-name A-share board tickers (.SS/.SZ) live in `data/china_stocks/`, not `data/china/`.
- **Empirical proof (pre-fix):** 0/3 exemplar board tickers resolved via `"china"`:
  603129.SS → None, 300725.SZ → None, 688306.SS → None.
  `grade("CN")` reported `n_calls=8859, n_graded=0` (8,859 calls logged over 5 dates, zero graded).
- **Root cause:** same structural cause as the #791 `china_standout_track` bug, propagated to
  `name_score_grader` at the time of its market-aware refactor. Not caught because the shim
  (`china_name_score_grader.py`) re-exports everything, making the bug invisible in the shim layer.

### Fix Applied

`engine/name_score_grader.py`:
- Changed `_FWD_GROUP["CN"]` from `"china"` (str) to `("china_stocks", "china")` (tuple).
- Updated `_fwd_return()` to resolve the group via a loop: `str → (str,)`, `tuple → tuple as-is`.
  First store that returns a non-None frame with a `close` column wins. Fallback to `china` preserved
  for the ~30 ETF tickers that might appear on the board.
- All other markets (`US`, `HK`, `CA`, `INTL`) use the original single-string mapping — no change.

**Empirical proof (post-fix):** 3/3 exemplar board tickers resolve via `china_stocks`:
603129.SS (2150 rows), 300725.SZ (2095 rows), 688306.SS (1038 rows). Resolution path confirmed.

**`grade("CN")` post-fix:** A synthetic test (`test_cn_grade_resolves_nonzero_after_fix`) with 10
calls on 130-session synthetic series confirms `n_21d > 0` once the store-group fix is in place.

### Is the Grader Superseded?

`name_score_grader` grades the **per-name POTENTIAL score** (washout/trigger composite, logged via
`conviction.potential.call`). `china_standout_track` grades the **board-order rank** (the actual
`blend_sorted` order that decides what the user sees at the top). They are DISTINCT graders measuring
DISTINCT hypotheses — the POTENTIAL grader is NOT superseded. It grades S4 (pick-strength tiers)
while `china_standout_track` grades F3 (board ordering). Both must be fixed and both are now alive.

---

## W0.2a — Extend `append_board` + `grade` in `engine/china_standout_track.py`

### Changes to `append_board()`

New fields added per the W0 recipe (P2 schema spec), using the established `pd.concat` schema-union
pattern from the COILED wave-3/4 ship (old parquet rows get NaN for new columns, handled transparently):

| New Field | Source | Semantic |
|---|---|---|
| `ticks` | `sig.get("ticks")` | Native-TF ticks since cross (None for projected T3/T4) |
| `provisional` | `sig.get("provisional")` | T3 incomplete-bucket flag |
| `ext_score` | `ext.get("score") or 0.0` | Extension score 0..1 at fire time |
| `washout_2w` | `r.get("washout_2w")` | Explicit-name alias (alongside legacy "washout") |
| `hold_state` | `(r.get("hold") or {}).get("state")` | W6-C basing state (None until W0.1 HOLD port) |
| `entry_status` | `(r.get("entry_signal") or {}).get("status")` | Confluence-gated entry gate label |

`board_rank` was already logged. `coiled` (bool) was already logged. Per the task spec,
`hold_state` is attached as a placeholder (None until `build_china_library.py` wires the HOLD builder).

### Changes to `grade()`

Added `_slice_table()` helper (mirrors `grade_us_board._slice_table` exactly: same groupby-on-NaN
behavior, same output schema `{n, hit_rate, wilson_lo, wilson_hi, median_excess, mean_excess}`).

Extended the per-row `recs` dict to carry `tier`, `washout_2w`, `coiled`, `hold_state`, `entry_status`.
The `washout_2w` field prefers the new explicit-name column and falls back to legacy `washout` so old
ledger rows (pre-W0.2a) are still stratified.

Each matured by_horizon block now emits:
- `by_tier` — stratified by T1/T2/T3/T4
- `by_washout_2w` — stratified by 2W washout-reclaim flag
- `by_coiled` — stratified by COILED cohort-washout flag
- `by_hold_state` — stratified by W6-C basing state (all "None" until W0.1 HOLD port lands)
- `by_entry_status` — stratified by entry gate label

Per F3 discipline: no bonus recalibration here. The ledger matures ~2026-07-29 (21d horizon).
The stratification blocks will populate at that point and drive the W6 recalibration pass.

---

## W0.2b — Add `tier_cascade` to `scripts/grade_us_board.py`

### Changes

`grade_boards()`: added `"tier_cascade": feat.get("tier_cascade")` to the `rec` dict.
Previously `tier_cascade` was extracted in `_row_features()` (L181) but never emitted into
the graded record — confirmed by the retro_grades.parquet schema (31 columns, no `tier_cascade`).

`build_track()`: added `"by_tier_cascade": _slice_table(buy, "tier_cascade", "excess_spy")` to the
`buy_lane` aggregation block (alongside the existing `by_hold_state`, `by_donor_state` slices).

None on pre-schema boards (earliest revisions lacked the `signal.tier_cascade` field) — these appear
as "None" in the stratification output, which is the honest representation.

---

## Evidence Summary

| Item | Pre-fix | Post-fix |
|---|---|---|
| W0.3: 3 exemplar tickers via `"china"` | 0/3 resolve | — (old path) |
| W0.3: 3 exemplar tickers via `("china_stocks","china")` | — | 3/3 resolve |
| W0.3: `grade("CN")` n_graded | 0 (8,859 calls, 0 graded) | >0 (synthetic test confirms) |
| W0.2a: append_board new fields | not logged | logged (test confirmed) |
| W0.2a: grade() `by_tier` | absent | present when matured |
| W0.2b: `tier_cascade` in graded record | absent from rec dict | present |
| W0.2b: `by_tier_cascade` in build_track | absent | present |
| All tests | — | 37/37 pass |

---

## Files Changed

| File | Change |
|---|---|
| `engine/name_score_grader.py` | W0.3 fix: `_FWD_GROUP["CN"]` → tuple; `_fwd_return` resolution loop |
| `engine/china_standout_track.py` | W0.2a: new fields in `append_board`; `_slice_table` helper; grade stratification |
| `scripts/grade_us_board.py` | W0.2b: `tier_cascade` in `grade_boards` rec; `by_tier_cascade` in `build_track` |
| `tests/test_china_standout_track.py` | 4 new W0.2a tests |
| `tests/test_china_name_score.py` | 3 new W0.3 tests |
| `tests/test_grade_us_board.py` | 3 new W0.2b tests; `_minimal_grade_df` updated with `tier_cascade` |

---

## Deferred Items (Not in W0 Scope)

- **hold_state actual values**: `hold_state` is logged as `None` until W0.1 HOLD builder port wires
  `rec["hold"]` in `build_china_library.py`. The schema placeholder is in place.
- **Sector-state column on board rows**: recipe P2 mentions `sector_state` as a desired log field.
  Not on the board row top-level; would require a join with `engine/china_sector_desk`. Deferred to
  the W1 feeder-fusion pass (F8).
- **MAE close-path (CN)**: US grader has `_close_path_mae`; CN standout track does not. Not required
  for W0 stratification (the benchmark is CSI300-relative excess, not MAE). Deferred to W1.
- **CROSS_MAX_AGE for suspended CN names**: noted in us-port-mechanics.md §CN-specific adaptations.
  Not in W0 scope.
- **O2 resolution**: the masterplan's open item O2 ("which grader is the dead one") is now answered:
  `name_score_grader._fwd_return` for CN (store group "china" → 0/N). The fix is in this wave.
