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
    "treemap", "search_index", "directory", "squarify", "pressure_band",
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


# ═══════════════════════════════════════════════════════════════════════════
# Pressure Watch — the resolved-first price-pressure band
# ═══════════════════════════════════════════════════════════════════════════
# The band's primary object is the RESOLVED ledger, not today's dips: "here is
# what usually happens" is a different claim from "here is what is cheap now",
# and the movers boards directly above already make the second one. So the copy
# this function shapes runs base rates -> resolved episodes -> open events, and
# the open list is ordered by RECENCY ONLY. Ordering it by move size or by how
# unusual the move was would be ranking authority the artifact explicitly
# denies itself, which is why `_recency_order` exists as its own named step and
# is pinned by a test rather than living inline in a sort call.
#
# Every string ships as an {en, zh} twin because no user-facing text on this
# page may reach the template as a single language, and CJK can never travel in
# a `title=` attribute (`scripts/check_title_i18n.py`) — the template spends
# these on `data-tip-en`/`data-tip-zh` instead.

PW_MAX_OPEN = 6            # a band, not a feed
PW_MAX_RESOLVED = 4
PW_MAX_STALE_SESSIONS = 5  # weekdays between the artifact and the page's own bars

_PW_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_PW_CN_NUM = "〇一二三四五六七八九十"

# Filing families. "no filing on record" is defined ONLY inside the covered
# panel; the ~half of the panel EDGAR does not track gets its own chip, because
# "we did not look" and "we looked and found nothing" are different facts and
# conflating them would invent evidence out of ignorance.
_PW_FAMILY = {
    "earnings-filing": {
        "en": "earnings filing", "zh": "财报公告",
        "tip_en": "An earnings filing landed around this move.",
        "tip_zh": "此次波动前后有财报公告落地。",
    },
    "other-filing": {
        "en": "other filing", "zh": "其他公告",
        "tip_en": "A filing that was not an earnings report landed around this move.",
        "tip_zh": "此次波动前后有非财报类公告落地。",
    },
    "no-filing": {
        "en": "no filing on record", "zh": "无公告记录",
        "tip_en": "We track filings for this name and found none around this move.",
        "tip_zh": "我们追踪该股公告，此次波动前后没有找到公告。",
    },
    "filing-coverage-unknown": {
        "en": "filings not tracked", "zh": "未追踪该股公告",
        "tip_en": ("We do not track filings for this name, so this is not a claim "
                   "that none exist."),
        "tip_zh": "我们没有追踪该股的公告，这并不代表它没有发布公告。",
    },
}

# Display states (§5.1) in plain words. Down and up sides are separate tables:
# the same underlying fraction means "recovered" on one side and "unwound" on
# the other, and one shared table would have to name it in machine terms.
_PW_STATE = {
    "down": {
        "SHOCK": ("new today", "今日新发生"),
        "SLIDING": ("still falling", "仍在下探"),
        "HOLDING": ("holding", "暂时企稳"),
        "RETRACING": ("{p}% recovered", "已收复 {p}%"),
    },
    "up": {
        "SHOCK": ("new today", "今日新发生"),
        "EXTENDING": ("still climbing", "仍在走高"),
        "HOLDING": ("holding", "维持涨幅"),
        "FADING": ("{p}% unwound", "已回落 {p}%"),
    },
}

# Window-end grades. Keys are matched on their leading token so the up-side
# mirror can ship either its own vocabulary or the shared one.
_PW_TERMINAL = {
    "RECOVERED": ("fully back within a month", "一个月内基本收复"),
    "KEPT": ("kept the gain", "涨幅得以保持"),
    "PARTIAL": ("partly back", "部分收复"),
    "ACCEPTED": ("kept the lower price", "维持在更低价位"),
    "GAVE": ("back to where it started", "回到起点"),
    "DELISTED": ("stopped trading", "已停止交易"),
}

# The outcome bar, worst -> best. `delisted` sits FIRST on purpose: names that
# stopped trading are inside the denominator, and putting them at the head of
# the bar is the difference between disclosing that and burying it.
_PW_OUTCOMES = (
    ("delisted", "gone", "stopped trading", "已停止交易"),
    ("accepted_lower", "low", "kept the lower price", "维持在更低价位"),
    ("partial", "mid", "partly back", "部分收复"),
    ("recovered", "back", "fully back", "基本收复"),
)


