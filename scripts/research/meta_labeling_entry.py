"""Meta-labeling (Lopez de Prado) over the validated entry-timing composite.

PRIMARY signal  : engine.strategy_signals.entry_composite_position — trend-gated
                  oversold-in-uptrend fire (z>=z_thr & price>sma200), hold 5 bars.
SECONDARY model : a PURGED-CV logistic classifier predicting P(fwd-5d ret > 0) on
                  the bars where the PRIMARY fires, using only causal features.
SIZING          : 0 / half / full of the primary position by the meta-probability.

HONESTY
  - Every feature is causal (value at t uses data <= t). Positions act via
    backtest_core's internal shift(1) (next-bar fill). Forward labels are strictly
    future (close[t+5]/close[t]-1). NET-OF-COST at 5bps one-way.
  - Meta-CV is PURGED (engine.validation.purged_folds, embargo=5) and the logistic
    is fit out-of-fold (train on the OTHER folds, predict the held fold) so the AUC /
    Brier / meta-sized Sharpe are OUT-OF-FOLD, never in-sample.
  - SURVIVORSHIP: data/stocks = 114 current mega-cap survivors. Cross-sectional
    results are an optimistic CONTEXT bound, not proven alpha. Reported as such.
  - DSR with an HONEST n_trials declared below.

Pooled panel design: we stack the per-name entry events into ONE cross-sectional
meta-training set (this is how meta-labeling is normally trained — one secondary
model over all primary fires), then for the Sharpe comparison we form an
equal-weight portfolio of the per-name positions (primary-alone vs meta-sized) and
backtest the portfolio return net of cost.
"""
from __future__ import annotations
import sys, math, tempfile
sys.path.insert(0, ".")
import numpy as np
import pandas as pd

from lib import store
from engine import strategy_signals as ss
from engine import vol_managed as vm
from engine import validation as val
from engine.trial_ledger import TrialLedger

Z_THR = 1.0
H = 5                      # forward window / hold
COST_BPS = 5.0            # one-way
EMBARGO = H               # forward label leaks H days across fold edges
K_FOLDS = 6
N_TRIALS = 24            # honest: ~ universe of meta-config variants we'd consider
SEED = 7
rng = np.random.default_rng(SEED)


# ------------------------------------------------------------------ helpers
def causal_features(df: pd.DataFrame, mkt: pd.Series) -> pd.DataFrame:
    """All CAUSAL (value at t uses only data <= t)."""
    c = df["close"]
    entry_z = ss.entry_timing_z(df)                          # composite oversold z
    trend = c / ss.sma(c, 200) - 1.0                          # trend strength
    rvol = vm.realized_vol(c, 21)                             # realized vol (annualized)
    dist52 = c / c.rolling(252, min_periods=60).max() - 1.0   # distance from 52w high (<=0)
    mkt_al = mkt.reindex(c.index).ffill()
    regime = (mkt_al > ss.sma(mkt_al, 200)).astype(float)     # SPX>200dma (1/0)
    out = pd.DataFrame({
        "entry_z": entry_z,
        "trend": trend,
        "rvol": rvol,
        "dist52": dist52,
        "regime": regime,
    })
    return out


def fwd_ret(close: pd.Series, h: int) -> pd.Series:
    return close.shift(-h) / close - 1.0


def fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 600, lr: float = 0.1,
                 l2: float = 1.0) -> np.ndarray:
    """Standardized-input logistic regression via GD with L2. Returns weights incl bias.
    Standardization stats are computed on the TRAIN X passed in (no leakage)."""
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        f = 1.0 / (1.0 + np.exp(-(Xb @ w)))
        g = Xb.T @ (f - y) / n
        g[1:] += l2 * w[1:] / n
        w -= lr * g
    return w


