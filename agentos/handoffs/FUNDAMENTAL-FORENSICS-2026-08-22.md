---
workstream: WS:FUNDAMENTAL-FORENSICS
session: codex/ff1p2r-closeout
model: codex
ended_because: complete
mission: >
  Commission FF-1P2R current-quarter EDGAR-index discovery through two
  production runs, record the parquet-derived universe law, and reconcile
  completed CI prerequisites without starting FF-1R or FF-2.
state_before: >
  #5898 was merged but FF-1P2R remained BUILT_NOT_PROVEN in AgentOS. Run A had
  completed safely with a 2,841-name canonical census but awaited Sol's
  correction of the frozen 2,837 expectation. W-TRANSPORT and
  W-PR-EVENT-CAUSALITY still carried stale awaiting_ci state.
changed:
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: >
      Record FF-1P2R PROVEN_LIVE, retain FF-1 partial / in progress, and keep
      FF-1R, previous-quarter reconciliation, and FF-2 unstarted.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: >
      Close only W-TRANSPORT and W-PR-EVENT-CAUSALITY with merged and exact-run
      receipts; preserve every adjacent wave.
  - path: agentos/decisions/DEC-FF-1-UNIVERSE-BIND-CAP-4000.md
    what: >
      Mark the prior decision record superseded by a complete successor whose
      only substantive rule change is removal of its historical literal 2,837
      census premise.
  - path: agentos/decisions/DEC-FF-1-UNIVERSE-CENSUS-IS-PARQUET-DERIVED.md
    what: >
      Make the canonical census parquet-derived while re-adopting every safety,
      recovery, and FF-2 boundary.
prs: [5898, 6223, 6252]
verified:
  - claim: >
      #5898 is merged and the Run B tested main is a descendant of its merge.
    command: >
      gh pr view 5898 --repo mastermindx-market-intelligence/macro --json
      state,mergeCommit && git merge-base --is-ancestor
      21f51a1ecfed778a738b048bd7e5efd30b1d9336
      0954c8354b78f18f26b6cab41ced50f90653bb74
    result: >
      MERGED as 21f51a1ecfed778a738b048bd7e5efd30b1d9336; ancestry
      exit 0.
  - claim: >
      Run A established a complete canonical baseline without issuer fanout.
    command: >
      gh run view 32604043860 --repo mastermindx-market-intelligence/macro
      --json conclusion,event,headSha,url,jobs && gh run view 32604043860
      --job 97106386087 --log; extract the final canonical receipt JSON line
      and run printf '%s\n' "$json" | shasum -a 256
    result: >
      success workflow_dispatch at 21f51a1ecfed778a738b048bd7e5efd30b1d9336;
      run_4e7970fb7cb841b6671d; baseline=true; canonical census
      2,841/2,841/2,841 with expected=observed=2,841 and failures=0;
      affected/Submissions/Company Facts=0/0/0; universe content sha256
      6d8089bf787852d083ea0461638236df6e2c678721f682b2e9b3566933af4269;
      index archive/member/snapshot/relevant-set sha256 values
      15e3d951c87f463064507ea49086024ce8947e8cf9b14a2631a318350a4e5ecb /
      88a4f5d62068cbab307059ae9d1a8ce03cda8f569d6c56cc76d9256570bc9e2d /
      7d518fd55dcf88bcec4d5a1cc7e04cde245c6c3d2b75fa52effc87965c82913a /
      65010952763c2deabf4aeb41af2900787cfae23eb9c1159297fd707ae9ad1cd4;
      receipt
      fundamental_forensics/broad-sec/v1/runs/run_4e7970fb7cb841b6671d/receipt.json
      sha256 4640f1c58cd7baf31f0887dbc5f44e64ba8149592d375c51b4e21dce00cab71f;
      observation
      fundamental_forensics/broad-sec/v1/runs/run_4e7970fb7cb841b6671d/issuer-observations.json.gz
      sha256 49eb03e5fc34cddc143dfa9117f5275beb5eaf92f33db21dd21dbaed56ac4a77;
      finalize complete=1 and successful exit prove latest-complete advanced
      after the immutable observation, receipt, and latest-observation writes
      under the same conditional-write and exact-readback path verified below.
  - claim: >
      Run B completed the quiet incremental acceptance branch on an unchanged
      FF implementation and canonical universe.
    command: >
      gh run view 32605564919 --repo mastermindx-market-intelligence/macro
      --json conclusion,event,headSha,url,jobs && gh run view 32605564919
      --job 97109992561 --log && git diff --name-only
      21f51a1ecfed778a738b048bd7e5efd30b1d9336..0954c8354b78f18f26b6cab41ced50f90653bb74
      -- engine/fundamental_forensics collectors/edgar_forensics.py
      scripts/run_fundamental_forensics_broad_sec.py
      .github/workflows/filing-forensics-broad-sec.yml
      contracts/fundamental_forensics_broad_sec_run.schema.json
      data/edgar/fundamentals.parquet; extract the final canonical receipt JSON
      line and run printf '%s\n' "$json" | shasum -a 256; sed -n
      '610,650p;2075,2140p' engine/fundamental_forensics/broad_sec_store.py
    result: >
      success workflow_dispatch at 0954c8354b78f18f26b6cab41ced50f90653bb74
      on mac-builder-3; no scoped diff; run_8583eb7ce7476290c0b2;
      baseline=false; one Q3 index acquisition; 2,627 unchanged relevant rows;
      new/corrections/affected/Submissions/Company Facts=0/0/0/0/0;
      canonical=true; issuer/ticker/CIK=2,841/2,841/2,841;
      expected/observed/failed=2,841/2,841/0; failures=[]; complete;
      source-accepted clock stayed null while archive_retrieved_at advanced to
      2026-08-22T23:34:37Z; universe content sha256
      6d8089bf787852d083ea0461638236df6e2c678721f682b2e9b3566933af4269;
      index archive/member/snapshot/relevant-set sha256 values remained
      15e3d951c87f463064507ea49086024ce8947e8cf9b14a2631a318350a4e5ecb /
      88a4f5d62068cbab307059ae9d1a8ce03cda8f569d6c56cc76d9256570bc9e2d /
      7d518fd55dcf88bcec4d5a1cc7e04cde245c6c3d2b75fa52effc87965c82913a /
      65010952763c2deabf4aeb41af2900787cfae23eb9c1159297fd707ae9ad1cd4;
      receipt
      fundamental_forensics/broad-sec/v1/runs/run_8583eb7ce7476290c0b2/receipt.json
      sha256 a1e2858d7ee0e4a45502a340efe3146a1ffc2604e603839f7ec4bfe9fdc992d4;
      observations sha256 852e09c28559fa4f1e87e6d048b3bd640a1210d5470ebbdf428f9a77d1cc53be;
      the successful code path reached finalize complete=1, wrote immutable
      observation and receipt, then latest-observation, then latest-complete
      last. Each pointer write is conditional and read back exactly; a CAS or
      readback failure returns exit 1, so the successful job proves the
      latest-complete pointer advanced to this complete head.
  - claim: >
      W-TRANSPORT and W-PR-EVENT-CAUSALITY have merged and live proof receipts.
    command: >
      gh pr view 6223 --repo mastermindx-market-intelligence/macro --json
      state,mergeCommit && gh run view 32602516677 --repo
      mastermindx-market-intelligence/macro --json conclusion,headSha,url &&
      gh pr view 6252 --repo mastermindx-market-intelligence/macro --json
      state,mergeCommit && gh run view 32593286806 --repo
      mastermindx-market-intelligence/macro --json conclusion,headSha,url &&
      gh run view 32593286723 --repo mastermindx-market-intelligence/macro
      --json conclusion,headSha,url && gh run view 32593286769 --repo
      mastermindx-market-intelligence/macro --json conclusion,headSha,url
    result: >
      #6223 MERGED as bc0a9cd896401fae7ec19a208b3a5017cc8d13a6;
      fresh #5898 fences 32602516677 reached the file-backed checker and
      returned PASS without E2BIG or exit 126. #6252 MERGED as
      27711c21665788bb9804b05b03a2587860679646; CI 32593286806,
      fences 32593286723, and active ci-authority/main 32593286769 all
      concluded success on exact subject 004452e517ca277596008ab3623beca3f707fa33.
