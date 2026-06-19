"""Tests for engine.vol_sentiment (vol-regime + put/call chip, display-only)."""
import json

import pandas as pd
import pytest

from engine import vol_sentiment as vsmod


def test_vol_regime_labels(monkeypatch):
    def cond(vix_pctile, term_state, vrp="normal"):
        return {"risk_appetite": {"vix_term_state": term_state, "vrp_state": vrp,
                                  "realized_vol": 15.0, "skew": 140.0},
                "complacency": {"vix_pctile": vix_pctile}}

    # STRESS via backwardation
    monkeypatch.setattr(vsmod, "_regime_conditions", lambda: cond(0.5, "backwardation (stress)"))
    monkeypatch.setattr(vsmod, "_vix_term", lambda: {"vix": 30.0, "vix3m": 28.0, "term_ratio": 1.07, "term_state": "backwardation"})
    assert vsmod._vol_regime()["label_en"] == "STRESS"

    # CALM via low pctile + contango
    monkeypatch.setattr(vsmod, "_regime_conditions", lambda: cond(0.10, "contango (calm)"))
    monkeypatch.setattr(vsmod, "_vix_term", lambda: {"vix": 12.0, "vix3m": 15.0, "term_ratio": 0.80, "term_state": "contango"})
    assert vsmod._vol_regime()["label_en"] == "CALM"

    # ELEVATED via high pctile
    monkeypatch.setattr(vsmod, "_regime_conditions", lambda: cond(0.65, "contango (calm)"))
    monkeypatch.setattr(vsmod, "_vix_term", lambda: {"vix": 20.0, "vix3m": 21.0, "term_ratio": 0.95, "term_state": "flat"})
    assert vsmod._vol_regime()["label_en"] == "ELEVATED"


def test_put_call_sentiment(monkeypatch, tmp_path):
    # build a putcall.parquet where the last obs is the HIGHEST -> protective/fearful
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    eq = [0.6 + 0.005 * i for i in range(40)]            # strictly rising -> last = max
    df = pd.DataFrame({"equity_pc_ratio": eq, "index_pc_ratio": eq}, index=idx)
    d = tmp_path / "cboe"
    d.mkdir()
    df.to_parquet(d / "putcall.parquet")
    monkeypatch.setattr(vsmod.config, "data_dir", lambda: tmp_path)
    pc = vsmod._put_call()
    assert pc is not None
    assert pc["sentiment_en"].startswith("protective")
    assert pc["n_obs"] == 40
    assert pc["young"] is True


def test_compute_smoke_real_data():
    out = vsmod.compute_vol_sentiment()
    if out is None:
        pytest.skip("no regime/cboe caches present")
    assert ("vol_regime" in out) or ("put_call" in out)
