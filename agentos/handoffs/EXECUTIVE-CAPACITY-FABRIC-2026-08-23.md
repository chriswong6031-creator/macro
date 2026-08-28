---
workstream: "WS:EXECUTIVE-CAPACITY-FABRIC"
session: "sol/executive-capacity-cf1-20260823"
model: codex
ended_because: complete
mission: >
  Execute MAS-126 CF1 only: build one deterministic secret-free no-write Macro projection from
  existing Provider Control observations to strict `mastermind.provider_capacity.v1`, expose one
  real JSON stdout consumer, prove the frozen F0 null/evidence/semantic-source law, and park one
  draft HOLD-FOR-SOL pull request without merge, deployment or CF2 work.
state_before: >
  F0 was accepted as source law, but Macro had no canonical provider-capacity producer or consumer.
  Existing display/dispatch helpers intentionally combined presence, enablement and usability or
  failed soft on unreadable state, so their output could not be re-labelled as the strict contract.
  The commissioned remote branch pointed exactly at pickup SHA
  a990d05df2505ae3929172d38c6e248d627fec4d and no overlapping CF1 pull request existed.
changed:
  - path: engine/provider_capacity.py
    what: >
      Added the closed v1 inventory/schema validator, evidence and freshness normalizer, canonical
      ordering/hash, static material-source digest and exact-commit grounding, source-owned
      observation collection, and secret-free failure vocabulary.
  - path: scripts/build_provider_capacity.py
    what: >
      Added the bounded no-write machine/operator consumer that emits only strict canonical JSON
      stdout and bounded secret-free refusal text on stderr.
  - path: engine/neuralweb/key_pool.py
    what: >
      Added a read-only source seam that preserves reviewed Claude/Codex/DeepSeek inventory,
      unfiltered presence, enablement, strict ledger quality, cooling evidence, safe header
      telemetry and last outcome without changing dispatcher behavior.
  - path: engine/codex_provider.py
    what: >
      Added a read-only three-slot Codex observation seam separating credential-marker presence,
      provider enablement and executable readiness without opening or returning auth contents/paths.
  - path: engine/provider_health.py
    what: >
      Added a strict secret-free attempt-telemetry reader that distinguishes missing, unreadable
      and corrupt health sources while omitting raw detail.
  - path: engine/metabolism/budget_gate.py
    what: >
      Added a strict estimator-config reader that preserves missing/corrupt/unreadable quality
      independently of the existing dispatch gate's required fail-soft defaults.
  - path: tests/test_provider_capacity.py
    what: >
      Added 35 contract/source/material-grounding/no-write/secret-redline tests including semantic
      mutation vectors and the real CLI consumer.
  - path: agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md
    what: >
      Recorded CF1 as built but pending Sol in draft PR #6297; every later wave remains held.
verified:
  - claim: CF1 and all directly touched neighboring provider-owner suites are green locally.
    command: python3 -m pytest -q tests/test_provider_capacity.py tests/test_codex_provider.py tests/test_provider_health.py tests/test_key_pool.py tests/test_key_pool_economy.py tests/test_key_pool_seven.py tests/test_metabolism_budget_gate.py
    result: 221 passed, 0 failed; three unrelated pytest temporary-directory cleanup warnings.
  - claim: The real consumer emitted a grounded complete 12-slot current-provider snapshot twice without semantic time drift.
    command: python3 scripts/build_provider_capacity.py
    result: >
      At implementation commit c50a0da5061135e0b0529fcd717ef017c8e8f0ac, audit commit matched
      HEAD, material_sources_match_commit was true, and projections at 06:55:38Z and 06:56:09Z
      shared snapshot hash b9c39f5bbce13476e8eb2b82fc345fe08356c2d95c44df5c962558339354025c.
  - claim: The real consumer made no canonical source write and emitted clean canonical JSON stdout.
    command: python3 -m pytest -q tests/test_provider_capacity.py::test_real_cli_is_canonical_json_and_no_write
    result: passed; explicit before/after SHA-256 receipts also found provider telemetry unchanged and Git state clean.
  - claim: The semantic producer identity is file-granular and independently grounded from Git audit provenance.
    command: python3 -m pytest -q tests/test_provider_capacity.py -k 'material or allowlist or audit or hash'
    result: >
      Passed grounded/dirty/restored material bytes, unrelated dirty and unrelated commit controls,
      allowlist mutation, missing/symlink/path-escape refusal, exact hash exclusions and semantic mutations.
  - claim: The implementation branch had no concurrent writer and newer main did not change provider semantics.
    command: git fetch origin && git diff --name-status a990d05df2505ae3929172d38c6e248d627fec4d..origin/main -- config/capability_manifest.yml config/metabolism_budget.yml config/mastermind_programs.yml engine/codex_lane/runner.py engine/codex_provider.py engine/llm_auth.py engine/metabolism/budget_gate.py engine/neuralweb/key_pool.py engine/provider_health.py lib/ai_costs.py
    result: >
      Exact commissioned remote branch remained at pickup before push. Only lib/ai_costs.py differed
      on newer main, by one unrelated earnings-event lobe classification; its provider-health state-root
      semantics were unchanged. No open overlapping CF1 pull request existed.
unverified:
  - claim: Final pull-request head has concluded all hosted binding checks green.
    what_would_verify: Wait for every check on draft PR #6297's final exact head and record the run/check receipts without merging.
  - claim: Independent adversarial review has accepted the final exact head with all mutation findings closed.
    what_would_verify: Run the commissioned independent reviewer against PR #6297's final exact head, repair any finding, and repeat on the repaired head.
  - claim: Sol accepts CF1 for merge.
    what_would_verify: Sol reviews the final exact-head packet and explicitly releases HOLD-FOR-SOL; nothing in this session may infer that release.
unresolved:
  - "Only Sol's exact-head acceptance/release decision remains after independent review and hosted CI conclude."
next_actions:
  - "Run independent adversarial review against the final exact PR #6297 head; close every real finding without widening scope."
  - "Wait for full hosted CI/fences on that same head and record exact run/check receipts."
  - "Audit that PR #6297 is still draft, has no merge-on-green label, has no native auto-merge, points to the commissioned branch, and has a clean exact pushed head; then stop for Sol review."
do_not_redo:
  - "Do not create another provider-capacity store, service, daemon, router, provider, inventory numbering scheme or Executive schema/placement change."
  - "Do not replace nullable unknowns with display zeros or fail-soft false values; the new owner seams are deliberately separate from dispatch/display helpers."
  - "Do not import Macro internals into Mastermind or begin CF2-F/CF2-I, RF1, HF1, PF1 or MH1 from this held CF1 candidate."
  - "Do not arm, ready, merge, deploy or call PR #6297 shipped; HOLD-FOR-SOL is a binding merge barrier."
danger_areas:
  - "Credential presence may be observed only inside existing source owners; engine/provider_capacity.py must never gain a direct secret/auth-file read path."
  - "MATERIAL_SOURCE_PATHS is semantic source law: any new first-party dependency that can alter a projected field must be reviewed into the static census."
  - "A complete empty cooling ledger proves only the local negative; an absent/corrupt/unreadable ledger stays cooling.active=null."
  - "A stale provider success remains historical available+stale evidence and cannot be restamped fresh by a new projection."
prs: [6297]
decisions:
  - "DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT"
---

This is a PARKED candidate mission, not a shipped result. The PR must remain draft and unarmed
until Sol explicitly releases the hold. The exact final-head review, CI and hold audit belong in
PR #6297 receipts because adding them here after conclusion would create a new unproven head.
