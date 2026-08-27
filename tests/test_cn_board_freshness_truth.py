"""The CN board must tell the truth about its own freshness.

The CN twin of tests/test_us_board_freshness_truth.py (PR #6532).  The US board was read
as five days stale and a force-majeure was declared over it; what the reader had actually
seen was the per-card zone-row date chip, which is neither the zone's vintage nor a
per-card fact.  templates/china.html.j2 carried the same unlabelled-date pattern in the
same shared ``#stocks-header`` family.  Measured by RENDERING the shipped artifacts
through the branch-point template:

  · the card chip printed ``(n.signal).asof or setups.as_of``, and on all three boards
    checked every rendered chip was the board's own ``as_of``: 85 chips all reading
    "Aug 26" on the 2026-08-26 board, 55 all "Aug 25" on 08-25, 43 all "Aug 24" on
    08-24.  One constant, verbatim, once per card, directly beneath a header that had
    already stated it.
  · the date was never the zone's vintage — zones are recomputed every session.  08-24
    -> 08-25, 49 of the 50 tickers carrying a zone on both boards had ``low``/``high``
    move (1 held); 08-25 -> 08-26, 34 of 36 moved.  The one thing a reader would
    reasonably take a date beside the zone numbers to mean is the one thing it never
    meant.
  · the ``signal.asof`` leg was a LIVE hazard rather than a shipped defect, and this
    suite pins it shut before it can become one.  Today the only rows carrying that key
    sit on ``laggards``, which renders no cards — but the artifact's values there are
    genuinely older (``2026-08-21`` on the 08-25 board, four sessions behind it).  Had
    such a row reached a carded shelf, one bare slot would have shown two clocks side by
    side with nothing to tell them apart.

DESIGN_DOCTRINE Law 4 ("one as-of stamp per panel"; "no per-row repetition of a
constant") and Law 3 ("a number on Tier 1 arrives with its interpretation") both land on
the same fix, and this suite pins all three halves of it:

  1. the board card carries NO bare date in the zone row, even when the row has one;
  2. the page header states the vintage in plain words — "Data through <date>" — across
     the CN board's THREE-state ladder, and carries a machine-readable twin on the board
     container for monitors;
  3. the delayed banner keeps firing on the engine's own ``board_staleness.delayed``
     verdict and NEVER on a healthy board.

WHY THE CN WIRING IS NOT A COPY OF THE US ONE.  ``compute_board_staleness`` (CN) and
``_compute_board_staleness`` (US) publish different blocks, and this suite is written
against the CN one as shipped:

  · CN nests the session count at ``inputs.sessions_behind``; there is no top-level
    ``sessions_behind``, no ``unknown``, and no ``basis`` key.
  · CN's fail-soft sentinel is ``{price_through: None, age_days: None, delayed: False}``
    — it SUPPRESSES the disclosure, where the US fail-soft reports DELAYED (unknown).
    So "no verdict" renders a plain board here, and the tests below say so rather than
    importing the US expectation.
  · the CN verdict is computed against the A-share calendar (lib/cn_calendar.py), not
    the NYSE one, which is why the machine-readable twin publishes the ENGINE's verdict:
    a monitor doing client-side day arithmetic would read Golden Week and Spring Festival
    — legitimately ~10 sessionless calendar days — as a ten-day outage.
  · the CN pill has a THIRD state the US pill does not have (partial collection), so it
    gets a third attribute and a third label rather than being flattened into two.

Import-light on purpose: the two harnesses reused here (the delayed-disclosure page
render and the unified-grid fixtures) need neither pandas nor plotly, so this suite runs
in any lane that can import jinja2.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import i18n  # noqa: E402
from tests.test_china_delayed_board_disclosure import _Loose  # noqa: E402
from tests.test_cn_board_unified_grid import v2_setups  # noqa: E402

# The board's own vintage, in the shape scripts/build_china.py hands the template.
# SIGNAL_ASOF is deliberately NOT equal to it: the whole defect was the two clocks being
# printed in one bare slot as though they were one.
ASOF = "2026-08-26"
SIGNAL_ASOF = "2026-08-21"

PV_DT = re.compile(r'<span class="pv-dt">')
SU_PANEL = re.compile(r'<div class="panel span12" id="standouts"[^>]*>')
# The banner ELEMENT text, not a class name — china.html.j2 styles the delayed panel
# inline, and "BOARD DELAYED" is the string a reader actually sees.
STALE_BANNER = "BOARD DELAYED"
# Attribute VALUES carry the Tier-2 copy (data-tip-en/zh), which legitimately holds the
# demoted entry-signal date.  Strip attributes to ask what a reader SEES without hovering.
ATTRS = re.compile(r'\s[a-zA-Z-]+="[^"]*"')

HEALTHY = {"price_through": ASOF, "age_days": 0, "delayed": False,
           "inputs": {"csi300_through": ASOF, "expected_session": ASOF,
                      "sessions_behind": 0, "backstop_days": 11}}
# The shape of the outage the CN disclosure exists for: board frozen four sessions back.
DELAYED = {"price_through": "2026-08-20", "age_days": 6, "delayed": True,
           "inputs": {"csi300_through": "2026-08-20", "expected_session": ASOF,
                      "sessions_behind": 4, "backstop_days": 11}}
# compute_board_staleness's literal fail-soft return when the anchor is unreadable.
SUPPRESSED = {"price_through": None, "age_days": None, "delayed": False}


def _setups(*, as_of: str | None = ASOF, signal_asof: str | None = SIGNAL_ASOF,
            partial: bool = False, coverage: bool = True,
            staleness: dict | None = None) -> dict:
    """A cn_prophet_v2-shaped artifact with the freshness keys the header reads.

    Rows come from the unified-grid fixture so the cards this suite inspects are the same
    cards that suite already pins — a date that came back would fail in both places.
    """
    su = v2_setups()
    for shelf in ("buy", "more_actionable", "late_or_unfillable", "forming"):
        for row in su.get(shelf) or []:
            if signal_asof:
                row["signal"]["asof"] = signal_asof
            else:
                row["signal"].pop("asof", None)
    if as_of is not None:
        su["as_of"] = as_of
    else:
        su.pop("as_of", None)
    if coverage:
        # `data_through` is the board's own settled-session anchor (CSI300 last bar) and is
        # the same value compute_board_staleness reports as `price_through`; the fixture
        # keeps them equal because production does.
        su["coverage"] = {"as_of": as_of, "data_through": as_of,
                          "partial_session": partial}
    if staleness is not None:
        su["staleness"] = staleness
    return su


def _render(staleness: dict | None, *, mode: str = "stocks", setups: dict | None = None) -> str:
    """Render the REAL china.html.j2 — the whole page, not a slice.

    All three truths live on one page (header pill, board container, cards), so proving
    them against one render is what proves they agree with each other.
    """
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=False, undefined=ChainableUndefined)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("china.html.j2").render(
        mode=mode,
        board_staleness=staleness,
        setups=_setups() if setups is None else setups,
        latest=_Loose(date=ASOF, quad_name="Goldilocks"),
        market_state=_Loose(color="yellow"),
        sectors=[],
    )


def _header(html: str) -> str:
    """The header pill region only — everything from #stocks-header to the Regime pill."""
    seg = html.split('id="stocks-header"', 1)[1]
    return seg[:seg.index("Regime")]


