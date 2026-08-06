from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Roster of pages that opt IN to macro-desk.css, with the variant class each declares.
# Membership changed with the Sector Intelligence consolidations (2026-08):
#   • US (#4237): baskets / subsector_rotation LEFT the family — both are redirect stubs
#     with their own inline style block (no macro-desk.css link, no body class).
#   • sector_central STAYED but changed VARIANT: the merged page is descended from the
#     baskets rvx layer, so it ships `page-baskets`, not `page-sector-central`.
#     KNOWN GAP (pre-existing, recorded in the consolidation masterplan §4b): the merged
#     page still carries scc-wrap / scc-cycle / cyc-stage / scc-section-h / scc-boardhead
#     markup, and macro-desk.css scopes ~15 rules for exactly those classes under
#     `body.macro-desk.page-sector-central` — dead on that page since the merge.
#     Reconciling is a styling call (cascade collision risk with the rvx layer),
#     not a roster call; this pin records the shipped truth in the meantime.
#   • China (#4299): baskets_china / subsector_rotation_china went the same way — stubs,
#     off the roster; their content lives on sector_central_china, which STAYED and
#     keeps page-sector-central (the merged China page still carries the scc-cycle /
#     cyc-stage markup those rules are scoped to).
#   • Stub invariants live in tests/test_sector_intelligence_page.py (US) and
#     tests/test_china_sector_intelligence_page.py (China).
PAGE_CLASSES = {
    "sector_central": "macro-desk page-baskets",
    "sector_central_china": "macro-desk page-sector-central",
    "sector_cycles": "macro-desk page-cycle",
    "sector_cycles_china": "macro-desk page-cycle",
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


def test_sector_central_cycle_section_is_one_island() -> None:
    """The cycle map + its rotation read-out are ONE container, not two cards.

    This test used to assert the opposite — that .cyc-stage was stripped bare
    (`padding: 0; border: 0; background: transparent; box-shadow: none`) so that
    .cyc-hero and .cyc-detail could each carry their own frame. That shipped the
    section as two stacked cards nested inside cycle.css's own framing, which the
    operator called out on 2026-08-04. The direction is now inverted: the STAGE is
    the single island and both children are flat.

    Pinning BOTH halves matters — flattening the children while leaving the stage
    bare would delete the section's container entirely, which reads as "fixed" in
    a screenshot of the seam and broken everywhere else.
    """
    css = _read("templates/macro-desk.css")

    stage_sel = "body.macro-desk.page-sector-central .scc-cycle .cyc-stage"
    start = css.index(stage_sel)
    stage_rule = css[start : css.index("}", start)]
    assert "border: 1px solid transparent" in stage_rule, "the island is borderless-but-boxed"
    assert "box-shadow:" in stage_rule and "none" not in stage_rule.split("box-shadow:")[1][:40]
    assert "background: var(--desk-tile" in stage_rule
    assert "gap: 0" in stage_rule, "no gutter — the children are one surface"

    kids_sel = "body.macro-desk.page-sector-central .scc-cycle :is(.cyc-hero, .cyc-detail)"
    kstart = css.index(kids_sel)
    kids_rule = css[kstart : css.index("}", kstart)]
    for decl in ("border: 0", "border-radius: 0", "background: transparent", "box-shadow: none"):
        assert decl in kids_rule, f"child card chrome not stripped: {decl}"


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
