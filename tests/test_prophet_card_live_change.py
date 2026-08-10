"""Live percentage contract for the shared Prophet card.

The live updater replaces ``.nb-px`` textContent, so the percentage must be an
adjacent ``.nb-chg`` node inside the same visual pill.  These tests render the real
Jinja macro and pin the four-board scope plus the language-aware direction tokens.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
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


class _QuoteChildren(HTMLParser):
    """Collect direct child spans of the first rendered ``.pv-quote``."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[set[str]] = []
        self.children: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if self._stack and "pv-quote" in self._stack[-1]:
            self.children.append(values)
        self._stack.append(classes)

    def handle_endtag(self, tag: str) -> None:
        if self._stack:
            self._stack.pop()


def _render_card(*, show_change: bool) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(("html", "j2")),
    )
    wrapper = env.from_string(
        "{% import '_prophet_card.html.j2' as pv %}{{ pv.pv_card(cx) }}"
    )
    return wrapper.render(
        cx={
            "href": "stock.html#NEAR",
            "tk": "NEAR",
            "sym": "NEAR",
            "mkt": "us",
            "price_txt": "$94.36",
            "show_change": show_change,
            "name": "Near Corp",
            "sec": "Technology",
            "verb": "near",
            "edge": 97,
            "stage": 3,
            "zone_kind": "active",
            "zone_lo": "$92.43",
            "date": "2026-08-07",
        }
    )


def _quote_children(html: str) -> list[dict[str, str | None]]:
    parser = _QuoteChildren()
    parser.feed(html)
    return parser.children


def _rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\{([^{}]*)\}", CSS)
    assert match, f"missing CSS rule: {selector}"
    return match.group(1)


def _pv_card_calls(template_name: str) -> list[str]:
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    return re.findall(r"\{\{\s*pv\.pv_card\(\{(.*?)\}\)\s*\}\}", source, flags=re.DOTALL)


def test_live_change_is_a_price_sibling_inside_one_quote_pill() -> None:
    children = _quote_children(_render_card(show_change=True))
    assert len(children) == 2, children
    assert children[0]["class"] == "nb-px pv-px"
    assert children[1]["class"] == "nb-chg pv-chg"
    assert children[0]["data-sym"] == children[1]["data-sym"] == "NEAR"
    assert children[0]["data-mkt"] == children[1]["data-mkt"] == "us"


def test_change_slot_is_opt_in_so_international_stays_unchanged() -> None:
    rendered = _render_card(show_change=False)
    assert 'class="pv-quote"' not in rendered
    assert 'class="nb-chg pv-chg"' not in rendered
    assert re.search(r'<span class="pv-ov pv-ovr">\s*<span class="nb-px pv-px"', rendered)


def test_requested_four_boards_opt_in_and_international_does_not() -> None:
    expected_calls = {
        "dashboard.html.j2": 1,
        "china.html.j2": 2,
        "hk.html.j2": 1,
        "canada.html.j2": 1,
    }
    for template_name, expected_count in expected_calls.items():
        calls = _pv_card_calls(template_name)
        assert len(calls) == expected_count, (template_name, len(calls))
        assert all("'show_change': true" in call for call in calls), template_name

    intl_calls = _pv_card_calls("intl.html.j2")
    assert len(intl_calls) == 1
    assert "show_change" not in intl_calls[0]


def test_price_and_percentage_have_identical_readable_typography() -> None:
    shared = _rule(".pvcard .nb-px.pv-px,.pvcard .nb-chg.pv-chg")
    assert "font-size:10.5px" in shared
    assert "font-weight:700" in shared
    assert "font-variant-numeric:tabular-nums" in shared


def test_direction_colors_use_language_flipping_semantic_inks() -> None:
    up = _rule(".pvcard .pv-quote .pv-chg.up")
    down = _rule(".pvcard .pv-quote .pv-chg.down")
    assert "var(--ink-up,var(--up))" in up
    assert "var(--ink-down,var(--down))" in down
    assert not re.search(r"#[0-9a-fA-F]{3,8}", up + down)


def test_stale_percentage_is_muted_without_shrinking_its_type() -> None:
    stale = _rule(".pvcard .pv-quote .pv-chg.stale")
    assert "color:var(--muted)" in stale
    assert "font-weight:700" in stale
