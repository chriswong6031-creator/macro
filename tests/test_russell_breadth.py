"""Tests for collectors.russell_breadth — RussellBreadthAdapter.

Contract:
  - Constituent floor: ≥1,600 rows; stale/absent JSON keeps last committed
    constituents.parquet (never-shrink-the-ledger semantics).
  - Stale-JSON guard: idx_rut.json older than 7 days is rejected.
  - GROUPS in engine.universe_history contains "russell_breadth": "r2000".
  - Adapter registered in scripts.collect.all_adapters().
  - _download_closes chunking override: patches batch_size to 250.
  - compute() drops rows with n_members < 1,200.

No network calls: all I/O is mocked/patched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import collectors.russell_breadth as rb
from collectors.russell_breadth import RussellBreadthAdapter, _CONSTITUENTS_FLOOR, _JSON_MAX_AGE_DAYS, _N_REPORTING_FLOOR


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_payload(n: int, age_days: float = 0.0) -> dict:
    """Build a minimal idx_rut.json payload with n rows."""
    from datetime import timedelta
    as_of_dt = datetime.now(timezone.utc) - timedelta(days=age_days)
    rows = [
        {"ticker": f"T{i:04d}", "company": f"Company {i}", "sector": "Technology"}
        for i in range(n)
    ]
    return {
        "filter": "idx_rut",
        "as_of": as_of_dt.strftime("%Y-%m-%d %H:%M UTC"),
        "n": n,
        "rows": rows,
    }


def _make_constituents_parquet(tmp_path, n: int = 1800) -> None:
    """Write a committed constituents.parquet with n rows."""
    cpath = tmp_path / "russell_breadth" / "constituents.parquet"
    cpath.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {"name": [f"Company {i}" for i in range(n)],
         "sector": ["Technology"] * n},
        index=pd.Index([f"T{i:04d}" for i in range(n)], name="symbol"),
    )
    df.to_parquet(cpath)


# ---------------------------------------------------------------------------
# constituents() — happy path: valid JSON with enough rows
# ---------------------------------------------------------------------------

def test_constituents_from_valid_json(tmp_path, monkeypatch):
    payload = _make_payload(1900, age_days=0.5)
    monkeypatch.setattr(rb, "_load_finviz_json", lambda: payload)
    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cache_path = tmp_path / "russell_breadth" / "_closes_cache.parquet"
    adapter.cfg = {}  # _repair() reads cfg.ticker_fixups; runtime __init__ always sets it

    members = adapter.constituents()
    assert len(members) == 1900
    assert set(members.columns) >= {"symbol", "name", "sector"}
    assert members["symbol"].iloc[0] == "T0000"


# ---------------------------------------------------------------------------
# Stale-JSON guard: JSON older than _JSON_MAX_AGE_DAYS → use parquet fallback
# ---------------------------------------------------------------------------

def test_stale_json_falls_back_to_parquet(tmp_path, monkeypatch, caplog):
    _make_constituents_parquet(tmp_path, n=1850)
    payload = _make_payload(1900, age_days=_JSON_MAX_AGE_DAYS + 1)
    monkeypatch.setattr(rb, "_load_finviz_json", lambda: payload)
    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cache_path = tmp_path / "russell_breadth" / "_closes_cache.parquet"
    adapter.cfg = {}  # _repair() reads cfg.ticker_fixups; runtime __init__ always sets it

    import logging
    with caplog.at_level(logging.WARNING, logger="collectors.russell_breadth"):
        members = adapter.constituents()

    assert len(members) == 1850
    assert "stale" in caplog.text.lower() or "idx_rut.json" in caplog.text


# ---------------------------------------------------------------------------
# Floor guard: JSON with too few rows → use parquet fallback (never-shrink)
# ---------------------------------------------------------------------------

def test_small_json_falls_back_to_parquet(tmp_path, monkeypatch, caplog):
    _make_constituents_parquet(tmp_path, n=1800)
    payload = _make_payload(_CONSTITUENTS_FLOOR - 1, age_days=0.5)
    monkeypatch.setattr(rb, "_load_finviz_json", lambda: payload)
    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cache_path = tmp_path / "russell_breadth" / "_closes_cache.parquet"
    adapter.cfg = {}  # _repair() reads cfg.ticker_fixups; runtime __init__ always sets it

    import logging
    with caplog.at_level(logging.WARNING, logger="collectors.russell_breadth"):
        members = adapter.constituents()

    assert len(members) == 1800
    assert "floor" in caplog.text.lower() or "idx_rut.json" in caplog.text


# ---------------------------------------------------------------------------
# Absent JSON + present parquet → use parquet (never-shrink, no error)
# ---------------------------------------------------------------------------

def test_absent_json_uses_parquet(tmp_path, monkeypatch):
    _make_constituents_parquet(tmp_path, n=1750)
    monkeypatch.setattr(rb, "_load_finviz_json", lambda: None)
    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cache_path = tmp_path / "russell_breadth" / "_closes_cache.parquet"
    adapter.cfg = {}  # _repair() reads cfg.ticker_fixups; runtime __init__ always sets it

    members = adapter.constituents()
    assert len(members) == 1750


# ---------------------------------------------------------------------------
# Absent JSON + absent parquet → RuntimeError (nothing to fall back to)
# ---------------------------------------------------------------------------

def test_absent_json_and_absent_parquet_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "_load_finviz_json", lambda: None)
    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cache_path = tmp_path / "russell_breadth" / "_closes_cache.parquet"
    adapter.cfg = {}  # _repair() reads cfg.ticker_fixups; runtime __init__ always sets it

    with pytest.raises(RuntimeError, match="absent/unusable"):
        adapter.constituents()


# ---------------------------------------------------------------------------
# constituents_checked: raises when below floor
# ---------------------------------------------------------------------------

def test_constituents_checked_raises_below_floor():
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    small = pd.DataFrame({"symbol": [f"T{i}" for i in range(_CONSTITUENTS_FLOOR - 1)],
                          "name": ["X"] * (_CONSTITUENTS_FLOOR - 1),
                          "sector": ["Tech"] * (_CONSTITUENTS_FLOOR - 1)})
    with pytest.raises(ValueError, match="suspicious"):
        adapter.constituents_checked(small)


def test_constituents_checked_passes_above_floor():
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    ok = pd.DataFrame({"symbol": [f"T{i}" for i in range(_CONSTITUENTS_FLOOR)],
                       "name": ["X"] * _CONSTITUENTS_FLOOR,
                       "sector": ["Tech"] * _CONSTITUENTS_FLOOR})
    assert len(adapter.constituents_checked(ok)) == _CONSTITUENTS_FLOOR


# ---------------------------------------------------------------------------
# compute(): rows with n_members < _N_REPORTING_FLOOR are dropped
# ---------------------------------------------------------------------------

def test_compute_drops_rows_below_n_reporting_floor():
    """compute() must drop days with n_members < 1200 (data-gap filter)."""
    from collectors.breadth import BreadthAdapter

    # Build a minimal closes DataFrame with enough rows for the rolling MA
    # window (need ≥200 rows for min_periods=200) plus a few "thin" rows
    n_tickers = _N_REPORTING_FLOOR + 100   # 1300 tickers total
    dates = pd.date_range("2025-01-01", periods=220, freq="B")
    rng = pd.RangeIndex(n_tickers)
    closes = pd.DataFrame(
        {f"T{i}": [10.0 + i * 0.01 + d * 0.001 for d in range(len(dates))]
         for i in range(n_tickers)},
        index=dates,
    )
    # Force the FINAL 5 days below the floor: only 900 tickers report (< 1200).
    # These rows MUST be dropped by the n_members filter — the load-bearing case.
    import numpy as np
    closes.iloc[-5:, 900:] = np.nan

    # Patch in a minimal cfg so the base class compute() can read ma_windows etc.
    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cfg = {"ma_windows": [50, 200], "nhnl_window": 252}

    # Run compute (no network, pure math)
    out = adapter.compute(closes)

    # The thin final rows (n_members=900) must be gone; earlier full rows survive.
    assert not out.empty, "full-coverage rows must survive the floor"
    assert (out["n_members"] >= _N_REPORTING_FLOOR).all(), (
        f"compute() left rows below n_members floor {_N_REPORTING_FLOOR}: "
        f"min={out['n_members'].min()}"
    )
    assert out.index.max() < dates[-5], "thin trailing rows were not dropped"


# ---------------------------------------------------------------------------
# _download_closes chunking: batch_size is overridden to 250
# ---------------------------------------------------------------------------

def test_download_closes_uses_chunk_size_250(monkeypatch):
    """_download_closes must pass batch_size=250 to the super() call."""
    from collectors.russell_breadth import _CHUNK_SIZE

    captured_batch_sizes = []

    def fake_download_closes(self_inner, tickers, period):
        captured_batch_sizes.append(self_inner.ycfg.get("batch_size"))
        # Return a minimal DataFrame so the caller doesn't fail
        return pd.DataFrame(
            {"T0000": [10.0, 11.0, 12.0]},
            index=pd.date_range("2025-01-02", periods=3, freq="B"),
        )

    from collectors import breadth as breadth_mod
    monkeypatch.setattr(breadth_mod.BreadthAdapter, "_download_closes", fake_download_closes)

    adapter = RussellBreadthAdapter.__new__(RussellBreadthAdapter)
    adapter.cfg = {"ma_windows": [50, 200], "nhnl_window": 252, "lookback_days_live": 730}
    adapter.ycfg = {"batch_size": 80, "retries": 3, "backoff_base_s": 5}

    _ = adapter._download_closes(["T0000"], "2y")

    assert len(captured_batch_sizes) == 1
    assert captured_batch_sizes[0] == _CHUNK_SIZE, (
        f"Expected batch_size={_CHUNK_SIZE}, got {captured_batch_sizes[0]}"
    )


# ---------------------------------------------------------------------------
# engine.universe_history.GROUPS includes "russell_breadth": "r2000"
# ---------------------------------------------------------------------------

def test_groups_contains_r2000():
    from engine.universe_history import GROUPS
    assert "russell_breadth" in GROUPS, (
        "GROUPS dict must contain 'russell_breadth' key"
    )
    assert GROUPS["russell_breadth"] == "r2000", (
        f"Expected GROUPS['russell_breadth']='r2000', got {GROUPS['russell_breadth']!r}"
    )


# ---------------------------------------------------------------------------
# scripts.collect.all_adapters() registers RussellBreadthAdapter
# ---------------------------------------------------------------------------

def test_collect_registers_russell_breadth():
    from scripts.collect import all_adapters
    registry = all_adapters()
    assert "russell_breadth" in registry, (
        "all_adapters() must register 'russell_breadth'"
    )
    from collectors.russell_breadth import RussellBreadthAdapter
    assert registry["russell_breadth"] is RussellBreadthAdapter
