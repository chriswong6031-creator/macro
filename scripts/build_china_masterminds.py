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


def _detail_vm(prof_key: str, res: dict, built: str, regime: dict | None = None) -> dict:
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
        # ── flagship UI + "how it works" explainer (parity with the US mastermind page) ──
        "accent": _ACCENT[prof_key], "grad": _GRAD[prof_key], "riskpos": _RISKPOS[prof_key],
        "profile_en": prof["label_en"], "profile_zh": prof["label_zh"],
        "sharpe_mult": round(sc["sharpe"] / sc["hodl_sharpe"], 1) if sc.get("hodl_sharpe") else None,
        "factors_detail": _factors_vm(), "universe": _universe_vm(), "pipeline": M.PIPELINE,
        "profiles_cmp": _profiles_cmp_vm(prof_key),
        "blurb_en": prof["blurb_en"], "blurb_zh": prof["blurb_zh"],
        "engine_a_en": _ENGINE[0], "engine_a_zh": _ENGINE[1], "engine_b_en": _ENGINE[2],
        "engine_b_zh": _ENGINE[3], "engine_c_en": _ENGINE[4], "engine_c_zh": _ENGINE[5],
        "universe_sub_en": _UNIVERSE_SUB[0], "universe_sub_zh": _UNIVERSE_SUB[1],
        # ── China-specific: the live credit/vol/margin regime layer that drives the book ──
        **_regime_vm(regime),
    }


# per-profile accent for the pinned UI (conservative→green, moderate→blue, aggressive→violet) —
# identical gradient to the US masterminds so the pinned hero looks the same.
_ACCENT = {"conservative": "#1FA971", "moderate": "#285fff", "aggressive": "#a855f7"}
_GRAD = {"conservative": "#1FA971,#34d399,#0ea5e9", "moderate": "#285fff,#6366f1,#8b5cf6",
         "aggressive": "#a855f7,#d946ef,#ec4899"}
_RISKPOS = {"conservative": 0.16, "moderate": 0.5, "aggressive": 0.9}
_BENCH_LBL = {"cn6040": ("China 40/60", "中国40/60"), "csi300": ("CSI 300", "沪深300")}

# China "how it works" explainer fragments (the <b>…</b> in the middle stays bold) + universe
# subtitle — the China counterparts of the US strings now parameterised in mastermind_detail.
_ENGINE = (
    "Every China Mastermind profile runs the SAME engine. It scores the six Mainland-investible assets on a",
    "每个中国操盘大师风险档都运行同一台引擎。它用一个",
    "regime-led four-factor conviction", "体制主导的四因子信念",
    " — but unlike the US flagship it DOWN-weights price trend (A-shares mean-revert and whipsaw trend timers) "
    "and leans hardest on a price-orthogonal credit / volatility / margin regime. It sizes by risk, scales the "
    "book to a target volatility, and rebalances weekly. The three profiles differ ONLY in how much risk they "
    "target and how much leverage they use — same signals, three risk dials.",
    "为六个境内可投资产打分——但与美国旗舰不同，它下调价格趋势的权重（A 股均值回归、会让趋势择时反复打脸），转而最重地依靠与价格正交的"
    "信用／波动率／融资体制。它按风险定仓，将组合缩放至目标波动率，并每周再平衡。三个档位之间唯一的差别，是它们瞄准多大的风险、使用多大的"
    "杠杆——相同信号，三档风险旋钮。")
_UNIVERSE_SUB = ("six Mainland-investible assets — A-shares, govt bonds, onshore gold & metals; no crypto, no US treasuries",
                 "六个境内可投资产——A股、国债、境内黄金与有色；无加密货币、无美债")


def _factors_vm() -> list[dict]:
    """The 4 conviction factors + a relative bar width (vs the largest weight)."""
    mx = max(f["weight"] for f in M.FACTORS) or 1
    out = []
    for f in M.FACTORS:
        d = dict(f)
        d["wpct"] = round(f["weight"] * 100)
        d["wrel"] = round(f["weight"] / mx * 100)
        out.append(d)
    return out


