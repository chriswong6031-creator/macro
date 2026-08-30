"""Shared Prophet-card `added_date` / `board_since` slot.

Distinct from legacy `date` / `.pv-dt`. Candidate age is labelled EN/ZH metadata
in `.pv-added`. Null or malformed input omits the chip; there is no fallback.
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
PARTIAL = TEMPLATES / "_prophet_card.html.j2"

_SOURCE = PARTIAL.read_text(encoding="utf-8")
_CLEAN_SOURCE = re.sub(r"\{#.*?#\}", "", _SOURCE, flags=re.DOTALL)
_STYLE = re.search(r"<style>(.*?)</style>", _CLEAN_SOURCE, flags=re.DOTALL)
assert _STYLE, "pv_css() no longer emits a style block"
CSS = _STYLE.group(1)

TIP_EN = (
    "On the Prophet board continuously since this date. "
    "If the name leaves and later returns, this date resets."
)


def _render_card(**overrides) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(("html", "j2")),
    )
    wrapper = env.from_string(
        "{% import '_prophet_card.html.j2' as pv %}{{ pv.pv_card(cx) }}"
    )
    cx = {
        "href": "stock.html#NEAR",
        "tk": "NEAR",
        "sym": "NEAR",
        "mkt": "us",
        "price_txt": "$94.36",
        "name": "Near Corp",
        "sec": "Technology",
        "verb": "near",
        "edge": 97,
        "stage": 3,
        "zone_kind": "active",
        "zone_lo": "$92.43",
        "zone_hi": "$94.10",
        "date": None,
    }
    cx.update(overrides)
    return wrapper.render(cx=cx)


def test_added_date_renders_labelled_en_and_zh():
    html = _render_card(added_date="2026-08-24")
    assert 'class="pv-added"' in html
    assert 'data-added="2026-08-24"' in html
    assert f'data-tip-en="{TIP_EN}"' in html
    assert "data-tip-zh=" in html
    assert 'title="' not in html.split('class="pv-added"', 1)[1][:400]
    assert ">Added Aug 24<" in html or ">Added Aug 24</span>" in html
    assert "入榜 08-24" in html
    assert 'class="pv-dt"' not in html


def test_board_since_alias_is_accepted():
    html = _render_card(board_since="2026-08-04")
    assert 'data-added="2026-08-04"' in html
    assert "Added Aug 4" in html
    assert "入榜 08-04" in html


def test_legacy_date_slot_unchanged_when_added_date_absent():
    html = _render_card(date="2026-08-07")
    assert 'class="pv-dt"' in html
    assert "Aug 7" in html
    assert "08-07" in html
    assert 'class="pv-added"' not in html
    assert "Added" not in html


def test_legacy_date_and_added_date_can_coexist_without_redefining_date():
    html = _render_card(date="2026-08-07", added_date="2026-08-24")
    assert 'class="pv-dt"' in html
    assert 'class="pv-added"' in html
    assert "Aug 7" in html
    assert "Added Aug 24" in html


def test_null_added_date_omits_chip():
    html = _render_card(added_date=None, board_since=None)
    assert 'class="pv-added"' not in html
    assert "Added" not in html
    assert "入榜" not in html


def test_malformed_added_date_omits_chip_no_fallback():
    for bad in ("2026-8-24", "Aug 24", "20260824", "today", "2026-08-21T00:00:00"):
        html = _render_card(added_date=bad, date=None)
        assert 'class="pv-added"' not in html, bad
        assert "Added" not in html, bad


def test_added_chip_does_not_use_signal_asof_as_fallback():
    html = _render_card(added_date=None, date=None)
    assert "Aug 21" not in html
    assert "08-21" not in html


def test_added_css_is_quiet_metadata_and_does_not_grow_the_zone_row():
    assert ".pv-added{" in CSS
    rule = CSS.split(".pv-added{", 1)[1].split("}", 1)[0]
    assert "flex:none" in rule
    assert "margin-left:auto" in rule
    assert "var(--muted)" in rule
    zn = CSS.split(".pv-zn{", 1)[1].split("}", 1)[0]
    assert "white-space:nowrap" in zn
    assert "overflow:hidden" in zn
