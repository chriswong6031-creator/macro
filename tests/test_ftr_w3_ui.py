"""Render/parse assertions for FTR W3+W8-UI tape-surface template additions.

Guards (all three templates: baskets.html.j2, allocation.html.j2, basket_detail.html.j2):
- ftr-tape-band with the tape band v3 idiom (#2227 port) in baskets:
  dtp-token state label, ONE as-of, ranked leader/laggard columns with ordinals,
  full-tape expander, ai_capex complex row
- user-first copy (docs/DESIGN_DOCTRINE.md): no rank numbers, no raw
  IGNITION/WATCH display labels, plain-word fade footer with the 58% / n=26
  receipt demoted to data-tips / ? help tips
- ftr-alloc-tape-panel in allocation (display names, no rank numbers)
- ftr-live-strip + ftr-anatomy-card in basket_detail
- T+1 58% fade base rate retained on all three templates (FT-R3, Tier-2 receipt)
- No "validated" keyword in FTR-added copy (house-law gauntlet guard)
- Relative paths for basket_detail fetches (../ prefix)
- FT-R8: fail-silent fetch pattern (catch) present
- W8 anatomy panel leg order / WEIGHTS present in basket_detail
- REACHABILITY (TestFtrBandReachability): every element the baskets band script
  reads has markup in the same template, and the band fetches only what it
  renders. These replace the per-card chip guards, which asserted class names
  against template SOURCE and so stayed green for months while the chips they
  described reached zero readers (#3282 deleted their emitter).
- RETIREMENT (TestFtrPerCardChipLaneRetired): the dead per-card chip lane
  (ftr-disagree-chip / ftr-stale-chip / ftr-heat-chip / ftr-tw-card) must not
  return without a live emitter.

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


# ── FTR band script isolation ────────────────────────────────────────────────
# The reachability guards below police ONLY the tape-band <script>, not the whole
# page: baskets.html.j2 carries other lanes (rotation board, act board, MLC stance
# chips) with their own owners and their own PRs.

_BAND_START = "/* FTR-BAND-SCRIPT:"


def _band_script(name: str = "baskets.html.j2") -> str:
    src = _src(name)
    i = src.find(_BAND_START)
    assert i != -1, (
        f"{_BAND_START} marker missing from {name} — the band script anchor was "
        "renamed or deleted; the reachability guards below cannot run without it"
    )
    j = src.find("</script>", i)
    assert j != -1, "unterminated band <script> block"
    return src[i:j]


def _band_fetch_urls(name: str = "baskets.html.j2") -> set[str]:
    """Every URL the band script fetches (fetchJson(...) or bare fetch(...))."""
    block = _band_script(name)
    return set(re.findall(r"""fetch(?:Json)?\(\s*['"]([^'"]+)['"]""", block))


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
        (docs/DESIGN_DOCTRINE.md Law 2 — plain words on Tier 1)."""
        src = _src("baskets.html.j2")
        assert "&#9889; IGNITION" not in src
        assert "&#9889; WATCH" not in src

    def test_t1_fade_rate(self):
        """FT-R3: T+1 58% fade base rate retained (in the Tier-2 technical receipt)."""
        assert "58%" in _src("baskets.html.j2")

    def test_plain_fade_footer_with_receipt(self):
        """User-first null disclosure (docs/DESIGN_DOCTRINE.md Law 5): plain words on
        Tier 1 ('Not a buy signal … 6 in 10 faded within a day'), the 58% receipt
        demoted to the footnote's ? tip — that IS the compliant 'nulls printed'
        form; the jargon form must be gone.

        (The Oracle P8 receipt moved out with the retired per-card turn-watch card;
        it still ships on the basket detail page, which has a live reader.)"""
        src = _src("baskets.html.j2")
        assert "Not a buy signal" in src
        assert "6 in 10" in src
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

    def test_band_fetches_only_the_artifact_it_reads(self):
        """The band script must fetch basket_pulse and nothing else.

        turn_watch.json and sector_pulse.json used to be fetched on every single
        page load purely to feed the per-card chip injector — which had targeted a
        DOM that #3282 deleted, so ~61 KB/load was downloaded and discarded. This
        pins the fetch list to what the band actually renders; adding a fetch back
        without a reader fails here.
        """
        urls = _band_fetch_urls()
        assert urls == {"live/basket_pulse.json"}, (
            f"band script must fetch exactly the tape source it renders; got {sorted(urls)}"
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


# ── Reachability: the band's JS and its markup must stay paired ───────────────


class TestFtrBandReachability:
    """The guards that would have caught the dead per-card chip lane.

    #3282 deleted the theme-desk cards that `injectCardChips` wrote into. The
    injector kept running, kept fetching three artifacts, and produced nothing
    for months — while `tests/test_ftr_w3_ui.py` stayed green, because every
    assertion it made was `"<class-name>" in template_source`, which is true
    whether or not a single chip ever reaches a reader.

    A source-substring assertion cannot see an empty NodeList. These can: they
    pin each DOM read in the band script to markup that exists in the same
    template, so deleting one half fails the build instead of going dark.
    """

    def test_every_band_target_id_has_markup(self):
        """Each getElementById('x') in the band script needs an id="x" element.

        This is the half that was missing: delete the markup and the JS still
        parses, still runs, and silently no-ops.
        """
        src = _src("baskets.html.j2")
        block = _band_script()
        targets = set(re.findall(r"""getElementById\(\s*['"]([\w-]+)['"]""", block))
        assert targets, "band script reads no elements — anchor probably drifted"
        missing = sorted(t for t in targets if f'id="{t}"' not in src)
        assert not missing, (
            "band script drives element(s) that no markup in baskets.html.j2 "
            f"renders — live-looking JS wired to nothing: {missing}"
        )

    def test_band_uses_no_id_prefix_selector(self):
        """No `[id^="..."]` fan-out selector in the band script.

        The retired injector's whole failure mode was a prefix selector whose
        emitter lived in another page's renderer (`baskets_desk.js`, which this
        page does not even load). A prefix selector is a promise about markup the
        template cannot see; the band addresses its own ids directly instead.
        """
        stray = re.findall(r"""\[id\^=['"][^'"]+['"]\]""", _band_script())
        assert not stray, (
            "band script selects elements by id-prefix; the emitter is not "
            f"guaranteed to exist in this template: {stray}"
        )

    def test_band_markup_and_visibility_toggle_both_present(self):
        """The band is the one surface here that IS live — keep it that way."""
        src = _src("baskets.html.j2")
        assert 'id="ftr-tape-band"' in src, "tape band markup must exist"
        assert ".ftr-tape-band.visible" in src, "the .visible CSS toggle must exist"
        assert "classList.add('visible')" in _band_script(), (
            "band script must still reveal the band"
        )


class TestFtrPerCardChipLaneRetired:
    """The per-card chip lane is retired — it must not come back half-wired.

    Retired because every read it carried is already on a live surface: the
    rank-delta chip duplicated the rotation board's velocity column (literally
    the same field, `pulse_rank_delta_5d`), the heat chip restated the quadrant
    map's LEADING/WEAKENING/IMPROVING/LAGGING classification in a second
    vocabulary, the disagreement chip is re-homed by the act board's stance chip
    (PR #4241), and the turn-watch card still ships on the basket detail page,
    which has a live reader.
    """

    RETIRED_CLASSES = (
        "ftr-disagree-chip",
        "ftr-stale-chip",
        "ftr-heat-chip",
        "ftr-tw-card",
        "ftr-chip-strip",
        "ftr-live-chg",
    )

    def test_no_injector(self):
        assert "injectCardChips" not in _src("baskets.html.j2")

    def test_no_retired_chip_emitters_or_css(self):
        """Rendered output carries none of the retired classes.

        Checked against the RENDER, not the template source, so a Jinja comment
        explaining the retirement does not satisfy the guard.
        """
        html = _render_baskets(["SPY"])
        # The #theme-desk compact-chip rule still names two of these inside one
        # selector list. It is dead CSS scoped to a container that no longer
        # exists, and PR #4246 (shared-desk-renderer cleanup) owns that line, not
        # this lane. Excise that ONE declaration rather than exempting the class
        # names, so a genuine re-emission of ftr-stale-chip / ftr-heat-chip
        # anywhere else on the page still trips this guard.
        html = re.sub(
            r"#theme-desk td \.txrow \.chip,.*?\{[^}]*\}", "", html, flags=re.S
        )
        present = [c for c in self.RETIRED_CLASSES if c in html]
        assert not present, (
            f"retired per-card chip artifacts are back in the render: {present} — "
            "if you are reviving them, give them a live emitter and a DOM-level "
            "assertion, not a source-substring one"
        )
