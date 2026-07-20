"""tests/test_watchlist_card.py — render_watchlist_card tests.

Covers the watchlist share-card renderer (engine.marketing.chart_render):
  - valid SVG for 3 / 5 / 8 rows
  - magnitude-descending sort of rows by |pct_change|
  - hostile ticker string is escaped (SVG-injection law)
  - monogram fallback path when no logo resolves
  - family branding (MASTERMIND lockup + CTA footer) present
  - no <script>; all text escaped; graceful None-field degradation

All tests are network-free: the default logo_root=None skips both the logo
CDN fetch and the closes loader, so nothing touches the filesystem or network.
"""
from __future__ import annotations

import re

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _rows(n: int) -> list[dict]:
    """n rows of plausible watchlist data (mixed direction)."""
    base = [
        {"ticker": "SNAP", "name": "Snap Inc.",      "price": 8.42,   "pct_change": -6.9},
        {"ticker": "RBLX", "name": "Roblox",         "price": 41.18,  "pct_change": -5.3},
        {"ticker": "PINS", "name": "Pinterest",      "price": 29.77,  "pct_change": -4.8},
        {"ticker": "META", "name": "Meta Platforms", "price": 512.30, "pct_change": -3.4},
        {"ticker": "BMBL", "name": "Bumble",         "price": 6.05,   "pct_change": -3.1},
        {"ticker": "MTCH", "name": "Match Group",    "price": 31.44,  "pct_change": -2.6},
        {"ticker": "GOOGL", "name": "Alphabet",      "price": 178.92, "pct_change": -1.9},
        {"ticker": "SPOT", "name": "Spotify",        "price": 388.10, "pct_change": -1.2},
    ]
    return base[:n]


# ---------------------------------------------------------------------------
# Valid SVG for 3 / 5 / 8 rows
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [3, 5, 8])
def test_render_watchlist_card_valid_svg(n: int):
    from engine.marketing.chart_render import render_watchlist_card
    svg = render_watchlist_card(f"{n}-row theme", _rows(n))
    assert svg.strip().startswith("<svg"), f"Expected SVG, got: {svg[:80]}"
    assert svg.rstrip().endswith("</svg>")
    # Every ticker must appear.
    for r in _rows(n):
        assert r["ticker"] in svg, f"Ticker {r['ticker']} missing from {n}-row card"


@pytest.mark.parametrize("n", [3, 10])
def test_render_watchlist_card_height_autoscales(n: int):
    """Auto height must grow with the row count (no fixed-height clipping)."""
    from engine.marketing.chart_render import render_watchlist_card
    svg = render_watchlist_card("theme", _rows(min(n, 8)) + _rows(2)[: max(0, n - 8)])
    m = re.search(r'height="(\d+)"', svg)
    assert m, "No height attribute on <svg>"
    # A 10-row card must be meaningfully taller than a 3-row card.
    small = render_watchlist_card("theme", _rows(3))
    big = render_watchlist_card("theme", _rows(8) + [
        {"ticker": "AAA", "price": 1.0, "pct_change": 9.9},
        {"ticker": "BBB", "price": 2.0, "pct_change": 8.8},
    ])
    hs = int(re.search(r'height="(\d+)"', small).group(1))
    hb = int(re.search(r'height="(\d+)"', big).group(1))
    assert hb > hs, f"10-row card ({hb}) should be taller than 3-row ({hs})"


# ---------------------------------------------------------------------------
# Magnitude sort
# ---------------------------------------------------------------------------

def test_render_watchlist_card_sorts_by_magnitude():
    from engine.marketing.chart_render import render_watchlist_card
    # Pass rows in NON-magnitude order; renderer must reorder by |pct_change| desc.
    rows = [
        {"ticker": "SMALL", "price": 10.0, "pct_change": -0.5},
        {"ticker": "HUGE",  "price": 20.0, "pct_change": 9.9},
        {"ticker": "MID",   "price": 30.0, "pct_change": -4.0},
    ]
    svg = render_watchlist_card("sort test", rows)
    i_huge = svg.index(">HUGE<")
    i_mid = svg.index(">MID<")
    i_small = svg.index(">SMALL<")
    assert i_huge < i_mid < i_small, (
        f"Rows not magnitude-sorted: HUGE@{i_huge} MID@{i_mid} SMALL@{i_small}"
    )


def test_render_watchlist_card_none_pct_sinks_to_bottom():
    from engine.marketing.chart_render import render_watchlist_card
    rows = [
        {"ticker": "NOPCT", "price": 10.0, "pct_change": None},
        {"ticker": "REAL",  "price": 20.0, "pct_change": 2.0},
    ]
    svg = render_watchlist_card("t", rows)
    assert svg.index(">REAL<") < svg.index(">NOPCT<"), (
        "Row with None pct_change should sort below rows with a real magnitude"
    )


