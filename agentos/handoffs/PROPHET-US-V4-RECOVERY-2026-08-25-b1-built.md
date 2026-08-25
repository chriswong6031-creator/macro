---
workstream: WS:PROPHET-US-V4-RECOVERY
session: claude/b1-candidate-episode-20260825
model: codex
ended_because: ci_handoff
mission: >
  Build the one canonical V4-B1 candidate-episode plane, wire exactly one natural
  nightly writer with explicit CI and dataset ownership, record its settled bindings,
  and stop at BUILT_PENDING_NATURAL_ACCEPTANCE without manufacturing production data
  or releasing D5 early.
state_before: >
  A1 was accepted and B1 was dependency-ready, but no durable per-security-epoch x
  structural-anchor candidate episode plane existed. TURN WATCH, candidate snapshots,
  Doors, Radar, identity, plans, rankings, Availability, and graders had separate
  canonical ownership. D5 remained blocked behind B1 and open PR #6275 carried only
  its frozen contract.
changed:
  - path: engine/us_candidate_episode.py
    what: >
      Adds the pure immutable event/replay contract, strict validation, deterministic
      episode/projection builders, and canonical HEAD-referenced reader.
  - path: engine/us_candidate_episode_intake.py
    what: >
      Normalizes exact Data OS identity plus TURN WATCH, candidate, Doors, and Radar
      observations without granting any source new authority.
  - path: engine/us_turn_watch.py and scripts/build_turn_watch.py
    what: >
      Emits the full uncapped private TURN WATCH sidecar from the existing engine-owned
      build while preserving the capped display artifact and existing CI owner.
  - path: scripts/reconcile_us_candidate_episodes.py
    what: >
      Adds the nightly-gated sole B1 writer: read-only report/replay modes, once-read
      source receipts, immutable complete generations, and one atomic HEAD publication.
  - path: .github/workflows/daily.yml, .github/ci/legacy-jobs.yml, and config/dag.yml
    what: >
      Places one hard-failing B1 natural writer after Door emission and before every
      forward grader/W3. The step retains failure visibility but is explicitly limited
      to schedule events, so daily workflow_dispatch skips B1. It stages only
      data/us_prophet_rank/episodes, declares the exact DAG order/--nightly arguments,
      and runs the four B1 suites in
      prophet-us-context-and-grades while TURN WATCH stays in its existing owner.
  - path: config/dataset_registry.yml
    what: >
      Registers six proposed B1 input/output contracts plus the three existing produced
      inputs B1 actually loads: context-vector candidates, Door flags, and Radar forward
      events. Their incumbent owners remain explicit, event identity is event_id/content_address,
      both event and suppression lineage list every intake, and only the generation selected
      by validated HEAD.json is canonical.
  - path: tests/test_us_candidate_episode.py, tests/test_us_candidate_episode_intake.py, tests/test_us_candidate_episode_reconciler.py, tests/test_us_candidate_episode_wiring.py, tests/test_us_turn_watch.py
    what: >
      Pins event identity, PIT intake, atomic publication, natural-lane wiring,
      no-authority boundaries, uncapped sidecar production, and canonical read failures.
  - path: tests/test_dataos_registry.py and tests/test_prophet_off_engine_lane.py
    what: >
      Preserves the original ten registry contracts and four historical identity
      consumers as subsets so lawful registry expansion is not blocked; B1 exact IDs,
      fields, clocks, and new edges are independently asserted by its wiring suite.
      Expands the existing off-engine module/order/gate contract to include B1 and its
      exact DAG declaration rather than leaving live workflow drift.
  - path: agentos/decisions/DEC-PROPHET-B1-CANONICAL-EPISODE-BINDINGS.md, agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md, research/prophet_v4/CAPABILITY_LEDGER.md
    what: >
      Records R1-R5 plus atomic HEAD publication, B1 owned paths, and the bounded
      BUILT_PENDING_NATURAL_ACCEPTANCE state while preserving D5 todo/blocking prose.
