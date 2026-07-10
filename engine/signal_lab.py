"""Signal Lab — the honest, consolidated validation scorecard.

The dashboard already runs an institutional-grade validation battery
(``engine.validation``: deflated Sharpe, purged k-fold + embargo, block
bootstrap, Newey-West HAC t-stats, Benjamini-Hochberg FDR, Brier/Platt
calibration, cost-aware backtests) across ~25 ``scripts/*_phase0.py`` /
``validate_*.py`` harnesses.  The verdicts have lived only in ``reports/*.md``
and a ``data/edgar/ic_scorecard.json`` wired to nothing.

This module assembles those verdicts into ONE structured payload so a single
page can show, per signal: rank-IC, IC-IR, Newey-West HAC t, BH-FDR q,
Deflated Sharpe, backtest Sharpe, hit-rate, n — and crucially the *verdict*,
including the signals we **measured and refused to ship**.  Publishing the
graveyard is the point: it is the difference between a dashboard and a model.

It is a pure assembler — no new computation, no new data.  The 11-factor
cross-section is read LIVE from ``ic_scorecard.json`` so it stays current; the
rest is a curated registry whose every number is quoted from a named report in
``reports/`` (the ``source`` field), so the page is auditable.

Tiers
-----
``scored``    validated AND wired into a number (allocation / composite / score)
``confirmer`` measured forward edge, used as context/tiebreaker, not a sizer
``display``   shown but NO validated standalone edge (failed Phase-0 / un-testable)
``killed``    measured and refused to ship (NO-GO)
``pending``   validated but the code/wiring lives in a worktree/PR, not this branch
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

from engine.signal_frontier_docket import page_frontier_rows, phase0_summary
from lib import config

# Tier metadata: order on the page + bilingual labels + a one-line honest blurb.
TIERS: list[dict] = [
    {"key": "scored", "label": "Scored — validated & wired into a number",
     "label_zh": "已计分 — 通过验证并纳入计算",
     "blurb": "Passed the validation battery AND drives an allocation, composite or score.",
     "blurb_zh": "通过验证电池，并实际驱动配置、综合分或评分。"},
    {"key": "confirmer", "label": "Confirmer / context — validated, but not a standalone sizer",
     "label_zh": "确认/背景 — 已验证，但非独立定量信号",
     "blurb": "A measured forward edge used as context or a tiebreaker — never sized on its own.",
     "blurb_zh": "有可测的前瞻性边际，用作背景或加分项 — 但不单独定仓。"},
    {"key": "display", "label": "Display-only — shown, but no validated edge",
     "label_zh": "仅展示 — 显示但无验证边际",
     "blurb": "Rendered as a research lens or risk context. Failed Phase-0, un-backtestable, "
              "or still accruing history. NOT a buy signal.",
     "blurb_zh": "作为研究视角或风险背景显示。未通过 Phase-0、无法回测或历史不足。并非买入信号。"},
    {"key": "killed", "label": "Killed (NO-GO) — measured and refused to ship",
     "label_zh": "已否决 (NO-GO) — 经测量后拒绝上线",
     "blurb": "The graveyard. Each looked plausible; the validation said no. This is the "
              "discipline most dashboards never show.",
     "blurb_zh": "信号墓地。每个看似合理，验证却说不。这是大多数仪表盘从不展示的纪律。"},
    {"key": "pending", "label": "Validated — pending wiring on this branch",
     "label_zh": "已验证 — 本分支待接入",
     "blurb": "Passed validation but the code/wiring lives in a worktree or open PR, not yet on "
              "the branch this page was built from.",
     "blurb_zh": "已通过验证，但代码/接线位于工作树或待合并 PR，尚未进入本页所基于的分支。"},
]

# Verdict word shown in the table's verdict cell, per tier.
VERDICT_WORD = {
    "scored": ("SCORED", "已计分"),
    "confirmer": ("CONFIRMER", "确认项"),
    "display": ("DISPLAY", "仅展示"),
    "killed": ("NO-GO", "否决"),
    "pending": ("PENDING", "待接入"),
}


def _name_to_slug(name: str) -> str:
    """Stable ASCII kebab slug for per-row anchor ids (A8).

    Only ASCII alphanumerics and hyphens; collapses runs of non-alnum to a single
    hyphen; strips leading/trailing hyphens.  Stable: the same name always gives
    the same slug across builds.
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80]


def _row(name, name_zh, market, tier, why, why_zh, source, *, horizon="",
         ic=None, ic_ir=None, t_hac=None, q_fdr=None, dsr=None, sharpe=None,
         hit=None, n=None, fdr_survivor=None, wired="", extra=None,
         dsr_family=None, dsr_n_trials=None, dsr_basis=None, dsr_expiry=None) -> dict:
    """One scorecard row. Numeric fields are floats or None (None => '—').

    DSR PROVENANCE (W1d, audit #21): a quoted DSR is only honest if its multiple-testing
    n_trials reflects the real search space. ``dsr_family`` names the Trial-Ledger family the
    n_trials should come from; ``dsr_n_trials`` is the number as quoted in ``source``;
    ``dsr_basis`` stamps how that number was fixed — ``'ledger'`` (sourced live at build from
    the ledger), ``'frozen-quote'`` (a hardcoded quote pending re-derivation) — and
    ``dsr_expiry`` date-stamps a frozen-quote per the passport rule. ``build_scorecard``
    prefers the live ledger count when ``dsr_family`` resolves, else surfaces the frozen quote
    with its expiry so a stale self-certifying number is visibly stale rather than trusted."""
    return {
        "name": name, "name_zh": name_zh, "market": market, "tier": tier,
        "horizon": horizon, "ic": ic, "ic_ir": ic_ir, "t_hac": t_hac,
        "q_fdr": q_fdr, "dsr": dsr, "sharpe": sharpe, "hit": hit, "n": n,
        "fdr_survivor": fdr_survivor, "wired": wired,
        "why": why, "why_zh": why_zh, "source": source,
        "extra": extra or [],   # list of (label, value_str) quoted context stats
        "dsr_family": dsr_family, "dsr_n_trials": dsr_n_trials,
        "dsr_basis": dsr_basis, "dsr_expiry": dsr_expiry,
        "slug": _name_to_slug(name),  # A8: stable anchor id
    }


