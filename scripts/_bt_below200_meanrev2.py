"""Follow-up: (1) full vol profile incl XLU, (2) does a 10-day RECLAIM split the
below-200d knife from the buyable oversold bounce, (3) era-robustness of the
'defensive dips are buyable in ABSOLUTE terms' finding, (4) XLU deep dive.

Run: python3 -m scripts._bt_below200_meanrev2
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_below200_meanrev import enrich, vol_profile, DEFENSIVE
from scripts._bt_sector_confluence import _load, SECTORS, BENCH

ERAS = [("99-07", "1999-01-01", "2007-12-31"), ("08-15", "2008-01-01", "2015-12-31"),
        ("16-20", "2016-01-01", "2020-12-31"), ("21-26", "2021-01-01", "2026-12-31")]


def _agg(sub, col):
    e = sub[col].dropna() * 100
    if len(e) < 20:
        return (len(e), np.nan, np.nan)
    return (len(e), round(float(e.mean()), 2), round(float(100 * (e > 0).mean()), 0))


def reclaim_flag(t: str, idx) -> pd.Series:
    """price > 10-day MA at each signal date = turning up (the washout reclaim)."""
    c = _load(t)
    ma10 = c.rolling(10).mean()
    rc = (c > ma10)
    return rc.reindex(idx, method="ffill").fillna(False)


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    spy = _load(BENCH)

    print("=" * 100)
    print("FULL VOL / MEAN-REVERSION PROFILE (sorted by vol)")
    print("=" * 100)
    vp = pd.DataFrame({t: vol_profile(t) for t in SECTORS}).T
    vp["cohort"] = ["DEF" if t in DEFENSIVE else "cyc" for t in vp.index]
    print(vp.sort_values("ann_vol%").to_string())

    # build enriched panel with reclaim flag
    frames = []
    for t in SECTORS:
        df = enrich(t, spy)
        df["reclaim10"] = reclaim_flag(t, df.index).values
        frames.append(df)
    R = pd.concat(frames)
    R["def"] = R["ticker"].isin(DEFENSIVE)
    R["fresh_up"] = R["macd_up"] | R["stoch_up"] | R["setup_up"]
    below = ~R["above200"]

    print("\n" + "=" * 100)
    print("KNIFE vs RECLAIM split — below-200d fresh-up, by whether price reclaimed the 10-day MA")
    print("  (the existing washout machinery's turn flag). exc=vs SPY, abs=absolute. DEF cohort.")
    print("=" * 100)
    for label, mask in [
        ("DEF below200 + reclaim10 (turning)", R["def"] & below & R["fresh_up"] & R["reclaim10"]),
        ("DEF below200 + NO reclaim (knife)",  R["def"] & below & R["fresh_up"] & ~R["reclaim10"]),
        ("cyc below200 + reclaim10 (turning)", ~R["def"] & below & R["fresh_up"] & R["reclaim10"]),
        ("cyc below200 + NO reclaim (knife)",  ~R["def"] & below & R["fresh_up"] & ~R["reclaim10"]),
    ]:
        sub = R[mask]
        line = f"  {label:36s}"
        for h in [10, 21, 63]:
            _, e, hit = _agg(sub, f"exc{h}")
            _, a, _ = _agg(sub, f"fwd{h}")
            line += f"  exc{h}={e:>6}/{hit:>4}% abs{h}={a:>6}"
        line += f"  n={len(sub['exc21'].dropna())}"
        print(line)

    print("\n" + "=" * 100)
    print("ERA ROBUSTNESS — DEF below-200d fresh-up + reclaim10: ABSOLUTE fwd-21d & fwd-63d (%)")
    print("=" * 100)
    sub = R[R["def"] & below & R["fresh_up"] & R["reclaim10"]]
    rows = []
    for name, lo, hi in ERAS:
        seg = sub[(sub.index >= lo) & (sub.index <= hi)]
        _, a21, h21 = _agg(seg, "fwd21"); _, a63, h63 = _agg(seg, "fwd63")
        _, e21, _ = _agg(seg, "exc21"); _, e63, _ = _agg(seg, "exc63")
        rows.append({"era": name, "n": len(seg["fwd21"].dropna()),
                     "abs21": a21, "hit21": h21, "abs63": a63, "hit63": h63,
                     "exc21": e21, "exc63": e63})
    print(pd.DataFrame(rows).set_index("era").to_string())

    print("\n" + "=" * 100)
    print("XLU DEEP DIVE")
    print("=" * 100)
    xlu = R[R["ticker"] == "XLU"]
    bx = xlu[~xlu["above200"]]
    print(f"  XLU profile: {vol_profile('XLU')}")
    print(f"  XLU signal bars below 200d: {len(bx)}  (of {len(xlu)} total = {round(100*len(bx)/len(xlu))}%)")
    for label, mask in [
        ("XLU below200 fresh-up (all)",          bx["fresh_up"]),
        ("XLU below200 fresh-up + reclaim10",     bx["fresh_up"] & bx["reclaim10"]),
        ("XLU below200 fresh-up + NO reclaim",    bx["fresh_up"] & ~bx["reclaim10"]),
        ("XLU below200 StochRSI x-up<20 +reclaim", bx["stoch_up"] & bx["reclaim10"]),
    ]:
        sub = bx[mask]
        line = f"  {label:38s}"
        for h in [10, 21, 42, 63]:
            _, e, hit = _agg(sub, f"exc{h}")
            _, a, _ = _agg(sub, f"fwd{h}")
            line += f"  {h}d abs={a}/{hit}%(exc{e})"
        line += f"  n={len(sub['exc21'].dropna())}"
        print(line)
