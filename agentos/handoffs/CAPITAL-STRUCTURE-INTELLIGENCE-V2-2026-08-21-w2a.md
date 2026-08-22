---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: codex/cs-v2-w2a
model: codex
ended_because: ci_handoff
mission: >
  Implement the bounded W2A scheduler and canonical information-horizon slice
  without changing the 200-filing cap, W1 evidence identity, closed bundles,
  append-only generation fence, #5792 health verdict, or Prophet authority;
  obtain independent Sol review before delivery.
state_before: >
  W1/W1A/W1B were PROVEN_LIVE. The implementation-base ledgers at
  33d70f5ce4b36329e8acfb285557f4c9d3c72589 had 18,652 retryable pending
  filings, 1,320 pending in the latest five completed SEC sessions, and recent
  all-policy arrivals above the unchanged 200 cap. Compiler age was exposed as
  freshness even though eligible-retained and compiled filing horizons were
  both 2026-07-31 against discovered 2026-08-20.
changed:
  - path: collectors/sec_capital_structure.py
    what: >
      Add operational LIVE_TAIL, RECOVERY, and HISTORICAL_BACKFILL classes;
      fixed 160/20/20 reservations; deterministic spill; newest-session-first
      live service inside each existing lane; exact current-run arrivals;
      additive queue receipt telemetry; attempt work_class; and run-scoped
      per-class outcomes. The global cap remains 200.
  - path: engine/capital_structure/ingestion_health.py
    what: >
      Add the sole canonical discovery -> eligible-retained -> compiled horizon
      calculation with current, lagging, degraded_capacity,
      degraded_discovery, and unavailable states; completed-session gaps;
      fail-closed date/clock handling; exact generation binding; and per-class
      progress. Keep #5792 decide_verdict separate and unchanged.
  - path: engine/capital_structure/projection.py
    what: >
      Derive public freshness only from a generation-bound canonical horizon
      while exposing compiler age separately as generation freshness.
  - path: scripts/build_capital_structure_projection.py
    what: >
      Require validated health and exact compiler generation/as_of binding
      before byte-identical canonical/public promotion.
  - path: .github/workflows/daily.yml
    what: Order events -> terms -> health/horizon -> projection.
  - path: config/dag.yml
    what: Record the same production dependency order.
  - path: templates/capital_structure.js and site/capital_structure.js
    what: >
      Keep the existing small coverage notice and its checked-in public twin
      truthful: current only when both freshness and horizon state are current.
  - path: contracts/
    what: >
      Add strict but backward-compatible queue-receipt, health-horizon, and
      projection-coverage fields. Legacy artifacts stay readable; missing W2
      truth cannot be presented as fresh.
  - path: tests/
    what: >
      Add hostile scheduler, current/lagging/degraded/unavailable horizon,
      malformed/null/offset clock, generation mismatch, twin promotion,
      workflow, page, and direct per-class collector-outcome regressions.
  - path: research/CAPITAL_STRUCTURE_W2A_QUEUE_CENSUS_2026-08-21.md
    what: Freeze the implementation-base queue and arrival census.
  - path: agentos/decisions/DEC-CS-V2-W2A-CLASS-RESERVES-AND-HORIZON-FRESHNESS.md
    what: Record the class allocation, spill, newest-live, and freshness law.
