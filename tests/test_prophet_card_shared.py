"""Featured-glow invariants pinned at the SOURCE of the shared prophet card.

`templates/_prophet_card.html.j2` is one partial with five consumers — the US
dashboard, china, hk, canada and intl — but the equivalent assertions live in
`tests/test_us_board_priority_ui.py` and read the US page's RENDERED output. That
covers exactly one caller: the CN board consumes the same partial, ships the same
`pv_css()` block, and had no test at all. A regression in the macro would therefore
be caught on us_stocks.html and land silently on china.html — and the CN board is
where the second invariant actually bites, because `--up` FLIPS to red under
`html[data-lang="zh"]` (theme.css `html[data-lang="zh"] { --up: #e06464 }`) and the
CN page is the one read in Chinese by default.

So these assertions grep the partial itself rather than any page render: one file,
every consumer, present and future. Two laws, both stated in the macro's own header:

  1. the featured glow is STATIC. That is what makes "no prefers-reduced-motion kill
     block" compliant rather than a gap — the strongest form of that compliance is
     having nothing to disable, and it only holds while nothing animates.
  2. the aura is pinned to `--pv-buy`, never to `--up`/`--up-flip` (which flip red in
     zh) and never to `--pvh` (which follows the card's verb). A featured pick
     glowing red in Chinese would invert the message the glow exists to carry.

Run: .venv/bin/python -m pytest tests/test_prophet_card_shared.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = ROOT / "templates" / "_prophet_card.html.j2"

#: Jinja comments are prose — the macro header *discusses* animation at length and a
#: substring test over the raw file would fire on the explanation rather than on a
#: rule. And the markup below the macro carries `{% ... %}` blocks whose braces read
#: as CSS rules to a naive matcher (`{% elif cx.get('triage') %}` did exactly that).
#: So: strip the comments, then narrow to the <style> block pv_css() emits.
_SRC = re.sub(r"\{#.*?#\}", "", PARTIAL.read_text(encoding="utf-8"), flags=re.S)
_STYLE = re.search(r"<style>(.*?)</style>", _SRC, flags=re.S)
assert _STYLE, "pv_css() no longer emits a <style> block — this whole file is vacuous"
CSS = _STYLE.group(1)

#: Hue tokens that flip meaning under `html[data-lang="zh"]` (红涨绿跌). `--up-flip`
#: is named defensively: it does not exist today, and a future rename of the flipping
#: token must not slip the guard.
FLIPPING = ("var(--up)", "var(--up-flip)", "var(--down)")


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
# 2. the glow hue is direction-STABLE
# --------------------------------------------------------------------------- #
def test_the_aura_is_pinned_to_pv_buy():
    for selector, body in AURA:
        assert "var(--pv-buy)" in body, f"{selector} lost the --pv-buy pin"
        assert "var(--pvh)" not in body, \
            f"{selector} follows the card's verb hue; the aura must stay green"


def test_no_featured_rule_uses_a_token_that_flips_red_under_zh():
    for selector, body in RULES:
        for token in FLIPPING:
            assert token not in body, (
                f"{selector} uses {token}, which theme.css swaps under "
                'html[data-lang="zh"] — a featured pick would glow RED in Chinese')


def test_the_featured_chip_carries_the_same_hue_law():
    """Colour is never the only carrier — the ★ Featured chip is the redundant one —
    so it must not contradict the aura by flipping when the aura does not."""
    chip = re.search(r"\.pv-mk-feat\{([^{}]*)\}", CSS)
    assert chip, ".pv-mk-feat rule not found"
    assert "var(--pv-buy)" in chip.group(1)
    for token in FLIPPING:
        assert token not in chip.group(1)


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
    assert "dashboard.html.j2" in consumers
    assert "china.html.j2" in consumers, "CN board no longer shares the partial"
    assert len(consumers) >= 3, consumers
