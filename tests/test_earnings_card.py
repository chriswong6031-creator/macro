"""tests/test_earnings_card.py — Earnings card renderer + fast-lane scaffold tests.

Coverage:
  A. render_earnings_card:
     1. Beat (AAPL EPS 2.10 vs 1.90) → green chip + BEAT label
     2. Miss → red chip + MISS label
     3. EPS-only (no rev) → renders without revenue block
     4. Logo embeds from a synthetic cached PNG (logo_root path)
     5. No <script> in output
     6. All text XSS-escaped (hostile ticker)
     7. < 60 KB with logo embedded

  B. todays_reporters:
     8. Filters by date — only today's reporters returned
     9. Maps time-pre-market → "pre", time-after-hours → "post", etc.
    10. Empty result when no reporters today

  C. build_earnings_post:
    11. Returns svg + headline + body dict
    12. Headline contains ticker, verdict, surprise pct
    13. EPS-only variant (no rev)
    14. Fail-soft: returns empty dict on bad inputs (no raise)
"""
from __future__ import annotations

import base64
import io
import json
import struct
import zlib
import pathlib
import datetime
import os

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tiny_white_png(width: int = 4, height: int = 4) -> bytes:
    """Generate a minimal valid RGBA PNG with all-white pixels."""
    # Construct a tiny RGBA PNG by hand (no PIL dependency in tests)
    raw_rows = []
    for _ in range(height):
        # filter byte 0 (None) + RGBA pixels
        row = b"\x00" + b"\xff\xff\xff\xff" * width
        raw_rows.append(row)
    raw_data = b"".join(raw_rows)
    compressed = zlib.compress(raw_data, 9)

    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr_data)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    return png


def _write_logo_cache(root: pathlib.Path, ticker: str, png_bytes: bytes) -> pathlib.Path:
    """Write a synthetic whitened logo to the cache location."""
    cache_dir = root / "data" / "marketing" / "logos"
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{ticker.upper()}_white.png"
    p.write_bytes(png_bytes)
    return p


