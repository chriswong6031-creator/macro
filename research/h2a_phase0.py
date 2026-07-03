"""H2a — SFC reportable short positions phase-0.

Pre-registered in research/HK_CANADA_H2a_PREREG.md (committed bc0796822d, BEFORE this run).
Two decision trials: LEVEL (own-history pctile of days-to-cover) and Delta4w.
Forward window starts T+7 CALENDAR days after SFC position date (real publication lag).
Expected sign NEGATIVE per trial; wrong (positive) sign = NO-GO, not a flipped GO.

NO WIRING. Reports only.
"""
import os, json, math
import numpy as np
import pandas as pd

import engine.validation as V

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POS = os.path.join(ROOT, "data/hk_shorts/positions.parquet")
CORE = os.path.join(ROOT, "data/hk_stocks")
EXT = os.path.join(ROOT, "data/hk_stocks_ext")
HSI = os.path.join(ROOT, "data/hk/_HSI.parquet")

PCTILE_WIN = 104      # weeks own-history window
MIN_PRIOR = 52        # min prior weekly obs to receive a percentile
ADV_WIN = 63          # trading days for ADV
FWD_TD = 21           # 4 weeks forward trading days
LAG_DAYS = 7          # SFC publication lag (calendar)
MIN_FWD_BARS = 15     # of 21 forward bars must be real (halt rule)
ENTRY_HALT_TD = 3     # +-3 td window to find a real entry close
N_TRIALS = 30         # program DSR budget

# ---- load prices ----
def load_price(ticker):
    for base in (CORE, EXT):
        p = os.path.join(base, f"{ticker}.parquet")
        if os.path.exists(p):
            d = pd.read_parquet(p)
            d = d[~d.index.duplicated(keep="last")].sort_index()
            return d
    return None

print("loading positions ...")
pos = pd.read_parquet(POS).sort_values(["ticker", "date"])
dates = sorted(pos["date"].unique())
print(f"  {len(pos):,} rows, {len(dates)} weekly dates {pd.Timestamp(dates[0]).date()}->{pd.Timestamp(dates[-1]).date()}")

# universe = covered names that have a local price file
tickers = sorted(pos["ticker"].unique())
price = {}
for t in tickers:
    d = load_price(t)
    if d is not None and {"close", "volume"}.issubset(d.columns) and len(d) > ADV_WIN + FWD_TD:
        price[t] = d
print(f"  price panel available for {len(price)} / {len(tickers)} SFC names")

hsi = pd.read_parquet(HSI).sort_index()
hsi_close = hsi["close"].astype(float)

# ---- build per-name weekly signal frame ----
# For each (ticker, week) compute days-to-cover = shorted_shares / ADV_shares(<=t),
# then own-history percentile over trailing PCTILE_WIN weeks.
pos_by = {t: g.set_index("date") for t, g in pos.groupby("ticker")}

def adv_shares_asof(pdf, dt):
    sub = pdf.loc[:dt]
    if len(sub) < 21:
        return np.nan
    vol = sub["volume"].tail(ADV_WIN)
    if (vol > 0).sum() < 21:
        return np.nan
    return float(vol.mean())

def real_close_near(pdf, dt, tol=ENTRY_HALT_TD):
    """first real traded close on/after dt within tol trading days; return (date, close) or None."""
    idx = pdf.index
    loc = idx.searchsorted(pd.Timestamp(dt))
    if loc >= len(idx):
        return None
    # accept if the found bar is within tol trading days of dt (calendar proximity via td count from dt)
    cand = idx[loc]
    if (cand - pd.Timestamp(dt)).days > tol + 5:  # generous: markets closed spans
        # still allow if it is simply the next trading bar and within ~ a week
        if (cand - pd.Timestamp(dt)).days > 10:
            return None
    return cand, float(pdf.at[cand, "close"])

def fwd_excess(pdf, pos_date):
    """T+7-lagged 4w forward excess vs HSI. Suspension rule enforced. Returns float or None."""
    entry_cal = pd.Timestamp(pos_date) + pd.Timedelta(days=LAG_DAYS)
    ent = real_close_near(pdf, entry_cal)
    if ent is None:
        return None
    ent_date, ent_px = ent
    idx = pdf.index
    loc = idx.searchsorted(ent_date)
    fwd = pdf.iloc[loc: loc + FWD_TD + 1]
    if len(fwd) < MIN_FWD_BARS:
        return None
    real = fwd["close"].dropna()
    if len(real) < MIN_FWD_BARS:
        return None
    exit_date = real.index[-1]
    exit_px = float(real.iloc[-1])
    name_ret = exit_px / ent_px - 1.0
    # HSI over the SAME entry->exit dates
    h = hsi_close.reindex(idx).ffill()  # align to name calendar (index days)
    try:
        h_ent = float(hsi_close.loc[:ent_date].iloc[-1])
        h_exit = float(hsi_close.loc[:exit_date].iloc[-1])
    except Exception:
        return None
    if not (h_ent > 0):
        return None
    hsi_ret = h_exit / h_ent - 1.0
    return name_ret - hsi_ret

