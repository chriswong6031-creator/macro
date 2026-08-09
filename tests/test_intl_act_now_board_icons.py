"""tests/test_intl_act_now_board_icons.py — the China / Canada / HK hover-card mark contract.

Doctrine §5.8 (2026-08-03): "Emoji are not UI icons — they read as clip-art on white and
render inconsistently headless; use the monoline set in templates/_icons.html.j2." PR #4735
swept the US Act-Now board; the three international boards kept passing the emoji 🏛 (and,
on China, the text glyph ◆) into the shared 34px `.row-pop-mark` tile of
templates/_decision_card.html.j2 until the sweep that this suite fences.

tests/test_act_now_board_icons.py is the model and covers the US board only. These are its
three international siblings — the China four-lane partial, canada.html.j2, hk.html.j2 —
and each one gets the same three fences:

  (1) the RENDERED mark tile draws an <svg class="ic-svg">, and no 🏛 survives the board;
  (2) a `.row-pop-mark .ic-svg` sizing rule ships at 17px and is NOT id-scoped;
  (3) the board's own <style> block emits no bare `.ic-svg {}` rule.

Every fence judges the RENDERED board, not the source, for the reason the US suite gives:
a source grep can only prove a string is absent from one file — it cannot catch an icon
that renders as escaped text (`&lt;svg`), a rule that never reaches the element it names,
or a host that inlined a divergent copy. The two source-level fences left are the China
two-host pair at the foot of this file, which is a claim about includes and can only be
read off the source.

SCOPE OF FENCE (3) — the block, not the file. On China the partial IS the board, so its
one <style> block is the whole surface (the US suite scans _us_act_now_board.html.j2 the
same way). Canada and HK are FULL PAGES whose board CSS is one <style> block among five or
six, and those pages legitimately carry a page-level base rule: canada.html.j2:35 has
`.ic-svg{width:1em;height:1em;…}` in its head <style>, which is correct and predates the
sweep. A whole-page fence would false-red on it. So fence (3) is scoped to the single
<style> block that carries the `.row-pop-mark .ic-svg` rule — the block the board ships —
and `_board_style_block` asserts there is exactly one, so the scoping can never go vacuous
by silently matching nothing.

WHY THE CHINA PARTIAL NEEDS NO PER-HOST RENDER. _china_act_now_board.html.j2 has TWO hosts
— china.html.j2:1624 and sector_central_china.html.j2:956 — and both reach it by
`{% include %}`. Because the partial carries its own <style> block, both the markup and the
CSS under test ride with the include, so fences (1)–(3) against the partial cover both
pages. That claim rots the moment a host inlines its own copy of the board or ships a
competing `.ic-svg` rule, so the last two tests here pin exactly those two conditions
rather than leaving the reasoning in a comment.

CSS COMMENTS ARE STRIPPED BEFORE ANY SELECTOR REGEX (`re.sub(r"/\\*.*?\\*/", "", css,
flags=re.S)`, exactly as the US suite does). The sweep's own explanatory comment names
`.row-pop-mark` five times in prose; without the strip, a naive selector regex matches the
comment and the fence reads green against a board that ships no rule at all. Measured.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEMPLATES = ROOT / "templates"
CHINA_PARTIAL = "_china_act_now_board.html.j2"
CHINA_HOSTS = ("china.html.j2", "sector_central_china.html.j2")

# The emoji the three boards shipped into the decision card before the sweep.
SECTOR_EMOJI = "\U0001f3db"

# The rule the sweep added to each of the three boards, matched on its selector.
SIZING_SELECTOR = ".row-pop-mark .ic-svg"
MARK_SIZE = "17px"


# ── renderers: the shipped harnesses, not new ones ───────────────────────────
# Cross-test imports are the house idiom (tests/__init__.py exists; see
# tests/test_action_board_hover_cards.py). Re-implementing a page's view-model here
# would produce a board the builders do not produce.

def _render_china() -> str:
    """The four-lane China board, one THEME row and one SECTOR row.

    `_render_anv2` slices _china_act_now_board.html.j2 from its ACT-NOW banner to EOF —
    i.e. BELOW the partial's own {% import %} lines — and re-provides them through that
    module's SNIPPET_IMPORTS constant, which already carries
    `{% from "_icons.html.j2" import icon %}`. If that line is ever dropped from
    SNIPPET_IMPORTS the slice renders against Undefined and every China fence below dies
    on `UndefinedError: 'icon' is undefined` — a harness fault, not a template fault.

    The slice DOES include the partial's <style> block, which is what lets fences (2) and
    (3) read the rendered board rather than the file.

    Both card kinds are rendered on purpose: `_full_anv2_row()` is a THEME row (mark =
    icon('diamond')), `_sector_anv2_row()` is a SECTOR row (mark = icon('sector')).
    """
    from tests.test_china_stocks_w1c_render import (
        _full_anv2_row, _render_anv2, _sector_anv2_row)

    return _render_anv2({"buy_now": [_full_anv2_row()],
                         "wait_pullback": [_sector_anv2_row()]})


def _render_canada() -> str:
    """canada.html.j2 in stocks mode — the only mode that renders the act-now board."""
    from tests.test_canada_build import _env, _vm

    return _env().get_template("canada.html.j2").render(**_vm(), mode="stocks")


def _render_hk() -> str:
    """hk.html.j2 in stocks mode with a POPULATED `actions` map.

    tests/test_hk_board_ui._vm ships every actions lane EMPTY — the page then renders the
    "no sectors in this lane" placeholder in all four lanes and ZERO decision cards, so a
    fence written against that vm would pass while seeing no mark at all. The payload here
    fills all six keys the board reads (hk.html.j2:3397-3400 — buy_now, on_the_run + hold,
    buy_soon, take_profits + avoid), in the row shape `_hk_anrow` consumes: ticker, name,
    label, dir, days. Six rows in, six marks out; the count is asserted below so this
    fixture cannot quietly stop producing them.

    The env mirrors that module's own `_render`: autoescape=False (which is how
    scripts/build_hk_library.py renders it — the reason the macro's SVG interpolates raw
    through `{{ d.get('mark') }}` instead of arriving as `&lt;svg`).
    """
    from jinja2 import Environment, FileSystemLoader

    from engine import i18n
    from tests.test_hk_board_ui import _vm as _hk_vm

    vm = _hk_vm(None, "stocks")
    vm["actions"] = {
        "buy_now": [{"ticker": "0700.HK", "name": "Tencent", "label": "UPTREND",
                     "dir": "up", "days": 12}],
        "buy_soon": [{"ticker": "0388.HK", "name": "HKEX", "label": "TURN IN PROGRESS",
                      "dir": "flat", "days": 3}],
        "on_the_run": [{"ticker": "0005.HK", "name": "HSBC", "label": "EXTENDED",
                        "dir": "up", "days": 40}],
        "hold": [{"ticker": "0001.HK", "name": "CK Hutchison", "label": "FLAT",
                  "dir": "flat", "days": None}],
        "take_profits": [{"ticker": "0883.HK", "name": "CNOOC", "label": "FADING",
                          "dir": "dn", "days": 9}],
        "avoid": [{"ticker": "1810.HK", "name": "Xiaomi", "label": "DOWNTREND",
                   "dir": "dn", "days": 20}],
    }
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("hk.html.j2").render(**vm)


# board -> (renderer, how many marks the fixture must draw)
BOARDS = {"china": (_render_china, 2), "canada": (_render_canada, 1), "hk": (_render_hk, 6)}

_CACHE: dict[str, str] = {}


def _rendered(board: str) -> str:
    """Render once per board per session — hk.html.j2 is a full page.

    No `pytest.importorskip("jinja2")` here, unlike the US suite: every renderer above
    reaches jinja2 through a sibling test module that imports it at module scope, so an
    importorskip would fire far too late to skip anything. A guard that cannot run is
    worse than no guard.
    """
    if board not in _CACHE:
        _CACHE[board] = BOARDS[board][0]()
    return _CACHE[board]


# ── html / css helpers ───────────────────────────────────────────────────────
def _board_region(html: str) -> str:
    """The act-now panel onward — the board's own <style> legitimately names classes."""
    i = html.index('id="act-now"')
    return html[i:]


