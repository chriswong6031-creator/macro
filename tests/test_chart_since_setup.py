"""tests/test_chart_since_setup.py — the "since setup" return chip + windowed loader.

Two fixes landed after an operator complaint (2026-07-26) about a marketing chart:
  1. A "-0.72 (-0.22%) / 5 bars" box floated over the candles with no referent —
     confusing. The box now (a) fires only for a MATERIAL move (|Δ| ≥ 3%) so a
     fresh signal's noise never draws it, and (b) carries a "since setup" caption
     so a reader knows it measures return-since-entry, not today's move.
  2. The publish path drew MACD/SMA starting ~1/3 across because it loaded no
     warm-up lead-in. load_ohlcv_windowed returns (bars, warmup) so a caller can
     never forget it — this pins the arithmetic.
"""
from __future__ import annotations

import math
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.marketing import chart_render  # noqa: E402
from engine.marketing.chart_render import render_chart_v2  # noqa: E402


def _series(n: int, *, drift: float) -> tuple:
    """n bars with a chosen per-bar close drift, so the move from an early anchor
    to the last close is a KNOWN sign/magnitude (no reliance on the sine texture)."""
    c = [100.0 + i * drift + 2.0 * math.sin(i / 6) for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [max(o[i], c[i]) + 0.8 for i in range(n)]
    l = [min(o[i], c[i]) - 0.8 for i in range(n)]
    vol = [1_000_000.0 for _ in range(n)]
    dates = [f"2026-{1 + (i // 28):02d}-{1 + (i % 28):02d}" for i in range(n)]
    return dates, o, h, l, c, vol


def _callout_headline(svg: str) -> str | None:
    # the bold percentage line inside the chip: e.g. >+14.2%<
    m = re.search(r">([+-][0-9]+\.[0-9]%)<", svg)
    return m.group(1) if m else None


def test_material_gain_draws_a_since_setup_chip():
    # +0.8/bar over ~40 bars from the anchor → well past the 3% material gate.
    dates, o, h, l, c, vol = _series(60, drift=0.8)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, marker_index=18,
                          highlight_index=18, pct_from_index=18)
    assert "since setup" in svg, "a material move must draw the return chip"
    hd = _callout_headline(svg)
    assert hd and hd.startswith("+"), f"headline should be a positive % , got {hd!r}"


def test_immaterial_move_draws_no_chip():
    # Nearly flat: a fresh signal that has barely travelled → the confusing
    # "-0.72 (-0.22%)" case. Must be suppressed.
    dates, o, h, l, c, vol = _series(60, drift=0.0)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, marker_index=52,
                          highlight_index=52, pct_from_index=52)
    assert "since setup" not in svg, "a sub-3% move must not draw a chip"


def test_material_loss_still_draws_a_chip_honestly():
    # A real drawdown is honest, not hidden: the suppression is symmetric, it
    # only removes NOISE, never a genuine loss.
    dates, o, h, l, c, vol = _series(60, drift=-0.8)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, marker_index=18,
                          highlight_index=18, pct_from_index=18)
    hd = _callout_headline(svg)
    assert hd and hd.startswith("-"), f"a material loss must show as negative, got {hd!r}"


def test_chip_caption_uses_plain_duration_not_bars_jargon():
    dates, o, h, l, c, vol = _series(60, drift=0.8)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, vol, marker_index=18,
                          highlight_index=18, pct_from_index=18)
    m = re.search(r">(since setup[^<]*)<", svg)
    assert m, "caption missing"
    cap = m.group(1)
    assert "bar" not in cap, f"caption should avoid 'bars' jargon: {cap!r}"
    assert ("w" in cap or "mo" in cap), f"caption should carry a plain duration: {cap!r}"


def test_windowed_loader_reports_warmup(monkeypatch):
    # Feed a synthetic load_ohlcv so the arithmetic is pinned without a parquet.
    def fake_load(ticker, root, n=90):
        k = min(n, 150)  # pretend the store has 150 rows
        d, o, h, l, c, v = _series(k, drift=0.5)
        return d, o, h, l, c, v
    monkeypatch.setattr(chart_render, "load_ohlcv", fake_load)
    out = chart_render.load_ohlcv_windowed("AAPL", ".", vis=90, warm=60)
    assert out is not None
    bars, warmup = out
    assert len(bars[0]) == 150, "loads vis+warm rows"
    assert warmup == 60, "warmup = loaded - vis so exactly `vis` bars are drawn"


def test_windowed_loader_none_when_no_bars(monkeypatch):
    monkeypatch.setattr(chart_render, "load_ohlcv", lambda *a, **k: None)
    assert chart_render.load_ohlcv_windowed("AAPL", ".") is None
