"""Geometry pins for the breaking radar card (W4g, operator 2026-08-02).

The operator's verdict on the one post that shipped that day: *"the illustration
needs fixing (text too small for both mobile and web, needs to be much larger
and digestible, too much whitespace too; and the title header is too long and
gets cut off)"*.

Before this suite existed, ``tests/test_marketing_breaking_card.py`` asserted
structure, escaping and presence — and NOT ONE geometry value.  So the card
could (and did) ship with:

* a 15.5px summary carrying the primary information — ~5.3 CSS px once X
  renders the 2000×1120 PNG in a ~340 CSS px mobile media well;
* a headline size table that bottomed out at ``>150 chars → 26px/56ch/3 lines``,
  i.e. ~168 characters displayed and everything past that hard-clipped with an
  ellipsis.  The live 2026-08-02 Iran item's ``headline`` is the entire Truth
  Social post — 814 characters — so the card cut mid-sentence at "…World War II…"
  and the actual news (the attack was CANCELLED) never appeared in the hero.

Every test here fails on the pre-fix renderer.  The three load-bearing ones and
the mutation that catches each:

===============================  ==========================================
test                             mutation it catches
===============================  ==========================================
no_ellipsis_in_hero              restore the wrap-then-clip ellipsis, or
(the real 814-char fixture)      remove the derive_card_headline() bound
body_font_size_floor             drop the summary back to any size < 26
headline_reconstructs_verbatim   any silent truncation anywhere in the path
===============================  ==========================================

The fixture is the REAL artifact, read from ``data/marketing/outbox/items.jsonl``
when present and pinned verbatim in this file otherwise, so the suite still
guards on a fresh checkout with no data tree.

Run: python3 -m pytest tests/test_marketing_breaking_card_geometry.py -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine.marketing.chart_render import (
    _BREAK_BODY_MIN,
    _BREAK_HEADLINE_MAX_CHARS,
    derive_card_headline,
    render_breaking_card,
)

ROOT = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# The real fixture — the Truth Social relay that shipped on 2026-08-02
# ─────────────────────────────────────────────────────────────────────────────

_IRAN_ITEM_ID = "ob-2026-08-02-86f9603bd3"

# Verbatim copy of that item's `headline` (814 chars) — the renderer's actual
# input on the night the operator complained.
IRAN_HEADLINE = (
    "The U.S.A. is locked and loaded and ready to go against the Islamic "
    "Republic of Iran, at levels of Military Terror, Strength, and Power not "
    "seen since World War II. Despite this, we have just been asked by Iran, "
    "and other Middle Eastern Countries, to hold off any attack in that the "
    "perimeters of a deal has been agreed to. This would include the "
    "Immediate, Complete, and Total OPENING OF THE HORMUZ STRAIT, and an end "
    "to Iran’s nuclear threat. Based on this request, I have agreed, for "
    "the future benefit of the WORLD and, likewise, the survival of a "
    "successful and prosperous Iran, to cancel the attack, subject to being "
    "able to rapidly make a DEAL. The Country of Israel joins me in this "
    "commitment. Get to work, everybody, and get it DONE. Thank you for your "
    "attention to this matter! President DONALD J. TRUMP"
)

IRAN_SUMMARY = (
    "The U.S. has agreed to cancel a planned attack on Iran after being asked "
    "to hold off while deal parameters are negotiated, which would include "
    "opening the Hormuz Strait and ending Iran's nuclear threat. Israel joins "
    "the commitment to pursue a deal. -- on Truth Social"
)


def _live_iran_headline() -> str:
    """The live artifact when the data tree is present; the pinned copy otherwise."""
    items = ROOT / "data" / "marketing" / "outbox" / "items.jsonl"
    if not items.exists():
        return IRAN_HEADLINE
    try:
        for line in items.read_text(encoding="utf-8").splitlines():
            if _IRAN_ITEM_ID not in line:
                continue
            row = json.loads(line)
            if row.get("id") == _IRAN_ITEM_ID and row.get("headline"):
                return str(row["headline"])
    except Exception:  # noqa: BLE001 — a malformed data tree must not fail the pin
        pass
    return IRAN_HEADLINE


# The hero's own signature is its negative tracking — the one attribute no
# other 800-weight text on the card carries. The old discriminator (excluding
# the footer URL by its fixed 15px size) died with the 1080 square card: the
# brand bar now scales with band_h, so the URL renders at ~27px and a size
# filter cannot tell it from a stepped-down hero line.
_HERO_RE = re.compile(
    r'font-size="([0-9.]+)" font-weight="800" font-family="sans-serif" '
    r'letter-spacing="-0.015em">([^<]*)</text>'
)


def _hero_lines(svg: str) -> list[str]:
    """The headline <text> lines, in render order."""
    return [m.group(2) for m in _HERO_RE.finditer(svg)]


def _hero_size(svg: str) -> float:
    sizes = [float(m.group(1)) for m in _HERO_RE.finditer(svg)]
    assert sizes, "no headline text found"
    return sizes[0]


def _body_lines(svg: str) -> list[str]:
    return re.findall(r'fill="#C8D4EA" font-size="[0-9.]+"[^>]*>([^<]*)</text>', svg)


def _body_size(svg: str) -> float:
    sizes = [float(s) for s in re.findall(r'fill="#C8D4EA" font-size="([0-9.]+)"', svg)]
    assert sizes, "no summary text found — the card rendered no body"
    return sizes[0]


def _unescape(s: str) -> str:
    return (s.replace("&#39;", "'").replace("&quot;", '"')
             .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. The headline is never truncated by ellipsis — at ANY length
# ─────────────────────────────────────────────────────────────────────────────

def test_no_ellipsis_in_hero_for_the_real_814_char_iran_headline():
    """THE regression. Pre-fix this rendered '…World War II…' and stopped."""
    headline = _live_iran_headline()
    assert len(headline) > 600, "fixture must stay a genuinely runaway headline"
    svg = render_breaking_card(
        headline, "Truth Social (via trumpstruth.org)", "aggregator",
        "2026-08-02T03:48:20Z", summary=IRAN_SUMMARY, event_class="geopolitical",
    )
    hero = " ".join(_hero_lines(svg))
    assert "…" not in hero, f"headline was ellipsized: {hero!r}"
    assert "..." not in hero


@pytest.mark.parametrize("n", [200, 400, 814, 1140, 3000])
def test_no_ellipsis_in_hero_at_any_length(n):
    """A headline of ANY length renders without truncation-by-ellipsis."""
    sentence = "The committee raised its forecast for the year ahead by a wide margin. "
    headline = (sentence * (n // len(sentence) + 2))[:n]
    svg = render_breaking_card(headline, "Reuters", "wire", "2026-07-19T14:32:00Z")
    hero = " ".join(_hero_lines(svg))
    assert "…" not in hero, f"n={n} ellipsized: {hero!r}"


def test_hero_ends_on_a_sentence_not_mid_clause():
    """Compression is sentence-bounded: the hero is a complete thought."""
    hero = " ".join(_hero_lines(render_breaking_card(
        _live_iran_headline(), "Truth Social", "aggregator", "2026-08-02T03:48:20Z",
    )))
    assert hero.rstrip().endswith("World War II."), hero


def test_hero_text_is_a_verbatim_prefix_of_the_source():
    """Relay, never editorialize: nothing is reworded and no case is changed."""
    headline = _live_iran_headline()
    hero = _unescape(" ".join(_hero_lines(render_breaking_card(
        headline, "Truth Social", "aggregator", "2026-08-02T03:48:20Z",
    )))).strip()
    normalized_source = " ".join(headline.split())
    assert normalized_source.startswith(hero), (
        "the card hero must be the source's own leading words, unmodified"
    )


def test_short_headline_reconstructs_word_for_word():
    """A headline that fits is never compressed at all."""
    hl = "Fed holds rates steady at 4.25%-4.50%, signals one cut this year"
    svg = render_breaking_card(hl, "Federal Reserve", "official", "2026-07-19T18:00:00Z")
    assert _unescape(" ".join(_hero_lines(svg))).strip() == hl


# ─────────────────────────────────────────────────────────────────────────────
# 2. Body legibility floor — the operator's "text too small"
# ─────────────────────────────────────────────────────────────────────────────

def test_body_font_size_floor():
    """The summary carries the primary information; 15.5px was ~5.3 CSS px on a phone.

    26 design px is the floor: on a 340 CSS px mobile media well that is ~8.8
    CSS px, and ~9.4 on a 360px well. Anything under it is not readable in a
    timeline and this test exists to stop it coming back.
    """
    assert _BREAK_BODY_MIN >= 26.0
    svg = render_breaking_card(
        _live_iran_headline(), "Truth Social", "aggregator", "2026-08-02T03:48:20Z",
        summary=IRAN_SUMMARY,
    )
    assert _body_size(svg) >= _BREAK_BODY_MIN


@pytest.mark.parametrize("summary_len", [40, 120, 200, 264, 400, 900])
def test_body_font_size_floor_holds_for_every_summary_length(summary_len):
    sentence = "Core inflation held at three tenths on the month per the release. "
    summary = (sentence * (summary_len // len(sentence) + 2))[:summary_len]
    svg = render_breaking_card(
        _live_iran_headline(), "Reuters", "wire", "2026-07-19T14:32:00Z",
        summary=summary,
        tickers=[{"ticker": "SPY", "price": 512.3, "pct": -0.8}],
    )
    assert _body_size(svg) >= _BREAK_BODY_MIN


def test_body_is_never_smaller_than_the_metadata_around_it():
    """Hierarchy inversion guard: the body used to be smaller than the timestamp."""
    svg = render_breaking_card(
        "Fed holds rates steady", "Federal Reserve", "official",
        "2026-07-19T18:00:00Z", summary="The FOMC left the target range unchanged.",
    )
    body = _body_size(svg)
    meta = [float(s) for s in re.findall(r'fill="#6b7a99" font-size="([0-9.]+)"', svg)]
    assert meta, "no metadata text found"
    assert body > max(meta), f"body {body} <= metadata {max(meta)}"


def test_headline_outranks_body():
    svg = render_breaking_card(
        "Fed holds rates steady at 4.25%-4.50%", "Federal Reserve", "official",
        "2026-07-19T18:00:00Z", summary="The FOMC left the target range unchanged.",
    )
    assert _hero_size(svg) > _body_size(svg)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Whitespace — the block fills the card
# ─────────────────────────────────────────────────────────────────────────────

def test_sparse_card_fills_the_column_instead_of_centring_a_void():
    """The SPARSE card is where the old capped centring showed as a dead field.

    A six-word headline plus one sentence leaves ~175 design px of slack on a
    1000x560 canvas. The pre-fix renderer pushed the whole block down by
    ``min(slack/2, 56)`` and left the remainder as empty ground under the
    summary. The fix answers slack with LARGER TYPE plus a widened
    headline->summary gap, so the last body line reaches materially further
    down the column. (This is the case that discriminates: when slack is small,
    centring and top-anchoring land within ~2% of each other and prove nothing.)
    """
    svg = render_breaking_card(
        "Fed holds rates steady", "Federal Reserve", "official",
        "2026-07-19T18:00:00Z",
        summary="The FOMC left the target range unchanged.",
    )
    body_ys = [float(m.group(1)) for m in re.finditer(
        r'<text x="[0-9.]+" y="([0-9.]+)" fill="#C8D4EA"', svg)]
    assert body_ys, "no body baselines found"
    # The 1080 square card's copy box: below the masthead+rule+eyebrow
    # chrome (253) and above the provenance-slug/footer reservation (826).
    box_top, box_bottom = 253.0, 826.0
    reach = (max(body_ys) - box_top) / (box_bottom - box_top)
    assert reach >= 0.68, f"content only reaches {reach:.0%} of the text column"
    # And the sparse card must answer its slack with size, not silence.
    assert _hero_size(svg) >= 60.0, f"sparse headline only {_hero_size(svg)}px"
    assert _body_size(svg) >= 34.0, f"sparse body only {_body_size(svg)}px"


def test_dense_card_fills_the_column():
    """The other end: the real 814-char item must reach the bottom of its column."""
    svg = render_breaking_card(
        _live_iran_headline(), "Truth Social", "aggregator",
        "2026-08-02T03:48:20Z", summary=IRAN_SUMMARY,
    )
    body_ys = [float(m.group(1)) for m in re.finditer(
        r'<text x="[0-9.]+" y="([0-9.]+)" fill="#C8D4EA"', svg)]
    # The 1080 square card's copy box: below the masthead+rule+eyebrow
    # chrome (253) and above the provenance-slug/footer reservation (826).
    box_top, box_bottom = 253.0, 826.0
    reach = (max(body_ys) - box_top) / (box_bottom - box_top)
    assert reach >= 0.90, f"content only reaches {reach:.0%} of the text column"


_WIDE_HEADLINE = (
    "MASSIVE WORLDWIDE MANUFACTURING SLOWDOWN HAMMERS COMMODITY MARKETS AS "
    "WAREHOUSE MOMENTUM COLLAPSES ACROSS MAJOR ECONOMIES"
)
_WIDE_SUMMARY = (
    "WORLDWIDE MANUFACTURING MOMENTUM WEAKENED ACROSS MAJOR ECONOMIES AND "
    "WAREHOUSE VOLUMES COLLAPSED, ACCORDING TO THE MONTHLY SURVEY."
)


@pytest.mark.parametrize("headline,summary", [
    (_WIDE_HEADLINE, _WIDE_SUMMARY),                       # all-caps: widest glyphs
    ("iiii llll iiii llll " * 6, "iiii llll " * 12),        # narrowest glyphs
    ("U.S. CPI rises 0.4% in June, hotter than the 0.3% forecast", None),
])
def test_no_rendered_line_overflows_its_column(headline, summary):
    """THE property a character-count budget cannot provide.

    Wrapping used to be a raw char count, so the budgets and the font sizes
    drifted apart whenever either moved: 84 chars at 15.5px underset the column
    by ~28%, while the same budget applied to ALL-CAPS text at a larger size
    runs straight off the card. Measuring advance widths is what makes both
    impossible, and this asserts exactly that — every line, both roles.
    """
    from engine.marketing.chart_render import _break_text_w
    svg = render_breaking_card(
        headline, "Reuters", "wire", "2026-07-19T14:32:00Z", summary=summary,
    )
    hero_size = _hero_size(svg)
    for ln in _hero_lines(svg):
        w = _break_text_w(_unescape(ln), hero_size, bold=True, tracking_em=-0.01)
        # 936 = the 1080 column; x1.03 absorbs estimator skew vs _bc_text_w.
        assert w <= 936.0 * 1.03, f"headline line overflows ({w:.0f}px > 964): {ln!r}"
    if summary:
        body_size = _body_size(svg)
        for ln in _body_lines(svg):
            w = _break_text_w(_unescape(ln), body_size)
            assert w <= 906.0 * 1.03, f"body line overflows ({w:.0f}px > 933): {ln!r}"


def test_hero_uses_the_full_text_column_width():
    """The old 30-56 char budgets left ~28% of the column unused at every size."""
    svg = render_breaking_card(
        _live_iran_headline(), "Truth Social", "aggregator", "2026-08-02T03:48:20Z",
        summary=IRAN_SUMMARY,
    )
    from engine.marketing.chart_render import _break_text_w
    size = _hero_size(svg)
    widths = [_break_text_w(_unescape(ln), size, bold=True, tracking_em=-0.01)
              for ln in _hero_lines(svg)]
    # Every line except the last must fill most of the 936px column.
    assert len(widths) >= 2
    assert min(widths[:-1]) >= 936 * 0.80, widths


# ─────────────────────────────────────────────────────────────────────────────
# 4. derive_card_headline — the upstream gate's engine
# ─────────────────────────────────────────────────────────────────────────────

def test_derive_card_headline_bounds_and_never_ellipsizes():
    out = derive_card_headline(IRAN_HEADLINE)
    assert len(out) <= _BREAK_HEADLINE_MAX_CHARS
    assert "…" not in out and not out.endswith("...")
    assert out.endswith("World War II.")


def test_derive_card_headline_leaves_short_text_untouched():
    hl = "Fed holds rates steady at 4.25%-4.50%"
    assert derive_card_headline(hl) == hl


def test_derive_card_headline_does_not_split_on_abbreviations():
    """'The U.S.A. is locked…' must not become a three-word headline."""
    assert derive_card_headline(IRAN_HEADLINE).startswith("The U.S.A. is locked and loaded")


def test_derive_card_headline_never_shouts():
    """F6: sentence-case compression, never ALL-CAPS synthesis."""
    out = derive_card_headline(IRAN_HEADLINE)
    assert out != out.upper()


@pytest.mark.parametrize("bad", [None, "", "   ", "x", "x" * 5000, "。" * 400])
def test_derive_card_headline_hostile_input(bad):
    out = derive_card_headline(bad)
    assert isinstance(out, str)
    assert len(out) <= _BREAK_HEADLINE_MAX_CHARS
    assert "…" not in out


# ─────────────────────────────────────────────────────────────────────────────
# 5. Blast radius — earnings_call_lane calls render_breaking_card directly
# ─────────────────────────────────────────────────────────────────────────────

def test_earnings_call_variant_keeps_the_floor_and_the_eyebrow():
    """earnings_call_lane.py:399 passes eyebrow='EARNINGS CALL' to this function."""
    svg = render_breaking_card(
        "Nvidia guides Q3 revenue to $54B, above the $52.1B consensus, and calls "
        "Blackwell supply 'sold out through 2027'",
        "Earnings call transcript", "aggregator", "2026-08-01T21:05:00Z",
        tickers=None, suppress_cta=False,
        summary="Management said data-centre revenue grew 62% year over year and "
                "that gross margin should hold in the mid-70s.",
        event_class=None, eyebrow="EARNINGS CALL",
    )
    assert "EARNINGS CALL" in svg
    assert _body_size(svg) >= _BREAK_BODY_MIN
    assert "…" not in " ".join(_hero_lines(svg))
    assert "bc-tier-aggregator" in svg


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tier rail — the anti-laundering signature, repeated on the content
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tier,expect_colour", [
    ("official", "#F5A623"),
    ("wire", "#F5A623"),
    ("aggregator", "#6b7a99"),
    ("premium-verified-vip", "#6b7a99"),   # unknown routes cautious, never up
])
def test_summary_rail_is_tier_inked(tier, expect_colour):
    svg = render_breaking_card(
        "Fed holds rates steady", "Some Source", tier, "2026-07-19T18:00:00Z",
        summary="The FOMC left the target range unchanged.",
    )
    rail = re.search(r'<rect [^>]*class="bc-rail bc-rail-([a-z]+)"[^>]*/>', svg)
    assert rail, "summary rail missing"
    rail_tag = re.search(r'<rect [^>]*fill="(#[0-9A-Fa-f]{6})"[^>]*class="bc-rail', svg)
    assert rail_tag and rail_tag.group(1) == expect_colour, svg[:0] or rail_tag


def test_official_rail_is_not_the_chip_ink():
    """The chip's dark ink (#1A1200) on the dark card would be an invisible rail."""
    svg = render_breaking_card(
        "Fed holds rates steady", "Federal Reserve", "official",
        "2026-07-19T18:00:00Z", summary="The FOMC left the target range unchanged.",
    )
    rail = re.search(r'<rect [^>]*fill="(#[0-9A-Fa-f]{6})"[^>]*class="bc-rail', svg)
    assert rail and rail.group(1) != "#1A1200"


