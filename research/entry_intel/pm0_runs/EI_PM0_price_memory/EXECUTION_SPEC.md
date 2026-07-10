# EI-PM0 Execution Spec — Fable, 2026-07-10

Binding implementation contract for executing `research/entry_intel/PM0_PRICE_MEMORY_BUNDLE_PREREG.md`
(APPROVED 2026-07-06, r3, DT-R14-compliant). This document records the Fable-tier resolutions of every
implementation ambiguity in the prereg, **frozen before any code runs**. Deviation from the prereg = new
recorded trial; deviation from this spec = blocker report to Fable. This spec adds no trials, changes no
thresholds, and touches nothing statistical that the prereg froze — it only pins execution details the
prereg left to the implementer.

## 0. Environment

- **Canonical data root (read):** `/Users/chriswong/Documents/Cluade/Macro Dashboard/data` — env override
  `MAIN_DATA` (TC-recheck convention). All reads absolute; the Massive store is host-only.
- **Worktree (code + committed outputs):** this checkout. Feature artifact writes to
  `<MAIN_DATA>/replay/pm0_features.parquet` (gitignored on canonical checkout, EI R9 — never committed).
- Inputs: `<MAIN_DATA>/replay/replay_boarded.parquet` (canonical ONLY, MD5 logged),
  `<MAIN_DATA>/massive_stock_day/<TICKER>.parquet` (raw OHLCV, index `date` datetime64[ms], first bar
  2021-07-06), `<MAIN_DATA>/edgar/statements_quarterly.parquet` (`ticker/filed/period_end/shares`, str dates).
- Substrate verification (Fable, 2026-07-10, pre-build): 961,656 rows; 57,640 fires; 49,939 verdict-grade
  fires; 22,295 episodes; state counts match prereg §1 exactly (grid-B DEAD_MONEY = 43); vg fires have
  `survivor_bias == False` and `horizon_censored == False` for all rows; `signal_date` dtype **str**,
  observed range 2022-06-30 → 2025-12-29 (the prereg's 2026-07-02 window end is the verdict-horizon end,
  not the last signal date — preamble prints both; TC-recheck DATE_MAX precedent). 992 vg-fire tickers.
  `shares` min/max = −8.9e8 / 5.1e14 (matches red-team B4).

## 1. Deliverables

1. `scripts/ei_pm0_price_memory_features.py` — outcome-blind feature builder + §4.4 QA gates.
   Research-only; never referenced by `daily.yml` or any render path.
2. `research/entry_intel/pm0_runs/EI_PM0_price_memory/run_PM0.py` — staged analysis runner.
3. Run outputs in the same dir: `qa_report.json`, `preamble.json`, `calibration.json`, `results.json`,
   `RESULTS.md` (§9 report contract). Feature parquet NOT committed.

## 2. Feature builder

### 2.1 Population and outcome blindness

- Reads ONLY {`ticker`, `signal_date`, `episode_id`, `survivor_bias`, `verdict_type`, `verdict_grade`,
  `horizon_censored`} from the replay. Loading any state/return/MDD/MFE column in the builder = defect.
- Artifact rows: all `verdict_type == 'fire'` rows (57,640) **plus** `verdict_type == 'near_miss'` &
  `verdict_grade == True` rows (15,053, required by prereg §8 near-miss context read; carried with
  `verdict_type` so the runner filters per §1). **Fable ruling EX-1:** the §4.4 artifact-spec sentence
  ("one row per (ticker, signal_date) of the fire population") and §8 (features on verdict-grade
  near-misses) are jointly satisfied by a single artifact carrying both row classes, distinguished by the
  `verdict_type` column; verdict statistics use fires per prereg §1 only.
- Artifact columns: `ticker`, `signal_date`, `episode_id`, `verdict_type`, `verdict_grade`,
  `survivor_bias`, `pm1..pm5`, `poc_dist_126`, per-feature reason codes (`pm1_reason`…`pm5_reason`,
  `poc_reason`; value `ok` when defined), `n_bars_avail`, `anchor_age_bars`, `n_gaps_ignored`,
  `so_staleness_days`, `so_shares_raw`.

### 2.2 Per-ticker computation (PIT-exact)