# --- The curated registry -----------------------------------------------------
# Every number here is quoted from the report named in ``source``. The 11-factor
# cross-section is appended LIVE from ic_scorecard.json by build_scorecard().
REGISTRY: list[dict] = [
    # ---- SCORED -------------------------------------------------------------
    _row("S&P / Macro Vector (macro-timed equity sleeve)",
         "标普／宏观向量（择时股票仓位）", "US macro", "scored",
         why="The strongest validated object in the system. Survives every gate: DSR 0.9994 "
             "at n_trials=30, leave-one-crisis-out edge in all 4 crises, split-half consistent, "
             "permutation-null skill p=0.0, and holds on genuine point-in-time (ALFRED) data "
             "(Sharpe 0.90 vs 0.92). The edge is drawdown + Sharpe, not CAGR: carry-stripped "
             "CAGR (10.56%) ≈ buy-and-hold; MaxDD −33% vs −55%.",
         why_zh="系统中验证最扎实的对象。通过所有关卡：n_trials=30 下 DSR 0.9994、四次危机逐一剔除仍有边际、"
                "两半一致、置换零假设技能 p=0.0，且在真实时点（ALFRED）数据上仍成立。边际在回撤与夏普，而非 CAGR。",
         source="spvector-phase1/2/3-audit/pit.md", horizon="allocation (daily)",
         dsr=0.9994, sharpe=0.92, wired="spvector.html / vector_allocation",
         # W1d passport: the "n_trials=30" is sourced LIVE from the spvector Trial-Ledger family
         # when calibrate_spvector* has run into the persistent ledger; otherwise it renders as
         # a frozen quote with an expiry (not a self-certifying constant).
         dsr_family="spvector", dsr_n_trials=30, dsr_basis="frozen-quote", dsr_expiry="2026-09-30",
         extra=[("MaxDD", "−33.2% vs −55.2% B&H"), ("Sharpe 95% CI", "[0.61, 0.93, 1.25]"),
                ("split-half", "0.83 / 1.02"), ("perm-null skill p", "0.0"),
                ("PIT (ALFRED) Sharpe", "0.90")]),
    _row("China reversal (3-month, within-sector)",
         "中国反转（3个月，行业内）", "China A", "scored",
         why="The honest A-share edge. Deepest-decliners quintile, NO confirmation gating "
             "(turn-confirmation and quality filters both HURT it). Beats 1-month reversal "
             "(0.38) and momentum (0.03 — dead). High turnover and deep drawdowns are the cost.",
         why_zh="A股真实的边际。最深下跌分位，不加确认门槛（确认与质量过滤都会削弱它）。优于 1 个月反转与动量（动量已失效）。",
         source="china-reversal-phase0.md", horizon="21d / monthly",
         sharpe=0.58, hit=0.564, n=413,
         wired="china.html standout / china_axes",
         extra=[("monthly excess", "+0.558%"), ("MaxDD", "−37.6%")]),
    _row("Recession-risk composite (jobless-claims folded in)",
         "衰退风险综合（已并入初请失业金）", "US macro", "scored",
         why="Jobless-claims leg validated vs NBER 1967–2026 (beats the Sahm leg standalone, "
             "+AUC every horizon, survives both split-halves and PIT/ALFRED) → it REPLACES "
             "Sahm as the labor leg in the scored recession composite.",
         why_zh="初请失业金腿相对 NBER 1967–2026 验证（独立优于 Sahm，各期限 AUC 提升，两半与时点数据均成立）→ 取代 Sahm 成为衰退综合中的就业腿。",
         source="bonds-calibration.md + validate_claims_recession*.py", horizon="multi-month",
         ic=0.531, wired="recession_risk (MRS scoring)",
         extra=[("target", "NBER recession"), ("vs Sahm", "replace > augment > Sahm-only")]),
    _row("Bond-health drawdown gauge",
         "债券健康回撤量表", "US macro", "scored",
         why="Beat the composite's own best single leg on forward S&P drawdown (recursive "
             "improvement). High-tercile P(−10% in fwd window) 0.244 vs 0.127 base (+11.7pp).",
         why_zh="在前瞻标普回撤上优于综合自身最佳单腿。高三分位 P(前瞻−10%) 0.244 对基线 0.127（+11.7pp）。",
         source="bonds-calibration.md", horizon="forward drawdown",
         ic=0.234, wired="bonds.html health composite",
         extra=[("hi-tercile uplift", "+11.7pp"), ("MOVE leg IC", "0.168 (confirmed)")]),

    # ---- CONFIRMER / CONTEXT ------------------------------------------------
    _row("Cross-sectional momentum / trend  (dual-panel re-validation)",
         "横截面动量／趋势（双面板复验）", "US S&P (deep)", "confirmer",
         why="Independent dual-panel, sector- & market-neutral forward-IC re-measurement of the "
             "momentum/trend cohort (mom_12_1, ma200_slope, volscaled_mom). Robust on the 64y "
             "deep panel — t_HAC ≈ 3, sign-stable across 4 sub-periods AND across panels — but "
             "FAILS the Deflated-Sharpe multiple-testing gate (best DSR 0.47<0.90), so it is a "
             "CONTEXT tilt, not a standalone sizer. Reproduces the live model's calibration: "
             "stock_score weights momentum at the 0.10 context weight, regime-scaled (0.28 calm / "
             "0.04 stress). Reversal legs flip sign (fragile / panel-artifact); the prior "
             "survivor-panel 'mean-reversion dominates' read was a survivorship artifact.",
         why_zh="对动量/趋势组（mom_12_1、ma200_slope、volscaled_mom）的独立双面板、行业与市场中性前瞻 IC 复测。"
                "在 64 年深度面板稳健（t_HAC≈3，四个子区间及跨面板符号一致），但未通过紧缩夏普多重检验门槛"
                "（最佳 DSR 0.47<0.90）→ 仅为背景倾斜，非独立定仓。复现实盘校准：stock_score 以 0.10 背景权重"
                "按régime缩放（平稳 0.28／承压 0.04）。反转腿符号翻转（脆弱/面板假象）。",
         source="STRATEGY_LAB_VALIDATION.md", horizon="63d / monthly",
         ic=0.033, ic_ir=0.17, t_hac=3.01, dsr=0.47, hit=0.588, n=767,
         fdr_survivor=False, wired="stock_score selection (regime-scaled context weight)",
         extra=[("ma200_slope IC-IR", "0.191 (t 3.29)"), ("volscaled_mom IC-IR", "0.165"),
                ("crowding fwd-MAE p10", "−23.7% top-decile vs −19.5% rest → drawdown risk"),
                ("21d extension legs", "live_dist_50dma t −5.1 (don't-chase)")]),
    _row("Insider buying  net_usd_mcap | SN  (mid-cap)",
         "内部人买入 net_usd_mcap | SN（中小盘）", "US S&P1500", "confirmer",
         why="The ONLY cross-sectional stock factor that survives BH-FDR in the leak-free PIT "
             "panel (q=0.0999) — but in the mid-cap habitat, and DSR is borderline (0.53<0.90), "
             "and long-only beats L/S. Orthogonal to momentum/size/reversal → shipped as a "
             "conviction confirmer chip, NOT a standalone sizer.",
         why_zh="唯一在无泄漏时点面板中通过 BH-FDR 的横截面个股因子（q=0.0999）— 但仅限中小盘，且 DSR 临界（0.53<0.90），"
                "多头优于多空。与动量/规模/反转正交 → 作为信心确认标签上线，而非独立定仓。",
         source="insider-phase0/1.md", horizon="21d + 63d",
         ic=0.0289, ic_ir=0.334, t_hac=2.903, q_fdr=0.0999, dsr=0.5253,
         sharpe=0.55, hit=0.629, n=170, fdr_survivor=True,
         wired="factors.html + standout 👤 chip"),
    _row("US macro regime quad (Goldilocks/Reflation/…)",
         "美国宏观四象限", "US macro", "confirmer",
         why="Whipsaw 6% of changes <10 days (target <15%) and transitions align with every "
             "major crisis (COVID flagged 2020-02-19). The structural backbone of the Vector "
             "de-risk glide — not a standalone return predictor.",
         why_zh="6% 的切换在 10 天内（目标 <15%），且转变与每次重大危机吻合（COVID 于 2020-02-19 标记）。是向量降险的结构骨架，非独立收益预测。",
         source="validation.md", horizon="regime state",
         wired="macro.html / spvector input",
         extra=[("whipsaw <10d", "6% (PASS)"), ("regime changes", "149")]),
    _row("China / HK regime quad + liquidity overlay",
         "中港四象限 + 流动性叠加", "China A / HK", "confirmer",
         why="Forward-return differentiated and split-half stable for most regimes (China "
             "Growth-scare +6.09% vs Reflation −2.85% fwd-63d; liquidity Expanding 1.71% vs "
             "Contracting 0.59%). HK Reflation/Stagflation signs flip across halves → flagged "
             "regime-unstable. Used as a drawdown/risk lens.",
         why_zh="多数象限前瞻收益有区分且两半稳定（中国 增长恐慌 +6.09% 对 再通胀 −2.85%）。港股部分象限两半符号翻转 → 标记不稳定。用作回撤/风险视角。",
         source="china-calibration.md / hk-calibration.md", horizon="63d",
         wired="china.html / hk.html"),
    _row("HK global-risk overlay (risk-on/off)",
         "港股全球风险叠加", "HK", "confirmer",
         why="Differentiates forward returns by global risk state and stays stable across "
             "split-halves: risk-on +1.9% (hit 58.1%) vs risk-off +0.84% fwd-63d. HK is a "
             "macro/global-beta product, not stock selection.",
         why_zh="按全球风险状态区分前瞻收益且两半稳定：风险偏好 +1.9%（命中 58.1%）对风险规避 +0.84%（63日）。港股是宏观/全球贝塔产品。",
         source="hk-calibration.md", horizon="63d",
         wired="hk.html",
         extra=[("risk-on / off / neutral fwd-63d", "+1.9% / +0.84% / +0.36%")]),
    _row("Commodity risk index (gold/silver/copper/oil)",
         "大宗商品风险指数", "Commodity", "confirmer",
         why="The risk_index is a CONFIRMED near-term drawdown gauge across BOTH split-halves "
             "for all four metals/energy; the gold-silver-ratio percentile band-differentiates "
             "forward returns. The ALLOCATION variants, by contrast, all fail DSR (see below).",
         why_zh="risk_index 在四种金属/能源上、两半均确认为近端回撤量表；金银比分位对前瞻收益有区分。但其配置变体均未通过 DSR（见下）。",
         source="commodity-calibration.md", horizon="21d",
         wired="commodities.html risk gauge"),
    _row("Index dealer-gamma regime (market GEX)",
         "指数做市商Gamma机制（市场GEX）", "US options", "confirmer",
         why="Validated at the INDEX level: short-gamma days precede higher forward realized "
             "vol than long-gamma days → a vol-regime banner. Per-equity GEX was evaluated and "
             "DECLINED (single-name sign too noisy).",
         why_zh="在指数层面验证：空Gamma日的前瞻已实现波动高于多Gamma日 → 波动机制横幅。个股 GEX 经评估后否决（单名符号过噪）。",
         source="gex-validation.md", horizon="intraday/days",
         wired="macro.html market-gamma note",
         extra=[("history", "accruing (n small)")]),
    _row("Cross-asset TSMOM — masterminds GTAA workhorse (W=0.45)",
         "跨资产时间序列动量 — masterminds GTAA 主力因子（权重0.45）", "Cross-asset", "scored",
         why="Cross-asset trend is the 0.45-weighted PRIMARY factor of the validated, served "
             "masterminds GTAA (engine/masterminds.py, cross_asset_trend.tsmom_alloc) — a live "
             "allocation that beats SPY on Sharpe (1.07 vs 0.62) and MaxDD (−24.1% vs −55.2%) over "
             "19y with OOS-stable Sharpe in BOTH halves (0.98 / 1.15). My phase0 independently "
             "confirms the diversified-trend sleeve as a drawdown overlay: DSR 0.9952, survives "
             "purged-CV + leave-one-crisis-out, executable ETF-only cuts a 60/40 book's MaxDD "
             "−10pp. Honest: the Sharpe/drawdown edge is the robust OOS part; the raw-CAGR beat is "
             "era-dependent. (Standalone leverage-free trend ≈ buy&hold — the display row below.)",
         why_zh="跨资产趋势是已验证、已上线的 masterminds GTAA 的 0.45 权重主力因子——该实盘配置19年间在夏普"
                "（1.07 对 0.62）与最大回撤（−24.1% 对 −55.2%）上跑赢标普，且两半样本外夏普均稳健（0.98 / 1.15）。"
                "我的 phase0 独立确认多元趋势作为回撤叠加：DSR 0.9952，通过净化CV与逐危机剔除，纯ETF版将60/40回撤削减约10pp。"
                "诚实说明：夏普/回撤优势为稳健的样本外部分，原始CAGR超额依赖时代。（无杠杆独立趋势≈买入持有，见下方仅展示行。）",
         source="tsmom-overlay-phase0.md / masterminds.py", horizon="GTAA allocation (weekly)",
         dsr=0.9952, sharpe=1.07, wired="masterminds.html GTAA — TREND factor (W=0.45)",
         extra=[("GTAA Moderate", "Sharpe 1.07 vs SPY 0.62 · MaxDD −24.1% vs −55.2% · 19y"),
                ("OOS Sharpe halves", "0.98 / 1.15 (both beat SPY)"),
                ("trend-overlay confirm", "DSR 0.995 · purged-CV + leave-one-crisis-out"),
                ("standalone sleeve", "≈ buy&hold (display row)")]),
    _row("Quad × NFCI-direction scenario odds",
         "宏观四象限 × NFCI方向 情景胜率", "US macro", "confirmer",
         why="Conditioning forward SPY odds on the regime quad × NFCI direction reproduces the "
             "measured split: Q1/Q2 with NFCI loosening 74.8% hit / +3.18% fwd-63d vs tightening "
             "38.3% / −5.69% (HAC t on the loosening leg +7.0). A flat-when-tight overlay shows "
             "DSR 0.9991 and cuts MaxDD −55%→−49% — BUT NFCI tight-and-tightening fires on ~5% of "
             "days and ZERO times post-2012, so the effective-N is ~2 pre-2012 crises. Already "
             "half-wired as the dial's NFCI rule; shipped as a scenario-odds CONFIRMER, not a "
             "high-confidence standalone.",
         why_zh="按宏观四象限×NFCI方向条件化前瞻标普胜率，复现既测分化：Q1/Q2 且 NFCI 宽松命中 74.8%/63日 +3.18%，"
                "紧缩则 38.3%/−5.69%（宽松腿 HAC t +7.0）。但 NFCI 紧且收紧仅约5%交易日触发，2012年后从未触发 → "
                "有效样本仅约2次危机。已部分接入仪表盘 NFCI 规则；作为情景胜率确认项上线，而非高置信独立信号。",
         source="quad-nfci-phase0.md", horizon="63d",
         hit=0.748, n=5700, wired="macro.html dial (NFCI rule) + signal_lab odds",
         extra=[("Q1/Q2 loose vs tight hit", "74.8% vs 38.3%"), ("HAC t (loosening)", "+7.0"),
                ("caveat", "tight fires ~5% days, 0 post-2012")]),

    _row("Repo/SOFR tail stress (p99 dispersion)",
         "回购/SOFR尾部压力（p99分散度）", "US macro", "confirmer",
         why="p99-dispersion composite of SOFR/repo spreads predicts S&P ≥5% drawdown onset "
             "with AUC 0.61 at 21d horizon — above the 0.50 coin-flip baseline and above a "
             "VIX-matching baseline. LOO-stable across sub-periods (leave-one-out subsample "
             "consistency). Study produces a drawdown predictor, not a cross-sectional "
             "return predictor: ic/t_hac/q_fdr are not defined for this study design and are "
             "left None. No score impact; recommended for risk-radar de-escalation panel "
             "candidacy pending program review.",
         why_zh="SOFR/回购利差 p99 分散度综合指标在 21 日期限内预测标普≥5% 回撤，AUC=0.61，"
                "高于掷硬币基线（0.50）和 VIX 匹配基线，且剔除子区间后保持稳健（LOO一致）。"
                "本研究为回撤预测设计，非横截面收益研究，故 ic/t_hac/q_fdr 均留 None。"
                "无评分影响；待项目审议后纳入风险雷达降级面板候选。",
         source="reports/slf056-funding-tail-phase0.md", horizon="21d drawdown onset",
         wired="none — risk-radar de-escalation panel candidacy pending program review",
         dsr_family="slf056_funding_tail",
         extra=[("AUC (21d drawdown ≥5%)", "0.61"), ("LOO-stable", "yes"),
                ("vs VIX baseline", "beats"), ("n trials in ledger", "14"),
                ("score impact", "none — display-only")]),

    # ---- DISPLAY-ONLY -------------------------------------------------------
    _row("Impulse Tracker (early-ignition screen)",
         "冲量追踪（早期点火扫描）", "US S&P1500", "display",
         why="A reactive screen for price/volume velocity + acceleration that surfaces names "
             "whose impulse is JUST firing while an entry still exists (small recent run-up, not "
             "stretched), and demotes names that already ran. Honest status: NOT a validated "
             "alpha and no P(up) is claimed — short-horizon direction is a measured coin-flip "
             "(engine/velocity.py) and momentum's edge is regime-switched (decays in stress), so "
             "this is a timing/context narrowing tool, regime-flagged, never a scored input. The "
             "ranking composite is fixed and legible (no learned weights); a forward Phase-0 "
             "(rank-IC / DSR on the early-ignition gate) is the open path to earning a tier.",
         why_zh="对价格/成交量的速度与加速度进行灵敏扫描，捕捉冲量刚刚点火、入场窗口仍开（近期涨幅小、未拉伸）的个股，"
                "并对已大涨的个股降权。诚实定位：并非经验证的阿尔法，也不给出涨跌概率——短周期方向接近抛硬币"
                "（engine/velocity.py），且动量优势随市场状态切换（承压时衰减），故仅为缩小关注范围的时机/背景工具，"
                "标注市场状态，绝不作为评分输入。排序合成固定可读（无学习权重）；前向 Phase-0 验证是其升级路径。",
         source="engine/impulse.py (unvalidated; forward Phase-0 pending)", horizon="1-5d",
         wired="impulse.html (display/context only)"),
    _row("US residual-alpha momentum (ranking)",
         "美国残差Alpha动量（排名）", "US S&P1500", "display",
         why="Positive but weak IC that FAILS BH-FDR (q=0.40) and the backtest Sharpe is "
             "negative with DSR≈0 (0.0014). Shown as a leaderboard / alpha baseline, not a "
             "scored buy signal.",
         why_zh="IC 为正但弱，未通过 BH-FDR（q=0.40），回测夏普为负且 DSR≈0。作为排行榜/alpha 基线显示，非计分买入信号。",
         source="residual-alpha-phase0.md", horizon="21d",
         ic=0.0124, ic_ir=0.077, t_hac=1.501, q_fdr=0.399, dsr=0.0014,
         sharpe=-0.29, hit=0.557, n=291, fdr_survivor=False,
         wired="discovery.html ranking (context)"),
    _row("US setup-score blend (selection × timing)",
         "美国 setup 融合分（选股×择时）", "US S&P1500", "display",
         why="Folding cycle-timing + reversal INTO the alpha rank gave NO IC gain and NO Sharpe "
             "gain vs alpha alone (setup IC −0.0013 / Sharpe −0.18 vs alpha +0.0101 / −0.16). "
             "Reverted to rank-by-alpha; timing is shown as separate risk-placement context.",
         why_zh="把周期择时+反转并入 alpha 排名相对 alpha 单独无 IC 增益、无夏普增益。已回退为按 alpha 排名；择时作为独立的风险位置背景显示。",
         source="setup-score-phase0.md", horizon="21d/63d",
         wired="macro/china standout cards (ordering)"),
    _row("China quality (ROE) cross-section",
         "中国质量（ROE）横截面", "China A", "display",
         why="No quality premium — junk BEATS quality on A-shares (quality-minus-junk spread "
             "Sharpe −0.58 cross-sectional, −0.71 sector-neutral). Shown as context only.",
         why_zh="无质量溢价 — A股 junk 跑赢 quality（质量减垃圾价差夏普 −0.58 横截面、−0.71 行业中性）。仅作背景。",
         source="china-quality-phase0.md", horizon="quarterly",
         sharpe=-0.58, n=120, wired="china context"),
    _row("China value (earnings yield) cross-section",
         "中国价值（盈利收益率）横截面", "China A", "display",
         why="Cross-sectional value spread negative (−0.46 Sharpe); sector-neutral only "
             "marginally positive (+0.06). No robust premium → context only.",
         why_zh="横截面价值价差为负（夏普 −0.46）；行业中性仅微正（+0.06）。无稳健溢价 → 仅作背景。",
         source="china-value-phase0.md", horizon="quarterly",
         sharpe=-0.46, n=119, wired="china context"),
    _row("China low-vol / low-beta cross-section",
         "中国低波/低贝塔横截面", "China A", "display",
         why="No low-risk anomaly on A-shares: low-vol long-short spread Sharpe −0.08, low-beta "
             "−0.01. Low-risk quintiles do not out-earn. Shown as risk stratification context.",
         why_zh="A股无低风险异象：低波多空价差夏普 −0.08，低贝塔 −0.01。低风险分位并不多赚。作为风险分层背景显示。",
         source="china-lowvol-phase0.md", horizon="quarterly",
         wired="china context"),
    _row("HK total-return momentum",
         "港股总回报动量", "HK", "display",
         why="HK's only positive cross-sectional signal (IC 0.0317, HAC t 2.04) — but it FAILS "
             "DSR (0.43<0.90) and it is market BETA, not stock alpha. Shown as a ranking.",
         why_zh="港股唯一为正的横截面信号（IC 0.0317，HAC t 2.04）— 但未通过 DSR（0.43<0.90），且是市场贝塔而非个股 alpha。作为排名显示。",
         source="hk-residual-alpha-phase0.md", horizon="monthly",
         ic=0.0317, t_hac=2.043, dsr=0.4339, sharpe=0.23, wired="hk context"),
    _row("Commodity per-asset allocation variants",
         "大宗商品单资产配置变体", "Commodity", "display",
         why="Every optimal single-commodity allocator fails the deflated-Sharpe bar "
             "(gold 0.58, silver 0.07, copper 0.32, oil 0.12 — all <0.90). The risk_index "
             "context is confirmed; the allocation edge is not.",
         why_zh="每个最优单一商品配置都未达 DSR 门槛（金 0.58、银 0.07、铜 0.32、油 0.12 — 均 <0.90）。风险指数背景已确认，但配置边际未确认。",
         source="commodity-calibration.md", horizon="allocation",
         dsr=0.5771, sharpe=0.48, wired="commodities.html (context)",
         extra=[("DSR gold/silver/copper/oil", "0.58 / 0.07 / 0.32 / 0.12")]),
    _row("Bitcoin Vector confirmation candidates (funding_z, OI div, VRP…)",
         "比特币向量确认候选（资金费率、持仓背离、波动溢价…）", "BTC", "display",
         why="Allocation-floor/cap candidates have NO pre-2021 footprint → cannot pass the "
             "both-halves split test; uplift is confirmation-only (ΔSharpe ~0.07 post-2021). "
             "Kept as risk-context confirmers, never hard-wired into the allocation math.",
         why_zh="配置下限/上限候选在 2021 年前无足迹 → 无法通过两半检验；增量仅为确认级（2021 后 ΔSharpe~0.07）。作为风险背景确认项保留，从不硬接入配置计算。",
         source="vector-integration-candidates.md", horizon="allocation",
         wired="vector.html (context)"),

    # ---- KILLED (NO-GO) -----------------------------------------------------
    _row("RVOL momentum confirmer",
         "RVOL 动量确认器", "US S&P1500", "killed",
         why="Volume does NOT confirm momentum — it mildly ANTI-confirms (momentum IC +0.013 "
             "on high-RVOL vs +0.028 on low-RVOL; uplift negative, no FDR survivors). The "
             "base-confirmed L/S that looked great was a survivorship/concentration artifact.",
         why_zh="成交量并不确认动量 — 反而轻微反向（高 RVOL 动量 IC +0.013 对低 RVOL +0.028；增量为负，无 FDR 幸存者）。看似亮眼的多空是幸存者/集中度假象。",
         source="rvol-phase0 (research)", horizon="21d", fdr_survivor=False,
         wired="not shipped"),
    _row("Constructive-base scanner (IBD pivot)",
         "建设性底部扫描（IBD 枢轴）", "US S&P1500", "killed",
         why="Anti-predictive: pivot-proximity / tightness IC significantly NEGATIVE and "
             "FDR-surviving (near-pivot = extended = short-term reversal, the OPPOSITE of the "
             "thesis). The L/S that looked great (Sharpe 0.49) is confounded; DSR 0.86<0.90 at "
             "honest n_trials. A lenient L/S gate gave a FALSE GO.",
         why_zh="反预测：枢轴接近度/紧致度 IC 显著为负且通过 FDR（近枢轴=拉伸=短期反转，与论点相反）。亮眼多空被混杂，诚实试验数下 DSR 0.86<0.90。宽松多空门槛给出假 GO。",
         source="base-scanner-phase0 (research)", horizon="21d", dsr=0.86,
         wired="not shipped"),
    _row("GBT meta-label (size/trust the BTC call)",
         "GBT 元标签（为 BTC 信号定量/定信）", "BTC", "killed",
         why="A López de Prado meta-label (HistGBT learns P(long call correct)). Honest verdict: "
             "DO NOT WIRE — ΔSharpe −0.43, negative calibration skill, all 20 configs lose.",
         why_zh="López de Prado 元标签（HistGBT 学习 P(做多正确)）。诚实结论：不接入 — ΔSharpe −0.43，校准技能为负，20 种配置全输。",
         source="gbt-meta-label-leaf", horizon="allocation",
         wired="not shipped",
         extra=[("ΔSharpe", "−0.43"), ("configs lost", "20 / 20")]),
    _row("HK residual-alpha (sector-neutral)",
         "港股残差 Alpha（行业中性）", "HK", "killed",
         why="Stripping beta/sector — which PURIFIED the US/China signals — REMOVES HK's signal "
             "entirely (residual IC ≈ 0, Sharpe −0.22/−0.35, DSR 0.0019). HK alpha is market "
             "beta, not stock-specific. Killed for HK.",
         why_zh="剥离贝塔/行业（这净化了美/中信号）反而完全移除港股信号（残差 IC≈0，夏普 −0.22/−0.35，DSR 0.0019）。港股 alpha 即市场贝塔。港股否决。",
         source="hk-residual-alpha-phase0.md", horizon="monthly",
         dsr=0.0019, sharpe=-0.22, wired="not shipped"),
    _row("China momentum (deep-history)",
         "中国动量（深度历史）", "China A", "killed",
         why="On 1992–2026 the only FDR-surviving cross-sectional effect is short-term REVERSAL "
             "(t −2.7…−5.0, q=0.0) — the OPPOSITE of momentum. Residual momentum IC is negative "
             "(−0.0045, t −0.49). A 5-year window made momentum look alive; deep history kills it.",
         why_zh="在 1992–2026 上，唯一通过 FDR 的横截面效应是短期反转（t −2.7…−5.0，q=0.0）— 与动量相反。残差动量 IC 为负。五年窗口曾让动量看似有效，深度历史否决之。",
         source="china-residual-alpha-deep.md", horizon="21d", fdr_survivor=False,
         wired="not shipped (reversal kept instead)"),
    _row("Commodity carry as single-asset timing",
         "大宗商品 carry 作单资产择时", "Commodity", "killed",
         why="'Backwardation = bullish' is WRONG-SIGNED for single-asset spot timing on 38y "
             "of EIA WTI futures (63d IC −0.16, t −4.6). Cross-sectional carry ≠ single-asset "
             "timing → display-only term-structure, green/red neutralized.",
         why_zh="“现货升水=看涨”在 38 年 EIA WTI 期货上对单资产现货择时方向错误（63日 IC −0.16，t −4.6）。横截面 carry ≠ 单资产择时 → 仅展示期限结构，红绿中性化。",
         source="commodity-carry-validation", horizon="63d",
         ic=-0.16, t_hac=-4.6, wired="display-only term structure"),
    _row("SPVector diversified sleeves (SPY + duration)",
         "标普向量多元化组合（标普+久期）", "US macro", "killed",
         why="Adding a Treasury sleeve fails the 2022 gate (−17.3% vs bills −13.5%) because the "
             "stock-bond correlation broke; no non-lagging correlation gate fixes it. Both "
             "halves underperform Phase-3. Phase-3 (SPY + bills) remains the product.",
         why_zh="加入国债组合未通过 2022 关卡（−17.3% 对国库券 −13.5%），因股债相关性破裂；无非滞后相关门槛可修复。两半均逊于 Phase-3。Phase-3（标普+国库券）仍为产品。",
         source="spvector-phase4.md", horizon="allocation",
         wired="not shipped"),

    # ---- DEMOTED — SUE failed deep re-validation (was scored) --------------
    _row("SUE — standardized unexpected earnings (earnings momentum)",
         "SUE — 标准化超预期盈利（盈利动量）", "US S&P1500", "display",
         why="DEMOTED from scored (2026-06-17). It WAS the lone FDR survivor on the shallow "
             "2023-2025 window (IC +0.038, q=0.077) and shipped as a scored leg — but a deep "
             "2011-2026 re-validation (survivorship-OPTIMISTIC, the one bias that helps a factor) "
             "collapses it to ~zero: IC 0.0005, HAC t 0.06, quintile L/S Sharpe 0.09. The win was a "
             "~2.5y-window artifact (PEAD post-publication decay). Still computed/shown on "
             "factors.html with the deep caveat; a clean delisting-recovered deep panel could revisit.",
         why_zh="已从“计分”降级（2026-06-17）。它曾是浅窗口（2023-2025）唯一通过 FDR 的正向因子（IC +0.038，q=0.077）并作为计分腿上线，"
                "但深度 2011-2026 复验（且对因子有利的幸存者偏差下）将其压至接近零：IC 0.0005、HAC t 0.06、五分位多空夏普 0.09。"
                "该胜出只是约2.5年窗口的产物（盈利公布后漂移的发表后衰减）。仍在 factors.html 展示但附深度警示。",
         source="sue-deep-history-phase0.md / factor-ic-scorecard.md / PR #35", horizon="63d",
         ic=0.0005, t_hac=0.061, sharpe=0.094, fdr_survivor=False,
         wired="factors.html (descriptive — deep-caveated)",
         extra=[("shallow 2023-2025 (was scored)", "IC 0.038, q 0.047, L/S Sharpe 1.45"),
                ("deep 2011-2026 (surv-opt.)", "IC 0.0005 · t 0.06 · L/S Sharpe 0.09 → edge GONE")]),

    # ---- DISPLAY-ONLY (cont.) — origin cross-asset / macro leaves ----------
    _row("Cross-asset TSMOM trend (managed-futures style)",
         "跨资产时间序列动量（趋势）", "Cross-asset", "display",
         why="Leverage-free time-series momentum over 10 keyless legs. After 8bps cost the "
             "diversified Sharpe (0.54) only matches buy&hold (0.56); permutation-null skill "
             "p=0.008 but Deflated Sharpe 0.80 < 0.90 → does NOT clear the gate. Shipped as a "
             "CONTESTED regime read, never a strategy.",
         why_zh="对 10 条无密钥腿的杠杆自由时间序列动量。扣 8bps 成本后多元夏普(0.54)仅与买入持有(0.56)持平；"
                "置换零假设技能 p=0.008，但去偏夏普 0.80<0.90 → 未通过门槛。作为有争议的体制读数，而非策略。",
         source="cross-asset-phase0.md", horizon="trend", dsr=0.795, sharpe=0.54,
         wired="crossasset.html (regime read)"),
    _row("Fund crowding / 13F concentration",
         "基金拥挤度 / 13F 集中度", "US S&P1500", "display",
         why="Cross-fund VIP overlap + holder Herfindahl. The contrarian 'sharper-pullback' "
             "context only reaches |t|=2.3 full-sample (H1 just −1.33) and short interest has no "
             "PIT history → un-backtestable. Display context, never scored.",
         why_zh="跨基金 VIP 重叠 + 持有人赫芬达尔。逆向“更深回撤”背景全样本仅 |t|=2.3（H1 仅 −1.33），"
                "且做空数据无时点历史 → 无法回测。仅作背景，从不计分。",
         source="fund-crowding-phase0.md", horizon="—", t_hac=-2.32,
         wired="display chip"),
    _row("Narrative regime (news text-uncertainty)",
         "叙事体制（新闻文本不确定性）", "US macro", "display",
         why="Raw news text-uncertainty does read forward vol (IC +0.06–0.11) — but VIX dominates "
             "(IC +0.67–0.73) and the INCREMENTAL signal over VIX is not significant. NO-GO as a "
             "scored conditioner; ships as a display banner with its gate multiplier pinned to 1.0.",
         why_zh="原始新闻文本不确定性确实读到前瞻波动（IC +0.06–0.11）— 但 VIX 占主导（IC +0.67–0.73），"
                "且相对 VIX 的增量不显著。不作为计分调节器；作为展示横幅，门控乘数固定为 1.0。",
         source="narrative-regime-phase0.md", horizon="fwd vol",
         wired="macro.html banner (×1.0)"),

    # ---- SIGNAL-LAB EXPANSION (validated 2026-06 — research + adversarial-verify workflows) ----
    _row("Bitcoin Vector — `optimal` momentum×risk allocation",
         "比特币向量 — optimal 动量×风险配置", "BTC", "scored",
         why="The one NEW scored win — a fully-wired live BTC allocation whose drawdown/Sharpe payoff survives "
             "every fatal-mode attack. Mechanical (momentum + on-chain risk_index) long/flat grid. "
             "PROVENANCE: pre-gate figure (DSR 0.9965, Sharpe 1.44) retired 2026-07 — it certified a strategy "
             "that baked the midterm-blackout human override into every backtest bar. Fresh dual-track as of 2026-07: "
             "RAW (pure engine, ungated) Sharpe 1.43 vs HODL 1.01, MaxDD −41.2% vs −83.8% (2.04× cut), "
             "DSR 0.9945 (n=68 = 65 base + 3 override dof_cost), dsr_effN 0.9236 (T_eff=2523 vs T_raw=4200). "
             "GATED (live behavior, midterm blackout active through 2026) Sharpe 1.56, MaxDD −32.3%, DSR 0.9986, "
             "dsr_effN 0.9622. Bootstrap P(Sharpe>0)=1.0 (CI [0.95,1.57,2.17]). DD-cut holds in both split-halves "
             "and every leave-one-crisis-out. Beats brake-matched 200dma. Decomposition proves NOT a brake artifact. "
             "SCORE THE DRAWDOWN/SHARPE ONLY — direction is a coin-flip (P(7d up|long) ~0.58). Honest-N ~4 crises.",
         why_zh="本轮唯一新增计分项——已上线的比特币配置，其回撤/夏普收益经全部致命检验仍成立。"
                "溯源注：旧数字（DSR 0.9965，夏普 1.44）于2026-07退役——中期选举人工覆盖污染了回测。"
                "双轨新数字（2026-07）：原始（纯引擎/未覆盖）夏普 1.43 对 HODL 1.01，最大回撤 −41.2% 对 −83.8%（缩小2.04倍），"
                "DSR 0.9945（n=68=65基础+3覆盖自由度），dsr_effN 0.9236。"
                "带覆盖（实盘，含中期选举封锁）夏普 1.56，回撤 −32.3%，DSR 0.9986。仅计回撤/夏普；方向为掷硬币。",
         source="btc-vector-optimal-phase0.md (scripts/btc_vector_optimal_phase0.py); engine/btc_signals.py allocation(); "
                "W1 N7 dual-track calibration 2026-07",
         horizon="allocation (daily)", dsr=0.9945, sharpe=1.43, n=4200,
         wired="vector.html / vector_allocation — alloc_optimal (LIVE, midterm-gated); alloc_optimal_raw (pure engine)",
         extra=[("RAW MaxDD", "−41.2% vs −83.8% (2.04× cut)"),
                ("GATED Sharpe / MaxDD", "1.56 / −32.3% (midterm blackout active through 2026)"),
                ("DSR gated / raw", "0.9986 / 0.9945 (n=68, incl. override dof_cost=3)"),
                ("dsr_effN gated / raw", "0.9622 / 0.9236 (T_eff≈2520 vs T_raw=4200)"),
                ("bootstrap P(Sh>0)", "1.0 · CI [0.95,1.57,2.17]"),
                ("direction", "coin-flip — NOT scored"),
                ("honest-N", "~4 crash episodes"),
                ("provenance", "pre-gate figure 0.9965 retired 2026-07; dual-track as of W1 N7")]),
    _row("Mastermind GTAA (Moderate) — diversified-leverage book",
         "Mastermind 全球配置（均衡）— 多元杠杆组合", "Multi-asset", "confirmer",
         why="Live levered vol-targeted cross-asset GTAA (~1.21× lev) beats SPY on risk-adjusted terms over 19.1y: "
             "Sharpe 1.07 vs SPY 0.62 / 60-40 0.77, MaxDD −24.1% vs −55.2% / −31.4%, DSR 0.9999, bootstrap "
             "P(Sharpe>0)=1.0, purged-CV 5/5, leave-one-crisis-out 6/6. BUT the adversarial incrementality test "
             "caps it at confirmer: the IDENTICAL chassis (inverse-vol + 12% vol-target + 1.6× cap) with "
             "conviction=1 (NO trend/carry/regime signal) already gives Sharpe 1.03 / MaxDD −27.5% — the "
             "four-factor conviction adds only +0.04 Sharpe / +3.4pp DD and loses in 2/5 folds and ex-2008. It "
             "credits the diversification+vol-target+leverage TRANSFORM, not timing alpha; raw-CAGR beat also "
             "flips OOS (H2 12.8 < SPY 15.4%).",
         why_zh="已上线的杠杆波动率目标跨资产全球配置，19.1年风险调整后跑赢标普（夏普 1.07 对 0.62，回撤 −24.1% 对 −55.2%）。"
                "但对照检验定为确认项：同一底盘信号=1已得夏普 1.03，四因子信号仅增 +0.04 夏普——计入的是分散+波动率目标+杠杆变换，非择时阿尔法。",
         source="mastermind-moderate-phase0.md; engine/masterminds.py", horizon="GTAA allocation (weekly)",
         dsr=0.9999, sharpe=1.07, wired="masterminds.html / strategy_mm_moderate (LIVE)",
         extra=[("MaxDD", "−24.1% vs SPY −55.2% / 60-40 −31.4%"),
                ("increment over no-signal chassis", "+0.04 Sharpe / +3.4pp DD (loses 2/5 folds, ex-2008)"),
                ("OOS CAGR", "flips (H2 12.8 < SPY 15.4%)")]),
    _row("Active levered commodity (silver & copper)",
         "主动杠杆商品（白银与铜）", "Commodity", "confirmer",
         why="Vol-targeted leverage-capable models that beat same-asset B&H on CAGR & Sharpe in BOTH split-halves "
             "(silver 16.25 vs 10.80% CAGR / 0.69 vs 0.48 Sharpe; copper 9.66 vs 7.98 / 0.54 vs 0.42) and beat a "
             "dumb 200dma. BUT the levered DSR gate is not cleanly met: silver DSR 0.919 (marginal, dies n≥40), "
             "copper 0.745 (fails every n + fails leave-one-crisis-out, 2008-dependent), and the active-minus-B&H "
             "Sharpe-diff 95% CI straddles zero for BOTH legs (silver [−0.21,+0.50] P=0.77; copper [−0.37,+0.39] "
             "P=0.53) — the textbook confirmer signature. The parameter-insensitive driver is a gold/silver-ratio "
             "mean-reversion leg (~0.61 Sharpe). Commodity-uptrend confirmation, not a sized signal; gold stays display.",
         why_zh="波动率目标杠杆模型在两半样本外均跑赢同资产买入持有（白银/铜 CAGR 与夏普），也跑赢200日均线。"
                "但杠杆 DSR 未达标（白银 0.919 临界、铜 0.745 失败且依赖2008），主动减买入持有的夏普差 95%区间跨零——确认项特征。",
         source="active-commodity-lev-phase0.md; engine/active_commodity.py evaluate()", horizon="allocation (daily)",
         dsr=0.919, sharpe=0.69, wired="commodity_strategies.html active cards (LIVE) — uptrend confirmer",
         extra=[("silver / copper DSR", "0.919 (marginal) / 0.745 (fail)"),
                ("active−B&H Sharpe-diff CI", "straddles 0 both legs"), ("driver", "gold/silver-ratio reversion ~0.61")]),
    _row("Credit-carry & duration-timing yield harvesters",
         "信用套息与久期择时收益收割", "US rates / credit", "display",
         why="Drawdown-context yield timers, downgraded to display. Credit Carry cuts MaxDD −14.7% vs −34.2% B&H "
             "(DSR 0.96 survives) but a dumb 150-250d SMA on HY DOMINATES it on Sharpe (overlay 0.745 < naive "
             "0.822) — a redundancy kill, its drawdown claim is subsumed. Duration Timing alone would merit "
             "confirmer (MaxDD −18.1% vs −48.4%, beats baselines, survives leave-one-crisis-out) but DSR 0.83<0.90 "
             "and it is a one-crisis-2022 story. BOTH give up CAGR vs B&H (excess return negative) — left-tail "
             "context only, honest-N ~5-6 crises not 5-6k autocorrelated rows.",
         why_zh="回撤情景的收益择时器，降级为仅展示。信用套息被一条朴素 HY 均线在夏普上压制（冗余否决）；久期 DSR 0.83 且仅2022单一危机。"
                "两者相对买入持有都让出 CAGR——仅作左尾情景。",
         source="credit-duration-verify-phase0.md (+ adversarial-refutation); reports/{credit-carry,duration-timing}-phase0.md",
         horizon="allocation (daily)", wired="strategies.html cards (LIVE) — display/research lens",
         extra=[("Credit DSR / Sharpe", "0.96 but 0.745 < dumb-200dma 0.822 (LOSES)"),
                ("Duration DSR", "0.83 (<0.90), one-crisis 2022"), ("both", "give up CAGR vs B&H")]),
    _row("Turn-of-month equity seasonal",
         "月末换月季节性", "US equity", "display",
         why="The famous turn-of-month calendar effect (hold last trading day + first 3, bills otherwise). Real on "
             "the 1927-2026 _GSPC full sample (Sharpe 0.93 vs 0.42, MaxDD −32% vs −86%, DSR ~1.0, beats 200dma + "
             "placebos) — but that full-sample DSR is a classic pre-publication DATA-MINED artifact: the edge "
             "concentrated PRE-2000 and decayed post-publication (Ariel/Lakonishok-Smidt/McConnell-Xu). Post-2010 "
             "SPY TOM LOSES on Sharpe (0.65 vs 0.86) and surrenders ~9pp CAGR; on tradeable SPY it fails "
             "leave-one-crisis-out and both-halves-beat-B&H, modern Sharpe inside the 73-89th-pctile noise band. "
             "The only surviving modern benefit is unconditional drawdown reduction from sitting in bills ~81% of "
             "days — not a forward edge. Display calendar curiosity.",
         why_zh="著名的月末换月效应。1927-2026 全样本看似强（夏普 0.93 对 0.42，DSR≈1.0），但这是发表前数据挖掘的产物——边际集中于2000年前并在发表后衰减。"
                "2010年后在可交易的 SPY 上夏普反而落后、CAGR 让出约9pp。唯一现代收益是空仓约81%带来的回撤下降，并非前瞻边际。",
         source="turn-of-month-phase0.md (scripts/turn_of_month_phase0.py); data/yahoo/_GSPC.parquet",
         horizon="seasonal (calendar)", wired="not shipped — display-only seasonal lens",
         extra=[("DSR", "1.0 full (artifact) / 0.836 post-2000 (FAILS)"),
                ("post-2010 SPY", "Sharpe 0.65 < B&H 0.86, CAGR −9pp"), ("modern", "noise-band 73-89th pctile")]),
    _row("Foreign-index trend de-risk basket (JP/DE/FR/KR/TW)",
         "海外指数趋势降险篮子", "International", "confirmer",
         why="A 200d-SMA trend overlay on FOREIGN PRICE indices — the US equity-trend kill is US-/total-return-"
             "specific (net-liquidity subsumes it; foreign price indices have secular bears + no dividend cushion). "
             "It cut the within-crisis drawdown in 5/5 global crises (Asian-97 +19, Dotcom +40, GFC +43, COVID +25, "
             "2022 +12pp); pooled MaxDD −57% → −18.5% (1997-2026, 5bps), and the DD-reduction is SKILL not "
             "mechanical: bootstrap CI [+5.9,+25.1,+48.1]pp excludes 0 (P=0.995) and sits above a random-overlay "
             "placebo band. HONEST: tail-insurance, NOT scored alpha — CAGR 4.77 vs 4.97 (gives up return), the "
             "Sharpe edge FAILS split-half (2H 0.57<0.85) and evaporates ex-1998-2003, DSR marginal (0.93→0.87 at "
             "n=24), edge gone by 15bps cost. Crash-avoidance risk-overlay; there is no intl scored row.",
         why_zh="对海外价格指数（无股息缓冲、有长期熊市）的200日趋势降险叠加——美式趋势否决是美国/全收益特有的。"
                "五次全球危机均削减回撤（合计 −57%→−18.5%，自举区间不含零），但属尾部保险而非计分阿尔法：让出 CAGR，夏普未过两半检验，成本15bps即消失。",
         source="intl-trend-overlay-phase0.md (scripts/intl_trend_overlay_phase0.py); data/intl/",
         horizon="overlay (daily)", sharpe=0.574, wired="not shipped — crash-avoidance risk-overlay",
         extra=[("pooled MaxDD", "−18.5% vs −57.0%"), ("DD-reduction CI", "[+5.9,+25.1,+48.1]pp P=0.995"),
                ("Sharpe edge", "FAILS split-half (2H 0.57<0.85); gone by 15bps cost")]),
    _row("Capitulation bounce overlay (Fed-put gated)",
         "投降式反弹叠加（美联储看跌期权门控）", "US equity", "confirmer",
         why="The capitulation gauge (VRP-extreme + VIX>30 + COT-washout) is a real FDR-validated bounce ALERT "
             "(63d P-up 75% vs 72% base; book-minus-base +0.66 bps/day, NW t 2.44, p 0.015; split-half + "
             "leave-one-fire pass). BUT a timed +0.5×/63d Fed-put-gated SPY-overweight does NOT clear the tradeable "
             "scored bar: the marginal-stream DSR is 0.737 (<0.90), it ties a one-line dumb buy-VIX>30 leg (paired "
             "NW t −0.64, p 0.52), the book-DSR 0.990 is a red herring (base SPY already 0.992), honest cluster "
             "count is 21 not 54, and the Fed-put gate LOWERS timed CAGR (12.5→12.0) — a drawdown-risk filter, not "
             "a return signal. Keep as a confirmer/attention signal feeding the dislocation gate.",
         why_zh="投降量表（VRP极值+VIX>30+COT洗盘）是经 FDR 验证的反弹预警（63日上涨概率 75% 对基线 72%，t 2.44）。"
                "但门控择时的 +0.5×/63日超配未达可交易计分线：边际 DSR 0.737，与朴素 VIX>30 持平，门控反而降低择时 CAGR——作为确认/关注信号喂给错位门控。",
         source="capitulation-overlay-phase0.md (scripts/capitulation_overlay_phase0.py); engine/conditions.py capitulation",
         horizon="63d (event-timed)", hit=0.75, wired="feeds dislocation drawdown gate (attention signal)",
         extra=[("timed DSR", "0.737 (FAIL; book-DSR 0.990 ≈ base SPY 0.992)"),
                ("vs dumb VIX>30", "ties (paired p 0.52)"), ("Fed-put gate", "LOWERS timed CAGR 12.5→12.0")]),
    _row("BTC on-chain valuation drawdown gauge (MVRV + Reserve-Risk)",
         "比特币链上估值回撤量表（MVRV+储备风险）", "BTC", "confirmer",
         why="Rolling-4y percentile of MVRV + Reserve Risk → forward BTC max-drawdown carries genuine sign-stable "
             "tail-risk content: Spearman −0.089/−0.134/−0.166 at 21/63/126d (monotone, correct sign — rich "
             "valuation precedes deeper drawdowns), split-half −0.105/−0.169 same-sign AND same-magnitude (rare), "
             "leave-one-crisis-out {2013,18,22} all hold, FDR q=0, causal (no look-ahead). Reserve Risk is the "
             "load-bearing leg (−0.267 vs MVRV −0.082). NOT scored: a dumb 200dma trend filter dominates it "
             "standalone and DSR fails the honest haircut (0.91 at n=18 → 0.78-0.87 at honest 30-72). What keeps it "
             "a confirmer: the partial-Spearman controlling for BOTH vol-pct AND 200dma is −0.145/−0.232 (genuine "
             "incremental forward-dd content). A contextual tail-risk / valuation-richness flag, never a sizer.",
         why_zh="MVRV+储备风险的滚动4年分位→前瞻 BTC 最大回撤，具备符号稳定的尾部风险内容（21/63/126日 单调正确符号，两半同号同量级，逐危机均成立，q=0）。"
                "但被朴素200日趋势单独压制、DSR 不过诚实折扣；保留为确认项因其在控制波动率与趋势后仍有增量（偏相关 −0.145/−0.232）。作为情景尾部风险标记，非定仓。",
         source="btc-onchain-dd-phase0.md (scripts/btc_onchain_dd_phase0.py); data/coinmetrics + data/checkonchain",
         horizon="forward drawdown (21/63/126d)", ic=-0.166, wired="contextual tail-risk / valuation flag (not sized)",
         extra=[("split-half IC", "−0.105 / −0.169 (same-sign+magnitude)"),
                ("partial-IC over vol+trend", "−0.145 / −0.232 (incremental)"),
                ("standalone", "dumb 200dma dominates; DSR fails honest haircut")]),
    _row("NAAIM manager-exposure de-risk overlay",
         "NAAIM 经理仓位降险叠加", "US equity", "confirmer",
         why="De-risking confirmer, NOT alpha. alloc=clip(NAAIM/100,0,1) cuts SPY MaxDD −55.2% → −20.2% "
             "(block-bootstrap CI [+7.0,+34.2]pp excludes 0, same-sign both halves) and lifts Sharpe over B&H "
             "(0.78 vs 0.65); the trend-following sign is confirmed (Spearman NAAIM-z vs fwd-63d drawdown +0.218 — "
             "high exposure precedes SHALLOWER drawdowns, the contrarian read is backwards). BUT it FAILS the "
             "beats-dumb-baseline gate: it TIES the free 200dma on drawdown (−20.2 vs −20.6) and LOSES on CAGR "
             "(7.97 vs 8.67), the paired Sharpe-diff vs 200dma is a coin flip (P=0.52), and the edge over B&H leans "
             "on 2008. A noisy weekly proxy for the same trend a daily SMA captures more cheaply. Lead with "
             "drawdown-reduction vs B&H, never alpha.",
         why_zh="降险确认项，非阿尔法。按 NAAIM 仓位削减回撤（−55.2%→−20.2%，自举区间不含零），夏普高于买入持有；趋势跟随符号确认（+0.218）。"
                "但未过朴素基线：在回撤上与200日均线持平、CAGR 落后，相对200日均线的夏普差为掷硬币。仅以相对买入持有的回撤下降为主。",
         source="naaim-overlay-phase0.md (scripts/naaim_overlay_phase0.py); data/sentiment/naaim.parquet",
         horizon="overlay (daily)", ic=0.218, sharpe=0.784, wired="de-risk confirmer vs B&H (not sized over an SMA)",
         extra=[("MaxDD", "−20.2% vs B&H −55.2% (ties 200dma −20.6%)"),
                ("vs dumb 200dma", "LOSES CAGR (7.97 vs 8.67); Sharpe-diff coin-flip"),
                ("edge over B&H", "vanishes ex-2008")]),
    _row("Stationarized HY-OAS 252d-z de-risk timer",
         "平稳化 HY-OAS 252日 z 降险择时", "US macro / credit", "display",
         why="A stationary 252d rolling-z of the HY-OAS de-risk overlay. Split-half stable, DSR 0.978, FDR q=0 — "
             "but those are COINCIDENT-credit artifacts (HY-OAS is ~0.6-0.7 contemporaneously rank-correlated with "
             "realized drawdown, so ANY transform survives). REDUNDANT with the incumbent HY-OAS LEVEL pct-rank: "
             "partial-IC(z252 | LEVEL) = −0.013 (~zero residual) vs partial-IC(LEVEL | z252) = −0.316, and strictly "
             "WORSE on every axis (Sharpe 0.65<0.77, MaxDD −50.8%>−22.5%). The z normalizes away the persistence "
             "that defines a credit crisis → de-risk benefit is ~entirely the single 2008 episode (fails "
             "leave-one-crisis-out, honest-N ~1), and a truly-causal expanding-quantile variant makes the benefit "
             "VANISH (the docstring's causal claim was an in-sample-threshold lookahead artifact). The level, not "
             "its z-score, carries the signal.",
         why_zh="HY-OAS 的平稳 252日 z 降险叠加。看似稳健（DSR 0.978、q=0），但属同期信用伪迹（任意变换都能过）。"
                "与现有 LEVEL 分位冗余（残差偏相关 ≈0）且各维更差；其降险几乎全靠2008单一危机，真正因果分位变体下收益消失。是水平而非其 z 携带信号。",
         source="hyoas-z-timer-phase0.md (scripts/hyoas_z_timer_phase0.py); data/archive/BAMLH0A0HYM2.parquet",
         horizon="overlay (daily)", ic=-0.301, wired="not shipped — graveyard/research lens (redundant with level)",
         extra=[("partial-IC over incumbent", "≈0 (−0.013)"), ("vs incumbent", "Sharpe 0.65<0.77, MaxDD −50.8%>−22.5%"),
                ("de-risk", "~one 2008 crisis; causal variant VANISHES")]),
    _row("Diversified commodity TSMOM book (gold/silver/copper/crude + USD)",
         "多元商品时间序列动量组合", "Commodity", "confirmer",
         why="Crisis-convexity context, NOT standalone alpha. A 5-leg 12-1m vol-targeted TSMOM book over 25.5y: "
             "Sharpe 0.42 / MaxDD −26.4% vs EW-long-commodity B&H 0.34 / −81.7% and each-leg 200dma 0.20 / −36.8% "
             "— beats both dumb baselines full-sample and pays in crises (2014-16 oil bust +25.5%, 2020 COVID "
             "+15.7% vs EW −26.5/−73.7%), no purged fold flips negative. BUT the +0.087 Sharpe edge does NOT "
             "survive the multiple-testing haircut: DSR 0.684 at n=12 and monotone-decreasing in n_trials (never "
             ">0.90 under any honest count); leave-one-crisis-out INVERTS on COVID (dSharpe +0.087→−0.31), the "
             "first split-half fails to beat EW-long, and the DD-reduction CI includes 0. Descriptive "
             "crisis-convexity context.",
         why_zh="危机凸性情景，非独立阿尔波。5腿12-1月波动率目标 TSMOM 组合（25.5年）：夏普 0.42 对等权多头 0.34，回撤 −26.4% 对 −81.7%，危机中盈利。"
                "但 +0.087 的夏普边际不过多重检验折扣（DSR 0.684 且随试验数单调下降），逐危机在COVID翻负，首半样本未跑赢——仅作危机凸性情景。",
         source="commodity-tsmom-phase0.md (scripts/commodity_tsmom_phase0.py); data/yahoo futures",
         horizon="allocation (daily)", dsr=0.6842, sharpe=0.42, wired="not shipped — crisis-convexity context sleeve",
         extra=[("MaxDD", "−26.4% vs EW-long −81.7%"), ("DSR", "0.684 (n=12), monotone-fails any honest n_trials"),
                ("leave-one-crisis-out", "INVERTS on COVID")]),

    # ---- ROUND-2 EXPANSION (2026-06-18 — archetype ports + data-unblock; 0 cleared scored) ----
    _row("ETH Vector — BTC-Vector optimal grid ported to ETH",
         "以太坊向量 — BTC向量最优网格移植到ETH", "ETH", "confirmer",
         why="Faithful port of the live BTC Vector builders (momentum × risk-index long/flat grid + drawdown brake) "
             "to ETH price (MVRV overlay unavailable this run — grid without valuation overlay). "
             "PROVENANCE: prior figure (DSR 0.5546, Sharpe 0.82) inherited the BTC midterm-election blackout with "
             "NO ETH evidence basis — that override is now explicitly disabled for the ETH run (W0 W1 N7 decontam). "
             "FRESH RERUN (ungated, 2026-07): Sharpe 0.796 vs HODL 0.647, MaxDD −46.6% vs −94.0% (2.02× cut), "
             "n=3157 (2017-11 → 2026-07). DSR 0.5345 (n=50) FAILS the haircut — confirmer status unchanged. "
             "Bootstrap P(Sharpe>0)=0.98 (not 1.0); a brake-matched 200dma BEATS it on Sharpe (0.82 vs 0.80). "
             "DD-cut holds both split-halves and every leave-one-crisis-out (DD-only edge). "
             "Sharpe edge fails drop-2022 (−0.05). ETH starts 2017-11 (~2-3 cycles). "
             "Direction coin-flip (never claimed). Confirmer status: unchanged.",
         why_zh="将上线的 BTC 向量构件（动量×风险指数多/空网格+回撤刹车）忠实移植到 ETH（无 MVRV 叠加）。"
                "溯源注：旧数字（DSR 0.5546）继承了 BTC 中期选举封锁（无 ETH 依据）——已解除（W0/W1 N7 去污）。"
                "最新重跑（2026-07，无封锁）：夏普 0.796 对 HODL 0.647，最大回撤 −46.6% 对 −94.0%（缩小2.02倍），n=3157。"
                "DSR 0.5345 仍未达门槛，确认项状态不变。刹车匹配200日均线在夏普上仍持平甚至压制。仅约2-3周期；方向掷硬币。",
         source="eth-vector-phase0.md (scripts/eth_vector_phase0.py); engine/btc_signals.py allocation(); "
                "W1 N7 rerun 2026-07 (BTC midterm gate explicitly disabled — no ETH evidence basis)",
         horizon="allocation (daily)", dsr=0.5345, sharpe=0.796, hit=0.549, n=3157,
         wired="signal_lab confirmer — crypto tail-insurance (BTC-Vector aligned), not sized standalone",
         extra=[("MaxDD", "−46.6% vs −94.0% HODL (2.02× cut)"),
                ("vs BTC DSR (raw)", "0.5345 vs 0.9945"),
                ("brake-matched 200dma", "BEATS ETH on Sharpe (0.82 vs 0.80)"),
                ("drop-2022 Sharpe edge", "−0.05 (concentrated in 2022)"),
                ("provenance", "prior DSR 0.5546 inherited BTC midterm gate with no ETH basis — now decontaminated"),
                ("direction", "coin-flip — NOT claimed")]),
    _row("Intl macro stress overlay (pooled JP/EZ/GB/KR)",
         "国际宏观压力叠加（JP/EZ/GB/KR 合并）", "Intl macro", "confirmer",
         why="Ported the S&P/Macro Vector de-risk gate (curve inversion + unemployment-Sahm + short-rate) to "
             "JP/EZ/GB/KR + a pooled inverse-vol sleeve. The pool cuts the tail (MaxDD −39.2% vs B&H −55.4%, "
             "Sharpe 0.72 vs 0.56) and is split-half stable (+0.70/+0.76) — BUT a plain 200dma long/flat DOMINATES "
             "it on BOTH Sharpe AND MaxDD (0.80 / −19.6%) in every market and the pool, and even a dumb "
             "curve-inversion gate beats it (0.78 / −42.5%). The macro gate gives up CAGR (JP 8.09→6.45%) to buy "
             "drawdown insurance a moving average buys more cheaply. Honest-N ~4 shared crises (JP exactly 3). "
             "Macro stress overlay, never a timed allocation.",
         why_zh="将标普/宏观向量降险门控（曲线倒挂+失业Sahm+短端利率）移植到 JP/EZ/GB/KR 及合并组合。合并削减尾部（回撤 −39.2% 对 −55.4%），"
                "但朴素200日均线在夏普与回撤上均压制它（各市场与合并皆然），且让出 CAGR。诚实样本约4次共享危机。仅作宏观压力叠加，非择时配置。",
         source="intl-macro-sleeve-phase0.md (scripts/intl_macro_sleeve_phase0.py); data/intl_macro/",
         horizon="allocation (daily)", sharpe=0.72,
         wired="signal_lab confirmer — macro stress overlay (never sized standalone)",
         extra=[("pooled MaxDD", "−39.2% vs −55.4% B&H"), ("dumb 200dma (dominates)", "Sharpe 0.80 / MaxDD −19.6%"),
                ("binding fail", "beats-200dma — all 4 markets + pool"), ("split-half", "+0.70 / +0.76"),
                ("honest-N", "~4 shared crises")]),
    _row("Intl total-return ETF trend de-risk basket (EWJ/EWG/EWU/EWY/EWA/EWQ)",
         "国际总回报ETF趋势降险篮子", "Intl ETF", "confirmer",
         why="Tested whether real tradeable USD total-return country ETFs (EWJ/EWG/EWU/EWY/EWA/EWQ, 25.3y, "
             "dividend-adjusted) rescue the intl trend overlay above confirmer — they do NOT. The pooled 200dma "
             "de-risk basket is robust tail-insurance (MaxDD −61.9% → −23.9%, DD-reduction bootstrap CI "
             "[6.2,25.8,50.4] excludes 0, cuts the tail in all 5 crises, leave-one-crisis-out holds) but gives up "
             "CAGR (6.42% vs 7.91% B&H on a fair T-bill carry) and its Sharpe edge FAILS DSR (0.848<0.90 at honest "
             "n_trials=17) AND fails same-sign split-half (+0.24 / −0.02 sign-flip). No single ETF clears scored "
             "(nearest EWY/sma200 is DSR-knife-edge, N=1 country). Confirms the price-index finding: USD "
             "total-return ETFs lack the secular bear the local indices had, so trend has less downside to exploit. "
             "Tail-insurance, not scored alpha.",
         why_zh="检验可交易的美元总回报国家 ETF（EWJ/EWG/EWU/EWY/EWA/EWQ，25.3年，含息）能否把国际趋势叠加提升到计分以上——不能。"
                "合并200日降险篮子是稳健尾部保险（回撤 −61.9%→−23.9%，区间不含零），但让出 CAGR，夏普边际未过 DSR（0.848）且两半符号翻转。"
                "美元总回报缺少本地指数的长期熊市，趋势可利用的下行更少。尾部保险，非计分阿尔法。",
         source="intl-tr-trend-phase0.md (scripts/intl_tr_trend_phase0.py); EWJ/EWG/EWU/EWY/EWA/EWQ (collected)",
         horizon="overlay (daily)", dsr=0.848, sharpe=0.575,
         wired="signal_lab confirmer — de-risk basket (not a scored allocation)",
         extra=[("pooled MaxDD", "−61.9% → −23.9%"), ("DD-reduction CI", "[6.2,25.8,50.4]pp excludes 0"),
                ("DSR", "0.848 (<0.90, n=17)"), ("split-half Sharpe", "+0.24 / −0.02 (sign-flip)"),
                ("CAGR give-up", "6.42% vs 7.91% B&H")]),
    _row("Crypto vol-targeted risk-parity sleeve (BTC+ETH)",
         "加密波动率目标风险平价组合（BTC+ETH）", "Crypto", "killed",
         why="A Moreira-Muir vol-managed BTC+ETH sleeve (scale inversely to trailing realized vol, lev cap ~2×). "
             "Measured and refused: DOMINATED by a dumb 200dma long/flat on BOTH Sharpe AND MaxDD, the "
             "drawdown-reduction bootstrap CI straddles 0, and the split-half Sharpe sign-FLIPS. Vol-targeting cuts "
             "crypto drawdown but adds no Sharpe over a trivial trend filter on the ~3-cycle sample. NO-GO.",
         why_zh="Moreira-Muir 波动率管理的 BTC+ETH 组合。经测量后否决：在夏普与回撤上均被朴素200日均线压制，回撤削减区间跨零，两半夏普符号翻转。"
                "波动率目标削减回撤但相对简单趋势无夏普增量。NO-GO。",
         source="crypto-voltarget-phase0.md (scripts/crypto_voltarget_phase0.py)", horizon="allocation (daily)",
         wired="not shipped",
         extra=[("vs dumb 200dma", "dominated on Sharpe AND MaxDD"), ("DD-reduction CI", "straddles 0"),
                ("split-half Sharpe", "sign-flip")]),

    # ---- DATA-CHASE for scored #7 (2026-06-19 — new commodity-xsec data; the wall held) ----
    _row("Cross-sectional commodity momentum (19-asset, deep)",
         "横截面商品动量（19资产，深度历史）", "Commodity", "killed",
         why="The classic Gorton-Rouwenhorst commodity-momentum factor (12-1m, long-winners/short-losers "
             "tercile L/S over 19 deep continuous fronts, 2002-2026) tested on freshly-collected NEW data — "
             "and it is DEAD. Forward 21d rank-IC is NEGATIVE (−0.018, t −1.01, q=0.31, fails BH-FDR) — the "
             "monthly commodity cross-section MEAN-REVERTS, the opposite of the trend prior. The L/S loses "
             "money even GROSS (−91% cumulative; net Sharpe −0.23 vs EW-long +0.64 and a per-commodity 200dma "
             "+0.18); DSR 0.0025; 1/7 gates (the lone pass is a trivially-both-negative split-half). Shorter "
             "lookbacks reject FDR but in the WRONG (reversal) sign. Matches the documented post-2004 "
             "financialization decay; only merit is crisis convexity from the short leg that bleeds back in "
             "normal regimes. NO-GO — new data did not break the scored wall.",
         why_zh="经典 Gorton-Rouwenhorst 商品动量因子（12-1月、多赢家空输家、19个深度连续合约、2002-2026）在新采数据上检验——已死。"
                "前瞻21日秩相关 IC 为负（−0.018，未过 FDR），月度商品横截面均值回归。多空即使毛收益也亏（−91%），DSR 0.0025。"
                "符合2004年后金融化衰减；唯一可取处是空头腿危机凸性，但常态回吐。NO-GO。",
         source="commodity-xsec-mom-phase0.md + commodity-xsec-mom-refute.md (scripts/commodity_xsec_mom_phase0.py)",
         horizon="21d / monthly", ic=-0.0181, t_hac=-1.01, q_fdr=0.314, dsr=0.0025, sharpe=-0.23, fdr_survivor=False,
         wired="not shipped (no daily collector — momentum empirically dead)",
         extra=[("fwd-IC", "−0.018 (mean-reverts, wrong sign)"), ("L/S net Sharpe", "−0.23 vs EW-long +0.64"),
                ("gross", "also negative (−91% cum)"), ("only merit", "crisis convexity (bleeds back)")]),
    _row("Cross-sectional commodity carry / basis",
         "横截面商品 carry／基差", "Commodity", "display",
         why="The storage-theory carry premium (long backwardation / short contango; ~81bps/mo t~4 in the "
             "literature; the team's own note: total-return basis IC +0.15) is real — but UN-BACKTESTABLE on "
             "free data, so NO edge is claimed here. yfinance DELETES expired dated contracts (CLZ24 → 404, "
             "verified), so a clean continuous adjacent-month basis chain cannot be built; the only "
             "constructible series uses a far/sticky ~24mo deferred leg whose basis is dominated by the front "
             "PRICE LEVEL (which mean-reverts) — a confound whose forward IC is significant but WRONG-SIGN "
             "(−0.16 @21d) and whose L/S loses to both dumb baselines. The clean deep EIA WTI c1-c4 (41y) "
             "confirms carry is a CROSS-SECTIONAL premium, not single-name timing. A genuine test needs a "
             "dated-history vendor (CME / Bloomberg / Quandl-Stevens) carrying expired contracts. Shown to "
             "document the data gap + the path — not an edge.",
         why_zh="仓储理论的 carry 溢价（多升水空贴水，文献 ~81bps/月；团队自有记录 总回报基差 IC +0.15）真实存在，"
                "但在免费数据上无法回测，故此处不主张任何边际。yfinance 删除到期合约，无法构建干净的相邻月基差链；"
                "唯一可构建的远月代理被前端价格水平混淆（符号相反）。真正检验需带历史到期合约的付费数据源。仅记录数据缺口与路径。",
         source="commodity-xsec-carry-phase0.md (scripts/commodity_xsec_carry_phase0.py); EIA WTI c1-c4 41y",
         horizon="—", wired="not shipped — un-backtestable on free data (needs dated-history vendor)",
         extra=[("blocker", "yahoo deletes expired contracts → no clean basis chain"),
                ("constructible proxy", "front-price-level confound, wrong-sign IC −0.16"),
                ("path", "CME / Bloomberg / Quandl-Stevens expired-contract history")]),

    # ---- INTL BRIDGE (W1 + W2 C1/C2/C3 2026-07-02 — the intl registry mirror) ----
    # Registry mirror of data/intl_bridge/ledger.json (engine/intl_claims.BACKFILL + C1/C2/C3 graded).
    # CONFIRMED verdict (C3) → confirmer tier (all gates pass; not wired to a scorer yet — W4).
    # CONTEXT verdicts (C1 measured weaker than HK; C2 graded vs the US book) → display tier;
    # PENDING → pending tier.
    # Every number is quoted from its report in `source`.

    # C3 CONFIRMED (W2-C3 2026-07-02): global ETF breadth barometer
    _row("Global country-ETF breadth barometer  (C3 — CONFIRMED)",
         "全球国家ETF广度晴雨表（C3 — 已确认）", "Intl / global risk", "confirmer",
         why="CONFIRMED (all hard gates pass). % of 23 country ETFs > their 200dma; causal "
             "trailing pctile de-risk signal (top-30% = flat). DSR 0.9326 (N=17 intl_bridge "
             "budget). Orthogonality: global breadth corr 0.68 with SPY trend but residual "
             "surviving frac = 0.62 after partialing out SPY/HY OAS/T10Y2Y — PASSES (>= 0.50). "
             "6/6 pre-declared crises covered. ES reduction ex top-3 windows = +0.0078 (not "
             "crisis-only). Split-half Sharpe both positive. Panel: 23 ETFs from 1996-03-18, "
             "min-panel >= 10 (satisfied from day 1 with the 1996 cohort of 17 ETFs). "
             "FXI/CSI300 target shows stronger MaxDD cut (-39.3% vs -72.7%) and near-pure "
             "orthogonality (surviving frac 0.97). W4: wire as US radar Tier-B leg (INTL-38) + "
             "risk_radar_intl profile leg once the forward log accrues.",
         why_zh="已确认（所有严格门均通过）。23只国家ETF高于200日均线的百分比；"
                "因果尾部百分位降险信号（前30%=空仓）。DSR 0.9326（N=17 intl_bridge预算）。"
                "正交性：全球广度与SPY趋势相关0.68，但剔除SPY/信用利差/收益曲线后残差存活分数=0.62 >= 0.50。"
                "6/6预声明危机均覆盖。去除前3大回撤窗口后期望损失降幅=+0.0078（非仅危机）。两半夏普均为正。"
                "W4：有前瞻日志后，作为美国雷达Tier-B腿（INTL-38）+ risk_radar_intl配置腿接入。",
         source="reports/intl-global-breadth-phase0.md (W2-C3 2026-07-02); "
                "data/intl_bridge/ledger.json (c3_global_etf_breadth); "
                "scripts/intl_phase0.py build_c3_global_breadth()",
         horizon="21/42d fwd drawdown (SPX + CSI300)", dsr=0.9326,
         wired="not wired (CONFIRMED; W4 will wire as US risk_radar Tier-B + intl profile leg; "
               "no scoring seam touched in W2)",
         extra=[("DSR", "0.9326 (N=17 intl_bridge budget, >= 0.90)"),
                ("orthogonal surviving frac", "0.62 vs SPY/HY/curve basis (>= 0.50, PASSES)"),
                ("effective_n_crises", "6/6 (all declared crises covered)"),
                ("ES ex top-3 windows", "+0.0078 (not crisis-only)"),
                ("split-half Sharpe", "H1 +0.45, H2 +1.11 (same sign)"),
                ("FXI MaxDD cut", "strat -39.3% vs bench -72.7%"),
                ("panel", "23 ETFs 1996-03-18 to 2026-07-01; min-panel=10 threshold")]),

    # ---- INTL BRIDGE remaining entries (C1/C2/C5/C8 CONTEXT + C4c INVERTED display graveyard; C4a CONFIRMED confirmer) ----
    _row("China per-name global-beta size-dampener  (C1 — the v1 flagship)",
         "中国个股全球贝塔仓位抑制器（C1 — v1 旗舰）", "China A", "display",
         why="MEASURED and REFUTED as a de-risk timing signal (W2). Port of hk_global_beta to the "
             "A-share panel: causal 252d beta to S&P-500 (overnight-lagged), Vasicek-shrunk. "
             "Transmission is HALF of HK's — HK/China ratio ~2.4× (HK SPY-beta 0.49 vs CSI300 0.20), "
             "exactly the china_global_factors prior. The per-name beta→forward-drawdown link is real "
             "but UNCONDITIONAL (rank-IC −0.17, t≈−13; orthogonality vs the CN RORO PASSES) — beta is "
             "beta. The specific dampener MECHANISM fails: conditioning on the global risk state being "
             "off makes the hi-minus-lo drawdown spread WEAKER, not stronger (off −2.3pp vs on −2.9pp; "
             "incremental +0.6pp, wrong sign). Crisis-count effective-N=1 (the ~5y china_search panel "
             "spans only the 2022 rate bear), DSR≈0, ES-ex-top3 negative. CONTEXT, weight_cap 0, "
             "kill=True — NOT wired into china_name_score._tailwind.",
         why_zh="已测量并否决其作为降险择时信号（W2）。将 hk_global_beta 移植到 A 股面板：对标普500（隔夜滞后）"
                "的因果252日贝塔，Vasicek 收缩。传导仅为香港的一半——港/华比约 2.4×（港 SPY-贝塔 0.49 对 沪深300 0.20），"
                "正合 china_global_factors 先验。个股贝塔→前瞻回撤关系真实但无条件（秩IC −0.17，t≈−13；相对中国RORO正交通过）"
                "——贝塔就是贝塔。具体抑制器机制失败：以全球风险状态转弱为条件反而使高减低回撤价差更弱（风险关 −2.3pp 对 风险开 −2.9pp；"
                "增量 +0.6pp，符号相反）。危机计数有效N=1（约5年面板仅含2022利率熊市），DSR≈0，剔除前三ES为负。"
                "CONTEXT，权重上限0，kill=True——未接入 china_name_score._tailwind。",
         source="scripts/c1_cn_global_beta.py + scripts/intl_phase0.py (grade); "
                "engine/cn_global_beta.py; data/intl_bridge/ledger.json (C1)",
         horizon="21/42d fwd drawdown", ic=-0.169,
         wired="not wired — CONTEXT (measured weaker than HK; dampener mechanism refuted)",
         extra=[("HK/China transmission", "~2.4× (HK 0.49 vs CSI300 0.20 SPY-beta)"),
                ("beta→DD rank-IC", "−0.17 (t≈−13, unconditional)"),
                ("RORO-conditional edge", "+0.6pp (WRONG sign — dampener refuted)"),
                ("crisis effective-N", "1 (panel ~5y, 2022 bear only)")]),
    _row("Intl macro de-risk sleeve  (pooled JP/EZ/GB → US book — C2)",
         "国际宏观降险组合（JP/EZ/GB → 美国 — C2）", "Intl macro", "display",
         why="W2 VERDICT: CONTEXT — do NOT wire. The prior DSR 0.9978 was the pooled INTL sleeve "
             "predicting INTL drawdowns. C2 graded the DECLARED target — US SPY forward drawdown — "
             "through the two gates the prior never ran: orthogonality vs the 5 US MRS legs + "
             "crisis-independent ES. On the honest fully-specified window (2002-05, first date all "
             "three markets carry all declared legs — no look-ahead), the sleeve-gated SPY strategy's "
             "deflated Sharpe is 0.83, BELOW the 0.90 promotion door, and its residual forward-DD "
             "content after partialing out the US legs is marginal and window-fragile (Spearman "
             "−0.03..−0.17). It DOES cut SPY MaxDD modestly (−50.1% vs −56.8% B&H) but that overlaps "
             "NFCI/liquidity/recession — no ORTHOGONAL edge that clears the door. A truthful negative: "
             "against the US book the intl sleeve adds nothing the 5 US MRS legs don't already carry.",
         why_zh="W2 结论：CONTEXT——不接线。此前 DSR 0.9978 是合并国际组合预测国际回撤。C2 针对预注册目标"
                "（美国 SPY 前瞻回撤）运行了先前从未跑过的两道门：相对5条美国MRS腿的正交性 + 危机无关期望损失。"
                "在诚实的完整规格窗口（2002-05，三市场首次全部携带全部声明腿——无前视），组合门控 SPY 策略的"
                "去偏夏普为 0.83，低于 0.90 晋升门；剔除美国腿后的残差前瞻回撤含量微弱且随窗口漂移"
                "（斯皮尔曼 −0.03..−0.17）。它确实小幅削减 SPY 回撤（−50.1% 对 −56.8%），但与 "
                "NFCI/流动性/衰退重叠——无可过门的正交边际。诚实的负面结论：相对美国本册，国际组合并未新增内容。",
         source="reports/intl-macro-sleeve-phase0.md; scripts/intl_phase0.py build_c2_sleeve; "
                "data/intl_bridge/ledger.json (C2)",
         horizon="21/42d fwd drawdown", dsr=0.8282,
         wired="not wired — CONTEXT (DSR 0.83 < 0.90 door; residual DD-content vs US legs marginal)",
         extra=[("US-book DSR", "0.83 (< 0.90 door)"), ("residual DD IC vs US legs", "−0.03..−0.17 (fragile)"),
                ("SPY MaxDD cut", "−50.1% vs −56.8% B&H (overlaps NFCI/liq)"),
                ("prior (INTL vs INTL)", "DSR 0.9978 — a different, easier test")]),
    # C4a CONFIRMED (W3-C4a 2026-07-02): the N=1 REER resurrection cleared its own budget
    _row("Broad-dollar REER value factor  (N=1 resurrection — C4a — CONFIRMED)",
         "宽美元 REER 价值因子（N=1 复活 — C4a — 已确认）", "Dollar / macro", "confirmer",
         why="CONFIRMED — the honest INTL-43 resurrection. The broad-USD REER value factor "
             "(cheap = bullish USD, faithful to config forex.dollar_desk.valuation) CONFIRMED in "
             "BOTH halves vs forward broad-USD returns at all three declared horizons (h=21 "
             "+0.031/+0.030, h=63 +0.062/+0.056, h=126 +0.120/+0.099). Graded on its OWN "
             "single-trial budget (trial_family c4_reer_value_n1) — the pre-registered N=1 door, "
             "budget-separated from the forex 60-trial family (DSR 0.0056 there) AND the "
             "intl_bridge N=17 family (DSR 0.40 there): de-risk long-flat DSR 0.9436 >= 0.90, "
             "split-half PASS, orthogonality vs the 5 US MRS legs PASS (residual −0.130), "
             "crisis-count 4, crisis-independent ES +0.0025. weight_cap 0.1333. NO consumer "
             "wiring this wave: verdict recorded + surfaced by intl_feed at cap, but no scorer "
             "consumes the feed — the MRS-composite orthogonality gate must clear first (W2-C2 "
             "showed the bar is high and this is a returns-predicting factor, not a US-DD leg).",
         why_zh="已确认——诚实的 INTL-43 复活。宽美元 REER 价值因子（便宜=看多美元，忠于 "
                "config forex.dollar_desk.valuation）在两半、三个预声明期限均确认对未来宽美元回报"
                "（h=21 +0.031/+0.030，h=63 +0.062/+0.056，h=126 +0.120/+0.099）。以独立单试验预算"
                "（trial_family c4_reer_value_n1）评分——预注册的 N=1 门，与外汇60试验家族（该处 DSR "
                "0.0056）及 intl_bridge N=17 家族（该处 DSR 0.40）分开：降险多-空仓 DSR 0.9436 >= 0.90，"
                "两半通过，对5条美国 MRS 腿正交通过（残差 −0.130），危机计数4，去危机期望损失 +0.0025。"
                "权重上限 0.1333。本波不接入消费者：结论已记录并由 intl_feed 以上限呈现，但无计分器消费"
                "该源——须先通过 MRS 组合正交门。",
         source="reports/forex-calibration.md (DOLLAR INDEX value); "
                "reports/forex-reer-n1-phase0.md (W3-C4a N=1); "
                "data/intl_bridge/ledger.json (c4_reer_value); "
                "scripts/c4_reer_value.py + scripts/intl_phase0.py (grade, N=1 budget)",
         horizon="21/63/126d fwd broad-USD return", dsr=0.9436, ic=0.0507,
         wired="not wired this wave — CONFIRMED verdict recorded + surfaced at cap 0.1333; "
               "no scorer consumes intl_feed (MRS-orthogonality gate deferred)",
         extra=[("N=1 budget DSR", "0.9436 (>= 0.90 door)"),
                ("vs intl_bridge N=17 / forex N=60", "0.40 / 0.0056 (budget-killed)"),
                ("orthogonality vs 5 US MRS legs", "residual −0.130 (PASS, de-risk sign)"),
                ("crises / crisis-indep ES", "4 / +0.0025 (PASS)")]),
    # C4c INVERTED (W3-C4c 2026-07-02): the CNH offshore-onshore basis is the wrong-signed graveyard
    _row("CNH offshore-onshore basis  (2nd China RORO leg? — C4c — INVERTED)",
         "CNH 离岸-在岸基差（第二条中国 RORO 腿？ — C4c — 已反转）", "China / RORO", "display",
         why="INVERTED — do NOT wire. Tested whether the offshore-minus-onshore CNH basis (a "
             "funding-stress spread) adds orthogonal de-risk content beside the EXISTING raw "
             "usdcnh RORO leg (offshore 20d move). It does not: graded at 42d DD vs FXI, rank-IC "
             "~0.0003 (null), split-half sign-FLIPS, DSR 0.0013, and — the decider — the residual "
             "after partialing out the raw usdcnh leg is WRONG-SIGNED (+0.121: wider basis → "
             "SHALLOWER forward drawdown), with negative crisis-independent ES (−0.0095). USDCNH "
             "history is short (2013+, ~2 China bears). Respecting W2-C1 (CN RORO legs already "
             "carry beta content), a second basis leg double-counts. china_conditions RORO frame "
             "UNCHANGED — no leg added.",
         why_zh="已反转——请勿接入。测试 CNH 离岸减在岸基差（融资压力价差）是否在现有原始 usdcnh "
                "RORO 腿（离岸20日动量）之外新增正交降险内容。并未：对 FXI 42日回撤评分，秩相关 "
                "~0.0003（无效），两半符号翻转，DSR 0.0013，且——决定项——剔除原始 usdcnh 腿后的残差符号"
                "错误（+0.121：基差越宽→未来回撤越浅），去危机期望损失为负（−0.0095）。USDCNH 历史短"
                "（2013+，约2次中国熊市）。遵循 W2-C1（中国 RORO 腿已含贝塔内容），第二条基差腿重复计数。"
                "china_conditions RORO 框架未变——未加腿。",
         source="reports/forex-reer-n1-phase0.md (W3-C4c CNH-basis section); "
                "data/intl_bridge/ledger.json (c4_cnh_basis); "
                "scripts/c4_cnh_basis.py + scripts/intl_phase0.py (grade)",
         horizon="21/42d fwd drawdown (FXI)", dsr=0.0013, ic=0.0003,
         wired="not wired — INVERTED (wrong-signed residual vs existing raw usdcnh RORO leg)",
         extra=[("residual vs raw usdcnh leg", "+0.121 (WRONG sign for a de-risk leg)"),
                ("rank-IC vs FXI fwd DD", "~0 (0.0003); split-half sign-flips"),
                ("crisis-indep ES", "−0.0095 (fails)")]),
    _row("Global cost-of-capital de-risk leg  (global 10y + US premium — C5)",
         "全球资本成本降险腿（全球10年期 + 美国溢价 — C5）", "Global rates", "display",
         why="W3 VERDICT: CONTEXT — do NOT wire. The GDP-weighted global 10y level + US-vs-world "
             "premium are reconstructed causally by engine.global_rates from the sovereign 10y "
             "roster (the display card dead-ends both in bond_health.json with no history — "
             "INTL-15). The honest prior — the global 10y is ~US 10y + noise — is confirmed by "
             "MEASUREMENT: the C5 global-10y rise signal correlates 0.948 with the US-only 10y "
             "momentum (US is a 0.42-weight roster leg), so it carries no orthogonal duration edge "
             "over the existing US curve/credit MRS legs. The binding gate is drawdown-reduction "
             "over the signal-active era (from 1963): the long/flat strategy cuts SPY MaxDD only "
             "1.1pp (−55.7% vs −56.8% B&H) while HALVING total return (Calmar 0.115 < 0.137 B&H — "
             "not cost-justified). DSR 0.98 is SPY drift, not an edge. weight_cap 0, kill=True — "
             "conditions._macro_risk_legs UNCHANGED.",
         why_zh="W3 结论：CONTEXT——不接线。GDP加权全球10年期水平 + 美国对世界溢价由 engine.global_rates "
                "从主权10年期名单因果重建（展示卡将两者困在 bond_health.json 无历史——INTL-15）。诚实先验"
                "——全球10年期≈美国10年期+噪声——经测量确认：C5 全球10年期上行信号与纯美国10年期动量相关 "
                "0.948（美国占名单0.42权重），故相对现有美国曲线/信用MRS腿无正交久期边际。约束门为降险时代"
                "（自1963起）的回撤削减：多/空策略仅削减 SPY 回撤 1.1pp（−55.7% 对 −56.8%），却使总回报腰斩"
                "（Calmar 0.115 < 0.137，不划算）。DSR 0.98 是 SPY 漂移，非边际。权重上限0，kill=True——"
                "conditions._macro_risk_legs 未变。",
         source="scripts/c5_global_rates.py + scripts/intl_phase0.py (grade, W3 C5); "
                "engine/global_rates.py; data/intl_bridge/ledger.json (C5)",
         horizon="21/42d fwd drawdown", ic=-0.064, dsr=0.9797,
         wired="not wired — CONTEXT (global 10y ≈ US 10y, corr 0.948; DD-cut not cost-justified)",
         extra=[("global-10y vs US-10y mom corr", "0.948 (≈ US 10y + noise)"),
                ("residual DD partial vs US legs", "−0.129 (survives but weak)"),
                ("SPY MaxDD cut (signal era)", "+1.1pp (−55.7% vs −56.8% B&H)"),
                ("Calmar strat vs B&H", "0.115 < 0.137 (return halved — not cost-justified)")]),
    _row("Cross-asset leading-caution votes booster  (credit+rates-vol+dollar — C8)",
         "跨资产领先警戒票增强器（信用+利率波动+美元 — C8）", "Cross-asset", "display",
         why="W3 VERDICT: CONTEXT — do NOT wire. The three cross-asset caution votes (credit "
             "HY-band/widening, rates-vol MOVE-band/leads-VIX, dollar risk-off bid) are "
             "reconstructed causally from their on-disk inputs (no vote history on disk — "
             "INTL-46). The votes>=2 while-equities-calm 'diverge' booster is CONTEXT on two "
             "counts: the credit/rates-vol votes are near-duplicates of the nfci/recession MRS "
             "legs (residual DD partial only −0.090), and over the signal-active era (from 2007) "
             "the de-risk strategy cuts SPY MaxDD only 0.6pp (−56.2% vs −56.8% B&H — below the "
             "1pp door) while cratering return (Calmar 0.105 < 0.153 B&H). It flattens out of "
             "good days without avoiding the bad ones. DSR 0.98 is SPY drift. weight_cap 0, "
             "kill=True — conditions._macro_risk_legs UNCHANGED.",
         why_zh="W3 结论：CONTEXT——不接线。三张跨资产警戒票（信用 HY 带/走阔、利率波动 MOVE 带/领先VIX、"
                "美元避险买盘）从磁盘输入因果重建（磁盘无投票历史——INTL-46）。票数≥2 且股市平静的'背离'增强器"
                "两点均属 CONTEXT：信用/利率波动票与 nfci/衰退 MRS 腿近乎重复（残差回撤偏相关仅 −0.090），"
                "且在降险时代（自2007起）降险策略仅削减 SPY 回撤 0.6pp（−56.2% 对 −56.8%，低于1pp门），"
                "却使回报暴跌（Calmar 0.105 < 0.153）。它在好日子空仓却躲不开坏日子。DSR 0.98 是 SPY 漂移。"
                "权重上限0，kill=True——conditions._macro_risk_legs 未变。",
         source="scripts/c8_leading_votes.py + scripts/intl_phase0.py (grade, W3 C8); "
                "engine/cross_asset_confirm.py (vote defs); data/intl_bridge/ledger.json (C8)",
         horizon="21/42d fwd drawdown", ic=-0.047, dsr=0.981,
         wired="not wired — CONTEXT (votes ≈ nfci/recession legs; DD-cut below door + return-killing)",
         extra=[("residual DD partial vs US legs", "−0.090 (near-dup of nfci/recession)"),
                ("SPY MaxDD cut (signal era)", "+0.6pp (below the 1pp door)"),
                ("Calmar strat vs B&H", "0.105 < 0.153 (return crushed)"),
                ("diverge-fire frequency", "~3% of days (votes≥2 + equities calm)")]),
    _row("Asia-semi read-through basket  (TSM+ASML ADRs → SMH — C6)",
         "亚洲半导体传导篮（台积电+阿斯麦ADR → SMH — C6）", "Asia-semi", "display",
         why="W4 VERDICT: CONTEXT — do NOT wire. ONE pre-registered EW Asia-semi basket "
             "(TSM + ASML, US-listed ADRs chosen ON PURPOSE to kill the timezone lag) graded vs "
             "SMH through the lead-lag kernel (HAC-t + BH-FDR + split-half) with ±2 trading-day "
             "earnings-print excision (12.8% of rows, INTL-49). The lag-0 correlation is huge "
             "(HAC-t +15.9, mean +0.82, FDR-reject, split-half stable) — but that is MECHANICAL "
             "CO-MEMBERSHIP (TSM + ASML are two of SMH's largest holdings), not a lead. NO lag>=1 "
             "link survives: lag1 HAC-t −1.67 (q_FDR 0.16, negative — it mirrors SMH's OWN lag-1 "
             "mean-reversion of −0.05), lag2/3/5 all |t|<2.1 and non-surviving. Because the ADRs "
             "trade in the US session there is not even the timezone-transmission lag-1 the raw "
             "local-index screen had — only same-day co-membership. The lead-lag kernel is the "
             "binding gate (ADJ-4): its pass excludes lag-0 by construction. Orthogonality vs "
             "SMH's OWN 5d/21d momentum leaves a wrong-signed residual (+0.07) — the basket adds "
             "nothing beyond 'semis lead semis'. weight_cap 0, kill=True — stock_score._axis_tailwind "
             "(the would-be DOWNGRADE-only seam) UNCHANGED.",
         why_zh="W4 结论：CONTEXT——请勿接入。一个预注册的等权亚洲半导体篮（台积电 + 阿斯麦，特意选用美股ADR"
                "以消除时区滞后），经领先滞后核（HAC-t + BH-FDR + 半样本），并剔除每次财报前后±2交易日窗口"
                "（占12.8%行，INTL-49），对 SMH 评分。滞后0相关极大（HAC-t +15.9，均值 +0.82，通过FDR，半样本"
                "稳定）——但这是机械式成分重叠（台积电+阿斯麦是 SMH 最大持仓之二），并非领先。无任何滞后≥1"
                "存活：滞后1 HAC-t −1.67（q 0.16，为负——与 SMH 自身滞后1均值回归 −0.05 一致），滞后2/3/5 "
                "均 |t|<2.1。因 ADR 在美股时段交易，连原始本地指数筛查中的时区传导滞后1也没有——只剩同日成分"
                "重叠。领先滞后核是约束门（ADJ-4），其判定按构造排除滞后0。相对 SMH 自身5日/21日动量的正交性"
                "留下错号残差（+0.07）——篮子在'半导体领先半导体'之外无增量。权重上限0，kill=True——"
                "stock_score._axis_tailwind（本应是仅降级的接入口）未变。",
         source="reports/intl-semi-readthrough-phase0.md (W4-C6 2026-07-02); "
                "scripts/c6_asia_semi_readthrough.py + scripts/intl_phase0.py --c6 (grade); "
                "data/intl_bridge/ledger.json (c6_asia_semi_readthrough); "
                "data/intl_bridge/c6_earnings_dates.json (print-excision source)",
         horizon="5d fwd (lead-lag kernel)", ic=0.157, dsr=0.446,
         wired="not wired — CONTEXT (lag-0 co-membership only; no lag>=1 lead survives the kernel)",
         extra=[("lag-0 HAC-t (co-membership)", "+15.9 (mean +0.82 — mechanical, TSM+ASML in SMH)"),
                ("lag-1 HAC-t", "−1.67 (q_FDR 0.16, does NOT survive; negative)"),
                ("lag>=1 kernel survivors", "0 (no tradeable lead; ADRs remove timezone lag)"),
                ("orthogonality vs SMH own momentum", "+0.07 residual (wrong sign; nothing beyond semis-lead-semis)"),
                ("print rows excised (±2td)", "838 (12.8%)")]),
    _row("Intl trend de-risk overlays  (price + total-return ETFs — C3)",
         "国际趋势降险叠加（价格指数 + 总回报ETF — C3）", "Intl ETF", "display",
         why="Two ports, one honest verdict: trend on tradeable intl is dead. The PRICE-index "
             "overlay cuts the tail for real (pooled MaxDD −18.5% vs −57.0%, DD-reduction CI "
             "[5.9,25.1,48.1] excludes 0) but its Sharpe edge FAILS split-half. The tradeable USD "
             "total-return ETF overlay (EWJ/EWG/EWU/EWY/EWA/EWQ) fails DSR (0.848<0.90) and "
             "split-half sign-flips, and macro-gating HARMS Korea (EWY −79.3% vs −74.1%, INTL-50). "
             "CONTEXT: crash-avoidance tail-insurance, never a scored alpha.",
         why_zh="两次移植，一个诚实结论：可交易国际标的的趋势已死。价格指数叠加确实削减尾部"
                "（合并回撤 −18.5% 对 −57.0%，区间不含零），但夏普边际未过两半。可交易美元总回报ETF叠加"
                "未过 DSR（0.848）且两半符号翻转，宏观门控还伤害韩国（EWY −79.3% 对 −74.1%）。"
                "CONTEXT：崩盘规避尾部保险，绝非计分阿尔法。",
         source="reports/intl-trend-overlay-phase0.md + intl-tr-trend-phase0.md; "
                "data/intl_bridge/ledger.json (C3)",
         horizon="overlay (daily)", dsr=0.848, sharpe=0.575,
         wired="not shipped — crash-avoidance risk-overlay (CONTEXT)",
         extra=[("price-index DD-cut", "−18.5% vs −57.0% (CI excludes 0)"),
                ("TR-ETF DSR", "0.848 (<0.90), split-half sign-flip"),
                ("macro-gate on EWY", "HARMS (−79.3% vs −74.1%)")]),
    _row("Per-pair FX conviction + cross-market lead/lag  (C4/C8)",
         "单对外汇信念 + 跨市场引导滞后（C4/C8）", "Forex / cross-asset", "display",
         why="The two intl read-through channels that shipped as CONTEXT. Per-pair FX conviction: "
             "EVERY pair fails DSR (best USDCAD 0.8607<0.90, most ≈0) → no pair-level gating on "
             "equities, ever (INTL-43). Cross-market lead/lag: 7/150 pairs survive HAC-t + BH-FDR "
             "and 5 are split-half stable — but ALL survivors are timezone lag-1 (US/global close → "
             "next Asia open), a transmission read, not a forecastable lead. Both are display "
             "context; the intl_bridge lead-lag kernel re-screens any new cross-market claim.",
         why_zh="两条以 CONTEXT 上线的国际读透渠道。单对外汇信念：每对都未过 DSR（最佳 USDCAD 0.8607，"
                "多数≈0）→ 绝不以对级门控股票（INTL-43）。跨市场引导滞后：150对中7对通过 HAC-t + BH-FDR、"
                "5对两半稳定——但幸存者全是时区滞后1（美/全球收盘→次日亚洲开盘），是传导读数而非可预测的引导。"
                "均为展示背景；intl_bridge 引导滞后核对任何新的跨市场主张重新筛选。",
         source="reports/forex-calibration.md + cross-asset-leadlag-phase0.md; "
                "data/intl_bridge/ledger.json (C4/C8)",
         horizon="varied", dsr=0.8607,
         wired="not shipped — transmission read / display context (CONTEXT)",
         extra=[("FX per-pair", "all fail DSR (best USDCAD 0.86)"),
                ("lead/lag survivors", "5 split-half stable, ALL lag-1 (timezone)")]),
    _row("European luxury → China-consumer read-through  (C7 — EW basket LVMUY+RMS.PA+CFR.SW)",
         "欧洲奢侈品 → 中国消费者读透（C7 — 等权组合 LVMUY+RMS.PA+CFR.SW）", "China / Intl", "display",
         why="W4-C7 VERDICT: CONTEXT — do NOT wire. The EW luxury basket (LVMUY ADR ~20y + "
             "RMS.PA/CFR.SW ~5y locals) rolling-return trend-turn signal carries NO statistically "
             "significant LEAD over FXI forward drawdowns at the declared 21d horizon. Lead-lag "
             "kernel: lag=0 strongly significant (t=11.75, contemporaneous same-session co-movement "
             "— luxury and FXI trade in overlapping US hours), but NO lagged link survives BH-FDR "
             "(lag=1: t=−1.49, p=0.14; lag=2/5: not significant). This is a TRANSMISSION READ: "
             "luxury and the Chinese consumer co-move in real-time, but the luxury basket does NOT "
             "lead FXI at any lag that survives multiple-testing correction. Strategy DSR=0.16 (far "
             "below the 0.90 door). Drawdown-reduction gate FAILS on Calmar: the flat-out-of-FXI "
             "overlay has negative Calmar (−0.008) while B&H FXI is positive (+0.045), meaning the "
             "strategy loses money while sitting out FXI recovery periods. Earnings-print excision: "
             "271 bars NaN'd (±2td around LVMH/Hermès/Richemont prints — causal method). "
             "Effective-N honesty: LVMUY has 4 crisis windows (20y), but the full 3-leg basket "
             "window covers only 1 declared crisis (rate_22) — the bias toward LVMUY's own momentum "
             "dominates. The validated channel is contemporaneous co-movement — useful as a display "
             "confirmer ('luxury and FXI are co-moving today') but structurally unable to carry the "
             "de-risk lead the C7 thesis required. weight_cap 0, kill=True; FXI target and all "
             "scorer seams UNCHANGED.",
         why_zh="W4-C7 结论：CONTEXT——不接线。等权奢侈品组合（LVMUY ADR ~20年 + RMS.PA/CFR.SW ~5年本地）"
                "滚动收益趋势翻转信号，在预声明的21日期限内，对 FXI 前瞻回撤无统计显著的引导。引导-滞后核：滞后=0 "
                "强显著（t=11.75，同期同时段共动——奢侈品与 FXI 在重叠的美国交易时段交易），但无滞后链路通过 "
                "BH-FDR（滞后=1：t=−1.49，p=0.14；滞后=2/5：不显著）。这是传导读数：奢侈品与中国消费者实时共动，"
                "但奢侈品组合在任何通过多重检验修正的滞后下均未领先 FXI。策略 DSR=0.16（远低于0.90门）。"
                "回撤削减门因Calmar失败：空仓叠加层 Calmar 为负（−0.008），而买持 FXI 为正（+0.045），意味着"
                "策略在 FXI 反弹期间踏空亏损。财报印发剔除：271根K线置NaN（LVMH/爱马仕/历峰公告±2交易日——因果方法）。"
                "有效N诚实说明：LVMUY 有4个危机窗口（20年），但全三腿组合窗口仅含1个声明危机（rate_22）——以"
                "LVMUY 自身动量为主导。已验证渠道为同期共动——可用作展示确认器（'今日奢侈品与 FXI 共动'），"
                "但在结构上无法承担 C7 论题所需的降险引导。权重上限0，kill=True；FXI 目标及所有计分器缝合点不变。",
         source="reports/intl-luxury-readthrough-phase0.md (W4-C7, 2026-07-02); "
                "scripts/c7_luxury_readthrough.py + scripts/intl_phase0.py --c7; "
                "data/intl_bridge/ledger.json (c7_luxury_china_consumer)",
         horizon="21d fwd drawdown (FXI)", dsr=0.1609, ic=-0.0695,
         wired="not wired — CONTEXT (no lagged lead survives BH-FDR; contemporaneous only)",
         extra=[("lead-lag kernel lag=0 t-stat", "11.75 (contemporaneous; same-session overlap)"),
                ("lag=1 HAC-t / p", "−1.49 / 0.14 (not significant; wrong sign)"),
                ("BH-FDR survivors at lag≥1", "NONE"),
                ("strategy DSR", "0.16 (far below 0.90 door)"),
                ("drawdown-reduction Calmar", "−0.008 strat vs +0.045 B&H (value-destroyer)"),
                ("earnings-print bars excised", "271 (±2td LVMH/Hermès/Richemont prints)"),
                ("effective-N (LVMUY 20y)", "4 crises; full-basket overlap: 1 crisis (rate_22)")]),
    _row("China external-driver radar  (C3 — governed by risk_radar_intl)",
         "中国外部驱动雷达（C3 — 由 risk_radar_intl 治理）", "China A", "display",
         why="Note-only entry for registry completeness. The validated China external-driver radar "
             "(breadth collapse, US rate shocks, US–CN differential, USD/CNH; composite ≥10%/42d "
             "drawdown lift 2.07×, p=0.01, CSI300-confirmed) already runs on main with committed "
             "forward logs and its OWN can_force maturation gate (≥30 graded, ≥8 alerts, realized "
             "lift ≥1.25×). The intl_bridge does NOT duplicate its machinery — it defers to "
             "engine/risk_radar_intl_audit.scorecard for the CN/HK/CA governance. Listed CONTEXT "
             "here so the registry is complete, not because it lacks edge.",
         why_zh="仅备注条目，用于登记完整性。已验证的中国外部驱动雷达（广度崩塌、美国利率冲击、美中利差、"
                "美元/离岸人民币；综合 ≥10%/42日回撤提升 2.07×，p=0.01，沪深300确认）已在 main 上运行，"
                "带提交的前瞻日志与自身的 can_force 成熟门。intl_bridge 不复制其机制——延用 "
                "risk_radar_intl_audit.scorecard 的中/港/加治理。此处列为 CONTEXT 仅为登记完整。",
         source="engine/risk_radar_intl.py (#711/#718) + risk_radar_intl_audit.py; "
                "data/intl_bridge/ledger.json (cn_external_radar)",
         horizon="42d fwd drawdown",
         wired="display-only on main until its own can_force gate matures (NOT duplicated by intl_bridge)",
         extra=[("composite lift", "2.07× (p=0.01), CSI300-confirmed"),
                ("governance", "risk_radar_intl_audit.can_force (≥30 graded, ≥8 alerts, lift ≥1.25×)")]),
    # ---- Day-3 SLF confirmer entries (2026-07-07) ----
    _row("Month-end bond-index extension day  (TLT / IEF last-day lift)",
         "月末债券指数展期日（TLT / IEF 尾日上涨）", "Rates", "confirmer",
         why="Bond index managers buy longer-duration bonds on the last trading day of each month "
             "to match their benchmark's new duration. TLT last-day mean return +0.183%/day "
             "(t_HAC=3.63, BH q=0.0009, n=287 months 2002-2026); IEF t=5.02, q~0. "
             "Known documented effect confirmed live. G2 split-half same-sign: both halves positive "
             "(H1=+0.258%, H2=+0.108%). G3 last-day > avg-other-days baseline: confirmed. "
             "Timing overlay candidacy: TLT/IEF entry-timing conditioner on last trading day of month. "
             "V1 (auction-cycle) and V2 (quarter-end pension rebalance) both NULL — only V3 survives.",
         why_zh="债券指数经理在每月最后一个交易日买入久期更长的债券以匹配基准新久期。"
                "TLT 月末日平均收益 +0.183%/天（t_HAC=3.63，BH q=0.0009，n=287个月，2002-2026）；"
                "IEF t=5.02，q≈0。已知文献效应，已在样本外确认。"
                "V1（拍卖周期）和V2（季末养老金再平衡）均为NULL——仅V3通过。",
         source="reports/d2-rates-calendar-flows-phase0.md; TLT/IEF Yahoo daily 2002-2026",
         horizon="1d (last trading day of month)",
         ic=None, t_hac=3.63, n=287,
         fdr_survivor=True,
         wired="none — timing overlay candidacy pending program review",
         dsr_family="d2_rates_calendar_flows",
         dsr_n_trials=11,
         dsr_basis="frozen-quote",
         extra=[("TLT last-day mean", "+0.183%/day, t_HAC=3.63, BH q=0.0009"),
                ("IEF last-day mean", "+0.110%/day, t_HAC=5.02, BH q~0"),
                ("V1 auction-cycle verdict", "NULL"),
                ("V2 QE-rebalance verdict", "NULL")]),
    _row("SEC comment-letter release drift  (substantive-review, 21d)",
         "SEC意见函披露漂移（实质性审查，21日）", "US S&P (broad)", "confirmer",
         why="When the SEC releases the full UPLOAD/CORRESP correspondence for a substantive "
             "review (≥3 SEC letters) on EDGAR, stocks drift lower over the next 21 trading days "
             "(massive store, post-2021): mean beta-adj AR -3.34%, t=-3.26, BH q=0.0044, n=1084. "
             "MANDATORY CAVEAT: effect concentrated 2023-2025 — first split-half not significant "
             "(first-half t=-1.396, p=0.163); second half highly significant (t=-5.008, p~0). "
             "Accrual required before any promotion. Light-review cells and yahoo-store cells "
             "are NULL. 7 of 8 pre-registered cells fail; single passing cell rides on post-2021 "
             "massive store only (survivorship bias present in both stores).",
         why_zh="当SEC在EDGAR上发布实质性审查（≥3封SEC来函）的完整往来信件时，"
                "股票在随后21个交易日内下跌（massive数据集，2021年后）：beta调整异常收益均值-3.34%，"
                "t=-3.26，BH q=0.0044，n=1084。"
                "强制警示：效应集中于2023-2025年——前半样本不显著（t=-1.396，p=0.163）；"
                "后半样本高度显著（t=-5.008，p~0）。需积累更多数据方可晋升。",
         source="reports/d2-comment-letter-release-phase0.md; EDGAR 2005-2026, massive+yahoo stores",
         horizon="21d",
         ic=None, t_hac=-3.26, n=1084,
         fdr_survivor=True,
         wired="none",
         dsr_family="d2_comment_letter_release",
         dsr_n_trials=8,
         dsr_basis="frozen-quote",
         extra=[("passing cell", "substantive/h21/massive: t=-3.26, q=0.0044, n=1084"),
                ("temporal caveat", "first-half t=-1.396 (p=0.163) not significant; concentrated 2023-2025"),
                ("survivorship", "both stores: only tickers alive at collection date"),
                ("7 of 8 cells", "NULL; promotion requires further accrual")]),
]


