"""China SI Workspace shell invariants — sibling of tests/test_si_workspace_shell.py.

sector_central_china.html.j2 and templates/si_workspace_china.js are a deliberate
SECOND copy of the US workspace, not a shared module: the two pages differ in view
count (China has no Money & Breadth organ), asset manifest, anchor table and read
composers, and the US router's tables are pinned line-by-line next door. Two small
files with a guard each beats one file with four conditionals — but a fork with no
guard drifts, so this file pins the China half.

What it defends, and why each pin exists rather than being obvious:

* **Router table.** The organs kept their section ids specifically so the router can
  reach them. A legacy id dropped from LEGACY_ANCHORS does not 404 — the deep link
  silently lands on Overview, a failure with no symptom except a user who never finds
  that panel again. Both halves are checked: the row exists AND the element it names
  is really inside the view it routes to.
* **Lazy mounting.** sector_cycles.js and subsector_rotation.js size themselves from a
  container's clientWidth. Loaded eagerly they measure 0 inside a display:none view and
  bake a blank chart for the whole session, so each must be injected by the router
  after its view is on screen — and must NOT also be loaded by a plain <script src>.
* **The board's cycle dependency.** The Overview conviction cards draw mini
  cycle-position sparklines from window.SECTOR_CYCLES, so '@cycles' has to be on the
  overview lazy list too. Drop it and 31 cards ship with an empty 66px slot each until
  the reader happens to open The Map.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"
PAGE = TPL / "sector_central_china.html.j2"
ROUTER = TPL / "si_workspace_china.js"

VIEWS = ["overview", "map", "moving", "explore"]


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _router() -> str:
    return ROUTER.read_text(encoding="utf-8")


def _code(js: str) -> str:
    """The router with comments stripped.

    Every code-SHAPE assertion below must run against this, not the raw file: the
    router documents its own traps in prose ("requestAnimationFrame never fires while
    the tab is hidden…"), so a raw-text scan for a banned construct matches the warning
    against it and reports a defect that is not there.
    """
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", js)


def _view_body(src: str, view: str) -> str:
    parts = re.split(r'<section class="si-view[^"]*" data-view="([a-z]+)"', src)
    names, bodies = parts[1::2], parts[2::2]
    assert view in names, f"no si-view for {view!r} (found {names})"
    return bodies[names.index(view)]


# ────────────────────────────────────────────────────────────── sidebar + views

def test_sidebar_present_with_four_view_buttons() -> None:
    s = _page()
    assert '<nav class="si-side" aria-label="China Sector Intelligence views">' in s, \
        "the persistent rail is gone or lost its aria-label"
    btns = re.findall(r'class="si-view-btn[^"]*" data-view="([a-z]+)" href="#([a-z]+)"', s)
    assert [b[0] for b in btns] == VIEWS, f"sidebar buttons/order wrong: {btns}"
    assert all(v == h for v, h in btns), "each button's href must be its own view hash"
    # the active button announces itself to assistive tech
    assert 'aria-current="page"' in s


def test_four_views_in_partition_order() -> None:
    s = _page()
    assert re.findall(r'<section class="si-view[^"]*" data-view="([a-z]+)"', s) == VIEWS
    assert s.count("{# /si-view") == 4, "a view wrapper is unclosed"
    # exactly one view ships pre-activated, so the correct panel is visible before the
    # router runs (no flash, and no blank page if the script fails to load)
    assert s.count('<section class="si-view on"') == 1
    assert '<section class="si-view on" data-view="overview">' in s


def test_v1_anchor_rail_is_retired() -> None:
    s = _page()
    assert 'id="si-rail"' not in s, "the V1 sticky anchor rail came back"
    assert 'class="scc-rail"' not in s
    # …but the funnel exit it carried must survive in the rail
    assert 'href="subsectors_china.html"' in s.split("</nav>", 1)[0], \
        "the stock entry funnel exit was dropped with the old rail"


def test_shell_grid_and_stage() -> None:
    s = _page()
    assert 'class="si-shell"' in s and 'class="si-stage"' in s
    assert "grid-template-columns:var(--si-rail-w, 200px)" in s, \
        "the shell grid and the --si-rail-w custom property are the shell contract"


def test_sticky_rail_containing_block_reaches_the_page_bottom() -> None:
    """The sidebar is PERSISTENT, and the way it measurably stops being persistent is
    slack below the shell: the rail is position:sticky inside .si-shell at a full 100vh,
    so every pixel left under the shell is a pixel the rail gets shoved up by at maximum
    scroll — clipping its top buttons off screen exactly where a reader is deepest in a
    view and most likely to switch. Two things fix it and both must hold: the footer
    lives inside the stage, and the shell cancels body's bottom padding."""
    s = _page()
    tail = s.split("{# /si-view explore #}", 1)[1]
    assert tail.index("<footer>") < tail.index("{# /si-stage #}"), \
        "the page footer escaped the stage — the sticky rail loses its bottom slack"
    assert "margin-bottom:-18px" in s, \
        "shell must cancel body's bottom padding or the rail unpins at max scroll"
    body_pad = re.search(r"body \{ background:var\(--bg\).*?padding:(\d+)px", s, re.S)
    assert body_pad and body_pad.group(1) == "18", (
        "body padding changed — the shell's negative bottom margin must match it "
        f"(found {body_pad.group(1) if body_pad else '?'}px)"
    )


def test_mobile_switcher_is_not_a_hamburger() -> None:
    """Under 768px the rail becomes a segmented switcher, never a menu that hides the
    product."""
    s = _page()
    mob = s.split("@media (max-width:767px)", 1)
    assert len(mob) == 2, "no <768px breakpoint — the mobile switcher is missing"
    block = mob[1][:900]
    assert "flex-direction:row" in block, "mobile rail must lay out as a tab row"
    assert "border-bottom-color:var(--link)" in block, \
        "on mobile the .on accent moves to border-bottom"
    assert "hamburger" not in block


def test_board_universe_toggle_survives_on_mobile() -> None:
    """It used to hide under 880px as "redundant with the page-level one". With the
    board in Overview and the cycle map's toggle in The Map they are no longer the same
    control, and hiding this one left a phone with no route to the 22 thematic
    baskets at all."""
    s = _page()
    assert ".scc-tabs.scc-tabs-board { display: none; }" not in s


# ───────────────────────────────────────────────────────── organ view membership

VIEW_ORGANS = {
    "overview": ('id="theme-context-hero"', 'id="regime"', 'id="actnow-section"',
                 'id="sc-board"', 'id="board"', 'id="grader"'),
    "map": ('id="si-map"', 'id="sc-cyclemap"', 'id="sc-tabs"', 'id="sc-desk-table"'),
    "moving": ('id="si-movement"', 'id="rc-events-cn"', 'id="rotation-app"'),
    "explore": ('id="si-explore"', 'id="table-section"', 'id="chart-section"',
                'id="categories"', 'id="entry-radar"', 'id="reversal-sleeve-card"',
                "_forming_narratives.html.j2", "_baskets_desk.html.j2"),
}


@pytest.mark.parametrize("view,organs", sorted(VIEW_ORGANS.items()))
def test_organ_lives_in_its_view(view: str, organs: tuple) -> None:
    body = _view_body(_page(), view)
    for organ in organs:
        assert organ in body, f"{organ} is not inside the {view} view"


# ─────────────────────────────────────────────────────────── LEGACY_ANCHORS table

# Every one of these is a live inbound deep link: the two redirect stubs
# (baskets_china.html → #si-explore, subsector_rotation_china.html → #si-movement),
# chat citations, dashboard cards, and the 22 basket detail back-links.
LEGACY_ANCHORS = {
    "actnow-section": "overview",
    "sc-board": "overview",
    "board": "overview",
    "regime": "overview",
    "grader": "overview",
    "si-map": "map",
    "sc-cyclemap": "map",
    "sc-desk-table": "map",
    "si-movement": "moving",
    "rc-events-cn": "moving",
    "rotation-app": "moving",
    "si-explore": "explore",
    "table-section": "explore",
    "chart-section": "explore",
    "categories": "explore",
    "entry-radar": "explore",
    "forming-narratives": "explore",
    "reversal-sleeve-card": "explore",
}


@pytest.mark.parametrize("anchor,view", sorted(LEGACY_ANCHORS.items()))
def test_legacy_anchor_is_routed(anchor: str, view: str) -> None:
    row = "'%s':['%s'," % (anchor, view)
    assert row in _router(), f"LEGACY_ANCHORS lost {anchor!r} → {view!r}"


@pytest.mark.parametrize("anchor,view", sorted(LEGACY_ANCHORS.items()))
def test_legacy_anchor_target_exists_in_that_view(anchor: str, view: str) -> None:
    """The other half of the contract, and the half a router-only pin cannot see:
    routing to a view whose scroll target is not there lands the user on the right page
    and shows them nothing."""
    src = _page()
    if anchor == "forming-narratives":     # lives inside the included partial
        assert "_forming_narratives.html.j2" in _view_body(src, view)
        assert 'id="forming-narratives"' in (TPL / "_forming_narratives.html.j2").read_text(
            encoding="utf-8")
        return
    assert 'id="%s"' % anchor in _view_body(src, view), \
        f"#{anchor} routes to {view} but no element with that id is in that view"


@pytest.mark.parametrize("stub,anchor", [
    ("baskets_china.html.j2", "si-explore"),
    ("subsector_rotation_china.html.j2", "si-movement"),
])
def test_redirect_stub_anchor_is_in_the_router_table(stub: str, anchor: str) -> None:
    """The stubs forward to a section anchor, not a view hash. If the router stopped
    resolving it the forward would land on Overview and the stub would look healthy."""
    src = (TPL / stub).read_text(encoding="utf-8")
    assert f"sector_central_china.html#{anchor}" in src, f"{stub} retargeted"
    assert "'%s':[" % anchor in _router(), \
        f"{stub} forwards #{anchor} but the router does not resolve it"


def test_basket_and_theme_hashes_are_left_to_their_own_resolvers() -> None:
    """openBasket()/openTheme() expand a row inside Explore. If the router rewrote
    those hashes first (unknown → #overview via replaceState) the deep link would be
    eaten before the resolver ever read it — and the 22 basket detail pages all link
    back with #b-<id>."""
    code = _code(_router())
    assert "h.indexOf('b-')===0" in code, "router does not exempt #b- hashes"
    assert "h.indexOf('theme-')===0" in code, "router does not exempt #theme- hashes"
    idx_b = code.index("h.indexOf('b-')===0")
    idx_theme = code.index("h.indexOf('theme-')===0")
    idx_replace = code.index("history.replaceState(null,'','#overview')")
    assert idx_b < idx_replace and idx_theme < idx_replace, \
        "both deep-link guards must run before any hash rewrite"


def test_unknown_hash_falls_back_to_overview() -> None:
    assert "activate('overview',null);" in _router()


# ───────────────────────────────────────────────────────────────── lazy mounting

@pytest.mark.parametrize("asset,view", [("subsector_rotation.js", "moving")])
def test_heavy_organ_is_lazy_not_eager(asset: str, view: str) -> None:
    page, router = _page(), _router()
    assert '<script src="%s"></script>' % asset not in page, \
        f"{asset} is still loaded eagerly — it would mount inside a display:none view"
    lazy = router.split("var LAZY={", 1)[1].split("};", 1)[0]
    assert re.search(r"%s:\[[^\]]*'%s'" % (view, re.escape(asset)), lazy), \
        f"{asset} is not assigned to the {view} view"


def test_cycle_map_trio_is_router_mounted_not_page_injected() -> None:
    page, router = _page(), _router()
    assert "'@cycles'" in router and "function loadCycles()" in router
    for f in ("sector_cycles_china_data.js", "mm_charts.js", "sector_cycles.js"):
        assert f in router, f"{f} missing from the router's cycle loader"
        assert '<script src="%s">' % f not in page, f"{f} is injected by the page again"
    assert "var files=['sector_cycles_china_data.js'" not in page, \
        "the page's own cycle-trio injector came back — it would double-load the map"
    assert "sc:cycles-data" in router, \
        "the board's mini sparklines listen for sc:cycles-data; the router must fire it"


def test_cycles_mount_on_overview_too() -> None:
    """The 31 Overview conviction cards each draw a mini cycle-position sparkline from
    window.SECTOR_CYCLES. Without '@cycles' on overview they ship an empty reserved slot
    until the reader happens to open The Map."""
    lazy = _router().split("var LAZY={", 1)[1].split("};", 1)[0]
    assert re.search(r"overview:\[[^\]]*'@cycles'", lazy), \
        "overview does not mount the cycle data — the board's sparklines would stay empty"
    assert re.search(r"map:\[[^\]]*'@cycles'", lazy)


def test_lazy_assets_keep_their_version_stamp() -> None:
    """Injected script names bypass the optimizer's src rewriting, so each lazy asset
    needs a head link the optimizer DOES stamp and vUrl() can read back — otherwise it
    loads unversioned: a second cache key for identical bytes."""
    page, router = _page(), _router()
    assert "function vUrl(name)" in router
    for asset in ("subsector_rotation.js", "sector_cycles_china_data.js",
                  "mm_charts.js", "sector_cycles.js"):
        assert '<link rel="prefetch" href="%s" as="script">' % asset in page, \
            f"{asset} has no stamped head link — it would load unversioned"


def test_sr_cfg_stays_eager() -> None:
    """subsector_rotation.js reads window.SR_CFG the moment it is injected; the config
    is a handful of bytes and must already be on the page when that happens."""
    page = _page()
    assert "window.SR_CFG={json:'marketdata/subsector_rotation_china.json'" in page
    assert page.index("window.SR_CFG=") < page.index('<script src="si_workspace_china.js">')


def test_mount_happens_after_the_view_is_visible() -> None:
    """The ordering IS the fix: organs that size themselves from clientWidth measure 0
    inside a display:none section and bake a blank panel for the session."""
    act = _router().split("function activate(", 1)[1].split("\nfunction ", 1)[0]
    assert act.index("classList.toggle('on'") < act.index("loadAssets(view)"), \
        "assets must load AFTER the view is switched on"
    assert "void sec.offsetHeight" in act, \
        "layout must be flushed before mounting, or clientWidth is still stale"


def test_mounting_does_not_wait_for_a_frame() -> None:
    """requestAnimationFrame never fires while the tab is hidden. A rAF-gated version
    activates the view, sets mounted[view]=true, and then never loads one organ — a
    permanently blank panel, no error, and the mounted flag means revisiting does not
    retry. A background tab or a restored session hits it."""
    code = _code(_router())
    assert "requestAnimationFrame" not in code, \
        "no part of the router may gate work behind rAF"


# ───────────────────────────────────────────────────────────── view reads + rail

def test_every_view_has_a_read_slot() -> None:
    s = _page()
    for v in VIEWS:
        assert 'id="si-read-%s" hidden' % v in s, \
            f"{v} has no read slot, or it does not ship hidden — an empty read is never " \
            "a rendered blank row"


def test_reads_recompose_when_the_payload_lands() -> None:
    """The basket payload arrives by fetch long after the router runs. Without the
    handshake the rail footer and the Moving/Explore reads would compose once against
    an empty window.BASKETS and stay that way — 'no data yet' baked into a page that
    has the data."""
    page, code = _page(), _code(_router())
    assert "document.addEventListener('csi:payload',reads)" in code, \
        "router does not listen for the payload-landed event"
    assert "new CustomEvent('csi:payload')" in page, \
        "the page never announces that the basket payload landed"


def test_rail_footer_carries_provenance() -> None:
    page, code = _page(), _code(_router())
    for slot in ('id="si-side-asof"', 'id="si-side-grade"'):
        assert slot in page, f"rail footer lost {slot}"
    assert "function paintFoot()" in code


def test_no_falsifier_language_on_the_router() -> None:
    """Operator ruling 2026-07-27: refutation vocabulary never ships front-facing."""
    code = _code(_router()).lower()
    for banned in ("falsifier", "refuted", "证伪", "thesis refuted"):
        assert banned not in code, f"front-facing copy uses banned term {banned!r}"
