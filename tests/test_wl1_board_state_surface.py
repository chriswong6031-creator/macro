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


def _slice(begin: str, end: str) -> str:
    a = DASH.index(begin)
    b = DASH.index(end)
    assert a < b, f"{begin} must precede {end}"
    return DASH[a:b]


def _js_contract() -> str:
    """The pure client decisions, lifted verbatim between their markers.

    TWO slices now, concatenated: the board-state gate (W-L1) and the provisional card
    renderer (W-L1d). `_bsQualify` and `_pvcWanted` call into each other, and JS function
    declarations hoist, so concatenation order does not matter — but BOTH have to be here
    or the half that is missing goes dark while the suite still reports green.
    """
    return (_slice("/* WL1-BOARDSTATE-CONTRACT-BEGIN",
                   "/* WL1-BOARDSTATE-CONTRACT-END */")
            + "\n"
            + _slice("/* WL1-PROVCARD-CONTRACT-BEGIN",
                     "/* WL1-PROVCARD-CONTRACT-END */"))


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
    """The fence MOVED with W-L1d (spec §10) rather than being quietly stretched, so this
    pins where it is now — which is still a short, closed list.

    The board-state half is unchanged: it writes four reserved slots and emits no markup.
    The card half writes markup, but into exactly ONE element, which it created itself and
    which it owns for the life of the mount. Everything that could reorder, re-rank or
    re-admit a row is still absent (A7): the order painted is the order the payload named.
    """
    js = _nc(_bs_js())
    # innerHTML is now permitted — but only into the client's OWN grid, never into a node
    # the server rendered. One assignment, one target.
    inner = re.findall(r"(\w+)\.innerHTML\s*=", js)
    assert inner == ["g"], inner
    assert re.search(r"g\s*=\s*document\.createElement\('div'\)", js), \
        "the only innerHTML target must be an element this code created"
    # `querySelectorAll?` reads as "All optional" but the `?` binds to the final `l`, so
    # the pattern this started as matched querySelectorAl(l) and NEVER the singular
    # querySelector( — it was inspecting 3 of 10 call sites and reporting green on the
    # rest (which is why the allowed set below used to name selectors, like `.pbs-dt`,
    # that it could not actually see). Both forms, explicitly.
    targets = re.findall(r"querySelector(?:All)?\('([^']+)'\)", js)
    assert len(targets) >= 10, f"the selector census went blind again: {targets}"
    assert set(targets) <= {
        # board-state half — the four reserved slots, unchanged
        ".pbs[data-bs]", ".pbs-nv[data-bs-note]", ".pbs-nv:not([hidden])",
        ".pbs-dt", ".l-en", ".l-zh",
        # the board the reader is actually looking at
        ".nbgrid:not([hidden]) .pvcard[data-ticker]",
        # W-L1d — what the mount displaces, and the shape it copies from the nightly cards
        ".nbgrid[data-showmore-rows]:not([data-provboard])", ".pb-fn",
        ".nbgrid .pvcard .nb-chg[data-sym]",
    }, targets
    # Nothing that could reorder, re-rank, re-admit or drop a ROW. Scoped to row
    # operations on purpose — `s.slice(0,4)` on a sparkline string is not a re-ranking,
    # and a blanket ban on the word would only teach the next reader to weaken the test.
    for forbidden in (".sort(", ".reverse(", "cards.filter(", "cards.slice(",
                      "cards.splice(", "Math.random", "localeCompare"):
        assert forbidden not in js, forbidden
    # the cards array is walked forward, by index, and nothing else touches its order
    walks = re.findall(r"for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*(\w+)\.length\s*;\s*i\+\+\s*\)", js)
    assert set(walks) <= {"cards", "cs", "t", "st", "nv", "els", "out"}, walks
    # the grid is replaced as a unit and restored, never mutated in place: the only nodes
    # removed are ones this code inserted (its grid and that grid's own show-more bar)
    # `grid` is the provisional grid this code created; `nb` is that grid's own show-more
    # bar. Nothing the SERVER rendered is ever removed — the nightly grid is hidden and
    # kept, so a teardown restores it by flipping one attribute back.
    removes = re.findall(r"(\w+)\.parentNode\.removeChild\(", js)
    assert set(removes) <= {"nb", "grid"}, removes
    assert re.search(r"\bnight\.hidden\s*=\s*true", js), "the nightly grid is hidden…"
    assert re.search(r"sv\.night\.hidden\s*=\s*false", js), "…and restored, never rebuilt"