# ─────────────────────────────────────────────────────────────────────────────
# 7. The UPSTREAM half — build_breaking_payload's length gate + counted drop
# ─────────────────────────────────────────────────────────────────────────────

def _iran_wire_item() -> dict:
    return {
        "id": _IRAN_ITEM_ID,
        "headline": _live_iran_headline(),
        "body_snippet": IRAN_SUMMARY,
        "source_name": "Truth Social (via trumpstruth.org)",
        "source": "trumpstruth",
        "source_tier": "aggregator",
        "published_at": "2026-08-02T03:48:20Z",
        "url": "https://truthsocial.com/@realDonaldTrump/117023461141824050",
        "event_class": "geopolitical",
        "salience": 31.2,
        "matched": {"tickers": []},
    }


def test_payload_carries_a_bounded_card_headline():
    """A 1,140-char press quote must never arrive at the card as a 'headline'."""
    from engine.marketing.breaking_summary import build_breaking_payload
    p = build_breaking_payload(_iran_wire_item(), {"breaking": {"llm": {"enabled": False}}})
    assert len(p["headline"]) > 600, "raw wire field stays verbatim"
    assert len(p["card_headline"]) <= _BREAK_HEADLINE_MAX_CHARS
    assert "…" not in p["card_headline"]
    assert p["card_headline"].endswith("World War II.")
    # ...and the card rendered from it carries no ellipsis either.
    hero = re.findall(r'font-weight="800"[^>]*>([^<]*)</text>', p["card_svg"])
    assert "…" not in " ".join(hero)


