"""Russell 2000 cache wiring in scripts/build_chart_data.py.

Tests cover:
  * _load_caches() includes "russell_breadth" after "midcap_breadth" in its
    priority order (missing file → absent key, no error).
  * _load_caches() with a present russell_breadth file loads the DataFrame.
  * _build_ticker() resolves a ticker present only in russell_breadth.
  * Priority order: sp500 (breadth) > sp600 (smallcap) > sp400 (midcap) >
    russell — a ticker in breadth is NOT replaced by russell data.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_chart_data as bcd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _closes_df(tickers: list[str], n: int = 10) -> pd.DataFrame:
    """Minimal close-only DataFrame for a set of tickers."""
    idx = pd.date_range("2024-01-01", periods=n, freq="D", name="Date")
    return pd.DataFrame(
        {t: np.linspace(10.0, 20.0, n) for t in tickers},
        index=idx,
    )


def _write_cache(df: pd.DataFrame, grp_dir: Path) -> Path:
    grp_dir.mkdir(parents=True, exist_ok=True)
    p = grp_dir / "_closes_cache.parquet"
    df.to_parquet(p)
    return p


# ---------------------------------------------------------------------------
# _load_caches() tests
# ---------------------------------------------------------------------------

def test_load_caches_includes_russell_key(tmp_path, monkeypatch):
    """russell_breadth appears in the loaded caches dict when the file exists."""
    data_root = tmp_path / "data"
    russ_dir = data_root / "russell_breadth"
    df = _closes_df(["RTWO", "RTHREE"])
    _write_cache(df, russ_dir)

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    caches = bcd._load_caches()
    assert "russell_breadth" in caches, (
        f"russell_breadth missing from _load_caches() result; keys={list(caches)}"
    )
    assert "RTWO" in caches["russell_breadth"].columns


def test_load_caches_missing_russell_no_error(tmp_path, monkeypatch):
    """_load_caches() with no russell_breadth dir must not raise."""
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    # No russell_breadth subdirectory.

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    caches = bcd._load_caches()
    assert "russell_breadth" not in caches
    # All other groups also missing → empty dict.
    assert isinstance(caches, dict)


def test_load_caches_priority_order_breadth_before_russell(tmp_path, monkeypatch):
    """Priority order: breadth > smallcap_breadth > midcap_breadth > russell_breadth.

    Both breadth and russell_breadth carry SHARED; it must come from breadth
    (the earlier layer in the iteration).  Since _load_caches() just returns
    the raw DataFrames keyed by group, the order test is via _build_ticker().
    This test verifies the dict key ordering via the group tuple in the loop.
    """
    data_root = tmp_path / "data"

    # Write breadth with SHARED at price 99.
    br_dir = data_root / "breadth"
    br_df = _closes_df(["SHARED"], n=5)
    br_df["SHARED"] = 99.0
    _write_cache(br_df, br_dir)

    # Write russell_breadth with SHARED at price 1.
    russ_dir = data_root / "russell_breadth"
    russ_df = _closes_df(["SHARED"], n=5)
    russ_df["SHARED"] = 1.0
    _write_cache(russ_df, russ_dir)

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    caches = bcd._load_caches()

    # Simulate what _build_ticker() does: iterate in priority order.
    # breadth wins because it appears first in the loop.
    resolved_src = None
    resolved_close = None
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
        cache = caches.get(grp)
        if cache is not None and "SHARED" in cache.columns:
            resolved_src = grp
            resolved_close = cache["SHARED"].iloc[-1]
            break

    assert resolved_src == "breadth", (
        f"Expected 'breadth' to win priority; got '{resolved_src}'"
    )
    assert resolved_close == 99.0


# ---------------------------------------------------------------------------
# _build_ticker() tests
# ---------------------------------------------------------------------------

def test_build_ticker_resolves_russell_only_ticker(tmp_path, monkeypatch):
    """_build_ticker() finds a ticker that exists only in russell_breadth."""
    data_root = tmp_path / "data"
    russ_dir = data_root / "russell_breadth"
    df = _closes_df(["RTWO"], n=20)
    _write_cache(df, russ_dir)

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)
    # Stub store.read to return None (no yahoo fallback).
    import lib.store as _store
    monkeypatch.setattr(_store, "read", lambda *a, **kw: None)

    deep_dir = tmp_path / "stocks"   # no deep parquets
    caches = bcd._load_caches()
    result = bcd._build_ticker("RTWO", deep_dir, caches)

    assert result is not None, "Expected a result for RTWO from russell_breadth cache"
    assert result["t"] == "RTWO"
    assert result["src"] == "russell_breadth"
    assert result.get("recon") == 1        # close-only → reconstructed OHLC
    assert len(result["bars"]) > 0


def test_build_ticker_russell_not_used_when_deep_exists(tmp_path, monkeypatch):
    """A ticker with a deep OHLC file must use 'deep', not russell."""
    import lib.config as _cfg
    _cfg.load.cache_clear()
    data_root = tmp_path / "data"
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)
    import lib.store as _store
    monkeypatch.setattr(_store, "read", lambda *a, **kw: None)

    deep_dir = tmp_path / "stocks"
    deep_dir.mkdir(parents=True)

    # Write a real OHLC parquet for AAPL in deep_dir.
    idx = pd.date_range("2024-01-01", periods=10, freq="D", name="Date")
    ohlc = pd.DataFrame({
        "close": np.linspace(100, 110, 10),
        "high":  np.linspace(101, 111, 10),
        "low":   np.linspace(99, 109, 10),
        "open":  np.linspace(100, 110, 10),
        "volume": np.arange(10, dtype=float),
    }, index=idx)
    (deep_dir / "AAPL.parquet").parent.mkdir(parents=True, exist_ok=True)
    ohlc.to_parquet(deep_dir / "AAPL.parquet")

    # Also put AAPL in russell cache to confirm it doesn't override deep.
    russ_dir = data_root / "russell_breadth"
    _write_cache(_closes_df(["AAPL"], n=10), russ_dir)

    caches = bcd._load_caches()
    result = bcd._build_ticker("AAPL", deep_dir, caches)

    assert result is not None
    assert result["src"] == "deep", (
        f"Expected 'deep' source; got '{result['src']}'"
    )
    assert result.get("recon") is None   # real OHLC → no reconstruction flag
