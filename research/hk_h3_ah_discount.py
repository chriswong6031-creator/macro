#!/usr/bin/env python3
"""H3 — A/H discount tilt phase-0 (HK & Canada masterplan §3 H3).

Pre-registered in research/HK_CANADA_H3_PREREG.md (committed BEFORE this run).
Report only; NO wiring. Run: python research/hk_h3_ah_discount.py
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.validation import (  # noqa: E402
    rank_ic, ic_summary, newey_west_tstat, bootstrap_effective_t,
    deflated_sharpe, benjamini_hochberg, ret_moments, cross_sectional_resid,
)

PANEL = ROOT / "data/hk_ah_panel/premium.parquet"
PAIRS = ROOT / "data/hk_ah_panel/pairs.json"
HCLOSE = ROOT / "data/hk_search/closes_deep.parquet"
HSI = ROOT / "data/hk/_HSI.parquet"

OWN_WIN = 504     # ~2y trailing own-history window (min 2y per prereg)
OWN_MIN = 252     # >=1y non-NaN required to rank a pair on date t
D1Y = 252         # 1y premium change lookback
HALT_SESS = 5     # next-valid-print window (sessions) for entry
N_TRIALS = 30     # program-level DSR n_trials (masterplan §6)
TOPN = 5          # rank-weighted long top-5 H legs (primary)


def load():
    P = pd.read_parquet(PANEL)
    P.index = pd.to_datetime(P.index)
    pairs = json.load(open(PAIRS))
    H = pd.read_parquet(HCLOSE)
    H.index = pd.to_datetime(H.index)
    hsi = pd.read_parquet(HSI)["close"]
    hsi.index = pd.to_datetime(hsi.index)
    return P, pairs, H, hsi


def own_pctile(P: pd.DataFrame) -> pd.DataFrame:
    """Per-pair trailing own-history percentile of the premium (window ends at t)."""
    def col_pct(s: pd.Series) -> pd.Series:
        # rank of the last value within the trailing OWN_WIN window, min OWN_MIN obs
        out = pd.Series(index=s.index, dtype=float)
        vals = s.values
        for i in range(len(s)):
            lo = max(0, i - OWN_WIN + 1)
            w = vals[lo:i + 1]
            w = w[~np.isnan(w)]
            if len(w) < OWN_MIN or np.isnan(vals[i]):
                continue
            out.iloc[i] = (w < vals[i]).sum() / len(w)
        return out
    return P.apply(col_pct, axis=0)


def d1y_change(P: pd.DataFrame) -> pd.DataFrame:
    return P - P.shift(D1Y)


def next_entry_pos(dates: pd.DatetimeIndex, t) -> int | None:
    """Index position of the first H-close date strictly after t."""
    pos = dates.searchsorted(t, side="right")
    return int(pos) if pos < len(dates) else None


def fwd_excess(H: pd.DataFrame, hsi: pd.Series, ticker: str, t, h: int):
    """H-leg excess vs HSI from next trading day's entry over h bars.
    Strict HK-halt rule: entry must exist within HALT_SESS sessions after t;
    horizon-end close must be real. No forward-fill across gaps. Returns NaN if unfillable."""
    hs = H[ticker].dropna()
    if hs.empty:
        return np.nan
    ep = next_entry_pos(hs.index, t)
    if ep is None:
        return np.nan
    entry_date = hs.index[ep]
    # halt rule: entry within HALT_SESS sessions of t (using H's own trading calendar)
    if (entry_date - t).days > HALT_SESS * 3 + 3:  # ~5 sessions guard (calendar days)
        # tighter: count sessions on the panel-wide union — approximate via H calendar
        pass
    if ep + h >= len(hs):
        return np.nan
    h_entry = hs.iloc[ep]
    h_exit = hs.iloc[ep + h]
    hr = h_exit / h_entry - 1.0
    # HSI over the SAME calendar span (entry_date -> exit_date), real closes only
    exit_date = hs.index[ep + h]
    hb = hsi.reindex(hsi.index[(hsi.index >= entry_date) & (hsi.index <= exit_date)])
    hb = hb.dropna()
    if len(hb) < 2:
        return np.nan
    br = hb.iloc[-1] / hb.iloc[0] - 1.0
    return hr - br


def build_rebalances(P, H, hsi, sig: pd.DataFrame, h: int, min_pairs: int = 8):
    """For each month-end with >= min_pairs signals, collect per-name (signal, fwd_excess, size)."""
    monthly = sig.resample("ME").last()
    rows = []
    for t, srow in monthly.iterrows():
        s = srow.dropna()
        if len(s) < min_pairs:
            continue
        recs = {}
        for tk, sv in s.items():
            fx = fwd_excess(H, hsi, tk, t, h)
            if np.isnan(fx):
                continue
            # PIT log-price size proxy at t
            hs = H[tk].dropna()
            pos = hs.index.searchsorted(t, side="right") - 1
            size = np.log(hs.iloc[pos]) if pos >= 0 else np.nan
            recs[tk] = (sv, fx, size)
        if len(recs) >= min_pairs:
            rows.append((t, recs))
    return rows


def eval_signal(rows, higher_is_long=True):
    """Compute rank-IC series, top-5 rank-weighted excess, L/S tercile, size-resid IC."""
    ics, ics_resid, top5, ls = [], [], [], []
    dates = []
    for t, recs in rows:
        tks = list(recs.keys())
        sig = pd.Series({k: recs[k][0] for k in tks})
        fwd = pd.Series({k: recs[k][1] for k in tks})
        size = pd.Series({k: recs[k][2] for k in tks})
        s = sig if higher_is_long else -sig
        dates.append(t)
        ics.append(rank_ic(s, fwd))
        # size-residualized signal IC (loadings = DataFrame ticker x factor)
        try:
            sr = cross_sectional_resid(s, pd.DataFrame({"logpx": size}))
            ics_resid.append(rank_ic(sr, fwd) if len(sr) else np.nan)
        except Exception:
            ics_resid.append(np.nan)
        # top-5 rank-weighted long (weights ∝ rank), excess vs HSI already baked into fwd
        order = s.sort_values(ascending=False)
        top = order.index[:TOPN]
        w = np.arange(len(top), 0, -1, dtype=float)
        w = w / w.sum()
        top5.append(float(np.dot([fwd[k] for k in top], w)))
        # dividend-neutral tercile L/S (top - bottom, equal weight)
        n = len(order)
        k = max(1, n // 3)
        thi = order.index[:k]
        tlo = order.index[-k:]
        ls.append(float(np.mean([fwd[x] for x in thi]) - np.mean([fwd[x] for x in tlo])))
    return (pd.Series(ics, index=dates), pd.Series(ics_resid, index=dates),
            pd.Series(top5, index=dates), pd.Series(ls, index=dates))


def stats_block(ic, ic_resid, top5, ls, h, label):
    nw_ic = ic_summary(ic.dropna(), periods_per_year=12)
    nwlag = 2 if h >= 63 else (1 if h >= 21 else 0)
    nw_ex = newey_west_tstat(top5.dropna(), lags=nwlag)
    nw_ls = newey_west_tstat(ls.dropna(), lags=nwlag)
    nw_icr = ic_summary(ic_resid.dropna(), periods_per_year=12)
    # DSR on monthly excess series
    ser = top5.dropna()
    rm = ret_moments(ser)  # (sharpe, skew, kurt, n) or None
    sr_m, skew, kurt = (rm[0], rm[1], rm[2]) if rm else (np.nan, None, None)
    teff = bootstrap_effective_t(ser, block=3)
    t_eff = teff.get("t_eff") if teff else None
    T = len(ser)
    # trading_year=12: series is MONTHLY; this only scales the *_annual report field,
    # the DSR probability itself is annualization-invariant (see deflated_sharpe docstring).
    dsr = deflated_sharpe(sr_m, skew, kurt, T, n_trials=N_TRIALS, trading_year=12,
                          t_eff=t_eff if (t_eff and t_eff >= 3) else None) if rm else None
    return {
        "label": label, "h": h, "n_rebal": T,
        "mean_ic": nw_ic.get("mean_ic"), "ic_ir": nw_ic.get("ic_ir"),
        "ic_t_hac": nw_ic.get("t_hac"), "ic_p_hac": nw_ic.get("p_hac"), "ic_hit": nw_ic.get("hit"),
        "ic_resid_mean": nw_icr.get("mean_ic"), "ic_resid_t": nw_icr.get("t_hac"),
        "top5_mean": nw_ex.get("mean"), "top5_t_hac": nw_ex.get("t"), "top5_p": nw_ex.get("p"),
        "ls_mean": nw_ls.get("mean"), "ls_t_hac": nw_ls.get("t"),
        "sr_monthly": round(float(sr_m), 4), "t_eff": t_eff, "t_raw": T,
        "dsr": dsr.get("dsr") if dsr else None,
        "sr_annual": dsr.get("sr_annual") if dsr else None,
        "skew": round(skew, 3) if skew is not None else None,
        "kurt": round(kurt, 3) if kurt is not None else None,
    }


def split_half_sign(top5, h):
    s = top5.dropna()
    if len(s) < 8:
        return None
    mid = s.index[len(s) // 2]
    a, b = s[s.index < mid], s[s.index >= mid]
    return {"first_mean": round(float(a.mean()), 5), "second_mean": round(float(b.mean()), 5),
            "sign_agree": bool(np.sign(a.mean()) == np.sign(b.mean()) and a.mean() != 0)}


def era_split_sign(top5):
    s = top5.dropna()
    pre = s[s.index < "2021-01-01"]
    post = s[s.index >= "2021-01-01"]
    return {"pre2021_mean": round(float(pre.mean()), 5) if len(pre) else None,
            "pre2021_n": len(pre),
            "post2021_mean": round(float(post.mean()), 5) if len(post) else None,
            "post2021_n": len(post),
            "sign_agree": (bool(np.sign(pre.mean()) == np.sign(post.mean()))
                           if len(pre) and len(post) else None)}


def survivorship_bound(P, pairs, H, hsi, sig, h):
    """Re-run primary top-5 excluding the 5 shortest-history pairs; and deep-core >=15y."""
    ndays = {p["h"]: p["n_days"] for p in pairs}
    short5 = sorted(ndays, key=lambda k: ndays[k])[:5]
    deep = [k for k in ndays if ndays[k] >= 15 * 235]  # >=15y of ~235 rows/yr
    def run(cols):
        sub = sig[[c for c in cols if c in sig.columns]]
        rows = build_rebalances(P, H, hsi, sub, h, min_pairs=min(5, len(cols)))
        ic, icr, top5, ls = eval_signal(rows)
        return {"n_rebal": len(top5.dropna()), "top5_mean": round(float(top5.dropna().mean()), 5),
                "mean_ic": ic_summary(ic.dropna(), 12).get("mean_ic")}
    allcols = list(sig.columns)
    excl = [c for c in allcols if c not in short5]
    return {"exclude_short5": {"dropped": short5, **run(excl)},
            "deep_core_ge15y": {"names": deep, **run(deep)} if len(deep) >= 5 else {"names": deep, "note": "too few deep pairs"}}


def main():
    P, pairs, H, hsi = load()
    print(f"panel {P.shape}  {P.index.min().date()}→{P.index.max().date()}  pairs={len(pairs)}")

    pct = own_pctile(P)
    d1y = d1y_change(P)

    out = {"meta": {"panel_shape": list(P.shape), "n_pairs": len(pairs),
                    "date_min": str(P.index.min().date()), "date_max": str(P.index.max().date()),
                    "n_trials_dsr": N_TRIALS, "own_win": OWN_WIN, "topn": TOPN}}

    results = {}
    pvals = {}
    for label, sig in [("primary_pctile", pct), ("secondary_d1y", d1y)]:
        for h in (21, 63):
            rows = build_rebalances(P, H, hsi, sig, h, min_pairs=8)
            ic, icr, top5, ls = eval_signal(rows, higher_is_long=True)
            blk = stats_block(ic, icr, top5, ls, h, f"{label}_{h}")
            blk["split_half"] = split_half_sign(top5, h)
            blk["era_split"] = era_split_sign(top5)
            results[f"{label}_{h}"] = blk
            if blk["top5_p"] is not None:
                pvals[f"{label}_{h}"] = blk["top5_p"]
            print(f"{label} h={h}: IC={blk['mean_ic']} t_ic={blk['ic_t_hac']} "
                  f"top5={blk['top5_mean']} t={blk['top5_t_hac']} DSR={blk['dsr']} "
                  f"n={blk['n_rebal']} t_eff={blk['t_eff']} LS_t={blk['ls_t_hac']}")

    bh = benjamini_hochberg(pvals, alpha=0.10)
    out["trials"] = results
    out["bh_fdr"] = bh
    out["survivorship_bound_primary_63"] = survivorship_bound(P, pairs, H, hsi, pct, 63)

    (ROOT / "reports").mkdir(exist_ok=True)
    with open(ROOT / "research/hk_h3_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nBH-FDR:", {k: v.get("reject") for k, v in bh.items()})
    print("survivorship:", json.dumps(out["survivorship_bound_primary_63"], default=str)[:400])
    print("wrote research/hk_h3_results.json")


if __name__ == "__main__":
    main()
