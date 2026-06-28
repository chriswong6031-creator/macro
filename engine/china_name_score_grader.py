"""Self-grader for the China per-name POTENTIAL score — the piece that makes the
buy-readiness score EARN trust instead of asserting it (the honesty mechanism the
A-share reality demands: name selection has no proven alpha, so the score must
measure itself forward, not claim conviction).

  • append_name_calls(calls, asof) — append today's per-name POTENTIAL calls
    (ticker, score, tier, fuel, trigger + the as-of close `level`) to an append-only,
    point-in-time store (data/china_name_score/calls.parquet), keep-FIRST per
    (date, ticker) so a past day's stamped score is never overwritten / leaked.
  • grade() — for every matured call, join the name's forward return (china close)
    and the Shanghai-Composite benchmark, then score: buy-tier (primed/setting_up)
    hit-rate + beat-the-index rate, cross-sectional rank-IC (score vs forward
    return), and per-tier forward / excess, by horizon. "accruing" until enough
    matured calls exist.

Until the scorecard shows a positive, stable rank-IC, the score is framed as an
EXPERIMENTAL timing screen, never a validated probability — mirroring the honesty
gates in [[stock-conviction-profile]] and engine/china_sector_central_grader.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63)                    # ~1 / 3 months — reversal is short-horizon
_STORE = ("china_name_score", "calls.parquet")
_BUY_TIERS = ("primed", "setting_up")    # the tiers the user would actually act on


def append_name_calls(calls: list[dict], asof: str | None = None) -> int:
    """Append today's POTENTIAL calls. Each call carries {ticker, score, tier, fuel,
    trigger} plus an as-of `level` (the day's close) so forward returns are leak-free.
    Keep-FIRST per (date, ticker). Returns the ledger row count after the merge."""
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
        p = config.data_dir() / _STORE[0] / _STORE[1]
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
        log.warning("name-score grader: append failed: %s", e)
        return 0


def _fwd_return(ticker: str, d0: pd.Timestamp, h: int) -> float | None:
    """Realized return from the call date to call_date + h trading days, or None if
    the horizon hasn't elapsed / the series is missing."""
    try:
        df = store.read("china", str(ticker))
        if df is None or "close" not in df:
            return None
        s = pd.to_numeric(df["close"], errors="coerce").dropna()
        s = s[s.index >= d0]
        if len(s) <= h:
            return None
        return float(s.iloc[h] / s.iloc[0] - 1.0)
    except Exception:  # noqa: BLE001
        return None


def grade() -> dict | None:
    """Score every matured call. Returns {available, n_calls, n_graded, dates,
    by_horizon} where each horizon carries the buy-tier hit / beat rates, the
    cross-sectional rank-IC, and a per-tier forward/excess breakdown."""
    p = config.data_dir() / _STORE[0] / _STORE[1]
    if not p.exists():
        return {"available": False, "note": "no calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "note": "empty"}

    bench = None
    try:
        from engine import china_sector_index as csi
        bench = csi.benchmark_close()
    except Exception:  # noqa: BLE001
        pass

    out = {"available": True, "n_calls": int(len(df)),
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D), "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        for _i, row in df.iterrows():
            d0 = pd.Timestamp(row["date"])
            fr = _fwd_return(row["ticker"], d0, h)
            if fr is None:
                continue
            br = None
            if bench is not None:
                bb = bench[bench.index >= d0]
                if len(bb) > h:
                    br = float(bb.iloc[h] / bb.iloc[0] - 1.0)
            recs.append({"date": row["date"], "ticker": row["ticker"],
                         "score": row.get("score"), "tier": row.get("tier"),
                         "fwd": fr, "excess": (fr - br) if br is not None else None})
        if len(recs) < 5:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        # cross-sectional rank-IC per date (score vs forward return), averaged
        ics = []
        for _d, sub in g.groupby("date"):
            if sub["score"].nunique() >= 5:
                ics.append(float(sub["score"].rank().corr(sub["fwd"].rank())))
        # buy-tier (primed/setting_up) outcomes — did the names we flagged actually rise / beat?
        buys = g[g["tier"].isin(_BUY_TIERS)]
        hit = float((buys["fwd"] > 0).mean()) if len(buys) else None
        beat = (float((buys["excess"] > 0).mean())
                if len(buys) and buys["excess"].notna().any() else None)
        by_tier = {}
        for lab, sub in g.groupby("tier"):
            if len(sub) >= 5:
                by_tier[lab] = {"n": int(len(sub)),
                                "mean_fwd": round(float(sub["fwd"].mean()), 4),
                                "mean_excess": (round(float(sub["excess"].dropna().mean()), 4)
                                                if sub["excess"].notna().any() else None),
                                "pos_rate": round(float((sub["fwd"] > 0).mean()), 3)}
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)),
            "buy_tier_hit_rate": round(hit, 3) if hit is not None else None,
            "buy_tier_beat_rate": round(beat, 3) if beat is not None else None,
            "rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "by_tier": by_tier,
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out
