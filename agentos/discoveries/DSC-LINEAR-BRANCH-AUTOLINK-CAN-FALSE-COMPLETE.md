---
key: LINEAR-BRANCH-AUTOLINK-CAN-FALSE-COMPLETE
discovered: 2026-08-20
scope: Mastermind-X Linear↔GitHub portfolio projection
claim: >
  A Linear issue identifier in a Git branch is an active native relationship input,
  not neutral traceability metadata. When a records-only architecture/source-law PR
  reuses a delivery issue's identifier, Linear's configured PR workflow can project
  that delivery issue to Done on merge even though its semantic acceptance condition
  remains unmet.
evidence:
  - >
    MAS-48 was a multi-wave production program whose stop condition required a real
    Personal-Pro Sol Slack→Executive→ACK→MCP canary. Records-only Mastermind PR #91
    merged architecture and Linear transiently projected MAS-48 to Done before Sol
    restored it to In Progress.
  - >
    MAS-75 was the runtime PR-A implementation issue. Records-only Mastermind PR #96
    changed exactly three research files and zero runtime/config/test/workflow files;
    on merge Linear moved MAS-75 to Done and populated completedAt despite zero
    implementation code/PR. Sol restored MAS-75 to Todo.
  - >
    Linear's current official GitHub documentation at https://linear.app/docs/github
    states that issue IDs in branch names auto-link PRs, distinguishes closing,
    non-closing and relation magic words, and documents skip/ignore suppression when
    branch-name auto-link must be prevented.
impact: >
  A technically accurate GitHub merge can create a false-green executive portfolio if
  native relationship semantics are broader than the PR's actual completion authority.
  This can make architecture look shipped, hide production/CEO/operator gates, and cause
  future agents to start downstream work prematurely.
correction: >
  Preserve Linear as projection. Use the delivery issue's branch ID only for a PR whose
  merge legitimately completes that Linear object. Use non-closing or relation-only
  linkage for contributing/architecture/evidence PRs; preferably give such work its own
  Linear object/branch. If the wrong issue ID is already embedded in the branch, use
  Linear's documented skip/ignore suppression and verify it survives later push + merge.
  The exact law is research/MASTERMIND_LINEAR_PR_LINKAGE_COMPLETION_AMENDMENT_2026-08-20.md.
affects:
  - DEC:LINEAR-IS-PORTFOLIO-PROJECTION-NOT-CANONICAL
  - research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md
  - research/MASTERMIND_LINEAR_PR_LINKAGE_COMPLETION_AMENDMENT_2026-08-20.md
  - MAS-67
  - MAS-48
  - MAS-75
confidence: high
---

## Operational warning

Do not infer `Done` from a linked merge without checking whether that PR was actually
completion-bearing for that Linear object. Native Linear status is a useful projection but
must be corrected when its relationship metadata disagrees with the canonical acceptance
law.

Do not repair this by disabling the GitHub integration or creating a custom lifecycle store.
The native relationship vocabulary is expressive enough; the defect is authoring/linkage
discipline plus missing regression proof.