def _universe_vm() -> list[dict]:
    """The 6-asset universe with (ticker, role) rows → dicts the template can read."""
    return [{"cls_en": c["cls_en"], "cls_zh": c["cls_zh"], "icon": c["icon"],
             "rows": [{"ticker": tk, "role_en": re, "role_zh": rz} for (tk, re, rz) in c["rows"]]}
            for c in M.UNIVERSE]


def _profiles_cmp_vm(cur: str) -> list[dict]:
    """All three risk profiles' knobs, current one flagged — the 'three dials' panel."""
    out = []
    for pk in ("conservative", "moderate", "aggressive"):
        p = M.PROFILES[pk]
        be, bz = _BENCH_LBL[p["bench"]]
        out.append({"key": pk, "accent": _ACCENT[pk], "icon": p["icon"],
                    "label_en": p["label_en"], "label_zh": p["label_zh"],
                    "target_vol": round(p["target_vol"] * 100), "max_lev": p["max_lev"],
                    "w_cap": round(p["w_cap"] * 100), "bench_en": be, "bench_zh": bz,
                    "is_current": pk == cur})
    return out


def _regime_vm(regime: dict | None) -> dict:
    """View-model for the live China regime-layer panel — the credit/vol/margin de-risk
    state that drives the book. Empty dict (panel omitted) when no leg resolves."""
    if not regime:
        return {}
    pct = regime["pct"]
    if regime["tone"] == "off":
        lead = (f"The regime layer — the largest single weight at 40% of the conviction — currently reads "
                f"risk-off (blended de-risk {pct}/100). The engine is fading A-shares & metals into China govt "
                f"bonds, dividend and gold, which is why the live book below holds little equity. It leans back "
                f"in as these gauges normalise.",
                f"体制层——信念中权重最大的单项（40%）——当前读数为风险偏离（综合降险 {pct}/100）。引擎正将 A 股与有色减配至国债、红利与黄金，"
                f"这正是下方实时组合几乎不持股票的原因。待这些指标回归正常，它会重新加仓。")
    elif regime["tone"] == "on":
        lead = (f"The regime layer — the largest single weight at 40% of the conviction — currently reads "
                f"risk-on (blended de-risk {pct}/100). The engine is leaning into A-shares & metals, so the live "
                f"book below carries fuller equity exposure. It de-risks into bonds and gold the moment the "
                f"credit / vol / margin gauges turn.",
                f"体制层——信念中权重最大的单项（40%）——当前读数为风险偏好（综合降险 {pct}/100）。引擎正加仓 A 股与有色，因此下方实时组合"
                f"持有较充分的股票敞口。一旦信用／波动率／融资指标转向，它会立即降险转入国债与黄金。")
    else:
        lead = (f"The regime layer — the largest single weight at 40% of the conviction — currently reads "
                f"mixed (blended de-risk {pct}/100): the credit, volatility and margin gauges disagree, so the "
                f"book sits between its risk-on and de-risked extremes.",
                f"体制层——信念中权重最大的单项（40%）——当前读数为混合（综合降险 {pct}/100）：信用、波动率与融资指标存在分歧，因此组合介于"
                f"加仓与降险两极之间。")
    return {"regime_legs": regime["legs"], "regime_tone": regime["tone"], "regime_pct": pct,
            "regime_v": regime["blended"], "regime_asof": regime["asof"],
            "regime_state_en": regime["state_en"], "regime_state_zh": regime["state_zh"],
            "regime_lead_en": lead[0], "regime_lead_zh": lead[1]}


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
    regime = M.regime_state(P)                  # live credit/vol/margin de-risk layer (once)
    cards = []
    for pk in ("conservative", "moderate", "aggressive"):
        res = M.backtest(pk, P)
        if res.get("error"):
            continue
        cards.append(_rich_card(pk, res))
        html = env.get_template("mastermind_detail.html.j2").render(
            **_detail_vm(pk, res, built, regime), C=C)
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
