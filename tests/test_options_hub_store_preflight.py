"""tests/test_options_hub_store_preflight.py — the guards that ended the 08-07 wedge.

On 2026-08-07 the nightly options-hub run resolved its store successfully, then
blocked forever on the first read across a symlink onto an external volume that
the launchd context had no TCC grant for. Python does not get EPERM there — it
blocks in the kernel. The job burned 1.7 s of CPU across 4.5 h looking alive,
and every options surface served the previous session.

Both guards run their probe on a SEPARATE thread, because the failure mode is an
uninterruptible read: a timeout the main thread has to check is a timeout that
never gets checked. These tests therefore have to exercise the real blocking
behaviour, in a subprocess, since the guards deliberately end in os._exit.

Run: .venv/bin/python -m pytest tests/test_options_hub_store_preflight.py -q
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(body: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout,
    )


def test_a_store_that_blocks_forever_exits_instead_of_hanging():
    """THE regression: an unreadable store must not be able to hang the run."""
    started = time.monotonic()
    proc = _run(
        """
        import os, sys, time
        real = os.listdir
        def hang(p):
            if "thetadata_eod" in str(p):
                time.sleep(3600)      # the wedge: a read that never returns
            return real(p)
        os.listdir = hang
        os.makedirs("/tmp/pf_probe/thetadata_eod/eod", exist_ok=True)
        from scripts.build_options_hub_nightly import preflight_store
        preflight_store("/tmp/pf_probe/thetadata_eod", budget_s=2)
        print("REACHED_UNREACHABLE_CODE")
        """
    )
    elapsed = time.monotonic() - started
    assert proc.returncode == 4, (
        f"expected the named exit code 4, got {proc.returncode}\n{proc.stderr[-2000:]}"
    )
    assert "REACHED_UNREACHABLE_CODE" not in proc.stdout
    assert elapsed < 90, f"guard took {elapsed:.0f}s — it is not bounding the read"


def test_the_abort_names_the_cause_rather_than_dying_quietly():
    """A silent exit is a page at 3am; the log must say what to go fix."""
    proc = _run(
        """
        import os, time
        real = os.listdir
        def hang(p):
            if "thetadata_eod" in str(p):
                time.sleep(3600)
            return real(p)
        os.listdir = hang
        os.makedirs("/tmp/pf_probe2/thetadata_eod/oi", exist_ok=True)
        from scripts.build_options_hub_nightly import preflight_store
        preflight_store("/tmp/pf_probe2/thetadata_eod", budget_s=2)
        """
    )
    err = proc.stderr.lower()
    assert "blocked, not slow" in err
    assert "tcc" in err and "removable" in err


def test_a_readable_store_passes_straight_through():
    """The guard must be invisible on every healthy run."""
    proc = _run(
        """
        import os
        for sub in ("eod", "oi", "greeks"):
            os.makedirs(f"/tmp/pf_ok/thetadata_eod/{sub}", exist_ok=True)
        from scripts.build_options_hub_nightly import preflight_store
        preflight_store("/tmp/pf_ok/thetadata_eod", budget_s=30)
        print("PASSED_THROUGH")
        """
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "PASSED_THROUGH" in proc.stdout


def test_the_stall_watchdog_fires_when_progress_stops():
    """Covers a hang anywhere else in the run — heartbeat, not elapsed time."""
    proc = _run(
        """
        import time
        from scripts.build_options_hub_nightly import _arm_stall_watchdog, heartbeat
        heartbeat("test start")
        _arm_stall_watchdog(budget_s=2)
        time.sleep(300)               # a run that stopped making progress
        print("REACHED_UNREACHABLE_CODE")
        """
    )
    assert proc.returncode == 3, f"got {proc.returncode}\n{proc.stderr[-2000:]}"
    assert "REACHED_UNREACHABLE_CODE" not in proc.stdout
    assert "no progress" in proc.stderr.lower()


def test_a_slow_but_progressing_run_is_never_killed():
    """The distinction the whole design rests on: slow is not wedged."""
    proc = _run(
        """
        import time
        from scripts.build_options_hub_nightly import _arm_stall_watchdog, heartbeat
        heartbeat("test start")
        _arm_stall_watchdog(budget_s=3)
        for i in range(12):           # well past the budget, but progressing
            time.sleep(1)
            heartbeat(f"root {i}")
        print("SURVIVED")
        """
    )
    assert proc.returncode == 0, f"a progressing run was killed\n{proc.stderr[-2000:]}"
    assert "SURVIVED" in proc.stdout