def _marks(html: str) -> list[tuple[str, str]]:
    """(kind, first 40 chars of body) for every rendered .row-pop-mark tile."""
    return re.findall(r'<span class="row-pop-mark row-pop-mark--(\w+)"[^>]*>(.{0,40})',
                      _board_region(html))


def _style_blocks(html: str) -> list[str]:
    """Every <style> block's contents, CSS comments stripped.

    The strip is load-bearing, not hygiene — see the module docstring.
    """
    return [re.sub(r"/\*.*?\*/", "", s, flags=re.S)
            for s in re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)]


def _rules(css: str):
    """(selector, declaration-body) for each rule, tolerating one at-rule nesting level."""
    for chunk in css.split("}"):
        if "{" not in chunk:
            continue
        head, _, body = chunk.rpartition("{")
        yield head.split("{")[-1].strip(), body


def _board_style_block(board: str) -> str:
    """The ONE <style> block that ships the hover-card sizing rule.

    Canada and HK are full pages carrying five or six blocks, one of which legitimately
    holds a page-level `.ic-svg` base rule — so fence (3) must read the board's block, not
    the page. Asserting there is exactly one match is what stops that scoping from
    silently selecting nothing.
    """
    blocks = [b for b in _style_blocks(_rendered(board)) if SIZING_SELECTOR in b]
    assert len(blocks) == 1, (
        f"expected exactly ONE <style> block on the {board} board carrying a "
        f"`{SIZING_SELECTOR}` rule, found {len(blocks)} — 0 means the hover-card mark "
        f"ships unsized (doctrine §5.8), >1 means the rule was duplicated across blocks "
        f"and the two copies are free to drift"
    )
    return blocks[0]


