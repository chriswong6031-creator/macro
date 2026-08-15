---
key: USER-BACKUP-POSTGREST-PRIMARY
question: >
  Should the nightly customer-table dump use pg_dump against the Supabase
  Postgres URL, or a PostgREST logical dump with the service-role key the VPS
  already carries?
answer: >
  PostgREST logical dump of the nine protected tables is the primary path.
  pg_dump remains optional if SUPABASE_DB_URL is later added; it is not required
  to arm the timer.
rationale: >
  The VPS already has SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for billing and
  watchlist reads. Direct Postgres (port 5432 / pooler) is not a documented VPS
  dependency, and a dump job that needs a new network path would fail closed
  every night until someone punched a hole. A JSONL logical dump restores with
  exact commands and is what the integrity check hashes.
alternatives:
  - option: Require pg_dump / pg_restore as the only format
    why_not: >
      Needs a DB URL and a client binary the box may not have. The launch gates
      say "pg_dump" as the idea of a logical copy, not as a hard binary dependency.
  - option: Dashboard-only backups, no repo job
    why_not: >
      Supabase backups die with the project. MMX-001 exists because that copy is
      unverified and not independent.
evidence:
  - "scripts/run_watchlist_sentinel.py and app/billing.py already speak PostgREST with the service-role key"
  - "research/MASTERMIND_LAUNCH_GATES.md GATE-1 names the nine tables, not the dump binary"
affects: [WS:USER-BACKUP]
confidence: high
reversibility: easy
decided_by: session
decided_at: 2026-08-15
---

## Notes

A later session may add a pg_dump extra artifact when a DB URL is present.
That is an addition, not a replacement, unless this decision is superseded.
