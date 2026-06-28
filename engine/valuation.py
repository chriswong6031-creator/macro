"""Forward-aware valuation read (engine v2) — a NON-VETO haircut + caveat.

The old conviction score had NO valuation-multiple awareness: it penalized PRICE
extension (distance above the 200-day) but never MULTIPLE extension. The naive fix —
penalize the trailing value factor — would FALSE-VETO a growth leader: NVDA trades at
a rich trailing P/S (~24x, value_z -1.05) but a CHEAP forward P/E (~16x). Penalizing
its trailing multiple is exactly the mistake that buried NVDA.

So this module keys on FORWARD valuation where available (the mega-caps, where the
false-veto risk is highest) and is deliberately light-touch on trailing-only names.
It returns a SUBTRACT-ONLY haircut to the quality axis (never a bonus, never a hard
block) plus a band + a 'valuation_watch' flag the verdict surfaces as an 'expensive'
caveat. A leader stays a leader; the score just stops pretending an extreme multiple
is free, and the card says so.
"""
from __future__ import annotations


# forward-P/E bands (broad-market, growth-neutral). Cheap/fair never haircut; the
# haircut ramps in only past 'fair' and is capped small so it can never veto a leader.
_FWD_CHEAP, _FWD_FAIR, _FWD_EXTREME = 18.0, 28.0, 40.0
_HAIRCUT_STRETCHED_MAX = 0.20      # z shaved at the top of the 'stretched' band
_HAIRCUT_EXTREME = 0.40            # z shaved in the 'extreme' band (still non-veto)
_QUALITY_WATCH_CAP = 0.3           # expensive names can't post a top quality axis


def _ramp(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _num(x):
    return x if isinstance(x, (int, float)) and x == x else None


def read(rec: dict) -> dict | None:
    """Valuation read for one name, or None when no usable multiple is present.

    Returns {band, haircut_z (<=0), watch, note, note_zh, forward_pe, basis}.
    """
    v = rec.get("valuation") or {}
    fwd = _num(v.get("forward_pe"))
    band = note = note_zh = basis = None
    haircut = 0.0
    watch = False

    if fwd is not None and fwd > 0:
        basis = "forward_pe"
        if fwd < _FWD_CHEAP:
            band = "cheap"
        elif fwd < _FWD_FAIR:
            band = "fair"
        elif fwd < _FWD_EXTREME:
            band = "stretched"
            haircut = -_HAIRCUT_STRETCHED_MAX * _ramp(fwd, _FWD_FAIR, _FWD_EXTREME)
        else:
            band = "extreme"
            haircut = -_HAIRCUT_EXTREME
            watch = True
        note = f"forward P/E {fwd:.0f}×"
        note_zh = f"前瞻市盈率 {fwd:.0f} 倍"
    else:
        # No forward P/E (most non-mega-caps). Use the trailing percentile blend
        # ('cheap' = 0-100, higher = cheaper). Light touch ONLY — trailing multiples
        # over-penalize growth, so we flag/haircut just the genuinely extreme tail.
        cheaps = [_num((m or {}).get("cheap")) for m in
                  (v.get("earnings_yield"), v.get("trailing_pe"), v.get("price_to_sales"))]
        cheaps = [c for c in cheaps if c is not None]
        if not cheaps:
            return None
        basis = "trailing_pctile"
        avg = sum(cheaps) / len(cheaps)
        if avg >= 55:
            band = "cheap"
        elif avg >= 30:
            band = "fair"
        elif avg >= 12:
            band = "stretched"
            haircut = -0.12
        else:
            band = "extreme"
            haircut = -0.25
            watch = True
        note = f"valuation rank {avg:.0f}/100 (higher = cheaper)"
        note_zh = f"估值分位 {avg:.0f}/100（越高越便宜）"

    return {"band": band, "haircut_z": round(haircut, 3), "watch": watch,
            "note": note, "note_zh": note_zh, "forward_pe": fwd, "basis": basis}


def apply_haircut(q_z: float | None, val: dict | None) -> float | None:
    """Apply the subtract-only valuation haircut to a quality-axis z (and cap an
    'extreme' name's quality so a rich multiple can't post a top score). Never
    raises the z; returns the input unchanged when there is no read."""
    if q_z is None or not val:
        return q_z
    z = q_z + (val.get("haircut_z") or 0.0)        # haircut_z <= 0
    if val.get("watch"):
        z = min(z, _QUALITY_WATCH_CAP)
    return z
