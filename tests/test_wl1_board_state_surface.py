"""tests/test_wl1_board_state_surface.py — W-L1 provisional close-pass board SURFACE.

Covers the three additions the pinned spec (``research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md``)
makes to the ``#us-standouts`` panel: the board-state stamp, the one-line board-state note,
and the per-card ``Adjusted`` mark — plus the contract interpreter they all hang off
(``lib/board_state.py``).

WHY THIS SUITE IS MOSTLY BROWSER-FREE. The CI packs install a minimal dependency set, not
``requirements.txt`` — a ``pytest.importorskip("playwright")`` here would SKIP in CI and
report green while proving nothing (house trap: ci-packs-install-minimal-deps-not-requirements).
So everything mechanically checkable is asserted against the rendered template, the shipped
CSS/JS source, and the interpreter. The measurements that genuinely need a browser —
composited contrast in both themes, header-height invariance across the four states, the
perforated edge read off getComputedStyle — live in
``mockups/refs/breathing-platform/verify_wl1.py``, which is run by hand and whose output is
pasted into the PR body.

THE ONE EXCEPTION IS THE CLIENT DECISION, and it is deliberate. Spec §0-2 ("the stamp is
derived from the payload that produced the cards") is the single failure that would
actively lie to the reader, so it is proved by EXECUTION rather than by a source grep: the
pure ``_bsQualify`` slice is lifted verbatim out of the template and its truth table is run
under node, which the CI packs do install (actions/setup-node@v4, node 20).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DASH = (ROOT / "templates" / "dashboard.html.j2").read_text()
CARD = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
THEME_CSS = (ROOT / "templates" / "theme.css").read_text()

#: Glance-tier vocabulary the reader may never meet without hovering (spec §0-7), plus the
#: falsifier/refutation family that is never front-facing anywhere (§0-8, operator
#: 2026-07-27). "provisional" is banned as UI COPY specifically: it is the right word for
#: the tier in the spec and in code comments, and the wrong word to say to a reader, who is
#: owed the plain-word version ("tonight's picks, confirmed by morning").
BANNED_GLANCE = (
    "W-L1", "close-pass", "close pass", "provisional", "armed", "reconciler",
    "admission", "gauntlet", "prereg", "display-tier", "expected-null",
    "falsifier", "falsified", "refuted", "invalidated", "证伪",
)

#: Every string §5.2 pins, EN and ZH. Nothing here may be paraphrased at build time.
COPY = {
    "stamp.ahead": ("◐ Tonight's picks", "◐ 今晚选股"),
    "stamp.behind": ("Last confirmed", "上次确认"),
    "note.ahead": ("<b>Get ready</b> — set from today's close, confirmed by morning.",
                   "<b>可以开始准备</b> — 依今日收盘价选出，明早完成确认。"),
    "note.behind": ("Tonight's early update isn't in — these are last night's confirmed "
                    "picks. Check a live quote before you act.",
                    "今晚的提前更新未到位，以下为昨晚确认的选股名单。操作前请先看一下实时报价。"),
    "note.closed": ("Markets are closed — these are the last confirmed picks. "
                    "The board updates after the next session's close.",
                    "休市中，以下为最近一次确认的选股名单。下一个交易日收盘后更新。"),
    "mark.adj": ("Adjusted", "已调整"),
}


# --------------------------------------------------------------------------- #
# Render helpers
# --------------------------------------------------------------------------- #

def _nc(src: str) -> str:
    """Strip comments. Every assertion about CODE runs on this, so that a comment
    *explaining* a rule cannot satisfy — or violate — a check about what the code does."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)


def _render(board_state=None, adjusted_tickers=(), n_rows: int = 3) -> str:
    """The real us_stocks page, through the house harness env.

    Rows carry a `stage` because the marks row is built on the PRIORITY path only — a
    census of `None` fields renders the legacy lane partition and no chip at all, so a
    fixture without it would prove the `Adjusted` fence by accident rather than on purpose.
    """
    from tests.test_dashboard_template_render import _base_vm, _board_row, _env

    vm = _base_vm()
    rows = []
    for i in range(n_rows):
        tk = f"TK{i}"
        rows.append(_board_row(ticker=tk, name=f"Name {i}", stage="live",
                               lane="bottoming", score_rank=i + 1, display_rank=i + 1,
                               prophet={"version": "us_prophet_v1", "score": 70 - i},
                               adjusted=(tk in adjusted_tickers)))
    su = {"buy": rows, "eligible": len(rows), "as_of": "2026-08-08"}
    if board_state is not None:
        from lib.board_state import board_state_view
        view = board_state_view(board_state)
        if view:
            su["board_state_view"] = view
    vm["us_standouts"] = su
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def _panel(html: str) -> str:
    """The ``#us-standouts`` panel only — the stamp/note/marks all live inside it."""
    i = html.index('id="us-standouts"')
    i = html.rindex("<div", 0, i)
    # the panel runs to the page's next top-level panel; the board-state surface is all in
    # the first 250k of it, and slicing on a balanced-tag walk buys nothing here.
    j = html.index('id="dash-tape-band"', i)
    return html[i:j]


