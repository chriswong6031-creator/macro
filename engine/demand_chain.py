"""Customer-demand chains — the L2 ("independent observable") leg of the Demand
Desk (see memory demand-desk-divergence). Phase 0 shipped the panel, Phase 1 the
first chain (AI capex), this generalizes to MULTIPLE chains + feeds a scored
ledger (engine/demand_ledger.py).

THE IDEA. The Demand Context panel's third row asks for a *management-independent*
read on forward demand — a number from someone ELSE's filings that the name in
question cannot manufacture. The cleanest free instances are supply-chain
linkages where one cohort's spending IS another cohort's demand:

  • ai_datacenter (LEADING): hyperscaler CAPEX (MSFT/Alphabet/Amazon/Meta/Oracle)
    is the demand pool for AI accelerators, memory, networking, WFE and the power
    buildout. Capex commitments lead chip revenue ~2-4 quarters → a genuine
    forward signal. THIS chain emits falsifiable, scored ledger theses.

  • housing (COINCIDENT): aggregate homebuilder REVENUE (DHI/LEN/PHM/NVR/TOL/KBH)
    is the end-market for building-products suppliers. This is a coincident
    cross-read, NOT a leading indicator (materials are consumed during the build,
    revenue books at closing) — so it is DISPLAY-ONLY and never emits a scored
    thesis. Its value is the divergence check: do supplier estimates match the
    builders' actual volume trend?

For each beneficiary we compare the independent observable's trend to the priced
consensus (analyst revisions already on the record) and label the divergence.

HONESTY (display-only, never scored into any allocation, never a buy signal):
- Cross-company PROXY, not the name's own bookings; its share can shift.
- Narrow panels, ANNUAL cadence, mixed fiscal-year ends — coarse trend reads.
- "Divergence" flags disagreement; it does NOT predict the resolution.

Pure functions only — all I/O lives in scripts/build_stock_library.py (display)
and engine/demand_ledger.py (the scored ledger).
"""
from __future__ import annotations

from typing import Any

# ─── Chain configuration ──────────────────────────────────────────────────────
# Each chain: a spender cohort whose aggregate `signal_kind` (capex or revenue)
# is the demand pool, mapped to beneficiary baskets. `tier_order` sets which tier
# wins when a name sits in several (most-specific first). `leading` gates whether
# the chain earns falsifiable ledger theses (engine/demand_ledger.py).
CHAINS: list[dict[str, Any]] = [
    {
        "key": "ai_datacenter",
        "label_en": "AI / datacenter", "label_zh": "AI／数据中心",
        "signal_kind": "capex", "leading": True, "horizon_d": 126,
        "spender_en": "Hyperscaler capex", "spender_zh": "云厂商资本开支",
        "spenders": [["MSFT"], ["GOOGL", "GOOG"], ["AMZN"], ["META"], ["ORCL"]],
        "min_cover": 4,
        "tier_order": ["ai_semiconductors", "ai_neoclouds", "semicap_equipment",
                       "ai_infra", "data_center_power", "power_grid", "nuclear_power"],
        "tiers": {
            "ai_semiconductors": {"key": "compute", "strength": "direct",
                                  "en": "AI accelerator / compute silicon", "zh": "AI 加速器／算力芯片"},
            "ai_infra": {"key": "compute", "strength": "direct",
                         "en": "AI infrastructure (compute, memory, networking)", "zh": "AI 基础设施（算力／内存／网络）"},
            "ai_neoclouds": {"key": "neocloud", "strength": "direct",
                             "en": "GPU neocloud capacity", "zh": "GPU 新云算力"},
            "semicap_equipment": {"key": "wfe", "strength": "lagged",
                                  "en": "wafer-fab equipment (one step back, longer lead)", "zh": "晶圆制造设备（上游一环，前置更长）"},
            "data_center_power": {"key": "power", "strength": "indirect",
                                  "en": "data-center power & cooling", "zh": "数据中心供电与散热"},
            "power_grid": {"key": "power", "strength": "indirect",
                           "en": "power & grid buildout", "zh": "电力与电网建设"},
            "nuclear_power": {"key": "power", "strength": "indirect",
                              "en": "nuclear / SMR power for data centers", "zh": "数据中心核电／小型堆"},
        },
    },
    {
        "key": "housing",
        "label_en": "Homebuilder demand", "label_zh": "房屋建筑商需求",
        "signal_kind": "revenue", "leading": False, "horizon_d": 63,
        "spender_en": "Homebuilder volume (revenue)", "spender_zh": "建筑商销量（营收）",
        "spenders": [["DHI"], ["LEN"], ["PHM"], ["NVR"], ["TOL"], ["KBH"]],
        "min_cover": 4,
        "tier_order": ["housing"],
        # Only the building-PRODUCTS suppliers in the housing basket are beneficiaries;
        # the builders themselves are the demand SOURCE, not a beneficiary.
        "beneficiary_only": {"BLDR", "MAS", "SHW", "OC", "BLD", "FBIN", "MHK", "LII", "CARR"},
        "tiers": {
            "housing": {"key": "products", "strength": "coincident",
                        "en": "building-products suppliers", "zh": "建材供应商"},
        },
    },
]

