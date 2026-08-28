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


# --- TP-1 Task 4: light art-direction structural fence ----------------------
#
# The theme-parity law (CLAUDE.md §"Theme art direction") holds that dark and
# light are TWO ART DIRECTIONS of one semantic system, and that "the same CSS
# still renders once the tokens swap" is NOT a light design. These tests prove
# only that an EXPLICIT light treatment EXISTS for each surface the plan names
# — presence, not taste. Whether the light plane is any good is settled by the
# committed dark/light x EN/ZH x 1440/390 evidence matrix and the independent
# design reviewer, never by this file.

LIGHT_ROOT = "html[data-theme=light] .mx-stockdash--ca"

# surface label -> class markers that must each appear in a light-rooted rule
REQUIRED_LIGHT_SURFACES: dict[str, tuple[str, ...]] = {
    "Act-Now (one instrument, four semantic lanes)": (
        ".ca-v36-an-lanes",
        ".ca-v36-an-lane",
        # stance identity on the lane headers, one rule per semantic lane
        ".ca-v36-an-hd.buy",
        ".ca-v36-an-hd.near",
        ".ca-v36-an-hd.wait",
        ".ca-v36-an-hd.avoid",
        # "View all" as a quiet footer control
        ".ca-v36-an-more",
    ),
    "Prophet Top Picks": (".ca-v36-card-grid", ".ca-v36-top-pick"),
    "segmented controls": (".ca-v36-seg", ".ca-v36-an-seg"),
    "Leadership & Rotation": (
        ".ca-v36-lead-col-h",
        ".ca-v36-lead-row",
        ".ca-v36-expand",
    ),
    "modal": (".ca-v36-modal", ".ca-v36-modal-card", ".ca-v36-modal-pane"),
}


# A light rule only counts as an art-direction DECISION if it actually declares
# material or composition. Anything else — a border reset inside a breakpoint,
# say — mentions the class without treating it.
TREATMENT_PROPERTIES = ("background", "border", "box-shadow", "color", "gap")


def _rules(text: str) -> list[tuple[str, str, bool]]:
    """Every (selector, declaration-block, inside_media) triple.

    Selectors are whitespace/quote-normalized: ``html[data-theme="light"]`` and
    ``html[data-theme=light]`` are the SAME selector to a browser. The shipped
    file uses the unquoted spelling the Task-3 extraction established and the
    plan writes the quoted one, so the fence pins the selector's MEANING rather
    than its punctuation.
    """
    body = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    out: list[tuple[str, str, bool]] = []
    depth, media_depth, buf = 0, None, ""
    for i, ch in enumerate(body):
        if ch == "{":
            head = re.sub(r"\s+", " ", buf.replace('"', "").replace("'", "")).strip()
            depth += 1
            if head.startswith("@"):
                if media_depth is None:
                    media_depth = depth
                buf = ""
                continue
            close = body.find("}", i)
            out.append((head, body[i + 1:close if close > 0 else len(body)],
                        media_depth is not None))
            buf = ""
        elif ch == "}":
            if media_depth is not None and depth == media_depth:
                media_depth = None
            depth -= 1
            buf = ""
        else:
            buf += ch
    return out


def test_light_art_direction_has_explicit_rules_for_every_named_surface():
    """Every surface TP-1 Task 4 names owns at least one TOP-LEVEL rule rooted
    at html[data-theme=light] .mx-stockdash--ca that actually declares material
    or composition.

    Both halves are load-bearing. Matching the selector alone is not enough —
    the first draft of this fence passed while the entire light Act-Now lane
    treatment was deleted, because the class still appeared in a breakpoint's
    border reset. Requiring a declaration, outside any @media block, is what
    makes the fence a positive proof of treatment rather than a proof that the
    string occurs somewhere.
    """
    rules = _rules(_css_text())
    missing: list[str] = []
    for surface, markers in REQUIRED_LIGHT_SURFACES.items():
        # Class names must match at a boundary, never as a substring: plain
        # `in` lets `.ca-v36-an-lane` be "satisfied" by `.ca-v36-an-lanes`,
        # which is how the first draft passed with the whole light lane
        # treatment deleted.
        for marker in markers:
            pattern = re.compile(re.escape(marker) + r"(?![\w-])")
            treated = any(
                LIGHT_ROOT in selector
                and pattern.search(selector)
                and not in_media
                and any(p in block for p in TREATMENT_PROPERTIES)
                for selector, block, in_media in rules
            )
            if not treated:
                missing.append(f"{surface}: no light-rooted treatment for {marker}")
    assert not missing, (
        "the Canada light art direction lost explicit treatment for:\n  "
        + "\n  ".join(missing)
        + f"\nEach needs a top-level rule rooted at {LIGHT_ROOT!r} declaring "
        f"one of {TREATMENT_PROPERTIES}."
    )


