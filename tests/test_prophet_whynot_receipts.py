"""tests/test_prophet_whynot_receipts.py — ANTICIPATION §6.9 R5 "why not" receipts.

Covers the three pieces of the per-name refusal shelf:

  1. ``engine.prophet_bridge.refusal_receipts`` — the ONE grouping function both the
     macro dashboard and ``scripts/build_prophet.py`` call,
  2. ``templates/_prophet_receipts.html.j2`` — the shelf partial, and
  3. the wiring that connects them (``scripts/build_site.py`` view-model key,
     ``templates/dashboard.html.j2`` import/CSS/shelf call, the published
     ``intake.receipts`` block).

WHY THIS SUITE IS BROWSER-FREE. The CI packs install a minimal dependency set, not
``requirements.txt`` — a ``pytest.importorskip("playwright")`` here would SKIP in CI and
report green while proving nothing. Everything asserted below is mechanically checkable
against the rendered template and the shipped source text. The design measurements that
genuinely need a browser (both themes, the caret rotation, chip wrapping) were made by
hand before the spec was frozen.

WHY NOTHING HERE READS site/factordata/us_standouts.json. That artifact is rewritten
every night, so pinning tonight's tickers or counts would be a SCHEDULED red — the
house's append-only-store-pinned-by-equality trap. Every fixture below is synthetic, and
the live board is used only as one-off evidence in the PR body.

The assertions are about LAWS, not wording:
  · the headline is SPECIFICITY-ordered, never gate-ordered (the regression that matters
    most — see test_extended_and_band_low_headlines_the_anti_chase_reason),
  · an unmapped status FAILS CLOSED to the generic line and never drops the row,
  · the copy table is complete, bilingual, and identical in the engine and the template,
  · a capped group still reports its TRUE count,
  · the surface leaks no internal token and carries no `title=` attribute,
  · absent context renders the empty string.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.prophet_bridge import (  # noqa: E402
    ADMITTED_STATUSES,
    REFUSAL_COPY,
    REFUSAL_NAMES_CAP,
    REFUSAL_NEAR,
    REFUSAL_ORDER,
    REFUSAL_STATUS_MAP,
    SELECTION_ERA,
    _KNOWN_REFUSED_STATUSES,
    refusal_receipts,
    select_candidates,
)

DASH = (ROOT / "templates" / "dashboard.html.j2").read_text()
BUILD_SITE = (ROOT / "scripts" / "build_site.py").read_text()
BUILD_PROPHET = (ROOT / "scripts" / "build_prophet.py").read_text()


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _row(ticker: str, *, status: str = "buy_now", band: str = "high",
         direction: str = "up", tier: str | None = "T1", score: float = 50.0,
         entry_signal: bool = True, name: str | None = None) -> dict:
    """One us_standouts ``buy[]`` row, only the fields admission actually reads."""
    return {
        "ticker": ticker,
        "name": name or f"{ticker} Industries",
        "dir": direction,
        "entry_signal": {"status": status} if entry_signal else None,
        "conviction": {"band": band},
        "signal": {"tier_cascade": tier},
        "prophet": {"score": score},
    }


def _board(*rows: dict) -> dict:
    return {"buy": list(rows)}


def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.py's Jinja env for the pieces this partial uses.

    autoescape=True matters: the hover disclosure interpolates company names into an
    attribute, and the production env escapes them. A test env without autoescape would
    prove the wrong thing about an apostrophe.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n  # noqa: PLC0415 — same import site as build_site.py
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


def _shelf(cx) -> str:
    return str(_env().get_template("_prophet_receipts.html.j2").module.pvr_shelf(cx))


def _headline(cx: dict, ticker: str) -> str:
    for group in cx["groups"]:
        for nm in group["names"]:
            if nm["ticker"] == ticker:
                return group["reason"]
    raise AssertionError(f"{ticker} produced no receipt: {cx}")


def _why(cx: dict, ticker: str) -> list[str]:
    for group in cx["groups"]:
        for nm in group["names"]:
            if nm["ticker"] == ticker:
                return nm["why"]
    raise AssertionError(f"{ticker} produced no receipt: {cx}")


# --------------------------------------------------------------------------- #
# 1. Grouping — the shape the surface consumes
# --------------------------------------------------------------------------- #

def test_groups_follow_refusal_order_and_omit_empties():
    """Groups arrive in REFUSAL_ORDER order, empty codes omitted."""
    cx = refusal_receipts(_board(
        _row("DOWN", direction="down"),
        _row("STOP", status="avoid"),
        _row("HOT", status="extended", band="high"),
        _row("SOON", status="buy_soon"),
        _row("OK"),                      # admitted, no origination knowledge → no receipt
    ))
    assert [g["reason"] for g in cx["groups"]] == [
        "not_ready", "ran_too_far", "stood_down", "pointing_down"]
    order = list(REFUSAL_ORDER)
    positions = [order.index(g["reason"]) for g in cx["groups"]]
    assert positions == sorted(positions)


def test_headline_counts_and_near_flag():
    cx = refusal_receipts(_board(
        _row("AAA", status="buy_soon"),
        _row("BBB", status="extended"),
        _row("CCC"),
    ))
    assert cx["considered"] == 3
    assert cx["passed"] == 2
    assert cx["planned"] == 1
    assert cx["unmapped"] == 0
    near = {g["reason"]: g["near"] for g in cx["groups"]}
    assert near == {"not_ready": True, "ran_too_far": False}
    assert REFUSAL_NEAR == frozenset({"plan_not_built", "already_open", "not_ready"})


def test_names_sort_by_score_desc_then_ticker():
    cx = refusal_receipts(_board(
        _row("ZZZ", status="watch", score=90),
        _row("AAA", status="watch", score=90),
        _row("MMM", status="watch", score=95),
        _row("NNN", status="watch", score=None),   # missing score → 0, sorts last
    ))
    group = cx["groups"][0]
    assert [n["ticker"] for n in group["names"]] == ["MMM", "AAA", "ZZZ", "NNN"]
    assert group["names"][-1]["score"] == 0


def test_every_gate_is_reported():
    """One row per gate — the five admission gates each produce their own code."""
    cx = refusal_receipts(_board(
        _row("NOSIG", entry_signal=False, band="high", tier="T1"),
        _row("BEARISH", direction="down"),
        _row("WEAKBAND", band="low"),
        _row("LOWTIER", tier="T4"),
        _row("STRETCH", status="extended"),
    ))
    assert _headline(cx, "NOSIG") == "no_trigger"
    assert _headline(cx, "BEARISH") == "pointing_down"
    assert _headline(cx, "WEAKBAND") == "conviction_low"
    assert _headline(cx, "LOWTIER") == "grade_low"
    assert _headline(cx, "STRETCH") == "ran_too_far"


def test_admitted_rows_need_an_origination_answer_before_they_get_a_receipt():
    """A cleared row produces a receipt only when the caller can say what happened.

    build_site knows the gate but not tonight's origination run, so it passes
    ``originated_tickers=None`` and a cleared row is simply absent — an invented
    "the plan wouldn't build" line would be a claim it cannot support.
    """
    board = _board(_row("CLEAR"), _row("LIVE"))
    blind = refusal_receipts(board, open_keys=())
    assert blind["passed"] == 0
    assert blind["groups"] == []

    knowing = refusal_receipts(board, open_keys=("LIVE-BULL",),
                               originated_tickers=set())
    assert _headline(knowing, "LIVE") == "already_open"
    assert _headline(knowing, "CLEAR") == "plan_not_built"

    originated = refusal_receipts(board, open_keys=(),
                                  originated_tickers={"CLEAR", "LIVE"})
    assert originated["passed"] == 0

    # build_site hands bare tickers rather than <TICKER>-<DIRECTION> keys; both work.
    bare = refusal_receipts(board, open_keys=("LIVE",))
    assert _headline(bare, "LIVE") == "already_open"


def test_open_key_normalisation_never_truncates_a_hyphenated_ticker():
    """``BRK-B`` must not inherit ``BRK``'s open plan (or the reverse)."""
    cx = refusal_receipts(_board(_row("BRK"), _row("BRK-B")),
                          open_keys=("BRK-B-BULL",), originated_tickers=set())
    assert _headline(cx, "BRK-B") == "already_open"
    assert _headline(cx, "BRK") == "plan_not_built"


