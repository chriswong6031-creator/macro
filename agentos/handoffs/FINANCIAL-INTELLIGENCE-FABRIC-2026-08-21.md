---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-2b-revision-history
model: local
ended_because: ci_handoff
prs: []
mission: >
  Ship FIF-2B authenticated POST /api/forensics/v1/financial/revisions as a
  thin projection of frozen assemble_financial_intelligence_packet revisions.
  Do not alter FIF-1. Do not start FIF-2C. Hold merge for Sol.
state_before: >
  FIF-1 DONE/FROZEN. FIF-2 IN_PROGRESS. FIF-2A ACCEPTED/ON_MAIN via PR #5983
  merge 0ea6a2524c74211e06709f04116b74f3dd5c444f. FIF-2B UNLOCKED/NOT_STARTED.
changed:
  - path: engine/fundamental_forensics/query_service.py
    what: Shared admit_financial_request for query and revisions; export validate_supplied_dataset.
  - path: engine/fundamental_forensics/revision_service.py
    what: Packet-build provider + execute_financial_revisions projecting packet["revisions"] exactly.
  - path: app/forensics.py
    what: Shared JSON body admission; POST /api/forensics/v1/financial/revisions on the existing router.
  - path: tests/test_fundamental_forensics_financial_revision_service.py
    what: Direct packet equality, T2/T3, multi-hop, relevance, misbind, #5983 hashes.
  - path: tests/test_fundamental_forensics_financial_revision_api.py
    what: Auth/private headers, SHA, 413, default 503.
  - path: tests/test_forensics_api.py
    what: Mount revisions on production OpenAPI and paid-path inventory.
  - path: .github/ci/legacy-jobs.yml
    what: Additive FIF-2B suite registration in the existing Fundamental Forensics step.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: FIF-2B BUILT_NOT_ACCEPTED; FIF-2C NOT_STARTED.
decisions:
  - DEC:FIF-1-V1-FROZEN
  - DEC:FIF-REVISION-ROOT-PRIOR-REVISED
  - DEC:FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE
  - DEC:FIF-ENTITY-ID-IS-NOT-CIK
verified:
  - claim: FIF-2B service + API tests plus FIF-2A regressions pass on this tree.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_revision_service.py tests/test_fundamental_forensics_financial_revision_api.py tests/test_fundamental_forensics_financial_query_service.py tests/test_fundamental_forensics_financial_query_api.py tests/test_forensics_api.py tests/test_fundamental_forensics_financial_intelligence_packet.py::test_golden_packet_is_schema_valid_and_content_addressed tests/test_fundamental_forensics_query.py tests/test_fundamental_forensics_metric_registry.py tests/test_fundamental_forensics_raw_ledger.py -q
    result: 323 passed
  - claim: Frozen FIF-1 kernel/packet/schema files empty-diff vs origin/main.
    command: git diff --stat origin/main -- engine/fundamental_forensics/query.py engine/fundamental_forensics/raw_ledger.py engine/fundamental_forensics/metric_registry.py engine/fundamental_forensics/financial_intelligence_packet.py engine/fundamental_forensics/synthetic_filing_package.py contracts/financial_intelligence_packet.schema.json
    result: empty
  - claim: FIF-2B collected 30 focused tests.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_revision_service.py tests/test_fundamental_forensics_financial_revision_api.py --collect-only -q
    result: 30 tests collected
  - claim: AgentOS validate exits 0 on FIF records.
    command: python3 scripts/agentos.py validate
    result: 0 error(s)
unverified:
  - claim: Hosted ci.yml and fences.yml conclude on the FIF-2B head.
    what_would_verify: gh pr checks after push
unresolved:
  - FIF-2 remains in_progress. FIF-2B is BUILT_NOT_ACCEPTED pending Sol.
  - FIF-2C is NOT_STARTED.
  - Production issuer packages remain FIF-3. Default packet provider returns 503.
next_actions:
  - Sol source-review this PR. Do not merge until accepted.
  - Do not start FIF-2C from this session.
do_not_redo:
  - Do not reopen frozen financial_intelligence_packet.v1 or the 63/64 lineage bound.
  - Do not reconstruct revision semantics in the HTTP adapter.
  - Do not overload the FIF-2A query provider with filesystem discovery.
  - Do not claim production issuer revision coverage.
  - Do not arm merge-on-green or GitHub native auto-merge before Sol accepts.
danger_areas:
  - JSONResponse would re-serialize and break X-FIF-Response-SHA256.
  - Canonical Mastermind entity_id and SEC CIK are different; never rewrite packet revisions.
  - Multi-hop hop C requires source_snapshot_at 2026-08-05T12:00:02Z, not T3_SOURCE 2025-12-31.
  - Current-main .github/ci/legacy-jobs.yml must be preserved in full; only FIF-2B suite registrations are additive.
---

FIF-2B ships authenticated revision-history read as a thin projection of the
frozen FIP assembler. FIF-1 remains DONE / FROZEN. FIF-2A remains ACCEPTED.
FIF-2 is not done. Hold for Sol. Do not start FIF-2C.