def test_the_copy_the_client_emits_is_pinned_in_one_place():
    """W-L1 baked every string server-side; W-L1d cannot, because the cards do not exist
    until the client makes them. So the rule changes from "emit no copy" to "emit only
    copy that is declared, bilingual, and in one table" — which is the property that
    actually protects a reader from a card that ships in one language.

    The board-state half's own strings stay SSR-only: §5.2's copy must never appear here.
    """
    js = _nc(_bs_js())
    for key, (en, zh) in COPY.items():
        assert en not in js and zh not in js, f"{key} is SSR-baked and must stay there"
    # every CJK string in the client lives in a declared PVC_* copy table
    tables = re.findall(r"var (PVC_\w+)\s*=\s*(.+?);\n", js, flags=re.S)
    assert tables, "the copy tables must be declared in the lifted slice"
    declared = "".join(body for _, body in tables)
    for cjk in re.findall(r"[一-鿿]+", js):
        assert cjk in declared, f"{cjk!r} is emitted outside the pinned copy tables"
    # and every entry of a COPY table is a PAIR — an entry with one language is the defect
    # this whole test exists to stop. A table with no Chinese in it at all is not copy
    # (PVC_MONTHS is a date format, mirroring the card macro's own _MN), so it is checked
    # for the opposite property instead: it must never grow a translated string.
    for name, body in tables:
        entries = re.findall(r"\[([^\]]*)\]", body)
        if not re.search(r"[一-鿿]", body):
            assert name == "PVC_MONTHS", f"{name} declares no Chinese twin for its copy"
            continue
        assert entries, f"{name} declares no entries"
        for pair in entries:
            parts = [p for p in pair.split(",") if p.strip()]
            assert len(parts) == 2, f"{name} entry {pair!r} is not an EN/ZH pair"
            assert re.search(r"[一-鿿]", parts[1]), \
                f"{name} entry {pair!r} has no Chinese twin"
    # the only DOM text this code assigns is the stamp DATE, and it comes from the payload
    for assign in re.findall(r"\.textContent\s*=\s*([^;]+);", js):
        assert assign.strip() in ("label.en", "label.zh"), assign


def test_no_translated_text_reaches_a_title_attribute():
    """House law, CI-guarded elsewhere; asserted here for the markup this client emits
    because that markup never passes through the template linters."""
    js = _nc(_bs_js())
    assert "title=" not in js, "bilingual text belongs in l-en/l-zh, never in title="


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


# --------------------------------------------------------------------------- #
# W-L1d — the provisional CARD renderer, executed (spec §10)
# --------------------------------------------------------------------------- #

_PVC_HARNESS = r"""
%(contract)s
const job = JSON.parse(process.argv[2]);
const out = job.cases.map(c => {
  if (c.fn === 'cards')  return _pvcCards(c.board) === null ? null : 'ok';
  if (c.fn === 'room')   return [_pvcRoom(c.runway), _pvcVerb(_pvcRoom(c.runway))];
  if (c.fn === 'wanted') return _pvcWanted(c.state, c.now, c.refused || '') ? 'ok' : null;
  if (c.fn === 'id')     return _pvcId(c.state, _pvcCards(c.state.board));
  if (c.fn === 'html')   return _pvcGridHTML(_pvcCards(c.board), !!c.chg);
  if (c.fn === 'mount') {
    /* the injected env IS the seam the real DOM plugs into: `read` returns whatever the
       painted grid would report, so a case can simulate a card that failed to paint. */
    const log = {painted: null, restored: 0};
    const env = {
      chg: !!c.chg,
      paint: html => { log.painted = html; },
      read: () => (c.readback === undefined
                   ? (c.board.tickers || []).join('|') : c.readback),
      restore: () => { log.restored += 1; }
    };
    const ok = _pvcMount(env, _pvcCards(c.board));
    return {ok: ok, restored: log.restored,
            tickers: (log.painted || '').match(/data-ticker="([^"]*)"/g) || []};
  }
  return 'unknown';
});
console.log(JSON.stringify(out));
"""


