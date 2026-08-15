---
key: USER-BACKUP
title: Customer-table backup and restore (MMX-001 / GATE-1)
objective: >
  A nightly encrypted dump of the nine protected customer/billing tables exists,
  a restore runbook names exact commands, and GATE-1 is closed only after a real
  restore into a scratch Supabase project with measured RTO/RPO. Done = §7 of
  docs/RESTORE_RUNBOOK.md is filled from that scratch run, not from a local file drill.
status: blocked
program: shared-auth-entitlements
repos: [macro]
owner: ops
class: build
blast_radius: irreversible
ambiguity: specified
owns_paths:
  - scripts/backup_user_tables.py
  - tests/test_backup_user_tables.py
  - app/deploy/macro-user-backup.service
  - app/deploy/macro-user-backup.timer
  - app/deploy/user-backup-setup.sh
  - docs/RESTORE_RUNBOOK.md
  - .github/workflows/user-backup.yml
blocked_by:
  - "OPERATOR-BLOCKED: no Supabase dashboard/account access in the implementing session — live plan/PITR retention unread."
  - "OPERATOR-BLOCKED: scratch (non-production) Supabase restore has not been performed."
decisions:
  - DEC:USER-BACKUP-POSTGREST-PRIMARY
  - DEC:USER-BACKUP-NO-UPDATE-SH
discoveries:
  - DSC:USER-BACKUP-NO-ACCOUNT-ACCESS
waves:
  - id: W1
    title: Repo dump job, systemd timer, runbook, local integrity drill
    status: done
    next_action: Merge the isolated PR; do not treat merge as GATE-1.
  - id: W2
    title: Operator scratch-project restore + plan/PITR capture
    status: todo
    depends_on: [W1]
    next_action: Execute docs/RESTORE_RUNBOOK.md §8 and fill §2 and §7.
do_not_redo:
  - "Do not add a second backup script or a parallel restore runbook."
  - "Do not wire this timer through app/deploy/update.sh without superseding DEC:USER-BACKUP-NO-UPDATE-SH."
  - "Do not restore into project fsldfzlxyavsuwqbceod. There is no override flag."
landmines:
  - "auth.users is not in the logical dump. A table upsert into an empty scratch project will FK-fail."
  - "A write into a sparse-omitted tree is not a risk here; do not git-add dump artifacts."
next_action: Operator executes docs/RESTORE_RUNBOOK.md §8 (plan/PITR read + scratch restore).
---

## Context

Remediation plan WS-1 / MMX-001 / GATE-1. Repo-side pieces shipped in W1. The
launch gate is not closed until W2.
