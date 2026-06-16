"""Render-guards + registry structure for the China & Commodity strategy hubs.

Mirrors tests/test_strategies_build.py: render each new grid template with a synthetic
view-model (autoescape + the i18n globals the builders wire in) so Jinja breakage is
caught before CI, plus structural checks on the two registries (unique keys, the
commodity `group` toggle, experimental flags).
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader

from lib import config

_C = {"blue": "#285fff", "indigo": "#5b6bff", "r2": "#9aa4b2", "r3": "#cfd4dc",
      "ink": "#101828", "text": "#344054", "muted": "#667085", "faint": "#98a2b3",
      "red": "#e5484d", "amber": "#e0a106", "grid": "#e6e9ef", "card": "#ffffff",
      "bg": "#f7f8fa"}


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


def _card(key="x", icon="🥇", href=None, exp=True):
    href = href or f"strategy_{key}.html"
    return {"key": key, "icon": icon, "href": href, "name_en": "Test Strat", "name_zh": "测试",
            "thesis_en": "t", "thesis_zh": "测", "experimental": exp,
            "cagr": 8.1, "hodl_cagr": 7.0, "sharpe": 0.7, "hodl_sharpe": 0.6,
            "maxdd": -20.0, "hodl_maxdd": -40.0, "income": 0.0, "years": 20,
            "stance_en": "60% X · 40% cash", "stance_zh": "60% X · 40% 现金"}


def test_china_strategies_grid_renders():
    cards = [_card("income_vector", "◎", "china_allocation.html", exp=False),
             _card("cn_credit_vol", "🪙", "strategy_cn_credit_vol.html")]
    html = _env().get_template("china_strategies.html.j2").render(cards=cards, built="now", C=_C)
    assert "China Strategy Scorecards" in html
    assert "china_allocation.html" in html and "strategy_cn_credit_vol.html" in html
    assert 'class="active" href="china_strategies.html"' in html      # China nav active
    assert "commodity_strategies.html" in html                        # nav has the sibling hub
    assert "Experimental" in html and len(html) > 5000


def test_commodity_strategies_toggle_grid_renders():
    groups = [
        {"key": "gold", "icon": "🥇", "label_en": "Gold", "label_zh": "黄金",
         "cards": [_card("cm_gold_swap"), _card("cm_gold_macro", "🏵️")]},
        {"key": "oil", "icon": "🛢️", "label_en": "Oil", "label_zh": "原油",
         "cards": [_card("cm_oil_swap", "🛢️")]},
    ]
    html = _env().get_template("commodity_strategies.html.j2").render(groups=groups, built="now", C=_C)
    assert "Commodity Strategy Scorecards" in html
    assert html.count("cmdy-tab") >= 2 and 'data-grp="gold"' in html and 'data-grp="oil"' in html
    assert "cmdy-grid" in html and "strategy_cm_gold_macro.html" in html
    assert "active" in html and len(html) > 5000          # first tab/grid pre-selected + JS toggle


def test_china_registry_structure():
    from engine import china_strategies as S
    keys = [s.key for s in S.CHINA_STRATEGIES]
    assert keys == ["cn_credit_vol", "cn_volmanaged", "cn_credit_margin"]
    assert len(keys) == len(set(keys))
    for spec in S.CHINA_STRATEGIES:
        assert spec.experimental is True and spec.own_page is None
        assert callable(spec.benchmark) and callable(spec.alloc) and callable(spec.score)
        assert spec.name_en and spec.name_zh and spec.bench_en == "CSI 300"


def test_commodity_registry_structure():
    from engine import commodity_strategies as S
    keys = [s.key for s in S.COMMODITY_STRATEGIES]
    assert len(keys) == 8 and len(keys) == len(set(keys))
    assert all(k.startswith("cm_") for k in keys)          # namespaced — no collision with US suite
    groups = {s.group for s in S.COMMODITY_STRATEGIES}
    assert groups == {"gold", "silver", "copper", "oil"}   # two strategies per commodity
    for g in groups:
        assert sum(1 for s in S.COMMODITY_STRATEGIES if s.group == g) == 2
    for spec in S.COMMODITY_STRATEGIES:
        assert spec.experimental is True and spec.cash_en == "T-bills"
    assert [g["key"] for g in S.COMMODITY_GROUPS] == ["gold", "silver", "copper", "oil"]
