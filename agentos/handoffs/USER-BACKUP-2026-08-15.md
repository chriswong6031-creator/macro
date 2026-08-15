---
workstream: WS:USER-BACKUP
session: cursor/user-backup-restore-3515
model: opus
ended_because: blocked
prs: [5732]
mission: >
  WS-1 of the red-team remediation plan — repo-side customer-data backup and a
  proven restore path. Isolated PR. No production deploy. No auth/billing redesign.
state_before: >
  origin/main at 6685df10a3e had no scripts/backup_user_tables.py, no
  docs/RESTORE_RUNBOOK.md, no backup timer, and no open PR matching MMX-001.
  grep for backup_user_tables / RESTORE_RUNBOOK / MMX-001 on open PRs returned none.
changed:
  - path: scripts/backup_user_tables.py
    what: "Dump/encrypt/restore/verify/prune for the nine protected tables. Refuses production project fsldfzlxyavsuwqbceod. File-backend + PostgREST + optional private R2."
  - path: app/deploy/macro-user-backup.service
    what: "Oneshot with RuntimeMaxSec=900, TimeoutStartSec=900, PrivateTmp, fail-closed env file."
  - path: app/deploy/macro-user-backup.timer
    what: "Nightly 05:17 UTC, Persistent=true."
  - path: app/deploy/user-backup-setup.sh
    what: "Operator-gated install. Does not run from update.sh."
  - path: docs/RESTORE_RUNBOOK.md
    what: "Exact commands, declared RPO 24h, local-drill receipt, OPERATOR-BLOCKED §2/§7/§8."
  - path: tests/test_backup_user_tables.py
    what: "Integrity, production refuse, retention >=30d, unit bounds, runbook pins."
  - path: .github/workflows/user-backup.yml
    what: "Standalone PR workflow so the suite is not unrun and does not edit legacy-jobs.yml."
verified:
  - claim: "18 (then 19) unit tests pass, including production-target refuse and 9/9 sha256 restore."
    command: "python3 -m pytest tests/test_backup_user_tables.py -q"
    result: "passed"
  - claim: "Local file-backend restore of user-tables-20260815T051700Z is integrity_ok with RPO 86400s."
    command: "python3 -m scripts.backup_user_tables restore --encryption-key test-backup-key-16+ --input-dir /tmp/mmx001-store/user-tables-20260815T051700Z --target-dir /tmp/mmx001-dst --i-am-restoring-into-scratch --receipt /tmp/mmx001-receipt.json"
    result: "integrity_ok true; 45 rows across 9 tables; rto_seconds 0.001"
  - claim: "No matching open repair PR existed at start."
    command: "GitHub search_pull_requests for backup_user_tables OR RESTORE_RUNBOOK OR MMX-001 is:open"
    result: "0 open items; only closed audit PR #5476"
unverified:
  - claim: "Active Supabase plan / PITR retention for fsldfzlxyavsuwqbceod."
    what_would_verify: "Owner dashboard at /database/backups/scheduled and /database/backups/pitr, or Management API with SUPABASE_ACCESS_TOKEN."
  - claim: "Restore into a scratch Supabase project."
    what_would_verify: "docs/RESTORE_RUNBOOK.md §5.2 or §5.3 run against a new project ref, receipt pasted into §7."
  - claim: "Nightly timer armed on the VPS."
    what_would_verify: "sudo APP_DIR=/opt/macro /opt/macro/app/deploy/user-backup-setup.sh && systemctl list-timers macro-user-backup.timer"
unresolved:
  - "GATE-1 remains a launch blocker until the operator finishes docs/RESTORE_RUNBOOK.md §8."
next_actions:
  - "Operator: confirm plan/PITR on the live project and write §2."
  - "Operator: create a scratch project and run §5.2 or §5.3; fill §7."
  - "Operator: write /etc/macro-user-backup.env and run user-backup-setup.sh. Do not restore into production."
do_not_redo:
  - "Do not open a second backup/restore PR covering the same files."
  - "Do not wire update.sh in a sibling Wave-1 PR for this timer."
  - "Do not fabricate §2/§7 closure without a scratch-project receipt."
danger_areas:
  - "Restore target containing fsldfzlxyavsuwqbceod is production. The script refuses it; a dashboard in-place restore would not."
  - "Logical dump omits auth.users. Scratch upserts need those UUIDs or a dashboard project restore."
---

## Operator block (exact)

See docs/RESTORE_RUNBOOK.md §8. The seven steps there are the only remaining
work. This session cannot perform them.