# --------------------------------------------------------------------------- #
# 2. Exhaustiveness — the copy table is complete and bilingual
# --------------------------------------------------------------------------- #

def test_every_order_code_has_non_empty_bilingual_copy():
    assert set(REFUSAL_COPY) == set(REFUSAL_ORDER)
    for code in REFUSAL_ORDER:
        en, zh = REFUSAL_COPY[code]
        assert en.strip(), code
        assert zh.strip(), code
        assert en != zh, code          # a ZH slot holding the EN string is a missing translation
        assert re.search(r"[一-鿿]", zh), code


def test_every_status_map_value_is_an_order_code():
    for status, code in REFUSAL_STATUS_MAP.items():
        assert code in REFUSAL_ORDER, (status, code)


def test_near_codes_are_order_codes():
    assert REFUSAL_NEAR <= set(REFUSAL_ORDER)


def test_template_copy_mirrors_the_engine_copy_exactly():
    """The partial carries its own copy map (a chip hover must be able to word EVERY
    code in a row's ``why`` list, including codes that head no group tonight). It is a
    MIRROR, and this is the pin that keeps it one."""
    mod = _env().get_template("_prophet_receipts.html.j2").module
    assert {k: tuple(v) for k, v in mod.pvr_copy.items()} == REFUSAL_COPY


