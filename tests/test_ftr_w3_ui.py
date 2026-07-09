"""Render/parse assertions for FTR W3+W8-UI tape-surface template additions.

Guards (all three templates: baskets.html.j2, allocation.html.j2, basket_detail.html.j2):
- ftr-tape-band, ftr-session-pill, ftr-cx-badge, ftr-top-movers, ftr-bot-movers in baskets
- ftr-disagree-chip (Variant B design) in baskets
- ftr-tw-card (turn-watch card) in baskets
- ftr-alloc-tape-panel in allocation
- ftr-live-strip + ftr-anatomy-card in basket_detail
- T+1 58% fade base rate string present on all three templates (FT-R3)
- Expected-null disclosure string present in baskets (turn-watch FT-R2)
- No "validated" keyword in FTR-added copy (house-law gauntlet guard)
- stale-gate: STALE chip present in baskets source (FT-R12)
- Relative paths for basket_detail fetches (../ prefix)
- FT-R8: fail-silent fetch pattern (catch) present
- W8 anatomy panel leg order / WEIGHTS present in basket_detail

All artifacts are display-tier / de-escalation only (FT-R1, FT-R2).
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

    env = Environment(
        loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False, undefined=Undefined
    )
    t = env.get_template("baskets.html.j2")
    return t.render(basket_member_syms=syms)


# ── Parse (Jinja syntax) guards ───────────────────────────────────────────────


class TestFtrW3TemplatesParse:
    def test_baskets_parses(self):
        _parse("baskets.html.j2")

    def test_allocation_parses(self):
        _parse("allocation.html.j2")

    def test_basket_detail_parses(self):
        _parse("basket_detail.html.j2")


# ── baskets.html.j2 tape band markers ─────────────────────────────────────────


class TestBasketsW3Markers:
    def test_tape_band_div(self):
        assert "ftr-tape-band" in _src("baskets.html.j2")

    def test_tape_band_visible_class(self):
        """CSS toggle class must be present (JS adds .visible to show the band)."""
        assert "ftr-tape-band.visible" in _src("baskets.html.j2")

    def test_session_pill(self):
        assert "ftr-session-pill" in _src("baskets.html.j2")

    def test_cx_badge(self):
        assert "ftr-cx-badge" in _src("baskets.html.j2")

    def test_top_movers_slot(self):
        assert "ftr-top-movers" in _src("baskets.html.j2")

    def test_bot_movers_slot(self):
        assert "ftr-bot-movers" in _src("baskets.html.j2")

    def test_disagree_chip(self):
        """Amber disagreement chip (FT-R2 display, FT-R12 stale-gated)."""
        assert "ftr-disagree-chip" in _src("baskets.html.j2")

    def test_tw_card(self):
        """Turn-watch inline card for WATCH/IGNITION states."""
        assert "ftr-tw-card" in _src("baskets.html.j2")

    def test_stale_chip_present(self):
        """FT-R12: STALE chip must be renderable from source."""
        assert "ftr-stale-chip" in _src("baskets.html.j2")

    def test_t1_fade_rate(self):
        """FT-R3: T+1 58% fade base rate must appear inline with tape reads."""
        assert "58%" in _src("baskets.html.j2")

    def test_expected_null_disclosure(self):
        """Turn-watch cards must carry the expected-null forward meter disclosure."""
        assert "Expected-null" in _src("baskets.html.j2")

    def test_no_validated_copy(self):
        """House law: 'validated' is CI-guarded and must not appear in FTR copy."""
        # Only check within JS/HTML added by FTR W3 (the tape band section)
        src = _src("baskets.html.j2")
        # Allowed in comments referencing CI guard itself; disallowed in user-facing copy
        # Simple check: no standalone "validated" as a user-facing claim
        assert "is validated" not in src
        assert '"validated"' not in src

    def test_fail_silent_catch(self):
        """FT-R8: fetch errors must be swallowed (catch present)."""
        assert ".catch(" in _src("baskets.html.j2")

    def test_turn_watch_json_fetch(self):
        """Tape band fetches turn_watch.json for WATCH/IGNITION states."""
        assert "turn_watch.json" in _src("baskets.html.j2")

    def test_basket_pulse_json_fetch(self):
        assert "basket_pulse.json" in _src("baskets.html.j2")

    def test_sector_pulse_json_fetch(self):
        assert "sector_pulse.json" in _src("baskets.html.j2")

    def test_card_selector_uses_id_prefix_not_data_bid(self):
        """BLOCKER fix: must use [id^="theme-"] selector (not [data-bid] which matches nothing).

        baskets_desk.js renders cards as id="theme-<bid>" with no data-bid attribute.
        Using [data-bid] produces an empty NodeList — all per-card chips silently no-op.
        """
        src = _src("baskets.html.j2")
        assert '[id^="theme-"]' in src, (
            "Card selector must be [id^='theme-'] — [data-bid] matches nothing in the DOM"
        )
        assert "[data-bid]" not in src, (
            "[data-bid] selector matches nothing (baskets_desk.js emits no data-bid attrs)"
        )

    def test_t1_fade_in_tape_band_html(self):
        """FT-R3: T+1 fade base rate must appear in the tape band HTML (not only in JS/shock banner).

        The tape band footer must show the base rate as always-visible copy,
        not only when the shock state is active. The ftr-tape-t1 div is always-rendered HTML
        (not inside a JS string or shock-conditional block).
        """
        src = _src("baskets.html.j2")
        # Search for the HTML element usage (class="ftr-tape-t1"), not the CSS rule
        html_element_marker = 'class="ftr-tape-t1"'
        assert html_element_marker in src, "ftr-tape-t1 HTML element must exist in tape band"
        idx = src.find(html_element_marker)
        tape_t1_section = src[idx : idx + 600]
        assert "58%" in tape_t1_section, (
            "T+1 58% fade base rate must appear in ftr-tape-t1 HTML element, not only in JS"
        )

    def test_mover_rows_use_tape_rank(self):
        """NIT fix: mover rows must use b.tape_rank (authoritative) not synthetic n-i index."""
        src = _src("baskets.html.j2")
        assert "b.tape_rank" in src, "moverRow must use b.tape_rank, not n-i or bot3.length-i"


# ── allocation.html.j2 tape panel markers ─────────────────────────────────────


class TestAllocationW3Markers:
    def test_alloc_tape_panel(self):
        assert "ftr-alloc-tape-panel" in _src("allocation.html.j2")

    def test_t1_fade_rate(self):
        """FT-R3: T+1 fade note on allocation tape panel."""
        assert "58%" in _src("allocation.html.j2")

    def test_fail_silent_catch(self):
        """FT-R8: allocation tape JS must be fail-silent."""
        src = _src("allocation.html.j2")
        # Count catches after the ftr-alloc-tape-panel block
        alloc_section = src[src.find("ftr-alloc-tape-panel") :]
        assert ".catch(" in alloc_section or ".catch(" in src

    def test_basket_pulse_fetch_in_allocation(self):
        src = _src("allocation.html.j2")
        assert "basket_pulse.json" in src

    def test_no_directional_lagging_verb(self):
        """MINOR fix: 'lagging' is a directional characterization (FT-R13). Must not appear in copy."""
        src = _src("allocation.html.j2")
        assert "lagging live tape" not in src, (
            "FT-R13: 'lagging' is a directional verb — replace with neutral tape-rank framing"
        )


# ── basket_detail.html.j2 live strip + W8 anatomy markers ─────────────────────


class TestBasketDetailW3Markers:
    def test_live_strip_css(self):
        assert "ftr-live-strip" in _src("basket_detail.html.j2")

    def test_anatomy_card_css(self):
        assert "ftr-anatomy-card" in _src("basket_detail.html.j2")

    def test_anatomy_panel_fn(self):
        """anatomyPanelHtml function must be defined."""
        assert "anatomyPanelHtml" in _src("basket_detail.html.j2")

    def test_w8_anatomy_section_class(self):
        assert "ftr-w8-anatomy-section" in _src("basket_detail.html.j2")

    def test_weights_present(self):
        """W8 anatomy panel must embed the seven leg weights."""
        src = _src("basket_detail.html.j2")
        assert "trend:0.26" in src or "trend: 0.26" in src
        assert "breadth:0.18" in src or "breadth: 0.18" in src
        assert "crowding:0.10" in src or "crowding: 0.10" in src

    def test_leg_order_complete(self):
        """All 7 legs must appear in basket_detail."""
        src = _src("basket_detail.html.j2")
        for leg in ("trend", "breadth", "impulse", "macro", "mtf", "volhole", "crowding"):
            assert leg in src, f"Leg '{leg}' missing from basket_detail anatomy panel"

    def test_relative_pulse_fetch_path(self):
        """basket_detail lives under site/basket/ — must use ../ prefix."""
        assert "../live/basket_pulse.json" in _src("basket_detail.html.j2")

    def test_relative_tw_fetch_path(self):
        assert "../basketdata/turn_watch.json" in _src("basket_detail.html.j2")

    def test_fail_silent_catch(self):
        """FT-R8: basket_detail fetches must be fail-silent."""
        src = _src("basket_detail.html.j2")
        # FTR section is after the main boot() function
        ftr_section = src[src.find("FTR W3: live strip") :]
        assert ".catch(" in ftr_section

    def test_crowding_penalty_note(self):
        """Crowding penalty must be explained in the anatomy panel."""
        assert "rs_pctile" in _src("basket_detail.html.j2")
        assert "0.85" in _src("basket_detail.html.j2")

    def test_injectFtrWidgets_fn(self):
        assert "injectFtrWidgets" in _src("basket_detail.html.j2")


# ── Full-render guard: baskets.html.j2 with syms ─────────────────────────────


class TestFtrW3BasketsRender:
    def test_tape_band_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-tape-band" in html

    def test_session_pill_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-session-pill" in html

    def test_top_movers_slot_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-top-movers" in html

    def test_disagree_chip_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-disagree-chip" in html

    def test_tw_card_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-tw-card" in html

    def test_t1_fade_rate_in_render(self):
        html = _render_baskets(["SPY"])
        assert "58%" in html

    def test_expected_null_disclosure_in_render(self):
        html = _render_baskets(["SPY"])
        assert "Expected-null" in html

    def test_sector_pulse_fetch_in_render(self):
        html = _render_baskets(["SPY"])
        assert "sector_pulse.json" in html
