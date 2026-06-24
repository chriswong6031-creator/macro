"""Does the 200-day gate wrongly suppress mean-reversion buys on low-vol defensives?

User's critique: the hard 200d gate kills BUY/SETUP signals BELOW the 200-day. For
a low-volatility defensive like XLU that just waves around its 200d in cycles, those
below-200d dips are buyable oversold bounces, not falling knives — so the gate
'forgets' exactly the stable, mean-reverting names where a dip-buy works.

This script decomposes the below-200d result the gate was built on, PER SECTOR and
BY VOLATILITY, across multiple horizons (mean reversion is faster than 63d), and
quantifies the coverage the gate suppresses.

Run: python3 -m scripts._bt_below200_meanrev
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_sector_confluence import _load, _to_3b, _signals_3b, SECTORS, BENCH

HOR = [5, 10, 21, 42, 63]
DEFENSIVE = {"XLU", "XLP", "XLV", "XLRE"}   # low-beta / defensive cohort


def enrich(t: str, spy: pd.Series) -> pd.DataFrame:
    daily = _load(t)
    s3 = _to_3b(daily)
    sig = _signals_3b(s3["close"])
    sma200 = daily.rolling(200).mean()
    above200 = (daily > sma200).reindex(sig.index, method="ffill")
    sig = sig.copy()
    sig["above200"] = above200.fillna(True).values
    # fresh up-signals (the buy-side triggers the gate would surface or block)
    sig["fresh_up"] = sig["macd_up"] | sig["stoch_up"] | sig["setup_up"]
    # the user's specific "oversold bounce": StochRSI crossing up over 20 from <20
    sig["os_bounce"] = sig["stoch_up"]
    didx = daily.index
    pos = didx.get_indexer(sig.index)
    sp = spy.reindex(didx)
    for h in HOR:
        fwd = np.full(len(sig), np.nan)
        exc = np.full(len(sig), np.nan)
        for i, p in enumerate(pos):
            if p < 0 or p + h >= len(didx):
                continue
            fwd[i] = daily.iloc[p + h] / daily.iloc[p] - 1
            if pd.notna(sp.iloc[p]) and pd.notna(sp.iloc[p + h]):
                exc[i] = fwd[i] - (sp.iloc[p + h] / sp.iloc[p] - 1)
        sig[f"fwd{h}"] = fwd
        sig[f"exc{h}"] = exc
    sig["ticker"] = t
    return sig


def vol_profile(t: str) -> dict:
    """Volatility + mean-reversion character of the ETF (200d-cross frequency,
    time below 200d)."""
    c = _load(t)
    ret = c.pct_change()
    ann_vol = float(ret.std() * np.sqrt(252) * 100)
    sma200 = c.rolling(200).mean()
    below = (c < sma200)
    pct_below = float(below.mean() * 100)
    # 200d crossings per year = mean-reversion-iness
    crosses = (below != below.shift(1)).sum()
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    cross_per_yr = crosses / yrs
    # when below 200d, how deep on average (abs % below)
    depth = float(((c / sma200 - 1) * 100)[below].mean())
    return {"ann_vol%": round(ann_vol, 1), "pct_below_200d": round(pct_below, 0),
            "200d_cross/yr": round(cross_per_yr, 1), "avg_depth_below%": round(depth, 1)}


def _agg(sub: pd.DataFrame, col: str) -> tuple:
    e = sub[col].dropna() * 100
    if len(e) < 25:
        return (len(e), np.nan, np.nan)
    return (len(e), round(float(e.mean()), 2), round(float(100 * (e > 0).mean()), 0))


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    spy = _load(BENCH)
    R = pd.concat([enrich(t, spy) for t in SECTORS])

    print("=" * 110)
    print("VOLATILITY / MEAN-REVERSION PROFILE PER SECTOR")
    print("=" * 110)
    vp = pd.DataFrame({t: vol_profile(t) for t in SECTORS}).T
    vp["cohort"] = ["DEF" if t in DEFENSIVE else "cyc" for t in vp.index]
    print(vp.sort_values("ann_vol%").to_string())

    print("\n" + "=" * 110)
    print("BELOW-200d 'fresh up' BUY signals — forward EXCESS vs SPY (%), PER SECTOR")
    print("  (does a dip-buy below the 200d work? cyc=knife hypothesis, DEF=mean-revert hypothesis)")
    print("=" * 110)
    rows = []
    for t in SECTORS:
        seg = R[(R["ticker"] == t) & ~R["above200"] & R["fresh_up"]]
        rec = {"sector": t, "cohort": "DEF" if t in DEFENSIVE else "cyc"}
        for h in [10, 21, 42, 63]:
            n, m, hit = _agg(seg, f"exc{h}")
            rec[f"exc{h}"] = m
            rec[f"hit{h}"] = hit
        rec["n"] = len(seg[f"exc21"].dropna())
        rows.append(rec)
    bsec = pd.DataFrame(rows).set_index("sector")
    print(bsec.to_string())

    print("\n" + "=" * 110)
    print("COHORT POOLED — below-200d fresh-up (DEF vs cyc), and ABSOLUTE fwd return (not excess)")
    print("=" * 110)
    for label, mask in [("DEFENSIVE below-200d fresh-up", R["ticker"].isin(DEFENSIVE) & ~R["above200"] & R["fresh_up"]),
                        ("CYCLICAL  below-200d fresh-up", ~R["ticker"].isin(DEFENSIVE) & ~R["above200"] & R["fresh_up"]),
                        ("DEFENSIVE above-200d fresh-up", R["ticker"].isin(DEFENSIVE) & R["above200"] & R["fresh_up"]),
                        ("CYCLICAL  above-200d fresh-up", ~R["ticker"].isin(DEFENSIVE) & R["above200"] & R["fresh_up"])]:
        sub = R[mask]
        line = f"  {label:32s}"
        for h in [10, 21, 63]:
            n, e, hit = _agg(sub, f"exc{h}")
            na, a, hita = _agg(sub, f"fwd{h}")
            line += f"  exc{h}={e:>6}/{hit:>4}%  abs{h}={a:>6}"
        line += f"  n={len(sub['exc21'].dropna())}"
        print(line)

    print("\n" + "=" * 110)
    print("THE USER'S SIGNAL — StochRSI cross-up from <20 (oversold bounce) BELOW the 200d, per sector")
    print("=" * 110)
    rows = []
    for t in SECTORS:
        seg = R[(R["ticker"] == t) & ~R["above200"] & R["os_bounce"]]
        rec = {"sector": t, "cohort": "DEF" if t in DEFENSIVE else "cyc",
               "n": len(seg["exc21"].dropna())}
        for h in [10, 21, 42]:
            n, m, hit = _agg(seg, f"exc{h}")
            rec[f"exc{h}"] = m; rec[f"hit{h}"] = hit
        rows.append(rec)
    print(pd.DataFrame(rows).set_index("sector").to_string())

    print("\n" + "=" * 110)
    print("COVERAGE — how many BUY/SETUP signals does the gate ALLOW vs SUPPRESS, per sector")
    print("  (allowed = fresh-up above 200d; suppressed = fresh-up below 200d)  [3B bars over full history]")
    print("=" * 110)
    rows = []
    for t in SECTORS:
        seg = R[R["ticker"] == t]
        allowed = int((seg["fresh_up"] & seg["above200"]).sum())
        suppressed = int((seg["fresh_up"] & ~seg["above200"]).sum())
        tot = allowed + suppressed
        rows.append({"sector": t, "cohort": "DEF" if t in DEFENSIVE else "cyc",
                     "allowed_above200": allowed, "suppressed_below200": suppressed,
                     "%_suppressed": round(100 * suppressed / tot, 0) if tot else 0})
    print(pd.DataFrame(rows).set_index("sector").to_string())

    print("\n" + "=" * 110)
    print("VOLATILITY-CONDITIONED: is the below-200d edge a function of ETF volatility?")
    print("=" * 110)
    vol_map = {t: vol_profile(t)["ann_vol%"] for t in SECTORS}
    R["lowvol"] = R["ticker"].map(lambda t: vol_map[t] <= np.median(list(vol_map.values())))
    for label, mask in [("LOW-vol  below-200d fresh-up", R["lowvol"] & ~R["above200"] & R["fresh_up"]),
                        ("HIGH-vol below-200d fresh-up", ~R["lowvol"] & ~R["above200"] & R["fresh_up"])]:
        sub = R[mask]
        line = f"  {label:30s}"
        for h in [10, 21, 63]:
            n, e, hit = _agg(sub, f"exc{h}")
            line += f"  exc{h}={e:>6}/{hit:>4}%"
        line += f"  n={len(sub['exc21'].dropna())}"
        print(line)
