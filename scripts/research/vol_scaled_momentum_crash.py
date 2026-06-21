"""Vol-scaled cross-sectional momentum (Barroso-Santa-Clara crash protection).

Primary sleeve  : long top-tercile 12-1 momentum (engine.predictive_signals.mom_12_1),
                  equal-weight, monthly rebalance, on data/stocks (114 survivors).
Treatment       : scale the WHOLE sleeve's daily exposure by a vol-target scalar built
                  on the SLEEVE's own realized vol (engine.vol_managed.vol_scalar logic) —
                  constant-risk momentum. cap>1 so calm regimes can be (modestly) levered.

Compare raw vs vol-scaled momentum: Sharpe, max-drawdown, worst calendar month,
net-of-cost (5bps one-way), DSR. Verdict RISK_LEVER if vol-scaling cuts the crash /
lifts Sharpe.

HONESTY:
 - Every signal causal: mom_12_1 at month-end t uses only closes <= t; positions act
   next bar via backtest_core's internal alloc.shift(1). The sleeve vol-scalar at day t
   uses ONLY the sleeve's trailing realized returns through t-1 (built on a lagged
   forecast), so no look-ahead.
 - NET of 5bps one-way cost via backtest_core(cost_bps=5) on the sleeve allocation
   turnover (monthly cross-sectional churn + daily scalar churn).
 - DSR with honest n_trials (declared below).
 - SURVIVORSHIP: data/stocks = 114 CURRENT mega-cap survivors. Cross-sectional
   momentum on survivors is an OPTIMISTIC CONTEXT bound (losers that delisted are
   absent), not proven alpha. The crash-protection COMPARISON (raw vs scaled on the
   SAME sleeve) is the robust takeaway; absolute Sharpe is inflated.
"""
from __future__ import annotations
import sys, math, tempfile
sys.path.insert(0, ".")
import numpy as np
import pandas as pd

from lib import store
from engine.predictive_signals import mom_12_1
from engine import vol_managed as vm
from engine.validation import (backtest_core, ret_moments, deflated_sharpe,
                               dsr_verdict, block_bootstrap_ci)
from engine.trial_ledger import TrialLedger

import glob, os
TRADING_YEAR = 252.0
COST_BPS = 5.0

# ---- load survivor close panel ----
tickers = sorted(os.path.basename(p)[:-8] for p in glob.glob("data/stocks/*.parquet"))
closes = {}
for t in tickers:
    try:
        s = store.read("stocks", t)["close"].dropna()
        if len(s) > 300:
            closes[t] = s
    except Exception:
        pass
closes = pd.DataFrame(closes).sort_index()
closes = closes[~closes.index.duplicated(keep="last")]
print(f"[data] {closes.shape[1]} tickers, {closes.shape[0]} rows, "
      f"{closes.index.min().date()} -> {closes.index.max().date()}")

# ---- monthly rebalance dates (month-end trading days) ----
me = closes.resample("ME").last().index
me = [closes.index[closes.index <= d][-1] for d in me if (closes.index <= d).any()]
me = sorted(set(me))
# require a few years of warmup for 12-1 + later sleeve-vol forecast
me = [d for d in me if d >= closes.index[0] + pd.Timedelta(days=400)]
print(f"[rebal] {len(me)} monthly rebalances {me[0].date()} -> {me[-1].date()}")

