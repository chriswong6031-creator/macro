"""Adversarial verification of vol_scaled_momentum_crash.py.

Re-implements the sleeve independently and stress-tests the LEVER claim:
  (A) Look-ahead probe: does the scalar at day t use ONLY info <= t-1?
      Rebuild scalar with EXTRA lag and with a deliberately leaky (no-shift) version;
      if the leaky version barely differs, the shift is doing little and we trust it;
      if removing the shift inflates the result a lot, the +1 shift is load-bearing.
  (B) Sharpe-improvement robustness: block-bootstrap the SHARPE DIFFERENCE (scaled-raw),
      not the mean-return diff. Is the +0.094 CI strictly > 0?
  (C) In-sample tuning: sweep TARGET x CAP grid -> is +0.094 cherry-picked? report the
      DISTRIBUTION of the Sharpe delta. honest n_trials.
  (D) Coverage of the 'crash' months: how many tickers were live in Oct-1987 etc.?
      Survivorship: the worst months may rest on a handful of names.
  (E) CAP=1.0 (pure de-risk) vs CAP=2.0 (lever): is the Sharpe lift from de-risking
      alone, or from the calm-regime lever? Barroso's point is constant-risk de-risk.
  (F) Does the scaled series simply de-lever? CAGR & vol should both fall.
"""
from __future__ import annotations
import sys, math, glob, os, tempfile
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from lib import store
from engine.predictive_signals import mom_12_1
from engine import vol_managed as vm
from engine.validation import ret_moments, deflated_sharpe
from engine.trial_ledger import TrialLedger

TY = 252.0; COST_BPS = 5.0

tickers = sorted(os.path.basename(p)[:-8] for p in glob.glob("data/stocks/*.parquet"))
closes = {}
for t in tickers:
    try:
        s = store.read("stocks", t)["close"].dropna()
        if len(s) > 300: closes[t] = s
    except Exception: pass
closes = pd.DataFrame(closes).sort_index()
closes = closes[~closes.index.duplicated(keep="last")]

me = closes.resample("ME").last().index
me = [closes.index[closes.index <= d][-1] for d in me if (closes.index <= d).any()]
me = sorted(set(me))
me = [d for d in me if d >= closes.index[0] + pd.Timedelta(days=400)]