# --------------------------------------------------------------------------- #
# 1 · the card stops printing a date against numbers on a different clock
# --------------------------------------------------------------------------- #

def test_board_cards_print_no_bare_date_even_when_the_rows_carry_one():
    """The hazard pin — the case the shipped boards did NOT exercise.

    On the live artifact the only rows carrying `signal.asof` sit on `laggards`, which
    renders no cards, so the signal leg never reached a chip.  This fixture puts one on a
    carded shelf anyway: a row WITH signal.asof must still render no `.pv-dt`.  The value
    stays untouched in the artifact — it simply is not the zone's vintage and no longer
    sits against the zone's numbers."""
    html = _render(HEALTHY)
    assert "pvcard" in html, "fixture must actually produce cards"
    assert PV_DT.search(html) is None, (
        "the zone row printed a bare date again — that date is either the board's own "
        "as_of reprinted per row or a 3-session entry-signal bucket, and neither is the "
        "vintage of the buy-zone numbers beside it"
    )


def test_the_fallback_path_stops_reprinting_the_boards_own_as_of_on_every_card():
    """The pin for what ACTUALLY shipped.  Every rendered chip on the last three boards
    came from the `or setups.as_of` fallback — 85 / 55 / 43 copies of the header's own
    vintage.  Removing only the signal leg would have left that constant untouched, so
    this fixture strips signal.asof entirely and demands the chip stay gone."""
    html = _render(HEALTHY, setups=_setups(signal_asof=None))
    assert "pvcard" in html
    assert PV_DT.search(html) is None


