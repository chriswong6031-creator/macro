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
from datetime import datetime, timezone
from pathlib import Path

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


def _row(name, name_zh, market, tier, why, why_zh, source, *, horizon="",
         ic=None, ic_ir=None, t_hac=None, q_fdr=None, dsr=None, sharpe=None,
         hit=None, n=None, fdr_survivor=None, wired="", extra=None) -> dict:
    """One scorecard row. Numeric fields are floats or None (None => '—')."""
    return {
        "name": name, "name_zh": name_zh, "market": market, "tier": tier,
        "horizon": horizon, "ic": ic, "ic_ir": ic_ir, "t_hac": t_hac,
        "q_fdr": q_fdr, "dsr": dsr, "sharpe": sharpe, "hit": hit, "n": n,
        "fdr_survivor": fdr_survivor, "wired": wired,
        "why": why, "why_zh": why_zh, "source": source,
        "extra": extra or [],   # list of (label, value_str) quoted context stats
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

    # ---- DISPLAY-ONLY -------------------------------------------------------
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


def build_scorecard() -> dict:
    """Assemble the full Signal Lab payload for the template. Pure assembler."""
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

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "tiers": tiers_out,
        "summary": summary,
        "factor_rows": factor_rows,
        "factor_survivors": survivors,
        "factor_meta": factor_meta,
    }
