"""tests/test_prophet_live_surface.py — Prophet Live P1 user-facing surfaces.

Covers the two surfaces the P1 design spec (``research/PROPHET_LIVE_P1_DESIGN_SPEC.md``)
adds to the us_stocks board:

  1. the "Forming today" strip in ``templates/dashboard.html.j2`` (SSR shell + page-inline
     CSS + the client render contract), and
  2. the reserved ◐ live chip in ``templates/_prophet_card.html.j2``.

WHY THIS SUITE IS BROWSER-FREE. The CI packs install a minimal dependency set, not
``requirements.txt`` — a ``pytest.importorskip("playwright")`` here would SKIP in CI and
report green while proving nothing (house trap: ci-packs-install-minimal-deps-not-requirements).
So everything mechanically checkable is asserted against the rendered template and the
shipped CSS/JS source text. The measurements that genuinely need a browser — height
invariance, computed hues, the DOM fence, row-cell geometry at every breakpoint — live in
``mockups/refs/prophet_live/verify_p1.py``, which is run by hand and whose output is pasted
into the PR body. Do NOT "upgrade" these to browser tests; they would stop running.

The assertions are deliberately about the LAWS, not the wording: presentation-tier fencing,
the banned vocabulary, the freshness disclosure, honest degradation, the derived height
contract, and the two payload fields that must degrade to an em-dash rather than be derived.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DASH = (ROOT / "templates" / "dashboard.html.j2").read_text()
CARD = (ROOT / "templates" / "_prophet_card.html.j2").read_text()

#: Words that may never describe a provisional intraday read as a settled fact
#: (G0.6 + operator 2026-07-27). The nightly build is the only confirmer, and
#: falsifier vocabulary is never front-facing.
BANNED_GLANCE = ("fired", "confirmed", "triggered", "refuted", "falsifier",
                 "validated", "证伪", "已触发", "已确认")


# --------------------------------------------------------------------------- #
# Source slicing helpers
# --------------------------------------------------------------------------- #

def _open_comment_before(marker: str) -> int:
    """Index of the `/*` that OPENS the comment containing `marker`.

    Both slices must start at a comment boundary, not inside one: starting mid-comment
    leaves a dangling `*/` and _nc() then pairs the next `/*` with a later `*/`, silently
    deleting real code and keeping comment prose. That mis-alignment made two vocabulary
    assertions read the header comment instead of the source.
    """
    return DASH.rindex("/*", 0, DASH.index(marker))


def _strip_css() -> str:
    """The page-inline `<style>` block that owns the strip."""
    i = _open_comment_before("── PROPHET LIVE strip (P1, spec §3)")
    return DASH[i:DASH.index("</style>", i)]


def _strip_js() -> str:
    """The inline JS region that renders the strip and the card chips.

    Ends at the enclosing `</script>` — NOT at the first `})();`, which belongs to the
    little names-island IIFE near the top of the block.
    """
    i = _open_comment_before('PROPHET LIVE P1 — the "Forming today" strip')
    return DASH[i:DASH.index("</script>", i)]


def _strip_markup() -> str:
    """The SSR shell, from the panel open tag to the names island."""
    i = DASH.index('id="prophet-live"')
    return DASH[DASH.rindex("<div", 0, i):DASH.index('id="plv-names"', i)]


def _nc(src: str) -> str:
    """Strip comments. Every assertion about CODE runs on this, so that a comment
    *explaining* a banned word (e.g. "nothing here says fired/confirmed") cannot satisfy
    or violate a check about what the code actually does."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)


def _copy_table(name: str) -> dict:
    """Pull one `var PLV_X = { ... };` copy table out of the JS as EN/ZH pairs."""
    js = _strip_js()
    body = js[js.index("var %s = {" % name):]
    body = body[:body.index("\n};")]
    pairs: dict[str, tuple[str, str]] = {}
    for key, blob in re.findall(r"(\w+):\s*\[(.+?)\]", body, re.S):
        lits = re.findall(r"""(['"])((?:\\.|(?!\1).)*)\1""", blob)
        vals = [v for _q, v in lits]
        if len(vals) >= 2:
            pairs[key] = (vals[0], vals[1])
    return pairs


