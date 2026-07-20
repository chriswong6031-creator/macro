"""ilx / "Signal Ink" — the house SSR-SVG illustration format.

A dependency-free (pure stdlib) renderer that turns a market/macro series into a
small, animated, theme-aware SVG fragment + absolutely-positioned HTML labels. It
is the lightweight replacement for Plotly chart fragments on illustrative /
display-tier surfaces (NOT for real stock/candle charting — that stays on the
lightweight-charts / trading stack).

Design law (docs/ILLUSTRATIONS.md):
  * The SVG carries paths only — NEVER <text>. `preserveAspectRatio="none"` stretches
    the 560-unit viewBox to the container width, which would warp any glyph. All text
    is HTML positioned over the figure in the page's own font (tabular-nums for data).
  * Single-series strokes/fills use `currentColor`; the accent is set as `color:` on
    the <figure> root, so a theme flip or the ZH --up/--down swap flows straight
    through without re-rendering. Dual-tint kinds (baseline waterline, sign-colored
    bars) bind var(--up)/var(--down) directly, so the ZH swap flips red/green.
  * Honesty in motion: settled data is *drawn once* and lands with a STATIC glow — no
    looping pulse that would fake liveness. A short / empty series renders an honest
    null (hairline + "No history yet"), never a fabricated chart (house nulls law).

Public API — keep the signature stable; HK / Canada lanes build against it:

    illus(series, *, kind="line", accent=None, height=190, unit_en="", unit_zh=None,
          baseline=None, reference=None, bands=None, value_fmt="{:,.1f}",
          max_points=220, aria_en="", aria_zh=None) -> str

`series`:
  * single-series kinds: {"dates": [iso...], "vals": [float...]}
  * kind="multi": list of {"label_en","label_zh","color","dates","vals"} (2-3 series)
"""
from __future__ import annotations

import hashlib
from html import escape

__all__ = ["illus"]

# viewBox is fixed; the container stretches it horizontally (preserveAspectRatio=none).
_VBW = 560.0
_PAD_T = 8.0     # top breathing room so the end-dot glow isn't clipped
_PAD_B = 8.0     # bottom breathing room


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _clean(dates, vals):
    """Zip -> drop pairs where the value is None/NaN, keep order."""
    out = []
    for d, v in zip(dates or [], vals or []):
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv:  # NaN
            continue
        out.append((d, fv))
    return out


