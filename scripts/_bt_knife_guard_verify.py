"""ADVERSARIAL VERIFIER #3 — does surfacing below-200d OVERSOLD-BOUNCE (StochRSI
cross-up<20) entries RESURFACE the 2000/2008/2022 falling knives?

The 200d gate exists to stop the engine surfacing knives. The proposed fix is an
OVERSOLD-BOUNCE state for below-200d + oversold-and-turning, gated to
non-deep-knife + Fed-put-present. I adversarially test the TAIL, not just the mean:
forward return AND worst-case forward drawdown (min path low + 5th pctile) of
below-200d stoch_up entries in (a) the worst bears / put-absent regimes,
(b) deep cyclicals, (c) range-bound defensives — then test whether
'not a DEEP knife' + 'put-present' guards CONTAIN the tail.

Point-in-time throughout:
 * stoch_up read at a 3B bar close; forward stats start from that close.
 * 200d SMA from daily closes <= signal date.
 * put_absent = recession (real-time Sahm>=0.50) OR Fed-put-off (10y breakeven
   smoothed 21d >= 2.5%) — the engine's exact master switch, lagged so each macro
   reading is only used AFTER its release (Sahm monthly w/ realtime vintage; we
   shift the monthly stamp forward to be safe).

Run: python3 -m scripts._bt_knife_guard_verify
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts._bt_sector_confluence import _load, _to_3b, _signals_3b, SECTORS, BENCH

DEFENSIVE = {"XLU", "XLP", "XLV", "XLRE"}
DEEP_CYC = ["XLE", "XLF", "XLC", "XLK"]          # the prompt's deep cyclicals
HOR = [10, 21, 42, 63]

# Worst bear / knife windows (the regimes the gate is meant to protect)
BEARS = [
    ("2000-2002 dotcom", "2000-09-01", "2002-12-31"),
    ("2008 GFC",         "2008-01-01", "2009-03-31"),
    ("2022 rate shock",  "2022-01-01", "2022-12-31"),
]


# ---------------------------------------------------------------- macro switch
def put_absent_series(daily_index: pd.DatetimeIndex) -> pd.Series:
    """Engine master switch, point-in-time, reindexed onto daily dates.
    recession (Sahm>=0.50) OR fedput_off (10y breakeven 21d-mean>=2.5%)."""
    sahm = pd.read_parquet("data/fred/SAHMREALTIME.parquet")["sahm"]
    be = pd.read_parquet("data/fred/T10YIE.parquet")["breakeven_10y"]
    # Sahm is monthly w/ a real-time vintage stamped at month-start; to avoid using
    # a month's reading before it could be known, shift the stamp +1 month forward.
    sahm = sahm.copy()
    sahm.index = sahm.index + pd.DateOffset(months=1)
    recession = (sahm >= 0.50).reindex(daily_index, method="ffill").fillna(False)
    be_sm = be.rolling(21, min_periods=10).mean()
    fedput_off = (be_sm >= 2.5).reindex(daily_index, method="ffill").fillna(False)
    return (recession | fedput_off)


# ---------------------------------------------------------------- enrich panel
def enrich(t: str, spy: pd.Series, pa: pd.Series) -> pd.DataFrame:
    daily = _load(t)
    s3 = _to_3b(daily)
    sig = _signals_3b(s3["close"]).copy()
    sma200 = daily.rolling(200).mean()
    above200 = (daily > sma200).reindex(sig.index, method="ffill")
    # DEPTH below the 200d at the signal bar (negative = below), point-in-time
    depth = ((daily / sma200 - 1) * 100).reindex(sig.index, method="ffill")
    # is the 200d STILL FALLING? (knife still accelerating down). slope over 21d.
    slope200 = sma200.diff(21).reindex(sig.index, method="ffill")
    # 10d reclaim flag (price > 10d MA = turning up out of the washout)
    ma10 = daily.rolling(10).mean()
    reclaim10 = (daily > ma10).reindex(sig.index, method="ffill").fillna(False)
    # put-absent at the signal bar
    pa_sig = pa.reindex(sig.index, method="ffill").fillna(False)

    sig["above200"] = above200.fillna(True).values
    sig["depth200"] = depth.values
    sig["sma200_slope"] = slope200.values
    sig["reclaim10"] = reclaim10.values
    sig["put_absent"] = pa_sig.values
    sig["os_bounce"] = sig["stoch_up"]      # the user's trigger

    # forward absolute return AND forward worst drawdown along the path
    didx = daily.index
    pos = didx.get_indexer(sig.index)
    sp = spy.reindex(didx)
    for h in HOR:
        fwd = np.full(len(sig), np.nan)
        exc = np.full(len(sig), np.nan)
        mdd = np.full(len(sig), np.nan)   # worst close-to-close drawdown over [t, t+h]
        for i, p in enumerate(pos):
            if p < 0 or p + h >= len(didx):
                continue
            entry = daily.iloc[p]
            path = daily.iloc[p:p + h + 1]
            fwd[i] = path.iloc[-1] / entry - 1
            mdd[i] = path.min() / entry - 1          # lowest close vs entry (<=0 usually)
            if pd.notna(sp.iloc[p]) and pd.notna(sp.iloc[p + h]):
                exc[i] = fwd[i] - (sp.iloc[p + h] / sp.iloc[p] - 1)
        sig[f"fwd{h}"] = fwd
        sig[f"exc{h}"] = exc
        sig[f"mdd{h}"] = mdd
    sig["ticker"] = t
    return sig


def tail_stats(sub: pd.DataFrame, h: int) -> dict:
    fwd = sub[f"fwd{h}"].dropna() * 100
    mdd = sub[f"mdd{h}"].dropna() * 100
    if len(fwd) < 8:
        return {"n": len(fwd), "mean": np.nan, "hit": np.nan,
                "p5": np.nan, "min": np.nan, "mdd_mean": np.nan,
                "mdd_p5": np.nan, "mdd_min": np.nan}
    return {
        "n": len(fwd),
        "mean": round(float(fwd.mean()), 2),
        "hit": round(float(100 * (fwd > 0).mean()), 0),
        "p5": round(float(np.percentile(fwd, 5)), 2),         # 5th pctile fwd return
        "min": round(float(fwd.min()), 2),                    # worst single outcome
        "mdd_mean": round(float(mdd.mean()), 2),              # mean worst-path drawdown
        "mdd_p5": round(float(np.percentile(mdd, 5)), 2),     # 5th pctile (deep) drawdown
        "mdd_min": round(float(mdd.min()), 2),                # absolute worst drawdown
    }


def line(label, sub, hs=(21, 63)):
    out = f"  {label:46s} n={len(sub['fwd21'].dropna()):>4}"
    for h in hs:
        s = tail_stats(sub, h)
        out += (f" | {h}d mean={s['mean']:>6} hit={s['hit']:>4}% "
                f"p5={s['p5']:>7} min={s['min']:>7} "
                f"mddμ={s['mdd_mean']:>6} mddp5={s['mdd_p5']:>7} mddmin={s['mdd_min']:>7}")
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 320)
    spy = _load(BENCH)
    pa = put_absent_series(spy.index)

    frames = [enrich(t, spy, pa) for t in SECTORS]
    R = pd.concat(frames)
    R["def"] = R["ticker"].isin(DEFENSIVE)
    below = ~R["above200"]
    osb = R["os_bounce"]

    print("=" * 200)
    print("PUT-ABSENT COVERAGE CHECK (sanity): fraction of below-200d stoch_up bars flagged put-absent, by era")
    print("=" * 200)
    bsig = R[below & osb]
    for name, lo, hi in [("00-02", "2000-09-01", "2002-12-31"), ("08-09", "2008-01-01", "2009-03-31"),
                         ("22", "2022-01-01", "2022-12-31"), ("16-20", "2016-01-01", "2020-12-31"),
                         ("21-26", "2021-01-01", "2026-12-31"), ("ALL", "1998-01-01", "2026-12-31")]:
        seg = bsig[(bsig.index >= lo) & (bsig.index <= hi)]
        if len(seg):
            print(f"  {name:7s} n={len(seg):>4}  put_absent={100*seg['put_absent'].mean():.0f}%")

    print("\n" + "=" * 200)
    print("(A) BELOW-200d StochRSI oversold-bounce IN THE WORST BEAR WINDOWS — UNGUARDED. Tail = mdd (worst path drawdown vs entry)")
    print("    The question: would surfacing these entries have dumped the user into the knives?")
    print("=" * 200)
    for name, lo, hi in BEARS:
        seg = bsig[(bsig.index >= lo) & (bsig.index <= hi)]
        print(line(f"{name} ALL below200 stoch_up", seg))
        segd = seg[seg["def"]]
        segc = seg[~seg["def"]]
        print(line(f"   ...DEFENSIVE", segd))
        print(line(f"   ...CYCLICAL", segc))

    print("\n" + "=" * 200)
    print("(B) DEEP CYCLICALS (XLE/XLF/XLC/XLK) vs (C) DEFENSIVES — below-200d stoch_up, FULL HISTORY, UNGUARDED")
    print("=" * 200)
    print(line("DEEP-CYC below200 stoch_up (unguarded)", R[below & osb & R["ticker"].isin(DEEP_CYC)]))
    print(line("DEFENSIVE below200 stoch_up (unguarded)", R[below & osb & R["def"]]))

    print("\n" + "=" * 200)
    print("THE GUARD TEST — progressively add guards to BELOW-200d stoch_up and watch the TAIL (mdd_p5 / mdd_min / fwd p5).")
    print("  not-deep      = depth200 > -12% (within ~12% of the 200d, not a deep washout)")
    print("  200d-not-fall = sma200_slope >= 0 (the long trend not still accelerating down)")
    print("  put-present   = NOT put_absent (Fed-put master switch present)")
    print("  reclaim10     = price reclaimed the 10d MA (turning up, not mid-air)")
    print("=" * 200)

    def guards(df, deep=False, slope=False, putp=False, reclaim=False):
        m = pd.Series(True, index=df.index)
        if deep:    m &= df["depth200"] > -12
        if slope:   m &= df["sma200_slope"] >= 0
        if putp:    m &= ~df["put_absent"]
        if reclaim: m &= df["reclaim10"]
        return df[m]

    for cohort_name, cohort in [("DEEP-CYC", R[below & osb & R["ticker"].isin(DEEP_CYC)]),
                                ("DEFENSIVE", R[below & osb & R["def"]]),
                                ("ALL-SECTORS", R[below & osb])]:
        print(f"\n--- {cohort_name} below-200d stoch_up ---")
        print(line("  UNGUARDED", cohort))
        print(line("  +not-deep(>-12%)", guards(cohort, deep=True)))
        print(line("  +not-deep +200d-not-falling", guards(cohort, deep=True, slope=True)))
        print(line("  +not-deep +200d-not-falling +put-present", guards(cohort, deep=True, slope=True, putp=True)))
        print(line("  +ALL (incl reclaim10)", guards(cohort, deep=True, slope=True, putp=True, reclaim=True)))

    print("\n" + "=" * 200)
    print("WORST-WINDOW RE-RUN WITH FULL GUARDS — do the guards SCRUB the knives out of 00/08/22 entirely?")
    print("=" * 200)
    for name, lo, hi in BEARS:
        seg = bsig[(bsig.index >= lo) & (bsig.index <= hi)]
        g = guards(seg, deep=True, slope=True, putp=True)
        print(line(f"{name}  full-guarded (all sectors)", g))
        gd = guards(seg[seg["def"]], deep=True, slope=True, putp=True)
        print(line(f"   ...DEFENSIVE full-guarded", gd))

    print("\n" + "=" * 200)
    print("SENSITIVITY — depth threshold for DEEP-CYC (put-present + 200d-not-falling held); how tight must 'not-deep' be?")
    print("=" * 200)
    cyc = R[below & osb & R["ticker"].isin(DEEP_CYC)]
    for thr in [-20, -15, -12, -10, -8, -5]:
        m = (cyc["depth200"] > thr) & (cyc["sma200_slope"] >= 0) & (~cyc["put_absent"])
        print(line(f"  depth>{thr}% +slope>=0 +put-present", cyc[m]))
