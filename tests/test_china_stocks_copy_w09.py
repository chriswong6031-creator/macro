"""China Prophet v2 copy smoke tests.

Verifies that the mode=stocks copy describes the selective multifactor T1–T3
entry shelf, states the priority score's limits, and complies with bilingual /
t()-in-attributes safety rules.

Mirrors the idiom of tests/test_china_board_track_render.py (the nearest sibling)
and tests/test_china_stocks_w1c_render.py (the extraction/anti-vacuity idiom).

Prophet-card redesign (2026-07-21) — what moved, and why this suite was re-pinned:
  - The standout panel's archetype description used to live in a separate h2 SUBTITLE
    CHIP ('cycle-aligned bottoming · weekly + 3-day + daily turning up').  That chip is
    GONE.  The h2 is now '⚡ Prophet Stock Signals / ⚡ 先知选股' and the entire archetype
    read — the washout → base → fresh-turn cascade (T1–T4), the buy-readiness score
    definition, and the three epistemic caveats — moved INTO the h2 help() tooltip
    (china.html.j2 ~L3163).  The copy was not lost; it moved from a chip into the (?)
    popover.  The tests below keep the old chip strings as ABSENCE pins (the chip must
    not come back) and pin the live caveat/cascade copy on its new tooltip home.
  - EXTRACTION ANCHOR (load-bearing): _render_standout_header extracts from the
    '{# ── W-FCT: shelf partitions hoisted above the panel' comment (~L3143), the SAME
    anchor the w1c suite uses, NOT from the panel <div>.  Two reasons: (1) the panel div
    now carries data-stfacet="{{ _stf_default }}", so the old literal marker
    '  <div class="panel span12" id="standouts">' no longer substring-matches and
    SRC.index() raised ValueError (the single root cause of all 8 failures on main —
    the suite was wired into no CI job so it rotted silently as the template evolved);
    (2) starting at W-FCT keeps _stf_default (and the _entry_rows/_rip*/_ran partition
    sets) DEFINED — the panel div interpolates _stf_default, so an anchor below the
    W-FCT block would render it Undefined-empty.  The W-FCT block calls setups.get(...)
    and setups.buy, so the fixture is a dict (not the old FakeSetups class, which had no
    .get()); see _standout_setups.
  - i18n: the extracted block calls t() and help() (macros, prepended in the harness) and
    does NOT call the tr() global, so — unlike the w1c suite — no engine.i18n.tr
    registration is needed here.  The stocks-header block (_render_stocks_header) does use
    the real i18n globals; that path is unchanged.
"""
import re
from pathlib import Path

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "templates" / "china.html.j2").read_text()

# The load-bearing extraction anchors for the standout panel header.  Kept as module
# constants so the render harness and the raw-source t()-in-attr test extract the
# SAME region (a drift between them was part of why this suite rotted).
STANDOUT_START = "{# ── W-FCT: shelf partitions hoisted above the panel"
STANDOUT_END = "    {# W0.7 DATA OUTAGE BANNER"


def _render_stocks_header() -> str:
    """Render the mode=stocks page header (the first panel in the grid)."""
    marker_start = "<!-- ===================== A-SHARE STOCK DASHBOARD HEADER"
    marker_end = "  {% endif %}\n\n  {% if mode != 'stocks' %}"
    start = SRC.index(marker_start) - len("  {% if mode == 'stocks' %}\n")
    end = SRC.index(marker_end, start) + len("  {% endif %}")
    snippet = SRC[start:end]

    from engine import i18n

    # Mirror china.html.j2's file-top imports (they sit outside every sliced
    # snippet) and let a FileSystemLoader resolve the real partials, so a new
    # {% import %} never breaks this harness again.
    blk = (
        '{% import "_prophet_card.html.j2" as pv %}\n'
        '{% import "_decision_card.html.j2" as dc %}\n'
        '{% import "_lens.html.j2" as lens %}\n'
    ) + snippet
    env = Environment(
        loader=ChoiceLoader([DictLoader({"blk": blk}), FileSystemLoader(str(ROOT / "templates"))]),
        autoescape=False,
    )
    # help() renders its copy: since the 2026-07-10 declutter the header's archetype
    # description is user-facing via the (?) tooltip, so the stub must not drop it.
    env.globals.update(
        t=i18n.t, td=i18n.td, tr=i18n.tr,
        help=lambda en, zh="", cls="": (
            f'<span class="help-tip l-en">{en}</span>'
            f'<span class="help-tip l-zh">{zh}</span>'
        ),
    )

    class FakeLatest:
        quad = "Q1"
        quad_name = "Goldilocks"

    class FakePB:
        dial = None

    return env.get_template("blk").render(
        mode="stocks", latest=FakeLatest(), pb=FakePB()
    )


