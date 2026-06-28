"""NOVEL: short-term reversal in market-RESIDUAL returns (Blitz-Huij-Lansdorp 2013).

Hypothesis: short-term (1-week) reversal is CLEANER in residual (market-neutralized)
returns than in raw returns. For each name: trailing 1y CAUSAL beta to _GSPC, form
the 5d residual return = name_5d_ret - beta * mkt_5d_ret; signal = -trailing 5d
residual return (buy residual losers). Compare residual-reversal vs raw-reversal via
cross-sectional rank IC (non-overlapping forward windows) and a net-of-cost long/flat
top-decile backtest.

HONESTY:
 - All signals CAUSAL: beta uses 252d window ending at t; residual/raw return uses
   returns up to and including t; forward windows strictly t+1..t+h.
 - Non-overlapping IC sampling (every h trading days) -> independent forward windows;
   t across names per date, then HAC across dates.
 - NET-OF-COST 5bps one-way via backtest_core.
 - SURVIVORSHIP: data/stocks = 114 current survivors. Cross-sectional results are an
   optimistic CONTEXT upper bound, NOT proven tradeable alpha.
"""
from __future__ import annotations
import sys, warnings, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib import store
from engine.validation import (
    backtest_core, rank_ic, ic_summary, newey_west_tstat,
    ret_moments, deflated_sharpe, dsr_verdict, block_bootstrap_ci,
)
from engine.trial_ledger import TrialLedger

BETA_WIN = 252      # 1y trailing beta
LOOK = 5            # signal formation window (1 week)
FWD_LIST = [5, 10]  # forward horizons
COST_BPS = 5.0      # one-way
MIN_NAMES = 25      # min cross-section per date

# ---------- load universe ----------
import os
tickers = sorted(p.stem for p in (ROOT / "data" / "stocks").glob("*.parquet"))
closes = {}
for t in tickers:
    df = store.read("stocks", t)
    if df is not None and "close" in df and len(df) > BETA_WIN + 300:
        closes[t] = df["close"].astype(float)
mkt = store.read("yahoo", "_GSPC")["close"].astype(float)

px = pd.DataFrame(closes).sort_index()
# align market
mkt = mkt.reindex(px.index).ffill()
print(f"universe={px.shape[1]} names  dates={px.index.min().date()}..{px.index.max().date()}  rows={px.shape[0]}")

# daily log-ish simple returns
ret = px.pct_change()
mret = mkt.pct_change()

# ---------- causal rolling beta per name ----------
# beta_t = cov(r_i, r_m)/var(r_m) over trailing BETA_WIN ending at t (uses data <= t)
var_m = mret.rolling(BETA_WIN).var()
betas = pd.DataFrame(index=px.index, columns=px.columns, dtype=float)
for c in px.columns:
    cov = ret[c].rolling(BETA_WIN).cov(mret)
    betas[c] = cov / var_m
betas = betas.clip(-3, 3)  # sanitize extreme

# trailing LOOK-day cumulative returns (>= t), causal
cum = (1 + ret).rolling(LOOK).apply(np.prod, raw=True) - 1   # name LOOK-day ret ending t
mcum = (1 + mret).rolling(LOOK).apply(np.prod, raw=True) - 1 # mkt LOOK-day ret ending t

# residual LOOK-day return ending at t: r_i - beta_t * r_m   (beta as of t -> causal)
resid_cum = cum.sub(betas.mul(mcum, axis=0))

# signals = NEGATIVE of trailing LOOK return (buy losers)
sig_raw   = -cum
sig_resid = -resid_cum

# forward h-day returns (strictly future)
def fwd_ret(h):
    f = px.shift(-h) / px - 1.0   # ret from t to t+h, uses future only
    return f

# ---------- non-overlapping cross-sectional IC ----------
def ic_series(signal: pd.DataFrame, h: int):
    fwd = fwd_ret(h)
    # sample every h trading days -> non-overlapping forward windows
    dates = signal.index
    # start far enough so beta + LOOK are defined
    start = BETA_WIN + LOOK + 5
    sel = dates[start::h]
    ics = []
    for d in sel:
        s = signal.loc[d]
        f = fwd.loc[d]
        j = pd.concat([s.rename("s"), f.rename("f")], axis=1).dropna()
        if len(j) < MIN_NAMES:
            continue
        ics.append(rank_ic(j["s"], j["f"]))
    return pd.Series(ics).dropna()

