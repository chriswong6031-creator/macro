"""Render/parse assertions for FTR W3+W8-UI tape-surface template additions.

Guards (all three templates: baskets.html.j2, allocation.html.j2, basket_detail.html.j2):
- ftr-tape-band with the tape band v3 idiom (#2227 port) in baskets:
  dtp-token state label, ONE as-of, ranked leader/laggard columns with ordinals,
  full-tape expander, ai_capex complex row
- user-first copy (docs/DESIGN_DOCTRINE.md): no rank numbers, no raw
  IGNITION/WATCH display labels, plain-word fade footer with the technical
  receipt (Oracle P8 / 58% / n=26) demoted to data-tips / ? help tips
- the per-card chip lane (ftr-disagree-chip / ftr-heat-chip / ftr-tw-card) is
  RETIRED (2026-08-02) and guarded by reachability, not presence — see
  TestFtrCardChipLaneReachability at the bottom of this module
- ftr-alloc-tape-panel in allocation (display names, no rank numbers)
- ftr-live-strip + ftr-anatomy-card in basket_detail
- T+1 58% fade base rate retained on all three templates (FT-R3, Tier-2 receipt)
- No "validated" keyword in FTR-added copy (house-law gauntlet guard)
- stale-gate: isChipSuppressed() still gates the tape band's flow chips (FT-R12)
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

# ── Per-card chip lane: the classes injectCardChips() used to append to
# theme-desk cards, and the two entry points that can put such a card on a page.
FTR_CARD_CHIP_CLASSES = (
    "ftr-disagree-chip",
    "ftr-heat-chip",
    "ftr-stale-chip",
    "ftr-tw-card",
    "ftr-chip-strip",
)
CARD_RENDERER_ENTRY_POINTS = ("renderThemeDesk", "deskBoot")


def _emits_class(src: str, cls: str) -> bool:
    """True when `src` puts `cls` on an element it BUILDS.

    Matches a class= / className= / classList.add() site only, so a CSS rule
    (`.ftr-tw-card { … }`) or a sentence in a comment does not read as markup.
    That distinction is the whole point: the pins this replaced were satisfied
    by both.
    """
    esc = re.escape(cls)
    return bool(
        re.search(rf"""(?:class|className)\s*=\s*["'][^"'\n]*{esc}""", src)
        or re.search(rf"""classList\.add\(\s*["']{esc}\b""", src)
    )


def _call_count(src: str, fn: str) -> int:
    """Times `fn` is CALLED in `src` (its own `function fn(` declaration excluded)."""
    total = len(re.findall(rf"\b{re.escape(fn)}\s*\(", src))
    declared = len(re.findall(rf"\bfunction\s+{re.escape(fn)}\s*\(", src))
    return total - declared


