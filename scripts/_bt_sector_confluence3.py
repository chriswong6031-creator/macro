"""Phase-3 robustness: is the sector-confluence edge stable across ERAS and
SECTORS, or a 2008 artifact? Confirms the two production signals before they
become the engine:
  * BUY  = SETUP-up (approaching 3D MACD up-cross) ABOVE the 200-day
  * AVOID = a 3D top-cross while EXTENDED (RSI>70 or StochRSI>80)

Run:  python3 -m scripts._bt_sector_confluence3
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_sector_confluence2 import _enrich
from scripts._bt_sector_confluence import _load, SECTORS, BENCH

ERAS = [("1999-2007", "1999-01-01", "2007-12-31"),
        ("2008-2015", "2008-01-01", "2015-12-31"),
        ("2016-2020", "2016-01-01", "2020-12-31"),
        ("2021-2026", "2021-01-01", "2026-12-31")]


def _stat(sub: pd.DataFrame) -> tuple:
    e = sub["exc63"].dropna() * 100
    if len(e) < 20:
        return (len(e), np.nan, np.nan)
    return (len(e), round(e.mean(), 2), round(100 * (e > 0).mean(), 0))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    spy = _load(BENCH)
    R = pd.concat([_enrich(t, spy) for t in SECTORS])
    R["buy_sig"] = R["setup_up"] & R["above200"]
    R["avoid_sig"] = (R["sell_full"] | R["sell_partial"]) & ((R["rsi14"] > 70) | (R["stoch"] > 80))

    print("=" * 90)
    print("ERA STABILITY (forward 63d excess vs SPY, %)  — n / mean exc63 / hit%")
    print("=" * 90)
    rows = []
    for name, lo, hi in ERAS:
        seg = R[(R.index >= lo) & (R.index <= hi)]
        bn, bm, bh = _stat(seg[seg["buy_sig"]])
        an, am, ah = _stat(seg[seg["avoid_sig"]])
        nn, nm, nh = _stat(seg)
        rows.append({"era": name, "BUY_n": bn, "BUY_exc": bm, "BUY_hit": bh,
                     "AVOID_n": an, "AVOID_exc": am, "AVOID_hit": ah,
                     "base_exc": nm})
    print(pd.DataFrame(rows).set_index("era").to_string())

    print("\n" + "=" * 90)
    print("PER-SECTOR (forward 63d excess vs SPY, %)")
    print("=" * 90)
    rows = []
    for t in SECTORS:
        seg = R[R["ticker"] == t]
        bn, bm, bh = _stat(seg[seg["buy_sig"]])
        an, am, ah = _stat(seg[seg["avoid_sig"]])
        rows.append({"sector": t, "BUY_n": bn, "BUY_exc63": bm, "BUY_hit": bh,
                     "AVOID_n": an, "AVOID_exc63": am, "AVOID_hit": ah})
    df = pd.DataFrame(rows).set_index("sector")
    print(df.to_string())
    print(f"\nBUY edge positive in {(df['BUY_exc63'] > 0).sum()}/{df['BUY_exc63'].notna().sum()} sectors; "
          f"AVOID edge negative in {(df['AVOID_exc63'] < 0).sum()}/{df['AVOID_exc63'].notna().sum()} sectors")

    # spread monotonicity by conviction: full confluence vs partial vs setup-only
    print("\n" + "=" * 90)
    print("CONVICTION LADDER (BUY side, above200, exc63 %)")
    print("=" * 90)
    above = R[R["above200"]]
    for lbl, m in [("full confluence (MACD+Stoch up)", above["buy_full"]),
                   ("partial (one cross up)", above["buy_partial"]),
                   ("setup-up (approaching)", above["setup_up"] & ~above["buy_full"] & ~above["buy_partial"]),
                   ("setup OR cross (any fresh up)", above["setup_up"] | above["buy_full"] | above["buy_partial"])]:
        n, mn, ht = _stat(above[m])
        print(f"  {lbl:38s} n={n:5d}  exc63={mn}  hit={ht}")
