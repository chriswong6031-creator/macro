"""Phase-0: regime QUAD × NFCI-direction scenario odds — READ-ONLY research.

Reproduces + stress-tests the measured prior (QUANT_FACTOR_EXPANSION §6 /
SP_VECTOR_VIABILITY:61): conditioning forward SPY odds on quad × NFCI direction
splits the Q1/Q2 hit-rate ~13-20pp (loosening ~72% vs tightening ~55%), holds in
both halves. The engine already uses "NFCI tight-and-tightening → −1" on the dial;
this asks whether the split is (a) reproducible, (b) split-half robust, and
(c) a tradeable de-risk overlay that clears DSR vs buy&hold + the 200dma baseline.

QUAD:  data/regime/regime_history.parquet 'quad' (Q1..Q4, daily 1971-).
NFCI:  engine/conditions.py:762 faithfully reproduced —
       tightening = (nfci_chg>0) & (nfci>0),  nfci_chg = nfci − nfci.shift(65)
No look-ahead: 63d forward return = shift(-63); the overlay acts NEXT bar (backtest_core).

Run: ./.venv/bin/python scripts/quad_nfci_phase0.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.inputs import build_features  # noqa: E402
from engine.validation import (  # noqa: E402
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    block_bootstrap_ci, newey_west_tstat, _sharpe, _maxdd,
)
from lib import store  # noqa: E402

H = 63
NFCI_WIN = 65            # engine config nfci_change_window_d
START = "1993-01-01"
SPLIT = "2012-01-01"
ANN = 252
COST_BPS = 2.0


def odds(mask: pd.Series, fwd: pd.Series, dd: pd.Series) -> dict:
    idx = mask[mask.fillna(False)].index
    fr = fwd.reindex(idx).dropna()
    dv = dd.reindex(idx).dropna()
    if len(fr) == 0:
        return {"n": 0}
    return {"n": len(fr), "hit": float((fr > 0).mean()) * 100,
            "mean": float(fr.mean()) * 100, "p10dd": float(dv.quantile(0.10)) * 100}


def line(label, o, w=26) -> str:
    if o.get("n", 0) == 0:
        return f"  {label:<{w}} (no obs)"
    return (f"  {label:<{w}} n={o['n']:>5}  hit={o['hit']:5.1f}%  "
            f"meanFwd={o['mean']:+5.2f}%  p10DD={o['p10dd']:+6.1f}%")


def metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 60:
        return {"n": len(r)}
    eq = (1.0 + r).cumprod()
    return {"cagr": (eq.iloc[-1] ** (ANN / len(r)) - 1.0) * 100,
            "sharpe": _sharpe(r.to_numpy(), ANN), "maxdd": _maxdd(r.to_numpy()) * 100, "n": len(r)}


def bt_line(label, m, w=22) -> str:
    if m.get("n", 0) < 60:
        return f"  {label:<{w}} (insufficient)"
    return (f"  {label:<{w}} CAGR={m['cagr']:+6.2f}%  Sharpe={m['sharpe']:+5.2f}  "
            f"MaxDD={m['maxdd']:+7.1f}%")


def main() -> None:
    f = build_features()
    spy = f["SPY"]
    nfci = f["nfci"]
    nfci_chg = nfci - nfci.shift(NFCI_WIN)
    tightening = ((nfci_chg > 0) & (nfci > 0)).fillna(False)
    quad = store.read("regime", "regime_history")["quad"].reindex(f.index).ffill(limit=5)
    fwd = spy.shift(-H) / spy - 1.0
    dd = spy.rolling(H).min().shift(-H) / spy - 1.0

    win = (spy.notna()) & (nfci.notna()) & (quad.notna())
    win &= (f.index >= START)
    fwd, dd = fwd.where(win), dd.where(win)
    loos = (~tightening) & win

    print("=" * 92)
    print(f"QUAD × NFCI-DIRECTION SCENARIO ODDS — Phase-0  (SPY {H}d forward, from {START})")
    print(f"  NFCI tightening = (Δ{NFCI_WIN}d>0 & level>0);  tightening on {tightening[win].mean()*100:.0f}% of days")
    print("=" * 92)

    print("\n### CONDITIONAL ODDS by quad × NFCI direction")
    for q in ("Q1", "Q2", "Q3", "Q4"):
        qm = (quad == q) & win
        print(f"  [{q}]")
        print(line("loosening", odds(qm & ~tightening, fwd, dd)))
        print(line("tightening", odds(qm & tightening, fwd, dd)))

    print("\n### HEADLINE — Q1/Q2 (expansion quads) loosening vs tightening")
    q12 = quad.isin(["Q1", "Q2"]) & win
    o_l, o_t = odds(q12 & ~tightening, fwd, dd), odds(q12 & tightening, fwd, dd)
    print(line("Q1/Q2 loosening", o_l))
    print(line("Q1/Q2 tightening", o_t))
    if o_l.get("n") and o_t.get("n"):
        print(f"  -> hit-rate split = {o_l['hit'] - o_t['hit']:+.1f}pp  (prior: ~13-20pp, loose 72 / tight 55)")
    # HAC t-stat of each subsample's mean forward return (overlapping 63d windows)
    for nm, m in [("Q1/Q2 loosening", q12 & ~tightening), ("Q1/Q2 tightening", q12 & tightening)]:
        s = fwd.reindex(m[m].index).dropna()
        nw = newey_west_tstat(s, lags=H)
        print(f"  HAC mean[{nm}] = {nw['mean']:+.4f}  t={nw['t']}  (n={nw['n']})")

    print("\n### SPLIT-HALF (OOS) — Q1/Q2 loosening-vs-tightening hit split")
    for lab, hm in [("1993-2011", f.index < SPLIT), ("2012-2026", f.index >= SPLIT)]:
        hm = pd.Series(hm, index=f.index)
        ol = odds(q12 & ~tightening & hm, fwd, dd)
        ot = odds(q12 & tightening & hm, fwd, dd)
        sp = (ol["hit"] - ot["hit"]) if (ol.get("n") and ot.get("n")) else float("nan")
        print(f"  {lab}: loose hit={ol.get('hit', float('nan')):5.1f}% (n={ol.get('n',0)})  "
              f"tight hit={ot.get('hit', float('nan')):5.1f}% (n={ot.get('n',0)})  split={sp:+.1f}pp")

    # tradeable: de-risk overlay (flat when NFCI tight-and-tightening) -------------
    print("\n### TRADEABLE OVERLAY — long SPY, de-risk when NFCI tight-and-tightening")
    rf = f["us3m"]
    bh = backtest_core(spy, pd.Series(1.0, index=f.index), cost_bps=0.0, cash_yield=rf)["net"].loc[START:]
    dma200 = (spy > spy.rolling(200, min_periods=120).mean()).astype(float)
    a200 = backtest_core(spy, dma200, cost_bps=COST_BPS, cash_yield=rf)["net"].loc[START:]
    variants = {"flat-when-tight": np.where(tightening, 0.0, 1.0),
                "half-when-tight": np.where(tightening, 0.5, 1.0)}
    print(bt_line("SPY buy&hold", metrics(bh)))
    print(bt_line("200dma long/flat", metrics(a200)))
    best = None
    for nm, al in variants.items():
        net = backtest_core(spy, pd.Series(al, index=f.index), cost_bps=COST_BPS, cash_yield=rf)["net"].loc[START:]
        m = metrics(net)
        print(bt_line(f"NFCI {nm}", m))
        if best is None or m["sharpe"] > best[1]["sharpe"]:
            best = (nm, m, net)
    mom = ret_moments(best[2])
    if mom:
        sr, sk, ku, n = mom
        d = deflated_sharpe(sr, sk, ku, n, n_trials=4, trading_year=ANN)  # 2 variants × ~2 thresholds
        s1 = _sharpe(best[2].loc[:SPLIT].dropna().to_numpy(), ANN)
        s2 = _sharpe(best[2].loc[SPLIT:].dropna().to_numpy(), ANN)
        print(f"  best overlay = NFCI {best[0]}:  DSR={d['dsr']:.4f} -> {dsr_verdict(d['dsr'])}")
        print(f"  split-half Sharpe {s1:+.2f} / {s2:+.2f}  same-sign={'YES' if np.sign(s1)==np.sign(s2) else 'NO'}")

    print("\n" + "=" * 92)
    print("READ-ME: descriptive odds = a CONFIRMER panel (already half-wired into the dial). A SCORED")
    print("  overlay needs DSR>=0.90 + same-sign split-half + beating the 200dma baseline net-of-cost.")
    print("=" * 92)


if __name__ == "__main__":
    main()
