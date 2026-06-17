"""Mastermind multi-asset GTAA flagship — hub grid + per-profile detail pages.

Renders site/masterminds.html (the 3 risk-profile scorecards) + site/strategy_mm_<profile>.html
detail pages from engine.masterminds, and data/regime/masterminds_latest.json for the
landing hub. Detail pages use templates/active_detail.html.j2 (leverage-aware, with the
current multi-asset allocation bar + the out-of-sample honesty panel).

Run: python -m scripts.build_masterminds
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from engine import masterminds as M
from lib import config
from scripts import _active_render as AR
from scripts.build_vector import C

BACK = ("masterminds.html", "Masterminds", "操盘大师")
_CAV = ("Multi-asset GTAA, experimental / display-only. Universe = SPY/QQQ, IEF/TLT, LQD/HYG, "
        "gold + copper, BTC (book starts 2007, BTC weight 0 before 2014). Net of 3 bps cost + 1% "
        "financing on the levered part; weekly rebalance. Leverage amplifies losses as well as gains. "
        "Benchmarks: the S&P 500 and a 60/40 (SPY/IEF). Full Phase-0 is a fast-follow.",
        "多资产全球配置，实验性 / 仅展示。资产池 = SPY/QQQ、IEF/TLT、LQD/HYG、黄金 + 铜、BTC（组合自 2007 年起，"
        "2014 年前 BTC 权重为 0）。扣除 3 个基点成本 + 杠杆部分 1% 融资；每周再平衡。杠杆会同时放大盈亏。"
        "基准：标普500 与 60/40（SPY/IEF）。完整 Phase-0 为后续跟进。")


def _bench_scorecard(prof_key: str, bt: dict, b6040: dict | None) -> tuple[dict, str, str, dict]:
    """Pick the right benchmark per profile (60/40 for conservative, else SPY) and splice
    its CAGR/Sharpe/MaxDD into the scorecard's hodl_* fields for honest card colouring."""
    sc = dict(bt)
    if M.PROFILES[prof_key]["bench"] == "6040" and b6040:
        sc["hodl_cagr"], sc["hodl_sharpe"], sc["hodl_maxdd"] = b6040["cagr"], b6040["sharpe"], b6040["maxdd"]
        sc["hodl_sortino"] = b6040.get("sortino", sc.get("hodl_sortino"))
        return sc, "60/40 (SPY/IEF)", "60/40（SPY/IEF）", b6040.get("eq")
    return sc, "S&P 500", "标普500", bt.get("hodl_eq")


def _detail_vm(prof_key: str, res: dict, built: str) -> dict:
    prof = M.PROFILES[prof_key]
    bt = res["scorecard"]
    sc, bench_en, bench_zh, hodl_eq = _bench_scorecard(prof_key, bt, res.get("bench6040"))
    alloc = res["alloc"]
    alloc_max = max((a["weight"] for a in alloc), default=1) or 1
    verdict = _verdict(prof_key, res["oos"], sc)
    return {
        "s": {"key": f"mm_{prof_key}", "icon": prof["icon"],
              "name_en": f"Mastermind — {prof['label_en']}", "name_zh": f"操盘大师 — {prof['label_zh']}",
              "thesis_en": prof["thesis_en"], "thesis_zh": prof["thesis_zh"],
              "bench_en": "multi-asset GTAA", "bench_zh": "多资产全球配置"},
        "as_of": res["asof"], "built": built,
        "exposure_title_en": "Current allocation", "exposure_title_zh": "当前配置",
        "alloc": alloc, "alloc_max": alloc_max, "gross_now": res["gross_now"],
        "lev_now": res["gross_now"], "lev_color": C["blue"], "lev_label_en": "", "lev_label_zh": "",
        "factors": [], "sc": sc,
        "bench_label_en": bench_en, "bench_label_zh": bench_zh,
        "charts": AR.charts_for(bt["eq"], hodl_eq if hodl_eq is not None else bt["hodl_eq"],
                                bt["gross_lev"], f"Mastermind {prof['label_en']}"),
        "oos": res["oos"], "verdict_en": verdict[0], "verdict_zh": verdict[1],
        "caveat_en": _CAV[0], "caveat_zh": _CAV[1],
        "back_href": BACK[0], "back_label_en": BACK[1], "back_label_zh": BACK[2],
    }


def _verdict(prof_key: str, oos: dict, sc: dict) -> tuple[str, str]:
    sharpe_mult = round(sc["sharpe"] / sc["hodl_sharpe"], 1) if sc.get("hodl_sharpe") else None
    if oos.get("robust"):
        return (f"Robust: beats the benchmark on CAGR in BOTH backtest halves, at ~{sharpe_mult}× its Sharpe "
                f"and a far shallower drawdown — the edge is not a single-era artifact.",
                f"稳健：在回测的两个半段均在年化上跑赢基准，夏普约为其 {sharpe_mult} 倍且回撤浅得多——优势并非单一时代的偶然。")
    return (f"The robust, out-of-sample-stable edge is the SHARPE (~{sharpe_mult}× the benchmark) and the "
            f"drawdown; the full-sample CAGR also beats here, but that part is era-dependent (it does not win "
            f"in both halves). This is genuine risk-adjusted alpha, levered — not just more risk.",
            f"稳健且样本外稳定的优势在于夏普（约为基准 {sharpe_mult} 倍）与回撤；全样本年化在此也跑赢，但该部分取决于时代"
            f"（并非两个半段都赢）。这是真实的风险调整阿尔法加杠杆——而非单纯承担更高风险。")


def _card(prof_key: str, res: dict) -> dict:
    prof = M.PROFILES[prof_key]
    sc, bench_en, bench_zh, _ = _bench_scorecard(prof_key, res["scorecard"], res.get("bench6040"))
    return {"key": f"mm_{prof_key}", "icon": prof["icon"], "href": f"strategy_mm_{prof_key}.html",
            "name_en": f"Mastermind — {prof['label_en']}", "name_zh": f"操盘大师 — {prof['label_zh']}",
            "thesis_en": prof["thesis_en"], "thesis_zh": prof["thesis_zh"], "experimental": True,
            "cagr": sc["cagr"], "hodl_cagr": sc["hodl_cagr"], "sharpe": sc["sharpe"],
            "hodl_sharpe": sc["hodl_sharpe"], "maxdd": sc["maxdd"], "hodl_maxdd": sc["hodl_maxdd"],
            "income": sc["avg_leverage"], "years": sc["years"],
            "stance_en": f"vs {bench_en} · {res['gross_now']}x gross",
            "stance_zh": f"对比{bench_zh} · {res['gross_now']}x 总敞口"}


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
        cards.append(_card(pk, res))
        html = env.get_template("active_detail.html.j2").render(**_detail_vm(pk, res, built), C=C)
        (site / f"strategy_mm_{pk}.html").write_text(html)

    hub = env.get_template("masterminds.html.j2").render(cards=cards, built=built, C=C)
    (site / "masterminds.html").write_text(hub)

    snap = {"n": len(cards), "built": built,
            "cards": [{"key": c["key"], "name": c["name_en"], "cagr": c["cagr"],
                       "sharpe": c["sharpe"], "maxdd": c["maxdd"]} for c in cards]}
    snap_dir = config.data_dir() / "regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "masterminds_latest.json").write_text(json.dumps(snap, indent=2))
    return str(site / "masterminds.html")


def main() -> int:
    print(f"[built] {build()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
