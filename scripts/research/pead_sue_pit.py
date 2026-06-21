"""
Post-Earnings-Announcement Drift (PEAD), point-in-time.

Design (event-time, strictly causal):
  - SUE per name/quarter via the SEASONAL RANDOM WALK proxy (no analyst estimates
    available in the PIT panel): surprise = eps_q - eps_{q-4} (same fiscal quarter,
    prior year), standardized by the EXPANDING std of that YoY change using only
    quarters whose filing (asof_date) is < the current event's filing date.
    => SUE(t) uses only data filed on/before the event date.
  - Event date = asof_date (the EDGAR filing date). We enter at the NEXT trading
    day's close (drift window starts strictly AFTER the filing).
  - Drift = cumulative ABNORMAL return vs _GSPC (stock cum return - GSPC cum return)
    over the FUTURE window [enter, enter+H], H in {1,5,21,63} trading days.
  - Cross-sectional rank-IC: per calendar quarter cohort, rank-correlate SUE against
    the forward CAR. ic_summary => mean IC, HAC (Newey-West) t, IC-IR.
  - DSR on a long/short SUE-quintile portfolio (top-minus-bottom by SUE, held H days,
    rebalanced at each event cohort), NET of 5bps one-way cost.

HONESTY:
  - data/stocks = 114 current survivors (95 with EPS coverage) -> SURVIVORSHIP biased.
    Delisted names absent => OPTIMISTIC CONTEXT bound, not proven alpha.
  - Every signal value at t uses only data with asof_date <= t. Entry shifted +1 day.
  - Forward windows are strictly future. NET-of-cost reported. HAC t + DSR with an
    HONEST n_trials (we test 4 horizons x {IC, LS-portfolio} -> declare n_trials=8).
"""
import os, sys, glob, math, json, tempfile
import numpy as np
import pandas as pd

ROOT = "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/agitated-nightingale-3cf266"
os.chdir(ROOT); sys.path.insert(0, ROOT)
import lib.store as store
from engine.validation import (rank_ic, ic_summary, newey_west_tstat,
                               deflated_sharpe, dsr_verdict, block_bootstrap_ci)
from engine.trial_ledger import TrialLedger

COST_BPS = 5.0
HORIZONS = [1, 5, 21, 63]

# ---- load prices (survivor panel) ----
tick_files = sorted(glob.glob("data/stocks/*.parquet"))
TICKS = [os.path.basename(f)[:-8] for f in tick_files]
px = {}
for t in TICKS:
    try:
        s = store.read("stocks", t)["close"].dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        if len(s) > 200:
            px[t] = s
    except Exception:
        pass
mkt = store.read("yahoo", "_GSPC")["close"].dropna()
mkt = mkt[~mkt.index.duplicated(keep="last")].sort_index()

# ---- load PIT EPS ----
eps = pd.read_parquet("data/edgar/eps_quarterly.parquet")
eps = eps.dropna(subset=["eps_q", "asof_date", "period_end"]).copy()
eps["asof_date"] = pd.to_datetime(eps["asof_date"])
eps["period_end"] = pd.to_datetime(eps["period_end"])

# fiscal-quarter label so we align YoY (same period of prior year ~ 4 quarters back)
eps = eps.sort_values(["ticker", "period_end"]).reset_index(drop=True)

def build_events():
    """Return per-event rows: ticker, asof_date, period_end, sue (seasonal random walk,
    expanding-std standardized, causal)."""
    rows = []
    for t, g in eps.groupby("ticker", observed=True):
        if t not in px:
            continue
        g = g.drop_duplicates("period_end").sort_values("period_end").reset_index(drop=True)
        if len(g) < 8:
            continue
        # YoY change = eps_q - eps_q[4 quarters earlier], aligned by position (quarterly cadence)
        e = g["eps_q"].values
        yoy = np.full(len(e), np.nan)
        for i in range(4, len(e)):
            yoy[i] = e[i] - e[i - 4]
        g["yoy"] = yoy
        # expanding std of yoy using ONLY prior events (filed before current asof).
        # shift(1) so std at row i excludes the current surprise.
        prior_std = g["yoy"].shift(1).expanding(min_periods=4).std()
        sue = g["yoy"] / prior_std
        g["sue"] = sue.replace([np.inf, -np.inf], np.nan)
        for _, r in g.iterrows():
            if pd.notna(r["sue"]):
                rows.append((t, r["asof_date"], r["period_end"], float(r["sue"])))
    return pd.DataFrame(rows, columns=["ticker", "asof", "period_end", "sue"])

