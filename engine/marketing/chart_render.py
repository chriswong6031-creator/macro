"""engine.marketing.chart_render — Pure-Python SVG price chart for Content Studio.

Public API (v1 — backward-compat, kept unchanged):
    load_closes(ticker, root, n=90) -> tuple[list[str], list[float]] | None
    macd_cross(closes)             -> dict|None   (internal signal only; never emitted)
    render_signal_chart(...)       -> str          (self-contained SVG, < 9 KB)

Public API (v2 — TrendSpider-grade terminal chart):
    load_ohlcv(ticker, root, n=90) -> tuple[dates, open, high, low, close, volume] | None
    load_ohlcv_timeframe(...)      -> ((bars), warmup) | None   (DAILY/WEEKLY/MONTHLY)
    resample_bars(...)             -> bars         (W-FRI / month-end aggregation)
    render_chart_v2(...)           -> str          (self-contained SVG, < 60 KB)
    render_earnings_card(...)      -> str          (branded earnings card SVG)
    resolve_logo(ticker, root)     -> str | None   (whitened data URI, cached)
    rasterize_svg(svg)             -> bytes        (PNG of that exact SVG; X rejects SVG)

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

import logging
import math
import re
import shutil
import subprocess
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SVG → PNG rasterizer (X rejects SVG; the POSTED image must be the SAME artwork
# the Content Studio preview shows)
# ─────────────────────────────────────────────────────────────────────────────
#
# WHY THIS EXISTS (2026-07-26 incident)
# The publish path used to raster a SEPARATE hand-drawn PIL reimplementation of
# the v1 line chart (render_signal_chart_png) while the admin preview and the
# outbox artifact showed the v2 candlestick SVG. The two drifted: v2 grew
# candles, volume/MACD subpanels, the logo overlay and the footer marketing bar
# (mastermind-x.com + "Start free 14-day trial"); the PNG never followed. The
# account therefore posted a plain line chart with no URL and no CTA while the
# mockup promised the full card. Rasterizing the EXACT SVG we already rendered
# removes the second renderer, so preview and post cannot diverge again.
#
# Rasteriser = headless Chrome, matching scripts/make_favicon.py (the house
# choice; cairosvg/rsvg are not installed on the render hosts). It is also the
# right choice on the merits here: the admin preview IS browser-rendered SVG, so
# a Chrome raster is pixel-faithful to the mockup by construction.
#
# FAIL-SOFT: no Chrome (CI, ubuntu publish runner) → returns b"" and the caller
# falls back to the legacy PIL PNG. A missing rasteriser must never break the
# nightly or turn a post text-only.

_CHROME_CANDIDATES: tuple[str, ...] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "chrome",
)

_SVG_DIM_RE = re.compile(r'<svg[^>]*?\bwidth="(\d+(?:\.\d+)?)"[^>]*?\bheight="(\d+(?:\.\d+)?)"')
_SVG_VIEWBOX_RE = re.compile(r'<svg[^>]*?\bviewBox="\s*[\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)')


def find_chrome() -> str | None:
    """First usable Chrome/Chromium binary, or None. Never raises."""
    for cand in _CHROME_CANDIDATES:
        try:
            if "/" in cand:
                if Path(cand).exists():
                    return cand
            else:
                found = shutil.which(cand)
                if found:
                    return found
        except Exception:  # noqa: BLE001 — probing must never raise
            continue
    return None


def svg_dimensions(svg: str) -> tuple[int, int] | None:
    """(width, height) from the <svg> root — explicit attrs first, then viewBox."""
    m = _SVG_DIM_RE.search(svg)
    if not m:
        m = _SVG_VIEWBOX_RE.search(svg)
    if not m:
        return None
    try:
        w, h = int(float(m.group(1))), int(float(m.group(2)))
    except (TypeError, ValueError):
        return None
    return (w, h) if w > 0 and h > 0 else None


# Poll interval while waiting for headless Chrome to finish writing a screenshot.
# 0.25s costs at most a quarter-second of slack per card and keeps the loop idle.
_RASTER_POLL_S = 0.25


def rasterize_svg(
    svg: str,
    *,
    width: int | None = None,
    height: int | None = None,
    scale: int = 2,
    timeout_s: int = 45,
) -> bytes:
    """Rasterize an SVG string to PNG bytes via headless Chrome. Fail-soft.

    width/height default to the SVG root's own dimensions, so the raster is the
    artwork at its designed size. `scale` is the device pixel ratio: 2 gives a
    retina-crisp 2000x1700 PNG from the 1000x850 v2 chart, which is what a phone
    timeline actually needs (X downscales; it never upscales).

    Deterministic for a given (svg, width, height, scale) — no clock, no
    randomness — so a re-run of the nightly rewrites identical bytes.

    Returns b"" on ANY failure (no Chrome, timeout, no output). The caller must
    treat b"" as "no PNG" and fall back; this never raises.
    """
    if not svg or "<svg" not in svg:
        return b""

    dims = svg_dimensions(svg)
    w = int(width or (dims[0] if dims else 1000))
    h = int(height or (dims[1] if dims else 850))
    if w <= 0 or h <= 0:
        return b""

    chrome = find_chrome()
    if not chrome:
        log.warning("rasterize_svg: no Chrome/Chromium binary — falling back to the legacy PNG")
        return b""

    # Strip anything before the root element so the wrapper holds a clean <svg>.
    try:
        svg_markup = svg[svg.index("<svg"):]
    except ValueError:
        return b""

    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            wrapper = tdp / "w.html"
            out = tdp / "out.png"
            # Force the SVG to exactly w×h CSS px: some roots carry only a
            # viewBox, and an unsized inline SVG defaults to 300x150 in Chrome.
            wrapper.write_text(
                "<!doctype html><meta charset=utf-8>"
                "<style>html,body{margin:0;padding:0;background:transparent}"
                f"svg{{display:block;width:{w}px;height:{h}px}}</style>{svg_markup}",
                encoding="utf-8",
            )
            cmd = [
                chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--hide-scrollbars",
                f"--force-device-scale-factor={int(scale)}",
                "--virtual-time-budget=4000",
                "--default-background-color=00000000",
                f"--screenshot={out}",
                f"--window-size={w},{h}",
                f"--user-data-dir={tdp / 'cr'}",
                wrapper.as_uri(),
            ]
            # Chrome writes the screenshot BEFORE it sometimes hangs on exit, so
            # cap the wait and check for the file rather than trust a clean exit
            # (same handling as scripts/make_favicon.py).
            #
            # POLL for the screenshot instead of waiting out `timeout_s`. On this
            # Mac, `--headless=new` writes the complete PNG at ~11s and then never
            # exits, so a plain run(timeout=45) paid the FULL 45s on every single
            # chart — 34s of pure hang per card, ~75% of the cost. That is what
            # made "a chart on every post" look unaffordable (74 D1 posts × 45s =
            # 55 min against a ~67 min render budget). Watching for the file and
            # killing Chrome the moment the PNG stops growing costs ~11.5s.
            #
            # Stability rule: the size must repeat across two consecutive polls
            # before we kill, so we never read a half-flushed PNG. Bytes are
            # unchanged — this only stops waiting on a process with nothing left
            # to say. Same deadline and same pkill fallback as before.
            deadline = time.monotonic() + timeout_s
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                prev_size = -1
                while time.monotonic() < deadline:
                    try:
                        size = out.stat().st_size
                    except OSError:
                        size = 0
                    if size > 0 and size == prev_size:
                        break          # written and stable — Chrome is just hanging
                    prev_size = size
                    if proc.poll() is not None and size > 0:
                        break          # exited cleanly with output
                    time.sleep(_RASTER_POLL_S)
            finally:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
                # Belt-and-braces for a Chrome that forked past its parent.
                subprocess.run(["pkill", "-9", "-f", str(tdp / "cr")],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False)
            if not out.exists():
                log.warning("rasterize_svg: Chrome produced no screenshot (%dx%d)", w, h)
                return b""
            data = out.read_bytes()
            return data if data.startswith(b"\x89PNG") else b""
    except Exception as exc:  # noqa: BLE001 — rasterizing is best-effort
        log.warning("rasterize_svg failed: %s", exc)
        return b""


# ─────────────────────────────────────────────────────────────────────────────
# Closes loader
# ─────────────────────────────────────────────────────────────────────────────

# Daily-bar search order for a US equity. IDENTICAL to the order Prophet itself
# uses (scripts/build_prophet._load_price_history_for_management): baskets first,
# then the large-cap tree.
#
# Marketing used to read data/stocks/ ALONE — 232 large caps — while Prophet
# picks the signals it publishes from data/baskets/ohlcv/, which carries 2,758
# names. So 30 of the 43 tickers in the plan had no bars ANYWHERE marketing could
# see them, and every post on those names was uncharted no matter what the
# content lane did. That is why the operator's $CBOE, $LKFN, $TEL and $CVI posts
# shipped bare on 2026-07-28: all four are baskets-only names. The engine that
# chose the ticker and the lane that draws it must look in the same place.
#
# Bonus: the baskets parquet carries a REAL `open` column, which data/stocks/
# does not — those candles no longer need the prev-close proxy.
_PRICE_SUBDIRS = ("data/baskets/ohlcv", "data/stocks")

# data/massive_stock_day/ is OPT-IN, for the Hot Tape radar ONLY (2026-07-28,
# masterplan §3.5). The intraday radar posts on whatever the tape hands it, so
# ANY liquid name must render the v2 tape card, not just the 2,990 in the two
# curated trees; that store is a nightly-host artifact (gitignored, ~20k
# parquets, never committed) and scripts/hot_tape_radar.py hydrates the ONE file
# it needs from R2 on demand.
#
# It is NOT in the default order, and that is the whole point: the store is
# neither split-adjusted nor kept current (it was 18 sessions stale on
# 2026-07-28), so silently adding it to _PRICE_SUBDIRS changed the bars under
# every existing caller — the nightly cards, the brain chart, the watchlist
# grid — to answer a question only the radar was asking. Callers who want the
# wide tail pass ``subdirs=HOT_TAPE_PRICE_SUBDIRS`` and own that choice.
HOT_TAPE_PRICE_SUBDIRS = (*_PRICE_SUBDIRS, "data/massive_stock_day")


def _price_parquet(
    ticker: str,
    root: Path | str,
    subdirs: "tuple[str, ...] | None" = None,
) -> Path | None:
    """First existing daily-bar parquet for *ticker*, in Prophet's search order."""
    for sub in (subdirs or _PRICE_SUBDIRS):
        p = Path(root) / sub / f"{ticker}.parquet"
        if p.exists():
            return p
    return None


def _parquet_rows_pyarrow(path: Path) -> tuple[list[str], dict[str, list]] | None:
    """(dates, {column: values}) read with pyarrow alone — the no-pandas path.

    The Hot Tape radar runs on a shallow ubuntu checkout with pyyaml+requests+
    pyarrow and NO pandas (its detector path is stdlib+json by design), so the
    two loaders below fall back here rather than losing their card. Every price
    parquet in this repo is pandas-written with its DatetimeIndex stored as a
    column ("Date" in the curated trees, "date" in data/massive_stock_day) and
    named in the schema's pandas metadata, which is what we read to find it.
    Rows come back sorted by date, mirroring the ``df.sort_index()`` both
    loaders do.
    """
    import json  # noqa: PLC0415  (only on the no-pandas path)
    import pyarrow.parquet as pq  # noqa: PLC0415  (only when pandas is absent)

    table = pq.read_table(path)
    names = list(table.column_names)
    index_col: str | None = None
    meta = (table.schema.metadata or {}).get(b"pandas")
    if meta:
        try:
            cols = json.loads(meta.decode("utf-8")).get("index_columns") or []
            index_col = next((c for c in cols if isinstance(c, str) and c in names), None)
        except Exception:  # noqa: BLE001
            index_col = None
    if index_col is None:
        index_col = next((c for c in ("date", "Date", "index", "timestamp") if c in names), None)
    if index_col is None:
        return None
    data = {n: table.column(n).to_pylist() for n in names}
    dates = [str(d)[:10] for d in data.pop(index_col)]
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return [dates[i] for i in order], {k: [v[i] for i in order] for k, v in data.items()}


def _load_closes_pyarrow(path: Path, n: int) -> tuple[list[str], list[float]] | None:
    """``load_closes``' body without pandas — same filters, same order."""
    rows = _parquet_rows_pyarrow(path)
    if rows is None:
        return None
    dates, cols = rows
    if "close" not in cols:
        return None
    kept = [(d, c) for d, c in zip(dates, cols["close"]) if c is not None and c == c]
    if not kept:
        return None
    kept = kept[-n:]
    return [d for d, _ in kept], [float(c) for _, c in kept]


def _load_ohlcv_pyarrow(
    path: Path,
    n: int,
) -> tuple[list[str], list[float], list[float], list[float], list[float], list[float]] | None:
    """``load_ohlcv``' body without pandas — including the prev-close open proxy."""
    rows = _parquet_rows_pyarrow(path)
    if rows is None:
        return None
    dates, cols = rows
    if not {"close", "volume"}.issubset(set(cols)):
        return None
    has_hl = {"high", "low"}.issubset(set(cols))
    keep = [
        i for i in range(len(dates))
        if cols["close"][i] is not None and cols["close"][i] == cols["close"][i]
        and (not has_hl or (cols["high"][i] is not None and cols["high"][i] == cols["high"][i]
                            and cols["low"][i] is not None and cols["low"][i] == cols["low"][i]))
    ]
    if len(keep) < 2:
        return None
    keep = keep[-(n + 1):]
    dates_raw = [dates[i] for i in keep]
    closes_raw = [float(cols["close"][i]) for i in keep]
    vols_raw = [float(cols["volume"][i]) if cols["volume"][i] is not None
                and cols["volume"][i] == cols["volume"][i] else 0.0 for i in keep]
    opens = [cols["open"][i] for i in keep] if "open" in cols else []
    if opens and all(o is not None and o == o for o in opens):
        opens_raw = [float(o) for o in opens]
    else:
        opens_raw = [closes_raw[0]] + closes_raw[:-1]
    if has_hl:
        highs_raw = [float(cols["high"][i]) for i in keep]
        lows_raw = [float(cols["low"][i]) for i in keep]
    else:
        highs_raw = [max(o, c) for o, c in zip(opens_raw, closes_raw)]
        lows_raw = [min(o, c) for o, c in zip(opens_raw, closes_raw)]
    return (dates_raw[-n:], opens_raw[-n:], highs_raw[-n:], lows_raw[-n:],
            closes_raw[-n:], vols_raw[-n:])


