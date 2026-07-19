"""engine.marketing.chart_render — Pure-Python SVG price chart for Content Studio.

Public API (v1 — backward-compat, kept unchanged):
    load_closes(ticker, root, n=90) -> tuple[list[str], list[float]] | None
    macd_cross(closes)             -> dict|None   (internal signal only; never emitted)
    render_signal_chart(...)       -> str          (self-contained SVG, < 9 KB)

Public API (v2 — TrendSpider-grade terminal chart):
    load_ohlcv(ticker, root, n=90) -> tuple[dates, open, high, low, close, volume] | None
    render_chart_v2(...)           -> str          (self-contained SVG, < 40 KB)
    render_earnings_card(...)      -> str          (branded earnings card SVG)

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
  - No <script> tags. All text _xesc'd. < 40 KB. Deterministic.
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


def _node_glyph(cx: float, cy: float, r: float = 9.0) -> str:
    """Draw Mastermind node-glyph: 3 dots connected by lines — the brand lockup."""
    # Three nodes in a triangle arrangement
    n1x, n1y = cx - r, cy + r * 0.5
    n2x, n2y = cx + r, cy + r * 0.5
    n3x, n3y = cx, cy - r * 0.9
    nr = r * 0.28
    lines = (
        f'<line x1="{n1x:.1f}" y1="{n1y:.1f}" x2="{n2x:.1f}" y2="{n2y:.1f}" '
        f'stroke="#38e0d4" stroke-width="1.5" opacity="0.9"/>'
        f'<line x1="{n1x:.1f}" y1="{n1y:.1f}" x2="{n3x:.1f}" y2="{n3y:.1f}" '
        f'stroke="#38e0d4" stroke-width="1.5" opacity="0.9"/>'
        f'<line x1="{n2x:.1f}" y1="{n2y:.1f}" x2="{n3x:.1f}" y2="{n3y:.1f}" '
        f'stroke="#38e0d4" stroke-width="1.5" opacity="0.9"/>'
        f'<circle cx="{n1x:.1f}" cy="{n1y:.1f}" r="{nr:.1f}" fill="#38e0d4"/>'
        f'<circle cx="{n2x:.1f}" cy="{n2y:.1f}" r="{nr:.1f}" fill="#38e0d4"/>'
        f'<circle cx="{n3x:.1f}" cy="{n3y:.1f}" r="{nr:.1f}" fill="#38e0d4"/>'
    )
    return lines


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
    company_name: str | None = None,
    width: int = 1000,
    height: int = 850,
) -> str:
    """Render a TrendSpider-grade candlestick SVG chart.

    Dark-navy (#0E1420) bg, big Mastermind lockup top-left, TICKER+TIMEFRAME
    top-right, candlesticks with wicks, right price-axis only with last-price pill,
    optional SMA50/SMA200 overlays, % change callout box, highlight zone + SETUP pill,
    stacked subpanels (volume / MACD / RSI), ghost watermark, footer.

    Returns self-contained SVG (<40KB). No <script>. All text _xesc'd.
    """
    n = len(c)
    if n < 5:
        return _empty_svg(width, height, ticker)

    # Clamp indices
    eff_highlight = highlight_index if highlight_index is not None else marker_index
    eff_marker = marker_index if marker_index is not None else (n - 1)
    eff_marker = max(0, min(eff_marker, n - 1))
    if eff_highlight is not None:
        eff_highlight = max(0, min(eff_highlight, n - 1))
    eff_pct_from = pct_from_index if pct_from_index is not None else eff_marker
    eff_pct_from = max(0, min(eff_pct_from, n - 1))

    # ── Layout ──────────────────────────────────────────────────────────────
    HEADER_H = 56          # header band height
    FOOTER_H = 24
    PAD_L = 14             # left padding (no left axis)
    PAD_R = 72             # right axis labels
    PAD_TOP = HEADER_H + 8

    # Subpanel heights
    active_panels: list[str] = []
    if show_indicators:
        for ind in indicators:
            if ind in ("volume", "macd", "rsi"):
                active_panels.append(ind)
    SUBPANEL_H = 110 if active_panels else 0
    n_sub = len(active_panels)
    total_sub_h = SUBPANEL_H * n_sub

    PRICE_H = height - PAD_TOP - FOOTER_H - total_sub_h - 8

    chart_w = width - PAD_L - PAD_R

    # Candle slot width
    slot_w = chart_w / n
    body_frac = 0.60        # body width = 60% of slot
    body_w = max(1.5, slot_w * body_frac)

    # Price range (from high/low with margin)
    all_h = [v for v in h if v == v]
    all_l = [v for v in l if v == v]
    price_max_raw = max(all_h) if all_h else max(c)
    price_min_raw = min(all_l) if all_l else min(c)
    price_range = price_max_raw - price_min_raw or 1.0
    margin = price_range * 0.07
    y_min = price_min_raw - margin
    y_max = price_max_raw + margin
    y_range = y_max - y_min

    def cx_bar(i: int) -> float:
        return PAD_L + (i + 0.5) * slot_w

    def py_price(price: float) -> float:
        return PAD_TOP + PRICE_H * (1.0 - (price - y_min) / y_range)

    # ── Candlesticks ────────────────────────────────────────────────────────
    candle_parts: list[str] = []
    for i in range(n):
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

    # ── Right price axis ─────────────────────────────────────────────────────
    axis_x = PAD_L + chart_w + 6
    n_ticks = 6
    axis_parts: list[str] = []
    for ti in range(n_ticks):
        frac = ti / (n_ticks - 1)
        tick_price = y_max - frac * y_range
        ty = PAD_TOP + PRICE_H * frac
        axis_parts.append(
            f'<text x="{axis_x + 2:.1f}" y="{ty + 4:.1f}" '
            f'fill="#6b7a99" font-size="10" font-family="monospace">'
            f'{_fmt_thousands(round(tick_price, 2))}</text>'
        )

    # Last-price pill
    last_close = c[-1]
    prev_close = c[-2] if n >= 2 else last_close
    pill_color = "#4CAF50" if last_close >= prev_close else "#E23B3B"
    pill_y = py_price(last_close)
    pill_label = _fmt_thousands(last_close)
    pill_w = max(58, len(pill_label) * 7 + 12)
    pill_x = PAD_L + chart_w + 4
    axis_parts.append(
        f'<rect x="{pill_x:.1f}" y="{pill_y - 10:.1f}" '
        f'width="{pill_w}" height="18" rx="3" fill="{pill_color}"/>'
        f'<text x="{pill_x + pill_w / 2:.1f}" y="{pill_y + 3:.1f}" '
        f'fill="#ffffff" font-size="10" font-weight="bold" '
        f'font-family="monospace" text-anchor="middle">{_xesc(pill_label)}</text>'
    )
    axis_svg = "\n  ".join(axis_parts)

    # ── SMA overlays ────────────────────────────────────────────────────────
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
                if sv is None:
                    continue
                pts_sma.append(f"{cx_bar(i):.1f},{py_price(sv):.1f}")
            if len(pts_sma) >= 2:
                sma_svg += (
                    f'<polyline points="{" ".join(pts_sma)}" '
                    f'fill="none" stroke="{sma_color}" stroke-width="1.2" '
                    f'opacity="0.8" stroke-dasharray="4,2"/>'
                )
                # Inline label at end
                last_sma = next(sv for sv in reversed(sma_vals) if sv is not None)
                label_x = cx_bar(n - 1) - 2
                label_y = py_price(last_sma) - 4
                sma_svg += (
                    f'<text x="{label_x:.1f}" y="{label_y:.1f}" '
                    f'fill="{sma_color}" font-size="9" text-anchor="end" '
                    f'opacity="0.9">{_xesc(sma_label)}</text>'
                )

    # ── % Change callout box ─────────────────────────────────────────────────
    pct_callout_svg = ""
    anchor_close = c[eff_pct_from]
    if anchor_close and anchor_close != 0:
        pct_chg = (last_close - anchor_close) / anchor_close * 100.0
        abs_chg = last_close - anchor_close
        bars_elapsed = n - 1 - eff_pct_from
        sign = "+" if pct_chg >= 0 else ""
        box_color = "#4CAF50" if pct_chg >= 0 else "#E23B3B"
        line1 = f"{sign}{abs_chg:.2f} ({sign}{pct_chg:.2f}%)"
        line2 = f"{bars_elapsed} bars"
        box_w, box_h = 148, 38
        # Anchor box near top-right of price panel
        box_x = PAD_L + chart_w - box_w - 4
        box_y = PAD_TOP + 10
        pct_callout_svg = (
            f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" '
            f'rx="4" fill="{box_color}" opacity="0.92"/>'
            f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 15:.1f}" '
            f'fill="#ffffff" font-size="12" font-weight="bold" '
            f'text-anchor="middle">{_xesc(line1)}</text>'
            f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 30:.1f}" '
            f'fill="#ffffffcc" font-size="10" text-anchor="middle">'
            f'{_xesc(line2)}</text>'
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

    # ── Ghost watermark (company name / ticker) ──────────────────────────────
    ghost_label = company_name if company_name else ticker
    ghost_font_size = max(48, min(90, chart_w // max(1, len(ghost_label))))
    ghost_x = PAD_L + chart_w / 2
    ghost_y = PAD_TOP + PRICE_H * 0.55
    ghost_svg = (
        f'<text x="{ghost_x:.1f}" y="{ghost_y:.1f}" '
        f'fill="#ffffff" fill-opacity="0.04" '
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
        # Panel label
        subpanel_svg_parts.append(
            f'<text x="{PAD_L + 4}" y="{panel_y + 14}" '
            f'fill="#6b7a99" font-size="10" font-weight="bold">'
            f'{_xesc(panel_name.upper())}</text>'
        )
        inner_y = panel_y + 18
        inner_h = SUBPANEL_H - 22

        if panel_name == "volume":
            vol_max = max((v for v in volume if v > 0), default=1.0)
            for i, vv in enumerate(volume):
                bx = cx_bar(i)
                bar_h = (vv / vol_max) * inner_h if vol_max > 0 else 0
                bar_y = inner_y + inner_h - bar_h
                vcolor = "#4CAF50" if c[i] >= o[i] else "#E23B3B"
                subpanel_svg_parts.append(
                    f'<rect x="{bx - body_w / 2:.1f}" y="{bar_y:.1f}" '
                    f'width="{body_w:.1f}" height="{max(1, bar_h):.1f}" '
                    f'fill="{vcolor}" opacity="0.6" stroke="none"/>'
                )
            # Volume axis (simplified: show max)
            vol_label = f"{vol_max / 1_000_000:.1f}M" if vol_max >= 1_000_000 else f"{vol_max:.0f}"
            subpanel_svg_parts.append(
                f'<text x="{PAD_L + chart_w + 8}" y="{inner_y + 10}" '
                f'fill="#6b7a99" font-size="9">{_xesc(vol_label)}</text>'
            )

        elif panel_name == "macd":
            macd_line, sig_line, hist_vals = _macd_lines(c)
            valid = [(i, m, s, hist_vals[i]) for i, (m, s) in enumerate(zip(macd_line, sig_line))
                     if m is not None and s is not None and hist_vals[i] is not None]
            if valid:
                all_m = [m for _, m, s, _ in valid]
                all_h2 = [abs(hv) for _, _, _, hv in valid]
                m_min = min(all_m + [-v for v in all_m])
                m_max = max(all_m + [v for v in all_m])
                m_range = max(m_max - m_min, 1e-9)

                def macd_y(v: float) -> float:
                    center = inner_y + inner_h / 2
                    return center - (v / m_range) * (inner_h / 2) * 0.9

                # Zero line
                zero_y = macd_y(0.0)
                subpanel_svg_parts.append(
                    f'<line x1="{PAD_L}" y1="{zero_y:.1f}" '
                    f'x2="{PAD_L + chart_w}" y2="{zero_y:.1f}" '
                    f'stroke="#232A3D" stroke-width="1"/>'
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
                # MACD line (blue)
                macd_pts = " ".join(
                    f"{cx_bar(i):.1f},{macd_y(m):.1f}" for i, m, s, _ in valid
                )
                subpanel_svg_parts.append(
                    f'<polyline points="{macd_pts}" fill="none" '
                    f'stroke="#2196F3" stroke-width="1.2"/>'
                )
                # Signal line (orange)
                sig_pts = " ".join(
                    f"{cx_bar(i):.1f},{macd_y(s):.1f}" for i, m, s, _ in valid
                )
                subpanel_svg_parts.append(
                    f'<polyline points="{sig_pts}" fill="none" '
                    f'stroke="#FF9800" stroke-width="1.0"/>'
                )
                # Right-axis: last MACD value
                last_m = valid[-1][1]
                mc = "#4CAF50" if last_m >= 0 else "#E23B3B"
                subpanel_svg_parts.append(
                    f'<text x="{PAD_L + chart_w + 8}" y="{macd_y(last_m) + 4:.1f}" '
                    f'fill="{mc}" font-size="9">{last_m:.3f}</text>'
                )

        elif panel_name == "rsi":
            rsi_vals = _rsi(c, 14)
            valid_rsi = [(i, rv) for i, rv in enumerate(rsi_vals) if rv is not None]

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

    # ── Header: brand lockup + ticker/timeframe ──────────────────────────────
    # Background header bar
    header_bg = (
        f'<rect x="0" y="0" width="{width}" height="{HEADER_H}" '
        f'fill="#0A1020" opacity="0.8"/>'
    )
    # Node glyph + MASTERMIND wordmark (top-left)
    glyph_cx, glyph_cy = 24, HEADER_H / 2 - 1
    glyph_svg = _node_glyph(glyph_cx, glyph_cy, r=10)
    wordmark_x = glyph_cx + 18
    wordmark_y = HEADER_H / 2 + 5
    wordmark_svg = (
        f'<text x="{wordmark_x:.1f}" y="{wordmark_y:.1f}" '
        f'fill="#ffffff" font-size="22" font-weight="bold" '
        f'font-family="sans-serif" letter-spacing="2">'
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

    # ── Footer ───────────────────────────────────────────────────────────────
    footer_y = height - 8
    footer_svg = (
        f'<text x="{PAD_L + 4}" y="{footer_y}" '
        f'fill="#3a4466" font-size="10">© 2026 Mastermind</text>'
    )

    # ── Date labels (bottom of price panel) ─────────────────────────────────
    date_y_pos = PAD_TOP + PRICE_H + 6
    date_svg = ""
    if dates:
        date_svg = (
            f'<text x="{PAD_L}" y="{date_y_pos}" '
            f'fill="#4a556a" font-size="9">{_xesc(dates[0])}</text>'
            f'<text x="{PAD_L + chart_w}" y="{date_y_pos}" '
            f'fill="#4a556a" font-size="9" text-anchor="end">'
            f'{_xesc(dates[-1])}</text>'
        )

    # ── Arrowhead marker def ─────────────────────────────────────────────────
    defs_svg = (
        '<defs>'
        '<marker id="arrowhead" markerWidth="8" markerHeight="6" '
        'refX="4" refY="3" orient="auto">'
        '<polygon points="0 0, 8 3, 0 6" fill="#4CAF50"/>'
        '</marker>'
        '</defs>'
    )

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
        f'  <!-- candlesticks -->\n'
        f'  {candles_svg}\n'
        f'  <!-- SMA overlays -->\n'
        f'  {sma_svg}\n'
        f'  <!-- highlight zone -->\n'
        f'  {highlight_svg}\n'
        f'  <!-- price axis -->\n'
        f'  {axis_svg}\n'
        f'  <!-- % change callout -->\n'
        f'  {pct_callout_svg}\n'
        f'  <!-- date labels -->\n'
        f'  {date_svg}\n'
        f'  <!-- subpanels -->\n'
        f'  {subpanel_svg}\n'
        f'  <!-- header -->\n'
        f'  {header_bg}\n'
        f'  {glyph_svg}\n'
        f'  {wordmark_svg}\n'
        f'  {ticker_svg}\n'
        f'  <!-- footer -->\n'
        f'  {footer_svg}\n'
        f'</svg>'
    )
    return svg


# ─────────────────────────────────────────────────────────────────────────────
# v2: Earnings card renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_earnings_card(
    ticker: str,
    company_name: str,
    eps_actual: float,
    eps_est: float,
    rev_actual: float,
    rev_est: float,
    *,
    width: int = 1000,
    height: int = 560,
) -> str:
    """Render a branded earnings illustration SVG.

    Dark card, big ticker + company name, EPS/Rev actual vs est with beat/miss
    green/red chips, Mastermind lockup, footer.

    Returns self-contained SVG. No <script>. All text _xesc'd.
    """
    eps_beat = eps_actual >= eps_est
    rev_beat = rev_actual >= rev_est

    eps_color = "#4CAF50" if eps_beat else "#E23B3B"
    rev_color = "#4CAF50" if rev_beat else "#E23B3B"
    eps_label = "BEAT" if eps_beat else "MISS"
    rev_label = "BEAT" if rev_beat else "MISS"

    def _chip(label: str, color: str, cx: float, cy: float) -> str:
        cw, ch = 52, 22
        return (
            f'<rect x="{cx - cw / 2:.1f}" y="{cy - ch / 2:.1f}" '
            f'width="{cw}" height="{ch}" rx="4" fill="{color}"/>'
            f'<text x="{cx:.1f}" y="{cy + 5:.1f}" fill="#fff" '
            f'font-size="11" font-weight="bold" text-anchor="middle">'
            f'{_xesc(label)}</text>'
        )

    def _fmt_rev(v: float) -> str:
        if v >= 1e12:
            return f"${v / 1e12:.2f}T"
        if v >= 1e9:
            return f"${v / 1e9:.2f}B"
        if v >= 1e6:
            return f"${v / 1e6:.2f}M"
        return f"${v:,.2f}"

    # Node glyph for brand lockup
    glyph_svg = _node_glyph(24, 28, r=10)
    wordmark_svg = (
        f'<text x="44" y="33" fill="#ffffff" font-size="18" '
        f'font-weight="bold" font-family="sans-serif" letter-spacing="1">'
        f'MASTERMIND</text>'
    )

    # Earnings content block (center of card)
    center_x = width / 2
    # Card columns: EPS left, Rev right
    col_l = width * 0.28
    col_r = width * 0.72

    content = (
        # Header
        f'<text x="{center_x:.1f}" y="90" fill="#8899bb" font-size="15" '
        f'text-anchor="middle" letter-spacing="2">REPORTS EARNINGS</text>'
        f'<text x="{center_x:.1f}" y="145" fill="#ffffff" font-size="52" '
        f'font-weight="bold" text-anchor="middle">{_xesc(ticker.upper())}</text>'
        f'<text x="{center_x:.1f}" y="180" fill="#8899bb" font-size="16" '
        f'text-anchor="middle">{_xesc(company_name)}</text>'
        # Divider
        f'<line x1="{width * 0.15:.1f}" y1="205" x2="{width * 0.85:.1f}" y2="205" '
        f'stroke="#232A3D" stroke-width="1"/>'
        # EPS column header
        f'<text x="{col_l:.1f}" y="240" fill="#6b7a99" font-size="12" '
        f'text-anchor="middle" letter-spacing="1">EPS</text>'
        # EPS actual
        f'<text x="{col_l:.1f}" y="285" fill="#ffffff" font-size="36" '
        f'font-weight="bold" text-anchor="middle">'
        f'{_xesc(f"${eps_actual:.2f}")}</text>'
        # EPS vs est
        f'<text x="{col_l:.1f}" y="310" fill="#6b7a99" font-size="12" '
        f'text-anchor="middle">Est: {_xesc(f"${eps_est:.2f}")}</text>'
        # EPS beat/miss chip
    ) + _chip(eps_label, eps_color, col_l, 340) + (
        # Revenue column header
        f'<text x="{col_r:.1f}" y="240" fill="#6b7a99" font-size="12" '
        f'text-anchor="middle" letter-spacing="1">REVENUE</text>'
        # Rev actual
        f'<text x="{col_r:.1f}" y="285" fill="#ffffff" font-size="36" '
        f'font-weight="bold" text-anchor="middle">'
        f'{_xesc(_fmt_rev(rev_actual))}</text>'
        # Rev vs est
        f'<text x="{col_r:.1f}" y="310" fill="#6b7a99" font-size="12" '
        f'text-anchor="middle">Est: {_xesc(_fmt_rev(rev_est))}</text>'
    ) + _chip(rev_label, rev_color, col_r, 340) + (
        # Vertical divider between columns
        f'<line x1="{center_x:.1f}" y1="220" x2="{center_x:.1f}" y2="360" '
        f'stroke="#232A3D" stroke-width="1"/>'
        # Footer cite slot
        f'<text x="{center_x:.1f}" y="{height - 30}" fill="#3a4466" '
        f'font-size="11" text-anchor="middle">Source: Company IR</text>'
        f'<text x="{width - 12}" y="{height - 12}" fill="#3a4466" '
        f'font-size="10" text-anchor="end">© 2026 Mastermind</text>'
    )

    svg = (
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}">\n'
        f'  <rect width="{width}" height="{height}" fill="#0E1420"/>\n'
        f'  <!-- brand lockup -->\n'
        f'  {glyph_svg}\n'
        f'  {wordmark_svg}\n'
        f'  <!-- earnings content -->\n'
        f'  {content}\n'
        f'</svg>'
    )
    return svg