def _render(mode: str, **over):
    from tests.test_dashboard_template_render import _base_vm, _env
    vm = _base_vm()
    vm.update(over)
    return _env().get_template("dashboard.html.j2").render(**vm, mode=mode)


@pytest.fixture(scope="module")
def stocks_html() -> str:
    return _render("stocks")


@pytest.fixture(scope="module")
def macro_html() -> str:
    return _render("macro")


# --------------------------------------------------------------------------- #
# G-A · Presentation tier only
# --------------------------------------------------------------------------- #

def test_strip_is_its_own_panel_outside_the_graded_board(stocks_html):
    """The strip is a sibling panel, never a block inside #us-standouts.

    Doctrine Law 4 allows one as-of stamp per panel and the two clocks are different
    objects: the board carries the nightly close vintage, the strip an intraday quote age.
    It also keeps the strip physically outside the graded board's subtree (DNR §1).
    """
    i, j = stocks_html.index('id="prophet-live"'), stocks_html.index('id="us-standouts"')
    assert i < j, "the strip must render before the board panel"
    # the panel's own closing tag sits before the names island, which sits before the board
    island = stocks_html.index('id="plv-names"')
    assert i < stocks_html.rindex("</div>", i, island) < island < j, \
        "the strip panel must be closed before #us-standouts opens"


def test_js_writes_only_to_the_strip_and_the_reserved_chip_slot():
    """§6.5 fence at the source level: no graded-board node is a write target.

    The board's own classes may not be assigned to, have innerHTML written, or be
    classList-toggled by this block. (The browser-side proof that a payload change leaves
    the board byte-identical is in verify_p1.py's DOM FENCE section.)
    """
    js = _strip_js()
    for owned in ("pv-chip", "pv-edn", "pv-trg", "pv-zn", "pv-stp", "pv-stl",
                  "pv-edge", "pv-cau", "nbgrid", "us-standouts", "USStockTable"):
        for verb in (".className", ".innerHTML", ".classList", ".remove(", ".appendChild"):
            assert f"{owned}'{verb}" not in js and f'{owned}"{verb}' not in js, \
                f"{owned} must never be a write target of the prophet_live block"
    # the ONLY card node it may touch
    assert ".pv-ov.pv-ovl > .pv-live" in js
    assert "pv-live" in js


def test_card_macro_adds_only_a_reserved_empty_slot():
    """The nightly card SSR gains one always-present, empty, hidden span — nothing else."""
    assert '<span class="pv-live" hidden></span>' in CARD
    # ordered after the nightly ⚡ chip and before the ⚠N popover — compared inside the
    # MARKUP macro, since every class name also appears earlier in pv_css().
    body = CARD[CARD.index("{% macro pv_card(cx) %}"):]
    assert body.index('class="pv-trg') < body.index('<span class="pv-live" hidden></span>') \
        < body.index('class="pv-cau-btn"')


def test_reserved_slot_renders_hidden_on_every_board_card(stocks_html):
    assert stocks_html.count('<span class="pv-live" hidden></span>') >= 2


# --------------------------------------------------------------------------- #
# G-B · Vocabulary
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("table", ["PLV_TOKEN", "PLV_SUB", "PLV_CHIP", "PLV_CARD", "PLV_DARK"])
def test_glance_tier_copy_carries_no_settled_fact_vocabulary(table):
    """Chips, tokens, stance lines and dark reasons are the GLANCE tier.

    Nothing there may read as a settled fact. (Tier-2 tips are exempt on purpose: they
    say "Nothing is confirmed: tonight's close decides", which is a denial, and the help
    receipt names the nightly build as the only confirmer.)
    """
    for key, (en, zh) in _copy_table(table).items():
        low = en.lower()
        for word in BANNED_GLANCE:
            assert word not in low and word not in zh, \
                f"{table}.{key} says {word!r}: {en!r} / {zh!r}"


def test_every_state_settles_at_tonights_close_in_both_languages():
    """The footer sentence is the one place that must always carry the settle clause."""
    js = _strip_js()
    assert "settles at tonight" in js
    assert "以今晚收盘为准" in js
    # and the stance line says it for the live case
    sub = _copy_table("PLV_SUB")
    assert "nothing is settled until tonight" in sub["live"][0].lower()
    assert "今晚收盘才算数" in sub["live"][1]


