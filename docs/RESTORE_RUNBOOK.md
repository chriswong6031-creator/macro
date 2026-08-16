# Restore runbook — customer and billing tables (MMX-001 / GATE-1)

**NEVER restore into production.** The live Supabase project ref is
`fsldfzlxyavsuwqbceod`. `scripts/backup_user_tables.py restore` refuses any
destination that contains that ref, matches `SUPABASE_URL` /
`SUPABASE_DB_URL` / `DATABASE_URL`, or shares their host. There is no override
flag.

This document is the operator procedure. A written procedure is **not** GATE-1.
GATE-1 passes only when a restore has been performed into a scratch
non-production Supabase project and the receipt below is filled with measured
times. Until that happens the two facts that require account access stay
**OPERATOR-BLOCKED**.

---

## What is protected

Nightly job: `python -m scripts.backup_user_tables dump`

Tables (allowlist; the job will not dump anything else):

| Table | Why it is here |
|---|---|
| `profiles` | Account profile / identity row |
| `watchlists` | User list containers |
| `watchlist_symbols` | Tickers on those lists |
| `chart_layouts` | Saved chart state |
| `saved_scripts` | Saved editor scripts |
| `alerts` | User alerts |
| `favorites` | Favorites |
| `user_entitlements` | Who paid, which tier, Stripe customer id |
| `stripe_events` | Webhook idempotency ledger |

`auth.users` is owned by Supabase Auth (GoTrue) and is **not** in this dump. A
scratch project must already have matching users, or the SQL restore must run
with `session_replication_role = replica` (the `psql` path does). A full
identity recovery still needs the vendor backup / PITR for `auth`.

`app/deploy/live-rollback.sh` recovers published artifacts only. It never
touches Postgres.

---

## Declared RPO / RTO

| Metric | Declared target | Meaning |
|---|---|---|
| **RPO** | **24 hours** | Nightly dump at 05:17 UTC. Worst case after a successful dump: lose the day's writes. Until the first successful dump, RPO is unbounded except for whatever Supabase-managed backup exists (unknown — see OPERATOR-BLOCKED). |
| **RTO** | **30 minutes** | Time from "we have a backup id and a scratch project with schema applied" to "row counts match the manifest". Does not include creating a new Supabase project or re-pointing production DNS. |

These are targets, not measurements. Measured values live in the receipt
sections below.

---

## Status of GATE-1 facts that need account access

| Fact | Status |
|---|---|
| Supabase plan / PITR: OPERATOR-BLOCKED | No `SUPABASE_ACCESS_TOKEN`, dashboard session, or Management API credential is present in this environment. The active plan, PITR toggle, and vendor retention window have **not** been read. |
| scratch-supabase restore: OPERATOR-BLOCKED | No scratch project exists that this session can write. A production dump was not taken (no live DB URL / service role in this environment either). |

Do not treat either row as a pass.

### Operator action required to close GATE-1

1. In the Supabase dashboard for project `fsldfzlxyavsuwqbceod`, open
   **Settings → Infrastructure / Database → Backups** (or **Add-ons → Point in
   Time Recovery**). Record:
   - plan name (Free / Pro / Team / Enterprise)
   - daily backup retention (days)
   - PITR enabled? (yes/no)
   - PITR retention (days), if enabled
   Paste those four values into § "Vendor backup / PITR" below.
2. Create a **new** Supabase project named `mmx-restore-scratch-YYYYMMDD`.
   Do not reuse production. Copy its DB URL and service-role key into a
   throwaway shell. Never write them into git.
3. Apply the application schema to the scratch project (Terminal
   `0001_init.sql` plus Macro `scripts/deploy/0005_user_entitlements.sql` and
   `0006_user_entitlements_plan_interval.sql`).
4. On the API VPS (or any host that can read the private R2 prefix and the
   encryption key), run the restore commands in § "Restore into scratch".
5. Paste the printed JSON receipt into § "Scratch-Supabase restore receipt".

---

## Nightly dump (VPS)

Units: `app/deploy/macro-user-backup.service` + `.timer` (05:17 UTC,
`RuntimeMaxSec=900`, `TimeoutStartSec=900`). `update.sh` self-arms the timer
on the box where `macro-api.service` is enabled.

Create `/etc/macro-user-backup.env` (mode 0600, root-only):

```bash
umask 077
cat > /etc/macro-user-backup.env <<'EOF'
BACKUP_ENCRYPTION_KEY=<openssl-rand-hex-32>
SUPABASE_DB_URL=<postgres-connection-string-with-password>
# Optional dedicated R2 (otherwise the job uses R2_* from /etc/macro-api.env):
# BACKUP_R2_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com
# BACKUP_R2_ACCESS_KEY_ID=...
# BACKUP_R2_SECRET_ACCESS_KEY=...
# BACKUP_R2_BUCKET=mastermindx
# BACKUP_R2_PREFIX=private/user-table-backups/
EOF
chmod 600 /etc/macro-user-backup.env
```

The encryption key must be at least 16 characters. Store a copy in the
operator password manager. Without it the ciphertext is unrecoverable.

Preferred dump path is the direct DB URL (`pg_dump` SQL sibling + `psql`
JSONL). If only `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` are set, the job
uses PostgREST. Either way the published object is an openssl
AES-256-CBC-PBKDF2 archive under `private/user-table-backups/`. That prefix
must not be mapped on the public R2 CDN.

Manual dump (same command the unit runs):

