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

# selector -> exact expected declaration (whitespace-tolerant). A bare
# "selector text is present somewhere" check is satisfied by the selector
# appearing in a comment or with the wrong declaration; pinning the
# declaration is what actually proves the override still defeats the
# author display rule it exists to beat.
REQUIRED_CANADA_VISIBILITY_DECLARATIONS: dict[str, str] = {
    ".mx-stockdash--ca .ca-v36-card-grid[hidden]": "display:none!important",
    ".mx-stockdash--ca .ca-v36-card-grid .pvcard[hidden]": "display:none!important",
    ".mx-stockdash--ca .ca-v36-card-grid .sm-hidden": "display:flex!important",
}


def _css_text() -> str:
    if not TEMPLATE_CSS.exists():
        pytest.fail(
            "templates/stock-dashboard.css does not exist yet — TP-1 Task 3 "
            "extraction has not run (expected RED before that task lands)"
        )
    return TEMPLATE_CSS.read_text(encoding="utf-8")


def _extract_balanced_media_block(text: str, media_query_pattern: str) -> str:
    """Return the body of the FIRST @media block matching media_query_pattern,
    delimited by brace-balance rather than a greedy-to-EOF ``.*``.

    A prior version of the 680px-block test used
    ``r"@media\\s*\\(max-width:\\s*680px\\)\\s*\\{(.*)\\}\\s*$"`` — greedy
    ``.*`` anchored at end-of-file, which only worked because the 680px query
    happened to be the LAST thing in the file. Any later content (a new rule,
    a trailing comment block) would have silently swallowed into "the 680px
    block" or broken the match outright. This walks braces instead, so the
    captured block is always exactly the one @media body, regardless of what
    comes after it in the file.
    """
    marker = re.search(media_query_pattern + r"\s*\{", text)
    assert marker, f"could not locate a media block matching {media_query_pattern!r}"
    start = marker.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, f"media block matching {media_query_pattern!r} never closed"
    return text[start:i - 1]


