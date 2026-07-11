"""Render/parse assertions for FTR W3+W8-UI tape-surface template additions.

Guards (all three templates: baskets.html.j2, allocation.html.j2, basket_detail.html.j2):
- ftr-tape-band with the tape band v3 idiom (#2227 port) in baskets:
  dtp-token state label, ONE as-of, ranked leader/laggard columns with ordinals,
  full-tape expander, ai_capex complex row
- user-first copy (docs/DESIGN_DOCTRINE.md): no rank numbers, no raw
  IGNITION/WATCH display labels, plain-word fade footer with the technical
  receipt (Oracle P8 / 58% / n=26) demoted to data-tips / ? help tips
- ftr-disagree-chip (plain words + receipt tip) in baskets
- ftr-tw-card (turn-watch card, STRONG SIGN / EARLY SIGN badges) in baskets
- ftr-alloc-tape-panel in allocation (display names, no rank numbers)
- ftr-live-strip + ftr-anatomy-card in basket_detail
- T+1 58% fade base rate retained on all three templates (FT-R3, Tier-2 receipt)
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

    def test_dtp_state_token(self):
        """The .dtp state token IS the label (LIVE · 15-MIN DELAYED / SETTLED CLOSE …)."""
        src = _src("baskets.html.j2")
        assert "dtp-token" in src
        assert "LIVE · 15-MIN DELAYED" in src
        assert "POST-MARKET · SETTLED CLOSE" in src

    def test_cx_chip(self):
        """AI-Capex complex chip rendered inside the .dtp chip row (live mode only)."""
        src = _src("baskets.html.j2")
        assert "ai_capex" in src
        assert "AI-Capex Complex" in src

    def test_v3_ranked_columns(self):
        """Tape band v3 (#2227): ranked two-column body + state-adaptive column labels
        + full-tape expander replace the old top/bottom mover halves."""
        src = _src("baskets.html.j2")
        assert "ftr-dtp-body" in src
        assert "LIVE LEADERS" in src
        assert "SESSION LEADERS — AT THE CLOSE" in src
        assert "ftr-dtp-full" in src
        assert "ftr-dtp-more" in src
        assert "Show full tape" in src
        # expander law (#2206 double-toggle lesson): own class + [hidden] re-assert
        assert ".dtp-full[hidden], .dtp-more[hidden] { display:none; }" in src
        assert ".lst-more" not in src

    def test_no_raw_rank_idiom(self):
        """The vetoed '#'-prefixed raw tape_rank idiom must not render (v3 per-column
        ordinals in .dtp-rank are the sanctioned form)."""
        src = _src("baskets.html.j2")
        assert "mr-rank" not in src
        assert "'#'+rank" not in src
        assert "tape rank #" not in src
        assert "dtp-rank" in src

    def test_no_raw_state_display_labels(self):
        """IGNITION/WATCH stay as JSON states but must not be user-facing labels
        (docs/DESIGN_DOCTRINE.md Law 2 — plain words on Tier 1)."""
        src = _src("baskets.html.j2")
        assert "&#9889; IGNITION" not in src
        assert "&#9889; WATCH" not in src
        assert "STRONG SIGN" in src
        assert "EARLY SIGN" in src

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
        """FT-R3: T+1 58% fade base rate retained (in the Tier-2 technical receipt)."""
        assert "58%" in _src("baskets.html.j2")

    def test_plain_fade_footer_with_receipt(self):
        """User-first null disclosure (docs/DESIGN_DOCTRINE.md Law 5): plain words on
        Tier 1 ('Not a buy signal … 6 in 10 faded within a day'), the expected-null
        receipt (Oracle P8) demoted to data-tips — that IS the compliant 'nulls
        printed' form; the jargon form must be gone."""
        src = _src("baskets.html.j2")
        assert "Not a buy signal" in src
        assert "6 in 10" in src
        assert "Oracle P8" in src  # receipt survives on Tier 2 (data-tip / ? tip)
        assert "Expected-null forward meter" not in src

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
        """FT-R3: the fade note must be always-rendered HTML in the tape band footer
        (not only in JS/shock banner) — plain words visible, 58% receipt in the
        adjacent ? help tip within the same footnote element.
        """
        src = _src("baskets.html.j2")
        # Search for the HTML element usage (class="dtp-fn ftr-tape-t1"), not the CSS rule
        html_element_marker = 'class="dtp-fn ftr-tape-t1"'
        assert html_element_marker in src, "ftr-tape-t1 footnote element must exist in tape band"
        idx = src.find(html_element_marker)
        tape_t1_section = src[idx : idx + 900]
        assert "Not a buy signal" in tape_t1_section, (
            "Plain-word fade note must appear in the ftr-tape-t1 footnote element"
        )
        assert "58%" in tape_t1_section, (
            "T+1 58% fade base rate receipt must live in the footnote's ? tip"
        )

    def test_mover_chips_use_tape_rank(self):
        """Mover chips must sort by b.tape_rank (authoritative) not synthetic n-i index."""
        src = _src("baskets.html.j2")
        assert "b.tape_rank" in src, "chip ordering must use b.tape_rank, not n-i or bot3.length-i"

    def test_honest_shared_scale_bars(self):
        """#2208 idiom law: bars are proportional on a shared px scale (maxAbs), not
        the old fake fixed-multiplier bars."""
        src = _src("baskets.html.j2")
        assert "maxAbs" in src
        assert "Math.abs(chg)/maxAbs" in src


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

    def test_no_rank_numbers_in_movers(self):
        """Operator-vetoed rank-# idiom (#2208 ruling): mover rows carry no rank numbers."""
        src = _src("allocation.html.j2")
        assert "'#'+rank" not in src
        assert "tape rank #" not in src

    def test_display_names_not_slugs(self):
        """Law 2 (docs/DESIGN_DOCTRINE.md): mover rows show display names from
        basketdata/baskets.json with a prettified-slug fallback, never raw ids."""
        src = _src("allocation.html.j2")
        assert "nameEnOf" in src
        assert "nameZhOf" in src
        assert "basketdata/baskets.json" in src

    def test_plain_fade_footer_with_receipt(self):
        """Plain-word fade footer on Tier 1; 58% receipt demoted to the ? data-tip."""
        src = _src("allocation.html.j2")
        assert "Not a buy signal" in src
        assert "T+1 violent-flip base rate 58% fade (n=26)" in src  # receipt tip


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

    def test_plain_turn_labels(self):
        """#2221 vocabulary on the live strip: STRONG SIGN / EARLY SIGN display labels,
        no raw state enums or rank-# idiom in user copy (states stay in code)."""
        src = _src("basket_detail.html.j2")
        assert "STRONG SIGN" in src
        assert "EARLY SIGN" in src
        assert "tape rank #" not in src
        assert "on today&#39;s board" in src


# ── Full-render guard: baskets.html.j2 with syms ─────────────────────────────


class TestFtrW3BasketsRender:
    def test_tape_band_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-tape-band" in html

    def test_dtp_token_in_render(self):
        html = _render_baskets(["SPY"])
        assert "dtp-token" in html

    def test_dtp_body_slot_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-dtp-body" in html

    def test_disagree_chip_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-disagree-chip" in html

    def test_tw_card_in_render(self):
        html = _render_baskets(["SPY"])
        assert "ftr-tw-card" in html

    def test_t1_fade_rate_in_render(self):
        html = _render_baskets(["SPY"])
        assert "58%" in html

    def test_plain_null_disclosure_in_render(self):
        html = _render_baskets(["SPY"])
        assert "Not a buy signal" in html
        assert "Oracle P8" in html  # Tier-2 receipt survives

    def test_sector_pulse_fetch_in_render(self):
        html = _render_baskets(["SPY"])
        assert "sector_pulse.json" in html
