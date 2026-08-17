"""Tripwire for the gap between PUBLISHED earnings records and UPSTREAM transcripts.

WHY THIS EXISTS (2026-08-02 -> 2026-08-14).  `earnings-evidence-graph` — the only
lane that ingests new calls — died on a missing `pyyaml` and stayed dead for
twelve days.  Nothing alarmed, because every instrument we owned was pointed at
the wrong thing:

* `earnings-story-packets` and `earnings-public-wire` both stayed GREEN.  They are
  downstream of the ingest, so they faithfully projected and republished a frozen
  evidence root once an hour.  A green lane republishing stale bytes is
  indistinguishable, from the lane's own vantage point, from a quiet news week.
* the hourly wire commit ("earnings-wire: publish current verified records")
  changed exactly one field — `verified_at` — so ~24 commits/day of pure churn
  read as a healthy publishing cadence.
* `scripts/audit_earnings_freshness.py` looks healthy and is NOT this: it grades
  the earnings CALENDAR store (`data/earnings/earnings.parquet`), a different
  artifact on a different lane.  Its green said nothing about the wire.

The measurement that would have caught it on day one is a CROSS-PLANE one, which
is why no single lane owned it: compare the newest call date we have PUBLISHED
against the newest call date the Terminal has ALREADY MADE AVAILABLE.  Both are
call dates, so the difference is a real lag in days, and the count of upstream
bodies newer than our newest published record is the actionable backlog number
(1,631 on the morning this was written).

SLA.  A small lag is normal and is NOT a defect: the ingest lane runs hourly in
bounded batches (<=500 bodies), so a heavy reporting day drains over a few runs.
The default gate warns at 3 days and escalates to ``::error`` at 7 — which would
have fired on 2026-08-09, five days before a human noticed.

CONTAINMENT.  This audit is annotations-only by default and writes nothing into
the repository.  `earnings-public-wire` stages `site/stocks/earnings` and the
content-hashed assets its pages link, and NOTHING else — no `data/` may ride out
on that lane — so a tripwire that wrote a quality artifact there would be a
containment break, not an improvement.  Use ``--json-out`` on lanes that want the
artifact.

Usage:
    python -m scripts.audit_earnings_wire_freshness
    python -m scripts.audit_earnings_wire_freshness --strict
    python -m scripts.audit_earnings_wire_freshness --index-file idx.json --offline
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CATALOG = _ROOT / "site" / "stocks" / "earnings" / "route-catalog.json"
DEFAULT_INDEX_URL = "https://app.mastermind-x.com/data/tx/index.json"
DEFAULT_WARN_DAYS = 3
DEFAULT_ERROR_DAYS = 7

_ISO_DATE = "%Y-%m-%d"


class EarningsWireFreshnessError(RuntimeError):
    """The audit could not be computed at all (missing/unreadable inputs)."""


def _parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), _ISO_DATE).date()
    except ValueError:
        return None


def newest_published_call_date(catalog: Mapping[str, Any]) -> date | None:
    """Newest call date across EVERY route event, not just each route's `latest`.

    Reading only `latest` would answer a different question — the freshest event
    per ticker — which stays comfortingly recent even when the archive as a whole
    has stopped advancing.
    """
    routes = catalog.get("routes")
    if not isinstance(routes, Mapping):
        raise EarningsWireFreshnessError("route catalog has no `routes` mapping")
    best: date | None = None
    for route in routes.values():
        if not isinstance(route, Mapping):
            continue
        events = route.get("events")
        if not isinstance(events, Mapping):
            continue
        for event in events.values():
            if not isinstance(event, Mapping):
                continue
            day = _parse_day(event.get("date"))
            if day is not None and (best is None or day > best):
                best = day
    return best


def as_of_day(index: Mapping[str, Any] | None = None, *, now: date | None = None) -> date:
    """The last day a transcript can be treated as an already-completed call.

    The Terminal index `dates` map includes scheduled/future call days. Using
    those as the upstream freshness ceiling reports an impossible date
    (observed 2026-08-16: published=2026-07-29 upstream=2026-08-20). Prefer the
    index's own `generated_at` day, then the supplied clock.
    """
    if now is None:
        now = datetime.now(timezone.utc).date()
    if isinstance(index, Mapping):
        generated = index.get("generated_at")
        if isinstance(generated, str) and len(generated) >= 10:
            parsed = _parse_day(generated[:10])
            if parsed is not None:
                return min(parsed, now)
    return now


def upstream_dates(
    index: Mapping[str, Any],
    *,
    as_of: date | None = None,
) -> list[date]:
    """Completed call dates advertised by the Terminal transcript index."""
    dates = index.get("dates")
    if not isinstance(dates, Mapping):
        # `dates` is a documented optional extension of the tx-index schema. With
        # no dates at all we cannot measure lag, and saying so beats inventing a
        # zero — a silent 0-day lag is exactly the false green this file exists
        # to prevent.
        raise EarningsWireFreshnessError(
            "terminal transcript index carries no `dates` map; lag is unmeasurable"
        )
    ceiling = as_of if as_of is not None else as_of_day(index)
    out = [
        d for d in (_parse_day(v) for v in dates.values())
        if d is not None and d <= ceiling
    ]
    if not out:
        raise EarningsWireFreshnessError("terminal transcript index `dates` map is empty")
    return out


def audit(
    catalog: Mapping[str, Any],
    index: Mapping[str, Any],
    *,
    warn_days: int = DEFAULT_WARN_DAYS,
    error_days: int = DEFAULT_ERROR_DAYS,
    as_of: date | None = None,
) -> dict:
    published = newest_published_call_date(catalog)
    ceiling = as_of if as_of is not None else as_of_day(index)
    upstream = upstream_dates(index, as_of=ceiling)
    newest_upstream = max(upstream)

    if published is None:
        raise EarningsWireFreshnessError("route catalog advertises no dated events")

    lag_days = (newest_upstream - published).days
    backlog = sum(1 for d in upstream if d > published)

    if lag_days >= error_days:
        level = "error"
    elif lag_days >= warn_days:
        level = "warning"
    else:
        level = "ok"

    return {
        "schema": "macro.earnings_wire_freshness/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "newest_published_call_date": published.strftime(_ISO_DATE),
        "newest_upstream_call_date": newest_upstream.strftime(_ISO_DATE),
        "as_of": ceiling.strftime(_ISO_DATE),
        "lag_days": lag_days,
        "upstream_bodies_newer_than_published": backlog,
        "article_count": catalog.get("article_count"),
        "catalog_as_of": catalog.get("as_of"),
        "warn_days": warn_days,
        "error_days": error_days,
        "level": level,
        "ok": level == "ok",
    }


def _load_index(index_file: str | None, index_url: str, *, offline: bool) -> dict:
    if index_file:
        return json.loads(Path(index_file).read_text(encoding="utf-8"))
    if offline:
        raise EarningsWireFreshnessError("--offline requires --index-file")
    import requests  # local import: the offline/test path must not need it

    response = requests.get(index_url, timeout=60)
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Earnings wire vs upstream transcript lag tripwire")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--index-file", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--warn-days", type=int, default=DEFAULT_WARN_DAYS)
    parser.add_argument("--error-days", type=int, default=DEFAULT_ERROR_DAYS)
    parser.add_argument("--json-out", default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when the lag has reached the error threshold",
    )
    args = parser.parse_args(argv)

    # Every annotation below is a BARE print starting at column 0 with flush=True.
    # Routing one through a logger prefixes it with the level name, GitHub silently
    # drops it, and the alarm reviews as armed while emitting nothing (CLAUDE.md
    # §GitHub annotations; tests/test_gh_annotation_line_start.py).
    try:
        catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
        index = _load_index(args.index_file, args.index_url, offline=args.offline)
        report = audit(
            catalog, index, warn_days=args.warn_days, error_days=args.error_days
        )
    except Exception as exc:  # an audit that cannot run must SAY so, never pass quietly
        print(
            f"::error title=earnings-wire-freshness::earnings_wire_freshness: "
            f"audit could not be computed: {exc}",
            flush=True,
        )
        return 1 if args.strict else 0

    detail = (
        f"published={report['newest_published_call_date']} "
        f"upstream={report['newest_upstream_call_date']} "
        f"lag={report['lag_days']}d "
        f"backlog={report['upstream_bodies_newer_than_published']} bodies"
    )

    if report["level"] == "error":
        print(
            f"::error title=earnings-wire-stale::earnings_wire_freshness: the earnings "
            f"archive has stopped advancing ({detail}). The ingest lane "
            f"(earnings-evidence-graph) is the first place to look — downstream lanes "
            f"stay green while it is dead.",
            flush=True,
        )
    elif report["level"] == "warning":
        print(
            f"::warning title=earnings-wire-freshness::earnings_wire_freshness: "
            f"earnings archive is behind upstream ({detail}).",
            flush=True,
        )
    else:
        print(f"earnings_wire_freshness: ok ({detail})", flush=True)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return 1 if (args.strict and report["level"] == "error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
