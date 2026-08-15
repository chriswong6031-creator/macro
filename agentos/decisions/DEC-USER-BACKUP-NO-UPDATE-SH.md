---
key: USER-BACKUP-NO-UPDATE-SH
question: >
  Should macro-user-backup.timer be self-armed by app/deploy/update.sh like the
  sentinel, or installed only by an operator-gated setup script?
answer: >
  Operator-gated only: app/deploy/user-backup-setup.sh. update.sh is not touched.
rationale: >
  The remediation plan scoped WS-1 to new files so Wave-1 lanes do not collide.
  update.sh is the hottest shared deploy file. House law also forbids autonomous
  production deploy of this capability: the timer must not start dumping customer
  tables until BACKUP_ENCRYPTION_KEY exists on the box.
alternatives:
  - option: Self-arm from update.sh the way macro-sentinel.timer does
    why_not: >
      Collides with other Wave-1 PRs editing update.sh, and would start dumps
      on the next 3-minute pull before the operator writes the encryption key.
  - option: Leave units in the repo with no install script
    why_not: >
      The runbook would have to invent install commands. A small setup script
      is the exact command the runbook names.
evidence:
  - "research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md WS-1 Files/systems lists new units + runbook, not update.sh"
  - "Task brief: No autonomous production deploy. Isolated PR. Do not combine with other Wave-1 lanes."
affects: [WS:USER-BACKUP]
confidence: high
reversibility: easy
decided_by: session
decided_at: 2026-08-15
---

## Reconsider when

A later session that owns update.sh alone, after GATE-1 is closed, may add a
self-heal block that installs changed units but still requires the env file
(`ConditionPathExists=/etc/macro-user-backup.env` already does).
