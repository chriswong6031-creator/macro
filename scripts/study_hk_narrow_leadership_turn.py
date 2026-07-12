#!/usr/bin/env python3
"""STUDY B — Narrow leadership-cohort turn (HK). READ-ONLY, rerunnable.

Question: Is a "narrow mega-cap leadership turn + inbound southbound flow" a real
PRECEDENT for a broad HSI advance, a COINCIDENT participation state, or a BULL-TRAP
pattern?

Construction (per task spec + kill-registry guards):
  Cohort  = fixed mega-cap list (top HK names by cap), store-availability adjusted.
  Cohort-turn indicator = fraction of cohort above a *rising* 10d MA crosses from
                          < 0.30 to >= 0.60 within a 10-session window (cohesion thrust).
  Narrow condition       = broad breadth pct_above_50 < 35 on the trigger day.
  Flow leg (REQUIRED per cn_supply_absorption kill: a cohort-turn signal MUST carry a
            non-price flow leg) = southbound net accumulation into the cohort positive.
  Price-only variant is run separately ONLY as a CONTROL to show what flow adds.

For each episode (consecutive trigger days collapsed): forward HSI 20/40/60d return +
hit rate, cohort own forward return, bull-trap rate (HSI lower-low within 40d).
Compared vs unconditional base rates + era split. Time-preserving null: permute
episode labels across MONTHS (episode-first-month blocking), NOT iid bootstrap —
effective N is months, not name-days.

HARD DATA CONSTRAINT (reported, not hidden): per-name southbound holdings only exist
2024-07-10 .. 2026-07-07 (~2y). The flow-required PRIMARY variant is therefore
n-limited by construction; the price-only CONTROL runs over the full 2016+ era.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = "/Users/chriswong/Documents/Cluade/Macro Dashboard"

COHORT = ["0700.HK", "9988.HK", "3690.HK", "1810.HK", "9618.HK",
          "1024.HK", "2318.HK", "0941.HK", "1211.HK", "9888.HK"]

LO, HI, WIN = 0.30, 0.60, 10          # cohesion-thrust thresholds + window
NARROW_MAX = 35.0                      # pct_above_50 narrow gate
HORIZONS = [20, 40, 60]
N_PERM = 5000
RNG = np.random.default_rng(20260711)


def load_prices():
    px = {}
    for t in COHORT:
        p = f"{ROOT}/data/hk_stocks/{t}.parquet"
        if os.path.exists(p):
            s = pd.read_parquet(p)["close"].sort_index()
            px[t] = s[~s.index.duplicated(keep="last")]
    return px


def load_hsi():
    h = pd.read_parquet(f"{ROOT}/data/hk/_HSI.parquet")["close"].sort_index()
    return h[~h.index.duplicated(keep="last")]


def load_breadth():
    b = pd.read_parquet(f"{ROOT}/data/hk_breadth/breadth.parquet").sort_index()
    return b["pct_above_50"]


def load_southbound_cohort_flow():
    """Per-day cohort net accumulation proxy: sum of chg5_v (5d change in HKD holding
    value) across cohort names present. Positive => mainland adding to the cohort."""
    df = pd.read_parquet(f"{ROOT}/data/hk_southbound/holdings.parquet")
    tks = df.index.get_level_values("ticker")
    sub = df[tks.isin(COHORT)]
    flow = sub.groupby(level="date")["chg5_v"].sum().sort_index()
    return flow


def cohort_above_rising_ma(px, ma=10):
    """Daily fraction of listed cohort names trading above a RISING <ma>d MA."""
    frames = {}
    for t, s in px.items():
        m = s.rolling(ma).mean()
        rising = m.diff() > 0
        above = (s > m) & rising
        frames[t] = above
    F = pd.DataFrame(frames)
    # fraction over names that are LISTED (have a valid MA) that day
    listed = pd.DataFrame({t: px[t].reindex(F.index).notna() for t in px})
    valid = F.notna() & listed
    num = (F & valid).sum(axis=1)
    den = valid.sum(axis=1)
    frac = num / den.replace(0, np.nan)
    return frac.where(den >= 5)   # require >=5 listed cohort names for a real read


def thrust_triggers(frac):
    """Day t is a trigger if frac[t] >= HI and min(frac[t-WIN..t]) < LO
    (crossed from <0.30 to >=0.60 within WIN sessions)."""
    lo_recent = frac.shift(1).rolling(WIN, min_periods=1).min()
    trig = (frac >= HI) & (lo_recent < LO)
    return trig.fillna(False)


def collapse_episodes(dates_bool, min_gap=20):
    """Collapse trigger days into episodes; a new episode starts if >min_gap sessions
    since the last trigger. Returns list of episode start dates (first trigger day)."""
    idx = dates_bool.index
    pos = np.where(dates_bool.values)[0]
    eps = []
    last = -10**9
    for p in pos:
        if p - last > min_gap:
            eps.append(idx[p])
        last = p
    return eps


def fwd_ret(series, d0, h):
    idx = series.index
    if d0 not in idx:
        # snap to next available
        loc = idx.searchsorted(d0)
        if loc >= len(idx):
            return np.nan, idx[-1] if len(idx) else None
        d0 = idx[loc]
    i = idx.get_loc(d0)
    j = i + h
    if j >= len(idx):
        return np.nan, None
    return series.iloc[j] / series.iloc[i] - 1.0, idx[j]


def hsi_lower_low(hsi, d0, h=40):
    idx = hsi.index
    loc = idx.searchsorted(d0)
    if loc >= len(idx):
        return np.nan
    d0 = idx[loc]
    i = idx.get_loc(d0)
    j = min(i + h, len(idx) - 1)
    win = hsi.iloc[i:j + 1]
    return bool(win.min() < hsi.iloc[i])


def eval_episodes(eps, hsi, cohort_close):
    rows = []
    for d in eps:
        row = {"date": d}
        for h in HORIZONS:
            r, _ = fwd_ret(hsi, d, h)
            row[f"hsi_{h}"] = r
        for h in HORIZONS:
            r, _ = fwd_ret(cohort_close, d, h)
            row[f"coh_{h}"] = r
        row["bulltrap_40"] = hsi_lower_low(hsi, d, 40)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(df, label):
    out = {"label": label, "n": len(df)}
    if len(df) == 0:
        return out
    for h in HORIZONS:
        c = df[f"hsi_{h}"].dropna()
        out[f"hsi_{h}_mean"] = round(float(c.mean()) * 100, 2) if len(c) else None
        out[f"hsi_{h}_hit"] = round(float((c > 0).mean()) * 100, 1) if len(c) else None
        ch = df[f"coh_{h}"].dropna()
        out[f"coh_{h}_mean"] = round(float(ch.mean()) * 100, 2) if len(ch) else None
    bt = df["bulltrap_40"].dropna()
    out["bulltrap_40_rate"] = round(float(bt.mean()) * 100, 1) if len(bt) else None
    return out


def base_rate(hsi, dates_universe, label):
    """Unconditional forward-return base rate over the sampling universe dates."""
    rows = []
    idx = hsi.index
    for d in dates_universe:
        loc = idx.searchsorted(d)
        if loc >= len(idx):
            continue
        d = idx[loc]
        row = {}
        for h in HORIZONS:
            r, _ = fwd_ret(hsi, d, h)
            row[f"hsi_{h}"] = r
        row["bulltrap_40"] = hsi_lower_low(hsi, d, 40)
        rows.append(row)
    df = pd.DataFrame(rows)
    out = {"label": label, "n_days": len(df)}
    for h in HORIZONS:
        c = df[f"hsi_{h}"].dropna()
        out[f"hsi_{h}_mean"] = round(float(c.mean()) * 100, 2) if len(c) else None
        out[f"hsi_{h}_hit"] = round(float((c > 0).mean()) * 100, 1) if len(c) else None
    bt = df["bulltrap_40"].dropna()
    out["bulltrap_40_rate"] = round(float(bt.mean()) * 100, 1) if len(bt) else None
    return out


def month_permutation_null(trigger_days, candidate_days, hsi, h=40, n=N_PERM):
    """Time-preserving null: the observed statistic is the mean forward-h HSI return on
    trigger days. Under the null, the *episode-to-month labelling* is exchangeable: we
    resample the same NUMBER of episodes, but draw their host MONTHS at random from the
    set of eligible months (months containing >=1 narrow-condition day), then place the
    episode on a random eligible day within that month. This preserves within-month
    autocorrelation and month-level clustering — effective N = months, not name-days."""
    idx = hsi.index

    def mean_fwd(days):
        vals = []
        for d in days:
            r, _ = fwd_ret(hsi, d, h)
            if not np.isnan(r):
                vals.append(r)
        return np.mean(vals) if vals else np.nan

    obs = mean_fwd(trigger_days)
    if np.isnan(obs) or len(trigger_days) == 0:
        return obs, np.nan, 0

    cand = pd.DatetimeIndex(candidate_days)
    by_month = {}
    for d in cand:
        by_month.setdefault((d.year, d.month), []).append(d)
    months = list(by_month.keys())
    k = len(trigger_days)
    if len(months) < 1:
        return obs, np.nan, 0

    ge = 0
    valid = 0
    for _ in range(n):
        pick_months = RNG.choice(len(months), size=min(k, len(months)), replace=False)
        days = []
        for mi in pick_months:
            pool = by_month[months[mi]]
            days.append(pool[RNG.integers(len(pool))])
        m = mean_fwd(days)
        if not np.isnan(m):
            valid += 1
            if m >= obs:
                ge += 1
    p = (ge + 1) / (valid + 1) if valid else np.nan
    return obs, p, valid


def run_variant(trig, frac, hsi, cohort_close, breadth, flow, label, era_lo=None,
                era_hi=None, require_flow=False):
    tr = trig.copy()
    # narrow gate
    br = breadth.reindex(tr.index).ffill(limit=3)
    tr &= (br < NARROW_MAX)
    if require_flow:
        fl = flow.reindex(tr.index).ffill(limit=3)
        tr &= (fl > 0)
        # restrict to flow-available window
        tr &= tr.index >= flow.index.min()
        tr &= tr.index <= flow.index.max()
    if era_lo is not None:
        tr &= tr.index >= era_lo
    if era_hi is not None:
        tr &= tr.index < era_hi
    tr = tr.fillna(False)

    eps = collapse_episodes(tr)
    df = eval_episodes(eps, hsi, cohort_close)
    summ = summarize(df, label)

    # candidate universe for the null = narrow-condition days in the active era/window
    cand = br.index[(br < NARROW_MAX)]
    if require_flow:
        fl = flow.reindex(pd.DatetimeIndex(cand)).ffill(limit=3)
        cand = pd.DatetimeIndex(cand)[(fl.values > 0)]
        cand = cand[(cand >= flow.index.min()) & (cand <= flow.index.max())]
    if era_lo is not None:
        cand = pd.DatetimeIndex(cand)[pd.DatetimeIndex(cand) >= era_lo]
    if era_hi is not None:
        cand = pd.DatetimeIndex(cand)[pd.DatetimeIndex(cand) < era_hi]

    obs40, p40, nperm = month_permutation_null(eps, list(cand), hsi, h=40)
    summ["null_hsi40_obs_pct"] = round(obs40 * 100, 2) if not np.isnan(obs40) else None
    summ["null_hsi40_p"] = round(p40, 3) if not np.isnan(p40) else None
    summ["null_valid_draws"] = nperm
    summ["episode_dates"] = [str(d.date()) for d in eps]
    return summ, df, list(cand)


def main():
    px = load_prices()
    hsi = load_hsi()
    breadth = load_breadth()
    flow = load_southbound_cohort_flow()
    frac = cohort_above_rising_ma(px)
    trig = thrust_triggers(frac)

    # equal-weight cohort close index (rebased) for cohort forward return
    rets = pd.DataFrame({t: s.pct_change() for t, s in px.items()})
    coh_ret = rets.mean(axis=1)
    cohort_close = (1 + coh_ret.fillna(0)).cumprod()

    print("=" * 78)
    print("DATA WINDOWS")
    print(f"  cohort names available : {sorted(px.keys())}")
    print(f"  HSI                    : {hsi.index.min().date()} .. {hsi.index.max().date()}")
    print(f"  breadth pct_above_50   : {breadth.dropna().index.min().date()} .. {breadth.dropna().index.max().date()}")
    print(f"  southbound cohort flow : {flow.index.min().date()} .. {flow.index.max().date()}  ({len(flow)} days)")
    print(f"  raw thrust triggers    : {int(trig.sum())} days ({frac.dropna().index.min().date()}+)")

    results = []

    # ---- PRICE-ONLY CONTROL (long era, 2016+) ----
    s, dfc, cand = run_variant(trig, frac, hsi, cohort_close, breadth, flow,
                               "CONTROL price-only narrow-turn [2016+]",
                               era_lo=pd.Timestamp("2016-01-01"), require_flow=False)
    results.append(s)

    # era split of the price-only control (split-half of 2016+ window)
    mid = pd.Timestamp("2021-01-01")
    s1, _, _ = run_variant(trig, frac, hsi, cohort_close, breadth, flow,
                           "CONTROL price-only [2016-2020]",
                           era_lo=pd.Timestamp("2016-01-01"), era_hi=mid)
    s2, _, _ = run_variant(trig, frac, hsi, cohort_close, breadth, flow,
                           "CONTROL price-only [2021-2026]",
                           era_lo=mid, era_hi=None)
    results.append(s1)
    results.append(s2)

    # ---- FLOW-REQUIRED PRIMARY (flow window only, ~2y) ----
    sf, dff, candf = run_variant(trig, frac, hsi, cohort_close, breadth, flow,
                                 "PRIMARY narrow-turn + southbound-flow [2024-07..2026-07]",
                                 require_flow=True)
    results.append(sf)

    # price-only over the SAME flow window (isolates what flow adds)
    sw, _, _ = run_variant(trig, frac, hsi, cohort_close, breadth, flow,
                           "price-only over flow window [2024-07..2026-07]",
                           era_lo=flow.index.min(), era_hi=None)
    results.append(sw)

    # ---- BASE RATES ----
    br_all = base_rate(hsi, hsi.index[(hsi.index >= pd.Timestamp("2016-01-01"))][::5],
                       "BASE-RATE unconditional HSI [2016+, every 5d]")
    # narrow-condition base rate (broad breadth<35, any cohort state)
    narrow_days = breadth.index[(breadth < NARROW_MAX) & (breadth.index >= pd.Timestamp("2016-01-01"))]
    br_narrow = base_rate(hsi, list(pd.DatetimeIndex(narrow_days)[::5]),
                          "BASE-RATE narrow-breadth days [2016+, every 5d]")

    print("\n" + "=" * 78)
    print("BASE RATES")
    for b in (br_all, br_narrow):
        print(f"\n{b['label']}  (n_days={b['n_days']})")
        for h in HORIZONS:
            print(f"   HSI {h}d: mean {b[f'hsi_{h}_mean']}%  hit {b[f'hsi_{h}_hit']}%")
        print(f"   bull-trap(40d lower-low): {b['bulltrap_40_rate']}%")

    print("\n" + "=" * 78)
    print("VARIANT RESULTS")
    for s in results:
        print(f"\n--- {s['label']} ---")
        print(f"   episodes n = {s['n']}   dates = {s.get('episode_dates')}")
        if s["n"]:
            for h in HORIZONS:
                print(f"   HSI {h}d: mean {s[f'hsi_{h}_mean']}%  hit {s[f'hsi_{h}_hit']}%   "
                      f"cohort {h}d mean {s[f'coh_{h}_mean']}%")
            print(f"   bull-trap(40d lower-low): {s['bulltrap_40_rate']}%")
            print(f"   month-perm null HSI40: obs {s['null_hsi40_obs_pct']}%  "
                  f"p={s['null_hsi40_p']}  (valid draws {s['null_valid_draws']})")
    print("\n" + "=" * 78)
    print("Interpretation guide: p<~0.10 on the month-permutation null => forward edge")
    print("beyond the narrow-breadth base rate. n<~5 episodes => insufficient-n.")


if __name__ == "__main__":
    main()