verified:
  - claim: >
      Review-fix coverage demonstrated the manual-dispatch, event-identity, missing-lineage,
      and authority-fence gaps before the schedule-only and registry repairs made it green.
    command: >
      PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest
      tests/test_us_candidate_episode_wiring.py -q
    result: >
      Before the fix: 5 failed and 11 passed for the intended review gaps. After the fix:
      16 passed. Three shared pytest temporary-directory cleanup warnings were unrelated.
  - claim: >
      The B1 workflow/CI/registry tests were observed red for the missing integration
      and then green after the exact wiring and six B1 contracts were added.
    command: >
      /opt/homebrew/bin/python3.12 -m pytest
      tests/test_us_candidate_episode_wiring.py tests/test_dataos_registry.py -q
    result: >
      Initial B1 wiring run: 6 intended failures and 3 passes after correcting the
      legacy manifest loader in the new test. Final combined run: 45 passed. The only
      output was an unrelated shared pytest temporary-directory cleanup warning.
  - claim: >
      The final B1/producer suite, adjacent authority fences available in a sparse
      checkout, and structural integration all pass after the DAG amendment.
    command: >
      /opt/homebrew/bin/python3.12 -m pytest
      tests/test_us_candidate_episode.py tests/test_us_candidate_episode_intake.py
      tests/test_us_candidate_episode_reconciler.py
      tests/test_us_candidate_episode_wiring.py tests/test_us_turn_watch.py -q;
      /opt/homebrew/bin/python3.12 -m pytest tests/test_us_context_vector.py
      tests/test_us_candidate_lanes.py tests/test_entry_radar_events.py
      tests/test_stock_identity_fingerprint.py tests/test_prophet_pit_replay.py -q
      --deselect tests/test_prophet_pit_replay.py::TestDisclosedGapGuard::test_against_the_real_repo_us_2026_08_04_refuses
      --deselect tests/test_prophet_pit_replay.py::TestVerifyCollisionsAheadOfIdempotence::test_committed_legacy_augmentation_matches_immutable_root;
      /opt/homebrew/bin/python3.12 -m pytest tests/test_prophet_off_engine_lane.py
      tests/test_dataos_registry.py -q
    result: >
      164 passed; 459 passed, 1 skipped, 2 deliberately deselected sparse-only
      production-data assertions; and 73 passed. Running the adjacent command without
      deselection produced exactly those two missing-data failures and otherwise
      459 passes/1 skip; no B1 or authority-boundary failure was hidden.
  - claim: >
      The affected Data OS and nightly-DAG logical jobs, workflow parse, unrun-suite
      ownership, and trigger closure are green.
    command: >
      PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest
      tests/test_dataos_identity.py tests/test_dataos_temporal.py
      tests/test_dataos_price.py tests/test_dataos_nulls.py
      tests/test_dataos_registry.py tests/test_dataos_quality.py -q -rs;
      /opt/homebrew/bin/python3.12 -m pytest tests/test_dag_conformance.py
      tests/test_tech_lab_offrender_budget.py tests/test_nightly_timings.py
      tests/test_daily_et_gate.py tests/test_workflow_file_size.py
      tests/test_nightly_liveness.py -q; python3 scripts/check_dag_conformance.py
      --verbose; python3 scripts/check_workflow_yaml.py .github/workflows;
      python3 scripts/audit_unrun_tests.py; python3 scripts/check_ci_trigger_closure.py
    result: >
      Data OS logical job 378 passed; nightly-DAG logical job 189 passed; DAG
      conformance checked 27 lanes with 2 inherited documented SUSPECT drifts and
      zero undeclared mismatches; all 94 workflows parse; the new B1 suite is named;
      all 1,715 path-gated suites have reachable trigger closure.
  - claim: >
      The authoritative twelve-pack plan validates and maps the affected logical jobs
      without executing omitted-tree-sensitive full packs locally.
    command: >
      CI_CHANGED_FILES_JSON='<the exact eleven Task 4 paths>' python3
      scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index N
      --pack-count 12 --changed-from explicit-task4 --validate-only, for N=0..11
    result: >
      203/203 legacy jobs validated. daily.yml is a global invalidator, so all packs
      are in scope; prophet-us-context-and-grades maps to pack 2, dataos-foundation to
      pack 7, and dag-conformance to pack 10. Their exact affected commands were run
      locally above; full pack execution was intentionally not used in the sparse tree.
  - claim: >
      Fix round 1 closes the schedule, registry, lineage, recursive authority-fence, and
      TURN WATCH documentation review findings without changing B1 acceptance state.
    command: >
      PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest
      tests/test_us_candidate_episode.py tests/test_us_candidate_episode_intake.py
      tests/test_us_candidate_episode_reconciler.py tests/test_us_candidate_episode_wiring.py
      tests/test_us_turn_watch.py -q; PYTHONDONTWRITEBYTECODE=1
      /opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode_wiring.py
      tests/test_dataos_registry.py tests/test_prophet_off_engine_lane.py -q;
      python3 scripts/agentos.py validate
    result: >
      170 focused passes; 89 structural passes; Agent OS 700 records, 0 errors, and
      37 advisory/pre-existing warnings. Data OS and DAG owner commands separately
      remained green at 378 and 189 passes; all twelve validate-only packs accepted
      203/203 jobs with daily.yml correctly widening scope to all packs.
  - claim: >
      Independent Task 3 review closed every original and follow-on atomicity,
      durability, validation, retry, and provenance finding before integration began.
    command: >
      git log --oneline -- engine/us_candidate_episode.py
      scripts/reconcile_us_candidate_episodes.py tests/test_us_candidate_episode_reconciler.py;
      rg -n 'APPROVE|closed' .superpowers/sdd/2026-08-25-b1-canonical-candidate-episode/task-3-fix3-review.md
    result: >
      Final writer fix commit 0ecd1d193617 follows complete-generation fix
      cde1c285bed2 and atomic-generation fix 4535a5237309; fix-round-3 review verdict
      APPROVE with all prior findings closed.
  - claim: >
      The integration modified no tracked production data, site artifact, generated
      Agent OS view, Radar producer, ranking, plan, Availability, V3, or D5 contract file.
    command: >
      git status --short; git diff --name-only c3ba40c8ee29
    result: >
      The Task 4 boundary contains only the workflow, CI manifest, DAG declaration,
      registry, three test files, one decision, the B1 workstream, capability ledger,
      and this handoff.
      No data/ or site/ path is present; PR #6275's D5 contract files were not edited.
