"""Phase-4 — lock the exact production rules.

BUY refinements (all on the 3D bar):
  base   = setup_up & above200
  +fresh = base & rsi14<65         (don't 'buy' something already extended)
  +pull  = base & came-from-pullback (rsi14 was <45 within the last 4 bars)
AVOID refinements:
  ext_topcross = (macd_dn|stoch_dn) & (rsi>70|stoch>80)
  ext_anyroll  = (macd_dn|stoch_dn|setup_dn) & (rsi>70|stoch>80)

Run: python3 -m scripts._bt_sector_confluence4
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_sector_confluence2 import _enrich
from scripts._bt_sector_confluence import _load, SECTORS, BENCH


def _stat(sub: pd.DataFrame, col="exc63") -> tuple:
    e = sub[col].dropna() * 100
    if len(e) < 20:
        return (len(e), np.nan, np.nan)
    return (len(e), round(e.mean(), 2), round(100 * (e > 0).mean(), 0))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    spy = _load(BENCH)
    R = pd.concat([_enrich(t, spy) for t in SECTORS])

    # recent pullback flag: rsi14 dipped below 45 within the last 4 3B bars
    R = R.sort_values(["ticker"]).copy()
    rsi_lt45 = R.groupby("ticker")["rsi14"].transform(
        lambda s: s.lt(45).rolling(4, min_periods=1).max().astype(bool))
    R["pullback"] = rsi_lt45.values

    ext = (R["rsi14"] > 70) | (R["stoch"] > 80)
    base_buy = R["setup_up"] & R["above200"]
    cross_up_any = (R["macd_up"] | R["stoch_up"]) & R["above200"]

    print("BUY variants (exc63 vs SPY, %):")
    for lbl, m in [
        ("setup_up & above200 (base)", base_buy),
        ("base & rsi<65 (not extended)", base_buy & (R["rsi14"] < 65)),
        ("base & pullback (rsi<45 recently)", base_buy & R["pullback"]),
        ("base & not-extended & pullback", base_buy & (R["rsi14"] < 65) & R["pullback"]),
        ("any cross-up & above200", cross_up_any),
        ("any cross-up & above200 & pullback", cross_up_any & R["pullback"]),
        ("(setup OR cross up) & above200 & rsi<65", (R["setup_up"] | R["macd_up"] | R["stoch_up"]) & R["above200"] & (R["rsi14"] < 65)),
    ]:
        for col in ("exc21", "exc63"):
            n, mn, ht = _stat(R[m], col)
            end = "\n" if col == "exc63" else "   "
            print(f"  {lbl:44s} {col}: n={n:5d} exc={mn} hit={ht}", end=end)

    print("\nAVOID variants (exc63 vs SPY, %  — want NEGATIVE):")
    for lbl, m in [
        ("ext & top-cross (macd|stoch dn)", (R["macd_dn"] | R["stoch_dn"]) & ext),
        ("ext & (top-cross | setup_dn)", (R["macd_dn"] | R["stoch_dn"] | R["setup_dn"]) & ext),
        ("ext & full top (macd&stoch dn)", (R["macd_dn"] & R["stoch_dn"]) & ext),
        ("ext alone (rsi>70|stoch>80)", ext),
        ("ext & setup_dn", R["setup_dn"] & ext),
        ("ext & below50 & top-cross", (R["macd_dn"] | R["stoch_dn"]) & ext & ~R["above50"]),
    ]:
        for col in ("exc21", "exc63"):
            n, mn, ht = _stat(R[m], col)
            end = "\n" if col == "exc63" else "   "
            print(f"  {lbl:44s} {col}: n={n:5d} exc={mn} hit={ht}", end=end)

    # final chosen rule, cross-sectional spread + monotonic 3-bucket
    R["BUY"] = (R["setup_up"] | R["macd_up"] | R["stoch_up"]) & R["above200"] & (R["rsi14"] < 65)
    R["AVOID"] = (R["macd_dn"] | R["stoch_dn"] | R["setup_dn"]) & ext
    print("\nFINAL cross-sectional (BUY vs AVOID vs rest), exc63 %:")
    for lbl, m in [("BUY", R["BUY"] & ~R["AVOID"]), ("AVOID", R["AVOID"] & ~R["BUY"]),
                   ("rest", ~R["BUY"] & ~R["AVOID"])]:
        n, mn, ht = _stat(R[m]); n21, m21, h21 = _stat(R[m], "exc21")
        print(f"  {lbl:6s} n={n:6d}  exc21={m21}  exc63={mn}  hit63={ht}")
    b = (R["BUY"] & ~R["AVOID"]); a = (R["AVOID"] & ~R["BUY"])
    print(f"  SPREAD exc63 = {(_stat(R[b])[1] - _stat(R[a])[1]):.2f}%")
