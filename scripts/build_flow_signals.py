"""scripts/build_flow_signals.py — nightly flow-signal ledger entrypoint.

Nightly pipeline:
  1. Harvest new events from R2 archive blobs + feed_current (collectors/flow_signals.py)
  2. Grade matured rows (engine/flow_signals_grade.py)
  3. Write data/flow_signals/gate.json (status artifact)
  4. Register in data/run_status.json (P0.7 pattern)
  5. Audit tripwire: warn if last harvest is >= 2 trading days stale

Runtime budget: trivial (<60s typical; harvest is bounded by archive blob count × small JSON).

FORWARD-LEDGER LAW: this script is the SOLE ADVANCER of the flow-signal ledger.
  Intraday lanes must not call collectors.flow_signals.harvest() with dry_run=False.

Usage:
  python -m scripts.build_flow_signals             # normal nightly run
  python -m scripts.build_flow_signals --dry-run   # no writes (smoke)
  python -m scripts.build_flow_signals --verbose   # debug logging
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


# ── gate.json writer ──────────────────────────────────────────────────────────

def _write_gate(
    gate_path: Path,
    ledger_stats: dict,
    grade_summary: dict,
    harvest_n_new: int,
    elapsed_sec: float,
    asof: str,
) -> None:
    """Write data/flow_signals/gate.json (status artifact; scored=false, building_history)."""
    # Events-per-day stats
    epd = ledger_stats.get("events_per_day", {})
    n_by_dte = ledger_stats.get("dte_bucket_counts", {})

    # Compute events/day mean (over last 30 days)
    epd_values = list(epd.values())
    epd_mean = round(sum(epd_values) / len(epd_values), 1) if epd_values else 0.0

    gate = {
        "schema":           "flow_signals.gate/v1",
        "asof":             asof,
        "scored":           False,
        "status":           "building_history",
        "ledger": {
            "n_rows":        ledger_stats.get("n_rows", 0),
            "n_sessions":    ledger_stats.get("n_sessions", 0),
            "last_ts":       ledger_stats.get("last_ts"),
            "events_per_day_mean": epd_mean,
            "events_per_day": epd,
            "n_by_dte_bucket": n_by_dte,
        },
        "harvest": {
            "n_new_this_run": harvest_n_new,
        },
        "grader": {
            "n_graded_ok":    grade_summary.get("n_graded_ok", 0),
            "n_split_seam":   grade_summary.get("n_split_seam", 0),
            "n_not_matured":  grade_summary.get("n_not_matured", 0),
            "n_errors":       grade_summary.get("n_errors", 0),
            "elapsed_sec":    grade_summary.get("elapsed_sec", 0.0),
        },
        "elapsed_sec":      round(elapsed_sec, 2),
        "note": (
            "Flow-event ledger accruing. Scored field remains false until "
            "FS-3 pre-registration + FS-4 model training + FS-5 gauntlet pass. "
            f"Ledger history older than {48}h is permanently lost from the R2 "
            "archive window (FS-R1); run nightly without gaps."
        ),
    }

    tmp = gate_path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(gate, indent=2))
    tmp.rename(gate_path)
    log.info("build_flow_signals: gate.json written → %s", gate_path)


# ── run_status registration (P0.7 pattern) ───────────────────────────────────

def _register_run_status(
    n_new: int, n_graded: int, elapsed_sec: float, asof: str,
) -> None:
    """Register this run in data/run_status.json per P0.7 pattern.

    Mirrors the pattern in scripts/build_tape_flow_daily.py:_register_run_status.
    """
    try:
        from lib import config
        rs_path = config.data_dir() / "run_status.json"
        try:
            rs: dict = json.loads(rs_path.read_text()) if rs_path.exists() else {}
        except Exception:  # noqa: BLE001
            rs = {}
        sources = rs.setdefault("sources", {})
        sources["flow_signals"] = {
            "status":       "ok" if (n_new >= 0) else "error",
            "n_new":        n_new,
            "n_graded_ok":  n_graded,
            "elapsed_sec":  round(elapsed_sec, 1),
            "last_date":    asof,
            "checked_at":   datetime.now(timezone.utc).isoformat(),
        }
        tmp = rs_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rs, indent=2))
        os.replace(tmp, rs_path)
        log.info("build_flow_signals: registered run_status[flow_signals]")
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: run_status registration failed: %s", e)


# ── audit tripwire ────────────────────────────────────────────────────────────

def _audit_staleness(last_ts: str | None, today: date) -> None:
    """Warn if the ledger's last event timestamp is >= 2 trading days stale.

    Per masterplan §7 (accrual fragility) and P0.7 doctrine.
    Emits a GHA warning annotation when stale.
    """
    if not last_ts:
        log.warning("build_flow_signals: ledger has no events yet (day 1 accrual)")
        return
    try:
        from lib.nyse_calendar import is_session
        ts = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        last_date = ts.date()

        # Count trading days since last event
        d = last_date
        trading_days_since = 0
        while d < today:
            d_next = d.__class__(d.year, d.month, d.day)
            from datetime import timedelta
            d_next = d_next + timedelta(days=1)
            if is_session(d_next):
                trading_days_since += 1
            d = d_next
            if trading_days_since > 10:
                break  # cap scan

        if trading_days_since >= 2:
            log.warning(
                "::warning title=flow_signals_stale::ledger last event %s is "
                "%d trading days old — check poller / R2 outage",
                last_date, trading_days_since,
            )
        else:
            log.info("build_flow_signals: staleness ok (%d trading days since last event)",
                     trading_days_since)
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: staleness audit failed: %s", e)


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flow-signal ledger nightly builder")
    parser.add_argument("--dry-run", action="store_true",
                        help="Harvest in dry-run mode; skip grader + gate write")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    t0 = time.perf_counter()
    asof = datetime.now(timezone.utc).date().isoformat()
    today = date.today()

    log.info("build_flow_signals: starting (dry_run=%s)", args.dry_run)

    # ── 1. Harvest ────────────────────────────────────────────────────────────
    try:
        from collectors.flow_signals import harvest, ledger_stats
        n_new = harvest(dry_run=args.dry_run)
        log.info("build_flow_signals: harvest complete — %d new events", n_new)
    except Exception as e:  # noqa: BLE001
        log.error("build_flow_signals: harvest failed: %s", e)
        n_new = 0

    # ── 2. Ledger stats ───────────────────────────────────────────────────────
    try:
        from collectors.flow_signals import ledger_stats as _stats
        stats = _stats()
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_signals: ledger_stats failed: %s", e)
        stats = {"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {}, "last_ts": None}

    # ── 3. Grade matured rows ─────────────────────────────────────────────────
    grade_summary: dict = {
        "n_graded_ok": 0, "n_split_seam": 0,
        "n_not_matured": 0, "n_errors": 0, "elapsed_sec": 0.0,
    }
    if not args.dry_run:
        try:
            from engine.flow_signals_grade import grade_matured
            grade_summary = grade_matured(today=today)
            log.info("build_flow_signals: grader complete — %s", grade_summary)
        except Exception as e:  # noqa: BLE001
            log.error("build_flow_signals: grader failed: %s", e)

    elapsed_sec = time.perf_counter() - t0

    # ── 4. Write gate.json ────────────────────────────────────────────────────
    if not args.dry_run:
        try:
            from lib import config
            gate_path = config.data_dir() / "flow_signals" / "gate.json"
            gate_path.parent.mkdir(parents=True, exist_ok=True)
            _write_gate(gate_path, stats, grade_summary, n_new, elapsed_sec, asof)
        except Exception as e:  # noqa: BLE001
            log.error("build_flow_signals: gate.json write failed: %s", e)

    # ── 5. run_status registration ────────────────────────────────────────────
    if not args.dry_run:
        _register_run_status(n_new, grade_summary.get("n_graded_ok", 0), elapsed_sec, asof)

    # ── 6. Audit staleness tripwire ───────────────────────────────────────────
    _audit_staleness(stats.get("last_ts"), today)

    # ── Timing ───────────────────────────────────────────────────────────────
    log.info(
        "[timing] build_flow_signals: total=%.2fs harvest=%d_events "
        "ledger_rows=%d graded_ok=%d",
        elapsed_sec, n_new, stats.get("n_rows", 0),
        grade_summary.get("n_graded_ok", 0),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
