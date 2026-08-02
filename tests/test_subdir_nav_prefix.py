"""Every template rendered into a site/ SUBDIRECTORY must set nav_prefix before its
nav include, or all ~85 header links 404 one level deep (/sectors/<page>.html).

Born from render run 30766686540 (2026-08-02): #4228's shared-header conversion
(12 variants → 1) dropped `{% set nav_prefix = '../' %}` from sector.html.j2 —
alone among the four subdirectory templates — and the dead-reference guard
red-wedged the render lane with 85 missing targets × 11 sector pages. The break
was silent at review time because the include still renders; only link RESOLUTION
dies. This pins the contract at the source so the wedge cannot recur quietly.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"

# template -> the nav include it must prefix. These four render one directory deep:
# sectors/ (build_site), basket*/ (build_theme_detail), rotation*/ + subsector*/
# (the two detail-page builders). Extend when a new subdir page family is born.
SUBDIR_TEMPLATES = {
    "sector.html.j2": "_site_nav.html.j2",
    "basket_detail.html.j2": None,          # nav include name varies; set line is the contract
    "subsector_detail.html.j2": None,
    "subsector_rotation_detail.html.j2": None,
}

_SET_RE = re.compile(r"{%-?\s*set\s+nav_prefix\s*=\s*'\.\./'\s*-?%}")


def test_every_subdir_template_sets_nav_prefix_before_its_nav_include():
    for name, nav in SUBDIR_TEMPLATES.items():
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        m = _SET_RE.search(src)
        assert m, (
            f"{name}: missing {{% set nav_prefix = '../' %}} — its pages render one "
            "directory deep and every header link would 404 (the #4228 regression class)"
        )
        if nav:
            inc = src.find(nav)
            assert inc != -1, f"{name}: expected nav include {nav} not found"
            assert m.start() < inc, (
                f"{name}: nav_prefix must be set BEFORE the {nav} include — a set "
                "after the include is invisible to it"
            )


def test_shared_nav_partials_still_read_nav_prefix():
    """The other half of the contract: the shared partials must keep consuming it."""
    for partial in ("_site_nav.html.j2", "_navlinks.html.j2"):
        src = (TEMPLATES / partial).read_text(encoding="utf-8")
        assert "nav_prefix" in src, (
            f"{partial}: no longer reads nav_prefix — subdirectory pages would lose "
            "their ../ link prefix silently"
        )
