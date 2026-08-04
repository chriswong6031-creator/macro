"""tests/test_watchlist_logo_contrast.py — the watchlist avatar chip must never
ship an invisible company mark.

THE DEFECT THESE TESTS PIN (live on the flagship 2026-08-03 ~17:30Z). The
publish-time content lane posted a theme_list watchlist card whose per-row logos
rendered as pure-white marks on a near-white avatar disc — COHR, LITE, AXON and
RBLX went out as blank circles. Operator: "some of them are using pure white logos
on a white background making it completely invisible wtf".

Root cause: the card mounted EVERY mark on one fixed near-white plate
(#FFFFFF→#E7ECF6), on the assumption that a "full-colour" icon has a hue dark
enough to read against it. The nvstly source set is a DARK-THEME icon set. Measured
straight from the CDN over 70 tickers:

  * 36 of 70 (51%) put less than half their ink above a 3:1 contrast ratio on that
    near-white plate;
  * 16 of them measure mean relative luminance 1.000 — every opaque pixel is pure
    white, contrast ratio 1.00:1 against #FFFFFF, i.e. absolute zero;
  * the mirror is equally real — JPM, WFC, LIN, DHR and NFLX are near-black marks
    that vanish on anything dark.

So no single plate serves the set, and the fix is to CHOOSE the plate per mark from
the mark's own pixels. These tests hold that choice to a stated, computed floor.

THE CONTRACT UNDER TEST
    Every mark drawn in a watchlist row must put at least 55% of its ink above a
    3:1 contrast ratio against EVERY colour of the plate it lands on. 3:1 is
    WCAG 2.1 SC 1.4.11 (non-text contrast) — the published floor for a graphical
    object whose shape must be identifiable, which is exactly what a logo is
    (nobody reads it, they recognise its silhouette). 55% is a clear majority
    rather than a coin flip: below half, more of the silhouette is lost than kept.
    A mark that clears the floor on NEITHER plate is drawn as a monogram, so the
    avatar column can never contain a blank hole.

NETWORK / WRITE SAFETY. Every test is network-free and writes nothing. The real
brand marks live in tests/fixtures/logos/ as committed bytes (produced by the same
logo_cache._downscale the live lane caches with), so nothing here touches the CDN
or data/marketing/logos/.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "logos"

# The four marks the operator caught rendering invisible on the live card, plus two
# controls. U (Unity) and JPM are DARK marks: they are the inverse scan — a fix
# that simply darkened every plate would make these two vanish instead, so they
# must still land on paper.
LIVE_DEFECT_TICKERS = ["COHR", "LITE", "AXON", "RBLX"]
DARK_MARK_CONTROLS = ["U", "JPM"]


def _fixture_bytes(ticker: str) -> bytes:
    """Real brand-mark bytes for *ticker*, exactly as the live lane caches them.

    Hard-fails (never skips) when the file is missing: these fixtures ARE the
    regression pin for a defect that reached production, and a pin that quietly
    skips itself is not a pin.
    """
    p = FIXTURES / f"{ticker}_color.png"
    assert p.exists(), (
        f"Missing regression fixture {p}. These are the marks that shipped "
        f"invisible on 2026-08-03; the test cannot pin the defect without them."
    )
    return p.read_bytes()


def _png(pixels: "list[tuple[int, int, int, int]]", size: tuple[int, int]) -> bytes:
    """Build a tiny RGBA PNG from an explicit pixel list (no network, no files)."""
    from PIL import Image
    img = Image.new("RGBA", size)
    img.putdata(pixels)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _solid_png(rgba: tuple[int, int, int, int], size: tuple[int, int] = (32, 32)) -> bytes:
    return _png([rgba] * (size[0] * size[1]), size)


def _datauri(png_bytes: bytes) -> str:
    import base64
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


# ---------------------------------------------------------------------------
# WCAG primitives — the arithmetic the whole decision rests on
# ---------------------------------------------------------------------------

def test_relative_luminance_matches_wcag_anchors():
    """Pins the LINEARISED sRGB formula, not a naive weighted byte average.

    The naive form overstates the luminance of dark saturated brand inks by roughly
    2x in exactly the band where a plate decision flips, which would strand dark
    marks on dark plates. #808080 is the anchor that separates the two: WCAG says
    0.2159, the naive form says 0.502.
    """
    from engine.marketing.logo_cache import relative_luminance
    assert relative_luminance(255, 255, 255) == pytest.approx(1.0, abs=1e-9)
    assert relative_luminance(0, 0, 0) == pytest.approx(0.0, abs=1e-9)
    assert relative_luminance(128, 128, 128) == pytest.approx(0.2159, abs=5e-4), (
        "Mid grey must linearise to ~0.216 (WCAG), not ~0.502 (naive byte average)"
    )


def test_contrast_ratio_matches_wcag_anchors():
    from engine.marketing.logo_cache import contrast_ratio, relative_luminance
    black = relative_luminance(0, 0, 0)
    white = relative_luminance(255, 255, 255)
    assert contrast_ratio(black, white) == pytest.approx(21.0, abs=1e-6)
    assert contrast_ratio(white, black) == pytest.approx(21.0, abs=1e-6), (
        "Contrast ratio must be symmetric in its arguments"
    )
    assert contrast_ratio(white, white) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# The measurement — mark_legible_fraction
# ---------------------------------------------------------------------------

def test_pure_white_mark_scores_zero_on_the_paper_plate():
    """THE defect, stated as a number.

    A pure-white knockout on the near-white plate the card used to ship is not
    "low contrast", it is 1.00:1 — no ink clears any floor at all. Sixteen of the
    seventy sampled marks are exactly this, including COHR, AXON and RBLX.
    """
    from engine.marketing.chart_render import _WL_CHIP_PAPER, _WL_CHIP_SLATE
    from engine.marketing.logo_cache import mark_legible_fraction
    white = _solid_png((255, 255, 255, 255))
    on_paper = mark_legible_fraction(
        white, (_WL_CHIP_PAPER["top"], _WL_CHIP_PAPER["bot"])
    )
    on_slate = mark_legible_fraction(
        white, (_WL_CHIP_SLATE["top"], _WL_CHIP_SLATE["bot"])
    )
    assert on_paper == pytest.approx(0.0), (
        f"A pure-white mark must score 0 on the near-white plate, got {on_paper}"
    )
    assert on_slate == pytest.approx(1.0), (
        f"A pure-white mark must score 1 on the slate plate, got {on_slate}"
    )


def test_legible_fraction_scores_against_the_worst_gradient_stop():
    """MUTATION GUARD on the "every plate colour, not the average" rule.

    The plate is a gradient. A mark tuned to clear the floor against the DARK stop
    while failing against the LIGHT stop must score zero — if the implementation
    averaged the stops, or checked only one, this mark would score 1.0 and a
    half-invisible logo would ship.
    """
    from engine.marketing.logo_cache import (
        contrast_ratio, mark_legible_fraction, relative_luminance,
    )
    # The stops are deliberately the extreme pair (#FFFFFF / #000000) rather than a
    # production plate. The shipped gradients are shallow — their two stops differ
    # by ~20% in luminance — so an averaging implementation gives nearly the same
    # answer as a worst-case one on them, and a test built on a production plate
    # CANNOT see the mutation (verified: it passed while the code averaged).
    # A wide pair separates the two implementations by a mile.
    stops = ("#FFFFFF", "#000000")
    lum_light = relative_luminance(0xFF, 0xFF, 0xFF)
    lum_dark = relative_luminance(0x00, 0x00, 0x00)

    # A light-grey ink: hopeless against white, excellent against black. The mean of
    # those two ratios sails past 3:1 while the worst of them is nowhere near it.
    ink = None
    for v in range(255, -1, -1):
        lum = relative_luminance(v, v, v)
        c_light = contrast_ratio(lum, lum_light)
        c_dark = contrast_ratio(lum, lum_dark)
        if c_light < 3.0 and (c_light + c_dark) / 2.0 >= 3.0:
            ink = v
            break
    assert ink is not None, "no grey separates worst-case from mean — retune fixture"

    mark = _solid_png((ink, ink, ink, 255))
    dark_only = mark_legible_fraction(mark, (stops[1],))
    both = mark_legible_fraction(mark, stops)
    assert dark_only == pytest.approx(1.0), (
        "control: this ink does clear 3:1 against the dark stop on its own"
    )
    assert both == pytest.approx(0.0), (
        f"Scoring must use the WORST stop, not the mean and not just one of them — "
        f"grey {ink} clears the dark stop but is invisible on the light one, so it "
        f"must score 0, got {both}"
    )
    # Order independence. Without this, an implementation that only ever reads
    # plate_hexes[0] passes every assertion above (the hard stop happens to be
    # listed first), and would then wave through any plate whose difficult colour
    # is the SECOND one — which is every plate in this file, since the gradients
    # are written top-stop-first and the hard colour depends on the mark.
    reversed_stops = mark_legible_fraction(mark, tuple(reversed(stops)))
    assert reversed_stops == pytest.approx(both), (
        f"The score must not depend on the ORDER the plate colours are listed in: "
        f"{stops} scored {both}, reversed scored {reversed_stops} — the "
        f"implementation is reading only one stop"
    )


def test_unmeasurable_mark_returns_none_never_zero():
    """"Unknown" and "illegible" must not collapse into one value.

    A caller that reads an undecodable mark as 0.0 would throw a perfectly good
    logo away and draw a monogram; a caller that reads it as 1.0 would ship the
    original blank circle. None forces the caller to make the fail-soft decision
    explicitly, which is what `_wl_chip_plate` does.
    """
    from engine.marketing.chart_render import _WL_CHIP_PAPER
    from engine.marketing.logo_cache import mark_legible_fraction
    stops = (_WL_CHIP_PAPER["top"], _WL_CHIP_PAPER["bot"])
    assert mark_legible_fraction(b"not a png at all", stops) is None
    assert mark_legible_fraction(b"", stops) is None
    # A fully transparent image has no ink to measure — unknown, not illegible.
    assert mark_legible_fraction(_solid_png((255, 255, 255, 0)), stops) is None
    # No plate colours given → unknown, never a silent pass.
    assert mark_legible_fraction(_solid_png((0, 0, 0, 255)), ()) is None


def test_measurement_never_raises_on_hostile_input():
    from engine.marketing.logo_cache import mark_legible_fraction
    for bad in (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, b"\xff" * 200):
        assert mark_legible_fraction(bad, ("#FFFFFF",)) is None


# ---------------------------------------------------------------------------
# The plate decision — the four live-defect tickers, pinned
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ticker", LIVE_DEFECT_TICKERS)
def test_live_defect_tickers_never_land_on_the_paper_plate(ticker: str):
    """REGRESSION PIN for the exact four marks that shipped invisible.

    Each of these is a light/white knockout. On the near-white plate the card used
    to ship, each puts under 55% of its ink above 3:1 — that is the blank circle
    the operator saw. The plate chooser must send every one of them to slate.
    """
    from engine.marketing.chart_render import (
        _WL_CHIP_PAPER, _WL_CHIP_SLATE, _wl_chip_plate,
    )
    from engine.marketing.logo_cache import mark_legible_fraction
    png = _fixture_bytes(ticker)

    on_paper = mark_legible_fraction(
        png, (_WL_CHIP_PAPER["top"], _WL_CHIP_PAPER["bot"])
    )
    assert on_paper is not None and on_paper < 0.55, (
        f"{ticker} is supposed to be a light mark that FAILS the near-white plate "
        f"(that is the shipped defect); it scored {on_paper:.3f}. If the fixture "
        f"changed, this test no longer pins anything."
    )
    plate = _wl_chip_plate(_datauri(png))
    assert plate is not None, f"{ticker} must still draw its real mark, not a monogram"
    assert plate["name"] == _WL_CHIP_SLATE["name"], (
        f"{ticker} rendered invisible on the live card because it landed on the "
        f"'{_WL_CHIP_PAPER['name']}' plate; it must land on "
        f"'{_WL_CHIP_SLATE['name']}', got '{plate['name']}'"
    )


@pytest.mark.parametrize("ticker", DARK_MARK_CONTROLS)
def test_dark_marks_still_land_on_the_paper_plate(ticker: str):
    """THE INVERSE SCAN — the quiet half of the fix.

    "Everything goes on slate" would pass every test above while making the dark
    half of the icon set (JPM, WFC, LIN, DHR, NFLX, and U here) invisible instead.
    These controls make the fix bidirectional rather than a plate swap.
    """
    from engine.marketing.chart_render import _WL_CHIP_PAPER, _wl_chip_plate
    plate = _wl_chip_plate(_datauri(_fixture_bytes(ticker)))
    assert plate is not None and plate["name"] == _WL_CHIP_PAPER["name"], (
        f"{ticker} is a dark mark — it must keep the light plate, got "
        f"{plate and plate['name']}"
    )


@pytest.mark.parametrize("ticker", LIVE_DEFECT_TICKERS + DARK_MARK_CONTROLS)
def test_every_fixture_mark_clears_the_stated_floor_on_its_chosen_plate(ticker: str):
    """THE CONTRACT, computed: >= 55% of the mark's ink above 3:1 on its plate.

    This is the check the whole lane exists to satisfy. It is stated in absolute
    terms rather than "better than before", so a future change that regresses
    legibility while still 'improving' something cannot pass it.
    """
    from engine.marketing.chart_render import (
        _WL_MARK_MIN_LEGIBLE, _WL_MARK_MIN_RATIO, _wl_chip_plate,
    )
    from engine.marketing.logo_cache import mark_legible_fraction
    png = _fixture_bytes(ticker)
    plate = _wl_chip_plate(_datauri(png))
    assert plate is not None, f"{ticker} must resolve to a plate"
    frac = mark_legible_fraction(
        png, (plate["top"], plate["bot"]), min_ratio=_WL_MARK_MIN_RATIO
    )
    assert frac is not None and frac >= _WL_MARK_MIN_LEGIBLE, (
        f"{ticker} on the '{plate['name']}' plate: only {frac:.1%} of its ink "
        f"clears {_WL_MARK_MIN_RATIO}:1, below the {_WL_MARK_MIN_LEGIBLE:.0%} floor"
    )


def test_plate_choice_is_deterministic():
    """The card documents itself as deterministic; the plate must not break that."""
    from engine.marketing.chart_render import _wl_chip_plate
    uri = _datauri(_fixture_bytes("COHR"))
    assert _wl_chip_plate(uri) is _wl_chip_plate(uri)


def test_unmeasurable_mark_defaults_to_slate_not_paper():
    """Fail-soft DIRECTION is load-bearing, not arbitrary.

    When a mark cannot be measured (Pillow absent, undecodable bytes) the chooser
    still has to put it somewhere. It must not be able to land on the near-white
    plate: that is the plate where this source set's most common mark — the pure
    white knockout — renders at 1.00:1, i.e. completely invisible. An unmeasured
    guess should never be able to reproduce the shipped defect.
    """
    from engine.marketing.chart_render import _WL_CHIP_SLATE, _wl_chip_plate
    for junk in ("data:image/png;base64,AAAA", "", "not-a-uri", "data:image/png;xx"):
        plate = _wl_chip_plate(junk)
        assert plate is not None and plate["name"] == _WL_CHIP_SLATE["name"], (
            f"Unmeasurable mark {junk!r} must fall back to slate, got "
            f"{plate and plate['name']}"
        )


def test_mark_legible_on_neither_plate_falls_back_to_monogram():
    """A mark that no plate can save must degrade to the monogram, not to a hole.

    Half pure-white / half pure-black ink: on paper only the black half reads, on
    slate only the white half, so neither plate clears the 55% floor. This is the
    only shape that can defeat both plates (any UNIFORM luminance clears one of
    them by construction), and it is the case the monogram exists for.
    """
    from engine.marketing.chart_render import _wl_chip_plate
    n = 32
    px = [(255, 255, 255, 255)] * (n * n // 2) + [(0, 0, 0, 255)] * (n * n // 2)
    plate = _wl_chip_plate(_datauri(_png(px, (n, n))))
    assert plate is None, (
        "A half-white/half-black mark clears neither plate; the chooser must say "
        "so (None) and let the caller draw a monogram"
    )


# ---------------------------------------------------------------------------
# End-to-end — what the rendered card actually contains
# ---------------------------------------------------------------------------

def _rows(tickers: "list[str]") -> list[dict]:
    return [
        {"ticker": t, "name": t.title(), "price": 100.0 + i, "pct_change": 5.0 - i}
        for i, t in enumerate(tickers)
    ]


def _render(monkeypatch, tickers: "list[str]", uri_for) -> str:
    import engine.marketing.chart_render as cr
    monkeypatch.setattr(cr, "load_closes", lambda *a, **k: None)
    monkeypatch.setattr(
        cr, "resolve_color_logo", lambda ticker, root: uri_for(str(ticker).upper())
    )
    return cr.render_watchlist_card("theme", _rows(tickers), logo_root="/x")


def test_white_mark_row_renders_on_slate_never_the_white_disc(monkeypatch):
    """END-TO-END pin on the shipped defect: a white mark must not be drawn on the
    near-white disc anywhere in the emitted SVG."""
    from engine.marketing.chart_render import _WL_CHIP_PAPER, _WL_CHIP_SLATE
    uri = _datauri(_solid_png((255, 255, 255, 255)))
    svg = _render(monkeypatch, ["COHR", "AXON", "RBLX"], lambda t: uri)
    assert f'stop-color="{_WL_CHIP_SLATE["top"]}"' in svg, "slate plate not emitted"
    assert f'stop-color="{_WL_CHIP_PAPER["top"]}"' not in svg, (
        "A pure-white mark was mounted on the near-white plate — this is exactly "
        "the blank circle that shipped on 2026-08-03"
    )
    assert "<image" in svg, "the real mark must still be drawn"
    assert "wlmono_" not in svg, "a legible mark must not be downgraded to a monogram"


def test_dark_mark_row_renders_on_paper(monkeypatch):
    """Inverse scan at the render level."""
    from engine.marketing.chart_render import _WL_CHIP_PAPER, _WL_CHIP_SLATE
    uri = _datauri(_solid_png((10, 12, 18, 255)))
    svg = _render(monkeypatch, ["JPM", "WFC"], lambda t: uri)
    assert f'stop-color="{_WL_CHIP_PAPER["top"]}"' in svg, "paper plate not emitted"
    assert f'stop-color="{_WL_CHIP_SLATE["top"]}"' not in svg, (
        "A near-black mark was mounted on the slate plate — the mirror defect"
    )


def test_one_card_may_carry_both_finishes(monkeypatch):
    """The two plates are a system, not a mode: a mixed card emits both."""
    from engine.marketing.chart_render import _WL_CHIP_PAPER, _WL_CHIP_SLATE
    light = _datauri(_solid_png((255, 255, 255, 255)))
    dark = _datauri(_solid_png((10, 12, 18, 255)))
    svg = _render(
        monkeypatch, ["COHR", "JPM"], lambda t: light if t == "COHR" else dark
    )
    assert f'stop-color="{_WL_CHIP_SLATE["top"]}"' in svg
    assert f'stop-color="{_WL_CHIP_PAPER["top"]}"' in svg


def test_unusable_mark_row_draws_a_monogram_never_a_blank_hole(monkeypatch):
    """"A missing or unusable logo must never leave a blank hole where a mark
    should be." The row draws an initial on a house-gradient disc instead."""
    n = 32
    px = [(255, 255, 255, 255)] * (n * n // 2) + [(0, 0, 0, 255)] * (n * n // 2)
    uri = _datauri(_png(px, (n, n)))
    svg = _render(monkeypatch, ["COHR"], lambda t: uri)
    assert "wlmono_" in svg, "unusable mark must fall back to the monogram"
    assert "<image" not in svg, "the unusable mark must not be drawn"
    assert ">C<" in svg, "the monogram initial must be rendered — never an empty disc"


def test_every_row_of_the_live_defect_card_clears_the_floor(monkeypatch):
    """THE ACCEPTANCE CHECK, run against the real card that shipped broken.

    Renders the 2026-08-03 theme_list card from the real brand marks, then reads
    each row's chip gradient back OUT of the emitted SVG and re-measures that row's
    mark against the stops the SVG actually carries. Nothing is asserted about
    intent — only about what a viewer would see.
    """
    import engine.marketing.chart_render as cr
    from engine.marketing.chart_render import (
        _WL_MARK_MIN_LEGIBLE, _WL_MARK_MIN_RATIO,
    )
    from engine.marketing.logo_cache import mark_legible_fraction

    tickers = LIVE_DEFECT_TICKERS + DARK_MARK_CONTROLS
    marks = {t: _fixture_bytes(t) for t in tickers}
    svg = _render(monkeypatch, tickers, lambda t: _datauri(marks[t]))

    # Row i's chip gradient is id="wlavg_<uid>r<i>"; rows are sorted by |pct| desc,
    # which _rows() already emits in descending order, so row index == list index.
    grads: dict[int, tuple[str, str]] = {}
    for idx, top, bot in re.findall(
        r'<linearGradient id="wlavg_\d+r(\d+)"[^>]*>'
        r'<stop offset="0" stop-color="(#[0-9A-Fa-f]{6})"/>'
        r'<stop offset="1" stop-color="(#[0-9A-Fa-f]{6})"/>',
        svg,
    ):
        grads[int(idx)] = (top, bot)

    assert len(grads) == len(tickers), (
        f"Expected one avatar chip per row, found {len(grads)} for {len(tickers)} rows"
    )

    report = []
    for i, ticker in enumerate(tickers):
        top, bot = grads[i]
        frac = mark_legible_fraction(
            marks[ticker], (top, bot), min_ratio=_WL_MARK_MIN_RATIO
        )
        report.append(f"{ticker}: plate {top}/{bot} → {frac:.1%} of ink ≥ 3:1")
        assert frac is not None and frac >= _WL_MARK_MIN_LEGIBLE, (
            f"Row {i} ({ticker}) is not legible on the plate the SVG actually "
            f"draws: {frac if frac is None else format(frac, '.1%')} of its ink "
            f"clears {_WL_MARK_MIN_RATIO}:1, floor is {_WL_MARK_MIN_LEGIBLE:.0%}. "
            + " | ".join(report)
        )
