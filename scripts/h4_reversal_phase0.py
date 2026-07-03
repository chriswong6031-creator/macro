#!/usr/bin/env python3
"""H4 phase-0 — within-universe short-horizon reversal on the expanded HK universe.

Pre-registered in research/H4_PREREG.md (committed before this run). Implements:
  PRIMARY  = bottom-half 63d HKD-ADV cohort, deepest-quintile 63bd return-z reversal,
             monthly rebalance, next-open fills, 21bd hold, HSI-relative.
  CONTROL1 = same construction on the 157 mega-cap panel (expected NO-GO).
  CONTROL2 = same on the 67-name pre-2005 deep subset (survivorship ceiling, labelled).
  SECONDARY= PRIMARY z-scored within the current 13-sector map (non-PIT, labelled).

Reads the gitignored ext store locally. No wiring. See PREREG for gates.
"""
from __future__ import annotations
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.validation import (  # noqa: E402
    bootstrap_effective_t, deflated_sharpe, dsr_verdict, newey_west_tstat,
    rank_ic, benjamini_hochberg, ret_moments,
)

# ---- data locations (ext store is gitignored → read from the fetched sibling worktree) ----
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_LOCAL = os.path.join(HERE, "data", "hk_stocks_ext")
EXT_SIBLING = os.path.join(
    HERE, "..", "amazing-blackburn-5d2027", "data", "hk_stocks_ext")
HK_DIR = os.path.join(HERE, "data", "hk_stocks")
HSI_FILE = os.path.join(HERE, "data", "hk_search", "_HSI_deep.parquet")
DEEP_FILE = os.path.join(HERE, "data", "hk_search", "closes_deep.parquet")
CONST_FILE = os.path.join(HERE, "data", "hk_breadth", "constituents.parquet")

LOOKBACK = 63          # 3-month reversal lookback (trading days)
HOLD = 21              # ~1-month forward hold
ADV_WIN = 63           # dollar-ADV window
ADV_FLOOR = 1_000_000  # HKD/day hygiene floor (small-cap-scaled)
STALE_SESS = 5         # staleness / suspension window
N_TRIALS = 30          # PROGRAM-level multiplicity
DELIST_MONTHLY = 0.005  # survivorship bound: 0.5%/month-of-held phantom losers
PHANTOM_RET = -0.30    # phantom terminal 1m return


def _ext_dir() -> str:
    if len(glob.glob(os.path.join(EXT_LOCAL, "*.parquet"))) >= 100:
        return EXT_LOCAL
    return os.path.normpath(EXT_SIBLING)


def _load_wide(files: dict[str, str], col: str) -> pd.DataFrame:
    cols = {}
    for tkr, f in files.items():
        try:
            s = pd.read_parquet(f, columns=[col])[col]
        except Exception:
            continue
        s = s[~s.index.duplicated(keep="last")]
        cols[tkr] = s
    df = pd.DataFrame(cols).sort_index()
    return df


def load_panels():
    extd = _ext_dir()
    ext_files = {os.path.basename(f)[:-8]: f
                 for f in glob.glob(os.path.join(extd, "*.parquet"))}
    hk_files = {os.path.basename(f)[:-8]: f
                for f in glob.glob(os.path.join(HK_DIR, "*.parquet"))}
    stamp = {"ext_dir": extd, "n_ext": len(ext_files), "n_hk": len(hk_files)}

    # HSI benchmark (close only) → sets the return clip
    hsi = pd.read_parquet(HSI_FILE)["close"].sort_index()
    hsi = hsi[~hsi.index.duplicated(keep="last")]
    hsi_max = hsi.index.max()
    stamp["hsi_max"] = str(hsi_max.date())

    # UNION close/open/vol (ext ∪ hk)
    all_files = {**hk_files, **ext_files}  # disjoint; hk first is irrelevant
    close = _load_wide(all_files, "close")
    op = _load_wide(all_files, "open")
    vol = _load_wide(all_files, "volume")
    # clip to HSI availability for return honesty
    idx = close.index[close.index <= hsi_max]
    close, op, vol = close.loc[idx], op.reindex(idx), vol.reindex(idx)
    stamp["union_names"] = close.shape[1]
    stamp["union_range"] = [str(idx.min().date()), str(idx.max().date())]

    # mega-cap panel (control 1)
    mega = [t for t in hk_files]
    # deep-67 subset (control 2)
    deep = pd.read_parquet(DEEP_FILE).sort_index()
    deep = deep[~deep.index.duplicated(keep="last")]
    deep = deep.loc[deep.index <= hsi_max]
    d67 = [c for c in deep.columns
           if deep[c].dropna().index.min() < pd.Timestamp("2005-01-01")]
    stamp["deep67_names"] = len(d67)

    # sector map (secondary)
    const = pd.read_parquet(CONST_FILE)
    sect = const["sector"].to_dict() if "sector" in const.columns else {}

    return dict(close=close, open=op, vol=vol, hsi=hsi, mega=mega,
                deep_close=deep, d67=d67, sect=sect, stamp=stamp)


