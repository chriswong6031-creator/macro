"""P-MP1-SHELL regression: a CSS comment closed with Jinja's `#}` instead of
CSS's `*/` swallows every rule until the next literal `*/` as comment text.

Caught during §11 evidence capture (checkpoint 5): the ladder headline
(`.ladder-headline` and 8 sibling rules + their @media block) never reached
the parsed CSSOM at all — `document.styleSheets[...].cssRules` skipped
straight from `.pv-mark` to `.fig`/`.mx-sec` with zero rules in between,
even though the raw HTML source had the text verbatim. Root cause:
`templates/dashboard.html.j2` had a comment opened `/* ...` and closed `#}`
(a Jinja comment closer, muscle-memory from writing `{#- ... -#}` blocks a
few lines away) — CSS never terminated the comment, so the parser treated
every byte up to the NEXT `*/` anywhere later in the stylesheet as comment
content, silently deleting nine rules. The page still rendered (comments are
invisible), Jinja parsed fine (CSS comment syntax means nothing to Jinja),
and every existing test passed — this was invisible to anything that didn't
either read the CSSOM or look at a screenshot closely.

This suite parses every `<style>...</style>` block in every OWNED template
this packet touches and asserts `/*` / `*/` counts balance — a mismatch is
exactly this bug's signature.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEMPLATES = [
    "templates/dashboard.html.j2",
    "templates/_prophet_card.html.j2",
    "templates/_us_prophet_plan_cards.html.j2",
]


def _style_blocks(src: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"<style[^>]*>(.*?)</style>", src, re.S)]


def test_every_style_block_has_balanced_css_comments():
    for rel in TEMPLATES:
        src = (ROOT / rel).read_text()
        for i, css in enumerate(_style_blocks(src)):
            opens = len(re.findall(r"/\*", css))
            closes = len(re.findall(r"\*/", css))
            assert opens == closes, (
                f"{rel} <style> block #{i}: {opens} '/*' vs {closes} '*/' — "
                "an unterminated CSS comment silently swallows every rule "
                "after it until the next literal '*/' anywhere later in the "
                "stylesheet (this exact bug shipped in checkpoint 1-4 and was "
                "only caught by reading the parsed CSSOM during evidence capture)"
            )


def test_no_jinja_comment_closer_appears_where_a_css_comment_is_open():
    """Belt-and-braces: no `/* ... #}` span (a CSS comment opener followed,
    before any '*/', by a Jinja comment closer) anywhere in these files —
    the exact shape of the bug, checked directly rather than inferred from
    a count mismatch."""
    for rel in TEMPLATES:
        src = (ROOT / rel).read_text()
        for m in re.finditer(r"/\*((?:(?!\*/).)*?)#\}", src, re.S):
            closer = "#" + "}"
            raise AssertionError(
                f"{rel}: CSS comment opened with /* and closed with Jinja's "
                f"{closer} instead of */, near byte {m.start()}: {m.group(0)[-80:]!r}"
            )


def test_ladder_headline_rules_survive_after_the_fix():
    """Direct pin on the specific rules this bug deleted."""
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text()
    for block in _style_blocks(dash):
        if ".ladder-headline {" in block:
            for selector in (
                ".ladder-headline", ".ladder-n {", ".ladder-nl", ".ladder-sub",
                ".ladder-absence", ".ladder-foot", ".ladder-clear", ".sk-n {", ".sk-head {",
            ):
                assert selector in block, f"{selector} missing from the ladder <style> block"
            return
    raise AssertionError(".ladder-headline rule not found in any <style> block")
