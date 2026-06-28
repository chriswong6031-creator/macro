"""
NOVEL: Turn-of-month (TOM) + monthly-seasonality calendar study.

Tests calendar return seasonality on:
  - _GSPC (S&P 500 index, deep history 1928+) -- the headline, NOT survivorship-biased
  - data/stocks (114 current mega-cap survivors) -- cross-sectional CONTEXT bound only

(a) Turn-of-month window: last trading day of month (t-1) ... first 3 trading days
    of next month, vs the rest of the month.
(b) Month-of-year: Sell-in-May (Nov-Apr vs May-Oct), Santa rally (last 5 + first 2
    trading days), per-calendar-month means.

HONESTY:
  - Every signal is CAUSAL: the TOM flag for a position on day t is known at the
    close of t-1 (calendar position is deterministic, fully known in advance).
  - Positions act via backtest_core, which SHIFTS alloc by 1 day -> no look-ahead.
  - Forward windows for the per-day mean tests use the realized return ON that day;
    we report HAC (Newey-West) t-stats because daily index returns are mildly serially
    correlated and the TOM sleeve has overlapping-regime structure.
  - NET-OF-COST: TOM timing sleeve charged 5bps one-way via backtest_core cost_bps=5.
  - DSR with an HONEST n_trials covering every calendar cut we examined.
  - Survivorship: data/stocks = 114 survivors. _GSPC is the clean test; stocks are CONTEXT.
"""
import sys, warnings, tempfile
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from lib import store
from engine import validation as v
from engine.trial_ledger import TrialLedger

COST_BPS = 5.0
SEED = 7
rng = np.random.default_rng(SEED)

def hac(x, lags=10):
    x = pd.Series(x).dropna()
    if len(x) < 30:
        return {"mean": np.nan, "t": np.nan, "n": len(x)}
    r = v.newey_west_tstat(x.values, lags=lags)
    return {"mean": float(x.mean()), "t": float(r.get("t", np.nan)), "n": len(x)}

def tom_flag(index, pre=1, post=3):
    """Boolean Series: True on the last `pre` trading days of a month and the
    first `post` trading days of the next month. Purely calendar-deterministic."""
    idx = pd.DatetimeIndex(index)
    ym = idx.to_period("M")
    s = pd.Series(np.arange(len(idx)), index=idx)
    flag = pd.Series(False, index=idx)
    # rank within month (ascending = first trading days; descending = last)
    df = pd.DataFrame({"ym": ym, "pos": np.arange(len(idx))}, index=idx)
    df["rank_first"] = df.groupby("ym").cumcount()            # 0 = first trading day
    df["rank_last"] = df.groupby("ym").cumcount(ascending=False)  # 0 = last trading day
    first_days = df["rank_first"] < post
    last_days = df["rank_last"] < pre
    return (first_days | last_days)

def santa_flag(index):
    """Last 5 trading days of Dec + first 2 of Jan."""
    idx = pd.DatetimeIndex(index)
    df = pd.DataFrame({"m": idx.month, "ym": idx.to_period("M")}, index=idx)
    df["rank_last"] = df.groupby("ym").cumcount(ascending=False)
    df["rank_first"] = df.groupby("ym").cumcount()
    dec_end = (df["m"] == 12) & (df["rank_last"] < 5)
    jan_start = (df["m"] == 1) & (df["rank_first"] < 2)
    return dec_end | jan_start

def analyze_series(name, close):
    out = {}
    ret = close.pct_change()
    idx = close.index
    # --- (a) TOM ---
    flag = tom_flag(idx, pre=1, post=3)
    r_tom = ret[flag]
    r_rest = ret[~flag]
    out["tom_in"] = hac(r_tom)
    out["tom_rest"] = hac(r_rest)
    # frac of days that are TOM
    out["tom_frac"] = float(flag.mean())
    # --- (b) Sell in May ---
    nov_apr = idx.month.isin([11, 12, 1, 2, 3, 4])
    out["nov_apr"] = hac(ret[nov_apr])
    out["may_oct"] = hac(ret[~nov_apr])
    # --- Santa ---
    sflag = santa_flag(idx)
    out["santa"] = hac(ret[sflag])
    # --- per-month means (daily) ---
    out["by_month"] = {int(m): hac(ret[idx.month == m]) for m in range(1, 13)}
    return out, ret, flag

