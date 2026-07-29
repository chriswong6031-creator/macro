"""tests/test_marketing_media_fallback_seal.py — the BUY marker may never reach
a no-claim post, INCLUDING through the Chrome-less fallback raster.

THE HOLE THIS SEALS (E-wave adversarial review, BLOCKER 1 / MAJOR 6). Two lanes
render a deliberately MARKERLESS card:

  * the filing lanes (congress / insider / house picks) — "Rep. Public bought
    NVDA six weeks ago" is a description, not a call;
  * the tape fallback — "watching, not buying yet".

Both enforced that on the SVG and only on the SVG. But the SVG is not the image
X receives: `media_publish.publish_card` rasterizes it with headless Chrome and,
when Chrome is missing or the raster times out (CI, the ubuntu publish runner —
a real, documented failure mode), falls back to `render_signal_chart_png`, which
had NO markerless mode and unconditionally drew a dashed guide, a green triangle,
a dot and the literal word BUY. So on exactly the hosts that lack Chrome, the
post that makes no call went to the timeline stamped BUY — a fabricated
recommendation attached to a named politician's trade, which the filing lane's
own docstring forbids.

Every test here forces the fallback (`rasterize_svg` -> b"") and then reads the
PIXELS of the PNG that would be uploaded. Asserting on the SVG would reproduce
the original blind spot exactly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

#: #3ddc84 — the BUY colour, shared by the guide, the triangle, the dot and the
#: label. PIL's ImageDraw does not anti-alias, so a marked card carries hundreds
#: of EXACT matches and a markerless one carries none.
BUY_RGB = (61, 220, 132)

_DATES = [f"2026-06-{d:02d}" for d in range(1, 21)]
_CLOSES = [100.0, 102.5, 101.0, 105.2, 103.8, 108.1, 107.0, 110.5, 109.2, 112.0,
           111.3, 115.8, 114.1, 118.0, 116.5, 120.2, 119.0, 122.5, 121.1, 125.0]


def _buy_pixels(png: bytes) -> int:
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB")
    raw = im.tobytes()
    target = bytes(BUY_RGB)
    return sum(1 for i in range(0, len(raw), 3) if raw[i:i + 3] == target)


# ─────────────────────────────────────────────────────────────────────────────
# 1. The renderer itself
# ─────────────────────────────────────────────────────────────────────────────

def test_markerless_png_draws_no_buy_and_the_marked_one_still_does():
    """Both directions, so the detector cannot pass vacuously.

    If the markerless branch is reverted the first assert fails; if the marker
    is ever silently dropped from real signal cards the second one does.
    """
    from engine.marketing.chart_render import render_signal_chart_png

    markerless = render_signal_chart_png("NVDA", _DATES, _CLOSES, marker_index=None)
    marked = render_signal_chart_png("NVDA", _DATES, _CLOSES, marker_index=5)

    assert _buy_pixels(markerless) == 0, (
        "a markerless card drew BUY geometry — this PNG is what X receives on a "
        "Chrome-less host")
    assert _buy_pixels(marked) > 0, (
        "the marked card drew no BUY pixels — the guard above is vacuous")
    # Deterministic on the markerless path too (no clock, no randomness).
    assert markerless == render_signal_chart_png(
        "NVDA", _DATES, _CLOSES, marker_index=None)


# ─────────────────────────────────────────────────────────────────────────────
# 2. The seam: _attach_chart_media -> publish_card -> legacy_png
# ─────────────────────────────────────────────────────────────────────────────

def _force_legacy_raster(monkeypatch):
    """No Chrome: rasterize_svg returns b"", so publish_card takes legacy_png."""
    from engine.marketing import chart_render

    monkeypatch.setattr(chart_render, "rasterize_svg", lambda svg, **kw: b"",
                        raising=False)


def _media_cfg() -> dict:
    return {"publish": {"media_enabled": True}}


def _read_png(root: Path, rel: str) -> bytes:
    return (root / rel).read_bytes()


def test_no_claim_card_fallback_png_is_markerless(monkeypatch, tmp_path):
    """A card whose caller passes marker_index=None ships a markerless raster.

    This is the filing/tape contract at the seam every lane goes through, and it
    asserts the FALLBACK actually ran (`media_render == "legacy_png"`) — a test
    that skipped the fallback would pass while the hole stayed open.
    """
    from engine.marketing.content_studio import _attach_chart_media

    _force_legacy_raster(monkeypatch)
    fc = {"id": "chart-001", "ticker": "NVDA", "svg": "<svg/>"}
    _attach_chart_media(fc, closes=_CLOSES, dates=_DATES, marker_index=None,
                        as_of="2026-07-29", root=tmp_path, cfg=_media_cfg(),
                        subtitle="$NVDA · congress")

    assert fc.get("media_render") == "legacy_png", (
        "the legacy fallback never ran — this test would be vacuous")
    assert _buy_pixels(_read_png(tmp_path, fc["media_png_path"])) == 0


def test_the_seal_is_not_vacuous_a_marked_caller_still_gets_its_marker(
        monkeypatch, tmp_path):
    """The control: an int marker_index must still draw BUY through the same seam."""
    from engine.marketing.content_studio import _attach_chart_media

    _force_legacy_raster(monkeypatch)
    fc = {"id": "chart-002", "ticker": "NVDA", "svg": "<svg/>"}
    _attach_chart_media(fc, closes=_CLOSES, dates=_DATES, marker_index=5,
                        as_of="2026-07-29", root=tmp_path, cfg=_media_cfg(),
                        subtitle="$NVDA · signal")

    assert fc.get("media_render") == "legacy_png"
    assert _buy_pixels(_read_png(tmp_path, fc["media_png_path"])) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. The DEFERRED path — what the nightly actually runs
# ─────────────────────────────────────────────────────────────────────────────

def test_deferred_tape_card_keeps_its_none_marker_through_raster_plan_media(
        monkeypatch, tmp_path):
    """`int(deferred.get("marker_index") or 0)` turned None into index 0.

    The governor calls `content_plan(defer_media=True)` and finishes with
    `raster_plan_media` AFTER the Sentinel gate, so this — not the inline call —
    is the production path. Rounding a markerless tape card's None down to 0 put
    a BUY triangle at the left edge of a "watching, not buying yet" post.
    """
    from engine.marketing.content_studio import raster_plan_media

    _force_legacy_raster(monkeypatch)
    plan = {
        "as_of": "2026-07-29",
        "featured_charts": [{
            "id": "chart-010", "ticker": "NVDA", "variant": "tape",
            "marker_source": "none", "svg": "<svg/>",
            "_defer": {"closes": _CLOSES, "dates": _DATES,
                       "marker_index": None, "subtitle": "$NVDA · tape"},
        }],
        "accounts": [{"id": "flagship", "queue": [
            {"chart_id": "chart-010", "slot": "D1-0900", "type": "chart"},
        ]}],
    }
    counts = raster_plan_media(plan, cfg=_media_cfg(), root=tmp_path)

    assert counts["rastered"] == 1, counts
    card = plan["featured_charts"][0]
    assert card.get("media_render") == "legacy_png"
    assert _buy_pixels(_read_png(tmp_path, card["media_png_path"])) == 0, (
        "the deferred tape card's markerless None was coerced to a real index")


def test_deferred_signal_card_still_carries_its_marker(monkeypatch, tmp_path):
    """Control for the test above: a real deferred index must survive too."""
    from engine.marketing.content_studio import raster_plan_media

    _force_legacy_raster(monkeypatch)
    plan = {
        "as_of": "2026-07-29",
        "featured_charts": [{
            "id": "chart-011", "ticker": "NVDA", "variant": "signal",
            "svg": "<svg/>",
            "_defer": {"closes": _CLOSES, "dates": _DATES,
                       "marker_index": 5, "subtitle": "$NVDA · signal"},
        }],
        "accounts": [{"id": "flagship", "queue": [
            {"chart_id": "chart-011", "slot": "D1-0900", "type": "signal"},
        ]}],
    }
    raster_plan_media(plan, cfg=_media_cfg(), root=tmp_path)
    card = plan["featured_charts"][0]
    assert _buy_pixels(_read_png(tmp_path, card["media_png_path"])) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. End to end through content_plan — the filing lane's own caller
# ─────────────────────────────────────────────────────────────────────────────

_OHLCV_DATES = [f"2026-07-{d:02d}" for d in range(1, 26)]
_OHLCV_CLOSES = [200.0 + i for i in range(25)]


def _stub_filing_sources(monkeypatch, *, ticker: str = "NVDA"):
    """One congress candidate, no insiders, no house picks — deterministic."""
    from engine.marketing import chart_render, congress_feed, house_picks, insider_feed

    cand = {
        "ticker": ticker,
        "facts": {"facts": [{"text": f"A member disclosed a {ticker} purchase."}],
                  "numbers_whitelist": []},
    }
    monkeypatch.setattr(congress_feed, "candidates",
                        lambda *a, **k: [dict(cand)], raising=False)
    monkeypatch.setattr(insider_feed, "candidates", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(house_picks, "house_picks", lambda *a, **k: [], raising=False)

    ohlcv = (_OHLCV_DATES,
             [c - 1 for c in _OHLCV_CLOSES], [c + 2 for c in _OHLCV_CLOSES],
             [c - 2 for c in _OHLCV_CLOSES], list(_OHLCV_CLOSES),
             [1_000_000] * len(_OHLCV_CLOSES))
    monkeypatch.setattr(chart_render, "load_ohlcv_windowed",
                        lambda t, r, **k: (ohlcv, 0), raising=False)
    monkeypatch.setattr(chart_render, "render_chart_v2",
                        lambda **kw: "<svg><!-- v2 card --></svg>", raising=False)


def _filing_plan(monkeypatch, tmp_path):
    from engine.marketing.content_studio import content_plan

    _stub_filing_sources(monkeypatch)
    _force_legacy_raster(monkeypatch)
    cfg = {
        "desk_network": {"stage": "A", "accounts": [
            {"id": "flagship", "kind": "branded", "beat": "US equities",
             "voice": "authoritative desk"},
        ]},
        "publish": {"media_enabled": True},
    }
    return content_plan(cfg, [], closes_loader=lambda t: (_DATES, _CLOSES),
                        root=tmp_path)


_STUB_PLANS = [
    {"id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL", "entry": 120.0,
     "invalidation": 100.0, "targets": [150.0, 180.0], "trigger": 125.0,
     "phase": "triggered_pre_t1", "recommended_action": "hold",
     "management_confidence": 66.0, "_signal_date": "2026-07-28"},
]


def test_a_tape_variant_card_never_ships_a_marked_fallback_png(monkeypatch, tmp_path):
    """The tape-fallback caller, through the real `content_plan` chart loop.

    A signal whose live gate fails is DEMOTED to `variant == "tape"` (it becomes
    a "watching, not triggered" post) and its v1 card is rendered markerless. The
    caller used to hand the legacy raster the Prophet `marker_index` anyway, so
    the demoted post's PNG still said BUY — under copy that explicitly does not.
    With no OHLCV available this also exercises the v1 markerless fallback that
    exists so a tape post keeps a chart at all.
    """
    from engine.marketing import chart_render, copywriter
    from engine.marketing.content_studio import content_plan

    _force_legacy_raster(monkeypatch)
    monkeypatch.setattr(chart_render, "load_ohlcv_windowed",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr(copywriter, "verify_signal_live",
                        lambda *a, **k: (False, "underwater"), raising=False)
    cfg = {
        "desk_network": {"stage": "A", "accounts": [
            {"id": "flagship", "kind": "branded", "beat": "US equities",
             "voice": "authoritative desk"},
        ]},
        "publish": {"media_enabled": True},
    }
    plan = content_plan(cfg, _STUB_PLANS,
                        closes_loader=lambda t: (_DATES, _CLOSES), root=tmp_path)

    tape = [c for c in plan["featured_charts"]
            if c.get("ticker") == "PLTR" and c.get("variant") == "tape"]
    assert tape, "no demoted tape card was produced — the guard would be vacuous"
    for card in tape:
        assert "BUY" not in str(card.get("svg") or "")
        assert card.get("media_render") == "legacy_png"
        assert _buy_pixels(_read_png(tmp_path, card["media_png_path"])) == 0, (
            f"{card['id']} is a tape card whose fallback PNG says BUY")


def test_a_filing_cards_fallback_png_never_carries_a_buy_label(monkeypatch, tmp_path):
    """The whole finding, end to end, on the real caller.

    A congressional-disclosure post, media armed, no Chrome. The uploaded PNG
    must be the markerless card — not the v1 BUY card the lane's SVG branch was
    the only thing refusing.
    """
    plan = _filing_plan(monkeypatch, tmp_path)
    filing = [c for c in plan["featured_charts"]
              if str(c.get("source") or "") in ("congress_desk", "congress", "house_picks")
              or c.get("variant") == "tape"]
    assert filing, "the filing splice produced no card — the guard would be vacuous"
    for card in filing:
        assert card.get("variant") == "tape", card
        assert card.get("media_render") == "legacy_png", (
            "the legacy fallback never ran for the filing card")
        assert _buy_pixels(_read_png(tmp_path, card["media_png_path"])) == 0, (
            f"{card['id']} shipped a BUY-marked PNG on a no-claim filing post")


def test_a_filing_card_stamps_the_series_it_actually_drew(monkeypatch, tmp_path):
    """Two renderers, ONE window.

    `_filing_chart` used to return closes_loader's series while drawing the card
    from the OHLCV window, so the stamped marker date/price described a
    different stretch of tape than the candles — and the fallback raster redrew
    that other stretch. The card's marker_date must be the last OHLCV bar.
    """
    plan = _filing_plan(monkeypatch, tmp_path)
    filing = [c for c in plan["featured_charts"] if c.get("variant") == "tape"]
    assert filing, "no filing card produced"
    for card in filing:
        assert card["marker_date"] == _OHLCV_DATES[-1], (
            "marker_date came from a different series than the drawn card")
        assert card["marker_price"] == pytest.approx(_OHLCV_CLOSES[-1], abs=1e-4)
        assert card["marker_date"] != _DATES[-1], (
            "fixture is degenerate — the two series must differ for this to bite")
