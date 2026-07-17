"""Source-level guards for the W-FCT standout stage facet bar + Terminal links
(templates/china.html.j2, scripts/build_china.py).

Follows the house pattern of string-level template assertions (see
test_pick_lab_cn_render.py). Guards:
  - facet bar present with all five facets (entry / rip / early / ran / all)
  - server-side default facet attribute on #standouts
  - the three shelf groups tagged for CSS facet filtering (entry, ran x2,
    rip-shelf shared "rip early")
  - zone-splitting CSS rules for the shared ripening shelf
  - bilingual facet labels (ZH glyphs intact)
  - Turn Setups: both tbodies link ticker+name to the chart anchor; name map
    guarded against old pickled VMs that lack the key
  - Reversion Desk cards are chart-anchor links (not inert divs)
  - build_china.py ships the cn_name_by_ticker VM key
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHINA_SRC = (ROOT / "templates" / "china.html.j2").read_text(encoding="utf-8")
BUILD_SRC = (ROOT / "scripts" / "build_china.py").read_text(encoding="utf-8")


def test_facet_bar_present_with_all_facets():
    assert 'id="st-facet-bar"' in CHINA_SRC
    for facet in ("entry", "rip", "early", "ran", "all"):
        assert f'data-facet="{facet}"' in CHINA_SRC, f"facet chip {facet} missing"


def test_facet_default_attr_on_panel():
    assert 'id="standouts" data-stfacet="{{ _stf_default }}"' in CHINA_SRC


def test_facet_groups_tagged():
    assert 'data-stf="entry"' in CHINA_SRC
    assert CHINA_SRC.count('data-stf="ran"') == 2, "both RAN blocks must be tagged"
    assert 'data-stf="rip early"' in CHINA_SRC


def test_facet_css_rules_present():
    assert '#standouts[data-stfacet="rip"] .rip-zone:not(.rz-ready)' in CHINA_SRC
    assert '#standouts[data-stfacet="early"] .rip-zone.rz-ready' in CHINA_SRC


def test_facet_prefix_does_not_reuse_stocktable_chrome():
    """stocktable.js injects .stf-* chrome (incl. .stf-bar) — the facet bar must
    use its own stgf- prefix or the injected CSS restyles it."""
    assert 'class="sb-seg stgf-bar"' in CHINA_SRC
    assert 'class="sb-seg stf-bar"' not in CHINA_SRC


def test_facet_labels_bilingual():
    for zh in ("入场", "蓄势中", "为时尚早", "信号已过", "全部"):
        assert zh in CHINA_SRC, f"ZH facet label {zh} missing"


def test_mtf_ticker_cells_linked_with_names():
    # two tbodies each carry the linked ticker cell (plus the two pre-existing
    # lookup-column links) — at least 4 anchors to china_lookup.html#{{ _sym }}
    assert CHINA_SRC.count("china_lookup.html#{{ _sym }}") >= 4
    assert CHINA_SRC.count("_mtf_names.get(_sym)") == 2, (
        "both MTF tbodies (visible + hidden) must render the company name"
    )


def test_mtf_name_map_guarded_for_old_vms():
    # render_china_fast re-renders from a pickled VM that may predate the key —
    # the template must not crash when cn_name_by_ticker is undefined or None
    assert "cn_name_by_ticker is defined" in CHINA_SRC


def test_reversion_desk_cards_are_links():
    assert '<a class="nbcard nb-up" href="china_lookup.html#' in CHINA_SRC
    assert 'class="nbcard nb-up" style="cursor:default"' not in CHINA_SRC


def test_build_china_ships_name_map():
    assert 'vm["cn_name_by_ticker"]' in BUILD_SRC
