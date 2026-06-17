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

from engine import active_commodity as Ach
from engine import commodity_strategies as S
from lib import config
from scripts import _active_render as AR
from scripts.build_strategies import _card, _detail_vm, _evaluate
from scripts.build_vector import C

BACK = ("Commodity Strategies", "商品策略")
_BACK = ("commodity_strategies.html", "Commodity Strategies", "商品策略")

# honest per-model out-of-sample verdict (shown in the OOS panel)
_ACTIVE_VERDICT = {
    "cm_gold_active": ("Genuine full-sample win on all three (CAGR + Sharpe + drawdown) at <1x average leverage. "
                       "The risk-adjusted edge is robust; the CAGR beat is concentrated in trending eras — it wins "
                       "the first half big and is a near-tie in the second.",
                       "全样本在三项上均真实跑赢（年化 + 夏普 + 回撤），平均杠杆 <1x。风险调整后的优势稳健；年化的跑赢集中在趋势性时代"
                       "——前半段大幅领先，后半段接近持平。"),
    "cm_silver_active": ("ROBUST: beats silver buy-&-hold on CAGR in BOTH out-of-sample halves, with a higher Sharpe "
                         "throughout. The gold/silver-ratio mean-reversion is genuine alpha that the leverage amplifies.",
                         "稳健：在两个样本外半段均在年化上跑赢白银买入持有，且全程夏普更高。金银比均值回归是真实阿尔法，由杠杆放大。"),
    "cm_copper_active": ("ROBUST: beats copper buy-&-hold on CAGR with Sharpe ≥ B&H in BOTH halves. The global-growth "
                         "tilt (China credit + industrial production) is genuine timing alpha, not just leverage.",
                         "稳健：在两个半段均以 ≥ 买入持有的夏普跑赢铜买入持有的年化。全球增长倾斜（中国信用 + 工业生产）是真实的择时阿尔法，"
                         "而非单纯杠杆。"),
}
_ACTIVE_CAV = ("Active, leverage-capable model — leverage amplifies losses as well as gains. Continuous "
               "front-month total-return close; net of 3 bps cost + a 1% financing spread on the levered part; "
               "the de-risked sleeve earns the T-bill yield. Experimental; full Phase-0 a fast-follow.",
               "主动、可加杠杆模型——杠杆会同时放大盈亏。连续近月总回报收盘价；扣除 3 个基点成本 + 杠杆部分 1% 融资利差；"
               "降险部分赚取短债收益。实验性；完整 Phase-0 为后续跟进。")


def _build_active(env, site, built, cards_by_group: dict) -> list:
    """Evaluate the active levered commodity models, add a card to each commodity's group,
    and render its leverage-aware detail page (active_detail.html.j2). Returns the cards."""
    out = []
    for key, m in Ach.MODELS.items():
        ev = Ach.evaluate(key)
        sc = ev["scorecard"]
        card = AR.card(key=key, icon=m["icon"], href=f"strategy_{key}.html",
                       name_en=m["name_en"], name_zh=m["name_zh"],
                       thesis_en=m["thesis_en"], thesis_zh=m["thesis_zh"], sc=sc,
                       extra_en=f"{ev['lev_now']}x {m['bench_en']} · vol-targeted",
                       extra_zh=f"{ev['lev_now']}x {m['bench_zh']} · 波动率目标")
        cards_by_group.setdefault(m["group"], []).append(card)
        out.append(card)
        vm = AR.commodity_detail_vm(ev, built=built, back=_BACK,
                                    caveat=_ACTIVE_CAV, verdict=_ACTIVE_VERDICT[key])
        html = env.get_template("active_detail.html.j2").render(**vm, C=C)
        (site / f"strategy_{key}.html").write_text(html)
    return out


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

    # ACTIVE (vol-targeted, levered) models — the CAGR-beaters, one per gold/silver/copper.
    flat += _build_active(env, site, built, cards_by_group)

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
