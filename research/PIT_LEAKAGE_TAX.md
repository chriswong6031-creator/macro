# PIT Leakage Tax — first measured numbers

**Date:** 2026-07-01 · **Workstream:** W1 Truth Layer (masterplan §W1a/b) · **Attacks:** audit `#5` (reference-vs-release timing leak), `#14` (revision-magnitude leak), `#16` (unvalidated forward suite / PIT bypass), `#39` (recession/cycle signals on revised finals).

**Status:** SHADOW. Nothing here changes a live signal path, a live artifact, or the render critical path. This is a measurement product: `calibration/leakage_tax.json`, produced by `scripts/shadow_pit_regime.py`, recomputes the growth/inflation axes and quad history on a leak-free point-in-time frame and diffs it against the live frame.

---

## What was leaking

The live feature frame (`engine/inputs.py:put()`) stamps every FRED series on its **reference** index — the month/week the data *describes* — and forward-fills. For monthly econ prints that publish weeks later, this bakes two distinct look-aheads into every historical row of the growth/inflation axes:

1. **Timing leak (#5):** the axis "knows" a payrolls or industrial-production print on the 1st of the reference month, when it was not published until ~5 business days (payrolls) to ~3 weeks (INDPRO) into the *following* month.
2. **Revision leak (#14):** the axis reads the *latest-revised* value, not the number that was on the screen at the time. Post-2008 payrolls were revised hundreds of thousands lower years later; the live axis backtest "saw" the corrected trend early.

The fix data — an ALFRED initial-release vintage matrix — was already collected (`data/fred_vintage/vintages.parquet`) and **entirely unused by the daily-axis path**. W1 wires it into a shadow accessor (`engine/pit.py`) and measures the tax.

## How the tax is measured

`engine/inputs.build_features(pit_basis='release')` routes the revision-prone econ columns through `engine.pit.series(...)` instead of the reference-stamped store, on the **same axis math** (no fork — `pit_basis=None` is byte-identical to the live call, regression-tested). The `'release'` frame carries, for each historical business day *d*, only what was available on *d*:
- **vintaged legs** (PAYEMS, INDPRO, WEI, GDPNOW, sticky-CPI family, M2, term premium, recession-prob, Sahm, financial-stress, UMich, claims): an as-of join on `realtime_start` — the latest **initial-release** vintage published on or before *d*. A period is never visible before its release date.
- **non-vintaged legs** (core CPI/PCE, PPI, ECI — see gaps below): the reference-stamped value shifted forward to a modelled release date via a documented static-prior calendar (`engine.pit.DEFAULT_RELEASE_LAGS`), with first-party learned lags accruing from the next collect run onward (`engine.pit_lag_recorder`).

The harness diffs `'release'` vs `'latest'` on four axes.

---

## The numbers

Two spans reported. **5-year** is the cheap default; **full** covers the whole PIT-covered history (from the first ALFRED release, ~1999 for the quad once all legs are live).

### 1. Per-leg availability shift — how much look-ahead PIT removes

The true per-row look-ahead the live axis carried (`realtime_start − period`, days):

| leg | median release lag | this is the daily look-ahead removed |
|-----|-------------------:|--------------------------------------|
| recession_prob (NY Fed) | **64 d** | ~6-week publication lag on a monthly series |
| industrial production (INDPRO) | **45 d** | published ~day 15-17 of the *following* month |
| M2 (money stock) | **43 d** | Fed H.6 ~4th Tuesday of following month |
| sticky CPI (Atlanta Fed) | **42 d** | released with the BLS CPI it is built from |
| payrolls (PAYEMS) | **34 d** | ~first Friday of following month |
| GDPNow | ~29 d | (a nowcast — updates intra-month; treated conservatively) |
| WEI | ~5 d | weekly, ~Thursday for the prior week |

**Biggest-leak legs: recession_prob, INDPRO, M2, sticky CPI.** These are the legs whose historical values the live axis "knew" a month-plus early.

### 2. Quad-label agreement (PIT vs latest)

| span | overall agreement |
|------|------------------:|
| last 5y (2021-06 → 2026-06, 1,305 days) | **82.8 %** |
| full (1999-02 → 2026-06, 7,151 days) | **84.2 %** |

So the leak-free quad **disagrees with the live quad ~1 day in 6**. It is not a rounding error, and it is not catastrophic either.

**The disagreement is concentrated at turning points.** Lowest-agreement years (full span): **2001 (57 %)**, **2025 (63 %)**, 2006 (74 %), 2003 (75 %), 2020 COVID (78 %) — recessions and slowdown inflections, exactly where revised/early econ data changes the read. In calm trend years agreement is 90-96 %.

**The leak lives on the inflation axis.** The disagreement confusion table is dominated by Q1↔Q2 flips (255 days, the two growth-accelerating quads that differ only on the inflation sign) and Q2↔Q3 (240 days). That is a direct consequence of the vintage gaps below: the inflation axis's official CPI/PCE legs have **no vintages**, so they fall back to the calendar-shift approximation, while sticky-CPI carries a real 42-day lag. The growth axis (payrolls/INDPRO fully vintaged back to 1997) agrees far more tightly.

### 3. Flip-date drift

Matching each PIT quad flip to the nearest same-quad live flip within 45 days:

| span | matched flips | median drift (pit − live) | pit later | pit earlier |
|------|-------------:|--------------------------:|----------:|------------:|
| 5y | 44 / 49 | **0 d** (p10–p90: −3…+4) | 27 % | 18 % |
| full | 223 / 246 | **0 d** (p10–p90: −7…+2) | 16 % | 24 % |

**Honest read: the *confirmed* quad flips barely move in time — median 0 days.** This is because the hysteresis-confirmed quad is dominated by the daily market legs (copper/gold, breadth, cyclical/defensive, breakevens), which are identical on both frames; the monthly econ legs are a minority of the axis weight and mostly nudge confirmation timing at the margin. Where they do move, the full-span distribution is mildly skewed toward PIT flipping *earlier* (24 % vs 16 %) — i.e. removing the leak did not uniformly delay the calls. What the econ leak changes is **which quad you sit in between flips at inflections** (the agreement gap above), more than **when the confirmed flip fires**.

### 4. Split-half edge delta

A deliberately coarse quad→SPY directional backtest (Q1/Q2 long, Q3/Q4 flat, exposure shifted one bar, 2 bps cost), run on both frames, split-half, with a **paired** circular-block bootstrap of the Sharpe difference (PIT − live):

| span | live Sharpe (full / pre / post) | PIT Sharpe (full / pre / post) | ΔSharpe CI (PIT − live) |
|------|--------------------------------|-------------------------------|-------------------------|
| 5y | 0.56 / 0.14 / 1.20 | 0.52 / 0.15 / 1.03 | **[−0.40, −0.04, +0.34]** |
| full | 0.45 / 0.07 / 0.95 | 0.47 / 0.13 / 0.89 | **[−0.13, +0.02, +0.18]** |

**Honest read: on this coarse edge proxy, the timing/revision leak is NOT worth a statistically significant amount of Sharpe.** Both ΔSharpe CIs straddle zero. The 5-year point estimate is mildly negative (−0.04, PIT slightly worse in the recent risk-on tape); the full-span point estimate is essentially zero (+0.02). Notably, on the full span the PIT frame's *pre-split* Sharpe is **higher** (0.13 vs 0.07) — the leak was not a free lunch even directionally over the long history.

This does **not** mean the leak is harmless — it means a two-state long/flat SPY proxy is too blunt to price it. The leak's real cost is to any signal that (a) reads the *inflation* axis at inflections, or (b) leans on the specific quad label rather than the coarse risk-on/off split. W1c's grading rebuild and W2's flip-attribution are where the finer edge deltas get measured; this harness sizes the coarse one and confirms the direction (removing the leak is roughly Sharpe-neutral, not Sharpe-destroying) so the migration decision is not held hostage to a scary headline number.

---

## Vintage store gaps (flag for the FRED store)

`vintages.parquet` currently holds **15 of the 26** intended vintage series (`collectors.fred.DEFAULT_VINTAGE_SERIES`). **Missing — the whole official-inflation and claims block:**

`CPIAUCSL` (headline CPI), `CPILFESL` (**core CPI**), `PCEPI` (headline PCE), `PCEPILFE` (**core PCE — the Fed's target**), `PPIFIS`, `PPIFES` (PPI), `ECIALLCIV`, `ECIWAG` (ECI wages), `ICSA`, `IC4WSA`, `CCSA` (jobless claims).

Consequences:
- The **inflation axis cannot be fully leak-free yet** — its official CPI/PCE legs fall back to the static release-lag calendar (a modelled shift, not a true initial-release vintage), which is why the Q1↔Q2 disagreement dominates. Sticky-CPI (vintaged from 2014) partially covers it.
- `engine/base_effect.py` already documents this exact gap ("core CPI/PCE are not yet in the store") — its PIT inflation projection silently falls back to `revised=True`. **This is the audit `#16` blocker on the leak-free inflation validation.**
- The vintaged legs also start late: WEI from 2020, GDPNow from 2016, sticky-CPI/median-CPI/flex-CPI from 2014, financial-stress (STLFSI4) from 2022. Pre-coverage, the `'release'` frame simply has no econ read (correct — nothing was knowable), which is why the full-span PIT quad starts ~1999 (payrolls/INDPRO era) and thins earlier.

**Ask of the store:** add the 11 missing series to the next `fetch_vintages()` run (they're already in `DEFAULT_VINTAGE_SERIES`; the parquet was built before they were added or their ALFRED fetch failed under the 100k-row cap — core CPI/PCE initial-release matrices are small and should fit). Once core CPI/PCE vintages land, re-run this harness; the inflation-axis agreement number will move and the base-effect inflation validation (#16) becomes possible.

---

## What this implies for the regime's claimed edge

- The quad's certified edge was validated on a frame with a **34-to-64-day per-leg econ look-ahead** and **latest-revised** values. That contamination is real and present in every historical row.
- But the **confirmed** quad is market-leg-dominated, so the *timing* of the headline flips is largely leak-insensitive (median 0-day drift). The leak's bite is on the **quad label between flips at inflections** (~16 % overall disagreement, up to 43 % in recession years) and specifically on the **inflation axis**, which is not yet fully de-leakable pending the CPI/PCE vintage gap.
- On a coarse risk-on/off SPY proxy, removing the leak costs **no significant Sharpe** (ΔSharpe CI straddles 0 on both spans). The regime's coarse directional edge is not a revision artifact.
- **No engine should be demoted on these numbers alone.** The honest verdict is: the growth-axis timing leak is measurable but the coarse edge survives it; the inflation-axis leak is only *partially* measurable until the vintage store is completed. Passport recommendation: tag the regime `frame: latest` with a `leakage_tax` reference, and re-measure the inflation axis once core CPI/PCE vintages land before any promotion/demotion decision.

## Artifacts

- `engine/pit.py` — the PIT accessor (`series(name, as_of, basis)`, `coverage_report`).
- `engine/pit_lag_recorder.py` — append-only learned-release-lag log (`data/pit_release_log/observations.jsonl`), hooked into `scripts/collect.py` (never raises).
- `engine/inputs.py` — `build_features(pit_basis=..., pit_as_of=...)`, backward-compatible (default byte-identical).
- `scripts/shadow_pit_regime.py` — the harness. `--full` for whole span, default last-5y.
- `calibration/leakage_tax.json` — the published measurement.
- `tests/test_pit_accessor.py` — as-of leak invariant, byte-identical regression, calendar/learned-lag sanity.
