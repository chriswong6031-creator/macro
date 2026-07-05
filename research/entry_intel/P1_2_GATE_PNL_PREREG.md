# P1.2 Gate P&L — Pre-Registration

**STATUS: DRAFT — PENDING FABLE APPROVAL (ruling R8: does not execute before replay golden test + PIT audit are clean)**
**Revision:** 2026-07-04 — blocking fixes applied (P1.2-B1: FLIP predicate rewritten; P1.2-B2: m corrected to 72) + advisory fixes (P1.2-A2: 10–24 gray band default stated) + era law absorbed from P0_MEASUREMENT_MEMO.md v1.0; §5 conformance checklist reference added.

*2026-07-04 · Entry Intelligence program (research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5/P1.2) · registered BEFORE first run (this file's merge commit precedes any run against `data/replay/`).*

---

## Study identity

**Study:** P1.2 Gate P&L
**Family ID (BH FDR):** `ei_gate_pnl` — one BH family across all rejection-reason tests; m taken from the trial grid below before first run and logged to the trial ledger.
**Horizon class:** positional (primary verdict at 21d and 63d; both horizons mandatory per safety-net axes; 126d printed as context).
**Upstream gate:** gated on P0.1 replay golden test PASS + P0.1 Opus PIT audit CLEAN (ruling R8). Reads `data/replay/standout_replay.parquet` only (ruling R9; see §Data source below).

---

## Purpose and mechanism story

The production funnel applies ten rejection gates (closed taxonomy, `engine/grading.py REJECTION_TAXONOMY`). Each gate is a deterministic rule that blocks a candidate on a specific grounds. When a gate blocks, the candidate does not appear on the board. Today that no vanishes — no outcome is ever recorded for it.

The hypothesis this study tests per gate: **does blocking on this reason actually protect capital (lower stop-out, lower dead-money) or does it block valid entries (lower cushion, lower clean-liftoff)?** The safety-net axis deltas determine whether each gate earns its keep, needs weakening (demote-to-penalty), or should flip to its opposite (flip). Verdicts are bounded by the matching quality and n floors declared below.

This study is NOT a separability test (that is P1.1). It is a per-gate counterfactual: given two cohorts — rows rejected for reason R and rows that fired near the same time, sector, and alignment tier — do the rejected rows have meaningfully worse or better downstream outcomes than the fires?

Pre-registered standing hypothesis (inherited from species masterplan §5.2): **rejection ≠ blacklist** — some rejection cohorts may outperform their accepted siblings. That is a valid finding, not a bug; it feeds gate demotion or flip verdicts below.

---

## Data source

**Canonical:** `data/replay/standout_replay.parquet` (canonical checkout, never committed to git per R9).

Every analysis in this study reads ONLY the replay artifact. No live production JSON, no `site/factordata/`, no online calls. Features frozen to columns logged by the replay harness at signal time.

Columns consumed (must be present in the replay schema; run halts with a clear error if absent):

| Column | Type | Notes |
|--------|------|-------|
| `ticker` | str | |
| `signal_date` | date | the signal bar (T); entry fill = T+1 close |
| `verdict` | str | `fire` / `near_miss` / `rejected` |
| `primary_rejection_reason` | str or null | CLOSED taxonomy member or null |
| `alignment_tier` | str | `PRIME` / `ARMED` / `APPROACHING` |
| `alignment_quality` | float | 0–100 quality score from `mtf_alignment` |
| `gics_sector` | str | GICS L1 sector at signal time |
| `terminal_state_21d` | str | `STOPPED` / `DEAD_MONEY` / `CUSHIONED` / `CLEAN_LIFTOFF` |
| `terminal_state_63d` | str | same partition at 63d |
| `terminal_state_126d` | str | context only |
| `fwd_ret_21d` | float | |
| `fwd_ret_63d` | float | |
| `fwd_mae_21d` | float | maximum adverse excursion through 21d |
| `fwd_mfe_21d` | float | maximum favorable excursion through 21d |
| `fwd_mae_63d` | float | |
| `fwd_mfe_63d` | float | |
| `episode_cluster_id` | str | date-cluster id (21d calendar windows, see §Matching algorithm) |
| `survivor_stamp` | str or null | `survivor_priced` if row is outside the 2021-07-06+ Massive-sourced verdict window (pre-2021 or unconfirmed source) |

---

## Era handling clause

**Memo citation (mandatory):** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)`. Every run prints this citation in the preamble per §5 conformance checklist.

**Primary window:** `2021-07-06 → last-full-replay-date` — the sole verdict-grade era per the P0 Measurement Memo §1 era table (STRICT-WINS ruling). The former PREREG placeholder "2015–present" is superseded; §1.2 of the memo explicitly rejects a 2015-boundary. Verdict-grade claims (stop-out / dead-money / cushion / clean-liftoff rates with BH p-values) are produced ONLY for UNSTAMPED rows (`survivor_bias = false`) within this window — i.e., rows with `signal_date ≥ 2021-07-06` whose price series is Massive-sourced and whose full grading horizon falls within the replay window.

Rows outside the primary window carry `survivor_stamp = survivor_priced` and are printed in a Survivor-Stamped Context Appendix only — they are NEVER included in the verdict computation, BH family, or flip criterion evaluation.

If `P0_MEASUREMENT_MEMO.md` does not exist at execution time, the study **HALTS** with an explicit error and returns a blocker report — it does not self-select an era.

The run preamble prints: memo version+date, exact primary window, count of unstamped rows, count of stamped rows excluded, and count of `horizon_censored` rows excluded per horizon. If unstamped episode-clustered n is insufficient for a verdict, the study returns INSUFFICIENT-POWER rather than borrowing pre-2021 rows.

**§5 conformance checklist** (P0_MEASUREMENT_MEMO.md §5 — confirmed at run start):
- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` in preamble.
- [ ] Primary window = `2021-07-06 → last-full-replay-date`.
- [ ] Verdict-grade statistics on `survivor_bias = false` rows only.
- [ ] Confirms via per-row source stamp that unstamped rows are Massive-sourced.
- [ ] All pre-2021 rows stamped, routed to labeled context appendix, excluded from BH family, sign-stability, n-floors, and all GO/NO-GO / flip decisions.
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately.
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] Returns INSUFFICIENT-POWER (honest null) if unstamped n floor not met.

