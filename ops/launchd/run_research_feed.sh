#!/bin/bash
# Canonical Research Vault fast-trigger watcher.
# The MarketDesk trickle daemon owns browser/download/vault work. This script
# only observes the producer's canonical DB and dispatches the existing ingest.
set -u
set -o pipefail

DEST="${RESEARCH_FEED_DEST:-$HOME/mastermind-research}"
CANONICAL_DB="/Volumes/STORAGE/MastermindX/marketdesk/db/marketdesk.sqlite"
LEGACY_ROOT="$HOME/mastermind-research/marketdesk_paper_extractor"
DB="${RESEARCH_FEED_DB_PATH:-$CANONICAL_DB}"
LOG="${RESEARCH_FEED_LOG_PATH:-$DEST/feed.log}"
WATERMARK="${RESEARCH_FEED_WATERMARK_PATH:-$DEST/.feed_vault_watermark}"
LOCK="${RESEARCH_FEED_LOCK_DIR:-$DEST/.feed.lock}"
REPO="${RESEARCH_FEED_REPO:-mastermindx-market-intelligence/macro}"
WORKFLOW="${RESEARCH_FEED_WORKFLOW:-research-ingest.yml}"
BRANCH="${RESEARCH_FEED_BRANCH:-main}"
GH_BIN="${RESEARCH_FEED_GH_BIN:-gh}"
LAUNCHCTL_BIN="${RESEARCH_FEED_LAUNCHCTL_BIN:-launchctl}"
PYTHON_BIN="${RESEARCH_FEED_PYTHON_BIN:-python3}"
PRODUCER_LABEL="${RESEARCH_FEED_PRODUCER_LABEL:-com.mastermindx.research-trickle}"

ts() { date -u +%FT%TZ; }
if ! mkdir -p "$(dirname "$LOG")" "$(dirname "$WATERMARK")" "$(dirname "$LOCK")"; then
  printf '%s feed: ERROR cannot create state directories\n' "$(ts)" >&2
  exit 10
fi
log() { printf '%s feed: %s\n' "$(ts)" "$*" >>"$LOG"; }

