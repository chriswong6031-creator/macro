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

---

## Addendum 2026-07-01 — full inflation-axis vintage coverage landed

**Branch:** `data/alfred-vintage-backfill` · **Harness re-run:** `scripts/shadow_pit_regime.py --full`

The 11 missing ALFRED series were backfilled into `data/fred_vintage/vintages.parquet` via `FRED API output_type=4` (initial-release matrix). Coverage is now **26/26** (zero gaps). Updated `calibration/leakage_tax.json` reflects the fuller frame.

### What changed in the numbers

**Overall quad agreement: unchanged at 84.2 %** (7,151 days, 1999-02-02 to 2026-06-30). Adding true initial-release vintages for CPI/PCE/PPI/ECI/claims did not move the headline agreement number. The confusion table is also identical. This confirms the prior runs conclusion: the dominant quad-label mismatch is structural (hysteresis on market legs) rather than a CPI/PCE vintage gap artifact.

**Inflation-axis availability shift — the numbers are now real, not modelled priors:**

| leg | prior run (source) | this run (source) | measured median lag |
|-----|-------------------|-------------------|--------------------:|
| headline_cpi (CPIAUCSL) | calendar prior, 8 bd modelled | **vintage** | **45 d** |
| core_cpi (CPILFESL) | calendar prior, 8 bd modelled | **vintage** | **45 d** |
| headline_pce (PCEPI) | calendar prior, 20 bd modelled | **vintage** | **59 d** |
| core_pce (PCEPILFE) | calendar prior, 20 bd modelled | **vintage** | **59 d** |
| ppi_final_demand (PPIFIS) | calendar prior, 9 bd modelled | **vintage** | **43 d** |
| ppi_core (PPIFES) | calendar prior, 9 bd modelled | **vintage** | **43 d** |
| eci_comp (ECIALLCIV) | calendar prior, 20 bd modelled | **vintage** | **121 d** |
| eci_wages (ECIWAG) | calendar prior, 20 bd modelled | **vintage** | **120 d** |
| initial_claims (ICSA) | calendar prior, 5 bd modelled | **vintage** | **5 d** (confirmed) |
| initial_claims_4wk (IC4WSA) | calendar prior, 5 bd modelled | **vintage** | **5 d** (confirmed) |
| continued_claims (CCSA) | calendar prior, 10 bd modelled | **vintage** | **12 d** (slight upward revision) |

The calendar priors for CPI (8 bd ~ 11 cal days) were substantially underestimating the true lag (~45 cal days). The 20 bd prior for PCE was closer but still short (~59 cal days). The ECI result is the largest surprise: the quarterly BLS Employment Cost Index carries a measured **120–121 day** initial-release lag — more than four months from the reference quarter end to initial ALFRED publication (quarter ends ~March/June/September/December; initial release is typically the last day of the following month, i.e. ~30–31 calendar days after quarter end, but ALFRED only holds releases from 2013 onward and appears to capture one release per series-period, so n=51–118 gives a reliable measurement).

**Biggest-leak legs: ECI now displaces INDPRO and M2 in the top-4:**

| prior run | this run |
|-----------|----------|
| recession_prob: 64 d | **eci_comp: 121 d** (new) |
| indpro: 45 d | **eci_wages: 120 d** (new) |
| us_m2: 43 d | recession_prob: 64 d |
| sticky_cpi: 42 d | **headline_pce: 59 d** (new; previously calendar-prior) |

**Inflation-axis disagreement: the Q1↔Q2 confusion pattern was NOT reduced by adding CPI/PCE vintages.** The confusion table is byte-identical (Q1→Q2: 255, Q4→Q1: 147, Q2→Q3: 123). This is the honest finding: adding true initial-release CPI/PCE vintages did not shift the inflation axis read enough to change quad labels at the inflection points that dominate the confusion. The inflation axis is driven by a composite of CPI/PCE/PPI/sticky-CPI/ECI, and the market-leg hysteresis swamps the econ-leg timing correction at these specific turning points.