def tom_sleeve(close, flag):
    """Long index only on TOM days, flat (0%) otherwise. Net of 5bps one-way.
    alloc is CAUSAL: flag is calendar-deterministic and backtest_core shifts by 1."""
    alloc = flag.astype(float).reindex(close.index).fillna(0.0)
    bt = v.backtest_core(close, alloc, cost_bps=COST_BPS)
    net = bt["net"].dropna()
    hold = bt["hold"].dropna()
    def sharpe(x):
        x = pd.Series(x).dropna()
        return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else np.nan
    def cagr(x):
        x = pd.Series(x).dropna()
        return float((1 + x).prod() ** (252 / len(x)) - 1)
    return {
        "sleeve_sharpe": sharpe(net),
        "hold_sharpe": sharpe(hold),
        "sleeve_cagr": cagr(net),
        "hold_cagr": cagr(hold),
        "sleeve_mean_d": float(net.mean()),
        "exposure": float(alloc.mean()),
        "net": net, "hold": hold,
    }

print("=" * 78)
print("CALENDAR SEASONALITY: Turn-of-month + Month-of-year")
print("=" * 78)

# ============ _GSPC (clean, deep history) ============
g = store.read("yahoo", "_GSPC")["close"].dropna()
print(f"\n_GSPC coverage: {g.index.min().date()} -> {g.index.max().date()}  ({len(g)} days)")
res, gret, gflag = analyze_series("_GSPC", g)

print("\n-- (a) TURN-OF-MONTH (last1 + first3), daily mean return (bps), HAC t --")
print(f"  TOM days  : mean={res['tom_in']['mean']*1e4:7.2f}bps  t={res['tom_in']['t']:6.2f}  n={res['tom_in']['n']} ({res['tom_frac']*100:.1f}% of days)")
print(f"  Rest days : mean={res['tom_rest']['mean']*1e4:7.2f}bps  t={res['tom_rest']['t']:6.2f}  n={res['tom_rest']['n']}")
diff = res['tom_in']['mean'] - res['tom_rest']['mean']
print(f"  TOM minus rest spread: {diff*1e4:.2f} bps/day")

print("\n-- (b) MONTH-OF-YEAR --")
print(f"  Nov-Apr  : mean={res['nov_apr']['mean']*1e4:7.2f}bps  t={res['nov_apr']['t']:6.2f}  n={res['nov_apr']['n']}")
print(f"  May-Oct  : mean={res['may_oct']['mean']*1e4:7.2f}bps  t={res['may_oct']['t']:6.2f}  n={res['may_oct']['n']}")
print(f"  Santa    : mean={res['santa']['mean']*1e4:7.2f}bps  t={res['santa']['t']:6.2f}  n={res['santa']['n']}")
print("  per calendar-month daily mean (bps) / HAC t:")
for m in range(1, 13):
    bm = res["by_month"][m]
    print(f"    M{m:2d}: {bm['mean']*1e4:7.2f}bps  t={bm['t']:6.2f}  n={bm['n']}")

# ============ TOM timing sleeve, NET of cost ============
print("\n-- TOM-only timing sleeve (long index ON tom days, flat else), NET 5bps --")
sl = tom_sleeve(g, gflag)
print(f"  Sleeve Sharpe : {sl['sleeve_sharpe']:.3f}   (exposure {sl['exposure']*100:.1f}% of days)")
print(f"  Buy&Hold Sharpe: {sl['hold_sharpe']:.3f}")
print(f"  Sleeve CAGR   : {sl['sleeve_cagr']*100:.2f}%   Buy&Hold CAGR: {sl['hold_cagr']*100:.2f}%")
print(f"  Sleeve net mean/day: {sl['sleeve_mean_d']*1e4:.2f}bps")

# DSR on the sleeve net returns. Honest n_trials: count every distinct calendar
# cut we examined as a 'trial' in the seasonality family.
N_TRIALS = (
    1   # TOM in-vs-rest
    + 1 # sell-in-may
    + 1 # santa
    + 12 # per-month
    + 4 # alternative TOM windows we conceptually scanned (pre/post variants below)
)
netd = sl["net"].dropna()
sr_d = netd.mean() / netd.std() if netd.std() > 0 else 0.0
_led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                   family="calendar_seasonality")
_led.log_grid([{"trial": i} for i in range(N_TRIALS)], family="calendar_seasonality")
dsr = v.deflated_sharpe(sr_daily=float(sr_d), skew=float(netd.skew()),
                        kurt=float(netd.kurtosis() + 3.0), T=len(netd),
                        ledger=_led, family="calendar_seasonality")
