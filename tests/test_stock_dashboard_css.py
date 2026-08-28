"""TP-1 (theme-parity-tp1-canada-20260828-sol-001): contract tests for the
governed Canada stock-dashboard stylesheet pair
(templates/stock-dashboard.css / site/stock-dashboard.css).

Canada's V3.8 composer (site/canada-stock-v36.js) used to author its own
presentation as a runtime `<style>` tag built from JS string concatenation
(injectCss()) — exactly the opaque runtime stylesheet system
research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md §4-5
and the house theme-parity law forbid on a governed surface. This wave moves
every rule injectCss() used to own into this governed, token-clean, paired
plain-copy stylesheet instead. These tests freeze the boundary:

  * the hidden-attribute visibility overrides the composer's
    ``card.hidden = !show`` mechanism depends on (pinned separately in
    tests/test_canada_v36_composer.py) now live here, scoped under the
    canonical ``.mx-stockdash--ca`` mount class;
  * the mobile one-lane Act-Now grammar (previously pinned against the
    composer's injected CSS text) lives here too;
  * the stance/lane-header color family reads the Prophet stance tokens,
    never a market-direction literal;
  * the stylesheet is byte-identical between templates/ and site/ (paired
    plain-copy asset law); and
  * the stylesheet is token-clean per TP-0 design-system enforcement — no
    color/font/radius literals, no parallel :root token family, no emoji.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CSS = ROOT / "templates" / "stock-dashboard.css"
SITE_CSS = ROOT / "site" / "stock-dashboard.css"

# Moved verbatim from tests/test_canada_v36_composer.py's
# REQUIRED_HIDDEN_OVERRIDES, now scoped under the canonical Canada mount
# class rather than the deleted composer-owned ``.ca-v36-card-grid`` bare
# selector.
REQUIRED_CANADA_VISIBILITY = (
    ".mx-stockdash--ca .ca-v36-card-grid[hidden]",
    ".mx-stockdash--ca .ca-v36-card-grid .pvcard[hidden]",
    ".mx-stockdash--ca .ca-v36-card-grid .sm-hidden",
)


def _css_text() -> str:
    if not TEMPLATE_CSS.exists():
        pytest.fail(
            "templates/stock-dashboard.css does not exist yet — TP-1 Task 3 "
            "extraction has not run (expected RED before that task lands)"
        )
    return TEMPLATE_CSS.read_text(encoding="utf-8")


def test_stylesheet_owns_canada_hidden_attribute_visibility():
    """The composer's ``card.hidden = !show`` mechanism (pinned in
    test_canada_v36_composer.py::test_composer_still_hides_via_hidden_attribute)
    is defeated by author display rules (``.pvcard{display:flex}`` /
    ``.ca-v36-card-grid{display:grid}``) unless an explicit [hidden] override
    ships with at-least-equal specificity. That CSS now belongs here, scoped
    under the canonical .mx-stockdash--ca mount, not in the deleted
    composer-owned injectCss()."""
    text = _css_text()
    for rule in REQUIRED_CANADA_VISIBILITY:
        assert rule in text, (
            f"stylesheet lost the {rule!r} override; the Top Picks segment, "
            "leadership filter and grid/table switch would go visually inert "
            "again"
        )


def test_stylesheet_roots_canonical_mount_semantics():
    """Root selector per the TP-1 plan: .mx-stockdash owns box-sizing/color/
    font-family for the whole subtree, and every descendant (including
    pseudo-elements) inherits box-sizing: border-box."""
    text = _css_text()
    assert re.search(r"\.mx-stockdash\s*\{[^}]*box-sizing:\s*border-box", text), (
        "stylesheet no longer roots .mx-stockdash with box-sizing: border-box"
    )
    assert re.search(r"\.mx-stockdash\s*\{[^}]*color:\s*var\(--text\)", text), (
        "stylesheet no longer roots .mx-stockdash with color: var(--text)"
    )
    assert re.search(r"\.mx-stockdash\s*\{[^}]*font-family:\s*var\(--font-ui\)", text), (
        "stylesheet no longer roots .mx-stockdash with font-family: var(--font-ui)"
    )
    assert re.search(r"\.mx-stockdash\s*\*[^{]*\{[^}]*box-sizing:\s*border-box", text), (
        "stylesheet lost the .mx-stockdash * box-sizing: border-box rule"
    )


def test_stylesheet_stance_and_lane_header_use_prophet_stance_tokens():
    """Action lane/stance identity must use the Prophet stance tokens named
    in the TP-1 plan (var(--ink-pv-<tone>, var(--pv-<tone>))), never a
    market-direction literal (--ink-up/--ink-down/etc.) — applied to both
    the stance chips AND the at-rest Act-Now lane headers."""
    text = _css_text()
    normalized = re.sub(r"\s+", "", text)
    for tone in ("buy", "near", "wait", "avoid"):
        pair = f"var(--ink-pv-{tone},var(--pv-{tone}))"
        assert pair in normalized, (
            f"stylesheet lost the canonical --ink-pv-{tone}/--pv-{tone} "
            "stance token pair"
        )
    assert re.search(r"\.ca-v36-stance\.buy\s*\{[^}]*--ink-pv-buy", text), (
        ".ca-v36-stance.buy no longer reads the Prophet stance token family"
    )
    assert re.search(r"\.ca-v36-an-hd\.buy\s*\{[^}]*--ink-pv-buy", text), (
        ".ca-v36-an-hd.buy (Act-Now lane header) no longer reads the same "
        "Prophet stance token family as the stance chips"
    )


def test_stylesheet_preserves_canada_quote_up_down_convention():
    """Canada quote colors stay Western green-up/red-down even under ZH —
    the .nb-chg.up/.down convention (var(--ok)/var(--act)) must not change."""
    text = _css_text()
    assert re.search(r"\.nb-chg\.up\s*\{[^}]*var\(--ok\)", text), (
        ".nb-chg.up no longer uses var(--ok) — the Western green-up "
        "convention must not change in this wave"
    )
    assert re.search(r"\.nb-chg\.down\s*\{[^}]*var\(--act\)", text), (
        ".nb-chg.down no longer uses var(--act) — the Western red-down "
        "convention must not change in this wave"
    )


def test_mobile_segment_grammar_one_lane_at_a_time():
    """V3.8 §5.5, moved from tests/test_canada_v36_composer.py now that the
    rule lives in the governed stylesheet: at ~390px, one segmented lane
    selector + ONE lane body at a time — never four stacked lane cards."""
    text = _css_text()
    assert re.search(r"\.ca-v36-an-seg\s*\{[^}]*display:\s*none", text), (
        "the Act-Now segment bar lost its desktop display:none base rule"
    )
    mq = re.search(r"@media\s*\(max-width:\s*680px\)\s*\{(.*)\}\s*$", text, re.S)
    assert mq, "could not locate the 680px media query block"
    block = mq.group(1)
    for pattern in [
        r"\.ca-v36-an-seg\s*\{[^}]*display:\s*flex",
        r"\.ca-v36-an-lanes\s*\{[^}]*grid-template-columns:\s*1fr",
        r"\.ca-v36-an-lane\s*\{[^}]*display:\s*none",
        r"\.ca-v36-an-lane\.is-current\s*\{[^}]*display:\s*block",
    ]:
        assert re.search(pattern, block), (
            f"680px media query lost {pattern!r} — the mobile one-lane "
            "grammar is broken"
        )


def test_template_site_stylesheet_pair_is_byte_identical():
    if not SITE_CSS.exists():
        pytest.skip("sparse checkout omits site/ (needs_full_checkout)")
    template_text = _css_text()
    assert template_text == SITE_CSS.read_text(encoding="utf-8"), (
        "templates/stock-dashboard.css and site/stock-dashboard.css have "
        "diverged; run python3 -m scripts.check_template_site_sync --fix"
    )


def test_stylesheet_is_token_clean():
    """TP-0 design-system enforcement: no color/font/radius literals, no
    parallel :root token family, no emoji (the same rule set --mode
    enforce-added blocks on for a newly-added file)."""
    from scripts.check_design_system import scan_text

    text = _css_text()
    findings = scan_text("templates/stock-dashboard.css", text)
    blocking_kinds = {
        "color-literal",
        "font-family-literal",
        "radius-literal",
        "literal-custom-property",
        "parallel-token-root",
        "emoji",
    }
    blocking = [f for f in findings if f.rule in blocking_kinds]
    assert not blocking, (
        "token-clean violations in stock-dashboard.css: "
        + "; ".join(f"{f.path}:{f.line} [{f.rule}] {f.detail}" for f in blocking)
    )
