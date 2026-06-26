"""S&P 500 sector treemap heatmap compute (engine/sp500_heatmap.py).

Pins the return maths (1D / rolling-window / MTD / YTD anchors, holiday-safe
reference lookback), the offline market-cap proxy (cross-sector scaling +
per-sector floor), the live-snapshot splice (fresher 1D + after-hours), and the
load-bearing contract invariants the frontend depends on: a stable timeframe
catalogue, per-timeframe `available` flags, and graceful empty handling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import sp500_heatmap as hm


# ---- fixtures ---------------------------------------------------------------
def _closes() -> pd.DataFrame:
    """~14 months of daily closes for three names so every daily window resolves."""
    idx = pd.bdate_range("2025-04-01", "2026-06-22")
    n = len(idx)
    # AAA: smooth +0.1%/day ramp; BBB: flat 100; CCC: has a NaN gap early
    aaa = 100.0 * (1.001 ** np.arange(n))
    bbb = np.full(n, 100.0)
    ccc = np.linspace(50.0, 80.0, n)
    df = pd.DataFrame({"AAA": aaa, "BBB": bbb, "CCC": ccc}, index=idx)
    df.loc[df.index[:3], "CCC"] = np.nan  # leading gap
    return df


def _constituents() -> pd.DataFrame:
    return pd.DataFrame(
        {"name": ["Alpha", "Beta", "Gamma"], "sector":
            ["Information Technology", "Information Technology", "Financials"]},
        index=pd.Index(["AAA", "BBB", "CCC"], name="symbol"),
    )


# ---- _pct -------------------------------------------------------------------
def test_pct_basic_and_edges():
    assert hm._pct(110, 100) == 10.0
    assert hm._pct(90, 100) == -10.0
    assert hm._pct(100, 0) is None        # zero reference
    assert hm._pct(None, 100) is None
    assert hm._pct(100, float("nan")) is None


# ---- daily_returns ----------------------------------------------------------
def test_daily_returns_windows():
    df = _closes()
    out = hm.daily_returns(df)
    assert "AAA" in out and "BBB" in out
    # BBB is flat -> every window is exactly 0
    for k in ("1D", "1W", "1M", "3M", "6M", "1Y", "MTD", "YTD"):
        assert out["BBB"][k] == 0.0
    # AAA rises every day -> every positive-lookback window is > 0, longer = larger
    a = out["AAA"]
    assert a["1D"] > 0 and a["1W"] > a["1D"] and a["1Y"] > a["3M"] > a["1M"]


def test_daily_returns_holiday_safe_reference():
    # a target lookback landing on a weekend must fall back to the last close
    df = _closes()
    out = hm.daily_returns(df)
    # 1Y must resolve for CCC even though its first rows are NaN
    assert "1Y" in out["CCC"]
    assert np.isfinite(out["CCC"]["1Y"])


def test_daily_returns_empty():
    assert hm.daily_returns(pd.DataFrame()) == {}


# ---- intraday_returns -------------------------------------------------------
def test_intraday_returns_from_hourly_bars():
    closes = [100, 101, 102, 103, 104, 105]   # 6 hourly bars
    df = pd.DataFrame({"close": closes})
    out = hm.intraday_returns({"AAA": df})
    assert out["AAA"]["1H"] == hm._pct(105, 104)
    assert out["AAA"]["2H"] == hm._pct(105, 103)
    assert out["AAA"]["4H"] == hm._pct(105, 101)
    # too few bars -> no keys
    assert hm.intraday_returns({"X": pd.DataFrame({"close": [100]})}) == {}


# ---- proxy sizing -----------------------------------------------------------
def test_proxy_sizes_scale_across_sectors_and_floor_missing():
    rows = [
        {"t": "AAA", "sector": "Information Technology"},
        {"t": "BBB", "sector": "Information Technology"},
        {"t": "CCC", "sector": "Financials"},
    ]
    weights = {"AAA": 30.0, "BBB": 10.0}   # CCC missing -> floored
    sizes = hm._proxy_sizes(rows, weights)
    it_total = sizes["AAA"] + sizes["BBB"]
    # IT block should dwarf Financials (32 vs 13.5 canonical weight) and each
    # sector's tiles sum to that sector's index weight.
    assert it_total > sizes["CCC"]
    assert abs(it_total - hm._SECTOR_INDEX_WEIGHT["Information Technology"]) < 1e-6
    assert sizes["AAA"] > sizes["BBB"] > 0     # higher within-sector weight -> bigger


# ---- build_heatmap ----------------------------------------------------------
def test_build_heatmap_contract():
    payload = hm.build_heatmap(
        _constituents(), _closes(),
        industry_map={"AAA": {"sub_industry": "Semiconductors"}},
        weights_in_sector={"AAA": 30.0, "BBB": 10.0},
    )
    assert payload["n_tiles"] == 3
    assert payload["source"] == "daily-close"
    # timeframe catalogue is stable + daily windows flagged available, intraday not
    keys = [t["key"] for t in payload["timeframes"]]
    assert keys == [t["key"] for t in hm.TIMEFRAMES]
    avail = {t["key"]: t["available"] for t in payload["timeframes"]}
    assert avail["1D"] and avail["1Y"] and not avail["5M"] and not avail["AH"]
    # industry map applied; missing names fall back to the sector
    by = {t["t"]: t for t in payload["tiles"]}
    assert by["AAA"]["industry"] == "Semiconductors"
    assert by["BBB"]["industry"] == "Information Technology"
    # sizes present and positive
    assert all(t["size"] > 0 for t in payload["tiles"])


def test_build_heatmap_live_splice_overrides_1d_and_after_hours():
    # after-hours on a MAJORITY of names so it clears the coverage gate
    payload = hm.build_heatmap(
        _constituents(), _closes(),
        weights_in_sector={"AAA": 30.0, "BBB": 10.0},
        live={
            "AAA": {"price": 110.0, "prev_close": 100.0, "after_hours": 111.1},
            "BBB": {"price": 101.0, "prev_close": 100.0, "after_hours": 100.5},
        },
    )
    assert payload["source"] == "polygon-live"
    aaa = next(t for t in payload["tiles"] if t["t"] == "AAA")
    assert aaa["perf"]["1D"] == 10.0                      # 110 vs prev 100
    assert aaa["perf"]["AH"] == hm._pct(111.1, 110.0)     # after-hours vs last
    # after-hours timeframe should now clear the coverage gate (2 of 3 names)
    avail = {t["key"]: t["available"] for t in payload["timeframes"]}
    assert avail["AH"]


def test_coverage_gate_hides_thinly_covered_timeframe():
    # only 1 of 3 names has an after-hours print -> below MIN_COVERAGE -> hidden
    payload = hm.build_heatmap(
        _constituents(), _closes(),
        weights_in_sector={"AAA": 30.0, "BBB": 10.0},
        live={"AAA": {"price": 110.0, "prev_close": 100.0, "after_hours": 111.1}},
    )
    avail = {t["key"]: t["available"] for t in payload["timeframes"]}
    assert not avail["AH"]
    assert avail["1D"]   # 1D still computed for all names from closes


def test_build_heatmap_empty_inputs():
    payload = hm.build_heatmap(pd.DataFrame(), pd.DataFrame())
    assert payload["n_tiles"] == 0
    assert payload["tiles"] == []
    assert [t["key"] for t in payload["timeframes"]] == [t["key"] for t in hm.TIMEFRAMES]
    assert all(not t["available"] for t in payload["timeframes"])


# ---- catalogue invariants ---------------------------------------------------
def test_timeframe_catalogue_stable():
    assert len(hm.TIMEFRAMES) == 16
    keys = [t["key"] for t in hm.TIMEFRAMES]
    assert len(set(keys)) == len(keys)                    # unique
    assert hm.DEFAULT_TIMEFRAME in keys
    for tf in hm.TIMEFRAMES:
        assert {"key", "en", "zh", "group"} <= set(tf)    # full metadata
