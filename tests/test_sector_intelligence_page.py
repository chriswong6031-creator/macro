"""Sector Intelligence consolidation invariants (2026-08 merge of baskets +
subsector_rotation into sector_central.html).

Pins the merge's load-bearing properties so a later template edit cannot silently
undo them: the two redirect stubs, the merged page's section skeleton, the
payload externalization (no inline BASKETS embed), the live-quote member-symbol
registry, and the China contract (its templates untouched by the shared-JS edit).
Charter: research/SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md §0.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"


def _read(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


def _view_body(src: str, view: str) -> str:
    """The markup between `<section class="si-view" data-view="<view>">` and the next
    view's open tag (V2 workspace shell). Views are display-toggled siblings, so
    "inside view X" is a slice between two sibling opens, not a nesting question."""
    opens = re.split(r'<section class="si-view[^"]*" data-view="([a-z]+)"', src)
    # re.split with one group → [pre, name, body, name, body, ...]
    names, bodies = opens[1::2], opens[2::2]
    assert view in names, f"no si-view for {view!r} (found {names})"
    return bodies[names.index(view)]


# ---------------------------------------------------------------- stubs

@pytest.mark.parametrize("name,target", [
    ("baskets.html.j2", "sector_central.html#actnow-section"),
    ("subsector_rotation.html.j2", "sector_central.html#si-movement"),
])
def test_redirect_stub(name: str, target: str) -> None:
    s = _read(TPL / name)
    assert f'content="0;url={target}"' in s, "meta refresh missing/retargeted"
    assert 'name="robots" content="noindex,follow"' in s
    assert f'location.replace("{target}")' in s
    assert 'seo_path = "sector_central.html"' in s, "canonical must point at the merged page"
    # A stub must never regrow page content
    assert len(s) < 4000, f"{name} is {len(s)} chars — no longer a stub?"


@pytest.mark.parametrize("name,target", [
    ("baskets.html", "sector_central.html#actnow-section"),
    ("subsector_rotation.html", "sector_central.html#si-movement"),
])
def test_redirect_stub_rendered(name: str, target: str) -> None:
    """The RENDERED stubs must hold too — the template pin above cannot see this
    failure mode. A scope=all render that raced the #4237 merge (04946ac459d,
    2026-08-02: pre-merge checkout replayed over main with `pull --rebase -X
    theirs`) resurrected the old 1,379-line baskets body under the stub's head,
    shipping a chimera to direct visitors for a day.
    """
    s = _read(ROOT / "site" / name)
    assert f'content="0;url={target}"' in s, "meta refresh missing/retargeted"
    assert f'location.replace("{target}")' in s, "JS redirect fallback missing"
    assert '<body class="macro-desk' not in s, "absorbed page body regrew in the render"
    assert "macro-desk.css" not in s, "stub must not re-join the macro-desk surface"
    # Headroom over the ~4.1KB healthy render for future head-injected chrome
    # (shim/preload/stamps); the resurrected chimera weighed ~840KB.
    assert len(s) < 12000, f"site/{name} is {len(s)} chars — stub body regrew?"


# ---------------------------------------------------- merged template skeleton

def test_merged_template_sections() -> None:
    s = _read(TPL / "sector_central.html.j2")
    for anchor in ('id="actnow-section"', 'id="si-map"', 'id="si-movement"',
                   'id="si-money"', 'id="explore-section"', 'id="rotation-app"',
                   'id="sc-cyclemap"', 'id="board"', 'id="grader"',
                   'id="heatmap-scorecard"', 'id="scc-leadership"',
                   'id="table-section"', 'id="chart-section"'):
        assert anchor in s, f"merged page lost {anchor}"
    # legacy deep-link anchors survive
    assert 'id="rotmap-section"' in s
    # live-quote scraper contract (FTR W2a): member-symbol registry must ship
    assert 'ftr-member-sym-registry' in s
    assert "basket_member_syms" in s


# V2 workspace partition (SI_WORKSPACE_V2_MASTERPLAN_BY_FABLE §2b). The V1 pin above
# only proved these ids EXIST somewhere on the page — which stayed true even while an
# organ sat in the wrong view. Membership is the property the shell actually depends
# on: the router sends every legacy anchor to a specific view, so an organ in the wrong
# view means a deep link that scrolls to a hidden element and shows the user nothing.
VIEW_MEMBERSHIP = {
    # 'id="actnow"' was the OLD client-rendered lanes div; the SI-central transplant
    # (2026-08) replaced it with the shared server-rendered board include (#action-board
    # lives inside the include, invisible to raw-source scanning) — pin the include filename,
    # mirroring how the explore view pins "_forming_narratives.html.j2".
    "overview": ('id="ftr-tape-strip"', 'id="ftr-tape-band"', 'id="regime"',
                 'id="actnow-section"', '_us_act_now_board.html.j2', 'id="grader"'),
    "map": ('id="rotmap-section"', 'id="si-map"', 'id="rvx-rmap"', 'id="rvx-board"',
            'id="sc-cyclemap"', 'id="sc-chart"', 'id="board"'),
    "moving": ('id="si-movement"', 'id="rc-events-mount"', 'id="rotation-app"',
               'id="desk-watch-mount"'),
    "money": ('id="si-money"', 'id="internals-section"', 'id="sc-heatmap"',
              'id="heatmap-scorecard"', 'id="scc-leadership"'),
    "explore": ('id="explore-section"', 'id="table-section"', 'id="chart-section"',
                'id="btable"', 'id="chart"', 'id="tm-mount"',
                "_forming_narratives.html.j2", "ftr-member-sym-registry"),
}


@pytest.mark.parametrize("view,anchors", sorted(VIEW_MEMBERSHIP.items()))
def test_organs_sit_in_their_assigned_view(view: str, anchors: tuple) -> None:
    body = _view_body(_read(TPL / "sector_central.html.j2"), view)
    for a in anchors:
        assert a in body, f"{a} is not inside the {view} view"


def test_view_order_is_the_sidebar_order() -> None:
    """Five views, in the pinned order, each driven by a sidebar button of the same
    name. Order is load-bearing twice over: it is the reading order of the product
    (overview → map → moving → money → explore) and it is the tab order of the mobile
    switcher."""
    s = _read(TPL / "sector_central.html.j2")
    order = ["overview", "map", "moving", "money", "explore"]
    assert re.findall(r'<section class="si-view[^"]*" data-view="([a-z]+)"', s) == order
    assert re.findall(r'class="si-view-btn[^"]*" data-view="([a-z]+)"', s) == order
    # the V1 sticky anchor rail is retired — the sidebar replaced it
    assert 'id="si-rail"' not in s, "the V1 anchor rail came back"
    assert 'class="scc-rail"' not in s


def test_forming_narratives_mounted_at_end_of_explore() -> None:
    """The Forming Narratives panel ships on the US page (PR-A1).

    engine.narrative_emergence has emitted site/basketdata/narrative_emergence.json for
    US nightly all along, but the shared panel was mounted only on the non-US baskets
    pages — the US read was computed and never shown.

    RETARGETED by the V2 workspace (SI_WORKSPACE_V2_MASTERPLAN_BY_FABLE §2b): the panel
    and the Time Machine both moved out of MOVEMENT into EXPLORE, because both are reads
    you go looking for rather than heads-up context. The ordering law is unchanged — the
    Time Machine still precedes the forming panel, which is still the LAST read of its
    view — only the view it ends changed. Mount ids are preserved so #tm-mount and
    #forming-narratives keep resolving through the router.
    """
    s = _read(TPL / "sector_central.html.j2")
    assert '{% include "_forming_narratives.html.j2" %}' in s, "panel not mounted"
    explore = _view_body(s, "explore")
    assert '{% include "_forming_narratives.html.j2" %}' in explore, \
        "panel escaped the EXPLORE view"
    assert 'id="tm-mount"' in explore, "time machine escaped the EXPLORE view"
    assert explore.index('id="tm-mount"') < explore.index("_forming_narratives"), \
        "panel must come after the time machine — it is the last read in EXPLORE"
    # …and both must have LEFT movement: a copy left behind would double-mount and the
    # second mount would silently win.
    movement = _view_body(s, "moving")
    assert 'id="tm-mount"' not in movement, "time machine still mounted in MOVEMENT too"
    assert "_forming_narratives" not in movement, "forming panel still in MOVEMENT too"


def test_forming_narratives_asset_copied_by_builder() -> None:
    """The panel loads forming_narratives.js relative to the page, so the US builder
    must copy it into site/ like its sibling MOVEMENT donors."""
    s = _read(ROOT / "scripts" / "build_sector_central.py")
    assert '"forming_narratives.js"' in s, "asset missing from the copy tuple"
    # it must sit in the SAME tuple as the other MOVEMENT donors (one copy loop)
    tup = s.split('for asset in (', 1)[1].split("):", 1)[0]
    assert "forming_narratives.js" in tup, "asset added outside the asset-copy tuple"


def test_payload_externalized_not_embedded() -> None:
    s = _read(TPL / "sector_central.html.j2")
    assert "baskets_json|safe" not in s, "inline BASKETS embed came back"
    assert "chart_json|safe" not in s, "inline CHART embed came back"
    assert "theme_alerts_json|safe" not in s, "inline THEME_ALERTS embed came back"
    assert "basketdata/baskets.json" in s, "payload fetch missing"
    # bell + theme_alerts payload removed sitewide (#4232, re-applied on rebase)
    assert "theme_alerts" not in s, "bell alerts plumbing resurfacing"


def test_dead_v1_desk_stays_dead() -> None:
    # renderStanceChips is NOT in this list: PR #4241 (MLC-W2b) rebuilt it as a LIVE
    # act-board surface (invocation pinned in test_theme_scoring_conflicted) — only
    # the V1 fork's members stay banned.
    s = _read(TPL / "sector_central.html.j2")
    for fn in ("renderThemeDesk", "renderConcentration", "renderScorecards",
               "renderMacroCtx", "decorateRealActivity",
               "renderActNow", "_fetchRadar"):
        assert fn not in s, f"dead V1 desk function {fn} resurrected"


def test_gated_read_and_movement_posture() -> None:
    s = _read(TPL / "sector_central.html.j2")
    # The lanes stay the only gated/graded surface; movement stays display-only.
    assert "Lanes are the only gated, graded calls on this page" in s
    assert "display-only" in s


# ------------------------------------------------------------- shared JS + China

def test_sr_js_themes_unit_flag_is_backward_compatible() -> None:
    js = _read(TPL / "subsector_rotation.js")
    # US hides the unit via flag; absent flag (China feed) keeps the button.
    assert "_data.themes_unit !== false" in js
    assert "data-u=\"subsectors\"" in js


def test_china_consolidation_landed_on_its_own_page() -> None:
    """The follow-up program this test was waiting for has landed.

    Was test_china_templates_untouched_by_consolidation: while the US merge shipped
    alone, the China siblings had to keep their own pages, so it asserted none of the
    three was a stub. The China Sector Intelligence consolidation (2026-08) ported the
    merge, so the premise inverts for the two absorbed pages — but the guard it was
    really providing survives, and is what matters now: the US merge must not have
    reached across and stubbed China's HUB. Full China invariants live in
    tests/test_china_sector_intelligence_page.py.
    """
    hub = _read(TPL / "sector_central_china.html.j2")
    assert "http-equiv=\"refresh\"" not in hub, (
        "sector_central_china.html.j2 is the China hub — it must never be a stub"
    )
    for name in ("baskets_china.html.j2", "subsector_rotation_china.html.j2"):
        s = _read(TPL / name)
        assert "http-equiv=\"refresh\"" in s, (
            f"{name} is an absorbed page and must stay a redirect stub"
        )
        assert "sector_central_china.html" in s, f"{name} retargeted off the China hub"


def test_us_builder_flags_themes_unit_hidden() -> None:
    s = _read(ROOT / "scripts" / "build_subsector_rotation.py")
    assert 'payload["themes_unit"] = False' in s
    # the themes ARRAY must survive for engine/neuralweb/thematic_state.py
    assert "payload.pop(\"themes\"" not in s


# ------------------------------------------------------------------ nav

def test_nav_flyout_collapsed_to_two_entries() -> None:
    s = _read(TPL / "_navlinks.html.j2")
    assert "Sector Intelligence" in s
    # the two absorbed pages have no US nav entry anymore (stubs are reachable
    # only via old bookmarks/links); China entries survive.
    us_zone = s.split("China")[0]
    assert 'href="{{ NP }}baskets.html"' not in us_zone
    assert 'href="{{ NP }}subsector_rotation.html"' not in us_zone
    assert 'href="{{ NP }}subsectors.html"' in s  # confluence funnel stays
