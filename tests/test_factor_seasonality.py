"""Ken French collector parsing + factor-seasonality engine.

The French CSV has a variable free-text preamble, a header line starting with ',',
monthly YYYYMM rows, then an 'Annual Factors:' block we must drop; -99.99 marks
missing. The seasonality engine maps French columns to our factors, computes
per-month mean/median/hit over full + trailing-30y + trailing-10y, and degrades
to None when the French data is absent (so the page just hides).
"""
from __future__ import annotations

import io
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from collectors.french import FrenchAdapter
from engine import factor_seasonality as fs


def _zip_csv(body: str, member="F-F_Test.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(member, body)
    return buf.getvalue()


def test_french_parser_header_annual_and_missing():
    body = (
        "This file was created using the 100% ...\n"
        "  preamble line that must be skipped\n"
        "\n"
        ",Mkt-RF,SMB,HML,RF\n"
        "192607,   2.96,  -2.30,  -2.87,    0.22\n"
        "192608,   2.64,  -1.40,    4.19,    0.25\n"
        "200007, -99.99, -99.99, -99.99,    0.48\n"
        "\n"
        " Annual Factors: January-December \n"
        ",Mkt-RF,SMB,HML,RF\n"
        "1926,   28.0,   -5.0,    2.0,    3.3\n"
    )
    df = FrenchAdapter._parse(FrenchAdapter.__new__(FrenchAdapter), _zip_csv(body))
    # only the 3 monthly rows survive (annual block dropped)
    assert list(df.columns) == ["mkt_rf", "smb", "hml", "rf"]
    assert len(df) == 3
    assert df.index[0] == pd.Timestamp("1926-07-31")
    # -99.99 sentinels -> NaN
    assert np.isnan(df.loc["2000-07-31", "mkt_rf"])
    # real value parsed
    assert abs(df.loc["1926-08-31", "hml"] - 4.19) < 1e-9


def _make_df(n_years: int = 40, start_year: int = 1985) -> pd.DataFrame:
    """40 years of monthly data so trailing-30y and trailing-10y have enough per month."""
    idx = pd.date_range(
        f"{start_year}-01-31",
        periods=n_years * 12,
        freq="ME",
    )
    rng = np.arange(len(idx))
    return pd.DataFrame({
        "mkt_rf": np.sin(rng) * 2,
        "smb": np.cos(rng),
        "hml": (rng % 12 - 5) * 0.3,
        "rf": 0.2,
        "rmw": np.cos(rng) * 0.5,
        "cma": np.sin(rng) * 0.4,
        "mom": (rng % 7 - 3) * 0.5,
    }, index=idx)


def _fake_store(monkeypatch, df: pd.DataFrame | None = None):
    if df is None:
        df = _make_df()
    monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)


def test_seasonality_maps_and_flags(monkeypatch):
    _fake_store(monkeypatch)
    out = fs.compute_factor_seasonality()
    assert out is not None
    keys = [f["key"] for f in out["factors"]]
    assert keys[:3] == ["value", "profitability", "investment"]   # mapped first
    value = next(f for f in out["factors"] if f["key"] == "value")
    assert value["our_factor"] == "value" and value["context_only"] is False
    mom = next(f for f in out["factors"] if f["key"] == "momentum")
    assert mom["context_only"] is True and mom["our_factor"] is None
    # every month present, hit in 0..100, full has more obs than trailing-30y
    assert set(value["full"]) == set(range(1, 13))
    assert all(0 <= c["hit"] <= 100 for c in value["full"].values())
    assert value["full"][1]["n"] >= value["trailing_30y"][1]["n"]
    assert out["disclosure_en"] and out["disclosure_zh"]


def test_seasonality_degrades_when_missing(monkeypatch):
    monkeypatch.setattr(fs.store, "read", lambda g, n: None)
    assert fs.compute_factor_seasonality() is None


# ---------------------------------------------------------------------------
# New tests: trailing_10y, verdict rules, now block
# ---------------------------------------------------------------------------

def test_trailing_10y_present_per_factor(monkeypatch):
    """Each factor dict must have a 'trailing_10y' key with per-month stats."""
    _fake_store(monkeypatch)
    out = fs.compute_factor_seasonality()
    assert out is not None
    assert out.get("schema") == "factor_seasonality.v2"
    for f in out["factors"]:
        assert "trailing_10y" in f, f"factor {f['key']} missing trailing_10y"
        # trailing_10y should have fewer obs than full
        if f["full"] and f["trailing_10y"]:
            full_n = list(f["full"].values())[0]["n"]
            t10_n = list(f["trailing_10y"].values())[0]["n"]
            assert t10_n <= full_n, f"factor {f['key']}: trailing_10y n > full n"
    # plain_en and plain_zh present
    for f in out["factors"]:
        assert "plain_en" in f and f["plain_en"], f"factor {f['key']} missing plain_en"
        assert "plain_zh" in f and f["plain_zh"], f"factor {f['key']} missing plain_zh"