# live-ticker count per month-end (coverage / survivorship probe)
live_count = {}
def build_weights():
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for i, d in enumerate(me):
        sig = mom_12_1(closes, d).dropna()
        live = [t for t in sig.index if closes[t].loc[:d].dropna().shape[0] >= 220]
        sig = sig.loc[live]
        live_count[d] = len(sig)
        if len(sig) < 9: continue
        k = max(1, len(sig)//3)
        win = sig.sort_values(ascending=False).head(k).index
        nxt = me[i+1] if i+1 < len(me) else closes.index[-1]
        seg = (closes.index > d) & (closes.index <= nxt)
        w.loc[seg, win] = 1.0/len(win)
        w.loc[d, win] = 1.0/len(win)
    return w.loc[me[0]:]

w = build_weights()
rets = closes.pct_change().reindex(w.index)
wsh = w.shift(1).fillna(0.0)
sleeve_gross = (wsh*rets).sum(axis=1)
turn = w.diff().abs().sum(axis=1).fillna(0.0)
cost_raw = (COST_BPS/1e4)*turn.shift(1).fillna(0.0)
raw = (sleeve_gross-cost_raw).dropna()
sleeve_px = (1.0+raw).cumprod()

def ann_sharpe(r):
    r=r.dropna(); return float("nan") if r.std()==0 else r.mean()/r.std()*math.sqrt(TY)
def cagr(r):
    nav=(1+r).cumprod(); yrs=(r.index[-1]-r.index[0]).days/365.25; return nav.iloc[-1]**(1/yrs)-1
def maxdd(r):
    nav=(1+r).cumprod(); return float((nav/nav.cummax()-1).min())
def vol(r): return r.std()*math.sqrt(TY)

def scaled_series(target, cap, extra_lag=1):
    sc = vm.vol_scalar(sleeve_px, target=target, cap=cap, floor=0.0).reindex(raw.index)
    sc = sc.shift(extra_lag).fillna(0.0)
    g = sc*sleeve_gross.reindex(raw.index)
    eff = w.mul(sc.reindex(w.index).fillna(0.0), axis=0)
    turn_s = eff.diff().abs().sum(axis=1).fillna(0.0)
    cost_s = (COST_BPS/1e4)*turn_s.shift(1).fillna(0.0)
    return (g - cost_s.reindex(g.index)).dropna()

# baseline (matches original: TARGET .12, CAP 2.0, extra_lag=1)
scl = scaled_series(0.12, 2.0, 1)
idx = raw.index.intersection(scl.index)
R = raw.reindex(idx).fillna(0.0); S = scl.reindex(idx).fillna(0.0)
print(f"[base] raw Sh={ann_sharpe(R):.3f} scl Sh={ann_sharpe(S):.3f} dSh={ann_sharpe(S)-ann_sharpe(R):+.3f}")

# ---- (A) look-ahead probe: leaky (no shift) vs +1 vs +2 ----
print("\n=== (A) LOOK-AHEAD PROBE: scalar lag sensitivity ===")
for lag in (0,1,2,3):
    s = scaled_series(0.12,2.0,lag).reindex(idx).fillna(0.0)
    print(f"  extra_lag={lag}: Sh={ann_sharpe(s):.3f} maxDD={maxdd(s):.3f} worstMo={((1+s).resample('ME').prod()-1).min():.3f}")

# ---- (B) Sharpe-DIFFERENCE block bootstrap (paired blocks) ----
print("\n=== (B) PAIRED BLOCK-BOOTSTRAP of Sharpe DIFFERENCE (scaled-raw) ===")
rng = np.random.default_rng(7)
Rv=R.values; Sv=S.values; n=len(Rv); block=21; nb=int(np.ceil(n/block)); grid=np.arange(block)
dS=np.empty(4000)
for k in range(4000):
    st = rng.integers(0,n,nb)
    ix = (st[:,None]+grid[None,:]).ravel()[:n]%n
    rr=Rv[ix]; ss=Sv[ix]
    a=np.mean(ss)/np.std(ss)*math.sqrt(TY); b=np.mean(rr)/np.std(rr)*math.sqrt(TY)
    dS[k]=a-b
print(f"  Sharpe-diff 95% CI: [{np.percentile(dS,2.5):+.3f}, {np.percentile(dS,50):+.3f}, {np.percentile(dS,97.5):+.3f}]  P(dSh>0)={np.mean(dS>0):.3f}")

# ---- (C) TARGET x CAP grid: distribution of Sharpe delta ----
print("\n=== (C) IN-SAMPLE TUNING: TARGET x CAP grid (net) ===")
deltas=[]
for tg in (0.08,0.10,0.12,0.15,0.20):
    row=[]
    for cp in (1.0,1.5,2.0,3.0):
        s=scaled_series(tg,cp,1).reindex(idx).fillna(0.0)
        d=ann_sharpe(s)-ann_sharpe(R); deltas.append(d); row.append(f"{d:+.3f}")
    print(f"  TARGET={tg:.2f}: CAP[1.0,1.5,2.0,3.0]={row}")
print(f"  delta distribution: min={min(deltas):+.3f} med={np.median(deltas):+.3f} max={max(deltas):+.3f} frac>0={np.mean(np.array(deltas)>0):.2f}")

# ---- (D) coverage of crash months ----
print("\n=== (D) COVERAGE / SURVIVORSHIP at worst months ===")
mr=(1+R).resample("ME").prod()-1
worst=mr.nsmallest(8).index
lc=pd.Series(live_count)
for d in worst:
    # find the rebalance month-end at or before d
    asof=[x for x in me if x<=d]
    cnt = live_count.get(asof[-1]) if asof else None
    print(f"  {d.date()}  raw {mr.loc[d]:+.3f}  live_names~{cnt}")
print(f"  median live names across all rebalances: {int(lc.median())}; min {int(lc.min())}")

# ---- (E) CAP=1.0 pure de-risk vs CAP=2.0 lever ----
print("\n=== (E) DE-RISK (CAP=1.0) vs LEVER (CAP=2.0) ===")
for cp in (1.0,2.0):
    s=scaled_series(0.12,cp,1).reindex(idx).fillna(0.0)
    print(f"  CAP={cp}: Sh={ann_sharpe(s):.3f} CAGR={cagr(s):.3f} vol={vol(s):.3f} maxDD={maxdd(s):.3f}")
print(f"  raw    : Sh={ann_sharpe(R):.3f} CAGR={cagr(R):.3f} vol={vol(R):.3f} maxDD={maxdd(R):.3f}")

# ---- (F) DSR honest: deltas are 20 configs, not 12 ----
print("\n=== (F) DSR with n_trials reflecting the grid actually searched (20) ===")
for name,r in (("raw",R),("scaled",S)):
    m=ret_moments(r)
    _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                       family="vol_scaled_momentum_verify")
    _led.log_grid([{"trial": i} for i in range(20)], family="vol_scaled_momentum_verify")
    d=deflated_sharpe(m[0],m[1],m[2],m[3],ledger=_led, family="vol_scaled_momentum_verify")
    print(f"  {name}: dsr={d['dsr']} sr_ann={d['sr_annual']} sr0_ann={d['sr0_annual']}")