def test_neither_clock_leaks_back_onto_a_card_in_any_rendered_form():
    """The macro renders the date FORMATTED ("Aug 21" / "08-21"), never as raw ISO, so an
    ISO-only assertion would pass against the very markup this pin forbids."""
    html = _render(HEALTHY)
    cards = html[html.index('id="standouts"'):]
    cards = ATTRS.sub("", cards[:cards.index("BOARD TRACK RECORD")] if "BOARD TRACK RECORD" in cards else cards)
    for leaked in (SIGNAL_ASOF, "Aug 21", "08-21", "Aug 26", "08-26"):
        assert leaked not in cards, f"a board date leaked back into the card grid: {leaked!r}"


def test_removing_the_date_did_not_take_the_zone_numbers_with_it():
    """The numbers are the point; only the date beside them was wrong."""
    html = _render(HEALTHY)
    assert "11.00" in html and "12.50" in html, "the buy-zone numbers vanished with the date"


def test_the_shared_macro_keeps_full_date_support():
    """The fix belongs at the two CN callers that were lying, never in _prophet_card's
    shared `pv_card` macro — other callers pass dates that ARE per-row and honest."""
    src = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
    assert 'class="pv-dt"' in src, (
        "the date slot was deleted from the shared macro rather than from the CN board's "
        "two pv_card calls"
    )


def test_the_two_cn_callers_pass_an_explicit_none():
    """Kept as an explicit `none` rather than a deleted key so the slot reads as a
    decision rather than an oversight — and so a future edit has something to trip over."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    assert src.count("'date': none,") == 2, "both CN board pv_card calls must pass 'date': none"
    assert "'date': (n.signal or {}).get('asof')" not in src


# --------------------------------------------------------------------------- #
# 2 · the board states its vintage in plain words, once
# --------------------------------------------------------------------------- #

def test_header_labels_the_vintage_in_both_languages():
    html = _render(HEALTHY)
    assert ">Data through</span>" in html, "the header stopped naming what its date is the date OF"
    assert ">数据截至</span>" in html, "ZH lost the vintage label (bilingual parity)"
    assert f"<strong>{ASOF}</strong>" in html


def test_header_vintage_is_the_boards_own_date_not_the_signal_bucket():
    """The two clocks must never be swapped back.  Judged on VISIBLE text only: the
    signal date is allowed to live in this chip's hover (its demoted home), but it must
    never be the number a reader sees without hovering."""
    visible = ATTRS.sub("", _header(_render(HEALTHY)))
    assert ASOF in visible
    assert SIGNAL_ASOF not in visible, (
        "the header prints the entry-signal bucket date as the board's vintage — the "
        "exact confusion this change exists to end"
    )


def test_delayed_header_keeps_a_word_not_just_a_colour():
    """The amber pill must never be the only carrier of the warning."""
    html = _render(DELAYED)
    assert ">Delayed · data through</span>" in html
    assert ">数据延迟 · 数据截至</span>" in html


def test_the_zh_delayed_word_matches_the_zh_banner_on_the_same_page():
    """One page, one name for one state: the banner at the top of the grid says 数据延迟,
    so the pill must not invent a second word for the same condition."""
    html = _render(DELAYED)
    assert STALE_BANNER in html and "数据延迟" in html
    assert "已延迟" not in html, "the US board's ZH wording leaked onto the CN page"


def test_partial_collection_keeps_its_own_third_state_and_is_labelled_too():
    """The CN ladder has three rungs, not the US two.  A partly-collected session is a
    real, separately-caused degrade and must not be flattened into either neighbour."""
    html = _render(HEALTHY, setups=_setups(partial=True))
    assert ">Partial data · data through</span>" in html
    assert ">数据不全 · 数据截至</span>" in html
    assert STALE_BANNER not in html, "a partial session is not a delayed board"


def test_delayed_outranks_partial_when_both_fire():
    """Most severe first — the pill's pre-existing precedence, kept."""
    html = _render(DELAYED, setups=_setups(partial=True, staleness=DELAYED))
    assert ">Delayed · data through</span>" in html
    assert "Partial data" not in _header(html)


