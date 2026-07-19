"""engine.marketing.share_cards — og:image share cards for Mastermind pages.

These 1200×630 PNGs are what X / Slack / Discord / WeChat unfurls render when a
Mastermind link is shared — the brand's face in a feed. Rendered with Pillow only
(no SVG, no cairosvg): flat-color fills + gradients drawn directly with PIL so the
output compresses small and reproduces byte-for-byte.

Public API (builders call this):
    CARD_W, CARD_H = 1200, 630
    CARD_VERSION                       -> int   (bump forces full regen)
    load_font(size, *, bold=False)     -> ImageFont  (never raises)
    render_ticker_card(...)            -> Image   (static identity card)
    render_movers_card(...)            -> Image   (daily gainers/losers)
    render_screener_card(...)          -> Image   (free signal-stack screener)
    save_card(img, out_path)           -> None    (optimized PNG, ≤ ~80 KB)
    card_fingerprint(payload)          -> str     (sha1 over version + payload)
    save_card_if_changed(...)          -> bool    (fingerprint-store skip)

Design (brand-locked; matches engine.marketing.chart_render):
  - Base navy #0E1420, header band #0A1020, panels #141C2E.
  - Mastermind logomark: gradient tile #5b9dff→#3b82f6→#6366f1→#7c5cff + white
    ascending-peak "M" — drawn directly with PIL. Wordmark weight-900.
  - Directional green #4CAF50 / red #E23B3B. Footer URL mastermind-x.com in #7f97c4.
  - Signature: a faint edge-to-edge "peak line" (the logomark's up-down-up
    silhouette blown up to card scale) + a thin left gradient brand rail + a soft
    gradient corner-wash from the brand lockup. Same frame on all three cards.

Honesty (DESIGN_DOCTRINE §Law 5): cards never overclaim. The word "validated" is
banned. The screener card carries "historical win rate — not a guarantee".

No network calls anywhere. Pure deterministic renders (same payload → same pixels):
no now-timestamps, no randomness.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CARD_W, CARD_H = 1200, 630
CARD_VERSION = 1  # bump forces full regen across the fingerprint store

MARGIN = 64  # generous safe margin — unfurl crops can shave edges

# Brand palette (locked to chart_render.py)
BG = (14, 20, 32)            # #0E1420 base navy
HEADER = (10, 16, 32)        # #0A1020 header band
PANEL = (20, 28, 46)         # #141C2E raised panel
PANEL_HI = (26, 36, 58)      # slightly lighter panel
INK = (255, 255, 255)        # white
MUTED = (136, 153, 187)      # #8899bb muted label
FAINT = (127, 151, 196)      # #7f97c4 brand-URL blue-grey
HAIRLINE = (35, 42, 61)      # #232A3D dividers
UP = (76, 175, 80)           # #4CAF50 green
DOWN = (226, 59, 59)         # #E23B3B red

# Gradient tile stops (logomark)
TILE_STOPS = [
    (0.00, (91, 157, 255)),   # #5b9dff
    (0.42, (59, 130, 246)),   # #3b82f6
    (0.74, (99, 102, 241)),   # #6366f1
    (1.00, (124, 92, 255)),   # #7c5cff
]

BRAND_URL = "mastermind-x.com"


# ─────────────────────────────────────────────────────────────────────────────
# Font loader — macOS system fonts first (nightly runs on a Mac Studio), then
# Linux DejaVu (CI), then PIL default. MUST never raise.
# ─────────────────────────────────────────────────────────────────────────────

# SFNS variable-font named instances we want per weight.
_SFNS_INSTANCE = {False: "Regular", True: "Heavy"}

# (path, index, variation_name) candidate chains. index=None → non-collection.
_FONT_CHAIN_BOLD = [
    ("/System/Library/Fonts/SFNS.ttf", None, "Heavy"),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1, None),      # Bold
    ("/System/Library/Fonts/Helvetica.ttc", 1, None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None, None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None, None),
    ("DejaVuSans-Bold.ttf", None, None),  # PIL-bundled name
]
_FONT_CHAIN_REG = [
    ("/System/Library/Fonts/SFNS.ttf", None, "Regular"),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0, None),      # Regular
    ("/System/Library/Fonts/Helvetica.ttc", 0, None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None, None),
    ("DejaVuSans.ttf", None, None),  # PIL-bundled name
]


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Return a TrueType font at *size*. Never raises — falls back all the way to
    PIL's built-in default (which has no size, but keeps callers alive on any host).
    """
    size = max(1, int(size))
    chain = _FONT_CHAIN_BOLD if bold else _FONT_CHAIN_REG
    for path, index, variation in chain:
        try:
            if index is not None:
                font = ImageFont.truetype(path, size, index=index)
            else:
                font = ImageFont.truetype(path, size)
            if variation is not None:
                try:
                    font.set_variation_by_name(variation)
                except Exception:  # noqa: BLE001 — not a variable font; plain weight is fine
                    pass
            return font
        except Exception:  # noqa: BLE001 — try the next candidate
            continue
    # Absolute last resort — PIL's embedded bitmap font. Never raises.
    try:
        return ImageFont.load_default(size=size)  # Pillow ≥10 accepts size
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


