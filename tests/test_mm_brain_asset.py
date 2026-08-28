"""Runtime-shape guard for the shared Brain widget asset (mm_brain.js).

Born from a production outage (2026-08-25, W1-C heal): a design comment INSIDE
the widget's CSS template literal used markdown-style backticks. The first
backtick terminated the template literal, the following ``.on`` became a
property access on the giant CSS string, and the next backtick re-opened a
template — turning the tail into a tagged-template CALL of a string:
``TypeError: "…" is not a function`` at load, on every page, with `node
--check` and the whole CI suite green (the defect is syntactically valid).

This test is dependency-free and pins the exact failure class: the widget's
CSS template literal may never contain an interior backtick, and the span it
closes must still contain the late-stylesheet composer rules (so an early
termination is named even if the interior backtick itself moved).
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COPIES = [ROOT / "templates" / "mm_brain.js", ROOT / "site" / "mm_brain.js"]


def _css_template_span(text: str) -> tuple[int, int]:
    """Return (open_index, close_index) of the `var CSS = <backtick>` literal."""
    marker = "var CSS = `"
    start = text.index(marker) + len(marker) - 1
    close = text.index("`", start + 1)
    return start, close


@pytest.mark.parametrize("path", COPIES, ids=lambda p: str(p.relative_to(ROOT)))
def test_css_template_literal_has_no_interior_backtick(path: pathlib.Path) -> None:
    if not path.exists():
        pytest.skip(f"{path} absent (sparse checkout)")
    text = path.read_text(encoding="utf-8")
    start, close = _css_template_span(text)
    body = text[start + 1 : close]
    line_of_close = text[:close].count("\n") + 1
    # The first backtick after the opener must terminate the WHOLE stylesheet:
    # the "explain this panel" affordance rules (.mmb-exp) are the final block
    # of the sheet, so if the span ends before them, an interior backtick split
    # the template and the tail becomes a tagged-template call of a string at
    # page load.
    assert ".mmb-exp" in body, (
        "CSS template literal of mm_brain.js terminated early at line "
        f"{line_of_close} — an interior backtick splits the stylesheet and "
        "the widget crashes at load (string-is-not-a-function outage, "
        "2026-08-25). Use quotes, never backticks, in comments inside the "
        "template."
    )
