"""Per-ticker factor-EXPOSURE betas (engine/factor_exposure.py).

Exposure is a risk decomposition, not a forecast, so the tests assert the math is
RIGHT and the guardrails hold: (1) an injected factor loading is recovered on the
correct factor with the correct sign, (2) book aggregation finds the hidden
one-way bet and flags concentration, (3) the radar excludes the proxies and sorts
by |beta|, (4) thin data degrades to None.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import factor_exposure as fe

CFG = {"win": 400, "min_obs": 200, "vif_thresh": 5.0, "sig_t": 2.0, "min_history": 300}


def _facrets(n: int = 450, seed: int = 0) -> pd.DataFrame:
    """Independent random factor returns, one column per FACTORS key."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    return pd.DataFrame({k: rng.normal(0, 0.01, n) for k in fe.FACTORS}, index=idx)


def _stock(fac, market_b, factor, factor_b, noise=0.004, seed=1):
    rng = np.random.default_rng(seed)
    y = market_b * fac["market"] + factor_b * fac[factor] + rng.normal(0, noise, len(fac))
    return pd.Series(y, index=fac.index)


def test_recovers_injected_loading_and_sign():
    fac = _facrets()
    e = fe.exposure(_stock(fac, 0.8, "semis", 1.5), fac, CFG)
    assert e is not None
    assert e["dominant"] == "semis"
    assert e["market_beta"] > 0
    assert e["betas"]["semis"]["beta"] > 0 and e["betas"]["semis"]["t"] > 3
    # an un-loaded factor should be insignificant
    assert abs(e["betas"]["oil"]["t"]) < 2.5


def test_negative_loading_is_signed():
    fac = _facrets(seed=7)
    e = fe.exposure(_stock(fac, 0.5, "usd", -1.4, seed=3), fac, CFG)
    assert e["dominant"] == "usd"
    assert e["betas"]["usd"]["beta"] < 0


def test_book_finds_hidden_one_way_bet():
    fac = _facrets(seed=2)
    expo = {t: fe.exposure(_stock(fac, 0.5, "crypto", load, seed=i), fac, CFG)
            for i, (t, load) in enumerate([("A", 2.0), ("B", 1.7), ("C", 1.4)])}
    bk = fe.book_exposure({t: 1.0 for t in expo}, expo)
    assert bk["dominant"] == "crypto" and bk["concentrated"]
    assert bk["n_aligned"] == 3 and bk["n_total"] == 3


def test_radar_excludes_proxies_and_sorts():
    fac = _facrets(seed=5)
    expo = {}
    for i, (t, load) in enumerate([("HI", 2.6), ("LO", 1.0), ("SMH", 3.0)]):  # SMH = a proxy id
        expo[t] = fe.exposure(_stock(fac, 0.4, "crypto", load, seed=i + 10), fac, CFG)
    rad = fe.radar(expo, top=10, sig_t=2.0)
    names = [r["ticker"] for r in rad["crypto"]]
    assert "SMH" not in names                       # proxy never heads its board
    assert "HI" in names
    betas = [abs(r["beta"]) for r in rad["crypto"]]
    assert betas == sorted(betas, reverse=True)     # ranked by |beta|


def test_thin_data_degrades_to_none():
    fac = _facrets()
    short = pd.Series(np.random.default_rng(4).normal(0, 0.01, 50), index=fac.index[:50])
    assert fe.exposure(short, fac, {"win": 252, "min_obs": 180}) is None


def test_factor_returns_smoke_real_or_skips():
    fac = fe.factor_returns()
    if fac.empty:
        return                                       # proxies absent in this checkout
    assert "market" in fac.columns and len(fac.columns) >= 3