def test_faded_via_drop_and_overrun_never_share_a_word():
    """`via` selects the word; "faded" is only ever the drop story.

    An overrun ran PAST the range the gate still admits — the opposite trade from falling
    through it. Sharing a word would lie about direction and pollute the axis the P0
    forward ledger measures.
    """
    chip = _copy_table("PLV_CHIP")
    assert chip["drop"][0] != chip["over"][0] and chip["drop"][1] != chip["over"][1]
    assert "fade" not in chip["over"][0].lower()
    # the house word survives in the Tier-2 tip for the drop story only
    tip = _copy_table("PLV_TIP")
    assert "faded" in tip["drop"][0].lower()
    assert "faded" not in tip["over"][0].lower()


def test_at_risk_is_never_surfaced_as_a_state_name_or_a_sell_call():
    """`at_risk` is internal; the card says "Below range", a statement about the tape."""
    card = _copy_table("PLV_CARD")
    assert card["drop"][0] == "Below range"
    for _k, (en, zh) in card.items():
        assert "risk" not in en.lower() and "风险" not in zh
    tips = _copy_table("PLV_CARD_TIP")
    assert "not a sell call" in tips["drop"][0].lower()
    assert "这不是卖出建议" in tips["drop"][1]


def test_no_falsifier_or_refutation_language_anywhere_in_the_block():
    """Operator 2026-07-27: falsifier language is never front-facing on a cycle surface."""
    js = _nc(_strip_js()).lower()
    for word in ("falsifier", "refuted", "证伪", "thesis refuted"):
        assert word not in js, f"{word!r} reaches the code, not just a comment"


# --------------------------------------------------------------------------- #
# G-C · Freshness on every live number
# --------------------------------------------------------------------------- #

def test_state_token_always_discloses_the_delay():
    tok = _copy_table("PLV_TOKEN")
    assert "delayed" in tok["rth"][0].lower() and "延迟" in tok["rth"][1]
    assert "delayed" in tok["preopen"][0].lower() and "延迟" in tok["preopen"][1]
    assert "{d}" in tok["rth"][0] and "{d}" in tok["rth"][1]


def test_null_delay_drops_the_number_never_guesses_fifteen():
    """delay_min is the VENDOR floor. Absent ⇒ "delayed" with no figure."""
    js = _nc(_strip_js())
    fill = js[js.index("function _plvFill"):js.index("function _plvPick")]
    assert "d===null" in fill
    assert "'{d}-min '" in fill and "''" in fill        # the number is removed
    assert "15" not in fill, "a fallback 15 would invent a vendor floor"


def test_one_as_of_stamp_in_both_clock_conventions():
    js = _strip_js()
    asof = _nc(js)[_nc(js).index("function _plvAsOf"):_nc(js).index("function _plvNum")]
    assert "as of " in asof and " ET" in asof
    assert "截至 美东 " in asof
    assert "_plvHm12" in asof and "_plvHm24" in asof


def test_no_live_pulse_or_status_dot_is_designed():
    """A green pulse is unreachable on a 15-min-delayed plane AND encodes certainty."""
    css, js = _nc(_strip_css()), _nc(_strip_js())
    assert "plv-dot" not in css and "plv-dot" not in js
    anims = set(re.findall(r"animation:([^;}]+)", css))
    assert anims == {"plv-in .2s ease-out", "none"}, \
        f"the only motion is the 200ms opacity fade on a genuinely new row: {anims}"
    assert "--up" not in css and "--down" not in css, \
        "no directional token: the component must not flip hue under zh 红涨绿跌"


def test_settle_rail_is_the_proof_of_life_and_ticks_without_a_fetch():
    js = _strip_js()
    assert "function _plvRail" in js
    rail = _nc(js)[_nc(js).index("function _plvRail"):_nc(js).index("function _plvMode")]
    assert "fetch" not in rail
    assert "PLV_OPEN" in rail and "PLV_CLOSE" in rail
    assert "setInterval(_plvRail, PLV_TICK)" in js
    assert "var PLV_TICK  = 60000" in js


# --------------------------------------------------------------------------- #
# G-D · Honest degradation — four distinct forms
# --------------------------------------------------------------------------- #