case "$DB" in
  /*) ;;
  *) log "canonical database unavailable: path must be absolute ($DB)"; exit 11 ;;
esac
if [ ! -f "$DB" ] || [ ! -r "$DB" ]; then
  log "canonical database unavailable: $DB"
  exit 12
fi
if ! "$PYTHON_BIN" -c 'import os, sys' >/dev/null 2>&1; then
  log "database query failed: Python runtime unavailable ($PYTHON_BIN)"
  exit 13
fi
DB_REAL="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$DB")"
LEGACY_ROOT_REAL="$("$PYTHON_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$LEGACY_ROOT")"
case "$DB_REAL" in
  "$LEGACY_ROOT_REAL"|"$LEGACY_ROOT_REAL"/*)
    log "legacy internal database is forbidden: $DB_REAL"
    exit 14
    ;;
esac
if ! mkdir "$LOCK" 2>/dev/null; then
  log "another feed process holds lock — skip"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

write_watermark() {
  value="$1"
  tmp="${WATERMARK}.tmp.$$"
  if ! printf '%s\n' "$value" >"$tmp"; then
    log "watermark write failed: $WATERMARK"
    rm -f "$tmp" 2>/dev/null || true
    return 1
  fi
  if ! mv -f "$tmp" "$WATERMARK"; then
    log "watermark replace failed: $WATERMARK"
    rm -f "$tmp" 2>/dev/null || true
    return 1
  fi
}

producer_health_note() {
  if ! "$LAUNCHCTL_BIN" list 2>/dev/null | grep -Fq "$PRODUCER_LABEL"; then
    log "WARNING trickle daemon not running ($PRODUCER_LABEL)"
  fi
}

LAST="$(cat "$WATERMARK" 2>/dev/null || true)"
QUERY_OUTPUT="$("$PYTHON_BIN" - "$DB_REAL" "$LAST" 2>&1 <<'PY'
import datetime as dt
import sqlite3
import sys

path, watermark = sys.argv[1:]

def parse(value: str) -> dt.datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("empty timestamp")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    stamp = dt.datetime.fromisoformat(raw)
    if stamp.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return stamp.astimezone(dt.timezone.utc)

with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(papers)")}
    if "vaulted_at" not in columns:
        raise RuntimeError("papers.vaulted_at is missing")
    values = [row[0] for row in conn.execute(
        "SELECT vaulted_at FROM papers WHERE vaulted_at IS NOT NULL"
    )]
parsed = [(parse(value), value) for value in values]
newest = max(parsed, default=(None, ""), key=lambda item: item[0] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
watermark_dt = parse(watermark) if watermark else None
count = sum(1 for stamp, _ in parsed if watermark_dt is not None and stamp > watermark_dt)
print(newest[1])
print(count)
PY
)"
QUERY_RC=$?
if [ "$QUERY_RC" -ne 0 ]; then
  if [ -n "$LAST" ] && ! "$PYTHON_BIN" - "$LAST" >/dev/null 2>&1 <<'PY'
import datetime as dt
import sys
raw = sys.argv[1].strip()
if raw.endswith("Z"):
    raw = raw[:-1] + "+00:00"
stamp = dt.datetime.fromisoformat(raw)
if stamp.tzinfo is None:
    raise ValueError("timestamp lacks timezone")
PY
  then
    log "invalid watermark: $LAST"
    exit 15
  fi
  QUERY_ERROR="$(printf '%s' "$QUERY_OUTPUT" | tail -n 1 | tr '\n' ' ')"
  log "database query failed: $QUERY_ERROR"
  exit 16
fi
NEWEST="$(printf '%s\n' "$QUERY_OUTPUT" | sed -n '1p')"
COUNT="$(printf '%s\n' "$QUERY_OUTPUT" | sed -n '2p')"
case "$COUNT" in ''|*[!0-9]*) log "database query failed: invalid count"; exit 17 ;; esac

if [ -z "$LAST" ]; then
  BASELINE="${NEWEST:-1970-01-01T00:00:00+00:00}"
  write_watermark "$BASELINE" || exit 18
  log "initialized watermark to current canonical state $BASELINE — no dispatch"
  producer_health_note
  exit 0
fi
if [ "$COUNT" -eq 0 ]; then
  log "nothing new"
  producer_health_note
  exit 0
fi
if ! command -v "$GH_BIN" >/dev/null 2>&1; then
  log "could not reconcile active ingestion runs: GitHub CLI unavailable ($GH_BIN)"
  exit 19
fi
ACTIVE_JSON="$("$GH_BIN" run list --repo "$REPO" --workflow "$WORKFLOW" \
  --limit 20 --json databaseId,status,conclusion,event,createdAt,url 2>>"$LOG")"
LIST_RC=$?
if [ "$LIST_RC" -ne 0 ]; then
  log "could not reconcile active ingestion runs (rc=$LIST_RC)"
  exit 20
fi
ACTIVE_DECISION="$(GH_RUNS_JSON="$ACTIVE_JSON" "$PYTHON_BIN" - "$NEWEST" 2>&1 <<'PY'
import datetime as dt
import json
import os
import sys

def parse(value: str) -> dt.datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    stamp = dt.datetime.fromisoformat(raw)
    if stamp.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return stamp.astimezone(dt.timezone.utc)

latest = parse(sys.argv[1])
runs = json.loads(os.environ.get("GH_RUNS_JSON", "[]"))
active = [run for run in runs if run.get("status") in {"queued", "in_progress", "waiting", "requested", "pending"}]
if not active:
    print("NONE")
else:
    newest = max(active, key=lambda run: parse(str(run["createdAt"])))
    mode = "COVER" if parse(str(newest["createdAt"])) >= latest else "DEFER"
    print("\t".join([mode, str(newest.get("databaseId", "")), str(newest["createdAt"]), str(newest.get("url", ""))]))
PY
)"
ACTIVE_RC=$?
if [ "$ACTIVE_RC" -ne 0 ]; then
  ACTIVE_ERROR="$(printf '%s' "$ACTIVE_DECISION" | tail -n 1 | tr '\n' ' ')"
  log "could not reconcile active ingestion runs: $ACTIVE_ERROR"
  exit 21
fi
IFS=$'\t' read -r ACTIVE_MODE ACTIVE_ID ACTIVE_CREATED ACTIVE_URL <<EOF
$ACTIVE_DECISION
EOF
case "$ACTIVE_MODE" in
  COVER)
    write_watermark "$NEWEST" || exit 22
    log "active ingestion run $ACTIVE_ID already covers latest vault row $NEWEST — watermark advanced"
    producer_health_note
    exit 0
    ;;
  DEFER)
    log "active ingestion run $ACTIVE_ID at $ACTIVE_CREATED predates latest vault row $NEWEST — defer"
    producer_health_note
    exit 0
    ;;
  NONE) ;;
  *) log "could not reconcile active ingestion runs: invalid decision"; exit 21 ;;
esac

log "$COUNT new vault publish(es) since $LAST — triggering ingest"
DISPATCH_OUTPUT="$("$GH_BIN" workflow run "$WORKFLOW" --repo "$REPO" --ref "$BRANCH" 2>&1)"
DISPATCH_RC=$?
if [ "$DISPATCH_RC" -ne 0 ]; then
  DISPATCH_ERROR="$(printf '%s' "$DISPATCH_OUTPUT" | tail -n 1 | tr '\n' ' ')"
  log "dispatch failed (rc=$DISPATCH_RC): $DISPATCH_ERROR; watermark preserved for retry"
  exit 23
fi
if ! write_watermark "$NEWEST"; then
  log "ingest dispatch succeeded but watermark did not advance; active-run dedupe must reconcile next tick"
  exit 24
fi
DISPATCH_RECEIPT="$(printf '%s' "$DISPATCH_OUTPUT" | tail -n 1 | tr '\n' ' ')"
log "ingest triggered successfully — watermark $NEWEST — $DISPATCH_RECEIPT"
producer_health_note
exit 0
