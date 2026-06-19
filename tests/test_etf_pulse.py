"""Tests for engine.etf_pulse (ETF Pulse rotation strip, display-only)."""
import json

import numpy as np
import pandas as pd
import pytest

from engine import etf_pulse


def _series(vals, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, dtype=float)


def test_ratio_perf_math():
    # num rises 1%/day, den flat -> ratio rises ~ monotonically; 20d change positive.
    n = 80
    num = _series([100 * (1.01 ** i) for i in range(n)])
    den = _series([100.0] * n)
    perf = etf_pulse._ratio_perf(num, den)
    assert perf is not None
    assert perf["chg_20d"] > 0
    assert perf["chg_1d"] == pytest.approx(1.0, abs=0.05)  # ~1%/day
    # standalone (den=None) returns the level series perf
    solo = etf_pulse._ratio_perf(num, None)
    assert solo is not None and solo["chg_20d"] > 0


def test_ratio_perf_short_history_none():
    assert etf_pulse._ratio_perf(_series([1.0] * 10), None) is None
    assert etf_pulse._ratio_perf(None, None) is None


def test_risk_leg_tilt_sign(monkeypatch):
    # HYG up vs TLT flat (credit>duration => risk-on, dir +1); gold down vs SPY flat
    # (risk-on, dir -1 on a NEGATIVE move => +); dollar flat; VIX down (risk-on).
    rising = _series([100 * (1.01 ** i) for i in range(80)])
    falling = _series([100 * (0.99 ** i) for i in range(80)])
    flat = _series([100.0] * 80)

    def fake_close(sym):
        return {"HYG": rising, "TLT": flat, "GC=F": falling, "SPY": flat,
                "DX-Y.NYB": flat, "_VIX": falling}.get(sym, flat)

    monkeypatch.setattr(etf_pulse, "_close", fake_close)
    risk = etf_pulse._risk_leg()
    assert risk is not None
    assert risk["tilt"] > 0
    assert risk["label_en"] == "RISK-ON"


def test_sector_leg_reads_regime(monkeypatch, tmp_path):
    reg = {"date": "2026-06-18", "sector_rs": [
        {"ticker": "XLK", "mom_20d_pct": 6.0, "mom_60d_pct": 20.0, "pctile_252d": 98, "above_200d_trend": True},
        {"ticker": "XLE", "mom_20d_pct": -2.0, "mom_60d_pct": -8.0, "pctile_252d": 12, "above_200d_trend": False},
        {"ticker": "SMH", "mom_20d_pct": 13.0, "mom_60d_pct": 41.0, "pctile_252d": 99, "above_200d_trend": True},
    ]}
    d = tmp_path / "regime"
    d.mkdir()
    (d / "latest.json").write_text(json.dumps(reg))
    monkeypatch.setattr(etf_pulse.config, "data_dir", lambda: tmp_path)
    leg = etf_pulse._sector_leg()
    assert leg is not None
    # SMH is a factor ETF, not a GICS sector -> excluded; XLK leads XLE.
    tickers = [r["ticker"] for r in leg["rows"]]
    assert "SMH" not in tickers
    assert tickers[0] == "XLK"
    assert leg["leaders"][0] == "XLK"
    assert leg["rows"][0]["rank"] == 1


def test_compute_smoke_real_data():
    """Against the worktree caches; skip if unavailable (CI without parquets)."""
    out = etf_pulse.compute_etf_pulse()
    if out is None:
        pytest.skip("no price caches present")
    assert "style" in out and "risk" in out and "sector" in out
    assert out.get("as_of")
