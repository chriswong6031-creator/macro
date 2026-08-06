"""SI Workspace V2 shell invariants.

Charter: research/SI_WORKSPACE_V2_MASTERPLAN_BY_FABLE.md §0 gates, §1 shell
contract, §1b visual spec, §2b view partition + LEGACY_ANCHORS table.

What this file is defending, and why each pin exists rather than being obvious:

* **Comment parity.** An unclosed ``{#`` does not raise — it swallows everything
  up to the NEXT ``#}`` anywhere later in the file. This template carries 34 Jinja
  comments and a 72KB head; a swallow eats charset/title/theme.css out of the head
  while the body still renders perfectly. A body-only invariant sweep reads that as
  a pass, so parity is asserted directly AND the rendered head is checked in bytes.
* **Router table.** The organs kept their section ids specifically so the router can
  reach them. If a legacy id is dropped from LEGACY_ANCHORS the corresponding deep
  link silently lands on overview instead of 404-ing — a failure with no symptom
  except a user who never finds the panel again.
* **Var-native shell CSS.** Light mode is a first-class surface here (gate 7), and
  the way it silently stops being one is a literal colour picked to look right in
  dark and never re-checked in light.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"
PAGE = TPL / "sector_central.html.j2"
ROUTER = TPL / "si_workspace.js"

VIEWS = ["overview", "map", "moving", "money", "explore"]
# The rail and the section order carry a sixth: the subsector-confluence board brought in
# from the standalone subsectors page (US parity with the China desk's #confluence, #4637).
# It is deliberately NOT in VIEWS: it ships no si-view-read slot, because it renders its own
# hero and its own payload — its hero IS its read. Keeping the two lists apart is what makes
# "every view has a read slot" still mean something rather than quietly counting to six.
NAV_VIEWS = VIEWS + ["confluence"]


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _router() -> str:
    return ROUTER.read_text(encoding="utf-8")


def _code(js: str) -> str:
    """The router with comments stripped.

    Every code-SHAPE assertion below must run against this, not the raw file. The
    router documents its own traps in prose ("requestAnimationFrame never fires while
    the tab is hidden…"), so a raw-text scan for a banned construct matches the warning
    against it and reports a defect that is not there — or worse, passes a real one
    because the prose satisfied a positive assertion.
    """
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", js)


def _view_body(src: str, view: str) -> str:
    parts = re.split(r'<section class="si-view[^"]*" data-view="([a-z]+)"', src)
    names, bodies = parts[1::2], parts[2::2]
    assert view in names, f"no si-view for {view!r} (found {names})"
    return bodies[names.index(view)]


# ────────────────────────────────────────────────────────────── sidebar + views

def test_sidebar_present_with_six_view_buttons() -> None:
    s = _page()
    assert '<nav class="si-side"' in s, "the persistent rail is gone"
    assert '<nav class="si-side" aria-label="Sector Intelligence views">' in s, \
        "rail lost its aria-label"
    btns = re.findall(r'class="si-view-btn[^"]*" data-view="([a-z]+)" href="#([a-z]+)"', s)
    assert [b[0] for b in btns] == NAV_VIEWS, f"sidebar buttons/order wrong: {btns}"
    assert all(v == h for v, h in btns), "each button's href must be its own view hash"
    # the active button announces itself to assistive tech (§1b)
    assert 'aria-current="page"' in s


def test_six_views_in_partition_order() -> None:
    s = _page()
    assert re.findall(r'<section class="si-view[^"]*" data-view="([a-z]+)"', s) == NAV_VIEWS
    assert s.count("{# /si-view") == 6, "a view wrapper is unclosed"
    # exactly one view ships pre-activated, so the correct panel is visible before
    # the router runs (no flash, and no blank page if the script fails to load)
    assert s.count('<section class="si-view on"') == 1
    assert '<section class="si-view on" data-view="overview">' in s


def test_v1_anchor_rail_is_retired() -> None:
    s = _page()
    assert 'id="si-rail"' not in s, "the V1 sticky anchor rail came back"
    assert 'class="scc-rail"' not in s
    # …and the funnel it carried is a routed view now, not an exit link: the rail owns a
    # #confluence button and no longer points off-page at the standalone subsectors page.
    rail = s.split("</nav>", 1)[0]
    assert 'data-view="confluence" href="#confluence"' in rail
    assert 'href="subsectors.html"' not in rail, \
        "the old funnel exit LINK survived — it should be the routed #confluence view now"


def test_shell_grid_and_stage() -> None:
    s = _page()
    assert 'class="si-shell"' in s and 'class="si-stage"' in s
    assert "grid-template-columns:var(--si-rail-w, 200px)" in s, \
        "§1 pins the shell grid and the --si-rail-w custom property"


def test_sticky_rail_containing_block_reaches_the_page_bottom() -> None:
    """gate 1 says the sidebar is PERSISTENT, and it measurably was not.

    The rail is `position:sticky` inside .si-shell at a full 100vh. A sticky element
    can only stay pinned while its containing block has slack beneath it, so every
    pixel left below the shell is a pixel the rail gets shoved up by at maximum scroll.
    Measured in-browser: with the page <footer> outside the shell the rail rode up 103px
    at the bottom of every view and clipped its own top buttons off screen — the sidebar
    stopped being persistent exactly where a reader is deepest in a view and most likely
    to switch. Two things fix it and both must hold: the footer lives inside the stage,
    and the shell cancels body's bottom padding.
    """
    s = _page()
    tail = s.split('{# /si-view explore #}', 1)[1]
    assert tail.index("<footer>") < tail.index("{# /si-stage #}"), \
        "the page footer escaped the stage — the sticky rail loses its bottom slack"
    css = _shell_css(s)
    assert "margin-bottom:-18px" in css, \
        "shell must cancel body's bottom padding or the rail unpins at max scroll"
    body_pad = re.search(r"body\s*\{[^}]*padding:\s*(\d+)px", s)
    assert body_pad and body_pad.group(1) == "18", (
        "body padding changed — the shell's negative bottom margin must match it "
        f"(found {body_pad.group(1) if body_pad else '?'}px)"
    )


def test_mobile_switcher_is_not_a_hamburger() -> None:
    """gate 9: <768px the rail becomes a segmented switcher, never a menu that
    hides the product."""
    s = _page()
    mob = s.split("@media (max-width:767px)", 1)
    assert len(mob) == 2, "no <768px breakpoint — the mobile switcher is missing"
    block = mob[1][:900]
    assert "flex-direction:row" in block, "mobile rail must lay out as a tab row"
    assert "border-bottom-color:var(--link)" in block, \
        "§1b: on mobile the .on accent moves to border-bottom"
    for banned in ("hamburger", "display:none;}\n    .si-side"):
        assert banned not in block


# ───────────────────────────────────────────────────────── organ view membership

VIEW_ORGANS = {
    "overview": ('id="ftr-tape-strip"', 'id="regime"', 'id="actnow-section"', 'id="grader"'),
    "map": ('id="rotmap-section"', 'id="si-map"', 'id="sc-cyclemap"', 'id="board"'),
    "moving": ('id="si-movement"', 'id="rc-events-mount"', 'id="rotation-app"',
               'id="desk-watch-mount"'),
    "money": ('id="si-money"', 'id="internals-section"', 'id="heatmap-scorecard"',
              'id="scc-leadership"'),
    "explore": ('id="explore-section"', 'id="table-section"', 'id="chart-section"',
                'id="tm-mount"', "_forming_narratives.html.j2"),
}


@pytest.mark.parametrize("view,organs", sorted(VIEW_ORGANS.items()))
def test_organ_lives_in_its_view(view: str, organs: tuple) -> None:
    body = _view_body(_page(), view)
    for organ in organs:
        assert organ in body, f"{organ} is not inside the {view} view"


def test_time_machine_and_forming_moved_to_explore() -> None:
    """§2b relocates both out of movement. The half that actually breaks is the one
    left behind: a duplicate mount id would double-mount and the second would win."""
    s = _page()
    explore, moving = _view_body(s, "explore"), _view_body(s, "moving")
    assert 'id="tm-mount"' in explore and "_forming_narratives" in explore
    assert 'id="tm-mount"' not in moving, "time machine still mounted in movement"
    assert "_forming_narratives" not in moving, "forming panel still in movement"
    assert s.count('id="tm-mount"') == 1, "two time-machine mounts on the page"
    assert s.count('{% include "_forming_narratives.html.j2" %}') == 1


# ─────────────────────────────────────────────────────────── LEGACY_ANCHORS table

# §2b, verbatim. Every one of these is a live inbound deep link somewhere on the
# estate (redirect stubs, chat citations, dashboard cards, detail back-links).
LEGACY_ANCHORS = {
    "actnow-section": "overview",
    "regime": "overview",
    "grader": "overview",
    "si-map": "map",
    "rotmap-section": "map",
    "sc-cyclemap": "map",
    "board": "map",
    "si-movement": "moving",
    "rc-events-mount": "moving",
    "rotation-app": "moving",
    "si-money": "money",
    "internals-section": "money",
    "scc-leadership": "money",
    "explore-section": "explore",
    "table-section": "explore",
    "chart-section": "explore",
    "forming-narratives": "explore",
    "tm-mount": "explore",
}


@pytest.mark.parametrize("anchor,view", sorted(LEGACY_ANCHORS.items()))
def test_legacy_anchor_is_routed(anchor: str, view: str) -> None:
    src = _router()
    row = "'%s':['%s'," % (anchor, view)
    assert row in src, f"LEGACY_ANCHORS lost {anchor!r} → {view!r}"


@pytest.mark.parametrize("anchor,view", sorted(LEGACY_ANCHORS.items()))
def test_legacy_anchor_target_exists_in_that_view(anchor: str, view: str) -> None:
    """The other half of the contract, and the half a router-only pin cannot see:
    routing to a view whose scroll target is not there lands the user on the right
    page and shows them nothing."""
    src = _page()
    if anchor == "forming-narratives":     # lives inside the included partial
        body = _view_body(src, view)
        assert "_forming_narratives.html.j2" in body
        assert 'id="forming-narratives"' in (TPL / "_forming_narratives.html.j2").read_text(
            encoding="utf-8")
        return
    assert 'id="%s"' % anchor in _view_body(src, view), \
        f"#{anchor} routes to {view} but no element with that id is in that view"


def test_unknown_hash_falls_back_to_overview() -> None:
    src = _router()
    assert "activate('overview',null);" in src
    assert "// unknown → overview" in src or "unknown → overview" in src


def test_theme_hash_is_left_to_its_own_resolver() -> None:
    """resolveThemeHash() navigates away to the basket detail page. If the router
    rewrote that hash first (unknown → #overview via replaceState) the deep link
    would be eaten before the resolver ever read it — the exact defect
    test_theme_hash_deeplink.py was written for, one layer up."""
    src = _router()
    assert "h.indexOf('theme-')===0" in src, "router does not exempt #theme- hashes"
    idx_theme = src.index("h.indexOf('theme-')===0")
    idx_replace = src.index("history.replaceState(null,'','#overview')")
    assert idx_theme < idx_replace, "the #theme- guard must run before any hash rewrite"


def test_read_hash_opens_the_lane_trace() -> None:
    src = _router()
    assert "h.indexOf('read-')===0" in src
    assert "pendingTrace" in src, "the trace request must survive the async board render"


# ───────────────────────────────────────────────────────────────── lazy mounting

@pytest.mark.parametrize("asset,view", [
    ("subsector_rotation.js", "moving"),
    ("rotation_events.js", "moving"),
    ("desk_watch.js", "moving"),
    ("heatmap.js", "money"),
    ("time_machine.js", "explore"),
])
def test_heavy_organ_is_lazy_not_eager(asset: str, view: str) -> None:
    page, router = _page(), _router()
    assert '<script src="%s"></script>' % asset not in page, \
        f"{asset} is still loaded eagerly — it would mount inside a display:none view"
    assert asset in router, f"{asset} is not in the router's lazy table"
    lazy = router.split("var LAZY={", 1)[1].split("};", 1)[0]
    assert asset in lazy
    assert re.search(r"%s:\[[^\]]*'%s'" % (view, re.escape(asset)), lazy), \
        f"{asset} is not assigned to the {view} view"


def test_time_machine_declares_its_srr_dependency() -> None:
    """time_machine.js draws through window.SRR, exported by subsector_rotation.js.
    Reaching explore without passing through moving must still load it."""
    lazy = _router().split("var LAZY={", 1)[1].split("};", 1)[0]
    explore = re.search(r"explore:\[([^\]]*)\]", lazy).group(1)
    assert "subsector_rotation.js" in explore
    assert explore.index("subsector_rotation.js") < explore.index("time_machine.js"), \
        "SRR must load before the Time Machine that renders through it"


def test_lazy_assets_keep_their_version_stamp() -> None:
    """Injected script names bypass the optimizer's src rewriting, so each lazy
    asset needs a head link the optimizer DOES stamp and vUrl() can read back."""
    page, router = _page(), _router()
    assert "function vUrl(name)" in router
    for asset in ("subsector_rotation.js", "rotation_events.js", "desk_watch.js",
                  "time_machine.js", "heatmap.js"):
        assert '<link rel="prefetch" href="%s" as="script">' % asset in page, \
            f"{asset} has no stamped head link — it would load unversioned"


def test_cycle_map_trio_is_mounted_by_the_map_view() -> None:
    router = _router()
    assert "'@cycles'" in router and "function loadCycles()" in router
    for f in ("sector_cycles_data.js", "mm_charts.js", "sector_cycles.js"):
        assert f in router
    assert "map:['@cycles']" in router
    # the mini-cycle sparklines on #board listen for this; both live in the map view
    assert "sc:cycles-data" in router


def test_mount_happens_after_the_view_is_visible() -> None:
    """The ordering IS the fix: organs that size themselves from clientWidth measure
    0 inside a display:none section and bake a blank panel for the session."""
    router = _router()
    act = router.split("function activate(", 1)[1].split("\nfunction ", 1)[0]
    assert "classList.toggle('on'" in act
    assert act.index("classList.toggle('on'") < act.index("loadAssets(view)"), \
        "assets must load AFTER the view is switched on"
    assert "void sec.offsetHeight" in act, \
        "layout must be flushed before mounting, or clientWidth is still stale"


def test_mounting_does_not_wait_for_a_frame() -> None:
    """Caught in-browser: requestAnimationFrame never fires while the tab is hidden.
    The rAF-gated version activated the view, set mounted[view]=true, and then never
    loaded one organ — a permanently blank panel, no error, and the mounted flag means
    revisiting the view does not retry. A background tab or a restored session hits it.
    A forced reflow gives the same 'view is laid out first' guarantee unconditionally.
    """
    code = _code(_router())
    act = code.split("function activate(", 1)[1].split("\nfunction ", 1)[0]
    assert "requestAnimationFrame" not in act, \
        "view activation must not depend on a frame callback — hidden tabs never get one"
    assert "requestAnimationFrame" not in code, \
        "no part of the router may gate work behind rAF"


def test_map_read_uses_the_hoisted_quadrant_source() -> None:
    """The router is a separate script and cannot see anything declared inside
    __siInitPage. rvxData() is declared in there, so a bare `rvxData()` call from the
    router resolves to undefined, the catch swallows it, and the map's read silently
    stays hidden — indistinguishable from 'no data yet'. Both halves are pinned: the
    page must hoist it, and the router must read the hoisted name."""
    page, code = _page(), _code(_router())
    assert "window.__siRvxData = rvxData;" in page, "page no longer hoists rvxData"
    assert "window.__siRvxData()" in code, "router does not read the hoisted name"
    read_map = code.split("function readMap(", 1)[1].split("\nfunction ", 1)[0]
    assert not re.search(r"(?<![.\w])rvxData\s*\(", read_map), \
        "readMap calls bare rvxData() — that name does not exist in this scope"


# ───────────────────────────────────────────────────────────── view reads + chips

def test_every_view_has_a_read_slot() -> None:
    s = _page()
    assert s.count('class="si-view-read"') == 5
    assert 'id="si-read-confluence"' not in s, \
        "confluence must not have a read slot — its hero is its read"
    for v in VIEWS:
        assert 'id="si-read-%s"' % v in s, f"{v} has no view-read slot"
        assert 'id="si-read-%s" hidden' % v in s, \
            f"{v}'s read must ship hidden — an empty read is never a rendered blank row"


def test_composer_is_named_and_wired() -> None:
    page, router = _page(), _router()
    assert "window.__siViewReads=reads;" in router, "§1 names the composer __siViewReads"
    assert "window.__siViewReads(BASKETS)" in page, \
        "the composer is never handed the payload — every read would stay hidden"


def test_composer_rules_ship_beside_the_composer() -> None:
    """§1: 'Composition rules live beside the composer as comments.' They are copy
    laws — a future editor who cannot see them will write a slug into a glance line."""
    src = _router()
    rules = src.split("Composition rules", 1)
    assert len(rules) == 2, "composition rules comment is missing"
    block = rules[1][:1400]
    for law in ("no raw slugs", "18 words", "fail-soft", "display-tier"):
        assert law in block, f"composition rules no longer state: {law}"


def test_view_reads_carry_a_receipt() -> None:
    src = _router()
    assert "var RECEIPTS=" in src
    for v in VIEWS:
        assert "%s:[" % v in src.split("var RECEIPTS=", 1)[1].split("};", 1)[0], \
            f"{v} read has no ? receipt naming its inputs"
    assert 'class="si-vr-q"' in src and "data-tip-en=" in src


def test_reads_are_bilingual_and_fail_soft() -> None:
    src = _router()
    # each read returns [en, zh] or null; null hides the row rather than printing ""
    assert "if(!pair){ el.hidden=true;" in src, "an absent read must hide, not blank"
    for fn in ("readOverview", "readMap", "readMoving", "readMoney", "readExplore"):
        assert "function %s(" % fn in src, f"missing composer {fn}"
        body = src.split("function %s(" % fn, 1)[1].split("\nfunction ", 1)[0]
        assert "return null" in body or "if(!" in body, f"{fn} has no absent-input path"


def test_view_reads_use_no_banned_vocabulary() -> None:
    """Glance-tier copy law (docs/DESIGN_DOCTRINE.md): plain words only — no internal
    state names, no study names, no raw slugs in user-facing text.

    Scoped to the PROSE the composer emits, not to the code that reads the payload:
    `t.pulse_rank_delta_5d` is a field access and must stay legible in the source,
    while "pulse_rank_delta_5d" printed into a glance line is the actual defect. So
    the scan takes string literals containing a space — that is what copy looks like
    and what an identifier does not.
    """
    src = _router()
    reads = src.split("function readOverview(", 1)[1].split("function paint(", 1)[0]
    prose = [m.group(1) for m in re.finditer(r"'([^'\\\n]*\s[^'\\\n]*)'", reads)]
    assert len(prose) >= 10, f"only {len(prose)} prose strings found — scan is vacuous"
    joined = " ".join(prose).lower()
    for banned in ("rank_ic", "pulse_rank", "act_now", "z-score", "zscore", "quadrant",
                   "falsifier", "refut", "证伪", "validated", "theme_intel", "_5d",
                   "regime", "slug", "null"):
        assert banned not in joined, \
            f"banned vocabulary in a glance-tier read: {banned!r}\n{prose}"
    # every prose string must be bilingual-partnered: the composer never emits an
    # English-only line (each read returns [en, zh])
    assert any("一" <= ch <= "鿿" for ch in joined), "reads carry no ZH copy"


def test_what_changed_strip_is_capped_and_fail_soft() -> None:
    s = _page()
    assert 'class="si-changed"' in s, "the what-changed strip is missing from overview"
    assert 'class="si-changed"' in _view_body(s, "overview"), "strip escaped overview"
    assert "_wc[:3]" in s, "gate 6 caps the strip at three chips"
    # absent data renders nothing at all — not an empty labelled strip
    assert "{%- if _wc %}" in s, "the strip must not render when no chip qualifies"
    assert "theme_context.state_changes" in s, \
        "chips must diff payload-resident state, not invent novelty"
    assert 'class="tc-chip"' in s, "§1b: chip idiom is the existing tc-chip"


def test_rail_footer_carries_provenance() -> None:
    page, router = _page(), _router()
    for slot in ('id="si-side-asof"', 'id="si-side-grade"'):
        assert slot in page, f"rail footer lost {slot}"
    assert "function paintFoot()" in router
    assert "SECTOR_CENTRAL&&window.SECTOR_CENTRAL.grader" in router


# ───────────────────────────────────────────────────────────────── shell CSS law

def _shell_css(src: str) -> str:
    marker = "SI WORKSPACE V2 shell"
    assert marker in src, "shell CSS block is gone"
    return src.split(marker, 1)[1].split("</style>", 1)[0]


def test_shell_css_has_no_literal_colours() -> None:
    """gate 7 / §1b: the shell is var-native so light mode is designed, not inherited.
    A literal colour is how a surface silently becomes dark-first."""
    css = _shell_css(_page())
    for pat, label in ((r"#[0-9a-fA-F]{3,8}\b", "hex colour"),
                       (r"\brgba?\(", "rgb()"),
                       (r"\bhsla?\(", "hsl()")):
        hits = re.findall(pat, css)
        assert not hits, f"literal {label} in the shell CSS: {hits[:4]}"
    assert "var(--" in css and "color-mix(" in css


def test_shell_state_colours_match_the_pinned_spec() -> None:
    css = _shell_css(_page())
    assert "color-mix(in srgb, var(--link) 6%, transparent)" in css, "§1b hover mix"
    assert "color-mix(in srgb, var(--link) 11%, var(--panel))" in css, "§1b .on mix"
    assert "border-left-color:var(--link)" in css, "§1b .on accent"
    assert "border-right:1px solid var(--line)" in css


def test_view_switch_is_a_display_toggle() -> None:
    """gate 1/8: instant, no reload, no refetch, no spinner."""
    css = _shell_css(_page())
    assert ".si-view { display:none; }" in css
    assert ".si-view.on { display:block; }" in css
    assert "transition" not in css.split(".si-view {", 1)[1][:200], \
        "§1b motion: the view switch is instant"


# ───────────────────────────────────────────────────── template integrity (traps)

def test_jinja_comment_parity() -> None:
    """An unclosed {# swallows to the next #} — the head-swallow trap. It does not
    raise, and the body still looks right, so only a count catches it early."""
    s = _page()
    assert s.count("{#") == s.count("#}"), \
        f"{s.count('{#')} '{{#' vs {s.count('#}')} '#}}' — an unclosed Jinja comment"


def test_page_renders_with_an_intact_head() -> None:
    """The parity count above is necessary but not sufficient: a balanced pair can
    still be mis-nested. This renders the real template and reads the head bytes."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TPL)), autoescape=False)
    env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("sector_central.html.j2").render(basket_member_syms=["SPY"])

    assert "</head>" in html, "the head was swallowed by a comment"
    head = html.split("</head>", 1)[0]
    for needle in ("<meta charset=", "<title>", "theme.css"):
        assert needle in head, f"head lost {needle!r} — comment swallow"
    title = re.search(r"<title>(.*?)</title>", head, re.S)
    assert title and title.group(1).strip(), "empty <title>"
    # and the shell survived the render, not just the source
    assert 'class="si-shell"' in html and html.count('class="si-view-read"') == 5
    assert re.findall(r'<section class="si-view[^"]*" data-view="([a-z]+)"', html) == NAV_VIEWS


def test_no_i18n_macro_inside_an_html_attribute() -> None:
    """Caught on screen, not in a test: the rail shipped with
    ``aria-label="{{ t('Sector Intelligence views', '行业智慧视图') }}"`` and rendered as

        <nav class="si-side" aria-label="<span class="l-en">Sector Intelligence views…

    t() returns a dual <span class="l-en">/<span class="l-zh"> pair, so the FIRST inner
    class= closes the attribute and everything after it leaks into the page as visible
    text — the words "Sector Intelligence views\">" sat above the buttons. Jinja does not
    complain, the HTML still parses, and every structural pin passed. Only the rendered
    page shows it, so this test reads the rendered page.
    """
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TPL)), autoescape=False)
    # the REAL builder globals: t() emits the dual-span pair, which is the whole point
    env.globals.update(
        td=lambda en: en, tr=lambda en: en,
        t=lambda en, zh="": f'<span class="l-en">{en}</span><span class="l-zh">{zh or en}</span>',
    )
    html = env.get_template("sector_central.html.j2").render(basket_member_syms=["SPY"])

    for tag in re.findall(r"<[a-zA-Z][^>]*>", html):
        for val in re.findall(r'=\s*"([^"]*)"', tag):
            assert "<span" not in val, (
                f"an i18n macro was expanded inside an HTML attribute — the tag breaks "
                f"and the copy leaks as text:\n  {tag[:170]}"
            )
    # and the rail's own label survived as plain text
    nav = re.search(r"<nav class=\"si-side\"[^>]*>", html)
    assert nav and 'aria-label="Sector Intelligence views"' in nav.group(0), nav


def test_router_asset_is_paired_into_site() -> None:
    """Plain-copy page asset law: templates/<name> that ships as site/<name> must be
    byte-identical in the same PR, and the builder must copy it on every render."""
    assert ROUTER.exists()
    site_copy = ROOT / "site" / "si_workspace.js"
    assert site_copy.exists(), "site/si_workspace.js missing — the page would 404 it"
    assert site_copy.read_bytes() == ROUTER.read_bytes(), "template↔site copy drifted"
    builder = (ROOT / "scripts" / "build_sector_central.py").read_text(encoding="utf-8")
    tup = builder.split("for asset in (", 1)[1].split("):", 1)[0]
    assert '"si_workspace.js"' in tup, "builder does not copy the router asset"
    assert '<script src="si_workspace.js"></script>' in _page()
