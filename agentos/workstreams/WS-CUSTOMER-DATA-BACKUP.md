---
key: CUSTOMER-DATA-BACKUP
title: Customer-data backup and restore (MMX-001 / GATE-1)
objective: >
  A nightly encrypted dump of the nine customer/billing tables reaches private R2
  with ≥30-day retention, a restore runbook names exact commands, and one restore
  into a scratch non-production Supabase project has been performed with measured
  RTO/RPO. Done only when that scratch receipt exists — a written procedure alone
  does not close GATE-1.
status: blocked
program: shared-auth-entitlements
repos: [macro]
owner: ops
class: build
blast_radius: irreversible
ambiguity: specified
owns_paths:
  - scripts/backup_user_tables.py
  - app/deploy/macro-user-backup.service
  - app/deploy/macro-user-backup.timer
  - docs/RESTORE_RUNBOOK.md
blocked_by:
  - "operator: confirm Supabase plan / PITR / vendor retention in the dashboard for fsldfzlxyavsuwqbceod"
  - "operator: create scratch project mmx-restore-scratch-YYYYMMDD and run the restore commands in docs/RESTORE_RUNBOOK.md"
waves:
  - id: W1
    title: Repo-side dump job, systemd timer, runbook, fail-closed tests
    status: awaiting_ci
    pr: 5733
  - id: W2
    title: Scratch-Supabase restore drill + vendor PITR fact
    status: todo
    depends_on: [W1]
decisions:
  - DEC:BACKUP-DUAL-SOURCE
discoveries:
  - DSC:SYSTEMD-ONESHOTS-USE-TIMEOUTSTARTSEC
landmines:
  - "NEVER restore into production project fsldfzlxyavsuwqbceod. The script refuses that ref; do not add an override."
  - "auth.users is not in the dump. A scratch project needs matching users or session_replication_role=replica."
  - "Losing BACKUP_ENCRYPTION_KEY loses the R2 copies."
do_not_redo:
  - "Do not invent a second backup script or a parallel timer. Extend scripts/backup_user_tables.py and macro-user-backup.*."
  - "Do not claim GATE-1 closed from the in-process fixture drill. That receipt is environment=in-process-fixture."
artifacts:
  - scripts/backup_user_tables.py
  - app/deploy/macro-user-backup.service
  - app/deploy/macro-user-backup.timer
  - docs/RESTORE_RUNBOOK.md
  - tests/test_backup_user_tables.py
next_action: >
  Operator fills docs/RESTORE_RUNBOOK.md §Vendor backup/PITR and §Scratch-Supabase
  restore receipt by creating mmx-restore-scratch-YYYYMMDD and running
  `python -m scripts.backup_user_tables restore --backup-id <id> --dest-db-url
  "$SCRATCH_DB_URL" --i-am-restoring-into-scratch`.
---

## Scope

WS-1 of `research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md`. Isolated from other
Wave-1 lanes. No auth/billing/Prophet/Radar redesign. No production deploy.