def predict_logistic(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return 1.0 / (1.0 + np.exp(-(Xb @ w)))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Rank AUC (Mann-Whitney)."""
    y = np.asarray(y); p = np.asarray(p)
    pos = p[y == 1]; neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(p)
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    # average ties
    s = pd.Series(p)
    ranks = s.rank(method="average").values
    rsum = ranks[y == 1].sum()
    n1 = (y == 1).sum(); n0 = (y == 0).sum()
    return (rsum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


# ------------------------------------------------------------------ build panel
FEATS = ["entry_z", "trend", "rvol", "dist52", "regime"]
import os
tickers = sorted(f[:-8] for f in os.listdir("data/stocks") if f.endswith(".parquet"))
mkt = store.read("yahoo", "_GSPC")["close"]

# common trading calendar across the panel
rows = []                     # per-event records for meta training (pooled)
pos_primary = {}              # ticker -> primary position series (0/1, hold H)
ret_by_tkr = {}               # ticker -> daily pct_change
feat_at_fire = {}             # ticker -> DataFrame of features ON FIRE bars (for sizing)
fire_dates = {}               # ticker -> DatetimeIndex of fire bars

for t in tickers:
    df = store.read("stocks", t)
    if df is None or len(df) < 600:
        continue
    df = df[~df.index.duplicated(keep="last")].sort_index()
    c = df["close"]
    feats = causal_features(df, mkt)
    z = ss.entry_timing_z(df)
    uptrend = c > ss.sma(c, 200)
    fire = (z >= Z_THR) & uptrend.fillna(False)               # PRIMARY fire bars
    fr = fwd_ret(c, H)
    pos = ss.entry_composite_position(df, h=H, z_thr=Z_THR)   # primary hold-H position
    pos_primary[t] = pos
    ret_by_tkr[t] = c.pct_change()

    fb = fire & feats.notna().all(axis=1) & fr.notna()
    if fb.sum() < 5:
        continue
    fire_dates[t] = c.index[fb]
    feat_at_fire[t] = feats.loc[fb, FEATS]
    sub = pd.DataFrame({**{k: feats.loc[fb, k] for k in FEATS},
                        "fwd": fr.loc[fb]})
    sub["label"] = (sub["fwd"] > 0).astype(int)
    sub["ticker"] = t
    sub["date"] = c.index[fb]
    rows.append(sub)

panel = pd.concat(rows, axis=0).sort_values("date").reset_index(drop=True)
print(f"[panel] tickers used={panel['ticker'].nunique()}  fire-events={len(panel)}")
print(f"[panel] date span: {panel['date'].min().date()} -> {panel['date'].max().date()}")
print(f"[panel] base rate P(fwd5>0)={panel['label'].mean():.4f}")

# ------------------------------------------------------------------ purged-CV meta model
# Fold by TIME on the pooled event dates so a forward label near a fold edge can't
# leak into the next fold (embargo). predict each fold from a model trained on the rest.
panel = panel.sort_values("date").reset_index(drop=True)
uniq_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
folds = val.purged_folds(uniq_dates, k=K_FOLDS, embargo=EMBARGO)
date_to_fold = {}
for fname, fidx in folds.items():
    for d in fidx:
        date_to_fold[pd.Timestamp(d)] = fname
panel["fold"] = panel["date"].map(date_to_fold)
panel = panel.dropna(subset=["fold"]).reset_index(drop=True)

oof_p = np.full(len(panel), np.nan)
X_all = panel[FEATS].values.astype(float)
y_all = panel["label"].values.astype(float)

for fname in folds:
    test_m = (panel["fold"] == fname).values
    train_m = ~test_m
    if train_m.sum() < 50 or test_m.sum() < 10:
        continue
    Xtr, ytr = X_all[train_m], y_all[train_m]
    mu = Xtr.mean(0); sd = Xtr.std(0); sd[sd == 0] = 1.0
    w = fit_logistic((Xtr - mu) / sd, ytr)
    oof_p[test_m] = predict_logistic(w, (X_all[test_m] - mu) / sd)

panel["meta_p"] = oof_p
ok = panel["meta_p"].notna()
print(f"[meta] OOF predictions: {ok.sum()}/{len(panel)}")

oof_auc = auc(y_all[ok.values], oof_p[ok.values])
brel = val.brier_reliability(oof_p[ok.values], y_all[ok.values])
print(f"[meta] OUT-OF-FOLD AUC = {oof_auc:.4f}")
print(f"[meta] OUT-OF-FOLD Brier = {brel.get('brier')}  base_brier={brel.get('base_brier')}  skill={brel.get('skill_score')}")

# ------------------------------------------------------------------ sizing thresholds
# meta-size 0 / half / full by OOF probability tertiles of the META prob distribution.
pv = panel.loc[ok, "meta_p"].values
q33, q66 = np.quantile(pv, [1/3, 2/3])
def size_from_p(p):
    if not np.isfinite(p): return 0.0
    if p >= q66: return 1.0
    if p >= q33: return 0.5
    return 0.0
print(f"[size] meta-p tertiles: q33={q33:.3f} q66={q66:.3f}")

# map (ticker,date)->meta size
size_map = {}
for _, r in panel.loc[ok].iterrows():
    size_map[(r["ticker"], pd.Timestamp(r["date"]))] = size_from_p(r["meta_p"])

# ------------------------------------------------------------------ portfolio backtest
# Build per-ticker daily position series for PRIMARY-ALONE and META-SIZED.
# A fire on date d => hold a position for H bars. META scales the held magnitude by the
# meta size decided at the FIRE bar (causal: size known at fire). We only score the
# OOF window (dates that received a meta prediction) for an apples-to-apples comparison.
all_idx = pd.DatetimeIndex(sorted(set().union(*[s.index for s in ret_by_tkr.values()])))
oof_dates = pd.DatetimeIndex(sorted(panel.loc[ok, "date"].unique()))
start, end = oof_dates.min(), oof_dates.max()
idx = all_idx[(all_idx >= start) & (all_idx <= end)]

def build_positions(meta: bool):
    P = {}
    for t in fire_dates:
        c = store.read("stocks", t)["close"]
        c = c[~c.index.duplicated(keep="last")].sort_index()
        pos = pd.Series(0.0, index=c.index)
        for d in fire_dates[t]:
            mult = 1.0
            if meta:
                mult = size_map.get((t, pd.Timestamp(d)), 0.0)
            if mult == 0.0 and meta:
                continue
            loc = c.index.get_loc(d)
            sl = c.index[loc: loc + H]
            pos.loc[sl] = np.maximum(pos.loc[sl].values, mult) if not meta else mult
        P[t] = pos.reindex(idx).fillna(0.0)
    return P

prim_pos = build_positions(meta=False)
meta_pos = build_positions(meta=True)

# equal-weight portfolio: average position across names (so 1.0 = fully in one name's
# fire); portfolio daily return = sum_t pos_t * ret_t / N_active-ish. Use mean alloc.
def portfolio_net(positions: dict):
    n = len(positions)
    alloc = pd.DataFrame({t: positions[t] for t in positions}).reindex(idx).fillna(0.0)
    rets = pd.DataFrame({t: ret_by_tkr[t].reindex(idx).fillna(0.0) for t in positions})
    # per-name next-bar backtest net of cost, then equal-weight average the net series
    nets = []
    for t in positions:
        c = store.read("stocks", t)["close"].reindex(idx).ffill()
        bt = val.backtest_core(c, positions[t], cost_bps=COST_BPS)
        nets.append(bt["net"])
    port = pd.concat(nets, axis=1).mean(axis=1)        # equal-weight sleeve
    return port

prim_net = portfolio_net(prim_pos)
meta_net = portfolio_net(meta_pos)

def stats(r):
    r = r.dropna()
    mu, sd = r.mean(), r.std()
    sr_d = mu / sd if sd > 0 else float("nan")
    sr_a = sr_d * math.sqrt(252)
    cagr = (1 + r).prod() ** (252 / len(r)) - 1 if len(r) else float("nan")
    cum = (1 + r).cumprod(); dd = (cum / cum.cummax() - 1).min()
    return sr_d, sr_a, cagr, dd, len(r)

ps = stats(prim_net); ms = stats(meta_net)
print("\n=== NET-OF-COST portfolio (OOF window) ===")
print(f"PRIMARY-alone : Sharpe_ann={ps[1]:.3f}  CAGR={ps[2]*100:.2f}%  maxDD={ps[3]*100:.1f}%  n={ps[4]}")
print(f"META-sized    : Sharpe_ann={ms[1]:.3f}  CAGR={ms[2]*100:.2f}%  maxDD={ms[3]*100:.1f}%  n={ms[4]}")
print(f"Sharpe uplift (meta - primary) = {ms[1]-ps[1]:+.3f}")

# DSR on the meta-sized sleeve (selected as best of N_TRIALS configs)
sk, ku = val.ret_moments(meta_net.dropna())[:2] if hasattr(val, "ret_moments") else (0,3)
m = meta_net.dropna()
sk = float(m.skew()); ku = float(m.kurt()) + 3.0
_led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                   family="meta_labeling_entry")
_led.log_grid([{"trial": i} for i in range(N_TRIALS)], family="meta_labeling_entry")
dsr = val.deflated_sharpe(ms[0], sk, ku, len(m), ledger=_led, family="meta_labeling_entry")
print(f"\n[DSR] meta-sized sleeve: dsr={dsr['dsr']}  sr_annual={dsr['sr_annual']}  n_trials={N_TRIALS}  -> {val.dsr_verdict(dsr['dsr'])}")

# Newey-West t on the DIFFERENCE series (meta - primary), HAC for overlap
diff = (meta_net - prim_net).dropna()
nw = val.newey_west_tstat(diff.values, lags=H)
print(f"[HAC] mean(meta-primary) daily={diff.mean():.2e}  NW t-stat={nw.get('t'):.3f}  (lags={H})")

print("\n--- VERDICT INPUTS ---")
print(f"oof_auc={oof_auc:.4f}  brier_skill={brel.get('skill_score')}  sharpe_uplift={ms[1]-ps[1]:+.3f}  nw_t={nw.get('t'):.3f}  dsr={dsr['dsr']}")