ev = build_events()
# winsorize SUE to tame seasonal-random-walk fat tails (cross-sectionally robust)
ev["sue"] = ev["sue"].clip(-6, 6)

# ---- compute forward CARs vs GSPC ----
def fwd_car(ticker, asof, H):
    """Enter at the FIRST trading day with index date > asof (strictly after filing);
    measure cum abnormal return (stock - GSPC) from enter to enter+H trading days."""
    s = px[ticker]
    pos = s.index.searchsorted(asof, side="right")  # first bar strictly after filing
    if pos + H >= len(s):
        return np.nan
    s0, s1 = s.iloc[pos], s.iloc[pos + H]
    # market aligned on the same calendar dates
    d0, d1 = s.index[pos], s.index[pos + H]
    mpos0 = mkt.index.searchsorted(d0, side="left")
    mpos1 = mkt.index.searchsorted(d1, side="left")
    if mpos0 >= len(mkt) or mpos1 >= len(mkt):
        return np.nan
    m0, m1 = mkt.iloc[mpos0], mkt.iloc[mpos1]
    if s0 <= 0 or m0 <= 0:
        return np.nan
    return (s1 / s0 - 1.0) - (m1 / m0 - 1.0)

for H in HORIZONS:
    ev[f"car{H}"] = [fwd_car(r.ticker, r.asof, H) for r in ev.itertuples()]

# cohort = calendar quarter of the filing (groups simultaneous earnings season events)
ev["cohort"] = ev["asof"].dt.to_period("Q")

print("=" * 70)
print("PEAD (SUE) point-in-time event study")
print("=" * 70)
print(f"events total: {len(ev)}  |  names: {ev["ticker"].nunique()}  "
      f"|  cohorts(qtrs): {ev["cohort"].nunique()}")
print(f"asof span: {ev["asof"].min().date()} .. {ev["asof"].max().date()}")
print(f"SUE mean/std: {ev["sue"].mean():.3f}/{ev["sue"].std():.3f}")

results = {}

# ---------- (A) cross-sectional rank-IC of SUE vs forward CAR, per cohort ----------
print("\n--- (A) Cross-sectional rank-IC: SUE vs forward CAR (per quarterly cohort) ---")
ic_tables = {}
for H in HORIZONS:
    ics = []
    for q, g in ev.groupby("cohort", observed=True):
        sub = g[["sue", f"car{H}"]].dropna()
        if len(sub) >= 8:  # need cross-sectional breadth
            ic = rank_ic(sub["sue"], sub[f"car{H}"])
            if not math.isnan(ic):
                ics.append(ic)
    summ = ic_summary(ics, periods_per_year=4)
    ic_tables[H] = summ
    print(f"H={H:>3}d  meanIC={summ.get('mean_ic')}  IC-IR={summ.get('ic_ir')}  "
          f"t_hac={summ.get('t_hac')}  p={summ.get('p_hac')}  hit={summ.get('hit')}  n={summ.get('n')}")
results["ic"] = ic_tables