# ─────────────────────────────────────────────────────────────────────────────
# Low-level draw helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _grad_color(stops: list[tuple[float, tuple[int, int, int]]], t: float) -> tuple[int, int, int]:
    """Sample a multi-stop gradient at position t∈[0,1]."""
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            span = (p1 - p0) or 1.0
            f = (t - p0) / span
            return (
                int(round(_lerp(c0[0], c1[0], f))),
                int(round(_lerp(c0[1], c1[1], f))),
                int(round(_lerp(c0[2], c1[2], f))),
            )
    return stops[-1][1]


def _diag_gradient_tile(size: int, stops: list[tuple[float, tuple[int, int, int]]]) -> Image.Image:
    """Render a square diagonal (top-left→bottom-right) gradient tile, RGBA."""
    tile = Image.new("RGB", (size, size))
    px = tile.load()
    denom = (2 * (size - 1)) or 1
    for y in range(size):
        for x in range(size):
            t = (x + y) / denom
            px[x, y] = _grad_color(stops, t)
    return tile.convert("RGBA")


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """1-channel rounded-rect mask for compositing a rounded tile."""
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    l, _, r, _ = draw.textbbox((0, 0), text, font=font)
    return r - l


def _tracked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    *,
    tracking: float = 0.0,
    anchor: str = "la",
) -> float:
    """Draw text with manual letter-spacing (PIL has none). Returns total width.

    anchor: "la" left, "ma" center, "ra" right (top-aligned). Vertical anchor is
    always top ("a") — callers position by top-left/top-center/top-right.
    """
    if tracking == 0.0:
        draw.text(xy, text, font=font, fill=fill, anchor="la" if anchor == "la"
                  else ("ma" if anchor == "ma" else "ra"))
        return _text_w(draw, text, font)
    # Manual tracking: measure total, then place per-glyph left-to-right.
    widths = [_text_w(draw, ch, font) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x0 = xy[0]
    if anchor == "ma":
        x0 = xy[0] - total / 2
    elif anchor == "ra":
        x0 = xy[0] - total
    cx = x0
    for ch, w in zip(text, widths):
        draw.text((cx, xy[1]), ch, font=font, fill=fill, anchor="la")
        cx += w + tracking
    return total


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    bold: bool,
    max_w: float,
    start: int,
    min_size: int = 12,
    tracking: float = 0.0,
) -> ImageFont.FreeTypeFont:
    """Largest font ≤ start whose text (with tracking) fits max_w. Never below min_size."""
    size = start
    while size > min_size:
        font = load_font(size, bold=bold)
        w = _text_w(draw, text, font) + tracking * max(0, len(text) - 1)
        if w <= max_w:
            return font
        size -= 2
    return load_font(min_size, bold=bold)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: float) -> str:
    """Ellipsis-truncate to fit max_w."""
    if _text_w(draw, text, font) <= max_w:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + ell
        if _text_w(draw, cand, font) <= max_w:
            lo = mid + 1
        else:
            hi = mid
    return (text[: max(0, lo - 1)].rstrip() + ell) if lo > 0 else ell


# ─────────────────────────────────────────────────────────────────────────────
# Brand frame — the shared identity every card wears
# ─────────────────────────────────────────────────────────────────────────────

