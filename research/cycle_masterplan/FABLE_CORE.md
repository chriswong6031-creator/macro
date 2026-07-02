# Fable core sections (pre-authored while design fleet runs)

## THE DOCTRINE — what "institutional grade" actually means here

Ten operating principles. Every wave in this masterplan either enforces one of these or it doesn't ship.

1. **The engine owns every plotted number.** Narrative may annotate; it may never set a position, a phase,
   a turn date, or a cone. Enforced by a build-time assertion, not by convention.
2. **Every claim carries its evidence class.** MEASURED (graded, n shown, CI shown) / EXPERIMENTAL
   (accruing, registered in the Experiments tracker with a come-back date) / STRUCTURAL (frame, not
   forecast — falsifier-monitored, never graded) / OPINION (dated, TTL'd, staleness-badged). The UI renders
   the class. Nothing ships unclassified.
3. **A probability is a promise.** Anything expressed as odds or a cone gets reliability-tracked (Brier vs
   base rate, coverage vs nominal). If we won't grade it, we don't express it as a probability.
4. **Calibration binds or it lies.** A calibration artifact that doesn't feed back into the shipped score
   is worse than no calibration — it's a rigor costume. Scores, tier cuts, and cone widths are *fit*,
   versioned, and refreshed on schedule.
5. **"Validated" is a file, not a word.** The label requires a stored verdict artifact (backtest JSON with
   window, n_eff, CI, and the exact claim tested) — same pattern as thematic_rotation_phase0.json.
6. **One ontology, compiled.** Position/phase/turn are defined once in Python and *generated* into JS.
   Two pages can disagree about the world only if the world's data disagrees, never about definitions.
7. **Point-in-time or it didn't happen.** Every stamp is reconstructable from tape ≤ t. Mutable state
   (membership, narratives, live scrapes) is either frozen at stamp time (hash) or excluded from grading.
8. **Small n is a disclosure, not a shame.** Pool across the cross-section (hierarchical shrinkage,
   hazard pooling) to earn n where possible; where impossible (18-yr cycles), say "frame" and monitor
   falsifiers instead of pretending to grade.
9. **Risk levers are not return levers.** Gates validated only for drawdown reduction size positions;
   they never vote direction. Mislabeling a vol-damper as alpha was one of the audit's deepest sins.
10. **Evergreen means zero hand-edits to stay true.** Wall-clock TODAY, auto-refreshed reads, TTL'd prose,
    tripwires that fire alerts. A page that requires a human to remain honest will eventually be dishonest.

## THE COLLAPSE MAP — 89 findings → 7 engineered systems

The audit's findings are not 89 independent bugs; they are symptoms of seven missing systems. Build the
system, and its findings fall as a group.

| # | System (what we build) | Kills findings (groups) | Core theses |
|---|---|---|---|
| S1 | **The Ontology Contract** (`engine/cycle_ontology.py` → generated JS; position semantic, phase crosswalk, turn primitive, clock-reconciliation state machine) | all cross-page position/phase/turn incompatibilities; contradictory-card findings; 4-detector fragmentation | T2 |
| S2 | **The Data Substrate Contract** (dual-basis store, FX decomposition, basis-matched benchmarks, frozen basket levels + membership hashes) | every TR-mislabeled-as-price finding; FX conflation; grader benchmark bias; basket survivorship/mutable-history leaks | T5 |
| S3 | **The Measurement Engine** (PIT backfill; `grading_stats` shared library; turn precision/recall; cone coverage; reliability curves; binding calibration) | empty-grader findings; no-CI/tiny-n/overlapping-window findings; decorative-calibration findings; inverted LADDER_SCORE | T4, N3 |
| S4 | **The Prediction Layer** (pooled discrete-time hazard model → calibrated cones; shrunken conditional forward-return cells; regime-prior service) | median-half-cycle projection findings; magic-cone findings; hand-typed regime blocks; FWER-failing pathway pretense | T3 |
| S5 | **The Flagship Re-platform** (proxy registry; monthly kernel; MEASURED/STRUCTURAL two-tier; engine-backed cycle.html/markets.html; markets→country consolidation) | every hand-curated flagship finding; frozen-TODAY; drawdown-exponential position; fake convergence bands; duplicate-coverage contradiction | T1, N1 |
| S6 | **The Honesty Surface** (narrative TTL/staleness badges; falsifier tripwire compiler + alerting; evidence-class labeling; build-time narrative-vs-engine assertions) | decorative-falsifier findings; stale-narrative-overrides-engine findings; "Live read" mislabeling | T6 |
| S7 | **The Interaction Layer** (measured lead-lag phase-0 → synchronization statistic → graded cross-asset conditioning, ONLY if phase-0 passes) | isolated-clocks finding; fake synchronized-inflection bands | T7 |

Dependency spine: **S2 → S1 → S3 → S4 → (S5, S6) → S7.** Substrate before ontology (turns must be
detected on the right basis before we freeze their IDs), ontology before measurement (we grade canonical
objects, not five vocabularies), measurement before prediction (the hazard model trains on backfilled
turns), and interaction dead last (it needs everything else's outputs and may be stopped by its own
phase-0 gate).

## WHY THIS RAISES DIRECTIONAL CAPACITY (the causal chain, stated falsifiably)

1. Correct substrate (S2) → turn dates and amplitudes stop being artifacts → every downstream feature is
   cleaner. *Testable: re-detected turns vs old turns diverge most for high-yield sectors; failed-cycle
   trigger rate changes measurably.*
2. One ontology (S1) → phase/position become comparable across ~160 series → cross-sectional pooling is
   legitimate → small-n stops being fatal. *Testable: confirmed-peak position distribution tightens vs the
   audit's 17.6–99.7 spread.*
3. Backfill (S3) → hundreds of matured PIT windows on day one → we finally *know* which states/phases carry
   edge, and the score starts obeying the evidence instead of inverting it. *Testable: n_matured goes from
   0 to >500; LADDER_SCORE refit changes at least the DECLINE/FRESH BUY ordering.*
4. Hazard model (S4) → projections become calibrated probabilities with honest cones → the platform makes
   its first gradeable *forecasts* (not descriptions). *Testable: OOS Brier beats the constant-hazard
   (median-half-cycle) baseline; cone coverage within ±10pts of nominal.*
5. Two-tier honesty (S5/S6) → the user can finally tell measurement from opinion → trust concentrates where
   evidence is, and the STRUCTURAL frames stop contaminating the MEASURED track record.
6. Interaction (S7) → *if and only if* lead-lag exists, conditioning on leader turns lifts follower hazard
   accuracy. *Pre-registered gate: ≥X% Brier improvement on followers, else we ship dispersion stats and stop.*

## DELEGATION PLAYBOOK (how wave sub-sessions run)

- **Every wave = one sub-session/agent, one branch off main, one PR, squash-merged same day.** No wave
  spans branches; no branch outlives its day (house PR-conflict rule).
- **Tiering:** Opus for judgment-heavy waves (ontology semantics, hazard-model spec, calibration binding);
  Sonnet for well-specified implementation (collectors, graders adopting grading_stats, UI wiring, i18n
  dual-span chores); Haiku for pure collection (FRED series adds, registry seeds, data dumps). The wave
  table names the tier; the sub-session prompt links the pillar design doc section.
- **Acceptance gates are executable.** Each wave lists commands (pytest targets, audit scripts, expected
  artifact diffs). A wave without a runnable gate doesn't ship.
- **Measurement waves register in the admin Experiments tracker** with come-back dates (N4) so accruals
  are tracked, not forgotten.
- **Verification against main, always** (stale-worktree house rule); builders run page-scoped, never the
  full 67-min render, unless the wave explicitly touches shared assets.
