#!/usr/bin/env python3
"""build_ticker_pages.py — nightly static SEO dossier page generator.

Produces:
  site/stocks/<TICKER>.html  — per-ticker dossier (source-only; baked by nightly job)
  site/stocks/index.html     — A-Z crawl hub
  site/sitemap.xml           — updated with /stocks/ entries

v1 universe = active sp500 members from data/universe/membership.parquet.
Every artifact read is fail-soft per ticker (missing/corrupt -> skip section, ::warning).
Minimum-information gate: render only when ≥3 substantive sections are available
(per research/TRENDSPIDER... §7.4).

Run standalone:
  python -m scripts.build_ticker_pages [--out /tmp/ticker_pages] [--sitemap-out /tmp/sitemap.xml]

Ends with lib.procutil.hard_exit() — Arrow shutdown-hang law (reads membership.parquet).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

SITE = _ROOT / "site"
TEMPLATES_DIR = _ROOT / "templates"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CANONICAL_BASE = "https://mastermind-x.com"
STALENESS_DAYS = 14

# Plain-word sector display names (machine-slug -> display)
_SECTOR_DISPLAY = {
    "Information Technology": "Tech",
    "Health Care": "Health Care",
    "Financials": "Financials",
    "Consumer Discretionary": "Consumer Disc.",
    "Communication Services": "Comm. Services",
    "Industrials": "Industrials",
    "Consumer Staples": "Staples",
    "Energy": "Energy",
    "Materials": "Materials",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
}

# Stance mapping colours for the chip
_STANCE_CLASS = {
    "uptrend": "pos",
    "watch": "neu",
    "protect": "warn",
    "aside": "neg",
    "mixed": "neu",
}

# Hero subtitle: plain bilingual description per stance key (Tier-1 copy — no
# engine free-text here; intelligence read strings carry untranslated jargon)
_STANCE_DESC = {
    "uptrend": ("In an uptrend, holding above its long-term trend line", "处于上升趋势，站稳长期趋势线上方"),
    "protect": ("Trend stop hit — the uptrend is under pressure", "触及趋势止损，上升趋势承压"),
    "aside":   ("Below its long-term trend — no setup here right now", "位于长期趋势下方，暂无合适形态"),
    "mixed":   ("Signals point in different directions right now", "当前信号方向不一"),
    "watch":   ("Worth monitoring — no confirmed trend signal here yet", "值得关注，暂无确认的趋势信号"),
}

# Alpha entry-state slug -> plain bilingual chip copy
_ENTRY_PLAIN = {
    "extended":   ("Extended — has run hot", "短期涨幅偏大"),
    "intact":     ("Trend intact", "趋势完好"),
    "laggard":    ("Lagging its group", "落后于同类"),
    "neutral":    ("Neutral setup", "形态中性"),
    "pullback":   ("In a pullback", "回调之中"),
    "overbought": ("Overbought — has run hot", "短期超买"),
    "oversold":   ("Oversold — washed out", "短期超卖"),
}

# GEX regime slug -> plain meta-description phrase (artifact emits long/short)
_REGIME_META_EN = {
    "long":     "market makers net long gamma",
    "positive": "market makers net long gamma",
    "short":    "market makers net short gamma",
    "negative": "market makers net short gamma",
    "neutral":  "balanced options positioning",
}

# Plain-word translations for intelligence read labels
_READ_LABEL_PLAIN = {
    "quiet": "No strong signal",
    "bullish": "Positive signals",
    "bearish": "Bearish signals",
    "mixed": "Mixed signals",
    "rising": "Momentum building",
    "fading": "Momentum fading",
    "watch": "Worth monitoring",
}
_READ_LABEL_ZH = {
    "quiet": "暂无明显信号",
    "bullish": "正面信号",
    "bearish": "负面信号",
    "mixed": "信号混杂",
    "rising": "动能积聚",
    "fading": "动能减弱",
    "watch": "值得关注",
}

# Factor z-score to plain-word translation
# z > +1 = strong/high/low depending on factor direction
def _factor_plain(factor: str, z: float | None) -> tuple[str, str]:
    """Return (en, zh) plain-word description for a factor z-score."""
    if z is None:
        return "", ""
    high = z >= 0.8
    low = z <= -0.8
    _map: dict[str, tuple[tuple[str, str], tuple[str, str], tuple[str, str]]] = {
        "value":         (("Cheap vs peers", "相对低估"), ("Average value", "估值居中"), ("Pricey vs peers", "相对高估")),
        "quality":       (("High quality", "高质量"), ("Average quality", "质量居中"), ("Lower quality", "质量偏低")),
        "profitability": (("High profitability", "高盈利"), ("Average profitability", "盈利居中"), ("Low profitability", "盈利偏低")),
        "accruals":      (("Low accruals — solid earnings", "应计较低·盈利扎实"), ("Average accruals", "应计居中"), ("High accruals — earnings quality risk", "应计较高·盈利质量存疑")),
        "investment":    (("Disciplined investment", "资本开支克制"), ("Average investment", "投资居中"), ("Heavy investment", "资本开支积极")),
        "payout":        (("Strong shareholder returns", "股东回报丰厚"), ("Moderate payout", "回报居中"), ("Low payout", "回报偏低")),
        "low_vol":       (("Low volatility", "波动性低"), ("Average volatility", "波动居中"), ("High volatility", "波动性高")),
        "low_beta":      (("Low market sensitivity", "市场敏感度低"), ("Average sensitivity", "敏感度居中"), ("High market sensitivity", "市场敏感度高")),
        "short_interest":(("Low short interest", "空头兴趣低"), ("Average short interest", "空头居中"), ("Heavy short interest", "空头压力大")),
        "sue":           (("Earnings beat streak", "盈利超预期"), ("In-line earnings", "盈利符合预期"), ("Earnings miss streak", "盈利不及预期")),
        "composite":     (("Strong composite standing", "综合排名靠前"), ("Average composite standing", "综合排名居中"), ("Weak composite standing", "综合排名偏后")),
    }
    if factor == "composite_rank":
        factor = "composite"
    labels = _map.get(factor)
    if not labels:
        return "", ""
    # accruals: high accruals is bad (so: high z = bad = neg direction)
    # investment, low_vol, low_beta, short_interest: high z = low = good
    if factor in ("accruals", "short_interest"):
        if high:
            return labels[2]
        elif low:
            return labels[0]
        return labels[1]
    if high:
        return labels[0]
    elif low:
        return labels[2]
    return labels[1]


# ---------------------------------------------------------------------------
# Pure functions (testable)
# ---------------------------------------------------------------------------

def compute_stance(signals: dict | None, intel: dict | None) -> tuple[str, str, str, str, str]:
    """Map engine states to plain-word stance.
    Returns (stance_en, stance_zh, stance_key, invalidation_en, invalidation_zh).
    Never raises.
    """
    try:
        if signals:
            state = (signals.get("state") or "").lower()
            above200 = bool(signals.get("above200"))
            trail_breach = bool(signals.get("trail_breach"))
            trail_stop = signals.get("trail_stop")

            if trail_breach:
                inv = f"would change on a close back above the trail stop at ${trail_stop:.2f}" if trail_stop else ""
                inv_zh = f"如收盘重新站上止损价 ${trail_stop:.2f}，信号将改变" if trail_stop else ""
                return ("Protect gains", "保护盈利", "protect", inv, inv_zh)
            if state in ("long-bias", "long_bias", "uptrend") and above200:
                inv = f"would change on a close below trail stop at ${trail_stop:.2f}" if trail_stop else ""
                inv_zh = f"如收盘跌破止损价 ${trail_stop:.2f}，信号将改变" if trail_stop else ""
                return ("Uptrend — watch, don't chase", "上升趋势，不追高", "uptrend", inv, inv_zh)
            if state in ("long-bias", "long_bias", "uptrend") and not above200:
                return ("Watch — above recent support", "关注中，关注支撑位", "watch", "", "")
            if state in ("bearish", "bear", "downtrend") or not above200:
                return ("Stand aside", "观望为主", "aside", "", "")
            if state in ("mixed", "neutral"):
                return ("Mixed — watch", "信号混杂，观望", "mixed", "", "")

        # Derive from intelligence read label
        if intel:
            read_rec = intel.get("read") or {}
            label = (read_rec.get("label") or "").lower()
            if label in ("bullish", "rising"):
                return ("Watch — positive signals", "观察中，正面信号", "watch", "", "")
            if label in ("bearish", "fading"):
                return ("Stand aside", "观望为主", "aside", "", "")

        return ("Watch", "关注中", "watch", "", "")
    except Exception:  # noqa: BLE001
        return ("Watch", "关注中", "watch", "", "")


def sections_available(
    factors_row: dict | None,
    alpha_row: dict | None,
    gex: dict | None,
    member_ctx: list | None,
    intel: dict | None,
    flow: dict | None,
    signals: dict | None,
    news_tickers: dict | None,
    ticker: str,
) -> int:
    """Count available substantive sections for the min-information gate.
    Gate: ≥3 sections required.
    """
    count = 0
    if factors_row:
        count += 1
    if alpha_row:
        count += 1
    if gex and gex.get("summary"):
        count += 1
    if member_ctx:
        count += 1
    if intel and (intel.get("read") or intel.get("brain")):
        count += 1
    if flow and flow.get("verdict"):
        count += 1
    if signals and signals.get("state"):
        count += 1
    if news_tickers and ticker in news_tickers and (news_tickers[ticker].get("top") or []):
        count += 1
    return count


def page_freshness(dates: list[str | None]) -> str | None:
    """Return the newest valid ISO date string from a list, or None."""
    best: date | None = None
    for d in dates:
        if not d:
            continue
        try:
            parsed = date.fromisoformat(str(d)[:10])
            if best is None or parsed > best:
                best = parsed
        except (ValueError, TypeError):
            continue
    return best.isoformat() if best else None


def is_stale(freshness_date: str | None) -> bool:
    """True if the page freshness is older than STALENESS_DAYS."""
    if not freshness_date:
        return True
    try:
        d = date.fromisoformat(freshness_date)
        return (date.today() - d).days > STALENESS_DAYS
    except (ValueError, TypeError):
        return True


def build_sitemap(
    existing_xml: str,
    stocks_entries: list[dict],  # [{"loc": ..., "lastmod": ..., "changefreq": ..., "priority": ...}]
) -> str:
    """Merge stocks entries into existing sitemap, preserving all non-/stocks/ entries."""
    # Parse existing non-stocks entries byte-faithfully
    non_stocks_lines: list[str] = []
    for line in existing_xml.splitlines():
        stripped = line.strip()
        if stripped.startswith("<url>") and "/stocks/" in stripped:
            continue
        non_stocks_lines.append(line)

    # Rebuild: find where to insert — before </urlset>
    base = "\n".join(non_stocks_lines)
    # Remove closing tag if present
    base = base.rstrip()
    if base.endswith("</urlset>"):
        base = base[: -len("</urlset>")].rstrip()

    parts = [base]
    for e in stocks_entries:
        loc = e["loc"]
        lm = e.get("lastmod", "")
        cf = e.get("changefreq", "daily")
        pri = e.get("priority", 0.6)
        entry = f'  <url><loc>{loc}</loc>'
        if lm:
            entry += f'<lastmod>{lm}</lastmod>'
        entry += f'<changefreq>{cf}</changefreq><priority>{pri}</priority></url>'
        parts.append(entry)
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


def _safe_float(v: Any, decimals: int = 2) -> str:
    """Format a float for display; returns '' on failure."""
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return ""


def _clean_str(v: Any) -> str:
    """Return str or empty string; guard against None/nan."""
    if v is None:
        return ""
    s = str(v)
    if s.lower() in ("none", "nan", "nat", "null"):
        return ""
    return s


def _sector_display(raw: str | None) -> str:
    """Translate raw sector string to display name."""
    if not raw:
        return ""
    return _SECTOR_DISPLAY.get(raw, raw)


# ---------------------------------------------------------------------------
# Data loaders (all fail-soft)
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    """Load JSON from path; return None on any error."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("::warning::could not load %s: %s", path, e)
    return None