# assemble long frame: rows (week, ticker, dtc, fwd_excess)
records = []
for t, pdf in price.items():
    if t not in pos_by:
        continue
    g = pos_by[t]
    for dt in g.index:
        ss = float(g.at[dt, "shorted_shares"]) if not isinstance(g.at[dt, "shorted_shares"], pd.Series) else float(g.at[dt, "shorted_shares"].iloc[0])
        advs = adv_shares_asof(pdf, dt)
        if not (advs and advs > 0):
            continue
        dtc = ss / advs
        fx = fwd_excess(pdf, dt)
        records.append((pd.Timestamp(dt), t, dtc, fx))

df = pd.DataFrame(records, columns=["week", "ticker", "dtc", "fwd"]).sort_values(["ticker", "week"])
print(f"  raw signal rows: {len(df):,}")

# own-history percentile of dtc within trailing PCTILE_WIN weeks (>= MIN_PRIOR obs)
def own_pctile(s):
    out = pd.Series(index=s.index, dtype=float)
    vals = s.values
    for i in range(len(vals)):
        lo = max(0, i - PCTILE_WIN + 1)
        win = vals[lo:i + 1]
        win = win[~np.isnan(win)]
        if len(win) < MIN_PRIOR:
            out.iloc[i] = np.nan
        else:
            out.iloc[i] = (win <= vals[i]).mean()
    return out

df["s1"] = df.groupby("ticker")["dtc"].transform(own_pctile)          # LEVEL
df["s2"] = df.groupby("ticker")["s1"].transform(lambda x: x - x.shift(4))  # Delta4w (pctile change)

# ---- weekly cross-sectional stats ----
def weekly_ls_and_ic(sig_col):
    """Return per-week Q5-Q1 spread series and per-week rank-IC series."""
    spreads, ics, wk = [], [], []
    for w, gk in df.groupby("week"):
        g = gk[[sig_col, "fwd"]].dropna()
        if len(g) < 20:      # min valid names per week
            continue
        s = g[sig_col]; f = g["fwd"]
        # quintiles by signal
        try:
            q = pd.qcut(s.rank(method="first"), 5, labels=False)
        except ValueError:
            continue
        q5 = f[q == 4].mean(); q1 = f[q == 0].mean()
        if np.isnan(q5) or np.isnan(q1):
            continue
        spreads.append(q5 - q1)          # Q5(high short) - Q1(low short); expect NEGATIVE
        ics.append(V.rank_ic(s, f))      # expect NEGATIVE
        wk.append(w)
    return pd.Series(spreads, index=wk), pd.Series(ics, index=wk)

def daily_ls_series(sig_col):
    """A per-week LS return (Q1 - Q5, i.e. the tradable +sign short-book) resampled to
    a return stream for effective-N / DSR. Uses the same weekly spreads negated so a
    correct-sign (negative Q5-Q1) edge maps to a POSITIVE tradable return."""
    sp, _ = weekly_ls_and_ic(sig_col)
    # tradable book = long Q1 (low short) short Q5 (high short) = -(Q5-Q1)
    return (-sp).dropna()

