---
key: CI-NATIVE-MERGE-QUEUE-REJECTED
question: >
  Should the repository replace the custom merge-on-green controller with GitHub's
  native Merge Queue, now that the July "structurally unavailable on this account"
  ruling is stale (repo is organization-owned on an Enterprise plan)?
answer: >
  No — keep the custom controller (simplified), and record the precondition under
  which the question reopens: producers no longer pushing directly to main.
rationale: >
  Availability is proven live and is NOT the blocker anymore: a repo ruleset with a
  merge_queue rule was accepted (ruleset 20833101), a probe PR enqueued, built a
  merge group, and was squash-merged by the queue 31 seconds after its required
  check went green. The blocker is structural: one direct push to the queue's
  target branch destroys and rebuilds every in-flight merge group (observed live —
  group ref pr-5581-dbfa67d6/commit 00951d82 replaced by pr-5581-9065b39c/commit
  341d7706, state reset to AWAITING_CHECKS, after a single contents-API push that
  even carried [skip ci]), and main receives ~323 direct producer pushes per day
  (~4.5-minute bursty cadence, measured 2026-08-14). Any queue validation longer
  than the inter-push gap restarts indefinitely, and the queue cannot be taught
  that a data tick is outside a PR's tested surface — the exact discrimination the
  custom controller's stale_for already performs. Separately, the github-actions
  integration is refused as a ruleset bypass actor (live 422: "Actor GitHub
  Actions integration must be part of the ruleset source or owner organization"),
  so the ~35 producer lanes pushing with GITHUB_TOKEN cannot be exempted from the
  ruleset that a merge queue requires.
alternatives:
  - option: Adopt native Merge Queue on main now
    why_not: >
      Perpetual merge-group invalidation under the measured producer cadence; the
      required ruleset would refuse every GITHUB_TOKEN producer push (bypass 422);
      migrating ~35 lanes to a dedicated App identity still leaves the
      invalidation problem intact.
  - option: Move producers off main first, then adopt the queue
    why_not: >
      Correct long-term door and explicitly recorded as the reopen precondition,
      but it is the deploy-path architecture project (VPS pulls main every 3 min;
      render lanes bake from main), out of scope for the 2026-08-14 incident.
  - option: Hybrid — queue for PRs, bypass for producers
    why_not: >
      Bypass pushes still move the target branch, which still resets the queue;
      the hybrid inherits the worst of both.
evidence:
  - "research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md §3 (full receipts)"
  - "ruleset id 20833101 (POST /repos/mastermindx-market-intelligence/macro/rulesets)"
  - "probe PR #5581: added_to_merge_queue 05:55:16Z, merged 05:58:50Z (31s after green)"
  - "422 on bypass_actors Integration 15368"
  - "git log origin/main --since='24 hours ago' | wc -l == 323 (2026-08-14)"
affects:
  - "path:.github/workflows/merge-on-green.yml"
  - "path:scripts/merge_on_green.py"
  - "path:docs/CI_MERGE_ARCHITECTURE.md"
confidence: high
reversibility: easy
decided_by: "session: github-ci-merge-recovery-d4a921 (incident commander)"
decided_at: 2026-08-14
review_by: 2026-11-14
---

The July 2026 comment block at the top of merge-on-green.yml ("every
GitHub-native alternative is structurally unavailable on this account") is
superseded on its availability claims by this record; the CONCLUSION (keep the
custom controller) stands for the new reasons above. If producers ever stop
pushing directly to main, re-run the evaluation in the recovery doc §3 — the
scratch-branch method there reproduces in ~10 minutes.