def _write_earnings_parquet(root: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    """Write a minimal earnings.parquet with given rows."""
    import pandas as pd
    path = root / "data" / "earnings"
    path.mkdir(parents=True, exist_ok=True)
    pq_path = path / "earnings.parquet"
    df = pd.DataFrame(rows)
    df = df.set_index("ticker")
    df.to_parquet(pq_path)
    return pq_path


# ─────────────────────────────────────────────────────────────────────────────
# A. render_earnings_card
# ─────────────────────────────────────────────────────────────────────────────

def test_beat_card_green_chip():
    """AAPL EPS 2.10 vs 1.90 → green (#4CAF50) chip + BEAT text."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("AAPL", "Apple Inc.", 2.10, 1.90, None, None)
    assert "<svg" in svg
    assert "AAPL" in svg
    assert "BEAT" in svg
    # Green chip color
    assert "#4CAF50" in svg


def test_miss_card_red_chip():
    """EPS miss → red (#E23B3B) chip + MISS text."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("MSFT", "Microsoft Corp.", 2.50, 2.80, None, None)
    assert "MISS" in svg
    assert "#E23B3B" in svg


def test_eps_only_no_rev_renders():
    """rev_actual=None, rev_est=None → SVG renders, no revenue block label."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("NVDA", "NVIDIA Corp.", 1.87, 1.70, None, None)
    assert "<svg" in svg
    # EPS-only path uses centered layout — should say EARNINGS PER SHARE
    assert "EARNINGS PER SHARE" in svg
    # No revenue column header
    assert "REVENUE" not in svg


def test_with_rev_both_columns():
    """With rev both present → both EPS and REVENUE headers present."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card(
        "AAPL", "Apple Inc.",
        2.10, 1.90,
        94_930_000_000.0, 93_500_000_000.0,
    )
    assert "EPS" in svg
    assert "REVENUE" in svg
    assert "BEAT" in svg


def test_quarter_label_present():
    """quarter= param appears in SVG."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card(
        "AAPL", "Apple Inc.", 2.10, 1.90, None, None, quarter="Q2 2026"
    )
    assert "Q2 2026" in svg


def test_logo_embeds_from_cache(tmp_path):
    """Logo from logo_root → data URI embedded (href=data:image/png)."""
    png = _tiny_white_png()
    _write_logo_cache(tmp_path, "AAPL", png)
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card(
        "AAPL", "Apple Inc.", 2.10, 1.90, None, None, logo_root=tmp_path
    )
    assert 'href="data:image/png;base64,' in svg


def test_logo_datauri_embedded():
    """Pre-resolved logo_datauri embeds directly without root resolution."""
    from engine.marketing.chart_render import render_earnings_card
    png = _tiny_white_png()
    b64 = base64.b64encode(png).decode("ascii")
    datauri = f"data:image/png;base64,{b64}"
    svg = render_earnings_card(
        "TSLA", "Tesla Inc.", 0.52, 0.60, None, None,
        logo_datauri=datauri,
    )
    assert b64[:20] in svg


def test_no_script_tag():
    """No <script> in earnings card SVG."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("AAPL", "Apple Inc.", 2.10, 1.90, None, None)
    assert "<script" not in svg.lower()


def test_xss_escaped_hostile_ticker():
    """Hostile ticker with XML chars → escaped in output, no raw < or &."""
    from engine.marketing.chart_render import render_earnings_card
    # Ticker with XML-hostile chars
    svg = render_earnings_card(
        "<XSS>", "Test & Co <evil>", 1.0, 0.9, None, None
    )
    # Raw unescaped chars must not appear outside defs/content
    assert "<XSS>" not in svg
    assert "&lt;XSS&gt;" in svg


def test_under_60kb_with_logo(tmp_path):
    """Card with embedded logo must stay under 60 KB."""
    png = _tiny_white_png(16, 16)
    _write_logo_cache(tmp_path, "AAPL", png)
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card(
        "AAPL", "Apple Inc.", 2.10, 1.90,
        94_930_000_000.0, 93_500_000_000.0,
        logo_root=tmp_path,
    )
    assert len(svg.encode("utf-8")) < 60 * 1024


def test_inline_classification_grey():
    """EPS within 0.5% of est → INLINE chip."""
    from engine.marketing.chart_render import render_earnings_card
    # 2.00 actual vs 2.00 est → exactly 0% surprise → INLINE
    svg = render_earnings_card("AMZN", "Amazon.com Inc.", 2.00, 2.00, None, None)
    assert "INLINE" in svg


def test_rev_beat_miss_chip():
    """Rev miss while EPS beats → both chips present with correct verdicts."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card(
        "META", "Meta Platforms",
        5.50, 5.00,           # EPS beat
        40_000_000_000.0,
        42_000_000_000.0,     # Rev miss
    )
    assert "BEAT" in svg
    assert "MISS" in svg


def test_mastermind_branding():
    """MASTERMIND wordmark and footer CTA present."""
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("AAPL", "Apple Inc.", 2.10, 1.90, None, None)
    assert "MASTERMIND" in svg
    assert "mastermind-x.com" in svg


# ─────────────────────────────────────────────────────────────────────────────
# B. todays_reporters
# ─────────────────────────────────────────────────────────────────────────────

def test_todays_reporters_filters_by_date(tmp_path):
    """Only rows with next_date == today are returned."""
    _write_earnings_parquet(tmp_path, [
        {"ticker": "AAPL", "next_date": "2026-07-19", "next_time": "time-after-hours",
         "eps_forecast": 1.88, "surprises_json": "[]", "as_of": "2026-07-19"},
        {"ticker": "MSFT", "next_date": "2026-07-20", "next_time": "time-pre-market",
         "eps_forecast": 3.10, "surprises_json": "[]", "as_of": "2026-07-19"},
    ])
    from engine.marketing.earnings_card import todays_reporters
    results = todays_reporters(tmp_path, today="2026-07-19")
    assert len(results) == 1
    assert results[0]["ticker"] == "AAPL"


def test_todays_reporters_time_mapping(tmp_path):
    """next_time strings map to pre/post/unknown."""
    _write_earnings_parquet(tmp_path, [
        {"ticker": "A", "next_date": "2026-07-19", "next_time": "time-pre-market",
         "eps_forecast": 1.0, "surprises_json": "[]", "as_of": "2026-07-19"},
        {"ticker": "B", "next_date": "2026-07-19", "next_time": "time-after-hours",
         "eps_forecast": 1.0, "surprises_json": "[]", "as_of": "2026-07-19"},
        {"ticker": "C", "next_date": "2026-07-19", "next_time": "time-not-supplied",
         "eps_forecast": 1.0, "surprises_json": "[]", "as_of": "2026-07-19"},
    ])
    from engine.marketing.earnings_card import todays_reporters
    results = todays_reporters(tmp_path, today="2026-07-19")
    by_ticker = {r["ticker"]: r["when"] for r in results}
    assert by_ticker["A"] == "pre"
    assert by_ticker["B"] == "post"
    assert by_ticker["C"] == "unknown"


def test_todays_reporters_empty_when_no_match(tmp_path):
    """Returns empty list when no reporters for today."""
    _write_earnings_parquet(tmp_path, [
        {"ticker": "AAPL", "next_date": "2026-07-30", "next_time": "time-after-hours",
         "eps_forecast": 1.88, "surprises_json": "[]", "as_of": "2026-07-19"},
    ])
    from engine.marketing.earnings_card import todays_reporters
    results = todays_reporters(tmp_path, today="2026-07-19")
    assert results == []


def test_todays_reporters_missing_file(tmp_path):
    """Returns [] when parquet doesn't exist — no raise."""
    from engine.marketing.earnings_card import todays_reporters
    results = todays_reporters(tmp_path, today="2026-07-19")
    assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# C. build_earnings_post
# ─────────────────────────────────────────────────────────────────────────────

def test_build_earnings_post_returns_all_keys(tmp_path):
    """Returns dict with headline, body, svg."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "AAPL", "Apple Inc.", 2.10, 1.90, None, None, tmp_path
    )
    assert "headline" in result
    assert "body" in result
    assert "svg" in result
    assert result["svg"].startswith("<svg")


def test_build_earnings_post_headline_contains_ticker(tmp_path):
    """Headline includes ticker and verdict."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "AAPL", "Apple Inc.", 2.10, 1.90, None, None, tmp_path
    )
    assert "AAPL" in result["headline"]
    assert "BEAT" in result["headline"]


