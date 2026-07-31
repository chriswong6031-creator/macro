"""Cross-surface guards for the Terminal indicator entitlement copy."""
from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from scripts.build_public_pages import plans_view_model
from scripts.build_site import _plans_view_model


ROOT = Path(__file__).resolve().parents[1]


def _access() -> dict:
    catalog = yaml.safe_load((ROOT / "config" / "plans.yml").read_text())
    return catalog["terminal_indicators"]


def test_both_plans_builders_receive_the_indicator_access_contract():
    expected = _access()
    assert plans_view_model()["terminal_indicators"] == expected
    assert _plans_view_model()["terminal_indicators"] == expected


def test_landing_and_onboarding_compare_show_each_tier_access():
    access = _access()
    for rel in ("templates/index.html", "site/index.html"):
        page = (ROOT / rel).read_text()
        assert "Advanced indicator modules" in page
        assert f"{access['core_count']} core indicators + Candle Painter" in page
        assert f"{access['access']['insider']} of {access['advanced_total']} advanced modules" in page
        assert f"All {access['access']['pro']} advanced modules" in page
        assert f"{access['access']['free']} / {access['advanced_total']}" in page
        assert f"{access['access']['insider']} / {access['advanced_total']}" in page
        assert f"All {access['access']['pro']}" in page

    for rel in ("templates/onboard.js", "site/onboard.js"):
        compare = (ROOT / rel).read_text()
        assert (
            f'{{ l: ["Advanced indicator modules", "高级指标模块"], '
            f'v: [["{access["access"]["free"]} / {access["advanced_total"]}", '
            f'"{access["access"]["free"]} / {access["advanced_total"]}"], '
            f'["{access["access"]["insider"]} / {access["advanced_total"]}", '
            f'"{access["access"]["insider"]} / {access["advanced_total"]}"], '
            f'["All {access["access"]["pro"]}", "全部 {access["access"]["pro"]} 个"]] }}'
        ) in compare


def test_rendered_plans_page_names_the_indicator_ladder():
    access = _access()
    vm = plans_view_model()
    page = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
    ).get_template("plans.html.j2").render(
        generated_utc="test",
        currency=vm["currency"],
        insider=vm["insider"],
        pro=vm["pro"],
        founding=vm["founding"],
        terminal_indicators=vm["terminal_indicators"],
    )
    assert "Advanced indicator modules" in page
    assert f"{access['core_count']} " in page and "core indicators" in page
    assert f"{access['access']['free']} / {access['advanced_total']}" in page
    assert f"{access['access']['insider']} / {access['advanced_total']}" in page
    assert f'<span class="l-zh">全部</span> {access["access"]["pro"]}<small' in page