def _peak_points(width: int, baseline: float, amp: float) -> list[tuple[float, float]]:
    """The logomark's ascending up-down-up 'M' peak silhouette, stretched edge to
    edge. Five vertices: low-left, high, dip, higher-right, low. This is the
    signature motif — an abstract brand mark, never data.
    """
    return [
        (0.00 * width, baseline),
        (0.28 * width, baseline - amp * 0.72),
        (0.50 * width, baseline - amp * 0.30),
        (0.74 * width, baseline - amp * 1.00),
        (1.00 * width, baseline - amp * 0.44),
    ]


def _draw_frame(img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """Paint the shared brand frame: base fill, top-left corner wash, edge-to-edge
    peak-line watermark, and the left gradient brand rail. Content draws on top.
    """
    # Base fill.
    draw.rectangle([0, 0, CARD_W, CARD_H], fill=BG)

    # Soft top-left corner wash (radial-ish bloom in brand blue) — additive layer.
    wash = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wash)
    cx, cy = 90, 70
    max_r = 620
    for r in range(max_r, 0, -14):
        t = r / max_r
        # brand blue #3b82f6 fading out
        alpha = int(46 * (1 - t) ** 2)
        if alpha <= 0:
            continue
        wd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(59, 130, 246, alpha))
    img.paste(Image.alpha_composite(img.convert("RGBA"), wash).convert(img.mode), (0, 0))
    # Re-bind draw to the mutated image content (paste replaced pixels in place).

    # Edge-to-edge peak-line watermark (the signature). Two echoes for depth.
    # Kept low + faint so it reads as an ambient brand mark behind content, never
    # competing with the text band that lives in the card's vertical middle.
    peak_layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(peak_layer)
    for baseline, amp, rgb, a, wdt in [
        (CARD_H * 1.02, CARD_H * 0.60, (91, 157, 255), 20, 3),   # far echo, cool blue
        (CARD_H * 1.10, CARD_H * 0.72, (124, 92, 255), 26, 4),   # near, violet
    ]:
        pts = _peak_points(CARD_W, baseline, amp)
        pd.line(pts, fill=(*rgb, a), width=wdt, joint="curve")
        # vertex glow dots
        for (vx, vy) in pts[1:4]:
            pd.ellipse([vx - 5, vy - 5, vx + 5, vy + 5], fill=(*rgb, a + 14))
    composite = Image.alpha_composite(img.convert("RGBA"), peak_layer).convert(img.mode)
    img.paste(composite, (0, 0))

    # Left gradient brand rail (thin vertical bar, tile-gradient top→bottom).
    rail_w = 8
    rail = Image.new("RGB", (rail_w, CARD_H))
    rpx = rail.load()
    for y in range(CARD_H):
        col = _grad_color(TILE_STOPS, y / (CARD_H - 1))
        for x in range(rail_w):
            rpx[x, y] = col
    img.paste(rail, (0, 0))


def _draw_logomark(img: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float) -> None:
    """Draw the Mastermind gradient tile + white ascending-M, centered at (cx,cy)."""
    s = int(round(size))
    x0 = int(round(cx - s / 2))
    y0 = int(round(cy - s / 2))
    radius = int(round(s * 10.5 / 40.0))

    tile = _diag_gradient_tile(s, TILE_STOPS)
    # Top sheen: white→transparent vertical wash over the top ~55%.
    sheen = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    spx = sheen.load()
    for y in range(s):
        t = y / (s - 1)
        a = int(max(0.0, (1 - t / 0.55)) * 78) if t < 0.55 else 0
        for x in range(s):
            spx[x, y] = (255, 255, 255, a)
    tile = Image.alpha_composite(tile, sheen)

    mask = _rounded_mask((s, s), radius)
    img.paste(tile, (x0, y0), mask)

    # Ascending-M path (viewBox 2..38 → mapped into tile), white, round joins.
    scale = s / 40.0

    def sp(o: float) -> float:
        return (o - 2) * scale + x0

    def sq(o: float) -> float:
        return (o - 2) * scale + y0

    m_pts = [
        (sp(13), sq(28)), (sp(13), sq(14.5)), (sp(20), sq(22)),
        (sp(27), sq(12.5)), (sp(27), sq(28)),
    ]
    sw = max(2, int(round(s * 3.3 / 40.0)))
    # subtle drop shadow
    shadow = [(px, py + max(1, sw * 0.32)) for (px, py) in m_pts]
    draw.line(shadow, fill=(21, 32, 90), width=sw, joint="curve")
    draw.line(m_pts, fill=INK, width=sw, joint="curve")
    # round the vertices (PIL line joins are square-ish at sharp angles)
    for (px, py) in m_pts:
        r = sw / 2
        draw.ellipse([px - r, py - r, px + r, py + r], fill=INK)


