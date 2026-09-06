"""tests/test_sanctions_map_nav.py — packet A-F02-1 §9.4."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAV = ROOT / "templates/_navlinks.html.j2"


def test_exactly_one_sanctions_map_anchor():
    html = NAV.read_text(encoding="utf-8")
    matches = re.findall(r'href="\{\{\s*NP\s*\}\}sanctions_map\.html"', html)
    assert len(matches) == 1


def test_anchor_sits_inside_international_dropdown():
    html = NAV.read_text(encoding="utf-8")
    idx = html.index("sanctions_map.html")
    idx_baskets = html.index("baskets_intl.html")
    # the sanctions_map anchor immediately follows the baskets_intl anchor,
    # both inside the same International dropdown block.
    assert 0 < (idx - idx_baskets) < 400


def test_anchor_has_en_and_zh_labels():
    html = NAV.read_text(encoding="utf-8")
    line_start = html.index("sanctions_map.html")
    line_end = html.index("</a>", line_start)
    snippet = html[line_start:line_end]
    assert "Sanctions Map" in snippet
    assert "制裁地图" in snippet


def test_nav_dd_count_unchanged():
    html = NAV.read_text(encoding="utf-8")
    # exactly the pre-existing set of top-level nav-dd families — no third
    # header was created by this packet (measured on the pre-edit file).
    count = len(re.findall(r'class="nav-dd', html))
    assert count == 22


def test_anchor_carries_no_data_intl_country():
    html = NAV.read_text(encoding="utf-8")
    line_start = html.index("sanctions_map.html")
    line_start = html.rindex("<a ", 0, line_start)
    line_end = html.index("</a>", line_start)
    snippet = html[line_start:line_end]
    assert "data-intl-country" not in snippet