print("\n=== CROSS-SECTIONAL RANK IC (non-overlapping, NET-of-cost N/A for IC) ===")
ic_out = {}
for h in FWD_LIST:
    ic_raw   = ic_series(sig_raw,   h)
    ic_resid = ic_series(sig_resid, h)
    sr = ic_summary(ic_raw,   periods_per_year=252//h)
    sd = ic_summary(ic_resid, periods_per_year=252//h)
    ic_out[h] = (sr, sd)
    print(f"\n h={h}d  (n_dates raw={sr.get('n')}, resid={sd.get('n')})")
    print(f"   RAW reversal     : meanIC={sr.get('mean_ic')}  IC-IR={sr.get('ic_ir')}  t_HAC={sr.get('t_hac')}  hit={sr.get('hit')}")
    print(f"   RESIDUAL reversal: meanIC={sd.get('mean_ic')}  IC-IR={sd.get('ic_ir')}  t_HAC={sd.get('t_hac')}  hit={sd.get('hit')}")

# ---------- net-of-cost long/flat backtest: top-decile residual losers ----------
# Equal-weight portfolio of top-quintile names by signal, rebalanced every LOOK days,
# benchmarked against same for raw. Build a single portfolio NAV via backtest_core on
# a synthetic close = portfolio cumulative return.
def portfolio_nav(signal: pd.DataFrame, h: int, top_frac=0.2):
    fwd = fwd_ret(h)
    start = BETA_WIN + LOOK + 5
    sel = signal.index[start::h]
    seg_rets = []        # realized net return per rebalance (already h-day fwd)
    seg_dates = []
    prev_set = set()
    for d in sel:
        s = signal.loc[d].dropna()
        if len(s) < MIN_NAMES:
            continue
        k = max(1, int(len(s) * top_frac))
        picks = s.sort_values(ascending=False).index[:k]
        f = fwd.loc[d, picks].dropna()
        if len(f) == 0:
            continue
        gross = float(f.mean())
        # turnover cost: names entering/exiting vs prev_set, one-way each side
        cur = set(picks)
        turn = len(cur.symmetric_difference(prev_set)) / max(len(cur), 1)
        cost = (COST_BPS / 1e4) * turn
        seg_rets.append(gross - cost)
        seg_dates.append(d)
        prev_set = cur
    r = pd.Series(seg_rets, index=pd.to_datetime(seg_dates))
    return r

print("\n=== NET-OF-COST LONG/FLAT TOP-QUINTILE BACKTEST (rebal every {}d, {}bps one-way) ===".format(LOOK, COST_BPS))
bt_out = {}
for h in FWD_LIST:
    r_raw   = portfolio_nav(sig_raw,   h)
    r_resid = portfolio_nav(sig_resid, h)
    ppy = 252 / h
    def summ(r, label):
        if len(r) < 10:
            return None
        ann_ret = (1 + r).prod() ** (ppy / len(r)) - 1
        sr_per = r.mean() / r.std(ddof=1) if r.std(ddof=1) else float("nan")
        sr_ann = sr_per * np.sqrt(ppy)
        nw = newey_west_tstat(r, lags=4)
        mom = ret_moments(r)
        dsr = None
        if mom:
            # honest n_trials: 2 signals (raw,resid) x 2 horizons x 2 sides tested = 8
            _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                               family="residual_reversal")
            _led.log_grid([{"trial": i} for i in range(8)], family="residual_reversal")
            dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_led, family="residual_reversal")
        print(f"   {label:18s} h={h}d: annRet={ann_ret*100:6.2f}%  SR_ann={sr_ann:5.2f}  "
              f"meanSeg={r.mean()*100:+.3f}%  t_HAC={nw['t']}  n={len(r)}  "
              f"DSR={dsr['dsr'] if dsr else 'na'}")
        return {"ann_ret": ann_ret, "sr_ann": sr_ann, "t_hac": nw["t"], "n": len(r),
                "dsr": dsr["dsr"] if dsr else None, "mean_seg": r.mean()}
    bt_out[h] = {"raw": summ(r_raw, "RAW reversal"), "resid": summ(r_resid, "RESIDUAL reversal")}

# ---------- verdict summary ----------
print("\n=== SUMMARY ===")
for h in FWD_LIST:
    sr, sd = ic_out[h]
    print(f" h={h}d IC: raw_meanIC={sr.get('mean_ic')} (t={sr.get('t_hac')}) vs resid_meanIC={sd.get('mean_ic')} (t={sd.get('t_hac')})")
print("Survivorship: 114 current survivors -> CONTEXT upper bound, not proven alpha.")
