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

import argparse
import json
import sys
import urllib.error
import urllib.request
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
    print(f"last_run age: {report['age_hours']}h | circuit-broken: {report['tripped'] or 'none'} "
          f"| signals: {'ok' if sanity['ok'] else 'FAIL'} | r2: {'ok' if r2['ok'] else 'FAIL'}")
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