# ── fence (1): the rendered mark is an icon, never an emoji ──────────────────
# Split in two on purpose. Reverting a board to its pre-sweep source is the positive
# control for this fence, and a single test would stop at whichever assertion happens to
# come first — leaving the other one unproven and free to be dead. As two tests, the
# revert reds BOTH: the emoji fence on 🏛, the svg fence on 🏛 and on China's ◆.

def _scanned_marks(board: str) -> list[tuple[str, str]]:
    """The board's rendered mark tiles, with the vacuity guard attached.

    A text assertion that cannot distinguish "renders an icon" from "renders nothing" is
    worthless: all three boards self-hide their act-now panel when every lane is empty,
    which is exactly the state tests/test_hk_board_ui._vm ships by default.
    """
    marks = _marks(_rendered(board))
    assert marks, (
        f"no .row-pop-mark tile rendered on the {board} board — this fence scanned "
        f"nothing, so it can no longer tell an icon from an emoji. Repair the fixture "
        f"(the board self-hides when its lanes are empty) before trusting a green here"
    )
    least = BOARDS[board][1]
    assert len(marks) >= least, (
        f"the {board} fixture drew {len(marks)} hover-card marks, expected at least "
        f"{least} — a lane stopped rendering its decision card"
    )
    return marks


@pytest.mark.parametrize("board", list(BOARDS))
def test_no_swept_emoji_survives_in_the_rendered_board(board):
    """🏛 was the sector mark on all three boards before the sweep."""
    _scanned_marks(board)
    assert SECTOR_EMOJI not in _board_region(_rendered(board)), (
        f"the emoji {SECTOR_EMOJI!r} is back on the {board} act-now board — doctrine §5.8: "
        f"emoji are not UI icons, extend templates/_icons.html.j2 instead"
    )


@pytest.mark.parametrize("board", list(BOARDS))
def test_every_hover_card_mark_draws_an_svg(board):
    """`dc_card`'s 'mark' is passed through {{ }} — a bare glyph prints, an icon draws.

    Every offending mark is collected before asserting, so the message names each card
    kind that regressed rather than stopping at the first one.
    """
    bad = [(kind, body) for kind, body in _scanned_marks(board)
           if '<svg class="ic-svg"' not in body]
    assert not bad, (
        f"the {board} board rendered {len(bad)} hover-card mark(s) as text instead of an "
        f"icon: " + "; ".join(f"{k} card -> {b!r}" for k, b in bad) + " — doctrine §5.8, "
        f"the mark must come from icon() in templates/_icons.html.j2"
    )


def test_the_china_board_draws_an_icon_for_both_card_kinds():
    """China is the only one of the three with theme rows: sector 🏛 AND theme ◆ were swept.

    Canada and HK are sector-only boards, so a kind-set fence there would pin nothing.
    """
    kinds = {k for k, _ in _marks(_rendered("china"))}
    assert kinds == {"sector", "theme"}, (
        f"expected the China board to render BOTH decision-card kinds (sector -> "
        f"icon('sector'), theme -> icon('diamond')), got {kinds or 'nothing'}"
    )


