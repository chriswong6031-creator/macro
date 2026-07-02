"""Market-aware self-grader for the per-name POTENTIAL score — the piece that makes the
buy-readiness score EARN trust per market instead of asserting it.

  • append_name_calls(calls, market, asof) — append today's per-name POTENTIAL calls
    (ticker, score, tier, fuel, trigger + the as-of close `level`) to an append-only,
    point-in-time store, keep-FIRST per (date, ticker) so a stamped score is never
    overwritten / leaked. CN keeps its legacy path (data/china_name_score/calls.parquet);
    every other market is data/name_score/<market>_calls.parquet.
  • grade(market) — for every matured call, join the name's forward return (the market's
    close store) and score: buy-tier (primed/setting_up) hit-rate, cross-sectional rank-IC
    (score vs forward return), per-tier forward, by horizon. "accruing" until enough.

Until a market's scorecard shows a positive, stable rank-IC, that market's score is framed
as an EXPERIMENTAL timing/edge screen, never a validated probability — mirroring the honesty
gates in [[stock-conviction-profile]] and [[china-name-potential-score]].
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import grading  # W1c: shared next-bar/survivorship-aware grader
from lib import config, store

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63)                    # ~1 / 3 months
_BUY_TIERS = ("primed", "setting_up")    # the tiers the user would actually act on
# per-market per-name close store group
_FWD_GROUP = {"US": "stocks", "CN": "china", "HK": "hk", "CA": "canada", "INTL": "intl"}


def _store_path(market: str):
    m = (market or "CN").upper()
    d = config.data_dir()
    if m == "CN":                       # legacy path — preserves the existing CN ledger
        return d / "china_name_score" / "calls.parquet"
    return d / "name_score" / f"{m.lower()}_calls.parquet"


def append_name_calls(calls: list[dict], market: str = "CN", asof: str | None = None) -> int:
    """Append today's POTENTIAL calls for one market. Each call carries {ticker, score,
    tier, fuel, trigger} plus an as-of `level` (the day's close). Keep-FIRST per
    (date, ticker). Returns the ledger row count after the merge."""
    if not calls or not asof:
        return 0
    rows = []
    for c in calls:
        tk = c.get("ticker")
        if not tk:
            continue
        rows.append({"date": str(asof), "ticker": str(tk), "score": c.get("score"),
                     "tier": c.get("tier"), "fuel": c.get("fuel"),
                     "trigger": c.get("trigger"), "level": c.get("level")})
    if not rows:
        return 0
    try:
        new = pd.DataFrame(rows)
        p = _store_path(market)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("name-score grader (%s): append failed: %s", market, e)
        return 0


def _fwd_return(market: str, ticker: str, d0: pd.Timestamp, h: int) -> float | None:
    """Forward return of a call, NEXT-BAR filled + survivorship-aware (W1c, audit #15).

    Pre-W1c this did ``s.iloc[h] / s.iloc[0]`` — a SAME-BAR fill (the score's own as-of
    close is the denominator) and it silently dropped a name that delisted (``store.read``
    returns None → survivorship in the accountability loop). Now it routes through
    engine.grading: the call fires on d0's close but is FILLED on the next bar, the forward
    return is measured to h bars past that fill, and a delisted name is extended by its
    dead-name terminal close (US only for now — the dead-name store is US-side) so its loss
    is graded instead of vanishing."""
    try:
        df = store.read(_FWD_GROUP.get((market or "CN").upper(), "china"), str(ticker))
        s = pd.to_numeric(df["close"], errors="coerce").dropna() if (
            df is not None and "close" in df) else None
    except Exception:  # noqa: BLE001
        s = None
    # US has the 8-K bankruptcy dead-name store; other markets have none → resolve_series
    # simply returns the live series unchanged there.
    if (market or "").upper() == "US":
        try:
            s = grading.resolve_series(str(ticker), s)
        except Exception:  # noqa: BLE001
            pass
    if s is None or s.empty:
        return None
    s = s.sort_index()
    # Snap to the call bar (nearest bar <= d0), fill next bar, measure h bars past the fill.
    # NOTE: this credits the call to the score's OWN as-of bar even if the price series
    # begins after d0-slicing would; grading._snap_loc handles the nearest-prior mapping.
    return grading.grade_next_bar_return(s, str(pd.Timestamp(d0).date()), h)


def grade(market: str = "CN") -> dict | None:
    """Score every matured call for one market. {available, n_calls, n_graded, dates,
    by_horizon} where each horizon carries the buy-tier hit-rate, the cross-sectional
    rank-IC, and a per-tier forward breakdown."""
    m = (market or "CN").upper()
    p = _store_path(m)
    if not p.exists():
        return {"available": False, "market": m, "note": "no calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "market": m, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "market": m, "note": "empty"}

    out = {"available": True, "market": m, "n_calls": int(len(df)),
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D), "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        for _i, row in df.iterrows():
            fr = _fwd_return(m, row["ticker"], pd.Timestamp(row["date"]), h)
            if fr is None:
                continue
            recs.append({"date": row["date"], "ticker": row["ticker"],
                         "score": row.get("score"), "tier": row.get("tier"), "fwd": fr})
        if len(recs) < 5:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        ics = []
        for _d, sub in g.groupby("date"):
            if sub["score"].nunique() >= 5:
                ics.append(float(sub["score"].rank().corr(sub["fwd"].rank())))
        buys = g[g["tier"].isin(_BUY_TIERS)]
        hit = float((buys["fwd"] > 0).mean()) if len(buys) else None
        by_tier = {}
        for lab, sub in g.groupby("tier"):
            if len(sub) >= 5:
                by_tier[lab] = {"n": int(len(sub)),
                                "mean_fwd": round(float(sub["fwd"].mean()), 4),
                                "pos_rate": round(float((sub["fwd"] > 0).mean()), 3)}
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)),
            "buy_tier_hit_rate": round(hit, 3) if hit is not None else None,
            "rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "by_tier": by_tier,
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out