unverified: []
decisions:
  - DEC:FF-1-UNIVERSE-CENSUS-IS-PARQUET-DERIVED
discoveries: []
unresolved:
  - >
    FF-1R July recovery remains NOT_STARTED / NOT_COMMISSIONED; previous-quarter
    weekly reconciliation remains SPEC_ONLY / NOT_BUILT.
next_actions:
  - >
    Do not start FF-1R without a separate Sol-approved recovery commission that
    selects the population before acquisition.
  - >
    Do not start FF-2 until the full FF-1 scope, not merely FF-1P2R, is complete
    and production-proven.
do_not_redo:
  - >
    Do not restore per-issuer nightly discovery, submissions.zip,
    companyfacts.zip, a fixed 2,837 universe, or the failed 8-to-5-to-2
    recovery shape.
  - >
    Do not reopen W-TRANSPORT or W-PR-EVENT-CAUSALITY to redesign CI,
    lifecycle cancellation, or Fundamental Forensics.
danger_areas:
  - >
    The 4,000 cap survives. Parquet-derived census semantics do not mean
    unbounded acquisition.
  - >
    FF-1P2R PROVEN_LIVE does not authorize recovery, previous-quarter
    reconciliation, or FF-2.
---

## 0. State

FF-1P2R is PROVEN_LIVE after Run A and Run B. FF-1 remains in progress because
the delivered current-quarter discovery capability does not include July
recovery or previous-quarter reconciliation. FF-2 remains forbidden.

## 1. What is left

Nothing remains in this closeout. Any FF-1R recovery, previous-quarter
reconciliation, or FF-2 work requires a separate bounded Sol commission.

## 2. What will bite you

The canonical universe is the execution identity's parquet, not a fixed count.
Every run must still prove canonical validation, rows == unique tickers ==
unique CIKs == expected == observed, immutable provenance, and count <= 4,000.

## 3. What was decided and found

DEC:FF-1-UNIVERSE-CENSUS-IS-PARQUET-DERIVED is the complete active successor
to the older census decision. Its only substantive rule change is removal of
the old literal 2,837 premise; it re-adopts every remaining safety and scope
rule. Existing transport and PR-event discoveries already record the CI
landmines, so no duplicate Discovery was minted.

## 4. Not in scope

No FF implementation, workflow, parquet, recovery state, FF-1R,
previous-quarter reconciliation, FF-2, Capital Structure, Prophet, render
product, or CI capability changed in this records-only closeout.
