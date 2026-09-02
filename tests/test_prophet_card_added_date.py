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


def test_zone_value_never_shrinks_the_added_and_date_chips_do():
    # F1 (2026-09-01 repair round): the buy-zone price (.pv-znr) must never
    # CROWD-OUT-clip because of the .pv-dt/.pv-added metadata chips sharing
    # the same flex row — .pv-znr is pinned flex:none (renders at full
    # content width, never shrunk by its siblings), while .pv-dt/.pv-added
    # are the ones that shrink + ellipsize under pressure. This is the
    # inverse of the pre-fix rule, where .pv-znr was the only shrinkable
    # child and absorbed 100% of the squeeze from the un-shrinkable metadata
    # chips.
    #
    # R4 (round 3 repair): flex:none alone has no ceiling of its own, so a
    # pathologically long zone string could still overflow the row and get
    # hard-clipped by .pv-zn's own overflow:hidden with no ellipsis — an
    # UNSIGNALLED clip, not the crowd-out F1 fixed but a different failure
    # mode. .pv-znr now carries its OWN bounded overflow (max-width:100%,
    # overflow:hidden, text-overflow:ellipsis) so that edge case degrades
    # visibly instead. min-width:0 is still deliberately absent — that
    # would reintroduce flex-shrink and let the chips crowd the price out
    # again, which is exactly what F1 fixed.
    css = _pv_css()
    znr_rule = re.search(r"\.pv-znr\{([^}]*)\}", css)
    assert znr_rule, ".pv-znr rule not found in pv_css()"
    znr_body = znr_rule.group(1)
    assert "flex:none" in znr_body
    assert "min-width:0" not in znr_body  # no shrink -> chips still yield first
    assert "max-width:100%" in znr_body
    assert "overflow:hidden" in znr_body
    assert "text-overflow:ellipsis" in znr_body  # bounded self-degradation, not a hard clip

    for cls in ("pv-dt", "pv-added"):
        rule = re.search(r"\." + cls + r"\{([^}]*)\}", css)
        assert rule, f".{cls} rule not found in pv_css()"
        body = rule.group(1)
        assert "flex:none" not in body, f".{cls} must not be flex:none (must be able to shrink)"
        assert "min-width:0" in body
        assert "overflow:hidden" in body
        assert "text-overflow:ellipsis" in body


def test_narrow_viewport_caps_added_chip_width_so_zone_gets_room():
    # R5 (round 3 repair): the ≤680px max-width:32% cap is scoped to
    # `.pv-added` ONLY. `.pv-dt` is the separate legacy per-row date chip
    # used by PLAN cards (a non-chip surface this program's evidence matrix
    # does not shoot) and must keep its PRIOR narrow-viewport behavior — no
    # extra cap beyond the shared shrink+ellipsize base rule (checked above).
    # This replaces test_narrow_viewport_caps_metadata_chip_width_so_zone_
    # gets_room, which pinned the (since-corrected) combined-selector cap.
    css = _pv_css()
    narrow_block = css[css.index("@media (max-width:680px)"):]
    assert re.search(r"(?<![.\w-])\.pv-added\{[^}]*max-width:32%", narrow_block), (
        ".pv-added must carry the max-width:32% narrow-viewport cap")
    # .pv-dt must NOT share that selector/cap anywhere in the narrow block.
    assert not re.search(r"\.pv-dt\s*,\s*\.pv-added\{", narrow_block)
    assert not re.search(r"\.pv-added\s*,\s*\.pv-dt\{", narrow_block)
    dt_rule = re.search(r"(?<![.\w-])\.pv-dt\{([^}]*)\}", narrow_block)
    assert not dt_rule, ".pv-dt must not gain its own narrow-viewport rule either"
