"""Smoke tests for scripts/calibrate_regime.py.

Tests:
  1. main() runs end-to-end and writes regime_calibration.json
  2. n_trials is reproducible (== len(choice_ledger), computed identically each run)
  3. IC is computed as a time-series rank correlation (assert IC≈+1 on a
     synthetic monotone index→return pair)
  4. PIT path is exercised or cleanly skipped (no crash either way)
  5. Verdict field is present and correct format
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure repo root is on the path (mirrors scripts/calibrate_regime.py style)
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


@pytest.fixture(scope="module")
def calib_report(tmp_path_factory):
    """Run main() once against an isolated copy of the real signals store.

    main() reads data/vector/signals.parquet and writes regime_calibration.json
    via config.data_dir(); unredirected, that write dirties the REAL data/
    tree (tests/conftest.py MM_DATA_GUARD). One ~2.5MB copy + one run per
    module; the smoke tests below share the resulting report.

    Returns (main_return_code, report_path).
    """
    from lib import config
    from scripts.calibrate_regime import main

    real_signals = config.data_dir() / "vector" / "signals.parquet"
    if not real_signals.exists():
        pytest.skip("data/vector/signals.parquet absent")
    root = tmp_path_factory.mktemp("calib_data")
    vec = root / "vector"
    vec.mkdir(parents=True)
    shutil.copyfile(real_signals, vec / "signals.parquet")

    mp = pytest.MonkeyPatch()
    mp.setattr(config, "data_dir", lambda: root)
    try:
        ret = main()
    finally:
        mp.undo()
    return ret, root / "vector" / "regime_calibration.json"


# --------------------------------------------------------------------------- #
# 1. main() runs and writes regime_calibration.json
# --------------------------------------------------------------------------- #
def test_main_runs_and_writes_json(calib_report):
    """Full smoke test: main() must complete without raising and write the output
    JSON in the configured (isolated) data/vector/ directory."""
    ret, out = calib_report
    assert ret == 0, "main() should return 0 on success"
    assert out.exists(), f"Expected {out} to be written by main()"

    data = json.loads(out.read_text())
    assert "verdict" in data, "Output JSON must have a 'verdict' field"
    assert "n_trials" in data, "Output JSON must have 'n_trials'"
    assert "ic_table" in data, "Output JSON must have 'ic_table'"
    assert "deflated_sharpe" in data, "Output JSON must have 'deflated_sharpe'"


# --------------------------------------------------------------------------- #
# 2. n_trials is reproducible
# --------------------------------------------------------------------------- #
def test_n_trials_reproducible(calib_report):
    """n_trials must equal len(choice_ledger) and must be the same value
    on two independent calls — it is determined purely by code structure."""
    from scripts.calibrate_regime import _build_choice_ledger

    ledger1 = _build_choice_ledger()
    ledger2 = _build_choice_ledger()

    assert len(ledger1) == len(ledger2), "choice_ledger length must be deterministic"
    assert len(ledger1) > 0, "choice_ledger must not be empty"

    # Check that the freshly written JSON output agrees
    _, out = calib_report
    data = json.loads(out.read_text())
    assert data["n_trials"] == len(ledger1), (
        f"JSON n_trials={data['n_trials']} ≠ len(choice_ledger)={len(ledger1)}"
    )


# --------------------------------------------------------------------------- #
# 3. IC is computed as time-series rank correlation
# --------------------------------------------------------------------------- #
def test_ts_rank_ic_on_monotone_pair():
    """The IC function must return IC ≈ +1 when the index is perfectly monotone
    relative to the forward return (and ≈ −1 for a perfectly inverse pair).
    This asserts that ts_rank_ic is a TIME-SERIES rank correlation (not a
    cross-sectional one), and that it behaves correctly on synthetic data."""
    from scripts.calibrate_regime import ts_rank_ic

    n = 200
    dates = pd.date_range("2018-01-01", periods=n, freq="D")

    # Perfect positive monotone: index increases; so does fwd return
    idx = pd.Series(np.arange(n, dtype=float), index=dates)
    fwd = pd.Series(np.arange(n, dtype=float) * 0.001, index=dates)
    ic_pos = ts_rank_ic(idx, fwd)
    assert abs(ic_pos - 1.0) < 0.01, f"Expected IC≈1 for monotone pair, got {ic_pos}"

    # Perfect negative monotone
    fwd_neg = pd.Series(-np.arange(n, dtype=float) * 0.001, index=dates)
    ic_neg = ts_rank_ic(idx, fwd_neg)
    assert abs(ic_neg + 1.0) < 0.01, f"Expected IC≈-1 for inverse monotone pair, got {ic_neg}"

    # Random pair should give IC near 0 (seed for reproducibility)
    rng = np.random.default_rng(7)
    idx_r = pd.Series(rng.normal(size=n), index=dates)
    fwd_r = pd.Series(rng.normal(size=n), index=dates)
    ic_r  = ts_rank_ic(idx_r, fwd_r)
    assert abs(ic_r) < 0.3, f"Expected IC≈0 for random pair, got {ic_r}"

    # NaN-alignment test: ts_rank_ic must handle NaN gracefully
    idx_nan = idx.copy()
    idx_nan.iloc[::5] = float("nan")
    ic_nan = ts_rank_ic(idx_nan, fwd)
    assert abs(ic_nan - 1.0) < 0.02, f"NaN-tolerant IC should still be ≈1, got {ic_nan}"

    # Too-short series should return NaN
    short = pd.Series(np.arange(10, dtype=float),
                      index=pd.date_range("2020-01-01", periods=10))
    fwd_s = pd.Series(np.ones(10), index=short.index)
    ic_short = ts_rank_ic(short, fwd_s)
    assert not np.isfinite(ic_short), "Should return NaN for n<30"


# --------------------------------------------------------------------------- #
# 4. PIT path exercised or cleanly skipped
# --------------------------------------------------------------------------- #
def test_pit_path_does_not_crash():
    """_pit_m2_composite must not raise whether or not vintages are available.
    It should return a dict with at least an 'ok' key."""
    from scripts.calibrate_regime import _pit_m2_composite
    from lib import config

    df = pd.read_parquet(config.data_dir() / "vector" / "signals.parquet")
    df.index = pd.to_datetime(df.index)
    df = df.loc["2015-01-01":].copy()

    result = _pit_m2_composite(df)
    # Must return a dict (not raise)
    assert isinstance(result, dict), "PIT function must return a dict"
    assert "ok" in result, "PIT result must have an 'ok' key"
    # If it succeeded, check required fields
    if result.get("ok"):
        assert "ic_revised_90d" in result
        assert "ic_pit_90d" in result
        assert "delta_ic" in result
        assert "note" in result
    else:
        # Graceful failure must include a reason
        assert "reason" in result or "note" in result


# --------------------------------------------------------------------------- #
# 5. Verdict field is present and display-only
# --------------------------------------------------------------------------- #
def test_verdict_is_display_only(calib_report):
    """The verdict in the JSON must contain 'DISPLAY-ONLY' (the composite does
    not gate-clear; any other verdict indicates an unexpected result)."""
    _, out = calib_report
    data = json.loads(out.read_text())
    verdict = data.get("verdict", "")
    assert "DISPLAY-ONLY" in verdict, (
        f"Verdict should contain 'DISPLAY-ONLY' — got: {verdict!r}"
    )


# --------------------------------------------------------------------------- #
# 6. choice_ledger contains all expected knob families
# --------------------------------------------------------------------------- #
def test_choice_ledger_knobs():
    """The choice_ledger must enumerate all the documented knob families:
    Z_WINDOW, z-cut points, SLOPE_LB, TREND_MA_D, TREND_MA_W, HIVIX_Z,
    EXPO_KNOTS (6), MIN_FACTORS, PANEL_LOOKBACK, TAIL_LO, TAIL_HI, K_SWEEP (3)."""
    from scripts.calibrate_regime import _build_choice_ledger

    ledger = _build_choice_ledger()
    knob_names = {e["knob"] for e in ledger}

    # Required single-value knobs
    for expected in ("Z_WINDOW", "SLOPE_LB", "TREND_MA_D", "TREND_MA_W",
                     "HIVIX_Z", "MIN_FACTORS", "PANEL_LOOKBACK", "TAIL_LO", "TAIL_HI"):
        assert expected in knob_names, f"Expected knob '{expected}' in choice_ledger"

    # z-cut points (4)
    for zcut in ("z_cut_lo1", "z_cut_hi1", "z_cut_lo2", "z_cut_hi2"):
        assert zcut in knob_names, f"Expected z-cut knob '{zcut}'"

    # 6 EXPO knots
    for i in range(6):
        assert f"EXPO_KNOT_{i}" in knob_names, f"Expected EXPO_KNOT_{i} in choice_ledger"

    # 3 K_SWEEP values
    for kk in (4, 5, 6):
        assert f"K_SWEEP_{kk}" in knob_names, f"Expected K_SWEEP_{kk} in choice_ledger"


# --------------------------------------------------------------------------- #
# 7. CPCV structure sanity
# --------------------------------------------------------------------------- #
def test_cpcv_structure(calib_report):
    """CPCV result must have non_independence_warning=True and a n_paths ≥ 0."""
    _, out = calib_report
    data = json.loads(out.read_text())
    cpcv = data.get("cpcv", {})
    assert cpcv.get("non_independence_warning") is True, (
        "CPCV must have non_independence_warning=True"
    )
    assert cpcv.get("n_paths", -1) >= 0, "n_paths must be >= 0"