def test_four_distinct_modes_exist_with_distinct_stance_lines():
    sub = _copy_table("PLV_SUB")
    assert set(sub) == {"live", "quiet", "dark", "closed"}
    assert len({v[0] for v in sub.values()}) == 4
    assert len({v[1] for v in sub.values()}) == 4


def test_dark_stance_says_the_board_below_is_unaffected():
    """An error state tells the reader what to do instead — it does not apologise."""
    sub = _copy_table("PLV_SUB")
    assert "board below is unaffected" in sub["dark"][0].lower()
    assert "下方看板不受影响" in sub["dark"][1]


def test_dark_reasons_are_plain_words_with_no_machine_vocabulary():
    for key, (en, zh) in _copy_table("PLV_DARK").items():
        for machine in ("pack", "stale_", "out_of_band", "debounce", "arming", "at_risk"):
            assert machine not in en.lower(), f"PLV_DARK.{key} leaks {machine!r}"
        assert zh and zh != en
    dark = _copy_table("PLV_DARK")
    assert set(dark) == {"no_pack", "stale_pack", "quotes"}
    assert len({v[0] for v in dark.values()}) == 3


def test_closed_mode_is_resolved_before_the_staleness_gates():
    """Without this ordering the age gate fires every evening and the strip lies
    "prices aren't updating" after every single close — a nightly lie, not an edge case."""
    js = _nc(_strip_js())
    mode = js[js.index("function _plvMode"):js.index("function _plvHide")]
    i_closed = mode.index("mode:'closed'")
    i_status = mode.index("d.status==='dark'")
    i_age = mode.index("PLV_MAXAGE")
    i_major = mode.index("0.5")
    assert i_closed < i_status < i_age < i_major, \
        "spec §6.2 order: closed (3) before status-dark (4) before age (5) before majority (6)"


def test_stale_session_never_presents_as_today():
    js = _nc(_strip_js())
    mode = js[js.index("function _plvMode"):js.index("function _plvHide")]
    assert "session_et!==et.ymd" in mode.replace(" ", "")
    assert mode.index("session_et") < mode.index("mode:'closed'")


def test_majority_dark_never_ships_a_confident_quiet_tape():
    """Speaking a calm "nothing crossing" while >half the armed names are unreadable is
    degraded-ships-confident."""
    js = _nc(_strip_js())
    mode = js[js.index("function _plvMode"):js.index("function _plvHide")]
    assert "dark_counts" in mode and "evaluated_n" in mode and ">=0.5" in mode.replace(" ", "")


def test_closed_and_dark_read_frozen_states_from_prev_states():
    """A dark artifact carries the same session's last per-name states under
    ``prev_states`` precisely so one bad pass cannot erase the day."""
    js = _strip_js()
    assert "d.prev_states" in js


def test_absent_artifact_leaves_the_panel_hidden(stocks_html):
    """Graceful-absent (FT-R8): no file ⇒ silence, not an empty box."""
    assert re.search(r'id="prophet-live"[^>]*\shidden', stocks_html)
    assert "#prophet-live{--plv:#62a0e8;--plv-rh:27px;display:none}" in _strip_css()
    assert "#prophet-live.visible{display:block}" in _strip_css()
    js = _strip_js()
    catch = js[js.index(".catch(function(){"):]
    assert "if(_plvData) _plvRender();" in catch, \
        "a later failure keeps the last good render until the age gate trips it"


def test_per_name_dark_names_are_never_rendered_as_a_guessed_state():
    """`dormant` / `near` / per-name `dark` are excluded from the row set entirely."""
    js = _nc(_strip_js())
    pick = js[js.index("function _plvPick"):js.index("function _plvCapRows")]
    assert "'forming'" in pick and "'faded'" in pick
    for excluded in ("dormant", "'near'", "'dark'"):
        assert excluded not in pick, f"{excluded} must not reach a strip row"


# --------------------------------------------------------------------------- #
# G-E · Coverage honesty
# --------------------------------------------------------------------------- #

def test_footer_owns_the_coverage_bound_in_both_languages():
    js = _strip_js()
    assert "names sitting near a decision are checked intraday" in js
    assert "盘中仅检查接近临界的" in js
    assert "meta.evaluated_n" in js