def _standout_setups(buy=None) -> dict:
    """A dict-based setups fixture for the W-FCT → outage-banner block.

    The W-FCT partition block calls setups.buy (selectattr over 'stage') AND
    setups.get('ripening' / 'ripening_falling' / 'ran'), so setups must be a dict.
    (The old FakeSetups class had only a .buy attribute and no .get() — it worked
    only for the pre-W-FCT panel-div anchor that no longer matches.)  A single
    stage=None buy row keeps the panel non-empty and exercises the pre-W1 backward-
    compat fallback (whole board → entry shelf) without needing full row fixtures.
    """
    return {
        "buy": buy if buy is not None else [{"stage": None}],
        "ripening": [],
        "ripening_falling": [],
        "ran": [],
    }


def _render_standout_header() -> str:
    """Render the standout panel header (W-FCT partition anchor → data-outage banner).

    Extraction starts at the W-FCT comment (~L3143) — the same anchor the w1c suite
    uses — NOT at the panel <div>.  The panel div now carries
    data-stfacet="{{ _stf_default }}" (so the old '  <div class="panel span12"
    id="standouts">' literal no longer matches), and _stf_default is set inside the
    W-FCT block, so anchoring there keeps it defined.  The block runs up to (but not
    including) the W0.7 data-outage banner, which is the first block after the h2.
    """
    start = SRC.index(STANDOUT_START)
    end = SRC.index(STANDOUT_END, start)
    snippet = SRC[start:end]

    # Prepend macro definitions so the snippet is self-contained.  The block uses only
    # t() and help() (no tr() global — unlike the w1c shelf block), so those two macros
    # are all that is needed.
    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
        "{%- macro help(en, zh=\"\") -%}"
        '<span class="help-tip l-en">{{ en }}</span>'
        '<span class="help-tip l-zh">{{ zh }}</span>'
        "{%- endmacro -%}\n"
    )
    # Mirror china.html.j2's file-top imports (they sit outside every sliced
    # snippet) and let a FileSystemLoader resolve the real partials, so a new
    # {% import %} never breaks this harness again.
    full = (
        '{% import "_prophet_card.html.j2" as pv %}\n'
        '{% import "_decision_card.html.j2" as dc %}\n'
        '{% import "_lens.html.j2" as lens %}\n'
    ) + macros + snippet

    env = Environment(
        loader=ChoiceLoader([DictLoader({"blk": full}), FileSystemLoader(str(ROOT / "templates"))]),
        autoescape=False,
    )
    return env.get_template("blk").render(setups=_standout_setups())


def test_template_parses_without_errors() -> None:
    """Full template must parse (Jinja2 syntax check) — the most important gate."""
    env = Environment(autoescape=False)
    env.parse(SRC)  # raises TemplateSyntaxError on failure


def test_seo_description_names_selective_readiness_product() -> None:
    """SEO copy names the selective entry shelf rather than an old single archetype."""
    # Extract the mode=stocks seo_desc assignment
    m = re.search(r"seo_desc = '([^']+)'", SRC)
    assert m, "seo_desc not found in mode=stocks block"
    desc = m.group(1)
    assert "selective" in desc.lower() and "readiness" in desc.lower()
    assert "T1–T3" in desc
    # Must NOT lead with 'reversal' or 'low-vol' as the product description
    # (those are separate products per F5 ruling)
    assert "reversal and low-vol reads" not in desc.lower(), (
        f"SEO desc still advertises 'reversal and low-vol reads': {desc!r}"
    )


def test_stocks_header_names_washout_base_turn() -> None:
    """Stocks header must describe the washed-out → fresh-turn archetype (plain wording).

    2026-07-10 operator declutter: the archetype description moved into the h1
    help() tooltip and was re-worded to plain English ("sold off hard") — the
    intent (header names the sold-off/washed-out archetype) is unchanged.
    """
    html = _render_stocks_header()
    low = html.lower()
    assert "washed-out" in low or "washout" in low or "sold off hard" in low, (
        "Header does not name the washed-out archetype"
    )
    assert "turn" in html.lower() or "转向" in html, (
        "Header does not mention the fresh turn"
    )
    # Must NOT claim the archetype is mean-reversion
    assert "mean-reversion setups" not in html, (
        "Header still claims 'mean-reversion setups' (old copy)"
    )


def test_standout_h2_selective_v2_copy_present_and_old_subtitle_gone() -> None:
    """The explainer states selective admission, in plain words, and keeps the weights.

    Operator order 2026-08-02 ("simplify and dumb down"): the 150-word paragraph of
    study vocabulary became a rich LENS card. The admission set is now named in
    plain words — Signal / Entry / Tradable / Not chased — instead of "an actionable
    T1-T3 confluence ... no chase veto, no extension flag", and the weights moved to
    the receipt line where DESIGN_DOCTRINE Law 5 puts them. Selectivity and the
    weights are still stated; only the vocabulary changed.
    """
    html = _render_standout_header()
    assert "Only the ready ones" in html, "explainer no longer states selective admission"
    for criterion in ("Signal", "Entry", "Tradable", "Not chased"):
        assert f">{criterion}</span>" in html, f"admission criterion '{criterion}' missing"
    assert "signal 35%" in html.lower(), "priority weights missing from the receipt line"
    # Old subtitle chip strings must NOT come back.
    assert "cycle-aligned bottoming" not in html, (
        "Old 'cycle-aligned bottoming' subtitle chip still present"
    )
    assert "weekly + 3-day + daily turning up" not in html, (
        "Old weekly-3d-daily alignment subtitle chip still present"
    )


