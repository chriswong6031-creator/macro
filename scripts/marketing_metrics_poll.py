"""scripts/marketing_metrics_poll.py — D02 per-post metrics poller.

Reads back per-post analytics for recently-posted marketing items and appends
them to an append-only ledger. Posts today are fire-and-forget: this closes the
loop so the admin console can show impressions/likes/reposts/comments/clicks and
the post's public x.com permalink (which createPost never returns).

DARK BY DEFAULT — exactly like scripts/marketing_publisher.py. With BUFFER_TOKEN
unset the poller prints one line and exits 0 (no network, no ledger write), so
the marketing-publish workflow can run it unconditionally after the publish step.

Sources of "what to poll" (deduped by remote id = Buffer post id):
  * data/marketing/outbox/status_ledger.jsonl — every `posted` transition
    carries receipt.external_id (the Buffer post id) and the row `at`.
  * data/marketing/publications.jsonl — the publications bridge; rows carry
    remote_id (platform post id) + account + published_at.
Only posts newer than --max-age-days (default 7, matching the Sentinel
receipt-age window) are polled; older analytics have stopped moving.

Output — append-only data/marketing/post_metrics.jsonl, one row per
(remote_id, poll date):
  {remote_id, account, external_url, metrics: {impressions?, likes?, reposts?,
   comments?, clicks?, engagement_rate?}, metrics_raw: [{type,name,value,unit}],
   metrics_updated_at, polled_at, ok, note?}
Re-runs re-poll (metrics refresh ~daily); a same-day re-run overwrites nothing —
each run appends a fresh dated row (append-only ledger law). Empty/absent
metrics produce an honest row with metrics={} and a note.

external_url backfill: when a polled post's publications.jsonl row lacks an
external_url and Buffer returns one, the appended metrics row carries it. We do
NOT rewrite publications.jsonl (append-only) — the metrics ledger is the
external_url of record for the console join.

Usage:
    # dry-run (default network-free listing of what WOULD be polled)
    python -m scripts.marketing_metrics_poll --dry-run

    # live poll (needs BUFFER_TOKEN in env; dark/no-op without it)
    BUFFER_TOKEN=... python -m scripts.marketing_metrics_poll
    BUFFER_TOKEN=... python -m scripts.marketing_metrics_poll --max-age-days 7
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("marketing_metrics_poll")


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrapping helpers (mirror scripts/marketing_publisher.py)
# ─────────────────────────────────────────────────────────────────────────────

def _code_root() -> Path:
    """Directory containing engine/ — always where this script lives (../)."""
    return Path(__file__).resolve().parent.parent


def _data_root(root_arg: str | None) -> Path:
    return Path(root_arg) if root_arg is not None else _code_root()


def _metrics_ledger_path(root: Path) -> Path:
    return root / "data" / "marketing" / "post_metrics.jsonl"


def _publications_path(root: Path) -> Path:
    return root / "data" / "marketing" / "publications.jsonl"


_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an iso8601-ish timestamp to an aware UTC datetime, or None."""
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    # Tolerate a trailing Z and fractional seconds; fall back to date-only.
    for candidate in (s, s.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Gather targets — dedupe by remote id across both ledgers
# ─────────────────────────────────────────────────────────────────────────────

def gather_targets(root: Path, *, now: datetime, max_age_days: int) -> list[dict]:
    """Collect {remote_id, account, source_ts, external_url} rows to poll.

    Deduped by remote_id (Buffer post id). status_ledger.jsonl wins the account
    field when both sources carry the same id (the outbox is the actuation
    source of truth). Only ids whose source timestamp is within max_age_days of
    `now` are returned. Fail-soft: unreadable ledgers contribute nothing.
    """
    from engine.marketing import outbox as _outbox  # noqa: PLC0415
    from engine.marketing.ledgers import read_jsonl  # noqa: PLC0415

    cutoff = now - timedelta(days=max_age_days)
    by_id: dict[str, dict] = {}

    # (1) Outbox status ledger: posted transitions carry receipt.external_id.
    try:
        state = _outbox.fold_state(root)
        items = state.get("items") or {}
        last = state.get("last") or {}
        status = state.get("status") or {}
        for iid, st in status.items():
            if st != "posted":
                continue
            lr = last.get(iid) or {}
            rec = lr.get("receipt")
            rec = rec if isinstance(rec, dict) else {}
            remote_id = str(rec.get("external_id") or "").strip()
            if not remote_id:
                continue
            src_ts = _parse_iso(rec.get("at") or lr.get("at"))
            if src_ts is None or src_ts < cutoff:
                continue
            it = items.get(iid) or {}
            by_id[remote_id] = {
                "remote_id": remote_id,
                "account": it.get("account", "") or "",
                "source_ts": src_ts,
                "external_url": (rec.get("external_url") or None),
                "origin": "status_ledger",
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("gather_targets: outbox ledger read failed: %s", exc)

    # (2) Publications bridge ledger: rows carry remote_id + account.
    try:
        for row in read_jsonl(_publications_path(root)):
            if not isinstance(row, dict):
                continue
            remote_id = str(row.get("remote_id") or "").strip()
            if not remote_id:
                continue
            src_ts = _parse_iso(row.get("published_at"))
            if src_ts is None or src_ts < cutoff:
                continue
            if remote_id in by_id:
                # Outbox already claimed this id; only backfill a missing url.
                if not by_id[remote_id].get("external_url") and row.get("external_url"):
                    by_id[remote_id]["external_url"] = row.get("external_url")
                continue
            by_id[remote_id] = {
                "remote_id": remote_id,
                "account": row.get("account", "") or "",
                "source_ts": src_ts,
                "external_url": (row.get("external_url") or None),
                "origin": "publications",
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("gather_targets: publications ledger read failed: %s", exc)

    return sorted(by_id.values(), key=lambda r: r["source_ts"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Poll
# ─────────────────────────────────────────────────────────────────────────────

def poll(
    root: Path,
    *,
    now: datetime | None = None,
    max_age_days: int = 7,
    dry_run: bool = False,
    publisher=None,
) -> dict:
    """Poll metrics for recently-posted items; append rows to post_metrics.jsonl.

    Returns a summary dict {targets, polled, ok, empty, failed, dry_run, dark}.
    Fail-soft everywhere — one bad post never aborts the batch.
    """
    from engine.marketing.ledgers import append_jsonl  # noqa: PLC0415
    from engine.marketing.social_publisher import BUFFER_TOKEN_ENV, BufferPublisher  # noqa: PLC0415

    ts_now = now if now is not None else datetime.now(timezone.utc)
    polled_at = ts_now.strftime(_ISO_FMT)

    targets = gather_targets(root, now=ts_now, max_age_days=max_age_days)
    summary = {
        "targets": len(targets),
        "polled": 0,
        "ok": 0,
        "empty": 0,
        "failed": 0,
        "dry_run": bool(dry_run),
        "dark": False,
    }

    if dry_run:
        for t in targets:
            log.info("DRY-RUN would poll remote_id=%s account=%s posted=%s",
                     t["remote_id"], t["account"] or "?",
                     t["source_ts"].strftime(_ISO_FMT))
        log.info("marketing_metrics_poll: DRY-RUN — %d target(s), no network, no write",
                 len(targets))
        return summary

    # Dark by default: no token → one line + exit 0 (workflow-safe).
    token = os.environ.get(BUFFER_TOKEN_ENV, "").strip()
    if publisher is None and not token:
        summary["dark"] = True
        log.info("marketing_metrics_poll: no %s in env — dark, %d posted item(s) "
                 "left un-polled (no-op, exit 0)", BUFFER_TOKEN_ENV, len(targets))
        return summary

    pub = publisher if publisher is not None else BufferPublisher(token=token)
    ledger_path = _metrics_ledger_path(root)

    for t in targets:
        res = pub.fetch_post_metrics(t["remote_id"], now=ts_now)
        summary["polled"] += 1

        row: dict = {
            "remote_id": t["remote_id"],
            "account": t["account"] or "",
            # Prefer the freshly-fetched permalink; else carry any known url.
            "external_url": res.external_url or t.get("external_url") or None,
            "metrics": res.metrics,
            "metrics_raw": res.raw,
            "metrics_updated_at": res.metrics_updated_at,
            "polled_at": polled_at,
            "ok": bool(res.ok),
        }
        if not res.ok:
            summary["failed"] += 1
            row["note"] = f"poll_failed: {res.error}"
        elif not res.metrics:
            summary["empty"] += 1
            summary["ok"] += 1
            row["note"] = "metrics_empty (not yet refreshed by backend)"
        else:
            summary["ok"] += 1

        append_jsonl(ledger_path, row)

    log.info("marketing_metrics_poll: polled=%d ok=%d empty=%d failed=%d → %s",
             summary["polled"], summary["ok"], summary["empty"], summary["failed"],
             ledger_path)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Marketing per-post metrics poller (D02 — dark by default)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="list what WOULD be polled; zero network, zero write")
    parser.add_argument("--max-age-days", type=int, default=7,
                        help="only poll posts newer than this many days (default 7)")
    parser.add_argument("--root", default=None,
                        help="Repo root directory (default: derived from script location)")
    parser.add_argument("--now", default=None,
                        help="Override 'now' as ISO8601 (testing/determinism)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Make engine.* importable when run as a module OR as a file.
    sys.path.insert(0, str(_code_root()))

    root = _data_root(args.root)
    now = None
    if args.now:
        from engine.marketing.social_publisher import _iso_now  # noqa: PLC0415,F401
        parsed = _parse_iso(args.now)
        if parsed is None:
            log.warning("bad --now %r; using wall-clock", args.now)
        now = parsed

    poll(root, now=now, max_age_days=args.max_age_days, dry_run=bool(args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