def evaluate(sig_col, name):
    sp, ics = weekly_ls_and_ic(sig_col)
    n_wk = len(sp)
    mean_ic = float(ics.mean())
    mean_sp = float(sp.mean())           # Q5-Q1, expect negative
    hac = V.newey_west_tstat(sp, lags=3) # t on Q5-Q1 spread series
    ic_hac = V.newey_west_tstat(ics, lags=3)
    # split-half sign of Q5-Q1
    mid = n_wk // 2
    h1 = float(sp.iloc[:mid].mean()); h2 = float(sp.iloc[mid:].mean())
    split_ok = (np.sign(h1) == np.sign(h2)) and mean_sp < 0
    # tradable book returns (weekly), for DSR + effective-N
    book = (-sp).dropna()                # positive if correct-sign edge
    # treat weekly as the return series; annualize with ~52 ppy
    mom = V.ret_moments(book)   # (sharpe, skew, kurt, n) or None
    if mom is None:
        sr, skew, kurt = float("nan"), None, None
    else:
        sr, skew, kurt, _ = mom
    teff = V.bootstrap_effective_t(book, block=8)  # 8-week blocks (2 non-overlapping 4w windows)
    t_eff = teff.get("t_eff") if teff else None
    dsr = V.deflated_sharpe(sr, skew, kurt, len(book),
                            n_trials=N_TRIALS, t_eff=t_eff)
    return {
        "trial": name, "sig": sig_col, "n_weeks": n_wk,
        "mean_ic": round(mean_ic, 4), "ic_hac_t": ic_hac["t"], "ic_hac_p": ic_hac["p"],
        "mean_Q5mQ1": round(mean_sp, 5), "sp_hac_t": hac["t"], "sp_hac_p": hac["p"],
        "sign_correct": bool(mean_sp < 0 and mean_ic < 0),
        "split_h1": round(h1, 5), "split_h2": round(h2, 5), "split_sign_ok": bool(split_ok),
        "book_sharpe_wk": round(sr, 4) if sr == sr else None,
        "t_eff": t_eff, "dsr": (dsr or {}).get("dsr"), "dsr_verdict": V.dsr_verdict((dsr or {}).get("dsr", 0.0)),
        "sp_series": sp, "ic_series": ics, "book": book,
    }

print("\n=== TRIAL 1: LEVEL (own-history pctile of days-to-cover) ===")
r1 = evaluate("s1", "LEVEL")
for k, v in r1.items():
    if k in ("sp_series", "ic_series", "book"):
        continue
    print(f"  {k}: {v}")

print("\n=== TRIAL 2: Delta4w (4w change in short-pressure pctile) ===")
r2 = evaluate("s2", "DELTA4W")
for k, v in r2.items():
    if k in ("sp_series", "ic_series", "book"):
        continue
    print(f"  {k}: {v}")

# BH-FDR across the 2 trials on the Q5-Q1 spread HAC p-values
pvals = {"LEVEL": r1["sp_hac_p"], "DELTA4W": r2["sp_hac_p"]}
bh = V.benjamini_hochberg(pvals, alpha=0.10)
print("\n=== BH-FDR (alpha=0.10) across 2 trials on Q5-Q1 HAC p ===")
print(" ", bh)

# ---- T+0 lag-cost diagnostic (labeled, non-decision) ----
def fwd_excess_t0(pdf, pos_date):
    return fwd_excess(pdf, pd.Timestamp(pos_date) - pd.Timedelta(days=LAG_DAYS))
# recompute fwd with entry at ~T+0 (subtract lag so entry lands ~ on position date)
df0 = df.copy()
recs0 = []
for t, pdf in price.items():
    if t not in pos_by:
        continue
    g = pos_by[t]
    for dt in g.index:
        recs0.append((pd.Timestamp(dt), t, fwd_excess(pdf, pd.Timestamp(dt) - pd.Timedelta(days=LAG_DAYS))))
lag0 = pd.DataFrame(recs0, columns=["week", "ticker", "fwd0"])
dfm = df.merge(lag0, on=["week", "ticker"], how="left")
# LEVEL Q5-Q1 with T+0 fwd
sp0 = []
for w, gk in dfm.groupby("week"):
    g = gk[["s1", "fwd0"]].dropna()
    if len(g) < 20:
        continue
    q = pd.qcut(g["s1"].rank(method="first"), 5, labels=False)
    q5 = g["fwd0"][q == 4].mean(); q1 = g["fwd0"][q == 0].mean()
    if not (np.isnan(q5) or np.isnan(q1)):
        sp0.append(q5 - q1)
sp0 = pd.Series(sp0)
print("\n=== LAG-COST diagnostic (LEVEL, T+0 vs T+7) — labeled, non-decision ===")
print(f"  T+0 mean Q5-Q1: {sp0.mean():.5f}   |   T+7 mean Q5-Q1: {r1['mean_Q5mQ1']}")

# ---- SECONDARY normalization svl (fragility, non-decision) ----
# svl = value_hkd / (ADV_hkd * 63); own pctile; LEVEL trial only for fragility
recs_v = []
for t, pdf in price.items():
    if t not in pos_by:
        continue
    g = pos_by[t]
    for dt in g.index:
        vv = g.at[dt, "value_hkd"]
        vv = float(vv.iloc[0]) if isinstance(vv, pd.Series) else float(vv)
        sub = pdf.loc[:dt]
        if len(sub) < 21:
            continue
        advh = (sub["close"] * sub["volume"]).tail(ADV_WIN)
        if (advh > 0).sum() < 21:
            continue
        svl = vv / (float(advh.mean()) * ADV_WIN)
        fx = df[(df.ticker == t) & (df.week == pd.Timestamp(dt))]["fwd"]
        recs_v.append((pd.Timestamp(dt), t, svl))
