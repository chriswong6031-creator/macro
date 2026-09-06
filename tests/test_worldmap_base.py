"""tests/test_worldmap_base.py — packet A-F02-1 §9.3."""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent


def _render():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    return env.get_template("_worldmap_base.html.j2").render(rungs={})


def test_every_path_has_unique_iso3():
    html = _render()
    isos = re.findall(r'data-iso3="([A-Z]{3})"', html)
    assert len(isos) == len(set(isos))
    assert len(isos) > 0


def test_iso3_superset_of_config_countries():
    html = _render()
    isos = set(re.findall(r'data-iso3="([A-Z]{3})"', html))
    cfg = yaml.safe_load((ROOT / "config/sanctions_ofac_programs.yml").read_text(encoding="utf-8"))
    config_isos = {row["iso3"] for row in cfg["programs"]}
    assert config_isos.issubset(isos)


def test_no_presentation_attributes():
    html = _render()
    assert "fill=\"#" not in html
    assert not re.search(r'<path[^>]*\bstyle="', html)
    for path_tag in re.findall(r"<path[^>]*>", html):
        assert "fill=" not in path_tag or "fill=\"url(" in path_tag
        assert "stroke=" not in path_tag


def test_no_title_element_or_attribute():
    html = _render()
    assert "<title>" not in html
    assert "title=" not in html
