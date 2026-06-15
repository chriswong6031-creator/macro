"""Portfolio factor-exposure engine. The math that must hold: orthogonalization
actually decorrelates the factors (so betas don't double-count); the decoupled betas
RECOVER known loadings; portfolio aggregation sums betas by weight, splits risk to
~1, and flags a one-factor book. Pure-math on synthetic data; snapshot() smoke-tested
vs the store. (engine/factor_exposure.py; validated in reports/factor-exposure-phase0.md.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import factor_exposure as fe


def _idx(n: int):
    return pd.date_range("2018-01-01", periods=n, freq="B")


def test_orthogonalize_removes_collinearity():
    rng = np.random.default_rng(0)
    n = 600
    m = rng.normal(0, 0.01, n)
    F = pd.DataFrame({                                  # growth/size highly collinear with market
        "mkt": m,
        "growth": 0.9 * m + rng.normal(0, 0.003, n),
        "size": 0.8 * m + rng.normal(0, 0.004, n),
    }, index=_idx(n))
    assert F.corr().loc["mkt", "growth"] > 0.85        # raw: badly collinear
    G = fe.orthogonalize_factors(F)
    off = G.corr().abs().to_numpy()[~np.eye(3, dtype=bool)]
    assert off.max() < 1e-9                             # mutually orthogonal after transform
    assert np.corrcoef(G["mkt"], F["mkt"])[0, 1] > 0.999   # market (first) is untouched


def test_betas_recover_known_loadings():
    rng = np.random.default_rng(1)
    n = 500
    F = pd.DataFrame({"mkt": rng.normal(0, 0.01, n), "growth": rng.normal(0, 0.008, n),
                      "size": rng.normal(0, 0.009, n)}, index=_idx(n))
    G = fe.orthogonalize_factors(F)
    true = {"AAA": {"mkt": 1.2, "growth": 0.5, "size": -0.3},
            "BBB": {"mkt": 0.7, "growth": -0.4, "size": 0.8}}
    R = pd.DataFrame({t: sum(b[k] * G[k] for k in b) + rng.normal(0, 0.0008, n)
                      for t, b in true.items()}, index=_idx(n))
    res = fe._betas_on_window(R, G, minp=100, max_abs=5.0)["betas"]
    for t, b in true.items():
        for k, v in b.items():
            assert abs(res[t][k] - v) < 0.05           # recovered
        assert res[t]["r2"] > 0.95                      # low-noise construction


def test_univariate_raw_betas_double_count_vs_orthogonal():
    # a stock that is PURE market should read ~1 market and ~0 elsewhere in the
    # orthogonal model, but the univariate growth/size betas are inflated by the
    # market collinearity — the double-count the orthogonalization removes.
    rng = np.random.default_rng(2)
    n = 600
    m = rng.normal(0, 0.01, n)
    F = pd.DataFrame({"mkt": m, "growth": 0.9 * m + rng.normal(0, 0.003, n),
                      "size": 0.8 * m + rng.normal(0, 0.004, n)}, index=_idx(n))
    px = pd.DataFrame({"PUREMKT": (1 + m).cumprod()}, index=_idx(n))
    orth = fe.stock_betas(px, F, window=n, min_obs=100, max_abs=5.0)["betas"]["PUREMKT"]
    raw = fe.raw_betas(px, F, window=n, min_obs=100, max_abs=5.0)["PUREMKT"]
    assert abs(orth["mkt"] - 1.0) < 0.05 and abs(orth["growth"]) < 0.1 and abs(orth["size"]) < 0.1
    assert raw["growth"] > 0.5 and raw["size"] > 0.5    # univariate over-attributes the market move


def test_portfolio_exposure_aggregates_and_flags_concentration():
    keys = fe.FACTOR_ORDER
    vols = {"mkt": 0.12, "growth": 0.06, "size": 0.10, "rates": 0.09,
            "usd": 0.05, "oil": 0.34, "btc": 0.34}
    fcov = pd.DataFrame(np.diag([vols[k] ** 2 for k in keys]), index=keys, columns=keys)
    betas = {"A": {k: 0.0 for k in keys}, "B": {k: 0.0 for k in keys}}
    betas["A"]["mkt"] = betas["B"]["mkt"] = 1.0         # two names, both pure market = ONE bet
    out = fe.portfolio_exposure({"A": 0.5, "B": 0.5}, betas, fcov)
    assert abs(out["betas"]["mkt"] - 1.0) < 1e-9
    assert out["top_factor"] == "mkt" and out["top_share"] > 0.99
    assert out["verdict"] == "concentrated"
    rc = out["risk_contrib"]
    assert abs(sum(v for v in rc.values() if v is not None) - 1.0) < 1e-6   # risk splits to 1


def test_portfolio_exposure_balanced_book():
    keys = fe.FACTOR_ORDER
    fcov = pd.DataFrame(np.diag([0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12]),
                        index=keys, columns=keys) ** 2
    # one name loads market, the other loads oil — genuinely two different bets
    betas = {"A": {k: 0.0 for k in keys}, "B": {k: 0.0 for k in keys}}
    betas["A"]["mkt"] = 1.0
    betas["B"]["oil"] = 1.0
    out = fe.portfolio_exposure({"A": 0.5, "B": 0.5}, betas, fcov)
    assert out["top_share"] < 0.7                       # not a single dominating factor


def test_snapshot_smoke():
    snap = fe.snapshot()
    assert isinstance(snap, dict)
    if "betas" in snap:                                 # store has data in CI
        assert snap["n"] > 0 and "factor_cov" in snap and snap["factors"]
        mk = [r["mkt"] for r in snap["betas"].values() if r.get("mkt") is not None]
        assert 0.6 < float(np.median(mk)) < 1.2         # market beta cross-section ~ centered on 1
        assert {f["key"] for f in snap["factors"]} <= set(fe.FACTOR_ORDER)
        # the client relies on confidence tiers being attached to factor metadata
        assert all("tier" in f and "scope" in f for f in snap["factors"])
    else:
        assert snap.get("verdict") == "unknown"


def test_compute_exposure_covers_etfs_self_consistently():
    out = fe.compute_exposure()
    if out is None:                                     # no store in this env — skip
        return
    b = out["betas"]
    # the factor proxies, as ETF holdings, must recover beta=1 to their own factor
    if "SPY" in b:
        assert b["SPY"]["is_etf"] is True and abs(b["SPY"]["mkt"] - 1.0) < 0.1
    if "TLT" in b:
        assert abs(b["TLT"]["rates"] - 1.0) < 0.15      # TLT IS the rates factor
    if "XLE" in b:
        assert b["XLE"]["oil"] > 0                       # energy ETF loads positively on oil
    # every record carries the client-required fields
    rec = next(iter(b.values()))
    assert {"name", "sector", "is_etf", "raw", "r2", "idio_vol"} <= set(rec)