For each ticker: load the store parquet once → numpy arrays (dates, o/h/l/c, volume). Missing store file
⇒ all features NaN, reason `no_store` (count printed). For each row: locate `signal_date` exactly in the
date array (absent ⇒ `no_signal_bar`); slice the last **min(250, available)** bars ending at the signal
bar inclusive (= window W). **All window computation happens on this slice only** — post-signal bars are
never touched (PIT by construction; the §4.4 gate-1 audit independently re-derives the slice).

- **Split adjustment:** call `split_adjust(close_slice)` (imported from
  `scripts.replay_standout_pipeline`, never reimplemented) on the W slice. Per-bar factor
  `factor_t = raw_close_t / adjusted_close_t` (red-team A3). Adjusted o/h/l = raw ÷ factor; adjusted
  volume = raw × factor. The slice's last bar is the signal bar ⇒ everything lands in signal-date units.
- **Split fence:** recompute `logr` on the raw close slice; a bar is a **split-suspect unadjusted jump**
  if `|log r| > SPLIT_LOG_THRESHOLD` (log 1.4, import the constant) AND `split_adjust` applied no snap at
  that jump (factor unchanged across it, tolerance-free comparison via the returned series). Any such bar
  inside W ⇒ pm1–pm4 and poc_dist_126 NaN, reason `split_suspect` (fence census counts per feature).
- **Window floor:** available bars < 200 ⇒ pm1–pm4 NaN, reason `short_window`.
- **PM1:** anchor = index of min adjusted close in W, **most recent bar if tied** (last argmin).
  `AVWAP = Σ_{t=a..s}(tp_t·v_t)/Σ_{t=a..s}(v_t)` on adjusted tp and adjusted volume;
  `pm1 = close_s/AVWAP − 1`. Degenerate anchor (a = s) accepted as-is. `anchor_age_bars = s − a`.
