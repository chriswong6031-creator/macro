"""Phase-0: rate-timed VALUE-vs-GROWTH tilt — READ-ONLY research.

Tests the measured prior (QUANT_FACTOR_EXPANSION §6): yield-rising → value
(t=+3.0, holds all four sub-periods 2000→2026); Q1→value / Q4→growth (~1.9% spread).
Construct the long/short value-minus-growth sleeve (IWD − IWF) and TIME it on the
10y-yield direction; judge by Sharpe + DSR + Newey-West t + per-sub-period sign.

  vg     = IWD.pct_change() − IWF.pct_change()      (value-minus-growth, daily L/S)
  signal = sign(Δ us10y over W)                      (rising yields → long value)
  strat  = signal.shift(1) · vg − turnover cost      (act next bar, no look-ahead)

Run: ./.venv/bin/python scripts/value_growth_phase0.py
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
    ret_moments, deflated_sharpe, dsr_verdict, newey_west_tstat, _sharpe, _maxdd,
)
from lib import store  # noqa: E402

ANN = 252
COST_BPS = 3.0           # L/S two-ETF, one-way
GRID = {"21d": 21, "63d": 63, "126d": 126}
HEADLINE = "63d"
START = "2000-06-01"
SUBS = [("2000-06..2006", "2000-06-01", "2006-12-31"),
        ("2007..2012", "2007-01-01", "2012-12-31"),
        ("2013..2018", "2013-01-01", "2018-12-31"),
        ("2019..2026", "2019-01-01", "2026-12-31")]


def sharpe_of(strat: pd.Series) -> float:
    s = strat.dropna()
    return _sharpe(s.to_numpy(), ANN) if len(s) > 30 else float("nan")


def main() -> None:
    f = build_features()
    iwd, iwf, y10 = f["IWD"], f["IWF"], f["us10y"]
    vg = (iwd.pct_change() - iwf.pct_change())          # value-minus-growth daily L/S
    print("=" * 90)
    print("RATE-TIMED VALUE-vs-GROWTH (IWD−IWF) — Phase-0  (from %s)" % START)
    print("  thesis: rising 10y yield → tilt to VALUE; falling → GROWTH")
    print("=" * 90)

    print("\n### UNCONDITIONAL value-minus-growth premium (is there a base drift?)")
    nw0 = newey_west_tstat(vg.loc[START:].dropna(), lags=5)
    print(f"  mean daily IWD−IWF = {nw0['mean']:+.5f}  ann≈{nw0['mean']*ANN*100:+.1f}%  "
          f"HAC t={nw0['t']}  (always-long-value Sharpe={sharpe_of(vg.loc[START:]):+.2f})")

    print("\n### RATE-TIMED L/S — grid of yield-change windows (net of cost)")
    strats = {}
    for nm, W in GRID.items():
        sig = np.sign(y10.diff(W))
        pos = sig.shift(1)                              # act next bar
        turn = pos.diff().abs().fillna(0)
        strat = (pos * vg - (COST_BPS / 1e4) * turn).loc[START:]
        strats[nm] = strat
        m = strat.dropna()
        print(f"  yields Δ{nm:<5}  Sharpe={sharpe_of(strat):+5.2f}  "
              f"ann={m.mean()*ANN*100:+5.1f}%  MaxDD={_maxdd(m.to_numpy())*100:+6.1f}%  "
              f"long-value {float((pos.loc[START:]>0).mean())*100:.0f}% of days")

    strat = strats[HEADLINE]
    print("\n### HEADLINE %s — significance + multiple-testing" % HEADLINE)
    nw = newey_west_tstat(strat.dropna(), lags=5)
    mom = ret_moments(strat)
    if mom:
        sr, sk, ku, n = mom
        d = deflated_sharpe(sr, sk, ku, n, n_trials=len(GRID), trading_year=ANN)
        print(f"  HAC t={nw['t']} (p={nw['p']})   DSR={d['dsr']:.4f} (n_trials={d['n_trials']}) "
              f"-> {dsr_verdict(d['dsr'])}")

    print("\n### PER-SUB-PERIOD SIGN (prior claims it holds in ALL FOUR)")
    holds = 0
    for lab, a, b in SUBS:
        sh = sharpe_of(strat.loc[a:b])
        holds += int(sh > 0)
        print(f"  {lab:<16} Sharpe={sh:+.2f}  {'OK' if sh > 0 else 'NEG'}")
    print(f"  -> positive in {holds}/4 sub-periods")

    print("\n### QUAD CONDITIONING — Q1 should favour value, Q4 growth (~1.9% spread prior)")
    quad = store.read("regime", "regime_history")["quad"].reindex(f.index).ffill(limit=5)
    for q in ("Q1", "Q2", "Q3", "Q4"):
        seg = vg.where(quad == q).loc[START:].dropna()
        if len(seg) > 60:
            print(f"  [{q}] mean IWD−IWF ann≈{seg.mean()*ANN*100:+5.1f}%  (n={len(seg)})")

    print("\n" + "=" * 90)
    print("READ-ME: a SCORED tilt needs DSR>=0.90 + HAC t supportive + same-sign in the sub-periods.")
    print("  Even if it clears, it is a relative VALUE/GROWTH tilt (factors.html tile), not index timing.")
    print("=" * 90)


if __name__ == "__main__":
    main()