def load_closes(
    ticker: str,
    root: Path | str,
    n: int = 90,
    subdirs: "tuple[str, ...] | None" = None,
) -> tuple[list[str], list[float]] | None:
    """Load last *n* closing prices for *ticker* from its daily-bar parquet.

    Source order is _PRICE_SUBDIRS (data/baskets/ohlcv, then data/stocks), or
    *subdirs* when a caller opts into a wider set (see HOT_TAPE_PRICE_SUBDIRS).

    Returns (dates, closes) where dates are ISO strings and closes are floats.
    Returns None on any error (missing file, bad data).
    """
    try:
        path = _price_parquet(ticker, root, subdirs)
        if path is None:
            return None
        try:
            import pandas as pd  # only import when needed
        except ImportError:
            # Hot Tape radar host: pyarrow, no pandas (see _parquet_rows_pyarrow).
            return _load_closes_pyarrow(path, n)
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
    marker_index: int | None,
    width: int = 560,
    height: int = 300,
    subtitle: str | None = None,
) -> str:
    """Render a price chart SVG.

    Returns a self-contained SVG string (< 9 KB target).
    Contains: price polyline, BUY marker at marker_index, gridlines,
    min/max/last labels, date labels, brand mark.

    marker_index=None renders the SAME card with NO BUY guide/triangle/label —
    the tape fallback (Content Studio W1 CI fix, 2026-07-29): when the v2
    OHLCV candlestick cannot load (name outside the parquet tree, or a
    pyarrow-less env), a "watching, not buying yet" post used to lose its
    chart entirely and then defer forever at publish under the
    ticker-post-carries-a-chart law. A markerless line chart is an honest
    chart with no claim attached; a BUY label on that post would be a lie,
    which is why the marked form was never a legal fallback for it.

    No MACD, RSI, EMA, or indicator text anywhere in output.
    No <script> tags. Transparent background.
    """
    n = len(closes)
    if n < 2:
        return _empty_svg(width, height, ticker)

    # Clamp marker_index (None = markerless tape card, no BUY geometry)
    if marker_index is not None:
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

    # BUY marker geometry (empty when markerless)
    buy_svg = ""
    if marker_index is not None:
        bx = px(marker_index)
        by = py(closes[marker_index])
        tri_size = 8
        tri_pts = (
            f"{bx:.1f},{by - tri_size:.1f} "
            f"{bx - tri_size * 0.7:.1f},{by + tri_size * 0.3:.1f} "
            f"{bx + tri_size * 0.7:.1f},{by + tri_size * 0.3:.1f}"
        )
        buy_svg = (
            f'<line x1="{bx:.1f}" y1="{PAD_TOP}" x2="{bx:.1f}" '
            f'y2="{PAD_TOP + chart_h}" stroke="#3ddc84" stroke-width="1" '
            f'stroke-dasharray="3,3" opacity="0.6"/>\n  '
            f'<polygon points="{tri_pts}" fill="#3ddc84" opacity="0.95"/>\n  '
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="3.5" fill="#3ddc84" '
            f'stroke="#0d1117" stroke-width="1"/>\n  '
            f'<text x="{bx:.1f}" y="{by - tri_size - 4:.1f}" fill="#3ddc84" '
            f'font-size="10" font-weight="bold" text-anchor="middle">BUY</text>'
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
  <!-- marker geometry (empty on the markerless tape card) -->
  {buy_svg}
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


def render_signal_chart_png(
    ticker: str,
    dates: list[str],
    closes: list[float],
    *,
    marker_index: int | None,
    width: int = 1200,
    height: int = 675,
    subtitle: str | None = None,
) -> bytes:
    """Render the signal chart as a PNG (X rejects SVG) — deterministic bytes.

    A PIL rasterization of render_signal_chart's dark-theme brand look: price
    line, area fill, gridlines, BUY vertical guide + triangle + label, min/max/
    last price labels, ticker, first/last date, MASTERMIND brand mark. Landscape
    ~1200x675 (16:9) for the X card. NO technical-indicator words anywhere (no
    MACD/RSI/EMA) — neither drawn nor in PNG metadata (bare save, no pnginfo).

    marker_index=None renders the SAME card with NO BUY guide/triangle/dot/label,
    exactly as ``render_signal_chart`` (the SVG) does. THE TWO MUST AGREE. This
    function is ``media_publish.publish_card``'s ``legacy_png`` fallback: whenever
    ``rasterize_svg`` returns b"" (no Chrome on the host, a raster timeout) the
    PNG *this* renderer produces is what gets uploaded and posted. Before the
    markerless branch existed, a filing card or a "watching, not buying yet" tape
    card whose SVG was correctly markerless still went to the timeline as a
    BUY-labelled v1 card the moment Chrome was missing — a fabricated
    recommendation attached to a named politician's trade, which is precisely
    what the filing lane's own docstring forbids. The SVG branch alone could
    never enforce that, because the SVG is not the image X receives.

    Deterministic: pure function of the inputs (no clock, no randomness), so two
    calls with the same args return byte-identical PNGs. PIL fonts resolve via
    share_cards.load_font (host-agnostic, never raises). Returns b"" only if PIL
    is unavailable (it is a vendored dep — this is defensive, never in practice).

    Colors mirror the SVG hex exactly:
      bg #0E1420, price/last #38e0d4, BUY #3ddc84, grid #2a3045,
      muted-label #93a0b4, ticker #e2e8f0.
    """
    try:
        import io  # noqa: PLC0415
        from PIL import Image, ImageDraw  # noqa: PLC0415
        from engine.marketing.share_cards import load_font  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — PIL is vendored; defensive only
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "render_signal_chart_png: PIL/share_cards unavailable (%s) — no PNG", exc)
        return b""

    # Palette (RGB) mirroring the SVG string colors.
    BG = (14, 20, 32)          # #0E1420
    GRID = (42, 48, 69)        # #2a3045
    MUTED = (147, 160, 180)    # #93a0b4
    LINE = (56, 224, 212)      # #38e0d4  price line + last
    BUY = (61, 220, 132)       # #3ddc84  buy marker
    TICK = (226, 232, 240)     # #e2e8f0  ticker label
    AREA = (24, 46, 58)        # flat blend of LINE @ ~6% over BG (opaque fill)

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    n = len(closes)
    if n < 2:
        # Honest empty card: ticker + brand mark, no fabricated line.
        f = load_font(40, bold=True)
        draw.text((60, 48), str(ticker or "").upper()[:12], font=f, fill=TICK)
        _png_brand_mark(img, draw, width, height)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    # Clamp marker_index (None = markerless card, no BUY geometry at all).
    if marker_index is not None:
        marker_index = max(0, min(marker_index, n - 1))

    # Layout — scaled from the SVG pads, roomier for the large canvas.
    PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOT = 96, 44, 96, 96
    chart_w = width - PAD_LEFT - PAD_RIGHT
    chart_h = height - PAD_TOP - PAD_BOT

    price_min = min(closes)
    price_max = max(closes)
    price_range = (price_max - price_min) or 1.0
    margin = price_range * 0.05
    y_min = price_min - margin
    y_max = price_max + margin
    y_range = y_max - y_min

    def px(i: int) -> float:
        return PAD_LEFT + (i / (n - 1)) * chart_w

    def py(price: float) -> float:
        return PAD_TOP + chart_h * (1 - (price - y_min) / y_range)

    pts = [(px(i), py(c)) for i, c in enumerate(closes)]

    # Area fill under the line (opaque flat blend — deterministic, no alpha).
    area_bottom = PAD_TOP + chart_h
    poly = [(PAD_LEFT, area_bottom)] + pts + [(PAD_LEFT + chart_w, area_bottom)]
    draw.polygon(poly, fill=AREA)

    # Gridlines (3 horizontal) + price labels.
    grid_font = load_font(20, bold=False)
    for frac in (0.25, 0.5, 0.75):
        gy = PAD_TOP + chart_h * frac
        grid_price = y_max - frac * y_range
        draw.line([(PAD_LEFT, gy), (PAD_LEFT + chart_w, gy)], fill=GRID, width=1)
        _png_text_anchor(draw, PAD_LEFT - 8, gy, _fmt_price(grid_price),
                         grid_font, MUTED, anchor="rm")

    # Price line.
    draw.line(pts, fill=LINE, width=3, joint="curve")

    # Last-price dot + label (anchored right-bottom, lifted clear of the dot).
    last_x, last_y = px(n - 1), py(closes[-1])
    _png_dot(draw, last_x, last_y, 5, LINE)
    _png_text_anchor(draw, last_x - 10, last_y - 16, _fmt_price(closes[-1]),
                     grid_font, LINE, anchor="rb")

    # BUY vertical guide (dashed) + triangle + dot + label. Skipped entirely on
    # the markerless card — no green pixel, no "BUY" glyph, nothing to read as a
    # call (see the marker_index=None note in the docstring).
    if marker_index is not None:
        bx, by = px(marker_index), py(closes[marker_index])
        _png_dashed_vline(draw, bx, PAD_TOP, PAD_TOP + chart_h, BUY, dash=6, gap=6)
        tri = 16
        draw.polygon(
            [(bx, by - tri), (bx - tri * 0.7, by + tri * 0.3), (bx + tri * 0.7, by + tri * 0.3)],
            fill=BUY)
        _png_dot(draw, bx, by, 6, BUY, outline=BG, outline_w=2)
        buy_font = load_font(24, bold=True)
        _png_text_anchor(draw, bx, by - tri - 20, "BUY", buy_font, BUY, anchor="mm")

    # Min / max labels at their price points.
    min_idx = closes.index(price_min)
    max_idx = closes.index(price_max)
    _png_text_anchor(draw, px(min_idx), py(price_min) + 22, _fmt_price(price_min),
                     grid_font, MUTED, anchor="mm")
    _png_text_anchor(draw, px(max_idx), py(price_max) - 22, _fmt_price(price_max),
                     grid_font, MUTED, anchor="mm")

    # Date labels (first + last).
    date_y = PAD_TOP + chart_h + 30
    if dates:
        draw.text((PAD_LEFT, date_y), str(dates[0]), font=grid_font, fill=MUTED)
        _png_text_anchor(draw, PAD_LEFT + chart_w, date_y + 10, str(dates[-1]),
                         grid_font, MUTED, anchor="rm")

    # Ticker + optional subtitle.
    tick_font = load_font(40, bold=True)
    draw.text((PAD_LEFT, PAD_TOP - 56), str(ticker or "").upper()[:12], font=tick_font, fill=TICK)
    if subtitle:
        sub_font = load_font(22, bold=False)
        draw.text((PAD_LEFT, PAD_TOP - 12), str(subtitle)[:60], font=sub_font, fill=MUTED)

    _png_brand_mark(img, draw, width, height)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _png_text_anchor(draw, x: float, y: float, text: str, font, fill, *, anchor: str) -> None:
    """Draw text with a 2-char anchor (h∈l/m/r, v∈t/m/b), computed from textbbox.

    PIL's own `anchor=` is font-dependent for some bitmap fallbacks; measuring the
    bbox keeps placement deterministic across the host font chain.
    """
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    w, h = r - l, b - t
    h_a, v_a = anchor[0], anchor[1]
    dx = {"l": 0, "m": -w / 2, "r": -w}[h_a]
    dy = {"t": 0, "m": -h / 2, "b": -h}[v_a]
    draw.text((x + dx - l, y + dy - t), text, font=font, fill=fill)


def _png_dot(draw, cx: float, cy: float, r: float, fill, *, outline=None, outline_w: int = 0) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill,
                 outline=outline, width=outline_w)


def _png_dashed_vline(draw, x: float, y0: float, y1: float, fill, *, dash: int, gap: int) -> None:
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dash, y1))], fill=fill, width=1)
        y += dash + gap


def _png_brand_mark(img, draw, width: int, height: int) -> None:
    """Draw the MASTERMIND lockup bottom-right, reusing share_cards helpers."""
    try:
        from engine.marketing.share_cards import _draw_logomark, load_font, _tracked_text  # noqa: PLC0415
        INK = (147, 160, 180)  # muted so the mark never fights the chart
        size = 28.0
        cx, cy = width - 190, height - 40
        _draw_logomark(img, draw, cx, cy, size)
        wf = load_font(22, bold=True)
        _tracked_text(draw, (cx + size * 0.75, cy - 12), "MASTERMIND", wf, INK, tracking=1.6)
    except Exception:  # noqa: BLE001 — brand mark is decorative; never fatal
        try:
            from engine.marketing.share_cards import load_font  # noqa: PLC0415
            draw.text((width - 260, height - 40), "MASTERMIND",
                      font=load_font(20, bold=True), fill=(42, 48, 69))
        except Exception:  # noqa: BLE001
            pass


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
    subdirs: "tuple[str, ...] | None" = None,
) -> tuple[list[str], list[float], list[float], list[float], list[float], list[float]] | None:
    """Load last *n* bars of OHLCV for *ticker*.

    US equities/ETFs come from _PRICE_SUBDIRS — data/baskets/ohlcv/<TICKER>.parquet
    (2,758 names, real OHLCV) then data/stocks/<TICKER>.parquet (232 large caps).
    Crypto (ETH, BTC, SOL, …) appears in neither; its daily bars live in
    data/yahoo/<TICKER>-USD.parquet, which carries close+volume only. For that feed
    high/low are synthesized as a close-to-close body (no wicks) so crypto charts
    render instead of coming back "chart unavailable" — the bug where "analyse ETH"
    reported no daily chart data even though ETH price history exists.

    'open' is used when the source has it (the baskets tree does); otherwise we
    proxy open_t = close_{t-1} (standard prev-close proxy for candlestick
    rendering; the first bar's open = its close).

    *subdirs* overrides the default store order for a caller that opts into a
    wider set (see HOT_TAPE_PRICE_SUBDIRS).

    Returns (dates, opens, highs, lows, closes, volumes) — all lists of length ≤ n.
    Returns None on any error (missing file, bad data, insufficient rows).
    """
    try:
        path = _price_parquet(ticker, root, subdirs)
        if path is None:
            # Crypto convention in data/yahoo/: <SYMBOL>-USD.parquet (BTC-USD, …).
            crypto_path = Path(root) / "data" / "yahoo" / f"{ticker}-USD.parquet"
            if not crypto_path.exists():
                return None
            path = crypto_path
        try:
            import pandas as pd  # only import when needed
        except ImportError:
            # Hot Tape radar host: pyarrow, no pandas (see _parquet_rows_pyarrow).
            return _load_ohlcv_pyarrow(path, n)
        df = pd.read_parquet(path)
        # close + volume are the hard requirement; high/low are optional and
        # synthesized below when the source is a close-only crypto feed.
        if not {"close", "volume"}.issubset(set(df.columns)):
            return None
        has_hl = {"high", "low"}.issubset(set(df.columns))
        df = df.sort_index().dropna(subset=["close", "high", "low"] if has_hl else ["close"])
        if len(df) < 2:
            return None
        # Take last n rows (need n+1 to compute prev-close open for first bar)
        df = df.iloc[-(n + 1):]
        dates = [str(d)[:10] for d in df.index]
        closes_raw = [float(c) for c in df["close"]]
        vols_raw = [float(v) if not (v != v) else 0.0 for v in df["volume"]]
        if "open" in df.columns and not df["open"].isna().any():
            # Real opens (data/baskets/ohlcv) — true candle bodies, gaps included.
            opens_raw = [float(o) for o in df["open"]]
        else:
            # prev-close proxy: open_t = close_{t-1}; first bar open = its close
            opens_raw = [closes_raw[0]] + closes_raw[:-1]
        if has_hl:
            highs_raw = [float(h) for h in df["high"]]
            lows_raw = [float(l) for l in df["low"]]
        else:
            # Close-only feed → each bar is a close-to-close body: high/low are the
            # max/min of (prev close, close). No invented intrabar extremes; up/down
            # days still read correctly.
            highs_raw = [max(o, c) for o, c in zip(opens_raw, closes_raw)]
            lows_raw = [min(o, c) for o, c in zip(opens_raw, closes_raw)]
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


# House-standard visible window + indicator warm-up lead-in for a SHAREABLE card.
# A daily MACD needs ~34 bars (26-EMA slow leg + 9-bar signal) before its line
# exists; SMA50 needs 50. Loading only the visible window (the old publish path
# did: load_ohlcv(n=90), warmup=0) therefore drew MACD/SMA starting ~1/3 across
# the panel — the "cut off" the operator saw (2026-07-26). The fix is to load a
# lead-in the indicators warm up on but that is never drawn.
MKT_VIS, MKT_WARM = 90, 60


