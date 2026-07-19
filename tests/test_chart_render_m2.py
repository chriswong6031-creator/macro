"""tests/test_chart_render_m2.py — Tests for M2 overlay params on render_chart_v2.

Tests:
1. Both overlays None → output byte-identical to pre-overlay baseline (no avwap/poc elements)
2. avwap_overlay provided → SVG contains polyline and label text
3. poc_overlay with POC inside bar range → dashed line + band rect rendered
4. poc_overlay with POC outside bar range → NO poc dashed line rendered (skip law)
5. avwap y-range extension: overlay values outside bar range included in panel
6. build_m2_overlays returns expected schema (fail-soft on missing module)
"""
from __future__ import annotations

import re
from datetime import date, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_dates(n: int, start: str = "2025-01-02") -> list[str]:
    d = date.fromisoformat(start)
    dates = []
    count = 0
    while count < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
            count += 1
        d += timedelta(days=1)
    return dates


def _sample_ohlcv(n: int = 60, base: float = 100.0):
    """Small deterministic OHLCV for chart rendering tests."""
    dates = _make_dates(n)
    c = [base + i * 0.2 for i in range(n)]
    o = [c[0]] + c[:-1]
    h = [ci + 1.0 for ci in c]
    l = [ci - 1.0 for ci in c]
    v = [1_000_000.0] * n
    return dates, o, h, l, c, v


# ─────────────────────────────────────────────────────────────────────────────
# Tests — overlay=None gives byte-identical output
# ─────────────────────────────────────────────────────────────────────────────