def _draw_brand_lockup(img: Image.Image, draw: ImageDraw.ImageDraw, top_y: int) -> int:
    """Top-left lockup: logomark tile + MASTERMIND wordmark (weight-900, tracked).
    Returns the baseline y used, so callers can place a hairline under it.
    """
    tile = 52
    cx = MARGIN + tile / 2
    cy = top_y + tile / 2
    _draw_logomark(img, draw, cx, cy, tile)
    word_font = load_font(34, bold=True)
    wx = MARGIN + tile + 20
    # vertically center wordmark cap-height against tile
    wy = top_y + (tile - 34) / 2 - 2
    _tracked_text(draw, (wx, wy), "MASTERMIND", word_font, INK, tracking=2.4)
    return top_y + tile


def _draw_footer(img: Image.Image, draw: ImageDraw.ImageDraw, *, tagline: str | None = None) -> None:
    """Bottom band: brand URL (left, prominent) + copyright (right). Optional
    accent-tinted tagline pill sits just above the URL.
    """
    base_y = CARD_H - MARGIN
    # hairline above footer
    draw.line([(MARGIN, base_y - 46), (CARD_W - MARGIN, base_y - 46)], fill=HAIRLINE, width=1)

    if tagline:
        pill_font = load_font(19)
        pw = _text_w(draw, tagline, pill_font)
        px0, py0 = MARGIN, base_y - 40
        pill_w, pill_h = pw + 34, 34
        # tinted rounded pill
        pill = Image.new("RGBA", (int(pill_w), pill_h), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pd.rounded_rectangle([0, 0, pill_w - 1, pill_h - 1], radius=pill_h // 2,
                             fill=(59, 130, 246, 40), outline=(91, 157, 255, 120), width=1)
        img.paste(Image.alpha_composite(
            img.convert("RGBA").crop((px0, py0, px0 + int(pill_w), py0 + pill_h)), pill
        ).convert(img.mode), (px0, py0))
        draw.text((px0 + 17, py0 + pill_h / 2), tagline, font=pill_font,
                  fill=(157, 184, 232), anchor="lm")

    url_font = load_font(30, bold=True)
    draw.text((MARGIN, base_y), BRAND_URL, font=url_font, fill=FAINT, anchor="ls")
    cr_font = load_font(18)
    draw.text((CARD_W - MARGIN, base_y - 4), "© 2026 Mastermind",
              font=cr_font, fill=(58, 68, 102), anchor="rs")


def _new_card() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)
    _draw_frame(img, draw)
    # _draw_frame paste-mutated img in place; the existing draw handle still
    # targets the same Image object, so it stays valid. Return both.
    return img, draw


# ─────────────────────────────────────────────────────────────────────────────
# Card 1 — Ticker identity (STATIC: no prices/dates/daily stats)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_monogram(img: Image.Image, draw: ImageDraw.ImageDraw, letter: str,
                   cx: float, cy: float, size: float) -> None:
    """Designed fallback when no whitened logo exists: a paneled tile with a
    gradient hairline ring + the ticker's first letter in white.
    """
    s = int(size)
    x0, y0 = int(cx - s / 2), int(cy - s / 2)
    r = int(s * 0.24)
    draw.rounded_rectangle([x0, y0, x0 + s, y0 + s], radius=r, fill=PANEL_HI)
    # gradient ring: draw a rounded rect outline sampled around the tile
    ring = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.rounded_rectangle([2, 2, s - 3, s - 3], radius=r - 2,
                         outline=(91, 157, 255, 150), width=3)
    img.paste(Image.alpha_composite(img.convert("RGBA").crop((x0, y0, x0 + s, y0 + s)), ring)
              .convert(img.mode), (x0, y0))
    mono_font = load_font(int(s * 0.5), bold=True)
    draw.text((cx, cy), letter.upper(), font=mono_font, fill=INK, anchor="mm")


