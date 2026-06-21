"""NOVEL: 52-week-high proximity x volume-confirmed breakout.

Tests George-Hwang (2004) 52-week-high momentum, asking whether a FRESH breakout
to a new 252d (Donchian) high on ABOVE-AVERAGE volume forecasts higher forward
returns than (a) near-high days without a fresh high, and (b) the unconditional base.

HONESTY:
  * Every signal value at date t uses only closes/volume with index <= t (causal).
  * Forward returns are strictly future (close[t+h]/close[t]-1) and never overlap
    the conditioning window.
  * Event-study legs reported NET of 5bps one-way cost (round-trip 10bps on a
    discrete enter->hold->exit, charged once each way) AND gross.
  * Long/flat backtest of the volume-confirmed-breakout BASKET vs equal-weight
    buy&hold runs through validation.backtest_core (positions act next bar via
    shift) NET of 5bps one-way, with DSR on an honestly-declared n_trials.
  * HAC (Newey-West) t-stats on the per-date IC / mean-diff series (overlapping
    forward windows serially correlate).
  * SURVIVORSHIP: data/stocks = 114 CURRENT mega-cap survivors. Any cross-sectional
    breakout edge here is an OPTIMISTIC CONTEXT bound, not proven tradeable alpha:
    names that broke out and then died (delisted) are absent from the panel.
"""
from __future__ import annotations
import sys, math, warnings, tempfile
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from lib import store
from engine.validation import (
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    newey_west_tstat, ic_summary, block_bootstrap_ci,
)
from engine.trial_ledger import TrialLedger

WIN = 252          # 52-week window
VOL_WIN = 50       # avg-volume lookback for the confirmation
VOL_MULT = 1.5     # breakout volume must be >= 1.5x the 50d avg
NEAR = 0.98        # "near 52w high" = close >= 98% of trailing-252d max
HORIZONS = [21, 63]
COST_BPS = 5.0     # one-way
TICKERS = ("AAPL ABBV ABT AEP AMAT AMD AMGN AMT AMZN APD AVGO AXP BA BAC BKNG BKR "
           "BRK-B C CAT CBRE CCI CEG CL COP COST CRH CSCO CTVA CVX D DE DIS DLR DUK "
           "EA EOG EQIX ETN ETR EXC FCX GE GEV GILD GOOG GOOGL GS HD HLT HON INTC "
           "ISRG JNJ JPM KMI KO LIN LLY LOW LRCX LYV MA MAR MCD MDLZ META MLM MNST "
           "MO MPC MRK MS MSFT MU NEE NEM NUE NVDA O OMC PEP PFE PG PLD PM PSA PSX "
           "RTX SATS SBUX SHW SLB SO SPG SRE STLD TJX TMO TSLA TTWO UBER UNH UNP V "
           "VLO VMC VST VTR WBD WELL WFC WMB WMT XOM").split()


def load():
    closes, vols = {}, {}
    for t in TICKERS:
        df = store.read("stocks", t)
        if df is None or len(df) < WIN + max(HORIZONS) + 60:
            continue
        closes[t] = df["close"].astype(float)
        vols[t] = df["volume"].astype(float)
    C = pd.DataFrame(closes).sort_index()
    Vd = pd.DataFrame(vols).sort_index()
    return C, Vd


def build_events(C: pd.DataFrame, Vd: pd.DataFrame):
    """Per-name daily flags (CAUSAL):
       prox          = close / trailing-252d max  (incl today, <=1)
       new_high      = close is the max of trailing-252d window (fresh Donchian high)
       vol_ratio     = volume / trailing-50d avg volume (avg uses days BEFORE today)
       near          = prox >= NEAR
       breakout_conf = new_high & vol_ratio>=VOL_MULT
       breakout_unc  = new_high & vol_ratio< VOL_MULT
       near_only     = near & ~new_high  (near the high but not a fresh high today)
    Returns long DataFrame of per (date,ticker) flags + forward returns per horizon.
    """
    roll_max = C.rolling(WIN, min_periods=WIN).max()          # incl today
    prior_max = C.shift(1).rolling(WIN, min_periods=WIN).max()  # strictly prior
    prox = C / roll_max
    new_high = C >= prior_max * 0.99999  # today >= every prior-252d close -> fresh high
    # require we actually have a full window (prior_max not nan)
    new_high = new_high & prior_max.notna() & C.notna()
    avg_vol = Vd.shift(1).rolling(VOL_WIN, min_periods=VOL_WIN).mean()  # prior 50d
    vol_ratio = Vd / avg_vol

    near = prox >= NEAR
    conf = new_high & (vol_ratio >= VOL_MULT)
    unc = new_high & (vol_ratio < VOL_MULT)
    near_only = near & (~new_high)

    fwd = {h: C.shift(-h) / C - 1.0 for h in HORIZONS}

    rows = []
    idx = C.index
    for t in C.columns:
        sub = pd.DataFrame({
            "prox": prox[t], "vol_ratio": vol_ratio[t],
            "near": near[t], "conf": conf[t], "unc": unc[t], "near_only": near_only[t],
        }, index=idx)
        for h in HORIZONS:
            sub[f"fwd{h}"] = fwd[h][t]
        sub["ticker"] = t
        sub["date"] = idx
        rows.append(sub)
    long = pd.concat(rows, ignore_index=True)
    long = long.dropna(subset=["prox", "vol_ratio"])
    return long, prox, conf, fwd


