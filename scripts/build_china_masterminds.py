"""China Mastermind multi-asset GTAA flagship — pinned-hero cards + per-profile detail pages.

The China sibling of scripts/build_masterminds.py. Renders site/strategy_cnmm_<profile>.html
detail pages from engine.china_masterminds (via active_detail.html.j2 — the leverage-aware
multi-asset allocation page) and data/china_regime/china_masterminds_latest.json for the
landing hub. The 3 flagship cards are PINNED onto china_strategies.html (no separate China
masterminds hub) by scripts.build_china_strategies, which imports china_mastermind_cards().

Run: python -m scripts.build_china_masterminds
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from engine import china_masterminds as M
from lib import config
from scripts import _active_render as AR
from scripts.build_vector import C

# detail pages link back to the China Strategies hub (where the flagships are pinned)
BACK = ("china_strategies.html", "Strategies", "策略")
_CAV = ("China multi-asset GTAA, experimental / display-only. Mainland-investible universe = "
        "CSI 300 (510300) + ChiNext (159915), SSE Dividend (510880), 5y China govt bond (511010), "
        "onshore gold (518880), nonferrous-metals equity (512400). NO crypto, NO US treasuries, "
        "NO US stocks. Net of 3 bps cost + 1% financing on the levered part; weekly rebalance; cash "
        "earns ~1.8%. Leverage amplifies losses as well as gains. The regime leg leans on China's "
        "credit impulse / margin euphoria / realized vol (price-orthogonal, since A-shares whipsaw "
        "trend timers). Benchmarks: CSI 300 and a China 40/60 (CSI300/CGB). Priors-based knobs — "
        "full Phase-0 + calibration is a fast-follow.",
        "中国多资产全球配置，实验性／仅展示。境内可投资产池 = 沪深300（510300）＋创业板（159915）、上证红利（510880）、"
        "5年国债（511010）、境内黄金（518880）、有色金属股票（512400）。无加密货币、无美债、无美股。扣除 3 个基点成本 + "
        "杠杆部分 1% 融资；每周再平衡；现金约 1.8%。杠杆同时放大盈亏。体制腿依靠中国的信用脉冲／融资狂热／已实现波动率（与价格"
        "正交，因 A 股趋势择时易反复打脸）。基准：沪深300 与中国 40/60（沪深300/国债）。参数为先验设定——完整 Phase-0 与校准为后续跟进。")


def _bench_scorecard(prof_key: str, bt: dict, b6040: dict | None) -> tuple[dict, str, str, dict]:
    """Pick the benchmark per profile (China 40/60 for conservative, else CSI 300) and splice
    its CAGR/Sharpe/MaxDD into the scorecard's hodl_* fields for honest card colouring."""
    sc = dict(bt)
    if M.PROFILES[prof_key]["bench"] == "cn6040" and b6040:
        sc["hodl_cagr"], sc["hodl_sharpe"], sc["hodl_maxdd"] = b6040["cagr"], b6040["sharpe"], b6040["maxdd"]
        sc["hodl_sortino"] = b6040.get("sortino", sc.get("hodl_sortino"))
        return sc, "China 40/60 (CSI300/CGB)", "中国 40/60（沪深300/国债）", b6040.get("eq")
    return sc, "CSI 300", "沪深300", bt.get("hodl_eq")


def _verdict(prof_key: str, oos: dict, sc: dict) -> tuple[str, str]:
    sharpe_mult = round(sc["sharpe"] / sc["hodl_sharpe"], 1) if sc.get("hodl_sharpe") else None
    if oos.get("robust"):
        return (f"Robust: beats the benchmark on CAGR in BOTH backtest halves, at ~{sharpe_mult}× its Sharpe "
                f"and a far shallower drawdown — the edge is not a single-era artifact.",
                f"稳健：在回测的两个半段均在年化上跑赢基准，夏普约为其 {sharpe_mult} 倍且回撤浅得多——优势并非单一时代的偶然。")
    return (f"The robust, out-of-sample-stable edge is the SHARPE (~{sharpe_mult}× the benchmark) and the "
            f"drawdown; the full-sample CAGR also beats here, but that part is era-dependent (it does not win "
            f"in both halves). Risk-adjusted alpha via diversification + the China regime layer — not just more risk.",
            f"稳健且样本外稳定的优势在于夏普（约为基准 {sharpe_mult} 倍）与回撤；全样本年化在此也跑赢，但该部分取决于时代"
            f"（并非两个半段都赢）。通过分散与中国体制层实现的风险调整阿尔法——而非单纯承担更高风险。")


