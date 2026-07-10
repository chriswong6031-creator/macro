"""scripts/run_signal_foundry_harness.py — Signal Foundry weekly batch harness runner.

Deterministic, no LLM calls. Reads data/signal_foundry/candidates.jsonl and:
  1. Promotes ALL pending 'proposed' specs to 'registered' status (stamps gates_hash
     and registered_at; fair DSR n: registration happens BEFORE any run this batch).
  2. Runs engine.signal_foundry.harness.run_spec for registered specs without results,
     capped at config budgets.runs_per_week per ISO week, wall-clock capped at
     config budgets.run_wallclock_min minutes.
  3. Updates candidates.jsonl statuses (registered → tested) and refreshes
     data/signal_foundry/lane_status.json.

ISO-week idempotency: counts runs from governance.jsonl for this week; stops when cap met.

Usage:
    python -m scripts.run_signal_foundry_harness [--root PATH] [--dry-run]

Outputs (non-fatal on any individual failure):
  data/signal_foundry/candidates.jsonl   — statuses updated (write in-place)
  data/signal_foundry/lane_status.json   — updated after batch
  data/signal_foundry/governance.jsonl   — run events appended
  data/signal_foundry/results/<id>.json  — harness outputs (written by engine)
  data/trial_ledger.jsonl                — trial ledger (written by engine)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Module-level import so tests can patch scripts.run_signal_foundry_harness.run_spec
from engine.signal_foundry.harness import run_spec  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_CONFIG_PATH = ROOT / "config" / "signal_foundry.yml"
_CANDIDATES_PATH = ROOT / "data" / "signal_foundry" / "candidates.jsonl"
_LANE_STATUS_PATH = ROOT / "data" / "signal_foundry" / "lane_status.json"
_GOVERNANCE_PATH = ROOT / "data" / "signal_foundry" / "governance.jsonl"
_RESULTS_DIR = ROOT / "data" / "signal_foundry" / "results"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config/signal_foundry.yml; fail-open with defaults."""
    try:
        import yaml
        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("run_signal_foundry_harness: could not load signal_foundry.yml (%s); using defaults", exc)
        return {}


# ---------------------------------------------------------------------------
# ISO week helper
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, tolerating absent file and torn lines."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """Overwrite a JSONL file with the given rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Lane status file
# ---------------------------------------------------------------------------

def _write_lane_status(
    status: str,
    reason: str,
    root: Path,
) -> None:
    """Write data/signal_foundry/lane_status.json."""
    lane_path = root / "data" / "signal_foundry" / "lane_status.json"
    try:
        lane_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "status": status,
            "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reason": reason,
        }
        lane_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("run_signal_foundry_harness: could not write lane status (%s)", exc)


# ---------------------------------------------------------------------------
# Governance event writer
# ---------------------------------------------------------------------------

def _append_governance_event(
    event_type: str,
    evidence: dict,
    root: Path,
) -> None:
    """Append a governance event to data/signal_foundry/governance.jsonl."""
    gov_path = root / "data" / "signal_foundry" / "governance.jsonl"
    try:
        gov_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event_type,
            "authored_by": "run_signal_foundry_harness",
            "evidence": evidence,
        }
        with gov_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("run_signal_foundry_harness: governance event write failed (%s)", exc)


# ---------------------------------------------------------------------------
# Count harness runs this week (from governance.jsonl)
# ---------------------------------------------------------------------------

def _count_runs_this_week(root: Path, iso_week: str) -> int:
    """Count sf_harness_run events in governance.jsonl for the current ISO week."""
    gov_path = root / "data" / "signal_foundry" / "governance.jsonl"
    rows = _read_jsonl(gov_path)
    count = 0
    for row in rows:
        if row.get("event") == "sf_harness_run":
            ev_week = (row.get("evidence") or {}).get("iso_week")
            if ev_week == iso_week:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Results check: which spec ids already have a results file?
# ---------------------------------------------------------------------------

def _results_exist_for(spec_id: str, root: Path) -> bool:
    """Return True if data/signal_foundry/results/<id>.json exists."""
    results_dir = root / "data" / "signal_foundry" / "results"
    return (results_dir / f"{spec_id}.json").exists()


# ---------------------------------------------------------------------------
# Phase 1: Register ALL pending 'proposed' specs (before any run — fair DSR n)
# ---------------------------------------------------------------------------