def render_ticker_card(
    *,
    ticker: str,
    name: str,
    sector: str | None,
    industry: str | None,
    logo_path: Path | None,
) -> Image.Image:
    """Identity card for a stock dossier page (site/stocks/<T>.html).

    DELIBERATELY STATIC — no prices, no dates, no daily stats. Changes only when
    ticker/name/sector/industry/logo/CARD_VERSION change (render-budget law:
    ~1,500 of these must NOT regenerate nightly).
    """
    ticker = (ticker or "").upper().strip()
    name = (name or "").strip()
    img, draw = _new_card()

    # Brand lockup top-left.
    _draw_brand_lockup(img, draw, MARGIN)

    # ── Hero row: logo/monogram (left) + ticker (dominant), co-centered ─────
    # This band holds ONLY the logo + ticker so the giant type never collides
    # with the name/meta lines beneath it.
    logo_box = 156
    hero_cy = 258                       # vertical center of the hero row
    logo_cx = MARGIN + logo_box / 2
    logo_cy = hero_cy

    logo_drawn = False
    if logo_path is not None:
        try:
            p = Path(logo_path)
            if p.exists():
                logo = Image.open(p).convert("RGBA")
                lw, lh = logo.size
                scale = min(logo_box / lw, logo_box / lh)
                nw, nh = max(1, int(lw * scale)), max(1, int(lh * scale))
                logo = logo.resize((nw, nh), Image.LANCZOS)
                img.paste(logo, (int(logo_cx - nw / 2), int(logo_cy - nh / 2)), logo)
                logo_drawn = True
        except Exception:  # noqa: BLE001 — fall through to monogram
            logo_drawn = False
    if not logo_drawn:
        _draw_monogram(img, draw, ticker[:1] or "•", logo_cx, logo_cy, logo_box)

    # Ticker — dominant element, right of the logo, weight-900, fit to width,
    # vertically centered on the hero row via middle anchor.
    tk_x = MARGIN + logo_box + 48
    tk_max_w = CARD_W - MARGIN - tk_x
    tk_font = _fit_font(draw, ticker, bold=True, max_w=tk_max_w, start=140, min_size=56, tracking=1.0)
    # Middle-anchor the ticker on the hero centerline (manual tracking uses top
    # anchor, so offset by half the font's cap box).
    _ta, _tt, _tb, _tbot = draw.textbbox((0, 0), ticker, font=tk_font)
    _tk_top = hero_cy - (_tbot - _tt) / 2 - _tt
    _tracked_text(draw, (tk_x, _tk_top), ticker, tk_font, INK, tracking=1.0)

    # ── Company name — its own clear line below the hero ────────────────────
    name_font = load_font(38)
    name_y = 400
    name_show = _truncate(draw, name, name_font, CARD_W - 2 * MARGIN)
    draw.text((MARGIN, name_y), name_show, font=name_font, fill=(206, 218, 238), anchor="ls")

    # ── Sector · industry eyebrow ───────────────────────────────────────────
    meta_bits = [b for b in [sector, industry] if b]
    if meta_bits:
        meta = "   ·   ".join(meta_bits)
        meta_font = load_font(23)
        meta_show = _truncate(draw, meta.upper(), meta_font, CARD_W - 2 * MARGIN)
        _tracked_text(draw, (MARGIN, 424), meta_show, meta_font, MUTED, tracking=1.6)

    # ── Quiet capability tagline (what the dossier offers) ──────────────────
    tag_font = load_font(23)
    _tracked_text(draw, (MARGIN, 476),
                  "signals   ·   options flow   ·   factor profile",
                  tag_font, FAINT, tracking=0.6)

    _draw_footer(img, draw)
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Card 2 — Daily movers (green/red directional columns)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_pct(pct: float) -> str:
    # Plain hyphen-minus (not U+2212) so it renders on every font, incl. PIL's
    # bundled CI default. The SFNS render is visually identical at card scale.
    sign = "+" if pct >= 0 else "-"
    return f"{sign}{abs(pct):.1f}%"


