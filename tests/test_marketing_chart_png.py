"""tests/test_marketing_chart_png.py — signal-chart PNG renderer (image pipeline).

render_signal_chart_png rasterizes the dark-theme SVG signal chart to a PNG (X
rejects SVG). Assertions: PNG magic bytes, byte-determinism across two renders
(no clock/randomness), correct 1200x675 size, NO technical-indicator words in the
bytes/metadata, and honest handling of a too-thin series. PIL is a vendored dep;
if it is somehow absent the function returns b"" (skip rather than fail).
"""
from __future__ import annotations

import io

import pytest

pytest.importorskip("PIL")

# A monotone-ish sample series with a mid-run BUY marker.
_CLOSES = [100.0, 102.5, 101.0, 105.2, 103.8, 108.1, 107.0, 110.5, 109.2, 112.0,
           111.3, 115.8, 114.1, 118.0, 116.5, 120.2, 119.0, 122.5, 121.1, 125.0]
_DATES = [f"2026-06-{d:02d}" for d in range(1, 21)]
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _render(**kw):
    from engine.marketing.chart_render import render_signal_chart_png
    base = dict(ticker="NVDA", dates=_DATES, closes=_CLOSES, marker_index=5, subtitle="signal")
    base.update(kw)
    return render_signal_chart_png(base["ticker"], base["dates"], base["closes"],
                                   marker_index=base["marker_index"], subtitle=base["subtitle"])


def test_png_magic_bytes():
    png = _render()
    assert png[:8] == _PNG_MAGIC


def test_png_deterministic_across_two_renders():
    assert _render() == _render()


def test_png_size_is_landscape_1200x675():
    from PIL import Image
    im = Image.open(io.BytesIO(_render()))
    assert im.size == (1200, 675)


@pytest.mark.parametrize("bad", [b"MACD", b"RSI", b"EMA", b"bollinger", b"stochastic", b"ichimoku"])
def test_png_has_no_indicator_words(bad):
    # Neither drawn nor in PNG metadata (bare save, no pnginfo).
    assert bad.lower() not in _render().lower()


def test_png_thin_series_is_honest_deterministic():
    from engine.marketing.chart_render import render_signal_chart_png
    from PIL import Image
    a = render_signal_chart_png("TSLA", [], [], marker_index=0)
    b = render_signal_chart_png("TSLA", [], [], marker_index=0)
    assert a[:8] == _PNG_MAGIC
    assert a == b  # deterministic even on the empty path
    assert Image.open(io.BytesIO(a)).size == (1200, 675)


def test_png_marker_index_out_of_range_is_clamped():
    # An out-of-range marker must not raise; still a valid PNG.
    png = _render(marker_index=9999)
    assert png[:8] == _PNG_MAGIC


def test_png_custom_size_respected():
    from PIL import Image
    from engine.marketing.chart_render import render_signal_chart_png
    png = render_signal_chart_png("AMD", _DATES, _CLOSES, marker_index=3, width=800, height=450)
    assert Image.open(io.BytesIO(png)).size == (800, 450)