def test_coverage_sentence_degrades_without_a_count_instead_of_guessing():
    js = _strip_js()
    fn = _nc(js)[_nc(js).index("var ev=Number(meta.evaluated_n)"):
                 _nc(js).index("var help=document.getElementById('plv-help')")]
    assert "Only the names sitting near a decision" in fn, \
        "no evaluated_n ⇒ the sentence drops the figure, it does not invent one"
    assert "盘中仅检查接近临界的标的" in fn


def test_universe_is_ssr_baked_and_the_receipt_is_a_ratio(stocks_html):
    """`us_standouts.universe` does not change intraday, so it is baked; the intraday
    count is patched in. Together they are the coverage receipt (Tier 2)."""
    # absent key ⇒ no attribute at all, and the receipt drops the ratio rather than guess
    assert "data-universe=" not in _render("stocks", us_standouts={"buy": []})
    html = _render("stocks", us_standouts={"buy": [], "universe": 1578})
    assert 'data-universe="1578"' in html
    js = _strip_js()
    assert "scored names were armed tonight" in js
    assert "全部评分股票" in js


def test_unprobed_is_never_implied_to_be_dormant():
    js = _strip_js()
    assert "out of coverage, not dormant" in js.lower() or "OUT OF COVERAGE" in js


# --------------------------------------------------------------------------- #
# G-F · No layout thrash
# --------------------------------------------------------------------------- #

def test_height_contract_is_derived_from_the_row_height_not_guessed_twice():
    """Two independently hand-measured numbers cannot stay equal — and did not: the spec's
    24.5px row measured 26.06px on the real page (this page inherits line-height 1.5) and
    the strip came out 4.69px taller in live than in quiet. The reservation is now
    calc(--plv-rh * 3 + 2px) against a FIXED row height, so invariance is structural."""
    css = _strip_css()
    assert "--plv-rh:27px" in css
    assert ".plv-body{min-height:calc(var(--plv-rh) * 3 + 2px)" in css
    assert "height:var(--plv-rh)" in css
    assert "min-height:24.5px" not in css and "min-height:75.5px" not in css


def test_empty_body_fills_the_reservation_and_has_no_height_of_its_own():
    css = _strip_css()
    assert ".plv-none{flex:1" in css


def test_column_labels_hide_rather_than_collapse_in_the_empty_modes():
    css = _strip_css()
    assert "#prophet-live.is-empty .plv-cols > span{visibility:hidden}" in css


def test_header_items_share_one_line_box_and_a_pinned_two_line_mobile_header():
    css = _strip_css()
    assert ".plv-hd > *{min-height:17px" in css
    mob = css[css.index("@media (max-width:680px)"):]
    assert ".plv-hd{row-gap:0}" in mob
    assert '.plv-hd::before{content:"";order:2;flex:0 0 100%;height:4px}' in mob, \
        "the token must start line 2 regardless of its own string length"
    for sel, order in ((".plv-more", 1), (".plv-token", 3), (".plv-asof", 4)):
        assert f"{sel}{{order:{order}" in mob.replace(";margin-left:auto}", "}") \
            or f"order:{order}" in mob


def test_every_grid_cell_is_pinned_to_its_column():
    """Auto-placement RESHUFFLES when a middle cell is hidden: the ≤560px rule hides
    .plv-nm (column 3), which slid `now` into that zero-width column and printed it on
    top of `cross level` at 375px. Pinning makes a demotion a no-op for the rest."""
    css = _nc(_strip_css())
    # every declaration block that pins a grid-column, as {selector: column}
    pinned = {}
    for sels, col in re.findall(r"([^{}\n]+)\{grid-column:(\d)\}", css):
        for sel in sels.split(","):
            pinned[sel.strip()] = int(col)
    for sel, col in ((".plv-row > .plv-chip", 1), (".plv-tk", 2), (".plv-nm", 3),
                     (".plv-now", 4), (".plv-lvl", 5), (".plv-since", 6),
                     (".plv-c1", 1), (".plv-c2", 4), (".plv-c3", 5), (".plv-c4", 6)):
        assert pinned.get(sel) == col, \
            f"{sel} must be pinned to column {col}, got {pinned.get(sel)!r}"