_TREND_WORD = {
    "accelerating": ("accelerating", "加速"),
    "expanding": ("still expanding", "持续扩张"),
    "peaking": ("decelerating", "增速放缓"),
    "contracting": ("contracting", "收缩"),
    "flat": ("flat", "持平"),
    "unknown": ("unclear", "不明"),
}


def _yr_totals(by_ticker: dict[str, dict[int, float]]) -> dict[int, tuple[float, int]]:
    """Sum spender values per fiscal-year label → {fy: (total, n_spenders)}."""
    out: dict[int, list[float]] = {}
    for series in by_ticker.values():
        for fy, v in series.items():
            if v is None or v != v:
                continue
            out.setdefault(int(fy), []).append(float(v))
    return {fy: (sum(vs), len(vs)) for fy, vs in out.items()}


def _trend(yoy_now: float | None, yoy_prev: float | None) -> str:
    if yoy_now is None:
        return "unknown"
    if yoy_now <= -2.0:
        return "contracting"
    if yoy_prev is not None and yoy_now > 5.0 and yoy_now >= yoy_prev - 3.0:
        return "accelerating" if yoy_now >= yoy_prev else "expanding"
    if yoy_now > 5.0:
        return "peaking"
    return "flat"


def _aggregate(by_ticker: dict[str, dict[int, float]], min_cover: int) -> dict | None:
    """Aggregate a spender cohort's annual values into a trend signal."""
    totals = _yr_totals(by_ticker)
    years = sorted(fy for fy, (_t, n) in totals.items() if n >= min_cover)
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
        "spenders": list(by_ticker),
        "fy_latest": latest,
        "total_latest_bn": round(cap_now / 1e9, 1),
        "total_prior_bn": round(cap_prev / 1e9, 1),
        "yoy_pct": yoy,
        "yoy_prev_pct": yoy_prev,
        "trend": _trend(yoy, yoy_prev),
        "series": series,
        "n_spenders": totals[latest][1],
    }


def compute_signals(statements_df) -> dict[str, dict]:
    """Compute the aggregate demand signal for every configured chain from the
    EDGAR statements frame (columns: ticker, fy, capex, revenue). Returns
    {chain_key: signal}; a chain is omitted when its data is too thin.

    `statements_df` is duck-typed: needs `.ticker`, `.fy`, and the chain's
    `signal_kind` column, with row access via itertuples / boolean masks. Passing
    a list-of-dicts fallback is also supported for tests.
    """
    # Normalize to {ticker: {fy: {col: val}}} once, so we don't re-scan per chain.
    rows: dict[str, dict[int, dict[str, float]]] = {}
    if hasattr(statements_df, "itertuples"):
        for r in statements_df.itertuples():
            t = getattr(r, "ticker", None)
            fy = getattr(r, "fy", None)
            if t is None or fy is None or fy != fy:
                continue
            rows.setdefault(str(t), {})[int(fy)] = {
                "capex": getattr(r, "capex", None), "revenue": getattr(r, "revenue", None)}
    else:
        for r in statements_df:
            rows.setdefault(str(r["ticker"]), {})[int(r["fy"])] = {
                "capex": r.get("capex"), "revenue": r.get("revenue")}

    out: dict[str, dict] = {}
    for chain in CHAINS:
        col = chain["signal_kind"]
        by_ticker: dict[str, dict[int, float]] = {}
        for aliases in chain["spenders"]:
            for a in aliases:                       # first alias with data wins (count once)
                series = {fy: vals[col] for fy, vals in rows.get(a, {}).items()
                          if vals.get(col) is not None and vals[col] == vals[col]}
                if series:
                    by_ticker[a] = series
                    break
        sig = _aggregate(by_ticker, chain["min_cover"])
        if sig:
            sig["chain_key"] = chain["key"]
            out[chain["key"]] = sig
    return out


