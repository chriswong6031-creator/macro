"""scripts/codex_research_loop.py — Codex research lane loop driver (CRX-R7).

CLI:
    python -m scripts.codex_research_loop [--lane cases|signals|both]
                                          [--iterations N]
                                          [--dry-run]

Reads CODEX_MODE / CODEX_LANES / CODEX_INTERVAL_HOURS from environment.
Fail-closed: absent CODEX_MODE (or anything other than 'interval'/'auto') -> no-op.

For each iteration:
  1. budget.can_run() -> stop with reason if False.
  2. Run enabled lanes' run_once().
  3. budget.note_result() is handled INSIDE each lane (not double-noted here).
  4. Append data/codex_lane/loop_journal.jsonl row.

Exit 0 always. Prints the journal path as the last line of stdout.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

def _resolve_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _codex_mode() -> str:
    """Return CODEX_MODE env value (lower). Absent / unrecognized -> 'off'."""
    val = os.environ.get("CODEX_MODE", "").strip().lower()
    return val if val in ("interval", "auto") else "off"


def _codex_lanes() -> str:
    """Return CODEX_LANES env value. Default 'both'."""
    val = os.environ.get("CODEX_LANES", "both").strip().lower()
    return val if val in ("cases", "signals", "both") else "both"


def _codex_interval_hours() -> float:
    """Return CODEX_INTERVAL_HOURS env value. Default 6."""
    try:
        return float(os.environ.get("CODEX_INTERVAL_HOURS", "6"))
    except (ValueError, TypeError):
        return 6.0


# ---------------------------------------------------------------------------
# Budget gate (guarded import)
# ---------------------------------------------------------------------------

def _can_run(root: Path, cfg: dict | None = None) -> tuple[bool, str]:
    try:
        from engine.codex_lane.budget import can_run  # noqa: PLC0415
        return can_run(root=root, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: can_run import failed (%s); fail-closed", exc)
        return False, f"budget import error: {exc}"


def _load_cfg(root: Path) -> dict:
    try:
        from engine.codex_lane.budget import load_cfg  # noqa: PLC0415
        return load_cfg(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: load_cfg failed (%s); using defaults", exc)
        return {"budget_pct": 85, "max_sessions_per_window": 10}


# ---------------------------------------------------------------------------
# Frozen cross-builder API: fetch_rate_limits + note_rate_limits (guarded)
#
# These live in engine.codex_lane.runner and engine.codex_lane.budget
# respectively; the other builder adds them.  Tolerate ImportError / None
# (CRX-R4 — degraded mode is honest, not fatal).
# ---------------------------------------------------------------------------

def _fetch_rate_limits(timeout_s: int = 30) -> "dict | None":
    """Guarded call to runner.fetch_rate_limits(). Returns None on any failure."""
    try:
        from engine.codex_lane.runner import fetch_rate_limits  # noqa: PLC0415
        return fetch_rate_limits(timeout_s=timeout_s)
    except (ImportError, AttributeError):
        # Other builder has not yet added this function — degrade gracefully
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: fetch_rate_limits failed (%s); non-fatal", exc)
        return None


def _note_rate_limits(rl: "dict | None", root: Path) -> None:
    """Guarded call to budget.note_rate_limits(). NEVER raises."""
    if rl is None:
        return
    try:
        from engine.codex_lane.budget import note_rate_limits  # noqa: PLC0415
        note_rate_limits(rl, root=root)
    except (ImportError, AttributeError):
        # Other builder has not yet added this function — degrade gracefully
        return
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: note_rate_limits failed (%s); non-fatal", exc)


# ---------------------------------------------------------------------------
# Journal writer
# ---------------------------------------------------------------------------

def _journal_path(root: Path) -> Path:
    return root / "data" / "codex_lane" / "loop_journal.jsonl"


def _append_journal(
    root: Path,
    lane: str,
    iteration: int,
    results: dict,
    stop_reason: str | None,
) -> None:
    """Append a row to data/codex_lane/loop_journal.jsonl. NEVER raises."""
    try:
        jpath = _journal_path(root)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "lane": lane,
            "iteration": iteration,
            "results": results,
            "stop_reason": stop_reason,
        }
        with jpath.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: journal write failed (%s)", exc)


# ---------------------------------------------------------------------------
# Lane runners (guarded imports)
# ---------------------------------------------------------------------------

def _run_cases(root: Path, dry_run: bool) -> dict:
    try:
        from scripts.codex_case_lane import run_once  # noqa: PLC0415
        return run_once(root=root, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: codex_case_lane.run_once failed (%s)", exc)
        return {"ok": False, "action": "error", "detail": str(exc)}


def _run_signals(root: Path, dry_run: bool) -> dict:
    try:
        from scripts.codex_signal_lane import run_once  # noqa: PLC0415
        return run_once(root=root, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_research_loop: codex_signal_lane.run_once failed (%s)", exc)
        return {"ok": False, "action": "error", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_loop(
    root: Path | str | None = None,
    lane: str = "both",
    iterations: int = 1,
    dry_run: bool = False,
) -> dict:
    """Run the loop driver.

    Returns dict: {ok, iterations_run, journal_path, stop_reason}.
    NEVER raises.
    """
    try:
        r = _resolve_root(root)
        cfg = _load_cfg(r)
        journal = _journal_path(r)

        enabled_lanes: list[str]
        if lane == "cases":
            enabled_lanes = ["cases"]
        elif lane == "signals":
            enabled_lanes = ["signals"]
        else:
            enabled_lanes = ["cases", "signals"]

        stop_reason: str | None = None
        iterations_run = 0

        for i in range(1, iterations + 1):
            # Frozen cross-builder API: fetch live rate limits ONCE per iteration
            # BEFORE the can_run gate, so the gate uses fresh data (CRX-R4).
            rl = _fetch_rate_limits()
            _note_rate_limits(rl, r)

            # Budget gate — checked once per iteration before running any lane
            ok, reason = _can_run(r, cfg=cfg)
            if not ok:
                stop_reason = f"budget_gate (iteration {i}): {reason}"
                log.info("codex_research_loop: stopping — %s", stop_reason)
                _append_journal(r, lane, i, {}, stop_reason)
                break

            # Run enabled lanes
            iter_results: dict[str, dict] = {}
            for ln in enabled_lanes:
                if ln == "cases":
                    result = _run_cases(r, dry_run=dry_run)
                else:
                    result = _run_signals(r, dry_run=dry_run)
                iter_results[ln] = result
                log.info("codex_research_loop: iter=%d lane=%s ok=%s action=%s",
                         i, ln, result.get("ok"), result.get("action"))

            _append_journal(r, lane, i, iter_results, stop_reason=None)
            iterations_run += 1

        return {
            "ok": True,
            "iterations_run": iterations_run,
            "journal_path": str(journal),
            "stop_reason": stop_reason,
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("codex_research_loop: unexpected error: %s", exc)
        return {
            "ok": False,
            "iterations_run": 0,
            "journal_path": "",
            "stop_reason": f"error: {exc}",
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit 0 always."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--lane",
        choices=["cases", "signals", "both"],
        default=None,
        help=(
            "Which lane(s) to run. Default: CODEX_LANES env (default 'both'). "
            "cases=winner cases only, signals=signal brainstorm only."
        ),
    )
    ap.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of loop iterations. Default: 1 (or CODEX_ITERATION env if set).",
    )
    ap.add_argument("--root", type=Path, default=None, help="Repo root")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Bypass the CODEX_MODE=off gate. "
            "Also bypassed automatically when GITHUB_EVENT_NAME=workflow_dispatch."
        ),
    )
    args = ap.parse_args(argv)

    # CODEX_MODE gate: fail-closed for token-spending lane.
    # Bypassed when --force is passed OR when running as a workflow_dispatch event.
    mode = _codex_mode()
    if mode == "off":
        force = args.force or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        if not force:
            print("[codex_research_loop] CODEX_MODE=off (or absent); no-op")
            _append_journal(
                _resolve_root(args.root),
                lane=args.lane or _codex_lanes(),
                iteration=0,
                results={},
                stop_reason="mode_off",
            )
            return 0
        log.info("codex_research_loop: CODEX_MODE=off bypassed by --force / workflow_dispatch")

    lane = args.lane or _codex_lanes()
    iterations = args.iterations
    if iterations is None:
        try:
            iterations = int(os.environ.get("CODEX_ITERATIONS", "1"))
        except (ValueError, TypeError):
            iterations = 1
    iterations = max(1, iterations)

    result = run_loop(
        root=args.root,
        lane=lane,
        iterations=iterations,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2, default=str))
    # Last line: journal path (per spec)
    print(result.get("journal_path", ""))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
