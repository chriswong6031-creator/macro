"""RC-R11 washout counter-read (engine/oracle/washout_counterread.py).

Network-free: synthetic closes drive the 63d-drawdown-percentile path; growth score is
passed directly. A calm growth score is quiet; an extreme growth score + a deep-drawdown
index fires the two-sided chip; authority stays all-False throughout.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.oracle import washout_counterread as wc


@pytest.fixture(autouse=True)
def _no_ihm(monkeypatch):
    """Isolate the PRICE path — the repo ships a real data/index_momentum/latest.json that
    would otherwise leak IHM hits into every case. Tests that want the IHM path override this."""
    monkeypatch.setattr(wc, "_ihm_depths", lambda: [])


def _deep_then_recover():
    """A 12y steady low-vol grind (so natural 63d drawdowns stay shallow) that ends in a
    sharp engineered −25% drawdown — unambiguously the deepest decile of its own history."""
    idx = pd.bdate_range("2014-01-02", periods=252 * 12)
    rng = np.random.default_rng(1)
    s = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.003, len(idx))), index=idx)
    tail = np.linspace(0, -0.25, 40)
    s.iloc[-40:] = s.iloc[-41] * (1 + tail)
    return s


def _shallow():
    """A steady low-vol grind ending near its highs — never a depth extreme."""
    idx = pd.bdate_range("2014-01-02", periods=252 * 12)
    rng = np.random.default_rng(2)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.003, len(idx))), index=idx)


def test_quiet_when_growth_calm():
    closes = {"SPY": _deep_then_recover(), "QQQ": _deep_then_recover(), "XLK": _shallow()}
    p = wc.compute(growth_score=40.0, growth_band="calm", as_of="2026-07-10", closes=closes)
    assert p["show"] is False              # deep drawdown but growth not extreme → no chip
    assert p["growth_extreme"] is False


def test_fires_on_growth_extreme_plus_price_depth():
    closes = {"SPY": _deep_then_recover(), "QQQ": _deep_then_recover(), "XLK": _shallow()}
    p = wc.compute(growth_score=91.0, growth_band="risk-off", as_of="2026-06-26", closes=closes)
    assert p["show"] is True
    assert "SPY" in p["price_hits"] and "QQQ" in p["price_hits"]
    assert "XLK" not in p["price_hits"]    # XLK near highs → not a hit
    assert "two-sided" in p["message_en"] and "投降区" in p["message_zh"]


def test_quiet_when_growth_extreme_but_no_depth():
    closes = {"SPY": _shallow(), "QQQ": _shallow(), "XLK": _shallow()}
    p = wc.compute(growth_score=91.0, growth_band="risk-off", as_of="x", closes=closes)
    # shallow prices, IHM stubbed empty → no depth hits → quiet even with extreme growth
    assert p["show"] is False


def test_fires_on_ihm_momentum_washout_path(monkeypatch):
    """The masterplan's OR: growth-extreme + an IHM cohort washout (no price-depth extreme)
    still fires — the 2026-06-26 shape (shallow index pullback, cohort washed out)."""
    monkeypatch.setattr(wc, "_ihm_depths", lambda: [
        {"index": "MAG7", "metric": "ihm_macd_hist_depth_pctile", "depth_pctile": 39.0,
         "reason": "washout_turn", "washout_turn": True, "extreme": True}])
    p = wc.compute(growth_score=90.8, growth_band="risk-off", as_of="2026-06-26",
                   closes={"SPY": _shallow(), "QQQ": _shallow(), "XLK": _shallow()})
    assert p["show"] is True
    assert p["price_hits"] == [] and p["ihm_hits"] == ["MAG7"]
    assert "washout-turn" in p["message_en"]


def test_authority_all_false_and_never_gates():
    p = wc.compute(growth_score=91.0, closes={"SPY": _deep_then_recover()})
    for k in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert p["authority"][k] is False
    # the chip copy never claims validation / forecast (the disclaimer's meta-sentence
    # "the word 'validated' does not appear on these surfaces" is the policy, not a claim).
    assert "validated" not in (p.get("message_en") or "").lower()
    assert "two-sided" in (p.get("message_en") or "")


def test_dd_percentile_depth_ranking():
    deep = wc.dd_percentile(_deep_then_recover())
    shallow = wc.dd_percentile(_shallow())
    assert deep is not None and shallow is not None
    assert deep["depth_pctile"] > shallow["depth_pctile"]
    assert deep["extreme"] is True and shallow["extreme"] is False


def test_thin_history_returns_none():
    idx = pd.bdate_range("2025-01-02", periods=200)
    assert wc.dd_percentile(pd.Series(range(200), index=idx, dtype=float)) is None
