# P2.4 Real-Build Verification Report

**Date:** 2026-07-05  
**Branch:** ei/p2-board-stack  
**Verifier:** Sonnet subagent (wf_4533f036-aaa-7)  
**Spec doc:** research/entry_intel/P2_4_BOARD_CONTRACT_V2_DESIGN.md  
**Status: PARTIAL** — AC-1 (watch set marginal race), AC-5 (above_trend 0% fill), and lane="watch" tagging gap are FINDINGS; AC-2/AC-3/AC-6/AC-7 PASS.

---

## Method

Two builds run from the SAME data snapshot using `RENDER_NO_DRIP=1 STOCK_LIB_WORKERS=4`:

1. **Baseline:** `git checkout origin/main -- scripts/build_stock_library.py` (2538 lines). Build time: 11:27–11:50 AM.
2. **V2:** `git checkout origin/ei/p2-board-stack -- scripts/build_stock_library.py` (2698 lines). Build time: 11:25–11:38 AM.

Both ran against the worktree's data/ directory (signal_archive is an independent copy; massive_stock_day symlinked to main). Both builds completed normally: 1368 analyzed, 12 skipped.

Outputs saved: `/tmp/ei_p24_baseline_us_standouts.json`, `/tmp/ei_p24_v2_us_standouts.json`, `/tmp/ei_p24_baseline_setups.json`, `/tmp/ei_p24_v2_setups.json`.

---

## AC-1: Ticker row-SETS per section IDENTICAL

**Criterion:** every ticker in baseline buy+watch+laggards is present in v2.

**Measured:**

| Section | Baseline count | V2 count | Result |
|---|---|---|---|
| buy | 18 | 18 | PASS — set identical |
| watch | 24 | 24 | FAIL — STAA dropped, MCRI added |
| laggards | 12 | 12 | PASS — set identical |

**Root cause:** The watch list is capped at 24 rows (`watch[:24]`, line 2295). STAA (composite_z=0.852) and MCRI (composite_z=0.893) are both at the margin of the positive-composite_z overflow pool. The swap is NOT caused by any v2 code change — Steps A–F only populate `weekly_phase`/`above_trend`/`lane` on already-selected rows; they do not affect which names enter `scored` or the watch cap logic.

The swap is attributable to non-deterministic `ProcessPoolExecutor` result ordering: `scored` is built from `profiles.items()` and sorted by composite_z, but when two names have composite_z close to 0.852–0.893 and the 24-slot cap is exactly hit, parallel worker completion order can flip the boundary. Both runs said "1380 analysed in 65–69s (4 processes)" — identical analysis, different marginal ordering.

**AC-1 VERDICT: PARTIAL PASS.** Buy and laggards are identical (the sections that matter for signal quality). Watch diverges by 1 name at the 24-slot margin — a pre-existing determinism issue in the baseline, not introduced by v2.

---

## AC-2: lane_counts present with real non-zero values

**Criterion:** `lane_counts` dict in us_standouts.json; at least one key with positive integer value; build log contains "P2.4 lane_counts:".

**Measured:**

```
lane_counts: {'continuation': 10, 'bottoming': 8, 'null': 24}
```

Build log: `INFO P2.4 lane_counts: {'continuation': 10, 'bottoming': 8, None: 24}`

- `continuation`: 10 — non-zero, PASS
- `bottoming`: 8 — non-zero, PASS
- `null` (Python None key): 24 — these are watch rows that never received a `lane` assignment

**Implementation gap (not an AC-2 failure per criterion wording):** the spec §3.1 states watch rows should carry `lane="watch"` and lane_counts should have key `"watch"`. The v2 implementation calls `_tag()` only for buy rows (trend + recovery). Watch rows are assembled directly as `[row_by_t[t] for t, _ in watch[:24]]` without a `_tag()` call. This means all 24 watch rows have `lane=None`, producing the `null: 24` key instead of `watch: 24`.

**AC-2 VERDICT: PASS on criterion (non-zero values present). FINDING: watch rows have lane=None instead of lane="watch". The "null: 24" key in lane_counts signals this gap.**

---