# ---------------------------------------------------------------------------
# XSS / injection — hostile ticker must be escaped
# ---------------------------------------------------------------------------

def test_render_watchlist_card_hostile_ticker_escaped():
    from engine.marketing.chart_render import render_watchlist_card
    hostile = '<script>alert(1)</script>&"x'
    rows = [{"ticker": hostile, "name": "Evil Co", "price": 1.0, "pct_change": -1.0}]
    svg = render_watchlist_card("theme", rows)
    # Raw hostile markup must NOT appear (ticker is upper-cased + truncated, but
    # the opening angle bracket must still be escaped, never emitted raw).
    assert "<script>" not in svg, "Hostile ticker not escaped"
    assert "<SCRIPT>" not in svg, "Hostile ticker not escaped (upper-cased form)"
    # The escaped form of the leading '<script' fragment must be present.
    assert "&lt;SCRIPT" in svg, "No escaped angle-bracket entity found"
    # The card is still a valid, closed SVG.
    assert svg.strip().startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_render_watchlist_card_hostile_title_and_subtitle_escaped():
    from engine.marketing.chart_render import render_watchlist_card
    svg = render_watchlist_card(
        "<b>title</b>",
        _rows(3),
        subtitle='<i>sub</i> & "q"',
        as_of="<x>",
    )
    assert "<b>title</b>" not in svg
    assert "<i>sub</i>" not in svg
    assert "&lt;" in svg  # something got escaped


# ---------------------------------------------------------------------------
# Monogram fallback path (no logo resolves)
# ---------------------------------------------------------------------------

def test_monogram_fallback_when_no_logo(monkeypatch):
    """With logo_root set but resolve_logo returning None, each row must draw a
    deterministic monogram tile (gradient + a single letter) — never an <image>
    or a broken glyph."""
    import engine.marketing.chart_render as cr
    monkeypatch.setattr(cr, "resolve_logo", lambda *a, **k: None)
    monkeypatch.setattr(cr, "load_closes", lambda *a, **k: None)  # no sparkline data
    svg = cr.render_watchlist_card("theme", _rows(4), logo_root="/nonexistent")
    # No embedded raster logo when none resolve.
    assert "<image" not in svg, "Expected monogram fallback, found an <image> tag"
    # Monogram gradient defs present (id prefix wlmono_).
    assert "wlmono_" in svg, "Monogram gradient not emitted"
    # First-letter initials present for each ticker.
    for r in _rows(4):
        first = r["ticker"][0]
        assert f">{first}<" in svg, f"Monogram initial '{first}' missing"


def test_monogram_direct_helper():
    """The monogram helper renders a single-letter tile and is deterministic."""
    from engine.marketing.chart_render import _wl_monogram
    defs_a, grp_a = _wl_monogram("NVDA", 100, 100, 38, "u1")
    defs_b, grp_b = _wl_monogram("NVDA", 100, 100, 38, "u1")
    assert (defs_a, grp_a) == (defs_b, grp_b), "Monogram must be deterministic"
    assert ">N<" in grp_a, "Leading initial not rendered"
    assert "linearGradient" in defs_a


# ---------------------------------------------------------------------------
# Sparkline path
# ---------------------------------------------------------------------------

def test_sparkline_renders_with_data(monkeypatch):
    import engine.marketing.chart_render as cr
    monkeypatch.setattr(cr, "resolve_logo", lambda *a, **k: None)
    monkeypatch.setattr(
        cr, "load_closes",
        lambda ticker, root, n=10: (
            [f"2026-07-{6 + i:02d}" for i in range(10)],
            [100 + i for i in range(10)],
        ),
    )
    svg = cr.render_watchlist_card("theme", _rows(3), logo_root="/x")
    assert "<polyline" in svg, "Sparkline polyline not drawn when closes available"


def test_sparkline_absent_without_data(monkeypatch):
    """A ticker with no price history must degrade to no sparkline — never a
    broken glyph or an empty <polyline>."""
    import engine.marketing.chart_render as cr
    monkeypatch.setattr(cr, "resolve_logo", lambda *a, **k: None)
    monkeypatch.setattr(cr, "load_closes", lambda *a, **k: None)
    svg = cr.render_watchlist_card("theme", _rows(3), logo_root="/x")
    # No row sparklines (the only polylines in this card come from sparklines).
    assert "<polyline" not in svg


def test_sparkline_helper_empty_on_short_series():
    from engine.marketing.chart_render import _wl_sparkline
    assert _wl_sparkline(None, 0, 0, 10, 10, "#4CAF50", "u") == ""
    assert _wl_sparkline([1.0], 0, 0, 10, 10, "#4CAF50", "u") == ""
    assert _wl_sparkline([1.0, 2.0, 3.0], 0, 0, 40, 20, "#4CAF50", "u") != ""


