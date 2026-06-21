"""Expansion gate (engine v2, anticipation tier) — the "tailwind to expand" filter
that is the REAL dead-cat-bounce discriminator (research/ANTICIPATION_ENGINE_DESIGN.md).

A bottom-formation signal alone cannot tell a durable low from a dead-cat bounce — the
external evidence (and our own calibration) says the bigger discriminator is CONTEXT:
is this a relative-strength LEADER whose primary trend is intact (a pullback in an
uptrend that institutions are defending), or a broken laggard in a downtrend (where
bounces fail)? Only the former has a credible reason to EXPAND after it bottoms.

So the anticipation ladder forwards a PRIMED name to the top of the watchlist ONLY when
this gate is positive. Point-in-time / causal: relative strength vs a benchmark + the
200-day primary-trend health, all from close (≤ as_of). Live builds additionally fold in
thematic acceleration (basketdata/flow.json stage/accel) and sector RS; those are not
available in the point-in-time calibration harness, so this core uses the price-derivable
leadership read and the live caller may pass an extra `theme_accel` tailwind.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_NEUTRAL = {"score": 0.5, "ok": False, "leader": False, "rs_rank": None, "above_200d": None}


def assess(close: pd.Series, bench: pd.Series | None, *,
           theme_accel: float | None = None, threshold: float = 0.55) -> dict:
    """Expansion read for one name. Returns {score 0-1, ok, leader, rs_rank, above_200d}.
    `ok` gates the PRIMED tier. `theme_accel` (optional, live only) in [-1,1] nudges the
    score for an accelerating/cooling theme; absent => price-leadership only."""
    c = close.dropna()
    if len(c) < 210 or bench is None or len(bench) == 0:
        return dict(_NEUTRAL)
    b = bench.reindex(c.index).ffill()
    rs = (c / b).replace([np.inf, -np.inf], np.nan).dropna()
    if len(rs) < 210:
        return dict(_NEUTRAL)

    # relative-strength leadership: where current RS sits in its 1y range (1 = strongest)
    rs_rank = float((rs.iloc[-252:] <= rs.iloc[-1]).mean())
    # RS momentum: the RS line is above its own ~60-day average (improving vs the market)
    rs_up = float(rs.iloc[-1] > rs.iloc[-60:].mean())
    # primary trend: above a rising 200-day average = a pullback in an uptrend, not a fall
    ma200 = c.rolling(200).mean()
    above200 = float(c.iloc[-1] > ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else 0.0
    ma200_up = float(ma200.iloc[-1] > ma200.iloc[-21]) if pd.notna(ma200.iloc[-21]) else 0.0

    score = 0.38 * rs_rank + 0.18 * rs_up + 0.26 * above200 + 0.18 * ma200_up
    if theme_accel is not None and np.isfinite(theme_accel):
        score = 0.85 * score + 0.15 * (0.5 + 0.5 * float(np.clip(theme_accel, -1, 1)))
    score = float(np.clip(score, 0.0, 1.0))
    return {"score": round(score, 2), "ok": bool(score >= threshold),
            "leader": bool(rs_rank >= 0.6 and above200), "rs_rank": round(rs_rank, 2),
            "above_200d": bool(above200)}