def test_row_cap_is_three_and_a_faded_row_is_never_the_silent_cut():
    js = _strip_js()
    assert "var PLV_CAP   = 3" in js
    cap = _nc(js)[_nc(js).index("function _plvCapRows"):_nc(js).index("function _plvRowHtml")]
    assert "faded" in cap and "cap-1" in cap
    assert "keepFaded=faded[faded.length-1]" in cap


def test_overflow_goes_to_a_user_initiated_more_button(stocks_html):
    assert 'class="plv-more" id="plv-more" type="button" aria-expanded="false" hidden' in stocks_html
    js = _strip_js()
    assert "_plvExpanded" in js and "aria-expanded" in js
    assert "'+hidden+' more'" in js and "还有 '+hidden+'" in js


def test_rows_are_reconciled_by_key_never_wholesale_replaced():
    js = _strip_js()
    paint = _nc(js)[_nc(js).index("function _plvPaintRows"):_nc(js).index("function _plvPaintNone")]
    assert "data-plv-tk" in paint and "insertBefore" in paint
    assert "body.innerHTML" not in js, \
        "wholesale replacement flashes every row and kills an open hover tip mid-read"
    assert "data-plv-sig" in paint, "rows are only rewritten when their content changed"


def test_stance_line_changes_only_on_a_mode_change():
    js = _strip_js()
    assert "if(mode!==_plvLastMode){" in js


def test_the_only_inline_style_written_is_the_rail():
    js = _strip_js()
    styles = re.findall(r"\.style\.(\w+)", js)
    assert set(styles) <= {"width", "left"}, f"unexpected inline styles: {set(styles)}"


def test_reduced_motion_kills_the_only_animation():
    css = _strip_css()
    assert "@media (prefers-reduced-motion:reduce){.plv-row.is-new{animation:none}}" in css


# --------------------------------------------------------------------------- #
# G-G · Bilingual
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("table", ["PLV_TOKEN", "PLV_SUB", "PLV_DARK", "PLV_CHIP",
                                   "PLV_TIP", "PLV_CARD", "PLV_CARD_TIP"])
def test_every_copy_string_has_a_real_zh_twin(table):
    pairs = _copy_table(table)
    assert pairs, f"{table} did not parse"
    for key, (en, zh) in pairs.items():
        assert en and zh, f"{table}.{key} is missing a language"
        if not key.endswith("--"):
            assert zh != en, f"{table}.{key} ships EN text as ZH"
            assert re.search(r"[一-鿿]", zh), f"{table}.{key} ZH has no CJK"


def test_static_ssr_copy_is_bilingual(stocks_html):
    for en, zh in (("Forming today", "今日正在形成"), ("Now", "当前"),
                   ("Cross level", "上穿价位"), ("Since", "起始"),
                   ("settles 4:00 pm ET", "美东 16:00 结算")):
        assert f'<span class="l-en">{en}</span><span class="l-zh">{zh}</span>' in stocks_html


def test_no_translated_text_inside_a_title_attribute(stocks_html):
    """CI guard parity (scripts/check_title_i18n.py). Tips ride on data-tip-en/zh, which
    theme.js's delegated LENS engine picks up even on client-rendered nodes."""
    for attr in re.findall(r'title="([^"]*)"', stocks_html):
        assert not re.search(r"[一-鿿]", attr), f"CJK in title=: {attr!r}"
    js = _strip_js()
    assert "title=" not in js
    assert "data-tip-en" in js and "data-tip-zh" in js


def test_mono_numerals_are_for_figures_only():
    css = _strip_css()
    for sel in (".plv-now", ".plv-lvl", ".plv-since"):
        assert sel in css
    figs = css[css.index(".plv-now,.plv-lvl,.plv-since{"):]
    assert "font-family:var(--font-mono" in figs[:200]
    assert ".plv-fig  {" not in css       # the footer figure gets tabular-nums, not mono
    assert ".plv-fig{font-variant-numeric:tabular-nums" in css
    # no words are set in mono
    for wordy in (".plv-sub", ".plv-fn", ".plv-title", ".plv-chip"):
        blk = css[css.index(wordy + "{"):css.index("}", css.index(wordy + "{"))]
        assert "font-mono" not in blk, f"{wordy} must not be mono — words are never mono"