def _visible_text(fragment: str) -> str:
    """Text a reader can see without hovering: strip every tip/popover and every tag."""
    no_tips = re.sub(r'<span class="tip[^"]*">.*?</span></span>', " ",
                     fragment, flags=re.S)
    no_tips = re.sub(r"data-tip-(en|zh)=\"[^\"]*\"", " ", no_tips)
    no_tips = re.sub(r"<!--.*?-->", " ", no_tips, flags=re.S)
    return re.sub(r"<[^>]+>", " ", no_tips)


def _js_contract() -> str:
    """The pure client decision, lifted verbatim between its two markers."""
    a = DASH.index("/* WL1-BOARDSTATE-CONTRACT-BEGIN")
    b = DASH.index("/* WL1-BOARDSTATE-CONTRACT-END */")
    return DASH[a:b]


# --------------------------------------------------------------------------- #
# §7 contract — lib/board_state.py
# --------------------------------------------------------------------------- #

def test_absent_or_junk_payload_yields_nothing_rather_than_a_guess():
    from lib.board_state import board_state_view
    for junk in (None, {}, [], "ahead", 3, {"rel": "sideways"}, {"note": "maybe"}):
        assert board_state_view(junk) == {}


def test_server_side_never_emits_a_stamp_at_all():
    """§0-2, server half. A nightly render by construction holds the board of record or
    last night's board — never the EVENING board's cards — so an SSR stamp would be
    describing cards that are not on the page."""
    from lib.board_state import board_state_view
    for rel in ("ahead", "behind"):
        view = board_state_view({"rel": rel, "note": rel,
                                 "confirmed_label": {"en": "Aug 7", "zh": "08-07"},
                                 "board": {"tickers": ["TK0"]}})
        assert "rel" not in view, rel
        assert view.get("note") != rel, rel


def test_receipt_renders_only_when_the_arithmetic_reconciles():
    from lib.board_state import board_state_view
    good = {"note": "confirmed", "n_total": 15, "n_confirmed": 13,
            "n_adjusted": 1, "n_dropped": 1}
    assert board_state_view(good)["note"] == "confirmed"
    for bad in ({**good, "n_confirmed": 12},          # 12+1+1 != 15
                {**good, "n_total": 14},              # 13+1+1 != 14
                {**good, "n_total": 0, "n_confirmed": 0, "n_adjusted": 0, "n_dropped": 0},
                {**good, "n_adjusted": -1},
                {**good, "n_dropped": None},
                {**good, "n_confirmed": True},        # a bool is not a count
                {"note": "confirmed"}):               # no counts at all
        assert board_state_view(bad) == {}, bad


def test_dropped_list_is_sanitised_and_capped():
    from lib.board_state import board_state_view, MAX_DROPPED
    view = board_state_view({
        "note": "confirmed", "n_total": 4, "n_confirmed": 2, "n_adjusted": 1,
        "n_dropped": 1, "dropped": ["TSLA", "TSLA", 7, "  ", None, "F"]})
    assert view["dropped"] == ["TSLA", "F"]
    many = board_state_view({
        "note": "confirmed", "n_total": 40, "n_confirmed": 20, "n_adjusted": 0,
        "n_dropped": 20, "dropped": [f"T{i}" for i in range(40)]})
    assert len(many["dropped"]) == MAX_DROPPED


def test_behind_without_a_date_paints_nothing_even_off_the_render_path():
    """The date is what makes a stale board impossible to mistake for a fresh one."""
    from lib.board_state import board_state_view
    assert board_state_view({"rel": "behind"}, server_side=False) == {}
    assert board_state_view({"rel": "behind", "confirmed_label": {"en": "Aug 7"}},
                            server_side=False) == {}
    ok = board_state_view({"rel": "behind", "confirmed_label": {"en": "Aug 7", "zh": "08-07"}},
                          server_side=False)
    assert ok["rel"] == "behind" and ok["confirmed_label"]["zh"] == "08-07"


def test_a_label_with_no_behind_stamp_is_not_carried():
    from lib.board_state import board_state_view
    view = board_state_view({"rel": "ahead", "confirmed_label": "Aug 7"},
                            server_side=False)
    assert "confirmed_label" not in view


# --------------------------------------------------------------------------- #
# §0-2 — the client decision, executed
# --------------------------------------------------------------------------- #

_JS_HARNESS = r"""
%(contract)s
const cases = JSON.parse(process.argv[2]);
const out = cases.map(c => _bsQualify(c.state, c.domKey, c.now));
console.log(JSON.stringify(out));
"""


