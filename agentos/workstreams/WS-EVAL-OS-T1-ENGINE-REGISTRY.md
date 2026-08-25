---
key: EVAL-OS-T1-ENGINE-REGISTRY
title: Intelligence Evaluation OS — T1 canonical engine registry (derived view + integrity guard + isolated CI)
objective: >
  One canonical unit of account for "an intelligence engine" — engine_id =
  producer::owner_program derived on demand over the synapse artifact estate, authority
  derived from canonical sources with provenance, missing evidence explicit
  (AUTHORITY_WITHOUT_EVIDENCE), nothing generated committed — plus an integrity guard that
  can never render "could not look" as "0 violations", enforced in an isolated CI job that
  cannot mask sibling suites. Done when the fix-wave PR is merged and the guard runs green
  in its own legacy job on main.
status: done
program: qualitative-intelligence
repos:
  - macro
owner: Eval-OS session (COO Fable lane)
class: build
blast_radius: reversible
ambiguity: specified
owns_paths:
  - engine/intelligence_registry.py
  - scripts/build_intelligence_registry.py
  - scripts/check_intelligence_registry.py
  - tests/test_intelligence_registry.py
  - tests/test_check_intelligence_registry.py
  - config/intelligence_registry_overlay.yml
decisions:
  - "DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE"
waves:
  - id: W1
    title: Parked build (three adversarial rounds, 2026-08-12)
    status: done
    next_action: "None — parked with research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md; recovered verbatim 2026-08-14."
  - id: W2
    title: Fix wave — B1/B2/B3 + M1-M4 + adversarial review findings + isolated CI job
    status: done
    pr: 5620
    next_action: "None — merged d13259abc51c 2026-08-14T17:31Z; ci-pack-7 (the pack carrying intelligence-registry) was green on the PR's own proof run; merged files byte-verified on main. The head run keeps a permanent frozen-vintage ci-pack-8 red (govrev dag drift #5516, healed on main by #5655 AFTER this merge; a rerun re-executes the pre-heal merge commit and cannot green) — disposition recorded in the 2026-08-14 handoff."
  - id: W3
    title: output_class bounded adjudication (the curated overlay)
    status: done
    next_action: "None — 107 of 109 required engines curated with evidence-cited rationales (59 descriptive / 21 predictive / 15 classification_state / 7 detection_event / 3 ranking / 2 salience); 2 deliberate nulls kept (cortex two-species CEO exception, options_structure unbuilt schema). Method: 12 evidence packets -> main-loop adjudication -> 4 adversarial opus reviews over 52 rows (7 class flips accepted, 1 unresolved refuted on partition law, 2 confirmed, ~18 rationale defects fixed). OUTPUT_CLASS_MISSING 109 -> 2; content findings 212 -> 105. Provenance in the 2026-08-14 handoff W3 addendum."
do_not_redo:
  - "Do not commit a generated registry artifact or add a --check/equality/drift mode — two parked rounds did and both were scheduled fleet-wide reds (handoff §2; the volatile-input measurement now reads N commits/14d on FULL history)."
  - "Do not re-fold the T1 CI steps into neural-web at either end — run_ci_pack returns on the first non-zero step; front masks nine sibling suites, back goes dark (CEO ruling 2026-08-14: isolated job)."
  - "Do not restore ledger waterfall rule 4's cross-program hop — measured 2026-08-14: 6 of 7 live hops resolved a foreign program's ledger (engine/run.py::engine-fix adopted hk-canada's ca_board.parquet)."
  - "Do not tighten the rule-1 path heuristic to basename-only — 5 of 35 live matches carry 'ledger' only in a directory component and all five are real grading stores; the fix was disclosure (weak_path_heuristic), not narrowing."
  - "Do not make data/qledger/claims.jsonl corruption red the PR lane without --strict — DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE; the reviewer reproduced one truncated line redding the job for every PR."
  - "Do not fill output_class mechanically to reach 100% — it selects the metric contract; a wrong contract is worse than a disclosed null."
landmines:
  - "The AST meta-test in tests/test_check_intelligence_registry.py enumerates live-invoking call shapes with a frozen allowlist — a new test that runs the guard/builder against the live repo must either take --root fixtures or be added to the allowlist with a justification; the detector has canned-source controls for each evasive shape it knows."
  - "engine/neuralweb/synapse.py 2k2 (scored_path_surfaces value validation) is a values-only validate-when-present hard gate in the ALWAYS-ON synapse validator — reviewed and kept 2026-08-14; requiring the key on all artifacts would change every open PR."
next_action: >
  This bounded T1 workstream is complete. Preserve the landed registry/guard/overlay and its
  two deliberate output_class nulls as durable residue. Any T4 output-health work, T12 Agent OS
  tier interface, prospective evidence accrual, cortex two-species adjudication, options_structure
  curation, or T7/T8 measurement belongs to its own canonical workstream/wave and does not reopen T1.
---

## State (2026-08-14)

The parked branch's three commits were recovered verbatim onto current main (cherry-pick -x,
T1 files byte-identical), then a builder wave closed B1/B2/M1-M4 with 13 biting mutation
controls, an Opus adversarial reviewer returned 2 MAJOR + 3 MINOR + 4 NIT (all reproduced with
commands), and a second builder wave closed every finding. T1c runs as the isolated
`intelligence-registry` legacy job (189th; 188 measured with zero exact-duplicate signatures,
so nothing could be safely consolidated). Full session detail:
`agentos/handoffs/WS-EVAL-OS-T1-ENGINE-REGISTRY-2026-08-14.md`.

## Lifecycle reconciliation — 2026-08-24/25

Sol reconciled the stale top-level `active` status after current-main validation showed all
three declared waves terminal, no live PR carrier, and the workstream's own objective already
satisfied. Future Eval OS choices named above are separate work and do not keep this bounded
T1 identity active. This correction changes organizational state only; no engine, guard, CI,
or generated registry behavior changes.