def load_ohlcv_windowed(
    ticker: str,
    root: Path | str,
    *,
    vis: int = MKT_VIS,
    warm: int = MKT_WARM,
    subdirs: "tuple[str, ...] | None" = None,
) -> tuple[tuple[list[str], list[float], list[float], list[float], list[float], list[float]], int] | None:
    """``load_ohlcv`` with a warm-up lead-in, for feeding ``render_chart_v2``.

    Returns ``(bars, warmup)`` where *bars* has up to ``vis + warm`` rows and
    *warmup* is how many leading rows to pass as ``render_chart_v2(warmup=…)`` so
    SMA50/MACD are already "warm" at the first DRAWN bar and their lines span the
    whole visible window. Returns ``None`` when no bars are available.

    This is the ONE seam every shareable-card caller should use — the brain chart
    ( ``brain_gateway._chart_for_chat`` ) hand-rolled this VIS/WARM idiom while the
    marketing publish path did not, and the two drifted (marketing shipped the
    squashed-MACD, cut-off card). Routing every caller through here keeps them
    from drifting apart again.
    """
    # subdirs is threaded ONLY when a caller opted in: the default call shape
    # stays exactly load_ohlcv(ticker, root, n=…), which is what every existing
    # monkeypatched stub of this seam is written against.
    bars = (load_ohlcv(ticker, root, n=vis + warm, subdirs=subdirs) if subdirs
            else load_ohlcv(ticker, root, n=vis + warm))
    if not bars or not bars[0]:
        return None
    warmup = max(0, len(bars[0]) - vis)
    return bars, warmup


# A "since setup" return chip is suppressed below this move — a fresh signal has
# barely moved, so a "-0.72 (-0.22%)" chip is noise, not news (operator, 2026-07-26).
_CALLOUT_MIN_PCT = 3.0


# ─────────────────────────────────────────────────────────────────────────────
# Annotation grammar constants (TrendSpider-hardening PR-A, masterplan §1.1)
# ─────────────────────────────────────────────────────────────────────────────
#
# PURE WHITE IS ANNOTATION INK AND NOTHING ELSE. Candles are lime/coral,
# indicators gold/cyan/salmon, volume muted slate — so the only thing on the
# canvas painted #ffffff is the layer a human "drew": trendlines, arcs, the
# measure arrow. That single rule is why these charts still read at 500px in a
# timeline. Never colour a DATA layer white.
_ANNOT_INK = "#ffffff"

# Spotlight discs are colour-coded by TENSE, not by direction: the reader has to
# know instantly whether a circle is history, now, or damage.
_SPOTLIGHT_COLORS: dict[str, str] = {
    "past": "#8FA6C8",    # blue-grey — a historical instance of the same setup
    "now": "#F5B301",     # gold — "YOU ARE HERE", never more than one per chart
    "damage": "#E23B3B",  # red — where it hurt
}
_SPOTLIGHT_DEFAULT_TENSE = "past"

# Zone bands: blue-grey structure, floored at 10px so a zone never degenerates
# into the hairline it exists to replace.
_ZONE_INK = "#8FA6C8"
_ZONE_MIN_PX = 10.0

# Moving-average palette when a caller names its own MAs (legacy 50/200 keep
# their historical amber pair).
_MA_COLORS: tuple[str, ...] = ("#F59E0B", "#FBBF24", "#5b9dff", "#7c5cff")

# Sub-pane vocabulary + the corpus's hard cap of two.
_SUBPANE_KINDS: tuple[str, ...] = ("volume", "macd", "rsi", "streak", "squeeze")
_MAX_SUBPANES = 2


def _clamp_box(
    x: float, y: float, w: float, h: float,
    canvas_w: float, canvas_h: float,
    pane_top: float | None = None, pane_h: float | None = None,
    pad: int = 4,
) -> tuple[float, float]:
    """Nudge a (x, y, w, h) plate until it lies fully inside the canvas.

    Preserves the numeric TYPE of its inputs (int in, int out) so the legacy
    callout's coordinates format byte-identically when no clamping is needed.
    When *pane_top*/*pane_h* are given the box is also kept inside that pane,
    which is what stops a receipt box from floating into the header band.
    """
    lo_x, hi_x = pad, canvas_w - w - pad
    x = max(lo_x, min(hi_x, x)) if hi_x >= lo_x else lo_x
    lo_y = pane_top + 2 if pane_top is not None else pad
    hi_y = canvas_h - h - pad
    if pane_top is not None and pane_h is not None:
        hi_y = min(hi_y, pane_top + pane_h - h - 2)
    y = max(lo_y, min(hi_y, y)) if hi_y >= lo_y else lo_y
    return x, y


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


def _streak_series(o: list[float], c: list[float]) -> list[int]:
    """Signed consecutive same-colour candle count, aligned to input length.

    +3 = the third consecutive up candle; -2 = the second consecutive down
    candle. The y-unit IS the claim's unit: a "four straight red weeks" post
    gets a pane whose bars are literally the number four (masterplan §1.1,
    "the indicator whose y-axis unit IS the claim's unit").
    """
    out: list[int] = []
    run = 0
    prev_up: bool | None = None
    for i in range(len(c)):
        is_up = c[i] >= o[i]
        if prev_up is None or is_up != prev_up:
            run = 1
        else:
            run += 1
        prev_up = is_up
        out.append(run if is_up else -run)
    return out


def _stdev(values: list[float]) -> float:
    """Population standard deviation (the Bollinger convention)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def _linreg_endpoint(values: list[float]) -> float:
    """Value of the least-squares fit at the LAST point of *values*.

    The squeeze-momentum convention: fit y = a + b·x over the window and report
    the fitted value at the newest bar, so the histogram reads as "where the
    trend of the deviation currently sits", not as raw noise.
    """
    n = len(values)
    if n == 0:
        return 0.0
    if n == 1:
        return values[0]
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (values[i] - mean_y) for i in range(n))
    den = sum((i - mean_x) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    return mean_y + slope * ((n - 1) - mean_x)


def _squeeze_series(
    h: list[float],
    l: list[float],
    c: list[float],
    *,
    length: int = 20,
    bb_mult: float = 2.0,
    kc_mult: float = 1.5,
) -> tuple[list[bool | None], list[float | None]]:
    """(squeeze_on, momentum) — BB(20,2) inside Keltner(20,1.5), from OHLCV alone.

    squeeze_on[i] is True when the Bollinger band is fully inside the Keltner
    channel (volatility compression), False when it has expanded back out, and
    None during the warm-up window where neither exists yet.

    Keltner uses SMA(close) ± mult · SMA(true range) — the range-MA form, which
    needs nothing beyond OHLC. Momentum is the linear-regression endpoint of
    close minus the midpoint of (Donchian mid, SMA close) over the same window.
    """
    n = len(c)
    on: list[bool | None] = [None] * n
    mom: list[float | None] = [None] * n
    if n < length + 1:
        return on, mom
    # True range needs a previous close, so bar 0 has none.
    tr: list[float | None] = [None]
    for i in range(1, n):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    for i in range(length, n):
        win_c = c[i - length + 1: i + 1]
        basis = sum(win_c) / length
        dev = _stdev(win_c)
        win_tr = [t for t in tr[i - length + 1: i + 1] if t is not None]
        if len(win_tr) < length:
            continue
        range_ma = sum(win_tr) / length
        bb_up, bb_lo = basis + bb_mult * dev, basis - bb_mult * dev
        kc_up, kc_lo = basis + kc_mult * range_ma, basis - kc_mult * range_ma
        on[i] = bool(bb_up < kc_up and bb_lo > kc_lo)
        hh = max(h[i - length + 1: i + 1])
        ll = min(l[i - length + 1: i + 1])
        mid = ((hh + ll) / 2.0 + basis) / 2.0
        mom[i] = _linreg_endpoint([win_c[k] - mid for k in range(length)])
    return on, mom


# ─────────────────────────────────────────────────────────────────────────────
# v2: timeframe resampling (DAILY source → WEEKLY / MONTHLY bars)
# ─────────────────────────────────────────────────────────────────────────────

# House visible-window defaults per timeframe. 90 daily ≈ a quarter and change;
# 156 weekly = 3 years; 120 monthly = 10 years — the horizons the corpus study
# found the weekly/monthly editorial charts actually use (masterplan §3 PR-A 1).
TIMEFRAME_VIS: dict[str, int] = {"DAILY": MKT_VIS, "WEEKLY": 156, "MONTHLY": 120}
# Warm-up bars (of the RESAMPLED series) so SMA50/MACD are already warm at the
# first drawn bar. MONTHLY is shorter because 120+60 months of daily history
# exceeds what the curated parquet trees hold; the loader degrades gracefully.
TIMEFRAME_WARM: dict[str, int] = {"DAILY": MKT_WARM, "WEEKLY": 60, "MONTHLY": 40}
# Daily bars consumed per resampled bar, used to size the parquet read.
_TIMEFRAME_DAILY_PER_BAR: dict[str, int] = {"DAILY": 1, "WEEKLY": 5, "MONTHLY": 21}


def normalize_timeframe(timeframe: str | None) -> str:
    """'weekly'/'W'/None → a key of TIMEFRAME_VIS. Unknown values stay DAILY."""
    tf = (timeframe or "DAILY").strip().upper()
    if tf in ("W", "1W", "WEEK"):
        tf = "WEEKLY"
    elif tf in ("M", "1M", "MONTH"):
        tf = "MONTHLY"
    return tf if tf in TIMEFRAME_VIS else "DAILY"


def _bucket_label(iso_date: str, timeframe: str) -> str | None:
    """Bucket label for a daily date: the week's FRIDAY, or the month's LAST day.

    Matches the pandas labels the rest of the repo resamples on —
    ``resample("W-FRI")`` (engine/weinstein_stage.py) labels a week by its
    Friday, ``resample("ME")`` labels a month by its last calendar day — so a
    weekly chart bar and a weekly stage read refer to the same bucket.
    """
    from datetime import date as _date, timedelta as _timedelta  # noqa: PLC0415

    try:
        d = _date.fromisoformat(iso_date[:10])
    except (TypeError, ValueError):
        return None
    if timeframe == "WEEKLY":
        return (d + _timedelta(days=(4 - d.weekday()) % 7)).isoformat()
    if timeframe == "MONTHLY":
        nxt = _date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
        return (nxt - _timedelta(days=1)).isoformat()
    return iso_date[:10]


def resample_bars(
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    v: list[float],
    timeframe: str,
) -> tuple[list[str], list[float], list[float], list[float], list[float], list[float]]:
    """Daily OHLCV → WEEKLY (W-FRI) or MONTHLY (month-end) bars. OHLC-correct.

    open = first, high = max, low = min, close = last, volume = sum — the same
    aggregation ``engine/weinstein_stage.py`` and
    ``engine/neuralweb/chart_perception.py`` use, so a resampled chart bar and a
    resampled signal bar are the same object.

    DELIBERATE divergence from weinstein_stage: the FORMING bucket is KEPT. That
    module drops an incomplete W-FRI week because a signal must never be
    computed from a partial bar; a chart that hid the current week would hide
    "you are here", which is the whole point of the annotation grammar. A chart
    shows the live bar; a signal does not consume it.

    Unrecognised timeframes (and DAILY) return the input unchanged.
    """
    tf = normalize_timeframe(timeframe)
    if tf == "DAILY" or not dates:
        return dates, o, h, l, c, v
    out_d: list[str] = []
    out_o: list[float] = []
    out_h: list[float] = []
    out_l: list[float] = []
    out_c: list[float] = []
    out_v: list[float] = []
    cur: str | None = None
    for i in range(len(dates)):
        key = _bucket_label(dates[i], tf)
        if key is None:
            continue
        if key != cur:
            cur = key
            out_d.append(key)
            out_o.append(o[i])
            out_h.append(h[i])
            out_l.append(l[i])
            out_c.append(c[i])
            out_v.append(v[i])
        else:
            out_h[-1] = max(out_h[-1], h[i])
            out_l[-1] = min(out_l[-1], l[i])
            out_c[-1] = c[i]
            out_v[-1] += v[i]
    return out_d, out_o, out_h, out_l, out_c, out_v


def load_ohlcv_timeframe(
    ticker: str,
    root: Path | str,
    *,
    timeframe: str = "DAILY",
    lookback_bars: int | None = None,
    warm: int | None = None,
    subdirs: "tuple[str, ...] | None" = None,
) -> tuple[tuple[list[str], list[float], list[float], list[float], list[float], list[float]], int] | None:
    """``load_ohlcv_windowed`` with a real timeframe. Returns ``(bars, warmup)``.

    Reads the SAME split-adjusted daily parquets (`_PRICE_SUBDIRS`) every other
    caller reads, pulls enough daily depth for the requested window, then
    resamples. *lookback_bars* overrides the per-timeframe visible default
    (DAILY 90 / WEEKLY 156 / MONTHLY 120); *warm* overrides the warm-up lead-in
    that keeps SMA/MACD warm at the first DRAWN bar — the warm-up is honoured
    AFTER the resample, so a weekly MACD is warm in weekly bars, not daily ones.

    Returns None when no bars are available (fail-soft, exactly like its
    daily-only sibling).
    """
    tf = normalize_timeframe(timeframe)
    vis = int(lookback_bars) if lookback_bars else TIMEFRAME_VIS[tf]
    vis = max(5, vis)
    warm_bars = TIMEFRAME_WARM[tf] if warm is None else max(0, int(warm))
    if tf == "DAILY":
        return load_ohlcv_windowed(ticker, root, vis=vis, warm=warm_bars, subdirs=subdirs)
    # +8 daily bars of slack so the oldest resampled bucket is complete rather
    # than a stub built from the two days that happened to survive the slice.
    need_daily = (vis + warm_bars) * _TIMEFRAME_DAILY_PER_BAR[tf] + 8
    bars = (load_ohlcv(ticker, root, n=need_daily, subdirs=subdirs) if subdirs
            else load_ohlcv(ticker, root, n=need_daily))
    if not bars or not bars[0]:
        return None
    res = resample_bars(*bars, tf)
    if not res[0]:
        return None
    keep = vis + warm_bars
    res = tuple(col[-keep:] for col in res)  # type: ignore[assignment]
    warmup = max(0, len(res[0]) - vis)
    return res, warmup  # type: ignore[return-value]


def _fmt_thousands(v: float) -> str:
    """Format a price with commas and 2 decimal places."""
    return f"{v:,.2f}"


def _fmt_signed(v: float) -> str:
    """Signed price delta with commas — the measure box's first number."""
    return f"{v:+,.2f}"


def _elapsed_phrase(d0: str, d1: str) -> str:
    """Plain-word calendar span between two ISO dates ('' when unusable).

    The measure box's second line is an arithmetic RECEIPT, so the elapsed time
    is real calendar time between the two anchored bars — not a bar count
    restated in another unit.
    """
    from datetime import date as _date  # noqa: PLC0415

    try:
        a = _date.fromisoformat(str(d0)[:10])
        b = _date.fromisoformat(str(d1)[:10])
    except (TypeError, ValueError):
        return ""
    days = abs((b - a).days)
    if days <= 0:
        return ""
    if days < 14:
        return f"{days} day" + ("" if days == 1 else "s")
    if days < 70:
        w = round(days / 7)
        return f"{w} week" + ("" if w == 1 else "s")
    if days < 730:
        m = round(days / 30.44)
        return f"{m} month" + ("" if m == 1 else "s")
    y = days / 365.25
    return f"{y:.1f} years"


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


