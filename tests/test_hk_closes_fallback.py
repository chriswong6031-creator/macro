"""HK close matrix must survive a missing runner-local breadth cache.

data/hk_breadth/_closes_cache.parquet is gitignored and ferried between CI runs via
actions/cache. 2026-07-18: the render-linux runner missed every restore (zstd
cache-version mismatch vs the macOS-saved entries), _closes_matrix() returned None,
signal_gate gated out all 156 names, and the live board shipped 0 buys for hours.
The committed deep panel (data/hk_search/closes_deep.parquet) must serve as the
fallback so a cache miss degrades to a one-session-stale tail, never an empty board.
"""
from unittest.mock import patch

import pandas as pd

from scripts.build_hk_library import _closes_matrix


def _deep_panel() -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-02", periods=120)
    return pd.DataFrame({"0700.HK": [100.0 + i for i in range(120)],
                         "9988.HK": [80.0 + i for i in range(120)]}, index=idx)


def test_falls_back_to_deep_when_cache_missing(tmp_path):
    (tmp_path / "hk_search").mkdir()
    _deep_panel().to_parquet(tmp_path / "hk_search" / "closes_deep.parquet")
    with patch("lib.config.data_dir", return_value=tmp_path):
        m = _closes_matrix()
    assert m is not None
    assert sorted(m.columns) == ["0700.HK", "9988.HK"]
    assert len(m) == 120
    assert isinstance(m.index, pd.DatetimeIndex)


def test_none_when_both_stores_missing(tmp_path):
    (tmp_path / "hk_search").mkdir()
    (tmp_path / "hk_breadth").mkdir()
    with patch("lib.config.data_dir", return_value=tmp_path):
        assert _closes_matrix() is None


def test_cache_still_wins_overlap_when_present(tmp_path):
    (tmp_path / "hk_search").mkdir()
    (tmp_path / "hk_breadth").mkdir()
    deep = _deep_panel()
    deep.to_parquet(tmp_path / "hk_search" / "closes_deep.parquet")
    (deep.tail(30) + 1000.0).to_parquet(tmp_path / "hk_breadth" / "_closes_cache.parquet")
    with patch("lib.config.data_dir", return_value=tmp_path):
        m = _closes_matrix()
    assert m.iloc[-1]["0700.HK"] > 1000.0   # cache rows win where present
    assert len(m) == 120                    # deep still extends the history back
