---
workstream: "WS:ALPHA-INTELLIGENCE-INTEGRATION"
session: claude/alpha-k2c-semantic-owner-repair-20260903
model: sonnet
ended_because: complete
mission: >
  Worker RESULT for the bounded post-merge repair
  alpha-k2c-semantic-owner-repair-20260828-sol-001, commissioned by
  agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-08-31-k2c-semantic-owner-repair-commission.md
  under DEC-ALPHA-K2C-K3D-CURRENT-DEPENDENCY-STATE-2026-08-28. Repaired
  lib/institutional_13f_adapter.py so it can no longer emit a semantic
  positive unless BOTH owner seams (canonical security identity, canonical
  manager-complex/vehicle epochs) are proven by their real owners through
  one new keyword-only channel, run_pilot(..., owner_semantics=...). This
  is a WORKER RESULT, not K2-C acceptance -- the commissioning session
  (Fable/CTO Sol per the commission's routing) owns push/PR/CI/review/merge
  and the final REVIEW_RETURN acceptance call.
state_before: >
  Macro #6710 (per the commission) and the frozen commission carrier were
  the controlling state. lib/institutional_13f_adapter.py's _vehicle_decision()
  mapped a 13F row's investment_discretion=="SOLE" to
  decision_mode="discretionary"/vehicle_class="concentrated_discretionary_active"
  (an AUTHORITY field read as vehicle STYLE); build_recipe() minted
  mcx_filer_<CIK>/mce_filer_<CIK>_v1/veh_filer_<CIK>/vie_filer_<CIK>_v1 as
  resolution_state:"resolved" manager-complex/vehicle identity straight from
  the filer CIK; and run_pilot() could emit state=PILOT_COMPILED while its
  own security_binding.dataos_security_id stayed null. K2-C was PARTIAL /
  NOT SOL-ACCEPTED for exactly this reason.
changed:
  - path: lib/institutional_13f_adapter.py
    what: >
      Deleted _vehicle_decision() entirely (no longer exists on the module).
      Added typed constants SECURITY_BINDING_UNRESOLVED, MANAGER_VEHICLE_
      BINDING_UNRESOLVED, OWNER_SEMANTICS_UNRESOLVED_STATE. Added
      _validate_owner_semantics(), a strict/atomic/fail-closed validator:
      any single missing/empty/wrong-typed/partial component in a supplied
      owner_semantics payload (provenance.owner/reference_id,
      security.dataos_security_id/dataos_resolution, manager_complex_epoch,
      vehicle_epoch, each epoch's own resolution_state=="resolved") makes
      the WHOLE payload unresolved -- never partial trust, no defaults
      filled. run_pilot(store, request, *, owner_semantics=None) gates on
      the validated result BEFORE any recipe construction: unresolved ->
      state=PILOT_OWNER_SEMANTICS_UNRESOLVED with compiled_observation_
      state/recipe/compiled all None, measure={"state":"not_compiled",
      "reason":"owner_semantics_unresolved"}, and a new top-level
      owner_semantics block recording both binding states + provenance
      (None when unresolved); periods/denominators/security_binding/
      request/persistence/authority/schema/receipt_id/adapter_version/
      owner_payloads_copied are computed identically to the positive path
      either way. Resolved -> build_recipe (new signature: dropped
      investment_discretion, added manager_complex_epoch/vehicle_epoch/
      security, all owner-supplied and carried VERBATIM -- no identity
      minting, no resolution_state/status stamping) -> compile_recipe ->
      POSITIVE_STATE/NON_POSITIVE_STATE exactly as before. CLI (main/
      _build_arg_parser) unchanged in behavior (no owner_semantics flag by
      design -- frozen spec point 8, a back-door risk); its description
      text now states its real-world outcome is always the owner-unresolved
      terminal receipt. Module docstring rewritten to state the repaired
      law plainly.
  - path: tests/test_institutional_13f_adapter_contract.py
    what: >
      Added 7 new falsifiers per the commission's required list (RED-first,
      captured against unmodified source -- see verified[] below):
      test_sole_discretion_alone_cannot_reach_a_positive,
      test_unresolved_security_binding_kills_the_positive,
      test_cik_is_not_manager_complex_identity,
      test_investment_discretion_never_selects_vehicle_semantics (asserts
      _vehicle_decision no longer exists; empty-string investment_discretion
      is proven unreachable via the owner's own catalog write-path refusal,
      documented inline, and covered instead via build_recipe's signature),
      test_owner_semantics_partial_or_unprovenanced_is_refused (8
      parametrized defect cases), test_no_repo_producer_supplies_owner_
      manager_vehicle_epochs (OWNER-BLOCKED discriminator: greps lib/
      engine/scripts/collectors/app for any manager_complex_epochs/
      vehicle_epochs producer; only this adapter is one, and it now
      requires -- never authors -- the seam), test_authority_stays_false_
      on_every_path. Added one clearly-labelled STRUCTURAL owner_semantics
      fixture (_structural_owner_semantics, commented as non-production
      evidence) used to prove the gate routes a resolved binding into the
      compiler. Repaired test_happy_path_two_period_read_compiles (now
      asserts the owner-unresolved terminal receipt; positive-path oracle
      moved to new test_owner_resolved_structural_fixture_reaches_positive_
      and_recompiles), test_determinism_same_inputs_are_byte_identical
      (now covers both owner-unresolved and owner-resolved determinism),
      test_explicit_generation_id_binds_the_exact_older_generation and
      test_amendment_known_after_cutoff_is_invisible_then_supersedes (both
      now pass the structural fixture to keep their real, orthogonal
      subject -- pointer pinning / amendment lineage -- meaningful),
      test_non_sole_discretion_compiles_non_positive_via_the_compiler (now
      reaches the compiler's own ineligibility law via an owner-resolved
      non-discretionary structural fixture, never via a bare investment_
      discretion value), test_compiled_output_is_uninjectable_and_matches_
      independent_recompute (rebuilt against the new build_recipe
      signature), test_cli_end_to_end_positive_and_refusal (now asserts
      the CLI's real-world outcome is the owner-unresolved state). Replaced
      test_vehicle_decision_mapping_is_honest_for_both_discretion_paths
      with test_investment_discretion_never_selects_vehicle_semantics per
      the commission's explicit instruction. Every other existing typed-
      refusal/adverse test (missing filing, not-yet-knowable, ambiguous
      lineage, unsupported amendment, CUSIP grammar, missing security row,
      ambiguous rows, units, raw-receipt mismatch, non-increasing periods,
      tampered object, CLI errors, denominators) is unchanged and green.
  - path: research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md
    what: >
      Appended new "8. K2-C semantic-owner repair (2026-09-03) -- repaired
      proof + limitation" section: what defect was killed and how it maps
      to specific new tests; the repaired law and receipt shape with a full
      worked owner-unresolved example generated from the repaired module's
      own test fixture world (same filer/CUSIP as the doc's earlier
      now-falsified §7 positive); and an explicit owner-primitive-blocker
      accounting (no repo producer of owner_semantics exists for either
      seam; the CLI carries no override flag by design; the one STRUCTURAL
      test fixture is explicitly not production evidence). No prior content
      edited or deleted.
  - path: agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-09-03-k2c-semantic-owner-repair-result.md
    what: This handoff.
verified:
  - claim: "The 7 new falsifiers fail on UNMODIFIED source for the intended semantic reason (RED-first)."
    command: >
      python3 -m pytest <scratch RED-capture harness mirroring the 7 new
      tests against unmodified lib/institutional_13f_adapter.py, using
      literal string stand-ins for the 3 not-yet-existing constants so
      no ImportError could mask the real per-test semantic failure> -q
    result: >
      14/14 failed (7 tests, one parametrized x8) -- every failure was a
      genuine semantic AssertionError/TypeError: state=='PILOT_COMPILED'
      instead of the unresolved sentinel (x3 tests); a full recipe/
      compiled payload present where None was expected; the literal string
      'mcx_filer_0001792167' found inside the receipt; hasattr(module,
      '_vehicle_decision') == True; run_pilot() rejecting the
      owner_semantics keyword outright (TypeError, x8 parametrized cases);
      'owner_semantics' absent from run_pilot's own signature. No
      ImportError, no typo, no environment failure.
  - claim: "All four required commands are green on the repaired source."
    command: "python3 -m pytest tests/test_institutional_13f_adapter_contract.py -q"
    result: "44 passed"
  - claim: "K2-B's own combined contract suite is unaffected."
    command: "python3 -m pytest tests/test_institutional_manager_intent_contract.py -q"
    result: "71 passed"
  - claim: "Agent OS records validate clean."
    command: "python3 scripts/agentos.py validate"
    result: "exit 0; 1032 records, 0 error(s), 83 warning(s) (all pre-existing, unrelated to this change -- phantom-owns-path/review-overdue on unrelated workstreams/decisions)."
  - claim: "tests/test_agent_os_records.py does not exist in this repo; skipped per the commission's conditional instruction."
    command: "ls tests/test_agent_os_records.py"
    result: "No such file or directory"
  - claim: "No mcx_filer_/mce_filer_/veh_filer_/vie_filer_ string remains in the adapter module."
    command: "grep -n 'mcx_filer_\\|mce_filer_\\|veh_filer_\\|vie_filer_' lib/institutional_13f_adapter.py"
    result: "no matches"
  - claim: "_vehicle_decision no longer exists on the module."
    command: "grep -n _vehicle_decision lib/institutional_13f_adapter.py"
    result: "no matches"
  - claim: "No authority value changed to True anywhere in the module."
    command: "grep -n 'can_rank\\|can_gate\\|can_size\\|can_originate\\|can_open_entry' lib/institutional_13f_adapter.py"
    result: "no matches at all (authority values are only ever read from lib.evidence_foundation.ALL_FALSE_AUTHORITY, never hardcoded True in this file)"
  - claim: "Only the four owned files changed; no data/site/mockups/verify_shots writes in this sparse worktree."
    command: "git status --porcelain"
    result: >
      4 modified/added paths only:
      M lib/institutional_13f_adapter.py,
      M tests/test_institutional_13f_adapter_contract.py,
      M research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md,
      ?? agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-09-03-k2c-semantic-owner-repair-result.md
unverified:
  - claim: "The repaired module behaves correctly against real production 13F store data (not just this worker's synthetic test-fixture world)."
    what_would_verify: >
      A real owner-read pilot run against the production institutional_13f
      store (as §7 of this same doc did pre-repair) confirming the
      OWNER_SEMANTICS_UNRESOLVED_STATE receipt shape holds for a live filer/
      CUSIP pair. This worker had no production store credentials/network
      access in-session and used only the existing test-fixture LocalStore
      pattern already established by this file's own test suite.
unresolved:
  - "No repository owner currently supplies a lawful owner_semantics payload for either seam (grep-confirmed in test_no_repo_producer_supplies_owner_manager_vehicle_epochs) -- K2-C therefore still cannot reach a REAL owner-backed semantic positive; the false-positive defect is closed, but a real positive still requires a separate Data OS CUSIP-identity commission and a separate institutional/K2-B manager-vehicle-epoch commission per the commission's owner-primitive-blocker contract."
  - "This worker did not push, open a PR, or run hosted CI/fences -- the commissioning session owns that chain per its explicit instruction (do NOT push/PR/merge)."
next_actions:
  - "Commissioning session: review this head, push, open PR, run hosted CI/fences, and carry the operation through REVIEW_RETURN per the commission's return/acceptance gate."
  - "Sol/CTO: adjudicate whether K2-C should now be recorded as 'false-positive defect closed, real positive still owner-blocked' rather than its prior PARTIAL/NOT-SOL-ACCEPTED framing, and whether a separate owner-primitive child (Data OS CUSIP identity; institutional/K2-B manager-vehicle epoch producer) should be opened."
do_not_redo:
  - "Do not build a CUSIP map, ticker resolver, security master, manager identity table, vehicle ontology, cache, store, scheduler, queue, or retry plane to fill the owner_semantics seam from this repair -- that is explicitly out of scope and belongs to a separate Data OS / institutional-owner commission."
  - "Do not add a CLI flag for owner_semantics -- deliberately absent; would be a back door around the owner-proof gate."
  - "Do not re-derive vehicle class or decision mode from investment_discretion, voting authority, filer CIK, manager name, or portfolio concentration anywhere in this module."
danger_areas:
  - "build_recipe's manager_complex_epochs/vehicle_epochs schema (contracts/institutional_intelligence/manager_intent_recipe.v1.schema.json) requires a concrete vehicle_class even when resolution_state is unresolved -- this repair avoids that trap by refusing BEFORE constructing any recipe on the unresolved path, never by choosing a convenient placeholder class for an owner-supplied-but-unresolved epoch."
  - "The STRUCTURAL test fixture's IDs (mcx_structural_test_owner, veh_structural_test_owner, ...) are deliberately NOT filer/CIK-derived and deliberately do not match the schema's own '^mcx_[a-z0-9_]+$' etc. patterns by accident -- do not repurpose this fixture as a template for a real owner producer without a fresh Sol adjudication."
---

# K2-C semantic-owner repair — worker RESULT

**Operation key:** `alpha-k2c-semantic-owner-repair-20260828-sol-001`
**Branch/head:** `claude/alpha-k2c-semantic-owner-repair-20260903` (not pushed by this worker)
**Base:** `origin/main` @ `12e96892723d79516bebfd3ec9075c7d420b1dc7`

See frontmatter `changed`/`verified` for the full file-by-file diff and command
evidence, and `research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md`
§8 for the repaired receipt shape and a full worked example.

This is a worker RESULT only — the commissioning session owns push, PR, hosted
CI/fences, review, and the final `REVIEW_RETURN` acceptance call per the
commission's explicit routing.
