---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude/ci-fence-e2big-closure
model: codex
ended_because: ci_handoff
prs: [6223]
discoveries:
  - "DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING"
  - "DSC:CI-SELF-MOD-FENCE-ARGV-BYPASSES-BOUNDED-TRANSPORT"
mission: >
  Repair the second production E2BIG breach in the CI control plane exposed by
  FF PR 5898 fences run 32546500471, without weakening self-modification policy,
  changing FF PR 5898, or reopening the bounded-transport architecture landed
  by PR 5608 and the semantic-proof architecture landed by PR 5750.
state_before: >
  PR 5608 had bounded the ci.yml planner-to-pack changed-files transport. FF PR
  5898 head 47d3b4b49e7191e72576ebc6e7495748ab1c8164 then produced fences run
  32546500471: the checker selftest and 58-test suite passed, but the live
  same-repository bridge expanded the changed-file and commit-message
  populations into argv, Python never started, and the process exited 126 with
  E2BIG. The fork workflow retained the same argv transport shape.
changed:
  - path: .github/workflows/fences.yml
    what: >
      Replace both live self-mod workflow copies' unbounded shell-variable and
      argv transport with canonical changed-files JSON and complete
      commit-message files, while preserving the same-repository synthetic-merge
      proof and both paths' exact attribution ranges.
  - path: scripts/check_self_mod_fence.py
    what: >
      Add a NUL-delimited Git-path producer for the existing canonical JSON file
      representation and bounded changed-files/commit-message file inputs; fail
      closed on missing, unreadable, malformed, empty, or ambiguous transport.
  - path: tests/test_self_mod_fence.py
    what: >
      Add real multi-megabyte process-launch coverage, retired-argv E2BIG
      reproduction, four-way policy parity, malformed/ambiguous input cases,
      execution of both real workflow steps, and bounded-checkout ancestry
      failure coverage.
  - path: tests/test_fence_checkout_contract.py
    what: >
      Pin both same-repository and fork workflow paths to bounded file handles,
      preserve their exact ranges, and forbid restoration of unbounded
      changed-files or commit-message argv.
  - path: agentos/discoveries/DSC-CI-SELF-MOD-FENCE-ARGV-BYPASSES-BOUNDED-TRANSPORT.md
    what: >
      Record the distinct missed-workflow-copy landmine without replacing the
      general execve-ceiling Discovery from PR 5608.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: >
      Expand W-TRANSPORT to cover the second terminal fence copy and keep the
      wave awaiting exact-head and merged/current-main proof.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-21-self-mod-fence-e2big.md
    what: >
      Give Sol/Fable a cold-start continuation packet for held PR 6223 and the
      separate post-merge rerun of unchanged FF PR 5898.
verified:
  - claim: >
      FF PR 5898 run 32546500471 failed in the live workflow-to-checker bridge
      before check_self_mod_fence.py emitted a policy verdict.
    command: >
      gh run view 32546500471 --repo mastermindx-market-intelligence/macro
      --job 96965778655 --log
    result: >
      The live step expanded --files $FILES; the shell reported Python Argument
      list too long and exit 126. The checker selftest succeeded and its suite
      reported 58 passed, isolating the production bridge.
  - claim: >
      The retired transport class now reproduces E2BIG while both repaired
      workflow copies launch with multi-megabyte changed-file and commit-message
      populations and preserve all policy classifications.
    command: >
      python3 -m pytest tests/test_self_mod_fence.py
      tests/test_fence_checkout_contract.py tests/test_ci_authority.py -q
    result: >
      136 passed after integrating main snapshot
      7cec9bb1c79419d9cd14e595a48e1e3ac405ff3e. The focused module contributes
      73 tests, including old-argv errno E2BIG, both real workflow commands,
      four-way classification parity, empty/malformed fail-closed cases, and
      missing-ancestry fail-closed behavior.
  - claim: >
      The original PR 5608 file-transport contract still passes.
    command: >
      python3 -m pytest
      tests/test_ci_pack.py::test_a_large_changed_file_list_cannot_cross_a_process_environment
      tests/test_ci_pack.py::test_the_file_transport_carries_the_list_that_e2bigs_the_environment
      tests/test_ci_plan_workflow.py::test_the_changed_file_list_never_travels_through_the_process_environment
      tests/test_ci_plan_workflow.py::test_ci_plan_publishes_the_changed_file_list_as_an_artifact
      tests/test_ci_plan_workflow.py::test_ci_pack_downloads_the_list_and_exports_only_its_path
      -q
    result: "5 passed after current-main integration."
  - claim: >
      PR 5750 semantic-proof architecture and the CI planner workflow remain
      green under the repair.
    command: >
      python3 -m pytest tests/test_ci_semantic_proof.py
      tests/test_ci_pack_semantic.py -q && python3 -m pytest
      tests/test_ci_plan_workflow.py -q
    result: "89 semantic-proof tests and 25 planner-workflow tests passed."
  - claim: >
      Trigger closure, workflow syntax, the legacy manifest, and AgentOS remain
      valid.
    command: >
      python3 scripts/check_ci_trigger_closure.py --selftest && python3
      scripts/check_ci_trigger_closure.py && python3 scripts/check_workflow_yaml.py
      .github/workflows && python3 scripts/run_ci_pack.py --workflow
      .github/ci/legacy-jobs.yml --validate-only && python3 scripts/agentos.py
      validate
    result: >
      Trigger closure reported 1,662 of 1,662 gated suites reachable and zero
      gaps; all 93 workflow files parsed; all 200 legacy jobs validated; AgentOS
      reported 511 records, zero errors, and 24 unrelated existing warnings.
  - claim: >
      The repair is isolated from Fundamental Forensics and is based on a clean
      current-main integration with no semantic conflict.
    command: >
      git merge-base --is-ancestor
      7cec9bb1c79419d9cd14e595a48e1e3ac405ff3e HEAD && git diff --name-only
      7cec9bb1c79419d9cd14e595a48e1e3ac405ff3e...HEAD
    result: >
      The ancestor check exited zero; only the seven paths named in this handoff
      differ, and none is a Fundamental Forensics path.
