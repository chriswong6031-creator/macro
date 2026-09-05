"""RED-before-GREEN tests for the pv_card `added_date` chip.

Renders the real Jinja macro (same harness as tests/test_prophet_card_live_change.py)
and pins: the strict-10-char-ISO gate, the absence of any placeholder when null, the
EN/ZH labels, the tooltip attributes, and that legacy `date` callers (plan cards) stay
byte-unchanged — `added_date` is a wholly separate slot from `date`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
PARTIAL = TEMPLATES / "_prophet_card.html.j2"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(("html", "j2")),
    )


def _render_card(**overrides) -> str:
    cx = {
        "href": "stock.html#NEAR", "tk": "NEAR", "mkt": "us",
        "price_txt": "$94.36", "name": "Near Corp", "sec": "Technology",
        "verb": "near", "edge": 97, "stage": 3, "zone_kind": "active",
        "zone_lo": "$92.43", "date": None,
    }
    cx.update(overrides)
    wrapper = _env().from_string(
        "{% import '_prophet_card.html.j2' as pv %}{{ pv.pv_card(cx) }}"
    )
    return wrapper.render(cx=cx)


def test_valid_iso_added_date_renders_a_chip():
    html = _render_card(added_date="2026-07-03")
    assert "pv-added" in html
    assert 'data-added="2026-07-03"' in html
    assert "Added Jul 3" in html
    assert "入榜 07-03" in html


def test_none_added_date_renders_no_chip_and_no_placeholder():
    html = _render_card(added_date=None)
    assert "pv-added" not in html
    assert "Added —" not in html
    assert "入榜 —" not in html


def test_missing_added_date_key_renders_no_chip():
    html = _render_card()
    assert "pv-added" not in html


@pytest.mark.parametrize("bad", ["2026-07-3", "26-07-03", "not-a-date", "", "2026/07/03", "2026-07-03T00:00:00"])
def test_non_strict_iso_added_date_renders_no_chip(bad):
    html = _render_card(added_date=bad)
    assert "pv-added" not in html


def test_added_date_chip_carries_tooltip_attrs_never_translated_title():
    html = _render_card(added_date="2026-07-03")
    assert "data-tip-en=" in html
    assert "data-tip-zh=" in html
    # Extract the pv-added span and confirm it carries no plain title= attribute
    # (house law: no translated text in title=).
    m = re.search(r'<span class="pv-added"[^>]*>', html)
    assert m, "pv-added span not found"
    assert "title=" not in m.group(0)


def test_legacy_date_slot_still_renders_independently_of_added_date():
    html = _render_card(date="2026-06-01", added_date="2026-07-03")
    assert "pv-dt" in html
    assert "pv-added" in html
    # both chips independently present, distinct classes
    assert re.search(r'<span class="pv-dt">', html)
    assert re.search(r'<span class="pv-added"', html)


def test_plan_cards_partial_keeps_plan_asof_and_gains_no_added_date():
    src = (TEMPLATES / "_us_prophet_plan_cards.html.j2").read_text(encoding="utf-8")
    assert "'date': p.get('plan_asof') or p.get('recorded_at')" in src
    assert "added_date" not in src


def _pv_css() -> str:
    src = PARTIAL.read_text(encoding="utf-8")
    mod = _env().from_string(src).module
    return str(mod.pv_css())


def _rule(css: str, cls: str, block: str | None = None) -> str:
    """Body of the FIRST `.<cls>{...}` rule in `css` (or in `block`)."""
    hay = block if block is not None else css
    m = re.search(r"(?<![.\w-])\." + cls + r"\{([^}]*)\}", hay)
    assert m, f".{cls} rule not found"
    return m.group(1)


def test_the_zone_shelf_folds_so_the_added_chip_can_never_truncate():
    """2026-09-02 (Chairman visibility report). The zone shelf is a two-end
    table row whose right end is provenance. It used to be a single
    unwrappable line in which the metadata chip was the only shrinkable
    child, so on a dense grid the chip did not yield space — it DISSOLVED.
    Measured on the live US board at its 2-up narrow grid (154px cards):
    `.pv-added` rendered at 5px EN ("Added A…" → nothing) and 18–29px ZH
    ("入.."), while `.pv-zn` itself overflowed and hard-clipped the zone
    price on the widest card.

    The law now is: the PRICE keeps first claim on line one, and the chip
    either renders in FULL or drops to its own line. It has no truncated
    state left. Three declarations carry that and all three are load-bearing.
    """
    css = _pv_css()

    # 1. the shelf may wrap — this is the whole mechanism
    zn = _rule(css, "pv-zn")
    assert "flex-wrap:wrap" in zn, (
        ".pv-zn must wrap — without it the chip has nowhere to fold to and "
        "the row goes back to truncating the metadata (or clipping the price)")
    assert re.search(r"gap:\d", zn), ".pv-zn must keep an explicit row/column gap pair"

    # 2. BOTH zone-value variants are unshrinkable-but-self-bounded, so the
    #    metadata always yields first and neither value can be crowded out.
    #    (F1 hardened .pv-znr only; .pv-znm was the value path it missed, and
    #    with the chip no longer shrinkable it would have become the sole
    #    absorber of the squeeze — clipping a stance sentence to protect a date.)
    for cls in ("pv-znr", "pv-znm"):
        body = _rule(css, cls)
        assert "flex:none" in body, f".{cls} must never shrink for metadata"
        assert "min-width:0" not in body, (
            f".{cls} must not carry min-width:0 — that reintroduces flex-shrink "
            "and lets the chip crowd the value out again")
        assert "max-width:100%" in body
        assert "overflow:hidden" in body
        assert "text-overflow:ellipsis" in body  # bounded self-degradation, never a hard clip

    # 3. the chip: never shrinks, and has NO truncated state to render
    added = _rule(css, "pv-added")
    assert "flex:0 0 auto" in added, ".pv-added must not shrink — it folds instead"
    assert "margin-left:auto" in added, ".pv-added stays hard against the right edge"
    assert "min-width:0" not in added
    # The two halves of one decision: a flex item whose overflow is not
    # `visible` resolves min-width:auto to 0, so re-adding overflow here
    # would silently defeat flex:0 0 auto and collapse the chip to 5px again.
    assert "overflow" not in added, (
        ".pv-added must carry NO overflow/text-overflow: with a non-visible "
        "overflow its automatic minimum size collapses to 0 and the fold dies "
        "silently — the chip would truncate again instead of wrapping")
    assert "ellipsis" not in added


def test_the_legacy_plan_card_date_chip_is_untouched_by_the_fold():
    """`.pv-dt` is the separate legacy per-row PLAN-card date (see the
    partial's header). R5 deliberately kept it out of this packet's scope and
    that still holds: it keeps min-width:0 + ellipsis, so it shrinks to
    nothing before the shelf ever folds and plan cards keep their prior
    geometry exactly. Only `.pv-added` opts into the fold."""
    css = _pv_css()
    dt = _rule(css, "pv-dt")
    assert "flex:0 1 auto" in dt
    assert "min-width:0" in dt
    assert "overflow:hidden" in dt
    assert "text-overflow:ellipsis" in dt


def test_the_narrow_viewport_truncation_cap_is_gone():
    """The ≤680px `.pv-added{max-width:32%}` cap enforced the right priority
    (price first) with the wrong verb: at the 2-up narrow grid it is ~42px
    against a 66px chip, i.e. it GUARANTEED a truncated date on every phone
    card carrying one. The fold enforces the same priority without ever
    rendering a partial date, so the cap is removed rather than retuned —
    on the folded line the chip has the whole row and a cap could only
    re-impose the defect. `.pv-dt` stays uncapped here, exactly as R5 left it."""
    css = _pv_css()
    narrow = css[css.index("@media (max-width:680px)"):]
    assert "max-width:32%" not in narrow, (
        "the truncation cap must not come back — the chip folds, it does not shrink")
    assert not re.search(r"(?<![.\w-])\.pv-added\{", narrow), (
        ".pv-added must carry no narrow-viewport rule at all")
    assert not re.search(r"(?<![.\w-])\.pv-dt\{", narrow)
    assert not re.search(r"\.pv-dt\s*,\s*\.pv-added\{", narrow)
    assert not re.search(r"\.pv-added\s*,\s*\.pv-dt\{", narrow)
