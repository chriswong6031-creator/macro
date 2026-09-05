"""tests/test_lens_nested_control_taps.py — shared theme.js interaction boundaries.

The original boundary in this suite pins the lens rule that a tooltip wrapper must
never steal a nested control's tap.  It also owns narrow interaction contracts that
live in the same shared ``templates/theme.js`` / emitted ``site/theme.js`` pair,
including Intelligence Hub ticker labels entering the canonical Terminal route.

WHY THIS SUITE IS BROWSER-FREE. The CI packs install a minimal dependency set, not
``requirements.txt`` — a ``pytest.importorskip("playwright")`` here would SKIP in CI
and report green while proving nothing.  Browser measurements live in PR evidence;
what is mechanically checkable is asserted against the shipped source.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_JS = ROOT / "templates" / "theme.js"
SITE_JS = ROOT / "site" / "theme.js"
HUB_HTML = ROOT / "site" / "intelligence_hub.html"

# The focusable set the lens carve-out must cover. A control the selector misses is
# a control whose tap the lens can still steal.
FOCUSABLE = ("button", "a", "input", "select", "textarea", "label", '[role="button"]')


def _lens_region(src: str) -> str:
    """The lens IIFE, from its SEL definition to the end of its keydown binding."""
    start = src.index("var SEL = '[data-tip-en], .lens-q, .lens-term';")
    end = src.index("if (e.key === 'Escape' && isOpen()) hide();", start)
    return src[start:end]


def _hub_terminal_region(src: str) -> str:
    """The Hub ticker-promotion helper, excluding the canonical router around it."""
    start = src.index("function initHubTerminalTickerLinks()")
    end = src.index("initHubTerminalTickerLinks();", start)
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
    """show() mounts .lens-scrim iff isSheet(); the focusin gate must track that."""
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


# ---------------------------------------------------------------------------
# Phantom-click self-dismissal: the tap whose focusin opened the tip must not
# be read as "tap elsewhere to dismiss" by its own trailing click.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_focusin_show_stamps_the_gesture_it_opened_under(name, src):
    """The bug verbatim: tapping a focusable trigger fires focusin -> show(t),
    sheet mode mounts the full-viewport scrim MID-TAP, the browser retargets the
    tap's own trailing click to <body>, and the click handler's outside-closes
    branch hid the tip inside the very tap that opened it. The focusin path must
    stamp the pointer gesture (after the nested-control carve-out, before show)
    so the click handler can tell that tap's own artifact from a dismissal."""
    src = _require(name, src)
    body = _handler_body(_lens_region(src), "focusin")
    assert "focusShowSeq = gestureSeq" in body, (
        f"{name}: focusin no longer stamps the gesture it opened under — the tap "
        "that opens the sheet will dismiss it via its own retargeted click"
    )
    carve = body.index("nestedCtrl")
    stamp = body.index("focusShowSeq = gestureSeq")
    show = body.index("show(t)")
    assert carve < stamp < show, (
        f"{name}: the stamp must sit after the nested-control carve-out (a "
        "carved-out tap never shows, so it must not stamp) and before show(t)"
    )


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_every_pointer_gesture_advances_the_sequence(name, src):
    """A real dismissal tap always brings its own pointerdown; that is the only
    thing that distinguishes it from the opening tap's trailing click. On touch,
    focusin lands AFTER pointerup (compat mouse events follow the pointer
    sequence), so an is-a-pointer-down flag cannot gate this — only a counter."""
    src = _require(name, src)
    region = _lens_region(src)
    assert re.search(
        r"addEventListener\('pointerdown',\s*function\s*\(\)\s*\{\s*gestureSeq\+\+;?\s*\}", region
    ), f"{name}: no pointerdown listener advancing gestureSeq in the lens region"


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_gesture_guard_keys_on_pointer_reality_not_timing(name, src):
    """The guard must (a) exclude keyboard activation — Enter on a <button>
    trigger emits click with detail === 0 and must keep toggling — and (b) match
    the exact gesture, never a time window."""
    src = _require(name, src)
    region = _lens_region(src)
    assert region.count("function gestureOpenedTip(") == 1, (
        f"{name}: gestureOpenedTip must be defined exactly once and shared"
    )
    m = re.search(r"function gestureOpenedTip\(e\)\s*\{(.*?)\n  \}", region, re.S)
    assert m, f"{name}: gestureOpenedTip body not found"
    g = m.group(1)
    assert "e.detail !== 0" in g, (
        f"{name}: the guard must exempt keyboard clicks (detail === 0) or Enter "
        "can never close a focus-opened tip"
    )
    assert "focusShowSeq === gestureSeq" in g, (
        f"{name}: the guard must compare gesture SEQUENCE, not wall-clock timing"
    )
    assert "isOpen()" in g and "focusShowEl" in g, (
        f"{name}: the guard must require the stamped trigger to still own an open tip"
    )


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_click_consults_the_gesture_guard_on_every_self_dismiss_path(name, src):
    """Three paths could eat the opening tap: the retargeted-to-body branch
    (sheet scrim), the touch toggle branch (non-sheet touch, click lands on the
    chip), and the desktop pin-toggle (focus arrives at mousedown). Each must
    consult the guard before hiding."""
    src = _require(name, src)
    body = _handler_body(_lens_region(src), "click")
    assert body.count("gestureOpenedTip(e)") >= 3, (
        f"{name}: expected the gesture guard on all three self-dismiss paths "
        "(body-retarget, touch toggle, desktop pin-toggle); found "
        f"{body.count('gestureOpenedTip(e)')}"
    )
    no_trigger = body[: body.index("nestedCtrl")]
    assert "gestureOpenedTip(e)" in no_trigger, (
        f"{name}: the no-trigger (retargeted click) branch lost its guard"
    )
    assert no_trigger.index("gestureOpenedTip(e)") < no_trigger.index("hide()"), (
        f"{name}: the retargeted-click guard must run BEFORE hide()"
    )