def _load_factor_table() -> dict | None:
    """The 11-factor leak-free PIT cross-section, read live from ic_scorecard.json."""
    p = config.data_dir() / "edgar" / "ic_scorecard.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — additive, never fatal
        return None


# Friendly labels for the raw factor keys in ic_scorecard.json.
_FACTOR_LABEL = {
    "value": ("Value", "价值"), "profitability": ("Profitability", "盈利能力"),
    "quality": ("Quality", "质量"), "investment": ("Investment (conservative)", "投资（保守）"),
    "payout": ("Payout yield", "股东收益率"), "low_vol": ("Low volatility", "低波动"),
    "low_beta": ("Low beta (BAB)", "低贝塔"), "short_interest": ("Low short interest", "低做空"),
    "accruals": ("Low accruals", "低应计"), "composite": ("Composite", "综合"),
    "composite_orth": ("Composite (orthogonalised)", "综合（正交化）"),
    "sue": ("SUE (earnings surprise)", "盈余惊喜"),
}


def _frontier_row(name, name_zh, market, readiness, readiness_zh, thesis, thesis_zh,
                  build, build_zh, gate, gate_zh, source, priority="P1",
                  fable_verdict="PENDING") -> dict:
    return {
        "name": name, "name_zh": name_zh, "market": market,
        "readiness": readiness, "readiness_zh": readiness_zh,
        "thesis": thesis, "thesis_zh": thesis_zh,
        "build": build, "build_zh": build_zh,
        "gate": gate, "gate_zh": gate_zh,
        "source": source, "priority": priority,
        "fable_verdict": fable_verdict,
    }


