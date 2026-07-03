#!/usr/bin/env python3
"""H-INCL event study — Stock-Connect southbound INCLUSION events.

STEP-2 of masterplan battery H-INCL. Pre-registered in research/H_INCL_PREREG.md
(committed BEFORE this run). Reads the committed roster + HK panel; computes
index-relative CARs around ADD events; runs HAC / BH-FDR / DSR / split-half on
the EPISODE-level (distinct effective-date) CAR series; reports a survivorship band.

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
from engine.trial_ledger import TrialLedger

ROSTER = pathlib.Path("data/hk_connect_roster/roster.parquet")
CLOSES = pathlib.Path("data/hk_search/closes_deep.parquet")
HSI = pathlib.Path("data/hk_search/_HSI_deep.parquet")
N_TRIALS = 30  # program-level DSR (masterplan §6), ledger-declared floor
FAMILY = "hincl_event_study"
_LED = TrialLedger.with_declared_budget(N_TRIALS, FAMILY)
HORIZONS = [5, 10, 20, 40, 60]
PRIMARY_H = 20
PRE = 10
SUSP_MAX = 5  # exclude if no valid print within 5 sessions after intended fill


def _block_mean_ci(x: np.ndarray, block: int = 4, B: int = 5000, seed: int = 7):
    """Distribution-free block-bootstrap 90% CI of the MEAN of an episode series."""
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


def load():
    df = pd.read_parquet(ROSTER)
    closes = pd.read_parquet(CLOSES)
    closes.index = pd.to_datetime(closes.index)
    hsi = pd.read_parquet(HSI)["close"]
    hsi.index = pd.to_datetime(hsi.index)
    cal = closes.index  # trading calendar (panel)
    return df, closes, hsi, cal


def next_trading_day(d: pd.Timestamp, cal: pd.DatetimeIndex):
    pos = cal.searchsorted(d, side="right")
    if pos >= len(cal):
        return None
    return cal[pos]


def car_for_event(ticker, fill_day, closes, hsi, h, pre=PRE):
    """Index-relative cumulative log-return over [fill, fill+h]; also the pre-run [-pre,0].
    Returns (car_h, car_pre, studiable_bool). Suspension rule: need a valid print within
    SUSP_MAX sessions after fill, and >= h subsequent valid bars; else not studiable."""
    if ticker not in closes.columns:
        return None, None, False
    s = closes[ticker].dropna()
    if s.empty:
        return None, None, False
    cal = closes.index
    pos = cal.searchsorted(fill_day, side="left")
    if pos >= len(cal):
        return None, None, False
    # find first valid print at/after fill within SUSP_MAX sessions
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
        return None, None, False  # window runs past panel end -> drop
    win_days = cal[fill_pos:end_pos + 1]
    sub = s.reindex(win_days).dropna()
    idx = hsi.reindex(win_days).dropna()
    common = sub.index.intersection(idx.index)
    if len(common) < max(3, h // 2):  # too many halts inside the window -> not studiable
        return None, None, False
    sub = sub.reindex(common); idx = idx.reindex(common)
    car = float(np.log(sub.iloc[-1] / sub.iloc[0]) - np.log(idx.iloc[-1] / idx.iloc[0]))
    # pre-run
    pre_lo = max(0, fill_pos - pre)
    pdays = cal[pre_lo:fill_pos + 1]
    ps = s.reindex(pdays).dropna(); pi = hsi.reindex(pdays).dropna()
    pc = ps.index.intersection(pi.index)
    car_pre = None
    if len(pc) >= 3:
        ps = ps.reindex(pc); pi = pi.reindex(pc)
        car_pre = float(np.log(ps.iloc[-1] / ps.iloc[0]) - np.log(pi.iloc[-1] / pi.iloc[0]))
    return car, car_pre, True


def run_trial(adds, closes, hsi, cal, anchor: str, h: int):
    """anchor in {'announce','effective'}. Returns dict of stats on episode-level CARs."""
    ev = []  # (episode_date, ticker, car, car_pre)
    all_add_tickers = set(adds["ticker"])
    studiable_tickers = set()
    for _, row in adds.iterrows():
        if anchor == "announce":
            fill = next_trading_day(row["announce_date"], cal)
        else:
            eff = next_trading_day(row["announce_date"], cal)  # effective = next SB day after announce
            fill = next_trading_day(eff, cal) if eff is not None else None  # next bar after effective
        if fill is None:
            continue
        car, car_pre, ok = car_for_event(row["ticker"], fill, closes, hsi, h)
        if ok:
            ep = row["announce_date"] if anchor == "announce" else next_trading_day(row["announce_date"], cal)
            ev.append((pd.Timestamp(ep).normalize(), row["ticker"], car, car_pre))
            studiable_tickers.add(row["ticker"])
    if not ev:
        return {"anchor": anchor, "h": h, "n_events": 0, "episode_k": 0}
    edf = pd.DataFrame(ev, columns=["episode", "ticker", "car", "car_pre"])
    # episode-level = average CAR within each distinct episode-date
    epi = edf.groupby("episode")["car"].mean().sort_index()
    epi_pre = edf.groupby("episode")["car_pre"].mean()
    x = epi.to_numpy(float)
    K = len(x)
    nw = newey_west_tstat(x, lags=4) if K >= 8 else {"mean": float(np.mean(x)) if K else None,
                                                     "se": None, "t": None, "p": None, "n": K}
    ci = _block_mean_ci(x)
    # DSR: Sharpe of the episode-CAR series (mean/std across episodes)
    dsr = None
    mom = ret_moments(pd.Series(x))
    if K >= 3 and mom is not None:
        sr, sk, ku, _ = mom
        try:
            dsr = deflated_sharpe(sr, sk, ku, T=K, ledger=_LED, family=FAMILY)
        except Exception:
            dsr = None
    # split-half chronological
    sh = None
    if K >= 4:
        med = np.median(np.arange(K))
        h1 = x[:K // 2]; h2 = x[K // 2:]
        sh = {"h1_mean": round(float(np.mean(h1)), 5), "h2_mean": round(float(np.mean(h2)), 5),
              "same_sign": bool(np.sign(np.mean(h1)) == np.sign(np.mean(h2)) and np.mean(h1) != 0)}
    # survivorship lower bound: impute non-panel adds as CAR=0 at horizon.
    # non-panel add tickers = add tickers never studiable (not in panel or no window)
    nonstud = all_add_tickers - studiable_tickers
    # each imputed as a single 0 episode-observation appended (conservative floor)
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
    print(f"roster: {len(df)} rows | adds {len(adds)} ({adds.ticker.nunique()} tickers) | "
          f"removes {len(removes)} | panel {closes.shape[1]} names | "
          f"panel end {closes.index.max().date()}")

    results = {"roster_add_events": int(len(adds)),
               "roster_add_tickers": int(adds.ticker.nunique()),
               "roster_remove_events": int(len(removes)),
               "panel_names": int(closes.shape[1]),
               "panel_end": str(closes.index.max().date()),
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
                      f"DSR={ (r.get('dsr') or {}).get('dsr') } "
                      f"LB_mean={r.get('surv_lb_mean')}")

    # BH-FDR across the 2 gated primary-horizon p-values
    pvals = {}
    for anchor in ("announce", "effective"):
        pr = results["trials"][anchor][f"h{PRIMARY_H}"]
        p = pr.get("hac", {}).get("p")
        if p is not None:
            # one-sided: halve the two-sided p when mean positive, else 1-p/2
            m = pr.get("mean_car", 0) or 0
            p1 = (p / 2.0) if m > 0 else (1 - p / 2.0)
            pvals[anchor] = p1
    results["bh_fdr"] = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    # exploratory removal side (effective anchor, +20d) — NOT gated
    if len(removes):
        rr = run_trial(removes, closes, hsi, cal, "effective", PRIMARY_H)
        results["exploratory_removal_eff_h20"] = {
            "episode_k": rr.get("episode_k"), "mean_car": rr.get("mean_car"),
            "hac_t": rr.get("hac", {}).get("t")}

    out = pathlib.Path("data/experiments/hincl_event_study_results.json")
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {out}")
    return results


if __name__ == "__main__":
    main()
