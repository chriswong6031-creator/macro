# Restore runbook — customer / billing tables (MMX-001 / GATE-1)

**Status of this document:** the repo-side dump, encrypt, timer, and restore
commands exist and have a passing local integrity drill. Two launch-gate facts
are **OPERATOR-BLOCKED** and are not closed by this PR:

1. The **active Supabase plan / PITR setting and retention** for production
   project `fsldfzlxyavsuwqbceod`.
2. An **actual restore into a scratch (non-production) Supabase project**,
   with measured RTO/RPO written below.

Do not treat a written procedure as a passed recovery gate. GATE-1 is closed
only after the operator block in §8 is executed and the receipt table in §7
is filled with a real scratch-project run.

**NEVER restore into production.** The live project ref is
`fsldfzlxyavsuwqbceod`. `scripts/backup_user_tables.py` refuses any restore
target containing that string, even when `--i-am-restoring-into-scratch` is
set.

Protected tables (all nine, every night):

`profiles`, `watchlists`, `watchlist_symbols`, `chart_layouts`,
`saved_scripts`, `alerts`, `favorites`, `user_entitlements`, `stripe_events`.

`auth.users` is **not** in the logical dump. A table-level restore into an
empty scratch project will fail foreign keys unless those UUIDs already
exist, or you use a dashboard-level project restore that includes Auth.

---

## 1. RPO and RTO (declared vs measured)