# ── fence (2): the sizing rule ships, and is not id-scoped ───────────────────
@pytest.mark.parametrize("board", list(BOARDS))
def test_the_mark_sizing_rule_ships_and_is_never_id_scoped(board):
    """theme.js:4696 clones the hover card onto document.body, OUTSIDE #act-now.

    `#act-now .row-pop-mark .ic-svg` would style the hidden `.rp-src` source and miss the
    card the reader actually sees — an unsized 24x24 icon in the visible popover. The rule
    must therefore stay class-only, and it must actually carry the 17px the tile is drawn
    at rather than merely existing.
    """
    sized = [body for sel, body in _rules(_board_style_block(board))
             if ".row-pop-mark" in sel and ".ic-svg" in sel]
    assert sized, (
        f"no `{SIZING_SELECTOR}` rule on the {board} board — the hover-card mark is unsized"
    )
    assert any(MARK_SIZE in b for b in sized), (
        f"the {board} board's `{SIZING_SELECTOR}` rule no longer sets {MARK_SIZE} — the "
        f"icon falls back to the host page's base size (canada.html.j2 ships 1em) and the "
        f"34px tile draws a mark of the wrong weight"
    )
    # Scanned across EVERY block on the page, not just the board's: an id-scoped rule is
    # broken wherever it is written, and scanning <style> contents (rather than the raw
    # page) keeps a `querySelector('.row-pop-mark')` in page JS from false-redding this.
    hits = [sel for block in _style_blocks(_rendered(board))
            for sel, _ in _rules(block) if ".row-pop-mark" in sel]
    assert hits, f"no .row-pop-mark rule at all in the {board} page CSS — this fence scanned nothing"
    offenders = [h for h in hits if "#" in h]
    assert not offenders, (
        f"the {board} board id-scopes a .row-pop-mark rule ({offenders!r}); theme.js "
        f"appends the hover card to document.body, so an id-scoped rule can never reach "
        f"the visible card — only the hidden .rp-src source it was cloned from"
    )


# ── fence (3): no bare .ic-svg rule shipped from the board's own block ───────
@pytest.mark.parametrize("board", list(BOARDS))
def test_the_board_style_block_never_emits_a_bare_ic_svg_rule(board):
    """Scoped to the board's OWN <style> block — see the module docstring.

    sector_central.html.j2:617 scopes its copy of `.ic-svg` under #si-confluence, and a
    global rule shipped from a board panel would fight its host on whichever page hosts
    both. Canada's head <style> legitimately carries a page-level `.ic-svg` base rule; that
    is the page's own, not the board's, which is why this fence reads one block.
    """
    for sel, _ in _rules(_board_style_block(board)):
        assert ".ic-svg" not in [s.strip() for s in sel.split(",")], (
            f"bare `.ic-svg` rule in the {board} board's CSS block — scope it to the mark "
            f"wrapper (`{SIZING_SELECTOR}`, …) so a panel cannot restyle every icon on "
            f"whatever page hosts it"
        )


# ── the China partial has two hosts; keep the coverage claim honest ──────────
def test_both_china_hosts_still_include_the_shared_board_partial():
    """The fences above render the PARTIAL, and that covers china_stocks.html AND the China
    SI Overview only for as long as both hosts reach the board by {% include %}. A host
    that pasted its own copy of the board would be entirely unfenced and would not fail any
    test above — so the include is asserted here directly."""
    for host in CHINA_HOSTS:
        src = (TEMPLATES / host).read_text(encoding="utf-8")
        assert f'{{% include "{CHINA_PARTIAL}" %}}' in src, (
            f"templates/{host} no longer includes {CHINA_PARTIAL} — if the board was "
            f"inlined there, that copy ships unfenced: every icon fence in this file "
            f"renders the partial, on the assumption both hosts share it"
        )


def test_the_china_si_overview_host_ships_no_competing_ic_svg_rule():
    """sector_central_china.html.j2 hosts the partial and today defines no `.ic-svg` rule.

    Its sibling sector_central.html.j2 DOES (scoped under #si-confluence), which is the
    shape to copy if this page ever needs one: an unscoped rule added here would win or
    lose against the partial's `.row-pop-mark .ic-svg` by source order alone.
    """
    src = (TEMPLATES / CHINA_HOSTS[1]).read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    offenders = [sel for sel, _ in _rules(css) if ".ic-svg" in sel]
    assert not offenders, (
        f"templates/{CHINA_HOSTS[1]} now ships its own `.ic-svg` rule(s) {offenders!r}; "
        f"it hosts {CHINA_PARTIAL}, whose hover-card mark rule is class-scoped, so scope "
        f"any host rule under this page's own id (as sector_central.html.j2 does with "
        f"#si-confluence) instead of shipping a competing global"
    )