def _downsample(pairs, max_points):
    """Bucketed min/max downsample that PRESERVES extremes (never a plain stride).

    Splits the series into ~max_points/2 buckets and keeps both the min and the
    max of each bucket in chronological order, so spikes survive. First and last
    points are always retained so the draw starts/ends on the true endpoints."""
    n = len(pairs)
    if n <= max_points or n < 4:
        return pairs
    n_buckets = max(1, max_points // 2)
    step = n / n_buckets
    kept = [pairs[0]]
    for b in range(n_buckets):
        lo = int(b * step)
        hi = int((b + 1) * step)
        if hi <= lo:
            hi = lo + 1
        chunk = pairs[lo:hi]
        if not chunk:
            continue
        vmin = min(chunk, key=lambda p: p[1])
        vmax = max(chunk, key=lambda p: p[1])
        # emit the two extremes in the order they occur (keeps the line shape honest)
        if chunk.index(vmin) <= chunk.index(vmax):
            pick = [vmin, vmax]
        else:
            pick = [vmax, vmin]
        for p in pick:
            if p != kept[-1]:
                kept.append(p)
    if pairs[-1] != kept[-1]:
        kept.append(pairs[-1])
    return kept


def _hash_id(kind, pairs, extra=""):
    """Per-instance suffix so gradient/clip ids never collide across charts on a page."""
    h = hashlib.md5()
    h.update(kind.encode())
    h.update(extra.encode())
    # a coarse fingerprint of the data is enough to disambiguate co-rendered charts
    for d, v in pairs[:: max(1, len(pairs) // 24)]:
        h.update(str(d).encode())
        h.update(f"{v:.4g}".encode())
    h.update(str(len(pairs)).encode())
    return h.hexdigest()[:8]


def _fmt(v, value_fmt):
    try:
        return value_fmt.format(v)
    except (ValueError, KeyError, IndexError):
        return f"{v:g}"


def _scale(pairs, height, *, baseline=None, reference=None, zero_floor=False):
    """Map (index, value) -> (x, y) in viewBox units. Returns (xy, y0, span, vmin, vmax).

    y0 is the pixel y of the baseline/zero (for splits + bar origins). Includes any
    baseline / reference level in the value range so the waterline is always on canvas.
    zero_floor pins the bottom of the range to 0 (for drawdown: 0 at top → underwater)."""
    xs = [p[1] for p in pairs]
    vmin, vmax = min(xs), max(xs)
    for extra in (baseline, reference):
        if extra is not None:
            vmin = min(vmin, extra)
            vmax = max(vmax, extra)
    if zero_floor:
        vmax = max(vmax, 0.0)
        vmin = min(vmin, 0.0)
    if vmax == vmin:
        vmax = vmin + 1.0
    pad = (vmax - vmin) * 0.08
    lo, hi = vmin - pad, vmax + pad
    top, bot = _PAD_T, height - _PAD_B
    n = len(pairs)

    def px(i):
        return 0.0 if n <= 1 else round(i / (n - 1) * _VBW, 2)

    def py(v):
        return round(bot - (v - lo) / (hi - lo) * (bot - top), 2)

    xy = [(px(i), py(v)) for i, (_d, v) in enumerate(pairs)]
    y0 = py(baseline if baseline is not None else 0.0)
    return xy, y0, (lo, hi, top, bot), vmin, vmax


def _path_len(xy):
    """Polyline length in viewBox units — drives the stroke-dash reveal (--ilx-len)."""
    tot = 0.0
    for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
        tot += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return round(tot, 1) or 1.0


def _d_line(xy):
    return "M" + " L".join(f"{x} {y}" for x, y in xy)


def _d_area(xy, y0):
    if not xy:
        return ""
    return (f"M{xy[0][0]} {y0} L"
            + " L".join(f"{x} {y}" for x, y in xy)
            + f" L{xy[-1][0]} {y0} Z")


def _corner_labels(pairs):
    """First / last ISO date as muted corner captions (dates are language-neutral)."""
    d0 = escape(str(pairs[0][0]))
    d1 = escape(str(pairs[-1][0]))
    return (f'<span class="ilx-d ilx-d0">{d0}</span>'
            f'<span class="ilx-d ilx-d1">{d1}</span>')


def _end_tag(last_v, value_fmt, unit_en, unit_zh):
    """End-value tag: last value + unit, bilingual via l-en/l-zh spans."""
    num = escape(_fmt(last_v, value_fmt))
    ue, uz = escape(unit_en or ""), escape(unit_zh if unit_zh is not None else (unit_en or ""))
    unit_html = ""
    if ue or uz:
        unit_html = (f'<span class="ilx-u">'
                     f'<span class="l-en">{ue}</span><span class="l-zh">{uz}</span></span>')
    return f'<span class="ilx-tag">{num}{unit_html}</span>'


def _null_fragment(accent, height, aria_en):
    """Honest null — hairline + plain-word 'No history yet' (house nulls-printed law)."""
    style = f"color:{escape(accent)};" if accent else ""
    aria = escape(aria_en or "No history yet")
    return (
        f'<figure class="ilx ilx-null" style="{style}--ilx-h:{int(height)}px" '
        f'role="img" aria-label="{aria}">'
        f'<svg viewBox="0 0 {int(_VBW)} {int(height)}" preserveAspectRatio="none" '
        f'aria-hidden="true"><line x1="0" y1="{height/2:.0f}" x2="{int(_VBW)}" '
        f'y2="{height/2:.0f}" class="ilx-hair"/></svg>'
        f'<span class="ilx-empty"><span class="l-en">No history yet</span>'
        f'<span class="l-zh">暂无历史</span></span>'
        f"</figure>"
    )


# --------------------------------------------------------------------------- #
# per-kind SVG bodies
# --------------------------------------------------------------------------- #
def _svg_line(xy, uid):
    """Plain single ink stroke + settle dot. (area/baseline/drawdown have own builders.)"""
    body = f'<path class="ilx-path" d="{_d_line(xy)}"/>'
    dot = f'<circle class="ilx-dot" cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="3.2"/>'
    return "", "", body, dot


def _svg_area(xy, y0, uid):
    grad = (f'<linearGradient id="ilxg-{uid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="currentColor" stop-opacity=".42"/>'
            f'<stop offset="1" stop-color="currentColor" stop-opacity="0"/>'
            f'</linearGradient>')
    veil = f'<path class="ilx-area" d="{_d_area(xy, y0)}" fill="url(#ilxg-{uid})"/>'
    body = f'<path class="ilx-path" d="{_d_line(xy)}"/>'
    dot = f'<circle class="ilx-dot" cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="3.2"/>'
    return grad, veil, body, dot


def _svg_baseline(xy, y0, uid, height):
    """THE signature: line + area dual-tinted --up above / --down below the waterline,
    split by two clipPaths at the baseline y, with a dashed waterline."""
    top_clip = f"ilxct-{uid}"   # everything above y0 (up)
    bot_clip = f"ilxcb-{uid}"   # everything below y0 (down)
    defs = (
        f'<clipPath id="{top_clip}"><rect x="0" y="0" width="{int(_VBW)}" height="{y0}"/></clipPath>'
        f'<clipPath id="{bot_clip}"><rect x="0" y="{y0}" width="{int(_VBW)}" height="{height - y0}"/></clipPath>'
        f'<linearGradient id="ilxgu-{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="var(--up)" stop-opacity=".40"/>'
        f'<stop offset="1" stop-color="var(--up)" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="ilxgd-{uid}" x1="0" y1="1" x2="0" y2="0">'
        f'<stop offset="0" stop-color="var(--down)" stop-opacity=".40"/>'
        f'<stop offset="1" stop-color="var(--down)" stop-opacity="0"/></linearGradient>'
    )
    area_d = _d_area(xy, y0)
    line_d = _d_line(xy)
    # define the area + line geometry once, reference via <use> for the clipped copies
    # (halves the fragment size vs emitting each big `d` string twice).
    defs += (f'<path id="ilxa-{uid}" d="{area_d}"/>'
             f'<path id="ilxl-{uid}" d="{line_d}"/>')
    veil = (
        f'<use href="#ilxa-{uid}" class="ilx-area" fill="url(#ilxgu-{uid})" clip-path="url(#{top_clip})"/>'
        f'<use href="#ilxa-{uid}" class="ilx-area" fill="url(#ilxgd-{uid})" clip-path="url(#{bot_clip})"/>'
    )
    # dashed waterline
    water = (f'<line class="ilx-water" x1="0" y1="{y0}" x2="{int(_VBW)}" y2="{y0}"/>')
    body = (
        f'<use href="#ilxl-{uid}" class="ilx-path ilx-up" clip-path="url(#{top_clip})"/>'
        f'<use href="#ilxl-{uid}" class="ilx-path ilx-down" clip-path="url(#{bot_clip})"/>'
    )
    last_up = xy[-1][1] <= y0
    dot = (f'<circle class="ilx-dot {"ilx-dot-up" if last_up else "ilx-dot-down"}" '
           f'cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="3.2"/>')
    return defs, veil + water, body, dot


def _svg_drawdown(xy, y0, uid, height):
    """0 pinned at the top; the underwater region fills downward in --down."""
    grad = (f'<linearGradient id="ilxg-{uid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="var(--down)" stop-opacity=".08"/>'
            f'<stop offset="1" stop-color="var(--down)" stop-opacity=".40"/></linearGradient>')
    veil = f'<path class="ilx-area" d="{_d_area(xy, y0)}" fill="url(#ilxg-{uid})"/>'
    water = f'<line class="ilx-water ilx-water-top" x1="0" y1="{y0}" x2="{int(_VBW)}" y2="{y0}"/>'
    body = f'<path class="ilx-path ilx-down" d="{_d_line(xy)}"/>'
    dot = f'<circle class="ilx-dot ilx-dot-down" cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="3.2"/>'
    return grad, veil + water, body, dot


def _svg_bars(pairs, height, uid, baseline):
    """Staggered rising bars. Sign-colored (--up/--down) when a baseline is given."""
    xy, y0, (lo, hi, top, bot), _vmin, _vmax = _scale(pairs, height, baseline=baseline)
    n = len(pairs)
    slot = _VBW / max(1, n)
    bw = max(1.2, slot * 0.62)
    signed = baseline is not None
    bars = []
    for i, (_d, v) in enumerate(pairs):
        cx = (i + 0.5) * slot
        x = round(cx - bw / 2, 2)
        yv = xy[i][1]
        if signed:
            up = v >= baseline
            top_y = min(yv, y0)
            h = abs(yv - y0)
            # up-bars grow from their bottom edge, down-bars from their top edge — both
            # edges sit on the waterline (CSS transform-origin, keyed on the -up/-down class)
            cls = "ilx-bar ilx-bar-up" if up else "ilx-bar ilx-bar-down"
        else:
            top_y = yv
            h = bot - yv
            cls = "ilx-bar"
        h = max(0.6, round(h, 2))
        bars.append(
            f'<rect class="{cls}" x={x!r} y="{round(top_y,2)}" width="{round(bw,2)}" '
            f'height="{h}" style="--i:{i}" rx="0.8"/>'
        )
    water = ""
    if signed:
        water = f'<line class="ilx-water" x1="0" y1="{y0}" x2="{int(_VBW)}" y2="{y0}"/>'
    return "", water + "".join(bars), "", ""


_MULTI_FALLBACK = ("var(--info)", "var(--orange)", "var(--warn)")


def _render_multi(series_list, *, height, value_fmt, max_points, aria_en, aria_zh,
                  baseline=None):
    """2-3 overlaid lines, per-series colors, HTML end-chips naming each line.

    `baseline` (optional): a value (e.g. 0 for signed regime scores) drawn as a
    faint dashed rule under the lines, so the eye reads each series above/below it.
    Included in the shared value range so the rule is always on canvas."""
    cleaned = []
    for s in series_list[:3]:
        pairs = _downsample(_clean(s.get("dates"), s.get("vals")), max_points)
        cleaned.append((s, pairs))
    valid = [(s, p) for s, p in cleaned if len(p) >= 4]
    if not valid:
        return _null_fragment(None, height, aria_en)

    # shared value range across all series so they read on one scale
    all_v = [v for _s, p in valid for _d, v in p]
    vmin, vmax = min(all_v), max(all_v)
    if baseline is not None:
        vmin, vmax = min(vmin, baseline), max(vmax, baseline)
    if vmax == vmin:
        vmax = vmin + 1.0
    pad = (vmax - vmin) * 0.08
    lo, hi = vmin - pad, vmax + pad
    top, bot = _PAD_T, height - _PAD_B
    uid = _hash_id("multi", valid[0][1], extra=str(len(valid)))

    # dashed baseline rule (drawn first, so the ink lands over it)
    base_svg = ""
    if baseline is not None:
        by = round(bot - (baseline - lo) / (hi - lo) * (bot - top), 2)
        base_svg = f'<line class="ilx-water" x1="0" y1="{by}" x2="{int(_VBW)}" y2="{by}"/>'

    paths, chips = [], []
    for k, (s, pairs) in enumerate(valid):
        color = s.get("color") or _MULTI_FALLBACK[k % len(_MULTI_FALLBACK)]
        n = len(pairs)
        xy = []
        for i, (_d, v) in enumerate(pairs):
            x = 0.0 if n <= 1 else round(i / (n - 1) * _VBW, 2)
            y = round(bot - (v - lo) / (hi - lo) * (bot - top), 2)
            xy.append((x, y))
        plen = _path_len(xy)
        paths.append(
            f'<path class="ilx-path ilx-m" d="{_d_line(xy)}" '
            f'style="stroke:{escape(color)};--ilx-len:{plen};--i:{k}"/>'
        )
        paths.append(
            f'<circle class="ilx-dot ilx-m" cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="2.8" '
            f'style="fill:{escape(color)};--i:{k}"/>'
        )
        le = escape(s.get("label_en", ""))
        lz = escape(s.get("label_zh", s.get("label_en", "")))
        chips.append(
            f'<span class="ilx-chip" style="--dot:{escape(color)}">'
            f'<span class="l-en">{le}</span><span class="l-zh">{lz}</span></span>'
        )

    dates0 = valid[0][1]
    corners = _corner_labels(dates0)
    aria = escape(aria_en or "Comparison chart")
    svg = (
        f'<svg viewBox="0 0 {int(_VBW)} {int(height)}" preserveAspectRatio="none" '
        f'aria-hidden="true">{base_svg}{"".join(paths)}</svg>'
    )
    return (
        f'<figure class="ilx ilx-multi" style="--ilx-h:{int(height)}px" '
        f'role="img" aria-label="{aria}">{svg}'
        f'<span class="ilx-chips">{"".join(chips)}</span>{corners}</figure>'
    )


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def illus(series, *, kind="line", accent=None, height=190, unit_en="", unit_zh=None,
          baseline=None, reference=None, bands=None, value_fmt="{:,.1f}",
          max_points=220, aria_en="", aria_zh=None) -> str:
    """Render a series as an ilx / Signal-Ink SVG+HTML fragment. See module docstring.

    Returns an HTML string (a <figure>). Never raises on bad data — an empty or
    too-short series returns the honest-null fragment."""
    height = int(height)

    if kind == "multi":
        return _render_multi(series or [], height=height, value_fmt=value_fmt,
                             max_points=max_points, aria_en=aria_en, aria_zh=aria_zh,
                             baseline=baseline)

    series = series or {}
    pairs = _downsample(_clean(series.get("dates"), series.get("vals")), max_points)
    if len(pairs) < 4:
        return _null_fragment(accent, height, aria_en)

    uid = _hash_id(kind, pairs, extra=f"{accent}{baseline}{reference}")

    if kind == "bars":
        defs, mid, _body, _dot = _svg_bars(pairs, height, uid, baseline)
        xy_for_len = []  # bars don't animate via dash
        plen = 1.0
        corners = _corner_labels(pairs)
        end = _end_tag(pairs[-1][1], value_fmt,
                       unit_en, unit_zh) if (unit_en or unit_zh) else ""
    else:
        zero_floor = (kind == "drawdown")
        xy, y0, _rng, vmin, vmax = _scale(
            pairs, height,
            baseline=(baseline if kind == "baseline" else None),
            reference=reference,
            zero_floor=zero_floor,
        )
        plen = _path_len(xy)
        if kind == "area":
            defs, mid, body, dot = _svg_area(xy, height - _PAD_B, uid)
        elif kind == "baseline":
            defs, mid, body, dot = _svg_baseline(xy, y0, uid, height)
        elif kind == "drawdown":
            # y0 = the 0% line (top of range); area fills from 0 down to the curve
            defs, mid, body, dot = _svg_drawdown(xy, y0, uid, height)
        else:  # "line"
            defs, mid, body, dot = _svg_line(xy, uid)
        end = _end_tag(pairs[-1][1], value_fmt, unit_en, unit_zh)
        corners = _corner_labels(pairs)

    # reference level marker (e.g. NBS climate neutral=100) as an HTML caption anchored
    # to its y — the SVG carries only a hairline; the number lives in HTML.
    ref_html = ""
    if reference is not None and kind not in ("bars", "baseline"):
        # y of the reference line as a % of height, for CSS top:
        _xy, _y0, (lo, hi, top, bot), _vm, _vx = _scale(
            pairs, height, reference=reference, zero_floor=(kind == "drawdown"))
        ry = round(bot - (reference - lo) / (hi - lo) * (bot - top), 2)
        ref_pct = round(ry / height * 100, 1)
        refnum = escape(_fmt(reference, "{:g}"))
        ref_html = (
            f'<line class="ilx-ref" x1="0" y1="{ry}" x2="{int(_VBW)}" y2="{ry}"/>'
        )
        # inject the ref line into the SVG defs stream (drawn under the path)
        mid = ref_html + mid
        ref_html = (f'<span class="ilx-reflab" style="top:{ref_pct}%">{refnum}</span>')

    # band zones (soft tints + corner labels) for the fear/euphoria gauge
    band_html = ""
    band_rects = ""
    if bands:
        _xy, _y0, (lo, hi, top, bot), _vm, _vx = _scale(pairs, height, reference=reference)
        for bd in bands:
            he = bd.get("hi")
            le = bd.get("lo")
            tint = bd.get("tint", "var(--muted)")
            y_hi = bot if he is None else round(bot - (he - lo) / (hi - lo) * (bot - top), 2)
            y_lo = top if le is None else round(bot - (le - lo) / (hi - lo) * (bot - top), 2)
            y_top = min(y_hi, y_lo)
            bh = abs(y_lo - y_hi)
            band_rects += (
                f'<rect class="ilx-band" x="0" y="{y_top}" width="{int(_VBW)}" '
                f'height="{round(bh,2)}" style="fill:{escape(tint)}"/>'
            )
            lbl_en = escape(bd.get("label_en", ""))
            lbl_zh = escape(bd.get("label_zh", bd.get("label_en", "")))
            pos = bd.get("pos", "top")  # "top" | "bottom"
            if lbl_en:
                band_html += (
                    f'<span class="ilx-bandlab ilx-bandlab-{pos}">'
                    f'<span class="l-en">{lbl_en}</span>'
                    f'<span class="l-zh">{lbl_zh}</span></span>'
                )
        mid = band_rects + mid  # bands sit UNDER the ink

    style = (f"color:{escape(accent)};" if accent else "") + f"--ilx-len:{plen};--ilx-h:{height}px"
    aria = escape(aria_en or f"{kind} chart")
    svg = (
        f'<svg viewBox="0 0 {int(_VBW)} {height}" preserveAspectRatio="none" '
        f'aria-hidden="true"><defs>{defs}</defs>{mid}{body if kind != "bars" else ""}'
        f'{dot if kind != "bars" else ""}</svg>'
    )
    return (
        f'<figure class="ilx ilx-{escape(kind)}" style="{style}" '
        f'role="img" aria-label="{aria}">{svg}{band_html}{ref_html}{corners}{end}</figure>'
    )