def _qualify(cases: list) -> list:
    node = shutil.which("node")
    if node is None:
        # A skip here is only ever a local-dev convenience. In CI it would take the
        # ONE gate that stops this surface lying to a reader (§0-2: a board showing
        # last night's cards must never render tonight's stamp) and make it silently
        # dark — the pack would go green having executed nothing. ci.yml installs
        # node 20 (`actions/setup-node@v4`), so if it is missing under CI the right
        # answer is a red pack telling someone the step moved, not a quiet pass.
        if os.environ.get("CI"):
            raise AssertionError(
                "node is required to execute the _bsQualify client contract, and CI "
                "installs it via actions/setup-node@v4 — its absence means the setup "
                "step was moved or removed, which would leave spec gate §0-2 unproven."
            )
        pytest.skip("node not available to execute the client contract (local only)")
    src = _JS_HARNESS % {"contract": _js_contract()}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "wl1_contract.mjs"
        path.write_text(src)
        run = subprocess.run([node, str(path), json.dumps(cases)],
                             capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


_NOW = 1786000000000          # some fixed instant
_HOUR = 3600000
_LIVE = {"rel": "ahead", "note": "ahead",
         "generated_at": "2026-08-09T21:00:00Z",
         "board": {"tickers": ["TK0", "TK1", "TK2"]}}
_KEY = "TK0|TK1|TK2"


def _state(**over):
    s = dict(_LIVE)
    s["generated_at"] = _iso(_NOW - _HOUR)
    s["valid_until"] = _iso(_NOW + _HOUR)
    s.update(over)
    return s


def _iso(ms: int) -> str:
    import datetime
    return (datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def test_a_board_showing_other_cards_can_never_render_tonights_stamp():
    """§0-2, client half — THE gate. Stale payload, missing payload, and a payload whose
    board is simply not the one on the page all resolve to NO stamp."""
    got = _qualify([
        {"state": _state(), "domKey": _KEY, "now": _NOW},                    # 0 the happy path
        {"state": None, "domKey": _KEY, "now": _NOW},                        # 1 absent
        {"state": _state(board={"tickers": ["TK9", "TK1", "TK2"]}),
         "domKey": _KEY, "now": _NOW},                                       # 2 different names
        {"state": _state(board={"tickers": ["TK1", "TK0", "TK2"]}),
         "domKey": _KEY, "now": _NOW},                                       # 3 same names, other order
        {"state": _state(board={"tickers": ["TK0", "TK1"]}),
         "domKey": _KEY, "now": _NOW},                                       # 4 a subset
        {"state": _state(board={"tickers": []}), "domKey": _KEY, "now": _NOW},  # 5 empty
        {"state": _state(), "domKey": "", "now": _NOW},                      # 6 no cards rendered
    ])
    assert got[0] == {"rel": "ahead", "note": "ahead", "label": None}
    assert got[1:] == [None] * 6


def test_a_stale_or_undated_payload_paints_nothing():
    got = _qualify([
        {"state": _state(valid_until=_iso(_NOW - 1)), "domKey": _KEY, "now": _NOW},
        {"state": _state(valid_until=None), "domKey": _KEY, "now": _NOW},
        {"state": _state(valid_until="whenever"), "domKey": _KEY, "now": _NOW},
        {"state": _state(generated_at=None), "domKey": _KEY, "now": _NOW},
        # a far-future expiry cannot outlive the absolute backstop
        {"state": _state(generated_at=_iso(_NOW - 200 * _HOUR),
                         valid_until=_iso(_NOW + 10000 * _HOUR)),
         "domKey": _KEY, "now": _NOW},
    ])
    assert got == [None] * 5


def test_the_client_never_paints_the_confirmed_receipt():
    """Its figures can only be checked against the board that produced them, so the
    receipt belongs to the nightly render and to nothing else."""
    got = _qualify([{"state": _state(rel=None, note="confirmed"),
                     "domKey": _KEY, "now": _NOW}])
    assert got == [None]


def test_behind_needs_its_date_in_both_languages():
    got = _qualify([
        {"state": _state(rel="behind", note="behind"), "domKey": _KEY, "now": _NOW},
        {"state": _state(rel="behind", note="behind", confirmed_label={"en": "Aug 7"}),
         "domKey": _KEY, "now": _NOW},
        {"state": _state(rel="behind", note="behind",
                         confirmed_label={"en": "Aug 7", "zh": "08-07"}),
         "domKey": _KEY, "now": _NOW},
    ])
    assert got[0] is None and got[1] is None
    assert got[2] == {"rel": "behind", "note": "behind",
                      "label": {"en": "Aug 7", "zh": "08-07"}}


def test_the_client_never_derives_state_from_a_clock():
    """`now` is only ever compared against dates the PAYLOAD carries. Sweeping the clock
    across a whole week must never turn a non-qualifying payload into a qualifying one,
    and must never change WHICH state a qualifying payload resolves to."""
    span = [{"state": _state(), "domKey": _KEY, "now": _NOW + h * _HOUR}
            for h in range(-6, 168, 6)]
    got = _qualify(span)
    inside = [g for g, c in zip(got, span) if g is not None]
    assert all(g == {"rel": "ahead", "note": "ahead", "label": None} for g in inside)
    assert inside, "the fixture must qualify at least once or this proves nothing"


# --------------------------------------------------------------------------- #
# Rendered surface
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def plain() -> str:
    return _panel(_render())


@pytest.fixture(scope="module")
def receipt() -> str:
    return _panel(_render(
        board_state={"note": "confirmed", "n_total": 3, "n_confirmed": 1,
                     "n_adjusted": 1, "n_dropped": 1, "dropped": ["TSLA"]},
        adjusted_tickers=("TK1",)))


def test_the_confirmed_board_carries_no_stamp_and_no_attribute(receipt):
    """Absence is the third state (§1) and it is load-bearing — so absence is asserted."""
    assert "data-boardstate" not in receipt
    for cls in ("pbs-ahead", "pbs-behind"):
        stamp = re.search(r"<span class=\"pbs %s\"[^>]*>" % cls, receipt)
        assert stamp and " hidden" in stamp.group(0), cls


def test_exactly_one_stamp_slot_of_each_kind_exists_and_both_start_hidden(plain):
    assert plain.count('class="pbs pbs-ahead"') == 1
    assert plain.count('class="pbs pbs-behind"') == 1
    assert len(re.findall(r'<span class="pbs pbs-[a-z]+" data-bs="[a-z]+" hidden>', plain)) == 2


def test_the_note_slot_is_always_present_and_reserves_its_line(plain):
    """The evening state lands under a reader who is already looking at the board, so the
    slot has to hold its height BEFORE the payload arrives or the flip shoves the grid."""
    assert plain.count('<div class="pbs-note">') == 1
    assert re.search(r"\.pbs-note\s*\{[^}]*min-height:\s*1\.5em", DASH)
    assert re.search(r"\.pbs-note\s*\{[^}]*text-wrap:\s*pretty", DASH)


def test_all_four_note_variants_ship_and_only_one_is_ever_visible(receipt):
    kinds = re.findall(r'<span class="pbs-nv" data-bs-note="([a-z]+)"( hidden)?>', receipt)
    assert [k for k, _ in kinds] == ["confirmed", "ahead", "behind", "closed"]
    assert [k for k, h in kinds if not h] == ["confirmed"]


def test_every_pinned_string_ships_in_both_languages(plain):
    for key, (en, zh) in COPY.items():
        if key.startswith("mark."):
            continue        # the mark is fenced on the receipt; asserted in its own test
        assert en in plain, f"{key} EN missing"
        assert zh in plain, f"{key} ZH missing"


def test_the_receipt_prints_its_figures_in_both_clause_orders(receipt):
    """§5.2: the ZH clause order is deliberately NOT the EN order — `调整 1 只` rather than
    a literal `1 只有调整`, which reads as "ONLY 1" (只有 = only) and is a genuine
    mis-parse."""
    assert ('<span class="pbs-fig">1</span> of <span class="pbs-fig">3</span> '
            "confirmed overnight" in receipt)
    assert ('<span class="pbs-fig">3</span> 只中 <span class="pbs-fig">1</span> '
            "只隔夜确认" in receipt)
    assert "调整 <span class=\"pbs-fig\">1</span> 只，离榜" in receipt
    assert "只有" not in receipt.split('data-bs-note="confirmed"')[1][:600]


def test_figures_are_tabular_and_the_words_around_them_are_not(receipt):
    assert re.search(r"\.pbs-fig\s*\{[^}]*font-variant-numeric:\s*tabular-nums", DASH)
    # numerals only — never the surrounding words
    assert '<span class="pbs-fig">confirmed' not in receipt
    assert '<span class="pbs-fig">only' not in receipt


def test_dropped_names_are_named_in_the_receipt_and_never_rendered_as_cards(receipt):
    """A card inside the pick grid claims to be a pick (§8-4)."""
    assert "Left the board: TSLA" in receipt
    assert "已离榜：TSLA" in receipt
    assert 'data-ticker="TSLA"' not in receipt


def test_the_dropped_clause_says_it_is_not_a_sell_instruction(receipt):
    assert "that is not a sell instruction for a position you already hold" in receipt
    assert "这不是让你卖出已有仓位的指令" in receipt


def test_the_adjusted_mark_never_renders_without_its_receipt():
    """Published together or not at all (§7 invariants)."""
    with_receipt = _panel(_render(
        board_state={"note": "confirmed", "n_total": 3, "n_confirmed": 1,
                     "n_adjusted": 1, "n_dropped": 1},
        adjusted_tickers=("TK1",)))
    assert "pv-mk-adj" in with_receipt
    assert COPY["mark.adj"][0] in with_receipt and COPY["mark.adj"][1] in with_receipt

    # same adjusted row, but the counts do not reconcile → no receipt, and no mark
    broken = _panel(_render(
        board_state={"note": "confirmed", "n_total": 9, "n_confirmed": 1,
                     "n_adjusted": 1, "n_dropped": 1},
        adjusted_tickers=("TK1",)))
    assert "pv-mk-adj" not in broken
    assert 'class="pbs-nv" data-bs-note="confirmed"' not in broken

    # and with no board state at all
    none = _panel(_render(adjusted_tickers=("TK1",)))
    assert "pv-mk-adj" not in none


def test_confirmed_names_carry_no_mark_of_their_own(receipt):
    """`Confirmed` is the other N−1 cards; a constant belongs in the receipt line once,
    never stamped N times (doctrine Law 4)."""
    assert "pv-mk-confirmed" not in receipt
    assert receipt.count("pv-mk-adj") == 1


def test_the_adjusted_mark_carries_its_tip_because_it_cannot_be_inferred():
    assert "_MK_NOTIP = ('feat', 'new')" in CARD          # 'adj' deliberately absent
    html = _panel(_render(
        board_state={"note": "confirmed", "n_total": 3, "n_confirmed": 1,
                     "n_adjusted": 1, "n_dropped": 1},
        adjusted_tickers=("TK1",)))
    tip = re.search(r'<span class="pv-mk-i pv-mk-adj"([^>]*)>', html)
    assert tip and "data-tip-en=" in tip.group(1) and "data-tip-zh=" in tip.group(1)


# --------------------------------------------------------------------------- #
# Doctrine
# --------------------------------------------------------------------------- #

def _new_surface(panel: str) -> str:
    """The stamp slots + the note slot — everything this PR puts in front of a reader.

    Scoped, not page-wide, and the scope is the point. The panel's PRE-EXISTING copy
    already carries two of these words ("not an admission limit" in the .pb-fn methodology
    footnote, and the nightly trigger chip's "Provisional: projected off an incomplete
    bar"). Those are legacy debt on a different surface; sweeping the whole panel here
    would make this suite fail on someone else's sentence and teach the next builder to
    delete the assertion rather than the defect.
    """
    out = re.findall(r'<span class="pbs pbs-[a-z]+".*?</span></span>', panel, flags=re.S)
    i = panel.index('<div class="pbs-note">')
    # the slot contains only spans, so the first </div> after it is its own close
    out.append(panel[i:panel.index("</div>", i) + 6])
    return " ".join(out)


def test_no_banned_vocabulary_reaches_the_glance_tier(receipt):
    text = _visible_text(_new_surface(receipt)).lower()
    assert "confirmed overnight" in text, "the scope must actually contain the surface"
    for word in BANNED_GLANCE:
        assert word.lower() not in text, word


def test_no_falsifier_vocabulary_anywhere_in_the_surface(receipt):
    """§0-8: a night that did not produce a board is described by what the reader GETS,
    not by what the system did. Tips included — Tier 2 has its own register, not a
    licence."""
    surface = _new_surface(receipt)
    for word in ("falsifier", "refuted", "invalidated", "证伪", "failed to", "thesis"):
        assert (word not in surface.lower()) if word.isascii() else (word not in surface)


def test_tier_two_copy_leaks_no_internals(receipt):
    tips = " ".join(re.findall(r'<span class="tip tip-wide">(.*?)</span></span></span>',
                               _new_surface(receipt), flags=re.S))
    assert tips
    for word in BANNED_GLANCE:
        assert word.lower() not in tips.lower(), word
    for leak in ("prophet_live", "us_standouts", "engine/", "scripts/", ".json", "R2"):
        assert leak not in tips, leak


def test_the_stale_state_is_quiet_honesty_not_a_caution(receipt):
    """§8-5: `.nb-stale-note`'s amber-on-tint treatment is for a DIFFERENT fact (prices
    behind the market) and can still fire independently."""
    rule = re.search(r"\.pbs-note \{[^}]*\}", DASH).group(0)
    assert "var(--muted)" in rule
    assert "background" not in rule and "border" not in rule
    assert "nb-stale-note" in DASH          # the amber banner still exists, untouched


def test_the_note_is_not_a_second_footnote(plain):
    """Doctrine Law 4: `.pb-fn` stays the panel's single permanent methodology note."""
    assert plain.count('class="pb-fn"') == 1


def test_no_translated_text_in_any_attribute_on_the_new_surface(plain):
    new = re.findall(r'<span class="pbs[^"]*"[^>]*>', plain)
    new += re.findall(r'<div class="pbs-note">', plain)
    for tag in new:
        assert "title=" not in tag, tag
        assert not re.search(r"[一-鿿]", tag), tag


# --------------------------------------------------------------------------- #
# CSS contract
# --------------------------------------------------------------------------- #

def test_the_provisional_tokens_are_direction_neutral_and_split_by_theme():
    assert ":root { --prov: #62a0e8; --prov-ink: var(--prov); }" in THEME_CSS
    assert 'html[data-theme="light"] { --prov: #2f6fd0;' in THEME_CSS
    # never derived from --up/--down: 红涨绿跌 must hold by construction
    block = _nc(THEME_CSS[THEME_CSS.index("/* W-L1 provisional plane"):
                          THEME_CSS.index("/* ---- Chinese mode")])
    assert "--up" not in block and "--down" not in block
    assert (ROOT / "site" / "theme.css").read_text() == THEME_CSS, \
        "templates/theme.css and site/theme.css must be byte-identical " \
        "(python -m scripts.check_template_site_sync --fix)"


def test_the_perforated_edge_is_a_pseudo_element_on_the_ahead_panel_only():
    """§8-7: a dashed border-top cannot be independently coloured or rounded against the
    panel's own border and would double the hairline."""
    assert '.panel[data-boardstate="ahead"]::before' in DASH
    assert '.panel[data-boardstate="behind"]::before' not in DASH
    edge = DASH[DASH.index('.panel[data-boardstate="ahead"]::before'):]
    edge = edge[:edge.index("}")]
    assert "repeating-linear-gradient" in edge
    assert "0 15px, transparent 15px 24px" in edge      # long dash, never a fine dot


def test_no_animation_is_introduced_so_there_is_nothing_to_disable():
    """§8-6. The strongest form of reduced-motion compliance is having nothing to turn
    off; if motion is ever added here the kill block must name ::before explicitly."""
    css = _nc(DASH[DASH.index("═══ W-L1 BOARD STATE STAMP"):
                   DASH.index("/* per-card expander toggle bar */")])
    for prop in ("animation", "transition", "@keyframes"):
        assert prop not in css, prop


def test_the_adjusted_chip_resolves_toward_muted_not_toward_new():
    """§8-3: at the marks row's normal formula it came out the same blue as `.pv-mk-new`,
    which sits inches away and means something completely different."""
    rule = CARD[CARD.index(".pv-mk-adj{"):]
    rule = rule[:rule.index("}")]
    assert "var(--muted)" in rule
    assert "--prov-ink" in rule and "--prov" in rule
    assert "var(--info)" not in rule
    assert "font-weight:700" in rule                    # quieter than new/feat's 800


def test_the_stamp_is_a_stamp_not_another_chip_in_the_chip_row():
    rule = DASH[DASH.index(".pbs { display: inline-flex"):]
    rule = rule[:rule.index("}")]
    assert "border-radius: 6px" in rule                 # never the board's 999px pills
    assert "white-space: nowrap" in rule


# --------------------------------------------------------------------------- #
# Presentation-tier fence (A7, §0-10)
# --------------------------------------------------------------------------- #

def _bs_js() -> str:
    """The board-state client, from the `/*` that OPENS its header comment.

    Starting mid-comment leaves a dangling `*/` and _nc() then pairs the next `/*` with a
    later `*/`, silently deleting real code while keeping comment prose — the exact
    mis-alignment documented in tests/test_prophet_live_surface.py.
    """
    marker = DASH.index("W-L1 BOARD STATE — which board is this?")
    a = DASH.rindex("/*", 0, marker)
    return DASH[a:DASH.index("function _plvPaint()", a)]


def test_the_client_writes_only_to_the_slots_the_server_reserved():
    js = _nc(_bs_js())
    writes = re.findall(r"\.(setAttribute|removeAttribute|textContent|hidden|innerHTML)\b", js)
    assert "innerHTML" not in writes, "the surface emits no markup of its own"
    targets = re.findall(r"querySelectorAll?\('([^']+)'\)", js)
    assert set(targets) <= {".nbgrid .pvcard[data-ticker]", ".pbs[data-bs]",
                            ".pbs-nv[data-bs-note]", ".pbs-nv:not([hidden])",
                            ".pbs-dt", ".l-en", ".l-zh"}, targets
    # nothing that could reorder, re-rank or re-admit a card
    for forbidden in ("appendChild", "insertBefore", "remove()", "sort(", "pv-chip",
                      "pv-edn", "pv-stp", "pv-zn", "nbgrid.append"):
        assert forbidden not in js, forbidden


def test_the_surface_emits_no_copy_of_its_own():
    """Every string is SSR-baked in both languages; the client only chooses which one is
    unhidden. A string born in JS is a string that ships in one language."""
    js = _nc(_bs_js())
    # not one CJK codepoint: a client that can write ZH is a client that can also forget to
    assert not re.search(r"[一-鿿]", js), "the client must emit no Chinese of its own"
    for key, (en, zh) in COPY.items():
        assert en not in js and zh not in js, key
    # the only text this code writes is the DATE, and it comes from the payload
    for assign in re.findall(r"\.textContent\s*=\s*([^;]+);", js):
        assert assign.strip() in ("label.en", "label.zh"), assign


def test_there_is_no_second_hydration_path():
    """One client owns everything the live plane says about this board: no new script tag,
    no new poll, no second artifact."""
    js = _nc(_bs_js())
    assert "fetch(" not in js
    assert "setInterval" not in js
    assert DASH.count("var PLV_URL") == 1
    assert DASH.count("_plvFetch()") >= 1


def test_no_data_writes_on_this_path():
    from lib import board_state
    src = Path(board_state.__file__).read_text()
    for forbidden in ("open(", "write_text", "Path(", "requests", "urllib"):
        assert forbidden not in src, forbidden


# ─────────────────────────────────────────────────────────────────────────────
# THE HOP — the receipt reaching the board it describes
#
# Everything above proves the SURFACE: given a board-state payload, the panel
# paints the right thing, or nothing. This section proves the payload arrives.
# It did not, for the whole life of #5148: `scripts.close_pass_reconcile`
# published the receipt to R2 and nothing read that key, while `build_site` read
# a `doc["board_state"]` nothing wrote — two correct halves with no hop between
# them, so spec State 2 had never rendered once.
#
# THE HOP CANNOT BE A FETCH. The receipt for session N can only exist once
# session N's board of record has landed, which is after the render that would
# show it — so a render that READ a published receipt could only ever print
# session N-1's arithmetic under session N's cards. The nightly therefore
# computes its own, from the board dict it is about to render, at the one moment
# both halves are in hand. These tests run that real chain: R2 stub →
# confirmation_receipt → board_state_payload → build_site's attach →
# board_state_view → rendered HTML. The only thing replaced is the network hop.
# ─────────────────────────────────────────────────────────────────────────────
HOP_SESSION = "2026-08-08"


def _nightly_doc(tiers: dict, as_of: str = HOP_SESSION) -> dict:
    """A us_standouts board of record, in the shape build_site holds it."""
    from tests.test_dashboard_template_render import _board_row

    return {
        "as_of": as_of,
        "eligible": len(tiers),
        "buy": [_board_row(ticker=tk, name=f"Name {tk}", stage="live",
                           lane="bottoming", score_rank=i + 1, display_rank=i + 1,
                           prophet={"version": "us_prophet_v1", "score": 70 - i},
                           signal={"tier_cascade": tier})
                for i, (tk, tier) in enumerate(sorted(tiers.items()))],
    }


def _evening_board(tiers: dict, as_of: str = HOP_SESSION) -> dict:
    """The provisional board as it has sat on R2 since ~16:25 ET."""
    return {"as_of": as_of, "built_at": f"{as_of}T20:30:00Z",
            "names": [{"ticker": tk, "tier_cascade": tier}
                      for tk, tier in sorted(tiers.items())]}


def _attach(monkeypatch, tmp_path, doc, provisional):
    """Run build_site's real board attach with only the R2 GET replaced.

    build_site is imported inside the test the way
    tests/test_basket_integration.py imports it — a real import in this pack,
    never a skip that would report green while proving nothing.
    """
    from engine.prophet_live import r2io

    seen = []

    def _fake_get(key, **kw):
        seen.append(key)
        return provisional

    monkeypatch.setattr(r2io, "get_json", _fake_get)
    import scripts.build_site as bs

    return bs._attach_board_display_chips(tmp_path, doc), seen


def _rendered_panel(doc):
    from tests.test_dashboard_template_render import _base_vm, _env

    vm = _base_vm()
    vm["us_standouts"] = doc
    return _panel(_env().get_template("dashboard.html.j2").render(
        **vm, mode="stocks"))


def test_the_nightly_computes_its_own_receipt_and_it_reaches_the_page(
        monkeypatch, tmp_path):
    """THE GATE (masterplan §0): the confirmation delta is published per name —
    computed in the nightly, and rendered by the SAME build. AAA holds its tier
    (confirmed), BBB moves tier (adjusted), CCC is gone (dropped), and DDD is a
    nightly addition that rides beside the identity, never inside it."""
    doc = _nightly_doc({"AAA": "T2", "BBB": "T3", "DDD": "T1"})
    prov = _evening_board({"AAA": "T2", "BBB": "T1", "CCC": "T2"})
    out, seen = _attach(monkeypatch, tmp_path, doc, prov)

    assert seen, "the evening board was never fetched — no hop happened"
    view = out["board_state_view"]
    assert view["note"] == "confirmed"
    # The arithmetic is over the PROVISIONAL population, so DDD is not in it.
    assert (view["n_total"], view["n_confirmed"], view["n_adjusted"],
            view["n_dropped"]) == (3, 1, 1, 1)
    assert view["n_confirmed"] + view["n_adjusted"] + view["n_dropped"] \
        == view["n_total"]
    assert view["dropped"] == ["CCC"]

    # …and it renders. Not "the payload is well-formed" — the reader's own line.
    # Asserted on the classes, never on the words "Adjusted"/"已调整": both appear
    # in the receipt line's OWN tooltip, which explains what adjusted means, so a
    # word-match here would pass with the per-card marks entirely absent.
    panel = _rendered_panel(out)
    assert 'class="pbs-nv" data-bs-note="confirmed"' in panel
    assert "confirmed overnight" in panel and "隔夜确认" in panel
    assert panel.count("pv-mk-adj") == 1, "exactly the one name that moved"
    assert 'data-ticker="BBB"' in panel


def test_the_per_card_marks_ship_with_the_line_they_belong_to(monkeypatch,
                                                              tmp_path):
    """Spec §7 publish-together, in the DATA as well as in the template's fence.
    Only the name the receipt calls adjusted is stamped; the confirmed name and
    the nightly addition are left alone."""
    doc = _nightly_doc({"AAA": "T2", "BBB": "T3", "DDD": "T1"})
    out, _ = _attach(monkeypatch, tmp_path, doc,
                     _evening_board({"AAA": "T2", "BBB": "T1", "CCC": "T2"}))
    marks = {r["ticker"]: r.get("adjusted") for r in out["buy"]}
    assert marks["BBB"] is True
    assert not marks["AAA"] and not marks["DDD"]


@pytest.mark.parametrize("provisional,why", [
    (None, "a `behind` night — no evening board was published to grade"),
    ({"as_of": "2026-08-07", "built_at": "2026-08-07T20:30:00Z",
      "names": [{"ticker": "AAA", "tier_cascade": "T2"}]},
     "a stale pairing — yesterday's evening board against tonight's record"),
    ({"as_of": HOP_SESSION, "built_at": f"{HOP_SESSION}T20:30:00Z",
      "names": [{"ticker": "AAA", "tier_cascade": "T2"},
                {"ticker": "AAA", "tier_cascade": "T3"}]},
     "a duplicate ticker — every count over it would be wrong"),
])
def test_a_pairing_the_build_cannot_vouch_for_paints_nothing(
        monkeypatch, tmp_path, provisional, why):
    """No receipt is better than a wrong one (spec §7). A pairing the build
    cannot vouch for must emit NOTHING rather than figures describing a board
    that is not on the screen — including the `behind` case, where
    `note='confirmed'` is impossible because there was no evening board for this
    session to confirm anything against."""
    doc = _nightly_doc({"AAA": "T2", "BBB": "T3"})
    out, _ = _attach(monkeypatch, tmp_path, doc, provisional)
    assert "board_state_view" not in out, why
    assert not any(r.get("adjusted") for r in out["buy"]), why

    panel = _rendered_panel(out)
    assert 'class="pbs-nv" data-bs-note="confirmed"' not in panel, why
    assert "confirmed overnight" not in panel, why
    assert "pv-mk-adj" not in panel, why


def test_the_first_pass_board_never_wears_tonights_receipt(monkeypatch, tmp_path):
    """build_site's FIRST pass reads the PRIOR build's us_standouts (the
    one-build lag); only the post-build_stock_library re-render holds tonight's.
    Both reach the page through this one attach, so the ordering safety cannot
    be left as a comment: last night's cards carry no receipt, because the two
    documents name different sessions."""
    out, _ = _attach(monkeypatch, tmp_path,
                     _nightly_doc({"AAA": "T2", "BBB": "T3"}, as_of="2026-08-07"),
                     _evening_board({"AAA": "T2", "BBB": "T1"}))
    assert "board_state_view" not in out

    out2, _ = _attach(monkeypatch, tmp_path,
                      _nightly_doc({"AAA": "T2", "BBB": "T3"}),
                      _evening_board({"AAA": "T2", "BBB": "T1"}))
    assert out2["board_state_view"]["n_total"] == 2


def test_the_render_computes_the_receipt_and_never_fetches_a_published_one():
    """The one-night-stale design, fenced. A render that read
    live_flow/us_board_confirmation.json would be reading a key that cannot yet
    exist for this session, and would paint the PREVIOUS session's figures under
    tonight's cards. The receipt key must never appear on the render path."""
    src = (ROOT / "scripts" / "build_site.py").read_text()
    assert "us_board_confirmation" not in src
    assert "board_state_for" in src, "the hop must be a computation, not a fetch"


def test_the_delta_has_exactly_one_definition():
    """Two producers of one receipt is how two surfaces end up disagreeing about
    a night. The render and the published artifact both route through
    engine.close_pass.reconcile.confirmation_receipt; neither reimplements it."""
    import scripts.close_pass_reconcile as rc
    from engine.close_pass import reconcile as cr

    assert rc.confirmation_receipt is cr.confirmation_receipt
    for rel in ("scripts/close_pass_reconcile.py", "scripts/build_site.py"):
        assert "def confirmation_receipt" not in (ROOT / rel).read_text(), rel
