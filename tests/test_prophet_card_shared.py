"""Shared Prophet-card color and mobile-layout invariants pinned at the source.

`templates/_prophet_card.html.j2` is one partial with five consumers — the US
dashboard, china, hk, canada and intl — but the equivalent assertions live in
`tests/test_us_board_priority_ui.py` and read the US page's RENDERED output. That
covers exactly one caller: the CN board consumes the same partial, ships the same
`pv_css()` block, and had no test at all. A regression in the macro would therefore
be caught on us_stocks.html and land silently on china.html — and the CN board is
where the second invariant actually bites, because `--up` FLIPS to red under
`html[data-lang="zh"]` (theme.css `html[data-lang="zh"] { --up: #e06464 }`) and the
CN page is the one most often read in Chinese mode.

So these assertions grep the partial itself rather than any page render: one file,
every consumer, present and future. Two laws, both stated in the macro's own header:

  1. the featured glow is STATIC. That is what makes "no prefers-reduced-motion kill
     block" compliant rather than a gap — the strongest form of that compliance is
     having nothing to disable, and it only holds while nothing animates.
  2. the aura is pinned to the semantic `--pv-buy` token, never straight to the
     base direction tokens and never to `--pvh` (which follows the card's verb).
     theme.css owns the language convention: bullish green in EN, bullish red in ZH.
  3. at mobile widths, the company name receives its own line so display zoom cannot
     collapse it to zero between the ticker and Edge score.

Run: .venv/bin/python -m pytest tests/test_prophet_card_shared.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = ROOT / "templates" / "_prophet_card.html.j2"
THEME = ROOT / "templates" / "theme.css"
THEME_CSS = THEME.read_text(encoding="utf-8")

#: Jinja comments are prose — the macro header *discusses* animation at length and a
#: substring test over the raw file would fire on the explanation rather than on a
#: rule. And the markup below the macro carries `{% ... %}` blocks whose braces read
#: as CSS rules to a naive matcher (`{% elif cx.get('triage') %}` did exactly that).
#: So: strip the comments, then narrow to the <style> block pv_css() emits.
_SRC = re.sub(r"\{#.*?#\}", "", PARTIAL.read_text(encoding="utf-8"), flags=re.S)
_STYLE = re.search(r"<style>(.*?)</style>", _SRC, flags=re.S)
assert _STYLE, "pv_css() no longer emits a <style> block — this whole file is vacuous"
CSS = _STYLE.group(1)

#: Base direction tokens. Prophet components consume the semantic --pv-* layer so
#: the language-specific convention stays centralized in theme.css.
DIRECTION_BASE = ("var(--up)", "var(--up-flip)", "var(--down)")


def _featured_rules(css: str) -> list[tuple[str, str]]:
    """(selector, declarations) for every rule whose SELECTOR names pv-featured."""
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]*pv-featured[^{}]*)\{([^{}]*)\}", css)]


def _featured_block(css: str) -> str:
    """The contiguous source region the glow occupies, header rule → next component."""
    start = css.index(".pvcard.pv-featured{")
    return css[start:css.index(".pv-chart{", start)]


RULES = _featured_rules(CSS)
BLOCK = _featured_block(CSS)
#: the aura rules proper — ::before is the card's own hue RAIL and legitimately
#: follows --pvh, so it is held to the animation law but not to the --pv-buy law.
AURA = [(s, b) for s, b in RULES if "::before" not in s]


# --------------------------------------------------------------------------- #
# the extraction itself must be able to fail
# --------------------------------------------------------------------------- #
def test_the_matchers_find_the_glow_and_fire_on_a_planted_offender():
    """A regex that silently matches nothing turns every assertion below green."""
    assert len(BLOCK) > 200, "featured block slice collapsed — the matcher is vacuous"
    assert len(AURA) >= 4, f"expected the 4 aura rules (±light/hover), got {len(AURA)}"
    assert any("::before" in s for s, _ in RULES), "::before rail rule not matched"

    planted = (".pvcard.pv-featured{animation:pv-pulse 2s infinite;"
               "box-shadow:0 0 26px var(--up)}\n.pv-chart{x:1}")
    sel, body = _featured_rules(planted)[0]
    assert "animation" in body and "var(--up)" in body, sel
    assert "animation" in _featured_block(planted)


# --------------------------------------------------------------------------- #
# 1. the glow is static
# --------------------------------------------------------------------------- #
def test_the_featured_glow_carries_no_animation():
    assert "animation" not in BLOCK, "featured glow must not animate"
    assert "@keyframes" not in BLOCK, "no keyframes may live in the featured block"


def test_no_featured_rule_animates_from_anywhere_in_the_partial():
    """The block slice alone is not enough: an `animation:` added to a featured rule
    that moved, or a @keyframes declared further down, would both escape it.
    (`transition` is deliberately NOT banned — the hover lift is a transition on
    .pvcard, which is state-driven and stops; an animation runs unprompted.)"""
    for selector, body in RULES:
        assert "animation" not in body, f"{selector} animates the featured card"
    named = re.findall(r"@keyframes\s+([\w-]+)", CSS)
    for frames in named:
        assert not any(frames in body for _, body in RULES), \
            f"@keyframes {frames} is driven from a featured rule"


# --------------------------------------------------------------------------- #
# 2. the glow hue follows the semantic Prophet buy token
# --------------------------------------------------------------------------- #
def test_the_aura_is_pinned_to_pv_buy():
    for selector, body in AURA:
        assert "var(--pv-buy)" in body, f"{selector} lost the --pv-buy pin"
        assert "var(--pvh)" not in body, \
            f"{selector} follows the card's verb hue; the aura must stay bullish"


def test_no_featured_rule_bypasses_the_prophet_palette():
    for selector, body in RULES:
        for token in DIRECTION_BASE:
            assert token not in body, (
                f"{selector} bypasses --pv-buy with {token}; language-aware Prophet "
                "colors must stay centralized in theme.css")


def test_the_featured_chip_carries_the_same_hue_law():
    """Colour is never the only carrier — the ★ Featured chip is the redundant one —
    so it must not contradict the aura by flipping when the aura does not."""
    chip = re.search(r"\.pv-mk-feat\{([^{}]*)\}", CSS)
    assert chip, ".pv-mk-feat rule not found"
    assert "var(--pv-buy)" in chip.group(1)
    for token in DIRECTION_BASE:
        assert token not in chip.group(1)


def _all_rule_bodies(selector: str) -> str:
    """Join every declaration block for an exact selector in theme.css."""
    return "\n".join(re.findall(re.escape(selector) + r"\s*\{([^{}]*)\}", THEME_CSS))


def test_chinese_mode_rebinds_prophet_bullish_red_and_bearish_green():
    # C8-C (#6011) made the zh direction flip STRUCTURAL: the zh block flips
    # --up/--down themselves, and Buy/Near derive from --up via the base
    # color-mix, so a zh Buy chip is red BY CONSTRUCTION. A zh restatement of
    # --pv-buy/--pv-near would re-create the desync DA-002 cured (a future
    # --up edit silently leaving zh on a stale hand-tuned red). The semantic
    # properties (AA on every consumer, dE floors, Near lighter than Buy)
    # live in tests/test_prophet_verb_ink_contrast.py — change either file
    # only alongside the other.
    zh = _all_rule_bodies('html[data-lang="zh"]')
    assert "--up: #e06464" in zh and "--down: #45b873" in zh
    assert "--pv-buy:" not in zh, "zh must not restate --pv-buy (flip is structural)"
    assert "--pv-near:" not in zh, "zh must not restate --pv-near (flip is structural)"
    # --pv-avoid is a :root literal, so zh still needs its one explicit rebind:
    assert "--pv-avoid: var(--down)" in zh

    light_zh = _all_rule_bodies('html[data-theme="light"][data-lang="zh"]')
    assert "--up: #cf4040" in light_zh and "--down: #1f9a55" in light_zh
    # The light+zh --ink-pv-buy/--ink-pv-near deepening rungs were RETIRED by
    # C8-C (the deepening moved into the token itself); re-adding one would
    # double-mix. --ink-pv-avoid keeps its quadrant rung.
    assert "--ink-pv-buy:" not in light_zh, "retired rung must stay retired (C8-C)"
    assert "--ink-pv-near:" not in light_zh, "retired rung must stay retired (C8-C)"
    assert "--ink-pv-avoid:" in light_zh and "var(--pv-avoid) 62%" in light_zh


def test_mobile_company_name_gets_a_noncollapsing_second_line():
    assert ".pv-idw{flex:1 1 auto;flex-wrap:wrap;row-gap:1px;overflow:visible}" in CSS
    assert ".pv-nm{flex-basis:100%;width:100%}" in CSS


def test_what_to_buy_now_keeps_its_existing_direction_palette():
    """The separate action lanes stay on --ink-up/--ink-down, not Prophet tokens."""
    assert ".anv2-lane--buy   .anv2-lane-title { color:var(--ink-up); }" in THEME_CSS
    assert ".anv2-lane--red   .anv2-lane-title { color:var(--ink-down); }" in THEME_CSS


# --------------------------------------------------------------------------- #
# the ⚠ caution popover must paint above the NEXT card, not just escape its own
# --------------------------------------------------------------------------- #
#: Reported 2026-08-03 on us_stocks.html and hk_stocks.html; the partial is shared, so
#: it was every board. The clip was released long ago (`overflow:visible`), but the
#: popover still rendered BEHIND the neighbouring card and lost its right-hand text.
#:
#: Cause: `.pvcard:hover` sets `transform:translateY(-2px)`, and a non-none transform
#: creates a stacking context — so `.pv-cau-pop{z-index:30}` is resolved INSIDE the
#: hovered card instead of against its siblings, and every later `.pvcard` paints over
#: it. Raising the popover further cannot fix that; the CARD has to be lifted.
#:
#: This pins the CAUSAL rule rather than a literal, so it stays honest under edits:
#: while the hover transform exists, the escape rule must also carry a z-index.
def _escape_rule() -> tuple[str, str]:
    """(selector, declarations) for the rule that lets the caution popover out.

    Narrowed to selectors that style the CARD (`.pvcard:has(…)`): the sibling rule
    `.pv-cau:hover .pv-cau-pop{display:block}` also names `.pv-cau:hover` but merely
    reveals the popover, and matching it here would make these assertions read the
    wrong declarations.
    """
    hits = [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", CSS)
            if ".pv-cau:hover" in m.group(1) and ".pvcard" in m.group(1)]
    assert len(hits) == 1, f"expected exactly one card-level caution rule, got {hits}"
    return hits[0]


def test_the_escape_rule_matcher_fires_on_a_planted_offender():
    """The extraction must be able to fail, or every assertion below is vacuous."""
    sel, decls = _escape_rule()
    assert "overflow" in decls, sel
    stripped = CSS.replace(f"{sel}{{{decls}}}", "")
    hits = [m for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", stripped)
            if ".pv-cau:hover" in m.group(1) and ".pvcard" in m.group(1)]
    assert not hits, "removing the rule left a second card-level match — matcher too loose"


def test_the_hover_transform_that_traps_the_popover_still_exists():
    """The premise. If the transform ever goes, this whole guard needs re-deriving —
    fail loudly rather than keep asserting a fix for a cause that moved."""
    hover = re.search(r"\.pvcard:hover\{([^{}]*)\}", CSS)
    assert hover, ".pvcard:hover rule not found"
    assert "transform:" in hover.group(1), (
        "the hover transform is gone — re-check whether .pvcard still needs z-index "
        "to lift the caution popover above its siblings"
    )


def test_releasing_the_clip_also_lifts_the_card_above_its_siblings():
    sel, decls = _escape_rule()
    assert "overflow:visible" in decls.replace(" ", ""), sel
    z = re.search(r"z-index:\s*(\d+)", decls)
    assert z, (
        "the caution escape rule releases the clip but sets no z-index — the popover "
        "escapes the card and then paints UNDER the next card in the grid"
    )
    assert int(z.group(1)) > 0, "z-index must beat sibling cards (z-index:auto)"


def test_the_lift_stays_below_the_modal_and_lens_layers():
    """A hovered CARD must never outrank a dialog. Page chrome on these boards tops
    out around z-index 4; the overlay/LENS layers live at 1200+."""
    _, decls = _escape_rule()
    z = int(re.search(r"z-index:\s*(\d+)", decls).group(1))
    assert 4 < z < 1000, f"card lift z-index={z} is outside the safe band"


def test_the_focus_within_half_is_lifted_too():
    """The ⚠ control is a real <button>: keyboard users open the popover via focus,
    not hover, and that path must not paint underneath the neighbour either."""
    sel, _ = _escape_rule()
    assert ".pv-cau:focus-within" in sel, (
        "the focus-within selector left the escape rule — the keyboard path would "
        "regain the clipping/stacking bug"
    )


# --------------------------------------------------------------------------- #
# the verb chip carries NO hover tip (operator removal, 2026-08-03)
# --------------------------------------------------------------------------- #
#: It restated what the card already shows — the chip reads "Buy", the tracker shows the
#: stage, the footer prints the zone. The ⚡ trigger tip and the ⚠N popover stay, so this
#: asserts the ONE chip, not "no tips on the card".
MARKUP = _SRC[_SRC.index("{% macro pv_card("):]


def test_the_verb_chip_has_no_data_tip():
    chip = re.search(r'<span class="pv-chip"[^>]*>', MARKUP)
    assert chip, "verb chip markup not found — this guard has gone vacuous"
    assert "data-tip" not in chip.group(0), (
        "the verb chip regained a hover tip: " + chip.group(0)
    )


def test_the_trigger_and_caution_disclosures_survived_the_removal():
    """Guard the removal's blast radius — which GREW by a second operator order.

    2026-08-03 took the tip off the verb chip only, and this guard pinned
    .pv-edge as a survivor. 2026-08-05 extended the same call to .pv-edge and to
    the feat/new marks: all three are badges whose whole job is to be read at a
    glance, and their explainers were the longest cards on the board.

    So the radius is re-pinned, not relaxed. What must SURVIVE is unchanged and
    still asserted — the ⚡ trigger tip and the ⚠N caution popover carry facts
    that appear nowhere else on the card. What went is now asserted GONE, so a
    tip creeping back onto a badge fails here rather than passing quietly.
    """
    trg = re.search(r'<span class="pv-trg[^>]*>', MARKUP)
    assert trg and "data-tip-en" in trg.group(0), "the ⚡ trigger tip was removed too"
    assert 'class="pv-cau-pop"' in MARKUP, "the ⚠ caution popover was removed too"

    edge = re.search(r'<span class="pv-edge"[^>]*>', MARKUP)
    assert edge, "the Edge slot markup is gone — this guard has gone vacuous"
    assert "data-tip" not in edge.group(0), (
        "the Edge/Priority badge regained a hover tip (removed 2026-08-05): "
        + edge.group(0)
    )
    assert "_MK_NOTIP" in MARKUP, (
        "the feat/new mark tip suppression is gone — the 2026-08-05 removal "
        "covered those badges too"
    )


# --------------------------------------------------------------------------- #
# the premise of this file
# --------------------------------------------------------------------------- #
def test_the_partial_really_is_shared_beyond_the_us_page():
    """If the CN board ever stopped consuming this partial, the reason this file
    exists alongside tests/test_us_board_priority_ui.py would be stale."""
    consumers = sorted(
        p.name for p in (ROOT / "templates").glob("*.j2")
        if "_prophet_card.html.j2" in p.read_text(encoding="utf-8")
    )
    expected = {"dashboard.html.j2", "china.html.j2", "hk.html.j2",
                "canada.html.j2", "intl.html.j2"}
    assert expected <= set(consumers), consumers