def _consensus_dir(revisions: dict | None) -> str:
    """Direction of the priced consensus from analyst-revision fields already on
    the record: 'rising' / 'flat' / 'falling' / 'none'."""
    if not revisions:
        return "none"
    drift = revisions.get("est_chg_90d")
    if drift is None:
        drift = revisions.get("est_chg_30d")
    breadth = revisions.get("breadth")
    if drift is None and breadth is None:
        return "none"
    score = 0
    if drift is not None:
        score += 1 if drift > 1.0 else -1 if drift < -1.0 else 0
    if breadth is not None:
        score += 1 if breadth > 0.2 else -1 if breadth < -0.2 else 0
    return "rising" if score > 0 else "falling" if score < 0 else "flat"


def _divergence(trend: str, consensus_dir: str) -> str:
    capex_up = trend in ("accelerating", "expanding")
    capex_down = trend in ("contracting", "peaking")
    if consensus_dir == "none":
        return "signal_only"
    if capex_up and consensus_dir == "rising":
        return "aligned"
    if capex_up and consensus_dir in ("flat", "falling"):
        return "ahead_of_consensus"
    if capex_down and consensus_dir == "rising":
        return "consensus_at_risk"
    return "aligned"


def chain_read(signals: dict[str, dict], baskets_membership: list[dict] | None,
               revisions: dict | None, ticker: str | None = None) -> dict | None:
    """Per-beneficiary divergence read across all chains. `ticker` is required to
    apply a chain's beneficiary allowlist (e.g. housing suppliers). Returns None
    for names not on any chain or when the matched chain has no signal. Bilingual,
    display-only."""
    if not signals or not baskets_membership:
        return None
    slugs = {b.get("slug") for b in baskets_membership if isinstance(b, dict)}
    for chain in CHAINS:
        sig = signals.get(chain["key"])
        if not sig:
            continue
        bonly = chain.get("beneficiary_only")
        for slug in chain["tier_order"]:
            if slug not in slugs or slug not in chain["tiers"]:
                continue
            if bonly is not None and (ticker is None or ticker not in bonly):
                continue                            # housing: suppliers only
            tier = {"slug": slug, **chain["tiers"][slug]}
            return _build_read(chain, sig, tier, revisions)
    return None


