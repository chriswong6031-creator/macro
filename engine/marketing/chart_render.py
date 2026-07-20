"""engine.marketing.chart_render — Pure-Python SVG price chart for Content Studio.

Public API (v1 — backward-compat, kept unchanged):
    load_closes(ticker, root, n=90) -> tuple[list[str], list[float]] | None
    macd_cross(closes)             -> dict|None   (internal signal only; never emitted)
    render_signal_chart(...)       -> str          (self-contained SVG, < 9 KB)

Public API (v2 — TrendSpider-grade terminal chart):
    load_ohlcv(ticker, root, n=90) -> tuple[dates, open, high, low, close, volume] | None
    render_chart_v2(...)           -> str          (self-contained SVG, < 60 KB)
    render_earnings_card(...)      -> str          (branded earnings card SVG)
    resolve_logo(ticker, root)     -> str | None   (whitened data URI, cached)

v1 spec constraints (§2.2):
  - NO matplotlib, NO external deps beyond pandas/pyarrow for parquet reading.
  - macd_cross values are NEVER returned in any artifact or drawn on chart.
  - No "MACD", "RSI", "EMA", "cross" text anywhere in SVG output.
  - BUY marker: upward triangle + label in green #3ddc84.
  - Transparent background (viewBox only, no background rect).
  - < 9 KB per SVG.
  - No <script> tags.

v2 spec constraints (§2 anatomy + §3 decision):
  - show_indicators=True: subpanel labels (MACD/RSI/Volume) ARE shown — the win-rate
    framing is the hook; visible indicators make the chart credible and shareable.
  - Public POST BODY copy must stay clean of indicator vocabulary; SVG subpanel labels OK.
  - No <script> tags. All text _xesc'd. < 60 KB. Deterministic.
"""
from __future__ import annotations

import math
import zlib
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Closes loader
# ─────────────────────────────────────────────────────────────────────────────

def load_closes(
    ticker: str,
    root: Path | str,
    n: int = 90,
) -> tuple[list[str], list[float]] | None:
    """Load last *n* closing prices for *ticker* from data/stocks/<TICKER>.parquet.

    Returns (dates, closes) where dates are ISO strings and closes are floats.
    Returns None on any error (missing file, bad data).
    """
    try:
        path = Path(root) / "data" / "stocks" / f"{ticker}.parquet"
        if not path.exists():
            return None
        import pandas as pd  # only import when needed
        df = pd.read_parquet(path)
        if "close" not in df.columns:
            return None
        df = df.sort_index()
        df = df.dropna(subset=["close"])
        if len(df) == 0:
            return None
        # Take last n rows
        df = df.iloc[-n:]
        dates = [str(d)[:10] for d in df.index]
        closes = [float(c) for c in df["close"]]
        return dates, closes
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Internal EMA + signal detection (values never emitted)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(values: list[float], period: int) -> list[float | None]:
    """Compute EMA with standard multiplier. Returns list aligned to *values*."""
    if len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    result: list[float | None] = [None] * (period - 1)
    seed = sum(values[:period]) / period
    result.append(seed)
    prev = seed
    for v in values[period:]:
        ema_val = v * k + prev * (1 - k)
        result.append(ema_val)
        prev = ema_val
    return result


def macd_cross(closes: list[float]) -> dict[str, Any] | None:
    """Detect the most recent bullish price-momentum cross.

    Internal only — values are NEVER surfaced in any artifact or SVG.
    Returns {index, offset_from_end} for the most recent bullish cross,
    or None if no cross found in the window.
    """
    if len(closes) < 35:  # need enough for EMA26 + signal9
        return None

    fast = _ema(closes, 12)
    slow = _ema(closes, 26)

    # Build MACD line (both EMAs must be non-None)
    macd_line: list[float | None] = []
    for f, s in zip(fast, slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)

    # Build signal line (EMA9 of MACD)
    macd_vals = [v for v in macd_line if v is not None]
    if len(macd_vals) < 9:
        return None

    signal_raw = _ema(macd_vals, 9)

    # Re-align signal to full indices
    offset = len(macd_line) - len(macd_vals)
    signal_line: list[float | None] = [None] * offset
    for i, sv in enumerate(signal_raw):
        macd_idx = offset + i
        signal_line.append(sv)

    # Detect bullish cross: MACD goes from below signal to above signal
    last_cross_index: int | None = None
    for i in range(1, len(closes)):
        m_cur = macd_line[i]
        m_prev = macd_line[i - 1]
        s_cur = signal_line[i] if i < len(signal_line) else None
        s_prev = signal_line[i - 1] if i - 1 < len(signal_line) else None
        if m_cur is None or m_prev is None or s_cur is None or s_prev is None:
            continue
        # Bullish cross: previously below, now above
        if m_prev <= s_prev and m_cur > s_cur:
            last_cross_index = i

    if last_cross_index is None:
        return None

    return {
        "index": last_cross_index,
        "offset_from_end": len(closes) - 1 - last_cross_index,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SVG renderer
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_price(p: float) -> str:
    """Format price with 2 decimal places."""
    return f"{p:.2f}"


def _xesc(s: object) -> str:
    """XML/SVG-escape any text interpolated into the SVG.

    The rendered SVG is injected into the admin DOM via innerHTML, so every
    non-numeric interpolation (ticker, subtitle, dates) MUST be escaped even
    though the inputs are first-party — defense against a hostile/odd ticker
    or thesis string breaking the SVG or injecting markup.
    """
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_signal_chart(
    ticker: str,
    dates: list[str],
    closes: list[float],
    *,
    marker_index: int,
    width: int = 560,
    height: int = 300,
    subtitle: str | None = None,
) -> str:
    """Render a price chart SVG.

    Returns a self-contained SVG string (< 9 KB target).
    Contains: price polyline, BUY marker at marker_index, gridlines,
    min/max/last labels, date labels, brand mark.

    No MACD, RSI, EMA, or indicator text anywhere in output.
    No <script> tags. Transparent background.
    """
    n = len(closes)
    if n < 2:
        return _empty_svg(width, height, ticker)

    # Clamp marker_index
    marker_index = max(0, min(marker_index, n - 1))

    # Layout constants
    PAD_LEFT = 52
    PAD_RIGHT = 16
    PAD_TOP = 32
    PAD_BOT = 40
    chart_w = width - PAD_LEFT - PAD_RIGHT
    chart_h = height - PAD_TOP - PAD_BOT

    price_min = min(closes)
    price_max = max(closes)
    price_range = price_max - price_min or 1.0

    # Add a small vertical margin (5% each side)
    margin = price_range * 0.05
    y_min = price_min - margin
    y_max = price_max + margin
    y_range = y_max - y_min

    def px(i: int) -> float:
        return PAD_LEFT + (i / (n - 1)) * chart_w

    def py(price: float) -> float:
        return PAD_TOP + chart_h * (1 - (price - y_min) / y_range)

    # Build polyline points
    pts = " ".join(f"{px(i):.1f},{py(c):.1f}" for i, c in enumerate(closes))

    # Gridlines (3 horizontal)
    grid_lines = []
    for frac in [0.25, 0.5, 0.75]:
        gy = PAD_TOP + chart_h * frac
        grid_price = y_max - frac * y_range
        grid_lines.append(
            f'<line x1="{PAD_LEFT}" y1="{gy:.1f}" x2="{PAD_LEFT + chart_w}" '
            f'y2="{gy:.1f}" stroke="#2a3045" stroke-width="1"/>'
            f'<text x="{PAD_LEFT - 4}" y="{gy + 4:.1f}" '
            f'fill="#93a0b4" font-size="9" text-anchor="end">{_fmt_price(grid_price)}</text>'
        )
    grid_svg = "\n  ".join(grid_lines)

    # Area fill under line (subtle)
    area_bottom = PAD_TOP + chart_h
    area_pts = (
        f"{PAD_LEFT:.1f},{area_bottom:.1f} "
        + pts
        + f" {PAD_LEFT + chart_w:.1f},{area_bottom:.1f}"
    )

    # BUY marker geometry
    bx = px(marker_index)
    by = py(closes[marker_index])
    tri_size = 8
    tri_pts = (
        f"{bx:.1f},{by - tri_size:.1f} "
        f"{bx - tri_size * 0.7:.1f},{by + tri_size * 0.3:.1f} "
        f"{bx + tri_size * 0.7:.1f},{by + tri_size * 0.3:.1f}"
    )

    # Min/Max/Last labels
    min_idx = closes.index(price_min)
    max_idx = closes.index(price_max)
    min_x = px(min_idx)
    max_x = px(max_idx)
    last_x = px(n - 1)
    last_y = py(closes[-1])

    # Dot on last price
    last_dot = (
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" '
        f'fill="#38e0d4" stroke="none"/>'
    )

    # Date labels (first and last) — escaped for the innerHTML sink
    date_first = _xesc(dates[0]) if dates else ""
    date_last = _xesc(dates[-1]) if dates else ""
    date_y = PAD_TOP + chart_h + 16

    # Subtitle text
    subtitle_text = ""
    if subtitle:
        subtitle_text = (
            f'<text x="{PAD_LEFT}" y="{PAD_TOP - 14}" '
            f'fill="#93a0b4" font-size="10">{_xesc(subtitle)}</text>'
        )

    # Brand mark
    brand_x = PAD_LEFT + chart_w
    brand_y = PAD_TOP + chart_h + 32

    svg = f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <!-- price area fill -->
  <polygon points="{area_pts}" fill="#38e0d4" fill-opacity="0.06" stroke="none"/>
  <!-- gridlines -->
  {grid_svg}
  <!-- price line -->
  <polyline points="{pts}" fill="none" stroke="#38e0d4" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  <!-- last price dot -->
  {last_dot}
  <!-- BUY vertical guide -->
  <line x1="{bx:.1f}" y1="{PAD_TOP}" x2="{bx:.1f}" y2="{PAD_TOP + chart_h}" stroke="#3ddc84" stroke-width="1" stroke-dasharray="3,3" opacity="0.6"/>
  <!-- BUY triangle -->
  <polygon points="{tri_pts}" fill="#3ddc84" opacity="0.95"/>
  <!-- BUY price dot -->
  <circle cx="{bx:.1f}" cy="{by:.1f}" r="3.5" fill="#3ddc84" stroke="#0d1117" stroke-width="1"/>
  <!-- BUY label -->
  <text x="{bx:.1f}" y="{by - tri_size - 4:.1f}" fill="#3ddc84" font-size="10" font-weight="bold" text-anchor="middle">BUY</text>
  <!-- min/max/last labels -->
  <text x="{min_x:.1f}" y="{py(price_min) + 14:.1f}" fill="#93a0b4" font-size="9" text-anchor="middle">{_fmt_price(price_min)}</text>
  <text x="{max_x:.1f}" y="{py(price_max) - 5:.1f}" fill="#93a0b4" font-size="9" text-anchor="middle">{_fmt_price(price_max)}</text>
  <text x="{last_x:.1f}" y="{last_y - 5:.1f}" fill="#38e0d4" font-size="9" text-anchor="end">{_fmt_price(closes[-1])}</text>
  <!-- date labels -->
  <text x="{PAD_LEFT}" y="{date_y}" fill="#93a0b4" font-size="9" text-anchor="start">{date_first}</text>
  <text x="{PAD_LEFT + chart_w}" y="{date_y}" fill="#93a0b4" font-size="9" text-anchor="end">{date_last}</text>
  <!-- ticker label -->
  <text x="{PAD_LEFT}" y="{PAD_TOP - 2}" fill="#e2e8f0" font-size="12" font-weight="bold">{_xesc(ticker)}</text>
  {subtitle_text}
  <!-- brand mark -->
  <text x="{brand_x}" y="{brand_y}" fill="#2a3045" font-size="8" text-anchor="end">MASTERMIND</text>
</svg>"""

    return svg


def _empty_svg(width: int, height: int, ticker: str) -> str:
    """Fallback SVG when insufficient data."""
    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f'<text x="50%" y="50%" fill="#93a0b4" font-size="12" text-anchor="middle">'
        f'{_xesc(ticker)} — no data</text>'
        f'</svg>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# v2: OHLCV loader
# ─────────────────────────────────────────────────────────────────────────────

def load_ohlcv(
    ticker: str,
    root: Path | str,
    n: int = 90,
) -> tuple[list[str], list[float], list[float], list[float], list[float], list[float]] | None:
    """Load last *n* bars of OHLCV for *ticker* from data/stocks/<TICKER>.parquet.

    The parquet has no 'open' column so we proxy open_t = close_{t-1} (standard
    prev-close proxy for candlestick rendering; the first bar's open = its close).

    Returns (dates, opens, highs, lows, closes, volumes) — all lists of length ≤ n.
    Returns None on any error (missing file, bad data, insufficient rows).
    """
    try:
        path = Path(root) / "data" / "stocks" / f"{ticker}.parquet"
        if not path.exists():
            return None
        import pandas as pd  # only import when needed
        df = pd.read_parquet(path)
        required = {"close", "high", "low", "volume"}
        if not required.issubset(set(df.columns)):
            return None
        df = df.sort_index().dropna(subset=["close", "high", "low"])
        if len(df) < 2:
            return None
        # Take last n rows (need n+1 to compute prev-close open for first bar)
        df = df.iloc[-(n + 1):]
        dates = [str(d)[:10] for d in df.index]
        closes_raw = [float(c) for c in df["close"]]
        highs_raw = [float(h) for h in df["high"]]
        lows_raw = [float(l) for l in df["low"]]
        vols_raw = [float(v) if not (v != v) else 0.0 for v in df["volume"]]
        # prev-close proxy for open: open_t = close_{t-1}; first bar open = its close
        opens_raw = [closes_raw[0]] + closes_raw[:-1]
        # Drop the extra lead row now that opens are computed
        dates = dates[-n:]
        opens_raw = opens_raw[-n:]
        highs_raw = highs_raw[-n:]
        lows_raw = lows_raw[-n:]
        closes_raw = closes_raw[-n:]
        vols_raw = vols_raw[-n:]
        return dates, opens_raw, highs_raw, lows_raw, closes_raw, vols_raw
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# v2: Internal indicator computation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sma(values: list[float], period: int) -> list[float | None]:
    """Simple moving average, result aligned to input length."""
    result: list[float | None] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(values[i - period + 1: i + 1]) / period)
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder RSI, result aligned to input length."""
    if len(closes) < period + 1:
        return [None] * len(closes)
    result: list[float | None] = [None] * period
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100.0 - 100.0 / (1.0 + rs))
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100.0 - 100.0 / (1.0 + rs))
    return result


def _macd_lines(closes: list[float]) -> tuple[
    list[float | None], list[float | None], list[float | None]
]:
    """Compute MACD line, signal line, histogram. All aligned to closes length."""
    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    macd_line: list[float | None] = []
    for f, s in zip(fast, slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)
    # Build signal line = EMA9 of non-None macd values
    macd_vals = [v for v in macd_line if v is not None]
    if len(macd_vals) < 9:
        return macd_line, [None] * len(closes), [None] * len(closes)
    signal_raw = _ema(macd_vals, 9)
    offset = len(macd_line) - len(macd_vals)
    signal_line: list[float | None] = [None] * offset + list(signal_raw)
    hist: list[float | None] = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            hist.append(None)
        else:
            hist.append(m - s)
    return macd_line, signal_line, hist


def _fmt_thousands(v: float) -> str:
    """Format a price with commas and 2 decimal places."""
    return f"{v:,.2f}"


