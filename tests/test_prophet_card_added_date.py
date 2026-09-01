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
