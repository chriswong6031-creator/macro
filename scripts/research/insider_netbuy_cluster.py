"""Insider net-buying cluster forward signal — honest validation.

Idea: insider net open-market buying (Form-4 P-S), built CAUSALLY as-of each
rebalance using ONLY transactions whose filing_date <= t, measured as net $ as a
fraction of dollar-volume (and a cluster count of >=2 distinct buyers), should
forward-predict the cross-section of the 113 survivor mega-caps.

Data:
  data/sec_insider/panel/*.parquet  — PIT per-transaction Form-4 panel
      (filing_date, trans_date, code P/S, rptownercik, usd, ...), 2006q1..2026q1,
      2.3M rows, 16,834 tickers.  This is the REAL point-in-time asset.
  lib/store.read("stocks", T) — Date-indexed adjusted close/high/low/volume,
      114 current survivors.

DEAD-PATH BUG (documented, NOT fixed — instructed not to edit engine files):
  engine/equity_factors.py reads `data/sec_insider/insider_panel.parquet`
  (a single flat file) in _insider_block (L83), _insider_block_panel and
  insider_signals (L190). That file DOES NOT EXIST — the panel lives as a
  PER-QUARTER directory data/sec_insider/panel/<YYYYqN>.parquet. Consequences:
    * insider_signals() (the per-ticker CONFIRMER chip) always returns {} →
      the confirmer leg is silently dead.
    * _insider_block() always falls through to _insider_block_aggregate(), i.e.
      the single-quarter (2026q1 only) data/sec_insider/insider.parquet, with
      cluster=False and NO trailing window / NO distinct-buyer cluster count.
  Canonicalization fix: point those three reads at the panel directory (read &
  concat panel/*.parquet, or build the flat insider_panel.parquet the reader
  expects). Until then the validated panel construction never reaches the page.

HONESTY: every signal value at t uses only filing_date<=t (causal). Forward
windows strictly future. Long-short return net of 5bps/side. DSR with declared
n_trials. HAC t on the IC series. SURVIVORSHIP: data/stocks = 114 CURRENT
survivors → cross-sectional IC is an OPTIMISTIC CONTEXT bound, not proven alpha.
"""
import glob
import math
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/agitated-nightingale-3cf266"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import lib.store as store  # noqa: E402
import engine.validation as V  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

COST_BPS = 5.0
PANEL_DIR = os.path.join(ROOT, "data", "sec_insider", "panel")

# ---------------------------------------------------------------- prices
stock_tickers = sorted(f[:-8] for f in os.listdir("data/stocks") if f.endswith(".parquet"))
closes = {}
dvol = {}  # dollar volume (close*volume) for the size-normaliser
for t in stock_tickers:
    try:
        df = store.read("stocks", t)
    except Exception:
        continue
    if df is None or df.empty or "close" not in df:
        continue
    c = df["close"].dropna()
    closes[t] = c
    if "volume" in df:
        dvol[t] = (df["close"] * df["volume"]).dropna()
close_mat = pd.DataFrame(closes).sort_index()
print(f"[universe] {len(close_mat.columns)} survivor names with prices "
      f"({close_mat.index.min().date()}..{close_mat.index.max().date()})")

# ---------------------------------------------------------------- insider panel (PIT)
frames = []
for f in sorted(glob.glob(os.path.join(PANEL_DIR, "*.parquet"))):
    frames.append(pd.read_parquet(
        f, columns=["ticker", "filing_date", "code", "usd", "rptownercik"]))
ins = pd.concat(frames, ignore_index=True)
ins = ins[ins["ticker"].isin(set(close_mat.columns))].copy()
ins["filing_date"] = pd.to_datetime(ins["filing_date"])
ins = ins[ins["code"].isin(["P", "S"])]
ins["sgn_usd"] = np.where(ins["code"] == "P", ins["usd"], -ins["usd"])
cov = sorted(ins["ticker"].unique())
print(f"[insider] {len(ins):,} P/S rows across {len(cov)} of {len(close_mat.columns)} "
      f"survivor names; filing_date {ins['filing_date'].min().date()}..{ins['filing_date'].max().date()}")

# ---------------------------------------------------------------- rebalance grid
# Monthly rebalances on the last trading day of each month from 2007-01 (so a full
# trailing window exists) to 2026-03 (panel ends 2026q1). Causal: at date t we use
# only filings with filing_date <= t.
all_dates = close_mat.index
month_ends = (pd.Series(all_dates, index=all_dates)
              .groupby([all_dates.year, all_dates.month]).last())
rebal = [d for d in month_ends.values]
rebal = pd.DatetimeIndex(pd.to_datetime(rebal))
rebal = rebal[(rebal >= "2007-01-01") & (rebal <= "2026-03-31")]
print(f"[grid] {len(rebal)} monthly rebalances {rebal.min().date()}..{rebal.max().date()}")

WINDOW_DAYS = 126  # ~6-month trailing window of filings (matches engine intent)
CLUSTER_MIN = 2
N_TRIALS = 4  # 2 horizons x {raw, cluster-gated} variants honestly considered

# Pre-sort insider rows by filing_date for windowed slicing
ins = ins.sort_values("filing_date")
fdates = ins["filing_date"].values