def _build_read(chain: dict, sig: dict, tier: dict, revisions: dict | None) -> dict:
    trend = sig["trend"]
    cons = _consensus_dir(revisions)
    div = _divergence(trend, cons)
    tw_en, tw_zh = _TREND_WORD.get(trend, _TREND_WORD["unknown"])
    yoy = sig.get("yoy_pct")
    yoy_s = (("+" if yoy >= 0 else "") + f"{yoy:.0f}%") if yoy is not None else "n/a"
    tot = sig.get("total_latest_bn")
    coincident = not chain["leading"]

    headline_en = (f"{chain['spender_en']} {tw_en} ({yoy_s} YoY to ~${tot:.0f}B) — "
                   f"the demand pool for {tier['en']}")
    headline_zh = (f"{chain['spender_zh']}{tw_zh}（同比{yoy_s}，约 ${tot:.0f}B）——"
                   f"{tier['zh']}的需求来源")

    # divergence read — leading chains speak of "running ahead"; coincident chains
    # of an end-market "cross-read" mismatch.
    if coincident:
        DIV = {
            "aligned": ("End-market demand and analyst estimates agree — the demand picture is consistent.",
                        "终端需求与分析师预期一致——需求面相互印证。"),
            "ahead_of_consensus": ("End-market volume is holding up better than this supplier's analyst revisions imply — a positive cross-read (coincident, not leading).",
                                   "终端销量好于该供应商分析师评级调整所暗示的——一个正面的交叉印证（同步，非领先）。"),
            "consensus_at_risk": ("End-market volume is softening while this supplier's estimates still rise — the consensus may be ahead of the end market. Caution.",
                                  "终端销量走弱，而该供应商预期仍在上修——共识可能领先于终端需求。需谨慎。"),
            "signal_only": ("No analyst-revision data for this name; we show the independent end-market read on its own.",
                            "该股暂无分析师评级调整数据，故仅单独展示独立的终端需求读数。"),
        }
        caveat_en = (f"COINCIDENT cross-read from {sig['n_spenders']} homebuilders' annual revenue "
                     f"(FY{sig['fy_latest']}) — an end-market sanity check, NOT a leading indicator "
                     "(materials book before builder revenue). Display-only; not a buy signal.")
        caveat_zh = (f"基于 {sig['n_spenders']} 家房屋建筑商年度营收（FY{sig['fy_latest']}）的同步交叉读数"
                     "——终端需求的合理性检验，并非领先指标（建材入账早于建筑商营收）。仅作展示，非买入信号。")
    else:
        DIV = {
            "aligned": ("Customer demand is strong AND analyst estimates already reflect it — this "
                        "forward-demand strength is largely IN THE PRICE, not an edge.",
                        "客户需求强劲，且分析师预期已反映——这部分前瞻需求基本已计入价格，并非优势。"),
            "ahead_of_consensus": ("Customer capex is running AHEAD of this name's analyst revisions — an "
                                   "independent forward-demand signal not yet fully in consensus estimates. "
                                   "Variant worth watching (not a buy signal).",
                                   "客户资本开支跑在该股分析师评级调整之前——一个尚未充分计入共识的独立前瞻需求信号。"
                                   "值得作为变体关注（非买入信号）。"),
            "consensus_at_risk": ("Customer capex is decelerating while analyst estimates are still rising — "
                                  "the priced consensus may be ahead of the forward-demand pool. Caution.",
                                  "客户资本开支增速放缓，而分析师预期仍在上修——已被定价的共识可能领先于前瞻需求。需谨慎。"),
            "signal_only": ("No analyst-revision data for this name, so we show the independent "
                            "customer-demand read on its own (no consensus to compare against).",
                            "该股暂无分析师评级调整数据，故仅单独展示独立的客户需求读数（无共识可对比）。"),
        }
        caveat_en = (f"Cross-company proxy from {sig['n_spenders']} hyperscalers' annual capex "
                     f"(FY{sig['fy_latest']}); leads chip revenue ~2-4 quarters ({tier['strength']} link "
                     "for this tier). Display-only — the name's share of capex can shift; not a buy signal.")
        caveat_zh = (f"基于 {sig['n_spenders']} 家云厂商年度资本开支（FY{sig['fy_latest']}）的跨公司代理；"
                     f"领先芯片收入约 2-4 个季度（该层为{tier['strength']}链接）。仅作展示——"
                     "该股在资本开支中的份额可能变化；非买入信号。")
    read_en, read_zh = DIV[div]

    return {
        "chain_key": chain["key"],
        "leading": chain["leading"],
        "tier": tier["key"],
        "tier_slug": tier["slug"],
        "divergence": div,
        "consensus_dir": cons,
        "trend": trend,
        "yoy_pct": yoy,
        "total_latest_bn": tot,
        "fy_latest": sig["fy_latest"],
        "horizon_d": chain["horizon_d"],
        "series": sig["series"],
        "spenders": sig["spenders"],
        "headline": {"en": headline_en, "zh": headline_zh},
        "read": {"en": read_en, "zh": read_zh},
        "caveat": {"en": caveat_en, "zh": caveat_zh},
    }
