"""Customer-capex demand chain — the first L2 ("independent observable") leg of
the Demand Desk (see memory demand-desk-divergence; Phase 0 shipped the panel,
this is Phase 1).

THE IDEA. The Demand Context panel has three layers: trailing accounting truth
(backward), priced consensus (revisions / forward P/E — already in the price),
and the missing third leg: a *management-independent* read on forward demand.
This module builds the cleanest free instance of that third leg for the AI-capex
complex: aggregate hyperscaler capital expenditure.

Why it is genuinely independent + leading: NVDA / AVGO / semicap demand is
literally the capex budget of MSFT, Alphabet, Amazon, Meta and Oracle. That
number lives in the SPENDERS' own 10-Ks — it cannot be manufactured by the
beneficiary's IR team, and signed/began capex programs lead recognized chip
revenue by ~2-4 quarters (longer for wafer-fab equipment). So for a name in the
AI-infrastructure chain we can ask the question the panel exists to ask: is the
forward-demand story (rising customer capex) ALREADY in the name's consensus, or
is customer capex running ahead of / behind what analysts have priced?

HONESTY (this is display-only, never scored, never a buy signal):
- It is a CROSS-COMPANY PROXY, not the name's own bookings. The beneficiary's
  *share* of the capex can shift (e.g. custom ASIC vs merchant GPU).
- Narrow panel (n~5 spenders), ANNUAL cadence, mixed fiscal-year ends — a coarse
  trend read, not a quarterly nowcast.
- "Divergence vs consensus" flags where the two disagree; it does NOT predict the
  resolution. Consensus may be right and the chain wrong.

Pure functions only — all I/O (reading statements.parquet, attaching to the
per-stock record) lives in scripts/build_stock_library.py.
"""
from __future__ import annotations

from typing import Any

# The AI-capex SPENDERS whose aggregate capital expenditure IS the forward-demand
# pool for the compute chain. Each entry lists ticker aliases (Alphabet files
# under GOOGL/GOOG depending on the share class in the cache); the first alias
# with data wins, counted once.
SPENDERS: list[list[str]] = [["MSFT"], ["GOOGL", "GOOG"], ["AMZN"], ["META"], ["ORCL"]]

# Which beneficiary baskets sit on the chain, and how directly capex transmits to
# their demand. `lead` is the rough order; `strength` tempers the language (the
# further from the GPU purchase order, the weaker/noisier the link).
CHAIN_TIERS: dict[str, dict[str, Any]] = {
    "ai_semiconductors": {"key": "compute", "strength": "direct",
                          "label_en": "AI accelerator / compute silicon",
                          "label_zh": "AI 加速器／算力芯片"},
    "ai_infra": {"key": "compute", "strength": "direct",
                 "label_en": "AI infrastructure (compute, memory, networking)",
                 "label_zh": "AI 基础设施（算力／内存／网络）"},
    "ai_neoclouds": {"key": "neocloud", "strength": "direct",
                     "label_en": "GPU neocloud capacity",
                     "label_zh": "GPU 新云算力"},
    "semicap_equipment": {"key": "wfe", "strength": "lagged",
                          "label_en": "wafer-fab equipment (one step back, longer lead)",
                          "label_zh": "晶圆制造设备（上游一环，前置更长）"},
    "data_center_power": {"key": "power", "strength": "indirect",
                          "label_en": "data-center power & cooling",
                          "label_zh": "数据中心供电与散热"},
    "power_grid": {"key": "power", "strength": "indirect",
                   "label_en": "power & grid buildout",
                   "label_zh": "电力与电网建设"},
    "nuclear_power": {"key": "power", "strength": "indirect",
                      "label_en": "nuclear / SMR power for data centers",
                      "label_zh": "数据中心核电／小型堆"},
}

# Minimum spenders that must report a fiscal year for it to enter the aggregate
# (avoids a half-filed latest year collapsing the total).
_MIN_COVER = 4


def _yr_totals(capex_by_ticker: dict[str, dict[int, float]]) -> dict[int, tuple[float, int]]:
    """Sum spender capex per fiscal-year label → {fy: (total, n_spenders)}.

    Alphabet's two share classes are de-duped by the alias resolution in
    compute_capex_signal, so each economic spender contributes at most once.
    """
    out: dict[int, list[float]] = {}
    for series in capex_by_ticker.values():
        for fy, v in series.items():
            if v is None or v != v:
                continue
            out.setdefault(int(fy), []).append(float(v))
    return {fy: (sum(vs), len(vs)) for fy, vs in out.items()}


