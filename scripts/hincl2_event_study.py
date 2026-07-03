#!/usr/bin/env python3
"""H-INCL-2 deeper-panel re-run — Stock-Connect southbound INCLUSION events.

Pre-registered in research/HINCL2_PREREG.md (committed BEFORE this run). Amends the
run-1 study (scripts/hincl_event_study.py) by widening the price panel from the 157-name
closes_deep to the UNION of all local HK per-ticker stores (closes_deep + data/hk_stocks +
hk_stocks_ext), refreshing the HSI benchmark, and bumping DSR n_trials 30->32. Every
mechanism / gate / episode rule / fill rule / verdict rule is inherited verbatim.

NO wiring. Report + registry only.
"""
from __future__ import annotations
import json
import pathlib

import numpy as np
import pandas as pd

from engine.validation import (
    newey_west_tstat, benjamini_hochberg, deflated_sharpe, ret_moments,
)

ROSTER = pathlib.Path("data/hk_connect_roster/roster.parquet")
CLOSES_DEEP = pathlib.Path("data/hk_search/closes_deep.parquet")
HK_STOCKS = pathlib.Path("data/hk_stocks")
EXT = pathlib.Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/"
                   ".claude/worktrees/amazing-blackburn-5d2027/data/hk_stocks_ext")
HSI_FRESH = pathlib.Path("data/hk/_HSI.parquet")

N_TRIALS = 32          # program-level DSR (masterplan §6; bumped 30->32, stricter)
HORIZONS = [5, 10, 20, 40, 60]
PRIMARY_H = 20
PRE = 10
SUSP_MAX = 5


def build_union_panel():
    """Union close matrix over closes_deep + data/hk_stocks + hk_stocks_ext.
    De-dup by ticker preferring the longest non-null close history."""
    series = {}  # ticker -> pd.Series(close)

    def add(tk, s):
        s = s.dropna()
        s = s[~s.index.duplicated(keep="last")]
        if tk not in series or s.notna().sum() > series[tk].notna().sum():
            series[tk] = s

    # closes_deep (wide)
    cd = pd.read_parquet(CLOSES_DEEP)
    cd.index = pd.to_datetime(cd.index)
    for tk in cd.columns:
        add(tk, cd[tk])
    # in-tree per-ticker
    for p in sorted(HK_STOCKS.glob("*.HK.parquet")):
        tk = p.name.replace(".parquet", "")
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index)
        if "close" in d.columns:
            add(tk, d["close"])
    # ext per-ticker (R2 / gitignored, absolute path)
    for p in sorted(EXT.glob("*.HK.parquet")):
        tk = p.name.replace(".parquet", "")
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index)
        if "close" in d.columns:
            add(tk, d["close"])

    panel = pd.DataFrame(series).sort_index()
    panel = panel[~panel.index.duplicated(keep="last")]
    return panel


def load():
    df = pd.read_parquet(ROSTER)
    closes = build_union_panel()
    hsi = pd.read_parquet(HSI_FRESH)["close"]
    hsi.index = pd.to_datetime(hsi.index)
    hsi = hsi[~hsi.index.duplicated(keep="last")].sort_index()
    cal = closes.index
    return df, closes, hsi, cal


def next_trading_day(d, cal):
    pos = cal.searchsorted(pd.Timestamp(d), side="right")
    if pos >= len(cal):
        return None
    return cal[pos]


def _block_mean_ci(x, block=4, B=5000, seed=7):
    x = np.asarray(x, float)
    n = len(x)
    if n < 4:
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        means[k] = x[idx].mean()
    return [round(float(np.percentile(means, p)), 5) for p in (5, 50, 95)]


