---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: claude/integration-baseline-keepalive
model: fable
ended_because: complete
prs: [5906, 5737, 5922]
discoveries:
  - DSC:PUSH-TRIGGERED-FRESHNESS-PROOF-IS-SELF-LOCKING
mission: >
  Operator reported that PRs showing "All checks have passed" were not being
  auto-merged by the sweeper, asked for #5737 to be assessed and rearmed, and
  left the remaining stuck PRs to a Grok bot. Find why the merge train was
  stalled and fix the cause rather than the instance.
state_before: >
  merge-on-green was running healthily every ~20 min and main was green (18
  clean names at 71b3e926c407). Four PRs sat armed and unmerged; #5906 sat CLEAN
  and unmerged; #5737 had been stalled since 2026-08-17T16:54Z. The prior
  session's diagnosis on record was the promisor base-replay failure (issue
  #5916), which is a real defect but was NOT what was blocking this queue.
changed:
  - path: .github/workflows/integration-baseline.yml
    what: >
      Added a 4-hourly `schedule:` keepalive (cron "17 1,5,9,13,17,21 * * *") so
      the merge-train circuit breaker's verdict cannot age past
      BASELINE_MAX_AGE_HOURS while main is quiet. Triggers, concurrency and
      runs-on are otherwise unchanged. The comment records the measurement, the
      cost argument, and the rejected alternative.
  - path: agentos/discoveries/DSC-PUSH-TRIGGERED-FRESHNESS-PROOF-IS-SELF-LOCKING.md
    what: >
      New discovery record for the self-locking breaker, including the one-line
      sweep-log diagnostic that distinguishes it from a red PR.
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: >
      On PR #5737 only. Resolved the single merge conflict against origin/main by
      taking main's newer next_action and folding in the branch's W8 detail. No
      other file on that PR changed; its diff vs main is byte-identical at 52
      files, +3927 -2.
verified:
  - claim: The sweeper was blocked by its own stale circuit breaker, not by any PR or by main being red.
    command: gh run view 32211895483 --log
    result: >
      "integration-baseline is pending (newest concluded baseline is 6.5h old,
      past the 6h freshness bound (fda2cfee4cb8))" and "PR #5921/#5737/#5892/#5903:
      source main baseline is pending; leaving it armed behind the circuit
      breaker", in the same log as "main proof: 18 clean name(s) at 71b3e926c407".
  - claim: The staleness recurs roughly nightly and is not a one-off.
    command: gh run list --workflow integration-baseline.yml --limit 100 --json createdAt,conclusion,status
    result: >
      99 completed runs from 2026-08-15T11:53Z to 2026-08-18T20:53Z; three
      green-to-green gaps crossed the 6h bound, all overnight — 6.8h (08-15
      17:10Z), 6.0h (08-16 20:43Z), 6.5h (08-18 20:53Z).
  - claim: The breaker self-rescues, so the stall is a lag rather than a permanent wedge.
    command: gh run list --workflow integration-baseline.yml --limit 10
    result: >
      ensure_integration_baseline dispatched run 32211919276 at 2026-08-19T03:22:43Z;
      it concluded success at 03:35:52Z and the armed PRs unblocked.
  - claim: PR #5906 was never armed, which is the whole reason the sweeper ignored it.
    command: gh pr view 5906 --json labels,mergeStateStatus
    result: >
      mergeStateStatus CLEAN with an empty label list. After `gh pr edit 5906
      --add-label merge-on-green` it merged at 2026-08-19T03:25:53Z as 2b345b75666e.
  - claim: PR #5737's only red was base-era, not its own content.
    command: gh api repos/.../commits/71b3e926c407/check-runs
    result: >
      ci-pack-9 is `success` on main's current proof, while #5737's red was
      ci-pack-9 -> tests/test_us_prophet_fusion.py::TestLegacyV2ByteParity at
      2026-08-17T17:39Z against a two-day-old base. The PR touches no fusion code.
  - claim: The keepalive does not break the gates the baseline job itself runs.
    command: python3 scripts/check_workflow_yaml.py .github/workflows; python3 scripts/check_runner_policy.py; python -m pytest tests/test_ci_pack.py tests/test_merge_on_green.py tests/test_runner_policy.py tests/test_ci_canary_tools.py tests/test_ci_canary_workflows.py
    result: >
      "OK: 92 workflow file(s) parse with on: + jobs: blocks."; "OK: Wave B/C
      runner routing is hosted-by-default and canary-only self-hosted."; "472
      passed, 3 warnings in 534.19s".
  - claim: Four PRs were armed against explicit owner holds and have been disarmed.
    command: gh api graphql (title/body/comments for 5889,5897,5898,5901,5908,5909); gh api repos/.../issues/5889/timeline
    result: >
      All six were labelled merge-on-green at 2026-08-19T03:29:49Z. #5889 (title
      DO NOT MERGE), #5898 (title "(do not merge)"), #5901 ("Do not merge until
      architecture acceptance / Do not arm merge-on-green") and #5909 ("Do not
      merge until Sol reviews") carry explicit holds; label removed from those
      four with a comment quoting each hold. autoMergeRequest is null on all four.