# --------------------------------------------------------------------------- #
# 3. Fail-closed — an unmapped status is disclosed, never dropped
# --------------------------------------------------------------------------- #

def test_invented_status_falls_closed_to_the_generic_line():
    cx = refusal_receipts(_board(_row("WOBBLE", status="quantum_wobble")))
    assert cx["considered"] == 1
    assert cx["passed"] == 1            # NOT dropped
    assert cx["unmapped"] == 1          # and the drift is counted
    assert _headline(cx, "WOBBLE") == "unknown"
    group = cx["groups"][0]
    assert group["en"] == "Held back for another reason"
    assert group["zh"] == "另有原因，暂未纳入"
    assert group["near"] is False
    assert "quantum_wobble" not in _shelf(cx)


def test_invented_status_renders_without_raising():
    html = _shelf(refusal_receipts(_board(_row("WOBBLE", status="quantum_wobble"))))
    assert "Held back for another reason" in html
    assert "WOBBLE" in html


def test_unknown_is_last_in_the_specificity_order():
    """A row with a real blocker AND an unmapped status headlines the real blocker."""
    cx = refusal_receipts(_board(_row("ODD", status="quantum_wobble", band="low")))
    assert _headline(cx, "ODD") == "conviction_low"
    assert _why(cx, "ODD") == ["conviction_low", "unknown"]
    assert cx["unmapped"] == 0          # `unmapped` counts HEADLINES, not mentions


def test_malformed_rows_do_not_crash_the_shelf():
    cx = refusal_receipts({"buy": [None, "AAPL", 7, _row("GOOD", status="watch")]})
    assert cx["considered"] == 4
    assert _headline(cx, "GOOD") == "not_ready"
    assert refusal_receipts(None)["groups"] == []
    assert refusal_receipts({})["considered"] == 0
    assert refusal_receipts({"buy": None})["considered"] == 0


# --------------------------------------------------------------------------- #
# 4. THE REGRESSION THAT MATTERS — specificity order, not gate order
# --------------------------------------------------------------------------- #

def test_extended_and_band_low_headlines_the_anti_chase_reason():
    """A row that is BOTH band-low AND `extended` headlines the ran-too-far reason.

    ``select_candidates`` tests the band BEFORE the status and short-circuits there, so a
    first-failing-gate receipt would label this row "No setup yet" and the anti-chase
    story would never reach the surface. On the committed 2026-08-09 board 14 of the 25
    refused rows fail more than one gate and ALL NINE `extended` rows also carry
    band == 'low' — i.e. gate order would bury the reason this shelf exists for on every
    single one of them. The other failing codes are not hidden: they ride ``why``, which
    the chip's Tier-2 hover prints in full.
    """
    cx = refusal_receipts(_board(_row("CHASE", status="extended", band="low")))
    assert _headline(cx, "CHASE") == "ran_too_far"
    assert _why(cx, "CHASE") == ["ran_too_far", "conviction_low"]

    html = _shelf(cx)
    assert "Ran too far — waiting for a pullback" in html
    # the buried reason is still disclosed, on the hover
    assert "Ran too far — waiting for a pullback; No setup yet." in html
    assert "涨得太急 — 等回调；暂无买点。" in html