---

## Rejection taxonomy (closed; all ten members tested)

Sourced from `engine/grading.py REJECTION_TAXONOMY` (frozen at registration). No silent additions per the masterplan law: adding or renaming a reason requires a §8 status row + monthly-review sign-off.

| reason code | gate description |
|---|---|
| `freshness_expired` | signal_gate FRESH_TICKS window — chasing an aged cross |
| `not_topped_veto` | signal_gate not-topped check — buying a topped oscillator |
| `tier_cutoff` | confluence_tiers T4-excluded / below-tier threshold |
| `extension_demote` | anti-chase EXT_PENALTY / extension-since-cross |
| `knife_demote` | falling-knife quintile demotion (US/CA port) |
| `sector_cap_displaced` | board sector-concentration cap |
| `board_rank_cutoff` | blend_sorted position below board width |
| `event_blackout` | earnings-proximity exclusion (where wired) |
| `cohort_null` | §3.3 coverage law (coverage_pct < 70%) |
| `hygiene_screen` | ST/ADV/staleness/mcap screens — EXCLUDED from all grading (see §Hygiene exclusion below) |

`hygiene_screen` rows are present in the replay for coverage tracking only. They are excluded from every verdict computation, BH family member count, and matching pool per incumbent law (R10 + species constitution §1.4: hygiene ≠ alpha; grading.py L109 explicitly documents "NOT graded as predictions"). The remaining nine reasons constitute the testable population.

---

## Matching algorithm (stated precisely)

The counterfactual cohort for each rejected row is a **matched fired cohort** drawn from the replay `fire` rows. Matching proceeds in the following order and is applied identically across all nine testable rejection reasons.

**Step 1 — date-cluster assignment.**
Calendar dates are partitioned into non-overlapping 21-trading-day windows starting from the earliest date in the primary era. Each (ticker, signal_date) row is assigned to the window containing its signal_date. This produces an `episode_cluster_id` column (must be present in the replay schema; if absent, computed here from `signal_date` using the same 21-day bucketing). Each cluster id is a string of the form `YYYY-MM_wNN` (year-month plus window index within month, for human readability; the exact string format is non-binding as long as non-overlapping 21-day buckets are used consistently).

**Step 2 — exact matching on (episode_cluster_id, gics_sector, alignment_tier).**
For each rejected row with reason R, the matching pool is all `fire` rows sharing the same `episode_cluster_id`, the same `gics_sector` (GICS L1), and the same `alignment_tier` (one of `PRIME`, `ARMED`, `APPROACHING`).

