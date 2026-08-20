---
key: LINEAR-BRANCH-AUTOLINK-CAN-FALSE-COMPLETE
claim: >
  A Linear issue identifier in a Git branch is an active native relationship input,
  so a non-completion PR can falsely project the referenced delivery issue to Done
  on merge when its relationship semantics are broader than the issue's acceptance law.
falsifier: >
  Re-run harmless native Linear↔GitHub canaries for a branch-name auto-link, a
  relation-only link, a non-closing link, and skip/ignore suppression; this claim is
  false if branch issue identifiers do not auto-link/status-transition under the
  configured workflow or if relation/suppression cannot prevent the merge transition.
so_what: >
  Future sessions must use a delivery issue's branch identifier only for PRs whose
  merge legitimately completes that object; architecture/source-law/research/evidence
  PRs use their own issue/branch or relation/non-closing linkage, and an unavoidable
  wrong branch-ID link uses documented skip/ignore suppression before merge.
kind: landmine
verified_at: 2026-08-20
verified_by: >
  Live MAS-48/#91 and MAS-75/#96 Linear status histories plus Linear GitHub docs
  https://linear.app/docs/github reviewed 2026-08-20
scope:
  - macro
  - Mastermind
  - MAS-67
  - MAS-48
  - MAS-75
  - Linear↔GitHub portfolio projection
confidence: verified
---

## Evidence

- **MAS-48 / Mastermind #91:** MAS-48 is a multi-wave production program whose stop
  condition requires a real Personal-Pro Sol Slack→Executive→ACK→MCP canary. The
  records-only #91 architecture merge transiently projected MAS-48 to `Done`; Sol
  restored it to `In Progress` because the production capability was not shipped.
- **MAS-75 / Mastermind #96:** MAS-75 is the runtime PR-A implementation issue. The
  records-only #96 merge changed exactly three research files and zero runtime/config/
  test/workflow files, yet Linear moved MAS-75 to `Done` and populated completion state.
  Sol restored it to `Todo` because zero implementation code/PR existed.
- Linear's official GitHub documentation says issue IDs in branch names auto-link PRs,
  distinguishes closing, non-closing and relation wording, and documents `skip`/`ignore`
  suppression when branch-name auto-linking must be prevented.

## Operational warning

Do not infer semantic completion from a linked GitHub merge without checking whether the
PR is actually completion-bearing for that Linear object. A false `Done` is a projection
defect, not evidence the feature or gate completed.

Do not repair this by disabling the native GitHub integration or creating a custom lifecycle
store. The native relationship vocabulary is expressive enough; the correction is authoring/
linkage discipline plus regression proof under MAS-67. The exact operating amendment is
`research/MASTERMIND_LINEAR_PR_LINKAGE_COMPLETION_AMENDMENT_2026-08-20.md`.