def month_ends(index: pd.DatetimeIndex) -> list:
    s = pd.Series(index, index=index)
    return list(s.groupby([index.year, index.month]).last().values)


def valid_lookback(close: pd.DataFrame, t, cols):
    """last STALE_SESS-fresh close at t, and >=LOOKBACK valid pts in the window."""
    pos = close.index.get_indexer([t])[0]
    if pos < LOOKBACK:
        return {}
    lo = pos - LOOKBACK
    win = close.iloc[lo:pos + 1]
    out = {}
    recent = close.index[pos]
    for c in cols:
        s = win[c]
        if s.count() < LOOKBACK:
            continue
        c_t = close[c].iloc[pos]
        if pd.isna(c_t):
            continue
        # staleness: last valid within STALE_SESS sessions of t
        last_valid = close[c].iloc[:pos + 1].last_valid_index()
        if last_valid is None:
            continue
        gap = close.index.get_indexer([t])[0] - close.index.get_indexer([last_valid])[0]
        if gap > STALE_SESS:
            continue
        c_lb = close[c].iloc[lo]
        if pd.isna(c_lb) or c_lb <= 0:
            # fall back to first valid in window
            fv = s.first_valid_index()
            c_lb = s[fv]
            if pd.isna(c_lb) or c_lb <= 0:
                continue
        out[c] = c_t / c_lb - 1.0
    return out


