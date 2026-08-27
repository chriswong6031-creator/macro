"""Forward shadow book — the institutional measurement floor (research/INSTITUTIONAL_ROADMAP.md
keystone). The traded score has never been graded on REALIZED forward returns; an in-sample
or even walk-forward backtest still overstates, because the only honest test of a live score
is to FREEZE it at build time and grade it once the forward window has fully elapsed.

Three pure functions, append-only, leak-free by construction:

  snapshot(date, recs)  — append (date, ticker, score, percentile, regime) frozen at the
                          build date `t`. Append-only + dedup by (date, ticker): a nightly
                          rebuild never overwrites or backfills history.
  mature(asof, closes)  — join only rows whose horizon has FULLY ELAPSED (the h-th trading
                          bar after `date` exists in `closes` AND its date <= asof) to the
                          realized forward return. The elapsed-horizon guard is the whole
                          point: a horizon that has not closed is NEVER graded.
  grade(matured)        — rolling forward rank-IC + ic_summary (IC-IR, HAC-t) + Clark-West
                          vs an expanding-mean benchmark, per horizon, using engine.validation.

Honest expectation (stated up front): given the committed factor scorecard (composite IC
~0, only payout survives FDR, all on the optimistic survivor bound), the forward book will
most likely show the cross-sectional score's realized forward IC ≈ 0 after a few quarters —
and KNOWING that is the institutional win, not a loss. The book is also a survivor-only
OPTIMISTIC bound (free prices serve listed names); that caveat ships on every artifact.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from engine import validation as V

BOOK_PATH = "data/shadow/stock_score_book.jsonl"
HORIZONS = (21, 63, 126)


# --------------------------------------------------------------------------- #
# snapshot (append-only, frozen at build time)
# --------------------------------------------------------------------------- #
def snapshot(date, recs, *, horizons=HORIZONS, path: str = BOOK_PATH) -> int:
    """Append frozen score rows for `date`. `recs` = iterable of dicts carrying at least
    `ticker` and `score` (and optionally `percentile`, `regime`). Returns rows written.
    Idempotent per (date, ticker): re-running a build does not duplicate or overwrite."""
    d = str(pd.Timestamp(date).date())
    seen = _seen_keys(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with open(path, "a") as fh:
        for r in recs:
            t = r.get("ticker")
            if t is None or (d, t) in seen:
                continue
            row = {"date": d, "ticker": t,
                   "score": _num(r.get("score")), "percentile": _num(r.get("percentile")),
                   "regime": r.get("regime"), "horizons": list(horizons)}
            fh.write(json.dumps(row, default=str) + "\n")
            seen.add((d, t)); n += 1
    return n


def _seen_keys(path: str) -> set:
    out = set()
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                out.add((r.get("date"), r.get("ticker")))
            except Exception:
                continue
    return out


def _num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def load_book(path: str = BOOK_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=["date", "ticker", "score", "percentile", "regime", "horizons"])
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# mature (leak-free: only fully-elapsed horizons)
# --------------------------------------------------------------------------- #
def mature(asof, closes: pd.DataFrame, *, path: str = BOOK_PATH, horizons=HORIZONS) -> pd.DataFrame:
    """Join snapshot rows to realized forward returns for every horizon that has FULLY
    elapsed on or before `asof`. `closes` = wide price panel (DatetimeIndex x ticker).
    A (date, ticker, h) is matured ONLY if the h-th trading bar after `date` exists in
    `closes` and its date <= asof — so a not-yet-closed horizon is never graded."""
    book = load_book(path)
    if book.empty:
        return pd.DataFrame()
    asof = pd.Timestamp(asof)
    idx = closes.index
    out = []
    # cache date -> integer position
    pos_of = {d: i for i, d in enumerate(idx)}
    for _, r in book.iterrows():
        t = r["ticker"]
        if t not in closes.columns:
            continue
        d0 = pd.Timestamp(r["date"])
        # snapshot acts on the NEXT bar (decision frozen at close d0); find d0's position
        p0 = pos_of.get(d0)
        if p0 is None:                                  # snapshot date not a trading bar in panel
            after = idx[idx > d0]
            if len(after) == 0:
                continue
            p0 = pos_of[after[0]]
        base = closes.iloc[p0][t]
        if not np.isfinite(base) or base <= 0:
            continue
        for h in (r.get("horizons") or horizons):
            pe = p0 + int(h)
            if pe >= len(idx):                          # horizon hasn't generated enough bars yet
                continue
            d_end = idx[pe]
            if d_end > asof:                            # LEAK GUARD: horizon not fully elapsed
                continue
            px = closes.iloc[pe][t]
            if not np.isfinite(px):
                continue
            out.append({"date": r["date"], "ticker": t, "horizon": int(h),
                        "score": _num(r.get("score")), "percentile": _num(r.get("percentile")),
                        "fwd_ret": float(px / base - 1.0), "end_date": str(d_end.date())})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# grade (rolling forward rank-IC + HAC-t + Clark-West)
# --------------------------------------------------------------------------- #
# Minimum PRIOR evidence before the expanding score→return map may issue a Clark-West
# forecast: with fewer closed rows/dates than this the fitted slope is noise, not a model.
_CW_MIN_PRIOR_ROWS = 60
_CW_MIN_PRIOR_DATES = 3

# A HAC t is only publishable when the series can carry its overlap lag: the Bartlett
# long-run variance DEGENERATES as L→n (gamma_0 cancels exactly at L=n-1), so a lag-h
# correction on n≈h dates inflates t instead of correcting it (red-team 2026-08-26 on the
# real book: t 6.82 at L=21 on n=23 vs 4.04 at L=6; Monte-Carlo null size 0.63 vs 0.55 at
# the 5% bar). Below this many sample points per lag the t/p are suppressed, not printed —
# the request stays visible so the artifact says WHY there is no t yet.
_HAC_MIN_N_PER_LAG = 3


def grade(matured: pd.DataFrame, *, key: str = "score") -> dict:
    """Per-horizon realized forward audit of the frozen score: cross-sectional rank-IC per
    snapshot date → ic_summary (mean IC, IC-IR, HAC-t) + a pooled Clark-West/OOS-R2 of the
    score-implied forecast vs an expanding-mean benchmark. Empty until horizons mature.

    HAC lags: the book snapshots DAILY cross-sections while each horizon's forward window
    spans h trading bars, so consecutive per-date ICs overlap h deep — the truncation lag
    REQUESTED is h itself, never ic_summary's rebalance-cadence default (engine/validation.py
    documents that default as under-correcting exactly this shape). But a lag the series is
    too short to carry is worse than none (see _HAC_MIN_N_PER_LAG): until n >= 3h the t/p
    are suppressed with the reason stamped, and the pre-registration's §3 floor keeps the
    verdict at "building" regardless. periods_per_year is the count of INDEPENDENT h-bar
    windows in a year — annualization only, not the lag."""
    out = {"n_matured": int(len(matured)), "by_horizon": {}}
    if matured is None or matured.empty:
        return out
    for h, g in matured.groupby("horizon"):
        h = int(h)
        ics, ic_dates, dates = [], [], sorted(g["date"].unique())
        for d in dates:
            sub = g[g["date"] == d]
            if len(sub) >= 10:
                ic = V.rank_ic(sub[key], sub["fwd_ret"])
                if np.isfinite(ic):
                    ics.append(ic)
                    ic_dates.append(d)
        summ = V.ic_summary(ics, periods_per_year=max(1, round(252 / h)), hac_lags=h)
        summ = _suppress_degenerate_t(summ, n=len(ics), lag=h)
        out["by_horizon"][f"h{h}"] = {
            "ic": summ, "n_dates": len(ics), "n_obs": int(len(g)),
            # honest independent-observation count over the dates that actually produced
            # an IC: n_dates overlapping windows can be as few as 1-2 real episodes
            # (engine/china_validation._disjoint_windows)
            "n_indep_windows": _disjoint_windows(g[g["date"].isin(ic_dates)]),
            "span": [str(min(dates)), str(max(dates))] if dates else None,
            "verdict": _prereg_state(ic_dates),
            "clark_west": _clark_west_pooled(g, key=key, hac_lags=h),
        }
    return out


def _suppress_degenerate_t(summ: dict, *, n: int, lag: int) -> dict:
    """Null t_hac/p_hac when the IC series cannot carry its overlap lag (n < 3·lag).
    The effective/requested lag echo stays, so the artifact shows the ask AND the reason
    no t accompanies it — printing a degenerate t reads as a fully-corrected one."""
    if "t_hac" not in summ or n >= _HAC_MIN_N_PER_LAG * lag:
        return summ
    return {**summ, "t_hac": None, "p_hac": None,
            "t_suppressed": (f"n={n} cannot carry the lag-{lag} overlap correction "
                             f"(needs n>={_HAC_MIN_N_PER_LAG * lag}; Bartlett variance "
                             "degenerates as lag approaches n)")}


def _prereg_state(ic_dates: list) -> str:
    """§3 of research/SHADOW_BOOK_PREREGISTRATION.md (FROZEN): below 6 matured entry-date
    clusters AND ~2 calendar quarters of matured history the audit reads 'building' —
    never PASS/NULL/NEGATIVE. At the floor the §2 table is applied by an adjudicating
    session (HAC t + Clark-West + DSR deflation via the trial ledger), never auto-stamped
    here: overlapping daily dates still need a non-overlapping subsample or block
    bootstrap before the t is trusted at the longer horizons."""
    if len(ic_dates) < 6:
        return "building"
    span_days = (pd.Timestamp(max(ic_dates)) - pd.Timestamp(min(ic_dates))).days
    if span_days < 182:
        return "building"
    return ("sample_floor_met — apply §2 of research/SHADOW_BOOK_PREREGISTRATION.md "
            "(HAC t + Clark-West + DSR deflation; not auto-adjudicated)")


def _disjoint_windows(g: pd.DataFrame) -> int:
    """Greedy count of NON-overlapping [date, end_date] forward windows among the matured
    snapshot dates — what n_dates would have been had the book sampled at the horizon
    instead of daily. The honest episode count beside every overlapping-date t-stat.
    A window starting exactly at the previous end_date is return-disjoint (its forward
    return covers the NEXT h bars), so ties count. Greedy-by-start is optimal here
    because end_date = date + h bars is monotone in date."""
    if "end_date" not in g.columns:
        return 0
    spans = g.dropna(subset=["end_date"]).groupby("date")["end_date"].first()
    n, cur_end = 0, None
    for d, e in sorted(spans.items()):
        if cur_end is None or pd.Timestamp(d) >= cur_end:
            n += 1
            cur_end = pd.Timestamp(e)
    return n


def _clark_west_pooled(g: pd.DataFrame, *, key: str, hac_lags: int) -> dict:
    """Pooled Clark-West (2007) + OOS-R2 of the frozen score vs an expanding-mean
    benchmark for one horizon. Leak-free by construction: the forecast for snapshot date
    d maps score→return with an OLS line fitted ONLY on rows whose forward window had
    fully CLOSED before d (end_date < d) — the information actually available at d. The
    benchmark is those same prior rows' mean return, so the pair is nested (slope 0
    recovers the benchmark exactly, the structure Clark-West requires). Per-date means of
    the adjusted MSPE difference then take a Newey-West t at the same overlap lag as the
    IC series; cw_p is ONE-sided (H1: the score has genuine OOS content). Weighting note:
    cw_t equal-weights DATES while oos_r2 pools per OBSERVATION — with uneven cross-section
    sizes the two can disagree in sign near zero; the t is the test, oos_r2 the effect size.
    Both t and oos_r2 are suppressed while the eligible-date series is too short to carry
    the correction (same _HAC_MIN_N_PER_LAG rule as the IC series; oos_r2 needs >= 8)."""
    if "end_date" not in g.columns:
        return {"n_dates": 0, "note": "no end_date column — cannot form a leak-free prior"}
    rows = g.dropna(subset=[key, "fwd_ret"]).copy()
    if rows.empty:
        return {"n_dates": 0}
    rows["_d"] = pd.to_datetime(rows["date"])
    rows["_end"] = pd.to_datetime(rows["end_date"])
    fadj_by_date: list[float] = []
    sse_f = sse_b = 0.0
    n_obs = 0
    for d in sorted(rows["_d"].unique()):
        prior = rows[rows["_end"] < d]
        if len(prior) < _CW_MIN_PRIOR_ROWS or prior["_d"].nunique() < _CW_MIN_PRIOR_DATES:
            continue
        cur = rows[rows["_d"] == d]
        if len(cur) < 10:                               # same floor as rank_ic
            continue
        x = prior[key].to_numpy(float)
        y = prior["fwd_ret"].to_numpy(float)
        bench = float(y.mean())
        var = float(np.var(x))
        slope = float(np.cov(x, y, bias=True)[0, 1] / var) if var > 0 else 0.0
        intercept = bench - slope * float(x.mean())
        r = cur["fwd_ret"].to_numpy(float)
        f = intercept + slope * cur[key].to_numpy(float)
        fa = (r - bench) ** 2 - (r - f) ** 2 + (bench - f) ** 2
        fadj_by_date.append(float(fa.mean()))
        sse_f += float(np.sum((r - f) ** 2))
        sse_b += float(np.sum((r - bench) ** 2))
        n_obs += int(len(r))
    if not fadj_by_date:
        return {"n_dates": 0}
    nw = V.newey_west_tstat(fadj_by_date, lags=hac_lags)
    t = nw.get("t")
    p1 = (nw["p"] / 2.0 if (t is not None and t > 0)
          else (1.0 - nw["p"] / 2.0 if t is not None else None))
    res = {"cw_t": t, "cw_p": round(p1, 4) if p1 is not None else None,
           "mean_adj": nw.get("mean"), "n_dates": len(fadj_by_date), "n_obs": n_obs,
           # a 2-date pooled R2 is noise wearing a number — same floor as newey_west's n>=8
           "oos_r2": (round(1.0 - sse_f / sse_b, 5)
                      if (sse_b > 0 and len(fadj_by_date) >= 8) else None),
           "hac_lags": nw.get("lags"), "hac_lags_requested": int(hac_lags),
           "benchmark": "expanding mean of prior fully-closed forward returns"}
    return _suppress_cw_t(res, n=len(fadj_by_date), lag=hac_lags)


def _suppress_cw_t(res: dict, *, n: int, lag: int) -> dict:
    """Same degeneracy rule as the IC series, applied to the CW date series."""
    if res.get("cw_t") is None or n >= _HAC_MIN_N_PER_LAG * lag:
        return res
    return {**res, "cw_t": None, "cw_p": None,
            "t_suppressed": (f"n={n} cannot carry the lag-{lag} overlap correction "
                             f"(needs n>={_HAC_MIN_N_PER_LAG * lag}; Bartlett variance "
                             "degenerates as lag approaches n)")}