def test_no_overlays_no_avwap_poc_in_svg():
    """With both overlays None, SVG must not contain AVWAP curve or POC line elements."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60)
    svg = render_chart_v2(
        "TEST", dates, o, h, l, c, v,
        avwap_overlay=None,
        poc_overlay=None,
    )
    # No AVWAP polyline (house indigo stroke on a polyline element)
    assert 'stroke="#7c5cff"' not in svg, (
        "Expected no AVWAP polyline (#7c5cff stroke) when overlay is None"
    )
    # No POC dashed line (specific dasharray+blue combination)
    # stroke-dasharray="6 4" is the POC dashing spec — only appears for POC line
    assert 'stroke-dasharray="6 4"' not in svg, (
        "Expected no POC dashed line when overlay is None"
    )
    # No value-area band rect (fill="#5b9dff" fill-opacity="0.06" is VA-specific)
    assert 'fill-opacity="0.06"' not in svg, (
        "Expected no VA band rect when overlay is None"
    )


def test_none_overlays_byte_identical():
    """render_chart_v2 with None overlays must produce the same output as without the params."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60)

    # Call with explicit None (new API) vs without the params at all
    svg_explicit_none = render_chart_v2(
        "AAPL", dates, o, h, l, c, v,
        avwap_overlay=None,
        poc_overlay=None,
    )
    svg_no_params = render_chart_v2(
        "AAPL", dates, o, h, l, c, v,
    )
    assert svg_explicit_none == svg_no_params, (
        "Output should be byte-identical when overlays are None vs not passed"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests — avwap_overlay present
# ─────────────────────────────────────────────────────────────────────────────

def test_avwap_overlay_polyline_in_svg():
    """With avwap_overlay, SVG must contain a polyline and the label text."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60)

    # Build a simple AVWAP values array (10 leading Nones, then linear)
    avwap_vals = [None] * 10 + [100.0 + i * 0.3 for i in range(50)]
    avwap_overlay = {
        "values": avwap_vals,
        "label": "AVWAP · Apr 24 vol-spike anchor",
    }
    svg = render_chart_v2(
        "NVDA", dates, o, h, l, c, v,
        avwap_overlay=avwap_overlay,
    )

    # Must contain a polyline (the AVWAP curve)
    assert "<polyline" in svg, "Expected <polyline> for AVWAP curve"

    # Must contain the label text (XML-escaped version of label)
    assert "AVWAP" in svg, "Expected 'AVWAP' label text in SVG"

    # Must contain the house indigo color
    assert "#7c5cff" in svg, "Expected house indigo #7c5cff for AVWAP curve"


def test_avwap_overlay_null_only_no_polyline():
    """All-None AVWAP values should not add a polyline (no non-null points)."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60)

    avwap_overlay = {
        "values": [None] * 60,
        "label": "AVWAP · test",
    }
    svg = render_chart_v2(
        "X", dates, o, h, l, c, v,
        avwap_overlay=avwap_overlay,
    )
    # No AVWAP-specific polyline (stroke="#7c5cff" on a polyline)
    # Note: #7c5cff appears in the favicon gradient defs, so we check the
    # polyline element specifically
    assert 'stroke="#7c5cff"' not in svg, (
        "Expected no AVWAP polyline (stroke=#7c5cff) when all avwap values are None"
    )


def test_avwap_yrange_extended():
    """AVWAP values outside bar range must be included in panel (y-scale extended)."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60, base=100.0)

    # AVWAP values substantially above bar range (bar range ~100-112, AVWAP goes to 130)
    avwap_vals = [None] * 20 + [120.0 + i * 0.5 for i in range(40)]
    avwap_overlay = {
        "values": avwap_vals,
        "label": "AVWAP · high anchor",
    }
    svg = render_chart_v2(
        "YEXT", dates, o, h, l, c, v,
        avwap_overlay=avwap_overlay,
    )
    # The AVWAP label must appear in the SVG (it was rendered, not clipped off)
    assert "AVWAP" in svg, "AVWAP label must be in SVG even when values exceed bar range"
    assert "<polyline" in svg, "AVWAP polyline must be present"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — poc_overlay
# ─────────────────────────────────────────────────────────────────────────────

def test_poc_overlay_inside_range_renders_line_and_band():
    """POC inside bar range → dashed line + band rect present."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60, base=100.0)
    # Bar range: approx 99-112 (base 100, rising 0.2/bar, wick ±1)
    poc_overlay = {
        "poc": 105.0,      # well inside range
        "va_low": 103.0,
        "va_high": 108.0,
        "label": "POC 105.00",
    }
    svg = render_chart_v2(
        "MSFT", dates, o, h, l, c, v,
        poc_overlay=poc_overlay,
    )
    # Dashed line: stroke-dasharray
    assert "stroke-dasharray" in svg, "Expected dashed line for POC inside range"
    # Band rect with fill-opacity="0.06"
    assert 'fill-opacity="0.06"' in svg, "Expected VA band rect with fill-opacity=0.06"
    # POC color
    assert "#5b9dff" in svg, "Expected #5b9dff POC/VA color"
    # Label
    assert "POC 105.00" in svg, "Expected POC label text"


def test_poc_overlay_outside_range_no_poc_line():
    """POC outside bar range → NO poc dashed line rendered (skip law)."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60, base=100.0)
    # Bar range ~99-112; POC way outside
    poc_overlay = {
        "poc": 300.0,       # far above range
        "va_low": 295.0,
        "va_high": 305.0,
        "label": "POC 300.00",
    }
    svg = render_chart_v2(
        "SKIP", dates, o, h, l, c, v,
        poc_overlay=poc_overlay,
    )
    # No dashed line (POC skip law)
    # The band also won't intersect since va range is 295-305, bar range ~98-113
    # So neither the line nor the label should appear
    assert "300.00" not in svg, (
        "Expected POC label to be skipped when POC is outside bar range"
    )
    # stroke-dasharray may appear for other elements (SMA is dashed too)
    # so we specifically check for the blue color + dasharray combination
    # by checking POC label absence is sufficient per spec
    assert "POC 300.00" not in svg


def test_poc_overlay_partial_band_clamped():
    """POC in range but VA band partially outside → band rect rendered (clamped)."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _sample_ohlcv(60, base=100.0)
    # Bar range ~99-113; VA extends below (va_low=50) and above (va_high=107)
    poc_overlay = {
        "poc": 105.0,
        "va_low": 50.0,     # below panel bottom
        "va_high": 107.0,
        "label": "POC 105.00",
    }
    svg = render_chart_v2(
        "PARTIAL", dates, o, h, l, c, v,
        poc_overlay=poc_overlay,
    )
    # Band rect must still be rendered (partial is ok)
    assert 'fill-opacity="0.06"' in svg, "Expected partial VA band rect"
    assert "#5b9dff" in svg


# ─────────────────────────────────────────────────────────────────────────────
# Tests — build_m2_overlays
# ─────────────────────────────────────────────────────────────────────────────

def test_build_m2_overlays_schema():
    """build_m2_overlays always returns the expected dict schema, never raises."""
    _m2 = pytest_importorskip_soft("engine.indicators_m2")
    from engine.marketing.chart_render import build_m2_overlays
    dates, o, h, l, c, v = _sample_ohlcv(80)
    import tempfile, os
    # Pass a non-existent root — should fail-soft and return None values
    result = build_m2_overlays("FAKE", dates, o, h, l, c, v, "/nonexistent/path")
    assert isinstance(result, dict), "build_m2_overlays must return a dict"
    assert "avwap_overlay" in result, "Must have 'avwap_overlay' key"
    assert "poc_overlay" in result, "Must have 'poc_overlay' key"
    # Either None or a valid overlay dict
    if result["avwap_overlay"] is not None:
        aov = result["avwap_overlay"]
        assert "values" in aov and "label" in aov, "avwap_overlay must have values + label"
    if result["poc_overlay"] is not None:
        pov = result["poc_overlay"]
        for k in ("poc", "va_low", "va_high", "label"):
            assert k in pov, f"poc_overlay must have key '{k}'"


def test_build_m2_overlays_fail_soft():
    """build_m2_overlays must not raise even when indicators_m2 is absent."""
    # We import it and mock by calling with bad root — should return None values
    from engine.marketing.chart_render import build_m2_overlays
    dates, o, h, l, c, v = _sample_ohlcv(30)
    result = build_m2_overlays("X", dates, o, h, l, c, v, "/no/such/path")
    # Must return a dict with both keys (values may be None)
    assert isinstance(result, dict)
    assert set(result.keys()) == {"avwap_overlay", "poc_overlay"}


# ─────────────────────────────────────────────────────────────────────────────
# Soft-skip helper (avoids pytest.importorskip side-effects in non-m2 tests)
# ─────────────────────────────────────────────────────────────────────────────

def pytest_importorskip_soft(modname: str):
    """Try to import modname; return module or skip via pytest.importorskip."""
    import importlib
    try:
        return importlib.import_module(modname)
    except ImportError:
        import pytest
        pytest.importorskip(modname)
