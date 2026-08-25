"""Byte-level pins for the Canada Stock Dashboard V3.6 client composer.

The composer (site/canada-stock-v36.js, entitled-only, no template pair) hides
grid cards and the grid container with the HTML ``hidden`` attribute
(``card.hidden = !show``).  The UA sheet's ``[hidden]{display:none}`` loses to
ANY author display rule, and both hidden targets carry one: the page stylesheet
sets ``.pvcard{display:flex}`` and the composer's own style sets
``.ca-v36-card-grid{display:grid}``.  Production consequence (found in the
2026-08-25 entitled acceptance matrix): the Top Picks segment, the leadership
filter's grid hiding, and the grid/table view switch were all visually inert —
state, counters, aria and the empty-state message updated while every card
stayed painted.  The repair scopes explicit ``[hidden]`` overrides into the
composer's injected style; these tests pin that the overrides ship and that
the hide mechanism they cover is still the one the composer uses.
"""

from pathlib import Path

import pytest

COMPOSER = Path(__file__).resolve().parents[1] / "site" / "canada-stock-v36.js"

REQUIRED_HIDDEN_OVERRIDES = [
    # container: grid pane must actually vanish when the Table view is active
    ".ca-v36-card-grid[hidden]{display:none!important}",
    # cards: Top Picks segment + leadership filter hide via card.hidden
    ".ca-v36-card-grid .pvcard[hidden]{display:none!important}",
]


def _composer_text() -> str:
    if not COMPOSER.exists():
        pytest.skip("sparse checkout omits site/ (needs_full_checkout)")
    return COMPOSER.read_text(encoding="utf-8")


def test_hidden_attribute_overrides_ship_in_composer_style():
    text = _composer_text()
    for rule in REQUIRED_HIDDEN_OVERRIDES:
        assert rule in text, (
            f"composer style lost the {rule!r} override; the hidden attribute "
            "is defeated by author display rules (.pvcard{display:flex} / "
            ".ca-v36-card-grid{display:grid}) and the Top Picks segment, "
            "leadership filter and grid/table switch go visually inert"
        )


def test_composer_still_hides_via_hidden_attribute():
    """The overrides above only matter while the composer hides with
    ``.hidden`` / ``hidden`` attribute semantics.  If the hide mechanism ever
    migrates to classes (like the table rows' ``ca-v36-hidden``), this test
    fails to force the override list above to be re-reviewed rather than
    silently pinning dead CSS."""
    text = _composer_text()
    assert "card.hidden = !show" in text.replace("  ", " "), (
        "composer no longer hides grid cards via the hidden attribute; "
        "re-review REQUIRED_HIDDEN_OVERRIDES before deleting them"
    )
