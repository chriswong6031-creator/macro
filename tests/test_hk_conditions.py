"""Tests for engine/hk_conditions.py — the HK-native RORO / slowdown / drawdown /
Fear<->Euphoria display-only conditioning layer.

Core invariant: the RORO composite (pre-tanh) equals the mean of its AVAILABLE
signed legs. Plus None-safety, 0..100 bounds, bilingual labels, the UNCALIBRATED
contract (HK ships honest-uncalibrated) and the display-only contract.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import hk_conditions as hc
from engine.hk_inputs import build_features


@pytest.fixture(scope="module")
def f():
    return build_features()


@pytest.fixture(scope="module")
def rf(f):
    return hc.roro_frame(f)


# --- (1) RORO ---------------------------------------------------------------
def test_roro_composite_equals_mean_of_signed_legs(rf):
    """THE invariant: roro_raw == mean of the available roro_<key> legs, per row."""
    assert "roro_raw" in rf.columns and "roro" in rf.columns
    leg_cols = [c for c in rf.columns if c.startswith("roro_") and c not in ("roro_raw", "roro")]
    assert leg_cols, "expected at least one signed RORO leg"
    expected = rf[leg_cols].mean(axis=1)
    pd.testing.assert_series_equal(rf["roro_raw"], expected, check_names=False)


def test_roro_headline_is_tanh_of_raw(rf):
    common = rf[["roro", "roro_raw"]].dropna()
    assert len(common) > 0
    np.testing.assert_allclose(common["roro"], np.tanh(common["roro_raw"]), atol=1e-9)


def test_roro_snapshot_invariant(f):
    snap = hc.hk_roro(f)
    legs = [v for k, v in snap.items() if k.startswith("hk_roro_") and v is not None]
    if legs:
        assert snap["roro_raw"] == pytest.approx(float(np.mean(legs)), abs=1e-3)
        assert snap["roro"] == pytest.approx(float(np.tanh(snap["roro_raw"])), abs=1e-3)


def test_roro_in_bounds_and_state(f):
    snap = hc.hk_roro(f)
    if snap["roro"] is not None:
        assert -1.0 <= snap["roro"] <= 1.0
        assert snap["roro_state"] in ("risk-on", "risk-off", "neutral")
    for lg in snap["legs"]:
        assert lg["lean"] in ("risk-on", "risk-off")
        assert lg["name_en"] and lg["name_zh"]   # bilingual


# --- (2) slowdown gauge -----------------------------------------------------
def test_recession_bounds_and_legs(f):
    rec = hc.hk_recession(f)
    # HK ships UNCALIBRATED (short, globally-coupled history) — honest by design.
    assert rec["calibrated"] is False
    if rec["score"] is not None:
        assert 0.0 <= rec["score"] <= 100.0
        assert rec["label"] in ("low", "elevated", "high")
        assert len(rec["bands"]) == 2 and rec["bands"][0] <= rec["bands"][1]
    for lg in rec["legs"]:
        assert lg["label"] and lg["label_zh"]    # bilingual
        if lg["active"]:
            assert 0.0 <= lg["value"] <= 100.0
            assert lg["points"] is None or lg["points"] >= 0.0


def test_recession_points_sum_to_score(f):
    rec = hc.hk_recession(f)
    if rec["score"] is None:
        pytest.skip("no slowdown legs available")
    pts = sum(lg["points"] for lg in rec["legs"] if lg["active"] and lg["points"] is not None)
    assert pts == pytest.approx(rec["score"], abs=0.5)


# --- (3) drawdown gauge -----------------------------------------------------
def test_drawdown_bounds(f):
    dd = hc.hk_drawdown(f)
    assert dd["calibrated"] is False
    if dd["score"] is not None:
        assert 0.0 <= dd["score"] <= 100.0
        assert dd["band"] in ("low", "elevated", "high", "extreme")


# --- fear / euphoria --------------------------------------------------------
def test_fear_euphoria_bounds_and_bilingual(f):
    fe = hc.fear_euphoria(f)
    if fe is None:
        pytest.skip("no RORO composite -> fear/euphoria unavailable")
    if fe["fe_score"] is not None:
        assert 0 <= fe["fe_score"] <= 100
        assert fe["band"] in ("Panic", "Fear", "Neutral", "Greed", "Euphoria")
        assert fe["band_zh"]
    for lg in fe["legs"]:
        assert 0 <= lg["pct"] <= 100
        assert lg["name_en"] and lg["name_zh"]
        assert lg["lean"] in ("risk-on", "risk-off")
    conf = fe["confirmation"]
    if conf is not None:
        assert conf["n_on"] + conf["n_off"] == conf["total"]
        assert conf["verdict_en"] and conf["verdict_zh"]


# --- snapshot bundle --------------------------------------------------------
def test_snapshot_shape_and_charts(f):
    snap = hc.snapshot(f)
    assert snap["display_only"] is True
    for key in ("roro", "recession", "drawdown_risk", "charts"):
        assert key in snap
    charts = snap["charts"]
    for line in ("roro", "recession", "drawdown", "fear_euphoria"):
        assert line in charts
        c = charts[line]
        assert len(c["dates"]) == len(c["vals"])


def test_snapshot_accepts_regime_kwarg(f):
    a = hc.snapshot(f, regime=None)
    assert a["display_only"] is True


# --- None-safety ------------------------------------------------------------
def test_none_safety_on_empty_frame():
    empty = pd.DataFrame(index=pd.bdate_range("2020-01-01", periods=10))
    rf = hc.roro_frame(empty)
    assert isinstance(rf, pd.DataFrame)
    rec = hc.hk_recession(empty)
    assert rec["score"] is None or 0.0 <= rec["score"] <= 100.0
    dd = hc.hk_drawdown(empty)
    assert dd["score"] is None or 0.0 <= dd["score"] <= 100.0


def test_round_helper_handles_nan_and_none():
    assert hc._round(None) is None
    assert hc._round(float("nan")) is None
    assert hc._round(np.inf) is None
    assert hc._round(1.23456, 2) == 1.23