# Research backlog surfaced on the page. These are NOT validation verdicts and
# never influence a score until a pre-registered Phase-0 report earns a registry row.
FRONTIER: list[dict] = [
    _frontier_row(
        "SEC fails-to-deliver pressure",
        "SEC 交割失败压力",
        "US equities", "free data / new collector", "免费数据 / 新采集",
        "FTD balances are a short-sale constraint/informed-short proxy; literature finds "
        "higher FTD stocks later earn negative abnormal returns.",
        "交割失败余额可作为卖空约束/知情做空代理；文献显示高 FTD 股票随后异常收益偏负。",
        "Build SEC semi-monthly FTD panel, map CUSIP->ticker, normalize by float and dollar "
        "volume, then test high-FTD and rising-FTD buckets.",
        "建立 SEC 半月 FTD 面板，CUSIP 映射到 ticker，按流通股与成交额标准化，再测高 FTD 与上升 FTD 分组。",
        "21/63d rank-IC, FDR across FTD variants, incremental IC vs size, momentum, short volume.",
        "21/63日 rank-IC，FTD 变体间 FDR，相对规模、动量、短量的增量 IC。",
        "SEC FTD data + Stratmann/Welborn 2016",
        priority="P0", fable_verdict="BUILD",
    ),
    _frontier_row(
        "Borrow-fee / loan-fee anomaly",
        "借券费 / 融券费异常",
        "US equities", "paid data", "付费数据",
        "Loan fees are one of the strongest documented short-side predictors; free short "
        "interest is a weak substitute.",
        "借券费是文献中最强的做空侧预测变量之一；免费做空余额只是弱替代。",
        "If a borrow-fee vendor is approved, archive daily fee/utilization PIT and test high-fee "
        "underperformance plus long-only exclusion value.",
        "若接入借券费供应商，按日归档费用/利用率时点数据，测试高费股票跑输及多头排除价值。",
        "Must beat FINRA short volume, FTD, size, low-price and microcap controls after costs.",
        "必须在成本后优于 FINRA 短量、FTD、规模、低价股和微盘控制项。",
        "Engelberg et al. Management Science 2024",
        priority="P0-data",
    ),
    _frontier_row(
        "Option informed-flow lens",
        "期权知情流镜头",
        "US options", "partial plumbing", "部分管线已在",
        "Buyer-to-open option put/call flow and IV spreads have evidence of informed trading; "
        "public EOD put/call is much weaker.",
        "买方开仓期权看跌/看涨流与隐波价差有知情交易证据；公开 EOD put/call 弱很多。",
        "Extend options_flow / ivspread history: separate stock-vs-index hedging, buyer-open "
        "proxies, scheduled-news windows, and O/S volume.",
        "扩展 options_flow / ivspread 历史：区分股票与指数对冲、买方开仓代理、预定新闻窗口与期权/股票量。",
        "Event-window and 1/5/21d forward tests; require improvement over GEX/200dma baselines.",
        "事件窗口及1/5/21日前瞻测试；必须优于 GEX/200日均线基线。",
        "Pan/Poteshman 2006; CBOE/POLYGON options feeds",
        priority="P1",
    ),
    _frontier_row(
        "EDGAR attention shock",
        "EDGAR 关注度冲击",
        "US filings", "free but heavy", "免费但重型",
        "SEC log files expose filing-demand attention; spikes around stale vs fresh filings may "
        "separate retail attention from informed acquisition.",
        "SEC 日志显示投资者对公告的阅读需求；围绕新旧文件的流量冲击可区分散户关注与信息获取。",
        "Prototype on 2020-2025 logs only: de-robot, aggregate human views by filing/ticker, "
        "join to 8-K/10-Q/10-K events.",
        "先用2020-2025日志试做：去机器人，按公告/ticker 聚合人类阅读量，并接入8-K/10-Q/10-K事件。",
        "Filing-day and post-filing drift; Brier calibration if used as event probability.",
        "公告日与公告后漂移；若作为事件概率则做 Brier 校准。",
        "SEC EDGAR log files; Drake/Roulstone/Thornock literature",
        priority="P1",
    ),
    _frontier_row(
        "Overnight/intraday tug-of-war",
        "隔夜/日内拉锯",
        "US equities", "OHLC on disk", "OHLC 已在盘",
        "Some anomalies accrue overnight while intraday returns mean-revert; this may improve "
        "entry timing without creating a new signal.",
        "部分异常收益在隔夜兑现而日内均值回归；它可能改善入场时点，而不是创造新信号。",
        "Decompose existing momentum/reversal/insider/payout candidates into close-open and "
        "open-close legs using adjusted OHLC.",
        "用调整后 OHLC 将现有动量/反转/内部人/payout 候选拆成 close-open 与 open-close 两腿。",
        "Net-of-open-spread viability, split-half, and no alpha claim unless tradable at open.",
        "扣除开盘价差后验证、两半稳定；除非开盘可交易，否则不声称 alpha。",
        "Lou/Polk/Skouras 2019",
        priority="P1", fable_verdict="KILLED",
    ),
    _frontier_row(
        "Treasury auction absorption",
        "美债拍卖吸收力",
        "US rates", "collector exists", "采集器已在",
        "Auction demand metrics can identify weak/strong duration absorption, but the data are "
        "mostly ex-post and must be framed as event context.",
        "拍卖需求指标可识别久期吸收强弱，但数据多为事后，需作为事件背景处理。",
        "Use treasury_auctions.parquet: bid-to-cover, indirect share, dealer takedown, issue size.",
        "使用 treasury_auctions.parquet：bid-to-cover、间接投标、一级交易商承接、发行量。",
        "Event study on TLT/IEF/curve moves; forbid scoring unless pre-auction predictors beat term premium.",
        "对 TLT/IEF/曲线做事件研究；除非拍卖前预测项优于期限溢价，否则禁止计分。",
        "TreasuryDirect auction query + 2025 auction-demand research",
        priority="P1", fable_verdict="BUILD",
    ),
    _frontier_row(
        "COT exhaustion matrix",
        "COT 仓位耗尽矩阵",
        "Cross-asset futures", "collector exists", "采集器已在",
        "COT already helps capitulation context; a broader matrix may detect crowded futures "
        "positions across rates, FX and commodities.",
        "COT 已用于投降背景；更广的矩阵可能识别利率、外汇与商品期货拥挤仓位。",
        "Compute 3y rolling spec-position percentiles, first differences, and cross-asset crowding "
        "clusters from existing COT store.",
        "从现有 COT 库计算3年滚动投机仓位分位、变化量与跨资产拥挤簇。",
        "Must beat dumb price trend / VIX gates; likely confirmer or graveyard, not scored.",
        "必须优于朴素价格趋势 / VIX 门；大概率是确认项或墓地，而非计分。",
        "CFTC COT public reporting environment",
        priority="P2", fable_verdict="KILLED",
    ),
    _frontier_row(
        "Crypto funding + on-chain stress",
        "加密资金费率 + 链上压力",
        "Crypto", "partial plumbing", "部分管线已在",
        "Funding, MVRV, realized cap and holder-profit metrics may add cycle/tail context to the "
        "BTC Vector, but single-asset crypto samples are tiny.",
        "资金费率、MVRV、实现市值与持有人盈利指标或可补充 BTC 向量的周期/尾部背景，但单资产样本极小。",
        "Separate raw engine from human gates; test funding-rate extremes and Coin Metrics "
        "valuation deltas as drawdown/entry confirmers.",
        "分离纯引擎与人工门；把资金费率极值和 Coin Metrics 估值变化作为回撤/入场确认项测试。",
        "Leave-one-cycle-out, brake-matched 200dma baseline, DSR with explicit trial ledger.",
        "逐周期剔除、匹配200日均线刹车基线、带明确试验账本的 DSR。",
        "Coin Metrics Community API; crypto funding literature",
        priority="P2",
    ),
    _frontier_row(
        "Supply-chain pressure impulse",
        "供应链压力脉冲",
        "Macro / sectors", "free data", "免费数据",
        "GSCPI-style shocks may matter more for inflation-sensitive sectors than for broad SPY timing.",
        "GSCPI 类冲击对通胀敏感行业可能比对广义 SPY 择时更有用。",
        "Collect FRBNY GSCPI; test level/change/surprise vs breakevens, CPI/PPI revisions, "
        "transports, semis, retailers and commodity sectors.",
        "采集纽约联储 GSCPI；测试水平/变化/意外值相对盈亏平衡通胀、CPI/PPI修正、运输、半导体、零售与商品板块。",
        "Sector-relative IC with macro controls; no broad-risk claim unless it beats NFCI/OFR.",
        "行业相对 IC 加宏观控制；除非优于 NFCI/OFR，否则不声明广义风险信号。",
        "NY Fed GSCPI",
        priority="P2",
    ),
    _frontier_row(
        "Lottery/MAX anti-chase flag",
        "彩票/MAX 反追高标记",
        "US equities", "price-only", "仅价格",
        "Extreme one-day winners often underperform later, but replication literature warns the "
        "edge can vanish outside microcaps.",
        "极端单日赢家随后常跑输，但复验文献警告该边际在排除微盘后可能消失。",
        "Compute prior-month MAX and idio-skew, then test as a subtract-only extension/fragility "
        "overlay inside liquid universes.",
        "计算上月 MAX 与特质偏度，在高流动性股票内作为减分式拉伸/脆弱叠加层测试。",
        "NYSE breakpoints, value weights, cost and liquidity gates; expect graveyard unless incremental.",
        "NYSE 断点、市值加权、成本与流动性门；除非有增量，否则预期进墓地。",
        "Bali/Cakici/Whitelaw 2011; Hou/Xue/Zhang replication",
        priority="P2", fable_verdict="KILLED",
    ),
]


