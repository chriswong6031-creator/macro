# L6-P0 — Macro-Transmission Phase-0 Pre-Registration (frozen)

**Registered:** 2026-07-06 (Fable). **Status:** FROZEN — committed before any overlap between macro flags and fire outcomes is computed. This document is the single numeric authority for the study (`research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md` §7 defers to it; where they could diverge, this prereg wins).
**Question:** at the sector/pooled grain, does a hostile macro condition at fire date separate forward outcomes of existing signal fires — strongly and stably enough OOS to beat the noisy-sector precedent (`sector_rate_inflation` / canon shadow, demoted for split-sample forward-IC instability)?
**This is a gate-clearing study for docket entry L6.** It charters nothing. P0-PASS re-opens the L6 charter question (subject to the two-lobe cap); P0-FAIL/P0-DEFER prints and L6 stays gated.

## 1. Fire tape

- Primary: `data/neuralweb/spine_index.parquet` via `engine/neuralweb/query.py`; rows with `ledger='track_record'`, `horizon=21`, `outcome_graded == True`. (Secondary horizons 5 and 63 computed and printed; budget-counted per RUL-C11.)
- Sensitivity (Mac-only, absent from git checkouts by design): `data/replay/replay_boarded.parquet` modern cohort. If absent, the report prints "sensitivity tape absent on this host" — not an error.
- Survivorship: the track_record archive's old eras are survivorship-exposed. All cells are **within-cohort hostile-vs-benign deltas** (both arms share the bias); outputs stamp `survivorship_biased=True` via `engine/vintage_stamp.py` and a modern-cohort (fires ≥ 2015-01-01) sensitivity is printed for every verdict cell.
- Sector map: current-date symbol→sector from the stock library/factor panel map. Declared anachronism limitation (map applied to historical fires; sectors are slow-moving). Sector cells are descriptive-only — no verdict at sector grain in P0.

## 2. Axes (four; separate; never fused — Signal Commons R3)

All axis series are read with the frozen publication lag below. σ and percentiles use a trailing 756-business-day window ending at the (lagged) read date — strictly backward-looking. A fire date is HOSTILE on an axis iff the axis condition holds at the fire date; BENIGN otherwise (within the axis's coverage window). No composite across axes is computed anywhere.

| Axis | Series (column) | Lag | Hostile condition (frozen) |
|---|---|---|---|
| A1 rates_shock | `data/fred/DGS10.parquet` (`us10y`) | 0 BD (market yield, same-day close; fires are computed after close) | 20-BD change ≥ +1.5σ of trailing-756BD 20-BD changes AND ≥ +25 bp |
| A2 usd_shock | `data/fred/DTWEXBGS.parquet` if present, else DX-Y.NYB close store (builder verifies and prints which) | 1 BD if FRED variant, else 0 BD | 20-BD return ≥ +1.5σ AND ≥ +2.0% |
| A3 credit_shock | `data/fred/BAMLH0A0HYM2.parquet` (HY OAS) | 1 BD | 20-BD change ≥ +1.5σ AND ≥ +50 bp |
| A4 fin_conditions | `data/fred/ANFCI.parquet` (weekly) | 7 calendar days | level ≥ 80th percentile of trailing 756-BD window |

Per-axis coverage windows differ (HY OAS 1996→, broad dollar 2006→, ANFCI 1973→, us10y 1962→). Achieved coverage, fire counts, and episode counts are computed and **printed before any outcome statistic** (long-hold-harness law). If a named series is absent from the repo, that axis is P0-DEFER (data), printed, not silently swapped.

## 3. Episodes and inference

- **Episode** = maximal run of consecutive hostile business days on an axis, padded ±5 BD; overlapping padded runs merge. The episode — never the fire — is the clustering unit (all fires inside one macro window are one draw).
- **Endpoint (primary):** hit rate = share of fires with `outcome_excess > 0` at h21. Delta = hostile − benign. (Adverse-tail columns available in the tape are printed descriptively.)
- **Drawdown stratification (confound control):** market drawdown at fire date = S&P 500 close vs trailing 252-BD high, strata: [0,−5%), [−5,−10%), [−10,−20%), ≤−20%. The verdict delta is the stratified delta: Σ w_s·delta_s with w_s ∝ harmonic mean of arm counts in stratum s; per-stratum deltas printed. Stratification, not residualization.
- **CI:** circular block bootstrap on calendar time, block length 63 BD, 2,000 draws, 95% CI on the stratified delta (btc_override_ledger precedent).
- **OOS halves:** per axis, the coverage window splits at its midpoint calendar date (deterministic; computed and printed). Verdict requires the stratified delta to be sign-stable AND its bootstrap CI to exclude 0 in BOTH halves.
- **Floors (per axis per half):** ≥ 300 graded fires per arm AND ≥ 8 hostile episodes. Any failure → P0-DEFER for that axis (printed with achieved counts and a come-back condition).

## 4. Multiplicity and registration

- `fdr_family='macro_tx'` — NEW flat pooled family for all present/future macro-conditioning studies; sub-scoping prohibited (RUL-C11). `TrialLedger.log_declared_budget(12, family='macro_tx')` BEFORE the run (4 axes × 3 horizons; h21 = the 4 verdict cells; h5/h63 descriptive but budget-counted).
- BH q=0.10 across the 4 primary h21 stratified deltas. PASS per axis = survives BH AND both-halves gates AND floors.
- Every summary prints the cumulative pooled `macro_tx` trial count. `derived_from_surface: null` (first registered macro-axis question). This report is itself a contamination surface: any later prereg on this tape carries `derived_from_surface: macro_tx_phase0_v1`.
- Experiments-registry row: id `macro-tx-phase0` (admin visibility; verdict/come-back dates).

## 5. Pre-committed branches

- **P0-PASS(axes):** listed axes re-open the L6 charter question at the docket. NOT an automatic charter; the two-lobe cap and a separate masterplan+prereg still apply. No live flag, chip, world_state key, kernel cell, or per-name output ships from this study regardless of outcome.
- **P0-FAIL:** nulls printed per cell; L6 stays gated; the noisy-sector precedent stands as the honest ceiling.
- **P0-DEFER(axis):** floors or data unmet; achieved counts + remediation + come-back printed.

Output: `research/macro_tx/L6_PHASE0_REPORT.md` (plain language, "In plain English" box, all 12 cells printed including nulls; the word "validated" may not appear — discipline, research/*.md is not CI-scanned) + committed summary JSON with the 8-field vintage stamp. Opus stats review required before the report merges; Fable adjudicates the verdict.