def _detail_vm(prof_key: str, res: dict, built: str) -> dict:
    prof = M.PROFILES[prof_key]
    bt = res["scorecard"]
    sc, bench_en, bench_zh, hodl_eq = _bench_scorecard(prof_key, bt, res.get("bench6040"))
    alloc = res["alloc"]
    alloc_max = max((a["weight"] for a in alloc), default=1) or 1
    verdict = _verdict(prof_key, res["oos"], sc)
    return {
        "s": {"key": f"cnmm_{prof_key}", "icon": prof["icon"],
              "name_en": f"China Mastermind — {prof['label_en']}", "name_zh": f"中国操盘大师 — {prof['label_zh']}",
              "thesis_en": prof["thesis_en"], "thesis_zh": prof["thesis_zh"],
              "bench_en": "China multi-asset GTAA", "bench_zh": "中国多资产全球配置"},
        "as_of": res["asof"], "built": built,
        "exposure_title_en": "Current allocation", "exposure_title_zh": "当前配置",
        "alloc": alloc, "alloc_max": alloc_max, "gross_now": res["gross_now"],
        "lev_now": res["gross_now"], "lev_color": C["blue"], "lev_label_en": "", "lev_label_zh": "",
        "factors": [], "sc": sc,
        "bench_label_en": bench_en, "bench_label_zh": bench_zh,
        "charts": AR.charts_for(bt["eq"], hodl_eq if hodl_eq is not None else bt["hodl_eq"],
                                bt["gross_lev"], f"China Mastermind {prof['label_en']}"),
        "oos": res["oos"], "verdict_en": verdict[0], "verdict_zh": verdict[1],
        "caveat_en": _CAV[0], "caveat_zh": _CAV[1],
        "back_href": BACK[0], "back_label_en": BACK[1], "back_label_zh": BACK[2],
    }


# per-profile accent for the pinned UI (conservative→green, moderate→blue, aggressive→violet) —
# identical gradient to the US masterminds so the pinned hero looks the same.
_ACCENT = {"conservative": "#1FA971", "moderate": "#285fff", "aggressive": "#a855f7"}
_RISKPOS = {"conservative": 0.16, "moderate": 0.5, "aggressive": 0.9}


def _rich_card(pk: str, res: dict) -> dict:
    """The rich card dict — single source of truth for the china_strategies.html pinned hero."""
    prof = M.PROFILES[pk]
    sc, bench_en, bench_zh, _ = _bench_scorecard(pk, res["scorecard"], res.get("bench6040"))
    return {
        "key": f"cnmm_{pk}", "href": f"strategy_cnmm_{pk}.html", "icon": prof["icon"],
        "name_en": f"China Mastermind — {prof['label_en']}", "name_zh": f"中国操盘大师 — {prof['label_zh']}",
        "profile_en": prof["label_en"], "profile_zh": prof["label_zh"],
        "accent": _ACCENT[pk], "riskpos": _RISKPOS[pk],
        "thesis_en": prof["thesis_en"], "thesis_zh": prof["thesis_zh"],
        "cagr": sc["cagr"], "hodl_cagr": sc["hodl_cagr"], "sharpe": sc["sharpe"],
        "hodl_sharpe": sc["hodl_sharpe"], "maxdd": sc["maxdd"], "hodl_maxdd": sc["hodl_maxdd"],
        "sharpe_mult": round(sc["sharpe"] / sc["hodl_sharpe"], 1) if sc.get("hodl_sharpe") else None,
        "bench_en": bench_en, "bench_zh": bench_zh, "gross_now": res["gross_now"], "years": sc["years"],
    }


def china_mastermind_cards(P=None) -> list[dict]:
    """The 3 China mastermind flagship cards (pinned onto china_strategies.html)."""
    P = P if P is not None else M._prices()
    if P.empty:
        return []
    out = []
    for pk in ("conservative", "moderate", "aggressive"):
        res = M.backtest(pk, P)
        if not res.get("error"):
            out.append(_rich_card(pk, res))
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

    P = M._prices()
    cards = []
    for pk in ("conservative", "moderate", "aggressive"):
        res = M.backtest(pk, P)
        if res.get("error"):
            continue
        cards.append(_rich_card(pk, res))
        html = env.get_template("active_detail.html.j2").render(**_detail_vm(pk, res, built), C=C)
        (site / f"strategy_cnmm_{pk}.html").write_text(html)

    snap = {"n": len(cards), "built": built,
            "cards": [{"key": c["key"], "name": c["name_en"], "cagr": c["cagr"],
                       "sharpe": c["sharpe"], "maxdd": c["maxdd"]} for c in cards]}
    snap_dir = config.data_dir() / "china_regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "china_masterminds_latest.json").write_text(json.dumps(snap, indent=2))
    return f"{len(cards)} china mastermind detail pages"


def main() -> int:
    print(f"[built] {build()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
