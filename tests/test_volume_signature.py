"""Deterministic tests for engine.volume_signature (accumulation/distribution lens).

Primary tests use synthetic in-memory frames and mock store.read so the suite runs
without any data files. The live-data smoke test is guarded: it skips if the data
store is unavailable or returns empty.

directional:false — these tests verify the descriptive math, not forward-return alpha.
"""
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.volume_signature as vs  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _bdate(n: int, start: str = "2023-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _px_frame(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    idx = _bdate(len(closes))
    return pd.DataFrame({"close": closes, "volume": volumes}, index=idx)


# --------------------------------------------------------------------------- #
# _obv_slope
# --------------------------------------------------------------------------- #
def test_obv_slope_rising_volume_on_up_days_gives_positive_slope():
    n = 60
    idx = _bdate(n)
    # Price rises every day; volume on up-days is high -> OBV always rising
    close = pd.Series(np.linspace(100, 120, n), index=idx)
    volume = pd.Series([1_000_000.0] * n, index=idx)
    slope = vs._obv_slope(close, volume, slope_d=20)
    assert slope is not None
    assert slope > 0


def test_obv_slope_falling_price_gives_negative_slope():
    n = 60
    idx = _bdate(n)
    close = pd.Series(np.linspace(120, 100, n), index=idx)
    volume = pd.Series([1_000_000.0] * n, index=idx)
    slope = vs._obv_slope(close, volume, slope_d=20)
    assert slope is not None
    assert slope < 0


def test_obv_slope_returns_none_on_insufficient_history():
    idx = _bdate(5)
    close = pd.Series([100.0] * 5, index=idx)
    volume = pd.Series([500_000.0] * 5, index=idx)
    result = vs._obv_slope(close, volume, slope_d=20)
    assert result is None


# --------------------------------------------------------------------------- #
# _member_signature
# --------------------------------------------------------------------------- #
def _make_store_px(closes, volumes):
    frame = _px_frame(closes, volumes)
    return frame


def test_member_signature_accumulation():
    n = 60
    # Zigzag price that trends up but has plenty of down days to avoid zero down_vol.
    # Volume is 4x higher on up-days than down-days -> ad_ratio > 1.
    rng = np.random.default_rng(42)
    # build a price series with ~60 % up days
    daily = [0.01 if rng.random() > 0.4 else -0.005 for _ in range(n)]
    closes = [100.0]
    for d in daily[:-1]:
        closes.append(closes[-1] * (1 + d))
    volumes = []
    for i in range(n):
        if i == 0:
            volumes.append(1_000_000.0)
        else:
            volumes.append(2_000_000.0 if closes[i] > closes[i - 1] else 500_000.0)
    px = _make_store_px(closes, volumes)
    with mock.patch("engine.volume_signature.store") as mock_store:
        mock_store.read.return_value = px
        result = vs._member_signature("AAPL", lookback_d=42, obv_slope_d=20)
    assert result is not None
    assert result["ad_ratio"] is not None
    assert result["up_vol"] > result["down_vol"]
    assert result["ad_ratio"] > 1.0


def test_member_signature_distribution():
    n = 60
    # Steady downtrend — price falls every day; volume on down-days is high
    closes = [120.0 - i * 0.5 for i in range(n)]
    volumes = [500_000.0 if i % 2 == 0 else 2_000_000.0 for i in range(n)]
    px = _make_store_px(closes, volumes)
    with mock.patch("engine.volume_signature.store") as mock_store:
        mock_store.read.return_value = px
        result = vs._member_signature("MSFT", lookback_d=42, obv_slope_d=20)
    assert result is not None
    # down-days carry more volume in the downtrend window
    assert result["down_vol"] > result["up_vol"]
    assert result["ad_ratio"] is not None and result["ad_ratio"] < 1.0


def test_member_signature_missing_volume_col_returns_none():
    idx = _bdate(60)
    px = pd.DataFrame({"close": [100.0] * 60}, index=idx)
    with mock.patch("engine.volume_signature.store") as mock_store:
        mock_store.read.return_value = px
        assert vs._member_signature("TSLA", 42, 20) is None


def test_member_signature_none_store_returns_none():
    with mock.patch("engine.volume_signature.store") as mock_store:
        mock_store.read.return_value = None
        assert vs._member_signature("NVDA", 42, 20) is None


def test_member_signature_too_short_returns_none():
    # Only 10 rows — below lookback_d=42
    closes = [100.0] * 10
    volumes = [1_000_000.0] * 10
    px = _make_store_px(closes, volumes)
    with mock.patch("engine.volume_signature.store") as mock_store:
        mock_store.read.return_value = px
        assert vs._member_signature("GOOG", lookback_d=42, obv_slope_d=20) is None


# --------------------------------------------------------------------------- #
# _basket_agg
# --------------------------------------------------------------------------- #
def test_basket_agg_accumulation_majority():
    rows = [
        {"ticker": "A", "ad_ratio": 1.25, "obv_slope": 0.002, "up_vol": 1000, "down_vol": 800, "signature": "accumulation"},
        {"ticker": "B", "ad_ratio": 1.15, "obv_slope": 0.001, "up_vol": 900, "down_vol": 700, "signature": "accumulation"},
        {"ticker": "C", "ad_ratio": 0.95, "obv_slope": -0.001, "up_vol": 700, "down_vol": 750, "signature": "neutral"},
    ]
    result = vs._basket_agg(rows)
    assert result["n"] == 3
    assert result["pct_accumulation"] == pytest.approx(2 / 3, abs=0.01)
    # median ad_ratio > 1.1 and pct_acc >= 0.4 -> basket = accumulation
    assert result["signature"] == "accumulation"
    assert result["ad_ratio"] is not None


def test_basket_agg_distribution_majority():
    rows = [
        {"ticker": "X", "ad_ratio": 0.82, "obv_slope": -0.003, "up_vol": 600, "down_vol": 900, "signature": "distribution"},
        {"ticker": "Y", "ad_ratio": 0.85, "obv_slope": -0.002, "up_vol": 700, "down_vol": 900, "signature": "distribution"},
        {"ticker": "Z", "ad_ratio": 1.02, "obv_slope": 0.001, "up_vol": 850, "down_vol": 840, "signature": "neutral"},
    ]
    result = vs._basket_agg(rows)
    assert result["pct_distribution"] == pytest.approx(2 / 3, abs=0.01)
    assert result["signature"] == "distribution"


def test_basket_agg_neutral_mixed():
    rows = [
        {"ticker": "A", "ad_ratio": 1.0, "obv_slope": 0.0, "up_vol": 800, "down_vol": 800, "signature": "neutral"},
        {"ticker": "B", "ad_ratio": 1.05, "obv_slope": 0.0, "up_vol": 820, "down_vol": 780, "signature": "neutral"},
    ]
    result = vs._basket_agg(rows)
    assert result["signature"] == "neutral"


def test_basket_agg_empty_returns_neutral():
    result = vs._basket_agg([])
    assert result["signature"] == "neutral"
    assert result["n"] == 0
    assert result["ad_ratio"] is None


# --------------------------------------------------------------------------- #
# volume_signature (public API) — fully mocked
# --------------------------------------------------------------------------- #
def _fake_membership():
    return {
        "baskets": {
            "ai_infra": {
                "id": "ai_infra",
                "name": "AI Infrastructure",
                "members": [
                    {"ticker": "NVDA", "added": "2021-01-01"},
                    {"ticker": "AMD", "added": "2021-01-01"},
                    {"ticker": "ANET", "added": "2021-01-01"},
                ],
            }
        }
    }


def _fake_closes():
    idx = _bdate(100)
    return pd.DataFrame(
        {"NVDA": np.linspace(100, 150, 100),
         "AMD": np.linspace(80, 110, 100),
         "ANET": np.linspace(60, 80, 100)},
        index=idx,
    )


def _fake_px(n=100, trend="up"):
    idx = _bdate(n)
    if trend == "up":
        c = np.linspace(100, 130, n)
        v = [2_000_000.0 if i % 2 == 0 else 600_000.0 for i in range(n)]
    else:
        c = np.linspace(130, 100, n)
        v = [600_000.0 if i % 2 == 0 else 2_000_000.0 for i in range(n)]
    return pd.DataFrame({"close": c, "volume": v}, index=idx)


def test_volume_signature_returns_dict_keyed_by_theme():
    with (
        mock.patch("engine.volume_signature._membership", return_value=_fake_membership()),
        mock.patch("engine.volume_signature._closes", return_value=_fake_closes()),
        mock.patch("engine.volume_signature._basket_extras", return_value=None),
        mock.patch("engine.volume_signature.store") as mock_store,
    ):
        mock_store.read.return_value = _fake_px()
        result = vs.volume_signature(region="us", lookback_d=42, obv_slope_d=20)
    assert isinstance(result, dict)
    assert "ai_infra" in result
    r = result["ai_infra"]
    assert "ad_ratio" in r
    assert "pct_accumulation" in r
    assert "signature" in r
    assert r["signature"] in ("accumulation", "distribution", "neutral")
    assert "n" in r
    assert "members" in r


def test_volume_signature_non_us_returns_empty():
    result = vs.volume_signature(region="cn")
    assert result == {}


def test_volume_signature_no_membership_returns_empty():
    with mock.patch("engine.volume_signature._membership", return_value=None):
        result = vs.volume_signature(region="us")
    assert result == {}


def test_volume_signature_no_closes_returns_empty():
    with (
        mock.patch("engine.volume_signature._membership", return_value=_fake_membership()),
        mock.patch("engine.volume_signature._closes", return_value=None),
        mock.patch("engine.volume_signature._basket_extras", return_value=None),
    ):
        result = vs.volume_signature(region="us")
    assert result == {}


def test_volume_signature_member_exception_is_swallowed():
    """A member that raises in _member_signature must not kill the whole basket."""
    with (
        mock.patch("engine.volume_signature._membership", return_value=_fake_membership()),
        mock.patch("engine.volume_signature._closes", return_value=_fake_closes()),
        mock.patch("engine.volume_signature._basket_extras", return_value=None),
        mock.patch("engine.volume_signature._member_signature", side_effect=RuntimeError("boom")),
    ):
        result = vs.volume_signature(region="us", lookback_d=42, obv_slope_d=20)
    # Should return neutral for the basket (no members succeeded)
    assert "ai_infra" in result
    assert result["ai_infra"]["n"] == 0
    assert result["ai_infra"]["signature"] == "neutral"


# --------------------------------------------------------------------------- #
# Live-data smoke test (guarded)
# --------------------------------------------------------------------------- #
def test_live_us_smoke():
    """Call the real function against the on-disk data store.

    Skipped automatically if the data store is unavailable or returns no baskets.
    This is a presence/shape test — NOT a correctness assertion on live values."""
    try:
        from lib import config  # noqa: PLC0415
        data_dir = config.data_dir()
        if not (data_dir / "baskets" / "membership.json").exists():
            pytest.skip("baskets/membership.json not found — skipping live smoke test")
    except Exception:  # noqa: BLE001
        pytest.skip("lib.config unavailable — skipping live smoke test")

    result = vs.volume_signature(region="us", lookback_d=42, obv_slope_d=20)
    if not result:
        pytest.skip("volume_signature returned empty (no volume data in store yet)")

    for tid, val in result.items():
        assert "signature" in val, f"{tid}: missing 'signature'"
        assert val["signature"] in ("accumulation", "distribution", "neutral")
        assert "n" in val and isinstance(val["n"], int)
        assert "pct_accumulation" in val
        assert "members" in val
        if val["ad_ratio"] is not None:
            assert val["ad_ratio"] > 0, f"{tid}: ad_ratio must be positive"
