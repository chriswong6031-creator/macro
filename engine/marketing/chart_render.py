"""engine.marketing.chart_render — Pure-Python SVG price chart for Content Studio.

Public API:
    load_closes(ticker, root, n=90) -> tuple[list[str], list[float]] | None
    macd_cross(closes)             -> dict|None   (internal signal only; never emitted)
    render_signal_chart(...)       -> str          (self-contained SVG, < 9 KB)

Spec constraints (§2.2):
  - NO matplotlib, NO external deps beyond pandas/pyarrow for parquet reading.
  - macd_cross values are NEVER returned in any artifact or drawn on chart.
  - No "MACD", "RSI", "EMA", "cross" text anywhere in SVG output.
  - BUY marker: upward triangle + label in green #3ddc84.
  - Transparent background (viewBox only, no background rect).
  - < 9 KB per SVG.
  - No <script> tags.
"""
from __future__ import annotations

import math
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