def test_why_list_is_full_and_specificity_ordered_with_the_headline_first():
    cx = refusal_receipts(_board(
        _row("EVERY", status="extended", band="low", direction="down", tier="T4"),
    ))
    assert _why(cx, "EVERY") == [
        "ran_too_far", "grade_low", "conviction_low", "pointing_down"]
    order = list(REFUSAL_ORDER)
    assert [order.index(c) for c in _why(cx, "EVERY")] == sorted(
        order.index(c) for c in _why(cx, "EVERY"))


def test_every_multi_gate_row_headlines_its_most_specific_code():
    """Property form of the above over every status the ladder can emit."""
    for status, expected in REFUSAL_STATUS_MAP.items():
        cx = refusal_receipts(_board(
            _row("MG", status=status, band="low", tier="T4", direction="down")))
        assert _headline(cx, "MG") == expected, status


# --------------------------------------------------------------------------- #
# 5. The rendered shelf
# --------------------------------------------------------------------------- #

def _demo_cx() -> dict:
    """Two groups, three chips, one admitted row that earns no receipt."""
    return refusal_receipts(_board(
        _row("NEARA", status="buy_soon", score=80, name="Near Alpha"),
        _row("NEARB", status="watch", score=75, name="Near Beta"),
        _row("CHASE", status="extended", band="low", score=70, name="Chase Corp"),
        _row("PLANNED", score=95, name="Planned Co"),
    ))


def test_shelf_renders_the_full_structure():
    html = _shelf(_demo_cx())
    assert '<details class="pvr">' in html
    assert " open" not in html.split(">")[0]          # closed by default
    assert 'class="pvr-sum"' in html
    assert 'class="pvr-hd"' in html
    assert "Passed on tonight" in html and "今晚未纳入" in html
    assert "3 of 4" in html and "3 / 4 只" in html
    assert 'class="pvr-caret" aria-hidden="true"' in html
    assert "Watch — don&#39;t chase. Each rejoins the board when its setup completes." in html
    assert "观望，不要追。形态走完，它们会自己回到榜上。" in html
    assert 'class="pvr-list"' in html
    assert html.count('<li class="pvr-g') == 2        # two groups tonight
    assert '<li class="pvr-g is-near"' in html        # the NEAR rail
    assert 'class="pvr-gh"' in html and 'class="pvr-why"' in html
    assert 'class="pvr-n"' in html
    assert 'class="pvr-tks"' in html
    assert html.count('class="pvr-tk"') == 3          # one chip per refused name
    assert ">NEARA<" in html and ">NEARB<" in html and ">CHASE<" in html
    assert "PLANNED" not in html                      # an admitted row is not a receipt
    assert 'class="pvr-ft"' in html
    assert "Re-drawn nightly" in html and "每晚重绘" in html


def test_every_chip_carries_both_hover_languages():
    html = _shelf(_demo_cx())
    # Scoped to the CHIPS. The footnote's era clause is a hover too (see the era tests
    # below), so a bare `data-tip-en=` count would silently pass whenever a chip LOST its
    # hover and some other element gained one.
    assert html.count('class="pvr-tk" data-tip-en=') == 3
    assert html.count("data-tip-zh=") == html.count("data-tip-en=")
    assert ("Chase Corp — what's holding it back tonight: "
            "Ran too far — waiting for a pullback; No setup yet.") in html
    assert "Chase Corp — 今晚未纳入的原因：涨得太急 — 等回调；暂无买点。" in html


