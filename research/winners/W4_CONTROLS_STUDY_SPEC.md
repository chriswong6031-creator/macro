# Winner Autopsy W4 — matched-controls fingerprint study spec (Layer-3b)

Authored 2026-07-22 (main-loop Fable). Executes the masterplan's Layer-3 question (b)
(`research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md` §2): **pre-onset, what separated
eventual breakaway names from matched controls sampled the same calendar day.** This is
the remaining unrun Layer-3 leg after W3 (Layer-3a) returned its census null
(`research/winners/FINGERPRINT_CENSUS_W3.md`, WA-R8: nothing registered). Different
question than W3: W3 asked *who keeps going among breakaways*; W4 asks *who breaks away
at all* — the watchlist-formation question. Descriptive / display-tier throughout; NO
registration in this lane (any candidate that survives goes to a WA-R8-style ruling
appended by the main loop). No composite scores (WA-R1/R5).

## 0. W3 lessons — binding from the start (each caused a round-1 finding last time)

1. **True multiplicity correction:** the `bonf` flag derives from the two-sided α/m
   percentile CI of the SAME bootstrap draws (tails = (0.05/m)/2 each side), never from
   the 95% CI. n_boot = 50,000, seed 20260722. Print BOTH CIs per row. Declare m in the
   header; structurally-constant features are excluded from m and tables.
2. **No label-embedded features:** every feature must be computable strictly from
   information ≤ t0 (the episode's onset date). NO forward windows of any length. The
   control's "outcome" is never used. (W4's design makes tautology harder than W3's —
   controls have no outcome label — but the guard stands: if a candidate feature's
   definition references the episode/candidate state itself, it is the SELECTION
   variable, not a fingerprint; see §3 exclusions.)
3. **Mask, don't impute:** missing coverage (8-K store absence, fundamentals absence)
   drops the observation from that feature with counted coverage — never zero-fill.
4. **Cluster honesty:** primary estimator is within-matched-set (below), with a
   month-block bootstrap over episodes AND a ticker-cluster bootstrap robustness column
   (episode tickers with replacement; a ticker's episodes + their control sets move
   together).
5. **Survivor-only caveat:** the census and its control pool are survivor-lean (the
   `survivorship_biased` column is an unpopulated constant; no dead-name price source in
   this parquet). State it in §Honesty; do not claim a tested survivorship stratum.
6. **Crypto excluded** from the primary (7-day calendar + SPY-benchmark category error);
   counts printed.

## 1. Substrate (frozen — no re-harvest)

Episodes: `data/research/winner_episodes.parquet` at origin/main HEAD (manifest hash +
harvest date recorded in the report; do NOT re-run `detect_episodes`/`label_outcomes`).
Controls: sampled live via `engine/winner_autopsy.py:sample_controls` (read-only import)
— deterministic (sorted, no RNG), same-sector, PIT-active at t0, liquidity floor, not in
candidate state within ±21td of t0, k ≤ 20 per episode. Record per-episode control
counts; episodes with < 3 eligible controls are excluded and COUNTED.

## 2. Population & contrasts

Equity episodes with matured outcome labels (same population W3 used, n ≈ 1,236 minus
crypto) PLUS their control sets.

- **Contrast 1 (PRIMARY): all matured episodes vs their matched controls** — what
  precedes ANY breakaway onset. This is the watchlist question, and after the W3 null
  (winners ≈ blow-offs at onset) it is the honest primary: predicting the onset, not
  its quality.
- **Contrast 2 (secondary): kept_going episodes vs their controls.**
- **Contrast 3 (secondary): blow_off episodes vs their controls.**
  If Contrasts 2/3 mirror Contrast 1 (expected under the W3 null), say so plainly —
  that is itself the finding: pre-onset structure predicts *motion*, not *quality*.

## 3. Features (strictly ≤ t0; computed IDENTICALLY for episode and control tickers)

For each episode (ticker E, date t0) and each of its controls (ticker Cᵢ, same t0):

- **Price/volume geometry (masterplan Tier-1 list):** drawdown from 252d high at
  t0−21td; days below 200dma in the trailing 252td; RS-turn 21/63 (trailing excess vs
  SPY at 21td and 63td); `dollar_vol_z21`; dv_5_60 ratio; close-location value (21td
  mean); trailing 63d realized vol. For EPISODE rows, where a parquet column exists
  (`excess_21d_pp`, `dollar_vol_z21`, `dv_5_60_ratio`), the recomputed value MUST match
  the committed column (parity check, tolerance 1e-6) — this pins the control-side
  implementation to the census's own definitions.
- **8-K catalyst density (trailing only):** hard/soft event counts in (t0−126d, t0)
  from `material_8k_events` (PIT `filing_date` < t0), masked where store coverage is
  absent (per W3's F1 finding, coverage ~44%; controls will have their own coverage —
  print both).
- **Fundamentals presence + B2-style self-funding** where committed panels cover
  (A2-firewall honored: no t0 ≥ 2024-01-01 fundamentals aggregation), NON-COMPARABLE
  flag below 30% coverage in either side of a contrast.
- **EXCLUDED by construction:** anything encoding the candidate/onset state itself
  (excess-at-t0 threshold crossings, new-high flags, candidate-state fields) — those
  ARE the detector's selection variables; comparing them episode-vs-control is
  tautological by §0.2. Also excluded: F6-class compressed-prior proxies (still
  structurally blocked — no PIT short interest/options/dispersion for the census era).

## 4. Estimator (committed)

Matched-set design: for each feature, per episode compute
`Δ = value(E, t0) − median(value(Cᵢ, t0))` over its covered controls.

- Primary statistic per contrast: **median of Δ across episodes** (continuous) or
  **rate(E) − pooled rate(controls)** computed within matched sets then aggregated
  (binary).
- CI: month-block bootstrap over EPISODES (block = t0 calendar month; one drawn month
  multiset per replicate; an episode drawn brings its whole control set — the matched
  set is the resampling atom inside the month), 50,000 reps, seed 20260722, percentile
  95% CI AND α/m CI per §0.1.
- Robustness: ticker-cluster bootstrap (resample episode tickers with replacement,
  matched sets attached).
- Degenerate guard: a contrast side with < 12 distinct t0 months → report only, no CI.

## 5. Honesty section (each its own table/paragraph)

Survivor-only statement (§0.5); per-feature coverage counts episode-side AND
control-side; excluded-episode counts (< 3 controls; crypto; unmatured); control-pool
size distribution; `gap_leg_crossed == False` stratum rerun of Contrast 1; a
"what W4 cannot see" paragraph (options/revisions/short-interest still forward-accruing,
first answerable ~2027-06).

## 6. Deliverable

Study script `scripts/research/run_w4_controls_fingerprints.py` (self-contained,
`--root` read-only for stores, never writes under root; engine imported read-only) +
pytest smoke tests (stat helpers incl. an α/m-vs-95% disagreement case, matched-set
bootstrap atomicity — an episode never separates from its controls in a draw, parity
check vs committed columns) + report `research/winners/FINGERPRINT_CONTROLS_W4.md`:
bottom line first; population + control-pool tables; per-feature tables (both CIs +
cluster CI + bonf flag + coverage); Contrast 2/3 vs Contrast 1 comparison; honesty
section; explicit per-feature SEPARATES / NULL / UNTESTABLE lines; ends with
`## Adjudication (main loop)` containing only "PENDING".

## 7. Prohibitions

No filter/gate/screen/score, no site surface, no registry edits, no census re-harvest,
no engine logic edits, no case-file touches. If `sample_controls` or feature parity
turns out to be unimplementable as specified, STOP and report — do not improvise a
different matching design.
