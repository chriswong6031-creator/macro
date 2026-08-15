---
workstream: WS:LIVE-ENTRY-RADAR
session: live-entry-radar-w3-589b54
model: fable
ended_because: complete

mission: >
  W3 / PR-3: exact C1–C5 specification lock (contract §18 A5, appended pre-outcome
  as the first branch commit) + implementation of the five challenger DetectorSpecs
  with the PIT-1..26 mutation battery. F1 stays reserved. No W4 live loop, no W5
  outcome read, no durable writer, no Detector Score. STOP after W3.

state_before: >
  W2 merged (#5698, cf4134feaa99) but recorded in_progress in the workstream
  (reconciled here from merged evidence, first commit). No competing W3 PR at
  claim time. Main red on churning unrelated guard tests (paywall, system-map
  renderer, script pinning, curated scopes) — attributed by test name, none in
  Radar's blast radius; the curated-scope red was additionally proven pre-existing
  at the branch base (identical ledger_lane coverage at base and HEAD).

changed:
  - path: research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md
    what: "§18 A5 (append-only, committed BEFORE any implementation or outcome
      reading; explicit no-results-seen statement): A5.0 shared reading object /
      ATR law / basis boundary / correction protocol; A5.1 provisional-1D + 5-min
      sampling law; A5.2 C1 (first arm IS candidate); A5.3 C2 (exactly six
      variants, no K<20 at the turn); A5.4 C3 (confirmed-daily arm + completed
      session-open-anchored 4H grid); A5.5 C4 (stratification-only, absolute
      anchor); A5.6 C5 (W2 watch-event binding by event_id, signal_known_ts
      knowability); A5.7 no new horizons; A5.8 event-family mapping."
  - path: engine/entry_radar/ (indicator_core, readings, challengers, four_hour, c5_adapter; detectors + entry_events + __init__ extended)
    what: "One pinned canon indicator family behind a Radar-owned interface
      (true-range Wilder ATR14, PIT-shifted); the ephemeral
      mastermind.entry_detector_reading.v1 with the structural null law
      (unavailable/stale ⇒ condition_met None) and all-false authority; pure
      C1/C2/C4 constructions on the 5-min sampled provisional path; RTH 4H grid
      (clipped tail, early close, extended-hours excluded) + C3 with the §10
      15-session arm expiry; C5 binding that references preserved W2 watch events
      without duplication or mutation; three Radar-native event families under an
      era fence (C4 has none and cannot mint, refused at two independent doors)."
  - path: tests/ (six new suites + fixtures) and .github/ci/legacy-jobs.yml
    what: "PIT-1..26 as named non-vacuous mutation tests (controls prove each
      mutation is caught); synthetic fixtures by K-inversion on real NYSE session
      dates with machine-readable provenance and the committed generator as
      receipt; 675 passing on the wired 11-suite CI line (401 W3). Two W2 pins
      lawfully updated (registry-size → G0-identity; family-list extension); G0's
      frozen hash literal untouched."
  - path: research/live_entry_radar/W3_REVIEW_DISPOSITIONS.md
    what: "Independent fresh-context Opus adversarial review (30-item attack
      list): 15 reproduced findings (1 BLOCKER-class, 8 MAJOR, 6 MINOR), all
      adjudicated and fixed per ruling with named test_W3_<n>_* regressions, then
      re-verified DEAD in a narrow round 2. Full table + judgment-call verdicts +
      clean surfaces + spec-hash record."

prs: [5724]

