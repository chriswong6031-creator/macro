# Vol-regime data accrual clock

Collect-first data infrastructure for `engine/vol_regime.py`. Two "start the clock" data
gaps were filled as fast-follows to the vol-regime engine. This file is the **canonical
record of which series is backfilled vs forward-accruing**, so a short `vix_curve.parquet`
or a recently-started series is never "rediscovered as broken."

Both collectors are **additive and graceful-degrade**: a moved/blocked endpoint marks the
source stale and drops the corresponding leg — it never raises into the daily build. They
run inside the existing `python -m scripts.collect` step, which `git add data/`s the result
(see `.github/workflows/daily.yml`), so the clock ticks automatically every build.

---

## 1. VVIX (vol-of-vol) — BACKFILLED, validatable now

| | |
|---|---|
| **Collector** | `collectors/cboe_indices.py::CboeVvixAdapter` (registered in `scripts/collect.py` as `cboe_vvix`) |
| **Source** | `https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv` (keyless; the analog of `SKEW_History.csv`) |
| **Store** | `data/cboe/vvix.parquet` (col `vvix`) |
| **History** | **Full — 2006-03-06 → present (~5,000 rows)**. One fetch returns the whole file, so a single run BACKFILLS the entire history and accrues the new day. There is **no separate backfill step** (`full_history` is a no-op for this adapter). |
| **Retires** | `data/yahoo/_VVIX.parquet` (~26 rows; yfinance only began carrying `^VVIX` in 2026). `build_vol_regime`/`validate_vol_regime` prefer `cboe/vvix` and fall back to `yahoo/_VVIX` only until the CBOE series exists. |

**Engine wiring** — `engine/vol_regime.build_frame(..., vvix=...)` adds a **VVIX-VIX leg**
(the `vvix_vix = VVIX/VIX` ratio, plus `vvix_pctile` / `vvix_vix_pctile` and a `vvix_state`).
It is a **CONTEXT / candidate leg** (`vol_regime.CONTEXT_LEGS`), NOT scored-eligible — so it
is surfaced for display and evaluated by the validator, but it **does not enter the gated
3-leg composite** and cannot move money until a deliberate promotion. Adding it leaves the
validated `risk_score` / `scored_score` byte-for-byte unchanged (regression-tested).

**Measured relationship (validator, 2006+, n≈4,900):** a **rich** VVIX/VIX ratio precedes
**lower** forward realized vol (HAC t ≈ −14.5, sign-stable across 4 purged folds,
crisis-robust) — fear already priced into vol-of-vol → mean-reversion (the "peak-fear"
contrarian read); a **cheap** ratio precedes **higher** vol (complacency = the quiet-
fragility tell). So the risk-on form is `+z(VVIX/VIX)` and the candidate **would-pass the
scored bar today**.

> **Why it is still only a candidate (do not auto-promote):** `VVIX/VIX` is partly the
> mechanical `1/VIX`, so much of this predictability is plain **vol persistence** (low VIX
> now → low vol ahead), which the existing `ts_slope` / VRP legs already capture.
> **Promotion requires showing INCREMENTAL forward-vol edge after orthogonalizing against
> the VIX level and the scored legs** — not just the raw t-stat. The candidate evidence is
> recorded in `reports/vol-regime-validation.md` under "Candidate legs" each run.

**To promote** (a deliberate, reviewed step): move `"vvix"` from `CONTEXT_LEGS` to
`SCORED_LEGS` in `engine/vol_regime.py`, add the incremental-edge (orthogonalized) check to
`scripts/validate_vol_regime.py`, re-run the composite validation/DSR, and only then
`--write-gate`.

---

## 2. Full VIX-futures curve (M1..M6) — FORWARD-ACCRUING, validatable ~2027-06