def load_all_aggregates(site: Path) -> dict:
    """Load all shared aggregates once. Returns dict with all loaded data."""
    agg: dict = {}

    # factors.json -> {ticker -> row}
    factors_raw = _load_json(site / "factordata" / "factors.json")
    if factors_raw:
        agg["factors_as_of"] = _clean_str(factors_raw.get("as_of"))
        agg["factors_map"] = {r["ticker"]: r for r in (factors_raw.get("table") or []) if r.get("ticker")}
    else:
        agg["factors_as_of"] = ""
        agg["factors_map"] = {}

    # alpha.json -> per_ticker
    alpha_raw = _load_json(site / "factordata" / "alpha.json")
    if alpha_raw:
        agg["alpha_as_of"] = _clean_str(alpha_raw.get("as_of"))
        agg["alpha_map"] = alpha_raw.get("per_ticker") or {}
    else:
        agg["alpha_as_of"] = ""
        agg["alpha_map"] = {}

    # member_context.json -> by_ticker
    mc_raw = _load_json(site / "basketdata" / "member_context.json")
    if mc_raw:
        agg["member_ctx_as_of"] = _clean_str(mc_raw.get("as_of"))
        agg["member_ctx_map"] = mc_raw.get("by_ticker") or {}
    else:
        agg["member_ctx_as_of"] = ""
        agg["member_ctx_map"] = {}

    # baskets.json -> {id -> {name, name_zh}}
    baskets_raw = _load_json(site / "basketdata" / "baskets.json")
    if baskets_raw:
        basket_list = baskets_raw.get("baskets") or []
        agg["baskets_map"] = {b["id"]: b for b in basket_list if b.get("id")}
    else:
        agg["baskets_map"] = {}

    # intelligence/by_ticker.json -> tickers
    intel_raw = _load_json(site / "intelligence" / "by_ticker.json")
    if intel_raw:
        agg["intel_as_of"] = _clean_str(intel_raw.get("as_of"))
        agg["intel_map"] = intel_raw.get("tickers") or {}
    else:
        agg["intel_as_of"] = ""
        agg["intel_map"] = {}

    # news/by_ticker.json -> tickers
    news_raw = _load_json(site / "news" / "by_ticker.json")
    if news_raw:
        agg["news_as_of"] = _clean_str(news_raw.get("asof", news_raw.get("as_of", "")))
        agg["news_map"] = news_raw.get("tickers") or {}
    else:
        agg["news_as_of"] = ""
        agg["news_map"] = {}

    # altdata/by_ticker.json -> tickers
    alt_raw = _load_json(site / "altdata" / "by_ticker.json")
    if alt_raw:
        agg["alt_as_of"] = _clean_str(alt_raw.get("as_of", alt_raw.get("asof", "")))
        agg["alt_map"] = alt_raw.get("tickers") or {}
    else:
        agg["alt_as_of"] = ""
        agg["alt_map"] = {}

    return agg