def card_chip_lane_violations(sources: dict[str, str]) -> dict[str, list[str]]:
    """Sources that BUILD per-card chip markup with no reachable card to put it on.

    A source may emit the chip classes only if it also *invokes* a renderer that
    emits theme-desk cards. Defining one is not enough — `renderThemeDesk` sat
    defined-and-uncalled on baskets.html.j2 for the entire dead window.
    """
    violations: dict[str, list[str]] = {}
    for name, src in sources.items():
        emitted = [c for c in FTR_CARD_CHIP_CLASSES if _emits_class(src, c)]
        if not emitted:
            continue
        if not any(_call_count(src, fn) > 0 for fn in CARD_RENDERER_ENTRY_POINTS):
            violations[name] = emitted
    return violations


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
        + full-tape expander replace the old top/bottom mover halves.

        The expander continues each column (.dtp-colmore) instead of opening one
        flat #ftr-dtp-full block. #2267 deleted the flat container after a
        user-reported bug: it sat inside a two-column CSS grid, so auto-flow
        interleaved the expansion (rank 1 left, 2 right, 3 left …) and restated
        every preview row, destroying the leaders-left / laggards-right reading.
        Continuation rows now live inside each preview column and the two columns
        meet at mid-tape, so each basket appears exactly once.
        """
        src = _src("baskets.html.j2")
        assert "ftr-dtp-body" in src
        assert "LIVE LEADERS" in src
        assert "SESSION LEADERS — AT THE CLOSE" in src
        assert "ftr-dtp-more" in src
        assert "Show full tape" in src
        # per-column continuation blocks: emitted hidden, toggled together (#2267)
        assert 'class="dtp-colmore" hidden' in src
        assert "querySelectorAll('.dtp-colmore')" in src
        # the flat interleaving container must not come back
        assert "ftr-dtp-full" not in src
        # expander law (#2206 double-toggle lesson): own class + [hidden] re-assert.
        # W0 of the Crypto Cockpit moved the shared .dtp vocabulary into theme.css;
        # keep this guard on the canonical owner instead of requiring a page-local copy.
        theme = _src("theme.css")
        assert ".dtp-colmore[hidden], .dtp-more[hidden] { display:none; }" in theme
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
        (docs/DESIGN_DOCTRINE.md Law 2 — plain words on Tier 1).

        The plain-word pair itself moved to basket_detail.html.j2 when the
        per-card turn-watch card was retired from this page (2026-08-02); the
        no-raw-enum half still belongs here.
        """
        src = _src("baskets.html.j2")
        assert "&#9889; IGNITION" not in src
        assert "&#9889; WATCH" not in src
        detail = _src("basket_detail.html.j2")
        assert "STRONG SIGN" in detail
        assert "EARLY SIGN" in detail

    def test_t1_fade_rate(self):
        """FT-R3: T+1 58% fade base rate retained (in the Tier-2 technical receipt)."""
        assert "58%" in _src("baskets.html.j2")

    def test_plain_fade_footer_with_receipt(self):
        """User-first null disclosure (docs/DESIGN_DOCTRINE.md Law 5): plain words on
        Tier 1 ('Not a buy signal … 6 in 10 faded within a day'), the technical
        receipt demoted to data-tips — that IS the compliant 'nulls printed'
        form; the jargon form must be gone.

        The disclosure follows the claim. This page's live claim is the tape
        band, whose receipt is the T+1 58% (n=26) fade rate in the footnote's ?
        tip. The Oracle P8 expected-null receipt belonged to the turn-watch
        meter, and moved with it to basket_detail.html.j2 (2026-08-02) — pinned
        by test_turn_watch_receipt_lives_with_its_surface below.
        """
        src = _src("baskets.html.j2")
        assert "Not a buy signal" in src
        assert "6 in 10" in src
        assert "58%" in src  # receipt survives on Tier 2 (data-tip / ? tip)
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

    def test_basket_pulse_json_fetch(self):
        """The tape band's own source — the one fetch this page still makes."""
        assert "fetchJson('live/basket_pulse.json'" in _src("baskets.html.j2")

    def test_no_fetches_for_the_retired_card_lane(self):
        """turn_watch.json (14 KB) and sector_pulse.json (47 KB) were fetched on
        every load of this page and handed to injectCardChips(), which had no
        cards to chip after #3282 — 62 KB parsed and dropped per view. Retired
        2026-08-02.

        Pinned as fetch CALLS, not bare filenames: the filenames appear in the
        comment that records why they went, and a substring pin would read that
        comment as a live fetch.
        """
        src = _src("baskets.html.j2")
        assert "fetchJson('basketdata/turn_watch.json'" not in src
        assert "fetchJson('basketdata/sector_pulse.json'" not in src

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
        the region's baskets.json with a prettified-slug fallback, never raw ids.

        The name map is region-aware since #2380 — HK/CN/CA rows were reading the
        US-only basketdata/ and so "fell back to slug names", the exact failure
        this test guards. The directory is now chosen by d.region at render time,
        so the literal "basketdata/baskets.json" exists only in the rendered US
        output (site/allocation.html); the template source carries the map.
        Assert the map and the lookup, which hold for every region.
        """
        src = _src("allocation.html.j2")
        assert "nameEnOf" in src
        assert "nameZhOf" in src
        # region-aware basket-name map (#2380): US default + HK/CN/CA siblings
        assert "/baskets.json" in src
        assert '.get(d.region,"basketdata")' in src
        assert '"china":"chinabasketdata"' in src
        assert '"hk":"hkbasketdata"' in src
        assert '"canada":"canadabasketdata"' in src
        # never a raw id: prettified-slug fallback when the map misses
        assert "_slugName(id)" in src

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

    def test_t1_fade_rate_in_render(self):
        html = _render_baskets(["SPY"])
        assert "58%" in html

    def test_plain_null_disclosure_in_render(self):
        html = _render_baskets(["SPY"])
        assert "Not a buy signal" in html
        assert "58%" in html  # Tier-2 receipt survives

    def test_retired_card_lane_absent_from_render(self):
        """The rendered US page must ship no per-card chip machinery."""
        html = _render_baskets(["SPY"])
        assert "injectCardChips" not in html
        for cls in FTR_CARD_CHIP_CLASSES:
            assert not _emits_class(html, cls), f"{cls} is emitted by a page with no cards"


# ── Per-card chip lane: reachability, not presence ───────────────────────────


class TestFtrCardChipLaneReachability:
    """The FTR per-card chip lane injected `ftr-disagree-chip` / `ftr-heat-chip`
    / `ftr-stale-chip` / `ftr-tw-card` into theme-desk cards — `[id^="theme-"]`
    / `.tcard` elements that `renderThemeDesk()` builds.

    #3282 (the baskets rvx revamp) replaced that desk with the act lanes and the
    rotation board and dropped the call. From then until 2026-08-02 the lane ran
    on every load of the US page, matched an empty NodeList, and injected
    nothing — while `assert "ftr-disagree-chip" in _src("baskets.html.j2")` and
    four sibling pins stayed green the whole time. A presence pin cannot see an
    unreachable feature: the string it asserts lives in the injector, and the
    injector is exactly the half that survives.

    These pins assert reachability instead. `card_chip_lane_violations` is
    itself pinned against a synthetic reproduction of the #3282 state below, so
    it cannot quietly decay into a function that never fires.
    """

    # The historical defect, minimised: the chip builder with no reachable card.
    DEAD_LANE = """
      function injectCardChips(pulse){
        document.querySelectorAll('[id^="theme-"]').forEach(function(card){
          card.innerHTML = '<span class="ftr-disagree-chip">strong today</span>';
        });
      }
      injectCardChips(pulse);
      function renderThemeDesk(){ return '<div class="tcard" id="theme-'+id+'"></div>'; }
    """
    # The same page with the desk actually booted.
    LIVE_LANE = DEAD_LANE + "\n renderThemeDesk();\n"

    def test_detector_fires_on_the_historical_defect(self):
        """Mutation check. If this stops failing, the guard below is decorative.

        Note DEAD_LANE *defines* renderThemeDesk — presence of the emitter is
        not reachability, which is precisely how the original pins were fooled.
        """
        found = card_chip_lane_violations({"dead.j2": self.DEAD_LANE})
        assert "dead.j2" in found
        assert found["dead.j2"] == ["ftr-disagree-chip"]

    def test_detector_clears_a_page_that_boots_the_desk(self):
        """Control: the guard must not fire on a page whose cards are reachable."""
        assert card_chip_lane_violations({"live.j2": self.LIVE_LANE}) == {}

    def test_detector_ignores_css_and_prose(self):
        """CSS rules and comments naming the retired classes are not markup."""
        noise = """
          .ftr-tw-card { border-radius:8px; }
          {# ftr-disagree-chip and ftr-heat-chip were retired 2026-08-02 #}
          // injectCardChips() appended an ftr-chip-strip here.
        """
        assert card_chip_lane_violations({"noise.j2": noise}) == {}

    def test_no_template_builds_card_chips_it_cannot_place(self):
        """The repo-wide guard. Fires on any template — including one that
        inherits this markup by being copied from baskets.html.j2 — that emits
        per-card chips without booting a renderer that produces the cards."""
        sources = {
            p.name: p.read_text()
            for p in sorted(TMPL_DIR.glob("*.j2")) + sorted(TMPL_DIR.glob("*.js"))
        }
        assert sources, "template sweep found nothing — the glob is wrong"
        found = card_chip_lane_violations(sources)
        assert found == {}, (
            "per-card chip markup with no reachable theme-desk card: "
            + "; ".join(f"{k} emits {v}" for k, v in found.items())
        )

    def test_us_page_ships_no_card_chip_injector(self):
        """The retirement itself, stated so re-adding the lane trips a pin."""
        src = _src("baskets.html.j2")
        assert "function injectCardChips" not in src
        assert 'querySelectorAll(\'[id^="theme-"]\')' not in src

    def test_turn_watch_receipt_lives_with_its_surface(self):
        """The turn-watch read kept its home on the per-basket detail page — one
        click from every act-lane and rotation-board row — and its expected-null
        receipt (Oracle P8) went with it. Disclosure follows the claim: the US
        index page makes no turn-watch claim, so it carries no orphan receipt.
        """
        detail = _src("basket_detail.html.j2")
        assert "fetch('../basketdata/turn_watch.json'" in detail
        assert "Oracle P8" in detail
        assert "Oracle P8" not in _src("baskets.html.j2")