def test_build_earnings_post_headline_surprise_pct(tmp_path):
    """Headline includes surprise percentage."""
    from engine.marketing.earnings_card import build_earnings_post
    # 2.10 vs 1.90 → +10.5% surprise
    result = build_earnings_post(
        "AAPL", "Apple Inc.", 2.10, 1.90, None, None, tmp_path
    )
    assert "+" in result["headline"]  # positive surprise


def test_build_earnings_post_miss(tmp_path):
    """Miss result shows MISS in headline."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "MSFT", "Microsoft Corp.", 2.50, 2.80, None, None, tmp_path
    )
    assert "MISS" in result["headline"]


def test_build_earnings_post_eps_only_svg(tmp_path):
    """EPS-only (no rev) → svg renders (no REVENUE in output)."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "NVDA", "NVIDIA Corp.", 1.87, 1.70, None, None, tmp_path
    )
    assert "REVENUE" not in result["svg"]
    assert "<svg" in result["svg"]


def test_build_earnings_post_with_rev(tmp_path):
    """With revenue → REVENUE appears in SVG."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "AAPL", "Apple Inc.",
        2.10, 1.90,
        94_930_000_000.0, 93_500_000_000.0,
        tmp_path,
    )
    assert "REVENUE" in result["svg"]
    assert "Rev" in result["headline"]


def test_build_earnings_post_with_quarter(tmp_path):
    """quarter= passed through to SVG and headline."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "AAPL", "Apple Inc.", 2.10, 1.90, None, None, tmp_path,
        quarter="Q2 2026"
    )
    assert "Q2 2026" in result["svg"]
    assert "Q2 2026" in result["headline"]


def test_build_earnings_post_failsoft(tmp_path):
    """Fail-soft: returns empty dict rather than raising on bad inputs."""
    from engine.marketing.earnings_card import build_earnings_post
    # Pass NaN actual — should not raise
    import math
    result = build_earnings_post(
        "", "", math.nan, math.nan, None, None, tmp_path
    )
    # Must return a dict, never raise
    assert isinstance(result, dict)


def test_build_earnings_post_headline_length(tmp_path):
    """Headline ≤ 280 chars (Twitter/X limit)."""
    from engine.marketing.earnings_card import build_earnings_post
    result = build_earnings_post(
        "A" * 20, "A" * 80, 2.10, 1.90,
        94_930_000_000.0, 93_500_000_000.0,
        tmp_path,
    )
    assert len(result["headline"]) <= 280


# ─────────────────────────────────────────────────────────────────────────────
# Sample render for manual verification (not a test — run as __main__)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pathlib
    from engine.marketing.chart_render import render_earnings_card

    # Beat card (AAPL)
    svg_beat = render_earnings_card(
        "AAPL", "Apple Inc.",
        2.10, 1.90,
        94_930_000_000.0, 93_500_000_000.0,
        quarter="Q2 2026",
    )
    out = pathlib.Path("/tmp/earnings_card.svg")
    out.write_text(svg_beat, encoding="utf-8")
    print(f"Beat card written to {out} ({len(svg_beat.encode())} bytes)")

    # Miss card
    svg_miss = render_earnings_card(
        "MSFT", "Microsoft Corp.",
        2.50, 2.80,
        60_000_000_000.0, 62_000_000_000.0,
        quarter="Q4 2026",
    )
    out_miss = pathlib.Path("/tmp/earnings_card_miss.svg")
    out_miss.write_text(svg_miss, encoding="utf-8")
    print(f"Miss card written to {out_miss} ({len(svg_miss.encode())} bytes)")