def test_header_falls_back_cleanly_when_the_board_has_no_date_at_all():
    """A degraded artifact carries no vintage; the header must still render a state
    rather than an empty label."""
    su = _setups(as_of=None, coverage=False)
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=False, undefined=ChainableUndefined)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china.html.j2").render(
        mode="stocks", board_staleness=SUPPRESSED, setups=su,
        latest=_Loose(quad_name="Goldilocks"),     # no date either
        market_state=_Loose(color="yellow"), sectors=[])
    hdr = _header(html)
    assert "Data through" not in hdr, "an empty label is worse than the bare state word"
    assert ">Fresh</span>" in hdr, "the no-date fallback must still name a state"


def test_header_hover_explains_the_clock_and_names_the_demoted_signal_date():
    """The bucket date is demoted, not deleted (DESIGN_DOCTRINE §1 demotion rule) — it
    lives on the board-level element, once, where it is true."""
    tip = _header(_render(HEALTHY)).split('data-tip-en="', 1)[1].split('"', 1)[0]
    assert "rebuilt every session" in tip
    assert SIGNAL_ASOF in tip, "the entry-signal bucket date lost its Tier-2 home"


def test_header_hover_stays_silent_when_the_board_disagrees_on_one_signal_date():
    """Self-falsifying: the sentence generalises ONE value to the whole board, so it may
    only render when the whole board actually carries that one value.  If a future
    artifact makes signal.asof per-card, the clause disappears instead of lying."""
    su = _setups()
    su["more_actionable"][0]["signal"]["asof"] = "2026-08-18"
    tip = _header(_render(HEALTHY, setups=su)).split('data-tip-en="', 1)[1].split('"', 1)[0]
    assert "2026-08-21" not in tip and "2026-08-18" not in tip


def test_header_hover_stays_silent_when_the_signal_date_equals_the_board_vintage():
    """The CN-specific guard the US twin does not need.  On the 2026-08-26 board the 12
    rows carrying a signal.asof carry the board's OWN date, so "a card can carry a signal
    older than the board" would be false — the clause must not render there."""
    tip = _header(_render(HEALTHY, setups=_setups(signal_asof=ASOF))).split(
        'data-tip-en="', 1)[1].split('"', 1)[0]
    assert "older than the board" not in tip
    assert "rebuilt every session" in tip, "the base sentence must survive"


def test_header_hover_stays_inside_the_tier_2_word_budget():
    """DESIGN_DOCTRINE §1: a Tier-2 tip is ~80 words.  This one grows a clause per state,
    so it is exactly the copy that drifts past the budget if nothing counts it."""
    for stale, su in ((DELAYED, _setups(staleness=DELAYED)),
                      (HEALTHY, _setups(partial=True))):
        tip = _header(_render(stale, setups=su)).split('data-tip-en="', 1)[1].split('"', 1)[0]
        assert len(tip.split()) <= 80, f"Tier-2 tip is {len(tip.split())} words: {tip}"


# --------------------------------------------------------------------------- #
# 3 · machine-readable twin, for monitors that grade the RENDERED page
# --------------------------------------------------------------------------- #

def test_board_container_carries_the_machine_readable_vintage():
    panel = SU_PANEL.search(_render(HEALTHY))
    assert panel, "#standouts board container missing"
    assert f'data-board-asof="{ASOF}"' in panel.group(0)
    assert 'data-board-delayed="0"' in panel.group(0)
    assert 'data-board-partial="0"' in panel.group(0)


def test_the_twin_tracks_the_engines_delayed_verdict():
    panel = SU_PANEL.search(_render(DELAYED, setups=_setups(staleness=DELAYED)))
    assert 'data-board-delayed="1"' in panel.group(0)
    assert 'data-board-partial="0"' in panel.group(0), (
        "delayed and partial are independent conditions; a delayed board is not "
        "automatically a partly-collected one"
    )


def test_the_twin_publishes_the_partial_state_separately():
    """Without this a monitor reading data-board-delayed="0" would call a partly-collected
    board healthy while the header says "Partial data" in words."""
    panel = SU_PANEL.search(_render(HEALTHY, setups=_setups(partial=True)))
    assert 'data-board-delayed="0"' in panel.group(0)
    assert 'data-board-partial="1"' in panel.group(0)


