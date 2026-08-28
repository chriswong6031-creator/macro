---
key: WORKFLOW-DEFINITION-PINS-TO-TRIGGERING-COMMIT
claim: >
  A newly merged workflow STEP cannot execute in a run that had already started, even
  when that run's jobs check out `ref: main` and `git pull origin main` after the merge
  landed. GitHub resolves the workflow DEFINITION from the commit that triggered the run
  (for `schedule`, the default-branch HEAD when the cron fired); the checkout only
  refreshes library code in the working tree. So an in-flight nightly WILL run
  newly merged library code and will NOT run a newly merged step. Measured 2026-08-26:
  Prophet V4 B1 merged 878930b3b2f9849e120391fa461ed528f32d2e3c at 00:13:07Z; scheduled
  run 32908543584 (fired 2026-08-25T22:57Z, head b52de3705cdb, pre-merge) executed its
  `us_prophet_ledgers` job at 07:30-07:35Z — well after the merge, checking out post-B1
  main — and the step `python -m scripts.reconcile_us_candidate_episodes --nightly` was
  absent from the job log entirely. Its resulting commit 2e9ebe6a8db4 carried no
  data/us_prophet_rank/episodes/ bytes. The engine job in the SAME run did execute B1's
  modified scripts/build_turn_watch.py, because that is library code inside a
  pre-existing step, and committed the sidecar.
falsifier: >
  A job log whose `##[group]Run` list contains a step absent from the workflow file at
  that run's own head SHA. Run, for the candidate run and job:
  `gh api repos/{owner}/{repo}/actions/jobs/<job_id>/logs --allow-escape-sequences | sed 's/\x1b\[[0-9;]*m//g' | grep '##\[group\]Run '`
  and compare against `git show <run_head_sha>:.github/workflows/daily.yml`, where the B1
  step sits at .github/workflows/daily.yml:6443-6444 on current main. A commit produced by
  such a run, or a checkout that demonstrably contains the newer workflow file, does not
  falsify this: the working tree and the workflow definition come from different places,
  which is the whole point.
so_what: >
  Any acceptance gate phrased as "the first ordinary scheduled run containing merge X"
  is satisfied ONLY by a run whose own HEAD SHA contains X. The `ref: main` checkout is
  not a shortcut, and treating it as one manufactures a false acceptance from a run in
  which the code never executed - the exact failure natural-run law exists to prevent.
  Verify by reading the job log's actual step list
  (`gh api repos/{owner}/{repo}/actions/jobs/<job_id>/logs --allow-escape-sequences`,
  then strip ANSI), never by reasoning about checkout ancestry. The converse also
  matters and is easy to miss: a merge that changes only library code DOES take effect
  mid-flight, so an in-flight run can legitimately mix pre-merge steps with post-merge
  code.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  Job log for us_prophet_ledgers (job 98084842822) of run 32908543584 fetched via
  `gh api repos/mastermindx-market-intelligence/macro/actions/jobs/98084842822/logs
  --allow-escape-sequences`, ANSI stripped; its step list runs emit_prophet_doors ->
  grade_prophet_doors -> grade_us_prophet_candidates -> accrue_us_prophet_w3 ->
  run_prophet_miss_audit -> push_retry with no reconcile step. Checkout confirmed as
  `ref: main` plus an explicit pull at .github/workflows/daily.yml:6411-6414, and the
  B1 step confirmed present in current main at :6443-6444.
  `git merge-base --is-ancestor 878930b3b2f9 b52de3705cdb` exits non-zero, confirming
  the run head predates the merge. `git show --stat 2e9ebe6a8db4` shows no episodes/
  paths. The engine job's sidecar commit 576959b11804 confirms the library-code half.
scope:
  - macro
  - .github/workflows/daily.yml
  - any natural-run acceptance gate
confidence: verified
---

Sixteen jobs in `daily.yml` use the `ref: main` plus explicit-pull idiom, so this applies
to the whole nightly, not one lane. The idiom exists so a long-queued job picks up the
newest code rather than hours-old bytes; the trap is assuming it also picks up newest
workflow structure. It does not, and the two halves fail in opposite directions: library
changes land mid-flight whether or not you wanted them, while step changes wait for the
next trigger.