def test_stylesheet_owns_canada_hidden_attribute_visibility():
    """The composer's ``card.hidden = !show`` mechanism (pinned in
    test_canada_v36_composer.py::test_composer_still_hides_via_hidden_attribute)
    is defeated by author display rules (``.pvcard{display:flex}`` /
    ``.ca-v36-card-grid{display:grid}``) unless an explicit [hidden] override
    ships with at-least-equal specificity. That CSS now belongs here, scoped
    under the canonical .mx-stockdash--ca mount, not in the deleted
    composer-owned injectCss()."""
    text = _css_text()
    normalized = re.sub(r"\s+", "", text)
    for rule in REQUIRED_CANADA_VISIBILITY:
        assert rule in text, (
            f"stylesheet lost the {rule!r} override; the Top Picks segment, "
            "leadership filter and grid/table switch would go visually inert "
            "again"
        )
    for selector, decl in REQUIRED_CANADA_VISIBILITY_DECLARATIONS.items():
        pair = re.sub(r"\s+", "", selector) + "{" + decl
        assert pair in normalized, (
            f"{selector!r} no longer declares {decl!r} — the selector text "
            "alone (matched above) is not proof the override still defeats "
            "the author display rule it exists to beat"
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
    # Accepts either the bare token or the cache-stale-resilience fallback
    # stack (var(--font-ui, -apple-system, ...)) — this repair wave (theme-
    # parity-tp1-canada-20260828-sol-001, R8) restores a literal fallback
    # everywhere the stylesheet uses var(--font-ui), including the root; the
    # assertion only needs to keep proving the ROOT reads --font-ui at all.
    assert re.search(r"\.mx-stockdash\s*\{[^}]*font-family:\s*var\(--font-ui[,)]", text), (
        "stylesheet no longer roots .mx-stockdash with font-family: var(--font-ui...)"
    )
    assert re.search(r"\.mx-stockdash\s*\*[^{]*\{[^}]*box-sizing:\s*border-box", text), (
        "stylesheet lost the .mx-stockdash * box-sizing: border-box rule"
    )


def test_stylesheet_stance_and_lane_header_use_prophet_stance_tokens():
    """Action lane/stance identity must use the Prophet stance tokens named
    in the TP-1 plan (var(--ink-pv-<tone>, var(--pv-<tone>))), never a
    market-direction literal (--ink-up/--ink-down/etc.) — applied to both
    the stance chips AND the at-rest Act-Now lane headers, for buy/wait/
    avoid.

    NEAR IS THE ONE EXCEPTION (theme-parity review repair,
    theme-parity-tp1-canada-20260828-sol-001): theme.css derives --pv-near
    FROM --pv-buy (color-mix toward --muted), so binding Near to the stance
    family paints it as a paler Buy rather than a fourth independent hue —
    measured pre-repair as a CIELAB collapse of the Buy/Near separation to
    single digits on both planes. Near is bound to the same informational
    link ink every other "look, don't act yet" affordance on this estate
    already uses (var(--ink-link, var(--link))) instead. This is the FROZEN
    ruling — architecture §5.2/§5.3 outranks the original plan snippet that
    put Near in the stance family."""
    text = _css_text()
    normalized = re.sub(r"\s+", "", text)
    for tone in ("buy", "wait", "avoid"):
        pair = f"var(--ink-pv-{tone},var(--pv-{tone}))"
        assert pair in normalized, (
            f"stylesheet lost the canonical --ink-pv-{tone}/--pv-{tone} "
            "stance token pair"
        )
    assert "var(--ink-link,var(--link))" in normalized, (
        "stylesheet lost the var(--ink-link, var(--link)) informational "
        "ink pair Near now reads"
    )
    assert re.search(r"\.ca-v36-stance\.buy\s*\{[^}]*--ink-pv-buy", text), (
        ".ca-v36-stance.buy no longer reads the Prophet stance token family"
    )
    assert re.search(r"\.ca-v36-an-hd\.buy\s*\{[^}]*--ink-pv-buy", text), (
        ".ca-v36-an-hd.buy (Act-Now lane header) no longer reads the same "
        "Prophet stance token family as the stance chips"
    )
    assert re.search(r"\.ca-v36-stance\.near\s*\{[^}]*--ink-link", text), (
        ".ca-v36-stance.near must read var(--ink-link, var(--link)), not "
        "the stance family — near is not an independent hue in theme.css"
    )
    assert re.search(r"\.ca-v36-an-hd\.near\s*\{[^}]*--ink-link", text), (
        ".ca-v36-an-hd.near (Act-Now lane header) must read var(--ink-link, "
        "var(--link)), not the stance family — near is not an independent "
        "hue in theme.css"
    )
    assert not re.search(r"\.ca-v36-stance\.near\s*\{[^}]*--ink-pv-near", text), (
        ".ca-v36-stance.near reverted to the stance family "
        "(--ink-pv-near/--pv-near), which collapses onto Buy because "
        "theme.css derives --pv-near from --pv-buy"
    )
    assert not re.search(r"\.ca-v36-an-hd\.near\s*\{[^}]*--ink-pv-near", text), (
        ".ca-v36-an-hd.near reverted to the stance family "
        "(--ink-pv-near/--pv-near), which collapses onto Buy because "
        "theme.css derives --pv-near from --pv-buy"
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
    block = _extract_balanced_media_block(text, r"@media\s*\(\s*max-width:\s*680px\s*\)")
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
    the SAME token the rail uses — never a decoration hue and never a
    market-direction token. Because the tint derives from the stance family, the
    zh 红涨绿跌 flip re-keys it with no zh-specific rule (verified in-browser:
    zh light Buy resolves red, Avoid green, each tint at 4% of its own ink).

    NEAR IS THE ONE EXCEPTION, matching the dark rule's repair (see
    test_stylesheet_stance_and_lane_header_use_prophet_stance_tokens above):
    it tints from var(--ink-link, var(--link)) instead of the stance family,
    because theme.css derives --pv-near from --pv-buy and painting Near in
    the stance family collapses it onto Buy."""
    text = re.sub(r"\s+", "", _css_text()).replace('"', "").replace("'", "")
    for tone in ("buy", "wait", "avoid"):
        rule = (
            f"html[data-theme=light].mx-stockdash--ca.ca-v36-an-hd.{tone}"
            f"{{background:color-mix(insrgb,var(--ink-pv-{tone},var(--pv-{tone}))"
        )
        assert rule in text, (
            f"the light Act-Now '{tone}' lane header no longer tints from the "
            f"--ink-pv-{tone}/--pv-{tone} stance token pair"
        )
    near_rule = (
        "html[data-theme=light].mx-stockdash--ca.ca-v36-an-hd.near"
        "{background:color-mix(insrgb,var(--ink-link,var(--link))"
    )
    assert near_rule in text, (
        "the light Act-Now 'near' lane header no longer tints from "
        "var(--ink-link, var(--link)) — near must not tint from the stance "
        "family (--ink-pv-near/--pv-near collapses onto buy)"
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


def test_modal_reachable_stance_and_lead_basis_families():
    """theme-parity-tp1-canada-20260828-sol-001 R2: .ca-v36-stance (the
    modalRows() action-status chip) and .ca-v36-lead-basis (the modalPane()
    title's THEME RANK basis pill) both render inside the sibling-scoped
    Leadership modal (site/canada-stock-v36.js:383-392), but the Task-3
    scoping pass only ever reached the `.mx-stockdash--ca` descendant tree
    — both families rendered unstyled inside the modal (RIG-refused
    regression). Pin that every stance/tone rule and the lead-basis rule is
    duplicated onto `.mx-stockdash--ca ~ .ca-v36-modal <class>` too, so a
    later "tidy the selectors" pass cannot silently re-break them."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    normalized = re.sub(r"\s+", "", text)
    for marker in (
        ".mx-stockdash--ca~.ca-v36-modal.ca-v36-stance",
        ".mx-stockdash--ca~.ca-v36-modal.ca-v36-stance.buy",
        ".mx-stockdash--ca~.ca-v36-modal.ca-v36-stance.near",
        ".mx-stockdash--ca~.ca-v36-modal.ca-v36-stance.wait",
        ".mx-stockdash--ca~.ca-v36-modal.ca-v36-stance.avoid",
        ".mx-stockdash--ca~.ca-v36-modal.ca-v36-lead-basis",
    ):
        assert marker in normalized, (
            f"{marker!r} is missing — a modal-scoped stance/tone or "
            "lead-basis rule regressed to unreachable inside the "
            "sibling-appended Leadership modal"
        )


def test_modal_fail_closed_base_exists():
    """theme-parity-tp1-canada-20260828-sol-001 R2: independent of the
    sibling combinator, the modal must default to display:none as an
    unconditional base rule. If a future wrapper change ever breaks the
    strict adjacency the `~` combinator depends on, this keeps the modal
    HIDDEN rather than rendering unstyled content at the foot of the page —
    fail-closed, not fail-open."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    assert re.search(r"(?<![\w-])\.ca-v36-modal\s*\{\s*display:\s*none;?\s*\}", text), (
        "the unconditional `.ca-v36-modal { display: none; }` fail-closed "
        "base rule is missing — a broken sibling combinator would now "
        "expose unstyled modal content instead of hiding it"
    )


def test_modal_table_name_column_left_numeric_columns_right():
    """theme-parity-tp1-canada-20260828-sol-001 R3: the Leadership modal's
    table (modalRows(), site/canada-stock-v36.js) renders Rank and Count as
    ``<td class="num">`` and Name/Action/Leaders as plain ``<td>``. Pin the
    alignment split: every plain td (including Name) is left-aligned text,
    and only td.num carries the right-aligned tabular-figure treatment —
    under the sibling-scoped modal selector, not the descendant one."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    normalized = re.sub(r"\s+", " ", text)
    assert re.search(
        r"\.mx-stockdash--ca\s*~\s*\.ca-v36-modal\s+\.ca-v36-modal-table\s+td\s*\{[^}]*text-align:\s*left",
        normalized,
    ), (
        "the sibling-scoped .ca-v36-modal-table td rule must set "
        "text-align: left (Name and every other non-numeric column)"
    )
    assert re.search(
        r"\.mx-stockdash--ca\s*~\s*\.ca-v36-modal\s+\.ca-v36-modal-table\s+td\.num\s*\{[^}]*text-align:\s*right",
        normalized,
    ), (
        "the sibling-scoped .ca-v36-modal-table td.num rule must set "
        "text-align: right (Rank + Count, the two numeric columns)"
    )


def test_breadth_measure_is_achromatic_not_the_link_hue():
    """theme-parity-tp1-canada-20260828-sol-001 R2 (Sol REVISE ruling): a
    reserved hue (--link) may not carry magnitude. The breadth gauge's
    track (::before) and fill (::after) on .ca-v36-lead-row must both read
    from the achromatic --line/--muted family in BOTH themes, with
    comparable semantic authority — no light-only override may reintroduce
    --link, and dark must not either."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    assert re.search(
        r"\.ca-v36-lead-row\.ca-v36-has-breadth::after\s*\{[^}]*color-mix\(in srgb,\s*var\(--muted\)",
        text,
    ), ".ca-v36-lead-row...::after (breadth fill) no longer reads the achromatic --muted token"
    assert re.search(
        r"\.ca-v36-lead-row\.ca-v36-has-breadth::before\s*\{[^}]*color-mix\(in srgb,\s*var\(--line\)",
        text,
    ), ".ca-v36-lead-row...::before (breadth track) no longer reads the achromatic --line token"
    for match in re.finditer(r"\.ca-v36-lead-row[^{]*::?(before|after)\s*\{([^}]*)\}", text):
        assert "--link" not in match.group(2), (
            f".ca-v36-lead-row::{match.group(1)} reintroduced var(--link) — "
            "the breadth measure must stay achromatic in both themes"
        )


def test_breadth_measure_is_a_bounded_gauge_with_a_visible_track():
    """theme-parity-tp1-canada-20260828-sol-001 R3-02 (Sol COND-R3-02): R3's
    inset ::after-only fill was still an UNBOUNDED row-width geometry
    (`width: var(--breadth); max-width: calc(100% - 24px)`) — on a ~1300px
    panel that inset is only ~24px, so a 100%-count row still rendered as a
    near-full-width rule, not an instrument. The fix reintroduces a ::before
    but as a fixed-length, bounded GAUGE TRACK (not the old full-row-width
    divider): both track and fill are scaled by one shared
    --mx-breadth-unit custom property, so the track's width is a fixed
    `100 * --mx-breadth-unit` and the fill's width is
    `var(--breadth) * --mx-breadth-unit` — a 100 value fills exactly to the
    track's own terminus and stops, never overflowing the row. Both
    pseudo-elements are scoped to the `.ca-v36-has-breadth` marker class the
    composer emits only for rows that carry a measured --breadth, so an
    unknown-membership row renders neither track nor fill."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    # --mx-breadth-unit is deliberately UNITLESS (a bare scalar, not a `2px`
    # literal) — check_design_system.py's literal-custom-property rule blocks
    # a custom property whose declared value is a literal quantity-with-unit,
    # so the scalar carries no unit suffix and the `px` is applied once,
    # inline, at each calc() use site instead.
    unit_match = re.search(
        r"\.ca-v36-lead-row\s*\{[^}]*--mx-breadth-unit:\s*([0-9.]+)\s*;", text
    )
    assert unit_match, (
        ".ca-v36-lead-row must define a unitless --mx-breadth-unit custom "
        "property so the gauge scale lives in one place"
    )
    assert not re.search(r"--mx-breadth-unit:\s*[0-9.]+px", text), (
        "--mx-breadth-unit must stay a unitless scalar (no `px` baked into "
        "the custom-property declaration) — apply `px` at the calc() use "
        "sites instead, or the design-system literal-custom-property rule "
        "blocks it"
    )
    before_match = re.search(
        r"\.ca-v36-lead-row\.ca-v36-has-breadth::before\s*\{([^}]*)\}", text
    )
    assert before_match, (
        ".ca-v36-lead-row.ca-v36-has-breadth::before (breadth track) rule "
        "is missing — the bounded gauge needs a visible fixed-length track"
    )
    before_body = before_match.group(1)
    assert re.search(
        r"width:\s*calc\(\s*100\s*\*\s*var\(--mx-breadth-unit\)\s*\*\s*1px\s*\)",
        before_body,
    ), (
        ".ca-v36-lead-row...::before must be a fixed 100-unit track "
        "(width: calc(100 * var(--mx-breadth-unit) * 1px))"
    )
    assert re.search(r"border-radius:\s*var\(--r-pill", before_body), (
        ".ca-v36-lead-row...::before (track) must carry a rounded "
        "(var(--r-pill)) terminus"
    )
    after_match = re.search(
        r"\.ca-v36-lead-row\.ca-v36-has-breadth::after\s*\{([^}]*)\}", text
    )
    assert after_match, ".ca-v36-lead-row.ca-v36-has-breadth::after (breadth fill) rule is missing"
    after_body = after_match.group(1)
    assert re.search(
        r"width:\s*calc\(\s*var\(--breadth,\s*0\)\s*\*\s*var\(--mx-breadth-unit\)\s*\*\s*1px\s*\)",
        after_body,
    ), (
        ".ca-v36-lead-row...::after must scale its width by "
        "var(--breadth, 0) * var(--mx-breadth-unit) * 1px — a bounded gauge "
        "fill, not a bare percentage — and fall back to 0 when the composer "
        "omits --breadth (unknown-membership rows get no meter)"
    )
    assert re.search(r"border-radius:\s*var\(--r-pill", after_body), (
        ".ca-v36-lead-row...::after (fill) must carry a rounded "
        "(var(--r-pill)) terminus"
    )
    assert "bottom: 6px" in before_body and "bottom: 6px" in after_body, (
        "track and fill must both sit clear of the row's own border-top "
        "boundary (bottom: 6px), for boundary separation"
    )
    # Bare (unscoped) .ca-v36-lead-row::before/::after must not exist —
    # both pseudo-elements are scoped to the has-breadth marker class so an
    # unknown-membership row (no marker) renders neither.
    assert not re.search(r"\.ca-v36-lead-row::before\s*\{", text), (
        "an unscoped .ca-v36-lead-row::before would render a track on "
        "unknown-membership rows too — scope it to .ca-v36-has-breadth"
    )
    assert not re.search(r"\.ca-v36-lead-row::after\s*\{", text), (
        "an unscoped .ca-v36-lead-row::after would render a fill on "
        "unknown-membership rows too — scope it to .ca-v36-has-breadth"
    )


def test_breadth_gauge_unit_rescales_on_mobile():
    """theme-parity-tp1-canada-20260828-sol-001 R3-02: the desktop gauge is
    100 * --mx-breadth-unit wide; at the desktop 2px unit that is 200px,
    which does not fit a 390px mobile row next to rank/name/stance/count.
    The @media (max-width: 680px) block must re-declare --mx-breadth-unit
    to a smaller value so the gauge still fits."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    mobile_match = re.search(
        r"@media\s*\(max-width:\s*680px\)\s*\{(.*)\}\s*$", text, re.S
    )
    assert mobile_match, "could not locate the @media (max-width: 680px) block"
    mobile_body = mobile_match.group(1)
    assert re.search(
        r"\.ca-v36-lead-row\s*\{[^}]*--mx-breadth-unit:\s*[0-9.]+\s*;", mobile_body
    ), (
        "the mobile media block must re-declare .ca-v36-lead-row's "
        "(unitless) --mx-breadth-unit so the bounded gauge rescales for a "
        "390px row"
    )


def test_dark_active_filter_rows_get_a_rail_not_only_a_tint():
    """theme-parity-tp1-canada-20260828-sol-001 R3: the dark plane's
    .is-active state used to share its rule with :hover (a 6% link tint
    that reads identically to a hover the pointer has already left). Dark
    needs an equivalent-information marker to the light plane's box-shadow
    rail: a deeper background tint AND an inset rail in the link ink, on
    both the Act-Now row family and the Leadership row family, in the BASE
    (dark) section — not only under html[data-theme=light]."""
    text = re.sub(r"/\*.*?\*/", " ", _css_text(), flags=re.S)
    # Split off the light-themed section so these assertions can only match
    # base (dark) rules, never a light[data-theme] duplicate.
    base_text = re.split(r"html\[data-theme=light\]", text)[0]
    for selector, rail_px in (
        (r"\.mx-stockdash--ca\s+\.ca-v36-an-row\.is-active", "2px"),
        (r"\.mx-stockdash--ca\s+\.ca-v36-lead-row\.is-active", "3px"),
    ):
        match = re.search(selector + r"\s*\{([^}]*)\}", base_text)
        assert match, f"base (dark) .is-active rule missing for {selector!r}"
        body = match.group(1)
        assert re.search(r"color-mix\(in srgb,\s*var\(--link\)\s*12%", body), (
            f"{selector!r} must carry a deeper (12%) link tint than the "
            "6% hover wash it used to share"
        )
        assert re.search(
            r"box-shadow:\s*inset\s*" + rail_px + r"\s+0\s+0\s+var\(--ink-link,\s*var\(--link\)\)",
            body,
        ), f"{selector!r} must carry an inset {rail_px} link-ink rail"


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
