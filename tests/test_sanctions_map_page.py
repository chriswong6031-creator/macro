"""tests/test_sanctions_map_page.py — packet A-F02-1 §9.2. Model:
tests/test_intl_build.py (render a synthetic VM in both languages)."""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from engine.i18n import t, td, tr

ROOT = Path(__file__).resolve().parent.parent

VM_OK = {
    "as_of": "2026-09-04",
    "source_url": "https://ofac.treasury.gov/sanctions-programs-and-country-information",
    "fetched_at": "2026-09-05T02:11:00Z",
    "n_programs_total": 5,
    "countries": [
        {"iso3": "RUS", "name_en": "Russia", "name_zh": "俄罗斯", "n_programs": 6, "rung": 3,
         "programs": [{"code": "RUSSIA-EO14024", "name_en": "Russia — EO 14024",
                        "name_zh": "俄罗斯 — 第14024号行政命令",
                        "url": "https://ofac.treasury.gov/x"}]},
    ],
    "unresolved": [{"code": "XYZ", "n_entries": 3}],
    "coverage": {"resolved": 4, "unresolved": 3},
}

VM_UNKNOWN_ASOF = dict(VM_OK, as_of=None)
VM_UNREADABLE = {
    "as_of": None, "source_url": None, "fetched_at": None,
    "n_programs_total": 0, "countries": [], "unresolved": [], "coverage": None,
}

BANNED = ["falsifier", "refuted", "证伪", "z-score", "percentile rank"]


def _render(vm):
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td, t=t)
    rungs = {c["iso3"]: c["rung"] for c in vm.get("countries") or []}
    return env.get_template("sanctions_map.html.j2").render(vm=vm, rungs=rungs)


def test_every_l_en_has_l_zh_twin():
    html = _render(VM_OK)
    assert html.count('class="l-en"') == html.count('class="l-zh"')
    assert html.count('class="l-en"') > 0


def test_no_cjk_in_title_attributes():
    html = _render(VM_OK)
    for m in re.findall(r'title="([^"]*)"', html):
        assert not re.search(r"[一-鿿]", m)


def test_source_url_and_as_of_present():
    html = _render(VM_OK)
    assert VM_OK["source_url"] in html
    assert VM_OK["as_of"] in html


def test_unresolved_count_prints():
    html = _render(VM_OK)
    assert ">3<" in html or "3</b>" in html


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


def test_no_banned_vocabulary():
    html = _render(VM_OK)
    low = html.lower()
    for word in BANNED:
        assert word.lower() not in low