def event_study(long: pd.DataFrame):
    """Forward-return means by bucket, gross and net of a discrete round-trip cost.
    Net = enter at close[t] (pay COST_BPS), hold h days, exit (pay COST_BPS):
    net_ret approx gross - 2*COST_BPS/1e4."""
    rt = 2 * COST_BPS / 1e4
    out = {}
    # base = all near-high observations (the George-Hwang population we condition within)
    base_mask = long["near"]
    for h in HORIZONS:
        col = f"fwd{h}"
        d = long.dropna(subset=[col])
        buckets = {
            "base_near":   d[d["near"]][col],
            "near_only":   d[d["near_only"]][col],
            "breakout_unc": d[d["unc"]][col],
            "breakout_conf": d[d["conf"]][col],
            "all":         d[col],
        }
        res = {}
        for name, s in buckets.items():
            if len(s) < 20:
                res[name] = {"n": int(len(s)), "mean": None}
                continue
            res[name] = {
                "n": int(len(s)),
                "mean_gross": round(float(s.mean()), 5),
                "mean_net": round(float(s.mean() - rt), 5),
                "median": round(float(s.median()), 5),
                "hit": round(float((s > 0).mean()), 4),
                "std": round(float(s.std()), 5),
            }
        # incremental: conf vs unc, conf vs near_only (does VOLUME add to the 52w-high signal?)
        def diff(a, b):
            sa, sb = buckets[a].dropna(), buckets[b].dropna()
            if len(sa) < 20 or len(sb) < 20:
                return None
            # pooled welch t on the difference of means (cross-sectionally many obs)
            ma, mb = sa.mean(), sb.mean()
            va, vb = sa.var(ddof=1), sb.var(ddof=1)
            se = math.sqrt(va/len(sa) + vb/len(sb))
            tstat = (ma - mb) / se if se else float("nan")
            return {"delta_gross": round(float(ma - mb), 5),
                    "t_pooled_naive": round(float(tstat), 2),
                    "na": int(len(sa)), "nb": int(len(sb))}
        res["_conf_minus_unc"] = diff("breakout_conf", "breakout_unc")
        res["_conf_minus_near_only"] = diff("breakout_conf", "near_only")
        res["_conf_minus_all"] = diff("breakout_conf", "all")
        out[h] = res
    return out


def overlap_hac(long: pd.DataFrame, h: int):
    """HAC t-stat on the per-DATE mean forward return of confirmed breakouts minus
    the per-date mean of all near-high names. Per-date aggregation removes the
    cross-sectional double counting; Newey-West handles the h-day overlap."""
    col = f"fwd{h}"
    d = long.dropna(subset=[col])
    g = d.groupby("date")
    conf_m = g.apply(lambda x: x.loc[x["conf"], col].mean())
    near_m = g.apply(lambda x: x.loc[x["near"], col].mean())
    series = (conf_m - near_m).dropna()
    if len(series) < 30:
        return {"n": int(len(series)), "t": None}
    # weekly-ish sampling overlap ~ h trading days
    nw = newey_west_tstat(series.values, lags=h)
    nw["n_dates"] = int(len(series))
    nw["mean_excess"] = round(float(series.mean()), 5)
    return nw