dv = pd.DataFrame(recs_v, columns=["week", "ticker", "svl"]).sort_values(["ticker", "week"])
dv["sv1"] = dv.groupby("ticker")["svl"].transform(own_pctile)
dvm = dv.merge(df[["week", "ticker", "fwd"]], on=["week", "ticker"], how="left")
sp_sv = []
for w, gk in dvm.groupby("week"):
    g = gk[["sv1", "fwd"]].dropna()
    if len(g) < 20:
        continue
    q = pd.qcut(g["sv1"].rank(method="first"), 5, labels=False)
    q5 = g["fwd"][q == 4].mean(); q1 = g["fwd"][q == 0].mean()
    if not (np.isnan(q5) or np.isnan(q1)):
        sp_sv.append(q5 - q1)
sp_sv = pd.Series(sp_sv)
sv_hac = V.newey_west_tstat(sp_sv, lags=3)
print("\n=== SECONDARY norm svl (LEVEL) — fragility, non-decision ===")
print(f"  mean Q5-Q1: {sp_sv.mean():.5f}  HAC-t: {sv_hac['t']}  n_wk: {len(sp_sv)}")

# ---- survivorship worst-case imputation bound (LEVEL) ----
# names that EXIT the SFC file >=8 weeks after appearing in top short-pressure quintile
# get -40% forward excess at last-observed rank. Recompute LEVEL Q5-Q1.
last_seen = pos.groupby("ticker")["date"].max()
overall_last = pos["date"].max()
imp = df.copy()
# a name is "gone" if its last SFC week is >= 8 weeks before the panel end
gone = last_seen[last_seen <= (pd.Timestamp(overall_last) - pd.Timedelta(weeks=8))].index
mask = imp["ticker"].isin(gone) & imp["fwd"].isna() & imp["s1"].notna() & (imp["s1"] >= 0.8)
imp.loc[mask, "fwd"] = -0.40
sp_imp = []
for w, gk in imp.groupby("week"):
    g = gk[["s1", "fwd"]].dropna()
    if len(g) < 20:
        continue
    q = pd.qcut(g["s1"].rank(method="first"), 5, labels=False)
    q5 = g["fwd"][q == 4].mean(); q1 = g["fwd"][q == 0].mean()
    if not (np.isnan(q5) or np.isnan(q1)):
        sp_imp.append(q5 - q1)
sp_imp = pd.Series(sp_imp)
print("\n=== SURVIVORSHIP worst-case imputation bound (LEVEL) ===")
print(f"  imputed names: {len(gone)} gone; masked rows: {int(mask.sum())}")
print(f"  raw mean Q5-Q1: {r1['mean_Q5mQ1']}   |   worst-case-imputed mean Q5-Q1: {sp_imp.mean():.5f}")
print(f"  sign held (both negative)? {bool(r1['mean_Q5mQ1'] < 0 and sp_imp.mean() < 0)}")

# ---- coverage / size skew stamp ----
covered_core = [t for t in os.listdir(CORE) if t.endswith('.parquet') and t.replace('.parquet','') in set(tickers)]
print(f"\n=== COVERAGE STAMP === core covered: {len(covered_core)}/157  union price: {len(price)}")

out = {
    "prereg": "research/HK_CANADA_H2a_PREREG.md (bc0796822d)",
    "n_trials_dsr": N_TRIALS,
    "trial_LEVEL": {k: v for k, v in r1.items() if k not in ("sp_series", "ic_series", "book")},
    "trial_DELTA4W": {k: v for k, v in r2.items() if k not in ("sp_series", "ic_series", "book")},
    "bh_fdr": bh,
    "lag_cost_T0_Q5mQ1_LEVEL": round(float(sp0.mean()), 5),
    "secondary_svl_LEVEL": {"mean_Q5mQ1": round(float(sp_sv.mean()), 5), "hac_t": sv_hac["t"], "n_wk": len(sp_sv)},
    "surv_imputed_Q5mQ1_LEVEL": round(float(sp_imp.mean()), 5),
    "surv_sign_held": bool(r1["mean_Q5mQ1"] < 0 and sp_imp.mean() < 0),
    "coverage_core": len(covered_core), "coverage_union": len(price),
}
with open(os.path.join(ROOT, "research/h2a_phase0_results.json"), "w") as f:
    json.dump(out, f, indent=2, default=str)
print("\nwrote research/h2a_phase0_results.json")