def test_shelf_carries_no_title_attribute():
    """CI-guarded house law: no translated text in `title=`. The hover is data-tip-*."""
    assert "title=" not in _shelf(_demo_cx())
    assert "title=" not in str(
        _env().get_template("_prophet_receipts.html.j2").module.pvr_css())


#: Vocabulary that may never reach this surface. Two families:
#:   · the operator's front-facing ban (verdict/falsification language), and
#:   · every INTERNAL token — machine status words, gate names, and the reason codes
#:     themselves, which must stay in the JSON and never become a class or an attribute.
#: Deliberately NOT listed: the bare English words `watch`, `hold`, `exit`, `avoid`. The
#: lede's operator-ratified stance line is literally "Watch — don't chase", so a bare
#: substring ban on those would fail on the copy the doctrine requires. Their machine
#: forms (`bounce_wait`, `wait_pullback`, `await_confluence`, …) ARE checked.
BANNED = (
    "validated", "falsifier", "refuted", "证伪", "已确认", "已触发",
    "fired", "confirmed", "triggered",
    "band_low", "tier_cascade", "admission_class", "entry_signal", "wait_reset",
    "intake", "buy_soon", "bounce_wait", "wait_pullback", "buy_now",
    "await_confluence", "extended", "topping", "T4", "conviction.band",
) + tuple(REFUSAL_ORDER)


def test_shelf_leaks_no_banned_vocabulary():
    html = _shelf(refusal_receipts(_board(
        _row("A1", status="extended", band="low"),
        _row("A2", status="buy_soon"),
        _row("A3", status="blocked"),
        _row("A4", status="quantum_wobble"),
        _row("A5", direction="down"),
        _row("A6", tier="T4"),
        _row("A7", entry_signal=False),
    ), open_keys=("A8-BULL",), originated_tickers=set()))
    lowered = html.lower()
    for word in BANNED:
        assert word.lower() not in lowered, word


def test_reason_codes_never_reach_the_dom():
    """Regression fence for the obvious "helpful" edit: a data-reason/class slug."""
    html = _shelf(_demo_cx())
    for code in REFUSAL_ORDER:
        assert code not in html


# --------------------------------------------------------------------------- #
# 6. Silent degradation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cx", [None, {}, {"groups": []},
                                {"considered": 0, "passed": 0, "groups": []}])
def test_absent_or_empty_context_renders_nothing(cx):
    assert _shelf(cx) == ""


def test_undefined_context_renders_nothing():
    """The non-US boards never pass this key at all — Undefined must degrade, not raise."""
    env = _env()
    out = env.from_string(
        '{% import "_prophet_receipts.html.j2" as pvr %}'
        "{{ pvr.pvr_shelf(us_prophet_refusals) }}").render()
    assert out.strip() == ""


# --------------------------------------------------------------------------- #
# 7. Capping discloses itself
# --------------------------------------------------------------------------- #

def test_capped_group_reports_the_true_count():
    rows = [_row(f"T{i:02d}", status="watch", score=100 - i) for i in range(20)]
    cx = refusal_receipts(_board(*rows))
    group = cx["groups"][0]
    assert REFUSAL_NAMES_CAP == 14
    assert group["n"] == 20                       # TRUE count — the disclosure
    assert len(group["names"]) == 14              # what is drawn
    assert [n["ticker"] for n in group["names"]] == [f"T{i:02d}" for i in range(14)]
    html = _shelf(cx)
    assert ">20<" in html
    assert html.count('class="pvr-tk"') == 14


# --------------------------------------------------------------------------- #
# 8. Wiring — the surface is actually reachable
# --------------------------------------------------------------------------- #

def test_dashboard_imports_and_emits_the_partial_once():
    assert '{% import "_prophet_receipts.html.j2" as pvr %}' in DASH
    assert DASH.count("pvr.pvr_css()") == 1
    assert DASH.count("pvr.pvr_shelf(us_prophet_refusals)") == 1


def test_shelf_sits_below_the_cards_and_above_the_panel_footnote():
    """BELOW the plans, never between them (spec §6)."""
    grid_close = DASH.index("end .nbgrid")
    shelf = DASH.index("pvr.pvr_shelf(us_prophet_refusals)")
    footnote = DASH.index('<p class="pb-fn">')
    assert grid_close < shelf < footnote


