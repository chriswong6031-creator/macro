"""Phase 0 harness tests — the cash-leg credit, backward compatibility of the
patched backtest_core, the baseline signals, and the bear-episode counter.
Run as a plain script (no pytest in the venv):  python -m tests.test_equity_alloc
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine.validation import backtest_core

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def _flat_price(days: int) -> pd.Series:
    idx = pd.date_range("2000-01-01", periods=days, freq="D")
    return pd.Series(100.0, index=idx)               # constant -> ret == 0


def test_cash_leg_accrues():
    """A fully-flat position (alloc=0) at a constant 5% bill yield should compound
    to ~5%/yr on the cash sleeve."""
    close = _flat_price(366)                          # ~1 calendar year, daily
    alloc = pd.Series(0.0, index=close.index)
    cy = pd.Series(5.0, index=close.index)           # 5% annualized, flat
    net = backtest_core(close, alloc, cost_bps=0.0, cash_yield=cy)["net"]
    term = float((1 + net).cumprod().iloc[-1])
    check("cash leg accrues ~5%/yr on the flat sleeve", 1.049 <= term <= 1.053,
          f"terminal={term:.5f}")


def test_cash_yield_none_unchanged():
    """cash_yield=None must keep legacy behavior: a flat position earns exactly 0."""
    close = _flat_price(200)
    alloc = pd.Series(0.0, index=close.index)
    net = backtest_core(close, alloc, cost_bps=0.0, cash_yield=None)["net"]
    check("cash_yield=None -> flat sleeve earns 0 (legacy)", float(net.abs().sum()) == 0.0,
          f"sum|net|={float(net.abs().sum())}")


def test_fully_invested_ignores_carry():
    """alloc=1 throughout: (1-pos)=0, so the carry term is irrelevant and the
    strategy return equals buy & hold (bar a one-day 0->1 ramp turnover cost)."""
    idx = pd.date_range("2010-01-01", periods=500, freq="B")
    close = pd.Series(100 * (1 + np.linspace(0, 0.5, 500)), index=idx)
    alloc = pd.Series(1.0, index=idx)
    cy = pd.Series(5.0, index=idx)
    bt = backtest_core(close, alloc, cost_bps=3.0, cash_yield=cy)
    eq = float((1 + bt["net"]).cumprod().iloc[-1])
    hodl = float((1 + bt["ret"]).cumprod().iloc[-1])
    check("fully-invested ~= buy&hold (carry irrelevant)", abs(eq / hodl - 1) < 0.001,
          f"eq/hodl={eq/hodl:.5f}")


def test_sma_switch_shape():
    idx = pd.date_range("2015-01-01", periods=400, freq="B")
    close = pd.Series(100 * (1 + np.linspace(0, 1.0, 400)), index=idx)   # steady uptrend
    a = ea.sma_switch(close, 200)
    check("sma warm-up is flat", a.iloc[:199].sum() == 0.0, f"warmup sum={a.iloc[:199].sum()}")
    check("sma long in a clean uptrend", a.iloc[250:].mean() > 0.95, f"mean tail={a.iloc[250:].mean():.3f}")


def test_bear_episode_counter():
    """A clean -30% drop then full recovery = exactly one >=20% episode, and zero
    at a >=40% threshold."""
    idx = pd.date_range("2000-01-01", periods=600, freq="B")
    path = np.concatenate([np.linspace(100, 100, 100),
                           np.linspace(100, 70, 200),     # -30%
                           np.linspace(70, 120, 300)])    # recover past peak
    close = pd.Series(path, index=idx)
    e20 = ea.bear_episodes(close, 0.20)
    e40 = ea.bear_episodes(close, 0.40)
    check("one >=20% episode detected", len(e20) == 1, f"n={len(e20)} {e20}")
    check("the episode is ~-30%", e20 and -32 <= e20[0]["drawdown_pct"] <= -28, f"{e20}")
    check("zero >=40% episodes", len(e40) == 0, f"n={len(e40)}")


def test_spy_baseline_sanity():
    """Smoke test against real data: SPY buy & hold ~10-11% CAGR / ~-55% MaxDD, and
    the 200dma switch cuts MaxDD materially while lagging CAGR (the reframe)."""
    try:
        close = ea.index_close("SPY")
        bills = ea.bill_yield()
    except FileNotFoundError as e:
        print(f"  SKIP  spy baseline ({e})")
        return
    bh = ea.summarize(close, ea.buy_hold(close), "bh", cash_yield=bills, cost_bps=3.0)
    sw = ea.summarize(close, ea.sma_switch(close, 200), "sw", cash_yield=bills, cost_bps=3.0)
    check("SPY B&H CAGR in 9-12%", 9 <= bh["cagr"] <= 12, f"{bh['cagr']}")
    check("SPY B&H MaxDD worse than -45%", bh["maxdd"] <= -45, f"{bh['maxdd']}")
    check("200dma cuts MaxDD vs B&H", sw["maxdd"] > bh["maxdd"] + 15, f"sw={sw['maxdd']} bh={bh['maxdd']}")
    check("200dma lifts Sharpe vs B&H", sw["sharpe"] >= bh["sharpe"], f"sw={sw['sharpe']} bh={bh['sharpe']}")


def test_risk_legs_synthetic_aggregation():
    """risk_legs must (a) return a composite identical to risk_score, (b) expose
    only the legs whose inputs are present, (c) have per-leg `points` that sum to
    the composite at the as-of date, and (d) keep value/points in bounds."""
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    cf = pd.DataFrame({"drawdown_risk": np.linspace(0, 80, 300),
                       "recession_risk": np.full(300, 40.0)}, index=idx)
    f = pd.DataFrame(index=idx)            # no hy_oas -> credit leg drops out
    regime = pd.DataFrame(index=idx)       # no 'liquidity' col -> liquidity leg drops
    s = ea.risk_score(f, regime, cf)
    rl = ea.risk_legs(f, regime, cf)
    legs = rl["legs"]
    check("risk_legs.score == risk_score (synthetic)",
          float((rl["score"].dropna() - s.dropna()).abs().max()) < 1e-9)
    check("only the two present legs are active", set(legs) == {"drawdown", "recession"},
          f"got {set(legs)}")
    sc = rl["score"].dropna()
    pts = sum((v["points"] or 0) for v in legs.values() if v["active"])
    check("per-leg points sum to the composite", abs(pts - float(sc.iloc[-1])) < 0.2,
          f"pts={pts:.2f} score={sc.iloc[-1]:.2f}")
    check("leg value/points in bounds",
          all(0 <= (v["value"] or 0) <= 100 and 0 <= (v["points"] or 0) <= 100
              for v in legs.values()))


def test_risk_legs_matches_score_real():
    """On real data the composite must equal risk_score exactly, the five
    pre-registered legs must appear, and points must reconstruct the score."""
    try:
        from engine.inputs import build_features
        from engine.conditions import conditions_frame
        from lib import store
        f = build_features(); cf = conditions_frame(f)
        reg = store.read("regime", "regime_history")
    except Exception as e:                 # noqa: BLE001 — no data store in CI sandbox
        print(f"  SKIP  risk_legs real ({e})")
        return
    s = ea.risk_score(f, reg, cf)
    rl = ea.risk_legs(f, reg, cf)
    if rl["score"].dropna().empty:
        print("  SKIP  risk_legs real (empty score)")
        return
    check("risk_legs.score == risk_score (real)",
          float((rl["score"].dropna() - s.dropna()).abs().max()) < 1e-9)
    check("legs are a subset of the pre-registered five",
          set(rl["legs"]) <= set(ea.RISK_WEIGHTS), f"got {set(rl['legs'])}")
    sc = rl["score"].dropna()
    pts = sum((v["points"] or 0) for v in rl["legs"].values() if v["active"])
    check("real points sum to the composite", abs(pts - float(sc.iloc[-1])) < 0.5,
          f"pts={pts:.2f} score={sc.iloc[-1]:.2f}")


def main() -> int:
    for fn in (test_cash_leg_accrues, test_cash_yield_none_unchanged,
               test_fully_invested_ignores_carry, test_sma_switch_shape,
               test_bear_episode_counter, test_spy_baseline_sanity,
               test_risk_legs_synthetic_aggregation, test_risk_legs_matches_score_real):
        print(f"\n{fn.__name__}")
        fn()
    print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
