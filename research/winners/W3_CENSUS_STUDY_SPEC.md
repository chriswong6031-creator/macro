# Winner Autopsy W3 — census fingerprint study spec (Layer-3a)

Authored 2026-07-20 (main-loop Fable). Executes the masterplan's Layer-3 question (a)
(`research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md` §2): **at onset, what separates
episodes that kept going from those that failed** — by testing the W2 candidate
fingerprints (`research/winners/FINGERPRINT_REPORT_W2.md` §4) against the full census
base rates. **Descriptive / display-tier throughout** (epistemics law: ships freely; a
null never blocks). NO fingerprint is registered in this lane — registration is a WA-R8
ruling appended by the main loop after results (§8 below). No composite score of any
kind (WA-R1/R5; the fused-score construction is STRUCK in DO_NOT_REBUILD §2).

## 1. Substrate (frozen — no re-harvest in this lane)

`data/research/winner_episodes.parquet` at current origin/main HEAD, as committed
(builder records the `winner_episodes_manifest.json` hash + harvest date in the report;
do NOT re-run `detect_episodes`/`label_outcomes` — census refresh is a separate lane).
2,650 episodes / 457 tickers / t0 1997-07-23 → 2026-07-02.

## 2. Population & contrasts

Matured episodes only: `outcome_label ∈ {durable_winner, clean_hold, blow_off, failed}`
(n ≈ 1,236; the 1,414 unmatured are COUNTED in the report, not silently dropped).

- **KEPT-GOING** = `durable_winner ∪ clean_hold` (n ≈ 150).
- **Contrast 1 (PRIMARY):** kept-going vs `blow_off` (n ≈ 773) — the live-watcher
  confusion pair (both look like breakaways at t0; blow-offs dominate ~6:1).
- **Contrast 2 (secondary):** kept-going vs `failed` (n ≈ 313).
- blow_off vs failed printed once as context, no verdicts.

## 3. Features (t0-measurable or bounded-early only — NO `fwd_*` columns as predictors)

**Circularity guard (hard rule):** outcome labels are determined from forward excess
windows out to 126d/252d. No feature may read information past **t0+21 trading days**,
and any feature using t0+k (k > 0) information is labeled an **early-move conditioner**,
not an onset feature, in every table.

- **Pure-t0 (from parquet columns):** `excess_21d_pp` (trailing), `dollar_vol_z21`,
  `dv_5_60_ratio`, `new_high_63d`, `liquid`, `self_funded_at_t0` (B2),
  `b2_cfo_y0`/`b2_cfo_y1`, `b1_coverage`, sector (context split only).
- **F4 composite (t0):** `new_high_63d ∧ excess_21d_pp ≥ 20`.
- **F1 — catalyst-ladder rung count (early-move conditioner).** BUILDER MUST VERIFY the
  window direction of `hard_event_count_126d` / `soft_event_count_126d` /
  `soft_then_hard` in `engine/winner_autopsy.py:extract_features` before use. If these
  count events in the FORWARD 126d window (likely), they overlap the labeling horizon
  and are FORBIDDEN as-is: recompute rung counts from `material_8k_events` bounded to
  **(t0, t0+21td]** (and report the t0−63d→t0 trailing count as a separate pure-t0
  feature). Feature = rung count ≥ 2 within the bound.
- **F2 — trigger gap holds (early-move conditioner):** onset-day gap % (open vs prior
  close from the same price store the census used, honoring `price_source`), and
  close(t0+k) > close(t0−1) for k ∈ {3, 5, 10}. Names with missing bars in the window
  are counted-not-hidden.
- **F3 — profit step-up faster than revenue (coverage-limited):** at the statement print
  nearest ≤ t0 (committed in-repo panels only — A2 firewall WA-R7): sign of
  Δ(operating income %) − Δ(revenue %) QoQ. Computed ONLY where panel coverage exists;
  coverage counts per group printed; if coverage < 30% of either primary-contrast group,
  compute anyway but flag NON-COMPARABLE.
- **F6 — compressed prior: STRUCTURALLY BLOCKED.** No PIT short-interest / options /
  consensus-dispersion history in-repo for the census era (WA deferral, L10-aligned).
  One honest paragraph in the report; not silently dropped.

## 4. Statistics (committed)

For each feature × contrast:

- Binary features: group rates, difference (kept-going − comparator), **month-block
  bootstrap 95% CI** (block = t0 calendar month; resample months with replacement,
  recompute pooled group rates; 10,000 reps, seed 20260720; paired-by-block — same drawn
  months feed both groups), Wilson diff CI as cross-check. Degenerate guard: a group
  with < 12 distinct t0 months → report only, no CI.
- Continuous features: group medians, median difference, same month-block bootstrap.
- **Multiplicity:** m = total number of feature × contrast tests, declared in the report
  header. A `bonf` column flags CIs that survive α = 0.05/m (via the corresponding
  percentile CI). ALL rows printed regardless — this is a census, not a screen.

## 5. Honesty strata (each printed as its own table)

- Primary contrast recomputed on `survivorship_biased == False` only.
- Primary contrast recomputed on `gap_leg_crossed == False` only (the 2021-10→2025-01
  full-universe price gap).
- `price_source` mix per group; unmatured count; per-feature coverage counts.

## 6. Deliverable

`research/winners/FINGERPRINT_CENSUS_W3.md`: bottom line first; population table;
feature tables per §4; strata per §5; an "honest read (nulls printed)" section that
states plainly which W2 candidates the census REFUTES (blow-offs share the feature),
which survive as candidates, and which are untestable; the W2 §4 predictions each get an
explicit CONFIRMED / REFUTED / UNTESTABLE line. Any supporting computation lives in
`scripts/research/` (a small, self-contained study script; engine untouched except a
read-only import), with a pytest smoke test.

## 7. What this study may NOT do

No filter, gate, screen, entry condition, or score. No site surface. No registry edits
(adjudication is main-loop work). No census re-harvest. No edits to
`engine/winner_autopsy.py` detection/labeling logic. Case files
(`research/winners/cases/`) untouched — two case PRs (#3084/#3085) are in flight on
those paths.

## 8. Adjudication placeholder

§ appended post-review by main-loop Fable: WA-R8 ruling on whether any candidate earns a
future pre-registered slot (which would be its own prereg doc + lane), or all stay
descriptive.
