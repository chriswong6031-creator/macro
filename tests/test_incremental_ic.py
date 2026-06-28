"""Tests for the incremental-IC layer (engine/validation.cross_sectional_resid / incremental_ic).

The residual must be orthogonal to the factors it was neutralized against, and a signal that
IS just a factor (plus noise) must lose most of its IC after neutralization."""
import numpy as np
import pandas as pd
import pytest

from engine import validation as V


def test_resid_orthogonal_to_loadings():
    rng = np.random.default_rng(1)
    n = 200
    tickers = [f"T{i}" for i in range(n)]
    load = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)}, index=tickers)
    sig = pd.Series(0.7 * load["f1"] - 0.4 * load["f2"] + rng.normal(0, 0.5, n), index=tickers)
    resid = V.cross_sectional_resid(sig, load)
    # the residual is (numerically) orthogonal to every loading
    for c in load.columns:
        assert abs(np.corrcoef(resid.values, load.loc[resid.index, c].values)[0, 1]) < 1e-6


def test_incremental_ic_collapses_for_redundant_signal():
    """A signal that is a factor + small noise has high RAW IC (because the factor predicts)
    but its INCREMENTAL IC collapses toward 0 once that factor is neutralized out."""
    rng = np.random.default_rng(2)
    n = 120
    tickers = [f"T{i}" for i in range(n)]
    sig_by, fwd_by, load_by = {}, {}, {}
    for di in range(10):
        f = pd.Series(rng.normal(size=n), index=tickers)            # the owned factor
        fwd = pd.Series(0.02 * f + rng.normal(0, 0.01, n), index=tickers)  # factor predicts return
        sig = pd.Series(f + rng.normal(0, 0.05, n), index=tickers)  # signal ≈ the factor
        d = f"2024-{di+1:02d}-01"
        sig_by[d] = sig; fwd_by[d] = fwd
        load_by[d] = pd.DataFrame({"owned": f}, index=tickers)
    r = V.incremental_ic(sig_by, fwd_by, load_by, periods_per_year=12)
    raw, inc = r["raw"]["mean_ic"], r["incremental"]["mean_ic"]
    assert raw is not None and inc is not None
    assert raw > 0.2                              # raw IC is strong (signal ≈ predictive factor)
    assert abs(inc) < 0.5 * raw                   # incremental collapses once the factor is removed


def test_incremental_ic_survives_for_independent_signal():
    """An independent predictive signal keeps its IC after neutralizing unrelated factors."""
    rng = np.random.default_rng(3)
    n = 120
    tickers = [f"T{i}" for i in range(n)]
    sig_by, fwd_by, load_by = {}, {}, {}
    for di in range(10):
        true = pd.Series(rng.normal(size=n), index=tickers)
        fwd = pd.Series(0.02 * true + rng.normal(0, 0.01, n), index=tickers)
        sig = pd.Series(true + rng.normal(0, 0.05, n), index=tickers)
        unrelated = pd.Series(rng.normal(size=n), index=tickers)    # independent of sig & fwd
        d = f"2024-{di+1:02d}-01"
        sig_by[d] = sig; fwd_by[d] = fwd
        load_by[d] = pd.DataFrame({"unrelated": unrelated}, index=tickers)
    r = V.incremental_ic(sig_by, fwd_by, load_by, periods_per_year=12)
    raw, inc = r["raw"]["mean_ic"], r["incremental"]["mean_ic"]
    assert inc > 0.6 * raw                         # neutralizing an unrelated factor barely dents IC
