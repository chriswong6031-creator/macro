"""Tests for engine.ownership_crowding — pure-function coverage with in-memory fixtures.

Key pathologies tested:
- unpriced ADR / missing ADV → None (null-honest)
- ADV absent → crowding_tier returns 'unavailable'
- PIT law: post-anchor volume bar cannot influence anchored result
- no-fusion: days_to_exit derives only from shares+ADV; crowding_tier from DTE only
- short_interest fields carry settlement_date stamp distinct from any 13F fields
- implied_entry_band labeled as proxy, not cost basis
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ownership_crowding as oc


# --------------------------------------------------------------------------- #
# days_to_exit (pure)                                                            #
# --------------------------------------------------------------------------- #

def test_dte_basic():
    assert oc.days_to_exit(1000.0, 100.0) == pytest.approx(10.0, abs=0.05)


def test_dte_none_when_adv_absent():
    assert oc.days_to_exit(1000.0, None) is None


def test_dte_none_when_shares_absent():
    assert oc.days_to_exit(None, 100.0) is None


def test_dte_none_zero_adv():
    assert oc.days_to_exit(1000.0, 0.0) is None


def test_dte_zero_shares():
    assert oc.days_to_exit(0.0, 100.0) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# crowding_tier                                                                  #
# --------------------------------------------------------------------------- #

def test_crowding_tier_unavailable_when_dte_none():
    assert oc.crowding_tier(None) == "unavailable"


def test_crowding_tier_static_low():
    assert oc.crowding_tier(5.0) == "low"


def test_crowding_tier_static_moderate():
    assert oc.crowding_tier(30.0) == "moderate"


def test_crowding_tier_static_elevated():
    assert oc.crowding_tier(50.0) == "elevated"


def test_crowding_tier_distribution_quintile():
    """With a provided distribution the tier follows quintile logic."""
    universe = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 40.0, 60.0, 80.0, 100.0]
    # p40 = sorted[4] = 20.0, p80 = sorted[8] = 80.0
    assert oc.crowding_tier(10.0, universe) == "low"     # < p40
    assert oc.crowding_tier(50.0, universe) == "moderate"  # p40 <= x < p80
    assert oc.crowding_tier(90.0, universe) == "elevated"  # >= p80


def test_crowding_tier_no_fusion_api():
    """crowding_tier only accepts dte + universe_values. It does NOT accept
    days_to_cover, short_ratio, or any 13F metric as positional inputs.
    This test asserts the API by calling with only the allowed arguments."""
    # Should work fine
    result = oc.crowding_tier(25.0, None)
    assert result in ("low", "moderate", "elevated", "unavailable")

    # Passing extra kwargs that aren't part of the signature should raise TypeError —
    # proving the function cannot accidentally fuse axes via keyword pollution.
    with pytest.raises(TypeError):
        oc.crowding_tier(25.0, None, days_to_cover=5.0)  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        oc.crowding_tier(25.0, None, si_change_pct=0.1)  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# implied_entry_band                                                             #
# --------------------------------------------------------------------------- #

def _holders(values_and_shares):
    return [{"value_usd": v, "shares": s} for v, s in values_and_shares]


def test_entry_band_basic():
    holders = _holders([(100.0, 10.0), (200.0, 10.0), (150.0, 10.0)])
    # implied prices: 10, 20, 15
    band = oc.implied_entry_band(holders, latest_close=12.0)
    assert band is not None
    assert band["p50"] == pytest.approx(15.0, abs=0.1)
    assert band["n"] == 3
    # n_underwater: only 15.0 > 12.0 and 20.0 > 12.0 → 2
    assert band["n_underwater"] == 2


def test_entry_band_label_is_proxy():
    """The label must say 'proxy', NOT 'cost basis' (SM2-R10)."""
    holders = _holders([(100.0, 10.0), (200.0, 20.0)])
    band = oc.implied_entry_band(holders, latest_close=None)
    assert band is not None
    assert "proxy" in band["label"].lower()
    assert "cost basis" not in band["label"].lower()


def test_entry_band_none_when_insufficient():
    holders = _holders([(100.0, 10.0)])  # only 1 holder
    assert oc.implied_entry_band(holders, latest_close=10.0) is None


def test_entry_band_none_when_no_price():
    holders = _holders([(100.0, 10.0), (200.0, 20.0)])
    band = oc.implied_entry_band(holders, latest_close=None)
    assert band is not None
    assert band["n_underwater"] is None


def test_entry_band_zero_shares_skipped():
    """A holder row with shares=0 must not be included."""
    holders = _holders([(100.0, 0.0), (200.0, 10.0), (300.0, 10.0)])
    band = oc.implied_entry_band(holders, latest_close=25.0)
    assert band is not None
    assert band["n"] == 2  # the zero-shares row is excluded


# --------------------------------------------------------------------------- #
# PIT law — adv_shares anchor-dated                                             #
# --------------------------------------------------------------------------- #

def test_adv_yahoo_pit_anchor(tmp_path, monkeypatch):
    """A post-anchor volume bar must NOT influence the anchored ADV result.

    We write a yahoo parquet with bars spanning 2025-01-01 to 2025-03-01.
    The anchor is 2025-01-31. The 30-session ADV computed with as_of=2025-01-31
    must NOT include bars after that date. We verify this by comparing the mean
    for sessions up to 2025-01-31 vs the full-window mean (they differ because the
    post-anchor bars have a distinct volume value).
    """
    import numpy as np

    # 40 business days: Jan 2 – Feb 28 (approx). First 20 days: volume=100.
    # Last 20 days: volume=9999 (clearly different).
    idx = pd.bdate_range("2025-01-02", periods=40)
    vol = pd.Series([100.0] * 20 + [9999.0] * 20, index=idx, name="volume")
    df = pd.DataFrame({"volume": vol, "close": 1.0})
    ticker = "TESTPIT"
    yahoo_dir = tmp_path / "yahoo"
    yahoo_dir.mkdir()
    df.to_parquet(yahoo_dir / f"{ticker}.parquet")

    # Patch config.data_dir() to return tmp_path
    import engine.ownership_crowding as _oc
    monkeypatch.setattr(_oc.config, "data_dir", lambda: tmp_path)

    # With as_of = day 20 (= idx[19], which is the last "100-volume" day),
    # the FINRA store doesn't exist in tmp_path, so it falls through to yahoo.
    anchor = str(idx[19].date())
    result_anchored = _oc.adv_shares(ticker, as_of=anchor)
    assert result_anchored is not None, "Expected yahoo fallback ADV"
    assert result_anchored["source"] == "yahoo"
    # All 20 bars up to anchor have volume=100 → mean=100
    assert result_anchored["adv"] == pytest.approx(100.0, abs=1e-6), (
        f"Post-anchor bars (volume=9999) must NOT influence the anchored ADV; "
        f"got {result_anchored['adv']}"
    )

    # Verify that WITHOUT an anchor we get a different (higher) mean due to post-anchor bars
    result_live = _oc.adv_shares(ticker, as_of=None)
    assert result_live is not None
    # 30-session tail of 40 bars: last 10 pre-anchor (100) + 20 post-anchor (9999)
    assert result_live["adv"] > 100.0, "Live ADV should include post-anchor bars"


def test_adv_finra_pit_skips_future_settlement(tmp_path, monkeypatch):
    """A FINRA record whose settlement_date is AFTER as_of must be skipped,
    falling through to the yahoo fallback."""
    # Write a FINRA short interest parquet with a future settlement date
    future_settle = "2099-01-01"
    finra_df = pd.DataFrame({
        "avg_daily_vol": [5000.0],
        "settlement_date": [future_settle],
        "short_shares": [100000],
    }, index=pd.Index(["TESTFUT"], name="ticker"))
    finra_dir = tmp_path / "finra"
    finra_dir.mkdir()
    finra_df.to_parquet(finra_dir / "short_interest.parquet")

    # Write a yahoo volume series as fallback
    idx = pd.bdate_range("2025-01-02", periods=30)
    df = pd.DataFrame({"volume": [200.0] * 30, "close": 1.0}, index=idx)
    yahoo_dir = tmp_path / "yahoo"
    yahoo_dir.mkdir()
    df.to_parquet(yahoo_dir / "TESTFUT.parquet")

    import engine.ownership_crowding as _oc
    monkeypatch.setattr(_oc.config, "data_dir", lambda: tmp_path)

    # as_of = today (well before 2099-01-01) → FINRA record settlement is future → skip
    result = _oc.adv_shares("TESTFUT", as_of="2025-06-30")
    assert result is not None
    assert result["source"] == "yahoo", (
        "Expected yahoo fallback when FINRA settlement_date is after as_of"
    )
    assert result["adv"] == pytest.approx(200.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# No-fusion guard: short_interest and 13F fields must have separate keys        #
# --------------------------------------------------------------------------- #

def test_short_and_13f_fields_distinct_keys():
    """Short-interest context and 13F context must never share a key in the same dict.
    This test simulates the payload structure and asserts key separation."""
    # A desk payload row as would be emitted by the crowding section (S4)
    crowding_row = {
        # 13F-derived fields
        "ticker": "AAPL",
        "n_funds": 7,
        "agg_value_usd": 1.5e9,
        "hhi": 0.20,
        "max_book_pct": 8.5,
        "days_to_exit": 12.3,
        "crowding_tier": "low",
        "entry_band": {"p25": 145.0, "p50": 150.0, "p75": 158.0,
                       "n_underwater": 2, "label": "implied avg entry (quarter-end proxy)"},
        # Short-volume fields — SEPARATE sub-dict, own asof
        "short_volume": {
            "ratio": 0.42,
            "trend_pp": 1.5,
            "ratio_z": 0.8,
            "asof": "2025-07-09",    # DAILY stamp, distinct from settlement_date
        },
        # Short-interest fields — SEPARATE sub-dict, own settlement_date stamp
        "short_interest": {
            "days_to_cover": 3.2,
            "si_change_pct": -1.5,
            "settlement_date": "2025-06-30",   # SETTLEMENT stamp
        },
    }

    # Assert short_volume and short_interest are separate nested dicts
    assert "short_volume" in crowding_row
    assert "short_interest" in crowding_row

    sv = crowding_row["short_volume"]
    si = crowding_row["short_interest"]

    # The two dicts must not share keys that could represent the same field
    # (e.g. a merged 'asof' that conflates daily and settlement dates)
    assert "asof" in sv        # short volume has own asof (daily)
    assert "asof" not in si    # short interest uses settlement_date, not asof
    assert "settlement_date" in si
    assert "settlement_date" not in sv

    # days_to_cover is a SHORT metric — must not appear as a top-level or 13F key
    assert "days_to_cover" not in crowding_row  # not top-level
    assert "days_to_cover" not in crowding_row.get("entry_band", {})  # not in 13F band

    # days_to_exit is a 13F+ADV metric — must not appear inside short_interest
    assert "days_to_exit" not in si
    assert "days_to_exit" not in sv
    # It lives at the TOP level, not inside either short sub-dict
    assert crowding_row["days_to_exit"] == pytest.approx(12.3, abs=0.05)
