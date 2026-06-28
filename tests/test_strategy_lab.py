"""Tests for engine.strategy_lab — causality (no look-ahead), sign alignment, and
the PIT SUE panel. The backtest's whole value rests on these legs being causal and
sign-aligned (positive IC => constructive), so guard both."""
import numpy as np
import pandas as pd
import pytest

from engine import strategy_lab as sl


def _panel(n=420, m=18, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    steps = rng.normal(0.0005, 0.02, size=(n, m))
    px = 100 * np.exp(np.cumsum(steps, axis=0))
    return pd.DataFrame(px, index=idx, columns=[f"T{i:02d}" for i in range(m)])


@pytest.mark.parametrize("name", list(sl.STRATEGIES))
def test_leg_is_causal(name):
    """A leg's value at asof must not change when FUTURE bars are appended."""
    closes = _panel(n=820)                    # long enough for the 2y-history legs (seasonality)
    asof = closes.index[600]
    fn = sl.STRATEGIES[name]["fn"]
    before = fn(closes, asof)
    # append 80 future bars and recompute at the SAME asof
    future = _panel(n=80, m=closes.shape[1], seed=99)
    future.index = pd.bdate_range(closes.index[-1] + pd.Timedelta(days=1), periods=80)
    future.columns = closes.columns
    after = fn(pd.concat([closes, future]), asof)
    common = before.index.intersection(after.index)
    assert len(common) >= 5, f"{name} produced no output on the test panel"
    assert np.allclose(before.loc[common].to_numpy(),
                       after.loc[common].to_numpy(), equal_nan=True), \
        f"{name} changed at asof when future bars were appended -> look-ahead"


def test_momentum_sign():
    """mom_12_1 ranks a steady up-trend above a steady down-trend."""
    idx = pd.bdate_range("2015-01-01", periods=320)
    up = pd.Series(100 * np.exp(np.linspace(0, 0.5, 320)), index=idx)
    dn = pd.Series(100 * np.exp(np.linspace(0, -0.5, 320)), index=idx)
    closes = pd.DataFrame({"UP": up, "DN": dn})
    s = sl.mom_12_1(closes, idx[-1])
    assert s["UP"] > s["DN"]


def test_reversal_sign():
    """rev_1m and below_200dma score a recent faller / below-MA name HIGHER
    (sign aligned so 'more washed out' = constructive)."""
    idx = pd.bdate_range("2015-01-01", periods=320)
    flat = pd.Series(100.0, index=idx)
    dropper = flat.copy()
    dropper.iloc[-21:] = np.linspace(100, 85, 21)      # fell over the last month
    closes = pd.DataFrame({"FLAT": flat, "DROP": dropper})
    assert sl.rev_1m(closes, idx[-1])["DROP"] > sl.rev_1m(closes, idx[-1])["FLAT"]
    assert sl.below_200dma(closes, idx[-1])["DROP"] > sl.below_200dma(closes, idx[-1])["FLAT"]


def test_forward_excess_is_demeaned():
    closes = _panel()
    fwd = sl.forward_excess(closes, 300, 63)
    assert abs(float(fwd.mean())) < 1e-9          # market-neutral by construction


def test_build_sue_panel():
    rows = []
    for tk in ["AAA", "BBB"]:
        for q in range(12):
            pe = pd.Timestamp("2018-03-31") + pd.DateOffset(months=3 * q)
            rows.append({"ticker": tk, "period_end": pe,
                         "eps_q": 1.0 + 0.1 * q + (0.3 if tk == "AAA" else 0.0),
                         "asof_date": pe + pd.Timedelta(days=45)})
    panel = sl.build_sue_panel(pd.DataFrame(rows))
    assert not panel.empty
    assert set(panel.columns) <= {"AAA", "BBB"}
    # sue_asof returns only reports within the staleness window
    asof = panel.index.max() + pd.Timedelta(days=10)
    sig = sl.sue_asof(panel, asof, max_stale_days=130)
    assert len(sig) >= 1


def test_signal_lab_still_builds():
    """The new confirmer row must not break the registry assembly."""
    from engine import signal_lab
    assert any("Cross-sectional momentum" in r["name"] for r in signal_lab.REGISTRY)
    for r in signal_lab.REGISTRY:
        assert r["tier"] in {"scored", "confirmer", "display", "killed", "pending"}
