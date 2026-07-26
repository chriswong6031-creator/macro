"""tests/test_chart_render_inline.py — W6c inline-chat chart layout.

Covers the render_chart_v2 kwargs the brain gateway's _chart_for_chat uses so an
inline chart matches the Terminal idiom:
  1. warmup makes SMA50 span from the visible LEFT edge (no mid-chart start)
  2. warmup makes MACD span from the visible left edge too
  3. volume_overlay embeds volume in the price pane → no VOLUME subpanel label
  4. subpanel_h grows the (now sole) MACD pane
  5. backward compat: warmup=0 + no overlay keeps the classic VOLUME subpanel
  6. output stays self-contained (no <script>, starts with <svg>)
  7. a SETUP mark that lands inside the warmup lead-in is dropped (off-screen)
"""
from __future__ import annotations

import math
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.marketing.chart_render import render_chart_v2  # noqa: E402

PAD_L = 14  # left padding used by render_chart_v2 (first drawn bar sits near here)

# Stroke colors these tests grep for, mirrored from engine/marketing/chart_render.py.
# Keep them in sync with the renderer: a color move there turns every polyline probe
# below into a silent no-match (x=None), which reads as "the pane vanished" rather
# than "the palette changed". #3088 moved MACD from raw material-blue (#2196F3) to
# house blue and left this file behind — it stayed red on main until 2026-07-26.
SMA_AMBER = "#F59E0B"   # SMA50 curve in the price pane (MACD's signal line shares it)
MACD_BLUE = "#5b9dff"   # MACD line in the MACD subpanel


def _series(n: int) -> tuple:
    c = [100 + i * 0.4 + 6 * math.sin(i / 7) for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [max(o[i], c[i]) + 1.2 for i in range(n)]
    l = [min(o[i], c[i]) - 1.2 for i in range(n)]
    vol = [1_000_000 * (1 + 0.5 * math.sin(i / 5)) for i in range(n)]
    dates = [f"2026-{1 + (i // 30):02d}-{1 + (i % 28):02d}" for i in range(n)]
    return dates, o, h, l, c, vol


def _leftmost_x(svg: str, stroke: str) -> float | None:
    """Leftmost x of the FIRST polyline drawn with ``stroke``, or None if there is none.

    First-match matters for SMA_AMBER, which the price-pane SMA50 and the MACD
    signal line both use: the price pane is emitted before the subpanels, so the
    first amber polyline is always the SMA50.
    """
    m = re.search(r'<polyline points="([^"]+)"[^>]*stroke="' + re.escape(stroke) + '"', svg)
    if not m:
        return None
    return min(float(p.split(",")[0]) for p in m.group(1).split())


def test_warmup_sma_spans_from_left():
    dates, o, h, l, c, vol = _series(150)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, warmup=60,
                          volume_overlay=True, subpanel_h=190, indicators=("volume", "macd"))
    x = _leftmost_x(svg, SMA_AMBER)  # SMA50 amber curve
    assert x is not None, f"no {SMA_AMBER} polyline — SMA50 missing, or its color moved"
    assert x < PAD_L + 16, f"SMA50 must span from the left edge, got x={x}"


def test_warmup_macd_spans_from_left():
    dates, o, h, l, c, vol = _series(150)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, warmup=60,
                          volume_overlay=True, subpanel_h=190, indicators=("volume", "macd"))
    # The MACD pane must actually exist before its span means anything — assert the
    # label separately so a vanished pane and a moved palette fail with distinct text.
    assert ">MACD<" in svg, "MACD pane must render under warmup + volume_overlay"
    x = _leftmost_x(svg, MACD_BLUE)  # MACD line, house blue
    assert x is not None, f"no {MACD_BLUE} polyline — MACD line missing, or its color moved"
    assert x < PAD_L + 26, f"MACD must span from the left edge, got x={x}"


def test_volume_overlay_drops_subpanel_but_keeps_macd():
    dates, o, h, l, c, vol = _series(150)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, warmup=60,
                          volume_overlay=True, subpanel_h=190, indicators=("volume", "macd"))
    assert ">VOLUME<" not in svg, "volume_overlay must not draw a VOLUME subpanel label"
    assert "embedded volume" in svg, "embedded-volume layer should be present"
    assert ">MACD<" in svg, "MACD pane must still render"


def test_backward_compat_keeps_volume_subpanel():
    dates, o, h, l, c, vol = _series(150)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, indicators=("volume", "macd"))
    assert ">VOLUME<" in svg and ">MACD<" in svg, "default path keeps both subpanels"
    # default SMA50 starts ~1/3 across (bar 50 of 150) — well right of the left edge
    x = _leftmost_x(svg, SMA_AMBER)
    assert x is not None, f"no {SMA_AMBER} polyline — SMA50 missing, or its color moved"
    assert x > PAD_L + 100, "default (warmup=0) SMA starts mid-chart, unchanged"


def test_self_contained_no_script():
    dates, o, h, l, c, vol = _series(150)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, warmup=60, volume_overlay=True)
    assert "<script" not in svg
    assert svg.startswith("<svg")


def test_setup_mark_in_warmup_is_dropped():
    """A highlight index inside the (undrawn) warmup lead-in must not draw a disc."""
    dates, o, h, l, c, vol = _series(150)
    # index 30 is inside warmup=60 → off-screen → SETUP pill must not render
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, warmup=60,
                          volume_overlay=True, highlight_index=30)
    assert ">SETUP<" not in svg, "a mark buried in the warmup lead-in must be dropped"
    # but a visible index (100 >= 60) does draw it
    svg2 = render_chart_v2("AAPL", dates, o, h, l, c, vol, warmup=60,
                           volume_overlay=True, highlight_index=100)
    assert ">SETUP<" in svg2, "a visible mark must render"