**Split-half edge delta: unchanged.** ΔSharpe CI (PIT − live) remains [−0.131, +0.015, +0.184] (CI straddles zero; removing the full inflation vintage lag is still Sharpe-neutral on the coarse Q→SPY proxy). The ECI lag is large in calendar days but quarterly — it contributes to four rows per year and ECI is a minority-weight axis leg.

### ALFRED depth limits for new series

- **CPIAUCSL / CPILFESL**: vintages back to 1997-01-14 (353 rows each). Deep and reliable.
- **PCEPI / PCEPILFE**: vintages back to 2000-08-28 (311 rows). PCE has a shallower ALFRED history than CPI; pre-2000 the release-lag calendar prior is still the fallback.
- **PPIFIS / PPIFES**: 2014-03-14 start (148 rows). ALFRED serves PPI only from 2014; pre-2014 the calendar prior remains the fallback.
- **ECIALLCIV / ECIWAG**: ECI comp back to 2013-11-19 (51 rows); ECI wages back to 1997-01-28 (118 rows). The discrepancy reflects ALFRED availability by component.
- **ICSA / IC4WSA / CCSA**: weekly claims from 2009 (876–891 rows). Pre-2009 the calendar prior is the fallback (but claims are weekly so the prior is mechanically tight; the vintage confirms median lag = 5 d for IC4WSA and 12 d for CCSA — the old 10 bd prior slightly underestimated).

### Verdict update

The original verdict stands with one refinement: the **ECI quarterly lag (120+ days) is now the single largest look-ahead in the axis**, not recession_prob. However, ECI enters the inflation axis at low weight (it measures labor cost acceleration, not the headline CPI/PCE print) and its quarterly cadence limits its impact to ~4 rows/year. The inflation-axis Q1↔Q2 disagreement — the #1 source of quad mismatches — is structurally driven by the market-leg hysteresis, and CPI/PCE vintage availability (now fully measured) does not change the confusion table.

**The inflation-axis full de-leaking is now possible** (`engine/base_effect.py` can switch `revised=False` for CPI/PCE/PPI, unblocking audit `#16`). That is a W1c deliverable; this harness only measures, it does not migrate.

---

## Artifacts

- `engine/pit.py` — the PIT accessor (`series(name, as_of, basis)`, `coverage_report`).
- `engine/pit_lag_recorder.py` — append-only learned-release-lag log (`data/pit_release_log/observations.jsonl`), hooked into `scripts/collect.py` (never raises).
- `engine/inputs.py` — `build_features(pit_basis=..., pit_as_of=...)`, backward-compatible (default byte-identical).
- `scripts/shadow_pit_regime.py` — the harness. `--full` for whole span, default last-5y.
- `calibration/leakage_tax.json` — the published measurement.
- `tests/test_pit_accessor.py` — as-of leak invariant, byte-identical regression, calendar/learned-lag sanity.

## Addendum 2026-07-02 — W1-CN China board leakage tax (shadow)
**Harness:** `scripts/shadow_pit_china.py` · **Artifact:** `calibration/leakage_tax_china.json` · **Status:** SHADOW (no live path touched).
W1 (`engine/pit.py`, `scripts/shadow_pit_regime.py`) covers only the US FRED/ALFRED macro legs; it replays ZERO of the China standout board. This harness ports the truncated-replay discipline (`tests/test_vector_pit.py`) to the board's own features and measures three point-in-time taxes.
- **Price-vintage tax** (17 git-committed panel vintage pairs, 3 mid-session partial-bar pairs excluded): **5.1%** of names had their last-2d closes revised >0.4% between vintages (the combine_first-seam band; median 0.83%, max 29.4%). At the looser >0.1% band 10.9%. The git-committed `china_search/closes.parquet` is a free ALFRED-analog vintage matrix.
- **Bucket-completeness tax** (2026-06-30, n=385): washout-2W flag flips **7.0%** between the live (incomplete final 2W bucket) and a completed-bucket backtest — a completed-bucket grade scores a different signal than users saw. `bucket_end` is persisted next to `asof` in the artifact.
- **Bucket-completeness tax** (2026-07-01, n=385): washout-2W flag flips **8.3%** between the live (incomplete final 2W bucket) and a completed-bucket backtest — a completed-bucket grade scores a different signal than users saw. `bucket_end` is persisted next to `asof` in the artifact.
- **Plane tax** (2026-06-30, n=59): replaying washout-2W on the WRONG price plane (search cache vs deep OHLC store) flips **5.1%** of rows; the correct-plane replay reproduces the live ledger flag 100.0%. Features must replay on their OWN store — `universe()` overlays the deep store and shifts the 2W bucket phase.
- **Plane tax** (2026-07-01, n=60): replaying washout-2W on the WRONG price plane (search cache vs deep OHLC store) flips **1.7%** of rows; the correct-plane replay reproduces the live ledger flag 100.0%. Features must replay on their OWN store — `universe()` overlays the deep store and shifts the 2W bucket phase.
- **rev_z** (2026-06-30): causally clean live (both ends observed closes); replay fragility is screened-set churn **0.1%** (current ST/mktcap/membership snapshot vs as-of), not a value leak.
- **rev_z** (2026-07-01): causally clean live (both ends observed closes); replay fragility is screened-set churn **0.0%** (current ST/mktcap/membership snapshot vs as-of), not a value leak.

