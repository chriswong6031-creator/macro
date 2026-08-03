from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Roster of pages that opt IN to macro-desk.css, with the variant class each declares.
# Membership changed with the Sector Intelligence consolidation (#4237):
#   • baskets / subsector_rotation LEFT the family — both are now redirect stubs with
#     their own inline style block. They link no macro-desk.css and declare no body
#     class, so they are off this roster (their China siblings keep their real pages).
#   • sector_central STAYED but changed VARIANT: the merged page is descended from the
#     baskets rvx layer, so it ships `page-baskets`, not `page-sector-central`.
#     KNOWN GAP (pre-existing, recorded in the consolidation masterplan §4b): the merged
#     page still carries scc-wrap / scc-cycle / cyc-stage / scc-section-h / scc-boardhead
#     markup, and macro-desk.css scopes ~15 rules for exactly those classes under
#     `body.macro-desk.page-sector-central` — dead on this page since the merge. Its
#     China sibling still declares page-sector-central, so those rules stay live there.
#     Reconciling the two is a styling call (cascade collision risk with the rvx layer),
#     not a roster call; this pin records the shipped truth in the meantime.
#   • Stub invariants for the two redirect stubs live in
#     tests/test_sector_intelligence_page.py.
PAGE_CLASSES = {
    "sector_central": "macro-desk page-baskets",
    "sector_central_china": "macro-desk page-sector-central",
    "subsector_rotation_china": "macro-desk page-rotation",
    "sector_cycles": "macro-desk page-cycle",
    "sector_cycles_china": "macro-desk page-cycle",
    "baskets_china": "macro-desk page-baskets",
    "baskets_hk": "macro-desk page-baskets",
    "baskets_canada": "macro-desk page-baskets",
    "baskets_intl": "macro-desk page-baskets",
    "subsectors": "macro-desk page-subsectors",
    "subsectors_china": "macro-desk page-subsectors",
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_macro_desk_source_and_rendered_pages_opt_in() -> None:
    for page, classes in PAGE_CLASSES.items():
        template = _read(f"templates/{page}.html.j2")
        rendered = _read(f"site/{page}.html")
        body = f'<body class="{classes}">'
        assert body in template, page
        assert body in rendered, page

    # One template renders the US, China, Hong Kong, and Canada variants.
    allocation_template = _read("templates/allocation.html.j2")
    assert '<body class="macro-desk page-baskets">' in allocation_template
    for page in ("allocation", "allocation_china", "allocation_hk", "allocation_canada"):
        assert '<body class="macro-desk page-baskets">' in _read(f"site/{page}.html")

    # The China template also renders the THS sibling.
    assert '<body class="macro-desk page-baskets">' in _read("site/baskets_china_ths.html")


def test_sector_central_double_frame_is_removed() -> None:
    css = _read("templates/macro-desk.css")
    selector = "body.macro-desk.page-sector-central .scc-cycle .cyc-stage"
    start = css.index(selector)
    rule = css[start : css.index("}", start)]
    assert "padding: 0" in rule
    assert "border: 0" in rule
    assert "background: transparent" in rule
    assert "box-shadow: none" in rule


def test_macro_desk_css_is_synced_scoped_and_cache_busted() -> None:
    template_css = (ROOT / "templates/macro-desk.css").read_bytes()
    site_css = (ROOT / "site/macro-desk.css").read_bytes()
    assert site_css == template_css

    version = hashlib.sha256(site_css).hexdigest()[:8]
    rendered_pages = set(PAGE_CLASSES) | {
        "baskets_china_ths",
        "allocation",
        "allocation_china",
        "allocation_hk",
        "allocation_canada",
    }
    for page in rendered_pages:
        assert f"macro-desk.css?v={version}" in _read(f"site/{page}.html"), page

    linked_pages = {
        path.stem
        for path in (ROOT / "site").glob("*.html")
        if "macro-desk.css?v=" in path.read_text(encoding="utf-8")
    }
    assert linked_pages == rendered_pages

    # The opt-in layer must not churn the immutable global theme boundary.
    assert (ROOT / "site/theme.css").read_bytes() == (ROOT / "templates/theme.css").read_bytes()


def test_rotation_time_machine_control_is_mobile_scroll_safe() -> None:
    css = _read("templates/macro-desk.css")
    assert "body.macro-desk.page-rotation .tm-unit-row" in css
    assert "overflow-x: auto" in css
    assert "body.macro-desk.page-rotation .tm-tier-btns { min-width: max-content; }" in css
