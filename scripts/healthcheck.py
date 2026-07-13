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

A fourth tripwire, check_weekly_lane, is the dead-lane guard for weekly.yml (the
#2193 class: a job killed at timeout-minutes concludes "cancelled" — not "failed" —
so GitHub sends no notification; weekly was timeout-killed every Saturday
2026-06-13..07-11 unnoticed).  weekly.yml stamps data/weekly_status.json only after
its build chain completes and commits it with the outputs, so a timeout kill, a dead
runner, or a lost push race all leave the committed stamp stale and fail this check.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
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


_LIVE_ROUTE_BASE = "https://mastermind-x.com/neuralwebdata"
_LIVE_ROUTE_FILES = [
    "mastermind_context.json",
    "bottom_sensors.json",
    "confluence_graph.json",
    "kernel_families.json",
]


def check_live_routes(timeout: float = 8.0) -> dict:
    """Probe the four public neuralwebdata JSON routes via HEAD requests.

    Fail-open: any network-level error (no connectivity, timeout, DNS) degrades to a
    warning, never a hard failure — so CI without outbound network access is unaffected.
    A definitive HTTP non-200 from a reachable host is reported as a warning line.
    Returns the same {ok, fail_reasons, warnings} shape as the other probes.
    """
    warnings: list[str] = []
    for fname in _LIVE_ROUTE_FILES:
        url = f"{_LIVE_ROUTE_BASE}/{fname}"
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
            if status != 200:
                warnings.append(f"live-route {fname}: HTTP {status} (expected 200)")
        except urllib.error.HTTPError as exc:
            warnings.append(f"live-route {fname}: HTTP {exc.code} {exc.reason}")
        except Exception as exc:  # noqa: BLE001 — network absent / timeout / DNS — degrade
            warnings.append(f"live-route {fname}: network error (non-fatal) — {type(exc).__name__}: {exc}")
    return {"ok": True, "fail_reasons": [], "warnings": warnings}
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


def check_weekly_lane(now: datetime, cfg: dict | None = None,
                      status_path: Path | None = None) -> dict:
    """DEAD-LANE tripwire for weekly.yml (calibrations + deep-dive builds).

    A job killed at timeout-minutes concludes "cancelled", not "failed", so no
    GitHub notification fires — weekly.yml died at its cap every Saturday
    2026-06-13..07-11 (5+ weeks, no calibrate_* ran) before anyone noticed, the
    same silent-death class asia-close hit for 8 days (#2193).

    weekly.yml writes data/weekly_status.json ONLY after its full build chain
    completes (the stamp step has no `if: always()`), and the stamp lands on main
    via the same commit step as the outputs.  So a timeout kill (stamp step never
    reached), a dead runner (job never starts), and a 5x-lost push race (outputs
    discarded) all leave the committed stamp stale — and this probe fails the
    heartbeat, which pings Telegram/Discord.

    Default max_age_hours=180 (7.5 days): the lane runs Saturdays 14:00 UTC and
    the heartbeat weekdays 14:30 UTC, so a healthy stamp reads at most ~6.0 days
    (Friday check) while a missed Saturday reads ~9 days by the Monday check.
    A missing or unparseable stamp is a definitive failure, not a degrade — it
    means the lane has never completed since the stamp shipped, or the file was
    deleted."""
    if cfg is None:
        cfg = (config.load().get("healthcheck", {}) or {}).get("weekly_lane", {}) or {}
    max_age_h = float(cfg.get("max_age_hours", 180.0))
    p = status_path if status_path is not None else (config.data_dir() / "weekly_status.json")
    if not p.exists():
        return {"ok": False, "warnings": [], "fail_reasons": [
            "WEEKLY LANE: no data/weekly_status.json — weekly.yml has never completed"
            " its chain since the stamp shipped (or the stamp was deleted)"]}
    try:
        lr = json.loads(p.read_text()).get("last_run")
        dt = datetime.fromisoformat(lr)
        if dt.tzinfo is None:                      # naive stamps are UTC by contract (#2463 class)
            dt = dt.replace(tzinfo=timezone.utc)
        age_h = (now - dt).total_seconds() / 3600.0
    except (ValueError, TypeError) as e:           # json.JSONDecodeError is a ValueError
        return {"ok": False, "warnings": [], "fail_reasons": [
            f"WEEKLY LANE: unreadable stamp data/weekly_status.json — {e!r}"]}
    fail = []
    if age_h > max_age_h:
        fail.append(
            f"WEEKLY LANE DEAD: last completed weekly.yml chain {age_h / 24:.1f}d ago"
            f" (limit {max_age_h / 24:.1f}d). Timeout-killed runs conclude 'cancelled' and"
            f" send NO notification (#2193 class) — check"
            f" `gh run list --workflow=weekly.yml` for cancelled conclusions")
    return {"ok": not fail, "fail_reasons": fail, "warnings": []}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Macro Dashboard heartbeat check")
    parser.add_argument(
        "--live-routes", action="store_true",
        help="Probe the four public mastermind-x.com/neuralwebdata routes (HEAD). "
             "Fail-open: network errors degrade to warnings only.",
    )
    args = parser.parse_args(argv)

    # --live-routes standalone: run only the live-route probe and exit.
    if args.live_routes:
        now = datetime.now(timezone.utc)
        lr = check_live_routes()
        for w in lr["warnings"]:
            print(f"::warning::{w}")
        if not lr["warnings"]:
            print("live-routes OK — all 4 neuralwebdata routes responded 200")
        return 0  # always exit 0 — live-route probe is advisory / W3 PR-F only

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
    # Dead-lane tripwire: weekly.yml stamps only on a completed chain; a timeout kill
    # concludes "cancelled" with no GitHub notification (#2193 class), so staleness of
    # the committed stamp is the only reliable death signal.
    weekly = check_weekly_lane(now, cfg.get("weekly_lane", None))
    report["fail_reasons"] = report["fail_reasons"] + weekly["fail_reasons"]
    report["warnings"] = report["warnings"] + weekly["warnings"]
    report["ok"] = report["ok"] and weekly["ok"]
    print(f"last_run age: {report['age_hours']}h | circuit-broken: {report['tripped'] or 'none'} "
          f"| signals: {'ok' if sanity['ok'] else 'FAIL'} | r2: {'ok' if r2['ok'] else 'FAIL'} "
          f"| data-freeze: {'ok' if freshness['ok'] else 'FAIL'} "
          f"| weekly-lane: {'ok' if weekly['ok'] else 'FAIL'}")
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