def _pw_pretty(v: Any) -> str:
    """Machine slug -> display name. Raw slugs never reach the glance tier."""
    s = str(v or "").strip()
    if not s:
        return ""
    if "-" in s or "_" in s:
        s = s.replace("-", " ").replace("_", " ").strip()
        return s[:1].upper() + s[1:]
    return s


def _pw_day(iso: Any, lang: str = "en") -> str:
    """'2026-07-01' -> 'Jul 1' / '7月1日'. Returns the input on anything odd."""
    s = str(iso or "")
    parts = s.split("-")
    if len(parts) != 3:
        return s
    try:
        mo, dy = int(parts[1]), int(parts[2])
    except ValueError:
        return s
    if not (1 <= mo <= 12):
        return s
    return f"{mo}月{dy}日" if lang == "zh" else f"{_PW_MONTHS_EN[mo - 1]} {dy}"


def _pw_cn_tenths(n: int) -> str:
    return "十" if n >= 10 else _PW_CN_NUM[n]


def _pw_in_ten(share: float) -> tuple[str, str]:
    """A share as a plain sentence fragment, never a bare percentage.

    Law 3 of the design doctrine: a number on the glance tier arrives with its
    interpretation. "0.58" is a statistic; "about 6 in 10" is information, and
    the exact figure is one hover away on the bar itself.
    """
    if share >= 0.95:
        return "almost all", "几乎全部"
    if share <= 0.05:
        return "almost none", "极少数"
    n = min(9, max(1, round(share * 10)))
    return f"about {n} in 10", f"约{_pw_cn_tenths(n)}成"


def _pw_pc(v: float | None, *, dp: int = 1, signed: bool = False) -> str:
    """Percent with a typographic minus — the band never prints a hyphen-minus."""
    if v is None:
        return "—"
    s = f"{v * 100:+.{dp}f}%" if signed else f"{abs(v) * 100:.{dp}f}%"
    return s.replace("-", "−")


def _pw_weekdays_between(a: str, b: str) -> int | None:
    """Weekday count between two ISO dates — a session proxy with no clock.

    Staleness is judged against the page's OWN bar session rather than the wall
    clock so the function stays pure and so a band can never claim to be fresher
    than the boards printed beside it. Holidays count as sessions, which errs
    toward showing the warm-up state early — the safe direction.
    """
    from datetime import date as _date

    try:
        y1, m1, d1 = (int(x) for x in str(a).split("-"))
        y2, m2, d2 = (int(x) for x in str(b).split("-"))
        d_a, d_b = _date(y1, m1, d1), _date(y2, m2, d2)
    except (ValueError, TypeError):
        return None
    if d_b <= d_a:
        return 0
    days = (d_b - d_a).days
    full, rest = divmod(days, 7)
    n = full * 5
    wd = d_a.weekday()
    for i in range(1, rest + 1):
        if (wd + i) % 7 < 5:
            n += 1
    return n


def _pw_recency_order(rows: Sequence[Mapping]) -> list[dict]:
    """Most recent first, then ticker A-Z. The ONLY ordering this band has.

    Named and tested as its own step because the tempting sort — biggest move,
    or most unusual move, first — is exactly the ranking authority the artifact
    denies itself. A board that puts the worst-hit name at the top is telling
    the reader it is the most interesting one, and nothing here measured that.
    """
    out = [dict(r) for r in rows if r and r.get("ticker")]
    out.sort(key=lambda r: str(r.get("ticker") or ""))
    out.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    return out


