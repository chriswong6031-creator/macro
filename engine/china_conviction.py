"""Unified conviction scale + bilingual word-bands — one source of truth across surfaces.

LEAF · PURE · no I/O · never raises. News importance, alt-data convergence, radar
conviction and the hub all map their raw read onto ONE bounded 0-100 scale and the SAME
bilingual word-bands, so a "High" on one surface means the same thing on another. A
word-band is what the user surfaces show — never a bare number. context-only / salience,
never a position size. See research/CHINA_INTEL_POWERHOUSE.md §1.4.
"""
from __future__ import annotations

SCHEMA = "china_conviction.v1"

# (floor, key, en, zh) — first band whose floor <= score wins (descending)
_BANDS = [
    (75, "high", "High", "高置信"),
    (55, "elevated", "Elevated", "偏强"),
    (35, "moderate", "Moderate", "中性"),
    (1, "low", "Low", "偏弱"),
    (0, "none", "None", "无"),
]


def to_100(x: float | None, lo: float = 0.0, hi: float = 1.0) -> int:
    """Clamp x to [lo,hi] and linearly map to 0..100. None -> 0."""
    if x is None:
        return 0
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0
    if hi <= lo:
        return 0
    frac = (x - lo) / (hi - lo)
    return int(round(max(0.0, min(1.0, frac)) * 100))


def band(s100: int | float | None) -> tuple[str, str, str]:
    """(key, en, zh) word-band for a 0..100 score."""
    s = 0 if s100 is None else int(s100)
    for floor, key, en, zh in _BANDS:
        if s >= floor:
            return key, en, zh
    return "none", "None", "无"


def signed_band(s100: int | float | None, direction: int) -> tuple[str, str, str]:
    """Word-band with a +/- side prepended from `direction` (>0 long-context, <0 short-context)."""
    key, en, zh = band(s100)
    if not direction or key == "none":
        return key, en, zh
    if direction > 0:
        return f"+{key}", f"{en} +", f"{zh} ↑"
    return f"-{key}", f"{en} −", f"{zh} ↓"


def combine(*parts: float | None, weights: list[float] | None = None) -> float:
    """Weighted geometric-leaning mean of parts in [0,1] — rewards ALL legs agreeing
    (one strong leg + two zeros stays low). Missing/None parts are skipped. 0.0 if none."""
    vals, ws = [], []
    for i, p in enumerate(parts):
        if p is None:
            continue
        v = max(0.0, min(1.0, float(p)))
        w = (weights[i] if weights and i < len(weights) else 1.0)
        vals.append(v)
        ws.append(w)
    if not vals:
        return 0.0
    tw = sum(ws) or 1.0
    # geometric-leaning: exp(weighted mean of log(v+eps)) - eps  (penalizes any near-zero leg)
    import math
    eps = 1e-3
    lg = sum(w * math.log(v + eps) for v, w in zip(vals, ws)) / tw
    return round(max(0.0, min(1.0, math.exp(lg) - eps)), 4)
