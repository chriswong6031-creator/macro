"""tests/test_sanctions_map_page.py — packet A-F02-1 §9.2. Model:
tests/test_intl_build.py (render a synthetic VM in both languages)."""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from engine.i18n import t, td, tr
from engine.sanctions_map import rungs_for

ROOT = Path(__file__).resolve().parent.parent

VM_OK = {
    "as_of": "2026-09-04",
    "source_url": "https://ofac.treasury.gov/sanctions-programs-and-country-information",
    "fetched_at": "2026-09-05T02:11:00Z",
    "n_programs_total": 5,
    "n_countries": 1,
    "countries": [
        {"iso3": "RUS", "name_en": "Russia", "name_zh": "俄罗斯", "n_programs": 6, "rung": 3,
         "programs": [{"code": "RUSSIA-EO14024", "name_en": "Russia — EO 14024",
                        "name_zh": "俄罗斯 — 第14024号行政命令",
                        "url": "https://ofac.treasury.gov/x"}]},
    ],
    "unresolved": [{"code": "XYZ", "n_entries": 3}],
    "thematic": [{"code": "SDGT", "n_entries": 10}],
    "coverage": {"resolved": 4, "unresolved": 3, "thematic": 1},
}

VM_UNKNOWN_ASOF = dict(VM_OK, as_of=None)
VM_UNREADABLE = {
    "as_of": None, "source_url": None, "fetched_at": None,
    "n_programs_total": 0, "n_countries": 0, "countries": [], "unresolved": [],
    "thematic": [], "coverage": None,
}
VM_MANY_COUNTRIES = dict(
    VM_OK,
    n_countries=12,
    countries=[
        {"iso3": f"C{i:02d}", "name_en": f"Country {i}", "name_zh": f"国家{i}",
         "n_programs": 1, "rung": 1, "programs": []}
        for i in range(12)
    ],
    coverage={"resolved": 12, "unresolved": 0, "thematic": 0},
)

BANNED = ["falsifier", "refuted", "证伪", "z-score", "percentile rank"]


ALL_ISO3 = {"RUS", "CHN", "USA"}  # CHN stands in for an unmapped-code country


def _render(vm, all_iso3=None):
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td, t=t)
    rungs = rungs_for(vm, all_iso3 if all_iso3 is not None else ALL_ISO3)
    return env.get_template("sanctions_map.html.j2").render(vm=vm, rungs=rungs)


def test_every_l_en_has_l_zh_twin():
    html = _render(VM_OK)
    assert html.count('class="l-en"') == html.count('class="l-zh"')
    assert html.count('class="l-en"') > 0


def test_zh_uses_name_zh_not_english_echo():
    """B3: programme and country labels must render the config name_zh, not an
    English echo through td()/LEX miss."""
    html = _render(VM_OK)
    assert '<span class="l-zh">俄罗斯</span>' in html
    assert '<span class="l-zh">俄罗斯 — 第14024号行政命令</span>' in html
    # Must not echo the English programme title into the ZH span.
    assert '<span class="l-zh">Russia — EO 14024</span>' not in html


def test_no_cjk_in_title_attributes():
    html = _render(VM_OK)
    for m in re.findall(r'title="([^"]*)"', html):
        assert not re.search(r"[一-鿿]", m)


def test_source_url_and_as_of_present():
    html = _render(VM_OK)
    assert VM_OK["source_url"] in html
    assert VM_OK["as_of"] in html


def test_unresolved_count_prints():
    """Pin the country-scoped unresolved count next to its null copy — not any
    digit 3 elsewhere on the page (Opus review minor)."""
    html = _render(VM_OK)
    assert "We could not verify a country for" in html
    assert re.search(
        r"We could not verify a country for</span>"
        r'<span class="l-zh">[^<]*</span>\s*'
        r'<b class="tnum">3</b>',
        html,
    )


def test_as_of_none_renders_unknown_not_blank():
    html = _render(VM_UNKNOWN_ASOF)
    assert "unknown" in html
    assert "未知" in html


def test_coverage_none_renders_degraded_and_hides_cards():
    html = _render(VM_UNREADABLE)
    assert "could not read the OFAC list" in html
    assert 'class="sm-cards"' not in html
    assert "<table" not in html
    assert "is-unknown" in html
    # BLOCKER 2: degraded header must not print a fabricated zero programme count.
    assert 'class="sm-count"' not in html
    assert "Programme count not available yet" in html
    assert "计划数暂无" in html
    meta = html.split('class="sm-meta"')[1].split("</p>")[0]
    assert ">0<" not in meta
    assert "sanctions programmes" not in meta


def test_no_banned_vocabulary():
    html = _render(VM_OK)
    low = html.lower()
    for word in BANNED:
        assert word.lower() not in low


def test_unresolved_coverage_marks_unmapped_countries_unknown():
    """A country with real programmes under an unmapped code must never paint
    identically to an unsanctioned country — it must render as coverage-unknown
    (rung 'x'), not as a false rung-0 clean read, whenever
    vm['coverage']['unresolved'] > 0."""
    html = _render(VM_OK)
    assert 'data-iso3="CHN" data-rung="x"' in html
    assert 'data-iso3="RUS" data-rung="3"' in html


def test_fully_resolved_coverage_marks_absent_as_not_named():
    vm = dict(VM_OK, coverage={"resolved": 4, "unresolved": 0, "thematic": 1})
    html = _render(vm)
    assert 'data-iso3="CHN" data-rung="0"' in html
    assert 'data-iso3="CHN" data-rung="x"' not in html


def test_country_table_lists_all_rows_no_dangling_see_all():
    """MAJOR 4: table shows every country; no dead 'See all' affordance."""
    html = _render(VM_MANY_COUNTRIES)
    assert "See all" not in html
    assert "查看全部" not in html
    for i in range(12):
        assert f'data-iso3="C{i:02d}"' in html


def test_legend_distinguishes_not_named_from_unknown():
    """MAJOR 3: hatch swatch for rung x; explicit panel fill for rung 0."""
    html = _render(VM_OK)
    assert '.sm-legend [data-rung="x"] i{background:repeating-linear-gradient' in html
    assert '.sm-legend [data-rung="0"] i{background:var(--panel2)}' in html
    assert 'html[data-theme="light"] .sm-legend [data-rung="0"] i{background:var(--panel)}' in html


def test_degraded_null_uses_date_not_iso_timestamp():
    """MINOR 6: glance-tier null copy prints YYYY-MM-DD, not a full ISO stamp."""
    vm = dict(VM_UNREADABLE, fetched_at="2026-09-06T05:53:36Z")
    html = _render(vm)
    assert "2026-09-06T05:53:36Z" not in html.split("<details")[0]
    assert "2026-09-06" in html.split("<details")[0]


def test_map_aria_label_has_zh():
    """MINOR 10: screen-reader label carries both EN and ZH."""
    html = _render(VM_OK)
    assert "现行美国 OFAC 制裁计划点名国家的世界地图" in html


def test_hover_row_has_leave_focus_blur_and_click_handlers():
    """The highlight must not latch — there must be a way to clear it
    (mouseleave/blur) and a keyboard/touch path (focus/click)."""
    html = _render(VM_OK)
    assert "mouseleave" in html
    assert "'focus'" in html
    assert "'blur'" in html
    assert "'click'" in html
    assert "tabindex" in html