def test_light_lane_headers_tint_from_the_prophet_stance_tokens():
    """Lane identity in light is a narrow semantic rail plus a low-alpha tint of
    the SAME stance token the rail uses — never a decoration hue and never a
    market-direction token. Because the tint derives from the stance family, the
    zh 红涨绿跌 flip re-keys it with no zh-specific rule (verified in-browser:
    zh light Buy resolves red, Avoid green, each tint at 4% of its own ink)."""
    text = re.sub(r"\s+", "", _css_text()).replace('"', "").replace("'", "")
    for tone in ("buy", "near", "wait", "avoid"):
        rule = (
            f"html[data-theme=light].mx-stockdash--ca.ca-v36-an-hd.{tone}"
            f"{{background:color-mix(insrgb,var(--ink-pv-{tone},var(--pv-{tone}))"
        )
        assert rule in text, (
            f"the light Act-Now '{tone}' lane header no longer tints from the "
            f"--ink-pv-{tone}/--pv-{tone} stance token pair"
        )


def _split_top_level(value: str) -> list[str]:
    """Split a comma-separated CSS value at top level only.

    A naive ``value.split(",")`` tears ``color-mix(in srgb, var(--x) 6%,
    transparent)`` into fragments and makes any shadow using one unreadable —
    which is how the first draft of the glow fence flagged a perfectly ordinary
    contained drop shadow.
    """
    parts, depth, current = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return parts


def test_light_plane_never_reintroduces_a_glow_halo():
    """§12/doctrine §5 (8): dark earns emphasis with a low-alpha bloom, light
    earns it with a RING — a bloom on white degrades into a pastel stain.

    A halo, precisely: a shadow layer that is CENTERED (both offsets zero),
    BLURRED (blur > 0) and not pulled back in by a negative spread. A ring
    (``0 0 0 1px``) has no blur; a contained drop shadow
    (``0 6px 18px -8px``) is offset and negatively spread. Both are legal in
    light; only the centered bloom is not.
    """
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    offenders = []
    for match in re.finditer(
        r"(html\[data-theme=[\"']?light[\"']?\][^{}]*)\{([^}]*)\}", text
    ):
        selector, block = match.group(1), match.group(2)
        for shadow in re.finditer(r"box-shadow:([^;}]*)", block):
            for layer in _split_top_level(shadow.group(1)):
                if "inset" in layer:
                    continue
                lengths = re.findall(r"(?<![\w.-])(-?\d+(?:\.\d+)?)(px)?(?![\w(])",
                                     layer.split("color-mix")[0].split("var(")[0])
                nums = [float(v) for v, _ in lengths]
                if len(nums) < 3:
                    continue
                dx, dy, blur = nums[0], nums[1], nums[2]
                spread = nums[3] if len(nums) > 3 else 0.0
                if dx == 0 and dy == 0 and blur > 0 and spread >= 0:
                    offenders.append(f"{' '.join(selector.split())} -> {layer.strip()}")
    assert not offenders, (
        "light-rooted rules reintroduced a centered glow halo (light uses a "
        "ring plus var(--card-shadow), never a bloom):\n  "
        + "\n  ".join(offenders)
    )


def test_modal_family_stays_sibling_scoped_to_the_mount():
    """The composer mounts the leadership modal with
    ``document.body.appendChild(modal)``, so it is a following SIBLING of the
    .mx-stockdash--ca <main>, never a descendant. The Task-3 extraction scoped
    it as a descendant and the whole family went dead in BOTH themes (measured
    on that head: position:static, display:block, no scrim — the dialog never
    overlaid and its rows rendered as a stray block at the foot of the page).
    Pin the combinator so a later "tidy the selectors" pass cannot silently
    re-break the dialog: the checker cannot see a selector that matches
    nothing, and neither can a passing unit test."""
    # Comments must be stripped first: this file's own header explains the bug
    # by quoting the broken descendant selector, and a naive scan reads that
    # prose as a live rule.
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    assert ".mx-stockdash--ca ~ .ca-v36-modal" in text, (
        "the modal family lost its sibling combinator; .mx-stockdash--ca "
        ".ca-v36-modal matches nothing in the shipped DOM"
    )
    bad = re.findall(r"\.mx-stockdash--ca\s+\.ca-v36-modal", text)
    assert not bad, (
        f"{len(bad)} modal selector(s) use the descendant combinator "
        "(.mx-stockdash--ca .ca-v36-modal); the modal is a SIBLING of the "
        "mount, so those rules are dead CSS"
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