- **PM2:** dollar volume `dv_t = tp_t·v_t` (adjusted; split-invariant). `pm2 = Σ dv_t·1[|tp_t/close_s − 1| ≤ 0.03] / Σ dv_t` over W.
- **PM3:** on adjusted O/H/L within W; gap candidates at t where both t and t−1 are inside W (**Fable
  ruling EX-2:** gaps whose pre-gap bar falls before the window are not scanned; a ≥250-bar-old gap edge
  is outside the prereg's stated window semantics; disclosed in RESULTS). Down-gap: `high_t < low_{t−1}`,
  zone `[high_t, low_{t−1}]`; unfilled at s iff no u ∈ (t, s] has `high_u ≥ low_{t−1}`; size fence:
  `low_{t−1}/high_t − 1 > 0.25` ⇒ gap ignored as artifact-suspect (`n_gaps_ignored` per row, census
  total). `pm3 = 1` iff any unfilled zone's lower edge `high_t ∈ (close_s, close_s × 1.10]`, else 0.
- **PM4:** `pm4 = Σ dv_t·1[tp_t > close_s] / Σ dv_t` over W.
- **poc_dist_126:** live-chip fidelity — **close-weighted** rolling VWAP verbatim per
  `engine.dannytrades.poc_proxy` semantics (win=126, min_periods=max(20,126//4)=31): on the adjusted
  slice, `poc = Σ_{last min(126,n) bars}(close·vol)/Σ(vol)` requiring ≥31 bars (else NaN `poc_short`);
  `poc_dist_126 = close_s/poc − 1`. Subject to the split fence, NOT the 200-bar floor (**Fable ruling
  EX-3:** the reference column follows the live chip's own min_periods convention; it is a redundancy
  comparator, not a PM feature).
- **PM5 (data_blocked — computed for context/coverage only, never tested):**
  - Requires ≥63 bars ≤ s (else `pm5_short_window`). Numerator = Σ last-63-bars adjusted volume
    (signal-date share units).
  - SO lookup: statements rows for ticker with non-null `shares`, `filed ≤ s` (str-date compare after
    parse), pick latest `filed`; none ⇒ `so_missing`; `s − filed > 270d` ⇒ `so_stale`
    (**Fable ruling EX-4:** rows with null `shares` carry no SO observation and are skipped when
    selecting the latest row; convention logged).
  - Sanity fence: not `0 < shares < 1e11` ⇒ `so_corrupt`.
  - Unit conversion: split multiplier over `(period_end, s]` from the same snap series; requires
    `period_end` ≥ first store bar (else `so_prehistory`); any split-suspect unadjusted jump in
    `(period_end, s]` ⇒ `so_split_suspect`. If `period_end` predates the W slice, extend the raw slice
    back to `period_end` for snap detection only. `SO_pit = shares × multiplier`;
    `pm5 = numerator / SO_pit`. Label FLOAT-PROXY everywhere.
- **Medians (builder-logged, outcome-blind):** pm2, pm4 (and pm5 for the frozen future run) medians over
  defined values of the **verdict-grade fire** rows only; written to `qa_report.json` before any outcome
  join exists anywhere.

### 2.3 §4.4 QA gates (blocking; all results into `qa_report.json`)

1. **PIT spot-audit:** 60 rows sampled with `numpy.random.default_rng(606)` from the full artifact
   (NaN rows included — reason codes must reproduce). For each: **independently reload** the store
   parquet, hard-truncate `df = df[df.index <= signal_date]` and the statements panel at `filed ≤
   signal_date`, then recompute through the same feature function. Every feature and reason code must
   match the artifact **exactly** (bit-equal floats / identical codes; NaN == NaN). Mismatch ⇒ HALT.
2. **Split-fence census:** counts NaN'd per fence per feature (split_suspect / gap artifact-ignored
   count / so_split_suspect / so_prehistory / so_corrupt / so_stale / so_missing).
3. **Coverage table:** defined-fraction per feature on (a) verdict-grade fires (primary), (b) all fires,
   (c) verdict-grade near-misses. PM5 coverage restated against the 60% floor with the 992-ticker /
   panel-intersection numbers.
4. **Anchor sanity:** PM1 anchor-age distribution (min/p25/median/p75/max), degenerate-anchor count.
5. **Determinism:** rerun the full path on 200 rows sampled with `default_rng(202)`; recomputed values
   must be byte-identical to the artifact (`np.array_equal(..., equal_nan=True)` on float64 views and
   exact string equality on reasons).

## 3. Analysis runner (`run_PM0.py`) — staged, gate-enforcing

CLI: `--stage {preamble,calibration,inference}` run in order; each stage writes its JSON and refuses to
run if the prior stage's output is missing or failed. **`inference` additionally requires
`--authorize-one-shot` AND `calibration.json` with `overall_pass == true`** — the mechanical encoding of
the prereg's blocking-gates clause. Stages `preamble`+`calibration` never print a real trial p-value.

### 3.1 Preamble stage

- MD5s (replay, features, statements), column-map resolution over the prereg §1 frozen list, exact
  terminal-state enum check of both grids ({STOPPED, DEAD_MONEY, CUSHIONED, CLEAN_LIFTOFF}) — HALT on
  absence/unexpected enum. `horizon_censored` semantics logged; HALT if flag disagrees with per-grid
  state nullness.
- Era block: memo v1.1 citation, effective window statement (2022-06-30 → 2026-07-02 verdict window;
  observed signal range printed), survivor-stamp exclusion (measured 0), per-grid censored counts
  (measured 0, guard retained), §5/§6 checklist lines.
- Population census; medians read back from `qa_report.json` (runner never recomputes them — it verifies
  equality against its own computation and HALTs on drift, which would mean artifact/QA desync).
- Favorable splits (frozen): pm1 ≥ 0; pm2 ≥ median; pm3 == 0; pm4 ≤ median.
- Month census per trial (feature-defined rows; both-group ≥5-row month qualification; qualifying-month
  counts; per-month group sizes; episode ISO-week month-straddle count; episode month = month of its
  first row).
- Redundancy matrix §4.3 (Spearman): continuous pm1/pm2/pm4/pm5 (defined rows), binary pm3, vs frozen
  reference set {ext_z, ext_atr, dist_to_52wh, near_52wh, rs_63d_return, align_quality,
  washout_proximity, poc_dist_126} + within-bundle PM×PM. (Reference columns are features, not outcomes —
  reading them pre-outcome-join is conformant.)
- **Then** outcomes join (states/returns), event floor (state <50 events in trial population or <10 in
  either group ⇒ INSUFFICIENT-DATA) and month floor (<24 qualifying months ⇒ INSUFFICIENT-POWER); any m
  decrement logged here, before any p-value exists. Expected on measured substrate: no decrements, m=20.

### 3.2 Statistic (single implementation, used by calibration and inference)

For trial (F, G, S) on its analysis population (vg fires, era-clean, non-censored-at-G, feature defined):
- Per qualifying month m: `Δ_m = inc(S|fav,m) − inc(S|unfav,m)` (pp); `w_m = 2·n_f·n_u/(n_f+n_u)`.
- `Δ̂ = Σ w_m Δ_m / Σ w_m`.
- **p (primary):** month-block bootstrap, B=5000, seed derived deterministically per trial from the
  registered constant: `default_rng(20260706·10⁵ + trial_idx)` (amended 2026-07-10 pre-run to match the
  implementation — a per-trial derivation of the registered seed, frozen before any run); resample
  qualifying months with replacement, each drawn month contributes (Δ_m, w_m) intact; two-sided add-one
  null-centered pivot `p = (1 + #{|Δ*_b − Δ̂| ≥ |Δ̂|})/(B+1)`.
- Diagnostics (labeled NOT TIME-CONTROLLED, never verdict-feeding): (a) episode-label permutation on
  pooled Δ — episode majority label, cross-episode full-window shuffle, 2000 draws,
  `default_rng((777, trial_idx))`, add-one two-sided p; (b) MWU + rank-biserial on the grid's paired
  forward return, scipy parametric p printed beside it. Pooled Δ and pooled-vs-within divergence printed.
- Favorable direction: Δ̂ < 0 for STOPPED/DEAD_MONEY; Δ̂ > 0 for CUSHIONED.
- THIN: favorable or unfavorable group < 25 unique episodes.
- Sign stability (per §4.2): within-month Δ̂ recomputed on `signal_date ≤ 2024-06-30` vs after (same ≥5/5
  month qualification within each half); sign(Δ̂) must match.

### 3.3 Calibration stage (§7; all blocking)

- **Seed-vector convention (frozen pre-run):** all derived seeds use integer seed vectors passed to
  `numpy.random.default_rng([...])` with `FEAT_IDX = {pm1:1..pm5:5}` — never python `hash()` (salted per
  process). Negative-control instrument rng = `[777, FEAT_IDX]`; per-draw bootstrap = `[20260706,
  FEAT_IDX, draw_idx]`; return-injection permutation = `[777, FEAT_IDX, 555]`; incidence-injection
  episode draw = `[4242, FEAT_IDX]`; incidence-injection bootstrap = `[20260706, FEAT_IDX, 999983]`.
- **Negative (4 instruments = grid-A STOPPED of PM1–PM4):** 200 draws (one rng
  sequence per instrument, instrument-order-independent); labels permuted
  at episode level **within calendar month** (episode true label = majority row label; mixed-label
  fraction logged; episode month = first-row month); full primary machinery per draw (within-month Δ̂ +
  month-block bootstrap p with B=5000 per draw, rng derived (20260706, feature, draw_idx)). PASS per
  instrument: rej@0.05 ≤ 0.12; mean AND median p ∈ [0.4, 0.6]; KS-uniformity p ≥ 0.05; divergence gate =
  per-draw MWU param_p on fwd_ret_21 vs the draw's bootstrap p, tripped if >1% of draws show
  (bootstrap_p > 0.3 ∧ param_p < 1e-6) or (bootstrap_p < 1e-3 ∧ param_p > 0.5) (P2.5
  SANITY_DIVERGENCE_ORDERS=6 signature, generalized to the control loop; definition logged).
- **Positive — return instrument:** per instrument, +0.05 injected into favorable rows' `fwd_ret_21`
  copy; episode-permutation MWU diagnostic must reject perm_p ≪ 0.05 (report the values; P2.5 reference
  2e-4 scale).
- **Positive — incidence instrument:** per instrument on grid A: relabel favorable-group STOPPED rows to
  CLEAN_LIFTOFF totaling 5pp of the favorable group (whole episodes, drawn uniformly across qualifying
  months, `default_rng(4242)`); primary pipeline must detect with conservative synthetic-family BH-adj
  `min(1, p×20) ≤ 0.10`. (**Fable ruling EX-5:** §7.2 names one incidence instrument without fixing the
  feature; running it per instrument for all four features and requiring all to reject is a strictly
  more stringent superset, symmetric with §7.1.) The return instrument's permutation diagnostic is an
  episode-label permutation MWU (rank-biserial statistic) computed **on the injected return column**.
- **Fable ruling EX-6 (poc_dist_126 volume weight):** the reference column's rolling VWAP is
  close-weighted per `poc_proxy` (red-team A5's "verbatim" clause concerns close- vs tp-weighting); its
  volume input is the split-adjusted volume, per the prereg §2 preamble sentence that applies the
  inferred factor to volume for ALL feature computation on the raw Massive store.
- **Fable ruling EX-7 (divergence gate re-scope, 2026-07-10, pre-inference):** the per-draw
  bootstrap-vs-MWU divergence check originally written into this spec is STRUCK as mis-specified — a
  pooled row-level MWU on returns is calendar-confounded by construction, so it diverges from the
  month-controlled bootstrap whenever a feature's favorable share is calendar-clustered (measured:
  0% of draws on calendar-stable PM1, 63–70% on PM2–PM4), which is the DT-R14 confound, not the P1.3
  round-1 defect signature the prereg names. The §4.2(b) param/perm sanity gate is implemented at TRIAL
  level on the SAME MWU statistic (parametric p vs episode-permutation p of the same U; P2.5 signature:
  trips when ep_perm_mwu_p > 0.3 ∧ mwu_param_p < 1e-6; any trip HALTs inference before BH/verdicts).
  Negative-control PASS criteria remain the three §7.1 histogram criteria, verbatim.
- **Fable ruling EX-8 (episode-month blocking, 2026-07-10, pre-inference):** prereg §4.2 assigns each
  episode to the month of its first row. The initial implementation grouped rows by their own
  signal-date month, letting straddling episodes leak label-correlated rows across adjacent month
  blocks — violating the DT-R14 rubric requirement that episode correlation live INSIDE blocks (and the
  bootstrap's month-independence). All within-month grouping (trial statistic, month census,
  negative-control per-draw contrast) now uses the episode's first-row month. This is conformance to
  the registered design, not an amendment; adopted after the first calibration run failed KS on the
  instrument with the highest straddle/mixed exposure (PM2, KS 0.0333) with no real trial p-value
  examined. The first (failed) calibration run is preserved in the run log for the record.
- Disposable copies only; `calibration.json` gets `overall_pass`; any FAIL ⇒ blocker report, no marker,
  inference impossible.

### 3.4 Inference stage (one-shot)

20 trials per prereg §5 table → BH q ≤ 0.10 over the post-decrement family → sign stability on
BH-survivors → THIN flags → §4.3 redundancy application (incl. within-bundle tie-break: smaller
BH-adjusted p on best surviving trial promotable, other REDUNDANT-WITHIN-BUNDLE) → §6.1 per-component
verdicts (SURVIVES / NO-GO / data_blocked / REDUNDANT) → §6.3 bundle verdict. §8 context outputs
(CLEAN_LIFTOFF deltas, grid-B DEAD_MONEY descriptive, MAE/MFE medians via fwd_mdd_21/fwd_mfe_21, sector
composition, deciles, near-miss read incl. pm5 labeled FLOAT-PROXY/PARTIAL-COVERAGE, DannyTrades
provenance box). `results.json` + `RESULTS.md` per §9 contract, all nine sections; nulls printed
honestly; NO price-level trade-instruction fields anywhere (DT-R2/DT-R7).

## 4. Report & routing (Fable-owned after the run)

Registry rows (family `price_memory`, ids EI-PM1-AVWAP / EI-PM2-SHELF / EI-PM3-GAP / EI-PM4-OVERHEAD /
EI-PM5-FLOATTURN), EI masterplan §9 entry, Signal Commons parked-row resolution, DT-R7 clock closure —
drafted into RESULTS.md §8-rows by the runner, applied to the registry/masterplan docs by Fable in the
same PR. Display-only ceiling restated in every verdict line.

## 5. Performance notes (non-binding)

Per-ticker array conversion once; per-row slice work is O(W). Expected: feature build minutes-scale;
calibration is the heavy stage (4 × 200 × 5000 bootstrap = 4M month-vector resamples — vectorize the
bootstrap over draws; per-draw work is small since months ≈ 43). Keep memory flat (never load the full
961k-row replay with all columns; use column projection).