# ---- build a daily TARGET-WEIGHT matrix for the top-tercile sleeve ----
# At each month-end, pick top tercile by mom_12_1 among names with valid signal AND
# >=200 days of history (so the sleeve can be vol-scaled). Equal-weight; weights held
# until the next rebalance. backtest_core shifts alloc by 1 bar, so weights set on the
# month-end date are realised from the NEXT bar (causal).
w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
for i, d in enumerate(me):
    sig = mom_12_1(closes, d).dropna()
    # require enough live history at d
    live = [t for t in sig.index if closes[t].loc[:d].dropna().shape[0] >= 220]
    sig = sig.loc[live]
    if len(sig) < 9:
        continue
    k = max(1, len(sig) // 3)
    win = sig.sort_values(ascending=False).head(k).index
    nxt = me[i + 1] if i + 1 < len(me) else closes.index[-1]
    seg = (closes.index > d) & (closes.index <= nxt)
    w.loc[seg, win] = 1.0 / len(win)
    # also set the rebalance row itself so alloc.shift(1) realises it next bar
    w.loc[d, win] = 1.0 / len(win)

w = w.loc[me[0]:]

# ---- RAW sleeve daily return (gross long-only equal-weight, weights act next bar) ----
rets = closes.pct_change().reindex(w.index)
# realised sleeve return: sum_i w_{t-1,i} * r_{t,i}  -> emulate via backtest_core per asset?
# Simpler & honest: the sleeve net return = portfolio of next-bar-acting weights.
wsh = w.shift(1).fillna(0.0)
sleeve_gross = (wsh * rets).sum(axis=1)
# turnover-based cost on the sleeve: sum |Δw| (one-way) * cost
turn = w.diff().abs().sum(axis=1).fillna(0.0)
cost_raw = (COST_BPS / 1e4) * turn.shift(1).fillna(0.0)
sleeve_raw_net = (sleeve_gross - cost_raw).dropna()

# synthetic sleeve NAV (for vol-scalar forecast on the sleeve's own price) ----
sleeve_px = (1.0 + sleeve_raw_net).cumprod()

# ---- TREATMENT: vol-target scalar on the SLEEVE's own realized vol ----
# Build scalar on the sleeve price; vol_scalar is trailing/causal. Lag by 1 extra day so
# the scalar applied to day-t return uses info through t-1 (belt-and-suspenders causality).
TARGET = 0.12          # annualized vol target for the constant-risk sleeve
CAP = 2.0              # allow modest lever in calm regimes (Barroso-style)
scalar = vm.vol_scalar(sleeve_px, target=TARGET, cap=CAP, floor=0.0).reindex(sleeve_raw_net.index)
scalar = scalar.shift(1).fillna(0.0)   # apply tomorrow's exposure from today's info

sleeve_scaled_gross = scalar * sleeve_gross.reindex(sleeve_raw_net.index)
# extra turnover from daily scalar moves -> charge cost on |Δ(scalar*w)| approximately:
# effective position = scalar * w. Turnover of the scaled book:
eff = w.mul(scalar.reindex(w.index).fillna(0.0), axis=0)
turn_s = eff.diff().abs().sum(axis=1).fillna(0.0)
cost_scaled = (COST_BPS / 1e4) * turn_s.shift(1).fillna(0.0)
sleeve_scaled_net = (sleeve_scaled_gross - cost_scaled.reindex(sleeve_scaled_gross.index)).dropna()

# align
idx = sleeve_raw_net.index.intersection(sleeve_scaled_net.index)
raw = sleeve_raw_net.reindex(idx).fillna(0.0)
scl = sleeve_scaled_net.reindex(idx).fillna(0.0)

# ---- metrics ----
def ann_sharpe(r):
    r = r.dropna()
    if r.std() == 0: return float("nan")
    return r.mean() / r.std() * math.sqrt(TRADING_YEAR)

def cagr(r):
    nav = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    return nav.iloc[-1] ** (1 / yrs) - 1

def max_dd(r):
    nav = (1 + r).cumprod()
    return (nav / nav.cummax() - 1).min()

def worst_month(r):
    m = (1 + r).resample("ME").prod() - 1
    return m.min()

def ann_vol(r):
    return r.std() * math.sqrt(TRADING_YEAR)

def summarize(name, r):
    return dict(name=name, sharpe=round(ann_sharpe(r), 3), cagr=round(cagr(r), 4),
                vol=round(ann_vol(r), 4), max_dd=round(max_dd(r), 4),
                worst_month=round(worst_month(r), 4), n=len(r))

S_raw = summarize("raw_mom", raw)
S_scl = summarize("vol_scaled_mom", scl)
print("\n=== NET OF 5bps ===")
for S in (S_raw, S_scl):
    print(S)

# ---- DSR (honest n_trials) ----
# Trials searched in THIS study: {raw, scaled} x small grid of (TARGET in {.10,.12,.15},
# CAP in {1.0,1.5,2.0}) considered during design = ~2 + 9 = ~11 configs. Declare n_trials=12.
N_TRIALS = 12
def dsr_for(r):
    m = ret_moments(r)
    if not m: return None
    sr, sk, ku, T = m
    _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                       family="vol_scaled_momentum")
    _led.log_grid([{"trial": i} for i in range(N_TRIALS)], family="vol_scaled_momentum")
    return deflated_sharpe(sr, sk, ku, T, ledger=_led, family="vol_scaled_momentum")

d_raw = dsr_for(raw); d_scl = dsr_for(scl)
print("\n=== DSR (n_trials=%d) ===" % N_TRIALS)
print("raw   ", d_raw)
print("scaled", d_scl)
print("raw   verdict:", dsr_verdict(d_raw["dsr"]) if d_raw else None)
print("scaled verdict:", dsr_verdict(d_scl["dsr"]) if d_scl else None)

# ---- crash-protection deltas ----
print("\n=== CRASH-PROTECTION DELTA (scaled - raw) ===")
print(f"Sharpe  : {S_raw['sharpe']:.3f} -> {S_scl['sharpe']:.3f}  (Δ {S_scl['sharpe']-S_raw['sharpe']:+.3f})")
print(f"MaxDD   : {S_raw['max_dd']:.3f} -> {S_scl['max_dd']:.3f}  (Δ {S_scl['max_dd']-S_raw['max_dd']:+.3f})")
print(f"WorstMo : {S_raw['worst_month']:.3f} -> {S_scl['worst_month']:.3f}  (Δ {S_scl['worst_month']-S_raw['worst_month']:+.3f})")
print(f"AnnVol  : {S_raw['vol']:.3f} -> {S_scl['vol']:.3f}")

# block-bootstrap CI on the Sharpe DIFFERENCE of the daily return series
diff = (scl - raw).dropna()
try:
    ci = block_bootstrap_ci(diff, block=21, B=4000, seed=11)
    print("\n[bootstrap] daily (scaled-raw) mean-return 95% CI:", ci)
except Exception as e:
    print("[bootstrap] skipped:", e)

# explicit worst-12 months comparison (where crash protection shows)
mr = (1 + raw).resample("ME").prod() - 1
ms = (1 + scl).resample("ME").prod() - 1
worst_idx = mr.nsmallest(8).index
print("\n=== 8 WORST RAW-MOMENTUM MONTHS: raw vs scaled ===")
for d in worst_idx:
    print(f"  {d.date()}  raw {mr.loc[d]:+.3f}   scaled {ms.loc[d]:+.3f}")
