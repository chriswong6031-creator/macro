---
key: FIF-3A3-ACCEPTED-GOLDEN-QUERY-ON-MAIN
question: >
  What is the durable program state of FIF-3A3 after Sol PASS /
  ACCEPTED_FOR_LANDING and the squash-merge of PR #6352?
answer: >
  FIF-3A3 is ACCEPTED / GOLDEN QUERY CONVERGENCE PROVEN / ON_MAIN.
  FIF-1 remains DONE / FROZEN. FIF-2 remains DONE / FIXTURE_PROVEN
  SERVICE SUBSTRATE. FIF-3 remains IN_PROGRESS. FIF-3A1 remains
  ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN. FIF-3A2 remains
  ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN. Production attested
  issuer service remains NOT_BUILT. FIF-3A4 is not started by this
  closeout.
rationale: >
  Sol source-reviewed exact product head
  197f405758fdfe19be7de739c1aabfc938272c40 as PASS /
  ACCEPTED_FOR_LANDING and released HOLD-FOR-SOL on PR #6352. GitHub
  squash-merged that PR as 34ce48ec67a8697ddfbe439e9840e818c98eee70.
  The accepted capability is the existing authenticated POST
  /api/forensics/v1/financial/query serving governed AAPL values from
  the accepted A1/A2 iXBRL bytes through one ixbrl_raw_ledger.py
  adapter into canonical RawFactLedger plus the existing core registry
  and BitemporalMetricQueryEngine. That is not production issuer
  coverage and does not complete the FIF-3 five-issuer slice.
alternatives:
  - option: Mark FIF-3 done because AAPL now has statements plus governed query
    why_not: FIF-3 is the golden five-issuer vertical. One accepted AAPL query path is not the slice.
  - option: Leave FIF-3A3 as BUILT_NOT_ACCEPTED after merge
    why_not: Sol accepted the exact head and released the hold. Durable truth must follow that ruling.
  - option: Start FIF-3A4 in the same landing or records closeout
    why_not: Sol forbade FIF-3A4 work in both the product landing and this records closeout.
evidence:
  - "gh pr view 6352 --json state,mergedAt,mergeCommit,headRefOid"
  - "tests/test_fundamental_forensics_ixbrl_raw_ledger.py _LEDGER_SHA ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8"
  - "tests/test_fundamental_forensics_ixbrl_raw_ledger.py _AAPL_QUERY_RESPONSE_SHA 58972cb88f82483e86acc9d9fc3b1cbce046f466ff8665ae214909d90ab078b0"
  - "tests/test_fundamental_forensics_ixbrl_raw_ledger.py _AAPL_QUERY_HASH f8f6dc3134592c817001738cbdefb09ee1b71798ef24a8e64dc75685a6f9c7a1"
  - "gh run view 32708680140 --json conclusion,headSha"
  - "gh run view 32708680107 --json conclusion,headSha"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-24
---

FIF-3A3 is accepted on main as golden AAPL query convergence from the
accepted A1/A2 iXBRL bytes. FIF-3 is not done. Production attested
issuer service is still NOT_BUILT.
