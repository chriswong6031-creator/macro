---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-2a-query-bridge
model: local
ended_because: complete
prs: [5983]
mission: >
  Amend PR #5983 in place for Sol A–D. Stop for Sol. Do not merge. Do not
  start FIF-2B.
state_before: >
  Sol reviewed head 4cb6832edc6990919981c36180ead9a6c73cefd1 and accepted
  the FIF-2A architecture in direction. Four defects were required: instant
  periods, no live-registry metric side door, streaming 64 KiB bound, and
  fail-closed source-misbound datasets.
changed:
  - path: engine/fundamental_forensics/query_service.py
    what: Admit instant PeriodRequest; drop live registry.metric_ids gate; catch UnsupportedMetricError; fail-closed dataset identity vs ledger source/XBRL.
  - path: app/forensics.py
    what: Stream request.stream() retaining at most MAX_REQUEST_BYTES+1; provider opened only after bounded admission.
  - path: tests/test_fundamental_forensics_financial_query_service.py
    what: Instant admission, mixed duration+instant parity, future-metric cutoff stability, source-CIK misbind 503, exact 64 KiB admission.
  - path: tests/test_fundamental_forensics_financial_query_api.py
    what: HTTP mixed-period parity, lying/missing Content-Length 413, source-misbind 503, future-metric HTTP identity.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: FIF-2A BUILT_NOT_ACCEPTED pending Sol after A–D.
decisions:
  - DEC:FIF-1-V1-FROZEN
  - DEC:FIF-ENTITY-ID-IS-NOT-CIK
verified:
  - claim: Frozen FIF-1 kernel/packet files are untouched.
    command: git diff --stat HEAD -- engine/fundamental_forensics/query.py engine/fundamental_forensics/raw_ledger.py engine/fundamental_forensics/metric_registry.py engine/fundamental_forensics/financial_intelligence_packet.py engine/fundamental_forensics/synthetic_filing_package.py contracts/financial_intelligence_packet.schema.json
    result: empty
  - claim: FIF-2A service + API tests pass after A–D.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_query_service.py tests/test_fundamental_forensics_financial_query_api.py -q
    result: 78 passed
  - claim: Existing forensics API + golden packet + kernel regressions pass.
    command: python3 -m pytest tests/test_forensics_api.py tests/test_fundamental_forensics_financial_intelligence_packet.py::test_golden_packet_is_schema_valid_and_content_addressed tests/test_fundamental_forensics_query.py tests/test_fundamental_forensics_metric_registry.py tests/test_fundamental_forensics_raw_ledger.py -q
    result: 214 passed
unverified:
  - claim: Hosted ci.yml/fences on the amended head are green or only classified external reds.
    what_would_verify: gh pr checks 5983 after push
  - claim: Sol accepts the A–D amendment.
    what_would_verify: Sol review verdict
unresolved:
  - FIF-2 remains in_progress. FIF-2A is BUILT_NOT_ACCEPTED. FIF-2B is not started.
  - Production issuer packages remain FIF-3. Default provider returns 503 until then.
next_actions:
  - Sol reviews the A–D amendment on PR #5983. Do not merge until accepted.
  - Do not start FIF-2B.
do_not_redo:
  - Do not reopen frozen financial_intelligence_packet.v1 or the 63/64 lineage bound.
  - Do not create a second financial truth model or a parallel /api/financial auth plane.
  - Do not fall back to Company Facts, the nine-metric snapshot, ticker joins, or request-time SEC fetch.
  - Do not build Source Registry, bulk query, CSV/Excel, or UI in FIF-2A.
danger_areas:
  - JSONResponse would re-serialize and break X-FIF-Response-SHA256; the handler must return the adapter bytes.
  - Canonical Mastermind entity_id and SEC CIK are different; never rewrite the kernel receipt.
  - A matching canonical ID with a foreign CIK must 503, not 200 another issuer's matrix.
  - await request.body() is not a 64 KiB bound; the handler must stream.
---

FIF-2A A–D amendment on PR #5983. Architecture unchanged. Held for Sol.
FIF-2A is BUILT_NOT_ACCEPTED. It is not a production issuer service.
