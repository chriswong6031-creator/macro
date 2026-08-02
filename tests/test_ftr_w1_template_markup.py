"""Render/parse assertions for FTR W1+W2a template additions.

Guards:
- ftr-shock-banner, ftr-lever-chip, ftr-member-sym-registry divs are present
- lever chip reads framing/framing_zh from fetched JSON (d.framing_zh), NOT hardcoded ZH
- allocation.html.j2 carries the FT-R11 horizon label
- basket_detail.html.j2 uses relative paths (../live/...) for shock_state / policy_lever
- sector_central.html.j2 full render with basket_member_syms emits data-sym spans

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
    t = env.get_template("sector_central.html.j2")
    return t.render(basket_member_syms=syms)


# ── Parse (syntax) guards ──────────────────────────────────────────────────

class TestFtrTemplatesParse:
    def test_baskets_parses(self):
        _parse("sector_central.html.j2")

    def test_allocation_parses(self):
        _parse("allocation.html.j2")

    def test_basket_detail_parses(self):
        _parse("basket_detail.html.j2")


# ── Static-source guards (framing + structure) ─────────────────────────────

class TestFtrStaticSource:
    """Check static source strings that can't be overridden by Jinja rendering."""

    @pytest.mark.parametrize("template", [
        "sector_central.html.j2", "allocation.html.j2", "basket_detail.html.j2",
    ])
    def test_shock_banner_div_present(self, template):
        assert "ftr-shock-banner" in _src(template)

    @pytest.mark.parametrize("template", [
        "sector_central.html.j2", "allocation.html.j2", "basket_detail.html.j2",
    ])
    def test_lever_chip_div_present(self, template):
        assert "ftr-lever-chip" in _src(template)

    @pytest.mark.parametrize("template", [
        "sector_central.html.j2", "allocation.html.j2", "basket_detail.html.j2",
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
        """FT-R11: allocation page must carry the honest strategic-horizon sub-label.

        The label ships in plain words, not the wording this test was born with.
        #2635 ported the original copy — "Strategic horizon (3–12m): skip-month
        momentum by construction — this view is deliberately slow." — to the
        current sentence under docs/DESIGN_DOCTRINE.md Law 2 (no unexplained
        construction jargon on Tier 1: "skip-month momentum by construction" is
        exactly the banned "comparative construction that needs a manual") and
        Law 3 (a Tier-1 number arrives with its interpretation). The label div
        and its FT-R11 marker comment are untouched by that port — only the
        sentence inside changed — so assert the disclosure, not the retired
        string. Asserting the old wording would pin a Law 2 violation in place.
        """
        src = _src("allocation.html.j2")
        assert "FT-R11 horizon label" in src
        # the horizon, and that it is slow by construction
        assert "A slow book" in src
        assert "3–12 month trends" in src
        assert "most recent month deliberately excluded" in src
        # the consequence the label exists to state: it is not an intraday read
        assert "reacts over months, not days" in src
        # Law 5 — honesty survives translation (the ZH twin carries the same claim)
        assert "慢速账本" in src

    def test_basket_detail_nb_chg_spans(self):
        """basket_detail must emit nb-chg spans for member live-price wiring."""
        src = _src("basket_detail.html.j2")
        assert "nb-chg" in src

    def test_baskets_member_sym_registry_div(self):
        """sector_central.html.j2 must have the hidden registry div for live-quotes scrape."""
        assert "ftr-member-sym-registry" in _src("sector_central.html.j2")


# ── Full-render guard for sector_central.html.j2 ─────────────────────────────────

class TestFtrBasketsRender:
    """Full Jinja render of sector_central.html.j2 with basket_member_syms context."""

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