# ---------------------------------------------------------------------------
# Family branding + safety invariants
# ---------------------------------------------------------------------------

def test_render_watchlist_card_has_mastermind_lockup():
    from engine.marketing.chart_render import render_watchlist_card
    svg = render_watchlist_card("theme", _rows(5))
    assert "MASTERMIND" in svg, "Brand lockup missing"
    assert "mastermind-x.com" in svg, "CTA footer URL missing"


def test_render_watchlist_card_no_script():
    from engine.marketing.chart_render import render_watchlist_card
    svg = render_watchlist_card("theme", _rows(5))
    assert "<script" not in svg.lower(), "SVG must not contain <script> tags"


def test_render_watchlist_card_pill_shows_pct():
    from engine.marketing.chart_render import render_watchlist_card
    rows = [{"ticker": "AAA", "price": 10.0, "pct_change": -3.4}]
    svg = render_watchlist_card("t", rows)
    assert "3.4%" in svg, "Percent change not rendered in pill"


def test_render_watchlist_card_missing_price_degrades():
    """A None price must not crash and must not print a placeholder dash."""
    from engine.marketing.chart_render import render_watchlist_card
    rows = [
        {"ticker": "AAA", "price": None, "pct_change": 2.0},
        {"ticker": "BBB", "price": 12.34, "pct_change": -1.0},
    ]
    svg = render_watchlist_card("t", rows)
    assert svg.strip().startswith("<svg")
    assert "12.34" in svg  # the row that HAS a price still renders it


def test_render_watchlist_card_empty_rows_is_valid_svg():
    from engine.marketing.chart_render import render_watchlist_card
    svg = render_watchlist_card("empty", [])
    assert svg.strip().startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "MASTERMIND" in svg  # brand still present on an empty card


def test_render_watchlist_card_deterministic():
    from engine.marketing.chart_render import render_watchlist_card
    a = render_watchlist_card("theme", _rows(5), as_of="Jul 20")
    b = render_watchlist_card("theme", _rows(5), as_of="Jul 20")
    assert a == b, "Render must be deterministic for identical inputs"


# ---------------------------------------------------------------------------
# NaN guard (fix 5b): float("nan") treated like None — no "nan" in output
# ---------------------------------------------------------------------------

def test_nan_price_degrades_cleanly():
    """float('nan') price must not print 'nan' in the SVG — degrades silently."""
    from engine.marketing.chart_render import render_watchlist_card
    rows = [{"ticker": "AAA", "price": float("nan"), "pct_change": 1.5}]
    svg = render_watchlist_card("t", rows)
    assert svg.strip().startswith("<svg")
    assert "nan" not in svg.lower(), f"'nan' appeared in SVG for NaN price"
    # The pct pill must still render (pct is valid)
    assert "1.5%" in svg, "Valid pct_change must still render when price is NaN"


def test_nan_pct_degrades_cleanly():
    """float('nan') pct_change must not print 'nan' — degrades to no pill."""
    from engine.marketing.chart_render import render_watchlist_card
    rows = [
        {"ticker": "AAA", "price": 10.0, "pct_change": float("nan")},
        {"ticker": "BBB", "price": 20.0, "pct_change": 2.0},
    ]
    svg = render_watchlist_card("t", rows)
    assert svg.strip().startswith("<svg")
    assert "nan" not in svg.lower(), f"'nan' appeared in SVG for NaN pct"
    # Valid price for AAA must still appear; BBB's pct must render
    assert "10.00" in svg, "Valid price must render even when pct is NaN"
    assert "2.0%" in svg, "Valid BBB pct must render"


# ---------------------------------------------------------------------------
# Determinism: uid is zlib.crc32, not hash() (PYTHONHASHSEED-stable)
# ---------------------------------------------------------------------------

def test_render_watchlist_card_uid_is_stable_across_hash_seeds():
    """The wl_uid gradient-id must be stable regardless of PYTHONHASHSEED."""
    import subprocess
    import sys
    import os
    code = (
        "from engine.marketing.chart_render import render_watchlist_card; "
        "import re; "
        "svg = render_watchlist_card('Social media', "
        "[{'ticker': 'SNAP', 'price': 8.0, 'pct_change': -3.0}]); "
        "ids = re.findall(r'id=\"([^\"]+)\"', svg); "
        "print('|'.join(sorted(set(ids))))"
    )
    import pathlib as _pl
    env_base = {"PATH": os.environ.get("PATH", "")}
    repo_root = str(_pl.Path(__file__).resolve().parent.parent)
    outs = []
    for seed in ("0", "1", "2", "42"):
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            env={**env_base, "PYTHONHASHSEED": seed},
            cwd=repo_root,
        )
        outs.append(r.stdout.strip())
    assert outs[0] == outs[1] == outs[2] == outs[3], (
        f"render_watchlist_card uid is not deterministic across PYTHONHASHSEED: {outs}"
    )
