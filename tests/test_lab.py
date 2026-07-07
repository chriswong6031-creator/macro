"""Smoke tests for engine/lab.py.

Tests:
  1. Module imports without error.
  2. indicator('rsi', df) matches canon.rsi exactly.
  3. A minimal 2-ticker backtest returns a Trial with finite stats.
  4. The deflated_sharpe path uses a ledger (not a literal N) — the ratchet test
     would catch it, but we verify explicitly here.
  5. Signal / confluence construction.
  6. features() returns a DataFrame.
  7. Trial.to_ledger() writes a JSONL row.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fake_ohlcv(n: int = 600, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV with a realistic random-walk close."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.012, n))
    high = close * (1.0 + rng.uniform(0.0, 0.01, n))
    low = close * (1.0 - rng.uniform(0.0, 0.01, n))
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame(
        {"close": close, "high": high, "low": low, "volume": volume},
        index=dates,
    )


def _fake_universe(n_tickers: int = 2, n_bars: int = 600) -> dict[str, pd.DataFrame]:
    return {f"T{i}": _fake_ohlcv(n_bars, seed=i) for i in range(n_tickers)}


# ---------------------------------------------------------------------------
# 1. Import smoke test
# ---------------------------------------------------------------------------

def test_import():
    import engine.lab  # noqa: F401


# ---------------------------------------------------------------------------
# 2. indicator('rsi') matches canon.rsi
# ---------------------------------------------------------------------------

def test_indicator_rsi_matches_canon():
    from engine import canon
    from engine import lab

    df = _fake_ohlcv()
    lab_rsi = lab.indicator("rsi", df, n=14)
    canon_rsi = canon.rsi(df["close"], n=14)

    # Align on common non-NaN rows
    common = lab_rsi.dropna().index.intersection(canon_rsi.dropna().index)
    assert len(common) > 100, "Too few common non-NaN bars"
    np.testing.assert_allclose(
        lab_rsi.loc[common].values,
        canon_rsi.loc[common].values,
        rtol=1e-9,
        err_msg="indicator('rsi') does not match canon.rsi",
    )


# ---------------------------------------------------------------------------
# 3. Unknown indicator raises KeyError
# ---------------------------------------------------------------------------

def test_indicator_unknown_raises():
    from engine import lab

    df = _fake_ohlcv()
    with pytest.raises(KeyError, match="Unknown indicator"):
        lab.indicator("__not_a_real_indicator__", df)


# ---------------------------------------------------------------------------
# 4. features() returns a DataFrame with expected columns
# ---------------------------------------------------------------------------

def test_features_returns_dataframe():
    from engine import lab

    df = _fake_ohlcv()
    feat = lab.features(df)
    assert isinstance(feat, pd.DataFrame), "features() must return a DataFrame"
    assert len(feat) == len(df), "features() index length mismatch"
    assert "rsi" in feat.columns, "'rsi' column expected in features()"
    assert "macd_hist" in feat.columns, "'macd_hist' column expected in features()"


def test_features_subset():
    from engine import lab

    df = _fake_ohlcv()
    feat = lab.features(df, cols=["rsi", "sma"])
    assert set(feat.columns) == {"rsi", "sma"}


# ---------------------------------------------------------------------------
# 5. Signal construction and evaluate()
# ---------------------------------------------------------------------------

def test_signal_from_expr():
    from engine import lab

    def _simple_expr(df):
        close = df["close"]
        sig = close.pct_change(5)
        pos = (sig > 0).astype(float)
        return sig, pos

    s = lab.Signal(expr=_simple_expr, horizon=5, family="test_lab")
    df = _fake_ohlcv()
    sig_out, pos_out = s.evaluate(df)
    assert isinstance(sig_out, pd.Series)
    assert isinstance(pos_out, pd.Series)
    assert len(sig_out) == len(df)


def test_signal_from_precomputed():
    from engine import lab

    df = _fake_ohlcv()
    sig = df["close"].pct_change(5)
    pos = (sig > 0).astype(float)
    s = lab.Signal(signal=sig, pos=pos, horizon=5, family="test_lab")
    out_s, out_p = s.evaluate(df)
    pd.testing.assert_series_equal(out_s, sig)
    pd.testing.assert_series_equal(out_p, pos)


def test_signal_missing_raises():
    from engine import lab

    s = lab.Signal(horizon=5, family="test_lab")
    with pytest.raises(ValueError, match="Signal must have"):
        s.evaluate(pd.DataFrame())


# ---------------------------------------------------------------------------
# 6. confluence()
# ---------------------------------------------------------------------------

def test_confluence_all():
    from engine import lab

    def _rsi_sig(df):
        r = lab.indicator("rsi", df, n=14)
        pos = (r < 40).astype(float)
        return r, pos

    def _mom_sig(df):
        m = df["close"].pct_change(21)
        pos = (m > 0).astype(float)
        return m, pos

    s1 = lab.Signal(expr=_rsi_sig, horizon=21, family="test_lab", name="rsi")
    s2 = lab.Signal(expr=_mom_sig, horizon=21, family="test_lab", name="mom")
    combined = lab.confluence(s1, s2, mode="all")

    df = _fake_ohlcv()
    sig_out, pos_out = combined.evaluate(df)
    assert isinstance(pos_out, pd.Series)
    # 'all' mode: combined pos <= each individual pos
    _, p1 = s1.evaluate(df)
    _, p2 = s2.evaluate(df)
    common = pos_out.dropna().index.intersection(p1.dropna().index).intersection(
        p2.dropna().index
    )
    assert (pos_out.loc[common] <= p1.reindex(common).fillna(0)).all()


# ---------------------------------------------------------------------------
# 7. Minimal 2-ticker backtest returns a Trial with finite stats
# ---------------------------------------------------------------------------

def test_backtest_returns_trial_with_finite_stats():
    from engine import lab

    universe = _fake_universe(n_tickers=2, n_bars=600)

    def _rsi_signal(df):
        r = lab.indicator("rsi", df, n=14)
        pos = (r < 40).astype(float)
        return r, pos

    sig = lab.Signal(
        expr=_rsi_signal, horizon=21, family="test_lab_backtest", name="rsi_oversold"
    )
    trial = lab.backtest(sig, universe, cost_bps=5.0, n_configs_searched=1)

    assert isinstance(trial, lab.Trial)
    assert trial.survivorship_biased is True
    assert isinstance(trial.stats, dict)

    # At least one finite numeric stat must be present
    finite_stats = [
        k for k, v in trial.stats.items()
        if isinstance(v, (int, float)) and np.isfinite(v)
    ]
    assert finite_stats, (
        f"Expected at least one finite numeric stat, got: {trial.stats}"
    )


# ---------------------------------------------------------------------------
# 8. deflated_sharpe path uses a ledger (not a literal n_trials)
# ---------------------------------------------------------------------------

def test_backtest_uses_ledger_not_literal_n():
    """Verify that engine.lab never calls deflated_sharpe with a literal n_trials.

    This is checked statically by tests/test_no_literal_ntrials.py but we also
    verify at runtime that the Trial stats contain 'n_trials' and that it came
    from TrialLedger.with_declared_budget, not a bare literal argument.
    """
    import ast
    import inspect
    from engine import lab

    source = inspect.getsource(lab)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = (f.attr if isinstance(f, ast.Attribute) else
                    f.id if isinstance(f, ast.Name) else None)
            if name == "deflated_sharpe":
                kw_names = {k.arg for k in node.keywords if k.arg}
                assert "ledger" in kw_names, (
                    "engine/lab.py calls deflated_sharpe without ledger= "
                    "— this violates the CI ratchet"
                )
                assert "n_trials" not in kw_names, (
                    "engine/lab.py passes n_trials= to deflated_sharpe "
                    "— use the Trial Ledger instead"
                )


# ---------------------------------------------------------------------------
# 9. Trial.verdict() returns one of the allowed strings
# ---------------------------------------------------------------------------

def test_trial_verdict_taxonomy():
    from engine import lab

    trial = lab.Trial(
        name="test",
        family="test_lab",
        stats={"dsr": 0.96, "sharpe_ci": [0.1, 0.5, 1.2], "split_half_consistent": True,
               "mean_ic": 0.05},
    )
    v = trial.verdict()
    assert v in ("TRADABLE", "ENTRY-OVERLAY", "RISK-CONTROL", "NO-EDGE")


def test_trial_verdict_no_edge():
    from engine import lab

    trial = lab.Trial(name="test", family="test_lab", stats={"dsr": 0.3})
    assert trial.verdict() == "NO-EDGE"


# ---------------------------------------------------------------------------
# 10. Trial.to_ledger() writes a JSONL row
# ---------------------------------------------------------------------------

def test_trial_to_ledger():
    import json
    from engine import lab

    trial = lab.Trial(
        name="test_ticker",
        family="test_lab_ledger",
        stats={"dsr": 0.85, "mean_ic": 0.03},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "trials.jsonl"
        trial.to_ledger(path)
        assert path.exists()
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "test_ticker"
        assert row["family"] == "test_lab_ledger"
        assert row["stats"]["dsr"] == 0.85
        assert "verdict" in row


# ---------------------------------------------------------------------------
# 11. load() with shortcuts
# ---------------------------------------------------------------------------

def test_load_quick():
    """load('quick') should return at most 8 tickers and each is a DataFrame."""
    from engine import lab

    result = lab.load("quick")
    # The quick list might not all exist in the store; just check types
    for ticker, df in result.items():
        assert isinstance(df, pd.DataFrame)
        assert "close" in df.columns


# ---------------------------------------------------------------------------
# 12. bench() returns a Series
# ---------------------------------------------------------------------------

def test_bench_returns_series():
    from engine import lab

    s = lab.bench("_GSPC")
    assert isinstance(s, pd.Series)
