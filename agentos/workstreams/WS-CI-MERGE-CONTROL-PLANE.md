---
key: CI-MERGE-CONTROL-PLANE
title: CI + merge control-plane recovery (the 2026-08 traffic jam)
objective: >
  A PR loop where ordinary changes validate quickly, structural mistakes red
  in minutes, armed PRs merge without babysitting, and a fast-moving producer
  main cannot re-prove the universe — with no transport in the pipeline that
  an unbounded changed-file list can kill.
status: active
program: project-active-build-control
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: open
decisions:
  - "DEC:CI-EXECUTION-PROFILE-V2"
discoveries:
  - "DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING"
  - "DSC:GITHUB-CONCURRENCY-SUPERSEDES-PENDING"
  - "DSC:PR-EVENT-DELIVERY-IS-NOT-CANDIDATE-IDENTITY"
  - "DSC:CI-SELF-MOD-FENCE-ARGV-BYPASSES-BOUNDED-TRANSPORT"
  - "DSC:CLAUDE-TASK-WAKES-OUTLIVE-TERMINAL-SHIP-STATES"
waves:
  - id: W-TRANSPORT
    title: Bounded changed-files transport across CI and self-mod fences
    status: done
    pr: [5608, 6223]
    note: >
      PR #5608 landed bounded planner-to-pack changed-file transport. PR #6223
      merged as bc0a9cd896401fae7ec19a208b3a5017cc8d13a6 and moved both
      same-repository and fork self-mod populations into files while
      preserving exact ancestry/range proof. The original #5898 fences run
      32546500471 failed before Python started with E2BIG. The authorized
      tree-preserving #5898 refresh kept the reviewed tree, and fences run
      32602516677 invoked the live checker through bounded file handles,
      emitted the actual PASS policy verdict, and showed no E2BIG or exit 126.
      #5898 then merged as 21f51a1ecfed778a738b048bd7e5efd30b1d9336;
      current main contains both repairs. No policy weakening, parallel
      transport, or separate runner path was introduced. W-TRANSPORT is done.
  - id: W-REWRITE
    title: Structural rewrite of planner/merge control plane
    status: in_progress
    note: >
      Two lineages collided 2026-08-14: PR 5585 (claude — API diff, plan
      consumption, wake diet) was closed in a reconciliation naming PR 5591
      (codex — authority plan artifact, committed scope index, evidence
      chain) canonical. PR 5591 was closed unmerged on 2026-08-15 and is now
      historical archaeology only; it carried the E2BIG defects this
      workstream's W-TRANSPORT fixed on main. Any successor must preserve the
      bounded transport — the wiring pins enforce it.
  - id: W-SEMANTIC-PROOF
    title: Semantic CI proof identity and ancestry-valid healing
    status: done
    note: >
      CEO V2 semantic proof landed through PR 5750 as
      064ebd53a9de3cd0fcc3eb813e634f30106eed03 on 2026-08-15. Current main
      b2938ee302e16654de2858e820877cad096f2446 is a verified descendant. Main
      semantic-producer run 31890203055 on descendant
      719b13774da34e518da57591f2cf940cbe9c856c emitted
      ci.semantic_evidence.v1 with status=clear for 194 jobs and no
      infrastructure findings; merge-on-green consumer run 31892639093 then
      completed successfully on that same merged head. Downstream merged-head
      consumer fixes PR 5756 / 0e84abd736d0 and PR 5757 / 5c253e21b4f7 also
      passed their exact-head semantic CI runs 31894942765 and 31896763803.
      Execution packs remain transport only; shared semantic identity,
      exact-base causality, complete accounting, infrastructure refusal,
      ancestry-valid monotone healing, authority self-excuse refusal, and
      ProofFreshness remain the governing contract. PR 5591 remains historical
      W-REWRITE archaeology only; completing this wave does not commission or
      complete W-REWRITE or any CI-speed/scoping wave.
  - id: W-PR-EVENT-CAUSALITY
    title: Candidate authority and lifecycle-event causality closure
    status: done
    pr: 6252
    note: >
      PR #6252 closed both causality races and merged as
      27711c21665788bb9804b05b03a2587860679646. Candidate authority no
      longer treats mutable same-ref live-base equality as candidate identity,
      while semantic CI remains the sole exact synthetic-merge/base proof;
      `closed` no longer enters the PR proof trigger or concurrency slot, so
      only opened, synchronize, and reopened produce proof. Exact-head evidence
      is semantic CI 32593286806, fences 32593286723, and ci-authority
      32593286769, all successful on subject 004452e517ca277596008ab3623beca3f707fa33.
      Current main contains the merge. No replacement cancellation service,
      semantic-proof weakening, or Fundamental Forensics change was introduced.
      Evidence: DSC:PR-EVENT-DELIVERY-IS-NOT-CANDIDATE-IDENTITY.
  - id: W-GATE-SPLIT
    title: Merge gate tests code against fixtures; data receipts post-nightly
    status: in_progress
    note: >
      Root cause DSC:MERGE-GATE-IS-GATED-ON-MOVING-DATA (main green 44%
      because 130-by-heuristic / 74-by-judgment of 194 merge-gate jobs assert
      on the nightly-rewritten tree). W1 merged 2026-08-19 as PR 5954: every
      legacy job declares gate: code | data (120/74; judgment pass over every
      named suite; decisive discriminator = git authorship of the asserted
      file). W2 MERGED 2026-08-19 10:58Z as PR 5969: ci.yml plans/packs --gate code everywhere
      (baselines prove exactly what the gate runs; the planner fallback is
      gated too), gate: data jobs run in .github/workflows/data-health.yml
      after a SUCCESSFUL nightly, failure feeds one standing data-health
      issue; W4 reachability + no-empty-pack guards ship with it. Opus
      pre-PR review fixed 2 blockers + 4 majors in the lane (repo resolution,
      label ensure, needs-result-not-artifact-presence, literal concurrency
      group, nightly-conclusion gate, fail-closed lookup).
  - id: W-CONTRACT-DELTA
    title: Differential pre-merge contract gate (post-merge jam class closed)
    status: awaiting_ci
    note: >
      2026-08-19 afternoon jam: merges 5872/5932 grew two curated-exclusive
      import closures without widening paths; the closure contract test runs
      only POST-merge (integration-baseline on main pushes; path-scoped PR
      packs never reach it), so the culprits merged green, main went red
      ~12:00Z, the breaker latched, and 21 armed PRs sat baseline-blocked
      ~6h. Heal = PR 6002 (paths widened, merged 18:19Z as main-red-repair;
      integration-baseline 32291151787 green 19:06Z; note the 6002 merge
      push itself SCHEDULED NO integration-baseline run - silent-no-run
      class - recovered via workflow_dispatch). Permanent = PR 6005 (merged
      19:27Z on green main): always-on contract-delta job in ci.yml, PR
      events only, feeding ci-gate needs; scripts/check_contract_delta.py
      fails ONLY on findings the PR's tree introduces vs its base (closure
      misses by (job,path); unwired suites by path) - inherited reds print
      as notices, so a red main can never re-jam the fleet at PR level.
      Finding computation is factored into run_ci_pack.py /
      audit_unrun_tests.py and shared with the absolute tests (no drift
      copy). Proven both directions pre-merge (0-introduced exit 0 against
      the then-red main; simulated introduced defect exit 1 naming the fix).
      Five suites remain unwired on main (analyzer_i18n_percentile,
      check_stock_dossier_integrity, china_special_situations_truth_wave1,
      dossier_identity_end_to_end, dossier_numeric_contract) - they red only
      the data-gated workflow-yaml job (data-health lane); owners' follow-up,
      deliberately not absorbed.
  - id: W3-PLANNER-CONTAINMENT
    title: ci-plan working-tree containment on the sole ci.yml carrier
    status: done
    pr: 6286
    note: >
      PR #6286 merged 2026-08-25T22:36:54Z as
      fafe8d7ee775f8b60a0229c085fb7aee6d4349e7 on exact head
      a8842dd5c6db23753c916aa27005aa7cab0c88ab under Sol's corrected W3
      acceptance law (review 5023367453) and the Chairman release recorded
      on the carrier. The corrected gate replaced the sub-60s ci-plan timing
      metric (hosted ref-fetch latency is not W3's capability) with one
      truthful terminal same-head binding graph: run 32893976114 attempt 2
      concluded SUCCESS at 22:19:30Z after attempt 1's ci-pack-6 died inside
      actions/checkout for ~64 minutes with zero tests executed — a
      checkout-only infrastructure failure recorded as issue #6351 evidence,
      healed by the one permitted same-head targeted retry. W3 deliberately
      fixed ci-plan only: the planner runs in a sparse tracked-paths
      checkout (--tracked-paths-file, scripts/ci_scope_dependencies) while
      ci-pack materialization remains the old hosted blob:none full-tree
      path, now explicitly owned by the #6351 trusted self-hosted promotion.
  - id: W-SELFHOSTED-BRIDGE
    title: P0R diagnostic bridge — canary reconciled to the current semantic contract
    status: in_progress
    note: >
      Issue #6351 is the sole coordination/evidence carrier for trusted
      self-hosted CI promotion (Sol CEO incident command 2026-08-25T19:52Z;
      Fable COO is the single principal owner bridge through P4). The bridge
      implements Sol's frozen design: one narrowly admitted diagnostic plan
      pair (pr_head/workflow_dispatch, valid ONLY for workflow
      infrastructure-selfhosted-ci-canary) in build_plan and
      load_authoritative_plan; ci_semantic_proof byte-unchanged and
      hostile-tested closed; canary pinned to Python 3.12.13 and gate code;
      hosted and self-hosted canary consumers consume ONE frozen plan via
      --plan-json with strict semantic-fragment parity; portable Linux
      execution profile v2 per DEC:CI-EXECUTION-PROFILE-V2. P0R/current-main
      closure is green through merge baseline 32942786458. P1 run 32945782277
      then failed before PC pickup because the canary resolver treated the PR
      API's stale base.sha as the synthetic merge ref's authoritative first
      parent (the observed API base lagged that exact parent by 23 commits).
      Production ci.yml already derives tested_base_sha from merge parent 1;
      #6351's bounded resolver correction merged through PR #6467 as
      b6b2307d34110052eaedd1a3779353b1779c3308. P1 run 32957250432 then
      proved exact hosted/self-hosted pack-0 semantic parity, missing-cache
      refusal, different-tree contamination isolation, and one PC CI slot at
      220.080s versus hosted 799.132s (3.63x). P2 run 32960314514 proved
      three distinct sealed PC slots concurrently at 174.986-254.000s,
      byte-stable shared cache, load-1m peak 4.053 on 16 CPUs, at least
      42.77GB memory available, and an independently routable render slot
      while pc-render-1 executed real production render work. Exact trusted
      manual comparison of the uploaded pack 0/1/9 receipts returned parity
      true for all three. The run wrapper concluded cancelled only because
      pack-9's receipt-only hosted compare job spent its full ten-minute
      budget materializing a redundant full repository checkout. The bounded
      P2R repair now publishes a runtime-complete, package-shaped
      main-defined comparator artifact before candidate checkout or any
      candidate-authored execution, and removes that compare-only checkout;
      executable tests lock both bundle imports and upload ordering. It does
      not change production routing or semantic authority. Sequence after P2R:
      P3A inert trusted executor, P3B production route with hosted ci-pack-N
      anchors, then P4 three natural PR proofs. P2 is now accepted from the
      combined receipts: run 32960314514 proved three concurrent PC CI slots and
      an independently acquired pc-render-4 reservation; run 32964925696 made
      checkoutless parity green for packs 0/1/9 on one exact tree and plan. PC
      wall time was 164.689-216.668s versus hosted 680.467-2050.9s, all semantic
      fragments were byte-identical, cache bytes were unchanged and the resource
      envelope stayed safe. P3A merged through PR #6481 as
      7dc0b0ddcd6dd7323a0bf9d45b4ebf6ebc785531. The exact main-pinned workflow
      was added as the fifth selected workflow in the existing organization runner
      group, and the merged root admission was deployed with identical hash
      e4ff74a96e9949a0ce4707e3fdb58cfffc251057d5e8c69a7309fe2871e11202;
      direct main admission passed and a hostile PR ref remained refused. First
      dispatch 33024021850 then failed closed before PC pickup: after exact resolver
      and candidate checkout success, hosted planning invoked the older candidate
      scripts/run_ci_pack.py, which does not admit the trusted executor event pair,
      so no plan artifact existed. P3A-R on the same #6351 program froze and
      transported the complete main-owned planner/semantic/control bundle while
      retaining the exact candidate tree and manifest. It merged through PR
      #6487 as ac3f8a888e2ece7a15f37180c19dc247227a3098. Direct main proof run
      33030976647 then passed on pc-ci-3 against PR #6390 with exact
      main/control SHA ac3f8a888e2ece7a15f37180c19dc247227a3098, tested merge
      078bdb7d212a3bcabea9df6ba06a6ef7bcf5ee07, plan
      1ad0b428cac9e81481545358f9e30b151c3fdffe88d28ed7bc99be8d5ac7e720,
      matching fragment/control/receipt identity, stable 66,228,371,240-byte
      root-owned cache, 60.03% peak CPU, 38.55GB memory-available floor and
      218.947s wall time. P3B-A is the next bounded carrier: make only the
      already main-selected executor call-capable, derive all PR/control/plan
      identity from the GitHub event and called-workflow context, preserve the
      direct one-pack diagnostic, cap production mode at the P2-accepted three
      PC slots, and keep ci.yml plus production_enabled unchanged. P3B-B alone
      may route ordinary same-repository PR traffic after P3B-A acceptance.
  - id: W-QUIESCENCE
    title: Ship-loop watcher quiescence after PARKED / external ladder exit
    status: awaiting_ci
    note: >
      Sol commission macro#6379 (2026-08-24). Root cause reproduced live: a
      run_in_background timer's completion starts a <task-notification> turn
      whose Stop re-enters the hooks, and no hook can enumerate/cancel
      Claude-native tasks (DSC:CLAUDE-TASK-WAKES-OUTLIVE-TERMINAL-SHIP-STATES).
      Canonical amendment: zero new model turns while external state is unchanged;
      timer/poll transports and unchanged successors are forbidden.
      Mechanism (one, deterministic, inside the existing per-session ledger):
      (1) every EXTERNAL block site mints a frozen-state exit key
      <code>:<head>:<digest12(reason)> so the ratified-ladder-exit memory
      quiesces post-escape wakes; (2) the hold wrapper writes parked_latch on
      the first lawful PARKED and passes the identical re-derived hold
      silently, clearing the latch on any positively changed hold state —
      an unanswerable probe never silences (delegates to the guard's own
      escapeable outage block; opus red-team F1/F2); (3) a PreToolUse:Bash
      branch of the guard fails open for ordinary Bash, fails closed for
      executed sleep/poll/detached/uncertain wait forms, and admits at most one
      native GitHub condition owner per session. Acquisition and every ledger
      mutation share one lock; the admitted owner carries a session-unique
      marker and binds to PID plus process-start identity rather than global
      command text. Process absence alone cannot admit the same HEAD/condition;
      unknown identity refuses. No watcher is admitted at a PARKED-latched HEAD
      and no task is killed. The 2026-08-26 same-carrier adversarial return also
      moved every ship_watcher ledger mutation under the one coherent lock,
      preserved exact PARKED latches across outage blocker mutation, made
      evaluated-tree watcher delegation fail closed, and hardened the ledger
      directory/lock/atomic-save paths against symlink substitution.
      The second same-carrier adversarial return (2026-08-26) structurally
      strips heredoc data while classifying executable eval/exec/nohup/env -S/
      PowerShell transports; parses gh option arity into repository + subject
      condition identity; and closes the parallel-hook phantom reservation.
      PreToolUse now writes only a pending claim, while the aggregate-allowed
      command confirms its exact shell PID/start identity before GitHub starts;
      a sibling-hook denial therefore cannot consume the condition. Existing
      unsafe/malformed/symlink ledger state is fail-closed at Stop and visible
      at SessionStart, while the narrow never-installed legacy Stop remains the
      sole absence fail-open. The third same-carrier return distinguishes
      executable bash/sh/zsh/Python stdin heredocs from data-only heredocs;
      computed watcher command positions fail closed; normalized executed gh
      watches consult the quota guard's canonical hot-watch helper before any
      pending claim is written, so a denied default-interval watch cannot delay
      an immediate lawful retry. Session-ledger directories are now traversed
      component-by-component with dir_fd + O_NOFOLLOW, including the
      macro-claude-ship-sessions ancestor. Local proof is deliberately bounded
      to hook-observable behavior: five unchanged PreToolUse requests yielded
      five denies/no updatedInput, and five unchanged post-PARKED wrapper
      observations yielded action=silent while still re-probing; this does not
      claim repository hooks control client model-turn creation. The fourth
      same-carrier return adds structural argv unwrapping for nice, caffeinate,
      and timeout, with unknown literal gh-watch transports failing closed and
      data/prose controls remaining open. It also permits a standard
      root-owned sticky OS temp root while retaining user-owned 0700/no-follow
      requirements for both ledger child directories; fake-gh execution and a
      child-symlink negative test bind those semantics.
      Internal codes byte-unchanged (Journey C). PR #6381 held HOLD-FOR-SOL
      per commission stop condition; mutation receipts + replayed-incident
      proof in the PR body and the
      CI-MERGE-CONTROL-PLANE-2026-08-24-quiescence.md handoff.
next_action: >
  W-TRANSPORT and W-PR-EVENT-CAUSALITY are closed. Do not reopen either for a
  new CI-speed, runner, branch-protection, or cancellation-system proposal.
  Continue W-GATE-SPLIT and W-CONTRACT-DELTA only under their existing evidence
  gates; W-REWRITE remains separately commissioned. Verify contract-delta
  appears and behaves on the next few ordinary PRs
  (inherited-immune, catches introduced closure/unwired defects); confirm
  the armed backlog fully drains post-breaker-open (21 -> 17 within an hour
  of the 19:06Z green). Then W3 at >=72h from the W2 merge (~08-22):
  trailing-100 green rate above 90% via
  scripts/ci_gate_reliability_report.py plus two consecutive ordinary PRs
  merged with no main-red-repair. W-SEMANTIC-PROOF remains stopped; W-REWRITE
  remains separately commissioned.
  W3-PLANNER-CONTAINMENT is closed; W-SELFHOSTED-BRIDGE (issue #6351, Fable
  COO principal) owns the permanent ci-pack materialization repair — hosted
  packs still run the blob:none full-tree checkout that produced the #6406
  and #6286 attempt-1 checkout-only failures; do not absorb pack-checkout
  repairs into product PRs or reopen them here outside the #6351 sequence.
  P3A-R and its repaired direct-main dispatch are accepted; run 33024021850 is
  a closed diagnostic receipt, not a retry candidate. Complete the bounded
  P3B-A call-capability carrier with ci.yml still byte-unchanged. Only after
  P3B-A merges may a separate P3B-B carrier make the exact main-owned call,
  preserve hosted control/anchors and existing ci-gate, and prove the new route
  on its own exact PR tree before P4 natural traffic.
owns_paths:
  - ".claude/hooks/ship_loop_guard.py"
  - "scripts/ship_loop_hold_wrapper.py"
  - ".github/workflows/ci.yml"
  - ".github/workflows/merge-on-green.yml"
  - ".github/workflows/fences.yml"
  - "scripts/ci_authority.py"
  - "scripts/run_ci_pack.py"
  - "scripts/merge_on_green.py"
  - "scripts/check_self_mod_fence.py"
  - ".github/workflows/trusted-ci-executor.yml"
---

The E2BIG incident model and receipts live in
DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING and the session handoff
CI-MERGE-CONTROL-PLANE-2026-08-14-e2big.md. The competing rewrite lineages'
own documentation lives in their PRs (5585 and 5591 both closed unmerged).
The mandatory pre-build semantic-step census is committed as
`DSC-CI-SEMANTIC-PROOF-MANIFEST-CENSUS.v1.json`.

## W-SEMANTIC-PROOF engineering receipts

- The pinned pre-build census records 193 logical jobs, 614 semantic steps,
  185 dependency-install steps, zero unnamed executable steps, and one
  two-step duplicate-name group. Only those two SBIR/STTR steps received
  explicit `proof_id` values. After fresh-main reconciliation the validated
  manifest has 194 logical jobs and 623 semantic units; no new ambiguity was
  introduced.
- `ci.pack_plan.v2` binds workflow/run/event role, tested merge tree, subject
  head, exact base, changed-file digest, semantic inventory, execution digests,
  and transport partition. `ci.semantic_fragment.v1` carries raw bounded pack
  observations. `ci.semantic_evidence.v1` is written once by `ci-gate`, including
  on planner failure, and is the only semantic-era causality verdict.
- Exact-base replay creates one independently pinned checkout, uses the base
  checkout's runner and manifest, and runs at most one serial child per failed
  logical job under one 900-second deadline. It does not create a replay matrix.
- The hostile mutation battery killed 14/14 required mutations. It exposed and
  closed a real missing-ancestry regression fixture before reaching zero
  survivors. Fresh review also closed main infrastructure bypass, job-level
  infrastructure healing, inactive pilot-authority context handling, and a
  production Unicode plan-digest mismatch.
- Local performance at the pre-release carrier: semantic inventory median
  6.316 ms (p95 9.010 ms), full plan median 9.233 ms, bounded failure capture
  over 1,001 representative lines median 0.444 ms (p95 0.702 ms), and full
  194-job/622-unit reconciliation median 12.106 ms (p95 18.490 ms). Exact-base
  checkout became ready in 129.346 s and checkout plus bounded cleanup took
  160.354 s, inside the shared 900-second red-only budget. These are overhead
  measurements, not a claim that the CI suite itself is faster.
- Green consumer paths make zero semantic artifact calls. A linked red PR lookup
  is bounded to three JSON calls plus one artifact download; descendant history
  is capped at 12 candidates. Main semantic dispatch is exact-SHA-bound and costs
  at most three calls when a red breaker lacks current evidence.
- Bootstrap remains deliberately unresolved in this file: this authority-changing
  branch must earn the old required checks without using its new inherited-red
  reasoning. Status stays `in_progress` until merged-main verification.
