"""tests/test_lens_nested_control_taps.py — the lens must never steal a nested control's tap.

`theme.js`'s lens binds `SEL = '[data-tip-en], .lens-q, .lens-term'` and opens on
`focusin`. Tapping a <button>/<a> INSIDE a tip wrapper focuses it, focusin bubbles
up to the wrapper, and in SHEET mode (`max-width:640px`) `show()` mounts a
full-viewport `.lens-scrim` — mid-tap. mousedown has already landed on the control
but mouseup then lands on the scrim, so the browser retargets the `click` to
<body> and the control's own handler NEVER runs.

The click handler has always carved nested controls out ("let the control activate
instead of hijacking the tap"), but that carve-out is unreachable here: no click
survives the scrim to reach it. So the fix belongs in `focusin`, and this suite
pins it there.

Measured on the deployed page at 390x844 / hover:none / isSheet, before the fix —
`elementFromPoint` at each control's own tap point returned `DIV.lens-scrim`:
  /us_stocks.html  3  (#us-src-toggle, #us-st-view-toggle, .nb-ewatch > a)
  /canada.html    24  (.cax-sorow > a)
  /bonds.html      2  (.cc-tile > a)

WHY THIS SUITE IS BROWSER-FREE. The CI packs install a minimal dependency set, not
``requirements.txt`` — a ``pytest.importorskip("playwright")`` here would SKIP in CI
and report green while proving nothing (house trap:
ci-packs-install-minimal-deps-not-requirements). The browser measurements live in
the PR body; what is mechanically checkable is asserted against the shipped source.

DO NOT "strengthen" this into "no data-tip wrapper may contain a focusable control".
That pins the WORKAROUND, not the fix: with the carve-out in place such a wrapper is
correct, and those tips (".cax-sorow" names the leader and its sector rank) are worth
keeping. The invariant is the carve-out, not the absence of the markup.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_JS = ROOT / "templates" / "theme.js"
SITE_JS = ROOT / "site" / "theme.js"

# The focusable set the carve-out must cover. A control the selector misses is a
# control whose tap the lens still steals.
FOCUSABLE = ("button", "a", "input", "select", "textarea", "label", '[role="button"]')


def _lens_region(src: str) -> str:
    """The lens IIFE, from its SEL definition to the end of its keydown binding."""
    start = src.index("var SEL = '[data-tip-en], .lens-q, .lens-term';")
    end = src.index("if (e.key === 'Escape' && isOpen()) hide();", start)
    return src[start:end]


def _handler_body(region: str, event: str) -> str:
    """The body of the lens's delegated `event` listener."""
    # Anchored on `document.` on purpose: the lens also binds a 'click' listener on
    # `pop` (the .lens-x close button), and an unanchored match finds that one first.
    m = re.search(
        r"document\.addEventListener\('" + event + r"',\s*function\s*\(e\)\s*\{(.*?)\n  \},\s*true\);",
        region,
        re.S,
    )
    assert m, f"lens {event!r} listener not found — did theme.js restructure?"
    return m.group(1)


def _sources():
    """Both shipped copies. site/theme.js is the BAKED asset browsers actually load —
    a fix that lands only in the template ships nothing, so it is not optional
    coverage. When it is sparse-omitted the case is kept and SKIPPED by name rather
    than dropped, so a thinned worktree cannot quietly halve what green means."""
    assert TEMPLATE_JS.exists(), TEMPLATE_JS
    return [
        ("templates/theme.js", TEMPLATE_JS.read_text(encoding="utf-8")),
        ("site/theme.js", SITE_JS.read_text(encoding="utf-8") if SITE_JS.exists() else None),
    ]


SOURCES = _sources()
SOURCE_IDS = [n for n, _ in SOURCES]


def _require(name, src):
    if src is None:
        pytest.skip(
            f"{name} not checked out (sparse worktree) — opt in with: "
            "python3 scripts/worktree_sparse.py add site"
        )
    return src


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_focusin_consults_the_nested_control_carve_out_before_showing(name, src):
    """The bug verbatim: `focusin` -> `show(t)` with nothing in between."""
    src = _require(name, src)
    body = _handler_body(_lens_region(src), "focusin")
    assert "nestedCtrl" in body, (
        f"{name}: the lens's focusin handler does not consult the nested-control "
        "carve-out. Tapping a button/link inside a [data-tip-en] wrapper will open "
        "the sheet mid-tap and the scrim will eat the click."
    )
    guard = body.index("nestedCtrl")
    show = body.index("show(t)")
    assert guard < show, f"{name}: carve-out must be checked BEFORE show(t), not after"


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_the_scrim_gate_matches_the_condition_show_mounts_a_scrim_under(name, src):
    """show() mounts .lens-scrim iff isSheet(); the focusin gate must track that.

    If show() ever starts mounting the scrim on another condition, this pins the
    coupling so the un-fix is loud rather than silent.
    """
    src = _require(name, src)
    region = _lens_region(src)
    body = _handler_body(region, "focusin")
    assert "isSheet()" in body, f"{name}: focusin gate must be tied to isSheet()"
    show_fn = region[region.index("function show(t)"):]
    show_fn = show_fn[: show_fn.index("function hide()")]
    scrim_open = show_fn.index("scrim.classList.add('open')")
    assert "if (isSheet())" in show_fn[:scrim_open], (
        f"{name}: show() no longer mounts the scrim under isSheet() — the focusin "
        "gate in this file is now guarding the wrong condition"
    )


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_click_and_focusin_share_one_carve_out_definition(name, src):
    """Two copies of this predicate WILL drift; the click copy already outlived a
    focusin path that never had it."""
    src = _require(name, src)
    region = _lens_region(src)
    assert region.count("function nestedCtrl(") == 1, (
        f"{name}: nestedCtrl must be defined exactly once and shared"
    )
    for event in ("click", "focusin"):
        assert "nestedCtrl" in _handler_body(region, event), (
            f"{name}: the lens {event} handler must use the shared nestedCtrl predicate"
        )


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_carve_out_covers_every_focusable_control_kind(name, src):
    """A kind missing from the selector is a kind whose tap is still stolen."""
    src = _require(name, src)
    region = _lens_region(src)
    m = re.search(r"var CTRL_SEL = '([^']+)';", region)
    assert m, f"{name}: CTRL_SEL not found in the lens region"
    sel = m.group(1)
    missing = [k for k in FOCUSABLE if k not in sel]
    assert not missing, f"{name}: carve-out selector misses {missing}"


def test_the_toggle_this_healed_still_carries_its_tooltip():
    """#us-st-view-toggle keeps data-tip-*: the fix makes the markup safe, so the
    tooltip does not have to be sacrificed to make the button tappable."""
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    m = re.search(r"<span[^>]*id=\"us-st-view-toggle\"[^>]*>", dash)
    assert m, "#us-st-view-toggle not found in dashboard.html.j2"
    assert "data-tip-en=" in m.group(0), (
        "the tooltip was removed instead of relying on the lens carve-out — if that "
        "was deliberate, delete this test and say why in the PR"
    )