unverified:
  - claim: The 4-hourly cadence is sufficient in the worst case.
    what_would_verify: >
      After #5922 merges, `gh run list --workflow integration-baseline.yml` over a
      week showing no green-to-green gap above 6h, and no sweep log line reading
      "integration-baseline is pending (newest concluded baseline is Nh old)".
  - claim: The promisor base-replay failure (issue #5916) is unrelated to this stall.
    what_would_verify: >
      A sweep log in which a PR is refused with classification=unknown while the
      breaker is open — that would isolate #5916's effect from the breaker's.
unresolved:
  - >
    Issue #5916 (semantic base replay cannot check out a base SHA in the blobless
    partial clone) is still open and unfixed. It did not cause this stall but it
    still disables inherited-red classification for authority-changing PRs.
  - >
    ci-main-heartbeat runs were observed concluding `cancelled` with zero failed
    jobs and no superseding sibling despite cancel-in-progress: false. Recorded on
    #5916; cause not found. scripts/metabolism_immune.py counts `cancelled` in its
    red set, so the now-sighted sentinel will report false reds from that lane.
  - >
    Whatever armed six PRs at 03:29:49Z has no hold-awareness. Until it does, the
    same four PRs can be re-armed by the next sweep.
next_actions:
  - Watch #5922 and #5737 to merged; both are armed and were green-or-pending with no reds at 03:45Z.
  - >
    After #5922 merges, confirm the first scheduled run fires at the next cron slot
    (17 past 05/09/13/17/21/01 UTC) via `gh run list --workflow integration-baseline.yml --json event`
    and that `event` reads `schedule`.
  - >
    Consider a `hold` label convention so a review freeze is machine-readable; today
    the only signal is prose in the title/body/comments, which is why the 03:29Z
    sweep could not see it.
do_not_redo:
  - >
    Do NOT diagnose a "baseline-blocked" sweep as a red PR, a red main, or a stale
    main proof. The line "main proof: N clean name(s)" printed alongside
    "integration-baseline is pending" means main is green and no PR is at fault.
  - >
    Do NOT replace the age bound with "skip it when main's SOURCE tree is unchanged
    since the last green proof". It decides freshness using the same path list the
    bound exists to compensate for, inheriting exactly the blind spot the bound
    covers. Rejected in DSC:PUSH-TRIGGERED-FRESHNESS-PROOF-IS-SELF-LOCKING.
  - >
    Do NOT re-diagnose #5737 as a fusion byte-parity defect. Its ci-pack-9 red was
    base-era; ci-pack-9 is green on main and the PR touches no fusion code. It was
    DIRTY, and a conflicting PR is scheduled zero check-runs, so its red could never
    have been disproven without the merge.
  - >
    Do NOT re-arm #5889, #5898, #5901 or #5909 as part of a sweep. Each was
    deliberately held by its owning session for Sol/CEO review; re-arm only after
    that review lands.
