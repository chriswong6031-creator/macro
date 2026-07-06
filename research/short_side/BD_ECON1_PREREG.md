# BD-ECON-1 — Avoided-Loss / Missed-Upside Counterfactual (PRE-REGISTRATION)

**Author:** Fable (orchestrating session), 2026-07-06
**Status:** pre-registered BEFORE the harness exists or any overlap is computed. Thresholds FROZEN; amendments require a dated entry below, committed before the amended run.
**Governing docs:** `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md`; `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md` (RUL-U3); `research/short_side/BD_PHASE0_PREREG.md` (parent tape).
**Contamination stamp:** `derived_from_surface: bd_phase0` — this study is a second look at the Phase-0 tape and its report is itself a contamination surface for any later prereg on these tapes.
**Budget semantics (red-team §2.5.8):** `TrialLedger.log_declared_budget` keeps a per-family **max()**, not a sum — this study's declared 6 is a within-study BH floor, and the family's declared budget does NOT accumulate cross-study multiplicity across Phase-0 / BD-AVOID-1 / this study / Phase-0b. That is acceptable only because all four are descriptive/research-only (no DSR haircut is computed). To keep the literal trail honest, the harness MUST additionally log each of the 6 verdict cells as a distinct config through the ledger so the family's `literal_n` accumulates, and every output prints both the family literal count and the max()-basis divergence note (the #1664 §0.5.6 convention).

## §0. Question

The Phase-0 tape says BD-2/BD-3 events mark bad long conditions in general. This study prices the avoid lens where it would actually bite: **production board fires that occurred inside an active BD avoid window.** If the board had skipped them, what drawdown was avoided and what upside was missed? This is retro decision-economics on already-graded history. It grants no live authority; its only consumer is the decision of which forward preregs to write.

## §1. Tapes (frozen)

- Events: `data/research/breakdown_events.parquet` (Mac-local), `is_control == False`, definitions BD-2 and BD-3 only (BD-1 parked underpowered per Phase-0 reading guide).
- Fires: `data/replay/replay_boarded.parquet` (Mac-local), `verdict_type == 'fire'`, `verdict_grade == True` (ERA-LAW cohort for absolute rates), joined on ticker.
- Outcome columns (fires): `state_8_21` / `stopped_at_8_21` for the stop endpoint; `fwd_ret_21`, `fwd_mdd_21`, `fwd_mfe_21` for economics. Censored/NaN outcome rows are counted and printed, never silently dropped.
- Vintage stamp mandatory on the summary; survivorship stamps inherited from both parents.

## §2. Flagging rule (frozen)

A fire is **flagged** by definition D ∈ {BD-2, BD-3} iff the same ticker has a D event (episode-collapsed, per the Phase-0 tape) with `event_date < signal_date ≤ event_date + 21 trading bars` on the massive plane calendar. **Builder note:** `event_date` is stored as a string in the tape — convert both dates to the trading-bar calendar; never diff calendar days. Fires with `signal_date ≤ event_date` are never flagged — this excludes BD-2's generating fire by construction (it always predates the event). A fire may be flagged by both definitions; it enters each definition's contrast independently and the overlap count is printed.

**Confound structure (frozen rationale):** BD-2 conditions on a recent same-ticker stopped fire *by construction* (its events derive from `state_8_21=='STOPPED'` fires), so a naive C1 contrast partly measures "re-fire after recent damage" — hence C3. BD-3 does NOT condition on a prior stop (a red-team data check found only ~41% of BD-3-flagged fires have a recent stopped fire), so C2 stands without a recent-stop control; its confound exposure is limited and is noted, not modeled.

**Recent-stop cohort (for C3):** an unflagged fire is in the recent-stop cohort iff the same ticker has a fire with `state_8_21 == 'STOPPED'` whose stop was reached within the trailing 21 bars of `signal_date`, and the ticker has NO active BD-2 window at `signal_date`.

## §3. Pre-declared contrasts and budget (frozen)

`TrialLedger.log_declared_budget(6, family='short_side')` BEFORE the run. Three contrasts × two co-endpoints = 6 cells; BH q = 0.10 within this declared set; the family's cumulative trial count is printed in every output.