def load_per_ticker(site: Path, ticker: str) -> dict:
    """Load per-ticker artifacts (gex, signals, flow, stockbrief). Fail-soft."""
    result: dict = {}

    # gex
    gex = _load_json(site / "gex" / f"{ticker}.json")
    result["gex"] = gex
    result["gex_as_of"] = _clean_str((gex or {}).get("meta", {}).get("asof")) if gex else ""

    # signals
    sig = _load_json(site / "signals" / f"{ticker}.json")
    result["signals"] = sig
    result["signals_as_of"] = _clean_str((sig or {}).get("asof")) if sig else ""

    # flow
    flow = _load_json(site / "flow" / f"{ticker}.json")
    result["flow"] = flow
    result["flow_as_of"] = _clean_str((flow or {}).get("asof")) if flow else ""

    # stockbrief — only include when summary is non-null, degraded_reason is
    # absent/null, and the brief itself is fresh (a month-old LLM narrative under
    # a fresh page misleads; the deterministic sections carry the current read)
    brief = _load_json(site / "stockbrief" / f"{ticker}.json")
    if brief and brief.get("summary") and not brief.get("degraded_reason"):
        brief_date = _clean_str(brief.get("asof") or "") or _clean_str(brief.get("generated_at") or "")[:10]
        if is_stale(brief_date):
            result["brief"] = None
            result["brief_as_of"] = ""
        else:
            result["brief"] = brief
            result["brief_as_of"] = brief_date
    else:
        result["brief"] = None
        result["brief_as_of"] = ""

    return result


