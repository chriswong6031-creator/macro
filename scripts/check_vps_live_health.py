"""External dead-man check for the VPS-owned live dashboard lanes.

Uses only the public, read-only ``/api/status`` endpoint. It is intentionally
standard-library-only so GitHub-hosted monitoring and an operator shell can run
it without installing the dashboard's full dependency set.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://mastermind-x.com/api/status"


def _age(checks: dict[str, Any], key: str) -> float | None:
    try:
        return float(checks[key]["age_min"])
    except (KeyError, TypeError, ValueError):
        return None


def _require_age(
    failures: list[str],
    checks: dict[str, Any],
    key: str,
    maximum: float,
) -> None:
    age = _age(checks, key)
    if age is None:
        failures.append(f"{key}: missing or invalid age")
    elif age > maximum:
        failures.append(f"{key}: stale at {age:.1f}m (limit {maximum:.1f}m)")


def evaluate(payload: dict[str, Any], *, now: datetime | None = None) -> list[str]:
    """Return human-readable health failures; an empty list is healthy."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    checks = payload.get("checks")
    if payload.get("status") != "ok" or not isinstance(checks, dict):
        return ["status endpoint did not return the expected healthy envelope"]

    failures: list[str] = []
    _require_age(failures, checks, "quotes", 5)
    _require_age(failures, checks, "release_publications", 5)
    _require_age(failures, checks, "orchestrator", 5)

    lanes = (checks.get("orchestrator") or {}).get("lanes")
    if not isinstance(lanes, dict):
        failures.append("orchestrator: per-lane health is missing")
        lanes = {}

    def require_lane(name: str, maximum: float) -> None:
        lane = lanes.get(name)
        if not isinstance(lane, dict):
            failures.append(f"lane {name}: missing")
            return
        if lane.get("ok") is not True:
            failures.append(f"lane {name}: last run was not healthy")
        try:
            age = float(lane["age_min"])
        except (KeyError, TypeError, ValueError):
            failures.append(f"lane {name}: missing or invalid age")
            return
        if age > maximum:
            failures.append(f"lane {name}: stale at {age:.1f}m (limit {maximum:.1f}m)")

    require_lane("fast", 5)
    weekday = current.weekday() < 5
    hour = current.hour
    if weekday:
        require_lane("snapshot", 15)
        _require_age(failures, checks, "basket_pulse", 15)
    if weekday and 11 <= hour <= 22:
        _require_age(failures, checks, "overlay", 6)
        _require_age(failures, checks, "risk_state", 6)
    if weekday and 1 <= hour < 9:
        _require_age(failures, checks, "china_risk_state", 6)
    # First bar is scheduled at 13:37 UTC. Allow it to complete before making
    # the hourly accrual/flow lane part of the external contract.
    if weekday and 14 <= hour <= 22:
        require_lane("bars", 90)
        _require_age(failures, checks, "flow_pulse", 90)
    return failures


def fetch_status(url: str, *, timeout: float = 15) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mastermind-VPS-Live-Heartbeat/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--status-file", help="read a local fixture instead of HTTP")
    parser.add_argument("--now", help="ISO-8601 UTC override for validation")
    args = parser.parse_args()
    try:
        payload = (
            json.loads(Path(args.status_file).read_text(encoding="utf-8"))
            if args.status_file
            else fetch_status(args.url)
        )
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
        failures = evaluate(payload, now=now)
    except Exception as exc:  # noqa: BLE001 - network/parse failures must trip the dead-man
        print(f"VPS LIVE UNHEALTHY: status check failed: {type(exc).__name__}: {exc}")
        return 1
    if failures:
        print("VPS LIVE UNHEALTHY:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("VPS live plane healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