def test_dashboard_template_still_compiles():
    _env().get_template("dashboard.html.j2")


def test_build_site_passes_the_receipts_into_the_view_model():
    assert "def _us_prophet_refusals(" in BUILD_SITE
    assert "us_prophet_refusals=us_prophet_refusals," in BUILD_SITE
    # the post-build_library re-render replaces us_standouts; the shelf is DERIVED from
    # that board, so it has to move with it or one page carries two generations.
    assert 'vm["us_prophet_refusals"] = _us_prophet_refusals(site, _fresh_su)' in BUILD_SITE


def test_build_site_does_not_source_the_reason_list_from_the_published_index():
    """The build-order law: build_site runs BEFORE build_prophet, so the reason list may
    only come from tonight's us_standouts.

    Last night's index may be read ONLY for facts that cannot go stale into a wrong
    number — a plan's open/closed state, and (§0.10) whether it was reconstructed after
    the outage, which is a settled fact about its past. Everything a REFUSAL says must
    come from ``doc``, tonight's board.

    The pin used to be the literal call ``refusal_receipts(doc, open_tickers)``. That
    spelling broke the moment a second permitted read was added, which made the guard
    look like a veto on a change it never meant to forbid — so it now pins the LAW: one
    index open, tonight's board as the reason source, and no refusal field read off the
    published document.
    """
    body = BUILD_SITE[BUILD_SITE.index("def _us_prophet_refusals("):]
    body = body[:body.index("\ndef ", 1)]
    # The receipts are built from tonight's board dict, positionally first — never from
    # anything derived out of the published index.
    assert "refusal_receipts(doc, open_tickers" in body
    # ONE index open, still.
    assert body.count("prophet\" / \"index.json") == 1
    # The only per-plan fields taken off last night's rows. `why`/`groups`/status words
    # would each be a reason sourced from the wrong generation.
    permitted = {"asset", "closed", "origination_mode"}
    read_from_index = set(re.findall(r"p\.get\(\"(\w+)\"\)", body))
    assert read_from_index <= permitted, read_from_index - permitted
    assert "is_reconstructed(p)" in body, "the mode is read through the shared predicate"


def test_build_prophet_publishes_the_receipts_additively():
    assert '"receipts": refusal_receipts(' in BUILD_PROPHET
    assert "refusal_receipts," in BUILD_PROPHET      # imported at module scope


# --------------------------------------------------------------------------- #
# 9. End to end through the real page
# --------------------------------------------------------------------------- #
# Source assertions prove the call is SPELLED; only a render proves the shelf reaches
# the page. The synthetic view-model is reused from the dashboard render suite (the
# house idiom test_dashboard_news_i18n.py already uses), with the sys.path bootstrap
# that makes the import work under any pytest import mode.
sys.path.insert(0, str(ROOT / "tests"))
from test_dashboard_template_render import _base_vm  # noqa: E402


def _page(refusals) -> str:
    vm = _base_vm()
    if refusals is not None:
        vm["us_prophet_refusals"] = refusals
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def test_page_renders_the_shelf_when_the_context_is_supplied():
    html = _page(_demo_cx())
    assert '<details class="pvr">' in html
    assert html.count('class="pvr-tk"') == 3
    assert ".pvr-sum{" in html                       # the CSS is emitted too


def test_page_renders_no_shelf_without_the_context():
    """The key is simply absent for every board that does not compute it."""
    assert '<details class="pvr">' not in _page(None)
    assert '<details class="pvr">' not in _page({"considered": 0, "passed": 0,
                                                 "planned": 0, "groups": [],
                                                 "unmapped": 0})


def test_page_puts_the_shelf_below_the_cards():
    html = _page(_demo_cx())
    assert html.index("nbgrid") < html.index('<details class="pvr">')


# --------------------------------------------------------------------------- #
# The shelf agrees with the gate it reports on
# --------------------------------------------------------------------------- #