# publish.chart_cta_enabled in-code default. True = the legacy card (trial button
# in the footer) for every caller that does not thread the knob.
_DEFAULT_CHART_CTA_ENABLED = True


def chart_cta_enabled(cfg: "dict | None") -> bool:
    """Resolve ``publish.chart_cta_enabled`` — may the outbound card footer carry
    the trial button?

    False keeps the brand lockup (favicon + URL + tagline) and drops ONLY the
    saturated CTA button: a trial button burned into every image is a
    promotional / content-farm fingerprint (D08 R4), which a cold account with no
    posting history cannot absorb. Parsed strictly — a quoted ``"false"`` must not
    re-enable the pitch. Missing key / unreadable cfg → the in-code default
    (True), so nothing changes for a config that never heard of this knob.

    Pure: takes the already-parsed cfg. chart_render never reads config from disk
    (it runs on hosts that install pandas but not necessarily anything else).
    """
    try:
        v = ((cfg or {}).get("publish") or {}).get(
            "chart_cta_enabled", _DEFAULT_CHART_CTA_ENABLED)
    except Exception:  # noqa: BLE001 — a malformed cfg must never break a render
        return _DEFAULT_CHART_CTA_ENABLED
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


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
    cta: bool = True,
    avwap_overlay: dict | None = None,
    poc_overlay: dict | None = None,
    level_overlay: dict | None = None,
    log_scale: bool = False,
    runway_frac: float | None = None,
    mas: list[dict] | None = None,
    spotlights: list[dict] | None = None,
    zones: list[dict] | None = None,
    trendlines: list[dict] | None = None,
    arcs: list[dict] | None = None,
    measure_box: dict | None = None,
    level_tags: list[dict] | None = None,
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
        level_overlay: {"price": float, "label": str} — ONE labeled dashed
            horizontal line at the price the post copy cites (weekend-levels
            contract: the text may only name a level the chart draws — the
            2026-07-27 $AVGO post cited "the POC at 379.32" over a card that
            drew no such line). Drawn only when the price is inside the
            visible axis range; label chip uses the same reserved-lane system
            as the M2 overlays.
        Both default None; None and omitted are byte-identical to each other.
        NOTE vs pre-M2 output: the SMA layer now paints UNDER the candles (it
        used to paint over them) so the M2 overlays could slot between —
        a deliberate, designer-approved z-order change for ALL charts.

    Annotation grammar (TrendSpider-hardening PR-A; every kwarg below is
    optional and OFF by default — an omitted set renders byte-identical output,
    which tests/test_chart_render_grammar.py pins against a committed golden):

        log_scale: draw the price pane on a log axis and print
            ``TICKER WEEKLY (LOG)`` in the header. Silently ignored when the
            visible low is <= 0. Every annotation primitive maps through the
            same py_price(), so all of them follow the log axis for free.
        runway_frac: fraction of the plot width left EMPTY to the right of the
            last bar (the corpus's "future runway": last bar at 60-85% of
            frame). Clamped to [0, 0.40]. None keeps the current full-width
            behaviour exactly.
        mas: [{"kind": "sma"|"ema", "length": int, "color"?: str}] — arbitrary
            moving averages with an inline same-colour end label ("200 EMA").
            When given it REPLACES the legacy 50/200 SMA pair; when omitted the
            legacy pair is unchanged.
        spotlights: [{"index": int, "price"?: float, "tense": "past"|"now"|
            "damage", "label"?: str}] — translucent circle discs. Blue-grey =
            a historical instance, gold = "you are here", red = damage. The
            optional 2-6 word label prints in the disc's own colour.
        zones: [{"lo": float, "hi": float, "start_index"?: int,
            "end_index"?: int, "label"?: str}] — translucent supply/demand
            BANDS (floored at 10px of visual weight; a S/R zone is never a
            hairline). Painted under the candles as structure, not ink.
        trendlines: [{"from_idx": int, "from_price": float, "to_idx": int,
            "to_price": float, "style"?: "solid"|"dotted", "extend"?: bool}] —
            white annotation ink; solid = structural, dotted = diagnostic.
            extend projects the line to the right edge (through the runway).
        arcs: [{"indices": [int, ...], "side": "under"|"over", "label"?: str}]
            — a smooth curve through the given swing points, so a formation
            reads as interpretation rather than as a polyline of clutter.
        measure_box: {"from_index": int, "to_index": int, "from_price"?: float,
            "to_price"?: float} — anchor-to-anchor arrow plus the arithmetic
            receipt ``-95.09 (-23.32%) / 2 bars (2 weeks)``, coloured by sign
            and clamped fully inside the canvas.
        level_tags: [{"price": float, "color": str, "label"?: str}] —
            additional right-axis tags in an indicator's own colour: the
            in-frame restatement device that lets a screenshot survive
            decontextualisation.

    Sub-panes: ``indicators`` accepts "volume", "macd", "rsi", "streak"
    (signed consecutive same-colour candle count — the y-unit IS a streak
    claim's unit) and "squeeze" (BB(20,2) inside Keltner(20,1.5) state dots +
    momentum histogram). Hard-capped at 2 panes, per the corpus grammar.

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

    # ── Unique id suffix: CRC32 of the ticker — stable across processes, so the
    # nightly rewrites identical bytes. Never use raw hash() here: Python salts
    # hash(str) per process (PYTHONHASHSEED), which re-rolled every gradient and
    # marker id on every run and broke rasterize_svg's byte-identity contract. ──
    uid = str(zlib.crc32(ticker.encode("utf-8")) & 0xFFFFFFFF)

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
            if ind in _SUBPANE_KINDS:
                active_panels.append(ind)
    # Hard cap at 2 sub-panes (masterplan §1.1: "≤2 sub-panes ever"). A third
    # pane squeezes the price pane below the 55% the grammar requires, and the
    # corpus has zero examples of it.
    active_panels = active_panels[:_MAX_SUBPANES]
    SUBPANEL_H = max(60, int(subpanel_h)) if active_panels else 0
    n_sub = len(active_panels)
    total_sub_h = SUBPANEL_H * n_sub

    # Floor the price pane so an adversarial subpanel_h can never invert the
    # layout (negative height flips the y-axis and paints candles into the header).
    PRICE_H = max(80, height - PAD_TOP - FOOTER_H - total_sub_h - 8)

    chart_w = width - PAD_L - PAD_R

    # ── Future runway ────────────────────────────────────────────────────────
    # The corpus grammar puts the last bar at 60-85% of frame width and keeps
    # the dead space to its right for the volume profile, the last-price tag and
    # level tags. runway_frac reserves that space; bar GEOMETRY (candles,
    # volume, MAs, sub-pane bars, date ticks) is confined to plot_w, while
    # full-width horizontal references (POC, level lines, zone bands) still run
    # to the panel edge the way they do in the reference charts.
    # runway_frac=None → runway_px 0.0 → plot_w == chart_w: byte-identical.
    runway_px = 0.0
    if runway_frac is not None:
        runway_px = chart_w * max(0.0, min(0.40, float(runway_frac)))
    plot_w = float(chart_w) if runway_px <= 0 else max(40.0, chart_w - runway_px)

    # Candle slot width — min 2px body, 1px gap between candles. Measured over the
    # VISIBLE bar count so warmup bars never squeeze the drawn candles.
    slot_w = plot_w / n_vis
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

    # Zones widen the axis so a band the caller asked for is never half off-panel
    # (an S/R zone clipped to a hairline at the edge is worse than no zone).
    for _z in (zones or []):
        try:
            _zl, _zh = float(_z["lo"]), float(_z["hi"])
        except (KeyError, TypeError, ValueError):
            continue
        price_max_raw = max(price_max_raw, max(_zl, _zh))
        price_min_raw = min(price_min_raw, min(_zl, _zh))

    price_range = price_max_raw - price_min_raw or 1.0
    margin = price_range * 0.07
    y_min = price_min_raw - margin
    y_max = price_max_raw + margin
    y_range = y_max - y_min

    # ── Log price axis ───────────────────────────────────────────────────────
    # Multi-year editorial charts (the corpus's MONTHLY/WEEKLY class) need a log
    # axis or a 29-year candle field collapses into a hairline at the bottom.
    # The margin is applied in log space so the padding is proportional at both
    # ends. Silently declines on non-positive prices — never raises, never
    # renders an empty pane.
    log_ok = bool(log_scale) and price_min_raw > 0 and price_max_raw > price_min_raw
    if log_ok:
        _lg_lo_raw = math.log10(price_min_raw)
        _lg_hi_raw = math.log10(price_max_raw)
        _lg_margin = (_lg_hi_raw - _lg_lo_raw) * 0.07
        lg_min = _lg_lo_raw - _lg_margin
        lg_max = _lg_hi_raw + _lg_margin
        lg_range = lg_max - lg_min or 1.0
        y_min = 10.0 ** lg_min
        y_max = 10.0 ** lg_max
        y_range = y_max - y_min

    def cx_bar(i: int) -> float:
        # i is an ABSOLUTE index into the full series; the warmup lead-in is
        # subtracted so the first visible bar sits at the left edge.
        return PAD_L + (i - warmup + 0.5) * slot_w

    if log_ok:
        def py_price(price: float) -> float:
            p = price if price > 0 else y_min
            return PAD_TOP + PRICE_H * (1.0 - (math.log10(p) - lg_min) / lg_range)
    else:
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

    def _log_axis_levels(lo: float, hi: float, target: int = 6) -> list[float]:
        """Geometrically spaced ticks for the log axis.

        Round decades would give one or two labels on a 3x range and twenty on a
        1000x one; a constant RATIO gives the same visual spacing at every
        magnitude — which is what a log axis means, and what the reference
        multi-decade charts print (they are not round numbers either).
        """
        if lo <= 0 or hi <= lo:
            return [hi]
        ratio = (hi / lo) ** (1.0 / (target + 1))
        levels: list[float] = []
        v = lo * ratio
        while v < hi and len(levels) < target + 2:
            levels.append(v)
            v *= ratio
        return levels or [hi]

    # Last-price pill geometry is needed BEFORE the tick loop: a round level that
    # falls under the pill must be suppressed, or the two numbers overprint each
    # other (e.g. a 381.70 pill sitting on the 380.00 label). The pill already
    # states the price, so a hidden tick costs the reader nothing.
    last_close = c[-1]
    prev_close = c[-2] if n >= 2 else last_close
    pill_color = "#4CAF50" if last_close >= prev_close else "#E23B3B"
    pill_y = py_price(last_close)
    pill_label = _fmt_thousands(last_close)
    _PILL_HALF_H = 11.0  # pill is 18px tall; +2px so glyphs never kiss

    _tick_levels = (_log_axis_levels(y_min, y_max, target=6) if log_ok
                    else _round_axis_levels(y_min, y_max, target=6))
    for tick_price in _tick_levels:
        ty = py_price(tick_price)
        if abs(ty - pill_y) < _PILL_HALF_H + 4:
            continue
        axis_parts.append(
            f'<text x="{axis_x + 2:.1f}" y="{ty + 4:.1f}" '
            f'fill="#6b7a99" font-size="10" font-family="monospace">'
            f'{_fmt_thousands(round(tick_price, 2))}</text>'
        )

    # Last-price pill — rx=2 (rounded corners), bold
    pill_w = max(58, len(pill_label) * 7 + 12)
    pill_x = PAD_L + chart_w + 4
    axis_parts.append(
        f'<rect x="{pill_x:.1f}" y="{pill_y - 10:.1f}" '
        f'width="{pill_w}" height="18" rx="2" fill="{pill_color}"/>'
        f'<text x="{pill_x + pill_w / 2:.1f}" y="{pill_y + 3:.1f}" '
        f'fill="#ffffff" font-size="10" font-weight="bold" '
        f'font-family="monospace" text-anchor="middle">{_xesc(pill_label)}</text>'
    )

    # ── Extra right-axis level tags (the in-frame restatement device) ────────
    # A number the caption claims must be re-rendered INSIDE the image, in the
    # colour of whatever drew it, so a screenshot survives decontextualisation
    # (masterplan §1.1). Dark ink on the coloured plate keeps these visually
    # subordinate to the white-on-colour LAST PRICE pill: one price is the tape,
    # the others are references.
    _tag_claimed: list[tuple[float, float]] = [(pill_y - 11.0, pill_y + 11.0)]
    for _tag in (level_tags or [])[:4]:
        try:
            _tag_price = float(_tag["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (y_min <= _tag_price <= y_max):
            continue  # off-panel: the tag would point at nothing
        _tag_color = str(_tag.get("color") or "#5b9dff")
        _tag_text = str(_tag.get("label") or _fmt_thousands(round(_tag_price, 2)))
        _tag_y = py_price(_tag_price)
        for _ in range(6):
            _hit = next((sp for sp in _tag_claimed
                         if _tag_y - 9 < sp[1] and sp[0] < _tag_y + 9), None)
            if _hit is None:
                break
            _tag_y = _hit[1] + 9.0 + 2.0
        _tag_y = max(PAD_TOP + 9.0, min(PAD_TOP + PRICE_H - 9.0, _tag_y))
        _tag_claimed.append((_tag_y - 9.0, _tag_y + 9.0))
        _tag_w = max(50, len(_tag_text) * 7 + 12)
        # A worded tag ("range high") is wider than the 72px axis gutter, so it
        # is pulled LEFT until it fits instead of running off the canvas — the
        # same clipping class as the callout box, one plate over.
        _tag_x = min(float(pill_x), width - _tag_w - 2.0)
        axis_parts.append(
            f'<rect x="{_tag_x:.1f}" y="{_tag_y - 8:.1f}" '
            f'width="{_tag_w}" height="16" rx="2" fill="{_tag_color}" '
            f'fill-opacity="0.92"/>'
            f'<text x="{_tag_x + _tag_w / 2:.1f}" y="{_tag_y + 4:.1f}" '
            f'fill="#0E1420" font-size="10" font-weight="bold" '
            f'font-family="monospace" text-anchor="middle">{_xesc(_tag_text)}</text>'
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

    # ── Zone bands (supply / demand / value) ─────────────────────────────────
    # A support level is a BAND, never a 1px hairline: price respected an area,
    # and a hairline over-claims a precision the tape never had. Floored at
    # _ZONE_MIN_PX of visual weight so a tight zone still reads as a zone.
    # Painted with the M2 geometry layer — UNDER the candles — because a zone is
    # background structure, not annotation ink.
    for _z in (zones or [])[:4]:
        try:
            _z_lo, _z_hi = float(_z["lo"]), float(_z["hi"])
        except (KeyError, TypeError, ValueError):
            continue
        if _z_hi < _z_lo:
            _z_lo, _z_hi = _z_hi, _z_lo
        _zy_top = py_price(_z_hi)
        _zy_bot = py_price(_z_lo)
        if _zy_bot - _zy_top < _ZONE_MIN_PX:
            _zc = (_zy_top + _zy_bot) / 2.0
            _zy_top, _zy_bot = _zc - _ZONE_MIN_PX / 2.0, _zc + _ZONE_MIN_PX / 2.0
        _zy_top = max(PAD_TOP, _zy_top)
        _zy_bot = min(PAD_TOP + PRICE_H, _zy_bot)
        if _zy_bot <= _zy_top:
            continue
        _z_si = _z.get("start_index")
        _z_ei = _z.get("end_index")
        _zx0 = (cx_bar(max(warmup, min(int(_z_si), n - 1))) - slot_w / 2.0
                if _z_si is not None else float(PAD_L))
        _zx1 = (cx_bar(max(warmup, min(int(_z_ei), n - 1))) + slot_w / 2.0
                if _z_ei is not None else float(PAD_L + chart_w))
        if _zx1 <= _zx0:
            continue
        m2_overlay_svg += (
            f'<rect x="{_zx0:.1f}" y="{_zy_top:.1f}" '
            f'width="{_zx1 - _zx0:.1f}" height="{_zy_bot - _zy_top:.1f}" '
            f'fill="{_ZONE_INK}" fill-opacity="0.16" stroke="none"/>'
            f'<line x1="{_zx0:.1f}" y1="{_zy_top:.1f}" x2="{_zx1:.1f}" '
            f'y2="{_zy_top:.1f}" stroke="{_ZONE_INK}" stroke-width="1" '
            f'stroke-opacity="0.42"/>'
            f'<line x1="{_zx0:.1f}" y1="{_zy_bot:.1f}" x2="{_zx1:.1f}" '
            f'y2="{_zy_bot:.1f}" stroke="{_ZONE_INK}" stroke-width="1" '
            f'stroke-opacity="0.42"/>'
        )
        _z_label = str(_z.get("label") or "")
        if _z_label:
            m2_label_svg += (
                f'<text x="{_zx0 + 6:.1f}" y="{_zy_top - 5:.1f}" '
                f'fill="{_ZONE_INK}" font-size="11" font-weight="600" '
                f'font-family="sans-serif">{_xesc(_z_label)}</text>'
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

        # ── Volume-by-price histogram, drawn INTO the runway ─────────────────
        # Bars grow LEFTWARD from the right edge and live entirely inside the
        # empty runway, so the profile can never occlude a candle — the corpus
        # rule that lets ~58% of their charts carry a profile without losing the
        # tape. No runway means no profile: without the reserved space the bars
        # would paint straight over the price action, which is the failure this
        # layout law exists to prevent.
        _vbp_edges = poc_overlay.get("bin_edges") or []
        _vbp_vols = poc_overlay.get("bin_volumes") or []
        if runway_px > 6 and len(_vbp_edges) == len(_vbp_vols) + 1 and _vbp_vols:
            _vbp_max = max(_vbp_vols)
            if _vbp_max > 0:
                _vbp_right = float(PAD_L + chart_w)
                _vbp_span = runway_px * 0.92
                for _bi, _bvol in enumerate(_vbp_vols):
                    if _bvol <= 0:
                        continue
                    _b_lo, _b_hi = float(_vbp_edges[_bi]), float(_vbp_edges[_bi + 1])
                    _by_top = max(PAD_TOP, py_price(_b_hi))
                    _by_bot = min(PAD_TOP + PRICE_H, py_price(_b_lo))
                    if _by_bot <= _by_top:
                        continue
                    _bw = (_bvol / _vbp_max) * _vbp_span
                    _b_mid = (_b_lo + _b_hi) / 2.0
                    _in_va = (_va_low is not None and _va_high is not None
                              and _va_low <= _b_mid <= _va_high)
                    _b_fill = "#5b9dff" if _in_va else "#54607d"
                    _b_op = "0.50" if _in_va else "0.34"
                    m2_overlay_svg += (
                        f'<rect x="{_vbp_right - _bw:.1f}" y="{_by_top:.1f}" '
                        f'width="{max(0.8, _bw):.1f}" '
                        f'height="{max(1.0, _by_bot - _by_top - 1.0):.1f}" '
                        f'fill="{_b_fill}" fill-opacity="{_b_op}" stroke="none"/>'
                    )

    # Cited-level overlay ─────────────────────────────────────────────────────
    # One labeled dashed line at the price the post copy names. Skipped
    # silently when out of the visible range (an average of the drawn window
    # is in-range by construction; a far-away 52-week level would squish the
    # candles if we forced the axis to include it).
    if level_overlay is not None:
        _lvl_price = level_overlay.get("price")
        _lvl_label = level_overlay.get("label", "")
        if _lvl_price is not None and y_min <= _lvl_price <= y_max:
            _lvl_y = py_price(_lvl_price)
            m2_overlay_svg += (
                f'<line x1="{PAD_L:.1f}" y1="{_lvl_y:.1f}" '
                f'x2="{PAD_L + chart_w:.1f}" y2="{_lvl_y:.1f}" '
                f'stroke="#5b9dff" stroke-width="1.5" stroke-dasharray="6 4" '
                f'opacity="0.85"/>'
            )
            if _lvl_label:
                m2_label_svg += _overlay_chip(
                    _lvl_label, _lvl_y + 12, "#5b9dff", anchor_up=False
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
    # `mas` REPLACES this pair when given (the grammar allows ONE MA on a
    # posted chart, and the director picks which one); omitting it leaves the
    # legacy 50/200 default path exactly as it was. An explicit `mas` is honored
    # even with show_indicators=False — asking for a specific MA by name is an
    # explicit request, not the generic "decorate this chart" flag.
    sma_svg = ""
    _ma_layers: list[tuple[list[float | None], str, str]] = []
    if mas is not None:
        for _mi, _ma in enumerate(mas[:4]):
            try:
                _ma_len = int(_ma.get("length") or 0)
            except (AttributeError, TypeError, ValueError):
                continue
            if _ma_len < 2 or n < _ma_len:
                continue
            _ma_kind = str(_ma.get("kind") or "sma").strip().lower()
            _ma_kind = "ema" if _ma_kind == "ema" else "sma"
            _ma_vals = _ema(c, _ma_len) if _ma_kind == "ema" else _sma(c, _ma_len)
            _ma_color = str(_ma.get("color") or _MA_COLORS[_mi % len(_MA_COLORS)])
            _ma_layers.append((_ma_vals, _ma_color, f"{_ma_len} {_ma_kind.upper()}"))
    elif show_indicators and n >= 50:
        sma50 = _sma(c, 50)
        sma200 = _sma(c, 200) if n >= 200 else [None] * n
        _ma_layers = [
            (sma50, "#F59E0B", "50 SMA"),
            (sma200, "#FBBF24", "200 SMA"),
        ]
    if _ma_layers:
        for sma_vals, sma_color, sma_label in _ma_layers:
            pts_sma: list[str] = []
            for i, sv in enumerate(sma_vals):
                if sv is None or i < warmup:
                    continue
                pts_sma.append(f"{cx_bar(i):.1f},{py_price(sv):.1f}")
            if len(pts_sma) >= 2:
                # A NAMED single MA is the subject of the chart (the corpus draws
                # exactly one, solid, in its own colour), so it gets a solid
                # slightly heavier stroke. The legacy 50/200 pair keeps its
                # dashed hairline — it is quiet background reference, and its
                # bytes are pinned by the backward-compat golden.
                sma_svg += (
                    f'<polyline points="{" ".join(pts_sma)}" '
                    f'fill="none" stroke="{sma_color}" stroke-width="1.6" '
                    f'opacity="0.92" stroke-linejoin="round"/>'
                    if mas is not None else
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

    # ── "Since setup" return chip ─────────────────────────────────────────────
    # The move from the highlighted setup bar to the last close. Two rules learned
    # from a confusing "-0.72 (-0.22%) / 5 bars" card (operator, 2026-07-26):
    #   1. It must SAY what it measures. A naked signed number floating over the
    #      candles reads as noise — the caption ("since setup") ties it to the SETUP
    #      mark below it, so the reader knows it is return-since-entry, not today's move.
    #   2. A tiny move is noise, not news. A fresh signal has barely travelled, so the
    #      chip stays hidden until the move is material (|Δ| ≥ _CALLOUT_MIN_PCT). A
    #      matured winner ("+14% since setup") still earns its trophy; a just-fired
    #      card stays clean. Suppression is symmetric (gains AND losses), so it hides
    #      noise, never a loss the LIVE gate would otherwise let through.
    pct_callout_svg = ""
    anchor_close = c[eff_pct_from] if eff_pct_from is not None else None
    if anchor_close and anchor_close != 0:
        pct_chg = (last_close - anchor_close) / anchor_close * 100.0
        bars_elapsed = n - 1 - eff_pct_from
        if bars_elapsed >= 5 and abs(pct_chg) >= _CALLOUT_MIN_PCT:
            sign = "+" if pct_chg >= 0 else "-"
            box_color = "#4CAF50" if pct_chg >= 0 else "#E23B3B"
            line1 = f"{sign}{abs(pct_chg):.1f}%"
            # Plain-language duration (doctrine: no "bars" jargon on the glance).
            if bars_elapsed < 21:
                dur_str = f"since setup · ~{max(1, round(bars_elapsed / 5))}w"
            else:
                dur_str = f"since setup · ~{max(1, round(bars_elapsed / 21))}mo"
            box_w, box_h = 132, 40
            # Anchor box near top-right of price panel, then CLAMP it fully
            # inside the canvas. The un-clamped form was one narrow canvas (or
            # one wider box string) away from painting half a receipt off the
            # right/top edge: box_x is derived from chart_w, so a card whose
            # plot area is narrower than the box pushed it past PAD_L, and
            # nothing bounded box_y against the price pane at all. A number that
            # is half off-frame is worse than no number — it reads as a render
            # fault on a shared image.
            box_x, box_y = _clamp_box(
                PAD_L + chart_w - box_w - 4, PAD_TOP + 10, box_w, box_h,
                width, height, PAD_TOP, PRICE_H,
            )
            pct_callout_svg = (
                f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" '
                f'rx="4" fill="{box_color}" opacity="0.92"/>'
                f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 18:.1f}" '
                f'fill="#ffffff" font-size="15" font-weight="bold" '
                f'text-anchor="middle">{_xesc(line1)}</text>'
                f'<text x="{box_x + box_w / 2:.1f}" y="{box_y + 32:.1f}" '
                f'fill="#ffffffcc" font-size="9" text-anchor="middle">'
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

    # ── Annotation grammar: spotlights, trendlines, arcs, measure box ────────
    # One layer, painted OVER the candles because this is the ink a human drew —
    # it must survive a busy tape at thumbnail size. Every primitive is opt-in;
    # with all four kwargs omitted `annot_svg` stays "" and the SVG template
    # below emits no bytes for it at all (the backward-compat contract).
    annot_parts: list[str] = []
    extra_defs = ""

    def _annot_x(i: int) -> float:
        return cx_bar(max(warmup, min(int(i), n - 1)))

    # Spotlights ──────────────────────────────────────────────────────────────
    for _sp in (spotlights or [])[:8]:
        try:
            _sp_i = int(_sp["index"])
        except (KeyError, TypeError, ValueError):
            continue
        _sp_i = max(0, min(_sp_i, n - 1))
        if _sp_i < warmup:
            continue  # a disc in the undrawn lead-in would point off-panel
        _sp_price = _sp.get("price")
        try:
            _sp_price = float(_sp_price) if _sp_price is not None else c[_sp_i]
        except (TypeError, ValueError):
            _sp_price = c[_sp_i]
        _sp_color = _SPOTLIGHT_COLORS.get(
            str(_sp.get("tense") or _SPOTLIGHT_DEFAULT_TENSE).strip().lower(),
            _SPOTLIGHT_COLORS[_SPOTLIGHT_DEFAULT_TENSE],
        )
        _sp_x = cx_bar(_sp_i)
        _sp_y = py_price(_sp_price)
        # Sized to survive the downscale: a disc that reads as a smudge at the
        # ~50% zoom of a timeline has not marked anything.
        _sp_r = max(slot_w * 2.6, 20.0)
        annot_parts.append(
            f'<circle cx="{_sp_x:.1f}" cy="{_sp_y:.1f}" r="{_sp_r:.1f}" '
            f'fill="{_sp_color}" fill-opacity="0.24" stroke="{_sp_color}" '
            f'stroke-width="1.3" stroke-opacity="0.70"/>'
        )
        _sp_label = str(_sp.get("label") or "")
        if _sp_label:
            # Below the disc by default; above it when the disc sits low enough
            # that the caption would fall out of the price pane.
            _below = _sp_y + _sp_r + 14 <= PAD_TOP + PRICE_H - 4
            _sp_ly = _sp_y + _sp_r + 14 if _below else _sp_y - _sp_r - 7
            _sp_lx = min(max(_sp_x, PAD_L + 30), PAD_L + chart_w - 30)
            annot_parts.append(
                f'<text x="{_sp_lx:.1f}" y="{_sp_ly:.1f}" '
                f'fill="{_sp_color}" font-size="12" font-weight="700" '
                f'text-anchor="middle" font-family="sans-serif">'
                f'{_xesc(_sp_label)}</text>'
            )

    # Trendlines ──────────────────────────────────────────────────────────────
    _pane_top, _pane_bot = float(PAD_TOP), float(PAD_TOP + PRICE_H)
    for _tl in (trendlines or [])[:4]:
        try:
            _x1 = _annot_x(_tl["from_idx"] if "from_idx" in _tl else _tl["from"][0])
            _y1 = py_price(float(
                _tl["from_price"] if "from_price" in _tl else _tl["from"][1]))
            _x2 = _annot_x(_tl["to_idx"] if "to_idx" in _tl else _tl["to"][0])
            _y2 = py_price(float(
                _tl["to_price"] if "to_price" in _tl else _tl["to"][1]))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if _x2 == _x1:
            continue
        if _tl.get("extend"):
            # Project to the right panel edge (through the runway, the way the
            # reference triangles do), then stop at the pane boundary rather
            # than letting the line escape into the sub-panes.
            _xe = float(PAD_L + chart_w)
            _slope = (_y2 - _y1) / (_x2 - _x1)
            _ye = _y2 + _slope * (_xe - _x2)
            if _ye < _pane_top or _ye > _pane_bot:
                _bound = _pane_top if _ye < _pane_top else _pane_bot
                if _slope != 0:
                    _xe = _x2 + (_bound - _y2) / _slope
                    _ye = _bound
            if _xe > _x2:
                _x2, _y2 = _xe, _ye
        _dash = (' stroke-dasharray="3 4"'
                 if str(_tl.get("style") or "solid").lower() == "dotted" else "")
        annot_parts.append(
            f'<line x1="{_x1:.1f}" y1="{_y1:.1f}" x2="{_x2:.1f}" y2="{_y2:.1f}" '
            f'stroke="{_ANNOT_INK}" stroke-width="1.4" stroke-opacity="0.88"'
            f'{_dash} stroke-linecap="round"/>'
        )

    # Arcs ────────────────────────────────────────────────────────────────────
    # A formation outline is a CURVE. A polyline through the same swing points
    # reads as clutter; the curve reads as somebody's interpretation, which is
    # what it is.
    for _arc in (arcs or [])[:3]:
        _idxs = [i for i in (_arc.get("indices") or [])
                 if isinstance(i, (int, float)) and warmup <= int(i) <= n - 1]
        if len(_idxs) < 2:
            continue
        _idxs = sorted({int(i) for i in _idxs})
        _over = str(_arc.get("side") or "under").strip().lower() == "over"
        _off = -12.0 if _over else 12.0   # push the curve clear of the wicks
        _pts = [(cx_bar(i), py_price(h[i] if _over else l[i]) + _off) for i in _idxs]
        if len(_pts) == 2:
            # Two anchors: a real arc, bulging away from the price, not a chord.
            (_ax, _ay), (_bx, _by) = _pts
            _cxp = (_ax + _bx) / 2.0
            _cyp = (_ay + _by) / 2.0 + (-26.0 if _over else 26.0)
            _d = f'M {_ax:.1f} {_ay:.1f} Q {_cxp:.1f} {_cyp:.1f} {_bx:.1f} {_by:.1f}'
        else:
            # Catmull-Rom through every anchor, converted to cubic beziers, so
            # the curve actually passes through the swings it claims to outline.
            _d = f'M {_pts[0][0]:.1f} {_pts[0][1]:.1f}'
            for _k in range(len(_pts) - 1):
                _p0 = _pts[_k - 1] if _k > 0 else _pts[0]
                _p1, _p2 = _pts[_k], _pts[_k + 1]
                _p3 = _pts[_k + 2] if _k + 2 < len(_pts) else _p2
                _c1x = _p1[0] + (_p2[0] - _p0[0]) / 6.0
                _c1y = _p1[1] + (_p2[1] - _p0[1]) / 6.0
                _c2x = _p2[0] - (_p3[0] - _p1[0]) / 6.0
                _c2y = _p2[1] - (_p3[1] - _p1[1]) / 6.0
                _d += (f' C {_c1x:.1f} {_c1y:.1f} {_c2x:.1f} {_c2y:.1f} '
                       f'{_p2[0]:.1f} {_p2[1]:.1f}')
        annot_parts.append(
            f'<path d="{_d}" fill="none" stroke="{_ANNOT_INK}" '
            f'stroke-width="1.5" stroke-opacity="0.85" stroke-linecap="round"/>'
        )
        _arc_label = str(_arc.get("label") or "")
        if _arc_label:
            _lx = sum(p[0] for p in _pts) / len(_pts)
            _ly = (min(p[1] for p in _pts) - 8.0 if _over
                   else max(p[1] for p in _pts) + 16.0)
            _ly = max(PAD_TOP + 10.0, min(PAD_TOP + PRICE_H - 4.0, _ly))
            annot_parts.append(
                f'<text x="{_lx:.1f}" y="{_ly:.1f}" fill="{_ANNOT_INK}" '
                f'font-size="12" font-weight="700" text-anchor="middle" '
                f'font-family="sans-serif">{_xesc(_arc_label)}</text>'
            )

    # Measure box ─────────────────────────────────────────────────────────────
    # Anchor-to-anchor arrow plus an arithmetic RECEIPT. The corpus's
    # highest-viewed chart post carries one, and the reason is that it shows its
    # work: the move, the percentage, the bar count AND the calendar time, so
    # nobody has to take the caption's word for the size of the move.
    if measure_box:
        try:
            _mi0 = max(0, min(int(measure_box["from_index"]), n - 1))
            _mi1 = max(0, min(int(measure_box["to_index"]), n - 1))
        except (KeyError, TypeError, ValueError):
            _mi0 = _mi1 = -1
        if _mi0 >= warmup and _mi1 >= warmup and _mi0 != _mi1:
            if _mi1 < _mi0:
                _mi0, _mi1 = _mi1, _mi0
            try:
                _mp0 = float(measure_box.get("from_price") or c[_mi0])
                _mp1 = float(measure_box.get("to_price") or c[_mi1])
            except (TypeError, ValueError):
                _mp0, _mp1 = c[_mi0], c[_mi1]
            _m_delta = _mp1 - _mp0
            _m_pct = (_m_delta / _mp0 * 100.0) if _mp0 else 0.0
            _m_color = "#4CAF50" if _m_delta >= 0 else "#E23B3B"
            _mx0, _my0 = cx_bar(_mi0), py_price(_mp0)
            _mx1, _my1 = cx_bar(_mi1), py_price(_mp1)
            # White head on a white shaft: the ARROW is annotation ink (it is the
            # gesture "from here to here"); only the receipt PLATE carries the
            # sign colour, exactly as the reference measure tool does.
            extra_defs += (
                f'<marker id="measure_{uid}" markerWidth="9" markerHeight="7" '
                f'refX="8" refY="3.5" orient="auto">'
                f'<polygon points="0 0, 9 3.5, 0 7" fill="{_ANNOT_INK}"/></marker>'
            )
            annot_parts.append(
                f'<line x1="{_mx0:.1f}" y1="{_my0:.1f}" '
                f'x2="{_mx1:.1f}" y2="{_my1:.1f}" '
                f'stroke="{_ANNOT_INK}" stroke-width="1.6" '
                f'marker-end="url(#measure_{uid})"/>'
            )
            _m_bars = _mi1 - _mi0
            _m_elapsed = _elapsed_phrase(dates[_mi0], dates[_mi1]) if dates else ""
            _m_l1 = f"{_fmt_signed(_m_delta)} ({_m_pct:+.2f}%)"
            _m_l2 = f"{_m_bars} bars" + (f" ({_m_elapsed})" if _m_elapsed else "")
            _m_bw = max(118, int(max(len(_m_l1), len(_m_l2)) * 7.6) + 18)
            _m_bh = 40
            # The plate sits BESIDE the arrow tip, never under it (both reference
            # measure charts do this): to the left once the anchor is past
            # mid-frame, which also keeps it out of the right-edge label lane
            # where the MA/POC chips live — a receipt half-covered by a "50 SMA"
            # chip is an unreadable receipt.
            _m_pref_x = (_mx1 - _m_bw - 12.0 if _mx1 > PAD_L + plot_w / 2.0
                         else _mx1 + 12.0)
            _m_bx, _m_by = _clamp_box(
                _m_pref_x, _my1 + 14.0, _m_bw, _m_bh,
                width, height, PAD_TOP, PRICE_H,
            )
            annot_parts.append(
                f'<rect x="{_m_bx:.1f}" y="{_m_by:.1f}" width="{_m_bw}" '
                f'height="{_m_bh}" rx="4" fill="{_m_color}" opacity="0.94"/>'
                f'<text x="{_m_bx + _m_bw / 2:.1f}" y="{_m_by + 17:.1f}" '
                f'fill="#ffffff" font-size="14" font-weight="bold" '
                f'text-anchor="middle" font-family="sans-serif">'
                f'{_xesc(_m_l1)}</text>'
                f'<text x="{_m_bx + _m_bw / 2:.1f}" y="{_m_by + 32:.1f}" '
                f'fill="#ffffffdd" font-size="11" text-anchor="middle" '
                f'font-family="sans-serif">{_xesc(_m_l2)}</text>'
            )

    annot_svg = "\n  ".join(annot_parts)

    # ── Company logo overlay (TrendSpider signature: giant white logo) ──────
    logo_svg = ""
    if logo_datauri:
        # Centered in upper third of price panel, ~34% chart width
        logo_w = chart_w * 0.34
        logo_x = PAD_L + (chart_w - logo_w) / 2
        logo_y = PAD_TOP + PRICE_H * 0.08
        logo_h = logo_w * 0.5  # reasonable aspect; SVG preserveAspectRatio handles it
        # WATERMARK, not a sticker. This was 0.88, which is opaque: a logo like
        # MSFT's (four solid squares) painted a white block straight over the
        # candles and buried the price action. It only ever looked acceptable on
        # low-contrast marks. It matters now because this SVG is rasterized and
        # POSTED (2026-07-26) — before, the posted PNG carried no logo at all.
        # 0.10 reads as brand texture behind the chart and never competes with it.
        logo_svg = (
            f'<image href="{logo_datauri}" '
            f'x="{logo_x:.1f}" y="{logo_y:.1f}" '
            f'width="{logo_w:.1f}" height="{logo_h:.1f}" '
            f'opacity="0.10" preserveAspectRatio="xMidYMid meet"/>'
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

        elif panel_name == "streak":
            # The y-unit IS the claim's unit: a "four straight red weeks" post
            # gets a pane whose bars ARE the number four, so the superlative is
            # scannable instead of asserted. Signed so the direction of the run
            # needs no legend.
            _stk = _streak_series(o, c)
            _stk_vis = [(i, _stk[i]) for i in range(warmup, n)]
            _stk_max = max((abs(s) for _, s in _stk_vis), default=1) or 1

            def streak_y(v: float) -> float:
                center = inner_y + inner_h / 2
                return center - (v / _stk_max) * (inner_h / 2) * 0.88

            _stk_zero = streak_y(0.0)
            subpanel_svg_parts.append(
                f'<line x1="{PAD_L}" y1="{_stk_zero:.1f}" '
                f'x2="{PAD_L + chart_w}" y2="{_stk_zero:.1f}" '
                f'stroke="#2f3750" stroke-width="1"/>'
            )
            for _si, _sv in _stk_vis:
                if _sv == 0:
                    continue
                _sy = streak_y(_sv)
                _s_top, _s_bot = min(_sy, _stk_zero), max(_sy, _stk_zero)
                subpanel_svg_parts.append(
                    f'<rect x="{cx_bar(_si) - body_w / 2:.1f}" y="{_s_top:.1f}" '
                    f'width="{body_w:.1f}" height="{max(1.0, _s_bot - _s_top):.1f}" '
                    f'fill="{"#4CAF50" if _sv > 0 else "#E23B3B"}" '
                    f'opacity="0.62" stroke="none"/>'
                )
            if _stk_vis:
                _stk_last = _stk_vis[-1][1]
                subpanel_svg_parts.append(
                    f'<text x="{PAD_L + chart_w + 8}" '
                    f'y="{streak_y(_stk_last) + 4:.1f}" '
                    f'fill="{"#4CAF50" if _stk_last > 0 else "#E23B3B"}" '
                    f'font-size="9" font-family="monospace">{_stk_last:+d}</text>'
                )

        elif panel_name == "squeeze":
            # Compression is a CLAIM about volatility, so the pane states it as
            # a state (dots on the zero line: gold = bands inside the channel,
            # slate = released) plus the momentum that will carry the release.
            # Both are computable from OHLCV alone — no extra data path.
            _sq_on, _sq_mom = _squeeze_series(h, l, c)
            _sq_vis = [(i, _sq_on[i], _sq_mom[i]) for i in range(warmup, n)
                       if _sq_mom[i] is not None]
            _sq_max = max((abs(m) for _, _, m in _sq_vis), default=1.0) or 1.0

            def squeeze_y(v: float) -> float:
                center = inner_y + inner_h / 2
                return center - (v / _sq_max) * (inner_h / 2) * 0.84

            _sq_zero = squeeze_y(0.0)
            subpanel_svg_parts.append(
                f'<line x1="{PAD_L}" y1="{_sq_zero:.1f}" '
                f'x2="{PAD_L + chart_w}" y2="{_sq_zero:.1f}" '
                f'stroke="#2f3750" stroke-width="1"/>'
            )
            for _qi, _qon, _qm in _sq_vis:
                _qy = squeeze_y(_qm)
                _q_top, _q_bot = min(_qy, _sq_zero), max(_qy, _sq_zero)
                subpanel_svg_parts.append(
                    f'<rect x="{cx_bar(_qi) - body_w / 2:.1f}" y="{_q_top:.1f}" '
                    f'width="{body_w:.1f}" height="{max(1.0, _q_bot - _q_top):.1f}" '
                    f'fill="{"#4CAF50" if _qm >= 0 else "#E23B3B"}" '
                    f'opacity="0.5" stroke="none"/>'
                )
                subpanel_svg_parts.append(
                    f'<circle cx="{cx_bar(_qi):.1f}" cy="{_sq_zero:.1f}" '
                    f'r="{max(1.0, min(2.2, body_w / 3.0)):.1f}" '
                    f'fill="{"#F5B301" if _qon else "#54607d"}"/>'
                )
            if _sq_vis:
                _sq_last_on = _sq_vis[-1][1]
                subpanel_svg_parts.append(
                    f'<text x="{PAD_L + chart_w + 8}" y="{_sq_zero + 4:.1f}" '
                    f'fill="{"#F5B301" if _sq_last_on else "#6b7a99"}" '
                    f'font-size="8" letter-spacing="0.08em">'
                    f'{"ON" if _sq_last_on else "OFF"}</text>'
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
        f'{_xesc(timeframe.upper() + (" (LOG)" if log_ok else ""))}</text>'
    )

    # ── Footer: brand bar (band + laser hairline + lockup + CTA button) ─────
    # footer_cta=None → full marketing bar; ""=brand-only (brain/admin);
    # custom text → quiet informational descriptor, no sales button (dossiers).
    # cta=False drops the trial button from the full marketing bar and keeps the
    # URL lockup (publish.chart_cta_enabled — see chart_cta_enabled()); the other
    # two branches never carried a button, so the knob cannot reach them.
    if footer_cta is None:
        bar_defs, footer_svg = _brand_bar(
            width, height, uid, descriptor="Daily stock signals", show_button=cta
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

    # extra_defs is "" unless an annotation primitive needed its own marker, so
    # a legacy render's <defs> is byte-identical to what it always was.
    defs_svg = f'<defs>{arrowhead_def}{logo_defs}{bar_defs}{extra_defs}</defs>'

    # ── Background rect ──────────────────────────────────────────────────────
    bg_rect = f'<rect width="{width}" height="{height}" fill="#0E1420"/>'

    # The annotation layer emits NOTHING — not even its comment — when no
    # annotation kwarg was passed. That is what makes "omitted == byte-identical
    # to the pre-grammar renderer" a testable claim rather than a hope.
    annot_block = (f'  <!-- annotation grammar (over candles) -->\n  {annot_svg}\n'
                   if annot_svg else "")

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
        f'{annot_block}'
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
                # The histogram itself, for the runway-drawn volume profile.
                # Carried unconditionally: render_chart_v2 only draws it when a
                # runway_frac reserved the space for it, so an existing caller
                # that passes this dict through gets the same picture it always
                # got and the director opts in by asking for a runway.
                try:
                    _edges = [float(e) for e in profile["bin_edges"]]
                    _vols = [float(v_) for v_ in profile["bin_volumes"]]
                    if len(_edges) == len(_vols) + 1 and any(v_ > 0 for v_ in _vols):
                        poc_overlay["bin_edges"] = _edges
                        poc_overlay["bin_volumes"] = _vols
                except (KeyError, TypeError, ValueError):
                    pass
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
    height: int = 610,
    cta: bool = True,
) -> str:
    """Render a branded earnings illustration SVG.

    Dark card (#0E1420), real Mastermind favicon lockup top-left + wordmark,
    full-color company logo (centered hero when logo_datauri / logo_root provided),
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
        logo_datauri: Pre-resolved data URI for company logo (color hero icon).
        logo_root: If logo_datauri is None and logo_root is provided, calls
            resolve_color_logo(ticker, logo_root) to auto-fetch + cache the
            full-color brand icon.
        width: Card width in px (default 1000).
        height: Card height in px (default 610).

    Returns:
        Self-contained SVG string. No <script>. All text _xesc'd. < 60 KB with logo.
    """
    # ── Auto-resolve logo ────────────────────────────────────────────────────
    # The hero logo is the PROMINENT brand identifier (front-and-center, high
    # opacity) — its job is instant recognition, so it wants the ORIGINAL
    # full-color icon, not the white silhouette used for chart watermarks.
    # (Silhouette-whitening flattens internal contrast — e.g. TSMC's red
    # wordmark-over-wafer-grid collapses to an unreadable white blob. The color
    # path is the same one the watchlist avatar chips already use.)
    if logo_datauri is None and logo_root is not None:
        logo_datauri = resolve_color_logo(ticker, logo_root)

    # ── Deterministic id suffix (zlib.crc32: PYTHONHASHSEED-stable) ─────────
    ec_uid = str(zlib.crc32((ticker + "ec").encode("utf-8")) & 0xFFFFFFFF)

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

    # ── Helper: one-line verdict chip — "BEAT +8.4%" together. Single line
    # buys the vertical room that lets every stat font run larger, and the
    # explicit sans-serif kills the serif fallback the old chip shipped with.
    def _stat_chip(label: str, color: str, surp: float, cx: float, cy: float) -> str:
        sign = "+" if surp >= 0 else ""
        surp_text = f"{sign}{surp:.1f}%"
        cw = int(len(label) * 10.2 + len(surp_text) * 8.4) + 40
        ch = 34
        label_w = len(label) * 10.2
        left = cx - (label_w + 10 + len(surp_text) * 8.4) / 2.0
        return (
            f'<rect x="{cx - cw / 2:.1f}" y="{cy - ch / 2:.1f}" '
            f'width="{cw}" height="{ch}" rx="8" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="1.4"/>'
            f'<text x="{left:.1f}" y="{cy + 6:.1f}" fill="{color}" '
            f'font-size="17" font-weight="800" font-family="sans-serif" '
            f'letter-spacing="1">{_xesc(label)}</text>'
            f'<text x="{left + label_w + 10:.1f}" y="{cy + 6:.1f}" fill="{color}" '
            f'font-size="15" font-weight="600" font-family="sans-serif" '
            f'opacity="0.88">{_xesc(surp_text)}</text>'
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
            f'<text x="{col_l:.1f}" y="{stat_top + 18:.1f}" fill="#7d8aa5" '
            f'font-size="14" text-anchor="middle" letter-spacing="2.5" '
            f'font-family="sans-serif">EPS</text>'
            f'<text x="{col_l:.1f}" y="{stat_top + 60:.1f}" fill="#ffffff" '
            f'font-size="40" font-weight="bold" text-anchor="middle" '
            f'font-family="sans-serif">{_xesc(f"${eps_actual:.2f}")}</text>'
            f'<text x="{col_l:.1f}" y="{stat_top + 86:.1f}" fill="#8899bb" '
            f'font-size="15" text-anchor="middle" font-family="sans-serif">'
            f'Est: {_xesc(f"${eps_est:.2f}")}</text>'
        ) + _stat_chip(eps_label, eps_color, eps_surp, col_l, stat_top + 114) + (
            # ── Vertical divider ──
            f'<line x1="{center_x:.1f}" y1="{stat_top:.1f}" '
            f'x2="{center_x:.1f}" y2="{stat_top + 134:.1f}" '
            f'stroke="#232A3D" stroke-width="1"/>'
            # ── Revenue column ──
            f'<text x="{col_r:.1f}" y="{stat_top + 18:.1f}" fill="#7d8aa5" '
            f'font-size="14" text-anchor="middle" letter-spacing="2.5" '
            f'font-family="sans-serif">REVENUE</text>'
            f'<text x="{col_r:.1f}" y="{stat_top + 60:.1f}" fill="#ffffff" '
            f'font-size="40" font-weight="bold" text-anchor="middle" '
            f'font-family="sans-serif">{_xesc(_fmt_rev(rev_actual))}</text>'
            f'<text x="{col_r:.1f}" y="{stat_top + 86:.1f}" fill="#8899bb" '
            f'font-size="15" text-anchor="middle" font-family="sans-serif">'
            f'Est: {_xesc(_fmt_rev(rev_est))}</text>'
        ) + _stat_chip(rev_label, rev_color, rev_surp, col_r, stat_top + 114)
    else:
        # EPS-only: centered single column
        stat_svg = (
            f'<text x="{center_x:.1f}" y="{stat_top + 18:.1f}" fill="#7d8aa5" '
            f'font-size="14" text-anchor="middle" letter-spacing="2.5" '
            f'font-family="sans-serif">EARNINGS PER SHARE</text>'
            f'<text x="{center_x:.1f}" y="{stat_top + 66:.1f}" fill="#ffffff" '
            f'font-size="48" font-weight="bold" text-anchor="middle" '
            f'font-family="sans-serif">{_xesc(f"${eps_actual:.2f}")}</text>'
            f'<text x="{center_x:.1f}" y="{stat_top + 92:.1f}" fill="#8899bb" '
            f'font-size="16" text-anchor="middle" font-family="sans-serif">'
            f'vs. Est {_xesc(f"${eps_est:.2f}")}</text>'
        ) + _stat_chip(eps_label, eps_color, eps_surp, center_x, stat_top + 120)

    # ── Footer: brand bar (Source attribution rides the copyright line) ──────
    ec_bar_defs, footer_svg = _brand_bar(
        width, height, ec_uid,
        copyright_text="© 2026 Mastermind · Source: Company IR",
        show_button=cta,
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
    cta: bool = True,
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
        show_button=cta,
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
_BREAK_BODY = "#C8D4EA"        # summary ink — raised from #a7b4cc (see _BREAK_BODY_MIN)

# ── Legibility floor (W4g, operator 2026-08-02: "text too small for both
# mobile and web") ───────────────────────────────────────────────────────────
# The card is authored on a 1000px-wide canvas and rasterized ×2 to a 2000×1120
# PNG.  In an X timeline on a phone the media well is ~340–360 CSS px wide, so
# every design px lands on screen at ~0.34 CSS px.  The old 15.5px summary
# therefore arrived at ~5.3 CSS px — smaller than any readable caption.  This
# floor (26 design px ≈ 8.8 CSS px on a 340px well, ≈ 9.4 on a 360px well) is
# the size below which the body stops being readable at arm's length; it is a
# LEGIBILITY FLOOR, not a style preference, and the fitter may never go under it.
_BREAK_BODY_MIN = 26.0
# Character bounds for what a card can hold at that floor.  Derived from the
# geometry, not taste: 4 lines × ~68 mixed-case chars at 26px across the 890px
# text column.  A headline longer than this is compressed to whole sentences
# UPSTREAM (see derive_card_headline) so the renderer never has to clip.
_BREAK_HEADLINE_MAX_CHARS = 180
_BREAK_SUMMARY_MAX_CHARS = 240      # no ticker strip — 4 body lines available
_BREAK_SUMMARY_MAX_CHARS_STRIP = 170  # ticker strip present — 3 body lines


# ── Glyph metrics ────────────────────────────────────────────────────────────
# Every wrap on this card used to be a raw CHARACTER COUNT, so the char budgets
# and the font sizes drifted apart whenever either moved (the 15.5px summary was
# set to 84 chars — ~651px of an available 908px column, a permanently underset
# line).  These are Helvetica advance widths in 1/1000 em; `sans-serif` resolves
# to Helvetica on the macOS render host and to a metric-compatible Arial clone
# on Linux.  Deterministic, no font library, no I/O.
_ADV_REG: dict[str, int] = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
}
_ADV_BOLD: dict[str, int] = {
    " ": 278, "!": 333, '"': 474, "#": 556, "$": 556, "%": 889, "&": 722,
    "'": 238, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 333, ";": 333, "<": 584, "=": 584, ">": 584,
    "?": 611, "@": 975, "[": 333, "\\": 278, "]": 333, "^": 584, "_": 556,
    "`": 333, "{": 389, "|": 280, "}": 389, "~": 584,
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611,
    "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611,
    "v": 556, "w": 778, "x": 556, "y": 556, "z": 500,
}
for _d in range(10):  # digits are tabular in both weights
    _ADV_REG[str(_d)] = 556
    _ADV_BOLD[str(_d)] = 556
# Punctuation that actually shows up in wire copy. The em dash is the one that
# matters: it is a FULL em in Helvetica, so leaving it on the generic fallback
# under-measures a line by ~0.45 em and lets it run past the column.
for _tbl in (_ADV_REG, _ADV_BOLD):
    _tbl.update({
        "—": 1000,  # — em dash
        "–": 556,   # – en dash
        "‘": 222, "’": 222,   # ‘ ’
        "“": 333, "”": 333,   # “ ”
        "…": 1000,  # …
        "·": 278,   # ·
        "°": 400, "€": 556, "£": 556, "¥": 556,
        "▲": 800, "▼": 800,   # ▲ ▼ (ticker strip arrows)
    })
del _tbl, _d


def _break_text_w(text: str, size: float, *, bold: bool = False,
                  tracking_em: float = 0.0) -> float:
    """Advance width of *text* at *size* px, in px. Deterministic, no I/O.

    Unknown codepoints fall back to the weight's average advance; CJK is charged
    a full em.  A 6% safety factor is applied so a Linux Arial-clone host (very
    slightly wider than Helvetica in places) still fits inside the column.
    """
    table = _ADV_BOLD if bold else _ADV_REG
    default = 611 if bold else 556
    units = 0
    for ch in str(text or ""):
        if ch in table:
            units += table[ch]
        elif "　" <= ch <= "鿿" or "＀" <= ch <= "￯":
            units += 1000
        else:
            units += default
    return (units / 1000.0) * size * 1.06 + tracking_em * size * len(str(text or ""))


def _break_fit(text: str, max_w: float, size: float, max_lines: int, *,
               bold: bool = False, tracking_em: float = 0.0) -> tuple[list[str], bool]:
    """Word-wrap *text* to lines that MEASURE under *max_w*. Deterministic.

    Returns ``(lines, overflow)``.  ``overflow`` is True when the text needs more
    than *max_lines* lines — the caller then steps down its size ladder instead
    of clipping.  Nothing is ellipsized here: the clip decision belongs to the
    caller, and for the headline it is unreachable by construction (the string
    is bounded by derive_card_headline before it ever arrives).

    A single token wider than the column (a URL, a runaway blob) is broken on a
    character boundary rather than being allowed to bleed off the card.
    """
    words = str(text or "").split()
    if not words:
        return [""], False
    lines: list[str] = []
    cur = ""
    i = 0
    while i < len(words):
        w = words[i]
        cand = w if not cur else f"{cur} {w}"
        if _break_text_w(cand, size, bold=bold, tracking_em=tracking_em) <= max_w:
            cur = cand
            i += 1
            continue
        if cur:
            lines.append(cur)
            cur = ""
            if len(lines) >= max_lines:
                return lines[:max_lines], True
            continue
        # Single token wider than the whole column → character-break it.
        cut = len(w)
        while cut > 1 and _break_text_w(w[:cut], size, bold=bold,
                                        tracking_em=tracking_em) > max_w:
            cut -= 1
        lines.append(w[:cut])
        words[i] = w[cut:]
        if len(lines) >= max_lines:
            return lines[:max_lines], True
    if cur:
        lines.append(cur)
    return lines[:max_lines], len(lines) > max_lines


# ── Sentence-bounded compression (the upstream length gate's engine) ─────────
# Abbreviations whose period is NOT a sentence end.  Without this, "The U.S.A.
# is locked and loaded…" splits after "U.S.A." and the card headline becomes
# three words.
_BREAK_ABBREV: frozenset[str] = frozenset({
    "u.s", "u.s.a", "u.k", "e.u", "d.c", "a.m", "p.m", "e.g", "i.e",
    "mr", "mrs", "ms", "dr", "prof", "sen", "rep", "gov", "gen", "lt", "col",
    "jr", "sr", "inc", "corp", "ltd", "co", "st", "no", "vs", "etc", "approx",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "est", "fig", "dept", "univ",
})

_BREAK_CLAUSE_MARKS = ("; ", " — ", " – ", ": ", ", ")


def _break_sentence_ends(text: str) -> list[int]:
    """Indices just past each sentence terminator. Abbreviation-aware."""
    ends: list[int] = []
    for m in re.finditer(r'([.!?])(["”’\')\]]*)(\s+)', text):
        idx = m.start(1)
        j = idx
        while j > 0 and (text[j - 1].isalnum() or text[j - 1] == "."):
            j -= 1
        token = text[j:idx].lower().rstrip(".")
        if token in _BREAK_ABBREV:
            continue
        if len(token) == 1 and token.isalpha():      # a single initial: "J."
            continue
        nxt = text[m.end():m.end() + 1]
        if nxt and not (nxt.isupper() or nxt.isdigit() or nxt in "\"'“‘("):
            continue
        ends.append(m.end(2))
    if text:
        ends.append(len(text))
    return sorted(set(ends))


def _break_compress(text: str, max_chars: int) -> str:
    """Compress *text* to <= max_chars WITHOUT an ellipsis. Deterministic.

    The ladder, in order of how much meaning survives:
      1. whole sentences (the wire-relay form — verbatim source words, just
         fewer of them; no rewriting, no ALL-CAPS synthesis, F6-safe);
      2. a clause boundary (``;`` ``—`` ``:`` ``,``) when the first sentence is
         itself over budget, provided at least half the budget is used;
      3. the last word boundary under budget;
      4. a hard character cut (degenerate input: one token, no punctuation).
    """
    s = " ".join(str(text or "").split())
    if len(s) <= max_chars:
        return s
    best = 0
    for e in _break_sentence_ends(s):
        if e <= max_chars:
            best = e
        else:
            break
    if best >= max(24, max_chars // 4):
        return s[:best].strip()
    head = s[:max_chars + 1]
    cut = max(head.rfind(mark) for mark in _BREAK_CLAUSE_MARKS)
    if cut >= max_chars // 2:
        return s[:cut].strip()
    cut = head.rfind(" ")
    if cut > 0:
        return s[:cut].strip()
    return s[:max_chars].strip()


def derive_card_headline(text: str, max_chars: int = _BREAK_HEADLINE_MAX_CHARS) -> str:
    """The card headline for an arbitrarily long source string.

    The breaking lane's ``headline`` field is whatever the wire carried — for a
    Truth Social relay that is the entire post (the 2026-08-02 Iran item was 814
    characters), and the card used to render ~156 of them before an ellipsis,
    cutting mid-sentence before any actual news arrived.  This derives a real
    headline instead: the leading WHOLE SENTENCES that fit the card's hero, in
    the source's own words.  Relay, never editorialize — nothing is reworded, no
    case is changed, and no ellipsis is appended (an ellipsis is the truncation
    artifact this exists to remove).

    Deterministic and side-effect free; safe on None/empty/degenerate input.
    """
    return _break_compress(text, max_chars)


def _break_tier_style(tier: str) -> dict[str, str]:
    """Map a source_tier to its chip visual treatment (weight encodes trust).

    Returns a dict with: key (canonical id — official|wire|aggregator|unknown),
    label (badge word), fill, ink, stroke, fill_opacity, and the rail pair
    (rail/rail_opacity) used for the summary-block rule. Unknown tiers route to
    the most cautious (aggregator-grade) treatment — never launder up.

    `ink` is the colour of text ON the chip (dark on the filled official pill);
    `rail` is the colour of the tier mark drawn ON THE CARD, so the same trust
    weight reads on the dark ground — solid amber / half amber / faint grey.
    Using `ink` there would paint an official card's rail near-black.
    """
    t = str(tier or "").strip().lower()
    if t == "official":
        # Strongest: filled amber, dark ink — the verified-primary look.
        return {
            "key": "official", "label": "OFFICIAL SOURCE",
            "fill": _BREAK_AMBER, "fill_opacity": "1", "ink": "#1A1200",
            "stroke": _BREAK_AMBER,
            "rail": _BREAK_AMBER, "rail_opacity": "1",
        }
    if t == "wire":
        # Medium: amber outline, hollow — a credible wire, not a primary print.
        return {
            "key": "wire", "label": "WIRE SERVICE",
            "fill": _BREAK_AMBER, "fill_opacity": "0.14", "ink": _BREAK_AMBER,
            "stroke": _BREAK_AMBER,
            "rail": _BREAK_AMBER, "rail_opacity": "0.5",
        }
    # Aggregator (and any unknown tier): visibly lighter grey outline.
    return {
        "key": "aggregator", "label": "AGGREGATOR",
        "fill": _BREAK_GREY, "fill_opacity": "0.08", "ink": _BREAK_GREY,
        "stroke": _BREAK_GREY,
        "rail": _BREAK_GREY, "rail_opacity": "0.55",
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
    eyebrow: str = "BREAKING",
    logo_root: "Path | str | None" = None,  # noqa: ARG001 — reserved; text cashtags used
    width: int = 1000,
    height: int = 560,
    cta: bool = True,
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
        headline: The breaking headline (hero). ANY length is safe: it is first
            compressed to whole sentences by derive_card_headline, then wrapped
            with MEASURED glyph widths against a size ladder — so it is never
            truncated with an ellipsis, at any length (W4g).
        source_name: Display name of the source ("Reuters", "Federal Reserve").
        source_tier: "official" | "wire" | "aggregator" (unknown → aggregator).
        published_at: ISO8601 UTC timestamp — the ONLY time input (deterministic).
        tickers: Optional [{"ticker","price","pct"}, ...]; capped at 4, house
            up/down coloring; strip omitted entirely when empty/None.
        suppress_cta: Sentinel tone rule — True on human-tragedy items removes
            the trial CTA line so the footer collapses to just the brand mark.
            Distinct from `cta`: this one is PER-ITEM tone (and also drops the
            URL); `cta` is the account-wide posture knob.
        cta: False drops the trial button from the ordinary footer while keeping
            the URL lockup (publish.chart_cta_enabled — see chart_cta_enabled()).
            Ignored when suppress_cta is set, which already removes everything.
        summary: Optional ≤2-sentence cited summary; omitted cleanly when None.
        event_class: Optional relevance class ("macro_print"|"policy"|
            "geopolitical"|"company_news") rendered as a quiet plain-word
            kicker beside the BREAKING eyebrow; unknown/none/None → omitted
            (the raw snake_case key is never shown — plain-word law).
        eyebrow: Plain-word desk label. Defaults to ``BREAKING`` for full
            backward compatibility; deterministic derivative lanes may supply
            a truthful sibling label such as ``EARNINGS CALL``.
        logo_root: Reserved for future logomark use; text cashtags are used now.
        width, height: Card dimensions (family default 1000×560).

    Returns:
        Self-contained SVG string. No <script>. All source/user text _xesc'd.
        Deterministic. On any internal error returns a minimal valid fallback
        SVG (fail-soft, stderr note) — never raises.
    """
    try:
        center_x = width / 2  # noqa: F841 — kept for layout symmetry with siblings
        # Deterministic id suffix (zlib.crc32: PYTHONHASHSEED-stable).
        bc_uid = str(zlib.crc32(((headline or "") + "bc").encode("utf-8")) & 0xFFFFFFFF)

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
            f'font-size="12.5" text-anchor="end" font-family="sans-serif" '
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

        # ── Desk eyebrow (left) + tier chip + timestamp (dateline row) ────────
        eyebrow_y = content_top
        # A small amber square + plain-word desk label — restrained, not a siren.
        eyebrow_text = _xesc(str(eyebrow or "BREAKING").strip().upper()[:24])
        eyebrow_size = 16.0
        eyebrow_track = 3.5
        eyebrow_x = pad_l + 20
        eyebrow_svg = (
            f'<rect x="{pad_l}" y="{eyebrow_y - 13:.1f}" width="12" height="12" '
            f'rx="2" fill="{_BREAK_AMBER}"/>'
            f'<text x="{eyebrow_x}" y="{eyebrow_y - 1:.1f}" fill="{_BREAK_AMBER}" '
            f'font-size="{eyebrow_size:g}" font-weight="900" font-family="sans-serif" '
            f'letter-spacing="{eyebrow_track:g}">{eyebrow_text}</text>'
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
            # Measured, not a fixed 152px guess: a longer eyebrow (EARNINGS CALL)
            # used to run straight under the kicker dot.
            eyebrow_w = _break_text_w(
                eyebrow_text, eyebrow_size, bold=True,
            ) + eyebrow_track * len(eyebrow_text)
            dot_cx = eyebrow_x + eyebrow_w + 12
            eyebrow_svg += (
                f'<circle cx="{dot_cx:.0f}" cy="{eyebrow_y - 6:.1f}" r="2" '
                f'fill="{_BREAK_GREY}"/>'
                f'<text x="{dot_cx + 12:.0f}" y="{eyebrow_y - 1:.1f}" '
                f'fill="{_BREAK_GREY}" font-size="13.5" font-weight="700" '
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
        # Measured width (Helvetica advances + tracking) — the old estimate was a
        # per-character caps/lowercase guess that under- or over-shot by up to a
        # dozen px depending on the label.
        chip_fs = 15.0
        chip_tw = _break_text_w(chip_label, chip_fs, bold=True) + 0.4 * len(chip_label)
        chip_w = 30 + int(chip_tw) + 18
        chip_h = 34
        chip_x = pad_l
        chip_y = eyebrow_y + 14
        # A leading dot in the chip echoes the tier ink — a tiny "seal".
        chip_svg = (
            f'<rect x="{chip_x}" y="{chip_y}" width="{chip_w}" height="{chip_h}" '
            f'rx="7" fill="{tier["fill"]}" fill-opacity="{tier["fill_opacity"]}" '
            f'stroke="{tier["stroke"]}" stroke-width="1.5" '
            f'class="bc-tier bc-tier-{tier["key"]}"/>'
            f'<circle cx="{chip_x + 17:.0f}" cy="{chip_y + chip_h / 2:.0f}" r="4.5" '
            f'fill="{tier["ink"]}"/>'
            f'<text x="{chip_x + 30:.0f}" y="{chip_y + chip_h / 2 + 5:.0f}" '
            f'fill="{tier["ink"]}" font-size="{chip_fs:g}" font-weight="bold" '
            f'font-family="sans-serif" letter-spacing="0.4">{chip_text}</text>'
        )
        # Timestamp dateline, to the right of the chip.
        ts_svg = (
            f'<text x="{chip_x + chip_w + 16:.0f}" '
            f'y="{chip_y + chip_h / 2 + 5:.0f}" fill="{_BREAK_GREY}" '
            f'font-size="14" font-family="sans-serif" letter-spacing="0.5">'
            f'{_xesc(ts_str)}</text>'
        )

        # ── Hero typesetting — MEASURED fit, top-anchored, never clipped ──────
        # Two rules replaced the old char-count size table:
        #   1. the headline is bounded to whole sentences BEFORE it is wrapped,
        #      so the wrap never has to ellipsize (belt-and-braces: the same
        #      bound is applied upstream in breaking_summary.build_breaking_payload,
        #      and again here so a direct caller — earnings_call_lane — is safe);
        #   2. sizes come from a ladder searched BODY-FIRST: the largest summary
        #      size that leaves room for a headline wins, because the body is the
        #      type the reader actually has to read on a phone.
        # Top-anchored, not centred: the old `v_offset` centring is what produced
        # the dead field the operator saw.
        rows_present = bool(tickers if isinstance(tickers, list) else [])
        text_w = width - pad_l * 2                      # 908 on the family default
        sm_rail_inset = 20.0
        sm_w = text_w - sm_rail_inset
        box_top = chip_y + chip_h + 30
        # Bottom of the text column: above the ticker divider, else above the
        # brand bar. Both keep a visible breathing gap — tight, not touching.
        box_bottom = (height - 122 - 20) if rows_present else (height - 46 - 16)
        avail = max(80.0, box_bottom - box_top)

        hl = derive_card_headline(headline)
        sm_full = " ".join(str(summary or "").split())

        # (size, max_lines). Headline descends far enough that a 180-char bound
        # always fits horizontally; the summary floor is the legibility floor.
        # The ladders reach UP as well as down: a sparse card (a six-word
        # headline and one sentence) is the other half of the whitespace
        # complaint — the answer there is bigger type, not more air.
        _HL_LADDER = ((68.0, 2), (60.0, 2), (52.0, 2), (46.0, 3),
                      (40.0, 4), (36.0, 4), (32.0, 5), (28.0, 6))
        _SM_LADDER = ((38.0, 2), (34.0, 2), (32.0, 3), (30.0, 3), (28.0, 4),
                      (_BREAK_BODY_MIN, 4), (_BREAK_BODY_MIN, 5))

        def _hl_lh(s: float) -> float:
            return round(s * 1.14, 1)

        def _sm_lh(s: float) -> float:
            return round(s * 1.32, 1)

        def _block_h(hs: float, hn: int, ss: float, sn: int) -> float:
            h = (hn - 1) * _hl_lh(hs) + hs
            if sn:
                h += round(ss * 1.05, 1) + (sn - 1) * _sm_lh(ss) + ss
            return h

        def _search(sm_text: str, min_ratio: float):
            """First (summary-size, headline-size) pair that fits. Body-first.

            *min_ratio* keeps the hero visibly senior to the body; the caller
            relaxes it before it ever compresses the source text, because losing
            a sentence costs more than a muddier size step.
            """
            cands = _SM_LADDER if sm_text else ((_BREAK_BODY_MIN, 0),)
            for ss, s_cap in cands:
                if sm_text:
                    s_lines, s_over = _break_fit(sm_text, sm_w, ss, s_cap)
                    if s_over:
                        continue
                else:
                    s_lines = []
                for hs, h_cap in _HL_LADDER:
                    if s_lines and hs < ss * min_ratio:
                        continue
                    h_lines, h_over = _break_fit(
                        hl, text_w, hs, h_cap, bold=True, tracking_em=-0.01
                    )
                    if h_over:
                        continue
                    if _block_h(hs, len(h_lines), ss, len(s_lines)) <= avail:
                        return hs, h_lines, ss, s_lines
            return None

        # Pass A: full source text, hero visibly senior to the body.
        # Pass B: full source text, hierarchy relaxed — keep every sentence.
        # Pass C: only now is the summary compressed to whole sentences that fit.
        sm_budget = (_BREAK_SUMMARY_MAX_CHARS_STRIP if rows_present
                     else _BREAK_SUMMARY_MAX_CHARS)
        sm = sm_full
        found = _search(sm_full, 1.30) or _search(sm_full, 0.0)
        if found is None:
            sm = _break_compress(sm_full, sm_budget)
            found = _search(sm, 0.0)
        if found is not None:
            hl_size, hl_lines, sm_size, sm_lines = found
        else:
            # Terminal rung (unreachable for bounded input; kept so a hostile
            # direct caller still gets a card). The HEADLINE keeps every line it
            # needs — the elaboration yields, never the fact.
            hl_size = _HL_LADDER[-1][0]
            hl_lines, _ = _break_fit(hl, text_w, hl_size, 8, bold=True, tracking_em=-0.01)
            sm_size = _BREAK_BODY_MIN
            used = (len(hl_lines) - 1) * _hl_lh(hl_size) + hl_size + round(sm_size * 1.05, 1)
            room = int((avail - used - sm_size) // _sm_lh(sm_size)) + 1
            sm_lines = (_break_fit(sm, sm_w, sm_size, max(0, room))[0]
                        if (sm and room > 0) else [])
            sm_lines = [ln for ln in sm_lines if ln]

        hl_lh = _hl_lh(hl_size)
        sm_lh = _sm_lh(sm_size)
        # Leftover height is spent on RHYTHM, not on a dead field: most of it
        # opens the headline→summary gap, a little of it drops the whole block
        # off the dateline. Both are bounded, so this can never drift back into
        # the old free-centring that left a void mid-card.
        slack = max(0.0, avail - _block_h(hl_size, len(hl_lines), sm_size, len(sm_lines)))
        gap_extra = min(slack * 0.45, sm_size * 1.6) if sm_lines else 0.0
        # A headline-only card has nothing to open a gap WITH, so its slack goes
        # into optical centring instead — the one case where centring is right.
        top_nudge = (min((slack - gap_extra) * 0.40, 40.0) if sm_lines
                     else min(slack * 0.45, 120.0))
        hl_top = box_top + top_nudge + hl_size * 0.78          # first baseline
        hl_tspans = "".join(
            f'<text x="{pad_l}" y="{hl_top + i * hl_lh:.1f}" fill="#ffffff" '
            f'font-size="{hl_size:g}" font-weight="800" font-family="sans-serif" '
            f'letter-spacing="-0.01em">{_xesc(ln)}</text>'
            for i, ln in enumerate(hl_lines)
        )
        hl_bottom = hl_top + (len(hl_lines) - 1) * hl_lh

        # ── Summary block (the source's account) — omit cleanly when None ─────
        # The 3px rail at its left edge is tier-inked: the same trust grade the
        # chip encodes, repeated exactly where the eye lands on the content, so
        # an aggregator's account can never be read as an official one (the same
        # anti-laundering law the chip serves — D05).
        summary_svg = ""
        summary_bottom = hl_bottom
        if sm_lines:
            sm_top = hl_bottom + round(sm_size * 1.05, 1) + gap_extra + sm_size * 0.78
            rail_top = sm_top - sm_size * 0.86
            rail_h = (len(sm_lines) - 1) * sm_lh + sm_size * 1.12
            summary_svg = (
                f'<rect x="{pad_l}" y="{rail_top:.1f}" width="3" '
                f'height="{rail_h:.1f}" rx="1.5" fill="{tier["rail"]}" '
                f'fill-opacity="{tier["rail_opacity"]}" '
                f'class="bc-rail bc-rail-{tier["key"]}"/>'
            )
            summary_svg += "".join(
                f'<text x="{pad_l + sm_rail_inset:.0f}" y="{sm_top + i * sm_lh:.1f}" '
                f'fill="{_BREAK_BODY}" font-size="{sm_size:g}" '
                f'font-family="sans-serif">{_xesc(ln)}</text>'
                for i, ln in enumerate(sm_lines)
            )
            summary_bottom = sm_top + (len(sm_lines) - 1) * sm_lh

        # ── Related-ticker mini strip (cap 4) — omit entirely when empty ──────
        strip_svg = ""
        rows = tickers if isinstance(tickers, list) else []
        rows = rows[:4]
        if rows:
            strip_y = height - 90
            # Faint divider above the strip (box_bottom is derived from this).
            strip_svg += (
                f'<line x1="{pad_l}" y1="{height - 122:.0f}" '
                f'x2="{width - pad_l}" y2="{height - 122:.0f}" '
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
                # MEASURED off the cashtag so it can never reach the card's right
                # edge (the old `len(cashtag) * 11` guess drifted with the size).
                pct_x = cx0 + _break_text_w(cashtag, 22.0, bold=True) + 14
                strip_svg += (
                    f'<text x="{cx0:.0f}" y="{strip_y:.0f}" fill="#e2e8f0" '
                    f'font-size="22" font-weight="bold" font-family="sans-serif">'
                    f'{_xesc(cashtag)}</text>'
                )
                if pct_s:
                    strip_svg += (
                        f'<text x="{pct_x:.0f}" y="{strip_y:.0f}" fill="{pcol}" '
                        f'font-size="19" font-weight="bold" font-family="sans-serif">'
                        f'{_xesc(pct_s)}</text>'
                    )
                if price_s:
                    strip_svg += (
                        f'<text x="{cx0:.0f}" y="{strip_y + 26:.0f}" fill="{_BREAK_GREY}" '
                        f'font-size="16" font-family="sans-serif">{_xesc(price_s)}</text>'
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
                show_button=cta,
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
