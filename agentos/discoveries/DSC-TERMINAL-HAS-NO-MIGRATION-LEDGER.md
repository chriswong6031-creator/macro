---
key: TERMINAL-HAS-NO-MIGRATION-LEDGER
claim: >
  The Terminal's shared Supabase project (fsldfzlxyavsuwqbceod) has NO migration history at all —
  the `supabase_migrations` SCHEMA does not exist, not merely an empty `schema_migrations` table.
  The Supabase CLI has never been run against it: no config.toml in charting-app, no CLI binary on
  the Mac or the VPS, and `terminal-build.sh` does not apply migrations. `supabase/migrations/` is
  a schema SOURCE OF RECORD that an operator applies by hand, per file, through the Management API
  (`POST https://api.supabase.com/v1/projects/<ref>/database/query`, PAT in charting-app/.env).
  Consequence: application status is per-file and ORDER-INDEPENDENT, and is not derivable from the
  filenames — 0009_watchlist_symbol_unique was applied 2026-08-19, two days BEFORE
  0008_chart_layouts_unique_name on 2026-08-21.
falsifier: >
  `select nspname from pg_namespace where nspname = 'supabase_migrations'` returning a row, or
  `select version from supabase_migrations.schema_migrations` succeeding instead of raising
  42P01. Either would mean someone has since adopted the CLI, at which point the re-application
  risk below becomes live and this record must be revisited rather than trusted.
so_what: >
  Three things change for any session touching Terminal schema. (1) The standard Supabase
  reconciliation advice — repair remote history, align timestamps, `supabase db push` — assumes a
  ledger that is NOT THERE; `db push` would find an empty history and attempt to apply everything
  from 0001, which is survivable only because every file is idempotent (`create ... if not
  exists`, policies wrapped in duplicate_object handlers, `drop trigger` before `create trigger`).
  Keep it that way: a migration that is not safe to re-run cannot be applied in this estate,
  because nothing records that it already was. (2) NEVER infer "is it applied?" from file order or
  from a neighbouring file's header — ask the database (`pg_indexes`, `pg_proc`). (3) The same
  Management API endpoint runs arbitrary SQL, so it is also the read-only CENSUS and DRY-RUN tool:
  0010's aggregate was proven against real production data as a plain `WITH ... SELECT` before ever
  being applied as DDL, and 0008's emptiness precondition was re-censused immediately before
  applying rather than trusted from the two-day-old header. Two hard-won endpoint rules: strip `--`
  comments first (it splits on `;` and chokes on a `;` inside a comment) and use curl, not
  python-urllib (Cloudflare 1010).
kind: constraint
verified_at: 2026-08-21
verified_by: >
  Read-only Management API census 2026-08-21 from charting-app:
  `select nspname from pg_namespace where nspname='supabase_migrations'` -> [];
  `select version, name from supabase_migrations.schema_migrations` -> ERROR 42P01 relation does
  not exist; `select indexname from pg_indexes where indexname in
  ('chart_layouts_user_name','wls_watchlist_symbol')` -> wls_watchlist_symbol ONLY (before 0008 was
  applied later the same day). Absence of tooling confirmed by `which supabase psql` (not found)
  and no supabase/config.toml. Shipped as charting-app PR #440 (renumber + CI guard +
  supabase/migrations/README.md) and PR #454 (application-status correction).
scope:
  - "charting-app"
  - "supabase/migrations/**"
  - "terminal/lib/watchlists.ts"
  - "terminal/lib/layouts.ts"
  - "terminal/lib/searchEvents.ts"
confidence: verified
---

## Grounds

The census was run because two files both claimed version `0008` — `0008_chart_layouts_unique_name`
(PR #427) and `0008_watchlist_symbol_unique` (PR #426), authored in parallel off the same base so
neither could see the other's number. A version prefix is a migration's identity, so "has 0008 been
applied?" had two different and simultaneously-true answers.

The intended fix was to reconcile the local filenames against remote history. There is no remote
history. That inverted the finding: the collision could not have caused a double-apply, because
nothing tracks application at all — and that same absence is why nothing detected the collision
either. A human noticed, later.

So the fix shipped as detection rather than reconciliation: `tests/test_migration_ledger.py`, which
runs inside the EXISTING `python` CI job so the three protected check contexts are unchanged. It
fails on a duplicate version prefix, an unparseable filename, mixed prefix widths, and any code
reference to a migration filename that no longer exists — the last because `lib/watchlists.ts`
names one in a runtime error string an operator is meant to act on, and a stale name there is a
dead end at exactly the moment someone is debugging production.

The renumber tie-break was merge time, not application status: merge time is immutable and
recoverable from git, whereas application status changes the moment an operator runs a file and
would have guaranteed a future renumber.

Related: `DEC:TERMINAL-SAVED-LAYOUT-CONTRACT-V2`,
`DSC:TERMINAL-CHART-LAYOUTS-TABLE-IS-EMPTY` (the census that made 0008 safe to write, and whose
emptiness precondition was re-verified before it was finally applied).