**Step 3 — pool size gate.**
If a rejected row's matching pool contains fewer than three distinct fire rows (distinct by ticker), the rejected row is dropped from the analysis for reason R and a coverage count is printed. The minimum-three rule avoids near-degenerate single-match comparisons while preserving pool diversity.

**Step 4 — matched cohort construction.**
For each rejection reason R, the matched fired cohort is the UNION of all fire rows that appear in at least one rejected row's matching pool for reason R. Rows may appear more than once (once per rejected row they match); the outcome distribution is computed on the full union with duplicate rows weighted equally. The rejection cohort for reason R is all rejected rows with `primary_rejection_reason == R` that survive the Step 3 gate.

**Step 5 — outcome computation.**
Separately for the rejection cohort and the matched fired cohort: compute the terminal-state distribution at 21d and 63d (stop_out_rate, dead_money_rate, cushion_rate, clean_liftoff_rate — each as proportion of rows in the cohort, denominator = all rows including those that have not yet resolved at the shorter horizon). Print absolute rates and the delta (rejection cohort minus matched fired cohort) on each axis.

**Precision note:** the matched fired cohort intentionally does NOT sample one matched fire per rejection row (caliper/nearest-neighbor matching). The union design is chosen because (a) per-rejection-reason cohorts are small and caliper matching would further thin them, and (b) the union shares the same confounders (date cluster, sector, tier) without introducing sampling variance. The resulting fired cohort may be larger than the rejection cohort; all rate comparisons are proportion-based, so size asymmetry is benign.

---

## Registered config grid (trial ledger family `ei_gate_pnl`)

Each testable rejection reason crossed with each primary verdict horizon constitutes one trial. The grid is fixed at registration; any post-hoc variation (e.g. alternative horizon, alternative matching key) is a new trial and must be recorded in the trial ledger before running.

| trial | rejection_reason | primary verdict horizon | notes |
|---|---|---|---|
| T01 | `freshness_expired` | 21d | primary |
| T02 | `freshness_expired` | 63d | primary |
| T03 | `not_topped_veto` | 21d | primary |
| T04 | `not_topped_veto` | 63d | primary |
| T05 | `tier_cutoff` | 21d | primary |
| T06 | `tier_cutoff` | 63d | primary |
| T07 | `extension_demote` | 21d | primary |
| T08 | `extension_demote` | 63d | primary |
| T09 | `knife_demote` | 21d | primary |
| T10 | `knife_demote` | 63d | primary |
| T11 | `sector_cap_displaced` | 21d | primary |
| T12 | `sector_cap_displaced` | 63d | primary |
| T13 | `board_rank_cutoff` | 21d | primary |
| T14 | `board_rank_cutoff` | 63d | primary |
| T15 | `event_blackout` | 21d | primary |
| T16 | `event_blackout` | 63d | primary |
| T17 | `cohort_null` | 21d | primary |
| T18 | `cohort_null` | 63d | primary |

m = 72 raw p-values (18 reason×horizon cells × 4 safety-net axes per cell). BH family size = 72. The trial grid has 18 reason×horizon cells; each cell produces four axis p-values (Δ_stop_out, Δ_dead_money, Δ_cushion, Δ_clean_lift), all of which enter the BH correction simultaneously. `deflated_sharpe` does NOT apply (proportion verdicts; DSR applies only to return-series legs per §1.2 measurement law). BH q ≤ 0.10 per family.

**126d context grid:** for every trial T01–T18 where the rejection cohort has n ≥ 10 surviving rows at 126d, the 126d terminal-state distribution is printed as context in the report. These context rows are NOT counted in the BH family and carry no verdict weight.

---

## Primary statistics and thresholds

**Primary statistic per trial:** the four safety-net axis deltas at the declared horizon:

```
Δ_stop_out    = stop_out_rate(rejected) − stop_out_rate(matched_fired)
Δ_dead_money  = dead_money_rate(rejected) − dead_money_rate(matched_fired)
Δ_cushion     = cushion_rate(rejected) − cushion_rate(matched_fired)
Δ_clean_lift  = clean_liftoff_rate(rejected) − clean_liftoff_rate(matched_fired)
```

A positive Δ_stop_out means the rejected cohort would have stopped out MORE than the fires. A negative Δ_cushion means the rejected cohort would have cushioned LESS.

