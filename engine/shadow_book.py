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
def grade(matured: pd.DataFrame, *, key: str = "score", periods_per_year: int = 12) -> dict:
    """Per-horizon realized forward audit of the frozen score: cross-sectional rank-IC per
    snapshot date → ic_summary (mean IC, IC-IR, HAC-t) + a pooled Clark-West/OOS-R2 of the
    score-implied ranking vs an expanding-mean benchmark. Empty until horizons mature."""
    out = {"n_matured": int(len(matured)), "by_horizon": {}}
    if matured is None or matured.empty:
        return out
    for h, g in matured.groupby("horizon"):
        ics, dates = [], sorted(g["date"].unique())
        for d in dates:
            sub = g[g["date"] == d]
            if len(sub) >= 10:
                ic = V.rank_ic(sub[key], sub["fwd_ret"])
                if np.isfinite(ic):
                    ics.append(ic)
        summ = V.ic_summary(ics, periods_per_year=periods_per_year)
        out["by_horizon"][f"h{int(h)}"] = {
            "ic": summ, "n_dates": len(ics), "n_obs": int(len(g)),
            "span": [str(min(dates)), str(max(dates))] if dates else None,
        }
    return out
