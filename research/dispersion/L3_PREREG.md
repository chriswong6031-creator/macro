# DISP-GATE-1: L3 Dispersion Regime — Shadow-Ladder Pre-Registration

**Date frozen:** 2026-07-05
**Status:** pre-registered BEFORE screening any fires against the dispersion regime.
Thresholds FROZEN; changing them after seeing results is p-hacking.

**Program authority:** NW Rails program §5 (research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md)

**Registration note:** The rule-experiment registry entry (data/rule_experiments/) requires
the PR-1 R1 governor CLI, which ships in a separate wave. This prereg doc states the
design intent, basis, and frozen gates so that any future run is bound by what is written
here. The registry entry will be created via `python -m scripts.register_experiment
DISP-GATE-1` before any run, as required by the R1 governor law.

---

## Question (shadow ladder — descriptive first)

**DISP-GATE-1:** Conditioning entry TRUST (not sizing) on lean_out regimes — do fires
opened when the dispersion regime is `lean_out` (low cross-sectional dispersion / high
pairwise correlation, macro-driven tape) show worse stop-5 rate and dead-money fraction
than fires opened in `lean_in` (high dispersion, selection pays)?

Outcome metric: at 21d time-exit, compare (a) `stop5` fraction (fires that drew down
≥5% from entry at any point in the 21d window) and (b) `dead_money` fraction (fires
with |ret_21d| < 2% — neither a gain nor a meaningful loss — a tape parking the name).
Primary comparison: `lean_out` cohort vs `lean_in` cohort. `neutral` cohort reported
descriptively as a third arm.

This is the shadow-ladder question for L3. A future verdict batch — using the
descriptive readout + episode-clustered bootstrap — would gate any `lean_out` de-trust
adjustment. That gate is NOT defined in this prereg; the prereg fixes design obligations
for the study that produces the descriptive readout.

---

## Universe and cohort

- Universe: replay_boarded fire tickers ∪ current US board universe.
- Fire population: fires from the signal ledger with a `fire_date` AND a resolvable
  regime state at/before `fire_date` (see Design obligation 2 below).
- Minimum n per arm: 25 episode-clusters (not raw fires) before any distributional
  statement. Arms with <25 clusters are reported as "sparse — descriptive only, no
  bootstrap CIs."

---

## Design obligation 1: basis reconciliation

`engine/dispersion.assess()` uses an **expanding-window percentile** — `(h <= h.iloc[-1]).mean()`
where `h` is the rolling-21d-mean CSD history since inception. This means the percentile
basis is non-stationary: an identical absolute CSD level maps to different pctile values
at different points in history (as the denominator grows and the empirical distribution
shifts).

The study MUST reconstruct the LIVE expanding-window basis as the PRIMARY assignment
(matching what the artifact actually produced at each date) and also run a
**trailing-252d sensitivity** (assign regime using a fixed 252-trading-day rolling
window for the percentile). Both assignments are printed. If regime assignments differ
materially across the two bases (>15% of fires flip state), the report flags
NON-STATIONARITY and the study proceeds descriptively on the primary basis only —
no promotion gate is triggered until a stationary basis is evaluated.

The expanding-window basis is the PIT-correct one (what operators saw at fire date);
the trailing-252d sensitivity is the stability check.

---

## Design obligation 2: regime-as-outcome confound control

Cross-sectional dispersion / pairwise correlation regimes correlate mechanically with
market drawdown regimes: low dispersion (lean_out) tends to coincide with macro-stress
tapes that hurt ALL stocks. A naive comparison "lean_out fires do worse" could
entirely re-discover that stressed tapes are stressed, not that lean_out per se hurts
selection quality.

Mandatory control: the study registers a **contemporaneous-market-drawdown covariate**
at fire_date. Candidate: SPY 21d return at fire_date (a proxy for the tape backdrop).
The primary analysis reports:
1. Raw comparison: stop5/dead_money by regime state (lean_in / neutral / lean_out).
2. Covariate-split comparison: within each drawdown tercile (SPY_21d_ret < -5%; -5%
   to +5%; >+5%), stop5/dead_money by regime state.
3. If the lean_out vs lean_in gap narrows substantially (>50% absorbed) in the
   covariate-split, the study concludes: "dispersion regime is a proxy for tape
   backdrop; selection trust adjustment is NOT supported as an independent mechanism."