verified:
  - claim: "The exact CI line passes: 675 tests across the 11 entry-radar suites."
    command: "python3 -m pytest tests/test_entry_radar_w1.py tests/test_entry_radar_producers.py tests/test_entry_radar_g0_parity.py tests/test_entry_radar_events.py tests/test_entry_radar_w2_guards.py tests/test_entry_radar_w3_*.py -q"
    result: "675 passed (post-fix; pre-fix baseline was 625)"
  - claim: "Prophet non-interference is mechanical and clean."
    command: "git diff --stat origin/main..HEAD -- engine/entry_signal.py engine/signal_gate.py engine/confluence_tiers.py engine/signal_quality.py 'engine/prophet_*.py' engine/washout_turn.py engine/mtf_upturn.py engine/technicals.py"
    result: "empty; AST import fence extended to W3 modules and green"
  - claim: "C1–C5 registered with stable spec hashes; F1 refused."
    command: "python3 -c 'from engine.entry_radar.detectors import DETECTORS, get_spec' (see dispositions doc for the hash table)"
    result: "C1 f0bbd6cf3a6e2339 · C2 d8ba60a25cfa7400 · C3 d54dc1e55c4261c8 · C4 dce21ac680233ee2 · C5 13dec66345a0376c · G0 9be89a8acc8b905c unchanged; get_spec('F1_FUSION') raises NotYetSpecified"
  - claim: "Every BLOCKER/MAJOR review finding reproduced before fixing and re-verified dead after."
    command: "reviewer round-1 probes (scratchpad review/) + round-2 re-runs; builder receipts in the PR"
    result: "W3-1..W3-9 DEAD; W3-10..15 verified as ruled"

unverified:
  - claim: "The 4H grid against REAL vendor minute aggregates (fixtures are synthetic
      by construction, marked so)."
    what_would_verify: "PR-4's live lane or an operator-authorized bounded vendor
      smoke (deliberately not run here: no vendor fetch in W3, CI stays offline)."

unresolved:
  - "Main was red on churning unrelated guard tests during this session; the
    curated-scope red (ledger_lane coverage of biocatalyst-history /
    unrun-government-revenue-grader) pre-exists this branch and is owned
    elsewhere — do not steal the heal from a Radar PR."

next_actions:
  - "W4 (PR-4): VPS 5-min evaluator, nightly threshold-inversion packs, raw-quote
    basis audit, state-transition loop, spool, liveness. W3 deliberately left
    run_c1/run_c2 single-episode-per-path; rearm_eligible is the exported §10
    primitive for PR-4 to wire."
  - "W5 (PR-5): replay + forward evidence; the PIT substrate is frozen under §18
    A5 with the hashes above; the look ledger and prereg-hash discipline of §11
    engage there."

do_not_redo:
  - "Do not re-run the W3 review cycles — 15 findings adjudicated, fixed, and
    re-verified; receipts in research/live_entry_radar/W3_REVIEW_DISPOSITIONS.md
    and the named test_W3_<n>_* regressions."
  - "Do not 'fix' C3 by re-requiring the washout at the turn — REJECTED ruling
    (rebuilds must-still-be-oversold); the lawful staleness instrument is the §10
    15-session arm expiry, already wired."
  - "Do not flatten C1_SPEC's nested rearm_law block — the values are hashed and
    pinned by named-key tests; nesting is cosmetic."
  - "Do not treat the C2 pre-arm encoding change (condition_met=False +
    eligible/pre_arm features) as a golden regeneration — it is the adjudicated
    W3-8 harmonization with C3's encoding, TRUTH-CHANGE-noted in three tests."
  - "Do not add a seventh C2 variant, a variant combination, or a C1_CONFIRMED
    arena detector — contract §18 A5.2/A5.3."

danger_areas:
  - "Spec hashes are now PUBLISHED (this PR + return packet): any future change to
    a firing-relevant constant is a new detector VERSION, never an in-place edit."
  - "The basis gate (W3-1) makes raw-basis tapes refuse wholesale — a W4 live lane
    must pass its own basis audit BEFORE feeding the engine, not strip the gate."
  - "engine.stock_technicals transitively loads engine.technicals at module scope
    (disclosed in indicator_core's docstring); the direct-import fence and the
    ATR byte-equality pin are the guards — do not 'clean this up' by re-implementing
    ATR locally (that is the third-implementation drift §4 forbids)."
---
