"""Pin the relative-navigation contract for pages rendered below ``site/``.

Subdirectory templates must set ``nav_prefix`` before including shared nav or
every root-owned destination resolves beneath the current directory.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"

SUBDIR_TEMPLATES = {
    "sector.html.j2": "_site_nav.html.j2",
    "basket_detail.html.j2": None,
    "subsector_detail.html.j2": None,
    "subsector_rotation_detail.html.j2": None,
}

_SET_RE = re.compile(r"{%-?\s*set\s+nav_prefix\s*=\s*'\.\./'\s*-?%}")


def test_every_subdir_template_sets_nav_prefix_before_its_nav_include() -> None:
    for name, nav in SUBDIR_TEMPLATES.items():
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        match = _SET_RE.search(source)
        assert match, f"{name}: missing one-level nav_prefix"
        if nav:
            include_at = source.find(nav)
            assert include_at != -1, f"{name}: expected nav include {nav} not found"
            assert match.start() < include_at, f"{name}: nav_prefix must precede {nav}"


def test_shared_nav_partials_still_read_nav_prefix() -> None:
    for partial in ("_site_nav.html.j2", "_navlinks.html.j2"):
        source = (TEMPLATES / partial).read_text(encoding="utf-8")
        assert "nav_prefix" in source, f"{partial}: nav_prefix consumer was removed"