def signal_asof(t: pd.Timestamp) -> pd.Series:
    """Net-buy INTENSITY cross-section knowable at t: trailing-WINDOW net $ as a
    fraction of trailing dollar-volume, *requiring* a >=2 distinct-buyer cluster on
    the buy side to qualify a name as 'insider conviction' (else intensity uses the
    raw net which can be negative for sells). Pure function of filing_date<=t."""
    lo = t - pd.Timedelta(days=WINDOW_DAYS)
    hi_i = np.searchsorted(fdates, np.datetime64(t), side="right")
    lo_i = np.searchsorted(fdates, np.datetime64(lo), side="left")
    w = ins.iloc[lo_i:hi_i]
    if w.empty:
        return pd.Series(dtype=float)
    g = w.groupby("ticker")
    net = g["sgn_usd"].sum()
    n_buyers = w[w["code"] == "P"].groupby("ticker")["rptownercik"].nunique()
    n_buyers = n_buyers.reindex(net.index).fillna(0)
    # size-normalise by trailing ~3-month dollar volume knowable at t
    out = {}
    for tk in net.index:
        dv = dvol.get(tk)
        if dv is None:
            continue
        dvw = dv[(dv.index > lo) & (dv.index <= t)]
        if dvw.empty:
            continue
        denom = dvw.sum()
        if denom <= 0:
            continue
        intensity = net[tk] / denom  # net buy $ as fraction of traded $
        # cluster gate: a positive read only "counts" with >=2 distinct buyers
        if intensity > 0 and n_buyers[tk] < CLUSTER_MIN:
            intensity = 0.0
        out[tk] = intensity
    return pd.Series(out)


def fwd_return(t: pd.Timestamp, h: int) -> pd.Series:
    """Strictly-future h-trading-day return per name from the close on/after t."""
    pos = all_dates.searchsorted(t)
    if pos + h >= len(all_dates):
        return pd.Series(dtype=float)
    t0, t1 = all_dates[pos], all_dates[pos + h]
    r = {}
    for tk in close_mat.columns:
        c = close_mat[tk]
        if t0 in c.index and t1 in c.index and pd.notna(c[t0]) and pd.notna(c[t1]) and c[t0] > 0:
            r[tk] = c[t1] / c[t0] - 1.0
    return pd.Series(r)


# ---------------------------------------------------------------- IC by horizon
results = {}
for h, ppy in [(21, 12), (63, 4)]:
    ics, ls_rets, dates = [], [], []
    active_counts = []
    for t in rebal:
        s = signal_asof(t)
        if s.empty:
            continue
        f = fwd_return(t, h)
        ic = V.rank_ic(s, f)
        if not np.isnan(ic):
            ics.append(ic)
            dates.append(t)
        # long-short decile-ish: top vs bottom tercile on the signal (net of cost)
        j = pd.concat([s.rename("s"), f.rename("f")], axis=1).dropna()
        active_counts.append(int((j["s"] != 0).sum()))
        if len(j) >= 12:
            q = j["s"].rank(pct=True)
            longs = j[q >= 2 / 3]["f"]
            shorts = j[q <= 1 / 3]["f"]
            if len(longs) and len(shorts):
                gross = longs.mean() - shorts.mean()
                # turnover-agnostic conservative cost: 2 sides per leg per rebal
                net = gross - 2 * COST_BPS / 1e4 * 2
                ls_rets.append(net)
    summ = V.ic_summary(ics, periods_per_year=ppy)
    # DSR on the long-short series (monthly bars), declared n_trials
    lr = pd.Series(ls_rets)
    dsr = None
    if len(lr) >= 12 and lr.std(ddof=1) > 0:
        sr_monthly = lr.mean() / lr.std(ddof=1)
        sr_daily = sr_monthly / math.sqrt(21)  # express per-day for the helper
        _led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                           family="insider_netbuy")
        _led.log_grid([{"trial": i} for i in range(N_TRIALS)], family="insider_netbuy")
        dsr = V.deflated_sharpe(sr_daily, float(lr.skew()), float(lr.kurt() + 3.0),
                                T=len(lr) * 21, ledger=_led, family="insider_netbuy")
    ann_ls = (1 + lr.mean()) ** ppy - 1 if len(lr) else float("nan")
    sharpe_ls = (lr.mean() / lr.std(ddof=1) * math.sqrt(ppy)) if len(lr) > 1 and lr.std(ddof=1) else float("nan")
    results[h] = dict(summ=summ, n_ic=len(ics), ls_n=len(lr),
                      ann_ls=ann_ls, sharpe_ls=sharpe_ls, dsr=dsr,
                      mean_active=float(np.mean(active_counts)) if active_counts else 0)


# ---------------------------------------------------------------- report
print("\n================ RESULTS (net of 5bps/side) ================")
print(f"SURVIVORSHIP: 113/114 survivor mega-caps (BRK-B dotted-ticker absent) — "
      f"OPTIMISTIC CONTEXT bound, not proven alpha.")
print(f"DSR n_trials declared = {N_TRIALS}")
for h in (21, 63):
    r = results[h]
    s = r["summ"]
    print(f"\n--- forward {h}d ---")
    print(f"  IC obs        : {r['n_ic']}")
    print(f"  mean rank-IC  : {s.get('mean_ic')}")
    print(f"  IC-IR (ann)   : {s.get('ic_ir_ann')}")
    print(f"  HAC t / p     : {s.get('t_hac')} / {s.get('p_hac')}")
    print(f"  IC hit rate   : {s.get('hit')}")
    print(f"  mean #active names/rebal (nonzero signal): {r['mean_active']:.1f}")
    print(f"  L/S tercile bars: {r['ls_n']}  ann={r['ann_ls']:.3%}  Sharpe={r['sharpe_ls']:.2f}")
    if r["dsr"]:
        d = r["dsr"]
        print(f"  DSR           : {d.get('dsr')}  verdict={V.dsr_verdict(d.get('dsr'))}")
    else:
        print(f"  DSR           : n/a (too few bars)")
print("\n[done]")
