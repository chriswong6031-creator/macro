"""Detect official US macro release publication without advancing research ledgers.

This is the VPS publication edge for Release Radar.  It polls only when a tracked
release is due, records an official-source fingerprint, and emits the display-only
``release_publications.json`` sidecar.  It deliberately does *not* write ``data/``,
parse a value into the forecast scoreboard, or advance the forward ledger.  The
nightly pipeline remains the canonical vintage/revision and scoring writer.

Detection and value ingestion are separate on purpose:

* this watcher answers "has the source published?" within roughly one timer tick;
* a provider/official-API adapter can later attach values to the same sidecar;
* the nightly ALFRED/official-source reconciliation owns canonical actuals.

The first poll before a release seeds a baseline.  A post-release content change is
then a publication.  If the process starts after the scheduled time, publisher dates
and HTTP ``Last-Modified`` metadata provide a conservative cold-start recovery path.
Every network/source failure is represented in source health and never raises into
the rest of the live loop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from engine import event_calendar

log = logging.getLogger("release_publications")

NY = ZoneInfo("America/New_York")
USER_AGENT = "Mastermind-Macro-Publication-Watcher/1.0 (+https://www.mastermind-x.com)"
POLL_BEFORE = timedelta(minutes=12)
POLL_AFTER = timedelta(hours=6)


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    event_types: tuple[str, ...]
    publisher: str
    url: str
    keywords: tuple[str, ...]


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "bls_cpi",
        ("CPI",),
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/news.release/cpi.nr0.htm",
        ("consumer price index", "cpi"),
    ),
    SourceSpec(
        "bls_ppi",
        ("PPI",),
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/news.release/ppi.nr0.htm",
        ("producer price index", "ppi"),
    ),
    SourceSpec(
        "bls_employment",
        ("NFP",),
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/news.release/empsit.nr0.htm",
        ("employment situation", "nonfarm"),
    ),
    SourceSpec(
        "bea_releases",
        ("GDP", "PCE"),
        "U.S. Bureau of Economic Analysis",
        "https://www.bea.gov/news/current-releases",
        ("gross domestic product", "personal income and outlays"),
    ),
    SourceSpec(
        "dol_claims",
        ("CLAIMS",),
        "U.S. Department of Labor",
        "https://www.dol.gov/ui/data.pdf",
        ("unemployment insurance", "initial claims"),
    ),
)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write valid JSON by same-directory temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def scheduled_releases(day: date, horizon_days: int = 3) -> list[dict[str, Any]]:
    """Network-free release subset from the shared event-calendar source of truth."""
    end = day + timedelta(days=max(0, horizon_days))
    out: list[dict[str, Any]] = []
    for event_type in ("CPI", "PPI", "NFP", "GDP", "PCE"):
        dates, source = event_calendar._scheduled_release_dates(  # noqa: SLF001
            event_type, day, end, use_fred=False
        )
        for event_day in dates:
            meta = event_calendar._META[event_type]  # noqa: SLF001
            out.append(
                {
                    "type": event_type,
                    "date": event_day.isoformat(),
                    "time_et": meta["time_et"],
                    "label": meta["label"],
                    "label_zh": meta["label_zh"],
                    "schedule_source": source,
                    "is_context_only": True,
                }
            )
    current = day
    while current <= end:
        if current.weekday() == 3:
            meta = event_calendar._META["CLAIMS"]  # noqa: SLF001
            out.append(
                {
                    "type": "CLAIMS",
                    "date": current.isoformat(),
                    "time_et": meta["time_et"],
                    "label": meta["label"],
                    "label_zh": meta["label_zh"],
                    "schedule_source": "computed",
                    "is_context_only": True,
                }
            )
        current += timedelta(days=1)
    return sorted(out, key=lambda row: (row["date"], row["time_et"], row["type"]))


def _event_at(event: dict[str, Any]) -> datetime:
    hh, mm = (int(part) for part in str(event["time_et"]).split(":", 1))
    return datetime.combine(date.fromisoformat(event["date"]), time(hh, mm), NY)


def active_events(events: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    now_et = now.astimezone(NY)
    return [
        event
        for event in events
        if _event_at(event) - POLL_BEFORE <= now_et <= _event_at(event) + POLL_AFTER
    ]


def _fetch(spec: SourceSpec, prior: dict[str, Any], timeout: float) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}
    if prior.get("etag"):
        headers["If-None-Match"] = str(prior["etag"])
    if prior.get("last_modified"):
        headers["If-Modified-Since"] = str(prior["last_modified"])
    request = urllib.request.Request(spec.url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_000)
            return {
                "status": int(getattr(response, "status", 200)),
                "body": body,
                "fingerprint": hashlib.sha256(body).hexdigest(),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_type": response.headers.get("Content-Type"),
            }
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return {
                "status": 304,
                "body": b"",
                "fingerprint": prior.get("fingerprint"),
                "etag": prior.get("etag"),
                "last_modified": prior.get("last_modified"),
                "content_type": prior.get("content_type"),
            }
        raise


def _date_markers(day: date) -> tuple[str, ...]:
    full = day.strftime("%B %d, %Y")
    full_plain = full.replace(" 0", " ")
    return (
        full.lower(),
        full_plain.lower(),
        day.strftime("%m/%d/%Y").lower(),
        day.isoformat().lower(),
    )


def _last_modified_is_day(value: str | None, day: date) -> bool:
    if not value:
        return False
    try:
        return parsedate_to_datetime(value).astimezone(NY).date() == day
    except (TypeError, ValueError, OverflowError):
        return False


def _body_looks_published(body: bytes, event: dict[str, Any], spec: SourceSpec) -> bool:
    if not body:
        return False
    text = re.sub(r"\s+", " ", body.decode("utf-8", errors="ignore")).lower()
    dated = any(marker in text for marker in _date_markers(date.fromisoformat(event["date"])))
    relevant = any(keyword.lower() in text for keyword in spec.keywords)
    return dated and relevant


def detect(
    *,
    now: datetime,
    state: dict[str, Any],
    fetcher=_fetch,
    timeout: float = 12.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one detection tick; pure apart from the injected HTTP fetcher."""
    now = now.astimezone(timezone.utc)
    today_et = now.astimezone(NY).date()
    events = scheduled_releases(today_et, horizon_days=7)
    due = active_events(events, now)
    source_state = dict(state.get("sources") or {})
    publications = dict(state.get("publications") or {})
    health: list[dict[str, Any]] = []

    for spec in SOURCES:
        matching = [event for event in due if event["type"] in spec.event_types]
        if not matching:
            continue
        prior = dict(source_state.get(spec.source_id) or {})
        try:
            result = fetcher(spec, prior, timeout)
            changed = bool(
                prior.get("fingerprint")
                and result.get("fingerprint")
                and prior["fingerprint"] != result["fingerprint"]
            )
            source_state[spec.source_id] = {
                "fingerprint": result.get("fingerprint"),
                "etag": result.get("etag"),
                "last_modified": result.get("last_modified"),
                "content_type": result.get("content_type"),
                "checked_at": now.isoformat(),
            }
            for event in matching:
                event_key = f"{event['type']}:{event['date']}"
                release_time = _event_at(event)
                after_release = now.astimezone(NY) >= release_time
                cold_start_match = (
                    _body_looks_published(result.get("body") or b"", event, spec)
                    or _last_modified_is_day(result.get("last_modified"), today_et)
                )
                if after_release and (changed or (not prior and cold_start_match)):
                    publications.setdefault(
                        event_key,
                        {
                            **event,
                            "status": "published",
                            "detected_at": now.isoformat(),
                            "publisher": spec.publisher,
                            "source_id": spec.source_id,
                            "source_url": spec.url,
                            "content_sha256": result.get("fingerprint"),
                            "data_ready": False,
                            "is_context_only": True,
                            "note": (
                                "Official publication detected. Canonical actuals and "
                                "forward-ledger scoring reconcile in the nightly lane."
                            ),
                        },
                    )
            health.append(
                {
                    "source_id": spec.source_id,
                    "status": "not_modified" if result.get("status") == 304 else "ok",
                    "http_status": result.get("status"),
                    "changed": changed,
                }
            )
        except Exception as exc:  # noqa: BLE001 - source failure is display health
            health.append(
                {
                    "source_id": spec.source_id,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
            )

    new_state = {
        "schema": "release_publication_state.v1",
        "sources": source_state,
        "publications": publications,
        "updated_at": now.isoformat(),
    }
    payload = {
        "schema": "release_publications.v1",
        "built": now.isoformat(),
        "poll_window": {"before_min": 12, "after_min": 360},
        "due": due,
        "upcoming": events,
        "publications": sorted(
            publications.values(), key=lambda row: (row.get("date", ""), row.get("type", ""))
        )[-20:],
        "source_health": health,
        "canonical_reconciliation": "nightly",
        "is_context_only": True,
    }
    return new_state, payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="display-only JSON sidecar path")
    parser.add_argument("--state-dir", required=True, help="durable VPS state directory")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--now", default=None, help="test override: ISO-8601 timestamp")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    state_path = state_dir / "release_publications_state.json"
    state = _load_json(state_path)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    new_state, payload = detect(now=now, state=state, timeout=args.timeout)
    atomic_write_json(state_path, new_state)
    atomic_write_json(Path(args.out), payload)
    log.info(
        "wrote %s — due=%d published=%d sources=%d",
        args.out,
        len(payload["due"]),
        len(payload["publications"]),
        len(payload["source_health"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
