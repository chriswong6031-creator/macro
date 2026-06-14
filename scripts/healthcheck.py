"""Dead-man's switch (Phase B ops hardening).

CI failures are SILENT: if the daily pipeline stops running or a swath of sources
break, the static dashboard just keeps serving stale numbers and nobody is told.
This reads data/run_status.json and fails (non-zero exit) when the pipeline looks
dead — a heartbeat workflow runs it on a schedule, so a failure trips GitHub's own
failed-run notification (and, if secrets are set, a Telegram/Discord ping).

Two failure conditions:
  • STALE — last_run older than max_age_hours (default 96h: the pipeline runs
    weekdays, so a Friday→Monday gap plus a holiday is normal; only a genuinely
    missed multi-day window should fire).
  • BROAD OUTAGE — at least `broad_outage` sources are circuit-broken (>= breaker_trip
    consecutive failures). One flaky source is graceful degradation, not death; a
    broad cluster means collection itself is down.
Individual circuit-broken sources are reported as warnings but don't fail the check.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402


def check_health(status: dict, now: datetime, max_age_hours: float = 96.0,
                 breaker_trip: int = 3, broad_outage: int = 8) -> dict:
    """Pure health evaluation → {ok, fail_reasons, warnings, age_hours, tripped}."""
    fail, warn = [], []

    lr = status.get("last_run")
    age_h = None
    if not lr:
        fail.append("no last_run timestamp in run_status.json")
    else:
        try:
            age_h = (now - datetime.fromisoformat(lr)).total_seconds() / 3600.0
            if age_h > max_age_hours:
                fail.append(f"STALE: last successful run {age_h:.0f}h ago (limit {max_age_hours:.0f}h)")
        except (ValueError, TypeError):
            fail.append(f"unparseable last_run: {lr!r}")

    cb = status.get("circuit_breaker", {}) or {}
    tripped = sorted(s for s, n in cb.items() if isinstance(n, (int, float)) and n >= breaker_trip)
    if tripped:
        warn.append(f"{len(tripped)} source(s) circuit-broken (>= {breaker_trip} fails): {tripped}")
    if len(tripped) >= broad_outage:
        fail.append(f"BROAD OUTAGE: {len(tripped)} sources down (limit {broad_outage}) — collection likely broken")

    return {"ok": not fail, "fail_reasons": fail, "warnings": warn,
            "age_hours": None if age_h is None else round(age_h, 1), "tripped": tripped}


def _notify(report: dict) -> None:
    """Best-effort outbound alert reusing the existing notifier (Telegram/Discord);
    silent if the secrets aren't set. The non-zero exit is the primary signal."""
    msg = "🚨 macro-dashboard heartbeat FAILED — " + "; ".join(report["fail_reasons"])
    try:
        from scripts.notify import send_discord, send_telegram
        send_telegram(msg)
        send_discord(msg)
    except Exception:  # noqa: BLE001 — alerting is best-effort
        pass


def main() -> int:
    cfg = (config.load().get("healthcheck", {}) or {})
    p = config.data_dir() / "run_status.json"
    if not p.exists():
        print("::error::no run_status.json — pipeline has never completed")
        return 1
    status = json.loads(p.read_text())
    report = check_health(status, datetime.now(timezone.utc),
                          max_age_hours=float(cfg.get("max_age_hours", 96)),
                          breaker_trip=int(cfg.get("breaker_trip", 3)),
                          broad_outage=int(cfg.get("broad_outage", 8)))
    print(f"last_run age: {report['age_hours']}h | circuit-broken: {report['tripped'] or 'none'}")
    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"]:
        print("heartbeat OK")
        return 0
    for r in report["fail_reasons"]:
        print(f"::error::{r}")
    _notify(report)
    return 1


if __name__ == "__main__":
    sys.exit(main())
