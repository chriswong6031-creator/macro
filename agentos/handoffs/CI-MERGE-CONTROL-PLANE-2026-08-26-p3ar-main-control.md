---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/ci-p3ar-main-control-6351
model: codex
ended_because: ci_handoff
mission: >
  Repair the P3A trusted executor on canonical issue #6351 so planning and PC
  execution use one complete main-owned control bundle while the exact PR
  candidate remains the tested tree. Keep production ci.yml hosted and inert.
state_before: >
  PR #6481 merged P3A as 7dc0b0ddcd6dd7323a0bf9d45b4ebf6ebc785531.
  The organization runner group was then restricted to five exact main-pinned
  workflows, including trusted-ci-executor.yml, and pc-ci-1/2/3 plus pc-render-1
  were idle. Root-owned PC admission bytes were identical and hostile PR-ref
  admission was refused. The first proof run 33024021850 resolved PR #6390
  exactly but failed in hosted planning before any PC pickup.
authority: >
  Protected Sol Skillpack re-pinned at
  mastermindx-market-intelligence/Mastermind@2292ea3a933bdff405385c8fb3d6706ca4646e23;
  schema mastermind.sol_skillpack.v1, version 1.0.0 and bootstrap major 1 are
  compatible. No docs/sol_skills path changed from the earlier loaded revision.
changed:
  - path: .github/workflows/trusted-ci-executor.yml
    what: >
      Freeze a package-shaped main-owned control bundle containing the pack
      planner, semantic proof, authority/scope helpers and their audit/workflow
      source import closure, resolver, selector, monitor and receipt generator
      before candidate checkout. Publish it as a same-run artifact and invoke its
      run_ci_pack.py for hosted planning and PC execution while retaining the exact
      candidate checkout as cwd and manifest.
  - path: tests/test_trusted_ci_executor_workflow.py
    what: >
      Add regressions that require the complete control bundle, upload before
      candidate materialization, download before PC materialization, explicit
      main-owned planner/executor/monitor/receipt paths, and an isolated import plus
      real-manifest validation with no candidate control modules available. They
      reject direct invocation of the candidate scripts/run_ci_pack.py control copy.
  - path: scripts/audit_unrun_tests.py
    what: >
      Add one fail-closed MASTERMIND_TRUSTED_CI_REPO_ROOT binding used only when
      main-owned control code runs from an external bundle. The path must be
      absolute, resolve to cwd and contain .git; default in-repository behavior is
      unchanged when the variable is absent.
verified:
  - claim: The first P3A dispatch reached the intended server-side trust gate.
    command: gh run view 33024021850 --repo mastermindx-market-intelligence/macro
    result: >
      Trust gate succeeded. Resolver and exact candidate checkout succeeded for
      tested merge 078bdb7d212a3bcabea9df6ba06a6ef7bcf5ee07, subject head
      0512bd5b79443430cf72fdfc10df2051d97d17bc and base
      7a8c5f64f75c651218e39f1c7448f20c7a761a58. PC trusted-pack was skipped.
  - claim: Root cause is candidate-control displacement, not runner capacity.
    command: gh run view 33024021850 --log-failed
    result: >
      The old candidate run_ci_pack.py rejected pr_head/workflow_dispatch and no
      plan.json was emitted; selection then failed with FileNotFoundError. No
      candidate code reached a PC listener. Receipt posted to issue #6351 as
      comment 5432489158. Do not retry this run.
  - claim: The new regression failed before implementation and passes afterward.
    command: >
      python3 -m pytest -q
      tests/test_trusted_ci_executor_workflow.py::test_p3ar_freezes_and_transports_the_complete_main_owned_control_bundle;
      python3 -m pytest -q tests/test_trusted_ci_executor_workflow.py
    result: >
      First command failed at the missing complete-bundle step. An isolated-copy
      check then exposed missing transitive audit_unrun_tests/workflow_run_source
      modules; the regression was widened before those files were added. The
      complete bundle now imports outside the checkout and validates all 132 real
      manifest jobs without candidate control-module fallback.
  - claim: Copied main control performs real changed-file planning against the candidate root.
    command: >
      Copy the declared bundle to a fresh temporary directory; set
      MASTERMIND_TRUSTED_CI_REPO_ROOT to the exact checkout; invoke copied
      run_ci_pack.py in plan-only active-scope mode for HEAD versus HEAD^; invoke
      the copied selector on the emitted plan.
    result: >
      PASS. Two real changed paths selected 81 of 132 jobs across 12 packs, emitted
      plan SHA 8a36fc399c4c9018da3f2304bc6769611d93489db9e7094aeec4016a01de8b3c,
      and selected pack 0/biocatalyst-worker. The control package imported from the
      temporary artifact while repository reads bound to the exact checkout.
  - claim: Broader CI semantic regression is green except one inherited current-main gap.
    command: >
      python3.12 -m pytest -q tests/test_trusted_ci_executor_workflow.py
      tests/test_runner_policy.py tests/test_ci_canary_tools.py tests/test_ci_pack.py
      tests/test_ci_semantic_proof.py --maxfail=10
    result: >
      221 passed; test_derived_scopes_are_startable_by_the_ci_workflow alone fails
      on existing defense-rail-laws fallback engine/*.py. This branch is byte-equal
      to origin/main for ci.yml, legacy-jobs.yml, run_ci_pack.py and that test, so
      the unrelated authority-path gap is not absorbed into P3A-R.
unverified:
  - claim: P3A-R exact-head hosted CI and review are green.
    what_would_verify: Push one PR carrier from current main and conclude all required checks.
  - claim: The repaired executor completes one real PC pack with exact receipt.
    what_would_verify: >
      Merge P3A-R, re-read the five-workflow group restriction and listener census,
      then dispatch trusted-ci-executor.yml exactly once against PR #6390 and
      validate plan, fragment, resource, cache and tree identity receipts.
unresolved:
  - >
    Production P3B remains forbidden until the repaired P3A one-pack proof is
    accepted. Production ci.yml, forks, hosted control and repository visibility
    remain unchanged.
  - >
    P3B requires two useful subwaves: first make the main-owned reusable workflow
    call-capable without routing production; only after that main is proven may a
    second carrier route ordinary same-repository PR packs through @refs/heads/main.
next_actions:
  - Complete focused policy/semantic/Agent OS tests and static validation.
  - Push one P3A-R carrier on issue #6351, review exact-head CI and merge only if current.
  - Re-read server/host admission and dispatch one exact-tree proof against PR #6390.
  - If accepted, begin the separately provable P3B-A call-capability wave.
do_not_redo:
  - Do not retry run 33024021850; its failure is deterministic and fully diagnosed.
  - Do not invoke planner, verifier, monitor or receipt code from the candidate tree.
  - Do not route production ci.yml, broaden selected workflows or expose fork work in P3A-R.
  - Do not create another scheduler, queue, semantic-proof or retry plane.
danger_areas:
  - >
    The candidate manifest and candidate files remain the execution subject. Only
    the control implementation is frozen from main; replacing the candidate
    manifest with main would create false proof.
  - >
    A reusable workflow called from ci.yml inherits caller context. P3B must bind
    the exact same-repository PR caller and main-owned called-workflow server
    allowlist without accepting caller-supplied SHA, base, plan or route identity.
---