def build_page_context(
    ticker: str,
    name: str,
    sector: str,
    group: str,
    agg: dict,
    per: dict,
) -> dict:
    """Build the full Jinja2 template context for one ticker page. Pure — no I/O."""
    factors_row = agg["factors_map"].get(ticker)
    alpha_row = agg["alpha_map"].get(ticker)
    gex = per.get("gex")
    gex_summary = (gex or {}).get("summary") or {}
    signals = per.get("signals")
    flow = per.get("flow")
    brief = per.get("brief")
    intel = agg["intel_map"].get(ticker)
    news_rec = agg["news_map"].get(ticker)
    alt_rec = agg["alt_map"].get(ticker)
    member_ctx_list = agg["member_ctx_map"].get(ticker) or []

    # Stance
    stance_en, stance_zh, stance_key, invalidation_en, invalidation_zh = compute_stance(signals, intel)

    # Page freshness
    freshness = page_freshness([
        agg.get("factors_as_of"),
        agg.get("alpha_as_of"),
        per.get("gex_as_of"),
        per.get("signals_as_of"),
        per.get("flow_as_of"),
        agg.get("intel_as_of"),
        agg.get("news_as_of"),
        per.get("brief_as_of"),
    ])
    stale = is_stale(freshness)

    # Hero subtitle: plain bilingual description keyed on the stance
    hero_desc_en, hero_desc_zh = _STANCE_DESC.get(stance_key, _STANCE_DESC["watch"])

    # Meta description: deterministic EN sentence from real data
    state_phrase = stance_en
    facts_parts = []
    regime_slug = _clean_str(gex_summary.get("regime")).lower()
    if regime_slug in _REGIME_META_EN:
        facts_parts.append(_REGIME_META_EN[regime_slug])
    if factors_row and factors_row.get("composite_rank") is not None:
        cr = factors_row.get("composite_rank")
        # composite_rank is a z-score (~-3..+3), not a percentile
        if isinstance(cr, (int, float)) and cr >= 1.0:
            facts_parts.append("strong composite factor score")
    meta_desc = f"{ticker} ({name}) — {state_phrase}."
    if facts_parts:
        meta_desc += " " + "; ".join(facts_parts[:2]).capitalize() + "."
    meta_desc += " Signals, options positioning, factor profile updated nightly."

    # JSON-LD (pre-serialized, safe for |safe injection)
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{ticker} — {name}: signals, options & factor profile",
        "datePublished": freshness or date.today().isoformat(),
        "dateModified": freshness or date.today().isoformat(),
        "author": {"@type": "Organization", "name": "Mastermind"},
        "publisher": {"@type": "Organization", "name": "Mastermind"},
        "about": {"@type": "Corporation", "name": name, "tickerSymbol": ticker},
        "url": f"{CANONICAL_BASE}/stocks/{ticker}.html",
    }
    jsonld_str = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")

    # ---- Factors section ----
    factors_section: dict | None = None
    if factors_row:
        rows = []
        factor_keys = ["value", "quality", "profitability", "low_vol", "low_beta",
                        "short_interest", "sue", "composite_rank"]
        for fk in factor_keys:
            z = factors_row.get(fk)
            if z is None:
                continue
            en_label, zh_label = _factor_plain(fk, z)
            if not en_label:
                continue
            rows.append({
                "key": fk,
                "en": en_label,
                "zh": zh_label,
                "z": z,
                "positive": z >= 0.5 if fk not in ("accruals", "short_interest") else z <= -0.5,
            })
        mktcap_bn = factors_row.get("mktcap_bn")
        mktcap_str = ""
        if mktcap_bn is not None:
            try:
                mktcap_str = f"${float(mktcap_bn):.0f}B" if float(mktcap_bn) >= 1 else f"${float(mktcap_bn)*1000:.0f}M"
            except (ValueError, TypeError):
                pass
        factors_section = {
            "rows": rows,
            "mktcap": mktcap_str,
            "sector": _sector_display(factors_row.get("sector") or sector),
            "composite_rank": factors_row.get("composite_rank"),
            "as_of": agg.get("factors_as_of", ""),
        }

    # ---- Alpha / RS section ----
    alpha_section: dict | None = None
    if alpha_row:
        rs = alpha_row.get("rs")
        rs3m = alpha_row.get("rs3m")
        rs6m = alpha_row.get("rs6m")
        rs12m = alpha_row.get("rs12m")

        def _pctile_word(v: Any) -> str:
            if v is None:
                return ""
            try:
                p = float(v)
                if p >= 0.8:
                    return "top 20%"
                if p >= 0.6:
                    return "above average"
                if p <= 0.2:
                    return "bottom 20%"
                if p <= 0.4:
                    return "below average"
                return "middle of the pack"
            except (TypeError, ValueError):
                return ""

        def _pctile_word_zh(v: Any) -> str:
            if v is None:
                return ""
            try:
                p = float(v)
                if p >= 0.8:
                    return "前20%"
                if p >= 0.6:
                    return "高于平均"
                if p <= 0.2:
                    return "后20%"
                if p <= 0.4:
                    return "低于平均"
                return "中等水平"
            except (TypeError, ValueError):
                return ""

        alpha_val = alpha_row.get("alpha")
        alpha_str = ""
        if alpha_val is not None:
            try:
                av = float(alpha_val)
                alpha_str = f"+{av:.1%}" if av >= 0 else f"{av:.1%}"
            except (TypeError, ValueError):
                pass

        entry = _clean_str(alpha_row.get("entry"))
        entry_en, entry_zh = _ENTRY_PLAIN.get(entry.lower(), ("", ""))
        alpha_section = {
            "rs_pctile_en": _pctile_word(rs),
            "rs_pctile_zh": _pctile_word_zh(rs),
            "rs3m_en": _pctile_word(rs3m),
            "rs3m_zh": _pctile_word_zh(rs3m),
            "rs6m_en": _pctile_word(rs6m),
            "rs6m_zh": _pctile_word_zh(rs6m),
            "rs12m_en": _pctile_word(rs12m),
            "rs12m_zh": _pctile_word_zh(rs12m),
            "alpha_str": alpha_str,
            "entry": entry,
            "entry_en": entry_en,
            "entry_zh": entry_zh,
            "sector_rank": alpha_row.get("sector_rank"),
            "sector_n": alpha_row.get("sector_n"),
            "as_of": agg.get("alpha_as_of", ""),
        }

    # ---- GEX / options positioning section ----
    gex_section: dict | None = None
    if gex and gex_summary:
        regime = _clean_str(gex_summary.get("regime"))
        # Plain-word regime translation (artifact emits long/short; unmapped -> hide)
        _regime_plain = {
            "long":     "Market makers are net long gamma — price pinned near current level",
            "positive": "Market makers are net long gamma — price pinned near current level",
            "short":    "Market makers are net short gamma — price moves may amplify",
            "negative": "Market makers are net short gamma — price moves may amplify",
            "neutral":  "Balanced gamma positioning",
        }
        _regime_plain_zh = {
            "long":     "做市商净持有正伽玛，价格倾向于在当前水平附近震荡",
            "positive": "做市商净持有正伽玛，价格倾向于在当前水平附近震荡",
            "short":    "做市商净持有负伽玛，价格波动可能被放大",
            "negative": "做市商净持有负伽玛，价格波动可能被放大",
            "neutral":  "伽玛头寸平衡",
        }
        regime_en = _regime_plain.get(regime.lower() if regime else "", "")
        regime_zh = _regime_plain_zh.get(regime.lower() if regime else "", "")
        em = (gex.get("expected_move") or {})
        em_daily = _safe_float(em.get("daily_pct"), 2)
        em_weekly = _safe_float(em.get("weekly_pct"), 2)
        call_wall = _safe_float(gex_summary.get("call_wall"), 0)
        put_wall = _safe_float(gex_summary.get("put_wall"), 0)
        flip = _safe_float(gex_summary.get("gamma_flip"), 0)
        iv30 = _safe_float(gex_summary.get("iv30"), 0)
        iv_rank = (gex_summary.get("iv_rank") or {})
        iv_rank_pct = _safe_float(iv_rank.get("rank_pct"), 0) if isinstance(iv_rank, dict) else ""
        skew = gex_summary.get("skew") or {}
        skew_tone = _clean_str(skew.get("tone") if isinstance(skew, dict) else "")
        gex_section = {
            "regime_en": regime_en,
            "regime_zh": regime_zh,
            "em_daily_pct": em_daily,
            "em_weekly_pct": em_weekly,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "gamma_flip": flip,
            "iv30": iv30,
            "iv_rank_pct": iv_rank_pct,
            "skew_tone": skew_tone,
            "as_of": per.get("gex_as_of", ""),
        }

    # ---- Flow section ----
    flow_section: dict | None = None
    if flow and flow.get("verdict"):
        verdict = flow.get("verdict") or {}
        flow_section = {
            "tone": _clean_str(verdict.get("tone")),
            "en": _clean_str(verdict.get("en")),
            "zh": _clean_str(verdict.get("zh")),
            "net_premium_mn": _safe_float(flow.get("net_premium_mn"), 1),
            "pc_ratio": _safe_float(flow.get("pc_ratio"), 2),
            "as_of": per.get("flow_as_of", ""),
        }

    # ---- Signal history section ----
    signals_section: dict | None = None
    if signals and signals.get("state"):
        markers = signals.get("markers") or []
        # Show the 12 most recent markers
        recent_markers = markers[-12:]
        signals_section = {
            "state": _clean_str(signals.get("state")),
            "above200": bool(signals.get("above200")),
            "weekly_bull": bool(signals.get("weekly_bull")),
            "trail_stop": _safe_float(signals.get("trail_stop"), 2),
            "trail_breach": bool(signals.get("trail_breach")),
            "markers": recent_markers,
            "n_total_markers": len(markers),
            "as_of": per.get("signals_as_of", ""),
        }

    # ---- Themes & baskets section ----
    baskets_section: list | None = None
    if member_ctx_list:
        rows = []
        for mc in member_ctx_list:
            bid = _clean_str(mc.get("basket_id"))
            basket_info = agg["baskets_map"].get(bid) or {}
            bname = _clean_str(mc.get("basket") or basket_info.get("name") or bid)
            bname_zh = _clean_str(basket_info.get("name_zh") or bname)
            rows.append({
                "id": bid,
                "name": bname,
                "name_zh": bname_zh,
                "band_en": _clean_str(mc.get("band_en")),
                "band_zh": _clean_str(mc.get("band_zh")),
                "tone": _clean_str(mc.get("tone")),
                "rs_rank": mc.get("rs_rank"),
                "href": f"../basket/{bid}.html",
            })
        if rows:
            baskets_section = rows

    # ---- News section ----
    news_section: list | None = None
    if news_rec:
        headlines = news_rec.get("top") or []
        if headlines:
            news_section = [
                {
                    "title": _clean_str(h.get("title")),
                    "url": _clean_str(h.get("url")),
                    "source": _clean_str(h.get("source")),
                    "published": _clean_str(h.get("published", ""))[:10],
                    "sentiment": _clean_str(h.get("sentiment")),
                }
                for h in headlines[:6]
                if h.get("title") and h.get("url")
            ]

    # ---- Alternative data section ----
    alt_section: dict | None = None
    if alt_rec and alt_rec.get("channels"):
        channels = alt_rec.get("channels") or []
        congress_net = alt_rec.get("congress_net")
        congress_members = alt_rec.get("congress_members")
        trump_linked = bool(alt_rec.get("trump_linked"))
        affiliated = bool(alt_rec.get("affiliated"))

        # Plain-word channel descriptions
        _channel_en = {
            "congress_buy":     "Congressional buy activity",
            "congress_sell":    "Congressional sell activity",
            "patent_cluster":   "Recent patent filings",
            "wsb_mentions":     "Retail trader chatter",
            "trump":            "Policy linkage",
            "affiliation":      "Notable ownership/affiliation",
            "special_situation":"Special situation flag",
        }
        _channel_zh = {
            "congress_buy":     "国会议员买入记录",
            "congress_sell":    "国会议员卖出记录",
            "patent_cluster":   "近期专利申请",
            "wsb_mentions":     "散户关注度较高",
            "trump":            "政策关联",
            "affiliation":      "知名持仓/关联",
            "special_situation":"特殊情况标记",
        }

        ch_rows = [
            {"en": _channel_en.get(c, c), "zh": _channel_zh.get(c, c)}
            for c in channels if _channel_en.get(c)
        ]

        if ch_rows:
            alt_section = {
                "channels": ch_rows,
                "congress_net": congress_net,
                "congress_members": congress_members,
                "trump_linked": trump_linked,
                "affiliated": affiliated,
            }

    # ---- AI brief section ----
    brief_section: dict | None = None
    if brief:
        brief_section = {
            "summary": _clean_str(brief.get("summary")),
            "drivers": brief.get("drivers") or [],
            "risks": brief.get("risks") or [],
            "catalysts": brief.get("catalysts") or [],
            "zh_summary": _clean_str((brief.get("zh") or {}).get("summary") if brief.get("zh") else ""),
            "confidence": brief.get("confidence"),
            "disclaimer": _clean_str(brief.get("disclaimer") or "AI-generated research context — not advice."),
            "as_of": per.get("brief_as_of", ""),
        }

    return {
        # Meta
        "ticker": ticker,
        "name": name,
        "sector": _sector_display(sector),
        "group": group,
        "canonical_url": f"{CANONICAL_BASE}/stocks/{ticker}.html",
        "meta_desc": meta_desc,
        "jsonld_str": jsonld_str,
        "freshness": freshness or date.today().isoformat(),
        "stale": stale,
        # Hero
        "stance_en": stance_en,
        "stance_zh": stance_zh,
        "stance_key": stance_key,
        "stance_class": _STANCE_CLASS.get(stance_key, "neu"),
        "invalidation_en": invalidation_en,
        "invalidation_zh": invalidation_zh,
        "hero_desc_en": hero_desc_en,
        "hero_desc_zh": hero_desc_zh,
        # Sections (None = section not available, omit entirely)
        "factors": factors_section,
        "alpha": alpha_section,
        "gex": gex_section,
        "flow": flow_section,
        "signals": signals_section,
        "baskets": baskets_section,
        "news": news_section,
        "alt": alt_section,
        "brief": brief_section,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    out: Path,
    sitemap_out: Path | None,
    site: Path | None = None,
) -> int:
    """Main entrypoint. Returns exit code 0 always (non-fatal)."""
    if site is None:
        site = SITE

    out.mkdir(parents=True, exist_ok=True)

    # --- Load templates ---
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=True,
        )
        tmpl_page = env.get_template("ticker.html.j2")
        tmpl_index = env.get_template("ticker_index.html.j2")
    except Exception as e:
        log.error("::error::failed to load templates: %s", e)
        return 1

    # --- Load membership ---
    try:
        import pandas as pd
        df = pd.read_parquet(str(_ROOT / "data" / "universe" / "membership.parquet"))
        # Filter active sp500 members
        sp500 = df[(df["group"] == "sp500") & (df["active"] == True)].copy()  # noqa: E712
        sp500 = sp500.dropna(subset=["ticker"])
        log.info("Loaded %d active sp500 members", len(sp500))
    except Exception as e:
        log.error("::error::failed to load membership.parquet: %s", e)
        return 1

    # --- Load shared aggregates ---
    agg = load_all_aggregates(site)

    # --- Render per-ticker pages ---
    n_rendered = 0
    n_skipped = 0
    n_noindexed = 0
    sitemap_entries: list[dict] = []
    index_rows: list[dict] = []

    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for _, row in sp500.iterrows():
        ticker = _clean_str(row.get("ticker"))
        if not ticker:
            continue
        name = _clean_str(row.get("name") or ticker)
        sector = _clean_str(row.get("sector") or "")
        group = _clean_str(row.get("group") or "sp500")

        try:
            per = load_per_ticker(site, ticker)

            # Check min-information gate
            n_sections = sections_available(
                factors_row=agg["factors_map"].get(ticker),
                alpha_row=agg["alpha_map"].get(ticker),
                gex=per.get("gex"),
                member_ctx=agg["member_ctx_map"].get(ticker),
                intel=agg["intel_map"].get(ticker),
                flow=per.get("flow"),
                signals=per.get("signals"),
                news_tickers=agg["news_map"],
                ticker=ticker,
            )

            if n_sections < 3:
                log.debug("skip %s: only %d sections (gate=3)", ticker, n_sections)
                n_skipped += 1
                continue

            ctx = build_page_context(ticker, name, sector, group, agg, per)
            ctx["generated_utc"] = generated_utc

            # Derive one-word state for index chip
            stance_key = ctx["stance_key"]
            state_chip = {
                "uptrend": "Uptrend",
                "protect": "Protect",
                "aside": "Aside",
                "mixed": "Mixed",
                "watch": "Watch",
            }.get(stance_key, "Watch")
            state_chip_zh = {
                "uptrend": "上涨",
                "protect": "保护",
                "aside": "观望",
                "mixed": "混杂",
                "watch": "关注",
            }.get(stance_key, "关注")

            html = tmpl_page.render(**ctx)
            write_page(out / f"{ticker}.html", html)
            n_rendered += 1

            # Sitemap entry
            freshness = ctx["freshness"]
            stale = ctx["stale"]
            if stale:
                n_noindexed += 1
            else:
                sitemap_entries.append({
                    "loc": f"{CANONICAL_BASE}/stocks/{ticker}.html",
                    "lastmod": freshness,
                    "changefreq": "daily",
                    "priority": 0.6,
                })

            index_rows.append({
                "ticker": ticker,
                "name": name,
                "sector": _sector_display(sector),
                "state_chip": state_chip,
                "state_chip_zh": state_chip_zh,
                "stance_class": ctx["stance_class"],
            })

        except Exception as e:  # noqa: BLE001 — per-ticker fail-soft
            log.warning("::warning title=%s::page render failed: %s", ticker, e)
            n_skipped += 1
            continue

    # --- Render index page ---
    try:
        index_rows_sorted = sorted(index_rows, key=lambda r: r["ticker"])
        index_html = tmpl_index.render(
            rows=index_rows_sorted,
            n_total=len(index_rows_sorted),
            generated_utc=generated_utc,
            canonical_url=f"{CANONICAL_BASE}/stocks/index.html",
        )
        write_page(out / "index.html", index_html)
        # Add index to sitemap
        sitemap_entries.insert(0, {
            "loc": f"{CANONICAL_BASE}/stocks/index.html",
            "lastmod": date.today().isoformat(),
            "changefreq": "daily",
            "priority": 0.7,
        })
    except Exception as e:  # noqa: BLE001
        log.warning("::warning title=index::index page render failed: %s", e)

    # --- Sitemap update ---
    # Only touch the real sitemap when out IS site/stocks (production run) OR when
    # sitemap_out is explicitly given (test / --sitemap-out)
    real_sitemap = site / "sitemap.xml"
    is_production = (out.resolve() == (site / "stocks").resolve())

    if sitemap_out or is_production:
        target_sitemap = sitemap_out if sitemap_out else real_sitemap
        try:
            existing = real_sitemap.read_text() if real_sitemap.exists() else '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>'
            new_sitemap = build_sitemap(existing, sitemap_entries)
            target_sitemap.parent.mkdir(parents=True, exist_ok=True)
            target_sitemap.write_text(new_sitemap)
            log.info("Updated sitemap: %s (%d /stocks/ entries)", target_sitemap, len(sitemap_entries))
        except Exception as e:  # noqa: BLE001
            log.warning("::warning title=sitemap::sitemap update failed: %s", e)

    log.info(
        "::notice title=ticker_pages::rendered=%d skipped=%d noindexed=%d",
        n_rendered, n_skipped, n_noindexed,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build static per-ticker stock dossier pages.")
    parser.add_argument("--out", default=None, help="Output directory (default: site/stocks)")
    parser.add_argument("--sitemap-out", default=None, help="Sitemap output path (default: site/sitemap.xml)")
    args = parser.parse_args(argv)

    out = Path(args.out) if args.out else (SITE / "stocks")
    sitemap_out = Path(args.sitemap_out) if args.sitemap_out else None

    rc = run(out=out, sitemap_out=sitemap_out)
    return rc


if __name__ == "__main__":
    from lib.procutil import hard_exit
    rc = main()
    hard_exit(rc)
