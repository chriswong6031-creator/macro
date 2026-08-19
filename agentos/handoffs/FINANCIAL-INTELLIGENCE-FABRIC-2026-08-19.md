---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-2a-query-bridge
model: local
ended_because: complete
prs: []
mission: >
  Ship FIF-2A only: POST /api/forensics/v1/financial/query as an authenticated
  adapter over the frozen MetricMatrix kernel. Stop for Sol review. Do not
  start FIF-2B.
state_before: >
  FIF-1 DONE / financial_intelligence_packet.v1 FROZEN on main at
  f4183edade53603fad7a97f702eb4c6e5eabff5d (PR #5889, DEC:FIF-1-V1-FROZEN).
  FIF-2 was UNLOCKED / NOT_STARTED.
changed:
  - path: engine/fundamental_forensics/query_service.py
    what: Thin non-HTTP adapter — admit request, bind canonical issuer to source identity, invoke BitemporalMetricQueryEngine, return canonical envelope of exact MetricMatrix.to_dict().
  - path: app/forensics.py
    what: POST /api/forensics/v1/financial/query on the existing private router, plus a private 405 for other methods.
  - path: tests/test_fundamental_forensics_financial_query_service.py
    what: Service-layer admission, T0–T3 / three-policy parity, identity, determinism, 50×8 size, no-network/no-write.
  - path: tests/test_fundamental_forensics_financial_query_api.py
    what: Auth/entitlement, private headers, HTTP==direct receipt, 400/413/503/405, SHA header.
  - path: tests/test_forensics_api.py
    what: OpenAPI path plus GET 401 mount inventory for the new route.
  - path: .github/ci/legacy-jobs.yml
    what: Register the two new pytest files in the existing Fundamental Forensics step.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: FIF-2 in_progress; FIF-2A fixture_proven and held for Sol; FIF-2B not started.
decisions:
  - DEC:FIF-1-V1-FROZEN
  - DEC:FIF-ENTITY-ID-IS-NOT-CIK
verified:
  - claim: Frozen FIF-1 kernel/packet files are untouched.
    command: git diff --stat HEAD -- engine/fundamental_forensics/query.py engine/fundamental_forensics/raw_ledger.py engine/fundamental_forensics/metric_registry.py engine/fundamental_forensics/financial_intelligence_packet.py engine/fundamental_forensics/synthetic_filing_package.py contracts/financial_intelligence_packet.schema.json
    result: empty
  - claim: Golden packet still reproduces accepted identity.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_intelligence_packet.py::test_golden_packet_is_schema_valid_and_content_addressed -q
    result: 1 passed; packet_id fip_18e2f725f6ba20678d0612bb
  - claim: FIF-2A service + API + existing forensics API tests pass.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_query_service.py tests/test_fundamental_forensics_financial_query_api.py tests/test_forensics_api.py -q
    result: 106 passed
  - claim: 50×8 FIP1 envelope is under the 8 MiB transport ceiling.
    command: pytest tests/test_fundamental_forensics_financial_query_service.py::test_fip1_max_envelope_under_8mib -s
    result: FIP1 50×8 envelope size 1184246 bytes (1.13 MiB)
  - claim: HTTP receipt equals direct MetricMatrix.to_dict() for as_reported, latest_known_as_of, and latest_restated.
    command: pytest tests/test_fundamental_forensics_financial_query_api.py::test_http_receipt_equals_direct_matrix_for_each_policy tests/test_fundamental_forensics_financial_query_service.py -q -k "t0 or t1 or t2 or t3 or as_reported or latest_restated or receipt_equals"
    result: parametrized HTTP parity plus T0 missing / T1 1050 / T2 1050 no-1060 / T3 1060; as_reported 1050; latest_restated T2 missing T3 1060
  - claim: Default production provider is unavailable (503), not an empty 200 grid.
    command: pytest tests/test_fundamental_forensics_financial_query_api.py::test_default_unavailable_provider_returns_503 -q
    result: 1 passed
unverified:
  - claim: Hosted ci.yml on the FIF-2A PR is green or only carries classified main-owned reds.
    what_would_verify: gh pr checks after the PR exists
  - claim: Sol accepts FIF-2A.
    what_would_verify: Sol freeze/review verdict
unresolved:
  - FIF-2 remains in_progress. FIF-2B (statements/revisions/trace/packet-read) is not started.
  - Production issuer packages remain FIF-3. Default provider returns 503 until then.
  - Unrelated main CI pack reds (qledger, Prophet, ticker, theme, merge-control) stay with those owners.
next_actions:
  - Sol reviews this FIF-2A PR. Do not merge until accepted.
  - Do not start FIF-2B in the review-hold session.
  - After acceptance, land via merge-on-green / concluded-green squash-merge, then verify the route on the live API.
do_not_redo:
  - Do not reopen frozen financial_intelligence_packet.v1 or the 63/64 lineage bound.
  - Do not create a second financial truth model or a parallel /api/financial auth plane.
  - Do not fall back to Company Facts, the nine-metric snapshot, ticker joins, or request-time SEC fetch.
  - Do not build Source Registry, bulk query, CSV/Excel, or UI in FIF-2A.
danger_areas:
  - JSONResponse would re-serialize and break X-FIF-Response-SHA256; the handler must return the adapter bytes.
  - Canonical Mastermind entity_id and SEC CIK are different; never rewrite the kernel receipt.
  - A provider that ignores entity_id must 503, not 200 a different issuer's receipt.
  - Starlette's default 405 has no private headers; wrong-method handlers must stay on the router.
---

FIF-2A is the first consumer of the frozen kernel: one authenticated,
bounded, point-in-time query that returns the existing MetricMatrix
receipt. It is fixture-proven. It is not a production issuer service.