| | |
|---|---|
| **Collector** | `collectors/cboe_vix_futures.py::CboeVixFuturesAdapter` (already registered as `cboe_vix_futures`; now emits a second series) |
| **Source** | `https://www.cboe.com/us/futures/market_statistics/settlement/csv/?dt=YYYY-MM-DD` (keyless; one CSV per date — the `cdn.*` path 403s bots) |
| **Stores** | `data/cboe/vix_futures.parquet` (`front_settle`, `days_to_expiry` — **unchanged**, still powers `engine/dislocation.py`'s thin-quote sanitizer) **and** `data/cboe/vix_curve.parquet` (`m1..m6_settle`, `m1..m6_dte`) |
| **History** | **NO deep backfill.** There is no bulk historical settlement file — each date is one request. The curve is derived from the SAME daily CSVs the front-month already fetches, so it seeds for free to the front-month backfill depth (`vix_backfill_days`, default 45 → seeded **≈ 2026-04-16 → present**), but it **accrues FORWARD only** from there. |
| **Accrual start** | **First production build that includes this change** (the ~45-day seed is from the same CSVs; treat the seed as a head-start, not deep history). |
| **Validatable** | Curve **slope / carry / roll-yield** needs ~12 months of forward overlapping windows → **~2027-06** for a first honest HAC-t / purged-fold pass. Until then, `vix_curve` is **persist-only** (no engine leg). |

**Monthly vs weekly:** the settlement CSV mixes **weekly** VX (week-number-prefixed symbols,
e.g. `VX25/M6`) with the standard **monthly** contracts (bare `VX/{Mon}{Yr}`). `vix_curve`
keeps **only the monthlies**, sorted by expiry, so M1..M6 is a clean ~constant-spacing ladder
(DTEs ≈ 30/60/90/120/150/180). `front_settle` is deliberately left as the nearest non-expired
contract **of any kind** (weekly or monthly) — unchanged, to preserve the validated sanitizer.

**Why no engine leg yet:** this is the futures analog of the `VIX/VIX3M` *spot* term-
structure leg the engine already scores — but on the actual tradeable curve, with a real
roll yield. It is deliberately **collect-first**: the leg is built and validated only once
~12 months of forward curve history exists. When it is, add a `vx_curve` leg to
`build_frame` (e.g. `m1/m2` contango + a carry/roll term) as a CONTEXT/candidate, exactly
like the VVIX leg, and let `scripts/validate_vol_regime.py` decide.

---

## Operational notes (don't re-debug these)

- **`data/cboe/vix_curve.parquet` is SHORT by design** (forward-accruing). A small row count
  is not a broken collector — see the table above.
- **`vix_curve` columns can be ragged** across days (a day listing only 5 monthlies omits
  `m6`); `store.upsert` aligns columns and never drops prior history.
- **VVIX early rows (2006) are sparse/noisy** (raw CBOE history). The engine z-scores over a
  ~2-year causal window, so ancient sparse points don't pollute recent reads; the store's
  8-sigma outlier guard does not run on the first (old=None) backfill, matching the SKEW
  collector — this is intentional, not a missing guard.
- **Off-hours / holidays:** the settlement endpoint returns no data on non-trading days; the
  collector skips them and only raises if it fetched **nothing at all** (endpoint moved).

---

## Repo / merge coordination

This work was built as a fast-follow while the `engine/vol_regime.py` feature itself was
still **uncommitted** (developed on a separate worktree). The two parts split cleanly:

- **Data infrastructure** (the two collectors, `config.yml`, `scripts/collect.py`, the two
  `data/cboe/*.parquet` seeds, this doc, `tests/test_cboe_vol_collectors.py`) is **fully
  independent of the vol-regime engine** — it applies to `main` today and starts both clocks.
- **The VVIX engine leg** edits `engine/vol_regime.py`, `engine/options_desk.py`,
  `scripts/build_vol_regime.py`, `scripts/validate_vol_regime.py`, `tests/test_vol_regime.py`.
  Those files are **vendored copies of the in-flight vol-regime feature + the leg edits**, kept
  so the branch builds and tests end-to-end. The leg delta alone is captured in
  **`research/vvix-engine-leg.patch`** (`git apply -p1`), so at merge you can either take the
  vendored superset files or apply just the patch onto the canonical vol-regime files once that
  feature lands. (`engine/opex.py` is vendored unchanged, only for the build import.)