```bash
sudo systemctl start macro-user-backup.service
# or, from /opt/macro with the env files loaded:
set -a
source /etc/macro-api.env
source /etc/macro-user-backup.env
set +a
python -m scripts.backup_user_tables dump
```

List published backups:

```bash
python -m scripts.backup_user_tables list
```

Decrypt-and-hash check (does not write to any database):

```bash
python -m scripts.backup_user_tables verify --backup-id user-tables-YYYYMMDDTHHMMSSZ
```

Retention: the job deletes objects under the prefix older than 30 days. Do not
pass `--retention-days` below 30; the process exits 2. Also set an R2
lifecycle rule on `private/user-table-backups/` to 30 days as a second
enforcement.

---

## Restore into scratch

Preconditions: scratch project exists, schema applied, `BACKUP_ENCRYPTION_KEY`
matches the dump, and you can read the private R2 prefix (or you have a
`--local-dir` copy).

```bash
export BACKUP_ENCRYPTION_KEY='<same key used to dump>'
export SCRATCH_DB_URL='postgresql://postgres.<scratch-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres'
# If listing/fetching from R2, the host also needs BACKUP_R2_* or R2_*.
# If you copied the two objects off R2 first:
#   --local-dir /var/tmp/mmx-backups

python -m scripts.backup_user_tables restore \
  --backup-id user-tables-YYYYMMDDTHHMMSSZ \
  --dest-db-url "$SCRATCH_DB_URL" \
  --i-am-restoring-into-scratch \
  --write-receipt /tmp/mmx-restore-receipt.json
```

REST alternative when you have the scratch API URL + its service-role key
instead of a DB URL:

```bash
export SUPABASE_SCRATCH_SERVICE_ROLE_KEY='<scratch service role>'
python -m scripts.backup_user_tables restore \
  --backup-id user-tables-YYYYMMDDTHHMMSSZ \
  --dest-supabase-url "https://<scratch-ref>.supabase.co" \
  --i-am-restoring-into-scratch \
  --write-receipt /tmp/mmx-restore-receipt.json
```

The process prints a JSON receipt with `backup_id`, redacted dest, `started_at`,
`ended_at`, `rto_seconds`, `rpo_seconds`, and per-table
`expected` / `restored` / `ok`. `integrity` must be `pass`. If any table is
`ok: false`, the restore did not succeed.

Production URLs fail closed even with `--i-am-restoring-into-scratch`.

After a successful scratch restore, **destroy the scratch project**. Do not
leave customer rows sitting in an unused project.

---

## Vendor backup / PITR

Status: **Supabase plan / PITR: OPERATOR-BLOCKED**

| Field | Value |
|---|---|
| Project ref | `fsldfzlxyavsuwqbceod` |
| Plan | OPERATOR-BLOCKED — dashboard not readable from this session |
| Daily backup retention | OPERATOR-BLOCKED |
| PITR enabled | OPERATOR-BLOCKED |
| PITR retention | OPERATOR-BLOCKED |
| Evidence | none — no Management API token, no screenshot |

Paste the dashboard values here when step 1 of the operator action is done.
A screenshot or `GET /v1/projects/{ref}` response is acceptable evidence.

---

## Scratch-Supabase restore receipt

Status: **scratch-supabase restore: OPERATOR-BLOCKED**

| Field | Value |
|---|---|
| Source backup identifier | OPERATOR-BLOCKED |
| Restore commands | see § "Restore into scratch" — not executed against a scratch Supabase project |
| Start (UTC) | OPERATOR-BLOCKED |
| End (UTC) | OPERATOR-BLOCKED |
| Measured RTO | OPERATOR-BLOCKED |
| Measured RPO | OPERATOR-BLOCKED |
| Row / count / integrity | OPERATOR-BLOCKED |
| Environment | must be a new project, never `fsldfzlxyavsuwqbceod` |

GATE-1 remains open until this table is filled from a real scratch project.

---

## In-process fixture drill (machinery only — not GATE-1)

This is a local encrypt → publish → decrypt → restore → count-check against an
in-memory table store. It proves the script, the cipher, and the receipt
shape. It is **not** a scratch Supabase restore and does **not** close GATE-1.

Recorded by `tests/test_backup_user_tables.py::test_restore_roundtrip_memory_store_and_receipt`:

| Field | Value |
|---|---|
| Source backup identifier | `user-tables-20260815T051700Z` (fixture clock) |
| Restore commands | `python -m scripts.backup_user_tables restore --backup-id user-tables-20260815T051700Z --i-am-restoring-into-scratch --dest-db-url "$SCRATCH_DB_URL"` |
| Start / end | fixture clock 05:20:00Z → 05:20:08Z |
| Measured RTO | 8 seconds (in-process; not a network restore) |
| Measured RPO | 4800 seconds (fixture source `as_of` 04:00:00Z → restore start 05:20:00Z) |
| Integrity | pass — all nine tables, counts match the manifest |
| Environment | `in-process-fixture` (`gate1_scratch_supabase: false`) |

Re-run:

```bash
python -m pytest tests/test_backup_user_tables.py -q
```

---

## Failure notes

- Missing `BACKUP_ENCRYPTION_KEY`, dump source, or R2/`--local-dir` → exit 2,
  nothing uploaded.
- A missing protected table fails the dump (unless `--allow-missing` on a
  scratch drill). Partial archives are not published.
- `openssl` missing → refuse. Plaintext is never stored.
- Restoring over a scratch database that already has rows may duplicate.
  Prefer an empty scratch project.
- Losing the encryption key loses the R2 copies. The vendor backup (once
  confirmed) is then the only recovery path.