def test_the_twin_is_absent_when_the_board_has_no_vintage():
    """Absence is the honest signal — a monitor must not read a stale attribute off a
    board that has no date behind it."""
    su = _setups(as_of=None, coverage=False)
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=False, undefined=ChainableUndefined)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china.html.j2").render(
        mode="stocks", board_staleness=SUPPRESSED, setups=su,
        latest=_Loose(quad_name="Goldilocks"),
        market_state=_Loose(color="yellow"), sectors=[])
    panel = SU_PANEL.search(html)
    assert panel and "data-board-asof" not in panel.group(0)


def test_the_attribute_agrees_with_the_words_in_the_header():
    """One clock, two readers: a monitor grading the attribute and a human reading the
    header must never be able to disagree."""
    html = _render(HEALTHY)
    attr = re.search(r'data-board-asof="([^"]+)"', html).group(1)
    assert f"<strong>{attr}</strong>" in _header(html)


def test_the_delayed_attribute_agrees_with_the_banner():
    """The other half of the same agreement: a monitor must never read `delayed="0"` off
    a page that is showing a BOARD DELAYED banner."""
    html = _render(DELAYED, setups=_setups(staleness=DELAYED))
    assert STALE_BANNER in html
    assert 'data-board-delayed="1"' in SU_PANEL.search(html).group(0)

    healthy = _render(HEALTHY)
    assert STALE_BANNER not in healthy
    assert 'data-board-delayed="0"' in SU_PANEL.search(healthy).group(0)


def test_the_facet_attribute_survived_the_addition():
    """tests/test_china_stf_facets.py pins the literal
    `id="standouts" data-stfacet="{{ _stf_default }}"` in the SOURCE — the new attributes
    must be appended after it, never inserted between."""
    src = (ROOT / "templates" / "china.html.j2").read_text()
    assert 'id="standouts" data-stfacet="{{ _stf_default }}"' in src


# --------------------------------------------------------------------------- #
# 4 · the delayed banner, and the state it must never fire on
# --------------------------------------------------------------------------- #

def test_banner_is_invisible_on_a_healthy_board():
    """The single most likely false alarm.  The banner reads the ENGINE's verdict, never a
    client-side day count, so Golden Week and Spring Festival — legitimately ~10
    sessionless calendar days on the A-share calendar — cannot manufacture one."""
    assert STALE_BANNER not in _render(HEALTHY)


def test_banner_appears_when_the_engine_says_the_board_is_delayed():
    html = _render(DELAYED, setups=_setups(staleness=DELAYED))
    assert STALE_BANNER in html
    assert "prices as of 2026-08-20" in html, (
        "scripts/freshness_sentinel.py::_DELAY_RE is a load-bearing contract with this "
        "exact English phrasing"
    )


def test_banner_stays_suppressed_on_the_fail_soft_sentinel():
    """CN's fail-soft differs from the US board's on purpose: an unreadable anchor
    SUPPRESSES the CN disclosure (delayed=False, price_through=None) rather than
    declaring an unknown-delay.  Pinned so the difference is a decision, not a drift."""
    html = _render(SUPPRESSED)
    assert STALE_BANNER not in html


# --------------------------------------------------------------------------- #
# 5 · house law that binds every user-facing change here
# --------------------------------------------------------------------------- #

def test_no_translated_text_in_title_attributes_on_the_new_markup():
    """CI-guarded house law (scripts/check_title_i18n.py); asserted locally too so a
    failure names the reason rather than arriving as a distant lint."""
    html = _render(DELAYED, setups=_setups(staleness=DELAYED, partial=True))
    for m in re.finditer(r'title="([^"]*)"', html):
        assert not re.search(r"[一-鿿]", m.group(1)), (
            f"translated text inside a title= attribute: {m.group(1)!r}"
        )


def test_the_new_header_copy_is_bilingual_on_every_rung_of_the_ladder():
    """Bilingual parity (DESIGN_DOCTRINE §5.5): every state ships both languages."""
    for html, en, zh in (
        (_render(HEALTHY), "Data through", "数据截至"),
        (_render(HEALTHY, setups=_setups(partial=True)), "Partial data · data through",
         "数据不全 · 数据截至"),
        (_render(DELAYED, setups=_setups(staleness=DELAYED)), "Delayed · data through",
         "数据延迟 · 数据截至"),
    ):
        assert f'<span class="l-en">{en}</span><span class="l-zh">{zh}</span>' in html, en
