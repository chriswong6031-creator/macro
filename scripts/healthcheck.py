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

A third tripwire, check_committed_data_freshness, detects silent data freezes where
the pipeline keeps running but collected bars stop landing in git (e.g. a failed push
loop after collection).  It reads a small set of witness parquet files from the
committed tree and fails when any witness is more than fail_after_sessions business
days stale.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

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


def check_signal_sanity(now: datetime, cfg: dict | None = None) -> dict:
    """CORRECTNESS companion to check_health (liveness). Validates the committed per-ticker
    boards both books select from — coverage / score-degeneracy / staleness — so the heartbeat
    also fails on a SILENT signal break, not only a dead pipeline. Returns the same
    {ok, fail_reasons, warnings} shape. Degrade-never-raise: any error here degrades to a single
    warning so a bug in the correctness add-on can never take the liveness probe down with it.
    (Freeze/drift need the rolling baseline and are owned by scripts/signal_sanity.py in the daily
    build; here we pass no prior, so those naturally no-op.)"""
    try:
        from engine import signal_sanity as ss  # stdlib-only; engine/__init__.py is empty
        if cfg is None:
            cfg = (config.load().get("signal_sanity", {}) or {})
        site = config.ROOT / config.load()["storage"]["site_dir"]
        report = ss.evaluate_all(ss.load_payloads(site), None, now=now, cfg=cfg)
        return {k: report[k] for k in ("ok", "fail_reasons", "warnings")}
    except Exception as e:  # noqa: BLE001 — never let the correctness add-on break liveness
        return {"ok": True, "fail_reasons": [], "warnings": [f"signal_sanity check skipped: {e!r}"]}


def check_r2_freshness(now: datetime) -> dict:
    """LIVENESS of the PUBLIC R2 data plane (the heavy per-ticker stores the browser
    fetches via templates/data_base.js). Every CI publish_r2 invocation is non-fatal and
    the script no-ops without creds, so a dead plane is invisible everywhere but here.
    Same degrade-never-raise shell as check_signal_sanity — a BUG in the probe can't take
    the liveness check down — but a definitive STALE/DARK/FORBIDDEN verdict DOES fail the
    heartbeat (that is the point). Network-indeterminate errors degrade to warnings
    inside the probe itself."""
    try:
        from scripts import audit_r2  # stdlib-only, like this module
        report = audit_r2.run(now=now)  # also persists data/quality/r2_audit.json
        return {k: report[k] for k in ("ok", "fail_reasons", "warnings")}
    except Exception as e:  # noqa: BLE001 — never let the add-on break liveness
        return {"ok": True, "fail_reasons": [], "warnings": [f"r2 freshness check skipped: {e!r}"]}


def _sessions_stale(through_date: object, now: datetime, holidays: list[str]) -> int:
    """Business days between *through_date* (inclusive end) and *now* (exclusive end).

    ``through_date`` may be a ``pandas.Timestamp``, ``datetime.date``, or any object
    that coerces to an ISO-formatted date string.  Returns 0 when through_date >= now
    (file is current or in the future).  ``holidays`` is a list of ISO date strings
    (``"YYYY-MM-DD"``) that are excluded from the business-day count.

    Pure function — no I/O, safe to unit-test."""
    hols = np.array([np.datetime64(h, "D") for h in holidays], dtype="datetime64[D]")
    try:
        from_d = np.datetime64(str(through_date)[:10], "D")
    except (TypeError, ValueError):
        return 0  # undatable — caller decides how to handle
    to_d = np.datetime64(now.date().isoformat(), "D")
    if from_d >= to_d:
        return 0
    return int(np.busday_count(from_d, to_d, holidays=hols))


