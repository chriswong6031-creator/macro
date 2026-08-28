---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/e3-a2-deterministic-qa
model: local
ended_because: complete
mission: >
  Build and prove a generic deterministic source-native Q&A reconstruction
  capability under E3-A2 only. No model calls. No live qa_exchanges write.
  Return a held draft PR to Sol. Do not start E3-B.
state_before: >
  E3-A closeout was on origin/main. This session re-pinned pickup to
  bdd8dffc18cd079dbd25e869a6b9afb910d70b2c after main moved. E3-A2 was
  todo. E3-B locked. No E3-A2 branch or PR existed at claim.
changed:
  - path: engine/company_intelligence/qa_reconstruction.py
    what: Generic Operator-go-ahead Q&A reconstruction from event/document/segments only.
  - path: tests/test_company_intelligence_qa_reconstruction.py
    what: AAPL gold structural oracle plus anti-hardcode mutation and leakage tests.
  - path: research/earnings_intelligence/e3/e3a2_aapl_fy2026_q3_reconstruction_receipt.json
    what: Bounded shadow proof receipt. Not a runtime truth store.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: E3-A2 in_progress, held for Sol; E3-B remains locked.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-23-e3a2.md
    what: This E3-A2 return handoff.
  - path: .github/ci/legacy-jobs.yml
    what: Register the new suite on the existing neural-web-core pytest line.
  - path: .github/workflows/ci.yml
    what: Path-filter the new test file so the suite cannot go dark.
prs: []
decisions:
  - DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
verified:
  - claim: origin/main pickup is bdd8dffc18cd079dbd25e869a6b9afb910d70b2c.
    command: git rev-parse origin/main
    result: bdd8dffc18cd079dbd25e869a6b9afb910d70b2c
  - claim: No colliding E3-A2 PR existed at claim time.
    command: gh pr list --search "E3-A2 OR qa_reconstruction" --state open
    result: empty
  - claim: AAPL reconstruction matches gold structure 7/26 with exchange-0 Kevan then two Tim turns.
    command: python3 -m pytest tests/test_company_intelligence_qa_reconstruction.py -q
    result: 21 passed
  - claim: Runtime module SHA is 23eccda6c6bcea2c6831709b415264b67d553ddc28f41f47933d6e5bd5403f41.
    command: python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('engine/company_intelligence/qa_reconstruction.py').read_bytes()).hexdigest())"
    result: 23eccda6c6bcea2c6831709b415264b67d553ddc28f41f47933d6e5bd5403f41
  - claim: Transcript SHA remains a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f.
    command: python3 -c "import gzip,hashlib,pathlib; print(hashlib.sha256(gzip.open('tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz').read()).hexdigest())"
    result: a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f
  - claim: Gold v2 SHA is unchanged.
    command: python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json').read_bytes()).hexdigest())"
    result: fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c
  - claim: E3-A plus A5A plus event-workspace regressions stay green.
    command: python3 -m pytest tests/test_company_intelligence_event_compiler_e3a.py tests/test_issuer_profiles_a5a.py tests/test_company_intelligence_event_workspace.py tests/test_company_intelligence_qa_reconstruction.py -q
    result: 140 passed
unverified:
  - claim: Hosted CI and fences on the draft PR have not concluded at handoff write time.
    what_would_verify: gh pr checks after the held draft is pushed
unresolved:
  - Topic labels remain UNRESOLVED / PASS_A_REFERENCE_ONLY. E3-A2 does not adjudicate topics.
  - E3-A2 is not canonically done until Sol accepts and lands the PR.
  - E3-B remains locked even if E3-A2 later lands.
  - Operator-intro identity grammar is the accepted deterministic dialect; other vendor intros may refuse.
  - Empty analyst role is the accepted analyst cue; a non-empty analyst role would currently be classified as management and should refuse or be extended in a later wave, not guessed here.
next_actions:
  - Sol reviews the held draft PR.
  - Do not merge E3-A2 in this session.
  - Do not start E3-B.
do_not_redo:
  - Do not retune Qwen full-transcript extraction to rescue [].
  - Do not copy Pass-A topics into reconstruction.
  - Do not write qa_exchanges into a live workspace from this wave.
  - Do not hardcode AAPL names, tickers, or boundary indexes in runtime reconstruction.
  - Do not start E3-B.
danger_areas:
  - E3-A2 must not be described as unlocking live publication.
  - Reconstruction is shadow/proof only; event_workspace.v1 qa_exchanges stays empty.
  - A later transcript SHA must mint new exchange IDs; do not add cross-revision matching here.
---

E3-A2 is implemented and held for Sol. It is a completed local proof of deterministic source-native Q&A structure, not a landed wave and not an E3-B unlock.