| Quantity | Declared (this design) | Measured this session | GATE-1 status |
|---|---|---|---|
| **RPO** (how much customer data we accept losing) | 24 hours — nightly dump at 05:17 UTC, plus whatever Supabase daily/PITR window is active | Local mechanism drill: RPO = 86400 s (the dump's own declaration). Live vendor RPO is unknown. | **OPERATOR-BLOCKED** for the live Supabase plan/PITR window |
| **RTO** (how long until a scratch copy answers queries) | Target: under 30 minutes for the nine-table logical restore | Local file-backend drill: see §6 | **OPERATOR-BLOCKED** for a scratch Supabase project |

The nightly job is the independent copy. Supabase's own backups, if enabled,
are a second copy that dies with the project: deleting the project deletes
those backups. That is why the R2 prefix exists.

---

## 2. Confirm the live Supabase backup / PITR plan

**This section is OPERATOR-BLOCKED.** This session had no Supabase dashboard
session and no `SUPABASE_ACCESS_TOKEN` / management-API credential. The
active plan was not read. Do not invent a retention number.

Operator action — do these exact steps and paste the answers into §7:

```bash
# 1. Open the live project's backup pages (browser, owner account):
#    https://supabase.com/dashboard/project/fsldfzlxyavsuwqbceod/database/backups/scheduled
#    https://supabase.com/dashboard/project/fsldfzlxyavsuwqbceod/database/backups/pitr
#    https://supabase.com/dashboard/project/fsldfzlxyavsuwqbceod/settings/addons?panel=pitr

# 2. If you have a Supabase management token, the same facts from the API:
curl -sS -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  "https://api.supabase.com/v1/projects/fsldfzlxyavsuwqbceod"

curl -sS -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  "https://api.supabase.com/v1/projects/fsldfzlxyavsuwqbceod/billing/addons"
```

Record:

| Fact | Value (operator fills) |
|---|---|
| Plan (Free / Pro / Team / Enterprise) | OPERATOR-BLOCKED |
| Daily backups enabled? | OPERATOR-BLOCKED |
| Daily backup retention | OPERATOR-BLOCKED (docs: Pro 7d, Team 14d, Enterprise up to 30d — **not a substitute for reading the project**) |
| PITR add-on enabled? | OPERATOR-BLOCKED |
| PITR retention window | OPERATOR-BLOCKED |
| Screenshot or API JSON saved at | OPERATOR-BLOCKED |

Vendor documentation (retention *by plan*, not this project's setting):
https://supabase.com/docs/guides/platform/backups

---

## 3. Install the nightly dump (VPS, operator-gated)

The unit is **not** armed by `app/deploy/update.sh`. That is deliberate: no
autonomous production deploy, and this Wave-1 lane does not share
`update.sh` with other remediation workstreams.

Create the env file first. Mode `0600`, root-only. Do not commit it.

```bash
sudo install -m 0600 /dev/null /etc/macro-user-backup.env
sudo tee /etc/macro-user-backup.env >/dev/null <<'EOF'
BACKUP_ENCRYPTION_KEY=replace-with-16-plus-chars-kept-offline-too
R2_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=...
BACKUP_R2_PREFIX=backups/user-tables
SUPABASE_URL=https://fsldfzlxyavsuwqbceod.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
EOF
sudo chmod 0600 /etc/macro-user-backup.env
```

`SUPABASE_*` may already live in `/etc/macro-api.env`; the unit reads that
file first and `/etc/macro-user-backup.env` second.

Then install and arm the timer:

```bash
sudo APP_DIR=/opt/macro /opt/macro/app/deploy/user-backup-setup.sh
sudo systemctl list-timers macro-user-backup.timer --no-pager
sudo systemctl status macro-user-backup.timer --no-pager
```

Optional one-shot now (still writes to R2, never to a database):

```bash
sudo systemctl start macro-user-backup.service
sudo journalctl -u macro-user-backup.service -n 80 --no-pager
```

List what landed:

```bash
python -m scripts.backup_user_tables list --output-dir /var/lib/macro-user-backup
```

R2 prefix `backups/user-tables/` is **private**. Do not put it behind
`DATA_BASE` / the public r2.dev host. Objects are MMUB1 (HMAC-SHA256 + SHA-256-CTR) and, when the unit runs
with `--r2-sse-c`, also R2 SSE-C. Retention prune is `>=30` days and is
part of the nightly command (`--prune`).

---

## 4. Take a logical dump by hand

From any machine that has the service-role key and the encryption key
(laptop for a drill; VPS for the real copy):

```bash
export BACKUP_ENCRYPTION_KEY='...'
export SUPABASE_URL='https://fsldfzlxyavsuwqbceod.supabase.co'
export SUPABASE_SERVICE_ROLE_KEY='...'

python -m scripts.backup_user_tables backup \
  --output-dir /var/lib/macro-user-backup \
  --upload-r2 --r2-sse-c --prune \
  --retention-days 30
```

Local-only (no R2, used by the mechanism drill and CI):

```bash
python -m scripts.backup_user_tables backup \
  --encryption-key "$BACKUP_ENCRYPTION_KEY" \
  --source-dir /path/to/table-json \
  --output-dir /tmp/user-backup-store \
  --backup-id user-tables-20260815T051700Z
```

---

## 5. Restore — scratch only

### 5.1 Hard rules

```bash
# These must all be true before any restore command:
#   1. The target is NOT project fsldfzlxyavsuwqbceod.
#   2. You pass --i-am-restoring-into-scratch.
#   3. You have a written backup_id.
#   4. You are not pointing --target-url at production.
```

The script exits `2` and writes nothing if the target contains
`fsldfzlxyavsuwqbceod`.

### 5.2 Preferred scratch path — dashboard restore into a NEW project

This is the path that also brings `auth.users`.

```bash
# Browser, owner account, NEVER the live project as the destination:
#   1. https://supabase.com/dashboard/project/fsldfzlxyavsuwqbceod/database/backups/scheduled
#      or .../database/backups/pitr
#   2. Restore → "Restore into a new project" (wording in the current dashboard).
#   3. Wait until the new project's status is Active.
#   4. Record: new project ref, start UTC, end UTC.
```

If the dashboard only offers in-place restore, **stop**. In-place is a
production restore. Create an empty scratch project and use §5.3.

### 5.3 Logical restore of the nine tables into a scratch project

Create a scratch project in the dashboard first. Put its URL in
`SCRATCH_URL`. Confirm the ref is not `fsldfzlxyavsuwqbceod`.

```bash
export BACKUP_ENCRYPTION_KEY='...'
export SUPABASE_SERVICE_ROLE_KEY='<scratch project service role>'
export SCRATCH_URL='https://<scratch-ref>.supabase.co'
export BACKUP_ID='user-tables-YYYYMMDDTHHMMSSZ'

# Refuse-check (must print the production ref and nothing else you care about):
python - <<'PY'
from scripts.backup_user_tables import project_ref_from_url, PRODUCTION_PROJECT_REFS
import os
ref = project_ref_from_url(os.environ["SCRATCH_URL"])
print("scratch_ref", ref)
assert ref not in PRODUCTION_PROJECT_REFS, "this is production — abort"
PY

# Clock start:
date -u +%Y-%m-%dT%H:%M:%SZ

python -m scripts.backup_user_tables restore \
  --encryption-key "$BACKUP_ENCRYPTION_KEY" \
  --input-dir "/var/lib/macro-user-backup/${BACKUP_ID}" \
  --target-url "$SCRATCH_URL" \
  --i-am-restoring-into-scratch \
  --receipt "/tmp/${BACKUP_ID}-scratch-receipt.json"

# Clock end:
date -u +%Y-%m-%dT%H:%M:%SZ

python -m json.tool "/tmp/${BACKUP_ID}-scratch-receipt.json"
```

If `auth.users` is empty in the scratch project, the upsert will fail on
FK. Either restore Auth first (dashboard project restore) or load a
scratch-only fixture of the same UUIDs.

### 5.4 Local file restore (mechanism drill — not GATE-1)

```bash
python -m scripts.backup_user_tables restore \
  --encryption-key "$BACKUP_ENCRYPTION_KEY" \
  --input-dir /tmp/user-backup-store/user-tables-YYYYMMDDTHHMMSSZ \
  --target-dir /tmp/user-backup-restored \
  --i-am-restoring-into-scratch \
  --receipt /tmp/user-backup-receipt.json

python -m scripts.backup_user_tables verify \
  --encryption-key "$BACKUP_ENCRYPTION_KEY" \
  --input-dir /tmp/user-backup-store/user-tables-YYYYMMDDTHHMMSSZ \
  --target-dir /tmp/user-backup-restored
```

---

## 6. Local mechanism drill (this session)

This is **not** the GATE-1 scratch-Supabase restore. It proves the dump
format, encryption, restore command, row counts, and sha256 integrity
against a file backend.

| Field | Value |
|---|---|
| Kind | local file-backend mechanism drill |
| Source backup identifier | `user-tables-20260815T051700Z` |
| Commands | §6.1 |
| Start time (UTC) | 2026-08-15T08:06:05Z |
| End time (UTC) | 2026-08-15T08:06:05Z |
| Measured RTO | 0.001 s (restore only; wall dump+restore+verify 0.025 s) |
| Measured RPO | 86400 s (nightly declaration) |
| Integrity | 9/9 tables, 45 rows, per-table sha256 match (`integrity_ok: true`) |
| Production target used? | no |
| GATE-1? | no — OPERATOR-BLOCKED pending §8 |

### 6.1 Exact session commands

```bash
python3 -m pytest tests/test_backup_user_tables.py -q
python3 -m scripts.backup_user_tables backup \
  --encryption-key 'test-backup-key-16+' \
  --source-dir /tmp/mmx001-src \
  --output-dir /tmp/mmx001-store \
  --backup-id user-tables-20260815T051700Z
python3 -m scripts.backup_user_tables restore \
  --encryption-key 'test-backup-key-16+' \
  --input-dir /tmp/mmx001-store/user-tables-20260815T051700Z \
  --target-dir /tmp/mmx001-dst \
  --i-am-restoring-into-scratch \
  --receipt /tmp/mmx001-receipt.json
```

The receipt path `/tmp/mmx001-receipt.json` is the machine record of
`backup_id`, `started_at`, `ended_at`, `rto_seconds`, `rpo_seconds`, and
per-table row/sha256 checks. Re-run the three commands after filling
`/tmp/mmx001-src` with one JSON list per protected table if you want a
wall-clock number outside pytest.

---

## 7. Scratch Supabase restore receipt (GATE-1)

**OPERATOR-BLOCKED — not fabricated.** Fill every cell after a real run.

| Field | Value |
|---|---|
| Source backup identifier | OPERATOR-BLOCKED |
| Scratch project ref | OPERATOR-BLOCKED |
| Restore commands | OPERATOR-BLOCKED (use §5.2 or §5.3 verbatim) |
| Start time (UTC) | OPERATOR-BLOCKED |
| End time (UTC) | OPERATOR-BLOCKED |
| Measured RTO | OPERATOR-BLOCKED |
| Measured RPO | OPERATOR-BLOCKED |
| Row / count / integrity verification | OPERATOR-BLOCKED |
| Production project touched? | must be **no** |

---

## 8. Exact operator action required to close GATE-1

1. Sign in to the Supabase owner account.
2. Open
   `https://supabase.com/dashboard/project/fsldfzlxyavsuwqbceod/database/backups/scheduled`
   and
   `https://supabase.com/dashboard/project/fsldfzlxyavsuwqbceod/database/backups/pitr`.
   Write the plan, daily-backup retention, and PITR window into §2.
3. Create a **new** scratch project. Do not restore in place on
   `fsldfzlxyavsuwqbceod`.
4. On the VPS: write `/etc/macro-user-backup.env` (§3) and run
   `sudo APP_DIR=/opt/macro /opt/macro/app/deploy/user-backup-setup.sh`.
5. Take one dump (`sudo systemctl start macro-user-backup.service`) and
   record the `backup_id` from
   `python -m scripts.backup_user_tables list --output-dir /var/lib/macro-user-backup`.
6. Restore that `backup_id` into the scratch project with the exact
   commands in §5.2 (preferred) or §5.3. Time it. Verify row counts and
   sha256 (or dashboard row counts) for all nine tables.
7. Paste the receipt into §7 and commit. GATE-1 is then checkable.

Until those seven steps happen, MMX-001 remains a launch blocker. The
code in this repository is the dump/restore tool and the runbook, not
the proof.

---

## 9. What this does not do

- It does not deploy itself. `update.sh` is untouched.
- It does not redesign auth or billing.
- It does not dump `auth.users`, Storage, or Edge Functions.
- It does not authorize a production restore. There is no override flag.