verified:
  - claim: Independent Sol review found no remaining P0, P1, or P2 pre-merge defect.
    command: >
      Independent gpt-5.6-sol xhigh review of the complete uncommitted W2A
      working tree after each hostile finding was fixed and re-reviewed.
    result: STATUS PASS; no deviations; production proof remains the only gap.
  - claim: Integrated W2A plus W1 identity/closed-bundle/compiler/fence suite passes.
    command: >
      PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest --noconftest -q
      tests/test_sec_capital_structure.py
      tests/test_capital_structure_ingestion_health.py
      tests/test_build_capital_structure_projection.py
      tests/test_capital_structure_projection.py
      tests/test_capital_structure_evidence_identity.py
      tests/test_capital_structure_closed_bundle.py
      tests/test_capital_structure_contracts.py
      tests/test_capital_structure_compiler.py
      tests/test_daily_capital_structure_job.py
      tests/test_capital_structure_page.py
      tests/test_append_only_base_fence.py::test_cs_stale_generation_withholds_whole_family_not_one_file
      tests/test_append_only_base_fence.py::test_registry_loads_and_declares_capital_structure_family
    result: 246 passed; three unrelated pytest temporary-directory cleanup warnings.
  - claim: Exact current-ledger replay preserves newest live work and reports the adverse capacity state.
    command: >
      Read-only select_retrieval_queue and evaluate_health replay on committed
      data/capital_structure artifacts at the implementation base.
    result: >
      selected 200: LIVE_TAIL 180, RECOVERY 0, HISTORICAL_BACKFILL 20;
      live pending 1,320 and unserved 1,140; newest selected 2026-08-20;
      discovered 2026-08-20, retained 2026-07-31, compiled 2026-07-31;
      14 completed-session discovery-to-retained gap; state
      degraded_discovery because 2026-08-21 remains retry plus capacity and lag.
  - claim: Arrival statistics reproduce the frozen capacity census.
    command: >
      Recompute in-policy arrivals for the latest eight completed sessions from
      committed discovery and index coverage.
    result: >
      counts 334, 353, 446, 485, 217, 190, 229, 199; p50 281.5;
      p95 471.4; max 485. The 200 cap is structurally insufficient.
unverified:
  - claim: Attributable exact-head GitHub CI on the W2A pull request.
    what_would_verify: Open the PR and wait for all required checks to conclude green.
  - claim: First natural post-merge collector -> Capital Structure production chain.
    what_would_verify: >
      The first scheduled daily containing the W2A merge; do not dispatch a
      duplicate daily merely to accelerate proof.
unresolved:
  - "W2A remains in_progress until PR CI, merge, and the first natural production chain are proven."
  - "The 200 cap remains insufficient; 160/20/20 is bounded fairness, not adequacy."
  - "Do not add a current-submissions overlay without new failure evidence and a separate review."
next_actions:
  - Commit, push, open the W2A PR, arm merge-on-green, and stay through concluded exact-head CI.
  - Merge only on the independent Sol PASS plus concluded green checks.
  - Wait for the first natural scheduled collector -> Capital Structure chain containing the merge.
  - Record exact class, lane, horizon, twin-hash, W1 stability, fence, #5792, and authority proof; then close W2A in a separate closeout PR.
do_not_redo:
  - Reopen W1 identity, closed-bundle, or append-only generation laws.
  - Change MAX_FILINGS_PER_RUN=200 in W2A.
  - Treat work_class as evidence, event, manifest, generation, or authority identity.
  - Dispatch a duplicate daily to manufacture the production receipt.
  - Present compiler age or a successful ingestion verdict as current filing coverage.
  - Start W3 or W4 before W2A production proof closes.
danger_areas:
  - "Newest-session-first inside LIVE_TAIL is necessary: oldest-first starved 2026-08-20 under the measured five-session backlog."
  - "Discovery and retention clocks must belong to their newest filing-date cohort, not be independently maximized."
  - "Malformed, null, naive, or invalid sibling clocks must fail unavailable, never fresh."
  - "not_published is calendar closure only when last_error begins the exact SEC calendar closure marker; an aged weekday 404 remains degraded discovery."
  - "Legacy W1 eligible-clean complete roots without later file-number provenance remain retained evidence."
prs: []
decisions:
  - DEC:CS-V2-W2A-CLASS-RESERVES-AND-HORIZON-FRESHNESS
discoveries: []
---

# W2A pre-merge state

Implementation and independent Sol review are complete. This record is not a
merge, deployment, or live-production claim. W2A stays in progress until the
first natural post-merge collector -> Capital Structure chain is receipted.