def _pw_move_words(row: Mapping) -> tuple[str, str]:
    """The row's one-line move phrase, in whichever form the data supports.

    `ret` is the raw session move and `resid` is the part of it the market or
    the peer group did not explain. When the artifact ships `ret` the line reads
    as a price move; when it does not, the line says "more than peers" rather
    than quietly relabelling a residual as a price change.
    """
    side = "up" if str(row.get("side")) == "up" else "down"
    ret = _f(row.get("ret"))
    resid = _f(row.get("resid"))
    vol = _f(row.get("vol_multiple"))
    vol_en = f" on {vol:.1f}× volume" if vol else ""
    vol_zh = f"，成交量为常态的 {vol:.1f} 倍" if vol else ""

    if ret is not None:
        verb_en, verb_zh = ("rose", "上涨") if side == "up" else ("fell", "下跌")
        return (f"{verb_en} {_pw_pc(ret)}{vol_en}",
                f"{verb_zh} {_pw_pc(ret)}{vol_zh}")
    if resid is not None:
        verb_en, verb_zh = ("rose", "涨幅") if side == "up" else ("fell", "跌幅")
        more_en = "more than the rest of the market"
        return (f"{verb_en} {_pw_pc(resid)} {more_en}{vol_en}",
                f"{verb_zh}比大盘多 {_pw_pc(resid)}{vol_zh}")
    return ("moved sharply", "出现大幅波动")


def _pw_compare_words(row: Mapping) -> tuple[str, str]:
    """The honest comparison clause, basis-aware.

    Three shapes, and which one prints is a correctness question rather than a
    stylistic one:

    * the peer helper falls back to a whole-universe mean for names it cannot
      label, so the word "peers" NEVER prints on a market-basis row;
    * where a thematic basket moved with the name, the basket leads — a silver
      miner's sector bucket is chemicals and steel, so "peers implied" would be
      economically false on exactly the day it matters most;
    * with neither, the clause is omitted rather than invented.
    """
    # The producer carries both the stable basket key and a curated display
    # label. Prefer the label when present: prettifying `us_sector_materials`
    # loses the economically useful "Materials (Equal-Weight)" wording.
    basket = (str(row.get("basket_en") or "").strip()
              or _pw_pretty(row.get("basket")))
    b_ret = _f(row.get("basket_ret"))
    side_down = str(row.get("side")) != "up"

    if basket and b_ret is not None and ((b_ret < 0) == side_down) and abs(b_ret) > 0.001:
        b_zh = str(row.get("basket_zh") or basket)
        verb_en, verb_zh = ("fell", "下跌") if b_ret < 0 else ("rose", "上涨")
        return (f"its {basket} basket {verb_en} {_pw_pc(b_ret)} too",
                f"同期「{b_zh}」板块也{verb_zh} {_pw_pc(b_ret)}")

    peer = _f(row.get("peer_ret"))
    if peer is None:
        return "", ""
    if str(row.get("peer_basis")) == "sector":
        return (f"peers moved {_pw_pc(peer, signed=True)}",
                f"同业当日 {_pw_pc(peer, signed=True)}")
    return (f"the market moved {_pw_pc(peer, signed=True)}",
            f"大盘当日 {_pw_pc(peer, signed=True)}")


def _pw_state_chip(row: Mapping) -> dict | None:
    side = "up" if str(row.get("side")) == "up" else "down"
    key = str(row.get("state") or "").upper()
    pair = _PW_STATE[side].get(key)
    if not pair:
        return None
    frac = _f(row.get("retrace_frac"))
    pct = max(0, min(100, round(abs(frac or 0.0) * 100)))
    return {"en": pair[0].format(p=pct), "zh": pair[1].format(p=pct)}


def _pw_terminal_words(row: Mapping) -> tuple[str, str]:
    key = str(row.get("terminal_state_21d") or "").upper()
    head = key.split("_")[0]
    pair = _PW_TERMINAL.get(head)
    if not pair:
        return "outcome on file", "结果已记录"
    return pair


def _pw_terminal_cls(row: Mapping) -> str:
    """Which end of the outcome bar this closed episode landed on.

    Shares the four segment classes so a resolved row and the bar above it are
    visibly the same vocabulary rather than two colour schemes for one fact.
    """
    head = str(row.get("terminal_state_21d") or "").upper().split("_")[0]
    if head == "DELISTED":
        return "gone"
    if head in ("RECOVERED", "KEPT"):
        return "back"
    if head in ("ACCEPTED", "GAVE"):
        return "low"
    return "mid"