# --------------------------------------------------------------------------- #
# Payload contract (§6.6) — degrade, never derive
# --------------------------------------------------------------------------- #

def test_since_and_cross_level_degrade_to_an_em_dash():
    """`passes × 5 min` is NOT a lawful duration (GitHub cron lands minutes late) and a
    level the payload does not carry must not be invented. Both cells print — instead."""
    js = _nc(_strip_js())
    row = js[js.index("function _plvRowHtml"):js.index("function _plvPaintRows")]
    assert "since_ts" in js
    assert "r.since===null?'—'" in row
    assert "cross_px" in row and "cross_level" in row
    px = js[js.index("function _plvPx"):js.index("var PLV_TOKEN")]
    assert "'—'" in px
    assert "passes" not in row, "a duration derived from the pass count is not lawful"


def test_row_include_filter_is_the_editorial_fence():
    """Only names that crossed TODAY and are not on last night's board. Board names get a
    card chip; a strip that also listed them would be a state dump."""
    js = _nc(_strip_js())
    pick = js[js.index("function _plvPick"):js.index("function _plvCapRows")]
    assert "st.entered !== 'cross'" in pick
    cards = _nc(js)[_nc(js).index("function _plvPaintCards"):_nc(js).index("function _plvRail")]
    assert "st.entered==='board'" in cards


def test_row_order_is_deterministic_and_never_dict_order():
    js = _strip_js()
    pick = js[js.index("out.sort(function"):js.index("return out;")]
    assert "a.rank-b.rank" in pick
    assert "as-bs" in pick
    assert "a.tk<b.tk" in pick, "ties must break on ticker, not on key iteration order"


def test_schema_is_checked_before_the_payload_is_trusted():
    js = _strip_js()
    assert "prophet_live.states/" in js


def test_source_path_is_the_live_family(stocks_html):
    js = _strip_js()
    assert "var PLV_URL   = 'live/prophet_live.json'" in js
    assert "var PLV_EVERY = 120000" in js
    assert "var PLV_FLOOR = 30000" in js


def test_first_fetch_is_never_gated_on_document_hidden():
    """The preview pane renders with visibility:hidden, so a visibility-gated first fetch
    produces a permanently empty strip in every verification screenshot."""
    js = _nc(_strip_js())
    boot = js[js.index("if(_plvPanel){"):]
    first = boot.index("_plvFetch();")
    guard = boot.index("if(!document.hidden) _plvFetch();")
    assert first < guard, "the unconditional first fetch must come before the interval"
    assert "document.hidden" not in boot[:first], \
        "nothing may gate the first paint on visibility"


# --------------------------------------------------------------------------- #
# Card chip CSS (§5.3) + the pre-existing overlay bug
# --------------------------------------------------------------------------- #

def test_pv_live_hidden_rule_is_present():
    """A class-level `display` out-specifies the UA [hidden] rule. Without this line every
    card on every prophet board grows an empty mystery pill."""
    assert ".pv-live[hidden]{display:none}" in CARD


def test_live_chip_does_not_follow_the_card_hue():
    """The one deliberate exception to the one-hue law: painting an at_risk chip with
    --pvh would render it GREEN on a Buy card, i.e. claim the live read is part of the
    confirmed verdict — the exact false claim this program exists to avoid."""
    i = CARD.index(".pv-live{")
    blk = CARD[i:CARD.index(".pv-live--close", i)]
    assert "--pvh" not in blk
    assert "--plvc:#62a0e8" in blk
    assert 'html[data-theme="light"] .pv-live{--plvc:#2f6fd0}' in CARD
    assert ".pv-live--drop,.pv-live--over{--plvc:var(--pv-wait)}" in CARD
    # and the nightly ⚡ chip is untouched
    trg = CARD[CARD.index(".pv-trg{"):CARD.index(".pv-trg.pv-trg-soon")]
    assert "var(--pvh)" in trg


