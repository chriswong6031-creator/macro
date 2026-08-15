---
key: USER-BACKUP-NO-ACCOUNT-ACCESS
claim: >
  The 2026-08-15 cloud-agent session that built WS-USER-BACKUP had no
  SUPABASE_*, R2_*, BACKUP_*, or DATABASE_URL credentials, no .env, and no
  Supabase dashboard session, so the live plan/PITR setting and a scratch
  Supabase restore could not be performed.
falsifier: >
  In the same class of cloud-agent environment, `env | grep -E '^(SUPABASE_|R2_|BACKUP_|DATABASE_URL)'`
  prints a live key, or a Management API call to
  https://api.supabase.com/v1/projects/fsldfzlxyavsuwqbceod returns 200 with a plan.
so_what: >
  A future session must probe credentials first and, if they are still absent,
  keep GATE-1 marked OPERATOR-BLOCKED. Do not fill docs/RESTORE_RUNBOOK.md §2 or
  §7 with guessed retention numbers or a fabricated scratch-project RTO.
kind: constraint
verified_at: 2026-08-15
verified_by: >
  env | grep -E '^(SUPABASE_|R2_|BACKUP_|DATABASE_URL)' → empty;
  ls /workspace/.env → absent; no pg_dump binary; no Supabase token in the environment.
scope: [macro]
confidence: verified
---

## Detail

The session finished every repo-side deliverable and ran a local file-backend
restore drill (backup_id `user-tables-20260815T051700Z`, 9/9 tables, integrity
ok). That drill is not GATE-1.
