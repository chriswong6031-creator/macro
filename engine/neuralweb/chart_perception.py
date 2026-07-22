"""Chart perception — deterministic structural digests for the Chart Mastermind (CMX W2).

The *Eyes* of the Brain. Pure, deterministic geometry over daily bars: swing pivots,
trend segments, support/resistance clusters, trendline candidates, unfilled gaps, an
ATR/volatility context, and a weekly multi-timeframe snapshot. Plus ``measure_line`` —
the server-side pre-draw fit checker the agent must consult before asserting a trendline.

House law bindings (masterplan §3 + §7):
  * READ-ONLY. Bars come from ``engine.marketing.chart_render.load_ohlcv`` (reads a parquet,
    never writes). This module performs NO filesystem writes and NO ``data/`` persistence —
    the MM_DATA_GUARD "reader-that-writes" class is a known lethal, so nothing here heals,
    caches to disk, or mutates state.
  * ANTI-DISTILLATION. Output dicts carry structure (levels, states, fit metrics) and
    *plain-word* labels only. No formula, threshold, ATR-multiple, lookback, or any other
    internal parameter value ever appears in an emitted text field. The LLM interprets;
    it never sees how the digest was computed.
  * NEVER RAISES to the tool loop. Bad symbol / missing data / degenerate series all return
    a compact ``{"symbol", "tf", "available": False, ...}`` shape — the caller gets a null,
    never an exception.

Entry points:
  * ``chart_digest(symbol, tf, sections=None) -> dict``
  * ``measure_line(symbol, tf, p1, p2) -> dict``

Everything else is a private helper. Numbers in the OUTPUT (prices, touch counts, deviations)
are results, not parameters — those are allowed; the banned thing is naming an internal knob.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

# ── Internal tuning knobs (NEVER surface any of these values in output text) ─────────────
# These are the "how" of perception. They are deliberately module-private and must never be
# echoed into a label, note, or verdict string (anti-distillation; test-enforced).
_ATR_PERIOD = 14                 # Wilder ATR lookback
_ZIGZAG_ATR_MULT = 1.5           # pivot reversal threshold, in ATRs
_LEVEL_CLUSTER_ATR = 0.6         # pivot prices within this many ATRs merge into one level
_TOUCH_BAND_ATR = 0.5            # a bar "touches" a line/level within this ATR band
_TREND_FLAT_ATR_PER_BAR = 0.02   # |slope| below this (ATR/bar) reads as "flat"
_PCTL_LOOKBACK = 252             # ~1 trading year for the ATR percentile band
_DIGEST_BARS = 420               # daily history pulled for a 1D digest (>1y for the percentile)
_WEEKLY_SOURCE_BARS = 900        # daily history resampled down to weekly (~3.5y of weeks)
_MAX_TRENDLINES = 5              # top-N trendline candidates returned
_FRESH_RECENT_FRAC = 0.15        # last-touch within this tail fraction reads "fresh"
_FRESH_STALE_FRAC = 0.60         # last-touch older than this reads "stale"

_VALID_TFS = ("1D", "1W")


# ─────────────────────────────────────────────────────────────────────────────
# Bar loading (read-only) + light numeric helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_daily(symbol: str, root: Path, n: int) -> dict | None:
    """Load the last *n* daily bars via the shared read-only loader.

    Returns ``{"t":[...], "o":[...], "h":[...], "l":[...], "c":[...], "v":[...]}`` with
    integer epoch-second timestamps, or ``None`` when bars are unavailable. Wrapped so a
    missing pandas/pyarrow dep degrades to ``None`` at call time (mirrors ``_chart_for_chat``).
    """
    try:
        from engine.marketing.chart_render import load_ohlcv  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — absent deps → no data, never crash
        return None
    try:
        bars = load_ohlcv(symbol, root, n=n)
    except Exception:  # noqa: BLE001
        return None
    if not bars:
        return None
    dates, o, h, l, c, v = bars
    if not dates or len(dates) < 3:
        return None
    return {
        "t": [_date_to_epoch(d) for d in dates],
        "o": list(o),
        "h": list(h),
        "l": list(l),
        "c": list(c),
        "v": list(v),
    }


def _date_to_epoch(d: str) -> int:
    """'YYYY-MM-DD' → UTC-midnight epoch seconds. Falls back to 0 on any parse trouble."""
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        return int(datetime.strptime(str(d)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except Exception:  # noqa: BLE001
        return 0


def _true_ranges(h: list[float], l: list[float], c: list[float]) -> list[float]:
    """Per-bar true range; first bar uses high-low (no prior close)."""
    tr: list[float] = []
    for i in range(len(h)):
        if i == 0:
            tr.append(max(0.0, h[i] - l[i]))
        else:
            pc = c[i - 1]
            tr.append(max(h[i] - l[i], abs(h[i] - pc), abs(l[i] - pc)))
    return tr


def _atr_series(h: list[float], l: list[float], c: list[float], period: int = _ATR_PERIOD) -> list[float | None]:
    """Wilder ATR aligned to input length (None until the first full window)."""
    tr = _true_ranges(h, l, c)
    out: list[float | None] = [None] * len(tr)
    if len(tr) < period:
        return out
    seed = sum(tr[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(tr)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def _last_atr(atr: list[float | None]) -> float | None:
    """Most recent non-None ATR value."""
    for v in reversed(atr):
        if v is not None and v > 0:
            return v
    return None


def _percentile_rank(values: list[float], x: float) -> float:
    """Fraction of *values* ≤ *x*, in [0, 1]. Empty → 0.5 (neutral)."""
    if not values:
        return 0.5
    below = sum(1 for v in values if v <= x)
    return below / len(values)


def _round_price(p: float) -> float:
    """Round a price for output: 4 sig-ish decimals for small, 2 for large."""
    if p == 0:
        return 0.0
    ap = abs(p)
    if ap >= 100:
        return round(p, 2)
    if ap >= 1:
        return round(p, 3)
    return round(p, 5)


# ─────────────────────────────────────────────────────────────────────────────
# Swing pivots — ZigZag with an ATR-scaled reversal threshold
# ─────────────────────────────────────────────────────────────────────────────

def _swing_pivots(t: list[int], h: list[float], l: list[float], c: list[float],
                  atr: list[float | None]) -> list[dict]:
    """ATR-scaled ZigZag pivots.

    A reversal is confirmed when price retraces from the running extreme by at least
    ``_ZIGZAG_ATR_MULT`` ATRs. Each pivot = ``{"t", "p", "kind": "high"|"low", "i"}``
    (``i`` = bar index, kept internally for downstream geometry; stripped from digest levels).
    """
    n = len(c)
    if n < 3:
        return []
    base_atr = _last_atr(atr) or (sum(h[i] - l[i] for i in range(n)) / max(1, n))
    if base_atr <= 0:
        base_atr = max(1e-9, (max(h) - min(l)) / max(1, n))
    thresh = base_atr * _ZIGZAG_ATR_MULT

    pivots: list[dict] = []
    # Seed direction by the first meaningful move from bar 0.
    ext_i = 0
    ext_hi = h[0]
    ext_lo = l[0]
    direction = 0  # +1 = seeking a high, -1 = seeking a low, 0 = undecided

    for i in range(1, n):
        if direction >= 0 and h[i] > ext_hi:
            ext_hi = h[i]
            if direction == 0:
                ext_i = i
        if direction <= 0 and l[i] < ext_lo:
            ext_lo = l[i]
            if direction == 0:
                ext_i = i

        if direction == 0:
            # Decide initial direction once price has moved a threshold either way.
            if ext_hi - l[i] >= thresh and h[i] <= ext_hi:
                direction = 1
                ext_i = _argmax(h, 0, i)
                ext_hi = h[ext_i]
            elif h[i] - ext_lo >= thresh and l[i] >= ext_lo:
                direction = -1
                ext_i = _argmin(l, 0, i)
                ext_lo = l[ext_i]
            continue

        if direction == 1:
            if h[i] >= ext_hi:
                ext_hi, ext_i = h[i], i
            elif ext_hi - l[i] >= thresh:
                pivots.append({"t": t[ext_i], "p": ext_hi, "kind": "high", "i": ext_i})
                direction = -1
                ext_lo, ext_i = l[i], i
        elif direction == -1:
            if l[i] <= ext_lo:
                ext_lo, ext_i = l[i], i
            elif h[i] - ext_lo >= thresh:
                pivots.append({"t": t[ext_i], "p": ext_lo, "kind": "low", "i": ext_i})
                direction = 1
                ext_hi, ext_i = h[i], i

    # Close out the final running extreme as a provisional pivot so the latest leg is visible.
    if direction == 1:
        pivots.append({"t": t[ext_i], "p": ext_hi, "kind": "high", "i": ext_i})
    elif direction == -1:
        pivots.append({"t": t[ext_i], "p": ext_lo, "kind": "low", "i": ext_i})

    return _dedupe_pivots(pivots)


def _argmax(seq: list[float], lo: int, hi: int) -> int:
    best_i, best_v = lo, seq[lo]
    for i in range(lo, hi + 1):
        if seq[i] > best_v:
            best_i, best_v = i, seq[i]
    return best_i


def _argmin(seq: list[float], lo: int, hi: int) -> int:
    best_i, best_v = lo, seq[lo]
    for i in range(lo, hi + 1):
        if seq[i] < best_v:
            best_i, best_v = i, seq[i]
    return best_i


def _dedupe_pivots(pivots: list[dict]) -> list[dict]:
    """Drop consecutive same-kind pivots keeping the more extreme, and drop zero-width dups."""
    out: list[dict] = []
    for pv in pivots:
        if out and out[-1]["kind"] == pv["kind"]:
            # Same kind twice in a row — keep the more extreme one.
            if pv["kind"] == "high":
                if pv["p"] >= out[-1]["p"]:
                    out[-1] = pv
            else:
                if pv["p"] <= out[-1]["p"]:
                    out[-1] = pv
            continue
        if out and out[-1]["i"] == pv["i"]:
            continue
        out.append(pv)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Trend segments — runs between consecutive pivots
# ─────────────────────────────────────────────────────────────────────────────

def _trend_segments(pivots: list[dict], atr_now: float) -> list[dict]:
    """One segment per consecutive pivot pair: direction + plain-word slope class."""
    segs: list[dict] = []
    for a, b in zip(pivots, pivots[1:]):
        di = b["i"] - a["i"]
        if di <= 0:
            continue
        slope = (b["p"] - a["p"]) / di  # price per bar
        segs.append({
            "from_t": a["t"],
            "to_t": b["t"],
            "from_p": _round_price(a["p"]),
            "to_p": _round_price(b["p"]),
            "direction": _slope_word(slope, atr_now),
            "bars": di,
        })
    return segs


def _slope_word(slope_per_bar: float, atr_now: float) -> str:
    """Plain-word slope class. Uses ATR-normalized magnitude internally; emits words only."""
    if atr_now <= 0:
        return "flat"
    norm = slope_per_bar / atr_now
    if norm > _TREND_FLAT_ATR_PER_BAR:
        return "rising"
    if norm < -_TREND_FLAT_ATR_PER_BAR:
        return "falling"
    return "flat"


# ─────────────────────────────────────────────────────────────────────────────
# Support / resistance level clusters
# ─────────────────────────────────────────────────────────────────────────────

def _level_clusters(pivots: list[dict], t: list[int], atr_now: float, n_bars: int) -> list[dict]:
    """Cluster pivot prices (ATR-scaled tolerance) into S/R levels.

    Each level = ``{price, touches, last_touch_t, side, freshness}`` with plain-word
    ``side`` (support|resistance|both) and ``freshness`` (fresh|recent|stale).
    """
    if not pivots or atr_now <= 0:
        return []
    tol = atr_now * _LEVEL_CLUSTER_ATR
    # Sort by price, then greedily merge neighbors within tolerance.
    pts = sorted(pivots, key=lambda pv: pv["p"])
    clusters: list[list[dict]] = []
    cur: list[dict] = [pts[0]]
    for pv in pts[1:]:
        anchor = sum(p["p"] for p in cur) / len(cur)
        if abs(pv["p"] - anchor) <= tol:
            cur.append(pv)
        else:
            clusters.append(cur)
            cur = [pv]
    clusters.append(cur)

    last_t = t[-1] if t else 0
    span = max(1, n_bars)
    levels: list[dict] = []
    for cl in clusters:
        price = sum(p["p"] for p in cl) / len(cl)
        touches = len(cl)
        last_touch_i = max(p["i"] for p in cl)
        last_touch_t = max(p["t"] for p in cl)
        kinds = {p["kind"] for p in cl}
        if kinds == {"high"}:
            side = "resistance"
        elif kinds == {"low"}:
            side = "support"
        else:
            side = "both"
        # Freshness from how recent the newest touch is, as a fraction of the window.
        age_frac = (span - 1 - last_touch_i) / span
        if age_frac <= _FRESH_RECENT_FRAC:
            freshness = "fresh"
        elif age_frac >= _FRESH_STALE_FRAC:
            freshness = "stale"
        else:
            freshness = "recent"
        levels.append({
            "price": _round_price(price),
            "touches": touches,
            "last_touch_t": last_touch_t,
            "side": side,
            "freshness": freshness,
        })
    # Strongest first: more touches, then fresher.
    _fresh_rank = {"fresh": 0, "recent": 1, "stale": 2}
    levels.sort(key=lambda lv: (-lv["touches"], _fresh_rank.get(lv["freshness"], 3)))
    return levels


# ─────────────────────────────────────────────────────────────────────────────
# Trendline candidates — pivot-pair fits ranked by touches / deviation
# ─────────────────────────────────────────────────────────────────────────────

def _line_at(p1: dict, p2: dict, idx: int) -> float | None:
    """Value of the line through (p1.i, p1.p)-(p2.i, p2.p) at bar index *idx*."""
    di = p2["i"] - p1["i"]
    if di == 0:
        return None
    slope = (p2["p"] - p1["p"]) / di
    return p1["p"] + slope * (idx - p1["i"])


def _line_fit(p1: dict, p2: dict, h: list[float], l: list[float], c: list[float],
              atr_now: float) -> dict:
    """Touch count + max *penetration* (in ATRs) for the line through two pivots.

    A bar "touches" when its high/low straddles the line within ``_TOUCH_BAND_ATR`` ATRs.

    ``max_dev_atr`` is the worst VIOLATION of the line — how far price closed through it on
    the wrong side — NOT the natural swing away from it. A support line is violated when a
    close prints below it; a resistance line when a close prints above it. The line's side is
    inferred from where closes predominantly sit over the span. This is what makes the verdict
    meaningful: a well-respected line (price returns to it, rarely closes through it) reads
    small even when price legitimately travels far on the correct side between touches.
    """
    if atr_now <= 0:
        return {"touches": 0, "max_dev_atr": 0.0}
    band = atr_now * _TOUCH_BAND_ATR
    lo_i, hi_i = min(p1["i"], p2["i"]), max(p1["i"], p2["i"])
    touches = 0
    above = 0
    below = 0
    for i in range(lo_i, hi_i + 1):
        y = _line_at(p1, p2, i)
        if y is None:
            continue
        if (l[i] - band) <= y <= (h[i] + band):
            touches += 1
        if c[i] > y:
            above += 1
        elif c[i] < y:
            below += 1
    # Side: support if closes mostly sit above the line, resistance if mostly below.
    is_support = above >= below
    max_pen = 0.0
    for i in range(lo_i, hi_i + 1):
        y = _line_at(p1, p2, i)
        if y is None:
            continue
        if is_support:
            pen = max(0.0, y - l[i])   # how far the low dipped BELOW support
        else:
            pen = max(0.0, h[i] - y)   # how far the high poked ABOVE resistance
        # A within-band poke is a touch, not a violation — discount the band.
        pen = max(0.0, pen - band)
        if pen > max_pen:
            max_pen = pen
    return {"touches": touches, "max_dev_atr": round(max_pen / atr_now, 3)}


def _trendline_candidates(pivots: list[dict], h: list[float], l: list[float], c: list[float],
                          atr_now: float) -> list[dict]:
    """Top-N trendline candidates from same-kind pivot pairs, ranked by touches then tightness."""
    if len(pivots) < 2 or atr_now <= 0:
        return []
    lows = [pv for pv in pivots if pv["kind"] == "low"]
    highs = [pv for pv in pivots if pv["kind"] == "high"]
    cands: list[dict] = []
    for group in (lows, highs):
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                p1, p2 = group[a], group[b]
                if p2["i"] == p1["i"]:
                    continue
                fit = _line_fit(p1, p2, h, l, c, atr_now)
                if fit["touches"] < 2:
                    continue
                cands.append({
                    "p1": {"t": p1["t"], "p": _round_price(p1["p"])},
                    "p2": {"t": p2["t"], "p": _round_price(p2["p"])},
                    "kind": "support" if p1["kind"] == "low" else "resistance",
                    "touches": fit["touches"],
                    "max_dev_atr": fit["max_dev_atr"],
                })
    # Rank: more touches first, then smaller max deviation.
    cands.sort(key=lambda d: (-d["touches"], d["max_dev_atr"]))
    return cands[:_MAX_TRENDLINES]


# ─────────────────────────────────────────────────────────────────────────────
# Unfilled gaps
# ─────────────────────────────────────────────────────────────────────────────

def _unfilled_gaps(t: list[int], h: list[float], l: list[float], c: list[float]) -> list[dict]:
    """Bar-to-bar gaps not yet filled by later price action.

    Up gap: today's low > yesterday's high (a hole below). Down gap: today's high <
    yesterday's low. Unfilled iff no *subsequent* bar's range re-enters the gap band.
    Each = ``{t, top, bottom, direction}`` (direction: up|down).
    """
    gaps: list[dict] = []
    n = len(c)
    for i in range(1, n):
        if l[i] > h[i - 1]:
            bottom, top, direction = h[i - 1], l[i], "up"
        elif h[i] < l[i - 1]:
            bottom, top, direction = h[i], l[i - 1], "down"
        else:
            continue
        # Filled if a later bar trades STRICTLY inside the open (bottom, top) band — a bar
        # merely touching an edge (l[j] == top or h[j] == bottom) does not fill the gap.
        filled = False
        for j in range(i + 1, n):
            if l[j] < top and h[j] > bottom:
                filled = True
                break
        if not filled:
            gaps.append({
                "t": t[i],
                "top": _round_price(top),
                "bottom": _round_price(bottom),
                "direction": direction,
            })
    return gaps


# ─────────────────────────────────────────────────────────────────────────────
# Volatility / distance context
# ─────────────────────────────────────────────────────────────────────────────

def _atr_word(pct: float) -> str:
    """Plain-word volatility state from the ATR's 1y percentile rank."""
    if pct <= 0.33:
        return "quiet"
    if pct >= 0.66:
        return "elevated"
    return "normal"


