---
key: FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION
question: >
  Of the four preregistered descriptive-normalization candidates (M0 incumbent slope_z,
  M1 winsorized, M2 median/MAD, M3 percentile->probit) evaluated in
  reports/flow_observatory_w5_methods.{md,json} against the frozen
  research/flow_observatory/W5_PREREG.md §5 decision rule, which method and which state
  thresholds (tau velocity cutoff, beta breadth-tilt band) should Flow Observatory V2 ship
  for the themes, names, and southbound lenses?
answer: >
  Themes: M0 stays; thresholds recalibrate to tau=0.75, beta=30 (in the honest-neutral
  band, flip strictly improves over the incumbent — not a tie). Names: M0 stays;
  thresholds recalibrate to tau=0.3 (beta=15, no production tilt-gauge consumer for names
  yet) via the frozen lexicographic rule's mechanical completion (no grid point sits
  genuinely in-band, so nearest-band applies; tau=0.3/0.4 tie on band distance and the tie
  breaks on flip rate). Southbound: M1 (winsorized) is ADOPTED for the aggregate path
  (M0-vs-M1 state disagreement measured 4.49%, under the 20% HOLD sanity bound), but its
  own threshold re-sweep excludes every candidate tau (0% held-out "above norm" reach at
  every grid point, a current-regime degeneracy) and falls back to the incumbent tau=0.5,
  numerically unchanged.
rationale: >
  research/flow_observatory/W5_PREREG.md froze the evaluation metrics, the §4 threshold
  sweep procedure, and the §5 decision rule BEFORE the harness ran
  (scripts/research_flow_observatory_methods.py), so no candidate/threshold choice could
  be reverse-fit to a preferred outcome. For themes and names, none of M1/M2/M3 satisfied
  §5's adoption bar (>=30% outlier/quiet improvement AND flip rate not >10% worse AND
  concordance >=0.8 AND no degeneracy alarm) against M0 — see
  reports/flow_observatory_w5_methods.md's §5 condition table — so M0 remained the method
  and only thresholds were open to recalibration per §4. For southbound, M1 cleared a
  sanity bound designed to fail toward the incumbent (a >20% M0-vs-M1 state-disagreement
  share would have forced a HOLD; the measured 4.49% did not), so M1 was adopted; its
  threshold re-sweep then hit a genuine current-regime degeneracy (every candidate tau's
  held-out reach for "above norm" was 0% in the last 60 sessions) which the frozen
  all-excluded fallback resolves honestly by keeping the incumbent tau rather than picking
  an unreachable "improvement". Full arithmetic for every ruling is in
  reports/flow_observatory_w5_methods.md §6 Adjudication.
alternatives:
  - option: Adopt M1/M2/M3 for themes or names
    why_not: >
      None cleared the frozen §5 adoption bar against M0 on any lens — M1's outlier/quiet
      improvement never reached 30%, M2/M3 failed on flip rate and/or concordance, and M3
      additionally tripped the quiet-series degeneracy alarm on every lens (max|v| > 1.5).
  - option: Pick the naive unfiltered threshold-sweep winner for southbound (tau=1.0)
    why_not: >
      That winner zeroed held-out "above norm" reach entirely — a construction that can
      never again print an inflow verdict in the drift-forward window is a degeneracy, not
      an improvement, which is exactly why §4's re-sweep for southbound carries the <2%
      held-out-reach exclusion the ruling invokes by name.
  - option: HOLD southbound on M0 because SOME degeneracy was found
    why_not: >
      The degeneracy is on the THRESHOLD axis (which tau), not the METHOD axis (M0 vs M1).
      The M0-vs-M1 state-disagreement sanity bound (the only gate that can force a method
      HOLD) cleared cleanly at 4.49% <= 20%; conflating a threshold-side fallback with a
      method-side HOLD would misreport what actually happened.