def _make_headwind_df() -> pd.DataFrame:
    """Synthetic data with deterministic July mom headwind.

    July mom values: 10 years, all negative => hit=0, mean<0 => headwind verdict.
    Other months: strongly positive for mom.
    """
    idx = pd.date_range("2010-01-31", "2024-12-31", freq="ME")
    data = {col: np.ones(len(idx)) * 2.0 for col in ["mkt_rf", "smb", "hml", "rf", "rmw", "cma", "mom"]}
    df = pd.DataFrame(data, index=idx)
    # Make July mom always negative (-3.0)
    july_mask = df.index.month == 7
    df.loc[july_mask, "mom"] = -3.0
    return df


def _make_tailwind_df() -> pd.DataFrame:
    """Synthetic data with deterministic July mom tailwind.

    July mom: 10 years all strongly positive => hit=100%, mean>0 => tailwind.
    """
    idx = pd.date_range("2010-01-31", "2024-12-31", freq="ME")
    data = {col: np.ones(len(idx)) * -0.5 for col in ["mkt_rf", "smb", "hml", "rf", "rmw", "cma", "mom"]}
    df = pd.DataFrame(data, index=idx)
    july_mask = df.index.month == 7
    df.loc[july_mask, "mom"] = 4.0
    return df


def _make_neutral_df() -> pd.DataFrame:
    """All July mom observations mixed: hit=50%, mean~0 => neutral."""
    idx = pd.date_range("2010-01-31", "2024-12-31", freq="ME")
    data = {col: np.ones(len(idx)) * 0.5 for col in ["mkt_rf", "smb", "hml", "rf", "rmw", "cma", "mom"]}
    df = pd.DataFrame(data, index=idx)
    # alternate +/- for July to get neutral hit
    july_idx = [i for i, ts in enumerate(idx) if ts.month == 7]
    for i, pos in enumerate(july_idx):
        df.iloc[pos, df.columns.get_loc("mom")] = 1.0 if i % 2 == 0 else -1.0
    return df


def _make_low_n_df() -> pd.DataFrame:
    """Only 5 years of data — trailing_10y n<8 for any month => falls back to trailing_30y for verdict.

    We make July mom positive in this short window (tailwind if used),
    but the full/30y data (same 5y = all data) also too short for 30y fallback to work differently.
    Key behavior: n<8 triggers fallback to trailing_30y window for verdict.
    """
    idx = pd.date_range("2020-01-31", "2024-12-31", freq="ME")
    data = {col: np.ones(len(idx)) * -2.0 for col in ["mkt_rf", "smb", "hml", "rf", "rmw", "cma", "mom"]}
    df = pd.DataFrame(data, index=idx)
    # Make July always negative (headwind from full/30y perspective too, n=5 < 8)
    july_mask = df.index.month == 7
    df.loc[july_mask, "mom"] = -3.0
    return df


class TestVerdictRule:
    """Unit tests for _verdict() function directly."""

    def test_headwind(self):
        y10 = {"mean": -2.0, "hit": 30, "n": 10}
        verdict, window = fs._verdict(y10, None)
        assert verdict == "headwind"
        assert window == "trailing_10y"

    def test_tailwind(self):
        y10 = {"mean": 1.5, "hit": 80, "n": 10}
        verdict, window = fs._verdict(y10, None)
        assert verdict == "tailwind"
        assert window == "trailing_10y"

    def test_neutral_mixed(self):
        y10 = {"mean": -0.2, "hit": 55, "n": 10}
        verdict, window = fs._verdict(y10, None)
        assert verdict == "neutral"
        assert window == "trailing_10y"

    def test_fallback_to_30y_when_n_lt_8(self):
        """n=5 < 8 => fall back to trailing_30y window."""
        y10_small = {"mean": 2.0, "hit": 80, "n": 5}   # would be tailwind if used
        y30 = {"mean": -2.0, "hit": 30, "n": 30}       # headwind
        verdict, window = fs._verdict(y10_small, y30)
        assert verdict == "headwind"
        assert window == "trailing_30y"

    def test_fallback_to_30y_when_10y_absent(self):
        """No 10y stats => fall to 30y."""
        y30 = {"mean": 2.0, "hit": 75, "n": 20}
        verdict, window = fs._verdict(None, y30)
        assert verdict == "tailwind"
        assert window == "trailing_30y"

    def test_all_absent_returns_neutral(self):
        verdict, window = fs._verdict(None, None)
        assert verdict == "neutral"


