"""Tests for scripts.build_movers_page.

Headless-safe: no network, no site/ writes.
Tests build_context (pure) and render_html (pure Jinja).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import sys
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scripts.build_movers_page import build_context, render_html

_ROOT = Path(__file__).resolve().parent.parent

# ── Synthetic movers data ────────────────────────────────────────────────────

def _make_sp500_tiles(gainers=("AAA", "BBB"), losers=("ZZZ",)):
    """Build sp500_tiles in the movers_source shape."""
    tiles = []
    for i, t in enumerate(gainers):
        tiles.append({
            "t": t,
            "name": f"{t} Corp",
            "sector": "Technology",
            "industry": "Software",
            "perf": {"1D": 4.0 + i},
        })
    for i, t in enumerate(losers):
        tiles.append({
            "t": t,
            "name": f"{t} Inc",
            "sector": "Financials",
            "industry": "Banks",
            "perf": {"1D": -(5.0 + i)},
        })
    return tiles


def _make_movers_data(asof="2026-07-19"):
    return {
        "sp500_tiles": _make_sp500_tiles(),
        "theme_tiles": [],
        "asof": asof,
    }


# ── build_context tests ──────────────────────────────────────────────────────

def test_build_context_none():
    ctx = build_context(None)
    assert ctx["gainers"] == []
    assert ctx["losers"] == []
    assert ctx["themes"] == []
    assert ctx["asof"] is None


def test_build_context_gainers_present():
    data = _make_movers_data()
    ctx = build_context(data)
    # AAA and BBB have pct=4.0 and 5.0, both above min_abs=3.0
    gainers = ctx["gainers"]
    tickers = [g["ticker"] for g in gainers]
    assert "AAA" in tickers or "BBB" in tickers


def test_build_context_losers_present():
    data = _make_movers_data()
    ctx = build_context(data)
    losers = ctx["losers"]
    tickers = [l["ticker"] for l in losers]
    assert "ZZZ" in tickers


def test_build_context_tf():
    data = _make_movers_data()
    ctx = build_context(data)
    assert ctx["tf"] == "1D"


def test_build_context_asof_preserved():
    data = _make_movers_data(asof="2026-07-18")
    ctx = build_context(data)
    assert ctx["asof"] == "2026-07-18"


def test_build_context_cta_url_present():
    ctx = build_context(None)
    assert ctx["cta_url"]
    assert "mastermind" in ctx["cta_url"].lower() or "app." in ctx["cta_url"]


# ── render_html tests ────────────────────────────────────────────────────────

def test_render_html_gainer_dossier_link():
    """Rendered HTML must contain a stock dossier link for the gainer AAA."""
    data = _make_movers_data()
    ctx = build_context(data)
    html = render_html(_ROOT, ctx)
    # The template links gainers to stocks/<TICKER>.html
    assert "stocks/AAA.html" in html or "stocks/BBB.html" in html


def test_render_html_og_meta_present():
    data = _make_movers_data()
    ctx = build_context(data)
    html = render_html(_ROOT, ctx)
    assert "og/movers.png" in html
    assert "summary_large_image" in html


def test_render_html_empty_state():
    """Empty-state context (no movers) renders without exception."""
    ctx = build_context(None)
    html = render_html(_ROOT, ctx)
    assert html  # non-empty HTML


def test_render_html_no_validated_word():
    """House law: 'validated' must not appear in user-facing rendered HTML."""
    data = _make_movers_data()
    ctx = build_context(data)
    html = render_html(_ROOT, ctx)
    assert "validated" not in html.lower()


def test_render_html_is_html():
    ctx = build_context(None)
    html = render_html(_ROOT, ctx)
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
