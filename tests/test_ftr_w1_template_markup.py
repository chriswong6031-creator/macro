"""Render/parse assertions for FTR W1+W2a template additions.

Guards:
- ftr-shock-banner, ftr-lever-chip, ftr-member-sym-registry divs are present
- lever chip reads framing/framing_zh from fetched JSON (d.framing_zh), NOT hardcoded ZH
- allocation.html.j2 carries the FT-R11 horizon label
- basket_detail.html.j2 uses relative paths (../live/...) for shock_state / policy_lever
- baskets.html.j2 full render with basket_member_syms emits data-sym spans

These are display-tier / de-escalation additions (FT-R2, PS-R3, PS-W2-F, FT-R11).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TMPL_DIR = Path(__file__).parent.parent / "templates"


def _src(name: str) -> str:
    return (TMPL_DIR / name).read_text()


def _parse(name: str) -> None:
    from jinja2 import Environment
    src = _src(name)
    Environment(autoescape=False).parse(src)


def _render_baskets(syms: list[str]) -> str:
    from jinja2 import Environment, FileSystemLoader, Undefined
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False,
                      undefined=Undefined)
    t = env.get_template("baskets.html.j2")
    return t.render(basket_member_syms=syms)


# ── Parse (syntax) guards ──────────────────────────────────────────────────

class TestFtrTemplatesParse:
    def test_baskets_parses(self):
        _parse("baskets.html.j2")

    def test_allocation_parses(self):
        _parse("allocation.html.j2")

    def test_basket_detail_parses(self):
        _parse("basket_detail.html.j2")


# ── Static-source guards (framing + structure) ─────────────────────────────

class TestFtrStaticSource:
    """Check static source strings that can't be overridden by Jinja rendering."""

    @pytest.mark.parametrize("template", [
        "baskets.html.j2", "allocation.html.j2", "basket_detail.html.j2",
    ])
    def test_shock_banner_div_present(self, template):
        assert "ftr-shock-banner" in _src(template)

    @pytest.mark.parametrize("template", [
        "baskets.html.j2", "allocation.html.j2", "basket_detail.html.j2",
    ])
    def test_lever_chip_div_present(self, template):
        assert "ftr-lever-chip" in _src(template)

    @pytest.mark.parametrize("template", [
        "baskets.html.j2", "allocation.html.j2", "basket_detail.html.j2",
    ])
    def test_framing_read_from_json_not_hardcoded(self, template):
        """Lever chip must use d.framing_zh from the fetched JSON, not a hardcoded ZH string."""
        src = _src(template)
        # Must reference framing_zh field from the fetched data
        assert "d.framing_zh" in src, f"{template} must read framing_zh from fetched JSON"
        # Must NOT contain the old hardcoded ZH disclaimer that diverged from policy_lever.json
        assert "更可能出现剧烈隔夜反转的条件" not in src, (
            f"{template}: hardcoded ZH disclaimer removed; use d.framing_zh from JSON"
        )

    def test_basket_detail_uses_relative_paths(self):
        """basket_detail pages live under site/basket/ — must use ../ prefix."""
        src = _src("basket_detail.html.j2")
        assert "../live/shock_state.json" in src
        assert "../policy_lever.json" in src

    def test_allocation_ft_r11_horizon_label(self):
        """FT-R11: allocation page must carry the honest strategic-horizon sub-label."""
        src = _src("allocation.html.j2")
        assert "Strategic horizon" in src
        assert "3" in src and "12m" in src  # "3–12m" range
        assert "deliberately slow" in src

    def test_basket_detail_nb_chg_spans(self):
        """basket_detail must emit nb-chg spans for member live-price wiring."""
        src = _src("basket_detail.html.j2")
        assert "nb-chg" in src

    def test_baskets_member_sym_registry_div(self):
        """baskets.html.j2 must have the hidden registry div for live-quotes scrape."""
        assert "ftr-member-sym-registry" in _src("baskets.html.j2")


# ── Full-render guard for baskets.html.j2 ─────────────────────────────────

class TestFtrBasketsRender:
    """Full Jinja render of baskets.html.j2 with basket_member_syms context."""

    def test_member_sym_spans_emitted(self):
        html = _render_baskets(["AAPL", "NVDA", "MSFT"])
        assert 'data-sym="AAPL"' in html
        assert 'data-sym="NVDA"' in html
        assert 'data-sym="MSFT"' in html

    def test_shock_banner_div_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-shock-banner" in html

    def test_lever_chip_div_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-lever-chip" in html

    def test_framing_zh_ref_in_render(self):
        """The rendered JS must reference d.framing_zh, not a static ZH string."""
        html = _render_baskets(["SPY"])
        assert "d.framing_zh" in html

    def test_no_member_spans_when_syms_empty(self):
        """Registry div must NOT be emitted when basket_member_syms is empty."""
        html = _render_baskets([])
        assert "ftr-member-sym-registry" not in html
