"""Commodity Strategy Scorecards (per-commodity toggle) + per-strategy detail pages.

Renders:
  site/commodity_strategies.html      — a scorecard grid with a per-commodity TOGGLE
                                        (gold / silver / copper / oil); each commodity
                                        shows its own strategies in the same grid container
  site/strategy_<key>.html            — one detail page per commodity strategy
and writes data/commodity/commodity_strategies_latest.json for the landing-hub card.

Reuses scripts.build_strategies (the US hub): _evaluate / _detail_vm / _card + the
build_spvector Plotly chart helpers, and the strategy_detail.html.j2 template. The grid
template (commodity_strategies.html.j2) groups the cards by spec.group and toggles which
group is visible. Two strategies per commodity: a simple risk on/off TREND SWAP and a
deeper, commodity-specific MULTIFACTOR model (engine.commodity_strategies).

Run: python -m scripts.build_commodity_strategies
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from engine import commodity_strategies as S
from lib import config
from scripts.build_strategies import _card, _detail_vm, _evaluate
from scripts.build_vector import C

BACK = ("Commodity Strategies", "商品策略")


def build() -> str:
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)

    site = config.ROOT / config.load()["storage"]["site_dir"]
    cards_by_group: dict[str, list] = {}
    flat: list = []
    for spec in S.COMMODITY_STRATEGIES:
        ev = _evaluate(spec, {})
        card = _card(ev, stance=S.CM_STANCE)
        cards_by_group.setdefault(spec.group, []).append(card)
        flat.append(card)
        html = env.get_template("strategy_detail.html.j2").render(
            **_detail_vm(ev, built, leg_meta=S.CM_LEG_META, back_href="commodity_strategies.html",
                         back_label=BACK), C=C)
        (site / f"strategy_{spec.key}.html").write_text(html)

    groups = [{**g, "cards": cards_by_group.get(g["key"], [])} for g in S.COMMODITY_GROUPS
              if cards_by_group.get(g["key"])]
    hub = env.get_template("commodity_strategies.html.j2").render(groups=groups, built=built, C=C)
    (site / "commodity_strategies.html").write_text(hub)

    snap = {"n": len(flat), "groups": [g["key"] for g in groups], "built": built,
            "cards": [{"key": c["key"], "name": c["name_en"], "cagr": c["cagr"],
                       "sharpe": c["sharpe"], "maxdd": c["maxdd"]} for c in flat]}
    snap_dir = config.data_dir() / "commodity"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "commodity_strategies_latest.json").write_text(json.dumps(snap, indent=2))
    return str(site / "commodity_strategies.html")


def main() -> int:
    print(f"[built] {build()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
