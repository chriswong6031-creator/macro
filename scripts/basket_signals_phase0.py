"""Phase-0 sanity check for the new basket-level signals before any of them touch the score.

House rule (memory: standout-reshape, deep-factor-ic-scorecard): a leg only earns a SCORED
weight if it carries measured forward content; otherwise it stays display-only. Cross-sectional
theme momentum has historically shown ~0 rank-IC here, and the one validated edge is the
ABSOLUTE-trend (above-200d) gate, which is drawdown CONTROL, not alpha.

This pools CAUSAL daily leg series across all baskets' consolidated candles (pit=False, full
history) and measures each leg's relationship to FORWARD basket returns:
  • Spearman rank-IC of each continuous leg vs fwd 20/60-day return,
  • an event study of the vol-hole breakout/breakdown (mean fwd return vs the unconditional base),
  • the 200-day absolute-trend gate's effect on fwd return AND forward max-drawdown.

Honest by design: prints the numbers, picks no winners. Run: python -m scripts.basket_signals_phase0
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import baskets, basket_index, dannytrades as dt  # noqa: E402


def _fwd_ret(close: pd.Series, h: int) -> pd.Series:
    return close.shift(-h) / close - 1.0


def _fwd_maxdd(close: pd.Series, h: int) -> pd.Series:
    """Worst close-to-close drawdown over the next h days (≤0)."""
    out = pd.Series(np.nan, index=close.index)
    arr = close.to_numpy()
    for i in range(len(arr) - 1):
        seg = arr[i + 1: i + 1 + h]
        if len(seg) == 0:
            continue
        out.iloc[i] = float(seg.min() / arr[i] - 1.0)
    return out


def _ic(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    """Spearman rank-IC without scipy: rank both, then Pearson."""
    j = pd.concat([x, y], axis=1).dropna()
    if len(j) < 50:
        return float("nan"), len(j)
    return float(j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank())), len(j)


def main() -> int:
    mem = baskets._membership()
    bdict = mem["baskets"]
    items = list(bdict.items()) if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]

    legs = {k: [] for k in ("danny_score", "cmf", "whale", "mtf_mom", "above200")}
    fwd = {h: [] for h in (20, 60)}
    dd = {h: [] for h in (20, 60)}
    breakout_fwd, base_fwd = [], []

    for bid, b in items:
        members = b["members"]
        idx = basket_index.deep_calendar(members)
        cand, _ = basket_index.consolidated_candle(members, idx, "equal", pit=False)
        if cand is None or len(cand) < 300:
            continue
        close, high, low = cand["close"], cand["high"], cand["low"]
        dvol = cand["dollar_vol"].fillna(0.0)
        sig = dt.signals(close, high, low, dvol)
        cmf = dt.cmf(high, low, close, dvol)
        sma200 = close.rolling(200, min_periods=100).mean()
        above200 = (close > sma200).astype(float)
        # MTF momentum proxy (causal): daily ribbon + weekly ribbon reindexed forward
        wk = close.resample("W-FRI").last().dropna()
        wk_rib = dt.ribbon_trend(wk).reindex(close.index, method="ffill")
        mtf_mom = (dt.ribbon_trend(close) + wk_rib) / 2.0

        legs["danny_score"].append(sig["score"])
        legs["cmf"].append(cmf)
        legs["whale"].append(sig["whale"])
        legs["mtf_mom"].append(mtf_mom)
        legs["above200"].append(above200)
        for h in (20, 60):
            fwd[h].append(_fwd_ret(close, h))
            dd[h].append(_fwd_maxdd(close, h))

        # vol-hole breakout event study (fwd 20d)
        f20 = _fwd_ret(close, 20)
        bo = sig["breakout_up"]
        breakout_fwd.append(f20[bo].dropna())
        base_fwd.append(f20.dropna())

    def cat(lst):
        return pd.concat(lst) if lst else pd.Series(dtype=float)

    print("\n=== Basket signals Phase-0 (pooled across baskets, CAUSAL legs) ===")
    print(f"baskets used: {len(legs['danny_score'])}\n")
    print(f"{'leg':14s} {'IC(20d)':>9s} {'n':>7s}   {'IC(60d)':>9s} {'n':>7s}")
    for name in ("danny_score", "cmf", "whale", "mtf_mom", "above200"):
        L = cat(legs[name])
        ic20, n20 = _ic(L, cat(fwd[20]))
        ic60, n60 = _ic(L, cat(fwd[60]))
        print(f"{name:14s} {ic20:9.3f} {n20:7d}   {ic60:9.3f} {n60:7d}")

    bf, base = cat(breakout_fwd), cat(base_fwd)
    if len(bf) > 20:
        print(f"\nvol-hole BREAKOUT_UP → fwd 20d: mean {bf.mean()*100:+.2f}% (n={len(bf)})  "
              f"vs base {base.mean()*100:+.2f}% (n={len(base)})  edge {(bf.mean()-base.mean())*100:+.2f}pp")

    print("\n200d absolute-trend gate (drawdown control):")
    for h in (20, 60):
        a200 = cat(legs["above200"]); f = cat(fwd[h]); d = cat(dd[h])
        j = pd.concat([a200, f, d], axis=1).dropna()
        j.columns = ["above", "fwd", "dd"]
        up = j[j["above"] == 1]; dn = j[j["above"] == 0]
        print(f"  h={h:2d}d  above200: fwd {up['fwd'].mean()*100:+.2f}%  maxDD {up['dd'].mean()*100:.2f}%   |   "
              f"below200: fwd {dn['fwd'].mean()*100:+.2f}%  maxDD {dn['dd'].mean()*100:.2f}%")
    print("\nRead honestly: small |IC| ⇒ keep the leg transparent + low-weight (decision-support, "
          "not alpha). The above-200d gap in maxDD is the validated drawdown-control content.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
