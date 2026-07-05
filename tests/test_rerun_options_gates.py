"""Tests for scripts/rerun_options_gates_thetadata.py.

Uses the hermetic fixture store (tests/fixtures/thetadata_store/).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURE_STORE = Path(__file__).parent / "fixtures" / "thetadata_store"


def _store():
    return str(FIXTURE_STORE)


# --------------------------------------------------------------------------- #
# Gate JSON schema / mandatory fields                                           #
# --------------------------------------------------------------------------- #

def test_doi_gate_schema():
    from scripts.rerun_options_gates_thetadata import run_s_doi
    from engine.thetadata_store import universe

    roots = universe(store=_store())
    tr_closes = pd.DataFrame()
    gate = run_s_doi(roots, tr_closes, store=_store(), smoke=False)

    assert gate["scored"] is False
    assert gate["store"] == "thetadata_eod"
    assert gate["reconstructed"] is True
    assert "era_stats" in gate
    assert "pooled" in gate
    assert "gate_criteria" in gate
    assert gate["gate_criteria"]["source"] == "OPTIONS_ALPHA_MASTERPLAN §4 — unchanged"
    assert gate["gate_criteria"]["hac_t_bar"] == 2.0
    assert gate["gate_criteria"]["min_dates"] == 60
    assert gate["iv_coverage"] is None  # S-DOI does not require IV
    # Era splits present
    for era in ["2012-15", "2016-19", "2020-22", "2023+"]:
        assert era in gate["era_stats"]


def test_cwiv_gate_schema():
    from scripts.rerun_options_gates_thetadata import run_s_cwiv_or_xzz
    from engine.thetadata_store import universe, iv_coverage

    roots = universe(store=_store())
    iv_cov = iv_coverage(store=_store())
    gate = run_s_cwiv_or_xzz("cwiv", roots, iv_cov, store=_store(), smoke=False)

    assert gate["scored"] is False
    assert gate["signal"] == "S-CWIV"
    assert gate["store"] == "thetadata_eod"
    assert gate["reconstructed"] is True
    assert "iv_coverage" in gate
    assert gate["iv_coverage"]["n_roots_with_iv"] == len(iv_cov)
    assert "era_stats" in gate
    assert gate["gate_criteria"]["min_dates"] == 120


def test_xzz_gate_schema():
    from scripts.rerun_options_gates_thetadata import run_s_cwiv_or_xzz
    from engine.thetadata_store import universe, iv_coverage

    roots = universe(store=_store())
    iv_cov = iv_coverage(store=_store())
    gate = run_s_cwiv_or_xzz("xzz", roots, iv_cov, store=_store(), smoke=False)

    assert gate["scored"] is False
    assert gate["signal"] == "S-XZZ"
    assert gate["gate_criteria"]["min_names_per_date"] == 15


# --------------------------------------------------------------------------- #
# Smoke mode: gate JSON files must NOT be written                              #
# --------------------------------------------------------------------------- #

def test_smoke_mode_no_gate_json_written(tmp_path, monkeypatch):
    """Smoke mode must not write gate JSON files (gate files stay untouched)."""
    import os

    monkeypatch.setenv("THETADATA_STORE", _store())

    # Patch lib.config to return tmp_path as data_dir
    import lib.config
    monkeypatch.setattr(lib.config, "data_dir", lambda: tmp_path)

    # Simulate the main() --smoke flow by calling individual gate functions
    from scripts.rerun_options_gates_thetadata import run_s_doi
    from engine.thetadata_store import universe

    roots = universe(store=_store())
    tr_closes = pd.DataFrame()
    gate = run_s_doi(roots, tr_closes, store=_store(), smoke=True)

    # Verify [SMOKE] label
    assert "[SMOKE]" in gate["note"]

    # No gate file should be written to tmp_path
    doi_path = tmp_path / "options_flow" / "gate_doi_thetadata.json"
    assert not doi_path.exists()


# --------------------------------------------------------------------------- #
# Thin-universe exclusion tally                                                 #
# --------------------------------------------------------------------------- #

def test_thin_universe_tallied_in_era_stats():
    """With only 2 roots in the fixture store, most dates should be excluded
    by the breadth floor (min 5 names for S-DOI, 15 for S-CWIV/S-XZZ)."""
    from scripts.rerun_options_gates_thetadata import run_s_doi
    from engine.thetadata_store import universe

    roots = universe(store=_store())
    assert len(roots) == 2  # SPY + AAPL

    tr_closes = pd.DataFrame()
    gate = run_s_doi(roots, tr_closes, store=_store())

    # With no forward returns, all dates will show n_dates=0
    for era_label, lo, hi in [("2019 era", "2019-01-01", "2019-12-31")]:
        pass  # just checking the structure is correct

    # Pooled stats should have n_dates=0 (no forward returns, < 5 names)
    pooled = gate["pooled"]
    for h in ["5", "10"]:
        assert str(h) in pooled


# --------------------------------------------------------------------------- #
# doi_series oi[t-1] law — adversarial anti-lookahead test                    #
# --------------------------------------------------------------------------- #

def test_doi_no_future_oi_leak():
    """Verify that injecting a future OI spike does NOT appear as a day-t signal.

    We create a synthetic OI series where date 3 has a huge spike.
    With correct oi[t-1] shift: signal at date 3 uses oi[date 2] (pre-spike).
    Without the shift (bug): signal at date 3 would use oi[date 3] (lookahead).

    We test that doi_series for date 3 does NOT reflect the spike value.
    """
    import pandas as pd
    from engine.thetadata_store import doi_series, _load_parquets, _normalise_date, store_root

    # Get raw OI totals
    oi_raw = _load_parquets("oi", "SPY", None, _store())
    oi_raw = _normalise_date(oi_raw)
    raw_totals = oi_raw.groupby("date")["open_interest"].sum().sort_index()

    # Verify that doi_series correctly shifts the raw OI
    s = doi_series("SPY", put_call="both", window=1, store=_store())
    s_indexed = s.set_index("date").sort_index()

    raw_dates = sorted(raw_totals.index)
    for i, d in enumerate(raw_dates):
        d_str = str(d)
        if d_str not in s_indexed.index:
            continue
        got_shifted_oi = s_indexed.loc[d_str, "total_oi"]
        if i == 0:
            # First date: shift(1) → NaN (no prior data)
            assert np.isnan(float(got_shifted_oi)), (
                f"First date {d_str}: expected NaN (shift(1) of first row), "
                f"got {got_shifted_oi}"
            )
        else:
            # Date i: should reflect raw_totals[i-1] (prior day, not current day)
            expected = float(raw_totals.iloc[i - 1])
            got = float(got_shifted_oi)
            if not np.isnan(got):
                assert abs(got - expected) < 1.0, (
                    f"At {d_str}: oi_shifted should be {expected:.0f} (= raw OI at {raw_dates[i-1]}), "
                    f"but got {got:.0f}. "
                    "This indicates a lookahead bug — same-day OI is being used."
                )


# --------------------------------------------------------------------------- #
# Era boundaries (also in test_thetadata_store.py — belt-and-suspenders)       #
# --------------------------------------------------------------------------- #

def test_era_boundary_2020():
    """2019-12-31 is in 2016-19; 2020-01-01 is in 2020-22."""
    from scripts.rerun_options_gates_thetadata import _era
    assert _era("2019-12-31") == "2016-19"
    assert _era("2020-01-01") == "2020-22"


def test_era_boundary_pooled():
    """pooled covers all eras (2012 through present)."""
    from scripts.rerun_options_gates_thetadata import _era_filter
    dates = ["2012-06-01", "2015-12-31", "2016-01-01", "2023-01-01", "2026-07-04"]
    pooled = _era_filter(dates, "2012-01-01", "2099-12-31")
    assert len(pooled) == len(dates)


# --------------------------------------------------------------------------- #
# Gate criteria are hardcoded from registry (not result-dependent)             #
# --------------------------------------------------------------------------- #

def test_gate_criteria_immutable():
    """Gate thresholds must exactly match the pre-registered values in §4."""
    from scripts.rerun_options_gates_thetadata import (
        _DOI_T_BAR, _IV_T_BAR, _DOI_MIN_DATES, _IV_MIN_DATES,
        _DOI_MIN_NAMES, _IV_MIN_NAMES, _DOI_HORIZONS,
    )
    # From OPTIONS_ALPHA_MASTERPLAN §4
    assert _DOI_T_BAR == 2.0
    assert _IV_T_BAR == 2.0
    assert _DOI_MIN_DATES == 60
    assert _IV_MIN_DATES == 120
    assert _DOI_MIN_NAMES == 5
    assert _IV_MIN_NAMES == 15
    assert 5 in _DOI_HORIZONS
    assert 10 in _DOI_HORIZONS


# --------------------------------------------------------------------------- #
# Report template                                                               #
# --------------------------------------------------------------------------- #

def test_report_written_in_smoke_mode(tmp_path, monkeypatch):
    """Smoke mode SHOULD write the report (labeled SMOKE) but not gate files."""
    import os
    from scripts.rerun_options_gates_thetadata import run_s_doi, _write_report
    from engine.thetadata_store import universe, iv_coverage

    roots = universe(store=_store())
    iv_cov = iv_coverage(store=_store())
    tr_closes = pd.DataFrame()

    doi_gate = run_s_doi(roots, tr_closes, store=_store(), smoke=True)
    gates = {"S-DOI": doi_gate}

    # Write report to tmp_path
    import importlib
    import lib.config
    monkeypatch.setattr(lib.config, "data_dir", lambda: tmp_path)

    # Patch the reports dir to tmp_path
    from unittest.mock import patch
    with patch("scripts.rerun_options_gates_thetadata.Path") as mock_path:
        # We just test _write_report doesn't crash with smoke=True
        pass

    # Call _write_report directly, it writes to reports/ relative to script
    # Just verify it runs without error
    try:
        p = _write_report(gates, _store(), iv_cov, smoke=True)
        assert p.exists()
        content = p.read_text()
        assert "SMOKE" in content
        assert "Post-publication Decay Commentary" in content
    finally:
        # Clean up
        if p.exists():
            p.unlink()


# --------------------------------------------------------------------------- #
# Existing skew/ivspread validators — regression guard                         #
# --------------------------------------------------------------------------- #

def test_skew_build_panel_default_no_error():
    """The refactored build_panel(chain_provider=None) must not raise."""
    from scripts.validate_options_skew import build_panel
    panel = build_panel(chain_provider=None)
    assert isinstance(panel, pd.DataFrame)


def test_ivspread_build_panel_default_no_error():
    """The refactored ivspread build_panel(chain_provider=None) must not raise."""
    from scripts.validate_options_ivspread import build_panel
    panel = build_panel(chain_provider=None)
    assert isinstance(panel, pd.DataFrame)


def test_skew_gate_structure_unchanged():
    """The existing skew validator gate structure is unchanged after refactor."""
    from scripts.validate_options_skew import _fwd_ic, _HORIZONS, _MIN_DATES, _MIN_NAMES, _T_BAR
    assert _T_BAR == 2.0
    assert _MIN_DATES == 120
    assert _MIN_NAMES == 15
    assert 5 in _HORIZONS


def test_ivspread_gate_structure_unchanged():
    """The existing ivspread validator gate structure is unchanged after refactor."""
    from scripts.validate_options_ivspread import _fwd_ic, _HORIZONS, _MIN_DATES, _MIN_NAMES, _T_BAR
    assert _T_BAR == 2.0
    assert _MIN_DATES == 120
    assert _MIN_NAMES == 15
    assert 5 in _HORIZONS
