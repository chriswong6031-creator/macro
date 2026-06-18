"""Rotation realized-check — close the loop on the policy capital-rotation map.

The Fed & Policy Watch rotation map ASSERTS which themes policy is steering capital
toward. This leaf grades that assertion against the tape: for each targeted theme it
computes the realized relative performance of its proxy tickers vs SPY over a trailing
window, and returns a coincident verdict (working / mixed / lagging / n-a).

DISCIPLINE: this is a COINCIDENT, descriptive read — "did the policy-favored theme
actually outperform recently?" — NOT a forecast and NEVER scored. It is the honest
falsifier for the rotation thesis: a TARGETED theme that persistently LAGS is evidence
against the call. Display / context only.
"""
from __future__ import annotations

import logging
from datetime import date

from engine import ai_desk as _desk          # reuse _close_series (yahoo close loader)

log = logging.getLogger(__name__)

_BENCH = "SPY"
# subject/proxy name -> the actual cached price ticker (GLD has no local series; GC_F does)
_ALIAS = {"GLD": "GC_F"}
_WORKING = 0.02        # +2% vs SPY over the window = "working"
_LAGGING = -0.02       # -2% vs SPY = "lagging"


def _rel(ticker: str, root, window: int, loader) -> float | None:
    """Trailing `window`-trading-day return of `ticker` minus SPY's, or None if either
    series is missing / too short."""
    tk = _ALIAS.get(ticker.upper(), ticker.upper())
    s = loader(tk, root)
    b = loader(_BENCH, root)
    if s is None or b is None or len(s) <= window or len(b) <= window:
        return None
    try:
        sr = float(s.iloc[-1]) / float(s.iloc[-window - 1]) - 1.0
        br = float(b.iloc[-1]) / float(b.iloc[-window - 1]) - 1.0
        return round(sr - br, 4)
    except Exception:  # noqa: BLE001
        return None


def _verdict(avg: float | None) -> str:
    if avg is None:
        return "na"
    if avg >= _WORKING:
        return "working"
    if avg <= _LAGGING:
        return "lagging"
    return "mixed"


def check(intel: dict, root=None, window: int = 63, loader=None) -> dict:
    """Grade every TARGETED rotation theme's proxies vs SPY over `window` trading days.
    Returns {window, as_of, themes: {theme_en: {avg_rel, verdict, n, proxies:[{ticker,rel}]}}}.
    `loader(ticker, root)` is injectable for tests (defaults to ai_desk._close_series)."""
    from lib import config
    root = root or config.ROOT
    loader = loader or _desk._close_series
    out: dict[str, dict] = {}
    targeted = ((intel or {}).get("rotation") or {}).get("targeted") or []
    for r in targeted:
        theme = r.get("theme_en")
        if not theme:
            continue
        rows = []
        for px in (r.get("proxies") or []):
            rel = _rel(px, root, window, loader)
            if rel is not None:
                rows.append({"ticker": px.upper(), "rel": rel})
        avg = round(sum(x["rel"] for x in rows) / len(rows), 4) if rows else None
        out[theme] = {"avg_rel": avg, "verdict": _verdict(avg), "n": len(rows), "proxies": rows}
    return {"window": window, "as_of": str(date.today()), "themes": out}