def _resolve_dsr_provenance(registry: list[dict]) -> None:
    """Stamp each row's DSR n_trials with a live-ledger or frozen-quote passport (W1d).

    For a row carrying ``dsr_family``: if that family has a budget in the persistent Trial
    Ledger, use the live ``effective_n`` (basis ``'ledger'``) — the number is now maintained,
    not asserted. Otherwise fall back to the row's frozen ``dsr_n_trials`` with its
    ``dsr_expiry``, and flag it EXPIRED once today is past the expiry (basis ``'frozen-quote'``
    / ``'expired'``). Mutates rows in place, adding a ``dsr_provenance`` dict the template can
    render. Degrade-safe: any ledger error leaves the frozen quote in place."""
    try:
        from datetime import date
        from engine.trial_ledger import TrialLedger
        led = TrialLedger()
        today = date.today().isoformat()
    except Exception:  # noqa: BLE001
        led = None
        today = None
    for r in registry:
        fam = r.get("dsr_family")
        if not fam:
            continue
        live_n = 0
        if led is not None:
            try:
                live_n = led.effective_n(fam) if led.declared_budget(fam) or led.literal_n(fam) else 0
            except Exception:  # noqa: BLE001
                live_n = 0
        if live_n:
            r["dsr_provenance"] = {"n_trials": live_n, "basis": "ledger", "family": fam}
        else:
            exp = r.get("dsr_expiry")
            expired = bool(exp and today and today > exp)
            r["dsr_provenance"] = {
                "n_trials": r.get("dsr_n_trials"),
                "basis": "expired" if expired else (r.get("dsr_basis") or "frozen-quote"),
                "family": fam, "expiry": exp, "expired": expired,
            }


