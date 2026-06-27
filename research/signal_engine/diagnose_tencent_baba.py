"""DIAGNOSTIC (microscope, NOT a verdict backtest).

Q: at each Tencent false-buy / early-exit and each BABA event over the last ~12
months on the 3D, would the three proposed discriminators have changed the call?
  (a) weekly-confirm     -- is the WEEKLY RSI-MACD up (trend intact) or rolling?
  (b) reclaim-and-hold   -- after a buy, did price reclaim/hold structure, or fade?
  (c) divergence         -- price higher-high vs MACD lower-high (and the bull mirror)

We do NOT score P&L or beat-B&H here. We only check whether the rules separate
the GOOD calls (July-25 bottom, Sep-25 top) from the FAKEOUTS (the bear-leg bounces).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from confluence import compute_signals   # same-dir import

ROOT = Path(__file__).resolve().parents[2]
SINCE = "2025-06-15"


def load_tencent() -> pd.Series:
    d = json.loads((ROOT / "site/hkstockdata/0700.HK.json").read_text())["chart"]
    s = pd.Series(d["c"], index=pd.to_datetime(d["t"]), dtype=float).dropna()
    return s


def load_baba() -> pd.Series:
    return pd.read_parquet(ROOT / "data/yahoo/BABA.parquet")["close"].dropna()


def swing_points(s: pd.Series, w: int = 2):
    """Indices of local maxima / minima on the 3D series (w bars each side)."""
    hi, lo = [], []
    v = s.to_numpy()
    for i in range(w, len(v) - w):
        seg = v[i - w:i + w + 1]
        if v[i] == seg.max():
            hi.append(i)
        if v[i] == seg.min():
            lo.append(i)
    return hi, lo


def divergence_at(i: int, close: pd.Series, macd: pd.Series, hi, lo, look: int = 12):
    """Bearish: last two swing highs <= i show price HH but macd LH. Bull mirror on lows."""
    cv, mv = close.to_numpy(), macd.to_numpy()
    rh = [h for h in hi if h <= i and h > i - look]
    rl = [l for l in lo if l <= i and l > i - look]
    if len(rh) >= 2 and cv[rh[-1]] > cv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]]:
        return "bear-div"
    if len(rl) >= 2 and cv[rl[-1]] < cv[rl[-2]] and mv[rl[-1]] > mv[rl[-2]]:
        return "bull-div"
    return "-"


def diagnose(name: str, close: pd.Series) -> None:
    sig = compute_signals(close)
    if sig.empty:
        print(f"{name}: thin history"); return
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    hi, lo = swing_points(sig["close"])
    c = sig["close"]; macd = sig["macd"]
    idx = sig.index
    n = len(sig)

    print(f"\n================ {name}  (3D bars, events since {SINCE}) ================")
    print(f"{'date':12s}{'event':9s}{'price':>9s}{'vs200':>7s}{'wkly':>6s}"
          f"{'diverg':>10s}{'fwd~30d':>9s}{'fwd~60d':>9s}   proposed-call")
    print("-" * 104)
    for i in range(n):
        row = sig.iloc[i]
        d = idx[i]
        if d < pd.Timestamp(SINCE):
            continue
        ev = ("BUY*" if row["CB"] else "RE-BUY" if row["revBuy"]
              else "SELL*" if row["CS"] else "CUT" if row["revSell"] else None)
        if not ev:
            continue
        vs200 = "below" if not row["above200"] else "above"
        wkly = "up" if row["w_bull"] else "dn"
        div = divergence_at(i, c, macd, hi, lo)
        f30 = (float(c.iloc[i + 10]) / float(c.iloc[i]) - 1) * 100 if i + 10 < n else np.nan
        f60 = (float(c.iloc[i + 20]) / float(c.iloc[i]) - 1) * 100 if i + 20 < n else np.nan
        # reclaim-and-hold: did the next ~3 bars hold above entry?
        held = (i + 3 < n) and (float(c.iloc[i + 3]) > float(c.iloc[i]))

        # ---- proposed rule ----
        if ev in ("BUY*", "RE-BUY"):
            # in a counter-trend regime (below 200 + weekly not up) demand the
            # weekly turn; otherwise the buy is "wait for confirmation"
            if vs200 == "below" and wkly == "dn":
                call = "BLOCK (counter-trend: weekly not up)"
            elif div == "bull-div" and wkly == "up":
                call = "TAKE (weekly up + bull divergence)"
            else:
                call = "TAKE-on-confirm (needs reclaim+hold)"
        else:  # sells
            if wkly == "up" and div != "bear-div":
                call = "TRIM only (weekly up, no divergence -> likely pause)"
            else:
                call = "FULL EXIT (weekly rolling or bear-div -> real top)"

        f30s = f"{f30:+.1f}%" if not np.isnan(f30) else "  n/a"
        f60s = f"{f60:+.1f}%" if not np.isnan(f60) else "  n/a"
        print(f"{str(d.date()):12s}{ev:9s}{row['close']:>9.1f}{vs200:>7s}{wkly:>6s}"
              f"{div:>10s}{f30s:>9s}{f60s:>9s}   {call}")


if __name__ == "__main__":
    diagnose("TENCENT 0700.HK", load_tencent())
    diagnose("BABA", load_baba())
