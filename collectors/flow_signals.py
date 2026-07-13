"""collectors/flow_signals.py — append-only flow-event PIT ledger harvester.

Harvests qualifying flow events from the live_flow R2 archive blobs and the
feed_current.json snapshot, deduplicates on _event_id (keep-first), normalizes
all timestamps to timezone-aware UTC, and appends new rows to
data/flow_signals/ledger.parquet.

SOURCE PRIORITY ORDER (FS-R1 / masterplan §2 F1):
  1. R2 live_flow/archive/YYYYMMDDTHH.json blobs within the 48h window.
  2. live_flow/feed_current.json snapshot (supplement for events not in archive).

ARCHIVE UPLOAD REALITY (verified in scripts/live_flow_poller.py lines 1514-1519):
  The poller DOES upload hourly archive blobs to R2 under the key
  live_flow/archive/YYYYMMDDTHH.json (ARCHIVE_HOUR_CADENCE=3600s, pruned at 48h).
  The key stem format is strftime("%Y%m%dT%H"). Both the local write AND R2 upload
  occur in the poller's main loop, so archive blobs exist on R2 whenever the
  poller ran. If R2 creds are absent or no blobs exist yet (first run before the
  poller has cycled for an hour), the collector falls back to feed_current.json.

PIT CONTRACT:
  - Append-only: existing rows are never mutated.
  - keep-first on _event_id: the first ingested record for a given event id is
    the authority; subsequent harvests of the same blob are safe (idempotent).
  - detector_version from config/flow_detector.yml is stamped on every row.
  - All timestamps (ts, ingested_at) are timezone-aware UTC at parse.
  - source field = 'live_feed' for all rows from this collector.

SINGLE-WRITER LAW: only this collector writes to data/flow_signals/ledger.parquet.
  The outcome grader (engine/flow_signals_grade.py) reads the ledger and writes
  a separate data/flow_signals/grades.parquet — no commingling of write paths.

GRACEFUL DEGRADATION:
  Absent R2 creds / no archive blobs / empty feed / missing config →
  clean no-op with a log line. Never a crash, never fake rows.

Usage (nightly, via scripts/build_flow_signals.py):
  from collectors.flow_signals import harvest
  n_new = harvest()

Usage (smoke, no side-effects):
  python -m collectors.flow_signals --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
LEDGER_DIR = "flow_signals"
LEDGER_FILE = "ledger.parquet"
R2_ARCHIVE_PREFIX = "live_flow/archive/"
R2_FEED_KEY = "live_flow/feed_current.json"
ARCHIVE_WINDOW_HOURS = 48

# Detector version loaded from config/flow_detector.yml at module import.
# Cached after first load; consumers see the same version for the process lifetime.
_DETECTOR_VERSION: str | None = None

# Full event schema columns (all fields from engine/live_flow.py event dict).
# These are the ingest fields — never mutated after first write (keep-first law).
_EVENT_COLS = [
    "event_id",       # renamed from 'id' for clarity in parquet schema
    "session_date",   # injected from archive key / feed session_date field
    "ts",             # trade timestamp (aware-UTC string, normalized at parse)
    "root",
    "group",
    "group_zh",
    "right",
    "exp",
    "strike",
    "dte",
    "dte_bucket",
    "mny_bucket",
    "side",
    "n_prints",
    "size",
    "avg_price",
    "premium",
    "premium_z",
    "baseline_source",
    "vol_gt_oi",
    "repeated",
    "zerodte",
    "signing_source",
    "swept",
    # Collector-stamped metadata
    "detector_version",
    "source",         # 'live_feed'
    "ingested_at",    # aware-UTC ISO string
]


# ── detector version loader ───────────────────────────────────────────────────

def _load_detector_version() -> str:
    """Return detector version from config/flow_detector.yml.

    Caches in module-level _DETECTOR_VERSION. Falls back to 'unknown' on any
    error (logged; never a crash).
    """
    global _DETECTOR_VERSION
    if _DETECTOR_VERSION is not None:
        return _DETECTOR_VERSION
    try:
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "flow_detector.yml"
        if not cfg_path.exists():
            log.warning("flow_signals: config/flow_detector.yml not found — version='unknown'")
            _DETECTOR_VERSION = "unknown"
            return _DETECTOR_VERSION
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f)
        ver = str(cfg.get("version", "unknown"))
        _DETECTOR_VERSION = ver
        return _DETECTOR_VERSION
    except Exception as e:  # noqa: BLE001
        log.warning("flow_signals: could not load detector version: %s", e)
        _DETECTOR_VERSION = "unknown"
        return _DETECTOR_VERSION


# ── R2 client (same pattern as live_flow_poller.py) ─────────────────────────

def _r2_client():
    """Build boto3 S3 client for R2 using env vars R2_ENDPOINT / R2_ACCESS_KEY_ID
    / R2_SECRET_ACCESS_KEY. Returns None if creds absent (graceful degradation).
    """
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        log.info("flow_signals: R2 creds absent — archive harvest skipped")
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(region_name="auto", signature_version="s3v4",
                  max_pool_connections=4,
                  retries={"max_attempts": 3, "mode": "standard"})
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep,
                            aws_access_key_id=ak,
                            aws_secret_access_key=sk,
                            config=cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("flow_signals: R2 client build failed: %s", e)
        return None


def _r2_bucket() -> str:
    """Return R2 bucket name from env R2_BUCKET (default: mastermindx)."""
    return os.environ.get("R2_BUCKET", "mastermindx")


# ── archive blob discovery ────────────────────────────────────────────────────

def _archive_keys_within_window(s3, bucket: str,
                                window_hours: int = ARCHIVE_WINDOW_HOURS) -> list[str]:
    """List live_flow/archive/ keys whose timestamp is within window_hours of now.

    Archive key format: live_flow/archive/YYYYMMDDTHH.json
    Stem format: strftime('%Y%m%dT%H')  (verified: live_flow_poller.py:1515,1517-1518)
    """
    try:
        out: list[str] = []
        tok = None
        while True:
            kw: dict[str, Any] = {"Bucket": bucket, "Prefix": R2_ARCHIVE_PREFIX}
            if tok:
                kw["ContinuationToken"] = tok
            r = s3.list_objects_v2(**kw)
            for o in r.get("Contents", []):
                out.append(o["Key"])
            if not r.get("IsTruncated"):
                break
            tok = r.get("NextContinuationToken")
    except Exception as e:  # noqa: BLE001
        log.warning("flow_signals: list archive keys failed: %s", e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    valid: list[str] = []
    for k in out:
        stem = Path(k).stem  # e.g. "20260713T14"
        try:
            ts = datetime.strptime(stem, "%Y%m%dT%H").replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                valid.append(k)
        except Exception:  # noqa: BLE001
            pass  # non-standard key; skip silently
    return sorted(valid)


def _fetch_r2_json(s3, bucket: str, key: str) -> dict | None:
    """Download a JSON object from R2. Returns None on any error."""
    try:
        import io
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        return json.loads(body)
    except Exception as e:  # noqa: BLE001
        log.warning("flow_signals: fetch R2 key %s failed: %s", key, e)
        return None


# ── timestamp normalization ───────────────────────────────────────────────────

def _normalize_ts(ts_val: Any) -> str:
    """Normalize any timestamp representation to aware-UTC ISO string.

    Handles:
      - strings ending in 'Z' (already UTC)
      - strings with '+00:00' suffix
      - naive strings (assume UTC per repo convention)
      - pd.Timestamp / datetime objects

    Returns ISO string like '2026-07-13T14:23:45+00:00'.
    Raises on completely unparsable input (caller should catch).
    """
    ts = pd.Timestamp(ts_val)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()  # includes +00:00 offset for aware timestamps


def _infer_session_date_from_archive_key(key: str) -> str | None:
    """Infer YYYY-MM-DD session date from archive key stem YYYYMMDDTHH."""
    stem = Path(key).stem
    try:
        ts = datetime.strptime(stem, "%Y%m%dT%H")
        return ts.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


# ── event extraction ─────────────────────────────────────────────────────────

def _events_from_blob(blob: dict, session_date_hint: str | None = None) -> list[dict]:
    """Extract and normalize events from a feed/archive blob.

    A blob is either a live_flow.feed/v1 payload (has 'events' list) or a
    raw list of event dicts. Returns normalized event dicts ready for ledger.
    """
    if isinstance(blob, list):
        raw_events = blob
        session_date = session_date_hint or ""
        if session_date_hint:
            # N8: UTC archive-key hint can mis-date late-ET sessions (events after
            # ~20:00 UTC belong to the next calendar day per the key stem but may
            # have been captured for the prior trading session).
            log.warning(
                "flow_signals: blob is a raw list — session_date derived from UTC "
                "archive-key hint '%s' which can mis-date late-ET sessions",
                session_date_hint,
            )
    elif isinstance(blob, dict):
        raw_events = blob.get("events", [])
        blob_session = blob.get("session_date", "")
        if blob_session:
            session_date = blob_session
        elif session_date_hint:
            # N8: fell back to UTC archive-key hint; warn because late-ET sessions
            # risk being stamped with the wrong date.
            session_date = session_date_hint
            log.warning(
                "flow_signals: blob lacks session_date field — falling back to "
                "UTC archive-key hint '%s' which can mis-date late-ET sessions",
                session_date_hint,
            )
        else:
            session_date = ""
    else:
        return []

    ingested_at = datetime.now(timezone.utc).isoformat()
    detector_version = _load_detector_version()
    results: list[dict] = []

    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        event_id = ev.get("id", "")
        if not event_id:
            continue  # malformed event; skip

        # Normalize timestamp to aware-UTC
        raw_ts = ev.get("ts", "")
        try:
            ts_norm = _normalize_ts(raw_ts) if raw_ts else ""
        except Exception:  # noqa: BLE001
            ts_norm = ""

        row: dict[str, Any] = {
            "event_id":        str(event_id),
            "session_date":    str(session_date),
            "ts":              ts_norm,
            "root":            str(ev.get("root", "")),
            "group":           str(ev.get("group", "")),
            "group_zh":        str(ev.get("group_zh", "")),
            "right":           str(ev.get("right", "")),
            "exp":             str(ev.get("exp", "")),
            "strike":          _coerce_float(ev.get("strike")),
            "dte":             _coerce_int(ev.get("dte")),
            "dte_bucket":      str(ev.get("dte_bucket", "")),
            "mny_bucket":      str(ev.get("mny_bucket", "unknown")),
            "side":            str(ev.get("side", "mixed")),
            "n_prints":        _coerce_int(ev.get("n_prints", 1)),
            "size":            _coerce_int(ev.get("size", 0)),
            "avg_price":       _coerce_float(ev.get("avg_price")),
            "premium":         _coerce_float(ev.get("premium")),
            "premium_z":       _coerce_float(ev.get("premium_z")),
            "baseline_source": str(ev.get("baseline_source", "")),
            "vol_gt_oi":       _coerce_bool(ev.get("vol_gt_oi")),
            "repeated":        _coerce_bool(ev.get("repeated", False)),
            "zerodte":         _coerce_bool(ev.get("zerodte", False)),
            "signing_source":  str(ev.get("signing_source", "tape")),
            "swept":           _coerce_bool(ev.get("swept", False)),
            "detector_version": detector_version,
            "source":          "live_feed",
            "ingested_at":     ingested_at,
        }
        results.append(row)

    return results


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        import math
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    try:
        return bool(int(v))
    except (TypeError, ValueError):
        return None


# ── ledger I/O ───────────────────────────────────────────────────────────────

def _ledger_path() -> Path:
    """Return the absolute path to data/flow_signals/ledger.parquet."""
    from lib import config
    p = config.data_dir() / LEDGER_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / LEDGER_FILE


_LEDGER_UNREADABLE = object()  # sentinel: ledger exists but could not be read


def _load_existing_ids(ledger_path: Path) -> set[str] | object:
    """Return the set of event_ids already in the ledger.

    Returns:
      - empty set: ledger file is absent (first run — fine, proceed)
      - set[str]:  ledger read successfully
      - _LEDGER_UNREADABLE sentinel: ledger exists but is corrupt/unreadable
        → caller MUST abort to avoid re-ingesting the full history (M3: fail CLOSED)
    """
    if not ledger_path.exists():
        return set()
    try:
        df = pd.read_parquet(ledger_path, columns=["event_id"])
        return set(df["event_id"].astype(str).tolist())
    except Exception as e:  # noqa: BLE001
        log.error(
            "flow_signals: ledger exists but is unreadable — aborting harvest "
            "to prevent double-ingest: %s", e
        )
        return _LEDGER_UNREADABLE


def _append_rows(ledger_path: Path, rows: list[dict]) -> int:
    """Append new rows to the ledger parquet. Returns count of rows written.

    Uses atomic write: writes to a temp file then renames.
    All timestamps in 'ts' and 'ingested_at' columns are stored as plain
    strings (no tz-aware dtype conversion) to avoid the LETHAL naive/aware
    mismatch class in parquet (tz-aware-into-naive-parquet memory).
    """
    if not rows:
        return 0
    new_df = pd.DataFrame(rows, columns=_EVENT_COLS)

    if ledger_path.exists():
        try:
            existing = pd.read_parquet(ledger_path)
        except Exception as e:  # noqa: BLE001
            log.error("flow_signals: could not read existing ledger: %s — aborting append", e)
            return 0
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df

    # Structural backstop: deduplicate on event_id, keep-first (M3).
    # This is a last-resort guard; the harvest loop's existing_ids check is
    # the primary dedup gate. This prevents a corrupt double-write from persisting.
    merged = merged.drop_duplicates(subset=["event_id"], keep="first")

    tmp = ledger_path.with_suffix(".tmp.parquet")
    try:
        merged.to_parquet(tmp, index=False)
        tmp.rename(ledger_path)
    except Exception as e:  # noqa: BLE001
        log.error("flow_signals: parquet write failed: %s", e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return 0

    return len(rows)


# ── feed_current.json fallback ────────────────────────────────────────────────

def _feed_current_path() -> Path | None:
    """Resolve the path to data/live_flow_out/feed_current.json.

    The poller writes this file to config.data_dir() / 'live_flow_out' /
    'feed_current.json' (see live_flow_poller._out_dir and _write_json).
    Returns None if not found.
    """
    try:
        from lib import config
        p = config.data_dir() / "live_flow_out" / "feed_current.json"
        return p if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _r2_feed_current(s3, bucket: str) -> dict | None:
    """Fetch live_flow/feed_current.json from R2. Returns None on any error."""
    return _fetch_r2_json(s3, bucket, R2_FEED_KEY)


# ── main harvest function ─────────────────────────────────────────────────────

def harvest(dry_run: bool = False) -> int:
    """Harvest flow events from R2 archives + feed_current, append to ledger.

    Returns the count of new rows appended (0 on no-op or error).

    Priority:
      1. R2 archive blobs within 48h window (preferred — more complete)
      2. feed_current.json (R2 then local) — supplement for events not in archive

    keep-first dedup on event_id ensures repeated harvests are idempotent.
    """
    ledger_path = _ledger_path()
    _existing = _load_existing_ids(ledger_path)
    if _existing is _LEDGER_UNREADABLE:
        # Ledger exists but is corrupt/unreadable — abort to prevent double-ingest (M3).
        log.error("flow_signals: harvest aborted — ledger unreadable (written nothing)")
        return 0
    existing_ids: set[str] = _existing  # type: ignore[assignment]
    all_new_rows: dict[str, dict] = {}  # event_id -> row (keep-first)

    s3 = _r2_client()
    bucket = _r2_bucket()

    # ── 1. R2 archive blobs ───────────────────────────────────────────────────
    n_archive_blobs = 0
    if s3 is not None:
        archive_keys = _archive_keys_within_window(s3, bucket, ARCHIVE_WINDOW_HOURS)
        log.info("flow_signals: found %d archive blobs within %dh window",
                 len(archive_keys), ARCHIVE_WINDOW_HOURS)
        for key in archive_keys:
            session_hint = _infer_session_date_from_archive_key(key)
            blob = _fetch_r2_json(s3, bucket, key)
            if blob is None:
                continue
            n_archive_blobs += 1
            for row in _events_from_blob(blob, session_date_hint=session_hint):
                eid = row["event_id"]
                if eid not in existing_ids and eid not in all_new_rows:
                    all_new_rows[eid] = row  # keep-first: first archive wins

    # ── 2. feed_current supplement ────────────────────────────────────────────
    # Fetch events from feed_current that weren't in archive blobs.
    feed_blob: dict | None = None
    if s3 is not None:
        feed_blob = _r2_feed_current(s3, bucket)
    if feed_blob is None:
        local_feed = _feed_current_path()
        if local_feed is not None:
            try:
                feed_blob = json.loads(local_feed.read_text())
                log.debug("flow_signals: loaded local feed_current.json (%s)", local_feed)
            except Exception as e:  # noqa: BLE001
                log.warning("flow_signals: local feed_current.json read failed: %s", e)

    if feed_blob is not None:
        for row in _events_from_blob(feed_blob):
            eid = row["event_id"]
            if eid not in existing_ids and eid not in all_new_rows:
                all_new_rows[eid] = row  # keep-first: archive already applied above

    new_rows = list(all_new_rows.values())
    log.info(
        "flow_signals: %d archive blobs processed; %d new events to append "
        "(existing ledger: %d rows)",
        n_archive_blobs, len(new_rows), len(existing_ids),
    )

    if not new_rows:
        log.info("flow_signals: nothing new to append — ledger unchanged")
        return 0

    if dry_run:
        log.info("flow_signals: dry-run — would append %d rows (not writing)", len(new_rows))
        return len(new_rows)

    n_written = _append_rows(ledger_path, new_rows)
    log.info("flow_signals: appended %d rows → %s", n_written, ledger_path)
    return n_written


# ── ledger stats ─────────────────────────────────────────────────────────────

def ledger_stats() -> dict:
    """Return summary stats for the current ledger. Empty dict if absent."""
    ledger_path = _ledger_path()
    if not ledger_path.exists():
        return {"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {}, "last_ts": None}
    try:
        df = pd.read_parquet(ledger_path,
                             columns=["event_id", "session_date", "dte_bucket", "ts"])
        n_rows = len(df)
        n_sessions = df["session_date"].nunique()
        dte_counts = df["dte_bucket"].value_counts().to_dict()

        # events per day
        events_per_day: dict[str, int] = {}
        if "session_date" in df.columns:
            epd = df.groupby("session_date").size()
            events_per_day = epd.to_dict()

        # last ingested ts (string; sort lexicographically on ISO strings)
        last_ts = df["ts"].dropna().max() if n_rows > 0 else None

        return {
            "n_rows": n_rows,
            "n_sessions": n_sessions,
            "dte_bucket_counts": {str(k): int(v) for k, v in dte_counts.items()},
            "events_per_day":    {str(k): int(v) for k, v in events_per_day.items()},
            "last_ts": str(last_ts) if last_ts is not None else None,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("flow_signals: ledger_stats failed: %s", e)
        return {"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {}, "last_ts": None}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flow-event ledger harvester")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count new events without writing to disk")
    parser.add_argument("--stats", action="store_true",
                        help="Print current ledger stats and exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.stats:
        stats = ledger_stats()
        import json as _json
        print(_json.dumps(stats, indent=2))
        return 0

    n = harvest(dry_run=args.dry_run)
    print(f"flow_signals: {'would append' if args.dry_run else 'appended'} {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