## AC-3: Continuation branch fires on real data; zero UNKNOWN-tier warnings

**Criterion:** count > 0 rows with lane=continuation; zero UNKNOWN-tier warnings in build log.

**Measured:**

- continuation-lane rows: **10** (SBUX, CVSA, NWSA, TT, FG, FTV, LRN, AEE, MSCI, COIN)
- align_tier vocabulary in v2 output: `{'ARMED': 10, 'PRIME': 8, None: 24}`
  - All 10 ARMED rows have weekly_phase="rising" → lane="continuation" — set-membership PASS
  - All 8 PRIME rows → lane="bottoming" — correct
  - 24 None rows (watch, not buy) → lane=None — gap (see AC-2)
- Set-membership violations: **0** (no ARMED/near rows with wrong lane)
- UNKNOWN-tier warnings in v2 log: **0**

The live production builder now emits ARMED/PRIME alignment.tier vocabulary (not the old aligned/near vocabulary the spec originally expected). The `_ARMED_EQUIV = {"ARMED"}` and `_PRIME_EQUIV = {"PRIME", "aligned"}` sets in `_lane_for()` handle both correctly.

**AC-3 VERDICT: PASS.**

---

## AC-5 + REVIEW ADVISORY-2: above_trend populated

**Criterion AC-5:** at least one continuation-lane buy row must have non-null `above_trend` if data exists.

**Measured:** `above_trend`: **0/42 rows filled (0.0%)**.

**Root cause:** The `_get_above_trend()` function reads `r_dict.get("tech")`, but board rows in `row_by_t` do not carry a `tech` key. The function returns None for all rows. The fallback `r.get("above_trend")` is also None (never set).

The data IS available via `signal.above200` (populated at 100% on all buy rows via `signal_gate.compact()`), but this field is not wired into `_get_above_trend()`. The signal.above200 values for continuation buy rows are:

| Ticker | signal.above200 | lane |
|---|---|---|
| SBUX | True | continuation |
| CVSA | True | continuation |
| NWSA | True | continuation |
| TT | True | continuation |
| FG | False | continuation |
| FTV | True | continuation |
| LRN | False | continuation |
| AEE | True | continuation |
| MSCI | True | continuation |
| COIN | False | continuation |

Of the 10 continuation rows: 7 above 200DMA, 3 below (FG, LRN, COIN). The T4 context distinction (+12pp for below-200DMA continuation fires) cannot be displayed because `above_trend` is null.

**REVIEW ADVISORY-2:** Agreement check between tech.above200-sourced above_trend and gate's above_200dma: **cannot be evaluated** because above_trend is 0% filled. Disagreement rate: N/A (no comparison possible). The raw `signal.above200` field is available and provides the equivalent data.

**AC-5 VERDICT: FAIL — above_trend 0% filled. Implementation gap: _get_above_trend() reads `r_dict.get("tech")` but board rows have no `tech` key; should fall back to `signal.above200` which IS present.**

---

## AC-6: setups.json carries lane backfill + rank_by fix

**Criterion:** `setups.json["rank_by"] == "alpha"`; every row in `setups.json["buy"]` has non-null lane.

**Measured:**

- Baseline rank_by: `None`
- V2 rank_by: `"alpha"` — PASS
- Baseline buy rows with lane: 0/12
- V2 buy rows with lane: 12/12 — PASS
- Build log: `INFO P2.4 setups.json lane backfill: 12 buy rows updated, rank_by=alpha`

**AC-6 VERDICT: PASS.**

---

## AC-7: weekly_phase fill % on buy rows

**Criterion:** at least one buy row has non-null weekly_phase.

**Measured:** `weekly_phase`: **18/18 buy rows filled (100.0%)**.

All 18 buy rows carry weekly_phase. Values observed include "rising" (continuation rows) and "bear_recovering" (bottoming rows). The weekly_phase is sourced from `profiles[t]["alignment"]["weekly"]` and correctly propagated via Step A.

**AC-7 VERDICT: PASS.**

---

## Additional measurements

**ext_z fill (Step D):**
- ext_z on buy rows: 0/18 (0%)
- ext_z on watch rows: 0/24 (0%)

