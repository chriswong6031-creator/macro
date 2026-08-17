---
key: BACKUP-DUAL-SOURCE
question: >
  Should the nightly customer-table backup require a direct Postgres URL and
  pg_dump, or also accept the PostgREST service-role path the VPS already has?
answer: >
  Prefer the direct DB URL (psql JSONL plus a pg_dump SQL sibling when
  pg_dump is installed). Fall back to PostgREST when only SUPABASE_URL +
  service-role are set. Fail closed if neither source exists. The published
  artifact is always encrypted JSONL so restore verification is one code path.
rationale: >
  GATE-1 asks for a nightly pg_dump, and that is the better dump. The API box
  today already carries SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in
  /etc/macro-api.env and does not carry a DB password. Requiring the DB URL
  before the first night would leave the timer red until an operator add.
  A REST fallback means the unit can produce an encrypted private copy the
  same day the timer arms, while the runbook still tells the operator to add
  SUPABASE_DB_URL so the pg_dump sibling appears.
alternatives:
  - option: pg_dump only
    why_not: >
      The VPS does not currently have SUPABASE_DB_URL. The first nights would
      fail closed with no copy at all, which is worse than a REST dump of the
      same nine tables.
  - option: REST only
    why_not: >
      The remediation plan and GATE-1 name pg_dump. Direct SQL also survives
      PostgREST schema cache misses and can attach a pg_dump.sql sibling.
  - option: dump auth.users as well
    why_not: >
      auth.users is GoTrue-owned; service-role REST cannot read it by default.
      The runbook states the gap instead of pretending the dump is a full
      identity backup.
evidence:
  - "research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md WS-1 — nightly dump of the nine tables to R2"
  - "app/deploy/macro-sentinel.service EnvironmentFile=-/etc/macro-api.env — existing VPS secret slot has service-role, not a DB URL"
  - "scripts/backup_user_tables.py resolve_mode — pg_dump when SUPABASE_DB_URL/DATABASE_URL set, else REST"
affects: [WS:CUSTOMER-DATA-BACKUP, shared-auth-entitlements]
confidence: high
reversibility: easy
decided_by: cursor-cloud-ws1
decided_at: 2026-08-15
---

## Notes

Restore still refuses production regardless of dump mode. The production project
ref `fsldfzlxyavsuwqbceod` is hard-coded plus any
`PRODUCTION_SUPABASE_PROJECT_REFS` extras.
