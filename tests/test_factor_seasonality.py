"""Ken French collector parsing + factor-seasonality engine.

The French CSV has a variable free-text preamble, a header line starting with ',',
monthly YYYYMM rows, then an 'Annual Factors:' block we must drop; -99.99 marks
missing. The seasonality engine maps French columns to our factors, computes
per-month mean/median/hit over full + trailing-30y, and degrades to None when the
French data is absent (so the page just hides).
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

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


def _fake_store(monkeypatch):
    # 40 years of monthly data so trailing-30y has enough per month
    idx = pd.date_range("1985-01-31", "2024-12-31", freq="ME")
    rng = np.arange(len(idx))
    df = pd.DataFrame({
        "mkt_rf": np.sin(rng) * 2, "smb": np.cos(rng), "hml": (rng % 12 - 5) * 0.3,
        "rf": 0.2, "rmw": np.cos(rng) * 0.5, "cma": np.sin(rng) * 0.4,
        "mom": (rng % 7 - 3) * 0.5,
    }, index=idx)
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
