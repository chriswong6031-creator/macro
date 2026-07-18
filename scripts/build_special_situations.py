"""Special Situations desk — DISPLAY-ONLY page builder (site/special_situations.html).

Renders the event-driven special-situations desk from engine.special_situations
(SCORED=False). The daily step: refresh the EDGAR event store (collector), classify
the ambiguous filings from their text (text lane), then render the page grouped by
category + a landing-hub snapshot. Reuses the shared bilingual / theme conventions.

Run: python -m scripts.build_special_situations
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter
from datetime import datetime, timezone, date as _date_type

from engine import special_situations as sse
from lib import config
from lib.pages import write_page
from scripts.build_vector import C

log = logging.getLogger(__name__)

# display order (lead with the highest-signal active categories)
CAT_ORDER = [
    "Activist Campaigns", "Acquisitions", "Going-Private", "Tender Offers",
    "Divestitures", "Spin-Offs", "New SpinCos", "Strategic Reviews",
    "Capital Returns", "Issuer Tenders", "Rights Offerings", "Restructuring",
    "Litigation Outcomes", "Deal Terminations", "Liquidations", "Delistings", "SPACs",
    "Management Changes", "Other",
]
_GREEN = "#1FA971"
CAT_COLOR = {
    "Activist Campaigns": C["indigo"], "Acquisitions": C["blue"], "Going-Private": C["indigo"],
    "Tender Offers": C["blue"], "Divestitures": _GREEN, "Spin-Offs": _GREEN, "New SpinCos": _GREEN,
    "Strategic Reviews": C["amber"], "Capital Returns": _GREEN, "Issuer Tenders": _GREEN,
    "Rights Offerings": C["amber"], "Restructuring": C["amber"], "Litigation Outcomes": C["amber"],
    "Deal Terminations": C["red"], "Liquidations": C["red"], "Delistings": C["red"], "SPACs": C["muted"],
    "Management Changes": C["muted"], "Other": C["muted"],
}
CAT_ZH = {
    "Activist Campaigns": "维权行动", "Acquisitions": "收购", "Going-Private": "私有化",
    "Tender Offers": "要约收购", "Divestitures": "剥离", "Spin-Offs": "分拆",
    "New SpinCos": "新分拆公司", "Strategic Reviews": "战略评估", "Capital Returns": "资本回报",
    "Issuer Tenders": "公司回购要约", "Rights Offerings": "配股", "Restructuring": "重组",
    "Litigation Outcomes": "诉讼结果", "Deal Terminations": "交易终止", "Liquidations": "清算",
    "Delistings": "退市", "SPACs": "SPAC", "Management Changes": "管理层变动", "Other": "其他",
}
STAGE_ZH = {
    "initiated": "启动", "escalation": "升级", "live": "进行中", "announced": "已宣布",
    "vote-scheduled": "已定投票", "registered": "已登记", "terminated": "已终止",
    "filed": "已申报", "notice": "通知", "completed": "已完成", "change": "变动",
    "proxy-fight": "代理权之争", "target-response": "标的回应",
    "closed": "已成交", "de-SPAC": "去SPAC",
}
GRADE_WORD = {"A": "Strong setup", "B": "Building", "C": "Early"}
GRADE_WORD_ZH = {"A": "布局成熟", "B": "布局中", "C": "早期"}
TIER_WORD = {"T1": "Setup live", "T2": "Setup live", "T3": "Setup forming", "T4": "Early"}
TIER_WORD_ZH = {"T1": "买点已现", "T2": "买点已现", "T3": "设置成形中", "T4": "早期"}


def _txt(v, dash: str = "—") -> str:
    """Clean a value for display: None / NaN / 'nan' -> dash."""
    if v is None:
        return dash
    if isinstance(v, float) and v != v:
        return dash
    s = str(v).strip()
    return dash if (not s or s.lower() == "nan") else s


def _arb_str(a: dict | None) -> str:
    """Compact merger-arb line: 'spread +8.3% · +24%/yr · ~120d · break -31%'."""
    if not a:
        return ""
    parts = [f"spread {a['gross_spread_pct']:+.1f}%"]
    if a.get("annualized_pct") is not None:
        parts.append(f"{a['annualized_pct']:+.0f}%/yr")
    if a.get("days_to_close"):
        parts.append(f"~{a['days_to_close']}d")
    if a.get("downside_on_break_pct") is not None:
        parts.append(f"break {a['downside_on_break_pct']:+.0f}%")
    return " · ".join(parts)


def _prior_str(p: dict | None) -> str:
    """Compact historical-context line (kept for detail panel / data-tip receipt).

    v1: 'hist 60% win · +2.4%/20d (n=10)'
    v2 (if drawdown/pre-drift available): adds '· dd −4.1% · pre +1.2%'
    insufficient: 'insufficient history (n=K)' — never "" and never a number (m1 fix).
    """
    if not p:
        return ""
    # Insufficient-history case: must print, not silently absent (m1 fix)
    if p.get("insufficient"):
        k = p.get("n", 0)
        return f"insufficient history (n={k})"
    bits = []
    if p.get("win_20d_pct") is not None:
        bits.append(f"{p['win_20d_pct']:.0f}% win")
    if p.get("med_ret_20d_pct") is not None:
        bits.append(f"{p['med_ret_20d_pct']:+.1f}%/20d")
    # v2 additive fields (None on old-schema files — skipped gracefully)
    if p.get("max_dd_20d_pct") is not None:
        bits.append(f"dd {p['max_dd_20d_pct']:+.1f}%")
    if p.get("pre_drift_pct") is not None:
        bits.append(f"pre {p['pre_drift_pct']:+.1f}%")
    if not bits:
        return ""
    n = p.get("n", 0)
    return "hist " + " · ".join(bits) + f" (n={n})"


def _prior_plain(p: dict | None) -> str:
    """Plain-language EN sentence for the detail panel (Tier 2)."""
    if not p:
        return ""
    if p.get("insufficient"):
        k = p.get("n", 0)
        return f"Not enough history for this event type (only {k} past cases)."
    n = p.get("n", 0)
    if n < 5:
        return f"Not enough history for this event type (only {n} past cases)."
    win = p.get("win_20d_pct")
    med = p.get("med_ret_20d_pct")
    if win is None and med is None:
        return ""
    # "about X in 10" phrasing
    if win is not None:
        ratio = win / 10.0  # e.g. 60% -> "6 in 10"
        ratio_str = f"about {ratio:.0f} in 10" if ratio == int(ratio) else f"about {ratio:.1f} in 10"
    else:
        ratio_str = None
    if win is not None and med is not None:
        direction = "higher" if med >= 0 else "lower"
        med_str = f"{abs(med):.1f}%" if abs(med) >= 0.1 else "roughly flat"
        return (
            f"In {n} similar past events, {ratio_str} were {direction} a month later "
            f"(median {'+' if med >= 0 else '−'}{med_str})."
        )
    if win is not None:
        return f"In {n} similar past events, {ratio_str} were higher a month later."
    med_str = f"{abs(med):.1f}%" if abs(med) >= 0.1 else "roughly flat"
    return f"In {n} similar past events, the median return over a month was {'+' if med >= 0 else '−'}{med_str}."


def _prior_plain_zh(p: dict | None) -> str:
    """Plain-language ZH sentence for the detail panel (Tier 2)."""
    if not p:
        return ""
    if p.get("insufficient"):
        k = p.get("n", 0)
        return f"此类事件历史案例不足（仅{k}例），暂无统计参考。"
    n = p.get("n", 0)
    if n < 5:
        return f"此类事件历史案例不足（仅{n}例），暂无统计参考。"
    win = p.get("win_20d_pct")
    med = p.get("med_ret_20d_pct")
    if win is None and med is None:
        return ""
    if win is not None and med is not None:
        # Chinese: "过去N次同类事件中，约六成一个月后走高（中位 +X%）"
        tens = round(win / 10)
        zh_nums = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        tens_str = zh_nums[tens] if 0 <= tens <= 10 else f"{tens}"
        direction = "走高" if med >= 0 else "走低"
        med_str = f"{abs(med):.1f}%"
        sign = "+" if med >= 0 else "−"
        return (
            f"过去{n}次同类事件中，约{tens_str}成一个月后{direction}"
            f"（中位 {sign}{med_str}）。"
        )
    if win is not None:
        tens = round(win / 10)
        zh_nums = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        tens_str = zh_nums[tens] if 0 <= tens <= 10 else f"{tens}"
        return f"过去{n}次同类事件中，约{tens_str}成一个月后走高。"
    med_str = f"{abs(med):.1f}%"
    sign = "+" if med >= 0 else "−"
    return f"过去{n}次同类事件中，一个月中位涨跌幅为{sign}{med_str}。"


def _usd_m(mc) -> str:
    if mc is None:
        return "—"
    try:
        mc = float(mc)
    except (TypeError, ValueError):
        return "—"
    if mc != mc:  # NaN
        return "—"
    return f"${mc / 1000:.1f}B" if mc >= 1000 else f"${mc:.0f}M"


def _age_days(date_filed: str | None, built_dt: datetime) -> int | None:
    """Integer days from date_filed to built date (snap date, not wall clock)."""
    if not date_filed:
        return None
    try:
        filed = datetime.strptime(date_filed[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        snap_day = built_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = snap_day - filed
        return max(0, delta.days)
    except Exception:
        return None


def _tech_tokens(row: dict) -> list[str]:
    """Derive filter tokens from tech/setup fields."""
    tokens: list[str] = []
    tier = row.get("tier")
    if tier in ("T1", "T2"):
        tokens.append("live")
    elif tier == "T3":
        tokens.append("forming")
    # oversold: either 2w or 1m
    if row.get("washout_2w") or row.get("washout_1m"):
        tokens.append("oversold")
    # momentum
    w1_macd = row.get("w1_macd")
    w1_stoch = row.get("w1_stoch")
    if w1_macd == "crossed" or w1_stoch == "crossed":
        tokens.append("momup")
    elif w1_macd == "near" or w1_stoch == "near":
        tokens.append("turning")
    return tokens


def _momentum_state(row: dict) -> str | None:
    """Merged momentum state for display: 'crossed', 'near', or None."""
    w1_macd = row.get("w1_macd")
    w1_stoch = row.get("w1_stoch")
    if w1_macd == "crossed" or w1_stoch == "crossed":
        return "crossed"
    if w1_macd == "near" or w1_stoch == "near":
        return "near"
    return None


def _momentum_tip(row: dict) -> str:
    """Detail text for the momentum chip data-tip."""
    parts = []
    w1_macd = row.get("w1_macd")
    w1_stoch = row.get("w1_stoch")
    if w1_macd == "crossed":
        parts.append("Weekly MACD crossed above signal")
    elif w1_macd == "near":
        parts.append("Weekly MACD approaching cross")
    if w1_stoch == "crossed":
        parts.append("Weekly StochRSI K crossed D")
    elif w1_stoch == "near":
        parts.append("Weekly StochRSI approaching cross")
    return " · ".join(parts) if parts else ""


def _oversold_tip(row: dict) -> str:
    """Detail text for the oversold chip data-tip."""
    parts = []
    if row.get("washout_2w"):
        parts.append("2-week StochRSI ≤ 35")
    if row.get("washout_1m"):
        parts.append("Monthly RSI deeply oversold")
    return " · ".join(parts) if parts else "Deeply oversold reading on weekly timeframe"


def build(refresh: bool = True) -> str:
    if refresh:
        from collectors import special_situations as col
        from collectors import special_news as colnews
        from collectors import special_intl as colintl
        from lib import config as _config
        ss = _config.load().get("special_situations", {}) or {}
        try:
            col.fetch_events()                                   # sweep new daily-index dates (bounded by watermark)
            # bounded per-build slices so one run can never stall the whole engine job;
            # progress persists in events.parquet, so the backlog converges over days.
            col.enrich_text(limit=int(ss.get("text_per_build", 1500)))       # keyword pre-filter (cached)
            col.enrich_filers(limit=int(ss.get("filer_per_build", 250)))     # P3.2 13D cover-page reporting person
            col.enrich_classify(limit=int(ss.get("classify_per_build", 150)))  # P1.1 LLM-verify (gated; no-op w/o key)
            col.enrich_summaries(limit=int(ss.get("summary_per_build", 200)))  # P1.3 LLM summary (gated; no-op w/o key)
            col.enrich_extraction(limit=int(                                 # W5 qual_extraction.v1 on top-importance 8-Ks
                _config.load().get("qual_extraction", {}).get("extract_per_build", 100)))
            colnews.fetch_news_situations()                      # P2.1 newswire form-absent categories (gated)
            colintl.fetch_intl_situations()                      # Phase 4 UK/Canada intl lanes (gated per market)
            from collectors import special_prices as colpx
            colpx.fetch_arb_prices()                             # P1.2 price ADR/OTC deal targets (best-effort)
        except Exception as e:  # noqa: BLE001 — desk degrades to last-known on a fetch outage
            log.warning("special_situations refresh failed (rendering last-known): %s", e)

    snap = sse.desk_payload()

    # Intelligence enrichment (display-tier: tech/ident/favor/setup)
    intel_cov: dict = {}
    intel_ctx: dict = {}
    try:
        from engine import special_sits_intel as ssi
        cov_result = ssi.enrich(snap["situations"])
        intel_cov = cov_result.get("coverage", {})
        intel_ctx = ssi.build_context_feed(snap["situations"])
    except Exception as e:  # noqa: BLE001
        log.warning("special_sits_intel failed: %s", e)

    sits = snap.get("situations", [])

    # Parse the built timestamp for age_days computation
    built_str = snap.get("built") or ""
    try:
        built_dt = datetime.strptime(built_str[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except Exception:
        built_dt = datetime.now(timezone.utc)

    # Build all rows flat, sorted by score desc then newest-first
    all_rows: list[dict] = []
    for s in sits:
        setup  = s.get("setup") or {}
        tech   = s.get("tech") or {}
        favor  = s.get("favor") or {}
        ident  = s.get("ident") or {}
        cat    = s.get("category") or "Other"
        prior  = s.get("prior")

        tier_raw = tech.get("tier")
        mc_musd  = s.get("mc_musd")
        mc_bucket = ident.get("mc_bucket") or _mc_bucket(mc_musd)
        sector   = ident.get("sector")
        themes   = list(ident.get("themes") or []) or []
        date_f   = s.get("date_filed") or ""

        # oversold: check both 2w and 1m keys
        washout_2w = bool(tech.get("washout_2w")) if tech.get("washout_2w") is not None else False
        washout_1m = bool(tech.get("washout_1m")) if tech.get("washout_1m") is not None else False
        oversold   = washout_2w or washout_1m

        # washout tip for data-tip attribute
        washout_row = {"washout_2w": washout_2w, "washout_1m": washout_1m,
                       "w1_macd": tech.get("w1_macd"), "w1_stoch": tech.get("w1_stoch")}
        row = {
            "ticker": _txt(s.get("ticker")),
            "company": _txt(s.get("company")),
            "stage": s.get("stage") or "",
            "stage_zh": STAGE_ZH.get(s.get("stage"), s.get("stage") or ""),
            "form": s.get("form_type") or "",
            "date": date_f,
            "age_days": _age_days(date_f, built_dt),
            "cross_border": bool(s.get("cross_border")),
            "mc": _usd_m(mc_musd),
            "mc_bucket": mc_bucket,
            "sector": sector or "",
            "themes": themes,
            "url": s.get("edgar_url") or s.get("source_url"),
            "summary": _txt(s.get("summary"), dash=""),
            "summary_short": _truncate(s.get("summary") or "", 300),
            "live": bool(s.get("live")),
            "low_conf": s.get("confidence") == "low",
            "arb": _arb_str(s.get("arb")),
            "n_amend": int(s.get("n_amendments") or 0),
            "terminal": s.get("terminal"),
            # prior: data-tip receipt (kept as-is), plain sentence in detail panel
            "prior": _prior_str(prior),
            "prior_plain": _prior_plain(prior),
            "prior_plain_zh": _prior_plain_zh(prior),
            # intel fields
            "grade": setup.get("grade"),
            "grade_word": GRADE_WORD.get(setup.get("grade"), ""),
            "grade_word_zh": GRADE_WORD_ZH.get(setup.get("grade"), ""),
            "score": setup.get("score"),
            "tier": tier_raw,
            "tier_word": TIER_WORD.get(tier_raw, ""),
            "tier_word_zh": TIER_WORD_ZH.get(tier_raw, ""),
            "washout_2w": washout_2w,
            "washout_1m": washout_1m,
            "oversold": oversold,
            "oversold_tip": _oversold_tip(washout_row),
            "w1_macd": tech.get("w1_macd"),
            "w1_stoch": tech.get("w1_stoch"),
            "momentum_state": _momentum_state(washout_row),
            "momentum_tip": _momentum_tip(washout_row),
            "sector_stance": favor.get("sector_stance"),
            "rotation": favor.get("rotation"),
            "standout": favor.get("standout"),
            # tech tokens for client-side filter chips
            "tech_tokens": _tech_tokens({"tier": tier_raw, "washout_2w": washout_2w,
                                          "washout_1m": washout_1m,
                                          "w1_macd": tech.get("w1_macd"),
                                          "w1_stoch": tech.get("w1_stoch")}),
            # why lines for setup detail
            "why": setup.get("why") or [],
            "why_zh": setup.get("why_zh") or [],
            # category fields
            "cat": cat,
            "cat_zh": CAT_ZH.get(cat, cat),
            "cat_color": CAT_COLOR.get(cat, C["muted"]),
            # deal details for detail panel
            "source_lane": s.get("source_lane") or "",
            "confidence": s.get("confidence") or "",
            "deal_terms": s.get("deal_terms") or {},
        }
        all_rows.append(row)

    # Sort: score desc, ties by newest date first (ISO string sort: higher date = newer)
    all_rows.sort(key=lambda r: (r.get("score") or 0, r.get("date") or ""), reverse=True)

    # Category chip bar: top 8 by count + rest
    cat_counts: Counter = Counter(r["cat"] for r in all_rows)
    top8_cats = [c for c, _ in cat_counts.most_common(8)]
    rest_cats = [c for c in cat_counts if c not in top8_cats]

    cat_chips = [
        {"cat": c, "cat_zh": CAT_ZH.get(c, c), "n": cat_counts[c], "color": CAT_COLOR.get(c, C["muted"])}
        for c in top8_cats
    ]
    cat_chips_more = [
        {"cat": c, "cat_zh": CAT_ZH.get(c, c), "n": cat_counts[c], "color": CAT_COLOR.get(c, C["muted"])}
        for c in sorted(rest_cats, key=lambda x: -cat_counts[x])
    ]

    # Distinct sector and theme option lists (with counts), filtering empty
    sector_counts: Counter = Counter(r["sector"] for r in all_rows if r["sector"])
    theme_counts: Counter = Counter(th for r in all_rows for th in r["themes"])

    sector_opts = [{"v": s, "n": n} for s, n in sector_counts.most_common()]
    theme_opts  = [{"v": t, "n": n} for t, n in theme_counts.most_common()]

    # groups for backward compat (still used by coverage + top_setups + totals)
    groups_map: dict[str, list] = {}
    for r in all_rows:
        groups_map.setdefault(r["cat"], []).append(r)
    # NOTE: groups list is NOT used for feed rendering anymore (flat rows take over)
    # but kept for coverage stats computation
    groups = [
        {"cat": cat, "cat_zh": CAT_ZH.get(cat, cat), "color": CAT_COLOR.get(cat, C["muted"]),
         "n": len(rows), "rows": rows}
        for cat in (CAT_ORDER + [c for c in groups_map if c not in CAT_ORDER])
        for rows in [groups_map.get(cat)]
        if rows
    ]

    # Top setups for hero strip: any graded name (A/B/C), by score desc, up to 6 —
    # the grade word on each card keeps an 'Early' name honest, and A/B-only left
    # the strip near-empty on calm tapes.
    top_setups = sorted(
        [r for r in all_rows if r.get("grade") in ("A", "B", "C")],
        key=lambda r: r.get("score") or 0, reverse=True
    )[:6]

    grade_a    = sum(1 for r in all_rows if r.get("grade") == "A")
    new_today  = int((intel_ctx.get("counts") or {}).get("new_today", 0))

    vm = {
        "rows": all_rows,          # flat sorted list for the feed
        "groups": groups,          # kept for coverage section
        "cat_chips": cat_chips,
        "cat_chips_more": cat_chips_more,
        "sector_opts": sector_opts,
        "theme_opts": theme_opts,
        "total": len(sits),
        "n_cats": len(groups),
        "counts": snap.get("counts", {}),
        "coverage": snap.get("coverage", {}),
        "built": snap.get("built"),
        "top_setups": top_setups,
        "grade_a": grade_a,
        "new_today": new_today,
        "intel_cov": intel_cov,
        # feed_rows_json intentionally removed — dead payload replaced by server-rendered rows
    }

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    html = env.get_template("special_situations.html.j2").render(**vm, C=C)
    out = config.ROOT / "site" / "special_situations.html"
    write_page(out, html)

    # landing-hub snapshot
    cov = snap.get("coverage", {})
    counts = snap.get("counts", {})
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    snap_out = {
        "total": vm["total"], "n_categories": vm["n_cats"],
        "cross_border": cov.get("cross_border", 0),
        "top_categories": [{"category": c, "n": n} for c, n in top],
        "floor_musd": cov.get("floor_musd"),
        "built": snap.get("built"),
        "grade_a": grade_a,
        "new_today": new_today,
    }
    snap_dir = config.data_dir() / "regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "special_situations_latest.json").write_text(json.dumps(snap_out, indent=2))

    # Mastermind / cross-surface emit: per-ticker context (CONTEXT-only, by_ticker).
    # Consumed by the trading brain (via vendor/macro) and board chips.
    emit = sse.mastermind_emit()
    # Inject intel fields into each ticker's emit slot
    for s in sits:
        t = s.get("ticker") or ""
        if not t or t == "—":
            continue
        setup = s.get("setup") or {}
        tech  = s.get("tech") or {}
        slot  = emit.get("by_ticker", {}).get(t)
        if isinstance(slot, dict):
            slot["setup_grade"]  = setup.get("grade")
            slot["setup_score"]  = setup.get("score")
            slot["tier"]         = tech.get("tier")
            slot["washout_2w"]   = bool(tech.get("washout_2w")) if tech.get("washout_2w") is not None else None
            slot["w1_macd"]      = tech.get("w1_macd")
            slot["w1_stoch"]     = tech.get("w1_stoch")
    emit_dir = config.ROOT / "site" / "allocationdata"
    emit_dir.mkdir(parents=True, exist_ok=True)
    (emit_dir / "special_situations.json").write_text(json.dumps(emit))
    return str(out)


def _truncate(s: str, maxlen: int) -> str:
    """Truncate a string to maxlen characters, adding ellipsis if needed."""
    if not s:
        return ""
    s = s.strip()
    if len(s) <= maxlen:
        return s
    return s[:maxlen].rsplit(" ", 1)[0] + "…"


def _mc_bucket(mc_musd) -> str:
    """Derive mc_bucket from market cap in USD millions when ident doesn't have it."""
    if mc_musd is None:
        return "unknown"
    try:
        mc = float(mc_musd)
    except (TypeError, ValueError):
        return "unknown"
    if mc != mc:
        return "unknown"
    if mc >= 10_000:
        return "large"
    if mc >= 2_000:
        return "mid"
    if mc >= 300:
        return "small"
    if mc >= 50:
        return "micro"
    return "micro"


def main() -> int:
    # production entry (daily.yml): sweep new filings + text-classify + render.
    # For a quick dev re-render from the existing store, call build(refresh=False).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = build(refresh=True)
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