# ---------- (B) Long/short SUE-quintile drift portfolio, NET of cost, per horizon ----------
# For each cohort, rank events into quintiles by SUE; LS = mean(top CAR) - mean(bottom CAR).
# This is the realizable PEAD trade return per cohort (overlapping if H spans cohorts but
# cohorts are quarterly ~63 trading days apart, so H<=63 is ~non-overlapping at cohort step).
print("\n--- (B) Long/short top-minus-bottom SUE quintile drift (NET 5bps/side) ---")
ls_tables = {}
for H in HORIZONS:
    rets = []
    dates = []
    for q, g in ev.groupby("cohort", observed=True):
        sub = g[["sue", f"car{H}"]].dropna()
        if len(sub) < 15:
            continue
        sub = sub.sort_values("sue")
        k = max(1, len(sub) // 5)
        bot = sub.iloc[:k][f"car{H}"].mean()
        top = sub.iloc[-k:][f"car{H}"].mean()
        gross = top - bot
        # cost: enter long+short legs then exit => 4 one-way crossings = 4*COST_BPS
        net = gross - 4 * COST_BPS / 1e4
        rets.append(net)
        dates.append(q)
    rets = pd.Series(rets, index=pd.PeriodIndex(dates, freq="Q")).dropna()
    if len(rets) >= 8:
        mu = rets.mean(); sd = rets.std(ddof=1)
        # per-trade Sharpe; annualize via number of independent trades/yr.
        # at H days, ~ 252/H non-overlapping trades per year possible; but cohorts are
        # quarterly so we hold 4 cohorts/yr. Use per-cohort Sharpe scaled by sqrt(periods/yr).
        periods_per_year = 252.0 / H  # how many times this drift trade could be run/yr
        sr_per = mu / sd if sd else float("nan")
        nw = newey_west_tstat(rets, lags=2)
        # DSR: treat per-cohort return as the unit; T = n cohorts; n_trials = 8 (4H x 2 stats)
        _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                           family="pead_sue_drift")
        _led.log_grid([{"trial": i} for i in range(8)], family="pead_sue_drift")
        dsr = deflated_sharpe(sr_per, float(pd.Series(rets).skew()),
                              float(pd.Series(rets).kurt()) + 3.0,
                              T=len(rets), ledger=_led, family="pead_sue_drift", trading_year=4.0)
        boot = block_bootstrap_ci(rets, block=2, B=5000, seed=7, ann=4)
        ls_tables[H] = {
            "n_cohorts": len(rets),
            "mean_net_per_cohort": round(float(mu), 5),
            "sd": round(float(sd), 5),
            "sharpe_per_cohort": round(float(sr_per), 3),
            "t_hac": nw["t"], "p_hac": nw["p"],
            "hit": round(float((rets > 0).mean()), 3),
            "dsr": (dsr or {}).get("dsr"),
            "dsr_verdict": dsr_verdict((dsr or {}).get("dsr", 0.0)) if dsr else None,
            "boot_ci": boot,
        }
        d = ls_tables[H]
        print(f"H={H:>3}d  net/cohort={d['mean_net_per_cohort']:+.4f}  "
              f"SR/cohort={d['sharpe_per_cohort']}  t_hac={d['t_hac']}  "
              f"hit={d['hit']}  DSR={d['dsr']} ({d['dsr_verdict']})  n={d['n_cohorts']}")
    else:
        ls_tables[H] = {"n_cohorts": len(rets), "note": "too few cohorts"}
        print(f"H={H:>3}d  too few cohorts ({len(rets)})")
results["ls"] = ls_tables

# ---------- (C) mean CAR by SUE quintile (drift monotonicity sanity) at H=63 ----------
print("\n--- (C) Mean forward CAR by SUE quintile (pooled, H=63) ---")
sub = ev[["sue", "car63"]].dropna().copy()
sub["qtile"] = pd.qcut(sub["sue"], 5, labels=["Q1(low)", "Q2", "Q3", "Q4", "Q5(high)"], duplicates="drop")
g = sub.groupby("qtile", observed=True)["car63"].agg(["mean", "count"])
for idx, row in g.iterrows():
    print(f"  {idx:>9}: meanCAR63={row['mean']:+.4f}  n={int(row['count'])}")
results["quintile_car63"] = {str(k): {"mean": round(float(v["mean"]), 5), "n": int(v["count"])}
                             for k, v in g.iterrows()}

# ---------- summary verdict inputs ----------
best_ic_h = max(HORIZONS, key=lambda h: (ic_tables[h].get("mean_ic") or -9))
print("\n" + "=" * 70)
print(f"BEST IC horizon: H={best_ic_h}  meanIC={ic_tables[best_ic_h].get('mean_ic')}  "
      f"t_hac={ic_tables[best_ic_h].get('t_hac')}  p={ic_tables[best_ic_h].get('p_hac')}")
print("survivorship: 95/114 current survivors w/ EPS coverage -> OPTIMISTIC bound")
print("=" * 70)
print(json.dumps({"ic": {str(k): v for k, v in ic_tables.items()},
                  "ls": {str(k): v for k, v in ls_tables.items()}}, default=str, indent=0))