def check_committed_data_freshness(now: datetime, cfg: dict | None = None) -> dict:
    """SILENT-FREEZE tripwire: verifies committed market-data stores are still advancing.

    The daily pipeline can keep running (last_run fresh, circuit-breakers clear) while
    a failed git-push loop silently freezes bars in the committed tree — dashboards
    show a fresh render timestamp but stale prices.  This probe reads a small set of
    witness parquet files directly from the committed tree, extracts their honest
    data-through date via ``engine.tushare_freshness.frame_asof``, and fails when any
    witness exceeds ``fail_after_sessions`` business days stale (warns at
    ``warn_after_sessions``).

    Degrade-never-raise: any unhandled exception degrades to a single warning so a bug
    here can never take the liveness probe down.  A MISSING witness file emits a warning
    (stores get renamed) but never hard-fails."""
    try:
        try:
            from engine.tushare_freshness import frame_asof  # noqa: PLC0415
        except Exception as imp_err:  # noqa: BLE001
            return {"ok": True, "fail_reasons": [],
                    "warnings": [f"data freshness check skipped: {imp_err!r}"]}

        import pandas as pd  # noqa: PLC0415 — guarded import; pandas is a hard dep

        if cfg is None:
            cfg = (config.load().get("healthcheck", {}) or {}).get("data_freshness", {}) or {}

        warn_after = int(cfg.get("warn_after_sessions", 1))
        fail_after = int(cfg.get("fail_after_sessions", 2))
        witnesses = list(cfg.get("witnesses", []) or [])
        raw_holidays = list(cfg.get("holidays", []) or [])

        fail, warn = [], []

        for w in witnesses:
            label = w.get("label", w.get("path", "unknown"))
            rel_path = w.get("path", "")
            p = config.ROOT / rel_path
            if not p.exists():
                warn.append(f"data-freeze witness missing (skipped): {label} — {rel_path}")
                continue
            try:
                df = pd.read_parquet(p)
                through = frame_asof(df)
            except Exception as read_err:  # noqa: BLE001
                warn.append(f"data-freeze witness unreadable (skipped): {label} — {read_err!r}")
                continue

            if through is None:
                warn.append(f"data-freeze witness undatable (skipped): {label}")
                continue

            stale = _sessions_stale(through, now, raw_holidays)
            if stale > fail_after:
                fail.append(
                    f"data-freeze: {label} {stale} trading-day{'s' if stale != 1 else ''} stale"
                    f" (through {str(through)[:10]}, limit {fail_after})"
                    f" — collected data not landing in git"
                )
            elif stale > warn_after:
                warn.append(
                    f"data-freeze warn: {label} {stale} trading-day{'s' if stale != 1 else ''} stale"
                    f" (through {str(through)[:10]}, warn_limit {warn_after})"
                )

        return {"ok": not fail, "fail_reasons": fail, "warnings": warn}

    except Exception as e:  # noqa: BLE001 — never let the add-on break liveness
        return {"ok": True, "fail_reasons": [], "warnings": [f"data freshness check skipped: {e!r}"]}


def _notify(report: dict) -> None:
    """Best-effort outbound alert via the W6b push spine.
    The non-zero exit is the primary signal; push_ops_alert() dispatches raw
    even when alert_push.enabled=false (dedup/ledger skipped, transport fires).
    W6b: replaces the former direct send_telegram/send_discord call."""
    msg = "🚨 macro-dashboard heartbeat FAILED — " + "; ".join(report["fail_reasons"])
    try:
        from engine.alert_triage import push_ops_alert  # noqa: PLC0415
        push_ops_alert(
            source="healthcheck",
            type_="heartbeat_failed",
            message=msg,
            severity="critical",
            lane="healthcheck",
        )
    except Exception:  # noqa: BLE001 — alerting is best-effort
        pass


def main() -> int:
    cfg = (config.load().get("healthcheck", {}) or {})
    now = datetime.now(timezone.utc)
    p = config.data_dir() / "run_status.json"
    if not p.exists():
        print("::error::no run_status.json — pipeline has never completed")
        return 1
    status = json.loads(p.read_text())
    report = check_health(status, now,
                          max_age_hours=float(cfg.get("max_age_hours", 96)),
                          breaker_trip=int(cfg.get("breaker_trip", 3)),
                          broad_outage=int(cfg.get("broad_outage", 8)))
    # Fold in the CORRECTNESS tripwire (silent-breakage), not just liveness. Merges into the
    # same warnings/fail_reasons → ::error::/::warning:: + _notify + non-zero-exit machinery.
    sanity = check_signal_sanity(now)
    report["fail_reasons"] = report["fail_reasons"] + sanity["fail_reasons"]
    report["warnings"] = report["warnings"] + sanity["warnings"]
    report["ok"] = report["ok"] and sanity["ok"]
    # And the R2 public-data-plane tripwire: the site serves per-ticker stores from R2,
    # published by non-fatal CI steps — stale/dark R2 must fail the heartbeat too.
    r2 = check_r2_freshness(now)
    report["fail_reasons"] = report["fail_reasons"] + r2["fail_reasons"]
    report["warnings"] = report["warnings"] + r2["warnings"]
    report["ok"] = report["ok"] and r2["ok"]
    # Silent-data-freeze tripwire: committed market-data bars must still be advancing.
    # A failed push loop leaves last_run fresh + circuit-breakers clear while bars freeze.
    freshness_cfg = cfg.get("data_freshness", None)
    freshness = check_committed_data_freshness(now, freshness_cfg)
    report["fail_reasons"] = report["fail_reasons"] + freshness["fail_reasons"]
    report["warnings"] = report["warnings"] + freshness["warnings"]
    report["ok"] = report["ok"] and freshness["ok"]
    print(f"last_run age: {report['age_hours']}h | circuit-broken: {report['tripped'] or 'none'} "
          f"| signals: {'ok' if sanity['ok'] else 'FAIL'} | r2: {'ok' if r2['ok'] else 'FAIL'} "
          f"| data-freeze: {'ok' if freshness['ok'] else 'FAIL'}")
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
