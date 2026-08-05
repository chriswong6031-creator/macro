# `basket_turn.v1` — forward ledger, and its two dark windows

`ledger.jsonl` — one row per basket per session in WATCH / IGNITION / DOWNGRADE.
Producer: `engine/basket_turn_watch.py`, stamped from `scripts/build_baskets.py`
on the nightly engine lane. Governance: `research/FAST_TURN_TWO_SPEED_TAPE_MASTERPLAN_BY_FABLE.md`
(FT-R9 — expected-NULL forward meter, display tier, grading unit is the
catalyst-day cohort, never the per-basket row).

## The law on this page

**Emptiness produced by a dark instrument is not evidence.** Two separate input
repairs landed on 2026-08-05, each with its own dark window below. For every
grading run, promotion argument, backtest, or "this confirms the prior null"
reading:

- **n counts from the fix date of the leg family the claim depends on**, not
  from ship. A claim resting on `rs_z` / `complex_confirm` / `shock_relative_bid`
  counts from the benchmark fix; a claim resting on any basket's member tape
  counts from the member-ladder fix.
- **Any run that spans a window must print it.** Silence about a dark window is
  the defect, not the window.
- The **pre-registered fire condition and every leg threshold are unchanged** by
  both repairs (FT-R9 / PS-R9 freeze holds). Only which series the legs could
  read moved. This is what makes these era breaks and not amendments.

## Era break 1 — benchmark dark (#4579)

| | |
|---|---|
| **Window** | 2026-07-09 (ship) → 2026-08-05 |
| **Defect** | `_load_prices` resolved every ticker out of `data/stocks/`. SPY is a member of no basket, so the member collector never writes `data/stocks/SPY.parquet` — SPY lands only in `data/yahoo/`. `spy_ret` was therefore `None` on every run since ship. |
| **Consequence** | `rs_z` returned `(False, None)` unconditionally; `complex_confirm` and `shock_relative_bid` could not fire either. The organ scored **3 of its 6 legs**, and IGNITION — gated on `k >= 3 AND rs_z` — was **arithmetically unreachable on every session**. |
| **Fix** | Benchmark-scoped store ladder `_STORE_LADDER = {"SPY": ("stocks", "yahoo")}`. |
| **Not citable** | Zero IGNITION cohorts exist for the window. That zero is an instrument artifact. It is **not** evidence for the registered expected-NULL and no grading run may read it as one. |

Also disclosed as the FT-R9 amendment in the FTR masterplan §Rules.

## Era break 2 — member coverage dark (this PR, W-B)

| | |
|---|---|
| **Window** | 2026-07-09 (ship) → 2026-08-05 |
| **Defect** | Members resolved out of `data/stocks/` alone (~235 names) while the 47 US baskets' active membership is **1,009 slots / ~683 distinct names**. A member the store did not have was **silently dropped** from `closes_map` — no error, no log line, no artifact field. |
| **Measured** | **399 of 1,009 member slots read (39.5%). 37 of 47 baskets below 60% coverage. Only 2 of 47 baskets fully read.** During the exact week both baskets ignited: `gold_miners` read **1/12** members (NEM alone), `space_economy` **0/15** — its EW 1d return was not merely wrong, it was `null`, uncomputable. |
| **Why it was a scoring defect, not just missing telemetry** | `_leg_impulse_day` takes its threshold from the **active** membership (`max(1/3 x N, 2)`) while it can only count the **readable** members. An unreadable member raises the bar and lowers the count at once. At 1/12, gold_miners could not fire `impulse_day` on any tape whatsoever. |
| **Fix** | Member ladder `_DEFAULT_STORES = ("stocks", "baskets/ohlcv")` — `data/stocks/` keeps first refusal (deeper adjusted series), `data/baskets/ohlcv/` is the fallback rung. Precedent: `scripts/audit_universe.MembershipResolver(data_dir, ["stocks", "baskets/ohlcv"])`. |
| **After** | **1,007 of 1,009 slots read. 45 of 47 baskets fully read. 0 baskets below 60%.** `gold_miners` 12/12, `space_economy` 15/15. |
| **Not citable** | Any WATCH / non-WATCH verdict in the window was scored on a fraction of its basket. The absence of a state is not evidence the state did not exist. |

### What changed on the tape the night the ladder landed

Re-running the organ over the same real store, pre-fix ladder vs shipped ladder
(2026-08-05, `data_session` 2026-07-31 — **identical under both**, the ladder
does not move the stamp):

- **2 baskets changed K, both by one leg, both `volume_confirm`:** `ai_software`
  K 1 → 0, `crypto` K 0 → 1.
- **0 baskets changed state.** `mag7` holds IGNITION, `data_center_power` holds
  WATCH.
- Reads that were previously impossible now exist: `space_economy`
  `ew_1d_ret` `null` → `+0.00718`, `rs_z` `null` → `0.611`; `gold_miners`
  `ew_1d_ret` −0.02141 → −0.03246 (one member's move had been standing in for
  twelve), `rs_z` −1.332 → −1.782.

Those deltas ARE the era break in action — the same session, honestly read.

## Coverage is disclosed from here on

Every artifact row in `site/basketdata/turn_watch.json` carries `members_read`
and `members_total`, and a basket read below `COVERAGE_WARN_FRACTION` (0.6) of
its active membership raises `::warning title=basket-turn-coverage::` in the
nightly Actions summary. A basket scored on a fraction of its members can no
longer print indistinguishably from a fully-read one.

Coverage is **not a leg, not a gate, and not in K** — a thin basket is still
scored and still stamped, exactly as before. It is only no longer scored
silently.

**Known residual: `MMC` (Marsh & McLennan)** resolves in neither store, so
`insurance` reads 18/19 and `us_sector_financials` 75/76. Both are far above the
warn threshold; the gap is a collector question, not a ladder one.

## Integrity rules

| Rule | Mechanism |
|---|---|
| Nightly is the sole advancer | `ledger_lane.nightly_advance_enabled()` (`COLLECT_LANE=nightly`, `US_LANE` legacy alias) is the first statement of `stamp_ledger` — an intraday or render lane returns 0 without opening the file |
| Session stamp comes from the DATA plane | `data_session` = newest bar the member legs actually read, never the wall clock (#4568 pattern). A run against a frozen store re-derives the session it already logged and dedupes |
| Idempotent | keep-first per `(date, basket_id)` |
| Member tape only in the stamp | SPY is collected on a different cadence; folding the benchmark into the `max()` would stamp a session the legs never read |
| No backfilled gradeable claims | forward ledger starts at ship date; the backscan block in the site artifact is descriptive only (FT-R9) — and it reports only the 3 legs it evaluates, never a fake 0.0% for the 3 it does not |