**Episode-clustered p-value:** for each Δ, a block-bootstrap p-value (B = 10,000 draws) with blocks = episode_cluster_ids, resampling at the cluster level. Block size ≥ 21 trading days (the forward window length). This produces one p-value per (rejection_reason, horizon, axis). BH correction applied across all 18 × 4 = 72 raw p-values, with q-threshold ≤ 0.10 for a finding to count as significant.

**Wilson lower bounds:** for each significant axis in a rejection reason, Wilson lower bound (z = 1.645, one-sided 95%) is computed on the cohort proportion to set the n-floor print: the Wilson bound is printed beside every rate so thin-cell inflation is visible.

**n floor for verdict eligibility:** a rejection cohort with n < 10 distinct rows after Step 3 pruning prints rates in the context table with a `thin_cell` flag and does NOT contribute to any flip criterion. A rejection reason where fewer than 10 rows survive is noted as `insufficient_n` in the verdict table; its trial is retained in the BH family (counted in m) but its verdict is INCONCLUSIVE regardless of the raw delta.

---

## Pre-registered verdict thresholds per gate

For each testable rejection reason, the verdict is one of: **KEEP / DEMOTE-TO-PENALTY / FLIP**, determined by the following decision rules applied in order. All criteria must be met at both the 21d and 63d horizon to trigger a DEMOTE or FLIP verdict (conservatism: if horizons disagree, the verdict is KEEP with a note).

**KEEP:** default verdict. Applied when (a) n < 10 (INCONCLUSIVE, logged as KEEP pending more data), (b) BH q > 0.10 on all four axes, or (c) significant axes show Δ_stop_out < 0 OR Δ_dead_money < 0 (rejected cohort would have had higher stop-out or dead-money — gate is protective on at least one safety-net axis). A rejection reason with 10 ≤ n < 25 that passes BH on the DEMOTE axes but does not meet the DEMOTE n-floor (n ≥ 25) is also logged as **KEEP-WITH-NOTE**: the direction is flagged as potentially demote-worthy but insufficient n prevents a DEMOTE verdict; it is printed in the report with its deltas and the note "n in 10–24 band; revisit if replay extends."

**DEMOTE-TO-PENALTY:** the gate is currently a hard block (fires ≡ 0 for this reason). Demote to a negative rank-weight penalty (does not zero the fire, reduces its rank score) when ALL of the following hold at both 21d and 63d:
- BH q ≤ 0.10 on at least the Δ_stop_out and Δ_cushion axes (both must be significant).
- Δ_stop_out > 0 at both horizons (rejected cohort stops out MORE — gate is currently blocking names that would have stopped out anyway; weakening saves recall without worsening safety net). OR: Δ_stop_out is not significantly positive but Δ_cushion < 0 AND Δ_clean_lift < 0 at both horizons (gate is blocking names with materially worse cushion/liftoff outcomes — demote is conservative, preserves the signal without full reversal).
- The Wilson lower bound on the rejection cohort's stop_out_rate is below the Wilson lower bound on the matched fired cohort's stop_out_rate (confirming the directional delta is real at the distribution level, not artifact of tail outliers).
- The rejection cohort n ≥ 25 distinct rows at both horizons (the n-floor for demote verdicts; thin cells cannot earn a demote).

**FLIP:** the gate blocks names that would have outperformed the fires on the primary safety-net axes. Flip verdict (gate becomes a positive rank bonus or is loosened to admit these rows) when ALL of the following hold at both 21d and 63d:
- BH q ≤ 0.10 on ALL four axes simultaneously.
- Δ_stop_out < 0 at both horizons (rejected cohort stops out LESS than the matched fired cohort).
- (Δ_cushion > 0 OR Δ_clean_lift > 0) at both horizons (rejected cohort cushions or lifts off MORE than the matched fired cohort).
- The rejection cohort n ≥ 50 distinct rows at both horizons (the n-floor for flip verdicts; a flip verdict changes money-path behavior and requires a higher evidence bar).
- Both-halves sign stability: the sign of Δ_stop_out and Δ_cushion must agree in both the first and second calendar halves of the primary era (one split at the midpoint date). A FLIP verdict is not issued if sign flips across halves.

Alignment with ruling R4: no pre-commitment to gate-ification. A FLIP verdict outputs a recommendation that the gate become a rank-weight bonus (positive weight for the "rejected" condition), NOT an automatic promotion to a new positive gate. The recommendation is reviewed by Fable before P2.2 execution.

---

## What result kills vs ships

