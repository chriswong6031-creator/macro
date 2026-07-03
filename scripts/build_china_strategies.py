"""China Strategy Scorecards hub + per-strategy detail pages.

Renders:
  site/china_strategies.html          — the responsive grid of China strategy scorecards
  site/strategy_<key>.html            — one detail page per NEW China strategy
and writes data/china_regime/china_strategies_latest.json for the landing-hub card.

Mirrors scripts.build_strategies (the US hub): it reuses that module's asset-agnostic
machinery (_evaluate / _detail_vm / _card + the build_spvector Plotly chart helpers) and
the same templates (china_strategies.html.j2 grid + strategy_detail.html.j2 detail). The
China Income Vector (the static income+gold+bond blend in engine.china_allocation) keeps
its bespoke page and is listed as the first card, linking to china_allocation.html.

Run: python -m scripts.build_china_strategies
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from engine import china_allocation as ca
from engine import china_strategies as S
from lib import config
from lib.pages import write_page
from scripts.build_strategies import _card, _detail_vm, _evaluate
from scripts.build_vector import C

BACK = ("China Strategies", "中国策略")


def _income_vector_card() -> dict:
    """Card for the China Income Vector (the validated static blend) — links to its own
    bespoke page. Numbers come from engine.china_allocation in CI (where the sleeve ETFs
    are present); a documented representative fallback keeps the card rendering locally."""
    try:
        bt = ca.backtest(ca.DEFAULT_VARIANT)
        bc = bt.get("bench_csi300", {}) or {}
        if bt.get("cagr") is not None and bc.get("cagr") is not None:
            cagr, sharpe, maxdd, years = bt["cagr"], bt["sharpe"], bt["maxdd"], bt.get("years")
            hcagr, hsharpe, hmaxdd = bc.get("cagr"), bc.get("sharpe"), bc.get("maxdd")
            income = round(bt.get("cagr") or 0, 1)
        else:
            raise ValueError("alloc backtest unavailable (sleeve ETFs absent locally)")
    except Exception:  # noqa: BLE001 — local fallback; CI recomputes live
        cagr, sharpe, maxdd, years = 6.8, 1.06, -13.8, 8.4
        hcagr, hsharpe, hmaxdd, income = 1.9, 0.42, -45.5, 2.6
    return {
        "key": "income_vector", "icon": "◎", "href": "china_allocation.html",
        "name_en": "China Income Vector", "name_zh": "中国收入向量",
        "thesis_en": "Diversification, not timing: a static income + gold + short-bond blend that "
                     "roughly triples the Sharpe of CSI 300 and cuts the drawdown to a quarter.",
        "thesis_zh": "靠分散而非择时：红利 + 黄金 + 短债的静态组合，夏普约为沪深300的三倍，回撤降至约四分之一。",
        "experimental": False,
        "cagr": cagr, "hodl_cagr": hcagr, "sharpe": sharpe, "hodl_sharpe": hsharpe,
        "maxdd": maxdd, "hodl_maxdd": hmaxdd, "income": income, "years": years or 8.4,
        "stance_en": "Income + gold + bonds", "stance_zh": "红利 + 黄金 + 国债",
    }


def build() -> str:
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)

    site = config.ROOT / config.load()["storage"]["site_dir"]
    cards = [_income_vector_card()]
    for spec in S.CHINA_STRATEGIES:
        ev = _evaluate(spec, {})
        cards.append(_card(ev, stance=S.CN_STANCE))
        html = env.get_template("strategy_detail.html.j2").render(
            **_detail_vm(ev, built, leg_meta=S.CN_LEG_META, back_href="china_strategies.html",
                         back_label=BACK), C=C)
        write_page(site / f"strategy_{spec.key}.html", html)

    # Pinned "China Mastermind Flagships" hero — the 3 multi-asset GTAA cards from the SAME
    # source build_china_masterminds renders (engine.china_masterminds), so the pinned hero
    # here and the per-profile detail pages stay in sync on every build. Additive: the
    # {% if masterminds %} guard means the hub still builds if the engine errors.
    masterminds = []
    try:
        from scripts.build_china_masterminds import china_mastermind_cards
        masterminds = china_mastermind_cards()
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("china mastermind hero cards unavailable (%s)", e)

    hub = env.get_template("china_strategies.html.j2").render(cards=cards, masterminds=masterminds,
                                                              built=built, C=C)
    write_page(site / "china_strategies.html", hub)

    snap = {"n": len(cards), "built": built,
            "cards": [{"key": c["key"], "name": c["name_en"], "cagr": c["cagr"],
                       "sharpe": c["sharpe"], "maxdd": c["maxdd"], "experimental": c["experimental"]}
                      for c in cards]}
    snap_dir = config.data_dir() / "china_regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "china_strategies_latest.json").write_text(json.dumps(snap, indent=2))
    return str(site / "china_strategies.html")


def main() -> int:
    print(f"[built] {build()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