Regime is measured at/before fire_date only (no lookahead). If the artifact does not
have a PIT state for fire_date (because the artifact postdates the fire), that fire is
excluded with explicit count noted.

---

## Frozen PASS thresholds (for a future verdict batch)

These thresholds are frozen here so that no post-hoc adjustment is possible. The
descriptive readout must be produced BEFORE any gate is evaluated; the gate is evaluated
on a SEPARATE registered run citing this prereg by exp_id.

A future verdict PASSES (enabling lean_out entry-trust flag display) ONLY if ALL hold:
1. n_episode_clusters(lean_out) ≥ 25 AND n_episode_clusters(lean_in) ≥ 25.
2. lean_out stop5 rate EXCEEDS lean_in stop5 rate by ≥8pp (absolute, not relative).
3. The gap is NOT absorbed by the covariate control (covariate-split check: gap
   persists ≥5pp in at least 2 of 3 drawdown terciles).
4. Episode-clustered bootstrap 90% CI for the stop5 gap excludes 0 (one-sided,
   H1: lean_out > lean_in).
5. dead_money fraction shows the same direction (lean_out > lean_in) — sign check only,
   no numeric threshold.

PASS = 1 ∧ 2 ∧ 3 ∧ 4 ∧ 5. A PASS enables a display flag on the chip (not a sizing
change — gross_mult_live stays 1.0 indefinitely per the US_BOARD_MEASUREMENT §Study 3
hard constraint).

---

## Standing notes

- The word "validated" may not appear in any output from the harness (epistemics house
  law; check_validated_claims.py CI guard; research/*.md files are not CI-scanned but
  this is discipline, not automation).
- Nulls are printed, not hidden. If n floors are not met, report the counts and state
  DEFER explicitly.
- Episode-clustering: fires cluster in calendar time (tapes create correlated outcomes).
  Bootstrap resamples episode clusters (contiguous blocks within ±30d), not individual
  fires.
- The harness has not been built yet. This prereg fixes the design. Harness build is
  a future Sonnet wave; Opus reviews the stats faithfulness.
- HARD CONSTRAINT: `gross_mult_live` is and remains 1.0 regardless of PASS/FAIL
  outcome. This study can only enable a display flag; sizing is governed by a separate
  measured selection-IR edge study (US_BOARD_MEASUREMENT §Study 3 precedent).

---

## Amendment L3-A1 (2026-07-07) — DT-R14 compliance + cluster-definition resolution

**Authority:** Ruling DT-R14 + research/TIME_CONFOUND_EXPOSURE_AUDIT.md §4, finding DG-1.
**Scope discipline:** amended BEFORE the verdict harness has been built or any verdict
batch has run against this prereg (see Standing Notes: "The harness has not been built
yet"). Frozen economic thresholds are untouched (criteria 1-3 and 5, the 8pp/5pp bars);
only the inference machinery of criterion 4 and the cluster definition are amended —
the same events-frozen/inference-only pattern as the DT-W1a repair.

1. **Criterion 4 is amended to:** "Month-block (or global ±30d contiguous tape-time
   block) bootstrap 90% CI for the stop5 gap excludes 0 (one-sided, H1: lean_out >
   lean_in), computed on within-period cross-sectionally demeaned outcomes; all fires
   within a drawn calendar block move together." A per-ticker `episode_id` bootstrap
   does NOT satisfy this criterion.
2. **Cluster definition resolved:** clusters = GLOBAL contiguous ±30d tape-time blocks
   (per the Standing Note above), NOT per-ticker `episode_id`s. The n≥25 floor in
   criterion 1 counts these blocks per arm. DISP_GATE_1_REPORT.md §9 measured
   lean_in=17 / lean_out=20 such blocks on the 2022-2025 tape — below floor — so the
   state as currently measured is DEFER on floors, consistent with the shipped
   DISP-GATE-1 outcome.
3. **Pre-declared DEFERRED/UNDERPOWERED path (per DT-R14):** if block floors are unmet,
   the verdict is DEFER (accrue more tape), never FAIL — a low-power null must be
   distinguishable from a refutation.
4. The "×2-replicated" language in DISP_GATE_1_REPORT.md §9 is a sign-and-flip-rate
   concordance across two panels, not a replicated inferential result; it must not be
   cited as corroboration in any future verdict batch.