def dollar_adv(close, vol, t, cols):
    pos = close.index.get_indexer([t])[0]
    lo = max(0, pos - ADV_WIN)
    cwin = close.iloc[lo:pos + 1]
    vwin = vol.iloc[lo:pos + 1]
    dv = (cwin * vwin)
    return {c: float(np.nanmedian(dv[c])) for c in cols
            if dv[c].notna().sum() >= ADV_WIN // 2}


def fwd_return(close, op, hsi, t, name, *, fill="open"):
    """enter NEXT open (t+1), hold HOLD trading days, exit on close; HSI-relative.
    Suspension rule: no valid print within STALE_SESS sessions after t+1 ⇒ drop.

    fill="open" (pre-registered) enters at t+1 open. fill="close" is the LABELLED
    fallback used ONLY for controls whose stores lack historical open prices
    (hk_stocks open is ~99.9% NaN; closes_deep is close-only) — enters at t+1 close.
    """
    idx = close.index
    pos = idx.get_indexer([t])[0]
    if pos + 1 >= len(idx):
        return None
    t1 = idx[pos + 1]
    exit_pos = pos + 1 + HOLD
    if exit_pos >= len(idx):
        return None
    if fill == "open":
        o1 = op[name].iloc[pos + 1] if name in op.columns else np.nan
    else:
        o1 = close[name].iloc[pos + 1]  # next-close fallback (labelled)
    if pd.isna(o1) or o1 <= 0:
        return None  # halt at entry → un-enterable
    # suspension: need a valid close within STALE_SESS sessions after t1
    post = close[name].iloc[pos + 1:pos + 1 + STALE_SESS + 1]
    if post.count() == 0:
        return None
    c_exit = close[name].iloc[exit_pos]
    if pd.isna(c_exit):
        lv = close[name].iloc[pos + 1:exit_pos + 1].last_valid_index()
        if lv is None:
            return None
        c_exit = close[name].loc[lv]
    r = c_exit / o1 - 1.0
    # HSI close-to-close over [t1, exit] (shared benchmark; L/S invariant)
    try:
        h1 = hsi.asof(t1)
        h2 = hsi.asof(idx[exit_pos])
        if pd.notna(h1) and pd.notna(h2) and h1 > 0:
            r -= (h2 / h1 - 1.0)
    except Exception:
        pass
    return r


def run_trial(P, *, label, universe, adv_cohort, by_sector, fill="open"):
    close, op, vol, hsi = P["close"], P["open"], P["vol"], P["hsi"]
    if label == "CONTROL2":
        close = P["deep_close"]
        op = P["open"].reindex(columns=close.columns).reindex(close.index)
        vol = P["vol"].reindex(columns=close.columns).reindex(close.index)
    cols = [c for c in universe if c in close.columns]
    tgrid = [t for t in month_ends(close.index)
             if close.index.get_indexer([t])[0] >= LOOKBACK]
    tgrid = [pd.Timestamp(t) for t in tgrid]

    ls_ret, long_ret, ic_series, dates = [], [], [], []
    held_counts = []
    for t in tgrid[:-1]:
        rev = valid_lookback(close, t, cols)
        if len(rev) < 20:
            continue
        adv = dollar_adv(close, vol, t, list(rev.keys()))
        elig = {c: rev[c] for c in rev if adv.get(c, 0) >= ADV_FLOOR}
        if len(elig) < 20:
            continue
        if adv_cohort:
            med = np.median([adv[c] for c in elig])
            elig = {c: v for c, v in elig.items() if adv[c] < med}
            if len(elig) < 15:
                continue
        # z-score (whole or within-sector)
        s = pd.Series(elig)
        if by_sector:
            secmap = P["sect"]
            z = pd.Series(index=s.index, dtype=float)
            for sec in set(secmap.get(c, "?") for c in s.index):
                grp = [c for c in s.index if secmap.get(c, "?") == sec]
                if len(grp) < 5:
                    continue
                g = s[grp]
                z[grp] = (g - g.mean()) / (g.std(ddof=0) or np.nan)
            z = z.dropna()
        else:
            z = (s - s.mean()) / (s.std(ddof=0) or np.nan)
            z = z.dropna()
        if len(z) < 15:
            continue
        # quintiles by z: deepest = lowest z (biggest losers) = reversal long
        q = z.quantile([0.2, 0.8])
        longs = z[z <= q.iloc[0]].index.tolist()
        shorts = z[z >= q.iloc[1]].index.tolist()
        # forward returns
        lr = [fwd_return(close, op, hsi, t, n, fill=fill) for n in longs]
        sr = [fwd_return(close, op, hsi, t, n, fill=fill) for n in shorts]
        lr = [x for x in lr if x is not None]
        sr = [x for x in sr if x is not None]
        if len(lr) < 3 or len(sr) < 3:
            continue
        long_mean = float(np.mean(lr))
        ls = long_mean - float(np.mean(sr))
        long_ret.append(long_mean)
        ls_ret.append(ls)
        held_counts.append(len(lr))
        dates.append(t)
        # rank-IC: signal = -z (deepest loser = highest expected fwd), fwd across cohort
        fwd_all = {n: fwd_return(close, op, hsi, t, n, fill=fill) for n in z.index}
        fwd_all = {n: v for n, v in fwd_all.items() if v is not None}
        sig = {n: -z[n] for n in fwd_all}
        ic = rank_ic(pd.Series(sig), pd.Series(fwd_all))
        ic_series.append(ic)

    r = _summarize(label, dates, ls_ret, long_ret, ic_series, held_counts)
    r["fill"] = fill
    return r


def _summarize(label, dates, ls_ret, long_ret, ic_series, held_counts):
    n = len(ls_ret)
    res = {"label": label, "n_months": n}
    if n < 8:
        res["verdict"] = "INSUFFICIENT"
        return res
    ls = pd.Series(ls_ret, index=pd.DatetimeIndex(dates))
    lg = pd.Series(long_ret, index=pd.DatetimeIndex(dates))
    nw = newey_west_tstat(ls, lags=3)
    res["ls_mean_m"] = round(float(ls.mean()), 5)
    res["ls_t_hac"] = nw["t"]
    res["ls_p_hac"] = nw["p"]
    res["long_mean_m"] = round(float(lg.mean()), 5)
    ics = pd.Series(ic_series).dropna()
    res["rank_ic_mean"] = round(float(ics.mean()), 4) if len(ics) else None
    res["ic_hit"] = round(float((ics > 0).mean()), 3) if len(ics) else None
    # Sharpe (monthly) + DSR
    mom = ret_moments(ls)
    if mom is None:
        res["verdict"] = "INSUFFICIENT"
        return res
    sr_m, skew, kurt, _ = mom
    # effective-N via block bootstrap on a daily-equivalent proxy: use monthly series
    teff = bootstrap_effective_t(ls, block=6, B=2000)
    t_eff = teff.get("t_eff") if teff else None
    dsr = deflated_sharpe(sr_m, skew, kurt, T=n, n_trials=N_TRIALS,
                          trading_year=12, t_eff=t_eff)
    res["sr_monthly"] = round(sr_m, 4)
    res["dsr"] = dsr["dsr"] if dsr else None
    res["dsr_verdict"] = dsr_verdict(dsr["dsr"]) if dsr else None
    res["eff_n"] = t_eff if t_eff else n
    # split-half sign
    h = n // 2
    s1 = float(ls.iloc[:h].mean())
    s2 = float(ls.iloc[h:].mean())
    res["splithalf"] = {"h1": round(s1, 5), "h2": round(s2, 5),
                        "sign_stable": bool(np.sign(s1) == np.sign(s2) and s1 != 0)}
    res["med_held"] = int(np.median(held_counts))
    # survivorship bound: inject phantom losers into the LONG leg each month
    bounded_ls = []
    for i, t in enumerate(dates):
        k = held_counts[i]
        kp = int(round(k * DELIST_MONTHLY * 2))  # 2x base rate
        if kp <= 0:
            bounded_ls.append(ls_ret[i])
            continue
        # long leg mean with phantoms at PHANTOM_RET
        lm = long_ret[i]
        lm_b = (lm * k + PHANTOM_RET * kp) / (k + kp)
        bounded_ls.append(ls_ret[i] - (lm - lm_b))
    bls = pd.Series(bounded_ls, index=pd.DatetimeIndex(dates))
    nwb = newey_west_tstat(bls, lags=3)
    res["bound"] = {"ls_mean_m": round(float(bls.mean()), 5),
                    "ls_t_hac": nwb["t"],
                    "sign_flip": bool(np.sign(bls.mean()) != np.sign(ls.mean()))}
    return res


def main():
    P = load_panels()
    union = list(P["close"].columns)
    trials = {}
    trials["PRIMARY"] = run_trial(P, label="PRIMARY", universe=union,
                                  adv_cohort=True, by_sector=False)
    trials["SECONDARY"] = run_trial(P, label="SECONDARY", universe=union,
                                    adv_cohort=True, by_sector=True)
    trials["CONTROL1"] = run_trial(P, label="CONTROL1", universe=P["mega"],
                                   adv_cohort=False, by_sector=False, fill="close")
    trials["CONTROL2"] = run_trial(P, label="CONTROL2", universe=P["d67"],
                                   adv_cohort=False, by_sector=False, fill="close")
    # BH-FDR across the 2 gated trials
    pv = {k: trials[k]["ls_p_hac"] for k in ("PRIMARY", "SECONDARY")
          if trials[k].get("ls_p_hac") is not None}
    bh = benjamini_hochberg(pv, alpha=0.10) if pv else {}
    out = {"stamp": P["stamp"], "trials": trials, "bh_fdr": bh,
           "params": {"lookback": LOOKBACK, "hold": HOLD, "adv_floor": ADV_FLOOR,
                      "n_trials": N_TRIALS, "delist_monthly_2x": DELIST_MONTHLY,
                      "phantom_ret": PHANTOM_RET}}
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
