"""Server-side layer for the /stocks/ market hub.

Pure functions — no I/O, no network, no clock. `scripts/build_ticker_pages.py`
hands in the per-ticker rows it already assembled for the index grid plus the
committed S&P heatmap payload, and gets back everything the template renders:
the breadth read, "the day's shape" curve, the mover boards, the sector ledger,
the treemap geometry and the compact client search index.

Two scopes live on this page and they are labelled, never blended:

* **Coverage scope** — every US name we publish a dossier for (~1,544). Owns the
  headline, the breadth stats, the spine, the mover boards, search and the A-Z
  directory. This is the honest denominator for "of the names we cover".
* **S&P 500 scope** — the committed `marketdata/sp500_heatmap.json`. Owns the
  sector ledger and the treemap, because those need trustworthy market-cap
  weights and that payload is where real caps live.

The advancing/declining dead-band is imported from `engine.market_heatmap` rather
than redeclared, so the breadth number under the headline and the crossing point
of the spine can never drift apart from the heatmap's own arithmetic.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from engine.market_heatmap import _ADV_BAND

__all__ = [
    "breadth", "day_shape", "boards", "theme_ribbons", "sector_ledger",
    "treemap", "search_index", "directory", "squarify",
]

# ── "the day's shape" geometry ──────────────────────────────────────────────
SPINE_W = 1200.0
SPINE_H = 128.0
_MID = SPINE_H / 2.0

# ── treemap geometry ────────────────────────────────────────────────────────
HM_W = 1200.0
HM_H = 520.0
_SEC_HEAD = 16.0            # px reserved for the sector caption strip


def _f(v: Any) -> float | None:
    """Best-effort float. Returns None rather than raising on junk."""
    try:
        if v is None:
            return None
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _median(vals: Sequence[float]) -> float | None:
    v = sorted(x for x in vals if x is not None)
    n = len(v)
    if not n:
        return None
    mid = n // 2
    return v[mid] if n % 2 else (v[mid - 1] + v[mid]) / 2.0


# ═══════════════════════════════════════════════════════════════════════════
# Breadth
# ═══════════════════════════════════════════════════════════════════════════
def breadth(returns: Sequence[float]) -> dict | None:
    """Advancing / declining / flat over the coverage universe.

    Uses `market_heatmap._ADV_BAND` so a name that moved 0.02% counts as flat
    here exactly as it does on the heatmap pages.
    """
    rets = [r for r in (_f(x) for x in returns) if r is not None]
    n = len(rets)
    if not n:
        return None
    adv = sum(1 for r in rets if r > _ADV_BAND)
    dec = sum(1 for r in rets if r < -_ADV_BAND)
    flat = n - adv - dec
    med = _median(rets)
    tot = max(1, n)
    return {
        "n": n, "adv": adv, "dec": dec, "flat": flat,
        "pct_up": round(100.0 * adv / tot),
        "adv_w": round(100.0 * adv / tot, 2),
        "flat_w": round(100.0 * flat / tot, 2),
        "dec_w": round(100.0 * dec / tot, 2),
        "median": med,
        "median_pc": f"{med:+.2f}%" if med is not None else None,
        "median_tone": "up" if (med or 0) > 0 else ("down" if (med or 0) < 0 else ""),
    }


def stance(pct_up: float, med: float | None) -> dict[str, str]:
    """Plain-word read of the tape — breadth arithmetic only.

    Deliberately descriptive, never directional advice: this panel reports what
    the tape did, it does not tell anyone what to do about it (no stance the
    engine did not compute). Thresholds mirror `market_heatmap._stance` minus its
    sector-leadership branch, which needs cap weights this scope does not carry.
    """
    m = med or 0.0
    if pct_up >= 60 and m > 0.2:
        return {"tone": "up", "en": "Broad advance", "zh": "普涨"}
    if pct_up <= 40 and m < -0.2:
        return {"tone": "down", "en": "Broad decline", "zh": "普跌"}
    if pct_up >= 54:
        return {"tone": "up", "en": "Firmer tape", "zh": "偏强"}
    if pct_up <= 46:
        return {"tone": "down", "en": "Softer tape", "zh": "偏弱"}
    return {"tone": "flat", "en": "Split tape", "zh": "涨跌分化"}


# ═══════════════════════════════════════════════════════════════════════════
# The signature — every covered name as one curve
# ═══════════════════════════════════════════════════════════════════════════
def day_shape(returns: Sequence[float], pct_up: int | None = None) -> dict | None:
    """Every covered name ranked worst -> best, as one filled curve.

    The zero crossing IS the breadth number and the tail steepness IS how violent
    the outliers were, so the whole coverage universe reads as a single glyph
    with no name selected in or out.

    `pct_up` is passed in rather than recomputed: the label under the curve must
    quote the same number as the stat strip beside it, and a locally recomputed
    "% green" using `>= 0` instead of the dead-band would print two answers to
    one question.
    """
    vals = sorted(r for r in (_f(x) for x in returns) if r is not None)
    n = len(vals)
    if n < 8:
        return None

    # Scale to the 97th percentile of |move| so one halted 40% name cannot
    # flatten the other 1,500 into a straight line; beyond that the curve
    # compresses logarithmically and the tail labels name the true extremes.
    mags = sorted(abs(v) for v in vals)
    scale = max(mags[min(n - 1, int(0.97 * n))] or 1.0, 0.8)

    def xy(i: int, v: float) -> tuple[float, float]:
        u = v / scale
        a = abs(u)
        if a > 1.0:
            a = 1.0 + math.log1p(a - 1.0) * 0.5
        u = math.copysign(min(a, 1.55), u) / 1.55
        return (i / (n - 1)) * SPINE_W, _MID - u * (_MID - 3)

    pts = [xy(i, v) for i, v in enumerate(vals)]
    cross = next((i for i, v in enumerate(vals) if v > _ADV_BAND), n)

    def seg(lo: int, hi: int) -> str:
        sub = pts[lo:hi]
        if len(sub) < 2:
            return ""
        return (f"M {sub[0][0]:.2f} {_MID:.2f} "
                + " ".join(f"L {x:.2f} {y:.2f}" for x, y in sub)
                + f" L {sub[-1][0]:.2f} {_MID:.2f} Z")

    return {
        "neg": seg(0, cross + 1),
        "pos": seg(max(0, cross - 1), n),
        "line": "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts),
        "cross_x": round((cross / (n - 1)) * SPINE_W, 1),
        "pct_up": pct_up,
        "w": SPINE_W, "h": SPINE_H, "mid": _MID,
        "n": n,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Mover boards
# ═══════════════════════════════════════════════════════════════════════════
def _bar_w(v: float, mx: float) -> int:
    return int(round(max(4.0, min(100.0, abs(v) / mx * 100.0)))) if mx > 0 else 0


def _fmt_dvol(v: float) -> str:
    if v >= 1e12:
        return f"${v / 1e12:.1f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v / 1e3:.0f}K"


def _row(r: Mapping, *, val: str, metric: float, mx: float,
         extra: str | None = None) -> dict:
    chg = _f(r.get("chg"))
    return {
        "t": r["ticker"], "name": r.get("name") or r["ticker"],
        "val": val, "extra": extra,
        "tone": "up" if (chg or 0) >= 0 else "dn",
        "w": _bar_w(metric, mx),
    }


def boards(rows: Sequence[Mapping], *, n: int = 8,
           liquid_floor: float = 2.0e8) -> dict:
    """The six mover boards, over the full coverage universe.

    `liquid_floor` gates the unusual-volume board only: a $3m-a-day name doubling
    its own volume is noise, and without the floor that board fills with the
    least liquid names on the list every single session.
    """
    have_chg = [r for r in rows if _f(r.get("chg")) is not None]
    have_dvol = [r for r in rows if (_f(r.get("dvol")) or 0) > 0]
    have_rvol = [r for r in rows
                 if (_f(r.get("rvol")) or 0) > 0 and (_f(r.get("dvol")) or 0) >= liquid_floor]
    have_52 = [r for r in rows if _f(r.get("pos52")) is not None]

    out: dict[str, list[dict]] = {}

    gain = sorted(have_chg, key=lambda r: -_f(r["chg"]))[:n]
    lose = sorted(have_chg, key=lambda r: _f(r["chg"]))[:n]
    for key, sel in (("gainers", gain), ("losers", lose)):
        mx = max((abs(_f(r["chg"])) for r in sel), default=0.0)
        out[key] = [_row(r, val=f'{_f(r["chg"]):+.2f}%', metric=_f(r["chg"]), mx=mx)
                    for r in sel]

    act = sorted(have_dvol, key=lambda r: -_f(r["dvol"]))[:n]
    mx = max((_f(r["dvol"]) for r in act), default=0.0)
    out["active"] = [
        _row(r, val=_fmt_dvol(_f(r["dvol"])), metric=_f(r["dvol"]), mx=mx,
             extra=(f'{_f(r["chg"]):+.1f}%' if _f(r.get("chg")) is not None else None))
        for r in act
    ]

    unu = sorted(have_rvol, key=lambda r: -_f(r["rvol"]))[:n]
    mx = max((_f(r["rvol"]) for r in unu), default=0.0)
    out["unusual"] = [
        _row(r, val=f'{_f(r["rvol"]):.1f}×', metric=_f(r["rvol"]), mx=mx,
             extra=(f'{_f(r["chg"]):+.1f}%' if _f(r.get("chg")) is not None else None))
        for r in unu
    ]

    hi = sorted((r for r in have_52 if _f(r["pos52"]) >= 93.0),
                key=lambda r: -_f(r["pos52"]))[:n]
    lo = sorted((r for r in have_52 if _f(r["pos52"]) <= 7.0),
                key=lambda r: _f(r["pos52"]))[:n]
    for key, sel in (("near_high", hi), ("near_low", lo)):
        mx = max((abs(_f(r.get("chg")) or 0.0) for r in sel), default=0.0)
        out[key] = [
            _row(r, val=(f'{_f(r["chg"]):+.2f}%' if _f(r.get("chg")) is not None else "—"),
                 metric=(_f(r.get("chg")) or 0.0), mx=mx)
            for r in sel
        ]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Themes moving together
# ═══════════════════════════════════════════════════════════════════════════
def theme_ribbons(data: Mapping | None, *, linkable: frozenset[str],
                  n_themes: int = 6, n_members: int = 8) -> list[dict]:
    """Shape the marketing theme tape for the consolidated stock hub.

    ``engine.marketing.movers_source`` remains the one authority for grouping,
    direction, ranking, deduplication and session provenance.  This adapter only
    makes that output safe for ``/stocks/``: every displayed member must have a
    dossier in the same render, so the retired stand-alone page's inert chips can
    never return as dead links.

    A ribbon needs at least two linkable members.  The source has already required
    four names to move in the same direction; after applying the dossier boundary,
    one surviving name would no longer communicate a group moving together.
    """
    if not data or not linkable:
        return []

    from engine.marketing.movers_source import theme_lists

    allowed = frozenset(str(t).upper() for t in linkable)
    raw = theme_lists(dict(data), tf="1D", n=n_members)
    out: list[dict] = []
    for item in raw:
        members: list[dict] = []
        member_pcts: list[float] = []
        for member in item.get("members") or []:
            ticker = str(member.get("ticker") or "").upper()
            pct = _f(member.get("pct"))
            if not ticker or ticker not in allowed or pct is None:
                continue
            member_pcts.append(pct)
            members.append({
                "t": ticker,
                "pc": f"{pct:+.2f}%",
                "tone": "up" if pct >= 0 else "dn",
            })

        if len(members) < 2:
            continue
        # The source aggregate spans the complete upstream theme membership.
        # This page shows a dossier-bounded subset, so label the average of the
        # names the reader can actually see rather than borrowing a hidden set's
        # number (Commodities, for example, can differ by several percentage
        # points after the linkability boundary).
        agg = sum(member_pcts) / len(member_pcts)
        direction = "up" if str(item.get("direction")) == "up" else "dn"
        out.append({
            "name": str(item.get("theme") or ""),
            "tone": direction,
            "avg_pc": f"{agg:+.2f}%" if agg is not None else "—",
            "members": members,
            "asof": item.get("asof"),
        })
        if len(out) >= n_themes:
            break
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Sector ledger (S&P scope — needs real cap weights)
# ═══════════════════════════════════════════════════════════════════════════
def sector_ledger(summary: Mapping | None) -> list[dict]:
    """Cap-weighted sector moves, straight off `market_heatmap.page_summary()`.

    Reused rather than recomputed: that function already owns the weighting rule
    the heatmap pages print, and a second implementation here would be a second
    answer to the same question.
    """
    if not summary:
        return []
    return list(summary.get("sectors") or [])


# ═══════════════════════════════════════════════════════════════════════════
# Treemap (S&P scope, server-rendered)
# ═══════════════════════════════════════════════════════════════════════════
def squarify(items: Sequence[Mapping], x: float, y: float,
             w: float, h: float) -> list[dict]:
    """Squarified treemap layout. `items` carry a positive `v` weight."""
    live = [dict(i) for i in items if (_f(i.get("v")) or 0) > 0]
    if not live or w <= 0 or h <= 0:
        return []
    tot = sum(i["v"] for i in live)
    live = sorted(({**i, "v": i["v"] / tot * (w * h)} for i in live),
                  key=lambda i: i["v"], reverse=True)
    out: list[dict] = []
    cx, cy, cw, ch = x, y, w, h

    def ratio(row: list[dict], length: float) -> float:
        s = sum(i["v"] for i in row)
        if s <= 0 or length <= 0:
            return math.inf
        band = s / length
        worst = 0.0
        for i in row:
            side = i["v"] / band
            if side <= 0:
                return math.inf
            worst = max(worst, band / side, side / band)
        return worst

    def place(row: list[dict], x0: float, y0: float, w0: float, h0: float):
        s = sum(i["v"] for i in row)
        if s <= 0:
            return x0, y0, w0, h0
        if w0 >= h0:
            band = s / h0 if h0 else 0.0
            cyy = y0
            for i in row:
                ih = i["v"] / band if band else 0.0
                out.append({**i, "x": x0, "y": cyy, "w": band, "h": ih})
                cyy += ih
            return x0 + band, y0, w0 - band, h0
        band = s / w0 if w0 else 0.0
        cxx = x0
        for i in row:
            iw = i["v"] / band if band else 0.0
            out.append({**i, "x": cxx, "y": y0, "w": iw, "h": band})
            cxx += iw
        return x0, y0 + band, w0, h0 - band

    row: list[dict] = []
    queue = list(live)
    while queue:
        length = ch if cw >= ch else cw
        cand = row + [queue[0]]
        if not row or ratio(cand, length) <= ratio(row, length):
            row, queue = cand, queue[1:]
        else:
            cx, cy, cw, ch = place(row, cx, cy, cw, ch)
            row = []
    if row:
        place(row, cx, cy, cw, ch)
    return out


def tone_var(ret: float) -> str:
    """Bin a move onto the shared +/-1/2/3% ladder as a CSS custom property.

    Returns a `var(--hm*)` reference, never a literal colour, so the ramp tracks
    --up/--down — including the red-up/green-down swap under data-lang="zh".
    """
    a = abs(ret)
    if a < 0.15:
        return "var(--hm0)"
    step = 1 if a < 1 else (2 if a < 2 else (3 if a < 3 else 4))
    return f"var(--hm{'u' if ret > 0 else 'd'}{step})"


def treemap(payload: Mapping | None, *, linkable: frozenset[str] | None = None) -> dict | None:
    """Sector -> stock treemap geometry from the committed heatmap payload.

    Server-rendered on purpose: `/marketdata/sp500_heatmap.json` sits behind the
    auth gate in `app/deploy/Caddyfile` while `/stocks/*` is anonymous-public, so
    a client-side fetch would draw an empty card for every logged-out visitor and
    every crawler.
    """
    if not payload:
        return None
    tf = str(payload.get("default_tf") or "1D")
    frames = list(payload.get("timeframes") or [])
    if not any(f.get("key") == tf and f.get("available") for f in frames):
        avail = [f["key"] for f in frames if f.get("available")]
        if not avail:
            return None
        tf = avail[0]

    tiles = [t for t in (payload.get("tiles") or [])
             if _f((t.get("perf") or {}).get(tf)) is not None and (_f(t.get("size")) or 0) > 0]
    if not tiles:
        return None

    labels = {s["key"]: s for s in (payload.get("sectors") or [])}
    by_sec: dict[str, list[dict]] = {}
    for t in tiles:
        by_sec.setdefault(str(t.get("sector") or "—"), []).append(t)

    cells = squarify(
        [{"v": sum(_f(x.get("size")) or 0.0 for x in g), "key": k, "rows": g}
         for k, g in by_sec.items()], 0, 0, HM_W, HM_H)

    sectors: list[dict] = []
    for c in cells:
        lab = labels.get(c["key"], {})
        en = lab.get("en", c["key"])
        inner = squarify([{"v": _f(r.get("size")) or 0.0, "r": r} for r in c["rows"]],
                         c["x"] + 2, c["y"] + _SEC_HEAD,
                         max(1.0, c["w"] - 6), max(1.0, c["h"] - _SEC_HEAD - 4))
        out_tiles: list[dict] = []
        for t in inner:
            if t["w"] < 1.4 or t["h"] < 1.4:
                continue
            r = t["r"]
            code = str(r.get("t") or "")
            ret = _f((r.get("perf") or {}).get(tf)) or 0.0
            big = t["w"] > 38 and t["h"] > 28
            out_tiles.append({
                "t": code,
                "name": r.get("name") or code,
                "ret": ret, "pc": f"{ret:+.2f}%",
                "x": round(t["x"], 1), "y": round(t["y"], 1),
                "w": round(max(0.0, t["w"] - 1.5), 1),
                "h": round(max(0.0, t["h"] - 1.5), 1),
                "cx": round(t["x"] + t["w"] / 2, 1),
                "fill": tone_var(ret),
                # label only where the glyphs actually fit — a clipped ticker is
                # worse than a bare tile a hover explains
                "show_t": t["w"] > 27 and t["h"] > 15,
                "show_pc": big,
                "ty": round(t["y"] + t["h"] / 2 + (-1.0 if big else 3.6), 1),
                "py": round(t["y"] + t["h"] / 2 + 10.5, 1),
                "href": (f"{code}.html" if (linkable is None or code in linkable) else None),
            })
        sectors.append({
            "key": c["key"], "en": en, "zh": lab.get("zh", en),
            "x": round(c["x"], 1), "y": round(c["y"], 1),
            "w": round(max(0.0, c["w"] - 2), 1), "h": round(max(0.0, c["h"] - 2), 1),
            "lx": round(c["x"] + 7, 1), "ly": round(c["y"] + 11.5, 1),
            "show_label": c["w"] > 56 and c["h"] > 32,
            "tiles": out_tiles,
        })
    return {"w": HM_W, "h": HM_H, "sectors": sectors, "tf": tf,
            "n": sum(len(s["tiles"]) for s in sectors)}


# ═══════════════════════════════════════════════════════════════════════════
# Client payloads
# ═══════════════════════════════════════════════════════════════════════════
def search_index(rows: Sequence[Mapping]) -> list[list]:
    """Compact positional rows for the client search.

    Positional, not keyed: at ~1,544 names an object-per-row payload costs
    several times this in repeated key names for zero added meaning. Column
    order is pinned in `stocks_hub.js`.
      [ticker, name, sector, price, chg%, stanceKey, capBn, rvol, pos52]
    """
    out: list[list] = []
    for r in rows:
        out.append([
            r["ticker"],
            r.get("name") or r["ticker"],
            r.get("sector") or "",
            round(_f(r.get("price_f")) or 0.0, 2),
            round(_f(r.get("chg")) or 0.0, 2),
            r.get("stance_key") or "",
            round(_f(r.get("cap_bn")) or 0.0),
            round(_f(r.get("rvol")) or 0.0, 2),
            round(_f(r.get("pos52")) or 0.0, 1),
        ])
    return out


def directory(rows: Sequence[Mapping]) -> list[dict]:
    """A-Z groups for the crawlable index at the foot of the page.

    This is why the page can stop rendering 1,544 cards without costing the site
    1,544 internal links: every dossier still ships an <a>, as a text chip.
    """
    groups: dict[str, list[str]] = {}
    for r in rows:
        t = str(r["ticker"])
        if not t:
            continue
        head = t[0].upper()
        groups.setdefault(head if head.isalpha() else "#", []).append(t)
    return [{"letter": k, "tickers": sorted(v)}
            for k, v in sorted(groups.items())]
