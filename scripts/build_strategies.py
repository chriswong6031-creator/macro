"""Strategy Scorecards hub + per-strategy detail pages.

Renders:
  site/strategies.html              — the responsive grid of strategy scorecards
  site/strategy_<key>.html          — one detail page per NEW strategy
and writes data/regime/strategies_latest.json for the landing-hub umbrella card.

The whole point is scalability: this loops engine.strategies.STRATEGIES and reuses the
asset-agnostic harness (validation.backtest_core + equity_alloc.summarize/after_tax/
bear_episodes + the build_spvector Plotly helpers), so a future strategy is just one
more StrategySpec — no new page code.

Byte-identical preservation: the validated S&P / Macro Vector keeps its own bespoke page
(scripts.build_spvector, untouched, run by its own hook in build_vector). Here it is only
listed as a scorecard whose card links to spvector.html — it is NOT re-rendered through
the generic template. The two NEW strategies (Credit Carry, Duration Timing) use
templates/strategy_detail.html.j2.

Run: python -m scripts.build_strategies
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from engine import equity_alloc as ea
from engine import strategies as S
from engine.validation import backtest_core, deflated_sharpe, ret_moments
from lib import config
# Reuse the size-disciplined Plotly helpers + the (now label-parametrized) chart builders.
from scripts.build_spvector import _chart_strategy, _chart_growth, _chart_dd
from scripts.build_vector import C

COST_DEFAULT = 3.0

# per-leg display metadata (colour + 中文) for the NEW strategies' score breakdown
LEG_META = {
    # original three strategies
    "hy_widening": (C["red"], "信用压力（高收益利差走阔）"),
    "recession": (C["amber"], "衰退风险"),
    "vol": ("#7c3aed", "股票波动风险溢价（避险）"),
    "value": (C["blue"], "实际收益率估值（昂贵 → 退避）"),
    "carry": (C["indigo"], "曲线套息（10年 − 3月）"),
    "trend": ("#0891b2", "趋势（时间序列动量）"),
    # suite legs (strategies 4-27)
    "realvol": ("#7c3aed", "已实现波动率（避险）"),
    "abs_mom": (C["indigo"], "绝对动量（低于现金）"),
    "gcross": (C["blue"], "50/200 日均线交叉"),
    "vix_term": (C["red"], "VIX 期限结构（贴水）"),
    "vix_level": (C["amber"], "VIX 水平（避险）"),
    "liquidity": ("#64748b", "净流动性收缩（美联储 − 逆回购）"),
    "curve": (C["indigo"], "收益率曲线衰退触发（10年 − 3月）"),
    "sahm": (C["amber"], "Sahm 失业率衰退触发"),
    "claims": ("#D98C00", "初请失业金上行"),
    "hy_level": ("#D98C00", "高收益利差水平"),
    "nfci": (C["indigo"], "金融条件（紧且收紧）"),
    "anfci": ("#7c3aed", "调整后金融条件"),
    "mom_crash": (C["red"], "动量崩溃护盾（自身波动）"),
    "breadth": ("#0891b2", "广度收窄（等权 vs 市值权重）"),
    "realrate": (C["blue"], "实际收益率上行（黄金逆风）"),
    "dollar": ("#0d9488", "美元走强"),
    "growth": ("#ea580c", "工业增长放缓"),
    "ig_widening": (C["red"], "投资级信用压力（Baa − Aaa 走阔）"),
    "dollar_em": (C["amber"], "新兴市场加权美元走强"),
    "rates_trend": (C["red"], "利率上行（久期逆风）"),
}
# compact stance labels per strategy key (risk asset / cash). Keys not listed fall
# back to the spec's own bench/cash labels in _card — only the awkwardly-long ones
# need an override here.
STANCE = {
    "spvector": ("S&P 500", "标普500", "T-bills", "短债"),
    "credit_carry": ("HY credit", "高收益债", "Treasuries", "国债"),
    "duration_timing": ("long Tsy", "长债", "T-bills", "短债"),
    "ig_carry": ("IG credit", "投资级", "Treasuries", "国债"),
    "em_debt_carry": ("EM debt", "新兴债", "Treasuries", "国债"),
    "flight_to_quality": ("7-10y Tsy", "中期国债", "T-bills", "短债"),
    "equalweight_trend": ("Equal-wt S&P", "等权标普", "T-bills", "短债"),
}

# dial bands (score → label/colour); weights match ea.glide_path defaults (100/66/33/0)
_BANDS = [
    (0, 25, "Calm — fully invested", "平静 — 满仓", "#1FA971", 100, "< 25"),
    (25, 50, "Watch — trim", "关注 — 减仓", C["amber"], 66, "25–50"),
    (50, 75, "Stress — de-risk", "压力 — 降险", "#D98C00", 33, "50–75"),
    (75, 101, "Defensive — all cash", "防守 — 全现金", C["red"], 0, "≥ 75"),
]


def _evaluate(spec: S.StrategySpec, ctx: dict) -> dict:
    """Run one strategy through the shared harness → all building blocks the card and
    the detail page need. Pure compute; no rendering."""
    bench = spec.benchmark(ctx)
    alloc = spec.alloc(ctx, bench)
    cash = spec.cash_yield(ctx)
    sc = ea.summarize(bench, alloc, spec.name_en, cash_yield=cash,
                      cost_bps=spec.cost_bps, bootstrap=False)
    at = ea.after_tax(bench, alloc, cash.reindex(bench.index).ffill().fillna(0.0),
                      st_rate=0.35, cost_bps=spec.cost_bps)
    bt = backtest_core(bench, alloc, cost_bps=spec.cost_bps, cash_yield=cash)
    eq = (1 + bt["net"]).cumprod()
    hodl = (1 + bt["hold"]).cumprod()
    mom = ret_moments(bt["net"])
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=8) if mom else None
    episodes = ea.bear_episodes(bench, 0.20)

    a = alloc.dropna()
    risk_w = round(float(a.iloc[-1]) * 100)
    cash_w = 100 - risk_w
    # current income = blend of risk-asset yield (when invested) + cash yield (de-risked)
    ry = spec.risk_yield(ctx).reindex(bench.index).ffill().dropna()
    cy = cash.reindex(bench.index).ffill().dropna()
    w = risk_w / 100.0
    income = round(w * float(ry.iloc[-1] if len(ry) else 0.0)
                   + (1 - w) * float(cy.iloc[-1] if len(cy) else 0.0), 2)

    sd = spec.score(ctx, bench) if spec.score else None
    score_s = sd["score"].dropna() if sd is not None else pd.Series(dtype=float)
    score = round(float(score_s.iloc[-1])) if len(score_s) else 0

    chg = a.diff()
    sw = chg[chg != 0].dropna()
    last_switch = None
    if len(sw):
        d0 = sw.index[-1]
        last_switch = {"date": d0.strftime("%Y-%m-%d"),
                       "frm": round(float(a.shift(1).loc[d0]) * 100),
                       "to": round(float(a.loc[d0]) * 100)}

    return {"spec": spec, "bench": bench, "alloc": alloc, "cash": cash, "sc": sc,
            "at": at, "dsr": dsr, "eq": eq, "hodl": hodl, "episodes": episodes,
            "risk_w": risk_w, "cash_w": cash_w, "income": income, "score": score,
            "score_series": sd["score"] if sd is not None else None,
            "legs_raw": sd["legs"] if sd is not None else {}, "last_switch": last_switch,
            "asof": bench.index[-1].strftime("%b %d, %Y")}


def _band_by_weight(risk_w: int):
    """Dial band label/colour from the CURRENT (debounced) weight, so the label, the
    allocation bar, and the highlighted rule-book row always agree. (The raw score can
    sit a band away from the weight while the 5-day glide-path debounce catches up —
    the label should describe what the book is actually doing, not the instant reading.)"""
    for _lo, _hi, lab, lab_zh, col, wt, _rng in _BANDS:
        if abs(wt - risk_w) < 1:
            return lab, lab_zh, col
    return _BANDS[0][2], _BANDS[0][3], _BANDS[0][4]


def _bands_table(risk_w: int) -> list[dict]:
    out = []
    for _lo, _hi, lab, lab_zh, _col, wt, rng in _BANDS:
        out.append({"label": lab, "label_zh": lab_zh, "rng": rng, "weight": wt,
                    "cur": abs(wt - risk_w) < 1})
    return out


def _detail_vm(ev: dict, built: str, leg_meta: dict | None = None,
               back_href: str = "strategies.html", back_label: tuple = ("Strategies", "策略")) -> dict:
    """Assemble the view-model for templates/strategy_detail.html.j2 from an _evaluate
    result (used for the NEW strategies; spvector keeps its bespoke page). `leg_meta`
    lets a sibling builder (China / commodities) supply its own leg colour + 中文 map;
    `back_href`/`back_label` point the breadcrumb at the owning grid (defaults = US hub)."""
    leg_meta = leg_meta if leg_meta is not None else LEG_META
    spec = ev["spec"]
    band_label, band_label_zh, band_color = _band_by_weight(ev["risk_w"])
    legs = []
    for name, lg in ev["legs_raw"].items():
        color, label_zh = leg_meta.get(name, (C["muted"], lg["label"]))
        legs.append({**lg, "color": color, "label_zh": label_zh})

    score_on_bench = (ev["score_series"].reindex(ev["bench"].index, method="ffill")
                      if ev["score_series"] is not None else pd.Series(index=ev["bench"].index))
    dd_s = (ev["eq"] / ev["eq"].cummax() - 1) * 100
    dd_h = (ev["hodl"] / ev["hodl"].cummax() - 1) * 100
    charts = {
        "strategy": _chart_strategy(ev["bench"], ev["alloc"], score_on_bench, ev["eq"],
                                    bench_label=spec.bench_en, strat_label=spec.name_en),
        "growth": _chart_growth(ev["eq"], ev["hodl"], strat_label=spec.name_en),
        "dd": _chart_dd(dd_s, dd_h, strat_label=spec.name_en),
    }
    return {
        "s": {"key": spec.key, "icon": spec.icon,
              "name_en": spec.name_en, "name_zh": spec.name_zh,
              "thesis_en": spec.thesis_en, "thesis_zh": spec.thesis_zh,
              "bench_en": spec.bench_en, "bench_zh": spec.bench_zh,
              "cash_en": spec.cash_en, "cash_zh": spec.cash_zh,
              "risk_word_en": spec.risk_word_en, "risk_word_zh": spec.risk_word_zh,
              "experimental": spec.experimental,
              "caveat_en": spec.caveat_en, "caveat_zh": spec.caveat_zh},
        "as_of": ev["asof"], "built": built, "income_now": ev["income"],
        "risk_w": ev["risk_w"], "cash_w": ev["cash_w"], "score": ev["score"],
        "band_label": band_label, "band_label_zh": band_label_zh, "band_color": band_color,
        "last_switch": ev["last_switch"], "legs": legs, "sc": ev["sc"], "at": ev["at"],
        "dsr": ev["dsr"], "bands": _bands_table(ev["risk_w"]), "episodes": ev["episodes"],
        "charts": charts,
        "back_href": back_href, "back_label_en": back_label[0], "back_label_zh": back_label[1],
    }


def _card(ev: dict, stance: dict | None = None) -> dict:
    stance = stance if stance is not None else STANCE
    spec, sc = ev["spec"], ev["sc"]
    rs_en, rs_zh, cs_en, cs_zh = stance.get(spec.key, (spec.bench_en, spec.bench_zh,
                                                       spec.cash_en, spec.cash_zh))
    stance_en = f"{ev['risk_w']}% {rs_en} · {ev['cash_w']}% {cs_en}"
    stance_zh = f"{ev['risk_w']}% {rs_zh} · {ev['cash_w']}% {cs_zh}"
    return {
        "key": spec.key, "icon": spec.icon,
        "href": spec.own_page or f"strategy_{spec.key}.html",
        "name_en": spec.name_en, "name_zh": spec.name_zh,
        "thesis_en": spec.thesis_en, "thesis_zh": spec.thesis_zh,
        "experimental": spec.experimental,
        "cagr": sc["cagr"], "hodl_cagr": sc["hodl_cagr"],
        "sharpe": sc["sharpe"], "hodl_sharpe": sc["hodl_sharpe"],
        "maxdd": sc["maxdd"], "hodl_maxdd": sc["hodl_maxdd"],
        "income": ev["income"], "years": sc["years"],
        "stance_en": stance_en, "stance_zh": stance_zh,
    }


def build() -> str:
    ctx = S._ctx()
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001 — i18n absent -> English-only, still builds
        env.globals.update(td=lambda en: en, tr=lambda en: en)

    site = config.ROOT / config.load()["storage"]["site_dir"]
    cards = []
    for spec in S.STRATEGIES:
        ev = _evaluate(spec, ctx)
        cards.append(_card(ev))
        if spec.own_page is None:        # NEW strategies → render the generic detail page
            html = env.get_template("strategy_detail.html.j2").render(**_detail_vm(ev, built), C=C)
            (site / f"strategy_{spec.key}.html").write_text(html)

    # Pinned "Mastermind Flagships" hero — the 3 multi-asset GTAA cards, fetched from the
    # SAME source build_masterminds renders (engine.masterminds via M.backtest), so the
    # pinned section here and the full masterminds.html hub stay in sync on every build.
    masterminds = []
    try:
        from scripts.build_masterminds import mastermind_cards
        masterminds = mastermind_cards()
    except Exception as e:  # noqa: BLE001 — additive; the hub still builds without the hero
        import logging
        logging.getLogger(__name__).warning("mastermind hero cards unavailable (%s)", e)

    hub = env.get_template("strategies.html.j2").render(cards=cards, masterminds=masterminds,
                                                        built=built, C=C)
    (site / "strategies.html").write_text(hub)

    snap = {"n": len(cards), "built": built,
            "cards": [{"key": c["key"], "name": c["name_en"], "cagr": c["cagr"],
                       "sharpe": c["sharpe"], "maxdd": c["maxdd"], "income": c["income"],
                       "experimental": c["experimental"]} for c in cards]}
    snap_dir = config.data_dir() / "regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "strategies_latest.json").write_text(json.dumps(snap, indent=2))
    return str(site / "strategies.html")


def main() -> int:
    out = build()
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