def _build_foundry_block(repo_root: Path | None = None) -> dict:
    """Assemble the Signal Foundry panel payload (D1).

    Reads data/signal_foundry/{candidates.jsonl, results/*.json, promotions.jsonl,
    lane_status.json} DEFENSIVELY — all may be absent.

    Returns a dict with key 'present' (bool).  When False, only {'present': False}
    is returned.  When True the dict contains the full funnel + row list + docket.
    All keys are always set so the template can reference them unconditionally.
    """
    if repo_root is None:
        repo_root = Path(__file__).parent.parent

    sf_dir = repo_root / "data" / "signal_foundry"

    # ---- 0. Fast-path: nothing filed yet -----------------------------------
    candidates_path = sf_dir / "candidates.jsonl"
    results_dir = sf_dir / "results"
    if not sf_dir.exists() or not candidates_path.exists():
        return {"present": False}

    # ---- 1. Load candidates.jsonl (tolerate corrupt lines) ----------------
    candidates: list[dict] = []
    try:
        with candidates_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    candidates.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    if not candidates:
        return {"present": False}

    # ---- 2. Load results/*.json -------------------------------------------
    from engine.signal_foundry.results import load_results, promotion_docket

    all_results: list[dict] = []
    try:
        all_results = load_results(repo_root)
    except Exception:  # noqa: BLE001
        pass

    results_by_id: dict[str, dict] = {}
    for r in all_results:
        sid = (r.get("spec") or {}).get("id") or r.get("spec_id") or r.get("id")
        if sid:
            results_by_id[str(sid)] = r

    # ---- 3. Load lane_status.json -----------------------------------------
    lane_status: dict = {}
    ls_path = sf_dir / "lane_status.json"
    if ls_path.exists():
        try:
            lane_status = json.loads(ls_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    # ---- 4. Load promotions.jsonl for human adjudication marks -----------
    adjudicated_ids: set[str] = set()
    prom_path = sf_dir / "promotions.jsonl"
    if prom_path.exists():
        try:
            with prom_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = row.get("spec_id") or row.get("id") or ""
                        if sid:
                            adjudicated_ids.add(str(sid))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    # ---- 5. Funnel counts -------------------------------------------------
    statuses = [c.get("status", "") for c in candidates]
    proposed = len(candidates)
    screen_rejected = sum(1 for s in statuses if s == "screen_rejected")
    registered = sum(1 for s in statuses if s in ("registered", "tested"))
    tested = sum(1 for s in statuses if s == "tested")

    verdict_counts: dict[str, int] = {}
    for r in all_results:
        v = r.get("verdict", "")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    pass_candidates = verdict_counts.get("pass_candidate", 0)
    promoted = sum(1 for c in candidates if c.get("status") == "promoted")

    funnel = {
        "proposed": proposed,
        "screen_rejected": screen_rejected,
        "registered": registered,
        "tested": tested,
        "pass_candidates": pass_candidates,
        "promoted": promoted,
    }

    # ---- 6. Per-candidate rows --------------------------------------------
    forward_dir = sf_dir / "forward"
    rows: list[dict] = []
    for c in candidates:
        sid = str(c.get("id") or c.get("spec_id") or "")
        res = results_by_id.get(sid, {})

        # Forward accrual day count
        fwd_days = 0
        if forward_dir.exists() and sid:
            fwd_path = forward_dir / f"{sid}.jsonl"
            if fwd_path.exists():
                try:
                    with fwd_path.open(encoding="utf-8") as fh:
                        fwd_days = sum(1 for ln in fh if ln.strip())
                except OSError:
                    pass

        # Stats from result record — harness.py writes the NESTED schema:
        #   stats = {n_obs, effective_months, full_ic, hac:{t,...}, split_half,
        #            era_split, block_bootstrap_ci, dsr:{dsr,...}|None}
        #   placebos = {time_shift:{shift_pctile,...}, negative_lag:{...}}
        # Map to the flat display keys used by the template.
        stats: dict = res.get("stats", {}) if res else {}
        placebos: dict = res.get("placebos", {}) if res else {}

        _hac: dict = stats.get("hac") or {}
        _dsr_dict = stats.get("dsr")  # is a dict or None from harness
        _dsr_scalar = (_dsr_dict.get("dsr") if isinstance(_dsr_dict, dict) else None)
        _shift = (placebos.get("time_shift") or {})

        # Seed provenance
        seed_prov = c.get("seed_provenance") or {}
        source = seed_prov.get("source") or c.get("source") or ""

        # Gates (from result or spec)
        spec_in_result = (res.get("spec") or {}) if res else {}
        gates = spec_in_result.get("gates") or c.get("gates") or {}

        # Thesis (short form — first 120 chars)
        thesis_full = c.get("thesis") or spec_in_result.get("thesis") or ""
        thesis_short = (thesis_full[:120] + "…") if len(thesis_full) > 120 else thesis_full

        # Verdict
        verdict = res.get("verdict") if res else c.get("verdict") or None
        status = c.get("status") or "proposed"

        rows.append({
            "id": sid,
            "name": c.get("name") or sid,
            "name_zh": c.get("name_zh") or "",
            "market": c.get("market") or "",
            "thesis": thesis_short,
            "thesis_full": thesis_full,
            "seed_provenance_source": source,
            "status": status,
            "verdict": verdict or "",
            # Stats — mapped from real harness nested schema
            "ic": stats.get("full_ic"),
            "t_hac": _hac.get("t"),
            "dsr": _dsr_scalar,
            "n_eff_months": stats.get("effective_months"),
            "placebo_pct": _shift.get("shift_pctile"),
            # Gates
            "gates": gates,
            "registered_at": c.get("registered_at") or "",
            "forward_days": fwd_days,
            # For expanded detail: data paths and pipeline
            "data": c.get("data") or spec_in_result.get("data") or [],
            "pipeline": (c.get("feature") or spec_in_result.get("feature") or {}).get("pipeline") or [],
            "target": c.get("target") or spec_in_result.get("target") or {},
        })

    # Sort: pass_candidates first, then by id
    _VERDICT_ORDER = {
        "pass_candidate": 0, "null": 1, "era_specific": 2, "unstable": 2,
        "insufficient_power": 3, "insufficient_history": 3, "data_missing": 4,
        "forbidden": 5, "error": 5, "": 6,
    }
    rows.sort(key=lambda r: (_VERDICT_ORDER.get(r["verdict"], 6), r["id"]))

    # ---- 7. Promotion docket ----------------------------------------------
    docket: list[dict] = []
    try:
        docket = promotion_docket(repo_root)
    except Exception:  # noqa: BLE001
        pass

    # ---- 8. Disclaimers (SF-R1/R3) ----------------------------------------
    disclaimer_en = (
        "machine lane — own FDR family; display-tier; nothing here is wired "
        "to any score"
    )
    disclaimer_zh = "机器信号道 — 独立FDR族；仅展示层；不接入任何评分"

    return {
        "present": True,
        "funnel": funnel,
        "rows": rows,
        "docket": docket,
        "lane_status": lane_status,
        "disclaimer_en": disclaimer_en,
        "disclaimer_zh": disclaimer_zh,
    }


def build_scorecard() -> dict:
    """Assemble the full Signal Lab payload for the template. Pure assembler."""
    warnings: list[str] = []  # A9: collect build warnings

    ft = _load_factor_table()
    factor_rows: list[dict] = []
    fdr_survivors_factor = 0
    if ft:
        for key, m in ft.get("factors", {}).items():
            lab = _FACTOR_LABEL.get(key, (key, key))
            surv = bool(m.get("survives_fdr"))
            fdr_survivors_factor += int(surv)
            factor_rows.append({
                "key": key, "name": lab[0], "name_zh": lab[1],
                "ic": m.get("mean_ic"), "ic_ir": m.get("ic_ir"),
                "t_hac": m.get("t_hac"), "q_fdr": m.get("q_fdr"),
                "hit": m.get("hit"), "n": m.get("n"), "survives": surv,
            })
        # sort by IC descending so the (failing) leaders sit on top
        factor_rows.sort(key=lambda r: (r["ic"] is None, -(r["ic"] or 0)))

    # W1d: resolve each DSR quote's multiple-testing n_trials from the Trial Ledger (live) or
    # surface it as a stamped frozen-quote with an expiry — no more self-certifying constants.
    _resolve_dsr_provenance(REGISTRY)

    # A10: audit source references for each registry row
    _audit_source_refs(REGISTRY)

    # group the curated registry by tier, preserving TIERS order
    by_tier: dict[str, list[dict]] = {t["key"]: [] for t in TIERS}
    for r in REGISTRY:
        by_tier.setdefault(r["tier"], []).append(r)

    tiers_out = []
    for t in TIERS:
        rows = by_tier.get(t["key"], [])
        if not rows:
            continue
        w = VERDICT_WORD[t["key"]]
        tiers_out.append({**t, "verdict_word": w[0], "verdict_word_zh": w[1],
                          "rows": rows, "count": len(rows)})

    summary = {k: len(by_tier.get(k, [])) for k in
               ("scored", "confirmer", "display", "killed", "pending")}
    summary["total"] = len(REGISTRY)
    summary["factor_survivors"] = fdr_survivors_factor
    summary["factor_total"] = len(factor_rows)

    # Point-in-time data stamps (ChatGPT proposal #2): what the page "knew" and when.
    factor_meta = {}
    if ft:
        factor_meta = {"span": ft.get("span"), "horizon_d": ft.get("horizon_d"),
                       "rebalances": ft.get("rebalances"),
                       "median_universe": ft.get("median_universe"),
                       "leak_free": ft.get("leak_free"),
                       "universe": ft.get("universe"),
                       "survivorship_biased": ft.get("survivorship_biased"),
                       "caveat": ft.get("caveat"),
                       "price_span": ft.get("price_span"),
                       "collinearity": ft.get("collinearity")}

    # survivor names (+ sign) so the page's prose adapts to whichever branch's
    # scorecard it reads — and can flag that a survivor with a NEGATIVE IC is
    # anti-predictive, not tradeable.
    survivors = [{"name": r["name"], "ic": r["ic"]} for r in factor_rows if r["survives"]]

    # A3: frontier rows for the page table
    frontier_rows = FRONTIER + page_frontier_rows()
    # Chip counts computed from ACTUAL rendered rows (not docket-wide FABLE_VERDICTS totals)
    frontier_chip_counts = _compute_frontier_chip_counts(frontier_rows)
    # Docket-wide summary still available as frontier_phase0_summary
    # A2: load adjudications from file (replaces hardcoded _waves_adjudication_block)
    adjudications = _load_adjudications(warnings)
    # Back-compat: expose the first (most-recent) adjudication as waves_adjudication for
    # tests and template code that reference it by the old key
    waves_adjudication = adjudications[0] if adjudications else {}

    # A12: total docket candidate count (derived, not hardcoded)
    from engine.signal_frontier_docket import CANDIDATES as _CANDIDATES
    docket_candidate_count = len(_CANDIDATES)

    # D1: Signal Foundry machine-lane block (SF-R1/R3/R10)
    repo_root = Path(__file__).parent.parent
    foundry = _build_foundry_block(repo_root)

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "tiers": tiers_out,
        "summary": summary,
        "factor_rows": factor_rows,
        "factor_survivors": survivors,
        "factor_meta": factor_meta,
        "frontier_rows": frontier_rows,
        "frontier_chip_counts": frontier_chip_counts,      # A3
        "frontier_phase0_summary": phase0_summary(),
        "docket_candidate_count": docket_candidate_count,  # A3 / A12
        "adjudications": adjudications,                    # A2
        "waves_adjudication": waves_adjudication,          # back-compat
        "warnings": warnings,                              # A9
        "foundry": foundry,                                # D1: Signal Foundry panel
    }


