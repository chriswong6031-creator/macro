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


def _source_age_min(breadth: dict[str, Any], now: datetime) -> float | None:
    """Minutes between the live-breadth SOURCE snapshot and `now`.

    Derived from the absolute ``source_asof`` stamp, NOT from the payload's own
    ``source_age_min`` (which is frozen at build time and therefore stops ageing
    the moment the producer dies). Falls back to ``source_age_min`` plus the
    artifact's own ``age_min`` when the absolute stamp is unparseable, which is
    the same quantity computed the long way round. Returns None when neither
    path yields a number — the caller fails closed on that.
    """
    raw = breadth.get("source_asof")
    if isinstance(raw, str) and raw.strip():
        try:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            stamp = None
        if stamp is not None:
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return (now - stamp.astimezone(timezone.utc)).total_seconds() / 60.0
    try:
        return float(breadth["source_age_min"]) + float(breadth.get("age_min") or 0.0)
    except (KeyError, TypeError, ValueError):
        return None


def _abs_age_min(raw: Any, now: datetime) -> float | None:
    """Minutes between an ABSOLUTE ISO stamp and `now`; None when unusable.

    Absolute stamps are the only clocks that keep ageing after a producer dies.
    A build-time scalar (`age_min`, `*_age_min` baked into the payload) freezes
    the moment the writer stops and therefore reads healthy forever -- the exact
    mechanism that let the US Prophet Live lane sit dead for 27 days in 2026-08.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (now - stamp.astimezone(timezone.utc)).total_seconds() / 60.0


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
    release_check = checks.get("release_publications") or {}
    if release_check.get("schema") == "release_publications.v2":
        if release_check.get("schedule_status") not in (None, "ok"):
            missing = release_check.get("missing_schedule_types") or []
            failures.append(
                "release_publications: official schedule coverage is incomplete"
                + (f" ({', '.join(str(value) for value in missing)})" if missing else "")
            )
        statuses = release_check.get("event_status")
        if not isinstance(statuses, dict):
            failures.append("release_publications: semantic event status is missing")
        else:
            delayed = int(statuses.get("verification_delayed") or 0)
            awaiting = int(statuses.get("awaiting_publication") or 0)
            status_unparsed = int(statuses.get("published_unparsed") or 0)
            try:
                unparsed = max(
                    status_unparsed,
                    int(release_check.get("unparsed_publications") or 0),
                )
            except (TypeError, ValueError):
                unparsed = status_unparsed
                failures.append("release_publications: invalid unparsed count")
            try:
                lag = float(release_check.get("max_publication_lag_min") or 0)
            except (TypeError, ValueError):
                lag = 0
                failures.append("release_publications: invalid publication lag")
            if delayed:
                failures.append(
                    "release_publications: "
                    f"{delayed} event(s) remain unverified beyond the watch window"
                )
            elif unparsed and (lag > 2 or status_unparsed == 0):
                failures.append(
                    "release_publications: official publication detected but "
                    f"{unparsed} event result(s) remain unparsed"
                    + (f" {lag:.1f}m after schedule" if lag > 0 else "")
                )
            elif awaiting and lag > 2:
                failures.append(
                    "release_publications: official result still unavailable "
                    f"{lag:.1f}m after schedule"
                )
    try:
        resolved = int(checks["quotes"]["resolved"])
    except (KeyError, TypeError, ValueError):
        failures.append("quotes: missing or invalid resolved count")
    else:
        if resolved < 5:
            failures.append(f"quotes: only {resolved} symbols resolved (minimum 5)")

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
    # CN Breathing Platform (CN-PR-1, spec §5). ABSENT-OK until the first ship:
    # the status endpoint does not grow a key until the evaluator is live, and
    # requiring it here would red the whole dead-man on every existing box.
    # Phase-aware ages: ≤6 min in morning/afternoon, ≤20 min through lunch,
    # close_board present by 07:20 UTC on sessions. Windows are UTC hour bands
    # (CST = UTC+8, no DST) so this file stays standard-library-only.
    cn_live = checks.get("cn_prophet_live")
    if weekday and isinstance(cn_live, dict):
        if (1 <= hour < 3) or (5 <= hour < 7):
            _require_age(failures, checks, "cn_prophet_live", 6)
        elif 3 <= hour < 5:
            _require_age(failures, checks, "cn_prophet_live", 20)
        if hour > 7 or (hour == 7 and current.minute >= 20):
            if not cn_live.get("close_board"):
                failures.append(
                    "cn_prophet_live: close_board missing after 07:20 UTC"
                )
    # First bar is scheduled at 13:37 UTC. Allow it to complete before making
    # the hourly accrual/flow lane part of the external contract.
    if weekday and 14 <= hour <= 22:
        require_lane("bars", 90)
        _require_age(failures, checks, "flow_pulse", 90)
        pulse = checks.get("flow_pulse")
        if isinstance(pulse, dict):
            n_tickers = int(pulse.get("n_tickers") or 0)
            with_bars = int(pulse.get("with_bars") or 0)
            if pulse.get("mode") != "fastpath" or n_tickers <= 0:
                failures.append(
                    f"flow_pulse: semantically unavailable (mode={pulse.get('mode') or 'missing'})"
                )
            elif with_bars / n_tickers < 0.80:
                failures.append(
                    f"flow_pulse: only {with_bars}/{n_tickers} tickers have current-session bars"
                )
    # Live-breadth truth boundary (FROZEN CONTRACT §6). ABSENT-OK — same
    # precedent as cn_prophet_live above: a box that has not deployed the
    # `macro-live-breadth` lane yet must not red the whole dead-man.
    breadth = checks.get("breadth")
    if isinstance(breadth, dict):
        if breadth.get("session") == "closed" or not weekday:
            # Stale last-session data outside a session is legitimate evidence
            # of nothing being wrong — never a fault (explicit spec requirement).
            pass
        elif 14 <= hour <= 20:
            # Expected live window: ~10:00-16:00 ET, safely inside RTH for both
            # DST offsets. `usable` is the semantic truth — never inferred from
            # artifact age alone (a fresh deploy can copy OLD content).
            if breadth.get("usable") is not True:
                reason = breadth.get("unusable_reason")
                failures.append(
                    "breadth: not usable during the live window"
                    + (f" ({reason})" if reason else "")
                )
            # Source age is measured against NOW from the ABSOLUTE source_asof,
            # never from the payload's own source_age_min. That field is frozen at
            # BUILD time, so a producer that died three hours ago keeps serving an
            # artifact reading `source_age_min: 16` forever — a dead lane would
            # look perfectly healthy and the dead-man would never fire. The
            # absolute stamp is the only value that keeps ageing after the writer
            # stops, so it answers both "is the source stale?" and "did the
            # producer actually run?" with one check and no reliance on mtime.
            source_age = _source_age_min(breadth, current)
            if source_age is None:
                failures.append("breadth: missing or invalid source_asof")
            elif source_age > 25:
                failures.append(
                    f"breadth: source stale at {source_age:.1f}m (limit 25.0m) — "
                    "stale feed or a producer that stopped writing"
                )
            try:
                coverage_pct = float(breadth["coverage_pct"])
            except (KeyError, TypeError, ValueError):
                failures.append("breadth: missing or invalid coverage_pct")
            else:
                if coverage_pct < 90:
                    failures.append(
                        f"breadth: coverage low at {coverage_pct:.1f}% (minimum 90.0%)"
                    )
            producer = breadth.get("producer")
            if not isinstance(producer, str) or not producer.strip():
                failures.append("breadth: missing producer (unowned)")
        # else: weekday, session open, but outside the expected live window —
        # require only that the key parses (already true); report nothing.
    # ---- US Prophet Live: THE US product lane -------------------------------
    # Deliberately NOT the ABSENT-OK precedent used by cn_prophet_live and
    # breadth above. Those lanes may legitimately not be deployed on a given box.
    # This one is the US product lane, and "the key simply isn't there" is
    # exactly how the 2026-07-30 -> 2026-08-26 freeze stayed invisible: the
    # evaluator ran every 5 minutes, published nothing (credentials were never
    # seeded at cutover), exited 0, and this dead-man printed "VPS live plane
    # healthy" for 27 days across ~18 lost sessions.
    #
    # `expected_now` is computed SERVER-SIDE from the repo's own NYSE calendar and
    # window law (engine.prophet_live.live_states), so this stdlib-only monitor
    # never mints a second holiday calendar. The coarse UTC guard below decides
    # only WHETHER to demand the key when the key is missing entirely -- it never
    # decides a freshness verdict.
    prophet = checks.get("prophet_live")
    coarse_us_window = weekday and 14 <= hour <= 20
    if not isinstance(prophet, dict):
        if coarse_us_window:
            failures.append(
                "prophet_live: check absent from /api/status during the US session "
                "— the product lane is ungraded (deploy the status projection)"
            )
    else:
        expected = prophet.get("expected_now")
        if expected is None and coarse_us_window:
            failures.append(
                "prophet_live: expected_now unavailable — the status surface could "
                "not evaluate the session law (failing closed)"
            )
        elif expected:
            status = prophet.get("status")
            reason = prophet.get("reason")
            if status == "absent":
                failures.append(
                    "prophet_live: no served artifact during an expected session"
                    + (f" ({reason})" if reason else "")
                )
            elif status == "unparseable":
                failures.append("prophet_live: served artifact is unparseable")
            else:
                # Absolute pass clock. The producer fires every 5 minutes, so 15
                # minutes is three missed passes -- inside the two-cadence
                # (20 min) detection budget with headroom for scheduler jitter.
                pass_age = _abs_age_min(prophet.get("pass_ts"), current)
                if pass_age is None:
                    failures.append("prophet_live: missing or invalid pass_ts")
                elif pass_age > 15:
                    failures.append(
                        f"prophet_live: last pass {pass_age:.1f}m ago (limit 15.0m) "
                        "— the producer stopped writing or cannot publish"
                    )
                # Quote clock, graded against the lane's own 25m freshness gate.
                quote_age = _abs_age_min(prophet.get("quote_asof"), current)
                if quote_age is None:
                    failures.append("prophet_live: missing or invalid quote_asof")
                elif quote_age > 25:
                    failures.append(
                        f"prophet_live: quote source stale at {quote_age:.1f}m "
                        "(limit 25.0m)"
                    )
                # Pack basis. A same-day or weekend `as_of` darkens the whole
                # session; that defect alone darkened 11 of the 18 sessions lost
                # in the 2026-08 incident, so it is graded by name.
                if prophet.get("pack_ok") is False:
                    failures.append(
                        "prophet_live: armed pack is not the last completed session "
                        f"(as_of={prophet.get('pack_as_of')!r}, "
                        f"expected={prophet.get('pack_expected')!r})"
                    )
                elif prophet.get("pack_ok") is None:
                    failures.append("prophet_live: pack basis could not be established")
                # A globally dark artifact during an expected session is an
                # outage, not a market condition. Per-name darkness is normal and
                # lives in state_counts, never in the top-level status.
                if status == "dark":
                    failures.append(
                        "prophet_live: artifact globally dark during an expected session"
                        + (f" ({reason})" if reason else "")
                    )
                producer = prophet.get("producer")
                if not isinstance(producer, str) or not producer.strip():
                    failures.append("prophet_live: missing producer (unowned lane)")
        # else: not an expected session — no freshness is required, and a stale
        # last-session artifact is legitimate evidence of nothing being wrong.
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
