---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-1r3-semantic-closure
model: local
ended_because: complete
prs: [5889]
mission: >
  Amend PR #5889 in place. Close Sol's remaining FIF-1R3 cross-layer contract
  defects (canonical↔source identity, cutoff-visible governance, lineage-safe
  revisions, whole-packet against-input) plus two boundedness corrections.
  Do not create FIF-1R4. Do not start FIF-2. Hold for Sol freeze review.
state_before: >
  PR #5889 head 59e0ac3a had accepted R3 direction (kernel re-query, root/prior/revised,
  bounded admission, tri-color walk) but Sol rejected freeze: identity tests
  rewrote source CIK to mmx.issuer.fip1; packet governance used live registry
  digest; revision extractor used child clocks and live mapping; against-input
  did not bind the full deterministic body; graph walk merged transitive leaf
  dicts; revision/extension ceilings measured after unbounded lists.
changed:
  - path: engine/fundamental_forensics/financial_intelligence_packet.py
    what: >
      EntityInput.source_entity_id binds canonical issuer to source CIK.
      Packet governance uses GovernanceBundle.content_id. expected_packet_body
      is shared by assemble and against-input. Graph validation stores only
      color/closure booleans. Revisions and extensions fail during accumulation.
  - path: engine/fundamental_forensics/raw_ledger.py
    what: lineage_ready_clocks walks the full revision ancestry on both clocks.
  - path: contracts/financial_intelligence_packet.schema.json
    what: entity.source_entity_id required; governance_bundle_id replaces live registry digest.
  - path: tests/test_fundamental_forensics_financial_intelligence_packet_r3.py
    what: Identity, future-rule, lineage, mapping, full-body tamper, accumulation tests.
  - path: tests/fixtures/fundamental_forensics/expected_financial_intelligence_packet_v1.json
    what: Regenerated golden packet after R3 final-closure semantics.
  - path: agentos/decisions/DEC-FIF-ENTITY-ID-IS-NOT-CIK.md
    what: Canonical issuer and source-native CIK are separate, explicitly bound dimensions.
  - path: agentos/decisions/DEC-FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE.md
    what: Historical packet identity is the cutoff-visible governance bundle.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: FIF-1 remains in_progress / BUILT_NOT_ACCEPTED; FIF-2 STOPPED.
decisions:
  - DEC:FIF-ENTITY-ID-IS-NOT-CIK
  - DEC:FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE
verified:
  - claim: Focused FIF packet tests including the R3 final-closure matrix pass locally after golden regen.
    command: >
      project-venv python -m pytest
      tests/test_fundamental_forensics_financial_intelligence_packet.py
      tests/test_fundamental_forensics_financial_intelligence_packet_r2.py
      tests/test_fundamental_forensics_financial_intelligence_packet_r3.py -q
    result: 60 passed
  - claim: Query, registry, raw-ledger, and import-pinning regressions pass locally.
    command: >
      project-venv python -m pytest tests/test_fundamental_forensics_query.py
      tests/test_fundamental_forensics_metric_registry.py
      tests/test_fundamental_forensics_raw_ledger.py
      tests/test_check_script_import_pinning.py::test_unpinned_entry_scripts_only_shrink -q
    result: 174 passed
  - claim: AgentOS validation reports zero errors.
    command: project-venv python scripts/agentos.py validate
    result: 0 error(s), 8 warning(s) unrelated to FIF
unverified:
  - claim: Required CI packs and fences conclude green on the amended #5889 head.
    what_would_verify: gh pr checks after push; wait for concluded packs; do not merge
unresolved:
  - Sol freeze review of amended #5889 before merge and before any FIF-2 work
  - financial_intelligence_packet.v1 freeze is pending that review
  - Fail-closed sol-review-required merge queue is a separate CI-control-plane program
next_actions:
  - Sol freeze-reviews this PR; do not merge; do not create FIF-1R4; do not start FIF-2
  - Keep merge-on-green off and GitHub native auto-merge disabled
  - Do not build the protected-review queue in this PR
do_not_redo:
  - Do not convert companyfacts_versions.json into the packet query ledger
  - Do not start FIF-2 in this PR
  - Do not replace BitemporalMetricQueryEngine, RawFactLedger, or the 50-metric registry
  - Do not rewrite source-native SEC/XBRL identity to mint a Mastermind issuer ID
  - Do not use live full-registry digest as historical packet identity
  - Do not mix a CI-control-plane redesign into FIF packet work
danger_areas:
  - Isolation keys on source_entity_id. Raw SEC/XBRL identity stays the filer CIK.
  - Packet governance identity must be the cutoff-visible bundle, not catalog_content_sha256.
  - A revision row requires the entire lineage to be knowable on both clocks.
  - Graph semantic validation must not construct transitive leaf-set unions.
---

FIF-1R3 final closure is held on PR #5889 for Sol freeze review. #5837 remains
on main and is not reverted. financial_intelligence_packet.v1 is still not
frozen. FIF-2 is not started.