print(f"\n-- DSR on TOM sleeve net returns (n_trials={N_TRIALS}) --")
print(f"  daily SR={sr_d:.4f}  DSR={dsr['dsr']:.4f} -> {v.dsr_verdict(dsr['dsr'])}" if dsr else "  DSR: n/a")

# Also: is TOM mean-spread itself significant after FDR across the per-month family?
# Build pvals from HAC t (two-sided, normal approx) for the calendar family.
from scipy import stats as sstats
fam = {"tom_spread": res['tom_in']['t'], "sell_in_may": (res['nov_apr']['t']),
       "santa": res['santa']['t']}
for m in range(1, 13):
    fam[f"month_{m}"] = res["by_month"][m]['t']
pvals = {k: float(2 * (1 - sstats.norm.cdf(abs(t)))) for k, t in fam.items() if np.isfinite(t)}
bh = v.benjamini_hochberg(pvals, alpha=0.10)
n_sig = sum(1 for k in bh if (bh[k] if isinstance(bh[k], (bool, np.bool_)) else bh[k].get("reject", False)))
print(f"\n-- BH-FDR (alpha=0.10) across {len(pvals)} calendar cuts --")
# bh return shape: inspect
print("  bh sample:", {k: bh[k] for k in list(bh)[:2]})

# Alternative TOM windows (robustness) on _GSPC
print("\n-- TOM window robustness (_GSPC), spread bps & HAC t --")
for pre, post in [(1, 3), (1, 2), (1, 4), (2, 3), (0, 4)]:
    f = tom_flag(g.index, pre=pre, post=post)
    ri, ro = gret[f], gret[~f]
    hi, ho = hac(ri), hac(ro)
    print(f"  pre={pre} post={post}: in={hi['mean']*1e4:6.2f}bps(t={hi['t']:5.2f}) "
          f"rest={ho['mean']*1e4:6.2f}bps  spread={(hi['mean']-ho['mean'])*1e4:5.2f}bps")

# ============ Cross-sectional CONTEXT on 114 survivors ============
import os
tickers = sorted(p[:-8] for p in os.listdir("data/stocks") if p.endswith(".parquet"))
print(f"\n{'='*78}\nSURVIVOR PANEL (n={len(tickers)} CURRENT mega-caps -> CONTEXT bound, not alpha)\n{'='*78}")
tom_spreads = []
sleeve_sh = []
hold_sh = []
for t in tickers:
    try:
        c = store.read("stocks", t)["close"].dropna()
    except Exception:
        continue
    if len(c) < 1000:
        continue
    r = c.pct_change()
    f = tom_flag(c.index, 1, 3)
    spread = r[f].mean() - r[~f].mean()
    tom_spreads.append(spread)
    sl_t = tom_sleeve(c, f)
    if np.isfinite(sl_t["sleeve_sharpe"]):
        sleeve_sh.append(sl_t["sleeve_sharpe"])
        hold_sh.append(sl_t["hold_sharpe"])
tom_spreads = np.array(tom_spreads)
print(f"  TOM spread across {len(tom_spreads)} names: "
      f"mean={tom_spreads.mean()*1e4:.2f}bps  median={np.median(tom_spreads)*1e4:.2f}bps  "
      f"%positive={(tom_spreads>0).mean()*100:.1f}%")
hac_panel = hac(tom_spreads, lags=0)
# cross-sectional t (simple, names ~independent-ish)
t_xs = tom_spreads.mean() / (tom_spreads.std(ddof=1) / np.sqrt(len(tom_spreads)))
print(f"  cross-sectional t of mean TOM spread: {t_xs:.2f}")
print(f"  TOM sleeve Sharpe (survivor avg): {np.mean(sleeve_sh):.3f}  vs buy&hold avg: {np.mean(hold_sh):.3f}")
print(f"  sleeve beats hold on {(np.array(sleeve_sh)>np.array(hold_sh)).mean()*100:.0f}% of names")

print("\nDONE.")
