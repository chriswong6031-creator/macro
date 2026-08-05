"""The closed Terminal overlay must paint NOTHING — evaluated, not grepped.

Why this suite exists.  Every other guard on the portal is a substring
assertion over ``templates/terminal_overlay.js``.  Substrings cannot see a
CASCADE, and the defect that stranded mobile users for weeks lived entirely in
the cascade:

* the root hid the closed overlay with ``visibility:hidden`` — an INHERITED
  property;
* ``.mmto-loader`` re-declared ``visibility:visible``, which un-hides a subtree
  straight through an ancestor's ``hidden``;
* the only rule that still hid the loader was
  ``#mm-terminal-overlay.is-ready .mmto-loader{visibility:hidden}``, and the
  mobile close path (``performClose`` → ``destroyFrame`` → ``resetFrameState``)
  REMOVES ``is-ready``;
* ``@media(max-width:700px)`` forced ``.mmto-stage{opacity:1!important}``
  unconditionally, deleting the one hide that did not inherit.

Result: after every mobile close the branded splash stayed painted full-screen
at ``z-index:2147483000`` over a dashboard that was, by every JS-observable
measure, correctly restored.  ``MDXTerminalOverlay.isOpen()`` was ``false``, the
iframe was gone, history was clean and scroll was restored — only the pixels
lied, which is why session after session "fixed" it and the operator kept
seeing it.

So this suite resolves the real cascade (specificity, ``!important``, source
order, inheritance, media queries) and asserts what the user's eyes see, in
every state the overlay can reach.  A substring test cannot regress-guard this;
this one can.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

OVERLAY_ID = "mm-terminal-overlay"
MOBILE_MEDIA = "@media(max-width:700px)"

# Inherited-vs-not is the whole point of this suite, so it is stated explicitly.
INHERITED = {"visibility"}


# --------------------------------------------------------------------------
# Extract the stylesheet the overlay actually injects
# --------------------------------------------------------------------------
def overlay_css(source: str | None = None) -> str:
    """Return the CSS text ``injectStyles()`` assigns to ``style.textContent``.

    The source is a JS array of single-quoted fragments joined with ``''``;
    block comments sit between fragments.  Everything is literal — no
    interpolation — so concatenating the string literals reproduces the exact
    bytes the browser parses.
    """
    text = source if source is not None else (
        ROOT / "templates" / "terminal_overlay.js"
    ).read_text(encoding="utf-8")
    start = text.index("style.textContent = [")
    end = text.index("].join('');", start)
    body = text[start + len("style.textContent = ["):end]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)          # drop comments
    fragments = re.findall(r"'((?:[^'\\]|\\.)*)'", body)       # keep literals
    assert fragments, "no CSS fragments found in injectStyles()"
    return "".join(f.replace("\\'", "'").replace('\\"', '"') for f in fragments)


# --------------------------------------------------------------------------
# A small, honest CSS cascade
# --------------------------------------------------------------------------
class Rule:
    __slots__ = ("selector", "decls", "order", "media")

    def __init__(self, selector: str, decls: dict, order: int, media: str) -> None:
        self.selector = selector.strip()
        self.decls = decls
        self.order = order
        self.media = media


def _parse_decls(block: str) -> dict:
    out = {}
    for chunk in block.split(";"):
        if ":" not in chunk:
            continue
        prop, _, value = chunk.partition(":")
        value = value.strip()
        important = value.endswith("!important")
        if important:
            value = value[: -len("!important")].strip()
        out[prop.strip().lower()] = (value, important)
    return out


def parse_rules(css: str) -> list[Rule]:
    """Flatten the stylesheet into rules tagged with their enclosing @media."""
    rules: list[Rule] = []
    i, order, media = 0, 0, ""
    while i < len(css):
        brace = css.find("{", i)
        if brace < 0:
            break
        prelude = css[i:brace].strip()
        if prelude.startswith("@media"):
            depth, j = 1, brace + 1
            while j < len(css) and depth:
                depth += (css[j] == "{") - (css[j] == "}")
                j += 1
            inner = css[brace + 1:j - 1]
            for rule in parse_rules(inner):
                rule.media = prelude
                rule.order = order
                order += 1
                rules.append(rule)
            i = j
            continue
        if prelude.startswith("@"):            # @keyframes and friends
            depth, j = 1, brace + 1
            while j < len(css) and depth:
                depth += (css[j] == "{") - (css[j] == "}")
                j += 1
            i = j
            continue
        close = css.find("}", brace)
        decls = _parse_decls(css[brace + 1:close])
        for selector in prelude.split(","):
            rules.append(Rule(selector, decls, order, media))
            order += 1
        i = close + 1
    return rules


_SIMPLE = re.compile(r"(::?[a-z-]+(?:\([^)]*\))?|#[\w-]+|\.[\w-]+|\[[^\]]*\]|[\w-]+|\*)")


def _specificity(selector: str) -> tuple[int, int, int]:
    a = b = c = 0
    for token in _SIMPLE.findall(selector):
        if token.startswith("#"):
            a += 1
        elif token.startswith("::"):
            c += 1
        elif token.startswith(":"):
            if token.startswith(":not("):
                inner = token[5:-1]
                ia, ib, ic = _specificity(inner)
                a, b, c = a + ia, b + ib, c + ic
            else:
                b += 1
        elif token.startswith(".") or token.startswith("["):
            b += 1
        elif token != "*":
            c += 1
    return a, b, c


class Node:
    """One element in a straight ancestor chain (no siblings needed here)."""

    def __init__(self, tag: str, node_id: str = "", classes: tuple = (), parent=None):
        self.tag, self.id, self.classes, self.parent = tag, node_id, set(classes), parent


def _matches_compound(node: Node, compound: str) -> bool:
    for token in _SIMPLE.findall(compound):
        if token.startswith("::"):
            return False                       # pseudo-elements: not this node
        if token.startswith(":not("):
            if _matches_compound(node, token[5:-1]):
                return False
        elif token.startswith(":"):
            return False                       # unused here; fail closed
        elif token.startswith("#"):
            if node.id != token[1:]:
                return False
        elif token.startswith("."):
            if token[1:] not in node.classes:
                return False
        elif token.startswith("["):
            return False                       # unused here; fail closed
        elif token != "*":
            if node.tag != token:
                return False
    return True


def matches(node: Node, selector: str) -> bool:
    """Descendant/child combinators only — the overlay uses nothing else."""
    if ">" in selector or "+" in selector or "~" in selector:
        return False
    parts = selector.split()
    if not parts:
        return False
    if not _matches_compound(node, parts[-1]):
        return False
    current = node.parent
    for compound in reversed(parts[:-1]):
        while current is not None and not _matches_compound(current, compound):
            current = current.parent
        if current is None:
            return False
        current = current.parent
    return True


def computed(node: Node, prop: str, rules: list[Rule], mobile: bool):
    """Resolve one property for ``node``, honouring inheritance."""
    applicable = [
        r for r in rules
        if (not r.media or (mobile and r.media == MOBILE_MEDIA))
        and prop in r.decls and matches(node, r.selector)
    ]
    if applicable:
        winner = max(
            applicable,
            key=lambda r: (r.decls[prop][1], _specificity(r.selector), r.order),
        )
        value = winner.decls[prop][0]
        if value != "inherit":
            return value
    if prop in INHERITED and node.parent is not None:
        return computed(node.parent, prop, rules, mobile)
    return None


# --------------------------------------------------------------------------
# The overlay's real DOM shape, as built by buildOverlay()
# --------------------------------------------------------------------------
def overlay_tree(root_classes: tuple):
    root = Node("div", OVERLAY_ID, root_classes)
    stage = Node("div", classes=("mmto-stage",), parent=root)
    return {
        "root": root,
        "stage": stage,
        "loader": Node("div", classes=("mmto-loader",), parent=stage),
        "frame": Node("iframe", classes=("mmto-frame",), parent=stage),
        "toast": Node("div", classes=("mmto-toast",), parent=stage),
    }


def paints(node: Node, rules: list[Rule], mobile: bool) -> bool:
    """True when this element would put pixels on screen.

    Visibility is the element's own inherited resolution; opacity is NOT
    inherited but DOES composite, so a zero anywhere up the chain wins.
    """
    if (computed(node, "visibility", rules, mobile) or "visible") == "hidden":
        return False
    walker = node
    while walker is not None:
        if float(computed(walker, "opacity", rules, mobile) or 1) == 0:
            return False
        walker = walker.parent
    return True


@pytest.fixture(scope="module")
def rules() -> list[Rule]:
    return parse_rules(overlay_css())


# --------------------------------------------------------------------------
# The evaluator must be able to SEE the defect, or it guards nothing
# --------------------------------------------------------------------------
PRE_FIX_CSS = (
    "#mm-terminal-overlay{position:fixed;inset:0;z-index:2147483000;"
    "visibility:hidden;pointer-events:none}"
    "#mm-terminal-overlay.is-open{visibility:visible;pointer-events:auto}"
    ".mmto-stage{position:absolute;inset:0;opacity:0}"
    "#mm-terminal-overlay.is-open .mmto-stage{opacity:1}"
    ".mmto-loader{position:absolute;inset:0;opacity:1;visibility:visible}"
    "#mm-terminal-overlay.is-ready .mmto-loader{opacity:0;visibility:hidden}"
    "@media(max-width:700px){"
    ".mmto-stage{opacity:1!important}"
    "#mm-terminal-overlay.is-open .mmto-stage{opacity:1!important}}"
)


def test_evaluator_reproduces_the_shipped_defect():
    """Guard the guard: the pre-fix cascade must FAIL this suite's paint check.

    Without this, a subtly broken evaluator would pass every assertion below
    while the real page stayed broken — the shape that let the original bug
    survive three "fixes".
    """
    pre = parse_rules(PRE_FIX_CSS)
    closed = overlay_tree(())
    assert paints(closed["loader"], pre, mobile=True), (
        "the evaluator no longer reproduces the defect (mobile close left "
        "the splash painted) — it can no longer prove the fix"
    )
    # ...and correctly reports desktop, where `.mmto-stage{opacity:0}` survived.
    assert not paints(closed["loader"], pre, mobile=False)


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------
@pytest.mark.parametrize("mobile", [True, False], ids=["mobile", "desktop"])
@pytest.mark.parametrize(
    "root_classes",
    [(), ("is-ready",), ("is-loading",), ("is-slow",), ("is-loading", "is-slow")],
    ids=["bare", "after-desktop-close", "after-reset", "slow", "loading-slow"],
)
def test_closed_overlay_paints_nothing(rules, mobile, root_classes):
    """No reachable closed state may paint — `is-ready` must not be load-bearing.

    ``resetFrameState()`` strips ``is-ready``/``is-loading``/``is-slow`` on the
    mobile close path while the desktop path leaves ``is-ready`` on, so the
    closed overlay is genuinely reached with and without each of them.
    """
    tree = overlay_tree(root_classes)
    for name in ("root", "stage", "loader", "frame", "toast"):
        assert not paints(tree[name], rules, mobile), (
            f"closed overlay still paints .{name} "
            f"(classes={root_classes or '<none>'}, mobile={mobile})"
        )


@pytest.mark.parametrize("mobile", [True, False], ids=["mobile", "desktop"])
def test_open_overlay_shows_the_loader_until_the_terminal_paints(rules, mobile):
    opening = overlay_tree(("is-open", "is-loading"))
    assert paints(opening["loader"], rules, mobile)
    assert paints(opening["stage"], rules, mobile)


@pytest.mark.parametrize("mobile", [True, False], ids=["mobile", "desktop"])
def test_ready_overlay_hands_the_screen_to_the_terminal(rules, mobile):
    ready = overlay_tree(("is-open", "is-ready"))
    assert not paints(ready["loader"], rules, mobile), "loader outlived the reveal"
    assert paints(ready["frame"], rules, mobile), "Terminal iframe never revealed"


def _visibility_visible_offenders(rule_list: list[Rule]) -> list[str]:
    """Rules that force ``visibility:visible`` on something below the root.

    Allowed: the root's own state rules (``#mm-terminal-overlay.is-open`` etc.),
    which is where the open state belongs.  Everything else re-declares an
    INHERITED property and therefore un-hides itself through a closed root.
    """
    offenders = []
    for rule in rule_list:
        if rule.decls.get("visibility", ("", False))[0] != "visible":
            continue
        compounds = rule.selector.split()
        subject = compounds[-1]
        is_root_itself = len(compounds) == 1 and f"#{OVERLAY_ID}" in subject
        scoped_to_open = ".is-open" in subject or ".is-closing" in subject
        if not (is_root_itself or scoped_to_open):
            offenders.append(rule.selector)
    return offenders


def test_no_descendant_re_declares_visibility_visible(rules):
    """The specific cascade mistake, banned by name.

    A descendant that hard-codes ``visibility:visible`` overrides the root's
    ``hidden`` and is invisible to every substring guard in the portal suite.
    If a future state genuinely needs it, scope the selector to ``.is-open``.
    """
    # Non-vacuous by construction: the shipped defect is the thing it catches.
    assert _visibility_visible_offenders(parse_rules(PRE_FIX_CSS)) == [".mmto-loader"]
    assert not _visibility_visible_offenders(rules), (
        "these rules un-hide themselves through the closed root's "
        f"visibility:hidden: {_visibility_visible_offenders(rules)}"
    )


def test_root_carries_an_inheritance_proof_hide(rules):
    """`opacity:0` on the root is the guarantee no descendant can undo."""
    root_closed = Node("div", OVERLAY_ID, ())
    assert computed(root_closed, "opacity", parse_rules(overlay_css()), True) == "0"
    for state in ("is-open", "is-closing"):
        node = Node("div", OVERLAY_ID, (state,))
        assert computed(node, "opacity", rules, True) == "1", (
            f".{state} must restore the root to opacity:1"
        )


def test_mobile_stage_opacity_override_is_scoped_to_the_open_state(rules):
    """The `!important` opacity belongs to `.is-open`, never to the base rule.

    Hoisting it to the unconditional ``.mmto-stage`` rule is what deleted the
    closed overlay's non-inheriting hide in the first place.
    """
    bad = [
        r.selector for r in rules
        if r.media == MOBILE_MEDIA
        and r.decls.get("opacity", ("", False)) == ("1", True)
        and ".is-open" not in r.selector
    ]
    assert not bad, f"unconditional mobile opacity:1 restored on: {bad}"


def test_closed_overlay_stops_its_infinite_animations(rules):
    """Hidden layers that keep animating are how WebKit strands them on screen."""
    paused = {
        r.selector for r in rules
        if r.decls.get("animation-play-state", ("", False))[0] == "paused"
    }
    for target in ("mmto-loader::before", "mmto-mark::before",
                   "mmto-mark::after", "mmto-progress::after"):
        assert any(target in s and ":not(.is-open)" in s for s in paused), (
            f"{target} keeps animating while the overlay is closed"
        )


def test_site_copy_and_theme_bundle_carry_the_same_stylesheet():
    """The fix is only real once the bytes production serves carry it."""
    source = overlay_css()
    assert overlay_css((ROOT / "site" / "terminal_overlay.js").read_text("utf-8")) == source
    for theme in ("templates/theme.js", "site/theme.js"):
        text = (ROOT / theme).read_text(encoding="utf-8")
        if "style.textContent = [" not in text:
            continue  # templates/theme.js carries the loader, not the bundle
        assert overlay_css(text) == source, f"{theme} ships a stale overlay stylesheet"