def _every_status_board() -> dict:
    """One row per status word the ladder can emit, plus the non-status refusals.

    Synthetic on purpose. Pinning this against the committed
    ``site/factordata/us_standouts.json`` would make the suite a SCHEDULED red the first
    night the board's composition moves, and the property under test is about the gate,
    not about any one night's names.
    """
    rows = [_row(f"OK{i}", status=s)
            for i, s in enumerate(sorted(ADMITTED_STATUSES))]
    rows += [_row(f"NO{i}", status=s)
             for i, s in enumerate(sorted(_KNOWN_REFUSED_STATUSES))]
    rows += [
        _row("DOWN", direction="down"),
        _row("BAND", band="low"),
        _row("TIER", tier="T4"),
        _row("NOSIG", entry_signal=False),
        _row("DRIFT", status="quantum_wobble"),
    ]
    return {"buy": rows}


def test_receipts_partition_exactly_matches_the_admission_gate():
    """The shelf's cohort is the gate's complement — no overlap, nothing unaccounted.

    This is the property that makes the surface honest: every buy-lane row is either on
    the board above or explained on the shelf below, and never both.  It is pinned here
    rather than left to inspection because the receipts evaluate the gates a SECOND time
    (without short-circuiting) — the one structural way this feature can rot is for that
    second reading to drift from ``select_candidates``.
    """
    board = _every_status_board()
    admitted = {r["ticker"] for r in select_candidates(board, n=None)}
    cx = refusal_receipts(board)
    refused = {n["ticker"] for g in cx["groups"] for n in g["names"]}
    everything = {r["ticker"] for r in board["buy"]}

    assert not (admitted & refused), "a row is both planned and passed on"
    assert everything - admitted - refused == set(), "a row is on neither surface"
    assert cx["considered"] == len(everything)
    assert cx["passed"] == len(refused)
    assert cx["planned"] == len(admitted)


# --------------------------------------------------------------------------- #
# Era stamp — Tier 1 plain words, Tier 2 identifier
# --------------------------------------------------------------------------- #

def _visible_text(html: str) -> str:
    """The rendered markup with every hover attribute value removed.

    Tier-2 copy lives in ``data-tip-en``/``data-tip-zh``; stripping those leaves what a
    reader actually SEES without hovering, which is the only text the glance-tier
    vocabulary laws apply to.
    """
    return re.sub(r'data-tip-(?:en|zh)="[^"]*"', "", html)


def test_receipts_carry_the_selection_era_from_the_payload():
    cx = refusal_receipts(_board(_row("A", status="extended")))
    assert cx["era"] == SELECTION_ERA           # the chartered literal, not a re-date
    assert cx["era_since_en"] == "8 Aug 2026"
    assert cx["era_since_zh"] == "2026年8月8日"


def test_era_identifier_is_tier_2_only():
    """Doctrine Law 2: a machine identifier may not appear at the glance tier.

    The era literal is a receipt, so it rides the footnote's hover — and the plain-word
    date is what the reader sees.  A future edit that "helpfully" prints the identifier
    on the surface fails here.
    """
    html = _shelf(_demo_cx())
    assert SELECTION_ERA in html                       # disclosed …
    assert SELECTION_ERA not in _visible_text(html)    # … but never on Tier 1
    assert "same selection rules since 8 Aug 2026" in html
    assert "选股规则自 2026年8月8日 起未变" in html


def test_era_clause_degrades_when_the_literal_stops_parsing(monkeypatch):
    """Fail-soft: an unparseable era costs the date clause, never a WRONG date."""
    monkeypatch.setattr("engine.prophet_bridge.SELECTION_ERA", "some-future-era")
    cx = refusal_receipts(_board(_row("A", status="extended")))
    assert cx["era"] == "some-future-era"
    assert cx["era_since_en"] == "" and cx["era_since_zh"] == ""
    html = _shelf(cx)
    assert "selection rules unchanged" in html
    assert "选股规则未变" in html
    assert "Re-drawn nightly" in html                  # the footnote still renders


def test_era_hover_carries_the_display_tier_disclaimer():
    """The receipt says what the shelf IS: a report on the rules, never a rule."""
    html = _shelf(_demo_cx())
    assert "This shelf reports the rules, it never changes them." in html
    assert "本栏只呈现筛选结果，不参与筛选。" in html