def test_payload_counts_the_drop_and_persists_it():
    """Counted drops only: a silent `continue` is the defect class that hid 12 nights."""
    from engine.marketing.breaking_summary import build_breaking_payload
    p = build_breaking_payload(_iran_wire_item(), {"breaking": {"llm": {"enabled": False}}})
    fit = p["provenance"]["card_fit"]
    assert fit["headline_source_chars"] == len(" ".join(p["headline"].split()))
    assert fit["headline_card_chars"] == len(p["card_headline"])
    assert fit["headline_chars_dropped"] > 0
    assert (fit["headline_source_chars"] - fit["headline_card_chars"]
            == fit["headline_chars_dropped"])


def test_payload_announces_the_compression_as_a_line_start_annotation(capsys):
    """Bare line-start print — never through a logger (CI-guarded, shipped dead 5x)."""
    from engine.marketing.breaking_summary import build_breaking_payload
    build_breaking_payload(_iran_wire_item(), {"breaking": {"llm": {"enabled": False}}})
    out = capsys.readouterr().out
    hits = [ln for ln in out.splitlines()
            if ln.startswith("::warning title=breaking-card-headline-compressed::")]
    assert hits, f"no line-start annotation emitted; stdout was {out!r}"


def test_payload_leaves_a_short_headline_alone_and_counts_zero():
    from engine.marketing.breaking_summary import build_breaking_payload
    item = _iran_wire_item()
    item["headline"] = "Fed holds rates steady at 4.25%-4.50%"
    p = build_breaking_payload(item, {"breaking": {"llm": {"enabled": False}}})
    assert p["card_headline"] == item["headline"]
    assert p["provenance"]["card_fit"]["headline_chars_dropped"] == 0


def test_payload_headline_field_is_untouched_by_the_card_gate():
    """The post-text lane composes from `headline`; this gate must not move it."""
    from engine.marketing.breaking_summary import build_breaking_payload
    item = _iran_wire_item()
    p = build_breaking_payload(item, {"breaking": {"llm": {"enabled": False}}})
    assert p["headline"] == item["headline"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. Determinism (the card is a hashed R2 artifact — bytes must be stable)
# ─────────────────────────────────────────────────────────────────────────────

def test_fitter_is_deterministic():
    args = (_live_iran_headline(), "Truth Social", "aggregator", "2026-08-02T03:48:20Z")
    a = render_breaking_card(*args, summary=IRAN_SUMMARY)
    b = render_breaking_card(*args, summary=IRAN_SUMMARY)
    assert a == b