def _pw_row_tip(row: Mapping) -> tuple[str, str]:
    """Tier 2: the mechanics, as label-value pairs rather than prose.

    Everything the glance tier deliberately does not say lives here — how far
    beyond its own history the move was, what it was compared against, how long
    it has been open, and whether a state change is waiting on a second close.
    """
    bits_en: list[str] = []
    bits_zh: list[str] = []
    z = _f(row.get("resid_z"))
    if z is not None:
        bits_en.append(f"Beyond its own history: {abs(z):.1f} standard deviations")
        bits_zh.append(f"超出自身历史波动：{abs(z):.1f} 个标准差")
    resid = _f(row.get("resid"))
    if resid is not None:
        bits_en.append(f"Move left unexplained: {_pw_pc(resid, signed=True)}")
        bits_zh.append(f"未被解释的部分：{_pw_pc(resid, signed=True)}")
    vol = _f(row.get("vol_multiple"))
    if vol:
        bits_en.append(f"Volume: {vol:.1f}× its own normal")
        bits_zh.append(f"成交量：常态的 {vol:.1f} 倍")
    basis = str(row.get("peer_basis") or "")
    if basis:
        bits_en.append("Compared against: "
                       + ("its sector" if basis == "sector" else "the whole market"))
        bits_zh.append("对比基准：" + ("所属行业" if basis == "sector" else "全市场"))
    days = _f(row.get("days_open"))
    if days is not None:
        bits_en.append(f"Tracked for {int(days)} session(s)")
        bits_zh.append(f"已跟踪 {int(days)} 个交易日")
    pending = str(row.get("state_pending") or "")
    if pending:
        bits_en.append("A change of state is waiting on a second close")
        bits_zh.append("状态变化需再收一根确认")
    return " · ".join(bits_en), " · ".join(bits_zh)


def _pw_base(base: Mapping | None) -> dict | None:
    """The frozen five-year record, as a headline plus one proportional bar.

    The bar IS the number: the sentence above it says what usually happened,
    the segments say in what proportion, and the exact shares stay on hover.
    Any outcome with a real share gets at least a visible sliver, and an outcome
    with none renders nothing at all rather than a decorative stub.
    """
    if not base:
        return None
    down = base.get("down") or {}
    n_ev = _f(down.get("n_events"))
    rec = _f(down.get("h21_share_recovered"))
    acc = _f(down.get("h21_share_accepted_lower"))
    dead = _f(down.get("h21_share_delisted"))
    if acc is None or rec is None:
        return None
    dead = dead or 0.0
    part = _f(down.get("h21_share_partial"))
    if part is None:
        part = max(0.0, 1.0 - rec - acc - dead)

    shares = {"recovered": rec, "accepted_lower": acc,
              "partial": part, "delisted": dead}
    total = sum(shares.values()) or 1.0
    segs = []
    for key, cls, lab_en, lab_zh in _PW_OUTCOMES:
        share = shares.get(key) or 0.0
        if share <= 0:
            continue
        pc = share / total
        segs.append({
            "key": key, "cls": cls, "en": lab_en, "zh": lab_zh,
            "w": round(max(0.6, pc * 100.0), 2),
            "pc": f"{round(pc * 100)}%",
            "tip_en": f"{lab_en} — {round(pc * 100)}% of past shocks, one month on.",
            "tip_zh": f"{lab_zh} —— 一个月后，{round(pc * 100)}% 的历史案例落在这一档。",
        })
    if not segs:
        return None

    en, zh = _pw_in_ten(acc)
    span = list(base.get("span") or [])
    span_txt = f"{span[0]} – {span[1]}" if len(span) == 2 else ""
    # The bar is the DOWN side (the record's primary half), while the tracked
    # list below carries both. The headline says "a drop like this" so the two
    # can never be read as one population.
    return {
        "headline_en": f"After a drop like this, {en} were still down a month later.",
        "headline_zh": f"出现这样的下跌之后，{zh}在一个月后仍未收复。",
        "null_en": "What kind of filing sat behind the move made no measurable difference.",
        "null_zh": "背后是哪类公告，对结果没有可测出的差别。",
        "segments": segs,
        "span": span_txt,
        "n_events": int(n_ev) if n_ev else None,
    }