def _draw_mover_column(
    img: Image.Image, draw: ImageDraw.ImageDraw,
    *, rows: list[dict], x0: int, w: int, top: int,
    accent: tuple[int, int, int], heading: str,
) -> None:
    """One column (gainers or losers): heading + up to 5 ticker/pct rows."""
    head_font = load_font(25, bold=True)
    _tracked_text(draw, (x0, top), heading.upper(), head_font, accent, tracking=1.4)
    # accent underline
    draw.line([(x0, top + 38), (x0 + w, top + 38)], fill=(*accent, ), width=2)

    row_h = 54
    ry = top + 52
    tk_font = load_font(29, bold=True)
    pct_font = load_font(29, bold=True)
    for row in rows[:5]:
        tk = str(row.get("ticker", "")).upper()[:6]
        pct = float(row.get("pct", 0.0))
        # ticker left
        draw.text((x0, ry + row_h / 2), tk, font=tk_font, fill=INK, anchor="lm")
        # pct right, accent
        draw.text((x0 + w, ry + row_h / 2), _fmt_pct(pct), font=pct_font,
                  fill=accent, anchor="rm")
        # thin row divider
        draw.line([(x0, ry + row_h), (x0 + w, ry + row_h)], fill=HAIRLINE, width=1)
        ry += row_h


def render_movers_card(*, asof: str, gainers: list[dict], losers: list[dict]) -> Image.Image:
    """Daily card for /movers.html. Top-5 green gainers | red losers, two columns."""
    img, draw = _new_card()
    _draw_brand_lockup(img, draw, MARGIN)

    # Title block below the lockup (clear of the wordmark).
    title_font = load_font(46, bold=True)
    draw.text((MARGIN, 168), "Today’s Movers", font=title_font, fill=INK, anchor="ls")
    # as-of stamp (single, per Law 4)
    asof_font = load_font(22)
    draw.text((CARD_W - MARGIN, 166), str(asof), font=asof_font, fill=MUTED, anchor="rs")

    # Two columns.
    col_top = 196
    gutter = 72
    col_w = (CARD_W - 2 * MARGIN - gutter) // 2
    _draw_mover_column(img, draw, rows=gainers, x0=MARGIN, w=col_w, top=col_top,
                       accent=UP, heading="Gainers")
    _draw_mover_column(img, draw, rows=losers, x0=MARGIN + col_w + gutter, w=col_w,
                       top=col_top, accent=DOWN, heading="Losers")

    _draw_footer(img, draw)
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Card 3 — Signal-stack screener (the #1 combo, in plain words)
# ─────────────────────────────────────────────────────────────────────────────

def render_screener_card(
    *,
    asof: str,
    combo_headline: str,
    wr_test_per10: str,
    n_fires: int,
    first_year: str,
    active_count: int,
) -> Image.Image:
    """Card for the free signal-stack screener page.

    Shows the #1 combo in plain words, its test-era "X wins per 10", depth
    (N entries since YYYY), and how many stocks match today. Carries the required
    honesty microcopy: "historical win rate — not a guarantee".
    """
    img, draw = _new_card()
    _draw_brand_lockup(img, draw, MARGIN)

    # Eyebrow.
    eb_font = load_font(24, bold=True)
    _tracked_text(draw, (MARGIN, 150), "SIGNAL STACK SCREENER", eb_font, FAINT, tracking=2.2)

    # ── Dominant element: the combo headline (plain English, weight-900) ─────
    combo = (combo_headline or "").strip()
    combo_font = _fit_font(draw, combo, bold=True, max_w=CARD_W - 2 * MARGIN,
                           start=68, min_size=34)
    # If still too wide, allow a second line by simple word-wrap.
    if _text_w(draw, combo, combo_font) <= CARD_W - 2 * MARGIN:
        draw.text((MARGIN, 196), combo, font=combo_font, fill=INK, anchor="la")
        stats_top = 300
    else:
        lines = _wrap(draw, combo, combo_font, CARD_W - 2 * MARGIN, max_lines=2)
        ly = 196
        for ln in lines:
            draw.text((MARGIN, ly), ln, font=combo_font, fill=INK, anchor="la")
            ly += combo_font.size + 8
        stats_top = ly + 20

    # ── The "wins per 10" hero figure + two supporting stats ────────────────
    # Big figure on the left, label under it. Then depth + matches to the right.
    fig_font = load_font(96, bold=True)
    draw.text((MARGIN, stats_top), wr_test_per10, font=fig_font, fill=UP, anchor="la")
    fw = _text_w(draw, wr_test_per10, fig_font)
    lbl_font = load_font(23)
    draw.text((MARGIN, stats_top + 104), "wins per 10 in testing",
              font=lbl_font, fill=MUTED, anchor="la")

    # Right supporting stats block.
    rx = MARGIN + max(fw + 90, 360)
    sv_font = load_font(46, bold=True)
    sl_font = load_font(21)
    # depth
    draw.text((rx, stats_top + 6), f"{n_fires:,}", font=sv_font, fill=INK, anchor="la")
    draw.text((rx, stats_top + 56), f"entries since {first_year}", font=sl_font,
              fill=MUTED, anchor="la")
    # matches today
    draw.text((rx, stats_top + 96), f"{active_count:,}", font=sv_font, fill=(91, 157, 255), anchor="la")
    _match_label = "stock matches today" if active_count == 1 else "stocks match today"
    draw.text((rx, stats_top + 146), _match_label, font=sl_font, fill=MUTED, anchor="la")

    # ── Honesty microcopy (required) ─────────────────────────────────────────
    # Hyphen (not em-dash) so it renders on every font incl. PIL's bundled CI
    # default, which lacks U+2014.
    honesty_font = load_font(20)
    draw.text((MARGIN, CARD_H - MARGIN - 70),
              "Historical win rate - not a guarantee.",
              font=honesty_font, fill=(150, 162, 186), anchor="ls")
    # as-of (single stamp)
    asof_font = load_font(20)
    draw.text((CARD_W - MARGIN, CARD_H - MARGIN - 70), str(asof),
              font=asof_font, fill=(90, 102, 128), anchor="rs")

    _draw_footer(img, draw)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
          max_w: float, *, max_lines: int = 2) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if _text_w(draw, cand, font) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines - 1:
                break
    remaining = text.split()
    if len(lines) < max_lines:
        # rebuild remainder for the last line
        used = " ".join(lines)
        rest = text[len(used):].strip() if used else text
        lines.append(_truncate(draw, rest, font, max_w))
    else:
        lines[-1] = _truncate(draw, cur, font, max_w)
    return lines[:max_lines]


