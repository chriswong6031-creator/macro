---
workstream: WS:EVAL-OS-T1-ENGINE-REGISTRY
session: claude/eval-os-t1-engine-registry-v2
model: fable
ended_because: ci_handoff

mission: >
  Resume the parked T1 engine-registry branch per the CEO continuation directive
  2026-08-14: recover the parked work onto current main, close blockers B1/B2/B3 and
  majors M1-M4, give T1 its own isolated CI job (CEO ruling), keep the derivation
  trustworthy on current main, enumerate the curated output_class set without filling it,
  and ship as armed PR(s).

state_before: >
  claude/eval-os-t1-engine-registry parked 2026-08-12 at 352d537438b (3 substantive
  commits, no PR) with an honest continuation handoff: 378 engines derived, 67/67
  selftest, but a test forbade the guard's own fail-closed annotation (B1), a malformed
  qledger store read as zero desk rows (B2), the T1 CI steps sat at the front of the
  always-on neural-web job masking nine sibling suites (B3), two tests asserted live
  synapse.yml contents with a meta-test that could not see the real call shapes (M1),
  the ledger waterfall hopped cross-program (M2), the path heuristic's disclosure said
  filename (M3), and fail-closed existed only behind a --strict nothing ran (M4).
  The repo clone was shallow (boundary 2026-08-11).

changed:
  - path: engine/intelligence_registry.py
    what: "Ledger waterfall rule 4 restricted to same-owner_program hops with a (producer, owner_program)-keyed index — measured 6 of 7 live cross-program hops wrong or unearned; evidence enum renamed weak_path_heuristic; every filename-wording disclosure corrected; churn figures re-measured on full history."
  - path: scripts/build_intelligence_registry.py
    what: "_load_qledger counts unparseable lines (B2) and names them in unreadable_inputs; DATA_PLANE_INPUTS + input_plane() implement the plane jurisdiction as mechanism (a decorative first version was caught by its own mutation control); unparseable synapse/overlay/qual_ladder fail closed with named summaries, never tracebacks."
  - path: scripts/check_intelligence_registry.py
    what: "Blindness exit policy by plane (DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE): PR-plane blind exits 1 unconditionally in both output modes, data-plane (claims.jsonl) always represented and reds under --strict; C-1 rows now also print as plain stdout lines; selftest grew 67 -> 84 controls; write_fixture_root factored as the single fixture source; SynapseUnavailable sentinel replaces the bare-SystemExit key."
  - path: tests/test_check_intelligence_registry.py
    what: "B1 fixed (three-channel annotation budget, blindness budgeted at one); M1 fixed (live-content tests rebuilt on fixture roots); the meta-test is AST-based over the real call shapes (subprocess _run, build(REPO), guard.main/bare main, import aliases, direct subprocess.run of either CLI) with a 16-entry justified allowlist, set-equality both directions, and canned-source controls per evasive shape."
  - path: tests/test_intelligence_registry.py
    what: "Live-parseability and live-non-emptiness assertions moved to fixtures; corpus-append immunity re-encoded as a fixture pair (valid append invisible / malformed append flips INCOMPLETE); a healed corpus is pinned silent-and-green."
  - path: .github/ci/legacy-jobs.yml
    what: "The two T1 steps left the front of neural-web (restored byte-exact to main); new isolated intelligence-registry job (guard selftest + plain guard run + both pytest suites) — CEO ruling 2026-08-14; 188 jobs measured pre-add with zero exact-duplicate run signatures, so nothing could be safely consolidated."
  - path: config/house_law_checks.yml
    what: "Both T1 law entries re-wired to the isolated job; FAIL CLOSED known_limit records the plane cut and the deferred nightly-side --strict (owner T7); post-rebase the whole file was rebuilt as pristine-main + the two T1 entries after a keep-both conflict resolution was caught truncating main's ops.nightly_liveness entry."
  - path: research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md
    what: "T1 amended into T1a/T1b/T1c with the two 2026-08-14 rulings (isolated job; plane-split fail-closed) and honest churn figures."
  - path: research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md
    what: "The historical parking record landed verbatim under a COMPLETED banner naming what closed it."
  - path: agentos/decisions/DEC-EVAL-OS-BLINDNESS-EXITS-BY-PLANE.md
    what: "The jurisdiction decision: which blindness reds the PR lane and why."
  - path: agentos/workstreams/WS-EVAL-OS-T1-ENGINE-REGISTRY.md
    what: "Workstream record with waves, do_not_redo, landmines."