def _pw_help(payload: Mapping, base: Mapping | None) -> dict:
    """The `?` card on the band heading — the sanctioned home for the mechanics.

    Carries the four things the glance tier is not allowed to carry: what counts
    as an event, how big and how old the record is, the measured family null
    with its source, and the scope sentence that keeps a display state from
    reading as a forecast.
    """
    cov = payload.get("coverage") or {}
    base = base or {}
    down = (base.get("down") or {}) if base else {}
    n_ev = _f(down.get("n_events"))
    span = list(base.get("span") or []) if base else []
    span_txt = f"{span[0]} – {span[1]}" if len(span) == 2 else ""
    names = _f(cov.get("panel_names"))
    sector_share = _f(cov.get("sector_basis_share"))
    edgar = _f(cov.get("edgar_covered_share"))
    prov = payload.get("provenance") or {}
    study = str(prov.get("study_title") or "").strip() or _pw_pretty(
        str(prov.get("study") or "").rsplit("/", 1)[-1].rsplit(".", 1)[0])

    rows = [{
        "k_en": "What counts", "k_zh": "什么算一次",
        "v_en": ("A one-day move far beyond what the market or the name's sector "
                 "explains, on heavy volume."),
        "v_zh": "单日波动远超大盘或所属行业能解释的幅度，且伴随明显放量。",
    }]
    # Both horizons under one label. §6 publishes family x horizon cells, but the
    # family contrast is measured NULL and the surface is required never to
    # contrast families — a grid invites exactly the comparison the record says
    # cannot be made, so the second horizon ships as a sentence instead.
    h5 = _f(down.get("h5_median_retrace"))
    if n_ev and span_txt:
        h5_en = h5_zh = ""
        if h5 is not None:
            h5_en = (f" Five days in, half had recovered less than "
                     f"{round(abs(h5) * 100)}% of the drop.")
            h5_zh = f"第五天时，一半个股收复的幅度不到跌幅的 {round(abs(h5) * 100)}%。"
        rows.append({
            "k_en": "The record", "k_zh": "记录范围",
            "v_en": f"{int(n_ev):,} past moves, {span_txt} — five years, not twenty.{h5_en}",
            "v_zh": f"{int(n_ev):,} 次历史案例，{span_txt}，是五年而非二十年。{h5_zh}",
        })
    if names or sector_share is not None or edgar is not None:
        cov_en, cov_zh = [], []
        if names:
            cov_en.append(f"{int(names):,} names watched")
            cov_zh.append(f"监测 {int(names):,} 只个股")
        if sector_share is not None:
            cov_en.append(f"{round(sector_share * 100)}% compared against a sector, "
                          "the rest against the whole market")
            cov_zh.append(f"其中 {round(sector_share * 100)}% 以所属行业为基准，"
                          "其余以全市场为基准")
        if edgar is not None:
            cov_en.append(f"filings tracked for {round(edgar * 100)}% of them")
            cov_zh.append(f"{round(edgar * 100)}% 的个股有公告追踪")
        rows.append({"k_en": "Coverage", "k_zh": "覆盖范围",
                     "v_en": " · ".join(cov_en), "v_zh": " · ".join(cov_zh)})
    rows.append({
        "k_en": "By filing type", "k_zh": "按公告类型",
        "v_en": ("Measured — no difference showed up in any of the ten "
                 "comparisons. Labels are context, not a reason to expect a "
                 "different ending."),
        "v_zh": "已做测量，十组对比均未显示差异。标签仅作背景，不代表结局会有所不同。",
    })
    rows.append({
        "k_en": "Scope", "k_zh": "适用范围",
        "v_en": ("These states describe the tracked window only, and are read off "
                 "prices that already happened."),
        "v_zh": "这些状态只描述被跟踪的时间窗口，全部依据已经发生的价格得出。",
    })
    up_n = _f((base.get("up") or {}).get("n_events")) if base else None
    if up_n:
        rows.append({
            "k_en": "Sharp gains", "k_zh": "急涨一侧",
            "v_en": (f"Recorded the same way ({int(up_n):,} moves). The bar above "
                     "shows the down side."),
            "v_zh": f"以同样方式记录（{int(up_n):,} 次）。上方条形图展示的是下跌一侧。",
        })
    # The artifact's own sentence about its record, surfaced verbatim but on the
    # tier that can carry it: whatever caveats the freeze wrote down belong in
    # front of the reader, and never in the four-word headline above.
    note_en = str((base or {}).get("note_en") or "").strip()
    if note_en:
        rows.append({
            "k_en": "From the record", "k_zh": "记录附注",
            "v_en": note_en,
            "v_zh": str((base or {}).get("note_zh") or "").strip() or note_en,
        })
    return {
        "kick_en": "PRESSURE WATCH", "kick_zh": "个股承压",
        "title_en": "How this is measured", "title_zh": "如何测量",
        "rows": rows,
        "receipt_en": ("display context · not a signal"
                       + (f" · source: {study}" if study else "")),
        "receipt_zh": ("展示背景 · 非交易信号"
                       + (f" · 来源：{study}" if study else "")),
    }


