"""tests/test_marketing_card_parity.py — the posted image IS the previewed image.

Regression cover for the 2026-07-26 flagship-account incident, which had three
independent causes:

  1. The publish path rastered a SEPARATE hand-drawn PIL lookalike of the older
     v1 line chart while the Content Studio preview showed the v2 candlestick
     SVG. The two drifted until the account posted a bare line chart with no
     mastermind-x.com footer and no "Start free 14-day trial" CTA, while the
     mockup promised the full card.
  2. The weekend_levels lane attached NO media at all — every flagship weekend
     post shipped as bare text.
  3. That same lane never touched the copywriter, so eight consecutive posts
     were one f-string skeleton with the numbers swapped.

These tests pin the fixes. ZERO network and ZERO Chrome: the rasteriser is
stubbed, so they assert the WIRING (which renderer feeds the PNG, that media is
attached, that copy varies) rather than pixels.
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. One renderer: the PNG is a raster of the SVG the preview shows
# ─────────────────────────────────────────────────────────────────────────────

def test_rasterize_svg_is_fail_soft_without_chrome(monkeypatch):
    from engine.marketing import chart_render
    monkeypatch.setattr(chart_render, "find_chrome", lambda: None)
    # No rasteriser must never raise — the caller falls back to the legacy PNG.
    assert chart_render.rasterize_svg('<svg width="10" height="10"></svg>') == b""


def test_rasterize_svg_rejects_non_svg():
    from engine.marketing.chart_render import rasterize_svg
    assert rasterize_svg("") == b""
    assert rasterize_svg("not markup at all") == b""


def test_svg_dimensions_reads_attrs_then_viewbox():
    from engine.marketing.chart_render import svg_dimensions
    assert svg_dimensions('<svg viewBox="0 0 1 2" width="1000" height="850">') == (1000, 850)
    # viewBox-only roots still size correctly (an unsized inline SVG would
    # otherwise rasterize at Chrome's 300x150 default).
    assert svg_dimensions('<svg viewBox="0 0 640 480" xmlns="x">') == (640, 480)
    assert svg_dimensions("<svg>") is None


def test_publish_card_png_is_the_rastered_svg(tmp_path, monkeypatch):
    """The PNG bytes come from rasterizing the SAME svg string, not a re-render."""
    from engine.marketing import chart_render, media_publish
    monkeypatch.setattr(chart_render, "rasterize_svg", lambda svg, **kw: b"\x89PNG" + svg.encode())
    monkeypatch.setattr(media_publish, "publish_chart_png", lambda *a, **k: None)

    svg = '<svg width="1000" height="850">CARD</svg>'
    out = media_publish.publish_card(svg, chart_id="chart-001", as_of="2026-07-25",
                                     root=tmp_path)

    assert out["media_render"] == "svg_raster"
    png = (tmp_path / out["media_png_path"]).read_bytes()
    assert png == b"\x89PNG" + svg.encode()          # the raster of THIS svg
    # and the SVG artifact the admin preview reads is the same string
    assert (tmp_path / out["svg_path"]).read_text() == svg


def test_publish_card_falls_back_to_legacy_png_without_a_rasteriser(tmp_path, monkeypatch):
    """A Chrome-less host degrades the image; it must never drop the post."""
    from engine.marketing import chart_render, media_publish
    monkeypatch.setattr(chart_render, "rasterize_svg", lambda svg, **kw: b"")
    monkeypatch.setattr(media_publish, "publish_chart_png", lambda *a, **k: None)

    out = media_publish.publish_card(
        '<svg width="10" height="10"/>', chart_id="c1", as_of="2026-07-25",
        root=tmp_path, legacy_png=lambda: b"\x89PNGlegacy")

    assert out["media_render"] == "legacy_png"
    assert (tmp_path / out["media_png_path"]).read_bytes() == b"\x89PNGlegacy"


def test_publish_card_without_any_png_returns_no_media_keys(tmp_path, monkeypatch):
    from engine.marketing import chart_render, media_publish
    monkeypatch.setattr(chart_render, "rasterize_svg", lambda svg, **kw: b"")
    out = media_publish.publish_card('<svg width="10" height="10"/>', chart_id="c1",
                                     as_of="2026-07-25", root=tmp_path)
    assert "media_png_path" not in out and "media_url" not in out
    assert out["svg_path"]          # the SVG artifact is still written


def test_v2_card_carries_the_url_and_trial_cta():
    """The footer marketing bar is the whole point of posting the v2 card."""
    from engine.marketing.chart_render import render_chart_v2
    n = 80
    c = [100.0 + i for i in range(n)]
    svg = render_chart_v2(
        "AAPL", [f"2026-01-{i % 28 + 1:02d}" for i in range(n)],
        c, [x + 1 for x in c], [x - 1 for x in c], c, [1e6] * n,
    )
    assert "mastermind-x.com" in svg
    assert "Start free 14-day trial" in svg


def test_logo_overlay_is_a_watermark_not_a_sticker():
    """A near-opaque logo painted a block over the candles (MSFT, four solid
    squares). It must stay well below the price action."""
    import re
    from engine.marketing.chart_render import render_chart_v2
    n = 80
    c = [100.0 + i for i in range(n)]
    svg = render_chart_v2(
        "AAPL", [f"2026-01-{i % 28 + 1:02d}" for i in range(n)],
        c, [x + 1 for x in c], [x - 1 for x in c], c, [1e6] * n,
        logo_datauri="data:image/svg+xml;base64,AAAA",
    )
    m = re.search(r'<image href="data:image/svg\+xml[^"]*"[^>]*opacity="([\d.]+)"', svg)
    assert m, "logo overlay not rendered"
    assert float(m.group(1)) <= 0.15, f"logo opacity {m.group(1)} obscures the chart"


def test_last_price_pill_does_not_overprint_an_axis_label():
    """A round level under the pill is suppressed (381.70 pill on 380.00 label)."""
    import re
    from engine.marketing.chart_render import render_chart_v2
    # Series engineered so the last close lands right on a round axis level.
    n = 80
    c = [360.0 + (i % 40) for i in range(n - 1)] + [380.0]
    svg = render_chart_v2(
        "AAPL", [f"2026-01-{i % 28 + 1:02d}" for i in range(n)],
        c, [x + 1 for x in c], [x - 1 for x in c], c, [1e6] * n,
    )
    # The axis tick text for 380.00 must not be drawn; the pill states it.
    axis_ticks = re.findall(r'fill="#6b7a99" font-size="10" font-family="monospace">'
                            r'([\d,.]+)</text>', svg)
    assert "380.00" not in axis_ticks


# ─────────────────────────────────────────────────────────────────────────────
# 2. + 3. weekend_levels: every post carries a card, and the copy is not one
#         skeleton with the numbers swapped
# ─────────────────────────────────────────────────────────────────────────────

def _seed_ohlcv(root, ticker, closes):
    pd = pytest.importorskip("pandas")
    d = root / "data" / "stocks"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    pd.DataFrame({
        "open": closes, "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes], "close": closes,
        "volume": [1e6] * len(closes),
    }, index=idx).to_parquet(d / f"{ticker}.parquet")


def test_build_items_attaches_a_chart_card(tmp_path, monkeypatch):
    """The incident: every weekend post shipped with media == []."""
    from engine.marketing import chart_render, media_publish, weekend_levels as wl
    monkeypatch.setattr(chart_render, "rasterize_svg", lambda svg, **kw: b"\x89PNGx")
    monkeypatch.setattr(media_publish, "publish_chart_png",
                        lambda *a, **k: "https://pub-x.r2.dev/marketing/charts/x.png")
    _seed_ohlcv(tmp_path, "NVDA", [float(x) for x in range(1, 121)])

    items = wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-25", max_items=1)

    assert len(items) == 1
    media = items[0]["media"]
    assert media, "weekend post must carry a chart card"
    assert media[0]["kind"] == "chart_svg"
    assert media[0]["media_url"].startswith("https://")
    # The publisher reads source.media_url to attach without unpacking media.
    assert items[0]["source"]["media_url"] == media[0]["media_url"]


def test_build_items_stays_postable_when_the_card_fails(tmp_path, monkeypatch):
    """A chart failure degrades to text-only; it must not drop the post."""
    from engine.marketing import weekend_levels as wl
    monkeypatch.setattr(wl, "build_card", lambda *a, **k: None)
    _seed_ohlcv(tmp_path, "NVDA", [float(x) for x in range(1, 121)])
    items = wl.build_items(tmp_path, tickers=["NVDA"], as_of="2026-07-25", max_items=1)
    assert len(items) == 1 and items[0]["media"] == []


def test_floor_copy_varies_by_state_not_just_by_number():
    """Eight posts sharing one sentence skeleton is what read as bot-generated."""
    from engine.marketing import weekend_levels as wl

    series = {
        "leading": [float(x) for x in range(1, 121)],
        "basing": [float(x) for x in range(120, 0, -1)],
        "cooling": [float(x) for x in range(1, 111)] + [95.0, 96.0, 97.0, 98.0, 99.0,
                                                        98.0, 97.0, 98.0, 99.0, 98.0],
        "reclaiming": [float(x) for x in range(120, 40, -1)] + [42.0, 44.0, 46.0, 48.0,
                                                                50.0, 52.0, 54.0, 56.0],
    }
    bodies = {}
    for state, closes in series.items():
        lv = wl.compute_levels(closes)
        assert wl.classify_state(lv) == state
        _, body = wl.render_post("NVDA", lv, variant=0)
        bodies[state] = body

    # No two states may open with the same six words.
    openers = [" ".join(b.split()[:6]) for b in bodies.values()]
    assert len(set(openers)) == len(openers), f"shared opener across states: {openers}"
    # The old skeleton is gone from the state-specific frames.
    assert not any(b.startswith("Closed ") for b in bodies.values())


def test_floor_copy_names_at_most_one_moving_average():
    """The doctrine demotes technicals: naming the 20-, the 50-, the % off highs
    AND the range position in one post is a data dump, not a read."""
    from engine.marketing import weekend_levels as wl
    for closes in ([float(x) for x in range(1, 121)],
                   [float(x) for x in range(120, 0, -1)]):
        lv = wl.compute_levels(closes)
        for variant in range(len(wl._TAILS)):
            _, body = wl.render_post("NVDA", lv, variant=variant)
            assert body.count("-day") <= 1, f"stacked moving averages: {body}"


def test_assert_clean_rejects_the_em_dash():
    """copywriter.validate_copy rejects U+2014 as a model tell; the floor that
    stands in for the LLM must clear the same bar."""
    from engine.marketing import weekend_levels as wl
    with pytest.raises(ValueError):
        wl._assert_clean("$NVDA is fine — for now", "NVDA")
    # and no rendered post may contain one
    lv = wl.compute_levels([float(x) for x in range(1, 121)])
    for variant in range(len(wl._TAILS)):
        headline, body = wl.render_post("NVDA", lv, variant=variant)
        assert "—" not in f"{headline}{body}"


def test_write_copy_returns_the_floor_when_the_llm_is_off():
    """LLM off (no MARKETING_LLM_ENABLED) → floor copy, never an empty post."""
    from engine.marketing import weekend_levels as wl
    lv = wl.compute_levels([float(x) for x in range(1, 121)])
    specs = [{"ticker": "NVDA", "lv": lv, "headline": "$NVDA into the week",
              "body": "Floor body."}]
    assert wl.write_copy(specs, {}) == [("$NVDA into the week", "Floor body.")]