def test_standout_help_contains_v2_epistemic_caveats() -> None:
    """The popup distinguishes priority from prediction and exposes the broader set."""
    html = _render_standout_header()
    assert "not a win rate and not a return forecast" in html.lower()
    assert "accruing" in html.lower() or "累积" in html, (
        "forward record accrual caveat not found"
    )
    assert "broader and blocked names stay below" in html.lower()


def test_standout_help_describes_actionable_tiers() -> None:
    """The explainer must identify the admission set — in plain words, not tier codes.

    "T1-T3 confluence" was internal vocabulary on a user surface; the plain-word
    equivalent is the four named criteria. The tier codes stay available on the
    Tier-3 detail pages.
    """
    html = _render_standout_header()
    assert "Several timeframes agree" in html, "multi-timeframe admission criterion missing"
    assert "The entry window is open today" in html, "entry-lifecycle criterion missing"
    assert "T1–T3" not in html, "internal tier codes are back on the glance surface"


def test_standout_help_says_rank_not_bottoming_alignment() -> None:
    """Help must NOT describe the board as a bottoming-alignment screen."""
    html = _render_standout_header()
    # Positive control: the tooltip actually rendered (readiness is its live rank
    # driver) — the two absence pins below are real absences, not a vacuous empty render.
    assert "how ready" in html.lower() or "就绪程度" in html, (
        "standout tooltip did not render (absence checks would be vacuous)"
    )
    assert "MULTI-TIMEFRAME BOTTOMING-ALIGNMENT" not in html, (
        "Old 'MULTI-TIMEFRAME BOTTOMING-ALIGNMENT screen' copy still present"
    )
    assert "Ranked by alignment quality" not in html, (
        "Old 'Ranked by alignment quality' copy still present"
    )


def test_standfirst_paragraph_honest() -> None:
    """Header must name the honest priority/readiness rank driver."""
    html = _render_standout_header()
    # Must name the honest driver: buy-readiness, or the T1–T4 cascade in the subtitle
    assert (
        "how ready" in html.lower() or "就绪程度" in html
    ), "Header does not name the honest readiness rank"
    # Must not claim ranked by 'alignment quality'
    assert "Ranked by alignment quality" not in html, (
        "Old alignment-quality ranking claim still present"
    )


def test_bilingual_dual_spans_present() -> None:
    """Rendered output must contain both l-en and l-zh spans (bilingual compliance)."""
    html = _render_stocks_header() + _render_standout_header()
    assert 'class="l-en"' in html or "l-en" in html, "No l-en spans found"
    assert 'class="l-zh"' in html or "l-zh" in html, "No l-zh spans found"
    assert "精选入场" in html and "就绪程度" in html


def test_no_t_call_inside_attributes_in_changed_blocks() -> None:
    """The i18n gotcha: t() must never appear inside an HTML attribute value.

    Checks the two changed regions: stocks-header block and standout h2/standfirst.
    """
    # Extract stocks-header block
    start = SRC.index("<!-- ===================== A-SHARE STOCK DASHBOARD HEADER")
    end = SRC.index("  {% if mode != 'stocks' %}", start)
    header_block = SRC[start:end]

    # Extract standout header up to the data-outage banner (W-FCT anchor — the panel
    # <div> now carries data-stfacet=, so the old id="standouts" literal no longer matches)
    ss = SRC.index(STANDOUT_START)
    se = SRC.index(STANDOUT_END, ss)
    standout_block = SRC[ss:se]

    for name, block in [("header", header_block), ("standout", standout_block)]:
        bad = re.search(
            r'(?:title|style|data-[a-z]+|aria-[a-z]+|class)="[^"]*\{\{\s*t\(', block
        )
        assert not bad, (
            f"t() found inside an HTML attribute in the {name} block: {bad.group()!r}"
        )


def test_no_straight_reversal_claims_in_standout_header() -> None:
    """The standout section must not claim 'reversal' is the ranking mechanism.

    The reversal-tiebreaker standfirst copy did NOT move to another surface — it was
    deleted outright in favour of the honest 'buy-readiness' rank driver (2026-07-21).
    So this stays an absence pin, guarded by a positive control naming the driver that
    replaced it.
    """
    html = _render_standout_header()
    # Positive control: the honest readiness driver IS present — proves the
    # header rendered, so the reversal-tiebreaker absence below is a real absence.
    assert "how ready" in html.lower() or "就绪程度" in html, (
        "honest readiness rank missing (absence check would be vacuous)"
    )
    # The old standfirst mentioned 'A-share reversal / relative-strength leg only as a tiebreaker'
    assert "reversal / relative-strength leg only as a tiebreaker" not in html, (
        "Old reversal-tiebreaker copy still present"
    )
