"""tests/test_lab_backtest_cli.py — Smoke tests for scripts/lab_backtest.py.

Tests:
  1. --list prints >=40 signals (catalog is populated).
  2. A 2-ticker quick backtest of one signal returns a Trial-like dict without error.
  3. --list with a family filter works.
  4. --json flag produces parseable JSON.
  5. Unknown signal_id returns exit code 1.
  6. Missing signal_id (no args) returns exit code 1.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from unittest import mock

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_ohlcv(n: int = 600, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.012, n))
    high = close * (1.0 + rng.uniform(0.0, 0.01, n))
    low = close * (1.0 - rng.uniform(0.0, 0.01, n))
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame(
        {"close": close, "high": high, "low": low, "volume": volume},
        index=dates,
    )


def _fake_universe(n: int = 2, bars: int = 600) -> dict[str, pd.DataFrame]:
    return {f"T{i}": _fake_ohlcv(bars, seed=i) for i in range(n)}


def _run_cli(argv: list[str], fake_univ: dict | None = None):
    """Run the CLI via main() with optional universe patching.

    Returns (exit_code, stdout_text).
    """
    from scripts.lab_backtest import main

    buf = StringIO()
    if fake_univ is not None:
        from engine import lab as _lab
        with mock.patch.object(_lab, "load", return_value=fake_univ):
            with mock.patch("sys.stdout", buf):
                code = main(argv)
    else:
        with mock.patch("sys.stdout", buf):
            code = main(argv)

    return code, buf.getvalue()


# ---------------------------------------------------------------------------
# 1. --list prints >=40 signals
# ---------------------------------------------------------------------------

def test_list_has_at_least_40_signals():
    """--list must enumerate at least 40 signals from the catalog."""
    code, out = _run_cli(["--list"])
    assert code == 0, f"--list exited with code {code}"
    # Count the signal IDs: each signal line has a leading + or - or ~ marker
    signal_lines = [ln for ln in out.splitlines() if ln.strip().startswith(("+", "-", "~"))]
    assert len(signal_lines) >= 40, (
        f"Expected >=40 signal lines, got {len(signal_lines)}.\nOutput:\n{out[:2000]}"
    )


# ---------------------------------------------------------------------------
# 2. 2-ticker quick backtest returns a Trial-like dict without error
# ---------------------------------------------------------------------------

def test_quick_backtest_returns_trial_dict():
    """Backtest of a known signal on a 2-ticker fake universe returns Trial stats dict."""
    from engine import lab, tech_catalog

    sigs = tech_catalog.list_signals()
    assert sigs, "tech_catalog returned an empty catalog — cannot run backtest smoke test"

    # Pick the first signal
    signal_id = sigs[0]["signal_id"]
    universe = _fake_universe(n=2, bars=600)

    trial = lab.catalog_backtest(signal_id, universe, cost_bps=5.0)

    # Must be a Trial instance
    from engine.lab import Trial
    assert isinstance(trial, Trial), f"Expected Trial, got {type(trial)}"
    assert trial.survivorship_biased is True
    assert isinstance(trial.stats, dict), "trial.stats must be a dict"

    # Verdict must be in the known taxonomy
    verdict = trial.verdict()
    assert verdict in ("TRADABLE", "ENTRY-OVERLAY", "RISK-CONTROL", "NO-EDGE"), (
        f"Unexpected verdict: {verdict!r}"
    )


# ---------------------------------------------------------------------------
# 3. --list with a family filter
# ---------------------------------------------------------------------------

def test_list_family_filter():
    """--list <family> must restrict output to that family."""
    from engine import tech_catalog

    # Pick a family that exists
    families = tech_catalog.signal_families()
    assert families, "No signal families in catalog"
    target_family = families[0]

    code, out = _run_cli(["--list", target_family])
    assert code == 0, f"--list family exited with {code}"
    # The family name should appear in the header block
    assert target_family in out, f"Family name {target_family!r} not in output"


# ---------------------------------------------------------------------------
# 4. --json produces parseable JSON
# ---------------------------------------------------------------------------

def test_json_flag_parseable():
    """--json must produce a parseable JSON object with expected keys."""
    from engine import tech_catalog

    sigs = tech_catalog.list_signals()
    assert sigs, "Empty catalog"

    signal_id = sigs[0]["signal_id"]
    universe = _fake_universe(n=2, bars=600)

    code, out = _run_cli(["signal_id_placeholder", "--json"], fake_univ=universe)
    # We patch both load AND the actual call via the full argv path
    # Easier: call with a real signal via the full main() path but patch load
    from engine import lab as _lab
    from scripts.lab_backtest import main

    buf = StringIO()
    with mock.patch.object(_lab, "load", return_value=universe):
        with mock.patch("sys.stdout", buf):
            exit_code = main([signal_id, "--json", "--universe", "quick"])

    assert exit_code == 0, f"CLI exited with {exit_code}"
    text = buf.getvalue()

    # Find the JSON portion (after the "Running backtest..." line)
    json_lines = []
    in_json = False
    for line in text.splitlines():
        if line.strip().startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(line)

    json_text = "\n".join(json_lines)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        pytest.fail(f"--json output is not valid JSON: {exc}\nOutput:\n{text}")

    assert "signal_id" in data, "JSON output must contain 'signal_id'"
    assert "verdict" in data, "JSON output must contain 'verdict'"
    assert "stats" in data, "JSON output must contain 'stats'"
    assert data["signal_id"] == signal_id


# ---------------------------------------------------------------------------
# 5. Unknown signal_id returns exit code 1
# ---------------------------------------------------------------------------

def test_unknown_signal_exits_1():
    """Passing an unknown signal_id must exit with code 1."""
    from scripts.lab_backtest import main

    buf_err = StringIO()
    with mock.patch("sys.stderr", buf_err):
        with mock.patch("sys.stdout", StringIO()):
            code = main(["__no_such_signal_xyz__"])

    assert code == 1, f"Expected exit code 1 for unknown signal, got {code}"
    assert "not found" in buf_err.getvalue().lower() or "error" in buf_err.getvalue().lower()


# ---------------------------------------------------------------------------
# 6. Missing signal_id (no positional arg) returns exit code 1
# ---------------------------------------------------------------------------

def test_no_args_exits_1():
    """Running with no signal_id and no --list must exit with code 1."""
    from scripts.lab_backtest import main

    with mock.patch("sys.stdout", StringIO()):
        code = main([])

    assert code == 1, f"Expected exit code 1 for no args, got {code}"


# ---------------------------------------------------------------------------
# 7. list_signals JSON mode
# ---------------------------------------------------------------------------

def test_list_json_parseable():
    """--list --json must produce a parseable JSON array."""
    from scripts.lab_backtest import main

    buf = StringIO()
    with mock.patch("sys.stdout", buf):
        code = main(["--list", "--json"])

    assert code == 0
    text = buf.getvalue().strip()
    data = json.loads(text)
    assert isinstance(data, list), "Expected JSON array"
    assert len(data) >= 40, f"Expected >=40 signals in JSON list, got {len(data)}"
    # Each entry must have signal_id
    for entry in data:
        assert "signal_id" in entry, f"Missing signal_id in entry: {entry}"
