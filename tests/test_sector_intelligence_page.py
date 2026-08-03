"""Sector Intelligence consolidation invariants (2026-08 merge of baskets +
subsector_rotation into sector_central.html).

Pins the merge's load-bearing properties so a later template edit cannot silently
undo them: the two redirect stubs, the merged page's section skeleton, the
payload externalization (no inline BASKETS embed), the live-quote member-symbol
registry, and the China contract (its templates untouched by the shared-JS edit).
Charter: research/SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md §0.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"


def _read(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


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


def test_forming_narratives_mounted_at_end_of_movement() -> None:
    """The Forming Narratives panel ships on the US page (PR-A1).

    engine.narrative_emergence has emitted site/basketdata/narrative_emergence.json for
    US nightly all along, but the shared panel was mounted only on the non-US baskets
    pages — the US read was computed and never shown. It belongs at the END of
    MOVEMENT: the funnel descends gated lanes → map → whole-market motion → what is
    forming next.
    """
    s = _read(TPL / "sector_central.html.j2")
    assert '{% include "_forming_narratives.html.j2" %}' in s, "panel not mounted"
    # placement: inside #si-movement, after the time-machine mount, before the close
    movement = s.split('id="si-movement"', 1)[1].split("</section>", 1)[0]
    assert '{% include "_forming_narratives.html.j2" %}' in movement, \
        "panel escaped the MOVEMENT section"
    assert movement.index('id="tm-mount"') < movement.index("_forming_narratives"), \
        "panel must come after the time machine — it is the last read in MOVEMENT"


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


def test_china_templates_untouched_by_consolidation() -> None:
    # The China siblings must keep their own pages (follow-up program ports them).
    for name in ("sector_central_china.html.j2", "baskets_china.html.j2",
                 "subsector_rotation_china.html.j2"):
        s = _read(TPL / name)
        assert "http-equiv=\"refresh\"" not in s, f"{name} must not be a stub"


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