**KILL (gate demotion/flip study halted):** if BH q > 0.10 for ALL nine testable rejection reasons across all axes at both horizons, the study returns INCONCLUSIVE (not enough power or not enough n in rejection cohorts). This is reported to Fable with the coverage table; it does NOT kill the program, only this study's power to produce verdicts. P1.2 may be re-run once the replay artifact extends further backward in time.

**SHIPS (a gate verdict):** any rejection reason reaching a DEMOTE-TO-PENALTY or FLIP verdict as defined above ships a recommendation entry for P2.2 (gate adjustments). Each such entry carries: the exact n, the exact deltas, the Wilson bounds, the BH q-value, and both-halves stability confirmation. Recommendations are candidates for P2.2, not automatic merges — Fable reviews before execution.

**SHIPS (a KEEP verdict):** a statistically significant result showing the gate IS protective (Δ_stop_out < 0 or Δ_dead_money < 0 at q ≤ 0.10) is a positive confirmation. It is noted in the P1.2 report as evidence the gate earns its keep and is not re-evaluated in P2.2 unless new era data changes the result.

---

## What this study does NOT do

- Does NOT run before P0.1 golden test passes and P0.1 PIT audit is clean (ruling R8).
- Does NOT grade `hygiene_screen` rows as predictions (incumbent law, R10, species §1.4).
- Does NOT auto-tune gate thresholds — verdicts are binary recommendations reviewed by Fable.
- Does NOT test the gates as rank weights (that is P1.3 scope for the trio; the gate-as-weight question for non-trio gates is a P2.2 execution decision, not a P1.2 PREREG commitment).
- Does NOT merge any code changes — P1.2 produces a report and recommendation list only.
- Does NOT produce a return-series verdict (DSR does not apply; proportion verdicts only).

---

## In plain English

> Every time the system says "no" to a stock for a specific reason — stale signal, topped oscillator, too many stocks from the same sector already on the board, and so on — we now check: what actually happened to that stock afterwards? We compare those "no" names against a matched group of "yes" names from the same sector, same time window, and same quality tier. If the rejected names would have stopped out just as often (or more) than the accepted ones, the gate is earning its keep. If the rejected names would have been safer and performed better than the accepted ones, we flag that gate for loosening or removal. Every verdict is pre-committed in this document before we look at a single outcome number — and a result only counts if it survives a formal multiple-testing correction across all 72 p-values (18 reason×horizon cells × 4 safety-net axes) we test.

---

## Report contract

`research/entry_intel/P1_2_GATE_PNL_REPORT.md` with:
- Per-reason coverage table: n rejection rows, n matched fire rows, Step 3 prune rate, `thin_cell` flags.
- Primary verdict table: Δ_stop_out, Δ_dead_money, Δ_cushion, Δ_clean_lift at 21d and 63d with Wilson bounds, raw p-value, BH q-value, verdict (KEEP / DEMOTE-TO-PENALTY / FLIP / INCONCLUSIVE).
- Context appendix: 126d distribution for reasons with n ≥ 10 at 126d; survivor-stamped rows listed in aggregate with no verdict attribution.
- Both-halves stability table for any FLIP candidate.
- Era coverage statement: exact primary window used (citing the P0 Measurement Memo era table), count of survivor-stamped rows excluded, count of primary-era rows included.
- Leak-audit section: fill rule (entry = first close strictly after signal_date, next-bar convention); date mapping (signal_date = signal bar T, not fill bar); no forward-looking feature confirmed (all features frozen to replay columns stamped at T, not T+1 or later); episode cluster window (21 trading days, non-overlapping, from primary era start). Explicit disclosure that `gics_sector` used as a matching key is the replay-frozen signal-time sector label — GICS reclassifications are historically non-PIT in many stores; this disclosure confirms the sector label is the replay-frozen signal-time value (already implied by "features frozen to replay columns"), and any post-signal GICS reclassification that silently re-pools cohorts would constitute a matching-key leak.
- P2.2 candidate list: all DEMOTE-TO-PENALTY and FLIP verdicts with full evidence table, formatted as recommendation entries for Fable review.
- BH family audit: m (registered before run), raw p-values sorted, q-values, rejection threshold.

---

## §8 status row (to be filled post-run)

| date | wave | status | notes | PR |
|------|------|--------|-------|-----|
| (pending) | P1.2 | DRAFT | PREREG registered 2026-07-04; awaiting P0 golden test + PIT audit | — |