danger_areas:
  - >
    integration-baseline.yml is authority-changing AND a global invalidator: editing
    it disables path scoping, so the PR runs the full manifest and inherits every
    latent main red. Open it only against a main whose newest proof is green.
  - >
    The workflow's concurrency group is shared by push, schedule and dispatch with
    cancel-in-progress: false. That is load-bearing — `true` produced a measured
    livelock on 2026-08-07 (59 cancelled / 1 running / 0 success over ~3h). Do not
    flip it to make the cron "more responsive".
  - >
    Arming a PR you did not open can merge work someone deliberately froze. The hold
    is prose, not a label; read title, body and the last two comments first.
---

## What was actually wrong

The operator's report was "PRs that have all checks passed aren't being auto-merged by sweeper". Three independent causes were live at once, and only one of them was the interesting one.

**1. #5906 was never armed.** `merge-on-green` gates which PRs the sweeper reads at all. #5906 was `CLEAN`, mergeable, every required check green — and carried no label, so the sweeper had never looked at it. Adding the label merged it in two minutes. Check the label before diagnosing anything else.

**2. #5737 was `DIRTY`, and a conflict starves the Actions suite.** Its last CI was two days old and red on `ci-pack-9`. That red could not be disproven by a re-run, because a conflicting PR is scheduled zero check-runs. The fix was the merge itself, not a heal: `ci-pack-9` is green on main, and a 52-file mockups/docs PR does not touch `tests/test_us_prophet_fusion.py`.

**3. The circuit breaker had gone stale — and that is the one worth remembering.**

`integration-baseline.yml` publishes the verdict `merge_on_green` uses to pause ordinary merges, and that verdict expires at `BASELINE_MAX_AGE_HOURS` (6h). The expiry is deliberate: the workflow's own path filter is explicitly not trusted to be complete. But until this change the only trigger that could renew it was a source push to main — and merges are what produce source pushes:

```
no merges -> no source push to main -> proof ages past 6h -> breaker pends -> no merges
```

Nothing inside that loop breaks it. `ensure_integration_baseline` in `scripts/merge_on_green.py` does, by dispatching the workflow once it observes a stale green — but that rescue is lagged by the sweep interval, and while it waits the sweep log reads exactly like a broken merge train. That is how a session ends up healing packs that were never red.

## The one-line diagnostic

```
::warning::integration-baseline is pending (newest concluded baseline is 6.5h old, past the 6h freshness bound)
PR #5921: source main baseline is pending; leaving it armed behind the circuit breaker.
main proof: 18 clean name(s) at 71b3e926c407, 3.2h old
```

`main proof: N clean name(s)` printed next to `baseline is pending` means **main is green and no PR is at fault**. Do not heal packs, rebase branches, or dispatch `ci.yml --ref main`. It drains itself.

## The hold hazard found in passing

Six open PRs were labelled `merge-on-green` at 03:29:49Z by something enumerating open PRs. Four carried an explicit hold in prose — `DO NOT MERGE` in the title, or an owner comment reading "Do not merge until Sol reviews / do not arm merge-on-green". The breaker opened six minutes later, so all four would have squash-merged on their next clean conclusion, landing architecture freezes and a packet-contract closure on main without the review they were held for.

They are disarmed with a comment quoting each PR's own hold text, explicitly not taking ownership, and inviting a re-arm once the review lands. `autoMergeRequest` is null on all four, so no second arm is live — label removal alone would not have been a hold.

The structural gap is that a review freeze is prose, not a label. A `hold` label convention would make it machine-readable; that is proposed, not built.