| Contrast | Arms |
|---|---|
| C1 | BD-2-flagged fires vs all unflagged fires |
| C2 | BD-3-flagged fires vs all unflagged fires |
| C3 (co-primary; the report LEADS with this) | BD-2-flagged fires vs recent-stop-without-BD unflagged fires — the BD-2 increment over generic post-stop damage. A C1 delta that vanishes in C3 means BD-2 adds nothing beyond "the name just stopped"; that null is a first-class printed outcome. |

Endpoints per contrast: (a) stop-rate delta at h21 (`state_8_21 == 'STOPPED'` share), (b) mean `fwd_ret_21` delta (the economics endpoint). Point estimates with 95% CIs.

**Inference (frozen):** two-way cluster bootstrap — resample calendar months (blocks) then tickers within resampled blocks, 2,000 draws, percentile CIs. Sensitivity printed: per-ticker jackknife of each delta. Splits by year and `tier_cascade` are DESCRIPTIVE multiplicity, declared here, not verdict cells (WAIT-GRID-1 precedent).

## §4. Economics block (frozen; arithmetic on the flagged cohort — no new contrasts)

Per definition: (a) **avoided drawdown**: distribution (mean/median/p90) of `fwd_mdd_21` among flagged fires that stopped; (b) **missed upside**: distribution of `fwd_ret_21` and `fwd_mfe_21` among flagged fires that ended CLEAN — printed with equal prominence per RUL-N6 (symmetric-cost law); (c) **skip-policy net read**: mean `fwd_ret_21`(unflagged) − mean `fwd_ret_21`(flagged) per fire, re-presenting the already-budgeted endpoint-(b) CI of the corresponding contrast — the builder must NOT compute a fresh unbudgeted inferential test here; (d) **re-entry quality (descriptive)**: for each flagged fire, the `state_8_21` distribution of the next unflagged fire on the same ticker within 63 bars.

## §5. Floors and branches (frozen)

Per definition: ≥300 flagged fires AND ≥100 distinct contributing BD episodes, printed BEFORE any statistic. Miss → **P0-DEFER** for that definition: counts + arrival note printed, no statistics, come-back registered. C3 additionally requires ≥300 recent-stop cohort fires. Pre-committed readings: DETERIORATION-CONFIRMED (stop-rate delta > 0, CI excl. 0, both endpoints directionally consistent) → informs (does not auto-write) a forward skip-prereg, which per RUL-U4 must carry a compensating gate ≥8pp; INCREMENT-NULL (C1 real, C3 ~0) → BD-2's board value is redundant with recent-stop; print and stand down; NULL/REVERSED → printed; the avoid lens does not transfer to board fires at 21d.

## §6. What this does NOT show

No live tradability claim; no forward verdict (BD-AVOID-1 owns the forward question); no short-side claim of any kind; no per-name signal; nothing feeds any board, gate, chip, alert, or score. The word "validated" appears nowhere.

## Amendments

- **2026-07-06 (pre-commit disclosure, logged per RUL-P3 spirit):** after this prereg was drafted but before commit, the orchestrator ran a coarse feasibility join (calendar-day ±30d approximation, no clustering, no exclusions) solely to verify the §5 floors would not insta-DEFER. It confirmed floors are comfortably met (BD-2 ≈ 24.7k flagged fires / ≈7.1k episodes; BD-3 ≈ 3.4k / ≈1.1k) and incidentally revealed coarse pooled stop rates (flagged ≈39.2%/42.7% vs ≈38.3% all-fires baseline — note that baseline includes flagged fires and is not the registered contrast). **No numeric gate, endpoint, floor, or contrast in this prereg was changed in response** — the document above is as drafted before the peek, except this note. The peek is disclosed as a contamination event: readers of the eventual report should know the orchestrator had seen approximate magnitudes at registration time. Its substantive implication (board fires are pre-filtered entries, so the flag's increment may be far smaller than raw event-level gaps) was already the design rationale for co-primary C3.
