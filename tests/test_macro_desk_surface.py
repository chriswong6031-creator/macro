from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PAGE_CLASSES = {
    "sector_central": "macro-desk page-sector-central",
    "sector_central_china": "macro-desk page-sector-central",
    "subsector_rotation": "macro-desk page-rotation",
    "subsector_rotation_china": "macro-desk page-rotation",
    "sector_cycles": "macro-desk page-cycle",
    "sector_cycles_china": "macro-desk page-cycle",
    "baskets": "macro-desk page-baskets",
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
    css = _read("templates/theme.css")
    selector = "body.macro-desk.page-sector-central .scc-cycle .cyc-stage"
    start = css.index(selector)
    rule = css[start : css.index("}", start)]
    assert "padding: 0" in rule
    assert "border: 0" in rule
    assert "background: transparent" in rule
    assert "box-shadow: none" in rule


def test_macro_desk_css_is_synced_and_cache_busted() -> None:
    template_css = (ROOT / "templates/theme.css").read_bytes()
    site_css = (ROOT / "site/theme.css").read_bytes()
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
        assert f"theme.css?v={version}" in _read(f"site/{page}.html"), page


def test_rotation_time_machine_control_is_mobile_scroll_safe() -> None:
    css = _read("templates/theme.css")
    assert "body.macro-desk.page-rotation .tm-unit-row" in css
    assert "overflow-x: auto" in css
    assert "body.macro-desk.page-rotation .tm-tier-btns { min-width: max-content; }" in css