def pressure_band(payload: Mapping | None, *, board_asof: str | None = None,
                  max_open: int = PW_MAX_OPEN,
                  max_resolved: int = PW_MAX_RESOLVED) -> dict:
    """Shape the Pressure Watch band. Pure — no I/O, no clock, no network.

    Always returns a renderable dict. A missing, unreadable or stale artifact
    yields the warm-up mode rather than an absent band or an exception, because
    the surface ships ahead of the engine that feeds it and an empty section is
    a design decision, not an error path.

    `board_asof` is the session the rest of the page is printing. The band goes
    back to warm-up when the artifact trails it by more than a working week, so
    the band can never quietly present month-old events beside today's boards.
    """
    warm = {
        "mode": "warmup",
        "title_en": "Pressure Watch", "title_zh": "个股承压",
        # Deliberately NOT "what usually happens" — that is the first stratum's
        # own label, and reading it twice in two lines spends the reader's
        # attention on the same four words instead of on the record.
        "sub_en": ("How one-day moves far beyond what the market explains have "
                   "actually ended."),
        "sub_zh": "单日波动远超大盘可解释的幅度时，这些个股最后是怎么收场的。",
        "warm_en": "Still building this record — nothing to show yet.",
        "warm_zh": "记录仍在建立中 —— 暂无可展示的内容。",
        "stance_en": "Nothing to act on yet.", "stance_zh": "暂时无需操作。",
        "asof": None, "banner": None, "demoted": False,
        "base": None, "resolved": [], "open": [], "open_n": 0,
        "count_en": "most recent first", "count_zh": "按时间先后排列",
        "help": None, "gaps": [],
        "foot_en": ("A record of what happened next, not a call on what will "
                    "— nothing here ranks or recommends a name."),
        "foot_zh": "这里记录的是历史结果，而非对后市的判断；不构成任何排名或推荐。",
    }
    if not payload or not isinstance(payload, Mapping):
        return warm

    asof = str(payload.get("asof") or "") or None
    if asof and board_asof:
        gap = _pw_weekdays_between(asof, str(board_asof))
        if gap is not None and gap > PW_MAX_STALE_SESSIONS:
            return warm

    base = _pw_base(payload.get("base_rates"))
    resolved_src = list(payload.get("recently_resolved") or [])
    open_src = list(payload.get("open_events") or [])
    if not base and not resolved_src and not open_src:
        return warm

    day = payload.get("day") or {}
    raw_banner = day.get("banner")
    banner = None
    if raw_banner:
        shock_n = _f(day.get("panel_shock_count"))
        tip_en = tip_zh = ""
        if shock_n:
            tip_en = (f"{int(shock_n)} covered names took a move this size today, "
                      "so the single-name reads below carry less weight than usual.")
            tip_zh = (f"今日有 {int(shock_n)} 只覆盖个股出现同等级别的波动，"
                      "因此下方的个股解读比平时更弱。")
        if isinstance(raw_banner, Mapping) and raw_banner.get("en"):
            banner = {"en": str(raw_banner["en"]),
                      "zh": str(raw_banner.get("zh") or raw_banner["en"]),
                      "tip_en": tip_en, "tip_zh": tip_zh}
        else:
            banner = {
                "en": "Most of today's pressure is market-wide, not single-name.",
                "zh": "今天的压力多数来自大盘，而非个股自身。",
                "tip_en": tip_en, "tip_zh": tip_zh,
            }

    resolved: list[dict] = []
    for r in _pw_recency_order(resolved_src)[:max_resolved]:
        mv_en, mv_zh = _pw_move_words(r)
        end_en, end_zh = _pw_terminal_words(r)
        fam = _PW_FAMILY.get(str(r.get("family") or ""))
        resolved.append({
            "t": str(r["ticker"]).upper(),
            "side": "up" if str(r.get("side")) == "up" else "down",
            "when_en": _pw_day(r.get("date")), "when_zh": _pw_day(r.get("date"), "zh"),
            "move_en": mv_en, "move_zh": mv_zh,
            "end_en": end_en, "end_zh": end_zh,
            "end_cls": _pw_terminal_cls(r),
            "fam_en": (fam or {}).get("en", ""), "fam_zh": (fam or {}).get("zh", ""),
        })

    events: list[dict] = []
    for r in _pw_recency_order(open_src)[:max_open]:
        mv_en, mv_zh = _pw_move_words(r)
        cmp_en, cmp_zh = _pw_compare_words(r)
        tip_en, tip_zh = _pw_row_tip(r)
        fam = _PW_FAMILY.get(str(r.get("family") or ""))
        chip = _pw_state_chip(r)
        events.append({
            "t": str(r["ticker"]).upper(),
            "side": "up" if str(r.get("side")) == "up" else "down",
            "when_en": _pw_day(r.get("date")), "when_zh": _pw_day(r.get("date"), "zh"),
            "move_en": mv_en, "move_zh": mv_zh,
            "cmp_en": cmp_en, "cmp_zh": cmp_zh,
            "fam_en": (fam or {}).get("en", ""), "fam_zh": (fam or {}).get("zh", ""),
            "fam_tip_en": (fam or {}).get("tip_en", ""),
            "fam_tip_zh": (fam or {}).get("tip_zh", ""),
            "state_en": (chip or {}).get("en", ""), "state_zh": (chip or {}).get("zh", ""),
            "tip_en": tip_en, "tip_zh": tip_zh,
        })

    # Rows that carry no ticker cannot be rendered — they were dropped above, so
    # re-check emptiness AFTER shaping rather than before it. A payload full of
    # unusable rows is indistinguishable from no payload, and an empty live band
    # states "we are tracking nothing" where the truth is "we cannot read this".
    if not base and not resolved and not events:
        return warm

    gaps: list[dict] = []
    for g in payload.get("gaps") or []:
        if isinstance(g, Mapping) and g.get("en"):
            gaps.append({"en": str(g["en"]), "zh": str(g.get("zh") or g["en"])})
        elif isinstance(g, str) and g.strip():
            gaps.append({"en": g.strip(), "zh": g.strip()})

    return {
        **warm,
        "mode": "live",
        "asof": asof,
        "banner": banner,
        "demoted": bool(banner),
        "base": base,
        "resolved": resolved,
        "open": events,
        "open_n": len(open_src),
        # The cap is disclosed rather than silent: a list that quietly stops at
        # six looks like a complete list, and "there are five more" is the kind
        # of fact a reader is entitled to without opening anything.
        "count_en": (f"showing {len(events)} of {len(open_src)} · most recent first"
                     if len(open_src) > len(events) else "most recent first"),
        "count_zh": (f"显示 {len(open_src)} 条中的 {len(events)} 条 · 按时间先后排列"
                     if len(open_src) > len(events) else "按时间先后排列"),
        "help": _pw_help(payload, payload.get("base_rates")),
        "gaps": gaps,
        "stance_en": "Watch — don't chase.",
        "stance_zh": "观察为主，不急于跟进。",
        "warm_en": None, "warm_zh": None,
    }