# --------------------------------------------------------------------------- #
# An open plan is not a refusal
# --------------------------------------------------------------------------- #

def _cx_with_open_plans() -> dict:
    """Three genuine declines plus four names that already hold a live plan."""
    return refusal_receipts(
        _board(
            _row("DECL1", status="extended", band="low", score=90),
            _row("DECL2", status="buy_soon", score=80),
            _row("DECL3", direction="down", score=70),
            _row("OPEN1", score=95), _row("OPEN2", score=94),
            _row("OPEN3", score=93), _row("OPEN4", score=92),
        ),
        open_keys=("OPEN1-BULL", "OPEN2-BULL", "OPEN3", "OPEN4-BEAR"),
    )


def test_open_plans_are_counted_apart_from_declines():
    """`passed` stays lossless; `declined` is the figure a surface may headline.

    Measured motive: through build_site's call site on the committed board, 48 of the 73
    receipted rows are open plans — so an undivided figure says "we put down 73 of 79"
    when the honest sentence is "we declined 25 and are already trading 48".
    """
    cx = _cx_with_open_plans()
    assert cx["considered"] == 7
    assert cx["passed"] == 7            # lossless: every row earned a receipt
    assert cx["open_now"] == 4
    assert cx["declined"] == 3
    assert cx["planned"] == 0           # none of them was left without a receipt


def test_shelf_headlines_declines_never_the_lossless_total():
    html = _shelf(_cx_with_open_plans())
    assert ">3 of 7<" in html            # declined, not passed
    assert ">7 of 7<" not in html


def test_drawn_group_counts_sum_to_the_headline():
    """A reader who adds the group counts must get the headline number back."""
    cx = _cx_with_open_plans()
    drawn = [g for g in cx["groups"] if g["reason"] != "already_open"]
    assert sum(g["n"] for g in drawn) == cx["declined"]


def test_open_plan_cohort_is_one_line_and_not_a_ticker_wall():
    """It answers "why isn't this a NEW plan?" with "it already is one — look up".

    Spending the shelf's largest block and its lead position on the one cohort that needs
    no explanation is the defect this pins (doctrine's demotion rule).
    """
    cx = _cx_with_open_plans()
    assert any(g["reason"] == "already_open" for g in cx["groups"]), \
        "the engine must still return it — the published receipts stay lossless"
    html = _shelf(cx)
    assert 'class="pvr-open"' in html
    assert "4 more already have a plan running" in html
    assert "另有 4 只已有在跑的计划" in html
    # …and no group heading or chip for them.
    assert "Already has a plan running" not in html
    for ticker in ("OPEN1", "OPEN2", "OPEN3", "OPEN4"):
        assert f">{ticker}<" not in html
    # Scoped to the <li>: a bare `pvr-g` prefix also matches each group's `pvr-gh` header.
    assert html.count('<li class="pvr-g') == 3


def test_open_plan_line_is_absent_when_nothing_is_open():
    assert 'class="pvr-open"' not in _shelf(_demo_cx())


# --------------------------------------------------------------------------- #
# Light mode is a design target, not a token swap (doctrine §5.8)
# --------------------------------------------------------------------------- #

def test_light_theme_keeps_the_near_rail_accent():
    """CSS SPECIFICITY fence — this shipped broken and was caught by computed style.

    `html[data-theme="light"] .pvr-g::before` scores (0,2,2) and OUTRANKS
    `.pvr-g.is-near::before` at (0,2,1), so the light block silently repaints EVERY rail
    muted-grey — including the near cohort's, which is the shelf's only visual hierarchy.
    Measured before the fix: all six rails returned the same computed rgb in light mode.
    An explicit light twin is the only thing that keeps the accent alive.
    """
    css = str(_env().get_template("_prophet_receipts.html.j2").module.pvr_css())
    generic = css.index('html[data-theme="light"] .pvr-g::before')
    near = css.index('html[data-theme="light"] .pvr-g.is-near::before')
    assert near > generic, "the light near-rail twin must come after the generic override"
    assert "var(--pv-wait)" in css[near:near + 120]