evidence:
  - "research/flow_observatory/W5_PREREG.md (frozen §4/§5 procedure, committed 820c8813
    before any evaluation run)"
  - "reports/flow_observatory_w5_methods.md and .json (harness report, generated at head
    3786b2399c11; §6 Adjudication section added by this record's own commission with full
    arithmetic and grid tables)"
  - "PR #6808 comment 5530582923 — https://github.com/mastermindx-market-intelligence/macro/pull/6808#issuecomment-5530582923
    (verbatim adjudication ruling this record implements)"
  - "tests/test_flow_observatory_methods.py::test_names_mechanical_threshold_selection_matches_the_adjudicated_tau_beta,
    ::test_themes_adjudicated_tau_beta_is_the_unique_in_band_min_flip_winner,
    ::test_southbound_m0_vs_m1_state_disagreement_within_the_hold_bound,
    ::test_southbound_every_tau_is_held_out_unreachable_so_the_incumbent_stays (arithmetic
    pinned against the committed report / recomputed from the harness's own functions)"
  - "tests/test_flow_velocity.py::test_w5_adjudicated_constants_are_pinned and siblings
    (production constants, breadth-threshold effect, boundary determinism, M0/M1
    equivalence on non-clipping data)"
  - "engine/flow_velocity.py (_NAMES_VIN/_VOUT, _THEMES_VIN/_VOUT, _THEMES_TILT_BETA,
    _winsorize_causal, _kinetics(winsorize=...)) and
    engine/flow_observatory/contract.py (THEMES_REL_THRESH, NAMES_REL_THRESH,
    SOUTHBOUND_REL_THRESH) — the applied constants"
affects: ["WS:FLOW-OBSERVATORY-V2", "engine/flow_velocity.py", "engine/flow_observatory/contract.py",
         "reports/flow_observatory_w5_methods.md", "reports/flow_observatory_w5_methods.json",
         "templates/flow_velocity.html.j2", "site/flow_velocity.html", "site/flowdata/desk.json",
         "docs/site_semantics/china.md"]
confidence: medium
reversibility: easy
decided_by: coo-fable
decided_at: 2026-09-03
superseded_by: DEC:FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION-R2
---

## Grounds

The W5 wave exists to replace an ad hoc, never-recalibrated 0.5σ / 25pp threshold pair
(and an unexamined choice of normalization method) with a preregistered, evaluated
selection. Freezing the candidates, metrics, sweep procedure, and decision rule BEFORE
the harness ran (research/flow_observatory/W5_PREREG.md, committed at 820c8813) is what
makes this record's numbers non-negotiable inputs rather than post-hoc justifications —
the harness reported facts only (`reports/flow_observatory_w5_methods.md`: "Report
only... Selection is reserved for the Fable principal"), and this record is that
reserved adjudication, applied.

The southbound HOLD sanity bound deserves a specific note: it is constructed so that ANY
ambiguity resolves toward the incumbent (a state-disagreement share too close to call
would exceed 20% and force M0 to stay), so a clean pass at 4.49% is genuine evidence the
winsorized variant behaves almost identically to the incumbent on this series' history —
which is also why its own threshold re-sweep landing back on tau=0.5 is not a contradiction:
the method changed (a real, if small, difference in how outliers are handled) while the
calibrated cutoff for "how big a move counts" did not need to move at all.

## What would reopen this

- A future W6+ wave re-running the same frozen harness on a materially longer history (the
  metric 7 revision-ledger deviation notes `data/flow_observatory/observations.parquet`
  was not yet materialized when this ran) could change any of the three arithmetic
  outcomes — re-run the harness and re-adjudicate against the SAME frozen §5 rule rather
  than hand-editing thresholds.
- If a future wave adds a genuine names-lens breadth-tilt gauge to production (none exists
  today — flow_breadth only counts `names_in`/`names_out`, it does not classify a tilt
  state for names the way it does for sectors), the names beta=15 result recorded here and
  in the report becomes directly applicable rather than disclosed-but-unused.
- A materially different current regime that restores nonzero held-out "above norm" reach
  for southbound would reopen the threshold (not method) side of the southbound ruling.