verified:
  - claim: "Guard selftest passes with every added control."
    command: "python3 scripts/check_intelligence_registry.py --selftest"
    result: "selftest: PASS (84/84), rc 0 (was 67/67 at park)."
  - claim: "Live derivation unchanged in size and clean: 378 engines, 0 structural violations, inputs complete."
    command: "python3 scripts/check_intelligence_registry.py"
    result: "intelligence registry: 378 engines, 0 structural violation(s), 212 content finding(s), inputs=complete — rc 0. Findings 222 -> 212: six engines lost an unearned cross-program ledger and four display-authority engines left the output_class-required set with it."
  - claim: "Both suites green on the rebased tree."
    command: "python3 -m pytest tests/test_intelligence_registry.py tests/test_check_intelligence_registry.py -q"
    result: "196 passed (165 at park)."
  - claim: "All 12 CI packs validate with the new isolated job; trigger closure, workflow YAML and the house-law registry are green."
    command: "for n in 0..11: python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index N --pack-count 12 --validate-only; python3 scripts/check_ci_trigger_closure.py; python3 scripts/check_workflow_yaml.py; python3 scripts/check_house_law_registry.py"
    result: "12/12 rc 0; closure OK; 86 workflow files OK; house-law rc 0 after the post-rebase registry rebuild."
  - claim: "The jurisdiction split is mechanism, not documentation — independently spot-checked by the orchestrator on top of the builder's 14/14 control battery."
    command: "Re-classify claims.jsonl as PR-plane (DATA_PLANE_INPUTS = frozenset()), pytest -k 'plane or jurisdiction or data'"
    result: "1 failed immediately; byte-identical restore -> 5/5 green."
  - claim: "T1 tests are clean under the append-only assertion law (P2, merged #5534)."
    command: "python3 scripts/check_append_only_assertions.py --selftest; python3 scripts/check_append_only_assertions.py"
    result: "Selftest OK; zero findings on tests/test_intelligence_registry.py and tests/test_check_intelligence_registry.py."
  - claim: "The branch's true change set touches only T1-owned + wiring files, with zero sibling deletions."
    command: "git diff --stat $(git merge-base origin/main HEAD) HEAD; git diff --diff-filter=D --name-only $(git merge-base origin/main HEAD) HEAD"
    result: "11 files, +6664/-8, no deleted files. (Raw diff vs origin/main tip shows wire-lane noise only because the shared clone's origin/main advances every few minutes.)"

unverified:
  - claim: "The isolated intelligence-registry job goes green on this PR's own CI run."
    what_would_verify: "After the sweeper merges, read the ci-pack run for the merge and confirm the intelligence-registry job's two steps concluded green."
  - claim: "agentos validate is green on the merge ref (my tree reds on a dangling WS:CI-MERGE-CONTROL-PLANE ref because the WS record landed via #5608, after this branch's merge-base)."
    what_would_verify: "The neural-web pack's agentos validate step on the PR's merge-ref checkout, where both files exist."

unresolved:
  - "Claim-store corruption alerts everywhere and gates nowhere until a nightly-era lane passes --strict (deliberate cost of the plane cut; owner: T7 wave; recorded in the guard docstring, house-law known_limit and DEC)."
  - "output_class curation: 109 engines are required_but_uncurated (86 display-authority gate-trippers, 12 engine_input, 6 user_ranking, 5 gate_size). The set is derivable on demand (build() then filter output_class_reason == 'required_but_uncurated') — deliberately NOT committed as a list. Needs a bounded adjudication session (W3)."
  - "The engine-level authority roll-up is a MAX and overstates authority for low-tier siblings in the 32 mixed-tier cells — standing disclosure, consumers must read artifacts[].artifact_authority per-artifact."

next_actions:
  - "Sweeper merges the armed PR; then confirm the intelligence-registry job ran green on the merge (gh run view on the merge SHA's ci run)."
  - "W3: hand the 109-engine output_class set to a curation session; fill config/intelligence_registry_overlay.yml rows with citations, never mechanically."
  - "T7 wave: wire the guard's --strict into a nightly-era lane so data-plane corruption gates where the data-plane actor lives."

do_not_redo:
  - "Do not commit a generated registry or add a --check/equality/drift mode — two parked rounds did, both were scheduled fleet-wide reds; synapse.yml measured ~70 commits/14d on FULL history 2026-08-14."
  - "Do not re-fold T1 steps into neural-web at either end — run_ci_pack returns on the first non-zero step (CEO ruling: isolated job)."
  - "Do not restore the cross-program rule-4 hop (6 of 7 live hops wrong: engine/run.py::engine-fix had adopted hk-canada's ca_board.parquet) or tighten rule 1 to basename (5 of 35 true positives live in directory components)."
  - "Do not make claims.jsonl corruption red the PR lane without --strict — DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE; the reviewer reproduced one truncated line redding the job for every PR."
  - "Do not fill output_class mechanically; a wrong metric contract is worse than a disclosed null."
  - "Do not resolve keep-both YAML conflicts on config/house_law_checks.yml with a line filter — it truncated main's ops.nightly_liveness entry here; rebuild as pristine-main + own entries and prove parsed-form equality per main entry instead."

danger_areas:
  - "The AST meta-test freezes live-invoking call shapes with a 16-entry allowlist — new tests that run the guard/builder live must take --root fixtures or join the allowlist with a justification."
  - "config/house_law_checks.yml and .github/ci/legacy-jobs.yml are append-collision magnets (four sibling PRs in two days); the doc is GENERATED — resolve the yml, then check_house_law_registry --emit-docs, never hand-merge the doc."
  - "engine/neuralweb/synapse.py 2k2 (scored_path_surfaces value validation) is a values-only hard gate in the always-on synapse validator — reviewed and kept; requiring the key on all artifacts would change every open PR."
  - "The shared clone's origin/main ref advances every few minutes under the wire lanes — diff sanity must run against the merge-base, and any keep-both rebase resolution must be re-proven against pristine main afterward."

prs: []
decisions:
  - "DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE"
---

## Cold-start orientation

Read `research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md` (now carrying its COMPLETED
banner) for the three-round history that produced the parked design, then the PR body for
the one-PR-instead-of-three justification (the workflow-yaml fence couples new test files
to legacy-jobs wiring per-PR; stacked PRs get zero CI here; a pack is one check, so partial
enforcement deadlocks). The single most important structural fact: the registry is a
DERIVED ON-DEMAND VIEW — nothing generated is committed, and both the guard and the tests
are built so that a legitimate nightly append or sibling synapse PR can never red them.
