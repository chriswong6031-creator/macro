"""Grade Research Vault source-content freshness independently of publication.

The Research Vault catalog has two different clocks:

* ``generated_at`` proves the catalog publication plane ran.
* the newest report's ``published_at`` proves the upstream MarketDesk producer
  is still admitting research.

A healthy hourly publisher can keep advancing ``generated_at`` while the source
producer is dead.  This stdlib-only guard makes that state fail visibly without
changing ``engine.research_vault.catalog`` or creating another health store.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "research_vault.source_freshness.v1"
DEFAULT_URL = "https://www.mastermind-x.com/api/research/catalog?limit=3&offset=0"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_FUTURE_TOLERANCE_MINUTES = 5.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# Deliberately coarse and standard-library-only.  Research is expected on
# business days, but Saturday/Sunday and the Friday->Monday boundary are not an
# outage.  The limit is tight again by Wednesday, so a dead producer cannot stay
# green merely because the catalog publisher keeps running.
_LIMIT_HOURS_BY_UTC_WEEKDAY = {
    0: 96.0,  # Monday: allow a normal Friday -> Monday gap
    1: 96.0,  # Tuesday: long-weekend grace, but fail by Tuesday afternoon
    2: 48.0,  # Wednesday
    3: 48.0,  # Thursday
    4: 48.0,  # Friday
    5: 72.0,  # Saturday
    6: 96.0,  # Sunday
}


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def source_limit_hours(now: datetime, override: float | None = None) -> float:
    if override is not None:
        if override <= 0:
            raise ValueError("--max-age-hours must be positive")
        return float(override)
    return _LIMIT_HOURS_BY_UTC_WEEKDAY[_coerce_now(now).weekday()]


def _report(
    status: str,
    *,
    ok: bool,
    now: datetime,
    source: str,
    reason: str,
    generated_at: datetime | None = None,
    latest_report_at: datetime | None = None,
    age_hours: float | None = None,
    limit_hours: float | None = None,
    count: int | None = None,
    observed_items: int | None = None,
    invalid_published_at: int = 0,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "ok": ok,
        "reason": reason,
        "source": source,
        "now": _iso(now),
        "generated_at": _iso(generated_at),
        "latest_report_at": _iso(latest_report_at),
        "age_hours": round(age_hours, 3) if age_hours is not None else None,
        "limit_hours": float(limit_hours) if limit_hours is not None else None,
        "count": count,
        "observed_items": observed_items,
        "invalid_published_at": invalid_published_at,
    }


def evaluate(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
    source: str = "catalog",
    max_age_hours: float | None = None,
    future_tolerance_minutes: float = DEFAULT_FUTURE_TOLERANCE_MINUTES,
) -> dict[str, Any]:
    """Return one typed source-content freshness verdict.

    This function intentionally does not restamp or persist anything.  It reads
    the complete local catalog or the public preview returned by the API.  The
    preview is sufficient for liveness because it is newest-first; ``count`` is
    retained as the whole-vault cardinality.
    """
    current = _coerce_now(now)
    if future_tolerance_minutes < 0:
        raise ValueError("future_tolerance_minutes must be non-negative")
    limit = source_limit_hours(current, max_age_hours)

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return _report(
            "CATALOG_UNAVAILABLE",
            ok=False,
            now=current,
            source=source,
            reason="catalog items is missing or not a list",
            limit_hours=limit,
        )

    raw_count = payload.get("count")
    try:
        count = int(raw_count) if raw_count is not None else len(raw_items)
    except (TypeError, ValueError):
        count = None

    generated_at = _parse_time(payload.get("generated_at"))
    catalog_health = payload.get("catalog_health")
    if generated_at is None and isinstance(catalog_health, Mapping):
        generated_at = _parse_time(catalog_health.get("generated_at"))

    # The serving tier may return a validated cached catalog with HTTP 200 after
    # its authoritative R2 read failed.  That is not a source-freshness pass.
    if payload.get("stale") is True:
        reason = "catalog API is serving a stale fallback"
        if isinstance(catalog_health, Mapping) and catalog_health.get("reason"):
            reason += f" ({catalog_health.get('reason')})"
        return _report(
            "CATALOG_UNAVAILABLE",
            ok=False,
            now=current,
            source=source,
            reason=reason,
            generated_at=generated_at,
            limit_hours=limit,
            count=count,
            observed_items=len(raw_items),
        )

    if not raw_items:
        return _report(
            "NO_REPORTS",
            ok=False,
            now=current,
            source=source,
            reason="catalog contains no report rows",
            generated_at=generated_at,
            limit_hours=limit,
            count=count,
            observed_items=0,
        )

    parsed_times: list[datetime] = []
    invalid = 0
    for item in raw_items:
        if not isinstance(item, Mapping):
            invalid += 1
            continue
        stamp = _parse_time(item.get("published_at"))
        if stamp is None:
            invalid += 1
        else:
            parsed_times.append(stamp)

    if not parsed_times:
        return _report(
            "LATEST_REPORT_INVALID",
            ok=False,
            now=current,
            source=source,
            reason="no observed report row carries a usable published_at clock",
            generated_at=generated_at,
            limit_hours=limit,
            count=count,
            observed_items=len(raw_items),
            invalid_published_at=invalid,
        )

    latest = max(parsed_times)
    tolerance = timedelta(minutes=future_tolerance_minutes)
    if latest - current > tolerance:
        return _report(
            "FUTURE_REPORT_CLOCK",
            ok=False,
            now=current,
            source=source,
            reason=(
                "newest report clock is beyond the accepted future tolerance "
                f"({future_tolerance_minutes:g}m)"
            ),
            generated_at=generated_at,
            latest_report_at=latest,
            age_hours=(current - latest).total_seconds() / 3600.0,
            limit_hours=limit,
            count=count,
            observed_items=len(raw_items),
            invalid_published_at=invalid,
        )

    age_hours = max(0.0, (current - latest).total_seconds() / 3600.0)
    if age_hours > limit:
        return _report(
            "PRODUCER_STALE",
            ok=False,
            now=current,
            source=source,
            reason=(
                f"newest admitted report is {age_hours:.1f}h old "
                f"(limit {limit:.1f}h)"
            ),
            generated_at=generated_at,
            latest_report_at=latest,
            age_hours=age_hours,
            limit_hours=limit,
            count=count,
            observed_items=len(raw_items),
            invalid_published_at=invalid,
        )

    return _report(
        "SOURCE_FRESH",
        ok=True,
        now=current,
        source=source,
        reason="newest admitted report is inside the source-content freshness window",
        generated_at=generated_at,
        latest_report_at=latest,
        age_hours=age_hours,
        limit_hours=limit,
        count=count,
        observed_items=len(raw_items),
        invalid_published_at=invalid,
    )


def _load_local(path: Path) -> Mapping[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(
            f"catalog exceeds bounded read limit ({len(raw)} > {MAX_RESPONSE_BYTES})"
        )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("catalog root must be an object")
    return payload


def _load_url(url: str, timeout_seconds: float) -> Mapping[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MastermindX-research-source-health/1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        announced = response.headers.get("Content-Length")
        if announced:
            try:
                announced_bytes = int(announced)
            except (TypeError, ValueError):
                announced_bytes = None
            if announced_bytes is not None and announced_bytes > MAX_RESPONSE_BYTES:
                raise ValueError(
                    "catalog response exceeds bounded read limit "
                    f"({announced_bytes} > {MAX_RESPONSE_BYTES})"
                )
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(
            f"catalog response exceeds bounded read limit ({len(raw)} > {MAX_RESPONSE_BYTES})"
        )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("catalog response root must be an object")
    return payload


def _emit(report: Mapping[str, Any]) -> None:
    print(json.dumps(dict(report), sort_keys=True))
    if report.get("ok") is not True:
        print(
            "::error title=research-vault-source::"
            f"{report.get('status')}: {report.get('reason')}"
        )


def _selftest() -> int:
    """Hermetic contract exercised by the owner workflow on every PR."""
    generated = "2026-09-05T03:53:00Z"

    def catalog(published: Any, *, count: Any = 1, stale: bool = False) -> dict[str, Any]:
        return {
            "schema": "research_vault.catalog.v1",
            "generated_at": generated,
            "count": count,
            "items": [{"id": "report-1", "published_at": published}],
            "stale": stale,
        }

    cases: list[tuple[str, Mapping[str, Any], datetime, str, dict[str, Any]]] = [
        (
            "fresh generated_at cannot hide Aug-25 source silence",
            catalog("2026-08-25T16:47:24Z", count=1843),
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "PRODUCER_STALE",
            {"ok": False, "count": 1843},
        ),
        (
            "recent admitted report passes",
            catalog("2026-09-04T18:00:00Z"),
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "SOURCE_FRESH",
            {"ok": True},
        ),
        (
            "normal Friday to Monday gap passes",
            catalog("2026-09-04T17:00:00Z"),
            datetime(2026, 9, 7, 12, tzinfo=timezone.utc),
            "SOURCE_FRESH",
            {"ok": True, "limit_hours": 96.0},
        ),
        (
            "source fails after weekday grace",
            catalog("2026-09-04T17:00:00Z"),
            datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
            "PRODUCER_STALE",
            {"ok": False, "limit_hours": 48.0},
        ),
        (
            "empty catalog is typed",
            {"generated_at": generated, "count": 0, "items": []},
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "NO_REPORTS",
            {"ok": False},
        ),
        (
            "invalid newest report clock is typed",
            catalog("not-a-time"),
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "LATEST_REPORT_INVALID",
            {"ok": False, "invalid_published_at": 1},
        ),
        (
            "future newest report clock is typed",
            catalog("2026-09-05T04:10:01Z"),
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "FUTURE_REPORT_CLOCK",
            {"ok": False},
        ),
        (
            "malformed catalog is unavailable",
            {"generated_at": generated, "items": "not-a-list"},
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "CATALOG_UNAVAILABLE",
            {"ok": False},
        ),
        (
            "stale API fallback never passes source freshness",
            catalog("2026-09-05T03:00:00Z", stale=True),
            datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            "CATALOG_UNAVAILABLE",
            {"ok": False},
        ),
    ]

    failures: list[str] = []
    for name, payload, now, expected_status, expected_fields in cases:
        report = evaluate(payload, now=now, source=f"selftest:{name}")
        if report.get("status") != expected_status:
            failures.append(
                f"{name}: status={report.get('status')!r}, expected={expected_status!r}"
            )
        for field, expected in expected_fields.items():
            if report.get(field) != expected:
                failures.append(
                    f"{name}: {field}={report.get(field)!r}, expected={expected!r}"
                )

    override = evaluate(
        catalog("2026-09-04T00:00:00Z"),
        now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
        max_age_hours=24,
        source="selftest:explicit override",
    )
    if override.get("status") != "PRODUCER_STALE" or override.get("limit_hours") != 24.0:
        failures.append(f"explicit max-age override not enforced: {override!r}")

    if failures:
        for failure in failures:
            print(f"SELFTEST FAILURE: {failure}", file=sys.stderr)
        return 1
    print(f"research-vault source-freshness selftest: {len(cases) + 1} passed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Grade Research Vault source-content freshness independently from "
            "catalog publication freshness."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--catalog", type=Path, help="local catalog JSON path")
    group.add_argument("--url", help="public catalog API URL")
    parser.add_argument(
        "--now",
        help="deterministic ISO-8601 time; defaults to current UTC",
    )
    parser.add_argument("--max-age-hours", type=float)
    parser.add_argument(
        "--future-tolerance-minutes",
        type=float,
        default=DEFAULT_FUTURE_TOLERANCE_MINUTES,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the hermetic behavioral contract and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()

    current = datetime.now(timezone.utc)
    if args.now is not None:
        parsed = _parse_time(args.now)
        if parsed is None:
            report = _report(
                "CATALOG_UNAVAILABLE",
                ok=False,
                now=current,
                source="arguments",
                reason=f"invalid --now value: {args.now!r}",
            )
            _emit(report)
            return 1
        current = parsed

    source = str(args.catalog) if args.catalog is not None else (args.url or DEFAULT_URL)
    try:
        payload = (
            _load_local(args.catalog)
            if args.catalog is not None
            else _load_url(source, args.timeout_seconds)
        )
        report = evaluate(
            payload,
            now=current,
            source=source,
            max_age_hours=args.max_age_hours,
            future_tolerance_minutes=args.future_tolerance_minutes,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        report = _report(
            "CATALOG_UNAVAILABLE",
            ok=False,
            now=current,
            source=source,
            reason=f"{type(exc).__name__}: {exc}",
        )
    _emit(report)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
