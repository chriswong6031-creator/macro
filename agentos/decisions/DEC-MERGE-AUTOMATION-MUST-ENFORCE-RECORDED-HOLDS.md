---
key: MERGE-AUTOMATION-MUST-ENFORCE-RECORDED-HOLDS
question: >
  PR #6109 carried an explicit HOLD-FOR-SOL comment from its author (merge-on-green
  disarmed, hold recorded 2026-08-20) and was nonetheless squash-merged at
  2026-08-20T22:03:18Z by the shared account, with no release comment. Fleet law
  (DEC:SOL-HOLD-IS-A-MERGE-BARRIER) already says a recorded hold binds every merge
  path — so is label/session discipline alone a sufficient enforcement mechanism,
  or must the merge automation itself refuse a recorded hold?
answer: >
  The merge automation must enforce recorded holds itself. merge-on-green must
  scan the PR title, body, and issue comments on its about-to-merge path and
  refuse to merge any pull request carrying an un-released hold marker,
  regardless of label state. A hold declaration is a marker beginning a line (or
  a title/heading segment); prose narrating someone else's hold does not bind.
  A hold is released by a HOLD-RELEASED comment newer than every hold, or by
  the hold's author removing the marker. Label state is an arming convenience,
  never an authority record: any session holding the shared token can add a
  label, so a label can never be allowed to override a recorded authority hold.
rationale: >
  The #6109 incident is the direct proof: the hold-as-state discipline
  (disarmed label + hold comment) was correctly applied by the PR author and was
  still overridden — the fleet shares one account token, so every session can
  re-arm or merge, and prose law binds only sessions that read it. The sweeper's
  only machine-readable hold before this decision was the hardcoded
  NEVER_AUTO_MERGE_PULLS frozenset in scripts/merge_on_green.py, which cannot
  see a hold recorded on the PR itself. Content on #6109 was the hold author's
  own Sol-consistent fix, so no damage resulted — but the control plane allowed
  an unauthorized merge path, and the same path would have merged a genuinely
  held change. Sol's 2026-08-21 A1A verdict orders this recorded as a
  control-plane defect: "future merge automation must not allow merge-on-green
  to override an explicit authority hold."
alternatives:
  - option: Keep hold-as-state discipline only (disarmed label + DRAFT + hold comment), no automation change
    why_not: >
      Exactly the mechanism that failed on #6109 — every session can flip label
      and draft state with the shared token; state discipline binds nothing at
      the API layer.
  - option: Extend the hardcoded NEVER_AUTO_MERGE_PULLS frozenset per hold
    why_not: >
      Requires a merged code change to record or release each hold — slower than
      the hold itself, and the list already drifted (its standing entries are
      long-merged PRs). Holds belong on the PR they bind.
  - option: A repository ruleset freeze per held PR
    why_not: >
      Org-admin-only bypass, repo-wide blast radius, and the 08-15
      ci-recovery-bootstrap-freeze incident showed an undocumented ruleset
      freezes the whole fleet's push path, not one PR.
evidence:
  - "PR #6109: HOLD-FOR-SOL comment recorded by author session 2026-08-20; merged 2026-08-20T22:03:18Z by chriswong6031-creator (shared account); autoMergeRequest null post-merge; no release comment (gh pr view 6109 --json mergedBy,mergedAt,autoMergeRequest)."
  - "scripts/merge_on_green.py NEVER_AUTO_MERGE_PULLS (line ~322) was the sweeper's only hold mechanism — a hold recorded in a PR body/comment was invisible to it."
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER (2026-08-19, #5974/#5953): a recorded hold binds every merge path; enforce as state. #6109 shows state enforcement alone is insufficient."
  - "Sol A1A round-2 verdict 2026-08-21: 'Separately record the #6109 merge-over-hold incident as a control-plane defect: future merge automation must not allow merge-on-green to override an explicit authority hold.'"
affects:
  - "scripts/merge_on_green.py"
  - ".github/workflows/merge-on-green.yml"
  - "WS:MARKET-OS"
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER"
confidence: high
reversibility: easy
decided_by: sol
decided_at: 2026-08-21
---

## Enforcement

Implemented in PR #6149 (merged 8a1b93889061, 2026-08-21) as a recorded-hold probe on merge-on-green's
about-to-merge path: after every check/freshness/semantic gate has concluded
clean and immediately before the merge call, the sweeper scans the PR title,
body, and issue comments for hold markers (line-start / title / heading-segment
declarations — prose narrating a hold elsewhere does not bind), refuses to
merge when held, labels `merge-blocked`, and explains once via a
`[merge-on-green hold-guard]` comment. Release = a HOLD-RELEASED comment newer
than every hold (Bot chatter neither holds nor releases), or the hold author
removing the marker. The probe fails closed on an unreadable comment history —
an unverifiable hold state is not permission. Boundary: holds bind via PR
title, body, and issue comments only, not review bodies. Three adversarial
review rounds hardened the contract (false-positive prose holds, self-defeating
release paths, blocked_names pollution that dispatched spurious main baselines,
label churn, cap-overflow spam). This automates, and does not replace,
DEC:SOL-HOLD-IS-A-MERGE-BARRIER — manual merges by sessions remain bound by the
recorded-hold law directly.