def car_for_event(ticker, fill_day, closes, hsi, h, pre=PRE):
    """Index-relative CAR over [fill, fill+h]; also pre-run [-pre,0]. Suspension-honest."""
    if ticker not in closes.columns:
        return None, None, False
    s = closes[ticker].dropna()
    if s.empty:
        return None, None, False
    cal = closes.index
    pos = cal.searchsorted(fill_day, side="left")
    if pos >= len(cal):
        return None, None, False
    fill_pos = None
    for k in range(0, SUSP_MAX + 1):
        if pos + k >= len(cal):
            break
        day = cal[pos + k]
        if day in s.index and np.isfinite(s.get(day, np.nan)):
            fill_pos = pos + k
            break
    if fill_pos is None:
        return None, None, False
    end_pos = fill_pos + h
    if end_pos >= len(cal):
        return None, None, False
    win_days = cal[fill_pos:end_pos + 1]
    sub = s.reindex(win_days).dropna()
    idx = hsi.reindex(win_days).dropna()
    common = sub.index.intersection(idx.index)
    if len(common) < max(3, h // 2):
        return None, None, False
    sub = sub.reindex(common); idx = idx.reindex(common)
    car = float(np.log(sub.iloc[-1] / sub.iloc[0]) - np.log(idx.iloc[-1] / idx.iloc[0]))
    pre_lo = max(0, fill_pos - pre)
    pdays = cal[pre_lo:fill_pos + 1]
    ps = s.reindex(pdays).dropna(); pi = hsi.reindex(pdays).dropna()
    pc = ps.index.intersection(pi.index)
    car_pre = None
    if len(pc) >= 3:
        ps = ps.reindex(pc); pi = pi.reindex(pc)
        car_pre = float(np.log(ps.iloc[-1] / ps.iloc[0]) - np.log(pi.iloc[-1] / pi.iloc[0]))
    return car, car_pre, True


def event_curve(adds, closes, hsi, cal, anchor, lo=-10, hi=60):
    """Exploratory event-time CAR curve t=lo..hi around the fill bar, averaged over events.
    Aligns each studiable event's index-relative log-CAR (relative to fill-bar=0)."""
    rows = []
    for _, row in adds.iterrows():
        fill = _fill_day(row, anchor, cal)
        if fill is None:
            continue
        tk = row["ticker"]
        if tk not in closes.columns:
            continue
        s = closes[tk].dropna()
        pos = cal.searchsorted(fill, side="left")
        # snap to first valid at/after fill within SUSP_MAX
        fp = None
        for k in range(0, SUSP_MAX + 1):
            if pos + k < len(cal) and cal[pos + k] in s.index:
                fp = pos + k; break
        if fp is None:
            continue
        lo_pos, hi_pos = fp + lo, fp + hi
        if lo_pos < 0 or hi_pos >= len(cal):
            continue
        days = cal[lo_pos:hi_pos + 1]
        sv = s.reindex(days); iv = hsi.reindex(days)
        base_s = s.get(cal[fp]); base_i = hsi.get(cal[fp])
        if not (np.isfinite(base_s) and np.isfinite(base_i)):
            continue
        rel = np.log(sv / base_s) - np.log(iv / base_i)  # 0 at fill bar
        rel.index = np.arange(lo, hi + 1)
        rows.append(rel)
    if not rows:
        return None
    M = pd.concat(rows, axis=1)
    curve = M.mean(axis=1)
    n = M.notna().sum(axis=1)
    return {str(int(t)): [round(float(curve.loc[t]), 5), int(n.loc[t])]
            for t in curve.index if t in (-10, -5, -3, -1, 0, 1, 3, 5, 10, 20, 40, 60)}


def _fill_day(row, anchor, cal):
    if anchor == "announce":
        return next_trading_day(row["announce_date"], cal)
    eff = next_trading_day(row["announce_date"], cal)
    return next_trading_day(eff, cal) if eff is not None else None


def run_trial(adds, closes, hsi, cal, anchor, h):
    ev = []
    all_add_tickers = set(adds["ticker"])
    studiable_tickers = set()
    for _, row in adds.iterrows():
        fill = _fill_day(row, anchor, cal)
        if fill is None:
            continue
        car, car_pre, ok = car_for_event(row["ticker"], fill, closes, hsi, h)
        if ok:
            ep = row["announce_date"] if anchor == "announce" else next_trading_day(row["announce_date"], cal)
            ev.append((pd.Timestamp(ep).normalize(), row["ticker"], car, car_pre))
            studiable_tickers.add(row["ticker"])
    if not ev:
        return {"anchor": anchor, "h": h, "n_events": 0, "episode_k": 0,
                "n_add_tickers_total": len(all_add_tickers), "n_studiable_tickers": 0}
    edf = pd.DataFrame(ev, columns=["episode", "ticker", "car", "car_pre"])
    epi = edf.groupby("episode")["car"].mean().sort_index()
    epi_pre = edf.groupby("episode")["car_pre"].mean()
    x = epi.to_numpy(float)
    K = len(x)
    nw = newey_west_tstat(x, lags=4) if K >= 8 else {"mean": float(np.mean(x)) if K else None,
                                                     "se": None, "t": None, "p": None, "n": K}
    ci = _block_mean_ci(x)
    dsr = None
    mom = ret_moments(pd.Series(x))
    if K >= 3 and mom is not None:
        sr, sk, ku, _ = mom
        try:
            dsr = deflated_sharpe(sr, sk, ku, T=K, n_trials=N_TRIALS)
        except Exception:
            dsr = None
    sh = None
    if K >= 4:
        h1 = x[:K // 2]; h2 = x[K // 2:]
        sh = {"h1_mean": round(float(np.mean(h1)), 5), "h2_mean": round(float(np.mean(h2)), 5),
              "same_sign": bool(np.sign(np.mean(h1)) == np.sign(np.mean(h2)) and np.mean(h1) != 0)}
    nonstud = all_add_tickers - studiable_tickers
    x_lb = np.concatenate([x, np.zeros(len(nonstud))]) if nonstud else x
    lb_mean = float(np.mean(x_lb))
    lb_nw = newey_west_tstat(x_lb, lags=4) if len(x_lb) >= 8 else {"t": None}
    return {
        "anchor": anchor, "h": h,
        "n_events": len(edf), "episode_k": K,
        "n_add_tickers_total": len(all_add_tickers),
        "n_studiable_tickers": len(studiable_tickers),
        "mean_car": round(float(np.mean(x)), 5),
        "hac": nw, "mean_ci90": ci,
        "dsr": dsr, "split_half": sh,
        "pre_run_mean": round(float(epi_pre.mean()), 5) if epi_pre.notna().any() else None,
        "surv_lb_mean": round(lb_mean, 5), "surv_lb_hac_t": lb_nw.get("t"),
        "n_imputed_zero": len(nonstud),
    }


def main():
    df, closes, hsi, cal = load()
    adds = df[df.action == "add"].copy()
    removes = df[df.action == "remove"].copy()

    # ---- headline coverage (pre-registered §1) ----
    add_tk = set(adds.ticker.unique())
    cov = len(add_tk & set(closes.columns))
    print(f"PANEL union names={closes.shape[1]} | panel end={closes.index.max().date()} | "
          f"HSI end={hsi.index.max().date()}")
    print(f"COVERAGE add-tickers on union panel: {cov}/{len(add_tk)} "
          f"({100*cov/len(add_tk):.1f}%)  [run1: 38/{len(add_tk)}]")

    results = {"roster_add_events": int(len(adds)),
               "roster_add_tickers": int(adds.ticker.nunique()),
               "roster_remove_events": int(len(removes)),
               "panel_names": int(closes.shape[1]),
               "panel_end": str(closes.index.max().date()),
               "hsi_end": str(hsi.index.max().date()),
               "coverage_add_tickers": cov,
               "coverage_frac": round(cov / len(add_tk), 4),
               "n_trials_dsr": N_TRIALS, "primary_horizon": PRIMARY_H,
               "trials": {}}

    for anchor in ("announce", "effective"):
        results["trials"][anchor] = {}
        for h in HORIZONS:
            r = run_trial(adds, closes, hsi, cal, anchor, h)
            results["trials"][anchor][f"h{h}"] = r
            if h == PRIMARY_H:
                t = r.get("hac", {}).get("t")
                print(f"[{anchor} +{h}d] K={r.get('episode_k')} events={r.get('n_events')} "
                      f"studiable_tk={r.get('n_studiable_tickers')}/{r.get('n_add_tickers_total')} "
                      f"meanCAR={r.get('mean_car')} HAC_t={t} "
                      f"DSR={(r.get('dsr') or {}).get('dsr')} LB_mean={r.get('surv_lb_mean')}")

    # BH-FDR across the 2 gated primary-horizon one-sided p-values
    pvals = {}
    for anchor in ("announce", "effective"):
        pr = results["trials"][anchor][f"h{PRIMARY_H}"]
        p = pr.get("hac", {}).get("p")
        if p is not None:
            m = pr.get("mean_car", 0) or 0
            p1 = (p / 2.0) if m > 0 else (1 - p / 2.0)
            pvals[anchor] = p1
    results["bh_fdr"] = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}
    results["bh_fdr_pvals_onesided"] = pvals

    # exploratory: event-time CAR curve (announce anchor) — the pre-fill run-up profile
    results["event_curve_announce"] = event_curve(adds, closes, hsi, cal, "announce")

    # exploratory removal side (effective, +20d) — NOT gated, bigger sample now
    if len(removes):
        rr = run_trial(removes, closes, hsi, cal, "effective", PRIMARY_H)
        results["exploratory_removal_eff_h20"] = {
            "episode_k": rr.get("episode_k"), "n_events": rr.get("n_events"),
            "studiable_tk": rr.get("n_studiable_tickers"),
            "mean_car": rr.get("mean_car"), "hac_t": rr.get("hac", {}).get("t"),
            "pre_run_mean": rr.get("pre_run_mean")}
        rr_ann = run_trial(removes, closes, hsi, cal, "announce", PRIMARY_H)
        results["exploratory_removal_ann_h20"] = {
            "episode_k": rr_ann.get("episode_k"), "n_events": rr_ann.get("n_events"),
            "mean_car": rr_ann.get("mean_car"), "hac_t": rr_ann.get("hac", {}).get("t"),
            "pre_run_mean": rr_ann.get("pre_run_mean")}

    out = pathlib.Path("data/experiments/hincl2_event_study_results.json")
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {out}")
    return results


if __name__ == "__main__":
    main()