# ─────────────────────────────────────────────────────────────────────────────
# Saving + fingerprint store
# ─────────────────────────────────────────────────────────────────────────────

def save_card(img: Image.Image, out_path: Path) -> None:
    """Write *img* as an optimized PNG (target ≤ ~80 KB). Flat-color design
    compresses well; we quantize to 256 colors (the gradients dither cleanly at
    card scale and stay under budget). Atomic write via same-dir temp + os.replace.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Quantize: cuts file size hard without visible degradation at this scale.
    to_save = img.convert("RGB").quantize(colors=256, method=Image.FASTOCTREE, dither=Image.NONE)
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), suffix=".png.tmp")
    os.close(fd)
    try:
        to_save.save(tmp, format="PNG", optimize=True)
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def card_fingerprint(payload: dict) -> str:
    """sha1 over CARD_VERSION + canonical-JSON payload (sort_keys, compact)."""
    blob = json.dumps(
        {"v": CARD_VERSION, "p": payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
    )
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _store_path(root: Path) -> Path:
    return Path(root) / "data" / "marketing" / "share_cards" / "fingerprints.json"


def _load_store(store: Path) -> dict:
    try:
        return json.loads(store.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt store → start empty
        return {}


def _write_store_atomic(store: Path, data: dict) -> None:
    """Atomic write: same-dir tempfile + os.replace. House law — never open('w')
    truncation on a shared store (a crash mid-write must not corrupt it)."""
    store.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(store.parent), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, indent=0)
        os.replace(tmp, store)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def save_card_if_changed(
    *, payload: dict, out_path: Path, render: Callable[[], Image.Image], root: Path
) -> bool:
    """Fingerprint-gated render. Skips render entirely on a fingerprint hit AND an
    existing out_path. Store keyed by out_path relative to *root*. Returns True if
    the card was (re)rendered, False if skipped.
    """
    out_path = Path(out_path)
    root = Path(root)
    store = _store_path(root)
    try:
        key = str(out_path.resolve().relative_to(root.resolve()))
    except Exception:  # noqa: BLE001 — out_path not under root; key by name
        key = out_path.name

    fp = card_fingerprint(payload)
    data = _load_store(store)
    if data.get(key) == fp and out_path.exists():
        return False  # skip: fingerprint + artifact both present

    img = render()
    save_card(img, out_path)
    data[key] = fp
    _write_store_atomic(store, data)
    return True
