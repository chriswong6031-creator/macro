"""Cross-root positioning screener — which names sit at a positioning extreme today.

Program of record: charting-app ``docs/VOLLAND_PARITY_PLAN_2026-08-01.md`` §5 (W3).

What this is, and where it differs from theirs
----------------------------------------------
Volland's "Quad Screener" scatters tickers on two axes — a direction measure and a
volatility measure — each normalised to ±1 within the current cross-section. That answers
"which name is most extreme **compared to the other names on screen right now**".

That framing has a defect worth naming: cross-sectional normalisation makes SPY and a
mid-cap biotech comparable by construction, when the honest answer is that a $6bn gamma
book and a $60mn one are not the same object scaled. Rank a quiet day for SPY against a
loud day for the biotech and the biotech wins on a measure that means nothing.

We rank each root against **its own recent history** instead — its trailing year, per
:data:`PCTILE_WINDOW_DAYS`. "NVDA gamma at its 3rd percentile" is a claim about NVDA;
"NVDA is the most negative on screen" is a claim about the screen.

Both axes therefore run 0–100 and are directly comparable across roots without any
normalisation step at all — which is also why this needs no cross-sectional rescaling and
cannot be distorted by which roots happen to be included.

The window matters as much as the self-comparison: see :data:`PCTILE_WINDOW_DAYS` for the
measured reason a nine-year rank would have shipped a trend dressed up as a signal.

Honesty
-------
Tier B (masterplan §4.1): the underlying exposures inherit the dealer-sign convention.
The percentile framing is the sturdier half — see `engine/agg_trend` — and the payload
carries `n_days` per root so a thin history is visible rather than implied.
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["SCHEMA", "MIN_HISTORY_DAYS", "PCTILE_WINDOW_DAYS", "build_quad", "quadrant"]

SCHEMA = "options_hub.quad/v1"

#: Sessions of history a root needs before its percentile is published.
#:
#: A percentile over 40 sessions is a number, not a distribution — the 5th percentile of
#: two months is one bad week. 250 is a year, enough for a rank to survive a regime.
MIN_HISTORY_DAYS = 250

#: Sessions the percentile is computed over. **Not** the full history, and the reason is
#: a measured defect rather than a preference.
#:
#: Dealer exposure scales with the underlying: gamma with S², vanna and charm with S. SPY
#: went from 225 to 741 between 2017 and 2026, and its yearly MEDIAN vanna climbed with
#: it — 3.54bn in 2017 to 5.07bn in 2026, with 2024/2025/2026 the three highest years on
#: record. Ranking today against nine years of that therefore measures how much the index
#: has GROWN, not how extreme positioning is: the first build of this board put 20 of 23
#: roots above the 85th vanna percentile, which is not a finding, it is a trend.
#:
#: A trailing year is also what a desk means by "at an extreme" — extreme relative to the
#: current regime, not to a market that traded at a third of today's level. The full
#: series stays available in the per-root trend card, where the drift is visible on the
#: chart and the reader can judge it directly.
PCTILE_WINDOW_DAYS = 252

#: Percentile beyond which a root is called out as extreme, either side.
EXTREME_PCT = 10.0


def quadrant(gamma_pctile: float, vol_pctile: float) -> str:
    """Name the corner a root sits in.

    The two axes are deliberately NOT direction and volatility in the price sense; they
    are *dealer gamma* (does hedging dampen or amplify a move) and *dealer vanna* (does a
    vol move force hedging). The four corners are the four hedging regimes:

    ``amplify_volsens``  low gamma, high vanna — the fragile corner: dealers chase price
                         AND are forced to trade on a vol move
    ``amplify_stable``   low gamma, low vanna  — dealers chase price, vol is not the lever
    ``dampen_volsens``   high gamma, high vanna — pinned on price, exposed on vol
    ``dampen_stable``    high gamma, low vanna — the quiet corner
    """
    hi_g = gamma_pctile >= 50.0
    hi_v = vol_pctile >= 50.0
    if hi_g and hi_v:
        return "dampen_volsens"
    if hi_g:
        return "dampen_stable"
    if hi_v:
        return "amplify_volsens"
    return "amplify_stable"


def _pct_of_last(values: np.ndarray, window: int = PCTILE_WINDOW_DAYS) -> float | None:
    """Percentile of the latest reading within the trailing `window` sessions.

    See :data:`PCTILE_WINDOW_DAYS` for why this is a window and not the full series.
    """
    if values.size == 0 or not np.isfinite(values[-1]):
        return None
    win = values[-window:] if window and values.size > window else values
    v = win[np.isfinite(win)]
    if v.size < 2:
        return None
    return float((v < values[-1]).mean() * 100.0)


def build_quad(frames: dict[str, "object"], asof: str) -> dict:
    """Assemble the cross-root board from per-root aggregate frames.

    Parameters
    ----------
    frames : dict[str, pandas.DataFrame]
        root → the frame `engine.agg_trend.daily_aggregates` produces (or its cached
        parquet). Roots with fewer than :data:`MIN_HISTORY_DAYS` sessions are dropped
        and counted in ``skipped``, never published with a thin percentile.
    asof : str
        Session the board describes.

    Returns
    -------
    dict
        ``options_hub.quad/v1``. Rows carry both the percentile (the axis) and the raw
        $bn figure (so a reader can see the size behind the rank), plus ``n_days``.
    """
    rows: list[dict] = []
    skipped: list[str] = []

    for root, df in sorted(frames.items()):
        if df is None or getattr(df, "empty", True):
            skipped.append(root)
            continue
        n = int(len(df))
        if n < MIN_HISTORY_DAYS:
            skipped.append(root)
            continue

        d = df.sort_values("date")
        g_pct = _pct_of_last(d["gamma"].to_numpy(float)) if "gamma" in d.columns else None
        v_pct = _pct_of_last(d["vanna"].to_numpy(float)) if "vanna" in d.columns else None
        if g_pct is None or v_pct is None:
            skipped.append(root)
            continue

        last = d.iloc[-1]

        def _last(col: str, scale: float = 1.0) -> float | None:
            if col not in d.columns:
                return None
            val = last[col]
            return round(float(val) / scale, 4) if np.isfinite(val) else None

        rows.append({
            "root": root,
            "gamma_pctile": round(g_pct, 1),
            "vanna_pctile": round(v_pct, 1),
            "quadrant": quadrant(g_pct, v_pct),
            "gamma_bn": _last("gamma", 1e9),
            "vanna_bn": _last("vanna", 1e9),
            "spot": _last("spot"),
            "atm_iv": _last("atm_iv"),
            "n_days": n,
            "pctile_n": min(n, PCTILE_WINDOW_DAYS),
            "since": str(d["date"].iloc[0]),
            # ⚠️ The row's OWN last session, not the board's. The board is rebuilt from
            # every cached root, so a root whose cache stopped updating (its build
            # failed, or it was simply not in this run's --roots) contributes
            # coordinates from an old session. Without this the reader sees month-old
            # positioning — and a month-old `spot` — under a current-dated header.
            "asof": str(d["date"].iloc[-1]),
            # Extremes are what the board is FOR — surfacing them as a flag saves the
            # reader from eyeballing a scatter to find the two names that matter.
            "extreme": bool(
                g_pct <= EXTREME_PCT or g_pct >= 100 - EXTREME_PCT
                or v_pct <= EXTREME_PCT or v_pct >= 100 - EXTREME_PCT
            ),
        })

    if skipped:
        log.info("quad: %d roots skipped for thin history (<%d sessions): %s",
                 len(skipped), MIN_HISTORY_DAYS, ", ".join(sorted(skipped)[:12]))

    return {
        "schema": SCHEMA,
        "asof": asof,
        "min_history_days": MIN_HISTORY_DAYS,
        "pctile_window_days": PCTILE_WINDOW_DAYS,
        "extreme_pct": EXTREME_PCT,
        # Rows whose own last session trails the board. Named, not merely derivable:
        # a consumer that forgets to compare per-row asof would show them as current.
        "n_stale": sum(1 for r in rows if r.get("asof") and r["asof"] < asof),
        "n_roots": len(rows),
        "n_skipped": len(skipped),
        "skipped": sorted(skipped),
        "rows": rows,
    }
