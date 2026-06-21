"""Tests for engine/vol_squeeze.py — the single-stock volatility black hole."""
import numpy as np
import pandas as pd

from engine import vol_squeeze as vs


def _idx(n):
    return pd.bdate_range("2019-01-01", periods=n)


def _noisy(n, start=100.0, scale=1.5, seed=0):
    rng = np.random.default_rng(seed)
    return start + np.cumsum(rng.standard_normal(n) * scale)


def _tight(level, n, jitter=0.03, seed=1):
    rng = np.random.default_rng(seed)
    return level + rng.standard_normal(n) * jitter


def _ohlc(close, spread, vol=1_000_000.0):
    c = pd.Series(close, index=_idx(len(close)))
    return c, c + spread, c - spread, pd.Series(vol, index=c.index)


def test_none_when_too_short():
    c = pd.Series(_noisy(50), index=_idx(50))
    assert vs.assess(c) is None


def test_coiled_when_compressed_now():
    noisy = _noisy(220, scale=1.5)
    tight = _tight(noisy[-1], 30, jitter=0.02)
    px = np.concatenate([noisy, tight])
    c, h, l, v = _ohlc(px, spread=0.02)
    out = vs.assess(c, h, l, v)
    assert out["state"] == "COILED"
    assert out["coiled"] is True
    assert out["days_compressed"] >= 5
    assert out["bbwp"] < 25 and out["hv_pctile"] < 25
    assert out["box_hi"] is not None and out["box_lo"] is not None


def test_fired_up_on_volume_confirmed_break():
    noisy = _noisy(220, scale=1.5)
    tight = _tight(noisy[-1], 25, jitter=0.02)
    px = np.concatenate([noisy, tight])
    c, h, l, v = _ohlc(px, spread=0.02)
    # append one decisive up-break bar on heavy volume
    brk = float(tight[-1]) + 8.0
    c.loc[_idx(len(px) + 1)[-1]] = brk
    h = c + 0.02
    l = c - 0.02
    v = v.reindex(c.index).fillna(1_000_000.0)
    v.iloc[-1] = 3_000_000.0
    out = vs.assess(c, h, l, v)
    assert out["state"] == "FIRED_UP"
    assert out["fired_dir"] == "up"
    assert out["volume_confirmed"] is True


def test_fired_down_break():
    noisy = _noisy(220, scale=1.5, seed=2)
    tight = _tight(noisy[-1], 25, jitter=0.02, seed=2)
    px = np.concatenate([noisy, tight])
    c, h, l, v = _ohlc(px, spread=0.02)
    brk = float(tight[-1]) - 8.0
    c.loc[_idx(len(px) + 1)[-1]] = brk
    h = c + 0.02
    l = c - 0.02
    v = v.reindex(c.index).fillna(1_000_000.0)
    out = vs.assess(c, h, l, v)
    assert out["state"] == "FIRED_DOWN"
    assert out["fired_dir"] == "down"


def test_expansion_when_vol_elevated_and_no_recent_squeeze():
    # persistently high, rising vol -> no compression, elevated HV percentile
    rng = np.random.default_rng(5)
    px = 100 + np.cumsum(rng.standard_normal(260) * 0.3)
    px[-40:] = px[-41] + np.cumsum(rng.standard_normal(40) * 4.0)
    c = pd.Series(px, index=_idx(260))
    out = vs.assess(c)
    assert out["state"] in ("EXPANSION", "NONE")
    if out["state"] == "EXPANSION":
        assert out["hv_pctile"] >= 80


def test_close_only_graceful():
    noisy = _noisy(220, scale=1.5)
    tight = _tight(noisy[-1], 30, jitter=0.02)
    c = pd.Series(np.concatenate([noisy, tight]), index=_idx(250))
    out = vs.assess(c)
    assert out["coverage"] == "close"
    assert out["volume_confirmed"] is None
    assert out["state"] in ("COILED", "COMPRESSED")
