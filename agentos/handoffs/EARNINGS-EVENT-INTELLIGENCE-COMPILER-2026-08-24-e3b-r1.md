---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/e3b-aapl-live-qa
model: local
ended_because: ci_handoff
mission: >
  Repair Sol REQUEST_CHANGES on the same two E3-B carriers. Close Macro
  CI/public-regression and harden canonical Q&A/transcript-clock binding.
  Harden Terminal clock rejection and Q&A/transcript revision binding,
  produce fixture browser proof, and obtain a green exact-head hosted
  check. Keep draft + hold + do-not-merge. No deploy. E3-C stays closed.
state_before: >
  Sol REQUEST_CHANGES on Terminal #470 @ e44432f629dc5e1f25e3ec0bff87263961fd0cc5
  and Macro #6376 @ 622160d2beefa214f69a86354e43361bc712f5df. Architecture
  passed; remaining defects were trust-boundary, CI wiring, glance
  regression, and missing browser proof. SOURCE_CLOCK_OWNER_GAP is a
  named limitation, not a block on unknown clocks.
changed:
  - path: .github/ci/legacy-jobs.yml
    what: Reconciled current main, then wired tests/test_company_intelligence_qa_exchange.py into the existing neural-web-core pytest line.
  - path: .github/workflows/ci.yml
    what: Added the new Q&A suite to the neural-web-core path filter.
  - path: tests/test_company_intelligence_api.py
    what: Glance leak-denylist now asserts 7 exchanges for accepted Q&A; new empty-Q&A case still expects unstructured/absence.
  - path: engine/company_intelligence/qa_exchange.py
    what: Closed identity states; unknown clock cannot carry a timestamp; named SOURCE_CLOCK_OWNER_GAP; actual span uniqueness/disjointness.
  - path: engine/company_intelligence/event_workspace.py
    what: Parent workspace cross-binds accepted Q&A to the byte-replayed transcript source/clock.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: E3-B next_action records REQUEST_CHANGES repair on the same carriers; E3-C remains locked.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-24-e3b-r1.md
    what: This REQUEST_CHANGES repair return.
prs:
  - 6376
decisions:
  - DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
verified:
  - claim: neural-web-core vs current origin/main only adds the new Q&A suite to the existing pytest line.
    command: git diff origin/main -- .github/ci/legacy-jobs.yml
    result: single insertion of tests/test_company_intelligence_qa_exchange.py after qa_reconstruction
  - claim: Glance accepted-Q&A state is 7 exchanges; empty Q&A remains unstructured; leak denylist retained.
    command: python3 -m pytest tests/test_company_intelligence_api.py::test_event_workspace_glance_200_and_leak_denylist tests/test_company_intelligence_api.py::test_event_workspace_glance_empty_qa_stays_unstructured tests/test_company_intelligence_qa_exchange.py -q
    result: 27 passed
unverified:
  - claim: Hosted Macro neural-web-core on the new exact head had not concluded at handoff write time.
    what_would_verify: gh pr checks 6376 after push
unresolved:
  - SOURCE_CLOCK_OWNER_GAP remains; lawful unknown is clock_state=unknown + source_available_at=null. Do not fabricate a timestamp.
  - E3-C remains locked.
  - Production AAPL rebuild/proof waits on Sol landing authorization.
next_actions:
  - Sol landing review of the repaired exact heads. Order if authorized: Terminal first, Macro second, then production AAPL rebuild/proof.
  - Do not merge, deploy, or start E3-C.
do_not_redo:
  - Do not open replacement PRs.
  - Do not invent source_available_at or a new clock store.
  - Do not waive the new Q&A suite out of neural-web-core.
  - Do not start E3-C.
danger_areas:
  - Unknown clocks must not be replaced by generated_at or processing time.
  - Accepted Q&A must stay bound to the byte-replayed transcript document ID/SHA and to that clock or explicit unknown/null.
---

E3-B stays held on the same two carriers. Macro's REQUEST_CHANGES repairs are the CI owner-lane wiring, the glance 7-exchanges/empty-unstructured pair, and the canonical validator/transcript-clock cross-bind. SOURCE_CLOCK_OWNER_GAP is preserved.