def _register_pending_specs(
    candidates_path: Path,
    dry_run: bool,
) -> tuple[list[dict], int]:
    """Promote all 'proposed' specs to 'registered'.

    Registration: stamp registered_at (if missing) and gates_hash (SF-R4 gate-freeze).
    ALL pending specs are registered BEFORE any run starts (fair DSR n — SF-R3).

    Returns (updated_rows, n_registered).
    """
    from engine.signal_foundry.spec import stamp_gates_hash  # noqa: PLC0415

    rows = _read_jsonl(candidates_path)
    n_registered = 0
    ts = datetime.now(timezone.utc).date().isoformat()

    for i, row in enumerate(rows):
        if row.get("status") != "proposed":
            continue
        # Stamp registered_at if not already set
        if not row.get("registered_at"):
            rows[i] = dict(row, registered_at=ts)
            row = rows[i]
        # Stamp gates_hash (SF-R4 gate-freeze)
        gates = row.get("gates")
        if gates and not row.get("gates_hash"):
            try:
                stamped = stamp_gates_hash(row)
                rows[i] = dict(row, gates_hash=stamped.get("gates_hash", ""))
                row = rows[i]
            except Exception as exc:
                log.warning("run_signal_foundry_harness: stamp_gates_hash failed for %s: %s",
                            row.get("id"), exc)
        # Transition to 'registered'
        rows[i] = dict(row, status="registered",
                       registered_at=row.get("registered_at", ts))
        n_registered += 1
        print(f"[run_signal_foundry_harness] REGISTERED: {row.get('id')} '{row.get('name', '')}'")

    if n_registered > 0 and not dry_run:
        _write_jsonl(candidates_path, rows)

    return rows, n_registered


# ---------------------------------------------------------------------------
# Phase 2: Run harness for registered specs without results
# ---------------------------------------------------------------------------