def test_live_chip_is_not_solid_filled_on_a_card():
    """A solid pill out-weighs an outlined verb chip, and the card's verb must stay its
    ruling stance. The fill escalation lives on the strip, where a cross is news."""
    blk = CARD[CARD.index(".pv-live--close{"):CARD.index(".pv-live--drop")]
    assert "color-mix" in blk and "background:var(--plvc)" not in blk
    # on the strip it IS solid — that is where the escalation belongs
    assert ".plv-chip--close{background:var(--plv);color:#fff" in _strip_css()


def test_overlay_wrap_is_promoted_out_of_the_mobile_block():
    """PRE-EXISTING BUG fixed in passing: the rule lived only inside
    @media (max-width:680px), so at desktop width a left overlay wider than
    .pv-ov{max-width:70%} did not wrap and the excess chip clipped BEHIND the price pill.
    Measured at 1400px: the old rule came to -9.4px (clipping), the shipped rule clears by
    +34.7px, and the card height is identical either way (the overlay is absolutely
    positioned). See verify_p1.py's OVERLAY WRAP sweep."""
    rule = ".pv-ov.pv-ovl{flex-wrap:wrap;row-gap:3px}"
    assert rule in CARD
    mobile = CARD[CARD.index("@media (max-width:680px){"):]
    assert rule not in mobile, "the rule must apply at EVERY width, not only on mobile"
    assert CARD.index(rule) < CARD.index("@media (max-width:680px){")


def test_live_chip_collapses_to_the_glyph_on_narrow_cards():
    mobile = CARD[CARD.index("@media (max-width:680px){"):]
    assert ".pv-live .l-en,.pv-live .l-zh{display:none!important}" in mobile
    assert ".pv-live{padding:2px 5px;gap:0}" in mobile


# --------------------------------------------------------------------------- #
# SSR shell + names island
# --------------------------------------------------------------------------- #

def test_strip_renders_only_on_the_stocks_board(stocks_html, macro_html):
    assert 'id="prophet-live"' in stocks_html
    assert 'id="prophet-live"' not in macro_html
    assert "PROPHET LIVE strip (P1, spec" not in macro_html


def test_shell_ships_no_state_text(stocks_html):
    """Every [js] slot is empty in the SSR — a baked state would be a frozen claim."""
    shell = _strip_markup()
    for slot in ("plv-token", "plv-sub", "plv-body", "plv-fn", "plv-asof"):
        assert re.search(r'id="%s"></' % slot, shell), f"#{slot} must ship empty"


def test_help_receipt_ships_empty_and_is_handed_to_the_shared_popover(stocks_html):
    """The receipt carries the intraday coverage count, so baking it would ship a stale
    number. Empty l-en/l-zh keep theme.js's upgradeOne from freezing a placeholder."""
    assert '<span class="help" id="plv-help">?<span class="tip tip-wide">' \
           '<span class="l-en"></span><span class="l-zh"></span></span></span>' in stocks_html
    js = _strip_js()
    assert "window.upgradeHelpIcons(_plvPanel)" in js
    assert "help.hasAttribute('data-tip-en')" in js, \
        "an already-upgraded icon reads the attributes, not the nested spans"


def test_names_island_is_a_display_only_label_lookup():
    html = _render("stocks", us_standouts={
        "buy": [{"ticker": "AAA", "name": "Alpha Inc", "sector": "Industrials"}],
        "watch": [{"ticker": "BBB", "name": "Beta Corp", "sector": "Energy"}],
        "leaders": [], "laggards": [], "eligible": 1, "universe": 1578})
    m = re.search(r'<script type="application/json" id="plv-names">(.*?)</script>', html, re.S)
    assert m, "the names island must render"
    names = json.loads(m.group(1))
    assert names["AAA"] == "Alpha Inc" and names["BBB"] == "Beta Corp"


def test_names_island_is_empty_and_harmless_without_a_board():
    html = _render("stocks", us_standouts=None)
    m = re.search(r'<script type="application/json" id="plv-names">(.*?)</script>', html, re.S)
    assert m and json.loads(m.group(1)) == {}


def test_strip_still_renders_when_the_board_panel_is_absent():
    """The strip is not conditional on us_standouts.buy — a day with no board still has
    crosses to surface, and the coverage footer degrades on its own."""
    html = _render("stocks", us_standouts=None,
                   action_board={"hold": [], "avoid": [], "notable": [], "buy": []})
    assert 'id="prophet-live"' in html
