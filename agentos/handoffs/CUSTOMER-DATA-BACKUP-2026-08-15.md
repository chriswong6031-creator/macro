---
workstream: "WS:CUSTOMER-DATA-BACKUP"
session: cursor/ws1-backup-restore-3cdc
model: local
ended_because: blocked
mission: >
  WS-1 / MMX-001 — establish and prove customer-data recovery. Isolated PR.
  Repo-side dump job, systemd timer, restore runbook, and one scratch-Supabase
  restore with measured RTO/RPO. No production deploy.
state_before: >
  origin/main had no scripts/backup_user_tables.py, no restore runbook, no
  backup timer. Grep for pg_dump/pg_restore/PITR in docs/ops/app/scripts/.github
  was empty of database-recovery hits (audit PR #5476). No open backup/restore
  PR existed to consume.
changed:
  - path: scripts/backup_user_tables.py
    what: Encrypted dump/restore CLI; REST + psql sources; production restore refuse-closed; 30-day R2 prune.
  - path: app/deploy/macro-user-backup.service
    what: Oneshot dump unit with TimeoutStartSec=900 and RuntimeMaxSec=900.
  - path: app/deploy/macro-user-backup.timer
    what: Nightly 05:17 UTC, Persistent=true.
  - path: app/deploy/update.sh
    what: Self-arms the timer on boxes where macro-api.service is enabled.
  - path: docs/RESTORE_RUNBOOK.md
    what: Exact commands, declared RPO 24h / RTO 30m, OPERATOR-BLOCKED receipts.
  - path: tests/test_backup_user_tables.py
    what: Fail-closed, encrypt, retain, production-guard, unit-file, runbook tests.
unverified:
  - claim: Active Supabase plan, PITR toggle, and vendor retention
    what_would_verify: Dashboard Settings → Backups for fsldfzlxyavsuwqbceod, or Management API GET /v1/projects/{ref}
  - claim: Restore into a scratch Supabase project
    what_would_verify: Run the restore command in docs/RESTORE_RUNBOOK.md against mmx-restore-scratch-YYYYMMDD and paste the JSON receipt
verified:
  - claim: No matching open backup/restore PR existed at start
    command: "MCP search_pull_requests query='repo:mastermindx-market-intelligence/macro is:open MMX-001 OR backup_user_tables OR RESTORE_RUNBOOK'"
    result: total_count 0 for that query; broader backup/restore search returned unrelated closed PRs only
  - claim: This environment has no Supabase or R2 credentials
    command: "python3 -c 'import os; print([k for k in (\"SUPABASE_URL\",\"SUPABASE_ACCESS_TOKEN\",\"R2_ENDPOINT\",\"BACKUP_ENCRYPTION_KEY\") if os.environ.get(k)])'"
    result: empty list — all four unset
unresolved:
  - GATE-1 remains open until the operator completes the two blocked facts.
  - First VPS night will fail closed until /etc/macro-user-backup.env has BACKUP_ENCRYPTION_KEY (and ideally SUPABASE_DB_URL).
next_actions:
  - Operator: record plan/PITR in docs/RESTORE_RUNBOOK.md §Vendor backup / PITR.
  - Operator: create scratch project, run restore, paste receipt.
  - Do not open a second backup PR.
do_not_redo:
  - Do not dump production customer rows into a cloud-agent VM.
  - Do not restore into fsldfzlxyavsuwqbceod.
  - Do not claim GATE-1 from the in-process fixture drill.
danger_areas:
  - Service-role key bypasses RLS — the dump is the full customer table.
  - A wrong dest URL that somehow evades the ref check would write customer rows. Keep the production-ref guard.
  - update.sh self-arm will enable the timer on the API box; without the encryption key the unit fails every night (visible, intended).
decisions:
  - DEC:BACKUP-DUAL-SOURCE
discoveries:
  - DSC:SYSTEMD-ONESHOTS-USE-TIMEOUTSTARTSEC
---

## Operator unblock (exact)

1. Supabase dashboard → project `fsldfzlxyavsuwqbceod` → Backups / PITR. Paste plan, retention, PITR yes/no into `docs/RESTORE_RUNBOOK.md`.
2. New project `mmx-restore-scratch-YYYYMMDD`. Apply schema. Export `SCRATCH_DB_URL`.
3. On a host that can read the private R2 prefix and `BACKUP_ENCRYPTION_KEY`:

```bash
python -m scripts.backup_user_tables restore \
  --backup-id <id-from-list> \
  --dest-db-url "$SCRATCH_DB_URL" \
  --i-am-restoring-into-scratch \
  --write-receipt /tmp/mmx-restore-receipt.json
```

4. Paste the receipt into the runbook. Destroy the scratch project.