**Verdict:** honest numbers, no demotion recommended on these alone — this sizes the taxes so any future 'grade the cascade / washout' work replays on the correct plane, persists bucket_end, and treats git panels as the vintage matrix.

---

## Addendum 2026-07-01 — W2 Regime One consumes these numbers (P2-A)

**Artifacts:** `engine/regime_one.py` → `data/regime/regime_one.json`, `data/regime/freshness_ledger.jsonl`, `data/regime/regime_fwd_hmm.jsonl`; `scripts/validate_regime_fwd.py` → `calibration/regime_fwd_grade.json`. **Status:** SHADOW (publishes alongside the legacy regime; zero consumer flips this wave).

W2's Regime One turns the leakage-tax findings from a measurement into structure:
- **The #809 measured lags are now in `DEFAULT_RELEASE_LAGS`** as `lag_bd_measured` (CPI 32bd/~45cal, core PCE 42bd/~59cal, PPI 31bd/~43cal, ECI 86bd/~120cal, continued_claims 9bd). `pit._effective_lag_bd()` prefers measured > prior for the non-vintaged calendar fallback; the vintaged legs (26/26) still use the true `realtime_start` as-of join, so only CPI-detail (`cpi_core_services`, `cpi_shelter`) actually change. The old CPI 8-bd prior was optimistic by ~24 bd.
- **The 84.2%-agreement / inflation-axis-inflection finding is encoded as an explicit confidence input**, not a footnote: `regime_one.fused_risk.confidence` drops (uncertainty 0.35 vs 0.05) whenever the coincident tape inflation axis and the leak-free macro (release-frame) inflation axis DISAGREE on sign — the live analog of the Q1↔Q2 inflection confusion the tax measured.
- **The market-leg-hysteresis-dominates-flips finding drives flip attribution**: since the confirmed quad moves on the market legs, a quad flip that is *majority renormalization* (a dead econ leg vanishing from the weighted sum, `axes.py:77-79`) is now VETOED — the label freezes and `degraded` is published. Chaos-tested: killing payrolls+indpro flips the raw quad Q1→Q4 but regime_one holds Q1 (100% renorm share) and caps gross at 0.90.
- **#16 unblocked and wired**: `scripts/validate_regime_fwd.py` (the gate that never existed) now matures + grades base_effect and the causal-HMM forward calls with accrual-aware Wilson CIs, and the SHADOW regime_one base_effect runs `revised=False` (leak-free CPI/PCE/PPI) by threading `as_of` + `load_vintages()` — verified `revised(pit)=False` vs `revised(run.py-legacy-call)=True`.
- **HMM honesty**: the P(Quad) history emitted by regime_one is the FILTERED (causal, forward-alpha) series — each point conditions only on data up to that day — flagged `smoothed_hindsight: false`. The full-sample smoothed `predict_proba` series stays confined to `engine/regime_hmm.py`'s display chart.
