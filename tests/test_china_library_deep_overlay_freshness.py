"""Regression tests for China library deep-OHLC overlay freshness.

The broad china_search close panel can reach the settled mainland session before
Yahoo's per-name OHLC plane.  The deep overlay is an enrichment layer; it must
never replace a fresher cache close with an older deep series and thereby move
Prophet's board/session clock backward.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_china_library as bcl  # noqa: E402


def _close_series(end: str, n: int = 320) -> pd.Series:
    idx = pd.bdate_range(end=end, periods=n)
    return pd.Series(np.linspace(10.0, 20.0, n), index=idx)


def _deep_frame(end: str, n: int = 320) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=n)
    close = np.linspace(9.0, 19.0, n)
    return pd.DataFrame({"close": close, "high": close * 1.01}, index=idx)


def test_deep_overlay_never_regresses_fresher_cache_close(monkeypatch):
    cache_close = _close_series("2026-08-27")
    deep = _deep_frame("2026-08-26")
    monkeypatch.setattr(bcl.store, "read", lambda group, ticker: deep)

    universe = [("000001.SZ", cache_close, None, "Ping An", "Banks")]
    upgraded = bcl._overlay_deep_ohlc(universe, "china_stocks", min_rows=300)

    assert upgraded == 0
    assert universe[0][1].index.max() == cache_close.index.max()
    assert universe[0][2] is None


def test_deep_overlay_still_upgrades_when_equally_fresh(monkeypatch):
    cache_close = _close_series("2026-08-27")
    deep = _deep_frame("2026-08-27")
    monkeypatch.setattr(bcl.store, "read", lambda group, ticker: deep)

    universe = [("000001.SZ", cache_close, None, "Ping An", "Banks")]
    upgraded = bcl._overlay_deep_ohlc(universe, "china_stocks", min_rows=300)

    assert upgraded == 1
    assert universe[0][1].index.max() == deep.index.max()
    assert universe[0][2] is deep["high"]