def _trend(yoy_now: float | None, yoy_prev: float | None) -> str:
    """Label the capex trajectory from the latest YoY growth and the one before
    it (the 2nd-derivative: is growth itself rising?)."""
    if yoy_now is None:
        return "unknown"
    if yoy_now <= -2.0:
        return "contracting"
    if yoy_prev is not None and yoy_now > 5.0 and yoy_now >= yoy_prev - 3.0:
        # still growing AND not decelerating meaningfully
        return "accelerating" if yoy_now >= yoy_prev else "expanding"
    if yoy_now > 5.0:
        return "peaking"          # still growing but decelerating hard
    return "flat"


def compute_capex_signal(capex_by_ticker: dict[str, dict[int, float]]) -> dict | None:
    """Aggregate the SPENDERS' annual capex into a forward-demand trend signal.

    `capex_by_ticker` maps ticker → {fiscal_year: capex_usd}. Returns None when
    too little data is present to read a trend. Values are reported in USD; the
    signal exposes $bn for display.
    """
    totals = _yr_totals(capex_by_ticker)
    # only fiscal years with enough spender coverage to be comparable
    years = sorted(fy for fy, (_t, n) in totals.items() if n >= _MIN_COVER)
    if len(years) < 2:
        return None
    series = [[fy, round(totals[fy][0] / 1e9, 1)] for fy in years]
    latest, prior = years[-1], years[-2]
    cap_now, cap_prev = totals[latest][0], totals[prior][0]
    yoy = round((cap_now / cap_prev - 1.0) * 100.0, 1) if cap_prev else None
    yoy_prev = None
    if len(years) >= 3:
        c2 = totals[years[-3]][0]
        yoy_prev = round((cap_prev / c2 - 1.0) * 100.0, 1) if c2 else None
    return {
        "spenders": [s for s in capex_by_ticker],
        "fy_latest": latest,
        "capex_latest_bn": round(cap_now / 1e9, 1),
        "capex_prior_bn": round(cap_prev / 1e9, 1),
        "yoy_pct": yoy,
        "yoy_prev_pct": yoy_prev,
        "trend": _trend(yoy, yoy_prev),
        "series": series,
        "n_spenders": totals[latest][1],
    }


def _consensus_dir(revisions: dict | None) -> str:
    """Direction of the priced consensus from the analyst-revision fields already
    on the record: 'rising' / 'flat' / 'falling' / 'none'."""
    if not revisions:
        return "none"
    drift = revisions.get("est_chg_90d")
    if drift is None:
        drift = revisions.get("est_chg_30d")
    breadth = revisions.get("breadth")
    score = 0
    if drift is not None:
        score += 1 if drift > 1.0 else -1 if drift < -1.0 else 0
    if breadth is not None:
        score += 1 if breadth > 0.2 else -1 if breadth < -0.2 else 0
    if drift is None and breadth is None:
        return "none"
    return "rising" if score > 0 else "falling" if score < 0 else "flat"


def _beneficiary_tier(baskets_membership: list[dict] | None) -> dict | None:
    """Pick the most-direct chain tier this name belongs to (compute > neocloud >
    wfe > power), or None if it is not on the AI-capex chain."""
    if not baskets_membership:
        return None
    slugs = {b.get("slug") for b in baskets_membership if isinstance(b, dict)}
    # Most-specific tier wins. semicap_equipment precedes ai_infra so WFE names that
    # sit in BOTH (AMAT/LRCX/KLAC) are tagged the more accurate "one step back" tier.
    order = ["ai_semiconductors", "ai_neoclouds", "semicap_equipment", "ai_infra",
             "data_center_power", "power_grid", "nuclear_power"]
    for slug in order:
        if slug in slugs and slug in CHAIN_TIERS:
            return {"slug": slug, **CHAIN_TIERS[slug]}
    return None