unverified:
  - claim: >
      PR 6223 exact-head GitHub CI and required fences conclude green and the
      same-repository live checker log contains its policy verdict rather than
      E2BIG or exit 126.
    what_would_verify: >
      Inspect all required checks and the fences live-step log on the final PR
      6223 head after this handoff commit; require checker PASS or BLOCKED output
      and no Argument list too long diagnostic.
  - claim: >
      Unchanged FF PR 5898 reaches policy evaluation under the repaired global
      control plane.
    what_would_verify: >
      After PR 6223 is reviewed, released, and merged, rerun fences against exact
      FF head 47d3b4b49e7191e72576ebc6e7495748ab1c8164 without changing that branch,
      then inspect the self-mod live log and required context.
unresolved:
  - >
    PR 6223 is draft and HOLD-FOR-SOL. The worker did not arm or merge it; only
    Sol/Fable can release the hold after exact-head review.
  - >
    W-TRANSPORT cannot become done until the repair is merged, proved on a
    current-main descendant, and unchanged FF PR 5898 reaches policy evaluation.
next_actions:
  - >
    Sol/Fable reviews PR 6223 at its exact final head, including the live
    self-mod log and required check contexts, and explicitly releases or retains
    the hold.
  - >
    After an authorized merge, rerun fences against unchanged FF PR 5898 head
    47d3b4b49e7191e72576ebc6e7495748ab1c8164 and record the policy verdict.
  - >
    Close W-TRANSPORT only on a separately proved current-main descendant after
    the repair and witness rerun are complete.
do_not_redo:
  - >
    Do not repeat PR 5608's general execve diagnosis or replace
    DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING. This incident is the
    independent fences.yml copy the earlier ci.yml repair did not cover.
  - >
    Do not put either changed paths or complete commit-message text back into
    argv, process environment, job outputs, or GITHUB_ENV. Only bounded paths or
    digests may cross process launch.
  - >
    Do not repair only the same-repository path; the fork live path carried the
    same retired transport and is pinned by the same change.
  - >
    Do not weaken the self-modification policy, ancestry checks, immutable-path
    classification, branch or trailer attribution, fail-closed behavior, or
    required check names.
  - >
    Do not modify, synchronize, rerun, arm, merge, or production-dispatch FF PR
    5898 from this worker session. Its failed run is evidence only.
danger_areas:
  - >
    The live step is continue-on-error so the aggregate can publish required
    contexts. A displayed completed step is not proof: its outcome and log must
    show that the checker actually started.
  - >
    Exit 1 from check_self_mod_fence.py can be an intended policy BLOCK, while
    shell exit 126 is a transport failure. Never treat them as equivalent.
  - >
    Changed paths are not the only unbounded input. Complete commit-message text
    crossed argv in the failing command and must remain file-backed.
  - >
    An empty changed-file population is unclassifiable and fails closed, while
    an empty commit-message file is valid because a PR may carry no Loop-Authored
    trailer.
---

## §0 State — what is true right now

Draft PR 6223 contains the bounded repair and is explicitly held for Sol/Fable.
Local regression and control-plane proof is green; exact-head GitHub proof is the
remaining worker-side evidence. FF PR 5898 was not changed or acted upon.

## §1 What is LEFT — in order

1. Inspect every required check and the self-mod live-step log on PR 6223's final
   head. Require an actual checker verdict and no E2BIG or exit 126.
2. Sol/Fable reviews the diff and explicitly decides whether to release the hold.
3. Only after an authorized merge, rerun fences against the unchanged FF 5898
   witness head and then close W-TRANSPORT on proved current main.

## §2 What will bite you

The fence live step is continue-on-error, so its visual step status can conceal
the transport failure that matters. Distinguish checker policy exit 1 from shell
transport exit 126, inspect both same-repository and fork wiring, and remember
that commit-message volume is independently unbounded even when paths are already
file-backed.

## §3 What was decided and found

- DSC:CI-SELF-MOD-FENCE-ARGV-BYPASSES-BOUNDED-TRANSPORT records the missed
  terminal workflow-copy landmine.
- No new Decision was needed: PR 6223 applies the already-ratified bounded
  transport and semantic-proof architecture.

## §4 Not in scope — do not adopt

No FF 5898 change or action, immutable-set change, attribution change,
merge-on-green redesign, CI pack/scoping optimization, branch-protection change,
or broader CI rewrite belongs in this PR. Generated AgentOS views were not edited.
