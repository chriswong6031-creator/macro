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


# --------------------------------------------------------------------------- #
# forward-accruing history — grade the rotation thesis over time (accountability)
# --------------------------------------------------------------------------- #
def _hist_path(root):
    from pathlib import Path
    return Path(root) / "data" / "policy" / "rotation_history.jsonl"


def append_history(result: dict, root=None) -> bool:
    """Append today's per-theme verdicts to data/policy/rotation_history.jsonl.
    Idempotent per as_of date. Returns True if a row was written. Never raises."""
    try:
        from lib import config
        import json
        root = root or config.ROOT
        p = _hist_path(root)
        asof = (result or {}).get("as_of")
        themes = (result or {}).get("themes") or {}
        if not asof or not themes:
            return False
        rows = []
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        if any(r.get("date") == asof for r in rows):
            return False
        rows.append({"date": asof,
                     "verdicts": {t: v.get("verdict") for t, v in themes.items()},
                     "avg_rels": {t: v.get("avg_rel") for t, v in themes.items()}})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("rotation history append failed: %s", e)
        return False


def history_summary(root=None, lookback: int = 20) -> dict:
    """Per-theme trailing hit-rate over the last `lookback` reads: how often a TARGETED
    theme actually printed 'working'. {theme: {reads, working, working_rate}}. Never raises."""
    try:
        from lib import config
        import json
        root = root or config.ROOT
        p = _hist_path(root)
        if not p.exists():
            return {}
        rows = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        rows = sorted(rows, key=lambda r: r.get("date") or "")[-lookback:]
        out: dict[str, dict] = {}
        for r in rows:
            for theme, verdict in (r.get("verdicts") or {}).items():
                if verdict in (None, "na"):
                    continue
                d = out.setdefault(theme, {"reads": 0, "working": 0})
                d["reads"] += 1
                if verdict == "working":
                    d["working"] += 1
        for theme, d in out.items():
            d["working_rate"] = round(d["working"] / d["reads"], 2) if d["reads"] else None
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("rotation history summary failed: %s", e)
        return {}