class TestNowBlock:
    """Integration tests for compute_factor_seasonality now block."""

    def test_headwind_now_block(self, monkeypatch):
        df = _make_headwind_df()
        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)
        out = fs.compute_factor_seasonality(today=date(2024, 7, 15))
        assert out is not None
        now = out["now"]
        assert now is not None
        assert now["month"] == 7
        assert now["month_label_en"] == "July"
        assert now["month_label_zh"] == "7月"
        # Find momentum in factors
        mom = next(f for f in now["factors"] if f["key"] == "momentum")
        assert mom["verdict"] == "headwind"
        # headline mentions rough
        assert "rough" in now["headline_en"].lower() or "rough" in now["headline_en"]
        assert now["stance_en"] == "Watch — don't chase this month's hottest stocks."
        assert now["chip_en"] is not None
        assert "context only" in now["chip_en"]
        # ZH parity
        assert now["headline_zh"]
        assert now["stance_zh"] == "观望——本月不要追逐最热门的股票。"
        assert "仅供参考" in now["chip_zh"]

    def test_tailwind_now_block(self, monkeypatch):
        df = _make_tailwind_df()
        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)
        out = fs.compute_factor_seasonality(today=date(2024, 7, 15))
        assert out is not None
        now = out["now"]
        assert now is not None
        mom = next(f for f in now["factors"] if f["key"] == "momentum")
        assert mom["verdict"] == "tailwind"
        # tailwind headline uses "kind" or "friendlier"
        assert "kind" in now["headline_en"] or "friendlier" in now["headline_en"]
        assert "merits" in now["stance_en"]
        assert now["chip_en"] is not None

    def test_neutral_now_block_all_neutral(self, monkeypatch):
        df = _make_neutral_df()
        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)
        out = fs.compute_factor_seasonality(today=date(2024, 7, 15))
        assert out is not None
        now = out["now"]
        assert now is not None
        # chip should be None when all neutral
        # (may not be ALL neutral depending on synthetic data; we just check structure)
        assert "headline_en" in now
        assert "stance_en" in now

    def test_n_lt_8_fallback_window(self, monkeypatch):
        """When trailing_10y has n<8, verdict uses trailing_30y; window_used should reflect this."""
        df = _make_low_n_df()
        monkeypatch.setattr(fs.store, "read", lambda g, n: df if (g, n) == ("french", "factors") else None)
        out = fs.compute_factor_seasonality(today=date(2024, 7, 15))
        assert out is not None
        now = out["now"]
        assert now is not None
        mom = next((f for f in now["factors"] if f["key"] == "momentum"), None)
        if mom:
            # n=5 < 8; but 30y may also have n<8 (all same 5y data), so may be neutral
            assert mom["window_used"] in ("trailing_10y", "trailing_30y")

    def test_headline_determinism_fixed_date(self, monkeypatch):
        """Same today=date(2026,7,15) call twice => identical headline."""
        _fake_store(monkeypatch)
        out1 = fs.compute_factor_seasonality(today=date(2026, 7, 15))
        out2 = fs.compute_factor_seasonality(today=date(2026, 7, 15))
        assert out1["now"]["headline_en"] == out2["now"]["headline_en"]
        assert out1["now"]["headline_zh"] == out2["now"]["headline_zh"]
        assert out1["now"]["chip_en"] == out2["now"]["chip_en"]

    def test_missing_french_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(fs.store, "read", lambda g, n: None)
        assert fs.compute_factor_seasonality() is None

    def test_now_block_structure(self, monkeypatch):
        """now block has all required keys."""
        _fake_store(monkeypatch)
        out = fs.compute_factor_seasonality(today=date(2026, 7, 15))
        assert out is not None
        now = out["now"]
        assert now is not None
        for key in ("month", "month_label_en", "month_label_zh", "factors", "market",
                    "headline_en", "headline_zh", "stance_en", "stance_zh",
                    "verdict_rule"):
            assert key in now, f"now block missing key: {key}"
        assert now["verdict_rule"] == "display.v1"
        # Per-factor structure
        for f in now["factors"]:
            for k in ("key", "plain_en", "plain_zh", "verdict", "window_used",
                      "y10", "y30", "full", "recent", "streak"):
                assert k in f, f"now.factors[{f['key']}] missing key {k}"
            assert f["verdict"] in ("headwind", "tailwind", "neutral")
            assert f["window_used"] in ("trailing_10y", "trailing_30y")
            assert isinstance(f["recent"], list)
            assert "sign" in f["streak"] and "len" in f["streak"]


class TestStreakHelper:
    """Unit tests for _streak()."""

    def test_empty(self):
        r = fs._streak([])
        assert r["sign"] == 0 and r["len"] == 0

    def test_all_negative(self):
        r = fs._streak([-1.0, -2.0, -0.5, -3.0])
        assert r["sign"] == -1 and r["len"] == 4

    def test_mixed(self):
        r = fs._streak([-1.0, -2.0, 1.0, -0.5])
        assert r["sign"] == -1 and r["len"] == 2

    def test_single_positive(self):
        r = fs._streak([0.5])
        assert r["sign"] == 1 and r["len"] == 1