unverified:
  - claim: >
      The first ordinary scheduled nightly descendant publishes a valid production B1
      generation and its canonical reader resolves the same HEAD-selected bytes.
    what_would_verify: >
      After merge, wait without dispatch/rerun/replay for the next scheduled daily.yml
      descendant; pin ancestry, exact B1 step/job conclusion, HEAD/manifest/source and
      projection hashes, event/suppression counts, and a read-only canonical-loader pass.
  - claim: >
      B1 is accepted and D5 may execute.
    what_would_verify: >
      A separate acceptance records PR must adopt the complete natural evidence packet,
      mark B1 done, promote the six produced contracts honestly, and explicitly release
      D5 after reconciling open PR #6275.
unresolved:
  - "B1 is BUILT_PENDING_NATURAL_ACCEPTANCE, not accepted, live, or production-proven."
  - "D5-EARNINGS remains blocked behind B1; PR #6275 remains contract-only and was not absorbed or edited here."
  - "B2, B3, B4, A2, A3, A4, and all other V4 waves remain separate and unchanged."
next_actions:
  - "Complete review, CI, and merge of the single B1 carrier."
  - "Wait for the first ordinary scheduled daily.yml descendant; do not manually dispatch, rerun, replay, or cancel it."
  - "Return the exact natural B1 evidence packet through a records-only acceptance PR, then reconcile and execute D5."
do_not_redo:
  - "Do not create a second candidate-episode ledger, projection plane, identity adapter, structural-anchor finder, or atomic publication pointer."
  - "Do not use ticker/date, Radar runtime episode_id, a reconstructed expert tuple, or recorded_at as semantic event identity."
  - "Do not let candidates, Doors, unanchored Radar, ranking, plans, Availability, or V3 open or govern B1 episodes."
  - "Do not treat an unreferenced generation as canonical or select the newest generation directory without validating HEAD.json."
  - "Do not author tracked production data in a sparse build tree or use a replay/rerun/manual dispatch as natural acceptance."
danger_areas:
  - "The single HEAD replacement is the visibility boundary; sequential target publication reintroduces split truth."
  - "epoch_0 is provisional. A real Stock Identity epoch appends IDENTITY_SUPERSEDED; it never edits or recycles the old episode."
  - "The input sidecar is full and private; site/turn_watch remains capped display evidence and is not the B1 anchor store."
  - "Registry paths beneath generations are resolved through HEAD.generation_id; orphan bytes are noncanonical even when internally valid."
decisions:
  - DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS
---

# B1 built return — natural acceptance still owed

## Verdict

`BUILT_PENDING_NATURAL_ACCEPTANCE.`

The canonical implementation, natural lane, CI owner, dataset contracts, and durable
rulings exist on one carrier. That is build evidence only. It is not a claim that a
production generation exists, that the natural writer has run, or that D5 is released.

## Acceptance boundary

The accepting session must resolve the exact `HEAD.json`, validate the referenced
manifest and every generation member, bind source/projection hashes to the ordinary
scheduled descendant, and exercise the canonical reader read-only. A green fixture,
manual workflow dispatch, rerun, replay, report-mode receipt, or merge SHA alone cannot
substitute for those facts.