def _favicon_logomark(cx: float, cy: float, size: float = 34.0, uid: str = "0") -> str:
    """Render the real Mastermind favicon logomark as an inline SVG group.

    Gradient tile (#5b9dff→#3b82f6→#6366f1→#7c5cff, rx proportional) + ascending
    market-peak "M" path in white. Gradient ids are suffixed with *uid* to prevent
    collisions when multiple charts appear on one admin page.

    Args:
        cx, cy: center of the tile.
        size: tile side length in px (default 34).
        uid: per-render suffix for all gradient/def ids.
    """
    half = size / 2.0
    x = cx - half
    y = cy - half
    rx = size * (10.5 / 40.0)  # proportional to viewBox 0 0 40 40
    sw = size * (3.3 / 40.0)   # stroke-width proportional

    # The M path in the original viewBox (2 2 36 36, tile at 3,3 size 34):
    # M13 28 L13 14.5 L20 22 L27 12.5 L27 28
    # Scale from original 40px viewBox to our `size`.
    scale = size / 40.0

    def sp(orig: float) -> float:
        return (orig - 2) * scale + x  # x-coords: offset by viewBox x=2 + our x

    def sq(orig: float) -> float:
        return (orig - 2) * scale + y  # y-coords

    m_path = (
        f"M{sp(13):.2f},{sq(28):.2f} "
        f"L{sp(13):.2f},{sq(14.5):.2f} "
        f"L{sp(20):.2f},{sq(22):.2f} "
        f"L{sp(27):.2f},{sq(12.5):.2f} "
        f"L{sp(27):.2f},{sq(28):.2f}"
    )
    # Shadow path (offset +1.1 in y, scaled)
    shadow_dy = 1.1 * scale
    m_shadow = (
        f"M{sp(13):.2f},{sq(28) + shadow_dy:.2f} "
        f"L{sp(13):.2f},{sq(14.5) + shadow_dy:.2f} "
        f"L{sp(20):.2f},{sq(22) + shadow_dy:.2f} "
        f"L{sp(27):.2f},{sq(12.5) + shadow_dy:.2f} "
        f"L{sp(27):.2f},{sq(28) + shadow_dy:.2f}"
    )

    tile_id = f"mbTile_{uid}"
    sheen_id = f"mbSheen_{uid}"
    glow_id = f"mbGlow_{uid}"
    ink_id = f"mbInk_{uid}"

    defs_part = (
        f'<linearGradient id="{tile_id}" x1="0" y1="0" x2="1" y2="1" '
        f'gradientUnits="objectBoundingBox">'
        f'<stop offset="0" stop-color="#5b9dff"/>'
        f'<stop offset=".42" stop-color="#3b82f6"/>'
        f'<stop offset=".74" stop-color="#6366f1"/>'
        f'<stop offset="1" stop-color="#7c5cff"/>'
        f'</linearGradient>'
        f'<linearGradient id="{sheen_id}" x1="0" y1="0" x2="0" y2="1" '
        f'gradientUnits="objectBoundingBox">'
        f'<stop offset="0" stop-color="#ffffff" stop-opacity=".34"/>'
        f'<stop offset=".55" stop-color="#ffffff" stop-opacity="0"/>'
        f'</linearGradient>'
        f'<radialGradient id="{glow_id}" cx=".5" cy=".4" r=".65" '
        f'gradientUnits="objectBoundingBox">'
        f'<stop offset="0" stop-color="#ffffff" stop-opacity=".22"/>'
        f'<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
        f'</radialGradient>'
        f'<linearGradient id="{ink_id}" x1="0" y1="0" x2="0" y2="1" '
        f'gradientUnits="objectBoundingBox">'
        f'<stop offset="0" stop-color="#ffffff"/>'
        f'<stop offset="1" stop-color="#dbe7ff"/>'
        f'</linearGradient>'
    )

    group = (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{size:.2f}" height="{size:.2f}" '
        f'rx="{rx:.2f}" fill="url(#{tile_id})"/>'
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{size:.2f}" height="{size:.2f}" '
        f'rx="{rx:.2f}" fill="url(#{glow_id})"/>'
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{size:.2f}" height="{size:.2f}" '
        f'rx="{rx:.2f}" fill="url(#{sheen_id})"/>'
        # Shadow stroke
        f'<path d="{m_shadow}" fill="none" stroke="#15205a" stroke-opacity=".30" '
        f'stroke-width="{sw:.2f}" stroke-linecap="round" stroke-linejoin="round"/>'
        # Main M stroke
        f'<path d="{m_path}" fill="none" stroke="url(#{ink_id})" '
        f'stroke-width="{sw:.2f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return defs_part, group


def resolve_logo(ticker: str, root: Path | str) -> str | None:
    """Return whitened data URI for ticker logo (cached; fetch if needed). Fail-soft None."""
    try:
        from engine.marketing.logo_cache import white_logo_datauri
        return white_logo_datauri(ticker, root, fetch=True)
    except Exception:  # noqa: BLE001
        return None


def resolve_color_logo(ticker: str, root: Path | str) -> str | None:
    """Return ORIGINAL full-color data URI for ticker logo (cached; fetch if needed).

    The avatar-chip counterpart to resolve_logo: keeps brand hue + transparency
    for the light circular chips in the watchlist card. Fail-soft None.
    """
    try:
        from engine.marketing.logo_cache import color_logo_datauri
        return color_logo_datauri(ticker, root, fetch=True)
    except Exception:  # noqa: BLE001
        return None


def _brand_bar(
    width: int,
    height: int,
    uid: str,
    *,
    descriptor: str | None = None,
    show_url: bool = True,
    show_button: bool = True,
    tagline: str | None = "AI stock signals",
    button_label: str = "Start free 14-day trial",
    copyright_text: str = "© 2026 Mastermind",
    band_h: int = 46,
) -> tuple[str, str]:
    """Bottom brand bar shared by the whole card family — the footer IS the ad
    unit, so it gets real chrome: a full-bleed #0A1020 band bookending the
    header, a brand-gradient "laser" hairline dissolving along its top edge,
    the favicon logomark + URL lockup at left, and one saturated gradient CTA
    button at right with the copyright tucked beside it.

    The quiet variants encode contracts, not taste: descriptor with no button =
    informational surfaces (dossier notes); show_url=False = the Sentinel sober
    form (tragedy items keep brand attribution, lose every pitch element).

    Returns (defs_svg, bar_svg); all gradient ids are uid-suffixed so several
    cards can share one document (admin galleries).
    """
    band_top = height - band_h
    cy = band_top + band_h / 2.0
    # Everything in the bar scales with the band height so a taller footer (the
    # portrait watchlist card passes band_h=72) keeps the logomark, URL, button
    # and copyright in proportion. The family default is band_h=46 (s == 1.0):
    # for THAT path the original literal geometry is emitted verbatim (see _num
    # below) so every existing caller's SVG stays byte-identical — only a
    # non-default band_h re-scales.
    s = band_h / 46.0
    _scaled = abs(s - 1.0) > 1e-9

    def _num(base: float, literal: str, fmt: str = ".1f") -> str:
        """Emit *literal* verbatim on the default band (byte-stable), else the
        scaled value formatted with *fmt*."""
        return literal if not _scaled else format(base * s, fmt)

    pad = 14 * s

    laser_id = f"bb_laser_{uid}"
    btn_id = f"bb_btn_{uid}"
    btn_sheen_id = f"bb_btnsheen_{uid}"
    defs = (
        f'<linearGradient id="{laser_id}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#5b9dff"/>'
        f'<stop offset="0.35" stop-color="#6366f1"/>'
        f'<stop offset="0.6" stop-color="#7c5cff"/>'
        f'<stop offset="0.92" stop-color="#7c5cff" stop-opacity="0"/>'
        f'</linearGradient>'
        f'<linearGradient id="{btn_id}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#3b82f6"/>'
        f'<stop offset="1" stop-color="#7c5cff"/>'
        f'</linearGradient>'
        f'<linearGradient id="{btn_sheen_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#ffffff" stop-opacity="0.18"/>'
        f'<stop offset="0.55" stop-color="#ffffff" stop-opacity="0.02"/>'
        f'<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
        f'</linearGradient>'
    )

    bar = (
        f'<rect x="0" y="{band_top}" width="{width}" height="{band_h}" '
        f'fill="#0A1020" opacity="0.94"/>'
        f'<rect x="0" y="{band_top}" width="{width}" height="{_num(1.5, "1.5", ".2f")}" '
        f'fill="url(#{laser_id})"/>'
    )

    # Left lockup: logomark tile always anchors the brand; URL is the marketing
    # voice (suppressed on sober cards), descriptor is the quiet second voice.
    tile = 18.0 * s
    lm_defs, lm_group = _favicon_logomark(pad + tile / 2, cy, size=tile, uid=f"{uid}bb")
    defs += lm_defs
    bar += lm_group
    x = pad + tile + 9.0 * s
    if show_url:
        bar += (
            f'<text x="{x:.1f}" y="{cy + 5 * s:.1f}" fill="#ffffff" '
            f'font-size="{_num(15, "15")}" font-weight="800" font-family="sans-serif" '
            f'letter-spacing="0.3">mastermind-x.com</text>'
        )
        x += 152.0 * s
        # The what-we-do tag: rides the URL so anyone seeing the image knows
        # what the product IS. Brighter than the descriptor whisper, quieter
        # than the URL; suppressed with it on the sober card form.
        if tagline:
            x += 11.0 * s
            bar += (
                f'<circle cx="{x:.1f}" cy="{cy:.1f}" r="{_num(1.5, "1.5", ".2f")}" '
                f'fill="#3a4466"/>'
            )
            x += 11.0 * s
            bar += (
                f'<text x="{x:.1f}" y="{cy + 4 * s:.1f}" fill="#93a7cc" '
                f'font-size="{_num(11, "11")}" font-weight="700" font-family="sans-serif" '
                f'letter-spacing="1.4">{_xesc(tagline.upper())}</text>'
            )
            x += (len(tagline) * 8.4 + 16) * s
    if descriptor:
        if show_url:
            x += 11.0 * s
            bar += (
                f'<circle cx="{x:.1f}" cy="{cy:.1f}" r="{_num(1.5, "1.5", ".2f")}" '
                f'fill="#3a4466"/>'
            )
            x += 11.0 * s
        bar += (
            f'<text x="{x:.1f}" y="{cy + 4 * s:.1f}" fill="#8899bb" '
            f'font-size="{_num(11, "11")}" font-family="sans-serif" letter-spacing="0.2">'
            f'{_xesc(descriptor)}</text>'
        )

    # Right cluster: © in whisper ink, then THE one saturated element.
    right_x = width - pad
    if show_button:
        bw = int(len(button_label) * 7.1 * s) + int(30 * s)
        bh = 26.0 * s
        bx = right_x - bw
        by = cy - bh / 2.0
        bar += (
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{bh:.0f}" '
            f'rx="{_num(13, "13")}" fill="url(#{btn_id})"/>'
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{bh:.0f}" '
            f'rx="{_num(13, "13")}" fill="url(#{btn_sheen_id})" stroke="#ffffff" '
            f'stroke-opacity="0.16" stroke-width="1"/>'
            f'<text x="{bx + bw / 2.0:.1f}" y="{cy + 4 * s:.1f}" fill="#ffffff" '
            f'font-size="{_num(12, "12")}" font-weight="700" font-family="sans-serif" '
            f'text-anchor="middle" letter-spacing="0.2">{_xesc(button_label)}</text>'
        )
        right_x = bx - 14.0 * s
    bar += (
        f'<text x="{right_x:.1f}" y="{cy + 3 * s:.1f}" fill="#3a4466" '
        f'font-size="{_num(9, "9")}" text-anchor="end" font-family="sans-serif">'
        f'{_xesc(copyright_text)}</text>'
    )
    return defs, bar


# ─────────────────────────────────────────────────────────────────────────────
# v2: TrendSpider-grade chart renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_chart_v2(
    ticker: str,
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    volume: list[float],
    *,
    timeframe: str = "DAILY",
    marker_index: int | None = None,
    highlight_index: int | None = None,
    pct_from_index: int | None = None,
    show_indicators: bool = True,
    indicators: tuple[str, ...] = ("volume", "macd"),
    warmup: int = 0,
    volume_overlay: bool = False,
    subpanel_h: int = 110,
    company_name: str | None = None,
    logo_datauri: str | None = None,
    logo_root: Path | str | None = None,
    width: int = 1000,
    height: int = 850,
    footer_cta: str | None = None,
    avwap_overlay: dict | None = None,
    poc_overlay: dict | None = None,
) -> str:
    """Render a TrendSpider-grade candlestick SVG chart.

    Dark-navy (#0E1420) bg, real Mastermind favicon lockup top-left (gradient tile +
    ascending-M path + MASTERMIND wordmark), TICKER+TIMEFRAME top-right, candlesticks
    with wicks (min 2px body), right price-axis (5-7 round levels), last-price pill,
    optional SMA50/SMA200 overlays, % change callout box (with duration), highlight
    zone + SETUP pill, stacked subpanels (volume / MACD / RSI), ghost watermark,
    company logo overlay (when logo_datauri provided or logo_root triggers auto-resolve),
    footer with URL + copyright.

    New kwargs:
        logo_datauri: pre-resolved whitened data URI — embedded as giant overlay in
            upper price area (TrendSpider signature move). Overrides ghost text when set.
        logo_root: if logo_datauri is None but logo_root is provided, calls
            resolve_logo(ticker, logo_root) to auto-fetch + cache the logo.
        avwap_overlay: {"values": list[float|None], "label": str} — anchored VWAP
            curve drawn in house indigo (#7c5cff) under candles, over SMA.
        poc_overlay: {"poc": float, "va_low": float, "va_high": float, "label": str}
            — volume point-of-control dashed line + value area band.
        Both default None; None and omitted are byte-identical to each other.
        NOTE vs pre-M2 output: the SMA layer now paints UNDER the candles (it
        used to paint over them) so the M2 overlays could slot between —
        a deliberate, designer-approved z-order change for ALL charts.

    Returns self-contained SVG (<60KB). No <script>. All text _xesc'd.
    """
    n = len(c)
    if n < 5:
        return _empty_svg(width, height, ticker)

    # ── warmup: leading bars that warm up SMA/MACD so their lines span the FULL
    # visible window instead of starting mid-chart. These bars feed the indicator
    # math but are never drawn; every x-geometry site below measures over the
    # visible tail (indices [warmup, n)) via cx_bar's warmup offset. ──────────
    warmup = max(0, min(int(warmup or 0), n - 5))
    n_vis = n - warmup

    # ── Unique id suffix: derived from ticker hash (deterministic, collision-safe) ──
    uid = str(abs(hash(ticker)) % 10_000_000)

    # ── Auto-resolve logo if not provided ───────────────────────────────────
    if logo_datauri is None and logo_root is not None:
        logo_datauri = resolve_logo(ticker, logo_root)

    # Clamp indices
    eff_highlight = highlight_index if highlight_index is not None else marker_index
    eff_marker = marker_index if marker_index is not None else (n - 1)
    eff_marker = max(0, min(eff_marker, n - 1))
    if eff_highlight is not None:
        eff_highlight = max(0, min(eff_highlight, n - 1))
        # A mark that lands in the (undrawn) warmup lead-in would float off the
        # left edge — drop it rather than draw a disc pointing at nothing.
        if eff_highlight < warmup:
            eff_highlight = None
    # % callout is strictly opt-in: pct_from_index=None means NO callout box.
    # (A "-3% in 2 bars" banner on a fresh bullish setup is contradictory noise —
    # callers suppress the callout when the window is too short to mean anything.)
    eff_pct_from = None if pct_from_index is None else max(0, min(pct_from_index, n - 1))
    # An anchor buried in the undrawn warmup lead-in has no visible bar to
    # measure from — suppress the callout rather than reference an off-screen bar.
    if eff_pct_from is not None and eff_pct_from < warmup:
        eff_pct_from = None

    # ── Layout ──────────────────────────────────────────────────────────────
    HEADER_H = 64          # header band height (taller for logo breathing room)
    FOOTER_H = 58  # room for the CTA pill + large URL line
    PAD_L = 14             # left padding (no left axis)
    PAD_R = 72             # right axis labels
    PAD_TOP = HEADER_H + 12  # extra padding so logo band breathes

    # Subpanel heights
    active_panels: list[str] = []
    if show_indicators:
        for ind in indicators:
            # volume_overlay draws volume INSIDE the price pane (paneless), the way
            # the Terminal does — so it never claims a subpanel of its own, freeing
            # that vertical space for a taller, legible MACD pane below.
            if ind == "volume" and volume_overlay:
                continue
            if ind in ("volume", "macd", "rsi"):
                active_panels.append(ind)
    SUBPANEL_H = max(60, int(subpanel_h)) if active_panels else 0
    n_sub = len(active_panels)
    total_sub_h = SUBPANEL_H * n_sub

    # Floor the price pane so an adversarial subpanel_h can never invert the
    # layout (negative height flips the y-axis and paints candles into the header).
    PRICE_H = max(80, height - PAD_TOP - FOOTER_H - total_sub_h - 8)

    chart_w = width - PAD_L - PAD_R

    # Candle slot width — min 2px body, 1px gap between candles. Measured over the
    # VISIBLE bar count so warmup bars never squeeze the drawn candles.
    slot_w = chart_w / n_vis
    body_frac = 0.60        # body width = 60% of slot
    body_w = max(2.0, slot_w * body_frac - 1.0)  # -1 = 1px gap

    # Price range (from high/low with margin) — VISIBLE bars only, so warmup-era
    # extremes never distort the scale of the window the user actually sees.
    all_h = [h[i] for i in range(warmup, n) if h[i] == h[i]]
    all_l = [l[i] for i in range(warmup, n) if l[i] == l[i]]
    price_max_raw = max(all_h) if all_h else max(c)
    price_min_raw = min(all_l) if all_l else min(c)

    # Extend y-scale to include avwap overlay non-null values so curve is never clipped
    if avwap_overlay is not None:
        _avwap_vals = avwap_overlay.get("values") or []
        # visible (post-warmup) values only — the warmup lead-in is never drawn
        _avwap_nonnull = [v for i, v in enumerate(_avwap_vals)
                          if i >= warmup and v is not None and v == v]
        if _avwap_nonnull:
            price_max_raw = max(price_max_raw, max(_avwap_nonnull))
            price_min_raw = min(price_min_raw, min(_avwap_nonnull))

    price_range = price_max_raw - price_min_raw or 1.0
    margin = price_range * 0.07
    y_min = price_min_raw - margin
    y_max = price_max_raw + margin
    y_range = y_max - y_min

    def cx_bar(i: int) -> float:
        # i is an ABSOLUTE index into the full series; the warmup lead-in is
        # subtracted so the first visible bar sits at the left edge.
        return PAD_L + (i - warmup + 0.5) * slot_w

    def py_price(price: float) -> float:
        return PAD_TOP + PRICE_H * (1.0 - (price - y_min) / y_range)

    # ── Candlesticks ────────────────────────────────────────────────────────
    candle_parts: list[str] = []
    for i in range(warmup, n):
        op = o[i]
        hp = h[i]
        lp = l[i]
        cp_val = c[i]
        is_up = cp_val >= op
        color = "#4CAF50" if is_up else "#E23B3B"
        bx = cx_bar(i)
        # Wick (high-low)
        wy_top = py_price(hp)
        wy_bot = py_price(lp)
        candle_parts.append(
            f'<line x1="{bx:.1f}" y1="{wy_top:.1f}" x2="{bx:.1f}" y2="{wy_bot:.1f}" '
            f'stroke="{color}" stroke-width="1"/>'
        )
        # Body (open-close)
        body_top = min(py_price(op), py_price(cp_val))
        body_bot = max(py_price(op), py_price(cp_val))
        body_h_px = max(1.5, body_bot - body_top)
        candle_parts.append(
            f'<rect x="{bx - body_w / 2:.1f}" y="{body_top:.1f}" '
            f'width="{body_w:.1f}" height="{body_h_px:.1f}" '
            f'fill="{color}" stroke="none"/>'
        )
    candles_svg = "\n  ".join(candle_parts)

    # ── Embedded volume (paneless): translucent bars anchored to the bottom of
    # the price pane, painted UNDER the candles — the Terminal / TradingView
    # idiom. Scaled to ~20% of the price-pane height so it reads as texture, not
    # a competing panel, and leaves the MACD pane its own full height. ─────────
    vol_overlay_svg = ""
    if volume_overlay and show_indicators:
        vband_h = PRICE_H * 0.20
        vband_bot = PAD_TOP + PRICE_H
        v_vis = [volume[i] for i in range(warmup, n) if volume[i] > 0]
        vmax = max(v_vis) if v_vis else 0.0
        if vmax > 0:
            vparts: list[str] = []
            for i in range(warmup, n):
                vv = volume[i]
                if vv <= 0:
                    continue
                bh = (vv / vmax) * vband_h
                bx = cx_bar(i)
                vcolor = "#4CAF50" if c[i] >= o[i] else "#E23B3B"
                vparts.append(
                    f'<rect x="{bx - body_w / 2:.1f}" y="{vband_bot - bh:.1f}" '
                    f'width="{body_w:.1f}" height="{max(0.6, bh):.1f}" '
                    f'fill="{vcolor}" opacity="0.28" stroke="none"/>'
                )
            vol_overlay_svg = "\n  ".join(vparts)

    # ── Right price axis: 5-7 round levels ──────────────────────────────────
    axis_x = PAD_L + chart_w + 6
    axis_parts: list[str] = []

    def _round_axis_levels(lo: float, hi: float, target: int = 6) -> list[float]:
        rng = hi - lo
        if rng <= 0:
            return [lo]
        step_raw = rng / target
        mag = 10 ** math.floor(math.log10(step_raw))
        chosen_step = mag * 10  # fallback
        for mult in (1, 2, 2.5, 5, 10):
            step = mag * mult
            if rng / step <= target + 1:
                chosen_step = step
                break
        first = math.ceil(lo / chosen_step) * chosen_step
        levels = []
        v = first
        while v <= hi + chosen_step * 0.01:
            if lo - chosen_step * 0.01 <= v <= hi + chosen_step * 0.01:
                levels.append(round(v, 6))
            v += chosen_step
        return levels or [lo, hi]

    for tick_price in _round_axis_levels(y_min, y_max, target=6):
        ty = py_price(tick_price)
        axis_parts.append(
            f'<text x="{axis_x + 2:.1f}" y="{ty + 4:.1f}" '
            f'fill="#6b7a99" font-size="10" font-family="monospace">'
            f'{_fmt_thousands(round(tick_price, 2))}</text>'
        )

    # Last-price pill — rx=2 (rounded corners), bold
    last_close = c[-1]
    prev_close = c[-2] if n >= 2 else last_close
    pill_color = "#4CAF50" if last_close >= prev_close else "#E23B3B"
    pill_y = py_price(last_close)
    pill_label = _fmt_thousands(last_close)
    pill_w = max(58, len(pill_label) * 7 + 12)
    pill_x = PAD_L + chart_w + 4
    axis_parts.append(
        f'<rect x="{pill_x:.1f}" y="{pill_y - 10:.1f}" '
        f'width="{pill_w}" height="18" rx="2" fill="{pill_color}"/>'
        f'<text x="{pill_x + pill_w / 2:.1f}" y="{pill_y + 3:.1f}" '
        f'fill="#ffffff" font-size="10" font-weight="bold" '
        f'font-family="monospace" text-anchor="middle">{_xesc(pill_label)}</text>'
    )
    axis_svg = "\n  ".join(axis_parts)

    # ── M2 overlays: AVWAP + POC ──────────────────────────────────────────────
    # Two layers, deliberately z-split (TrendSpider idiom):
    #   m2_overlay_svg — geometry (curve, POC line, VA band). Sits UNDER candles so
    #                    price always wins the foreground; the analytical line reads
    #                    as a quiet reference, never fights the tape.
    #   m2_label_svg   — the label chips. Painted in the TOP-MOST band (above candles,
    #                    axis, callout) so a label is never chopped by a wick or body.
    # A label is a legend, not decoration: it must be readable at thumbnail size, so
    # each rides a solid backing plate rather than a bare halo that a busy candle
    # field defeats.
    m2_overlay_svg = ""
    m2_label_svg = ""

    # Right edge where end-anchored chips sit (inside the price panel, clear of axis).
    _chip_right_x = PAD_L + chart_w - 5
    # Reserved vertical lanes at the right edge, seeded with the last-price pill band
    # so no overlay chip is ever drawn on top of the price pill. Each entry is a
    # (top, bottom) y-span already claimed; a new chip nudges until it clears them.
    _pill_cy = py_price(c[-1])
    _claimed_spans: list[tuple[float, float]] = [(_pill_cy - 12, _pill_cy + 12)]

    def _overlay_chip(
        text: str,
        cy: float,
        color: str,
        *,
        right_x: float = _chip_right_x,
        anchor_up: bool = True,
        leader_to_y: float | None = None,
    ) -> str:
        """A quiet legend chip: rounded #0E1420 plate + hairline + colored text,
        right-anchored, vertically de-conflicted against already-claimed spans.

        cy is the *preferred* baseline centre; anchor_up biases the nudge direction
        when a collision forces a move. Registers its own span so later chips avoid it.

        leader_to_y: when set, and the chip ends up meaningfully off its preferred
        centre, draw a short colored leader tick from the chip's left edge to that
        y (the curve/line endpoint it labels) so the association survives the nudge.
        """
        if not text:
            return ""
        _cw = int(len(text) * 6.4) + 14      # chip width from glyph count
        _ch = 17                              # chip height
        _cy = cy
        # De-conflict: if the chip's band overlaps a claimed span, step it away.
        for _ in range(6):
            _band = (_cy - _ch / 2, _cy + _ch / 2)
            _hit = None
            for (st, sb) in _claimed_spans:
                if _band[0] < sb and st < _band[1]:
                    _hit = (st, sb)
                    break
            if _hit is None:
                break
            # Push above or below the obstacle per preferred direction.
            if anchor_up:
                _cy = _hit[0] - _ch / 2 - 3
            else:
                _cy = _hit[1] + _ch / 2 + 3
        # Clamp inside the price panel so a chip never escapes into header/subpanels.
        _cy = max(PAD_TOP + _ch / 2 + 2, min(PAD_TOP + PRICE_H - _ch / 2 - 2, _cy))
        _claimed_spans.append((_cy - _ch / 2, _cy + _ch / 2))
        _rx = right_x
        _lx = _rx - _cw
        # Optional leader tick: only draw it if the chip was displaced far enough
        # from its target that the eye needs the tie-back (>6px), so an in-place
        # chip stays clean.
        _leader = ""
        if leader_to_y is not None and abs(leader_to_y - _cy) > 6:
            _leader = (
                f'<line x1="{_lx - 5:.1f}" y1="{leader_to_y:.1f}" '
                f'x2="{_lx:.1f}" y2="{_cy:.1f}" '
                f'stroke="{color}" stroke-width="1" stroke-opacity="0.5"/>'
            )
        return (
            _leader
            + f'<rect x="{_lx:.1f}" y="{_cy - _ch / 2:.1f}" '
            f'width="{_cw}" height="{_ch}" rx="4" '
            f'fill="#0E1420" fill-opacity="0.82" '
            f'stroke="{color}" stroke-opacity="0.55" stroke-width="1"/>'
            f'<text x="{_rx - 7:.1f}" y="{_cy + 4:.1f}" '
            f'fill="{color}" font-size="11" text-anchor="end" '
            f'font-family="sans-serif">{_xesc(text)}</text>'
        )

    # POC / Value-Area overlay ────────────────────────────────────────────────
    if poc_overlay is not None:
        _poc = poc_overlay.get("poc")
        _va_low = poc_overlay.get("va_low")
        _va_high = poc_overlay.get("va_high")
        _poc_label = poc_overlay.get("label", "")
        if _poc is not None and _va_low is not None and _va_high is not None:
            _poc_in_range = y_min <= _poc <= y_max
            # Value area band: clamp edges to panel.
            _band_top_price = min(_va_high, y_max)
            _band_bot_price = max(_va_low, y_min)
            if _band_bot_price < _band_top_price:
                _band_y_top = py_price(_band_top_price)
                _band_y_bot = py_price(_band_bot_price)
                # Quiet fill — the wash alone reads as a rendering smudge, so it is
                # BOUNDED: 1px hairlines at the value-area edges (only when the true
                # edge is in-panel, not a clamp artefact) + short right-axis edge
                # ticks. This makes it read as a deliberate zone, not a smear.
                m2_overlay_svg += (
                    f'<rect x="{PAD_L:.1f}" y="{_band_y_top:.1f}" '
                    f'width="{chart_w:.1f}" height="{_band_y_bot - _band_y_top:.1f}" '
                    f'fill="#5b9dff" fill-opacity="0.06" stroke="none"/>'
                )
                _edge_specs = []
                if _va_high <= y_max:
                    _edge_specs.append(_band_y_top)
                if _va_low >= y_min:
                    _edge_specs.append(_band_y_bot)
                for _ey in _edge_specs:
                    # full-width hairline at the edge
                    m2_overlay_svg += (
                        f'<line x1="{PAD_L:.1f}" y1="{_ey:.1f}" '
                        f'x2="{PAD_L + chart_w:.1f}" y2="{_ey:.1f}" '
                        f'stroke="#5b9dff" stroke-width="1" stroke-opacity="0.32"/>'
                    )
                    # stronger 8px edge tick where it meets the right axis
                    m2_overlay_svg += (
                        f'<line x1="{PAD_L + chart_w - 8:.1f}" y1="{_ey:.1f}" '
                        f'x2="{PAD_L + chart_w:.1f}" y2="{_ey:.1f}" '
                        f'stroke="#5b9dff" stroke-width="1.5" stroke-opacity="0.7"/>'
                    )
            # POC dashed line (only when in range).
            if _poc_in_range:
                _poc_y = py_price(_poc)
                m2_overlay_svg += (
                    f'<line x1="{PAD_L:.1f}" y1="{_poc_y:.1f}" '
                    f'x2="{PAD_L + chart_w:.1f}" y2="{_poc_y:.1f}" '
                    f'stroke="#5b9dff" stroke-width="1.5" stroke-dasharray="6 4" '
                    f'opacity="0.85"/>'
                )
                if _poc_label:
                    # POC chip prefers to sit just BELOW its line (the line is the
                    # reference; the chip labels it without covering the dashes).
                    m2_label_svg += _overlay_chip(
                        _poc_label, _poc_y + 12, "#5b9dff", anchor_up=False
                    )

    # AVWAP overlay ───────────────────────────────────────────────────────────
    if avwap_overlay is not None:
        _avwap_values = avwap_overlay.get("values") or []
        _avwap_label = avwap_overlay.get("label", "")
        _avwap_pts: list[str] = []
        _last_avwap_i: int | None = None
        _last_avwap_v: float | None = None
        for _i, _v in enumerate(_avwap_values):
            # skip the undrawn warmup lead-in — cx_bar(i<warmup) lands off-panel
            if _i >= warmup and _v is not None and _v == _v:
                _avwap_pts.append(f"{cx_bar(_i):.1f},{py_price(_v):.1f}")
                _last_avwap_i = _i
                _last_avwap_v = _v
        if len(_avwap_pts) >= 2:
            m2_overlay_svg += (
                f'<polyline points="{" ".join(_avwap_pts)}" '
                f'fill="none" stroke="#7c5cff" stroke-width="2" '
                f'opacity="0.95" stroke-linejoin="round" stroke-linecap="round"/>'
            )
            if _avwap_label and _last_avwap_i is not None and _last_avwap_v is not None:
                _av_end_y = py_price(_last_avwap_v)
                # Decide up/down by local candle air near the curve end: sample the
                # last few bars' body/wick extent and place the chip on the side with
                # room, so it never lands on the price path.
                _tail = range(max(0, n - 6), n)
                _tops = [py_price(h[i]) for i in _tail]           # smaller y = higher
                _bots = [py_price(l[i]) for i in _tail]
                _air_above = _av_end_y - min(_tops)   # px of clear space above curve end
                _air_below = max(_bots) - _av_end_y
                _up = _air_above >= _air_below
                _pref_y = _av_end_y - 14 if _up else _av_end_y + 14
                m2_label_svg += _overlay_chip(
                    _avwap_label, _pref_y, "#7c5cff", anchor_up=_up
                )

    # ── SMA overlays ────────────────────────────────────────────────────────
    # The curves paint UNDER the candles (quiet reference). The END-LABELS ride
    # the SAME reserved-lane chip system as the M2 labels (POC/AVWAP): a solid
    # backing plate, right-anchored inside the panel, de-conflicted against the
    # last-price pill and every other claimed span. Bare end-text used to clip at
    # the right edge and collide with the price pill ("50SMA"/"200SMA" mush) —
    # the chip lane fixes that on EVERY marketing chart, overlays or not.
    sma_svg = ""
    if show_indicators and n >= 50:
        sma50 = _sma(c, 50)
        sma200 = _sma(c, 200) if n >= 200 else [None] * n
        for sma_vals, sma_color, sma_label in [
            (sma50, "#F59E0B", "50 SMA"),
            (sma200, "#FBBF24", "200 SMA"),
        ]:
            pts_sma: list[str] = []
            for i, sv in enumerate(sma_vals):
                if sv is None or i < warmup:
                    continue
                pts_sma.append(f"{cx_bar(i):.1f},{py_price(sv):.1f}")
            if len(pts_sma) >= 2:
                sma_svg += (
                    f'<polyline points="{" ".join(pts_sma)}" '
                    f'fill="none" stroke="{sma_color}" stroke-width="1.2" '
                    f'opacity="0.8" stroke-dasharray="4,2"/>'
                )
                # End-label chip in the top-most label band. Its preferred baseline
                # is the curve's last value; the de-conflict nudge (biased toward the
                # curve's own side) keeps it near its line while dodging the pill and
                # sibling chips. A short leader tick ties the chip back to the curve.
                last_sma = next(sv for sv in reversed(sma_vals) if sv is not None)
                _sma_end_y = py_price(last_sma)
                m2_label_svg += _overlay_chip(
                    sma_label, _sma_end_y, sma_color,
                    anchor_up=True, leader_to_y=_sma_end_y,
                )

    # ── % Change callout box ─────────────────────────────────────────────────
    pct_callout_svg = ""
    anchor_close = c[eff_pct_from] if eff_pct_from is not None else None
    if anchor_close and anchor_close != 0:
        pct_chg = (last_close - anchor_close) / anchor_close * 100.0
        abs_chg = last_close - anchor_close
        bars_elapsed = n - 1 - eff_pct_from
        sign = "+" if pct_chg >= 0 else ""
        box_color = "#4CAF50" if pct_chg >= 0 else "#E23B3B"
        line1 = f"{sign}{abs_chg:.2f} ({sign}{pct_chg:.2f}%)"
        # Duration wording: bars → approximate week/month label
        if bars_elapsed <= 0:
            dur_str = "0 bars"
        elif bars_elapsed < 5:
            dur_str = f"{bars_elapsed} bar{'s' if bars_elapsed != 1 else ''}"
        elif bars_elapsed < 22:
            weeks = bars_elapsed / 5
            dur_str = f"{bars_elapsed} bars (~{weeks:.1f}wk)"
        elif bars_elapsed < 65:
            months = bars_elapsed / 21
            dur_str = f"{bars_elapsed} bars (~{months:.1f}mo)"
        else:
            months = bars_elapsed / 21
            dur_str = f"{bars_elapsed} bars (~{months:.0f}mo)"
        box_w, box_h = 165, 42
        # Anchor box near top-right of price panel
        box_x = PAD_L + chart_w - box_w - 4
        box_y = PAD_TOP + 10
        pct_callout_svg = (
            f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" '
            f'rx="4" fill="{box_color}" opacity="0.92"/>'
            f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 16:.1f}" '
            f'fill="#ffffff" font-size="12" font-weight="bold" '
            f'text-anchor="middle">{_xesc(line1)}</text>'
            f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 32:.1f}" '
            f'fill="#ffffffcc" font-size="10" text-anchor="middle">'
            f'{_xesc(dur_str)}</text>'
        )

    # ── Highlight zone + SETUP pill ──────────────────────────────────────────
    highlight_svg = ""
    if eff_highlight is not None:
        hx = cx_bar(eff_highlight)
        hy = py_price(c[eff_highlight])
        disc_r = max(slot_w * 2.5, 18)
        # translucent highlight disc
        highlight_svg += (
            f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{disc_r:.1f}" '
            f'fill="#4CAF50" fill-opacity="0.15" stroke="#4CAF50" '
            f'stroke-width="1.2" stroke-opacity="0.6"/>'
        )
        # Arrow pointing down from above
        arrow_y_top = hy - disc_r - 20
        arrow_y_bot = hy - disc_r - 4
        highlight_svg += (
            f'<line x1="{hx:.1f}" y1="{arrow_y_top:.1f}" '
            f'x2="{hx:.1f}" y2="{arrow_y_bot:.1f}" '
            f'stroke="#4CAF50" stroke-width="1.5" marker-end="url(#arrowhead)"/>'
        )
        # SETUP pill
        pill_label_s = "SETUP"
        pill_w_s = 50
        pill_x_s = hx - pill_w_s / 2
        pill_y_s = arrow_y_top - 20
        highlight_svg += (
            f'<rect x="{pill_x_s:.1f}" y="{pill_y_s:.1f}" '
            f'width="{pill_w_s}" height="16" rx="3" fill="#4CAF50"/>'
            f'<text x="{hx:.1f}" y="{pill_y_s + 11:.1f}" '
            f'fill="#ffffff" font-size="9" font-weight="bold" '
            f'text-anchor="middle">{pill_label_s}</text>'
        )

    # ── Company logo overlay (TrendSpider signature: giant white logo) ──────
    logo_svg = ""
    if logo_datauri:
        # Centered in upper third of price panel, ~34% chart width
        logo_w = chart_w * 0.34
        logo_x = PAD_L + (chart_w - logo_w) / 2
        logo_y = PAD_TOP + PRICE_H * 0.08
        logo_h = logo_w * 0.5  # reasonable aspect; SVG preserveAspectRatio handles it
        logo_svg = (
            f'<image href="{logo_datauri}" '
            f'x="{logo_x:.1f}" y="{logo_y:.1f}" '
            f'width="{logo_w:.1f}" height="{logo_h:.1f}" '
            f'opacity="0.88" preserveAspectRatio="xMidYMid meet"/>'
        )

    # ── Ghost watermark (fallback when no logo) ──────────────────────────────
    ghost_label = company_name if company_name else ticker
    ghost_font_size = max(48, min(90, chart_w // max(1, len(ghost_label))))
    ghost_x = PAD_L + chart_w / 2
    ghost_y = PAD_TOP + PRICE_H * 0.55
    # Ghost text is suppressed when logo is shown (logo replaces it in upper area)
    ghost_opacity = "0.04" if not logo_datauri else "0.02"
    ghost_svg = (
        f'<text x="{ghost_x:.1f}" y="{ghost_y:.1f}" '
        f'fill="#ffffff" fill-opacity="{ghost_opacity}" '
        f'font-size="{ghost_font_size}" font-weight="bold" '
        f'text-anchor="middle" dominant-baseline="middle">'
        f'{_xesc(ghost_label.upper())}</text>'
    )

    # ── Subpanels ────────────────────────────────────────────────────────────
    subpanel_svg_parts: list[str] = []
    sub_y_start = PAD_TOP + PRICE_H + 8
    divider_color = "#232A3D"

    for pi, panel_name in enumerate(active_panels):
        panel_y = sub_y_start + pi * SUBPANEL_H
        # Divider line
        subpanel_svg_parts.append(
            f'<line x1="{PAD_L}" y1="{panel_y}" '
            f'x2="{PAD_L + chart_w}" y2="{panel_y}" '
            f'stroke="{divider_color}" stroke-width="1"/>'
        )
        # Panel label — small-caps, muted-blue. #4a5568 was near-invisible at the
        # ~50% zoom of an X timeline (illegible = defect); #6b7a99 matches the axis
        # tick ink and survives the downscale while staying quiet under the tape.
        subpanel_svg_parts.append(
            f'<text x="{PAD_L + 4}" y="{panel_y + 13}" '
            f'fill="#6b7a99" font-size="9" font-weight="700" '
            f'letter-spacing="0.12em">'
            f'{_xesc(panel_name.upper())}</text>'
        )
        inner_y = panel_y + 18
        inner_h = SUBPANEL_H - 22

        if panel_name == "volume":
            vol_max = max((volume[i] for i in range(warmup, n) if volume[i] > 0), default=1.0)
            # Reserve 14% headroom so the tallest bar never jams the divider/label —
            # a full-height block reads as a solid wall; the gap gives it a top edge.
            vol_span = inner_h * 0.86
            for i in range(warmup, n):
                vv = volume[i]
                bx = cx_bar(i)
                bar_h = (vv / vol_max) * vol_span if vol_max > 0 else 0
                bar_y = inner_y + inner_h - bar_h
                vcolor = "#4CAF50" if c[i] >= o[i] else "#E23B3B"
                subpanel_svg_parts.append(
                    f'<rect x="{bx - body_w / 2:.1f}" y="{bar_y:.1f}" '
                    f'width="{body_w:.1f}" height="{max(1, bar_h):.1f}" '
                    f'fill="{vcolor}" opacity="0.55" stroke="none"/>'
                )
            # Volume axis: peak value at the level the tallest bar actually reaches,
            # with a "Vol" unit tag so the bare "360.8M" is not a naked number.
            vol_label = f"{vol_max / 1_000_000:.1f}M" if vol_max >= 1_000_000 else f"{vol_max:.0f}"
            _vol_peak_y = inner_y + inner_h - vol_span
            subpanel_svg_parts.append(
                f'<text x="{PAD_L + chart_w + 8}" y="{_vol_peak_y + 4:.1f}" '
                f'fill="#6b7a99" font-size="9" font-family="monospace">{_xesc(vol_label)}</text>'
                f'<text x="{PAD_L + chart_w + 8}" y="{_vol_peak_y + 15:.1f}" '
                f'fill="#4a556a" font-size="7" letter-spacing="0.08em">VOL</text>'
            )

        elif panel_name == "macd":
            macd_line, sig_line, hist_vals = _macd_lines(c)
            valid = [(i, m, s, hist_vals[i]) for i, (m, s) in enumerate(zip(macd_line, sig_line))
                     if i >= warmup and m is not None and s is not None and hist_vals[i] is not None]
            if valid:
                all_m = [m for _, m, s, _ in valid]
                all_h2 = [abs(hv) for _, _, _, hv in valid]
                m_min = min(all_m + [-v for v in all_m])
                m_max = max(all_m + [v for v in all_m])
                m_range = max(m_max - m_min, 1e-9)

                def macd_y(v: float) -> float:
                    center = inner_y + inner_h / 2
                    return center - (v / m_range) * (inner_h / 2) * 0.9

                # Zero line — a touch brighter than the divider so it anchors the
                # warmup region (first ~34 bars have no MACD; a visible baseline
                # keeps the panel from reading as half-rendered).
                zero_y = macd_y(0.0)
                subpanel_svg_parts.append(
                    f'<line x1="{PAD_L}" y1="{zero_y:.1f}" '
                    f'x2="{PAD_L + chart_w}" y2="{zero_y:.1f}" '
                    f'stroke="#2f3750" stroke-width="1"/>'
                )
                # Histogram bars
                for i, m, s, hv in valid:
                    bx = cx_bar(i)
                    hcolor = "#4CAF50" if hv >= 0 else "#E23B3B"
                    bar_top = min(macd_y(hv), zero_y)
                    bar_bot = max(macd_y(hv), zero_y)
                    bar_h_px = max(1, bar_bot - bar_top)
                    subpanel_svg_parts.append(
                        f'<rect x="{bx - body_w / 2:.1f}" y="{bar_top:.1f}" '
                        f'width="{body_w:.1f}" height="{bar_h_px:.1f}" '
                        f'fill="{hcolor}" opacity="0.5" stroke="none"/>'
                    )
                # MACD line — house blue (#5b9dff), not raw material-blue, so the
                # subpanel belongs to the same palette as the rest of the chart and
                # reads cleanly on #0E1420. Signal line stays amber for contrast.
                macd_pts = " ".join(
                    f"{cx_bar(i):.1f},{macd_y(m):.1f}" for i, m, s, _ in valid
                )
                subpanel_svg_parts.append(
                    f'<polyline points="{macd_pts}" fill="none" '
                    f'stroke="#5b9dff" stroke-width="1.5" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>'
                )
                # Signal line (amber, thinner)
                sig_pts = " ".join(
                    f"{cx_bar(i):.1f},{macd_y(s):.1f}" for i, m, s, _ in valid
                )
                subpanel_svg_parts.append(
                    f'<polyline points="{sig_pts}" fill="none" '
                    f'stroke="#F59E0B" stroke-width="1.2" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>'
                )
                # Right-axis: last MACD value (monospace, like the price axis)
                last_m = valid[-1][1]
                mc = "#4CAF50" if last_m >= 0 else "#E23B3B"
                subpanel_svg_parts.append(
                    f'<text x="{PAD_L + chart_w + 8}" y="{macd_y(last_m) + 4:.1f}" '
                    f'fill="{mc}" font-size="9" font-family="monospace">{last_m:.3f}</text>'
                )

        elif panel_name == "rsi":
            rsi_vals = _rsi(c, 14)
            valid_rsi = [(i, rv) for i, rv in enumerate(rsi_vals) if rv is not None and i >= warmup]

            def rsi_y(v: float) -> float:
                return inner_y + inner_h * (1.0 - v / 100.0)

            # Guide lines at 70/50/30
            for level, guide_color in [(70, "#E23B3B"), (50, "#6b7a99"), (30, "#4CAF50")]:
                gy = rsi_y(float(level))
                subpanel_svg_parts.append(
                    f'<line x1="{PAD_L}" y1="{gy:.1f}" '
                    f'x2="{PAD_L + chart_w}" y2="{gy:.1f}" '
                    f'stroke="{guide_color}" stroke-width="0.7" opacity="0.4"/>'
                    f'<text x="{PAD_L + chart_w + 8}" y="{gy + 4:.1f}" '
                    f'fill="{guide_color}" font-size="8" opacity="0.7">{level}</text>'
                )
            if len(valid_rsi) >= 2:
                rsi_pts = " ".join(
                    f"{cx_bar(i):.1f},{rsi_y(rv):.1f}" for i, rv in valid_rsi
                )
                subpanel_svg_parts.append(
                    f'<polyline points="{rsi_pts}" fill="none" '
                    f'stroke="#9C27B0" stroke-width="1.2"/>'
                )
                last_rv = valid_rsi[-1][1]
                rcolor = "#E23B3B" if last_rv >= 70 else ("#4CAF50" if last_rv <= 30 else "#9C27B0")
                subpanel_svg_parts.append(
                    f'<text x="{PAD_L + chart_w + 8}" y="{rsi_y(last_rv) + 4:.1f}" '
                    f'fill="{rcolor}" font-size="9">{last_rv:.1f}</text>'
                )

    subpanel_svg = "\n  ".join(subpanel_svg_parts)

    # ── Header: real favicon lockup + ticker/timeframe ──────────────────────
    header_bg = (
        f'<rect x="0" y="0" width="{width}" height="{HEADER_H}" '
        f'fill="#0A1020" opacity="0.9"/>'
    )
    # Real favicon logomark — gradient tile + M path, uid-suffixed to avoid collisions
    logo_tile_size = 34.0
    logo_cx = 8 + logo_tile_size / 2
    logo_cy = HEADER_H / 2
    logo_defs, logo_group = _favicon_logomark(logo_cx, logo_cy, size=logo_tile_size, uid=uid)
    # MASTERMIND wordmark — prominent, weight 900
    wordmark_x = logo_cx + logo_tile_size / 2 + 8
    wordmark_y = HEADER_H / 2 + 7
    wordmark_svg = (
        f'<text x="{wordmark_x:.1f}" y="{wordmark_y:.1f}" '
        f'fill="#ffffff" font-size="20" font-weight="900" '
        f'font-family="sans-serif" letter-spacing="0.07em">'
        f'MASTERMIND</text>'
    )
    # Ticker + timeframe (top-right)
    tf_right_x = width - PAD_R - 4
    ticker_svg = (
        f'<text x="{tf_right_x:.1f}" y="{HEADER_H / 2 - 2:.1f}" '
        f'fill="#ffffff" font-size="26" font-weight="bold" '
        f'text-anchor="end" font-family="sans-serif">'
        f'{_xesc(ticker.upper())}</text>'
        f'<text x="{tf_right_x:.1f}" y="{HEADER_H / 2 + 16:.1f}" '
        f'fill="#8899bb" font-size="13" text-anchor="end" '
        f'letter-spacing="1" font-family="sans-serif">'
        f'{_xesc(timeframe.upper())}</text>'
    )

    # ── Footer: brand bar (band + laser hairline + lockup + CTA button) ─────
    # footer_cta=None → full marketing bar; ""=brand-only (brain/admin);
    # custom text → quiet informational descriptor, no sales button (dossiers).
    if footer_cta is None:
        bar_defs, footer_svg = _brand_bar(
            width, height, uid, descriptor="Daily stock signals"
        )
    elif footer_cta == "":
        bar_defs, footer_svg = _brand_bar(width, height, uid, show_button=False)
    else:
        bar_defs, footer_svg = _brand_bar(
            width, height, uid, descriptor=footer_cta, show_button=False
        )

    # ── Date labels (bottom of price panel): 4-6 evenly spaced ─────────────
    date_y_pos = PAD_TOP + PRICE_H + 6
    date_svg = ""
    if dates:
        # Choose 4-6 evenly spaced indices across the VISIBLE window only.
        n_date_labels = min(6, max(4, n_vis // 15))
        date_indices = [
            warmup + int(round(i * (n_vis - 1) / (n_date_labels - 1)))
            for i in range(n_date_labels)
        ]
        # Deduplicate while preserving order
        seen: set[int] = set()
        date_parts = []
        for di in date_indices:
            if di in seen:
                continue
            seen.add(di)
            dx = cx_bar(di)
            anchor = "middle"
            if di == warmup:
                anchor = "start"
            elif di == n - 1:
                anchor = "end"
            date_parts.append(
                f'<text x="{dx:.1f}" y="{date_y_pos}" '
                f'fill="#4a556a" font-size="9" text-anchor="{anchor}">'
                f'{_xesc(dates[di])}</text>'
            )
        date_svg = "\n  ".join(date_parts)

    # ── Defs: arrowhead + favicon gradients ─────────────────────────────────
    arrowhead_def = (
        f'<marker id="arrowhead_{uid}" markerWidth="8" markerHeight="6" '
        f'refX="4" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="#4CAF50"/>'
        f'</marker>'
    )
    # Update any arrowhead references in highlight_svg to use uid
    highlight_svg_final = highlight_svg.replace(
        'url(#arrowhead)', f'url(#arrowhead_{uid})'
    )

    defs_svg = f'<defs>{arrowhead_def}{logo_defs}{bar_defs}</defs>'

    # ── Background rect ──────────────────────────────────────────────────────
    bg_rect = f'<rect width="{width}" height="{height}" fill="#0E1420"/>'

    svg = (
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}">\n'
        f'  {defs_svg}\n'
        f'  <!-- background -->\n'
        f'  {bg_rect}\n'
        f'  <!-- ghost watermark -->\n'
        f'  {ghost_svg}\n'
        f'  <!-- company logo overlay -->\n'
        f'  {logo_svg}\n'
        f'  <!-- embedded volume (paneless, under candles) -->\n'
        f'  {vol_overlay_svg}\n'
        f'  <!-- SMA overlays -->\n'
        f'  {sma_svg}\n'
        f'  <!-- M2 overlays: AVWAP + POC (over SMA, under candles) -->\n'
        f'  {m2_overlay_svg}\n'
        f'  <!-- candlesticks -->\n'
        f'  {candles_svg}\n'
        f'  <!-- highlight zone -->\n'
        f'  {highlight_svg_final}\n'
        f'  <!-- price axis -->\n'
        f'  {axis_svg}\n'
        f'  <!-- % change callout -->\n'
        f'  {pct_callout_svg}\n'
        f'  <!-- date labels -->\n'
        f'  {date_svg}\n'
        f'  <!-- M2 overlay labels (top-most in price panel, never occluded) -->\n'
        f'  {m2_label_svg}\n'
        f'  <!-- subpanels -->\n'
        f'  {subpanel_svg}\n'
        f'  <!-- header (rendered last so it sits on top) -->\n'
        f'  {header_bg}\n'
        f'  {logo_group}\n'
        f'  {wordmark_svg}\n'
        f'  {ticker_svg}\n'
        f'  <!-- footer -->\n'
        f'  {footer_svg}\n'
        f'</svg>'
    )
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# v2: M2 overlay builder (single seam for callers)
# ─────────────────────────────────────────────────────────────────────────────

def build_m2_overlays(
    ticker: str,
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    v: list[float],
    root: "Path | str",
) -> dict:
    """Build AVWAP + POC overlay dicts for render_chart_v2.

    Imports engine.indicators_m2 and calls:
      - earnings_proxy_anchor(df, lookback=min(63, len-1)) → anchor position
      - anchored_vwap(df, anchor) → pd.Series aligned to df index
      - volume_profile(df, window=min(126, len)) → profile dict | None

    Returns {"avwap_overlay": dict|None, "poc_overlay": dict|None}.
    Both values are None on any failure (fail-soft, logged at debug).
    Never raises.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    avwap_overlay: dict | None = None
    poc_overlay: dict | None = None

    try:
        import pandas as pd
        from engine import indicators_m2 as _m2

        n = len(c)
        if n < 2:
            return {"avwap_overlay": None, "poc_overlay": None}

        df = pd.DataFrame(
            {"open": o, "high": h, "low": l, "close": c, "volume": v},
            index=pd.to_datetime(dates),
        )

        # ── AVWAP overlay ────────────────────────────────────────────────────
        try:
            lookback = min(63, n - 1)
            anchor_pos = _m2.earnings_proxy_anchor(df, lookback=lookback)
            if anchor_pos is not None:
                avwap_series = _m2.anchored_vwap(df, anchor_pos)
                anchor_date = df.index[anchor_pos]
                anchor_label = anchor_date.strftime("%b %d")
                avwap_vals = [
                    float(_av) if not (_av != _av) else None
                    for _av in avwap_series
                ]
                avwap_overlay = {
                    "values": avwap_vals,
                    # Tight glance-tier label: "AVWAP · Jun 26" (date only). The
                    # anchor-kind honesty ("volume-spike anchor") lives in the post
                    # copy, not on the chart — a long form clutters the right edge and
                    # collides with the SMA end-labels. Date-only is honest for a daily
                    # anchor and never implies intraday precision.
                    "label": f"AVWAP · {anchor_label}",
                }
        except Exception as _e:
            _log.debug("build_m2_overlays: avwap failed: %s", _e)

        # ── POC / Value-Area overlay ─────────────────────────────────────────
        try:
            window = min(126, n)
            profile = _m2.volume_profile(df, window=window)
            if profile is not None:
                _poc_price = profile["poc"]
                poc_overlay = {
                    "poc": float(_poc_price),
                    "va_low": float(profile["va_low"]),
                    "va_high": float(profile["va_high"]),
                    "label": f"POC {_poc_price:.2f}",
                }
        except Exception as _e:
            _log.debug("build_m2_overlays: poc failed: %s", _e)

    except Exception as _e:
        _log.debug("build_m2_overlays: outer failure for %s: %s", ticker, _e)

    return {"avwap_overlay": avwap_overlay, "poc_overlay": poc_overlay}


# ─────────────────────────────────────────────────────────────────────────────
# v2: Earnings card renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_earnings_card(
    ticker: str,
    company_name: str,
    eps_actual: float,
    eps_est: float,
    rev_actual: float | None,
    rev_est: float | None,
    *,
    quarter: str | None = None,
    logo_datauri: str | None = None,
    logo_root: "Path | str | None" = None,
    width: int = 1000,
    height: int = 560,
) -> str:
    """Render a branded earnings illustration SVG.

    Dark card (#0E1420), real Mastermind favicon lockup top-left + wordmark,
    giant white company logo (centered hero when logo_datauri / logo_root provided),
    big TICKER EARNINGS header + quarter label, two stat blocks (EPS + Revenue) with
    BEAT/MISS/INLINE chips (green/red/grey) + surprise %, revenue column suppressed
    when rev_actual/rev_est are None (EPS-only card), branded footer CTA.

    Args:
        ticker: Stock ticker symbol.
        company_name: Full company display name.
        eps_actual: Reported EPS.
        eps_est: Consensus EPS estimate.
        rev_actual: Reported revenue in dollars, or None to omit revenue block.
        rev_est: Consensus revenue estimate in dollars, or None to omit.
        quarter: Quarter label, e.g. "Q2 2026". Shown below ticker.
        logo_datauri: Pre-resolved whitened data URI for company logo.
        logo_root: If logo_datauri is None and logo_root is provided, calls
            resolve_logo(ticker, logo_root) to auto-fetch + cache.
        width: Card width in px (default 1000).
        height: Card height in px (default 560).

    Returns:
        Self-contained SVG string. No <script>. All text _xesc'd. < 60 KB with logo.
    """
    # ── Auto-resolve logo ────────────────────────────────────────────────────
    if logo_datauri is None and logo_root is not None:
        logo_datauri = resolve_logo(ticker, logo_root)

    # ── Unique id suffix (deterministic, collision-safe) ────────────────────
    ec_uid = str(abs(hash(ticker + "ec")) % 10_000_000)

    # ── Beat/miss/inline classification ─────────────────────────────────────
    def _classify(actual: float, est: float) -> tuple[str, str, float]:
        """Returns (label, color, surprise_pct)."""
        if est == 0:
            surp = 0.0
        else:
            surp = (actual - est) / abs(est) * 100.0
        if abs(surp) < 0.5:
            return "INLINE", "#6b7a99", surp
        return ("BEAT", "#4CAF50", surp) if actual > est else ("MISS", "#E23B3B", surp)

    eps_label, eps_color, eps_surp = _classify(eps_actual, eps_est)
    has_rev = rev_actual is not None and rev_est is not None

    # ── Helper: wide chip (BEAT/MISS/INLINE) with surprise % below ──────────
    def _stat_chip(label: str, color: str, surp: float, cx: float, cy: float) -> str:
        cw, ch = 72, 26
        sign = "+" if surp >= 0 else ""
        surp_text = f"{sign}{surp:.1f}%"
        return (
            f'<rect x="{cx - cw / 2:.1f}" y="{cy - ch / 2:.1f}" '
            f'width="{cw}" height="{ch}" rx="5" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="1.2"/>'
            f'<text x="{cx:.1f}" y="{cy + 5:.1f}" fill="{color}" '
            f'font-size="12" font-weight="bold" text-anchor="middle">'
            f'{_xesc(label)}</text>'
            f'<text x="{cx:.1f}" y="{cy + 22:.1f}" fill="{color}" '
            f'font-size="10" text-anchor="middle" opacity="0.85">'
            f'{_xesc(surp_text)}</text>'
        )

    def _fmt_rev(v: float) -> str:
        if v >= 1e12:
            return f"${v / 1e12:.2f}T"
        if v >= 1e9:
            return f"${v / 1e9:.2f}B"
        if v >= 1e6:
            return f"${v / 1e6:.2f}M"
        return f"${v:,.2f}"

    # ── Brand lockup (top-left) ──────────────────────────────────────────────
    ec_logo_tile = 30.0
    logo_cx_brand = 14 + ec_logo_tile / 2
    logo_cy_brand = 14 + ec_logo_tile / 2
    ec_logo_defs, ec_logo_group = _favicon_logomark(
        logo_cx_brand, logo_cy_brand, size=ec_logo_tile, uid=ec_uid
    )
    wordmark_x = logo_cx_brand + ec_logo_tile / 2 + 8
    wordmark_y = logo_cy_brand + 7
    wordmark_svg = (
        f'<text x="{wordmark_x:.1f}" y="{wordmark_y:.1f}" '
        f'fill="#ffffff" font-size="17" '
        f'font-weight="900" font-family="sans-serif" letter-spacing="0.07em">'
        f'MASTERMIND</text>'
    )

    # ── Header band (dark strip) ─────────────────────────────────────────────
    header_h = 60
    header_bg = (
        f'<rect x="0" y="0" width="{width}" height="{header_h}" '
        f'fill="#0A1020" opacity="0.92"/>'
    )

    # ── Company logo (hero, centered below header) ───────────────────────────
    logo_svg = ""
    if logo_datauri:
        logo_area_top = header_h + 8
        logo_area_h = height * 0.30          # 30% of card height
        logo_w = width * 0.32
        logo_x_pos = (width - logo_w) / 2
        logo_svg = (
            f'<image href="{logo_datauri}" '
            f'x="{logo_x_pos:.1f}" y="{logo_area_top:.1f}" '
            f'width="{logo_w:.1f}" height="{logo_area_h:.1f}" '
            f'opacity="0.92" preserveAspectRatio="xMidYMid meet"/>'
        )

    # ── Main heading ─────────────────────────────────────────────────────────
    center_x = width / 2
    # Push content down when logo is present
    content_top = header_h + (height * 0.34 if logo_datauri else 24)

    ticker_y = content_top + 44
    heading_label = f"{ticker.upper()} EARNINGS"
    heading_size = max(32, min(52, int(width * 0.048)))
    heading_svg = (
        f'<text x="{center_x:.1f}" y="{ticker_y:.1f}" fill="#ffffff" '
        f'font-size="{heading_size}" font-weight="bold" '
        f'text-anchor="middle" font-family="sans-serif">'
        f'{_xesc(heading_label)}</text>'
    )

    # Quarter label
    quarter_svg = ""
    if quarter:
        quarter_y = ticker_y + 28
        quarter_svg = (
            f'<text x="{center_x:.1f}" y="{quarter_y:.1f}" fill="#8899bb" '
            f'font-size="15" text-anchor="middle" letter-spacing="1" '
            f'font-family="sans-serif">{_xesc(quarter.upper())}</text>'
        )
        company_y = ticker_y + 52
    else:
        company_y = ticker_y + 30
    company_svg = (
        f'<text x="{center_x:.1f}" y="{company_y:.1f}" fill="#6b7a99" '
        f'font-size="14" text-anchor="middle" font-family="sans-serif">'
        f'{_xesc(company_name)}</text>'
    )

    # ── Stat blocks ──────────────────────────────────────────────────────────
    stat_top = company_y + 28
    divider_y = stat_top - 8

    # Horizontal divider above stat blocks
    divider_svg = (
        f'<line x1="{width * 0.12:.1f}" y1="{divider_y:.1f}" '
        f'x2="{width * 0.88:.1f}" y2="{divider_y:.1f}" '
        f'stroke="#232A3D" stroke-width="1"/>'
    )

    if has_rev:
        # Two columns: EPS left, Revenue right
        col_l = width * 0.28
        col_r = width * 0.72
        rev_label, rev_color, rev_surp = _classify(rev_actual, rev_est)

        stat_svg = (
            # ── EPS column ──
            f'<text x="{col_l:.1f}" y="{stat_top + 16:.1f}" fill="#6b7a99" '
            f'font-size="11" text-anchor="middle" letter-spacing="2" '
            f'font-family="sans-serif">EPS</text>'
            f'<text x="{col_l:.1f}" y="{stat_top + 54:.1f}" fill="#ffffff" '
            f'font-size="34" font-weight="bold" text-anchor="middle" '
            f'font-family="sans-serif">{_xesc(f"${eps_actual:.2f}")}</text>'
            f'<text x="{col_l:.1f}" y="{stat_top + 76:.1f}" fill="#6b7a99" '
            f'font-size="12" text-anchor="middle" font-family="sans-serif">'
            f'Est: {_xesc(f"${eps_est:.2f}")}</text>'
        ) + _stat_chip(eps_label, eps_color, eps_surp, col_l, stat_top + 108) + (
            # ── Vertical divider ──
            f'<line x1="{center_x:.1f}" y1="{stat_top:.1f}" '
            f'x2="{center_x:.1f}" y2="{stat_top + 140:.1f}" '
            f'stroke="#232A3D" stroke-width="1"/>'
            # ── Revenue column ──
            f'<text x="{col_r:.1f}" y="{stat_top + 16:.1f}" fill="#6b7a99" '
            f'font-size="11" text-anchor="middle" letter-spacing="2" '
            f'font-family="sans-serif">REVENUE</text>'
            f'<text x="{col_r:.1f}" y="{stat_top + 54:.1f}" fill="#ffffff" '
            f'font-size="34" font-weight="bold" text-anchor="middle" '
            f'font-family="sans-serif">{_xesc(_fmt_rev(rev_actual))}</text>'
            f'<text x="{col_r:.1f}" y="{stat_top + 76:.1f}" fill="#6b7a99" '
            f'font-size="12" text-anchor="middle" font-family="sans-serif">'
            f'Est: {_xesc(_fmt_rev(rev_est))}</text>'
        ) + _stat_chip(rev_label, rev_color, rev_surp, col_r, stat_top + 108)
    else:
        # EPS-only: centered single column
        stat_svg = (
            f'<text x="{center_x:.1f}" y="{stat_top + 16:.1f}" fill="#6b7a99" '
            f'font-size="11" text-anchor="middle" letter-spacing="2" '
            f'font-family="sans-serif">EARNINGS PER SHARE</text>'
            f'<text x="{center_x:.1f}" y="{stat_top + 62:.1f}" fill="#ffffff" '
            f'font-size="44" font-weight="bold" text-anchor="middle" '
            f'font-family="sans-serif">{_xesc(f"${eps_actual:.2f}")}</text>'
            f'<text x="{center_x:.1f}" y="{stat_top + 86:.1f}" fill="#6b7a99" '
            f'font-size="13" text-anchor="middle" font-family="sans-serif">'
            f'vs. Est {_xesc(f"${eps_est:.2f}")}</text>'
        ) + _stat_chip(eps_label, eps_color, eps_surp, center_x, stat_top + 116)

    # ── Footer: brand bar (Source attribution rides the copyright line) ──────
    ec_bar_defs, footer_svg = _brand_bar(
        width, height, ec_uid,
        copyright_text="© 2026 Mastermind · Source: Company IR",
    )

    svg = (
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}">\n'
        f'  <defs>{ec_logo_defs}{ec_bar_defs}</defs>\n'
        f'  <!-- background -->\n'
        f'  <rect width="{width}" height="{height}" fill="#0E1420"/>\n'
        f'  <!-- company logo hero -->\n'
        f'  {logo_svg}\n'
        f'  <!-- main heading -->\n'
        f'  {heading_svg}\n'
        f'  {quarter_svg}\n'
        f'  {company_svg}\n'
        f'  <!-- stat blocks -->\n'
        f'  {divider_svg}\n'
        f'  {stat_svg}\n'
        f'  <!-- header band (on top) -->\n'
        f'  {header_bg}\n'
        f'  {ec_logo_group}\n'
        f'  {wordmark_svg}\n'
        f'  <!-- footer -->\n'
        f'  {footer_svg}\n'
        f'</svg>'
    )
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# v2: Watchlist share-card renderer (multi-ticker theme lists — docket D-WL)
# ─────────────────────────────────────────────────────────────────────────────
#
# Design intent (docs/DESIGN_DOCTRINE.md + frontend-design skill):
#   Multi-ticker posts ("Social media selling off: $SNAP -3.4% $RBLX -4.3% …")
#   used to ship as bland text. This card reframes them as a SCREENSHOT OF A
#   PREMIUM SAAS WATCHLIST PANEL — the third member of the earnings / breaking
#   card family (dark #0E1420 base, favicon lockup + wordmark, _brand_bar CTA
#   footer). Where the sibling cards are editorial POSTERS (one centered hero),
#   a watchlist is a PRODUCT surface: dense, rhythmic, scannable rows that read
#   like live app cells, so the reader feels they are looking over the shoulder
#   of someone using the terminal — not reading a caption.
#
# Signature element: every row is a raised cell (plate + hairline) fronted by a
#   thin vertical accent SPINE tinted to that row's direction (up green / down
#   red), while the panel title carries the house indigo→blue gradient of the
#   _brand_bar laser. The spines rhyme with the footer laser and bind the rows
#   into a single "watchlist object". Per-row 10-session sparklines (direction-
#   colored) are what actually sell "live watchlist, not a text post"; a row
#   with no price history degrades to no sparkline — never a broken glyph.
#
# Palette is 100% inherited (no invented colors): family up #4CAF50 / down
#   #E23B3B, base #0E1420, header #0A1020, hairline #232A3D, muted ink #6b7a99,
#   house gradient #5b9dff→#7c5cff. Pills reuse the earnings-card chip idiom
#   (colored fill at 0.16 opacity + colored ink) so they read as native.

# Deterministic monogram-tile palette — house-gradient siblings, used only when
# a company logo cannot be resolved. Each is a (top, bottom) gradient pair.
_WL_MONO_PALETTE = [
    ("#3b82f6", "#6366f1"),   # blue → indigo (house)
    ("#6366f1", "#7c5cff"),   # indigo → violet
    ("#0ea5e9", "#3b82f6"),   # sky → blue
    ("#7c5cff", "#a855f7"),   # violet → purple
    ("#14b8a6", "#0ea5e9"),   # teal → sky
    ("#f59e0b", "#f97316"),   # amber → orange (warm outlier for balance)
]


def _wl_sparkline(
    closes: "list[float] | None",
    x: float,
    y: float,
    w: float,
    h: float,
    color: str,
    uid: str,
) -> str:
    """A tiny direction-colored area sparkline for one watchlist row.

    Returns "" (draw nothing) when there is too little data — the row then reads
    as a clean logo/price cell rather than a broken glyph. Baseline is the series
    min so the line hugs the cell floor; a faint area fill gives it body at
    thumbnail size. All geometry is local to the (x, y, w, h) box.
    """
    if not closes or len(closes) < 3:
        return ""
    vals = [float(v) for v in closes if v is not None and v == v]
    if len(vals) < 3:
        return ""
    lo = min(vals)
    hi = max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    inner_pad = 1.5

    def sx(i: int) -> float:
        return x + inner_pad + (i / (n - 1)) * (w - 2 * inner_pad)

    def sy(v: float) -> float:
        # small vertical inset so peaks/troughs never clip the cell
        return y + inner_pad + (h - 2 * inner_pad) * (1.0 - (v - lo) / rng)

    pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals))
    area = (
        f"{sx(0):.1f},{y + h:.1f} " + pts + f" {sx(n - 1):.1f},{y + h:.1f}"
    )
    grad_id = f"wlspk_{uid}"
    return (
        f'<linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="0.28"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient>'
        f'<polygon points="{area}" fill="url(#{grad_id})" stroke="none"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def _wl_monogram(ticker: str, cx: float, cy: float, size: float, uid: str) -> tuple[str, str]:
    """Deterministic circular monogram — the fallback when no color logo resolves.

    A house-gradient CIRCLE (matching the avatar-chip silhouette) picked from the
    ticker hash, with the ticker's leading initial in white. Circular — not a
    rounded square — so a monogram and a logo chip share one silhouette and the
    column never looks half-avatar / half-tile. Reads as a deliberate avatar,
    never a broken-image glyph. Returns (defs, group).
    """
    r = size / 2.0
    tk = "".join(ch for ch in str(ticker).upper() if ch.isalnum())
    # A single initial reads as a deliberate avatar; two letters look like a
    # placeholder abbreviation. Keep it to the leading glyph.
    letters = (tk[:1] or "•")
    idx = (zlib.crc32(tk.encode("utf-8")) % len(_WL_MONO_PALETTE)) if tk else 0
    c_top, c_bot = _WL_MONO_PALETTE[idx]
    grad_id = f"wlmono_{uid}"
    defs = (
        f'<linearGradient id="{grad_id}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c_top}"/>'
        f'<stop offset="1" stop-color="{c_bot}"/>'
        f'</linearGradient>'
    )
    fsize = size * 0.46
    group = (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="url(#{grad_id})"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#ffffff" '
        f'fill-opacity="0.07"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r - 0.5:.1f}" fill="none" '
        f'stroke="#ffffff" stroke-opacity="0.14" stroke-width="1"/>'
        f'<text x="{cx:.1f}" y="{cy + fsize * 0.35:.1f}" fill="#ffffff" '
        f'font-size="{fsize:.1f}" font-weight="800" text-anchor="middle" '
        f'font-family="sans-serif" letter-spacing="0.01em">{_xesc(letters)}</text>'
    )
    return defs, group


def _wl_avatar_chip(logo_datauri: str, cx: float, cy: float, size: float, uid: str) -> tuple[str, str]:
    """A light circular avatar chip housing a full-color company logo.

    The premium-fintech idiom: a near-white circle with a subtle cool rim and a
    soft inner shadow, the logo centered with ~22% padding. Any brand mark — dark
    or light, square or round — reads as intentional inside it, and the light disc
    lifts off the dark card the way an app-icon does off a home screen. Returns
    (defs, group). The logo is clipped to the disc so a wide wordmark can never
    bleed past the rim.
    """
    r = size / 2.0
    pad = size * 0.22          # inner padding — the logo occupies the middle ~56%
    inner = size - 2 * pad
    clip_id = f"wlav_{uid}"
    grad_id = f"wlavg_{uid}"
    defs = (
        f'<clipPath id="{clip_id}"><circle cx="{cx:.1f}" cy="{cy:.1f}" '
        f'r="{r - 1:.1f}"/></clipPath>'
        # Faint top-down sheen so the disc reads as a lit surface, not a flat dot.
        f'<linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#ffffff"/>'
        f'<stop offset="1" stop-color="#E7ECF6"/>'
        f'</linearGradient>'
    )
    group = (
        # Light disc + cool rim (the chip).
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="url(#{grad_id})"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r - 0.5:.1f}" fill="none" '
        f'stroke="#C3CEE0" stroke-width="1"/>'
        # Full-color logo, padded + clipped to the disc.
        f'<image href="{logo_datauri}" '
        f'x="{cx - inner / 2:.1f}" y="{cy - inner / 2:.1f}" '
        f'width="{inner:.1f}" height="{inner:.1f}" '
        f'preserveAspectRatio="xMidYMid meet" clip-path="url(#{clip_id})"/>'
    )
    return defs, group


def render_watchlist_card(
    title: str,
    rows: "list[dict]",
    *,
    as_of: str | None = None,
    logo_root: "Path | str | None" = None,
    subtitle: str | None = None,
    width: int = 1080,
    height: int | None = 1350,
) -> str:
    """Render a branded watchlist share-card SVG in the Mastermind card family.

    Reframes a plain multi-ticker text post ("Social media selling off:
    $SNAP -3.4% $RBLX -4.3% …") as a screenshot of a premium SaaS watchlist
    panel on a phone: dark #0E1420 base, favicon lockup + wordmark, a titled
    panel with a column-label header, one raised cell per ticker (rank rail +
    light color-logo avatar chip + ticker/name + 10-session sparkline +
    right-aligned price + colored % pill), and the shared _brand_bar CTA footer.
    The third member of the earnings / breaking card family.

    v2 (portrait, mobile-first): defaults are 1080×1350 (4:5) — the tallest image
    X renders un-cropped in a phone timeline. The canvas is assumed displayed at
    ~390px wide (2.8x downscale), so type is sized generously (tickers/prices
    ~44-52px on canvas) and nothing on-canvas is smaller than ~26px. The signature
    is the RANK RAIL: the magnitude order is a true sequence, so each cell carries
    its ordinal on a left spine fused with the direction accent.

    Args:
        title: Theme / list name (the hero, e.g. "Social media selling off").
        rows: List of dicts, each {ticker, name (optional), price, pct_change}.
            4-8 rows typical; 3-10 handled gracefully via height auto-scaling.
            price / pct_change may be None → the cell degrades cleanly (no pill /
            no price) rather than printing a placeholder dash.
        as_of: Optional as-of stamp shown in the panel header (e.g. "Jul 20").
        logo_root: If provided, each row's logo is auto-resolved + cached via
            resolve_color_logo(ticker, logo_root) — the ORIGINAL full-color icon,
            housed in a light avatar chip. Rows with no resolvable logo fall back
            to a deterministic circular gradient monogram.
        subtitle: Optional one-line plain-word stance under the title
            (Tier-1 doctrine: every panel answers "so what do I do"). Omitted
            cleanly when None.
        width: Card width in px (default 1080; back-compat — pass 1000 for the
            old landscape geometry).
        height: Card height in px (default 1350 = 4:5 portrait). Pass None to
            auto-scale to the row count instead (old behavior); explicit height
            wins over both.

    Returns:
        Self-contained SVG string. No <script>. All text _xesc'd. Deterministic.
        Rows are sorted by |pct_change| descending unless the caller pre-sorts
        (a caller signals "leave my order" by passing rows already in order — we
        cannot detect that, so magnitude sort is the documented default; pass
        pre-sorted rows and they will be re-sorted by magnitude by design).
    """
    # ── Normalize + sort rows (magnitude-descending; None pct sinks to bottom) ──
    safe_rows: list[dict] = [r for r in (rows or []) if isinstance(r, dict)]
    # Cap to a sane render window; 3-10 is the supported band.
    safe_rows = safe_rows[:10]

    def _pct_of(r: dict) -> float:
        try:
            return abs(float(r.get("pct_change")))
        except (TypeError, ValueError):
            return -1.0  # missing pct → sinks below any real magnitude

    safe_rows = sorted(safe_rows, key=_pct_of, reverse=True)
    n_rows = len(safe_rows)

    # ── Deterministic id suffix (zlib.crc32: PYTHONHASHSEED-stable) ─────────
    wl_uid = str(zlib.crc32(((title or "") + "wl").encode("utf-8")) & 0xFFFFFFFF)

    # ── Layout geometry — scaled ~1.9x from the old 1000-wide landscape so every
    # element clears the ~26px on-canvas floor (≈9.5pt at the 2.8x phone
    # downscale). Row height and type are the load-bearing legibility levers. ──
    HEADER_H = 92                 # brand band (family constant, portrait scale)
    PAD = 56                      # left/right card gutter
    # Title block reserves room BELOW the header for: eyebrow + title baseline +
    # (optional stance line) + breathing room before the column-label strip.
    TITLE_BLOCK = 214 if subtitle else 176   # header→top of column-label strip
    COLHEAD_H = 40                # column-label strip
    ROW_H = 108                   # one watchlist cell (generous — legible at 390px)
    ROW_GAP = 16                  # air between cells
    FOOTER_H = 72                 # _brand_bar band (portrait scale)
    PANEL_TOP = HEADER_H + TITLE_BLOCK   # y where the column-label strip begins
    rows_span = n_rows * ROW_H + max(0, n_rows - 1) * ROW_GAP
    auto_h = PANEL_TOP + COLHEAD_H + 26 + rows_span + 40 + FOOTER_H
    # Portrait default (1350) unless the caller pins a height; height=None opts
    # back into row-count auto-scaling (old behavior).
    if height is not None:
        H = int(height)
    else:
        H = int(auto_h)
    # If a fixed portrait canvas can't fit the rows at the default rhythm,
    # COMPRESS the row rhythm toward a legibility floor first: X crops images
    # taller than 4:5 in the timeline, so the pinned height is the hard
    # platform constraint. Only grow past it when even floor-rhythm rows
    # cannot fit (pathological row counts).
    if height is not None and auto_h > H:
        _ROW_H_MIN = 88.0   # ~31px displayed at the 2.8x phone downscale
        _ROW_GAP_MIN = 10.0
        _chrome = PANEL_TOP + COLHEAD_H + 26 + 40 + FOOTER_H
        _avail = H - _chrome
        _row_h = (_avail - max(0, n_rows - 1) * _ROW_GAP_MIN) / max(1, n_rows)
        if _row_h >= _ROW_H_MIN:
            ROW_H = min(float(ROW_H), _row_h)
            if n_rows > 1:
                ROW_GAP = min(
                    float(ROW_GAP),
                    (_avail - n_rows * ROW_H) / (n_rows - 1),
                )
            else:
                ROW_GAP = 0.0
            rows_span = n_rows * ROW_H + max(0, n_rows - 1) * ROW_GAP
        else:
            H = int(auto_h)

    panel_x = PAD
    panel_w = width - 2 * PAD
    center_x = width / 2  # noqa: F841 — kept for symmetry with siblings

    defs_parts: list[str] = []
    body_parts: list[str] = []

    # ── Panel title gradient (house indigo→blue) — the one saturated title ─────
    title_grad_id = f"wltitle_{wl_uid}"
    defs_parts.append(
        f'<linearGradient id="{title_grad_id}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#5b9dff"/>'
        f'<stop offset="0.55" stop-color="#6366f1"/>'
        f'<stop offset="1" stop-color="#7c5cff"/>'
        f'</linearGradient>'
    )

    # ── Title + eyebrow + optional stance subtitle ────────────────────────────
    eyebrow_y = HEADER_H + 58
    body_parts.append(
        f'<rect x="{PAD}" y="{eyebrow_y - 18:.1f}" width="17" height="17" '
        f'rx="4" fill="url(#{title_grad_id})"/>'
        f'<text x="{PAD + 30}" y="{eyebrow_y - 2:.1f}" fill="#8899bb" '
        f'font-size="20" font-weight="700" font-family="sans-serif" '
        f'letter-spacing="5">WATCHLIST</text>'
    )
    title_y = eyebrow_y + 62
    title_text = str(title or "Watchlist")
    # Size the title down for very long theme names so it never collides with
    # the as-of stamp on the right. Portrait scale — the title is the hero.
    t_size = 56 if len(title_text) <= 22 else (
        46 if len(title_text) <= 30 else (38 if len(title_text) <= 44 else 30))
    body_parts.append(
        f'<text x="{PAD}" y="{title_y:.1f}" fill="#ffffff" '
        f'font-size="{t_size}" font-weight="800" font-family="sans-serif" '
        f'letter-spacing="-0.015em">{_xesc(title_text)}</text>'
    )
    # As-of stamp — right-aligned on the eyebrow baseline (one stamp per panel).
    if as_of:
        body_parts.append(
            f'<text x="{width - PAD:.1f}" y="{eyebrow_y - 2:.1f}" fill="#6b7a99" '
            f'font-size="20" text-anchor="end" font-family="sans-serif" '
            f'letter-spacing="0.5">{_xesc(str(as_of))}</text>'
        )
    if subtitle:
        body_parts.append(
            f'<text x="{PAD}" y="{title_y + 42:.1f}" fill="#a7b4cc" '
            f'font-size="24" font-family="sans-serif">{_xesc(str(subtitle))}</text>'
        )

    # ── Panel surface (subtle raised card the rows live inside) ───────────────
    # Starts just above the column-label strip so the title + stance line read as
    # a header ABOVE the panel (like a real app's list section), not inside it.
    panel_top = PANEL_TOP - 22
    panel_bot = H - FOOTER_H - 22
    body_parts.append(
        f'<rect x="{panel_x - 10:.1f}" y="{panel_top:.1f}" '
        f'width="{panel_w + 20:.1f}" height="{panel_bot - panel_top:.1f}" '
        f'rx="26" fill="#0B111C" stroke="#1B2333" stroke-width="1.5"/>'
    )

    # ── Column-label strip (this is the "app panel" tell) ─────────────────────
    col_y = PANEL_TOP + 12
    # x anchors: rail | avatar | name-block ... sparkline | price | pct-pill(right)
    inner_l = panel_x + 30
    inner_r = panel_x + panel_w - 30
    rail_w = 46                            # left rank rail column width
    sym_x = inner_l + rail_w              # where the SYMBOL cluster begins
    price_col_x = inner_r - 200           # right edge of price numerals
    pill_col_x = inner_r                  # right edge of pct pill
    spark_w = 150
    spark_r = price_col_x - 236           # right edge of sparkline box
    spark_l = spark_r - spark_w
    body_parts.append(
        f'<text x="{sym_x:.1f}" y="{col_y:.1f}" fill="#5c6a86" '
        f'font-size="18" font-weight="700" font-family="sans-serif" '
        f'letter-spacing="2.5">SYMBOL</text>'
        f'<text x="{price_col_x:.1f}" y="{col_y:.1f}" fill="#5c6a86" '
        f'font-size="18" font-weight="700" text-anchor="end" '
        f'font-family="sans-serif" letter-spacing="2.5">LAST</text>'
        f'<text x="{pill_col_x:.1f}" y="{col_y:.1f}" fill="#5c6a86" '
        f'font-size="18" font-weight="700" text-anchor="end" '
        f'font-family="sans-serif" letter-spacing="2.5">CHANGE</text>'
        f'<line x1="{inner_l:.1f}" y1="{col_y + 18:.1f}" '
        f'x2="{inner_r:.1f}" y2="{col_y + 18:.1f}" '
        f'stroke="#1B2333" stroke-width="1.5"/>'
    )

    # ── Rows ─────────────────────────────────────────────────────────────────
    UP, DOWN, FLAT = "#4CAF50", "#E23B3B", "#6b7a99"
    # Distribute free vertical space as an even inter-row GAP so the rows fill the
    # panel from the column header down (the real-app list idiom) — centering the
    # whole block instead would strand the header above a void on short lists. The
    # gap is capped so a 3-row card never looks like 3 lonely bars in a big box.
    rows_top = col_y + 34
    _rows_region_bot = panel_bot - 26
    _slack = (_rows_region_bot - rows_top) - rows_span
    if n_rows > 1 and _slack > 0:
        _gap_add = min(_slack / (n_rows - 1), ROW_H * 0.9)
        eff_gap = ROW_GAP + _gap_add
        # Any slack the gap cap couldn't absorb (very short lists) is split above
        # and below so the block sits centered, not top-anchored over a void.
        _residual = _slack - _gap_add * (n_rows - 1)
        rows_top += max(0.0, _residual / 2.0)
    else:
        eff_gap = ROW_GAP
    for i, r in enumerate(safe_rows):
        ry = rows_top + i * (ROW_H + eff_gap)
        row_cy = ry + ROW_H / 2.0
        ruid = f"{wl_uid}r{i}"
        ticker = str(r.get("ticker", "") or "").upper()[:8]
        name = str(r.get("name", "") or "").strip()

        # Direction + numbers (NaN treated same as None — degrade, don't print "nan")
        try:
            pct = float(r.get("pct_change"))
            has_pct = not math.isnan(pct)
            if not has_pct:
                pct = 0.0
        except (TypeError, ValueError):
            pct = 0.0
            has_pct = False
        up = pct > 0
        down = pct < 0
        dcolor = UP if up else (DOWN if down else FLAT)
        spine_color = dcolor if has_pct else "#3a4466"

        # Row cell plate + direction accent spine.
        body_parts.append(
            f'<rect x="{inner_l - 12:.1f}" y="{ry:.1f}" '
            f'width="{inner_r - inner_l + 24:.1f}" height="{ROW_H:.1f}" '
            f'rx="18" fill="#141C2C" stroke="#20293C" stroke-width="1.5"/>'
            f'<rect x="{inner_l - 12:.1f}" y="{ry:.1f}" width="6" height="{ROW_H:.1f}" '
            f'rx="3" fill="{spine_color}"/>'
        )

        # Rank rail — the signature. The magnitude order is a true sequence, so
        # each cell carries its ordinal on the left spine (tinted to direction),
        # turning the sort into visible information rather than decoration.
        rank_x = inner_l + rail_w / 2 - 8
        body_parts.append(
            f'<text x="{rank_x:.1f}" y="{row_cy + 11:.1f}" fill="{spine_color}" '
            f'font-size="32" font-weight="800" text-anchor="middle" '
            f'font-family="sans-serif" fill-opacity="0.9" '
            f'letter-spacing="-0.03em">{i + 1}</text>'
        )

        # Avatar chip: full-color logo in a light disc, else circular monogram.
        av = 58.0
        av_cx = sym_x + av / 2
        color_uri = resolve_color_logo(ticker, logo_root) if logo_root else None
        if color_uri:
            a_defs, a_group = _wl_avatar_chip(color_uri, av_cx, row_cy, av, ruid)
            defs_parts.append(a_defs)
            body_parts.append(a_group)
        else:
            m_defs, m_group = _wl_monogram(ticker, av_cx, row_cy, av, ruid)
            defs_parts.append(m_defs)
            body_parts.append(m_group)

        # Ticker + name block.
        text_x = av_cx + av / 2 + 24
        if name:
            body_parts.append(
                f'<text x="{text_x:.1f}" y="{row_cy - 8:.1f}" fill="#ffffff" '
                f'font-size="34" font-weight="800" font-family="sans-serif" '
                f'letter-spacing="0.005em">{_xesc(ticker)}</text>'
                f'<text x="{text_x:.1f}" y="{row_cy + 26:.1f}" fill="#7d8aa5" '
                f'font-size="21" font-family="sans-serif">'
                f'{_xesc(name[:24])}</text>'
            )
        else:
            body_parts.append(
                f'<text x="{text_x:.1f}" y="{row_cy + 11:.1f}" fill="#ffffff" '
                f'font-size="36" font-weight="800" font-family="sans-serif" '
                f'letter-spacing="0.005em">{_xesc(ticker)}</text>'
            )

        # Sparkline (10-session closes) — direction-colored; silent if no data.
        spark = ""
        if logo_root is not None:
            closes = load_closes(ticker, logo_root, n=10)
            if closes is not None:
                _, cvals = closes
                spark = _wl_sparkline(
                    cvals, spark_l, ry + 26, spark_w, ROW_H - 52, dcolor, ruid
                )
        if spark:
            body_parts.append(spark)

        # Price (right-aligned, tabular monospace precision).
        # NaN is treated same as None: no price rendered, no "nan" in output.
        try:
            price = float(r.get("price"))
            if not math.isnan(price):
                price_s = f"{price:,.2f}"
                body_parts.append(
                    f'<text x="{price_col_x:.1f}" y="{row_cy + 11:.1f}" fill="#e6ecf6" '
                    f'font-size="34" font-weight="700" text-anchor="end" '
                    f'font-family="monospace" letter-spacing="-0.03em">'
                    f'{_xesc(price_s)}</text>'
                )
        except (TypeError, ValueError):
            pass

        # Percent pill (earnings-chip idiom: colored fill 0.16 + colored ink).
        if has_pct:
            sign = "+" if pct >= 0 else "−"   # true minus glyph for optical weight
            pct_txt = f"{sign}{abs(pct):.1f}%"
            arrow = "▲" if up else ("▼" if down else "•")
            pill_label = f"{arrow} {pct_txt}"
            pw = 40 + int(len(pill_label) * 15.6)
            ph = 54
            px0 = pill_col_x - pw
            py0 = row_cy - ph / 2.0
            body_parts.append(
                f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{pw}" height="{ph}" '
                f'rx="16" fill="{dcolor}" fill-opacity="0.16" '
                f'stroke="{dcolor}" stroke-opacity="0.5" stroke-width="1.5"/>'
                f'<text x="{px0 + pw / 2:.1f}" y="{row_cy + 9:.1f}" fill="{dcolor}" '
                f'font-size="27" font-weight="700" text-anchor="middle" '
                f'font-family="sans-serif" letter-spacing="0.01em">'
                f'{_xesc(pill_label)}</text>'
            )

    # ── Brand lockup (top-left) — identical family treatment (portrait scale) ──
    wl_logo_tile = 46.0
    logo_cx_brand = 24 + wl_logo_tile / 2
    logo_cy_brand = 22 + wl_logo_tile / 2
    wl_logo_defs, wl_logo_group = _favicon_logomark(
        logo_cx_brand, logo_cy_brand, size=wl_logo_tile, uid=wl_uid
    )
    defs_parts.append(wl_logo_defs)
    wordmark_x = logo_cx_brand + wl_logo_tile / 2 + 13
    wordmark_y = logo_cy_brand + 10
    header_svg = (
        f'<rect x="0" y="0" width="{width}" height="{HEADER_H}" '
        f'fill="#0A1020" opacity="0.92"/>'
        + wl_logo_group
        + f'<text x="{wordmark_x:.1f}" y="{wordmark_y:.1f}" fill="#ffffff" '
        f'font-size="26" font-weight="900" font-family="sans-serif" '
        f'letter-spacing="0.07em">MASTERMIND</text>'
        # Desk tag, right of header — signals the lane (family idiom).
        f'<text x="{width - 24}" y="{logo_cy_brand + 8:.1f}" fill="#6b7a99" '
        f'font-size="18" text-anchor="end" font-family="sans-serif" '
        f'letter-spacing="3">WATCHLIST</text>'
    )

    # ── Footer — shared brand bar (the ad unit) ───────────────────────────────
    wl_bar_defs, footer_svg = _brand_bar(
        width, H, wl_uid,
        copyright_text="© 2026 Mastermind",
        band_h=FOOTER_H,
    )

    defs_svg = "".join(defs_parts) + wl_bar_defs
    svg = (
        f'<svg viewBox="0 0 {width} {H}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{H}">\n'
        f'  <defs>{defs_svg}</defs>\n'
        f'  <!-- background -->\n'
        f'  <rect width="{width}" height="{H}" fill="#0E1420"/>\n'
        f'  <!-- panel + title + rows -->\n'
        f'  {"".join(body_parts)}\n'
        f'  <!-- header band (on top) -->\n'
        f'  {header_svg}\n'
        f'  <!-- footer -->\n'
        f'  {footer_svg}\n'
        f'</svg>'
    )
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# v2: Breaking-news card renderer (Radar / Breaking Desks — docket D05)
# ─────────────────────────────────────────────────────────────────────────────
#
# Design intent (see docs/DESIGN_DOCTRINE.md + research/marketing_dockets/D05):
#   The SOURCE is the hero, not the scream. This is an accountable market-
#   intelligence brand, so the signature element is a self-grading credibility
#   chip — the tier the card actually used (official > wire > aggregator) is
#   encoded in the chip's *weight* so an aggregator can never look as
#   authoritative as an official feed (the anti-laundering trap is law).
#   Amber (#F5A623) is the breaking accent — urgent like a wire dateline, not
#   tabloid red (red stays reserved for "down" price semantics). The card never
#   adds interpretation ("bullish") — stance lives in the signal lanes.
#
# Tier chip system (weight = trust):
#   official    → filled amber, dark ink        (strongest)
#   wire        → amber outline, hollow          (medium)
#   aggregator  → grey outline, muted            (visibly lighter, honest)

# Shared with render_breaking_card; kept module-private.
_BREAK_AMBER = "#F5A623"       # breaking accent — wire-dateline urgency, not tabloid red
_BREAK_GREY = "#6b7a99"        # family neutral (matches earnings-card muted ink)
_BREAK_UP = "#4CAF50"          # family up-color
_BREAK_DOWN = "#E23B3B"        # family down-color


def _break_tier_style(tier: str) -> dict[str, str]:
    """Map a source_tier to its chip visual treatment (weight encodes trust).

    Returns a dict with: key (canonical id — official|wire|aggregator|unknown),
    label (badge word), fill, ink, stroke, and fill_opacity. Unknown tiers route
    to the most cautious (aggregator-grade) treatment — never launder up.
    """
    t = str(tier or "").strip().lower()
    if t == "official":
        # Strongest: filled amber, dark ink — the verified-primary look.
        return {
            "key": "official", "label": "OFFICIAL SOURCE",
            "fill": _BREAK_AMBER, "fill_opacity": "1", "ink": "#1A1200",
            "stroke": _BREAK_AMBER,
        }
    if t == "wire":
        # Medium: amber outline, hollow — a credible wire, not a primary print.
        return {
            "key": "wire", "label": "WIRE SERVICE",
            "fill": _BREAK_AMBER, "fill_opacity": "0.14", "ink": _BREAK_AMBER,
            "stroke": _BREAK_AMBER,
        }
    # Aggregator (and any unknown tier): visibly lighter grey outline.
    return {
        "key": "aggregator", "label": "AGGREGATOR",
        "fill": _BREAK_GREY, "fill_opacity": "0.08", "ink": _BREAK_GREY,
        "stroke": _BREAK_GREY,
    }


def _break_fmt_ts(published_at: str) -> str:
    """Format an ISO8601 UTC string as a compact dateline, e.g. '14:32 UTC · Jul 19'.

    Deterministic (no now()): the stamp comes only from *published_at*. On any
    parse failure returns the raw string trimmed — never raises (fail-soft; the
    caller wraps everything, but keep this leaf honest too).
    """
    import datetime as _dt
    raw = str(published_at or "").strip()
    try:
        s = raw.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(_dt.timezone.utc)
        mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][dt.month - 1]
        return f"{dt.hour:02d}:{dt.minute:02d} UTC · {mon} {dt.day}"
    except Exception:  # noqa: BLE001
        # Unparseable stamp: show a trimmed echo rather than a fake time.
        return raw[:24] if raw else "TIME UNKNOWN"


def _break_wrap(text: str, max_chars: int, max_lines: int) -> list[str]:
    """Greedy word-wrap to at most *max_lines* lines of ~*max_chars* each.

    Overflow past the last line is hard-clipped with a trailing ellipsis so a
    runaway headline can never blow the card layout. Deterministic.
    """
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = w if not cur else f"{cur} {w}"
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur:
        lines.append(cur)
    # Hard-clip: if words remain unplaced, ellipsize the final line.
    placed = sum(len(ln.split()) for ln in lines)
    if placed < len(words) and lines:
        last = lines[-1]
        if len(last) > max_chars - 1:
            last = last[: max_chars - 1].rstrip()
        lines[-1] = last + "…"
    return lines[:max_lines]


def _break_fallback_svg(width: int, height: int) -> str:
    """Minimal valid fallback card — used when rendering raises internally."""
    return (
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="{width}" height="{height}" fill="#0E1420"/>'
        f'<text x="{width / 2:.0f}" y="{height / 2:.0f}" fill="#6b7a99" '
        f'font-size="16" text-anchor="middle" font-family="sans-serif">'
        f'MASTERMIND · Breaking</text>'
        f'</svg>'
    )


def render_breaking_card(
    headline: str,
    source_name: str,
    source_tier: str,
    published_at: str,
    *,
    tickers: "list[dict] | None" = None,
    suppress_cta: bool = False,
    summary: "str | None" = None,
    event_class: "str | None" = None,
    logo_root: "Path | str | None" = None,  # noqa: ARG001 — reserved; text cashtags used
    width: int = 1000,
    height: int = 560,
) -> str:
    """Render a branded breaking-news card SVG in the Mastermind card family.

    The card belongs to the render_earnings_card visual family (dark #0E1420
    base, favicon lockup + wordmark, branded footer CTA) but its signature is a
    self-grading SOURCE-TIER chip: the tier actually used is encoded in the
    chip's weight (official = filled amber / wire = amber outline / aggregator =
    muted grey outline), so an aggregator can never be laundered as an official
    print (docket D05 trap — this is law). The model behind this card only
    summarizes-with-citation; the card adds no interpretation.

    Args:
        headline: The breaking headline (hero; auto-wraps + scales + hard-clips).
        source_name: Display name of the source ("Reuters", "Federal Reserve").
        source_tier: "official" | "wire" | "aggregator" (unknown → aggregator).
        published_at: ISO8601 UTC timestamp — the ONLY time input (deterministic).
        tickers: Optional [{"ticker","price","pct"}, ...]; capped at 4, house
            up/down coloring; strip omitted entirely when empty/None.
        suppress_cta: Sentinel tone rule — True on human-tragedy items removes
            the trial CTA line so the footer collapses to just the brand mark.
        summary: Optional ≤2-sentence cited summary; omitted cleanly when None.
        event_class: Optional relevance class ("macro_print"|"policy"|
            "geopolitical"|"company_news") rendered as a quiet plain-word
            kicker beside the BREAKING eyebrow; unknown/none/None → omitted
            (the raw snake_case key is never shown — plain-word law).
        logo_root: Reserved for future logomark use; text cashtags are used now.
        width, height: Card dimensions (family default 1000×560).

    Returns:
        Self-contained SVG string. No <script>. All source/user text _xesc'd.
        Deterministic. On any internal error returns a minimal valid fallback
        SVG (fail-soft, stderr note) — never raises.
    """
    try:
        center_x = width / 2  # noqa: F841 — kept for layout symmetry with siblings
        bc_uid = str(abs(hash((headline or "") + "bc")) % 10_000_000)

        # ── Brand lockup (top-left) — identical family treatment ──────────────
        bc_logo_tile = 30.0
        logo_cx = 14 + bc_logo_tile / 2
        logo_cy = 14 + bc_logo_tile / 2
        bc_logo_defs, bc_logo_group = _favicon_logomark(
            logo_cx, logo_cy, size=bc_logo_tile, uid=bc_uid
        )
        wordmark_x = logo_cx + bc_logo_tile / 2 + 8
        wordmark_y = logo_cy + 7
        wordmark_svg = (
            f'<text x="{wordmark_x:.1f}" y="{wordmark_y:.1f}" '
            f'fill="#ffffff" font-size="17" font-weight="900" '
            f'font-family="sans-serif" letter-spacing="0.07em">MASTERMIND</text>'
        )
        # "RADAR" desk tag, right of the header — signals the intelligence lane.
        desk_svg = (
            f'<text x="{width - 14}" y="{logo_cy + 5:.1f}" fill="{_BREAK_GREY}" '
            f'font-size="11" text-anchor="end" font-family="sans-serif" '
            f'letter-spacing="2">RADAR</text>'
        )
        header_h = 60
        header_bg = (
            f'<rect x="0" y="0" width="{width}" height="{header_h}" '
            f'fill="#0A1020" opacity="0.92"/>'
        )
        # Thin amber urgency rule directly under the header band (the "dateline").
        break_rule = (
            f'<rect x="0" y="{header_h}" width="{width}" height="3" '
            f'fill="{_BREAK_AMBER}"/>'
        )

        pad_l = 46
        content_top = header_h + 40

        # ── BREAKING eyebrow (left) + tier chip + timestamp (dateline row) ────
        eyebrow_y = content_top
        # A small amber square + "BREAKING" — restrained, not a siren.
        eyebrow_svg = (
            f'<rect x="{pad_l}" y="{eyebrow_y - 12:.1f}" width="11" height="11" '
            f'rx="2" fill="{_BREAK_AMBER}"/>'
            f'<text x="{pad_l + 19}" y="{eyebrow_y - 1:.1f}" fill="{_BREAK_AMBER}" '
            f'font-size="15" font-weight="900" font-family="sans-serif" '
            f'letter-spacing="3.5">BREAKING</text>'
        )
        # Plain-word event-class kicker — quiet grey, subordinate to the tier
        # chip (the signature). Unknown/none keys are omitted, never echoed raw.
        _KICKER_WORDS = {
            "macro_print": "MACRO PRINT",
            "policy": "POLICY",
            "geopolitical": "GEOPOLITICAL",
            "company_news": "COMPANY NEWS",
        }
        kicker = _KICKER_WORDS.get(str(event_class or "").strip().lower(), "")
        if kicker:
            eyebrow_svg += (
                f'<circle cx="{pad_l + 152:.0f}" cy="{eyebrow_y - 6:.1f}" r="2" '
                f'fill="{_BREAK_GREY}"/>'
                f'<text x="{pad_l + 164}" y="{eyebrow_y - 1:.1f}" '
                f'fill="{_BREAK_GREY}" font-size="12.5" font-weight="700" '
                f'font-family="sans-serif" letter-spacing="2.5" '
                f'class="bc-kicker">{_xesc(kicker)}</text>'
            )

        # Tier chip — the signature. Weight encodes trust; anti-laundering law.
        ts_str = _break_fmt_ts(published_at)
        tier = _break_tier_style(source_tier)
        chip_label = f"{source_name} · {tier['label']}"
        if len(chip_label) > 48:
            chip_label = chip_label[:47] + "…"
        chip_text = _xesc(chip_label)
        # Caps-aware width estimate (deterministic; no font metrics): bold caps
        # at 12.5px run ~8.6px vs ~6.9px lowercase, plus tracking — a flat
        # per-char guess undersizes ALL-CAPS tier labels and the label touches
        # the pill border. Generous right pad keeps it clear in any renderer.
        chip_tw = sum(8.6 if (c.isupper() or c.isdigit()) else 6.9 for c in chip_label)
        chip_tw += 0.4 * len(chip_label)
        chip_w = 26 + int(chip_tw) + 16
        chip_h = 30
        chip_x = pad_l
        chip_y = eyebrow_y + 14
        # A leading dot in the chip echoes the tier ink — a tiny "seal".
        chip_svg = (
            f'<rect x="{chip_x}" y="{chip_y}" width="{chip_w}" height="{chip_h}" '
            f'rx="6" fill="{tier["fill"]}" fill-opacity="{tier["fill_opacity"]}" '
            f'stroke="{tier["stroke"]}" stroke-width="1.5" '
            f'class="bc-tier bc-tier-{tier["key"]}"/>'
            f'<circle cx="{chip_x + 15:.0f}" cy="{chip_y + chip_h / 2:.0f}" r="4" '
            f'fill="{tier["ink"]}"/>'
            f'<text x="{chip_x + 26:.0f}" y="{chip_y + chip_h / 2 + 4:.0f}" '
            f'fill="{tier["ink"]}" font-size="12.5" font-weight="bold" '
            f'font-family="sans-serif" letter-spacing="0.4">{chip_text}</text>'
        )
        # Timestamp dateline, to the right of the chip.
        ts_svg = (
            f'<text x="{chip_x + chip_w + 14:.0f}" '
            f'y="{chip_y + chip_h / 2 + 4:.0f}" fill="{_BREAK_GREY}" '
            f'font-size="12.5" font-family="sans-serif" letter-spacing="0.5">'
            f'{_xesc(ts_str)}</text>'
        )

        # ── Headline hero — auto-wrap + scale by length + hard-clip ───────────
        hl = str(headline or "").strip()
        n = len(hl)
        # Longer headline → smaller type + more chars/line + up to 3 lines.
        if n <= 42:
            hl_size, hl_max_chars, hl_max_lines = 44, 30, 2
        elif n <= 90:
            hl_size, hl_max_chars, hl_max_lines = 36, 40, 2
        elif n <= 150:
            hl_size, hl_max_chars, hl_max_lines = 30, 48, 3
        else:
            hl_size, hl_max_chars, hl_max_lines = 26, 56, 3
        hl_lines = _break_wrap(hl, hl_max_chars, hl_max_lines)
        hl_lh = hl_size + 8
        sm = (summary or "").strip() if summary is not None else ""
        sm_lines = _break_wrap(sm, 84, 3) if sm else []
        sm_lh = 22
        # Vertical balance: center the hero block (headline + summary) between
        # the dateline row and the bottom zone (ticker strip or footer) instead
        # of top-anchoring — short cards otherwise leave a dead void mid-card.
        # The downshift is capped so the headline stays visually attached to
        # its dateline chip.
        min_top = chip_y + chip_h + 40
        rows_present = bool(tickers if isinstance(tickers, list) else [])
        bottom_limit = (height - 116 - 26) if rows_present else (height - 64)
        block_span = (len(hl_lines) - 1) * hl_lh
        if sm_lines:
            block_span += 34 + (len(sm_lines) - 1) * sm_lh
        v_offset = max(0.0, (bottom_limit - (min_top + block_span)) / 2)
        hl_top = min_top + min(v_offset, 56.0)
        hl_tspans = "".join(
            f'<text x="{pad_l}" y="{hl_top + i * hl_lh:.1f}" fill="#ffffff" '
            f'font-size="{hl_size}" font-weight="800" font-family="sans-serif" '
            f'letter-spacing="-0.01em">{_xesc(ln)}</text>'
            for i, ln in enumerate(hl_lines)
        )
        hl_bottom = hl_top + (len(hl_lines) - 1) * hl_lh

        # ── Summary block (quieter secondary) — omit cleanly when None ────────
        summary_svg = ""
        summary_bottom = hl_bottom
        if sm_lines:
            sm_top = hl_bottom + 34
            summary_svg = "".join(
                f'<text x="{pad_l}" y="{sm_top + i * sm_lh:.1f}" '
                f'fill="#a7b4cc" font-size="15.5" font-family="sans-serif">'
                f'{_xesc(ln)}</text>'
                for i, ln in enumerate(sm_lines)
            )
            summary_bottom = sm_top + (len(sm_lines) - 1) * sm_lh

        # ── Related-ticker mini strip (cap 4) — omit entirely when empty ──────
        strip_svg = ""
        rows = tickers if isinstance(tickers, list) else []
        rows = rows[:4]
        if rows:
            strip_y = height - 96
            # Faint divider above the strip.
            strip_svg += (
                f'<line x1="{pad_l}" y1="{strip_y - 20:.0f}" '
                f'x2="{width - pad_l}" y2="{strip_y - 20:.0f}" '
                f'stroke="#232A3D" stroke-width="1"/>'
            )
            cell_w = (width - pad_l * 2) / len(rows)
            for i, row in enumerate(rows):
                cx0 = pad_l + i * cell_w
                cashtag = ("$" + str(row.get("ticker", "") or "").upper())[:8]
                # Missing numbers render as a clean cashtag-only chip — never
                # placeholder dashes (a "—" row reads as broken, not honest).
                try:
                    price_s = f"${float(row.get('price')):,.2f}"
                except (TypeError, ValueError):
                    price_s = ""
                pct_s = ""
                pcol = _BREAK_GREY
                try:
                    pct = float(row.get("pct"))
                    up = pct >= 0
                    pcol = _BREAK_UP if up else _BREAK_DOWN
                    arrow = "▲" if up else "▼"
                    sign = "+" if up else ""
                    pct_s = f"{arrow} {sign}{pct:.1f}%"
                except (TypeError, ValueError):
                    pass
                # Cashtag (white) and pct (colored) share line 1; the pct x is
                # derived from the cashtag length so it can NEVER reach the card's
                # right edge (fixed far-right offsets overflow on wide cells).
                pct_x = cx0 + 10 + len(cashtag) * 11
                strip_svg += (
                    f'<text x="{cx0:.0f}" y="{strip_y:.0f}" fill="#e2e8f0" '
                    f'font-size="17" font-weight="bold" font-family="sans-serif">'
                    f'{_xesc(cashtag)}</text>'
                )
                if pct_s:
                    strip_svg += (
                        f'<text x="{pct_x:.0f}" y="{strip_y:.0f}" fill="{pcol}" '
                        f'font-size="15" font-weight="bold" font-family="sans-serif">'
                        f'{_xesc(pct_s)}</text>'
                    )
                if price_s:
                    strip_svg += (
                        f'<text x="{cx0:.0f}" y="{strip_y + 22:.0f}" fill="{_BREAK_GREY}" '
                        f'font-size="13" font-family="sans-serif">{_xesc(price_s)}</text>'
                    )

        # ── Footer — CTA collapses to brand mark when suppress_cta (tragedy) ──
        if suppress_cta:
            # Sentinel tone rule: no trial pitch on human-tragedy items. The
            # brand bar keeps only the sober attribution — no URL, no button.
            bc_bar_defs, footer_svg = _brand_bar(
                width, height, bc_uid,
                descriptor="MASTERMIND · Market Intelligence",
                show_url=False, show_button=False,
            )
        else:
            bc_bar_defs, footer_svg = _brand_bar(
                width, height, bc_uid,
                copyright_text="© 2026 Mastermind · cited source above",
            )

        # summary_bottom documents where the summary block ends; the ticker strip
        # is pinned to the card bottom so there is no overlap by construction.
        _ = summary_bottom

        svg = (
            f'<svg viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}">\n'
            f'  <defs>{bc_logo_defs}{bc_bar_defs}</defs>\n'
            f'  <!-- background -->\n'
            f'  <rect width="{width}" height="{height}" fill="#0E1420"/>\n'
            f'  <!-- breaking eyebrow + tier chip + timestamp -->\n'
            f'  {eyebrow_svg}\n'
            f'  {chip_svg}\n'
            f'  {ts_svg}\n'
            f'  <!-- headline hero -->\n'
            f'  {hl_tspans}\n'
            f'  <!-- summary -->\n'
            f'  {summary_svg}\n'
            f'  <!-- related-ticker strip -->\n'
            f'  {strip_svg}\n'
            f'  <!-- header band (on top) -->\n'
            f'  {header_bg}\n'
            f'  {break_rule}\n'
            f'  {bc_logo_group}\n'
            f'  {wordmark_svg}\n'
            f'  {desk_svg}\n'
            f'  <!-- footer -->\n'
            f'  {footer_svg}\n'
            f'</svg>'
        )
        return svg
    except Exception as exc:  # noqa: BLE001
        import sys
        print(
            f"render_breaking_card: fail-soft fallback ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return _break_fallback_svg(width, height)
