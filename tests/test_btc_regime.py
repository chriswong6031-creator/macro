"""Tests for the display-only BTC macro-regime composite + tail flags + mode lean."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_regime, btc_regime_flags, btc_correlation_regime

SIG = "data/vector/signals.parquet"


@pytest.fixture(scope="module")
def df():
    p = Path(SIG)
    if not p.exists():
        pytest.skip("signals.parquet not built")
    return pd.read_parquet(p)


def _synth(n=1600):
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    rng = np.random.default_rng(0)
    close = pd.Series(20000 * np.exp(np.cumsum(rng.normal(0.0004, 0.03, n))), index=idx)
    return pd.DataFrame({
        "close": close,
        "net_liq_roc": pd.Series(rng.normal(0, 2, n), index=idx),
        "global_m2_yoy": pd.Series(rng.normal(7, 2, n), index=idx),
        "real_yield": pd.Series(rng.normal(0.5, 0.8, n), index=idx),
        "dxy": pd.Series(100 + np.cumsum(rng.normal(0, 0.2, n)), index=idx),
        "vix": pd.Series(np.abs(rng.normal(18, 6, n)), index=idx),
        "hy_oas": pd.Series(np.abs(rng.normal(3.5, 1, n)), index=idx),
        "etf_flow_z": pd.Series(rng.normal(0, 1, n), index=idx),
        "stbl_growth_z": pd.Series(rng.normal(0, 1, n), index=idx),
        "mvrv_z": pd.Series(rng.normal(1.5, 1.5, n), index=idx),
        "nupl": pd.Series(rng.normal(0.3, 0.2, n), index=idx),
        "mayer": pd.Series(np.abs(rng.normal(1.1, 0.4, n)), index=idx),
    }, index=idx)


# ---- composite -------------------------------------------------------------- #
def test_score_z_bounds():
    z = pd.Series([-3, -1, 0, 1, 3.0])
    s = btc_regime._score_z(z)
    assert s.min() >= -2 and s.max() <= 2
    assert s.iloc[0] == -2 and s.iloc[-1] == 2 and s.iloc[2] == 0


def test_composite_index_range_synth():
    d = _synth()
    cf = btc_regime.composite_frame(d)
    idx = cf["index"].dropna()
    assert len(idx) > 200
    assert idx.min() >= 0 and idx.max() <= 100


def test_compute_render_shape_synth():
    out = btc_regime.compute(_synth())
    assert out["ok"] and out["display_only"] is True
    assert 0 <= out["index"] <= 100
    assert {t["tier"] for t in out["tiers"]} <= {"T1", "T2", "T3", "T4", "T5"}
    assert any(f["key"] == "trend" for f in out["factors"])
    # every factor carries an origin tag
    assert all(f["origin"] in ("apriori", "tuned", "context") for f in out["factors"])


def test_exposure_band_monotone():
    xs = [5, 20, 50, 80, 100]
    ys = [btc_regime.exposure_band(x) for x in xs]
    assert ys == sorted(ys) and ys[0] == 0.0 and ys[-1] == 1.0
    assert btc_regime.exposure_band(None) is None


def test_missing_factor_renormalizes():
    d = _synth().drop(columns=["dxy", "real_yield"])
    out = btc_regime.compute(d)
    assert out["ok"]                      # degrades, does not raise
    keys = {f["key"] for f in out["factors"] if f["present"]}
    assert "dxy" not in keys and "real10y" not in keys


def test_never_raises_on_garbage():
    out = btc_regime.compute(pd.DataFrame({"close": [1, 2, 3]}))
    assert "ok" in out                    # returns a dict, never throws


# ---- flags ------------------------------------------------------------------ #
def test_flags_confluence_shape():
    f = btc_regime_flags.evaluate(_synth())
    assert f["ok"]
    assert f["active"] in ("STAY-AWAY", "DOUBLE-DOWN", "NONE")
    assert set(f["stay_away"]["fires_at_k"]) == {4, 5, 6}
    assert f["double_down"]["prereq"] == "DD_netliq_expanding_accel"


def test_double_down_requires_prerequisite():
    """If net-liq is NOT expanding+accelerating, DOUBLE-DOWN can never be active."""
    d = _synth()
    d["net_liq_roc"] = -5.0   # hard-contracting every day
    f = btc_regime_flags.evaluate(d)
    assert f["double_down"]["prereq_ok"] is False
    assert f["double_down"]["active"] is False


def test_onchain_panel_co_flash():
    d = _synth()
    # force all three on-chain metrics to their lows on the last row
    for c in ("mvrv_z", "nupl", "mayer"):
        d.loc[d.index[-1], c] = d[c].min() - 1
    p = btc_regime_flags.onchain_panel(d)
    assert p["ok"] and p["depressed_co_flash"] is True


# ---- mode lean -------------------------------------------------------------- #
def test_mode_lean_non_numeric():
    m = btc_correlation_regime.lean(_synth())
    assert m["ok"] and m["non_numeric"] is True
    assert m["lean"] in ("flow", "macro", "mixed")


def test_mode_lean_pre_etf_is_macro():
    d = _synth().drop(columns=["etf_flow_z"])
    m = btc_correlation_regime.lean(d)
    assert m["ok"] and m["lean"] == "macro"


# ---- live parquet smoke ----------------------------------------------------- #
def test_live_parquet_smoke(df):
    out = btc_regime.compute(df)
    assert out["ok"]
    assert 0 <= out["index"] <= 100
    f = btc_regime_flags.evaluate(df)
    assert f["ok"]
    m = btc_correlation_regime.lean(df)
    assert m["ok"]