_ADJUDICATIONS_PATH = Path(__file__).parent.parent / "data" / "signal_lab" / "adjudications.json"


def _load_adjudications(warnings: list[str]) -> list[dict]:
    """Load adjudication events from data/signal_lab/adjudications.json (A2).

    Returns a list of adjudication-event objects sorted date-desc.
    Appends to ``warnings`` on missing/corrupt file and returns empty list.
    """
    if not _ADJUDICATIONS_PATH.exists():
        warnings.append(
            f"adjudications.json missing at {_ADJUDICATIONS_PATH} — adjudication panel will be empty"
        )
        return []
    try:
        events = json.loads(_ADJUDICATIONS_PATH.read_text(encoding="utf-8"))
        if not isinstance(events, list):
            raise ValueError("top-level must be a JSON array")
        return sorted(events, key=lambda e: e.get("date", ""), reverse=True)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"adjudications.json corrupt ({exc}) — adjudication panel will be empty")
        return []


# Source-ref extraction pattern (A10): tokens like path/to/file.md or reports/x
_SOURCE_REF_RE = re.compile(r"[\w./\-]+\.md|reports/[\w./\-]+")


def _audit_source_refs(registry: list[dict]) -> None:
    """For each registry row, extract .md / reports/<x> references from source string.

    Attaches row['source_refs'] = [{'ref': str, 'exists': bool}].
    Checks both reports/ and research/ directories under the repo root.
    Never crashes on odd source strings (A10).
    """
    root = Path(__file__).parent.parent
    reports_dir = root / "reports"
    research_dir = root / "research"

    for r in registry:
        source = r.get("source") or ""
        try:
            refs: list[dict] = []
            seen: set[str] = set()
            for token in _SOURCE_REF_RE.findall(source):
                if token in seen:
                    continue
                seen.add(token)
                # Strip leading path separators to form a relative path
                clean = token.lstrip("/")
                # Check under reports/ first, then research/, then as absolute within repo
                exists = (
                    (reports_dir / clean).exists()
                    or (research_dir / clean).exists()
                    or (root / clean).exists()
                    or (reports_dir / Path(clean).name).exists()
                    or (research_dir / Path(clean).name).exists()
                )
                refs.append({"ref": token, "exists": exists})
            r["source_refs"] = refs
        except Exception:  # noqa: BLE001
            r["source_refs"] = []


def _compute_frontier_chip_counts(frontier_rows: list[dict]) -> dict:
    """Compute fable_verdict counts from the ACTUAL rendered frontier rows (A3).

    This ensures prose counts match the table below them.
    Returns a dict: {'BUILD': n, 'PROBE': n, 'PILOT': n, 'KILLED': n, ...}
    """
    counts: Counter = Counter(r.get("fable_verdict", "PENDING") for r in frontier_rows)
    return dict(counts)
