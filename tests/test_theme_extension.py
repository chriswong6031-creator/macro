"""Tests for engine.theme_extension (per-theme ATR extension, display-only)."""
import numpy as np
import pandas as pd
import pytest

from engine import theme_extension as tx


def _series(vals, start="2019-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, dtype=float)


def test_atr_ext_sign():
    # steadily rising series -> price well above its 50d MA -> positive extension
    rising = _series([100 + i for i in range(120)])
    assert tx._atr_ext(rising) > 0
    # steadily falling -> below MA -> negative
    falling = _series([300 - i for i in range(120)])
    assert tx._atr_ext(falling) < 0
    # too short -> None
    assert tx._atr_ext(_series([100.0] * 10)) is None


def test_band_thresholds():
    assert tx._band(6.0)[0] == "parabolic"
    assert tx._band(4.0)[0] == "stretched"
    assert tx._band(2.0)[0] == "extended"
    assert tx._band(0.0)[0] == "normal"
    assert tx._band(-3.0)[0] == "washed out"
    assert tx._band(None)[0] == "—"


def test_mt_tolerant():
    assert tx._mt({"ticker": "AAPL"}) == "AAPL"
    assert tx._mt({"symbol": "MSFT"}) == "MSFT"


@pytest.mark.parametrize("region", ["us", "cn", "hk", "ca"])
def test_compute_region_smoke(region):
    """Region-aware compute against the worktree caches; skip a region with no cache."""
    out = tx.compute_theme_extension(region)
    if out is None:
        pytest.skip(f"no {region} baskets cache present")
    assert out["region"] in (region, "us")
    assert out["themes"] and "atr_ext" in out["themes"][0]
    # sorted descending by headline extension
    exts = [t["atr_ext"] for t in out["themes"] if t["atr_ext"] is not None]
    assert exts == sorted(exts, reverse=True)
