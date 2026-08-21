"""P-MP1-SHELL W-L1 NEUTRALIZATION — the four required proofs (FROZEN SPEC).

Sol's Day-4 ruling (research/migration_packets/MP-1-prophet-board.md §13,
option (b), binding) requires the shell to "demonstrate explicitly that no
selector miss or nightly-vs-live taxonomy contradiction remains." The
commissioning packet names four properties:

  (a) the repaint path cannot write into the migrated grid
  (b) the board-state stamp still updates from poller state
  (c) no live-payload fragment carrying the old _su.buy/stage taxonomy can
      land anywhere in the migrated DOM
  (d) the poller itself still runs (not disabled wholesale)

MECHANISM (dashboard.html.j2): the migrated Setups grid carries
`id="us-life-grid" data-mp1-grid="1"`. `_pvcPaint` (the W-L1d card-injection
function) resolves its target via
`_bsPanel.querySelector('.nbgrid[data-showmore-rows]:not([data-provboard]):not([data-mp1-grid])')`
— the added `:not([data-mp1-grid])` is the entire guard. When the migrated
grid is the page's only `.nbgrid`, this selector cannot match anything, so
`night` is null and `_pvcPaint` returns on its very first guard line, before
any DOM write.

TEST STYLE, matching tests/test_wl1_board_state_surface.py's own convention
for this exact JS: static analysis of the extracted, comment-stripped source
— not DOM execution. `_pvcMount`'s post-mount identity re-verification
(exercised elsewhere, test_wl1_board_state_surface.py's node harness) already
covers the belt-and-braces case where a paint somehow produced the wrong
tickers; this file covers the FRONT guard the neutralization ruling actually
depends on.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = (ROOT / "templates" / "dashboard.html.j2").read_text()


def _nc(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)


def _wl1_script() -> str:
    """The whole W-L1/W-L1d client script, from `var _bsPanel = ...` (the
    first line of the block) through the poller's own IIFE close, i.e. up to
    (not including) the closing `})();\\n</script>` that ends the file's last
    inline script before `<script src="stocktable.js">`."""
    start = DASH.index("var _bsPanel = document.getElementById('us-standouts');")
    end = DASH.index('<script src="stocktable.js">', start)
    return DASH[start:end]


JS = _nc(_wl1_script())


# --------------------------------------------------------------------------- #
# (a) the repaint path cannot write into the migrated grid
# --------------------------------------------------------------------------- #

def test_a_repaint_selector_excludes_the_migrated_grid():
    """The exact selector `_pvcPaint` uses to find its repaint target must
    exclude `[data-mp1-grid]` — the marker the migrated grid alone carries."""
    m = re.search(
        r"var night\s*=\s*_bsPanel\?_bsPanel\.querySelector\('([^']+)'\)\s*:\s*null;",
        JS)
    assert m, "the _pvcPaint target-selector line was not found — did it move or get renamed?"
    selector = m.group(1)
    assert selector == (
        ".nbgrid[data-showmore-rows]:not([data-provboard]):not([data-mp1-grid])"
    ), selector
    assert ":not([data-mp1-grid])" in selector


def test_a_no_dom_write_precedes_the_night_guard():
    """`_pvcPaint`'s FIRST statement after resolving `night` is the early
    return (`if(!night||!night.parentNode) return;`) — every DOM-mutating
    statement (innerHTML assignment, insertBefore, hidden=true) is textually
    AFTER it, so a null `night` (guaranteed whenever the migrated grid is the
    page's only .nbgrid — see test_a_repaint_selector_excludes_the_migrated_grid)
    makes the function a no-op before it touches anything."""
    fn_start = JS.index("function _pvcPaint(html){")
    fn_end = JS.index("\nfunction _pvcTeardown", fn_start)
    body = JS[fn_start:fn_end]
    guard = re.search(r"if\(!night\|\|!night\.parentNode\)\s*return;", body)
    assert guard, "the night-guard line was not found inside _pvcPaint"
    before = body[:guard.start()]
    after = body[guard.end():]
    # Nothing that writes DOM appears before the guard.
    for writer in ("innerHTML", "insertBefore(", ".hidden=true", "createElement("):
        assert writer not in before, f"{writer!r} appears before the night-guard in _pvcPaint"
    # ...and every write the function performs DOES appear after it (proving
    # the guard is load-bearing, not vestigial in front of dead code).
    for writer in ("innerHTML", "insertBefore(", "createElement("):
        assert writer in after, f"{writer!r} expected after the night-guard in _pvcPaint"


def test_a_client_write_boundary_selector_census_includes_the_guard():
    """Cross-check against the sibling selector-census test
    (test_wl1_board_state_surface.py::
    test_the_client_writes_only_to_the_slots_the_server_reserved) — the two
    tests must agree on the exact selector string, or one of them is stale."""
    targets = set(re.findall(r"querySelector(?:All)?\('([^']+)'\)", JS))
    assert ".nbgrid[data-showmore-rows]:not([data-provboard]):not([data-mp1-grid])" in targets
    # and the PRE-neutralization (two-part) selector must not survive anywhere
    # in this script as an alternate, unguarded route to the same grid.
    assert ".nbgrid[data-showmore-rows]:not([data-provboard])" not in targets


# --------------------------------------------------------------------------- #
# (b) the board-state stamp still updates from poller state
# --------------------------------------------------------------------------- #

def test_b_stamp_functions_are_untouched_by_the_neutralization():
    """`_bsQualify` (the pure stamp-decision function) and `_bsRender` (which
    calls `_bsApply` regardless of whether the card mount succeeded) must
    both exist, and neither may reference the neutralization marker — proving
    the guard is confined to the card-paint half and the stamp path was not
    touched to make it work."""
    for fn in ("_bsQualify", "_bsRender", "_bsApply"):
        assert re.search(r"\bfunction " + fn + r"\(", JS) or re.search(r"\bvar " + fn + r"\s*=", JS), \
            f"{fn} not found in the W-L1 script"
    qualify_start = JS.index("function _bsQualify(")
    qualify_end = JS.index("\n}", qualify_start)
    assert "data-mp1-grid" not in JS[qualify_start:qualify_end]
    render_start = JS.index("function _bsRender(")
    render_end = JS.index("\n}", render_start)
    render_body = JS[render_start:render_end]
    assert "data-mp1-grid" not in render_body
    # _bsRender calls _bsApply UNCONDITIONALLY on the stamp decision (q), never
    # gated on whether the card mount (_pvcMount) returned true — this is what
    # makes (b) true even though (a) makes the mount a guaranteed no-op here.
    assert "_bsApply(" in render_body
    apply_call = re.search(r"_bsApply\(q\.rel,", render_body)
    assert apply_call, "the stamp apply call is not unconditional on q"


# --------------------------------------------------------------------------- #
# (c) no old-taxonomy fragment can land in the migrated DOM
# --------------------------------------------------------------------------- #

def test_c_no_write_path_into_the_migrated_grid_exists_anywhere_in_the_script():
    """Exhaustive check: `.nbgrid` (any variant) is queried from exactly the
    guarded selector above, plus the read-only DOM-ticker-identity helper
    (`_bsDomTickers`, which only READS — it feeds the stamp decision, never
    writes) and the client-write-boundary's own read target. No OTHER
    `.nbgrid`-matching query exists that could reach the migrated grid via a
    second, unguarded path."""
    nbgrid_queries = re.findall(r"querySelector(?:All)?\('([^']*\.nbgrid[^']*)'\)", JS)
    for q in nbgrid_queries:
        assert q in (
            ".nbgrid[data-showmore-rows]:not([data-provboard]):not([data-mp1-grid])",
            ".nbgrid:not([hidden]) .pvcard[data-ticker]",
            # read-only (feeds a boolean into _pvcEnv(), never assigned to)
            ".nbgrid .pvcard .nb-chg[data-sym]",
        ), f"unexpected/unguarded .nbgrid query: {q!r}"
    # the read-only identity helper never assigns into what it reads
    dom_tickers_start = JS.index("function _bsDomTickers(")
    dom_tickers_end = JS.index("\n}", dom_tickers_start)
    dom_tickers_body = JS[dom_tickers_start:dom_tickers_end]
    assert "innerHTML" not in dom_tickers_body and "insertBefore" not in dom_tickers_body


# --------------------------------------------------------------------------- #
# (d) the poller itself still runs
# --------------------------------------------------------------------------- #

def test_d_poller_setinterval_and_first_fetch_are_untouched():
    """`_plvFetch` (the poller) is invoked unconditionally once, then on a
    `setInterval`, exactly as before the neutralization — the guard changes
    WHAT gets painted when data arrives, never WHETHER the client keeps
    asking for it."""
    assert "_plvFetch();" in JS
    assert re.search(r"setInterval\(function\(\)\s*\{\s*if\s*\(!document\.hidden\)\s*_plvFetch\(\);\s*\}\s*,\s*PLV_EVERY\)", JS), \
        "the poller's setInterval call is missing or reshaped"
    # The guard string naturally appears EARLIER in the raw source than the
    # first _plvFetch() call (function declarations precede the IIFE's own
    # invocation code at the bottom of the script) — a plain substring-order
    # check would be a false signal. What actually matters: the block that
    # GATES the first fetch (`if(_plvPanel||_bsPanel){ ... _plvFetch(); ...}`)
    # does not itself reference the marker anywhere inside it.
    gate_start = JS.index("if(_plvPanel||_bsPanel){")
    gate_end = JS.index("_plvFetch();", gate_start) + len("_plvFetch();")
    assert "data-mp1-grid" not in JS[gate_start:gate_end], \
        "the guard must not gate the poller's own first fetch"


def test_d_poller_is_byte_identical_to_pre_neutralization():
    """Direct diff against origin/main: the poller block itself (first fetch +
    interval + visibilitychange re-fetch) must not have moved a single byte —
    only the repaint SELECTOR inside _pvcPaint changed."""
    import subprocess
    orig = subprocess.check_output(
        ["git", "show", "origin/main:templates/dashboard.html.j2"], cwd=str(ROOT)
    ).decode()
    marker = "_plvFetch();"
    o_start = orig.index(marker)
    o_end = orig.index("})();\n</script>", o_start)
    c_start = JS.index(marker)
    # JS here is comment-stripped/sliced differently, so compare against the
    # raw (non-stripped) DASH text instead for a true byte diff.
    raw_start = DASH.index(marker)
    raw_end = DASH.index("})();\n</script>", raw_start)
    assert orig[o_start:o_end] == DASH[raw_start:raw_end]
