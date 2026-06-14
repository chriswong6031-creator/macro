"""Factor portfolio RETURN SERIES — the FactorWatch "index" view on free data.

FactorWatch charts each factor as a daily portfolio return series; we only had a
single trailing-spread snapshot. This walks month-ends over the ~3y price cache and,
at each, rebuilds the factor cross-section AS IT WAS KNOWABLE THEN
(engine.equity_factors.compute_factors(asof=d) — point-in-time, no look-ahead) to form:

  * long-only  : top-quintile, CAP-WEIGHTED with a 5% single-name cap (so it can't
                 degenerate into a few mega-caps)
  * long/short : top-quintile minus bottom-quintile, EQUAL-WEIGHTED (the academic
                 factor-premium diagnostic — a paper spread, not a shortable book)

held buy-and-hold to the next month-end. From the daily series we derive horizon
returns (1/5/20d) z-scored vs each series' own trailing-252 distribution, Sharpe/
MaxDD WITH a block-bootstrap CI, a crowding correlation matrix of the L/S series,
leadership rotation (20d leader, 3-session-persistent flips), and a monthly quilt.

HONEST CEILING (stated on the page): free fundamentals are ANNUAL, so the fundamental
factor RANKS only refresh ~once a year per name — most rebalance turnover is the
price-derived legs (low-vol/low-beta). History is ~3 years and NO factor clears FDR
(see the IC scorecard). Descriptive context, not validated/tradeable alpha.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.equity_factors import _closes, compute_factors
from engine.validation import _maxdd, _sharpe, block_bootstrap_ci, top_correlated_pairs
from lib import config, store

log = logging.getLogger(__name__)

# composite legs + the composite itself + low_beta (price-derived). short_interest is a
# current-snapshot leak / accruals is a quality sub-leg → excluded from the series set.
SERIES_FACTORS = ["value", "profitability", "quality", "investment", "payout",
                  "low_vol", "low_beta", "composite"]
LABELS = {"value": "Value", "profitability": "Profitability", "quality": "Quality",
          "investment": "Investment", "payout": "Payout", "low_vol": "Low volatility",
          "low_beta": "Low beta", "composite": "Composite"}
HORIZONS = {"d1": 1, "d5": 5, "d20": 20}
SPARK_POINTS = 120
SINGLE_NAME_CAP = 0.05
TRAIL = 252


def _cap_weight(mc: pd.Series, cap: float = SINGLE_NAME_CAP) -> pd.Series:
    """Cap-weight by market cap with an iterative single-name cap (excess redistributed
    pro-rata to the uncapped until every weight <= cap; weights sum to 1). If the cap is
    infeasible (n*cap <= 1, i.e. too few names) fall back to equal weight."""
    n = len(mc)
    if n == 0:
        return mc
    if n * cap <= 1.0:
        return pd.Series(1.0 / n, index=mc.index)
    w = mc / mc.sum()
    for _ in range(100):
        over = w > cap + 1e-9
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        under = ~over
        base = float(w[under].sum())
        if base <= 0:
            break
        w[under] = w[under] + excess * w[under] / base
    return w


def _month_ends(idx: pd.DatetimeIndex) -> list:
    df = pd.Series(idx, index=idx)
    return [grp.iloc[-1] for _, grp in df.groupby([idx.year, idx.month])]


def _hz(r: pd.Series, h: int) -> float | None:
    r = r.dropna()
    if len(r) <= h:
        return None
    return float(((1.0 + r).tail(h).prod() - 1.0) * 100)


def _hz_z(r: pd.Series, h: int) -> tuple:
    """z-score + percentile of the latest h-day compounded return vs the trailing-252
    distribution of overlapping h-day returns of the same series."""
    r = r.dropna()
    if len(r) <= h + 30:
        return None, None, False
    comp = (1.0 + r).rolling(h).apply(np.prod, raw=True) - 1.0
    comp = comp.dropna()
    if len(comp) < 40:
        return None, None, False
    cur = float(comp.iloc[-1])
    hist = comp.iloc[-(TRAIL + 1):-1]                 # trailing window, current excluded
    mu, sd = float(hist.mean()), float(hist.std())
    z = (cur - mu) / sd if sd else None
    pct = int(round(float((hist < cur).mean()) * 100))
    return (round(float(z), 2) if z is not None else None), pct, bool(z is not None and abs(z) >= 2)


def _spark(cum: pd.Series) -> list:
    cum = cum.dropna()
    if cum.empty:
        return []
    step = max(1, len(cum) // SPARK_POINTS)
    return [round(float(v), 2) for v in cum.iloc[::step]]


def _nav(r: pd.Series) -> list:
    """Daily NAV LEVEL series (1.0 at first valid, NaN before) for the interactive chart —
    full resolution so the client can rebase per range + z-score (winRet/winZ)."""
    first = r.first_valid_index()
    if first is None:
        return [None] * len(r)
    lv = pd.Series(np.nan, index=r.index)
    lv.loc[first:] = (1.0 + r.loc[first:].fillna(0.0)).cumprod()
    return [None if pd.isna(v) else round(float(v), 5) for v in lv]


def compute_factor_series(universe: str = "broad") -> dict | None:
    """Walk month-ends, build per-factor long-only + L/S daily return series, and
    derive horizons, stats, crowding, rotation and the quilt. None if no caches.
    universe='narrow' restricts to the S&P 500 large-cap cache (shorter history)."""
    closes = _closes(universe)
    if closes is None or closes.empty:
        return None
    rets = closes.pct_change(fill_method=None)
    idx = closes.index
    me = _month_ends(idx)
    if len(me) < 6:
        return None

    lo = {f: pd.Series(np.nan, index=idx) for f in SERIES_FACTORS}     # long-only daily ret
    ls = {f: pd.Series(np.nan, index=idx) for f in SERIES_FACTORS}     # Q5-Q1 daily ret
    sec_ret: dict = {}                                                 # cap-weighted GICS sector daily ret

    for i, d in enumerate(me):
        try:
            fac = compute_factors(asof=d, universe=universe)
        except Exception as e:  # noqa: BLE001
            log.warning("compute_factors(asof=%s) failed: %s", d.date(), e)
            continue
        if not fac or not fac.get("table"):
            continue
        t = pd.DataFrame(fac["table"]).set_index("ticker")
        hold = idx[(idx > d) & (idx <= (me[i + 1] if i + 1 < len(me) else idx[-1]))]
        if len(hold) == 0:
            continue
        mc_all = pd.to_numeric(t.get("mktcap_bn"), errors="coerce") if "mktcap_bn" in t else None
        for f in SERIES_FACTORS:
            if f not in t.columns:
                continue
            z = pd.to_numeric(t[f], errors="coerce").dropna()
            if len(z) < 100:
                continue
            q5 = z[z >= z.quantile(0.8)].index
            q1 = z[z <= z.quantile(0.2)].index
            if len(q5) < 20 or len(q1) < 20:
                continue
            # long-only: cap-weighted top quintile (5% cap), names with a valid mktcap
            if mc_all is not None:
                mc = mc_all.reindex(q5).dropna()
                mc = mc[mc > 0]
                cols = [c for c in mc.index if c in rets.columns]
                if len(cols) >= 10:
                    w = _cap_weight(mc[cols])
                    lo[f].loc[hold] = rets.loc[hold, cols].mul(w[cols], axis=1).sum(axis=1)
            # long/short: EW top minus EW bottom (paper premium)
            c5 = [c for c in q5 if c in rets.columns]
            c1 = [c for c in q1 if c in rets.columns]
            if len(c5) >= 10 and len(c1) >= 10:
                ls[f].loc[hold] = rets.loc[hold, c5].mean(axis=1) - rets.loc[hold, c1].mean(axis=1)
        # cap-weighted GICS sector series — the relational sector-vs-benchmark monitor
        if "sector" in t.columns and mc_all is not None:
            for sec in [s for s in t["sector"].dropna().unique() if s and s != "—"]:
                grp = t.index[t["sector"] == sec]
                mc = mc_all.reindex(grp).dropna()
                mc = mc[mc > 0]
                cols = [c for c in mc.index if c in rets.columns]
                if len(cols) >= 3:
                    w = mc[cols] / mc[cols].sum()
                    sec_ret.setdefault(sec, pd.Series(np.nan, index=idx))
                    sec_ret[sec].loc[hold] = rets.loc[hold, cols].mul(w, axis=1).sum(axis=1)

    # SPY benchmark (cap-weighted market)
    spy = store.read("yahoo", "SPY")
    spy_ret = (spy["close"].reindex(idx).ffill().pct_change()
               if spy is not None and "close" in spy.columns else None)

    active = [f for f in SERIES_FACTORS if ls[f].notna().sum() > 60]
    if not active:
        return None

    def _cum(r):
        r = r.copy()
        first = r.first_valid_index()
        if first is None:
            return pd.Series(dtype=float)
        c = (1.0 + r.loc[first:].fillna(0.0)).cumprod() - 1.0
        return c * 100

    series, horizons, stats = {}, {}, {}
    for f in active:
        lo_c, ls_c = _cum(lo[f]), _cum(ls[f])
        series[f] = {
            "long_only": {"spark": _spark(lo_c), "cum_pct": round(float(lo_c.iloc[-1]), 1) if not lo_c.empty else None},
            "long_short": {"spark": _spark(ls_c), "cum_pct": round(float(ls_c.iloc[-1]), 1) if not ls_c.empty else None},
        }
        hz = {}
        for leg, sr in (("long_only", lo[f]), ("long_short", ls[f])):
            hz[leg] = {}
            for k, h in HORIZONS.items():
                z, pct, flag = _hz_z(sr, h)
                hz[leg][k] = {"ret_pct": round(_hz(sr, h), 2) if _hz(sr, h) is not None else None,
                              "z": z, "pct": pct, "flag": flag}
        horizons[f] = hz
        lsv = ls[f].dropna()
        ci = block_bootstrap_ci(lsv, ann=252)
        stats[f] = {
            "sharpe_lo": round(_sharpe(lo[f].dropna(), 252), 2) if lo[f].notna().sum() > 30 else None,
            "sharpe_ls": round(_sharpe(lsv, 252), 2) if len(lsv) > 30 else None,
            "maxdd_ls_pct": round(_maxdd(lsv) * 100, 1) if len(lsv) > 30 else None,
            "sharpe_ls_ci": ci.get("sharpe_ci"), "sharpe_gt0_prob": ci.get("sharpe_gt0_prob"),
        }

    # SPY benchmark series (rebased over the longest factor window)
    bench = None
    if spy_ret is not None:
        anchor = min((lo[f].first_valid_index() for f in active if lo[f].first_valid_index() is not None),
                     default=idx[0])
        bc = (1.0 + spy_ret.loc[anchor:].fillna(0.0)).cumprod() - 1.0
        bench = {"spark": _spark(bc * 100), "cum_pct": round(float((bc.iloc[-1]) * 100), 1)}

    # crowding: signed corr of the L/S daily returns across factors (deep blue=crowded, red=hedge)
    lsdf = pd.DataFrame({f: ls[f] for f in active}).dropna()
    crowding = None
    if len(lsdf) > 60 and lsdf.shape[1] >= 3:
        cm = lsdf.corr()
        crowding = {
            "factors": active,
            "matrix": [[round(float(cm.loc[a, b]), 2) for b in active] for a in active],
            "pairs": top_correlated_pairs(lsdf, k=6, thresh=0.5),
        }

    # leadership rotation: leader = top factor by trailing-20d L/S return; flag flips that
    # persist 3 consecutive sessions (debounce one-day wobble).
    rotation = _rotation(ls, active)

    # quilt: monthly L/S total return per factor (ranked best->worst per month elsewhere/UI)
    quilt = _quilt(ls, active)

    # dense NAV matrix for the interactive lightweight-charts view (client rebases per range):
    # long-only + Q5-Q1 spread per factor, cap-weighted GICS sectors, and the SPY benchmark.
    chart_data = {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "bench": _nav(spy_ret) if spy_ret is not None else [None] * len(idx),
        "long": {f: _nav(lo[f]) for f in active},
        "spread": {f: _nav(ls[f]) for f in active},
        "sector": {s: _nav(r) for s, r in sorted(sec_ret.items()) if r.notna().sum() > 60},
        "labels": {f: LABELS.get(f, f) for f in active},
    }

    return {
        "as_of": idx.max().strftime("%Y-%m-%d"),
        "history_start": idx.min().strftime("%Y-%m-%d"),
        "n_rebalances": len(me),
        "factors": active,
        "labels": {f: LABELS.get(f, f) for f in active},
        "series": series, "horizons": horizons, "stats": stats,
        "benchmark": bench, "crowding": crowding, "rotation": rotation, "quilt": quilt,
        "chart_data": chart_data,
        "note": ("Point-in-time month-end rebalanced; long-only = cap-weighted top quintile "
                 "(5% name cap), long/short = equal-weight Q5-Q1 (a paper premium, not shortable)."),
        "honesty": ("Free fundamentals are ANNUAL, so fundamental factor ranks refresh only ~once "
                    "a year per name — most rebalance turnover is the price legs (low-vol/low-beta). "
                    "History is ~3 years; every Sharpe ships with a block-bootstrap CI that mostly "
                    "straddles zero, and NO factor clears FDR on the IC scorecard. Descriptive "
                    "context, not validated or tradeable alpha."),
    }


def _rotation(ls: dict, active: list) -> dict:
    df = pd.DataFrame({f: ls[f] for f in active}).dropna(how="all")
    roll20 = (1.0 + df.fillna(0.0)).rolling(20).apply(np.prod, raw=True) - 1.0
    roll20 = roll20.dropna(how="all")
    if roll20.empty:
        return {}
    leader_raw = roll20.idxmax(axis=1)
    # 3-session-persistent leader (debounce)
    confirmed, cur, run = [], None, 0
    for d, lead in leader_raw.items():
        if lead == (confirmed[-1][1] if confirmed else None):
            run = 0
        if lead == cur:
            run += 1
        else:
            cur, run = lead, 1
        if run >= 3 and (not confirmed or confirmed[-1][1] != lead):
            confirmed.append((d, lead))
    flips = [{"date": d.strftime("%Y-%m-%d"), "to": f, "label": LABELS.get(f, f)}
             for d, f in confirmed[-6:]]
    last = leader_raw.iloc[-1]
    return {"leader": last, "leader_label": LABELS.get(last, last),
            "leader_ret20_pct": round(float(roll20.iloc[-1][last]) * 100, 2),
            "recent_flips": flips}


def _quilt(ls: dict, active: list) -> dict:
    df = pd.DataFrame({f: ls[f] for f in active})
    monthly = (1.0 + df.fillna(0.0)).resample("ME").apply(lambda x: x.prod()) - 1.0
    monthly = monthly.dropna(how="all").tail(15)                       # last ~15 months
    months = [d.strftime("%Y-%m") for d in monthly.index]
    table = {f: {d.strftime("%Y-%m"): round(float(monthly.loc[d, f]) * 100, 1)
                 for d in monthly.index if pd.notna(monthly.loc[d, f])} for f in active}
    ranked = {d.strftime("%Y-%m"): [f for f in monthly.loc[d].sort_values(ascending=False).index
                                    if pd.notna(monthly.loc[d, f])] for d in monthly.index}
    return {"months": months, "returns": table, "ranked": ranked}