def test_the_toggle_this_healed_still_carries_its_tooltip():
    """#us-st-view-toggle keeps data-tip-*: the fix makes the markup safe."""
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    m = re.search(r"<span[^>]*id=\"us-st-view-toggle\"[^>]*>", dash)
    assert m, "#us-st-view-toggle not found in dashboard.html.j2"
    assert "data-tip-en=" in m.group(0), (
        "the tooltip was removed instead of relying on the lens carve-out — if that "
        "was deliberate, delete this test and say why in the PR"
    )


# ---------------------------------------------------------------------------
# Intelligence Hub ticker -> existing Terminal overlay boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_intelligence_hub_promotes_inert_tickers_to_canonical_analyzer_links(name, src):
    """Hub `.tk` spans must enter the already-existing terminalTarget() route."""
    src = _require(name, src)
    region = _hub_terminal_region(src)

    assert "classList.contains('page-hub')" in region, (
        f"{name}: Hub ticker promotion must be scoped to body.page-hub"
    )
    assert "querySelectorAll('.tk')" in region
    assert "mm-terminal-ticker-link" in region
    assert "document.createElement('a')" in region
    assert "stock.html#" in region
    assert "encodeURIComponent(ticker)" in region


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_intelligence_hub_promotion_skips_existing_interactive_controls(name, src):
    """Never nest a new ticker anchor inside an existing link/button/control."""
    src = _require(name, src)
    region = _hub_terminal_region(src)

    assert 'a,button,input,select,textarea,[role="button"],[role="link"]' in region
    assert ".closest(interactive)" in region


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_intelligence_hub_promotion_accepts_real_symbol_punctuation_only(name, src):
    """BRK.B is valid; arbitrary prose must never become a stock route."""
    src = _require(name, src)
    region = _hub_terminal_region(src)

    assert "/^[A-Z0-9][A-Z0-9.-]{0,15}$/" in region


def test_current_hub_fixture_contains_a_dot_symbol_regression_case():
    hub = HUB_HTML.read_text(encoding="utf-8")
    assert '<span class="tk">BRK.B</span>' in hub


@pytest.mark.parametrize("name,src", SOURCES, ids=SOURCE_IDS)
def test_hub_reuses_the_single_existing_terminal_click_controller(name, src):
    """Do not add a Hub iframe/modal/controller parallel to openTerminal()."""
    src = _require(name, src)
    region = _hub_terminal_region(src)

    assert "iframe" not in region.lower()
    assert "MDXTerminalOverlay" not in region
    assert "openTerminal(" not in region
    assert src.count("openTerminal(target.ticker, a, target.url)") == 1