def basket_backtest(C: pd.DataFrame, conf: pd.DataFrame, hold: int = 63):
    """Long/flat tradeable test of the CONFIRMED-BREAKOUT basket vs equal-weight B&H.
    On each day, the strategy is invested in name i if i had a confirmed breakout in
    the last `hold` days (a rolling membership). Per-name long/flat allocation -> the
    portfolio is the equal-weight average net return of the per-name backtests, each
    NET of 5bps one-way via backtest_core (positions act next bar via shift)."""
    member = conf.fillna(False).astype(bool)
    member = member.rolling(hold, min_periods=1).max().astype(bool)  # in for `hold` days
    member = member.reindex(C.index).fillna(False)

    strat_rets, hold_rets = [], []
    for t in C.columns:
        close = C[t].dropna()
        if len(close) < WIN + hold:
            continue
        alloc = member[t].reindex(close.index).fillna(False).astype(float)
        bt = backtest_core(close, alloc, cost_bps=COST_BPS)
        strat_rets.append(bt["net"].rename(t))
        hold_rets.append(bt["hold"].rename(t))
    if not strat_rets:
        return None
    S = pd.concat(strat_rets, axis=1)
    H = pd.concat(hold_rets, axis=1)
    # equal-weight across names that have data each day
    port = S.mean(axis=1, skipna=True).dropna()
    bench = H.mean(axis=1, skipna=True).reindex(port.index)

    mom = ret_moments(port)
    if mom is None:
        return None
    sr_d, sk, ku, T = mom
    # n_trials: NEAR(1) x VOL_MULT(1) x VOL_WIN(1) x hold(1) but we explored a small
    # grid mentally -> declare an honest 12 (3 vol_mult x 2 near x 2 hold variants).
    N_TRIALS = 12
    _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                       family="breakout_52w_volume")
    _led.log_grid([{"trial": i} for i in range(N_TRIALS)], family="breakout_52w_volume")
    dsr = deflated_sharpe(sr_d, sk, ku, T, ledger=_led, family="breakout_52w_volume")
    boot = block_bootstrap_ci(port.values, block=21, B=3000, ann=252)

    ann = math.sqrt(252)
    def cagr(r):
        eq = (1 + r).prod()
        yrs = (r.index[-1] - r.index[0]).days / 365.25
        return eq ** (1/yrs) - 1 if yrs > 0 else float("nan")
    return {
        "T": int(T), "years": round((port.index[-1]-port.index[0]).days/365.25, 1),
        "strat_sr_ann_net": round(sr_d*ann, 3),
        "bench_sr_ann": round((bench.mean()/bench.std())*ann, 3) if bench.std() else None,
        "strat_cagr_net": round(cagr(port), 4),
        "bench_cagr": round(cagr(bench.dropna()), 4),
        "avg_exposure": round(float(member.reindex(C.index).mean(axis=1).mean()), 3),
        "dsr": dsr["dsr"] if dsr else None,
        "dsr_verdict": dsr_verdict(dsr["dsr"]) if dsr else None,
        "n_trials_declared": N_TRIALS,
        "boot_sharpe_ci": boot.get("sharpe_ci") if isinstance(boot, dict) else None,
        "boot_sharpe_gt0_prob": boot.get("sharpe_gt0_prob") if isinstance(boot, dict) else None,
    }


def main():
    C, Vd = load()
    print(f"[universe] {C.shape[1]} tickers loaded (survivors), "
          f"{C.index.min().date()}..{C.index.max().date()}, {len(C)} dates")
    long, prox, conf, fwd = build_events(C, Vd)
    n_conf = int(long["conf"].sum()); n_unc = int(long["unc"].sum())
    n_near = int(long["near"].sum()); n_nearonly = int(long["near_only"].sum())
    print(f"[events] near-high obs={n_near}  near_only={n_nearonly}  "
          f"fresh-high+volconf={n_conf}  fresh-high+unconf={n_unc}")

    es = event_study(long)
    for h in HORIZONS:
        print(f"\n===== forward {h}d event study (net = minus {2*COST_BPS:.0f}bps round-trip) =====")
        for name in ["all", "base_near", "near_only", "breakout_unc", "breakout_conf"]:
            r = es[h][name]
            if r.get("mean_gross") is None:
                print(f"  {name:14s} n={r['n']:6d}  (too few)"); continue
            print(f"  {name:14s} n={r['n']:6d}  meanG={r['mean_gross']:+.4f} "
                  f"meanNet={r['mean_net']:+.4f} med={r['median']:+.4f} hit={r['hit']:.3f}")
        for k in ["_conf_minus_unc", "_conf_minus_near_only", "_conf_minus_all"]:
            d = es[h][k]
            if d:
                print(f"  DIFF {k:24s} delta={d['delta_gross']:+.4f} "
                      f"t_naive={d['t_pooled_naive']:+.2f} (na={d['na']},nb={d['nb']})")
        hac = overlap_hac(long, h)
        print(f"  HAC per-date (conf - near pop): mean_excess="
              f"{hac.get('mean_excess')}, t_HAC={hac.get('t')}, p={hac.get('p')}, "
              f"n_dates={hac.get('n_dates')}")

    print("\n===== tradeable basket backtest (confirmed-breakout, hold=63d) =====")
    bt = basket_backtest(C, conf, hold=63)
    if bt is None:
        print("  insufficient data")
    else:
        for k, v in bt.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