def _context(t: list[int], h: list[float], l: list[float], c: list[float],
             atr: list[float | None], levels: list[dict]) -> dict:
    """ATR state (vs 1y band), last close, and distance to nearest support/resistance."""
    last_close = c[-1]
    atr_now = _last_atr(atr)
    atr_vals = [v for v in atr if v is not None]
    tail = atr_vals[-_PCTL_LOOKBACK:] if atr_vals else []
    pct = _percentile_rank(tail, atr_now) if (atr_now and tail) else 0.5
    state = _atr_word(pct) if atr_now else "unknown"

    nearest_support = None
    nearest_resistance = None
    for lv in levels:
        price = lv["price"]
        if price <= last_close and lv["side"] in ("support", "both"):
            if nearest_support is None or price > nearest_support["price"]:
                nearest_support = lv
        if price >= last_close and lv["side"] in ("resistance", "both"):
            if nearest_resistance is None or price < nearest_resistance["price"]:
                nearest_resistance = lv

    def _dist(lv: dict | None) -> dict | None:
        if lv is None or atr_now in (None, 0):
            return None
        return {
            "price": lv["price"],
            "atr_away": round(abs(last_close - lv["price"]) / atr_now, 2),
        }

    return {
        "last_close": _round_price(last_close),
        "volatility": state,
        "nearest_support": _dist(nearest_support),
        "nearest_resistance": _dist(nearest_resistance),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Weekly resample
# ─────────────────────────────────────────────────────────────────────────────

def _iso_week_key(epoch: int) -> tuple[int, int]:
    """(ISO year, ISO week) for grouping daily bars into weeks."""
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        d = datetime.fromtimestamp(epoch, tz=timezone.utc).isocalendar()
        return (d[0], d[1])
    except Exception:  # noqa: BLE001
        return (0, 0)


def _resample_weekly(bars: dict) -> dict | None:
    """Daily OHLCV → weekly OHLCV (ISO-week buckets). None if fewer than a few weeks."""
    t, o, h, l, c, v = bars["t"], bars["o"], bars["h"], bars["l"], bars["c"], bars["v"]
    if not t:
        return None
    weeks: dict[tuple[int, int], dict] = {}
    order: list[tuple[int, int]] = []
    for i in range(len(t)):
        key = _iso_week_key(t[i])
        if key not in weeks:
            weeks[key] = {"t": t[i], "o": o[i], "h": h[i], "l": l[i], "c": c[i], "v": v[i]}
            order.append(key)
        else:
            w = weeks[key]
            w["h"] = max(w["h"], h[i])
            w["l"] = min(w["l"], l[i])
            w["c"] = c[i]
            w["v"] += v[i]
    if len(order) < 3:
        return None
    out = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for key in order:
        w = weeks[key]
        out["t"].append(w["t"])
        out["o"].append(w["o"])
        out["h"].append(w["h"])
        out["l"].append(w["l"])
        out["c"].append(w["c"])
        out["v"].append(w["v"])
    return out


def _weekly_snapshot(symbol: str, root: Path) -> dict | None:
    """Compact weekly structure: swings + top levels + trend, resampled from daily."""
    daily = _load_daily(symbol, root, _WEEKLY_SOURCE_BARS)
    if not daily:
        return None
    weekly = _resample_weekly(daily)
    if not weekly:
        return None
    return _skeleton(weekly, want_trendlines=False, want_gaps=False, compact=True)


# ─────────────────────────────────────────────────────────────────────────────
# Skeleton assembly (shared by 1D full digest and 1W compact snapshot)
# ─────────────────────────────────────────────────────────────────────────────

def _skeleton(bars: dict, *, want_trendlines: bool, want_gaps: bool, compact: bool) -> dict:
    """Assemble the structural skeleton from a bar dict. Pure; never raises."""
    t, o, h, l, c = bars["t"], bars["o"], bars["h"], bars["l"], bars["c"]
    n = len(c)
    atr = _atr_series(h, l, c)
    atr_now = _last_atr(atr) or 0.0
    pivots = _swing_pivots(t, h, l, c, atr)

    # Pivots for output: strip the internal bar index.
    out_pivots = [{"t": pv["t"], "p": _round_price(pv["p"]), "kind": pv["kind"]} for pv in pivots]
    levels = _level_clusters(pivots, t, atr_now, n)
    segments = _trend_segments(pivots, atr_now)
    ctx = _context(t, h, l, c, atr, levels)

    skel: dict[str, Any] = {
        "bars": n,
        "swings": out_pivots if not compact else out_pivots[-8:],
        "levels": levels if not compact else levels[:5],
        "trend": segments if not compact else segments[-3:],
        "context": ctx,
    }
    if want_trendlines:
        skel["trendlines"] = _trendline_candidates(pivots, h, l, c, atr_now)
    if want_gaps:
        skel["gaps"] = _unfilled_gaps(t, h, l, c)
    return skel


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

# Digest sections a caller may request; unknown names are ignored.
_SECTIONS = ("swings", "trend", "levels", "trendlines", "gaps", "context", "weekly")


def _clean_symbol(symbol: str) -> str:
    """Local symbol sanitizer (mirrors the gateway's ``_safe_symbol`` without importing it).

    Uppercase; keep alphanumerics + dot/dash; collapse repeated dots (path-traversal guard);
    strip edge dots; cap length. Kept independent so this module has no gateway dependency.
    """
    import re  # noqa: PLC0415
    clean = re.sub(r"[^A-Z0-9.\-]", "", (symbol or "").upper())
    clean = re.sub(r"\.{2,}", ".", clean)
    return clean.strip(".")[:10]


def chart_digest(symbol: str, tf: str = "1D", sections: list | None = None,
                 root: Path | str | None = None) -> dict:
    """Deterministic structural digest of *symbol* on timeframe *tf* (``"1D"`` or ``"1W"``).

    Returns a compact typed dict with plain-word labels — swing pivots, trend segments,
    S/R level clusters, trendline candidates, unfilled gaps, a volatility/distance context,
    and (for 1D) a weekly snapshot. ``sections`` filters the top-level keys returned
    (unknown names ignored; ``None`` = all applicable). Never raises: bad symbol or missing
    data yields ``{"available": False, ...}``.
    """
    sym = _clean_symbol(symbol)
    tf_norm = (tf or "1D").upper().replace(" ", "")
    if tf_norm not in _VALID_TFS:
        tf_norm = "1D"
    base_root = Path(root) if root is not None else _default_root()

    if not sym:
        return {"symbol": "", "tf": tf_norm, "available": False, "reason": "no symbol"}

    if tf_norm == "1W":
        weekly = _weekly_snapshot(sym, base_root)
        if not weekly:
            return {"symbol": sym, "tf": tf_norm, "available": False, "reason": "no data"}
        digest = {"symbol": sym, "tf": tf_norm, "available": True, **weekly}
        return _select_sections(digest, sections)

    daily = _load_daily(sym, base_root, _DIGEST_BARS)
    if not daily:
        return {"symbol": sym, "tf": tf_norm, "available": False, "reason": "no data"}

    skel = _skeleton(daily, want_trendlines=True, want_gaps=True, compact=False)
    digest: dict[str, Any] = {"symbol": sym, "tf": tf_norm, "available": True, **skel}
    # Weekly context rides along on the 1D digest for cheap multi-TF grounding.
    weekly = _weekly_snapshot(sym, base_root)
    if weekly:
        digest["weekly"] = {
            "swings": weekly.get("swings", []),
            "levels": weekly.get("levels", []),
            "trend": weekly.get("trend", []),
            "context": weekly.get("context", {}),
        }
    return _select_sections(digest, sections)


def _select_sections(digest: dict, sections: list | None) -> dict:
    """Keep only requested top-level sections; always retain the header + availability keys."""
    if not sections:
        return digest
    keep = {s for s in sections if s in _SECTIONS}
    if not keep:
        return digest
    header = {"symbol", "tf", "available", "reason", "bars"}
    return {k: v for k, v in digest.items() if k in header or k in keep}


def measure_line(symbol: str, tf: str, p1: dict, p2: dict,
                 root: Path | str | None = None) -> dict:
    """Server-side pre-draw fit checker for a trendline through two points.

    ``p1``/``p2`` = ``{"t": <epoch>, "p": <price>}``. Uses the SAME touch definition as the
    digest's trendline candidates. Returns ``{touches, max_dev_atr, verdict}`` where verdict
    is ``"holds"`` (well-supported), ``"weak"`` (few touches / loose), or ``"invalid"``
    (unusable input or no data). Never raises.
    """
    sym = _clean_symbol(symbol)
    tf_norm = (tf or "1D").upper().replace(" ", "")
    if tf_norm not in _VALID_TFS:
        tf_norm = "1D"
    base_root = Path(root) if root is not None else _default_root()

    t1, pr1 = _point(p1)
    t2, pr2 = _point(p2)
    if not sym or t1 is None or t2 is None or pr1 is None or pr2 is None:
        return {"symbol": sym, "tf": tf_norm, "touches": 0, "max_dev_atr": 0.0,
                "verdict": "invalid", "reason": "bad points"}
    if t1 == t2 or not (pr1 > 0 and pr2 > 0):
        return {"symbol": sym, "tf": tf_norm, "touches": 0, "max_dev_atr": 0.0,
                "verdict": "invalid", "reason": "degenerate line"}

    if tf_norm == "1W":
        daily = _load_daily(sym, base_root, _WEEKLY_SOURCE_BARS)
        bars = _resample_weekly(daily) if daily else None
    else:
        bars = _load_daily(sym, base_root, _DIGEST_BARS)
    if not bars:
        return {"symbol": sym, "tf": tf_norm, "touches": 0, "max_dev_atr": 0.0,
                "verdict": "invalid", "reason": "no data"}

    t, h, l, c = bars["t"], bars["h"], bars["l"], bars["c"]
    atr_now = _last_atr(_atr_series(h, l, c)) or 0.0
    if atr_now <= 0:
        return {"symbol": sym, "tf": tf_norm, "touches": 0, "max_dev_atr": 0.0,
                "verdict": "invalid", "reason": "no volatility scale"}

    i1 = _nearest_index(t, t1)
    i2 = _nearest_index(t, t2)
    if i1 == i2:
        return {"symbol": sym, "tf": tf_norm, "touches": 0, "max_dev_atr": 0.0,
                "verdict": "invalid", "reason": "points map to one bar"}

    fit = _line_fit({"i": i1, "p": pr1}, {"i": i2, "p": pr2}, h, l, c, atr_now)
    verdict = _line_verdict(fit["touches"], fit["max_dev_atr"])
    return {
        "symbol": sym,
        "tf": tf_norm,
        "touches": fit["touches"],
        "max_dev_atr": fit["max_dev_atr"],
        "verdict": verdict,
    }


def _line_verdict(touches: int, max_dev_atr: float) -> str:
    """Plain-word verdict from fit metrics. Thresholds live here, never in output text."""
    if touches >= 3 and max_dev_atr <= _TOUCH_BAND_ATR:
        return "holds"
    if touches >= 2 and max_dev_atr <= (_TOUCH_BAND_ATR * 2):
        return "weak"
    return "invalid"


def _point(p: Any) -> tuple[int | None, float | None]:
    """Extract (epoch_t, price) from a point dict; (None, None) on bad shape."""
    if not isinstance(p, dict):
        return None, None
    t = p.get("t")
    pr = p.get("p")
    try:
        ti = int(t)
    except Exception:  # noqa: BLE001
        return None, None
    try:
        pf = float(pr)
    except Exception:  # noqa: BLE001
        return None, None
    if not math.isfinite(pf):
        return None, None
    return ti, pf


def _nearest_index(t: list[int], target: int) -> int:
    """Index of the bar whose timestamp is closest to *target*."""
    best_i, best_d = 0, abs(t[0] - target)
    for i in range(1, len(t)):
        d = abs(t[i] - target)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _default_root() -> Path:
    """Repo root: three parents up from this file (engine/neuralweb/chart_perception.py)."""
    return Path(__file__).resolve().parents[2]