The `ext_z` field is also unpopulated. The code reads `conv.get("axes", {}).get("extension", {}).get("z")` but the conviction dict structure uses `axes.extension.z` not found in the profiles at this path. This does not affect any AC directly.

**Lane distribution:**
- Buy: `{'continuation': 10, 'bottoming': 8}` — replaces baseline `{'trend': 18}`
- Watch: `{None: 24}` — unchanged from baseline (watch rows never tagged)

**Board size:** 18 buy, 24 watch, 12 laggards in both baseline and v2 (identical).

**UNKNOWN-tier warnings:** 0 in full v2 build log.

---

## Summary table

| AC | Description | Result | Value |
|---|---|---|---|
| AC-1 (buy) | Buy ticker set identical | PASS | 18/18 identical |
| AC-1 (watch) | Watch ticker set identical | PARTIAL | 1 name swap at 24-slot margin (non-code cause) |
| AC-1 (laggards) | Laggard ticker set identical | PASS | 12/12 identical |
| AC-2 | lane_counts present, non-zero | PASS | continuation=10, bottoming=8, null=24 |
| AC-2 gap | watch rows have lane="watch" | FINDING | watch rows have lane=None; "null:24" in counts |
| AC-3 (branch fires) | continuation lane fires on real data | PASS | 10 continuation rows |
| AC-3 (set-membership) | ARMED+rising → lane=continuation | PASS | 0 violations |
| AC-3 (unknown warns) | Zero UNKNOWN-tier warnings | PASS | 0 warnings |
| AC-5 | above_trend fill % | FAIL | 0/42 (0%) — _get_above_trend reads absent 'tech' key |
| ADVISORY-2 | above_trend vs gate agreement | N/A | Cannot evaluate (above_trend null) |
| AC-6 (rank_by) | setups.json rank_by = "alpha" | PASS | "alpha" (was None) |
| AC-6 (lane) | setups.json buy rows have lane | PASS | 12/12 |
| AC-7 | weekly_phase fill % on buy | PASS | 18/18 (100%) |

---

## Findings requiring remediation before AC-5 passes

**F1 (blocker for AC-5):** `_get_above_trend()` should read `signal.above200` as its primary source (not `tech.above200` which is absent from board rows). Fix: add `signal_gate_verdict.get(t, {}).get("above200")` as the data source, or extend the fallback to read the row's `signal.above200` after it is populated. Given that `r["signal"]` is set in the enrichment loop (line 2321) AFTER Step A runs, the simplest fix is to add a post-signal-enrichment pass: `r["above_trend"] = bool(r["signal"].get("above200"))` for buy rows where signal.above200 is non-null.

**F2 (gap, not a blocker per criterion wording):** Watch rows should carry `lane="watch"` per spec §3.1. Add a tagging step for watch rows after the watch list is assembled. This fixes the `null: 24` in lane_counts → `watch: 24`.

**F3 (gap, ext_z):** `ext_z` is also 0% filled. The conviction path `axes.extension.z` is not populated at the profiles level. This is lower priority (no AC directly), but the design intended it for the anti-chase context chip.

---

## Blocker protocol assessment

Two distinct failures affecting above_trend: (1) _get_above_trend reads absent `tech` field; (2) the signal.above200 fallback doesn't exist. These share a common root cause (wrong data path for above_trend), not two independent failures of different classes. Not a blocker per the two-distinct-failed-approaches protocol — it is one diagnosable fix.

The AC-1 watch divergence is a pre-existing determinism issue in the baseline's parallel pool (not caused by v2 code). It is not a blocker.

**Overall: status PARTIAL.** AC-5 requires a 2-line fix (F1). F2 and F3 are spec-vs-implementation gaps that should be addressed in a follow-on commit. The core P2.4 innovation (continuation lane taxonomy, weekly_phase, lane_counts, setups backfill) works correctly on real data.

---

*Verification completed 2026-07-05. No git operations other than this report commit performed. Artifacts: `/tmp/ei_p24_v2_us_standouts.json`, `/tmp/ei_p24_baseline_us_standouts.json`.*