def _run_batch(
    rows: list[dict],
    candidates_path: Path,
    root: Path,
    iso_week: str,
    runs_per_week: int,
    wallclock_cap_min: float,
    dry_run: bool,
) -> dict[str, Any]:
    """Run engine.signal_foundry.harness.run_spec for eligible specs.

    Eligibility: status='registered' AND no existing results file.
    Stops when: runs_per_week cap hit, wall-clock cap hit, or no more eligible specs.

    Returns summary dict: {n_run, n_skipped, n_failed, specs_run}.
    """
    # Count runs already done this week (idempotency — SF-R6)
    runs_done_this_week = _count_runs_this_week(root, iso_week)
    runs_remaining = runs_per_week - runs_done_this_week

    if runs_remaining <= 0:
        print(f"[run_signal_foundry_harness] ISO-week run budget exhausted "
              f"({runs_per_week}/{runs_per_week}); skip batch")
        return {"n_run": 0, "n_skipped": 0, "n_failed": 0, "specs_run": []}

    # Eligible: registered, no results yet
    eligible = [
        row for row in rows
        if row.get("status") == "registered"
        and not _results_exist_for(str(row.get("id") or ""), root)
    ]

    print(f"[run_signal_foundry_harness] Eligible specs to run: {len(eligible)}, "
          f"budget remaining: {runs_remaining}/{runs_per_week}")

    batch_start = time.monotonic()
    wallclock_cap_sec = wallclock_cap_min * 60.0
    n_run = 0
    n_skipped = 0
    n_failed = 0
    specs_run: list[str] = []

    # Reload rows from file for status updates (avoid stale in-memory state)
    for spec in eligible:
        # Wall-clock cap: stop launching new specs when exceeded
        elapsed = time.monotonic() - batch_start
        if elapsed >= wallclock_cap_sec:
            n_skipped += len(eligible) - n_run - n_failed
            print(f"[run_signal_foundry_harness] Wall-clock cap reached "
                  f"({wallclock_cap_min}min); stopping batch")
            break

        # Run budget cap
        if n_run >= runs_remaining:
            n_skipped += len(eligible) - n_run - n_failed
            print(f"[run_signal_foundry_harness] ISO-week run budget cap reached; stopping batch")
            break

        spec_id = str(spec.get("id") or "")
        if not spec_id:
            n_skipped += 1
            continue

        print(f"[run_signal_foundry_harness] Running harness for {spec_id} '{spec.get('name', '')}'...")
        run_start = time.monotonic()

        if dry_run:
            print(f"[run_signal_foundry_harness] DRY-RUN: would run {spec_id}")
            n_run += 1
            specs_run.append(spec_id)
            # Update status to tested in dry-run (in-memory only)
            for i, row in enumerate(rows):
                if str(row.get("id") or "") == spec_id:
                    rows[i] = dict(row, status="tested")
                    break
            continue

        try:
            result = run_spec(spec, repo_root=root)
            run_elapsed = time.monotonic() - run_start
            verdict = result.get("verdict", "error")
            print(f"[run_signal_foundry_harness] {spec_id}: verdict={verdict} "
                  f"(elapsed={run_elapsed:.1f}s)")

            # Update status to tested
            for i, row in enumerate(rows):
                if str(row.get("id") or "") == spec_id:
                    rows[i] = dict(row,
                                   status="tested",
                                   verdict=verdict,
                                   tested_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    break

            _append_governance_event(
                "sf_harness_run",
                {
                    "spec_id": spec_id,
                    "verdict": verdict,
                    "iso_week": iso_week,
                    "elapsed_s": round(run_elapsed, 2),
                    "dry_run": dry_run,
                },
                root=root,
            )
            n_run += 1
            specs_run.append(spec_id)

        except Exception as exc:  # noqa: BLE001
            run_elapsed = time.monotonic() - run_start
            print(f"[run_signal_foundry_harness] ERROR running {spec_id}: {exc} "
                  f"(elapsed={run_elapsed:.1f}s)")
            for i, row in enumerate(rows):
                if str(row.get("id") or "") == spec_id:
                    rows[i] = dict(row,
                                   status="error",
                                   run_error=str(exc),
                                   tested_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    break
            _append_governance_event(
                "sf_harness_run",
                {
                    "spec_id": spec_id,
                    "verdict": "error",
                    "iso_week": iso_week,
                    "elapsed_s": round(run_elapsed, 2),
                    "error": str(exc),
                    "dry_run": dry_run,
                },
                root=root,
            )
            n_failed += 1

    # Flush updated candidates.jsonl
    if not dry_run and (n_run > 0 or n_failed > 0):
        _write_jsonl(candidates_path, rows)

    return {
        "n_run": n_run,
        "n_skipped": n_skipped,
        "n_failed": n_failed,
        "specs_run": specs_run,
    }


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Main entrypoint. Always returns 0 except unexpected crash."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None,
                    help="Repo root (default: inferred from script location)")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Dry-run: register specs and log but do not execute harness runs")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    dry_run = args.dry_run
    iso_week = _current_iso_week()

    print(f"[run_signal_foundry_harness] iso_week={iso_week}, dry_run={dry_run}")

    cfg = _load_config()
    budgets = cfg.get("budgets") or {}
    runs_per_week = int(budgets.get("runs_per_week", 10))
    wallclock_cap_min = float(budgets.get("run_wallclock_min", 30))

    candidates_path = root / "data" / "signal_foundry" / "candidates.jsonl"

    if not candidates_path.exists():
        print("[run_signal_foundry_harness] No candidates.jsonl found; nothing to do")
        _write_lane_status("full", "no candidates.jsonl found", root=root)
        return 0

    # ---- Phase 1: Register ALL pending 'proposed' specs BEFORE any run ----
    # (fair DSR n — SF-R3: all specs in the family are registered before the first run)
    print("[run_signal_foundry_harness] Phase 1: registering all pending specs...")
    rows, n_registered = _register_pending_specs(candidates_path, dry_run=dry_run)
    print(f"[run_signal_foundry_harness] Registered {n_registered} spec(s)")

    if n_registered > 0:
        _append_governance_event(
            "sf_batch_registration",
            {
                "iso_week": iso_week,
                "n_registered": n_registered,
                "dry_run": dry_run,
            },
            root=root,
        )

    # ---- Phase 2: Run harness batch ----
    print(f"[run_signal_foundry_harness] Phase 2: running harness batch "
          f"(cap: {runs_per_week}/week, {wallclock_cap_min}min wall-clock)...")
    batch_result = _run_batch(
        rows=rows,
        candidates_path=candidates_path,
        root=root,
        iso_week=iso_week,
        runs_per_week=runs_per_week,
        wallclock_cap_min=wallclock_cap_min,
        dry_run=dry_run,
    )

    n_run = batch_result["n_run"]
    n_skipped = batch_result["n_skipped"]
    n_failed = batch_result["n_failed"]

    print(f"[run_signal_foundry_harness] Batch complete: "
          f"{n_run} run, {n_skipped} skipped, {n_failed} failed")

    # ---- Update lane status ----
    if n_run > 0 or n_registered > 0:
        _write_lane_status(
            "full",
            (f"harness batch: {n_registered} registered, {n_run} run, "
             f"{n_skipped} skipped, {n_failed} failed; iso_week={iso_week}"),
            root=root,
        )
    else:
        _write_lane_status(
            "full",
            f"harness batch: nothing to run (all up to date); iso_week={iso_week}",
            root=root,
        )

    _append_governance_event(
        "sf_batch_complete",
        {
            "iso_week": iso_week,
            "n_registered": n_registered,
            "n_run": n_run,
            "n_skipped": n_skipped,
            "n_failed": n_failed,
            "specs_run": batch_result.get("specs_run", []),
            "dry_run": dry_run,
        },
        root=root,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
