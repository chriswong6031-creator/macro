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
import math
import re
from datetime import date, datetime
from html import escape

__all__ = ["illus", "regime_tape", "session_filmstrip"]

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


def _date_number(value):
    """ISO-ish date/datetime -> ordinal float, or None when it cannot be parsed.

    Regime Tape x geometry is calendar-based, never kept-point-position based.
    Keeping this helper stdlib-only preserves ilx's dependency-free contract.
    """
    if isinstance(value, datetime):
        seconds = (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        )
        return float(value.date().toordinal()) + seconds / 86400.0
    if isinstance(value, date):
        return float(value.toordinal())
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) >= 10:
        try:
            return float(date.fromisoformat(raw[:10]).toordinal())
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() / 86400.0
    except (TypeError, ValueError, OSError):
        return None


def _date_x(value, start, end):
    """Map a date to the fixed ilx viewBox using elapsed calendar time."""
    dv, d0, d1 = _date_number(value), _date_number(start), _date_number(end)
    if dv is None or d0 is None or d1 is None or d1 <= d0:
        return None
    return round(max(0.0, min(1.0, (dv - d0) / (d1 - d0))) * _VBW, 2)


def _d_step(xy):
    """Horizontal-then-vertical step path for allocation ribbons."""
    if not xy:
        return ""
    out = [f"M{xy[0][0]} {xy[0][1]}"]
    for x, y in xy[1:]:
        out.append(f"H{x} V{y}")
    return " ".join(out)


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
# Regime Tape — Bitcoin/Crypto cockpit signature
# --------------------------------------------------------------------------- #
def regime_tape(price, *, allocation=None, regimes=None, events=None, projection=None,
                height=250, max_points=220, accent="var(--btc, #F7931A)",
                value_fmt="${:,.0f}", aria_en="Bitcoin price, regime and allocation",
                aria_zh=None) -> str:
    """Render the cockpit's signature price/regime/allocation tape.

    The four additive forms are deliberately one cohesive API:
      * calendar-true regime spans behind the price path;
      * a final-series allocation step ribbon (``alloc_optimal`` at call sites);
      * baseline event ticks with bilingual HTML receipts; and
      * an optional hatched projection window.

    ``price`` / ``allocation`` follow the ordinary ``{"dates", "vals"}`` shape.
    ``regimes`` is a list of ``{start, end, tone}`` dictionaries, where tone is one
    of bull/bear/neutral/watch. ``events`` carries ``date`` plus label_en/label_zh.
    ``projection`` carries start/end plus optional label_en/label_zh.

    X coordinates are elapsed calendar time across the complete domain, including
    the forward window when present. They never use kept-point index, so the ilx
    extreme-preserving downsampler cannot move a halving/event marker by several
    days on a multi-year tape.
    """
    height = int(height)
    pairs_all = _clean((price or {}).get("dates"), (price or {}).get("vals"))
    if len(pairs_all) < 4:
        return _null_fragment(accent, height, aria_en)

    pairs = _downsample(pairs_all, max_points)
    domain_start = pairs_all[0][0]
    domain_end = pairs_all[-1][0]
    if projection and _date_number(projection.get("end")) is not None:
        if _date_number(projection.get("end")) > _date_number(domain_end):
            domain_end = projection.get("end")

    chart_top = _PAD_T
    ribbon_top = max(chart_top + 48.0, height - 52.0)
    chart_bot = ribbon_top - 10.0
    ribbon_bot = height - 18.0

    # Price uses a log scale when values are strictly positive. Crypto spans are
    # multiplicative; log geometry keeps early years visible without changing labels.
    raw_vals = [v for _d, v in pairs]
    use_log = all(v > 0 for v in raw_vals)
    scaled_vals = [(math.log(v) if use_log else v) for v in raw_vals]
    vmin, vmax = min(scaled_vals), max(scaled_vals)
    if vmax == vmin:
        vmax = vmin + 1.0
    pad = (vmax - vmin) * 0.08
    lo, hi = vmin - pad, vmax + pad

    def py(v):
        sv = math.log(v) if use_log else v
        return round(chart_bot - (sv - lo) / (hi - lo) * (chart_bot - chart_top), 2)

    xy = []
    for d, v in pairs:
        x = _date_x(d, domain_start, domain_end)
        if x is not None:
            xy.append((x, py(v)))
    if len(xy) < 4:
        return _null_fragment(accent, height, aria_en)

    uid = _hash_id("regime-tape", pairs, extra=f"{domain_end}{height}")
    price_d = _d_line(xy)
    plen = _path_len(xy)

    tone_color = {
        "bull": "var(--up)", "bear": "var(--down)",
        "neutral": "var(--muted)", "watch": "var(--warn)",
    }
    span_svg = []
    for rg in regimes or []:
        x0 = _date_x(rg.get("start"), domain_start, domain_end)
        x1 = _date_x(rg.get("end"), domain_start, domain_end)
        if x0 is None or x1 is None or x1 <= x0:
            continue
        tone = str(rg.get("tone") or "neutral").lower()
        color = tone_color.get(tone, "var(--muted)")
        span_svg.append(
            f'<rect class="ilx-regime-span ilx-regime-{escape(tone)}" '
            f'x="{x0}" y="{chart_top}" width="{round(x1 - x0, 2)}" '
            f'height="{round(chart_bot - chart_top, 2)}" style="fill:{color}"/>'
        )

    projection_defs = ""
    projection_rect = ""
    projection_html = ""
    if projection:
        x0 = _date_x(projection.get("start"), domain_start, domain_end)
        x1 = _date_x(projection.get("end"), domain_start, domain_end)
        if x0 is not None and x1 is not None and x1 > x0:
            projection_defs = (
                f'<pattern id="ilxhat-{uid}" width="8" height="8" '
                f'patternUnits="userSpaceOnUse" patternTransform="rotate(35)">'
                f'<line class="ilx-projection-hatch" x1="0" y1="0" x2="0" y2="8"/>'
                f'</pattern>'
            )
            projection_rect = (
                f'<rect class="ilx-projection" x="{x0}" y="{chart_top}" '
                f'width="{round(x1 - x0, 2)}" height="{round(chart_bot - chart_top, 2)}" '
                f'fill="url(#ilxhat-{uid})"/>'
            )
            le = escape(projection.get("label_en") or "Projection window")
            lz = escape(projection.get("label_zh") or "观察窗口")
            projection_html = (
                f'<span class="ilx-projection-label" style="--x:{round(x0 / _VBW * 100, 2)}%">'
                f'<span class="l-en">{le}</span><span class="l-zh">{lz}</span></span>'
            )

    alloc_svg = ""
    alloc_html = ""
    alloc_pairs = _clean((allocation or {}).get("dates"), (allocation or {}).get("vals"))
    if alloc_pairs:
        # Allocation is already bounded by its engine contract; clamp only for drawing.
        alloc_xy = []
        last_val = None
        for d, v in alloc_pairs:
            x = _date_x(d, domain_start, domain_end)
            if x is None:
                continue
            cv = max(0.0, min(1.0, v))
            if last_val is None or cv != last_val or d == alloc_pairs[-1][0]:
                y = round(ribbon_bot - cv * (ribbon_bot - ribbon_top), 2)
                alloc_xy.append((x, y))
                last_val = cv
        if len(alloc_xy) >= 2:
            step_d = _d_step(alloc_xy)
            fill_d = (f'M{alloc_xy[0][0]} {ribbon_bot} '
                      f'L{alloc_xy[0][0]} {alloc_xy[0][1]} '
                      + " ".join(
                          f"H{x} V{y}" for x, y in alloc_xy[1:]
                      )
                      + f' L{alloc_xy[-1][0]} {ribbon_bot} Z')
            alloc_svg = (
                f'<line class="ilx-alloc-base" x1="0" y1="{ribbon_bot}" '
                f'x2="{int(_VBW)}" y2="{ribbon_bot}"/>'
                f'<path class="ilx-alloc-fill" d="{fill_d}"/>'
                f'<path class="ilx-alloc-step" d="{step_d}"/>'
            )
            latest = round(max(0.0, min(1.0, alloc_pairs[-1][1])) * 100)
            alloc_html = (
                f'<span class="ilx-alloc-label"><span class="l-en">Model exposure</span>'
                f'<span class="l-zh">模型仓位</span> · {latest}%</span>'
            )

    event_svg = []
    event_html = []
    for ev in events or []:
        x = _date_x(ev.get("date"), domain_start, domain_end)
        if x is None:
            continue
        le = escape(ev.get("label_en") or str(ev.get("date") or "Event"))
        lz = escape(ev.get("label_zh") or ev.get("label_en") or str(ev.get("date") or "事件"))
        pct = round(x / _VBW * 100, 2)
        event_svg.append(
            f'<line class="ilx-event-tick" x1="{x}" y1="{chart_bot}" '
            f'x2="{x}" y2="{ribbon_bot}"/>'
        )
        event_html.append(
            f'<span class="ilx-event" style="--x:{pct}%" tabindex="0" role="note" '
            f'data-tip-en="{le}" data-tip-zh="{lz}" aria-label="{le}"><i></i></span>'
        )

    end_tag = _end_tag(pairs_all[-1][1], value_fmt, "", "")
    corners = (
        f'<span class="ilx-d ilx-d0">{escape(str(pairs_all[0][0]))}</span>'
        f'<span class="ilx-d ilx-d1">{escape(str(domain_end))}</span>'
    )
    aria = escape(aria_en or "Regime tape")
    svg = (
        f'<svg viewBox="0 0 {int(_VBW)} {height}" preserveAspectRatio="none" '
        f'aria-hidden="true"><defs>{projection_defs}</defs>'
        f'{"".join(span_svg)}{projection_rect}'
        f'<path class="ilx-path ilx-tape-price" d="{price_d}"/>'
        f'<circle class="ilx-dot ilx-tape-dot" cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="3.2"/>'
        f'{alloc_svg}{"".join(event_svg)}</svg>'
    )
    return (
        f'<figure class="ilx ilx-regime-tape" '
        f'style="color:{escape(accent)};--ilx-len:{plen};--ilx-h:{height}px" '
        f'role="img" aria-label="{aria}">{svg}{end_tag}{alloc_html}'
        f'{"".join(event_html)}{projection_html}{corners}</figure>'
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


# --------------------------------------------------------------------------- #
# Session filmstrip — OIP W1 estate-wide signature (research/options_estate/
# W1_DESIGN_SPEC.md §3). One session's net-premium path across the session
# window, with tick marks where structure events fired.
#
# WHY THIS IS AN SSR FRAGMENT, NOT A CLIENT FETCH-AND-DRAW: the figure is
# rendered ONCE, here, at nightly build time (scripts/build_session_digest.py,
# per (record) it just built), and shipped as a field inside
# site/session/<ROOT>.json. Every client-side home (Ticker mode, gex.html,
# eventually Brief mode) fetches that JSON and drops the ready-made HTML string
# in via innerHTML — never recomputing geometry in JS. Same "SSR SVG, never
# Plotly, never re-derived client-side" law as every other ilx chart.
#
# Ink is ALWAYS --oew-accent (structure), hardcoded — never a caller-supplied
# accent. The arc's sign (call-heavy vs put-heavy premium) is not one of the
# two sanctioned direction instruments (tape_flow, ΔOI), so it may never be
# colored --up/--down; making the accent a fixed constant here, rather than a
# parameter, makes that law impossible for a call site to violate by accident.
# --------------------------------------------------------------------------- #
_FILM_H = 64.0        # the two W1 client-rendered homes both pin height:64px
_FILM_Y_TOP = 10.0     # ink/tick vertical bounds, pinned by W1_DESIGN_SPEC §3.3
_FILM_Y_BOT = 54.0     # (NOT the generic _PAD_T/_PAD_B — this is its own contract)
_FILM_ACCENT = "var(--oew-accent)"
_FILM_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _film_hhmm_window(window_label):
    """'09:30–16:00 ET' -> (open_min, close_min) minutes-since-midnight, or None.

    Reads whatever two HH:MM tokens are in the label (session_digest.session_window_
    label's own format, en-dash separated) rather than assuming a literal '09:30' /
    '16:00' — early-close sessions (13:00 ET) must degrade honestly too, not draw a
    normal day's geometry against an abbreviated one.
    """
    m = _FILM_TIME_RE.findall(str(window_label or ""))
    if len(m) < 2:
        return None
    try:
        open_min = int(m[0][0]) * 60 + int(m[0][1])
        close_min = int(m[1][0]) * 60 + int(m[1][1])
    except ValueError:
        return None
    if close_min <= open_min:
        return None
    return open_min, close_min


def _film_corner_labels(window_label):
    m = _FILM_TIME_RE.findall(str(window_label or ""))
    if len(m) < 2:
        return "", ""
    return f"{int(m[0][0]):02d}:{m[0][1]}", f"{int(m[1][0]):02d}:{m[1][1]}"


def _film_x(t_label, open_min, close_min):
    """Elapsed-session-time x, [0, 560] — NEVER array-index spacing (index spacing
    would silently misrepresent a mid-session gap as compressed time)."""
    m = _FILM_TIME_RE.search(str(t_label or ""))
    if not m:
        return None
    total = int(m.group(1)) * 60 + int(m.group(2))
    frac = (total - open_min) / (close_min - open_min)
    return round(max(0.0, min(1.0, frac)) * _VBW, 2)


def _film_y(v, vmin, vmax):
    """`net` scaled to its own min/max within [_FILM_Y_TOP, _FILM_Y_BOT] — a SHAPE,
    never an absolute value axis (no gridlines, no y-axis labels)."""
    if vmax == vmin:
        return round((_FILM_Y_TOP + _FILM_Y_BOT) / 2.0, 2)
    frac = (v - vmin) / (vmax - vmin)
    return round(_FILM_Y_BOT - frac * (_FILM_Y_BOT - _FILM_Y_TOP), 2)


def _film_null(coverage: dict) -> str:
    """Honest-null variant: no ink, no ticks, no dot — only the flat track and the
    session's own composed absence sentence (coverage.quality_en/zh, verbatim)."""
    coverage = coverage if isinstance(coverage, dict) else {}
    en = escape(str(coverage.get("quality_en") or "No intraday record for this session"))
    zh = escape(str(coverage.get("quality_zh") or "本交易日没有盘中记录"))
    vb = int(_VBW)
    return (
        f'<figure class="ilx oew-film oew-film-null" role="img" aria-label="{en}" '
        f'style="color:{_FILM_ACCENT};--ilx-h:{int(_FILM_H)}px">'
        f'<svg viewBox="0 0 {vb} {int(_FILM_H)}" preserveAspectRatio="none" aria-hidden="true">'
        f'<line class="oew-film-track" x1="0" y1="32" x2="{vb}" y2="32"/>'
        f'<line class="oew-film-closecap" x1="{vb}" y1="14" x2="{vb}" y2="50"/>'
        f"</svg>"
        f'<span class="oew-film-empty"><span class="l-en">{en}</span>'
        f'<span class="l-zh">{zh}</span></span>'
        f"</figure>"
    )


def session_filmstrip(record: dict) -> str:
    """Render the OIP W1 session filmstrip figure for one `options_session.v1`
    record (engine/session_digest.py). Returns the `<figure>` markup ONLY — the
    surrounding panel chrome (title, footer sentence, as-of) is the caller's job;
    this function draws the figure and nothing else (W1_DESIGN_SPEC.md §3.3).

    Pure function, never raises: degrades to the honest-null variant whenever
    `coverage.minutes` is 0, the session window can't be parsed, or the arc is too
    short to draw a shape (defensive beyond the spec's literal minutes==0 check —
    a malformed non-empty arc must not emit a broken SVG path).
    """
    record = record if isinstance(record, dict) else {}
    coverage = record.get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    try:
        minutes = int(coverage.get("minutes") or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return _film_null(coverage)

    window = _film_hhmm_window(coverage.get("session_window_et"))
    raw_arc = record.get("arc")
    arc = ([row for row in raw_arc if isinstance(row, dict)]
           if isinstance(raw_arc, (list, tuple)) else [])
    if window is None or len(arc) < 2:
        return _film_null(coverage)
    open_min, close_min = window

    pts = []
    for row in arc:
        x = _film_x(row.get("t"), open_min, close_min)
        v = row.get("net")
        if x is None or v is None:
            continue
        try:
            pts.append((x, float(v)))
        except (TypeError, ValueError):
            continue
    if len(pts) < 2:
        return _film_null(coverage)

    vmin = min(v for _x, v in pts)
    vmax = max(v for _x, v in pts)
    xy = [(x, _film_y(v, vmin, vmax)) for x, v in pts]
    dot_x, dot_y = xy[-1]

    raw_events = record.get("events")
    events = raw_events if isinstance(raw_events, (list, tuple)) else []
    tick_svg, ev_html = [], []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        x = _film_x(ev.get("t"), open_min, close_min)
        en = str(ev.get("label_en") or "")
        if x is None or not en:
            continue
        zh = str(ev.get("label_zh") or en)
        en_e, zh_e = escape(en), escape(zh)
        pct = round(x / _VBW * 100, 2)
        tick_svg.append(
            f'<line class="ilx-event-tick oew-film-tick" x1="{x}" y1="{_FILM_Y_TOP:g}" '
            f'x2="{x}" y2="{_FILM_Y_BOT:g}"/>'
        )
        ev_html.append(
            f'<span class="ilx-event oew-film-ev" style="--x:{pct}%" tabindex="0" role="note" '
            f'data-tip-en="{en_e}" data-tip-zh="{zh_e}" aria-label="{en_e}"><i></i></span>'
        )

    open_lbl, close_lbl = _film_corner_labels(coverage.get("session_window_et"))
    n_ev = len(ev_html)
    aria = escape(f"Session premium arrival, {n_ev} event{'' if n_ev == 1 else 's'}")
    vb = int(_VBW)

    svg = (
        f'<svg viewBox="0 0 {vb} {int(_FILM_H)}" preserveAspectRatio="none" aria-hidden="true">'
        f'<line class="oew-film-track" x1="0" y1="32" x2="{vb}" y2="32"/>'
        f'<line class="oew-film-closecap" x1="{vb}" y1="14" x2="{vb}" y2="50"/>'
        f'<path class="ilx-path oew-film-ink" d="{_d_line(xy)}"/>'
        f'<circle class="ilx-dot oew-film-dot" cx="{dot_x}" cy="{dot_y}" r="3.2"/>'
        + "".join(tick_svg)
        + "</svg>"
    )
    return (
        f'<figure class="ilx oew-film" role="img" aria-label="{aria}" '
        f'style="color:{_FILM_ACCENT};--ilx-len:{_path_len(xy)};--ilx-h:{int(_FILM_H)}px">'
        f"{svg}"
        f'<span class="oew-film-d oew-film-d0 mono">{escape(open_lbl)}</span>'
        f'<span class="oew-film-d oew-film-d1 mono">{escape(close_lbl)}</span>'
        + "".join(ev_html)
        + "</figure>"
    )