def _divergence(trend: str, consensus_dir: str) -> str:
    """Compare the independent observable (customer-capex trend) to the priced
    consensus direction."""
    capex_up = trend in ("accelerating", "expanding")
    capex_down = trend in ("contracting", "peaking")
    if consensus_dir == "none":
        return "signal_only"
    if capex_up and consensus_dir == "rising":
        return "aligned"                 # strong AND already in the price
    if capex_up and consensus_dir in ("flat", "falling"):
        return "ahead_of_consensus"      # the valuable variant: capex outrunning estimates
    if capex_down and consensus_dir == "rising":
        return "consensus_at_risk"       # capex rolling over while estimates still climb
    return "aligned"


_TREND_WORD = {
    "accelerating": ("accelerating", "加速"),
    "expanding": ("still expanding", "持续扩张"),
    "peaking": ("decelerating", "增速放缓"),
    "contracting": ("contracting", "收缩"),
    "flat": ("flat", "持平"),
    "unknown": ("unclear", "不明"),
}


def chain_read(signal: dict | None, baskets_membership: list[dict] | None,
               revisions: dict | None) -> dict | None:
    """Per-beneficiary divergence read. Returns None for names not on the chain or
    when no capex signal exists. Bilingual, display-only."""
    if not signal:
        return None
    tier = _beneficiary_tier(baskets_membership)
    if tier is None:
        return None
    trend = signal["trend"]
    cons = _consensus_dir(revisions)
    div = _divergence(trend, cons)
    tw_en, tw_zh = _TREND_WORD.get(trend, _TREND_WORD["unknown"])
    yoy = signal.get("yoy_pct")
    yoy_s = (("+" if yoy >= 0 else "") + f"{yoy:.0f}%") if yoy is not None else "n/a"
    cap = signal.get("capex_latest_bn")

    headline_en = (f"Hyperscaler capex {tw_en} ({yoy_s} YoY to ~${cap:.0f}B) — "
                   f"the demand pool for {tier['label_en']}")
    headline_zh = (f"云厂商资本开支{tw_zh}（同比{yoy_s}，约 ${cap:.0f}B）——"
                   f"{tier['label_zh']}的需求来源")

    DIV_READ = {
        "aligned": (
            "Customer demand is strong AND analyst estimates already reflect it — "
            "this forward-demand strength is largely IN THE PRICE, not an edge.",
            "客户需求强劲，且分析师预期已反映——这部分前瞻需求基本已计入价格，并非优势。"),
        "ahead_of_consensus": (
            "Customer capex is running AHEAD of this name's analyst revisions — an "
            "independent forward-demand signal not yet fully in consensus estimates. "
            "Variant-worth watching (not a buy signal).",
            "客户资本开支跑在该股分析师评级调整之前——一个尚未充分计入共识的独立前瞻需求信号。"
            "值得作为变体关注（非买入信号）。"),
        "consensus_at_risk": (
            "Customer capex is decelerating while analyst estimates are still rising — "
            "the priced consensus may be ahead of the forward-demand pool. Caution.",
            "客户资本开支增速放缓，而分析师预期仍在上修——已被定价的共识可能领先于前瞻需求。需谨慎。"),
        "signal_only": (
            "No analyst-revision data for this name, so we show the independent "
            "customer-demand read on its own (no consensus to compare against).",
            "该股暂无分析师评级调整数据，故仅单独展示独立的客户需求读数（无共识可对比）。"),
    }
    read_en, read_zh = DIV_READ[div]

    caveat_en = (f"Cross-company proxy from {signal['n_spenders']} hyperscalers' "
                 f"annual capex (FY{signal['fy_latest']}); leads chip revenue ~2-4 "
                 f"quarters ({tier['strength']} link for this tier). Display-only — "
                 "the name's share of capex can shift; not a buy signal.")
    caveat_zh = (f"基于 {signal['n_spenders']} 家云厂商年度资本开支（FY{signal['fy_latest']}）的跨公司代理；"
                 f"领先芯片收入约 2-4 个季度（该层为{tier['strength']}链接）。仅作展示——"
                 "该股在资本开支中的份额可能变化；非买入信号。")

    return {
        "tier": tier["key"],
        "tier_slug": tier["slug"],
        "divergence": div,
        "consensus_dir": cons,
        "trend": trend,
        "yoy_pct": yoy,
        "capex_latest_bn": cap,
        "fy_latest": signal["fy_latest"],
        "series": signal["series"],
        "spenders": signal["spenders"],
        "headline": {"en": headline_en, "zh": headline_zh},
        "read": {"en": read_en, "zh": read_zh},
        "caveat": {"en": caveat_en, "zh": caveat_zh},
    }