def _pvc(cases: list) -> list:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "node is required to execute the W-L1d card contract, and CI installs it "
                "via actions/setup-node@v4 — its absence would leave the post-mount "
                "identity re-verification (spec §10.5) unproven."
            )
        pytest.skip("node not available to execute the client contract (local only)")
    src = _PVC_HARNESS % {"contract": _js_contract()}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "wl1d_contract.mjs"
        path.write_text(src)
        run = subprocess.run([node, str(path), json.dumps({"cases": cases})],
                             capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


def _card(tk, **over):
    c = {"tk": tk, "sym": tk, "mkt": "us", "href": f"stocks/{tk}.html",
         "date": "2026-08-10", "price_txt": "$10.00", "name": f"{tk} Corp",
         "sec": "Technology", "sec_zh": "科技", "signal": 0.9, "runway": 0.8}
    c.update(over)
    return c


def _board(tickers=("TK0", "TK1", "TK2"), **over):
    b = {"as_of": "2026-08-10", "lane": "closepass", "tickers": list(tickers),
         "card_complete": True, "cards": [_card(t) for t in tickers]}
    b.update(over)
    return b


def test_the_payload_must_prove_its_two_halves_agree():
    """THE REPLACEMENT for "payload vs. DOM" (spec §10.5). While the client is the thing
    putting cards in the DOM, comparing the payload to the DOM it just wrote proves
    nothing — so the payload's own `cards` must be exactly parallel to its own `tickers`
    before a single one is painted."""
    got = _pvc([
        {"fn": "cards", "board": _board()},                                    # 0 happy
        {"fn": "cards", "board": _board(card_complete=False)},                 # 1 not complete
        {"fn": "cards", "board": _board(cards=[_card("TK0"), _card("TK1")])},  # 2 short
        {"fn": "cards", "board": _board(                                       # 3 out of order
            cards=[_card("TK1"), _card("TK0"), _card("TK2")])},
        {"fn": "cards", "board": _board(tickers=[])},                          # 4 empty
        {"fn": "cards", "board": _board(                                       # 5 legs missing
            cards=[_card("TK0", signal=None), _card("TK1"), _card("TK2")])},
        {"fn": "cards", "board": _board(                                       # 6 runway junk
            cards=[_card("TK0", runway="lots"), _card("TK1"), _card("TK2")])},
        {"fn": "cards", "board": _board(                                       # 7 offsite link
            cards=[_card("TK0", href="https://evil.example/x"),
                   _card("TK1"), _card("TK2")])},
        {"fn": "cards", "board": None},                                        # 8 no board
        # `runway: null` is the ONE permitted null among the two legs — "not measured",
        # which the card says in words rather than binning as "already run"
        {"fn": "cards", "board": _board(                                       # 9 accepted
            cards=[_card("TK0", runway=None), _card("TK1"), _card("TK2")])},
    ])
    assert got[0] == "ok"
    assert got[1:9] == [None] * 8
    assert got[9] == "ok", "a null runway is a supported state, not a malformed payload"


def test_a_score_that_arrives_is_refused_rather_than_ignored():
    """Spec §10.2 — the evening lane scores 40 of 100 weight points, so a number must never
    reach the slot a reader has learned to read on the 100 scale. A producer that starts
    sending one has drifted, and the board refuses instead of quietly dropping the field."""
    got = _pvc([
        {"fn": "cards", "board": _board(
            cards=[_card("TK0", edge=40), _card("TK1"), _card("TK2")])},
        {"fn": "cards", "board": _board(
            cards=[_card("TK0", edge=0), _card("TK1"), _card("TK2")])},
        # an explicit null is the contract and must still pass
        {"fn": "cards", "board": _board(
            cards=[_card("TK0", edge=None), _card("TK1"), _card("TK2")])},
    ])
    assert got == [None, None, "ok"]


def test_the_verb_is_never_a_constant_and_comes_only_from_runway():
    """Spec §10.4-2/3. `runway` = 1 - clip01(ext_z/2), so the bands sit at ext_z <= 0.5 and
    <= 1.0; the verb splits at one full sigma of extension. `buy` is not in the vocabulary
    at all — a card may not out-claim the board it sits on, and the board says "Get
    ready"."""
    got = _pvc([{"fn": "room", "runway": r}
                for r in (1.0, 0.9, 0.75, 0.74, 0.6, 0.5, 0.49, 0.2, 0.0, -3, 7)])
    assert got == [
        ["ample", "near"], ["ample", "near"], ["ample", "near"],
        ["some", "near"], ["some", "near"], ["some", "near"],
        ["thin", "wait"], ["thin", "wait"], ["thin", "wait"],
        ["thin", "wait"],          # clamped below 0
        ["ample", "near"],         # clamped above 1
    ]
    assert {b for b, _ in got} == {"ample", "some", "thin"}
    assert {v for _, v in got} == {"near", "wait"}, "buy/hold/avoid are out of scope here"


def test_an_unmeasured_name_is_not_binned_as_one_that_has_already_run():
    """The engine's ranking leg scores an unmeasured extension as 0.0 — fail-closed, and
    right for ORDERING — but 0.0 is also what a name two full sigma out scores. Binning
    both as "Thin" would tell a reader "this one has run" about a name nobody measured,
    which is a claim rather than a caution. It gets its own words, and routes to the
    cautious verb (the ratified rule for unknown states, #2206).

    ~5 of 79 rows on the live artifact are this case, so it is not a corner."""
    got = _pvc([{"fn": "room", "runway": r} for r in (None, 0.0)])
    assert got[0] == ["unknown", "wait"]
    assert got[1] == ["thin", "wait"], "a MEASURED zero still reads as thin"
    assert got[0][0] != got[1][0], "unmeasured must not collapse into measured-extreme"
    # and the words differ on the card, not just in the band name
    html = _pvc([{"fn": "html", "board": _board(
        cards=[_card("TK0", runway=None), _card("TK1", runway=0.0), _card("TK2")])}])[0]
    first = html[:html.index('data-ticker="TK1"')]
    second = html[html.index('data-ticker="TK1"'):html.index('data-ticker="TK2"')]
    assert "Not checked" in first and "未检查" in first
    assert "Thin" in second and "有限" in second
    assert "Not checked" not in second


def test_the_mount_tears_the_board_down_when_the_paint_does_not_verify():
    """SPEC §10.5, AND THE POINT OF THIS WHOLE FILE. Once the client renders the cards the
    identity gate would be trivially true — so the mount reads the painted ticker order
    straight back and restores if it is not what was asked for.

    Delete the `env.read() !== want` check in `_pvcMount` and cases 1-4 return ok=true with
    restored=0, and this test fails. That is the whole design: a board that cannot prove it
    painted correctly never stays up long enough to be stamped.
    """
    b = _board()
    got = _pvc([
        {"fn": "mount", "board": b},                                   # 0 paints correctly
        {"fn": "mount", "board": b, "readback": "TK0|TK1"},            # 1 a card went missing
        {"fn": "mount", "board": b, "readback": "TK1|TK0|TK2"},        # 2 order came out wrong
        {"fn": "mount", "board": b, "readback": ""},                   # 3 nothing painted
        {"fn": "mount", "board": b, "readback": "TK0|TK1|TK2|TK9"},    # 4 something extra
    ])
    assert got[0]["ok"] is True and got[0]["restored"] == 0
    assert got[0]["tickers"] == ['data-ticker="TK0"', 'data-ticker="TK1"',
                                 'data-ticker="TK2"']
    for i in (1, 2, 3, 4):
        assert got[i]["ok"] is False, f"case {i} mounted a board it could not verify"
        assert got[i]["restored"] == 1, f"case {i} did not restore the nightly board"


def test_cards_without_a_stamp_are_refused_exactly_like_a_stamp_without_cards():
    """Both directions are the same lie. `_pvcWanted` asks the UNCHANGED board-state gate
    whether a page showing exactly these cards would earn the `ahead` stamp; if it would
    not, the cards are not painted either."""
    fresh = {"generated_at": _iso(_NOW - _HOUR), "valid_until": _iso(_NOW + _HOUR)}
    base = dict(rel="ahead", note="ahead", board=_board(), **fresh)

    def st(**over):
        s = dict(base)
        s.update(over)
        return s

    got = _pvc([
        {"fn": "wanted", "state": st(), "now": _NOW},                            # 0 happy
        {"fn": "wanted", "state": st(valid_until=_iso(_NOW - 1)), "now": _NOW},  # 1 expired
        {"fn": "wanted", "state": st(rel="behind"), "now": _NOW},                # 2 wrong rel
        {"fn": "wanted", "state": st(rel=None, note="confirmed"), "now": _NOW},  # 3 receipt
        {"fn": "wanted", "state": st(generated_at=_iso(_NOW - 200 * _HOUR),
                                     valid_until=_iso(_NOW + 9000 * _HOUR)),
         "now": _NOW},                                                           # 4 too old
        # a board whose mount already failed once is never retried — keyed on the board's
        # own identity (as-of + ordered tickers), the same key the mount is keyed on
        {"fn": "wanted", "state": st(), "now": _NOW,
         "refused": "2026-08-10#TK0|TK1|TK2"},                                   # 5
    ])
    assert got[0] == "ok"
    assert got[1:] == [None] * 5


def test_the_link_shape_the_nightly_board_already_uses_is_accepted():
    """The US nightly card links `stock.html#AAPL`, china `china_lookup.html#…`, hk
    `hk_lookup.html#…`. Refusing a trailing fragment would hard-refuse the whole evening
    board over a link shape the morning board already ships — while everything that could
    leave the site still has to be refused."""
    ok = ["stock.html#AAPL", "stocks/AAPL.html", "china_lookup.html#600519.SS",
          "hk_lookup.html#0700.HK", "stock.html"]
    bad = ["https://evil.example/x", "//evil.example/x", "/absolute", "../../etc/passwd",
           "javascript:alert(1)", "stock.html#a b", "stock.html?x=1",
           'stock.html"onmouseover="alert(1)']
    got = _pvc([{"fn": "cards",
                 "board": _board(cards=[_card("TK0", href=h), _card("TK1"), _card("TK2")])}
                for h in ok + bad])
    assert got[:len(ok)] == ["ok"] * len(ok), list(zip(ok, got))
    assert got[len(ok):] == [None] * len(bad), list(zip(bad, got[len(ok):]))
    # and the accepted one lands in the markup unmangled
    html = _pvc([{"fn": "html", "board": _board(
        cards=[_card("TK0", href="stock.html#TK0"), _card("TK1"), _card("TK2")])}])[0]
    assert 'href="stock.html#TK0"' in html


def test_a_republished_but_unchanged_board_is_not_remounted():
    """`board_state` rides an artifact the live producer rewrites every ~5 minutes. Keying
    the mount on a WRITE timestamp would tear the grid down and rebuild it on every poll —
    a flicker under a reader, their "show more" expansion reset each time, and a leaked
    resize listener per rebuild. The board is the same board while its as-of and its
    ordered tickers are, so the mount is keyed on that and nothing else."""
    fresh = {"generated_at": _iso(_NOW - _HOUR), "valid_until": _iso(_NOW + _HOUR)}
    same_board_later_write = dict(fresh, rel="ahead", note="ahead", board=_board())
    same_board_later_write["generated_at"] = _iso(_NOW - 60000)
    got = _pvc([
        {"fn": "id", "state": dict(fresh, rel="ahead", note="ahead", board=_board())},
        {"fn": "id", "state": same_board_later_write},
        # a genuinely different board — one name swapped — must NOT share the identity
        {"fn": "id", "state": dict(fresh, rel="ahead", note="ahead",
                                   board=_board(("TK0", "TK1", "TK9")))},
        # nor must a different session's board carrying the same names
        {"fn": "id", "state": dict(fresh, rel="ahead", note="ahead",
                                   board=_board(as_of="2026-08-11"))},
    ])
    assert got[0] == got[1], "a rewrite with no board change must not remount"
    assert got[0] != got[2] and got[0] != got[3]
    assert "2026-08-10" in got[0] and "TK0|TK1|TK2" in got[0]


def test_the_card_markup_degrades_rather_than_breaks_on_a_null_field():
    """The producer emits null rather than guessing, and every optional field is genuinely
    optional: no name, no sector, no sparkline, no price. A missing line is omitted, never
    rendered empty — the grid row stretches and .pv-zn's margin-top:auto keeps every zone
    row on one baseline, so a degraded card costs alignment nothing."""
    bare = _board(cards=[_card("TK0", name=None, name_zh=None, sec=None, sec_zh=None,
                               spark=None, price_txt=None),
                         _card("TK1"), _card("TK2")])
    html = _pvc([{"fn": "html", "board": bare}])[0]
    first = html[:html.index('data-ticker="TK1"')]
    assert "pv-nm" not in first and "pv-ind" not in first, "empty lines must be omitted"
    assert "pv-nochart" in first, "no spark still reserves the chip rail"
    assert "nb-px" not in first, "no price means no pill at all"
    for required in ('class="pvcard pv-near"', 'data-ticker="TK0"', "pv-chip",
                     "pv-edl", "pv-edn pv-edna", "pv-znm", "pv-dt"):
        assert required in first, required
    # and the slots §10.3 omits are absent from EVERY card
    for banned in ("pv-stp", "pv-stl", "pv-mk", "pv-live", "pv-trg", "pv-cau",
                   "data-stage", "pv-featured", "pv-triage"):
        assert banned not in html, banned


def test_the_quote_pill_mirrors_whatever_the_nightly_cards_use():
    """A live-change sibling is a per-board opt-in that may or may not have shipped; the
    evening card has to look like the morning card either way round, so the shape is
    measured off the page rather than assumed."""
    plain, withchg = _pvc([{"fn": "html", "board": _board()},
                           {"fn": "html", "board": _board(), "chg": True}])
    assert '<span class="pv-ov pv-ovr"><span class="nb-px pv-px"' in plain
    assert "nb-chg" not in plain
    assert '<span class="pv-quote"><span class="nb-px pv-px"' in withchg
    # live.js replaces the price node's textContent, so the percentage must be a SIBLING
    assert re.search(r'<span class="nb-px pv-px"[^>]*>[^<]*</span>'
                     r'<span class="nb-chg pv-chg"', withchg)


def test_a_sparkline_that_is_not_a_drawing_is_dropped_not_rendered():
    """The artifact is same-origin and auth-gated, which is a reason to be calm and not a
    reason to skip the check: innerHTML does not run <script>, but it does run an SVG
    event handler. A dropped spark is an already-supported state."""
    evil = [
        '<svg onload="alert(1)"><path d="M0 0"/></svg>',
        # `/` is a valid attribute separator inside a start tag, so these parse exactly as
        # `<svg onload=…>`. A \s-anchored pattern waved them straight through.
        '<svg/onload=alert(1)></svg>',
        '<svg//onload=alert(1)><path d="M0 0"/></svg>',
        '<svg\tonload=alert(1)></svg>',
        '<svg><script>alert(1)</script></svg>',
        '<svg><animate onbegin="alert(1)"/></svg>',
        # `set`/`animate` write an attribute onto another element — including a handler
        '<svg><set attributeName="onload" to="alert(1)"/></svg>',
        '<svg><animateTransform attributeName="onload" to="alert(1)"/></svg>',
        '<svg><style>@import url(//evil.example/x)</style></svg>',
        '<svg><foreignObject><b>x</b></foreignObject></svg>',
        '<svg><image href="javascript:alert(1)"/></svg>',
        '<svg><a href="vbscript:alert(1)"><path d="M0 0"/></a></svg>',
        '<img src=x onerror="alert(1)">',
    ]
    boards = [_board(cards=[_card("TK0", spark=s), _card("TK1"), _card("TK2")])
              for s in evil]
    good = _board(cards=[
        _card("TK0", spark='<svg viewBox="0 0 2 2"><path d="M0 0L2 2"/></svg>'),
        _card("TK1"), _card("TK2")])
    got = _pvc([{"fn": "html", "board": b} for b in boards]
               + [{"fn": "html", "board": good}])
    for html, src in zip(got[:-1], evil):
        low = html.lower()
        for token in ("onload", "onerror", "onbegin", "<script", "foreignobject",
                      "javascript:", "vbscript:", "@import", "<set", "<animate"):
            assert token not in low, f"{src!r} leaked {token!r}"
        assert html.count("pv-nochart") == 3, f"{src!r} should have fallen back"
    assert "<path" in got[-1] and got[-1].count("pv-nochart") == 2, "a real drawing survives"
