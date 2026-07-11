"""tests/test_metabolism_w2_pulse.py — W2 pulse build: verify script + dream invocability.

COVERAGE:
  1. metabolism_verify --scan: no dockets dir → clean no-op (exit 0, zero writes).
  2. metabolism_verify --scan: dockets with check_by in future → skipped.
  3. metabolism_verify --scan: docket with check_by arrived → triggers _run_single.
  4. metabolism_verify --scan: already-verified cycle → skipped.
  5. metabolism_verify --cycle-id (single-cycle) still works with valid args.
  6. metabolism_verify with no args (no --cycle-id, no --scan) → logs error, exit 0.
  7. metabolism_dream.main() accepts --dry-run + --today with no crash (no real LLM call).
  8. metabolism_verify respects AUTONOMY_PAUSED kill switch (scan mode).
  9. metabolism_verify respects AUTONOMY_PAUSED kill switch (single-cycle mode).

All tests are HERMETIC (tmp dirs, monkeypatched kill-switch, no network).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    """Create a minimal metabolism directory tree in a temp dir."""
    d = Path(tempfile.mkdtemp())
    for sub in [
        "data/metabolism/dockets",
        "data/metabolism/verify",
        "data/metabolism/journal",
        "data/metabolism/fitness",
    ]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _write_docket(root: Path, cycle_id: str, check_by: str) -> None:
    """Write a minimal docket with one proposal whose check_by is given."""
    docket = {
        "schema": "metabolism.docket.v1",
        "cycle_id": cycle_id,
        "proposals": [
            {
                "proposal_id": f"{cycle_id}-p0",
                "fitness_contract": {
                    "check_by": check_by,
                    "falsifier": {"sensor": "ic_sharpe", "band": [0.0, None]},
                },
            }
        ],
    }
    path = root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
    path.write_text(json.dumps(docket), encoding="utf-8")


def _write_verify_record(root: Path, cycle_id: str) -> None:
    """Simulate an already-verified cycle by placing a verify record."""
    record = {"schema": "metabolism.verify.v1", "cycle_id": cycle_id}
    path = root / "data" / "metabolism" / "verify" / f"{cycle_id}.json"
    path.write_text(json.dumps(record), encoding="utf-8")


# ── Test: scan with no dockets dir ───────────────────────────────────────────

def test_scan_no_dockets_dir_exits_zero():
    """--scan with no dockets dir: clean no-op, exit 0."""
    root = Path(tempfile.mkdtemp())
    # Intentionally don't create data/metabolism/dockets

    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        from scripts.metabolism_verify import main
        rc = main(["--scan", "--root", str(root)])
    assert rc == 0


# ── Test: scan, future check_by ───────────────────────────────────────────────

def test_scan_skips_future_check_by():
    """--scan: docket with check_by in future → not triggered."""
    root = _tmp_root()
    future = "2099-12-31"
    _write_docket(root, "cycle-future", future)

    called = []

    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        with patch("scripts.metabolism_verify._run_single", side_effect=lambda *a, **kw: called.append(a)):
            from scripts.metabolism_verify import main
            rc = main(["--scan", "--root", str(root), "--today", "2026-07-11"])

    assert rc == 0
    assert len(called) == 0, "future check_by should not trigger _run_single"


# ── Test: scan, past check_by → triggers _run_single ─────────────────────────

def test_scan_triggers_run_single_for_past_check_by():
    """--scan: docket with check_by arrived → triggers _run_single once."""
    root = _tmp_root()
    _write_docket(root, "cycle-past", "2026-07-01")

    called = []

    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        with patch("scripts.metabolism_verify._run_single", side_effect=lambda *a, **kw: called.append(a)):
            from scripts.metabolism_verify import main
            rc = main(["--scan", "--root", str(root), "--today", "2026-07-11"])

    assert rc == 0
    assert len(called) == 1, "past check_by should trigger exactly one _run_single call"
    assert called[0][0] == "cycle-past"


# ── Test: scan, already verified → skipped ───────────────────────────────────

def test_scan_skips_already_verified():
    """--scan: cycle that already has a verify record is skipped."""
    root = _tmp_root()
    _write_docket(root, "cycle-done", "2026-07-01")
    _write_verify_record(root, "cycle-done")

    called = []

    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        with patch("scripts.metabolism_verify._run_single", side_effect=lambda *a, **kw: called.append(a)):
            from scripts.metabolism_verify import main
            rc = main(["--scan", "--root", str(root), "--today", "2026-07-11"])

    assert rc == 0
    assert len(called) == 0, "already-verified cycle should be skipped"


# ── Test: single-cycle mode still works ──────────────────────────────────────

def test_single_cycle_mode():
    """--cycle-id in single-cycle mode still triggers _run_single."""
    root = _tmp_root()

    called = []

    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        with patch("scripts.metabolism_verify._run_single", side_effect=lambda *a, **kw: called.append(a)):
            from scripts.metabolism_verify import main
            rc = main(["--cycle-id", "cycle-xyz", "--root", str(root)])

    assert rc == 0
    assert len(called) == 1
    assert called[0][0] == "cycle-xyz"


# ── Test: no args → logs error, exits 0 (NEVER-RAISE) ────────────────────────

def test_no_args_exits_zero():
    """No --cycle-id and no --scan: logs error, exits 0 (NEVER-RAISE contract)."""
    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        from scripts.metabolism_verify import main
        rc = main(["--root", "/tmp"])
    assert rc == 0


# ── Test: AUTONOMY_PAUSED kills scan mode ────────────────────────────────────

def test_scan_respects_kill_switch():
    """--scan with AUTONOMY_PAUSED → exits 0, no work done."""
    root = _tmp_root()
    _write_docket(root, "cycle-paused", "2026-07-01")

    called = []

    with patch("scripts.metabolism_guard.is_paused", return_value=True):
        with patch("scripts.metabolism_guard.pause_reason", return_value="AUTONOMY_PAUSED=true"):
            with patch("scripts.metabolism_verify._run_single", side_effect=lambda *a, **kw: called.append(a)):
                from scripts.metabolism_verify import main
                rc = main(["--scan", "--root", str(root), "--today", "2026-07-11"])

    assert rc == 0
    assert len(called) == 0, "kill switch should prevent any work"


# ── Test: AUTONOMY_PAUSED kills single-cycle mode ────────────────────────────

def test_single_cycle_respects_kill_switch():
    """--cycle-id with AUTONOMY_PAUSED → exits 0, no work done."""
    root = _tmp_root()

    called = []

    with patch("scripts.metabolism_guard.is_paused", return_value=True):
        with patch("scripts.metabolism_guard.pause_reason", return_value="AUTONOMY_PAUSED=true"):
            with patch("scripts.metabolism_verify._run_single", side_effect=lambda *a, **kw: called.append(a)):
                from scripts.metabolism_verify import main
                rc = main(["--cycle-id", "cycle-x", "--root", str(root)])

    assert rc == 0
    assert len(called) == 0


# ── Test: metabolism_dream main() is cron-invokable (dry-run, no LLM) ────────

def test_dream_dry_run_exits_zero():
    """metabolism_dream.main(['--dry-run', '--today', ...]) exits 0 with paused guard."""
    with patch("scripts.metabolism_guard.is_paused", return_value=True):
        from scripts.metabolism_dream import main as dream_main
        rc = dream_main(["--dry-run", "--today", "2026-07-11"])
    assert rc == 0


def test_dream_scan_mode_no_crash_when_paused():
    """metabolism_dream.main() with AUTONOMY_PAUSED pauses cleanly."""
    with patch("scripts.metabolism_dream._check_paused", return_value=True):
        from scripts.metabolism_dream import main as dream_main
        rc = dream_main([])
    assert rc == 0


# ── Test: "validated" absent from verify script ──────────────────────────────

def test_validated_absent_from_verify_script():
    """The word 'validated' must not appear in metabolism_verify.py output strings."""
    src = (_ROOT / "scripts" / "metabolism_verify.py").read_text(encoding="utf-8")
    # Check user-facing strings (log messages, docstrings) — not comments with the CI rule name
    lower = src.lower()
    # Find all string literals and log messages containing 'validated'
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "validated" not in node.value.lower(), (
                f"'validated' found in string literal at line {node.lineno}: {node.value!r}"
            )
