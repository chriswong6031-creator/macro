#!/usr/bin/env python3
"""build_ticker_pages.py — nightly static SEO dossier page generator (v2).

v2 runs INSIDE the engine job right after scripts.build_site (which writes
site/stockdata/<T>.json ~1,595 tickers + site/ohlc/<T>.json), so it reads
the FULL stockdata blobs.

Produces:
  site/stocks/<TICKER>.html  — per-ticker dossier (context-only mode also
                                writes ctx JSONs for template builder)
  site/stocks/index.html     — A-Z crawl hub
  site/sitemap.xml           — updated with /stocks/ entries

Run standalone:
  python -m scripts.build_ticker_pages [--out /tmp/ticker_pages]
  python -m scripts.build_ticker_pages --context-only --dump-context /tmp/ctx

Ends with lib.procutil.hard_exit() — Arrow shutdown-hang law (reads
membership.parquet).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
from calendar import month_abbr
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from lib.seo import SITE_BASE as _SITE_BASE  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

SITE = _ROOT / "site"
TEMPLATES_DIR = _ROOT / "templates"

# ---------------------------------------------------------------------------
# Share-card (og:image) — fail-soft import; None disables the feature silently
# ---------------------------------------------------------------------------
try:
    from engine.marketing import share_cards as _SHARE_CARDS  # noqa: E402
    from engine.marketing import logo_cache as _LOGO_CACHE    # noqa: E402
except Exception as _sc_import_err:  # noqa: BLE001
    _SHARE_CARDS = None  # type: ignore[assignment]
    _LOGO_CACHE = None   # type: ignore[assignment]
    log.warning("::warning title=share_cards_import::share_cards/logo_cache not available: %s", _sc_import_err)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# CANONICAL_BASE: strip trailing slash for use in URL path concatenation.
CANONICAL_BASE = _SITE_BASE.rstrip("/")
STALENESS_DAYS = 14
SEASONALITY_MIN_BARS = 750  # require at least this many ohlc bars

OG_DIR = SITE / "og" / "stocks"
LOGO_DIR = _ROOT / "data" / "marketing" / "logos"
MAX_LOGO_FETCH_PER_RUN = 300
_LOGO_ATTEMPTS_PATH = _ROOT / "data" / "marketing" / "share_cards" / "logo_attempts.json"
_LOGO_NEGATIVE_CACHE_DAYS = 30

# Plain-word sector display names
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

# Stance → chip CSS class
_STANCE_CLASS = {
    "uptrend": "pos",
    "watch": "neu",
    "protect": "warn",
    "aside": "neg",
    "mixed": "neu",
    "bottoming": "neu",
    "recovering": "pos",
    "extended": "warn",
    "topping": "warn",
    "downtrend": "neg",
}

# Ladder state → stance key
_LADDER_TO_STANCE: dict[str, str] = {
    "UPTREND": "uptrend",
    "RALLY ON": "uptrend",
    "BOTTOMING": "bottoming",
    "BOTTOM WATCH": "bottoming",
    "NEARING A LOW": "bottoming",
    "NEARING A HIGH": "extended",
    "UNCONFIRMED TURN": "watch",
    "DOWNTREND": "downtrend",
}

# Stance key → hero subtitle
_STANCE_DESC = {
    "uptrend":    ("In an uptrend — holding above its long-term trend line", "处于上升趋势，站稳长期趋势线上方"),
    "recovering": ("Recovering — early signs of a trend turn", "复苏中，趋势转变初现信号"),
    "bottoming":  ("Setting up near a low — not yet confirmed", "接近低点，尚未确认"),
    "extended":   ("Extended — has run far above the trend line", "短期涨幅偏大，远高于趋势线"),
    "topping":    ("Topping pattern — watch for a trend reversal", "顶部形态，留意趋势反转"),
    "protect":    ("Trend stop hit — the uptrend is under pressure", "触及趋势止损，上升趋势承压"),
    "downtrend":  ("Below its long-term trend — no setup here right now", "位于长期趋势下方，暂无合适形态"),
    "mixed":      ("Signals point in different directions right now", "当前信号方向不一"),
    "watch":      ("Worth monitoring — no confirmed trend signal yet", "值得关注，暂无确认的趋势信号"),
}

# GEX regime plain words
_REGIME_PLAIN_EN = {
    "long":     "Market makers are net long gamma — price pinned near current level",
    "positive": "Market makers are net long gamma — price pinned near current level",
    "short":    "Market makers are net short gamma — price moves may amplify",
    "negative": "Market makers are net short gamma — price moves may amplify",
    "neutral":  "Balanced gamma positioning",
}
_REGIME_PLAIN_ZH = {
    "long":     "做市商净持有正伽玛，价格倾向于在当前水平附近震荡",
    "positive": "做市商净持有正伽玛，价格倾向于在当前水平附近震荡",
    "short":    "做市商净持有负伽玛，价格波动可能被放大",
    "negative": "做市商净持有负伽玛，价格波动可能被放大",
    "neutral":  "伽玛头寸平衡",
}

# Smart money action plain words
_SM_ACTION_EN = {
    "buy": "Buying",
    "sell": "Selling",
    "hold": "Holding",
    "new": "New position",
    "sold_out": "Exited",
    "add": "Adding",
    "reduce": "Reducing",
}
_SM_ACTION_ZH = {
    "buy": "买入",
    "sell": "卖出",
    "hold": "持有",
    "new": "新建仓",
    "sold_out": "清仓",
    "add": "加仓",
    "reduce": "减仓",
}

# Valuation multiple display labels
_VAL_LABELS: dict[str, tuple[str, str]] = {
    "trailing_pe":       ("P/E (trailing)", "市盈率（历史）"),
    "forward_pe":        ("P/E (forward)", "市盈率（预测）"),
    "price_to_book":     ("P/B", "市净率"),
    "price_to_sales":    ("P/S", "市销率"),
    "earnings_yield":    ("Earnings yield", "盈利收益率"),
    "fcf_yield_true":    ("FCF yield", "自由现金流收益率"),
    "shareholder_yield": ("Shareholder yield", "股东收益率"),
    "ev_to_ebitda":      ("EV/EBITDA", "企业价值/EBITDA"),
    "price_to_fcf":      ("P/FCF", "市值/自由现金流"),
}

# Factor display
_FACTOR_LABELS: dict[str, tuple[str, str]] = {
    "value":         ("Value", "价值"),
    "profitability": ("Profitability", "盈利能力"),
    "quality":       ("Quality", "质量"),
    "investment":    ("Investment", "资本投入"),
    "payout":        ("Shareholder payout", "股东回报"),
    "low_vol":       ("Low volatility", "低波动"),
    "low_beta":      ("Low market beta", "低市场敏感度"),
    "accruals":      ("Earnings quality", "盈利质量"),
    "short_interest":("Short interest", "空头兴趣"),
}

# Altdata channel labels
_CHANNEL_EN = {
    "congress_buy":      "Congressional buy activity",
    "congress_sell":     "Congressional sell activity",
    "patent_cluster":    "Recent patent filings",
    "wsb_mentions":      "Retail trader chatter",
    "trump":             "Policy linkage",
    "affiliation":       "Notable ownership/affiliation",
    "special_situation": "Special situation flag",
}
_CHANNEL_ZH = {
    "congress_buy":      "国会议员买入记录",
    "congress_sell":     "国会议员卖出记录",
    "patent_cluster":    "近期专利申请",
    "wsb_mentions":      "散户关注度较高",
    "trump":             "政策关联",
    "affiliation":       "知名持仓/关联",
    "special_situation": "特殊情况标记",
}


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------

def _safe_float(v: Any, decimals: int = 2) -> str:
    """Format a float; returns '' on failure."""
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return ""


def _clean_str(v: Any) -> str:
    """Return str or '' guarding against None/nan/null."""
    if v is None:
        return ""
    s = str(v)
    if s.lower() in ("none", "nan", "nat", "null"):
        return ""
    return s


def _sector_display(raw: str | None) -> str:
    if not raw:
        return ""
    return _SECTOR_DISPLAY.get(raw, raw)


def _humanize_number(v: Any) -> str:
    """Format large numbers: $382B, $24.3M, $1.2K, 24.3%."""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == 0:
        return "$0"
    sign = "-" if f < 0 else ""
    f = abs(f)
    if f >= 1e12:
        return f"{sign}${f/1e12:.1f}T"
    if f >= 1e9:
        return f"{sign}${f/1e9:.1f}B"
    if f >= 1e6:
        return f"{sign}${f/1e6:.1f}M"
    if f >= 1e3:
        return f"{sign}${f/1e3:.1f}K"
    return f"{sign}${f:.2f}"


def _pct_word_en(v: Any) -> str:
    if v is None:
        return ""
    try:
        p = float(v)
    except (TypeError, ValueError):
        return ""
    if p >= 80:
        return "top 20%"
    if p >= 60:
        return "above average"
    if p <= 20:
        return "bottom 20%"
    if p <= 40:
        return "below average"
    return "middle of the pack"


def _pct_word_zh(v: Any) -> str:
    if v is None:
        return ""
    try:
        p = float(v)
    except (TypeError, ValueError):
        return ""
    if p >= 80:
        return "前20%"
    if p >= 60:
        return "高于平均"
    if p <= 20:
        return "后20%"
    if p <= 40:
        return "低于平均"
    return "中等水平"


def _rsi_zone(rsi: float | None) -> tuple[str, str]:
    if rsi is None:
        return ("", "")
    if rsi >= 70:
        return ("Overbought", "超买区域")
    if rsi >= 60:
        return ("Elevated", "偏高")
    if rsi <= 30:
        return ("Oversold", "超卖区域")
    if rsi <= 40:
        return ("Depressed", "偏低")
    return ("Neutral zone", "中性区域")


def _adx_word(adx: float | None) -> tuple[str, str]:
    if adx is None:
        return ("", "")
    if adx >= 30:
        return ("Strong trend", "趋势强劲")
    if adx >= 20:
        return ("Trending", "趋势中")
    return ("No clear trend", "无明显趋势")


def _rel_vol_word(rv: float | None) -> tuple[str, str]:
    if rv is None:
        return ("Normal volume", "正常成交量")
    try:
        f = float(rv)
    except (TypeError, ValueError):
        return ("Normal volume", "正常成交量")
    if f >= 2.0:
        return ("Heavy volume", "成交量大幅偏高")
    if f >= 1.5:
        return ("Above-average volume", "成交量高于平均")
    if f <= 0.5:
        return ("Light volume", "成交量清淡")
    return ("Normal volume", "正常成交量")


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
    if not freshness_date:
        return True
    try:
        d = date.fromisoformat(freshness_date)
        return (date.today() - d).days > STALENESS_DAYS
    except (ValueError, TypeError):
        return True


def build_sitemap(existing_xml: str, stocks_entries: list[dict]) -> str:
    """Merge stocks entries into existing sitemap, preserving non-/stocks/ entries."""
    non_stocks_lines: list[str] = []
    for line in existing_xml.splitlines():
        stripped = line.strip()
        if stripped.startswith("<url>") and "/stocks/" in stripped:
            continue
        non_stocks_lines.append(line)

    base = "\n".join(non_stocks_lines).rstrip()
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


# ---------------------------------------------------------------------------
# Stance computation (v2 — prefers ladder state from stockdata blob)
# ---------------------------------------------------------------------------

def _trunc_words(s: str, limit: int) -> str:
    """Truncate at a word boundary with an ellipsis — never mid-word."""
    if not s or len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:·—-")
    return (cut or s[:limit]) + "…"


# Machine-read tokens that must not surface in Tier-1 stance copy (operator
# order 2026-07-20: "remove machine text" — e.g. "(daily RSI 72, 98th-percentile
# volatility)"). The engine strings live in the blob; the page sanitizes.
_MACHINE_TOKEN_RE = re.compile(
    r"RSI|MACD|ADX|stoch|percentil|pctile|z[-= ]?score|\bn=|σ|volatility|BBWP|ATR",
    re.IGNORECASE,
)


def _scrub_machine(s: str) -> str:
    """Strip machine parentheticals + engineering shorthand from EN stance copy.

    "extended (overbought (daily RSI 72))"      -> "extended (overbought)"
    "a low formed ~4 day(s) ago @ 275.15"       -> "a low formed ~4 days ago at $275.15"
    """
    if not s:
        return s
    s = s.replace("day(s)", "days").replace("week(s)", "weeks").replace("month(s)", "months")
    # innermost-first: nested machine parens dissolve one layer per pass
    for _ in range(4):
        out = re.sub(
            r"\(([^()]*)\)",
            lambda m: "" if _MACHINE_TOKEN_RE.search(m.group(1)) else f"({m.group(1)})",
            s,
        )
        if out == s:
            break
        s = out
    s = re.sub(r"@ ?(\d)", r"at $\1", s)
    s = re.sub(r"\(\s*\)", "", s)               # emptied shells
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s.strip()


def _scrub_machine_zh(s: str) -> str:
    """ZH twin of _scrub_machine (full-width parens; '@' → '价位')."""
    if not s:
        return s
    for _ in range(4):
        out = re.sub(
            r"（([^（）]*)）",
            lambda m: "" if _MACHINE_TOKEN_RE.search(m.group(1)) else f"（{m.group(1)}）",
            s,
        )
        out = re.sub(
            r"\(([^()]*)\)",
            lambda m: "" if _MACHINE_TOKEN_RE.search(m.group(1)) else f"({m.group(1)})",
            out,
        )
        if out == s:
            break
        s = out
    s = re.sub(r"\s*@ ?(\d)", r"，价位 \1", s)
    s = re.sub(r"（\s*）|\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def compute_stance(
    blob: dict | None,
    signals: dict | None = None,
    intel: dict | None = None,
) -> tuple[str, str, str, str, str]:
    """Map engine states to plain-word stance.
    Returns (stance_en, stance_zh, stance_key, invalidation_en, invalidation_zh).
    v2: prefers blob.ladder.state / conviction; falls back to v1 signals/intel path.
    Never raises.
    """
    try:
        if blob:
            ladder = blob.get("ladder") or {}
            lstate = _clean_str(ladder.get("state")).upper()
            conv = blob.get("conviction") or {}
            band_en = _clean_str(conv.get("band_en"))
            band_zh = _clean_str(conv.get("band_zh"))
            verdict = _clean_str(conv.get("verdict"))
            verdict_zh = _clean_str(conv.get("verdict_zh"))

            # Extended stance desc: prefer conviction band when available
            if lstate:
                stance_key = _LADDER_TO_STANCE.get(lstate, "watch")
                desc_en, desc_zh = _STANCE_DESC.get(stance_key, _STANCE_DESC["watch"])
                # Override desc with conviction band if available
                if band_en:
                    desc_en = band_en
                if band_zh:
                    desc_zh = band_zh
                # Invalidation from ladder entry text
                entry = ladder.get("entry") or {}
                inv_text = _clean_str(entry.get("text"))
                inv_text_zh = _clean_str(entry.get("text_zh"))
                stance_en_text = verdict if verdict else desc_en
                stance_zh_text = verdict_zh if verdict_zh else desc_zh
                return (stance_en_text, stance_zh_text, stance_key,
                        _trunc_words(inv_text, 160), _trunc_words(inv_text_zh, 120))

            # Conviction band as fallback
            if band_en:
                key = "watch"
                if "uptrend" in band_en.lower() or "rally" in band_en.lower():
                    key = "uptrend"
                elif "bottom" in band_en.lower() or "low" in band_en.lower():
                    key = "bottoming"
                elif "protect" in band_en.lower():
                    key = "protect"
                elif "aside" in band_en.lower() or "avoid" in band_en.lower():
                    key = "aside"
                return (band_en, band_zh or band_en, key, "", "")

        # v1 signals fallback
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

        # Intel label fallback
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


# ---------------------------------------------------------------------------
# OHlc helpers — trailing returns + seasonality
# ---------------------------------------------------------------------------

def compute_trailing_returns(
    bars: list, spy_bars: list | None = None
) -> dict:
    """Compute 1w/1m/3m/6m/YTD/1y/3y/5y returns from bar list.
    Bars format: [date, o, h, l, c, vol] (o=1) or [date, c, vol] (o=0).
    Returns dict of period -> (ticker_ret, spy_ret | None).
    """
    results: dict = {}
    if not bars:
        return results

    def _close(bar: list) -> float | None:
        try:
            # 6-element = OHLCV, 3-element = C+V
            return float(bar[4]) if len(bar) >= 6 else float(bar[1])
        except (IndexError, TypeError, ValueError):
            return None

    def _bar_date(bar: list) -> date | None:
        try:
            return date.fromisoformat(str(bar[0])[:10])
        except (IndexError, TypeError, ValueError):
            return None

    last_close = _close(bars[-1])
    last_date = _bar_date(bars[-1])
    if last_close is None or last_date is None:
        return results

    # Build SPY close map if available
    spy_map: dict[date, float] = {}
    if spy_bars:
        for b in spy_bars:
            d = _bar_date(b)
            c = _close(b)
            if d and c:
                spy_map[d] = c

    def _spy_ret(base_date: date) -> float | None:
        spy_last = spy_map.get(last_date)
        spy_base = spy_map.get(base_date)
        if spy_last and spy_base and spy_base > 0:
            return (spy_last / spy_base - 1) * 100
        return None

    def _find_bar_n_days_ago(n_days: int) -> tuple[float | None, date | None]:
        """Find close roughly n_days calendar days ago."""
        target = last_date
        from datetime import timedelta
        cutoff = last_date - timedelta(days=n_days)
        # Walk backwards to find first bar on or before cutoff
        best_c, best_d = None, None
        for bar in reversed(bars):
            d = _bar_date(bar)
            if d is None:
                continue
            if d <= cutoff:
                c = _close(bar)
                if c:
                    best_c, best_d = c, d
                    break
        return best_c, best_d

    # 1w ≈ 5 trading days = ~7 calendar days
    # 1m ≈ 21 trading = ~30 cal
    # 3m ≈ 63 td = ~90 cal
    # 6m ≈ 126 td = ~180 cal
    # 1y ≈ 252 td = ~365 cal
    # 3y ≈ 756 td = ~1095 cal
    # 5y ≈ 1260 td = ~1825 cal
    periods = {
        "1w":  7,
        "1m":  30,
        "3m":  90,
        "6m":  180,
        "1y":  365,
        "3y":  1095,
        "5y":  1825,
    }
    for label, cal_days in periods.items():
        base_c, base_d = _find_bar_n_days_ago(cal_days)
        if base_c and base_c > 0:
            ret = (last_close / base_c - 1) * 100
            spy_r = _spy_ret(base_d) if base_d else None
            results[label] = {"ticker": round(ret, 1), "spy": round(spy_r, 1) if spy_r is not None else None}

    # YTD — first bar of current year
    jan1 = date(last_date.year, 1, 1)
    for bar in bars:
        d = _bar_date(bar)
        c = _close(bar)
        if d and d >= jan1 and c and c > 0:
            ret = (last_close / c - 1) * 100
            spy_r = _spy_ret(d)
            results["YTD"] = {"ticker": round(ret, 1), "spy": round(spy_r, 1) if spy_r is not None else None}
            break

    return results


def compute_seasonality(bars: list) -> list[dict] | None:
    """Compute monthly seasonality (win_rate + median return per calendar month).
    Returns list of 12 dicts or None if <SEASONALITY_MIN_BARS.
    """
    if len(bars) < SEASONALITY_MIN_BARS:
        return None

    def _close(bar: list) -> float | None:
        try:
            return float(bar[4]) if len(bar) >= 6 else float(bar[1])
        except (IndexError, TypeError, ValueError):
            return None

    def _bar_date(bar: list) -> date | None:
        try:
            return date.fromisoformat(str(bar[0])[:10])
        except (IndexError, TypeError, ValueError):
            return None

    # Collect (year, month) -> list of daily returns
    monthly_rets: dict[tuple[int, int], list[float]] = {}
    for i in range(1, len(bars)):
        d = _bar_date(bars[i])
        c = _close(bars[i])
        pc = _close(bars[i - 1])
        if d and c and pc and pc > 0:
            daily_ret = (c / pc - 1) * 100
            key = (d.year, d.month)
            monthly_rets.setdefault(key, []).append(daily_ret)

    # Aggregate per calendar month (1-12) across all years
    by_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for (yr, mo), rets in monthly_rets.items():
        if rets:
            monthly_total = sum(rets)
            by_month[mo].append(monthly_total)

    result = []
    for m in range(1, 13):
        rets = by_month[m]
        if not rets:
            result.append({
                "month": month_abbr[m],
                "n": 0,
                "win_rate": None,
                "median_pct": None,
            })
        else:
            wins = sum(1 for r in rets if r > 0)
            result.append({
                "month": month_abbr[m],
                "n": len(rets),
                "win_rate": round(wins / len(rets) * 100, 0),
                "median_pct": round(sorted(rets)[len(rets) // 2], 1),
            })
    return result


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("::warning::could not load %s: %s", path, e)
    return None


def load_all_aggregates(site: Path) -> dict:
    """Load all shared aggregates once."""
    agg: dict = {}

    # factor_betas.json -> {ticker -> {mkt, ...}}
    fb = _load_json(site / "factor_betas.json")
    agg["factor_betas"] = (fb.get("betas") or {}) if fb else {}

    # factors.json table -> {ticker -> row} (name/sector/mktcap_bn — peers source)
    fr = _load_json(site / "factordata" / "factors.json")
    agg["factors_map"] = {r["ticker"]: r for r in ((fr or {}).get("table") or []) if r.get("ticker")}

    # tech_screener.json -> {ticker -> row}
    ts = _load_json(site / "factordata" / "tech_screener.json")
    agg["tech_screener"] = (ts.get("stocks") or {}) if ts else {}

    # member_context.json -> by_ticker
    mc_raw = _load_json(site / "basketdata" / "member_context.json")
    if mc_raw:
        agg["member_ctx_as_of"] = _clean_str(mc_raw.get("as_of"))
        agg["member_ctx_map"] = mc_raw.get("by_ticker") or {}
    else:
        agg["member_ctx_as_of"] = ""
        agg["member_ctx_map"] = {}

    # baskets.json -> {id -> {name, name_zh}}
    # Real format: flat baskets[] list; categories[] is a list of strings.
    # Guard: categories may be list-of-dicts (nested) or list-of-strings (flat).
    baskets_raw = _load_json(site / "basketdata" / "baskets.json")
    if baskets_raw:
        basket_list: list = []
        # Try nested format (categories[].baskets[]) first
        for cat in (baskets_raw.get("categories") or []):
            if isinstance(cat, dict):
                for b in (cat.get("baskets") or []):
                    basket_list.append(b)
        # Flat format: baskets[] directly (the real production format)
        if not basket_list:
            basket_list = baskets_raw.get("baskets") or []
        agg["baskets_map"] = {b["id"]: b for b in basket_list if isinstance(b, dict) and b.get("id")}
    else:
        agg["baskets_map"] = {}

    # intelligence/by_ticker.json -> tickers
    intel_raw = _load_json(site / "intelligence" / "by_ticker.json")
    agg["intel_as_of"] = _clean_str((intel_raw or {}).get("as_of")) if intel_raw else ""
    agg["intel_map"] = (intel_raw.get("tickers") or {}) if intel_raw else {}

    # news/by_ticker.json -> tickers
    news_raw = _load_json(site / "news" / "by_ticker.json")
    agg["news_as_of"] = _clean_str((news_raw or {}).get("asof", (news_raw or {}).get("as_of", "")))
    agg["news_map"] = (news_raw.get("tickers") or {}) if news_raw else {}

    # altdata/by_ticker.json -> tickers (secondary; blob.altdata is primary)
    alt_raw = _load_json(site / "altdata" / "by_ticker.json")
    agg["alt_as_of"] = _clean_str((alt_raw or {}).get("as_of", (alt_raw or {}).get("asof", "")))
    agg["alt_map"] = (alt_raw.get("tickers") or {}) if alt_raw else {}

    # SPY ohlc for benchmark returns
    spy_ohlc = _load_json(site / "ohlc" / "SPY.json")
    agg["spy_bars"] = (spy_ohlc.get("bars") or []) if spy_ohlc else []
    if not agg["spy_bars"]:
        # Fallback: committed data/yahoo/SPY.parquet -> close-format bars
        try:
            import pandas as pd
            spy_df = pd.read_parquet(str(_ROOT / "data" / "yahoo" / "SPY.parquet"))
            col = "close" if "close" in spy_df.columns else "close_price"
            agg["spy_bars"] = [
                [str(idx)[:10], float(v)] for idx, v in spy_df[col].dropna().items()
            ]
        except Exception as e:  # noqa: BLE001
            log.warning("::warning::SPY fallback load failed: %s", e)

    return agg


def load_per_ticker(site: Path, ticker: str) -> dict:
    """Load per-ticker artifacts. Fail-soft."""
    result: dict = {}

    # PRIMARY: stockdata blob (v2 — full rich schema)
    blob = _load_json(site / "stockdata" / f"{ticker}.json")
    result["blob"] = blob
    result["blob_asof"] = _clean_str((blob or {}).get("asof")) if blob else ""

    # ohlc for trailing returns + seasonality + chart
    ohlc = _load_json(site / "ohlc" / f"{ticker}.json")
    result["ohlc"] = ohlc
    result["ohlc_bars"] = (ohlc.get("bars") or []) if ohlc else []
    result["ohlc_is_candle"] = ((ohlc or {}).get("o") == 1)

    # SECONDARY v1 artifacts (fallbacks / supplements)
    gex = _load_json(site / "gex" / f"{ticker}.json")
    result["gex_v1"] = gex
    result["gex_as_of"] = _clean_str((gex or {}).get("meta", {}).get("asof")) if gex else ""

    sig = _load_json(site / "signals" / f"{ticker}.json")
    result["signals"] = sig
    result["signals_as_of"] = _clean_str((sig or {}).get("asof")) if sig else ""

    flow = _load_json(site / "flow" / f"{ticker}.json")
    result["flow"] = flow
    result["flow_as_of"] = _clean_str((flow or {}).get("asof")) if flow else ""

    # stockbrief — fresh-only gate
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


# ---------------------------------------------------------------------------
# Chart rendering helper
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Deep dialogs (Wave 2 — popup dashboards; Tier-2/3 depth behind one click)
# ---------------------------------------------------------------------------

def _fmt_bn(v: Any) -> str:
    """Humanize a raw USD amount (blob raw values are absolute dollars)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    a = abs(f)
    if a >= 1e12: s = f"${f/1e12:.2f}T"
    elif a >= 1e9: s = f"${f/1e9:.1f}B"
    elif a >= 1e6: s = f"${f/1e6:.0f}M"
    else: s = f"${f:,.0f}"
    return s


def _fmt_pct(v: Any, dp: int = 1, sign: bool = False) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return f"{'+' if sign and f > 0 else ''}{f:.{dp}f}%"


def _kv(rows: list) -> dict:
    return {"kind": "kv", "rows": [r for r in rows if r and r.get("v") not in (None, "", "None")]}


def _panel_alive(p: dict) -> bool:
    if p.get("kind") == "kv":
        return bool(p.get("rows"))
    if p.get("kind") == "table":
        return bool(p.get("rows"))
    if p.get("kind") == "cards":
        return bool(p.get("cards"))
    if p.get("kind") == "notes":
        return bool(p.get("lines"))
    return False


def _mk_dialog(did: str, ten: str, tzh: str, panels: list) -> dict | None:
    panels = [p for p in panels if p and _panel_alive(p)]
    if not panels:
        return None
    for p in panels:
        p.setdefault("title_en", ""); p.setdefault("title_zh", "")
    return {"id": did, "title_en": ten, "title_zh": tzh, "panels": panels}


def _deep_stats(blob: dict, performance: list | None, stats: dict | None) -> dict | None:
    val = blob.get("valuation") or {}
    alpha = blob.get("alpha") or {}
    tech = blob.get("tech") or {}
    panels: list = []

    # Valuation vs sector — {v, med, cheap} triplets + yield-style singles
    vrows = []
    for key, en, zh in (("trailing_pe", "P/E (trailing)", "市盈率（静态）"),
                        ("forward_pe", "P/E (forward)", "市盈率（预测）"),
                        ("price_to_book", "Price / Book", "市净率"),
                        ("price_to_sales", "Price / Sales", "市销率"),
                        ("ev_to_ebitda", "EV / EBITDA", "EV/EBITDA"),
                        ("earnings_yield", "Earnings yield", "盈利收益率"),
                        ("fcf_proxy_yield", "Free-cash-flow yield", "自由现金流收益率"),
                        ("shareholder_yield", "Shareholder yield", "股东综合回报率")):
        rec = val.get(key)
        if rec is None:
            continue
        if isinstance(rec, dict):
            v, med, cheap = rec.get("v"), rec.get("med"), rec.get("cheap")
            if v is None:
                continue
            unit = "%" if "yield" in key else "×"
            vrows.append([{"en": en, "zh": zh}, f"{float(v):.1f}{unit}",
                          f"{float(med):.1f}{unit}" if med is not None else "—",
                          _fmt_pct(cheap, 0) if cheap is not None else "—"])
        else:
            try:
                unit = "%" if "yield" in key else "×"
                vrows.append([{"en": en, "zh": zh}, f"{float(rec):.1f}{unit}", "—", "—"])
            except (TypeError, ValueError):
                continue
    if vrows:
        panels.append({"kind": "table", "title_en": "Valuation vs sector", "title_zh": "估值对比行业",
                       "head": [["Multiple", "指标"], ["This stock", "本股"], ["Sector median", "行业中位"], ["Cheaper than", "相对便宜"]],
                       "rows": vrows})

    # Relative strength (alpha block) — plain-word framing
    rs_rows = []
    for key, en, zh in (("rs", "vs market, 1 month", "相对大盘（1个月）"),
                        ("rs3m", "vs market, 3 months", "相对大盘（3个月）"),
                        ("rs6m", "vs market, 6 months", "相对大盘（6个月）"),
                        ("rs12m", "vs market, 12 months", "相对大盘（12个月）")):
        v = alpha.get(key)
        if v is None:
            continue
        f = float(v)
        word_en = "stronger than most" if f >= 70 else ("weaker than most" if f <= 30 else "middle of the pack")
        word_zh = "强于多数" if f >= 70 else ("弱于多数" if f <= 30 else "居中")
        rs_rows.append({"k_en": en, "k_zh": zh, "v": f"{f:.0f}/100 — ", "v_en": word_en, "v_zh": word_zh,
                        "cls": "pos" if f >= 70 else ("neg" if f <= 30 else "")})
    if alpha.get("sector_rank") is not None and alpha.get("sector_n"):
        rs_rows.append({"k_en": "Rank in sector", "k_zh": "行业内排名",
                        "v": f"#{int(alpha['sector_rank'])} / {int(alpha['sector_n'])}", "v_en": "", "v_zh": ""})
    if rs_rows:
        panels.append({"kind": "kv", "title_en": "Relative strength", "title_zh": "相对强度",
                       "rows": rs_rows,
                       "foot_en": "0–100 percentile of total return vs all covered stocks.",
                       "foot_zh": "总回报在全部覆盖股票中的百分位（0–100）。"})

    # Price history — the old Performance table's home
    if performance:
        prows = []
        for row in performance:
            prows.append([{"en": row.get('label_en', ''), "zh": row.get('label_zh', '')},
                          row.get("ticker_ret") or "—", row.get("spy_ret") or "—"])
        panels.append({"kind": "table", "title_en": "Price history", "title_zh": "价格历史",
                       "head": [["Period", "周期"], ["This stock", "本股"], ["S&P 500", "标普500"]],
                       "rows": prows})

    trows = []
    if stats:
        for key, en, zh in (("beta", "Beta vs market", "贝塔"),
                            ("hv_pctile", "Volatility rank", "波动率分位"),
                            ("short_pct_float", "Short interest", "空头占比"),
                            ("mktcap", "Market cap", "市值"),
                            ("eps", "EPS (trailing)", "每股收益"),
                            ("div_yield", "Dividend yield", "股息率")):
            v = stats.get(key)
            if v:
                trows.append({"k_en": en, "k_zh": zh, "v": str(v), "v_en": "", "v_zh": ""})
    off_hi = tech.get("off_52w_high_pct")
    if off_hi is not None:
        trows.append({"k_en": "Off 52-week high", "k_zh": "距52周高点", "v": _fmt_pct(-abs(float(off_hi)), 1, sign=True), "v_en": "", "v_zh": ""})
    rv = tech.get("rel_volume")
    if rv is not None:
        trows.append({"k_en": "Volume vs normal", "k_zh": "成交量相对平常", "v": f"{float(rv):.1f}×", "v_en": "", "v_zh": ""})
    if trows:
        panels.append({"kind": "kv", "title_en": "Trading information", "title_zh": "交易信息", "rows": trows})

    return _mk_dialog("stats", "Statistics — full detail", "统计数据 — 完整明细", panels)


def _deep_financials(blob: dict) -> dict | None:
    fin = blob.get("financials") or {}
    my = fin.get("multiyear") or {}
    raw = fin.get("raw") or {}
    aq = blob.get("accounting_quality") or {}
    panels: list = []

    years = my.get("years") or []
    if years:
        head = [["", ""]] + [[str(y), str(y)] for y in years]
        rows = []
        def _series(key, label_en, label_zh, fmt):
            arr = my.get(key)
            if not arr:
                return
            cells = [{"en": label_en, "zh": label_zh}]
            for i in range(len(years)):
                v = arr[i] if i < len(arr) else None
                cells.append(fmt(v) if v is not None else "—")
            rows.append(cells)
        _series("revenue", "Revenue", "营业收入", _fmt_bn)
        _series("eps", "EPS", "每股收益", lambda v: f"${float(v):.2f}")
        _series("fcf", "Free cash flow", "自由现金流", _fmt_bn)
        _series("gross_margin", "Gross margin", "毛利率", lambda v: _fmt_pct(v))
        _series("net_margin", "Net margin", "净利率", lambda v: _fmt_pct(v))
        _series("fcf_margin", "FCF margin", "自由现金流利润率", lambda v: _fmt_pct(v))
        if rows:
            panels.append({"kind": "table", "title_en": "Multi-year record", "title_zh": "多年财务记录",
                           "head": head, "rows": rows})

    snap = []
    for key, en, zh in (("revenue", "Revenue (FY)", "营业收入（财年）"), ("gross_profit", "Gross profit", "毛利润"),
                        ("ni", "Net income", "净利润"), ("cfo", "Operating cash flow", "经营现金流"),
                        ("assets", "Total assets", "总资产"), ("equity", "Shareholder equity", "股东权益"),
                        ("debt_lt", "Long-term debt", "长期负债"), ("dividends", "Dividends paid", "股息支出"),
                        ("repurchases", "Buybacks", "股票回购")):
        v = raw.get(key)
        if v is not None:
            snap.append({"k_en": en, "k_zh": zh, "v": _fmt_bn(v), "v_en": "", "v_zh": ""})
    shares = raw.get("shares")
    if shares:
        snap.append({"k_en": "Shares outstanding", "k_zh": "总股本", "v": f"{float(shares)/1e9:.2f}B", "v_en": "", "v_zh": ""})
    if snap:
        panels.append({"kind": "kv", "title_en": "Latest fiscal year", "title_zh": "最近财年", "rows": snap})

    qual = []
    for key, en, zh, fmt in (("roe", "Return on equity", "股本回报率", _fmt_pct),
                             ("roa", "Return on assets", "资产回报率", _fmt_pct),
                             ("debt_to_assets", "Debt / assets", "负债/资产", lambda v: _fmt_pct(float(v) * 100 if abs(float(v)) <= 1.5 else float(v))),
                             ("rev_growth", "Revenue growth", "营收增速", lambda v: _fmt_pct(v, 1, sign=True)),
                             ("ni_growth", "Profit growth", "利润增速", lambda v: _fmt_pct(v, 1, sign=True)),
                             ("asset_growth", "Asset growth", "资产增速", lambda v: _fmt_pct(v, 1, sign=True))):
        v = fin.get(key)
        if v is not None:
            qual.append({"k_en": en, "k_zh": zh, "v": fmt(v), "v_en": "", "v_zh": ""})
    if qual:
        panels.append({"kind": "kv", "title_en": "Returns & growth", "title_zh": "回报与增长", "rows": qual})

    reads = aq.get("reads") or []
    lines = []
    for r in reads[:6]:
        if not isinstance(r, dict):
            continue
        lab, det = _clean_str(r.get("label")), _clean_str(r.get("detail"))
        lab_zh = _clean_str(r.get("label_zh") or lab)
        det_zh = _clean_str(r.get("detail_zh") or det)
        state = _clean_str(r.get("state"))
        if lab:
            lines.append({"en": f"{lab}: {det}" if det else lab,
                          "zh": f"{lab_zh}：{det_zh}" if det_zh else lab_zh,
                          "cls": "wrn" if state == "caution" else ("pos" if state == "good" else "mut")})
    if lines:
        panels.append({"kind": "notes", "title_en": "Accounting quality checks", "title_zh": "会计质量检查", "lines": lines})

    return _mk_dialog("financials", "Financials — full detail", "财务数据 — 完整明细", panels)


_MTF_LABELS = {"D": ("Daily", "日线"), "3D": ("3-day", "3日线"), "W": ("Weekly", "周线"), "M": ("Monthly", "月线")}


def _deep_technicals(blob: dict, tech_screener_row: dict | None) -> dict | None:
    tech = blob.get("tech") or {}
    vs = blob.get("vol_squeeze") or {}
    mtf = blob.get("mtf") or {}
    panels: list = []

    ind = []
    def _tr(v, en, zh, fmt=lambda x: f"{float(x):.1f}", cls=""):
        if v is None:
            return
        try:
            ind.append({"k_en": en, "k_zh": zh, "v": fmt(v), "v_en": "", "v_zh": "", "cls": cls})
        except (TypeError, ValueError):
            pass
    _tr(tech.get("rsi14"), "RSI (14-day)", "RSI（14日）", lambda x: f"{float(x):.0f}")
    _tr(tech.get("rsi2"), "RSI (2-day)", "RSI（2日）", lambda x: f"{float(x):.0f}")
    _tr(tech.get("adx14"), "Trend strength (ADX)", "趋势强度（ADX）", lambda x: f"{float(x):.0f}")
    _tr(tech.get("atr_pct"), "Average daily range", "平均日波幅", lambda x: _fmt_pct(x))
    _tr(tech.get("pct_vs_20dma"), "vs 20-day average", "相对20日均线", lambda x: _fmt_pct(x, 1, sign=True))
    _tr(tech.get("pct_vs_50dma"), "vs 50-day average", "相对50日均线", lambda x: _fmt_pct(x, 1, sign=True))
    _tr(tech.get("pct_vs_200dma"), "vs 200-day average", "相对200日均线", lambda x: _fmt_pct(x, 1, sign=True))
    if tech.get("golden") is not None:
        ind.append({"k_en": "Golden cross (50>200)", "k_zh": "金叉（50>200）",
                    "v": "", "v_en": "in effect" if tech.get("golden") else "not in effect",
                    "v_zh": "生效中" if tech.get("golden") else "未生效",
                    "cls": "pos" if tech.get("golden") else "mut"})
    if tech.get("macd_pos") is not None:
        ind.append({"k_en": "MACD", "k_zh": "MACD", "v": "",
                    "v_en": "above signal" if tech.get("macd_pos") else "below signal",
                    "v_zh": "位于信号线上方" if tech.get("macd_pos") else "位于信号线下方",
                    "cls": "pos" if tech.get("macd_pos") else "neg"})
    if ind:
        panels.append({"kind": "kv", "title_en": "Indicator readings", "title_zh": "指标读数", "rows": ind})

    # Multi-timeframe alignment — verdict word per TF from macd_pos + stoch/rsi
    mrows = []
    for tf in ("D", "3D", "W", "M"):
        rec = mtf.get(tf)
        if not isinstance(rec, dict):
            continue
        macd_ok = rec.get("macd_pos")
        if macd_ok is None:
            continue
        en, zh = _MTF_LABELS[tf]
        word_en = "momentum up" if macd_ok else "momentum down"
        word_zh = "动能向上" if macd_ok else "动能向下"
        extra = []
        if rec.get("macd_cross_up"): extra.append(("fresh upturn", "刚刚转强"))
        elif rec.get("macd_approaching_up"): extra.append(("turning up soon", "接近转强"))
        elif rec.get("macd_cross_dn"): extra.append(("fresh downturn", "刚刚转弱"))
        if extra:
            word_en += f" — {extra[0][0]}"
            word_zh += f"——{extra[0][1]}"
        mrows.append({"k_en": en, "k_zh": zh, "v": "", "v_en": word_en, "v_zh": word_zh,
                      "cls": "pos" if macd_ok else "neg"})
    if mrows:
        panels.append({"kind": "kv", "title_en": "Timeframe alignment", "title_zh": "多周期共振",
                       "rows": mrows,
                       "foot_en": "When daily through monthly point the same way, moves carry further.",
                       "foot_zh": "当日线到月线方向一致时，行情往往更有延续性。"})

    sq = []
    state = _clean_str(vs.get("state"))
    if state:
        word_en = {"COMPRESSION": "coiling — range compressed", "EXPANSION": "expanding — range opening up"}.get(state, state.title())
        word_zh = {"COMPRESSION": "压缩中 — 波幅收窄", "EXPANSION": "扩张中 — 波幅放大"}.get(state, state)
        sq.append({"k_en": "Range state", "k_zh": "波幅状态", "v": "", "v_en": word_en, "v_zh": word_zh})
    if vs.get("days_compressed"):
        sq.append({"k_en": "Days compressed", "k_zh": "已压缩天数", "v": str(int(vs["days_compressed"])), "v_en": "", "v_zh": ""})
    if vs.get("bbwp") is not None:
        sq.append({"k_en": "Range width percentile", "k_zh": "波幅宽度分位", "v": f"{float(vs['bbwp']):.0f}/100", "v_en": "", "v_zh": ""})
    if sq:
        panels.append({"kind": "kv", "title_en": "Volatility regime", "title_zh": "波动状态", "rows": sq})

    sigs = (tech_screener_row or {}).get("signals") or []
    srows = []
    for s in sigs:
        name = _clean_str(s.get("display_en"))
        if not name:
            continue
        active = s.get("state") == 1 or s.get("state") == "1"
        age = s.get("age_days")
        srows.append([name,
                      {"en": "● active", "zh": "● 活跃"} if active else {"en": "quiet", "zh": "静默"},
                      f"{age}d" if age not in (None, "") else "—"])
    if srows:
        panels.append({"kind": "table", "title_en": "All tracked signals", "title_zh": "全部跟踪信号",
                       "head": [["Signal", "信号"], ["State", "状态"], ["Age", "距今"]],
                       "rows": srows})

    return _mk_dialog("technicals", "Technicals — full detail", "技术面 — 完整明细", panels)


def _deep_earnings(blob: dict) -> dict | None:
    earn = blob.get("earnings") or {}
    rev = blob.get("revisions") or {}
    an = blob.get("analyst") or {}
    tech = blob.get("tech") or {}
    panels: list = []

    sur = earn.get("surprises") or []
    srows = []
    for s in sur:
        try:
            sp = float(s.get("surprise_pct") or 0)
        except (TypeError, ValueError):
            sp = 0.0
        srows.append([_clean_str(s.get("qtr")), f"${float(s.get('eps') or 0):.2f}",
                      f"${float(s.get('consensus') or 0):.2f}",
                      f"{'+' if sp > 0 else ''}{sp:.1f}%"])
    if srows:
        panels.append({"kind": "table", "title_en": "Surprise history", "title_zh": "超预期历史",
                       "head": [["Quarter", "季度"], ["Reported", "实际"], ["Expected", "预期"], ["Surprise", "超预期"]],
                       "rows": srows})

    rrows = []
    if rev.get("n_analysts"):
        rrows.append({"k_en": "Analysts covering", "k_zh": "覆盖分析师", "v": f"{int(float(rev['n_analysts']))}", "v_en": "", "v_zh": ""})
    if rev.get("breadth") is not None:
        b = float(rev["breadth"])
        word_en = "mostly raising" if b > 0.6 else ("mostly cutting" if b < 0.4 else "mixed")
        word_zh = "多数上调" if b > 0.6 else ("多数下调" if b < 0.4 else "分歧")
        rrows.append({"k_en": "Estimate direction", "k_zh": "预期调整方向", "v": "", "v_en": word_en, "v_zh": word_zh,
                      "cls": "pos" if b > 0.6 else ("neg" if b < 0.4 else "")})
    if rev.get("est_chg_90d") is not None:
        rrows.append({"k_en": "Estimate change, 90 days", "k_zh": "预期变化（90天）",
                      "v": _fmt_pct(rev["est_chg_90d"], 1, sign=True), "v_en": "", "v_zh": ""})
    if rev.get("net_up_30d") is not None:
        rrows.append({"k_en": "Net upgrades, 30 days", "k_zh": "净上调（30天）",
                      "v": f"{float(rev['net_up_30d']):+.0f}", "v_en": "", "v_zh": ""})
    if rrows:
        panels.append({"kind": "kv", "title_en": "Estimate revisions", "title_zh": "预期修正", "rows": rrows})

    arows = []
    tgt = an.get("target")
    price = tech.get("price")
    if tgt and price:
        try:
            up = (float(tgt) / float(price) - 1) * 100
            arows.append({"k_en": "Average price target", "k_zh": "平均目标价",
                          "v": f"${float(tgt):,.0f} ({'+' if up >= 0 else ''}{up:.0f}%)", "v_en": "", "v_zh": "",
                          "cls": "pos" if up > 0 else "neg"})
        except (TypeError, ValueError):
            pass
    if an.get("rating"):
        arows.append({"k_en": "Street rating", "k_zh": "华尔街评级", "v": _clean_str(an.get("rating")), "v_en": "", "v_zh": ""})
    if an.get("forward_pe"):
        arows.append({"k_en": "Forward P/E", "k_zh": "预测市盈率", "v": f"{float(an['forward_pe']):.1f}×", "v_en": "", "v_zh": ""})
    if an.get("profit_margin") is not None:
        arows.append({"k_en": "Profit margin", "k_zh": "净利率", "v": _fmt_pct(an["profit_margin"]), "v_en": "", "v_zh": ""})
    if arows:
        panels.append({"kind": "kv", "title_en": "Analyst view", "title_zh": "分析师观点", "rows": arows})

    return _mk_dialog("earnings", "Earnings — full detail", "财务业绩 — 完整明细", panels)


def _deep_options(blob: dict, gex_v1: dict | None) -> dict | None:
    gx = blob.get("gex") or {}
    v1 = (gex_v1 or {}).get("summary") or {}
    ivs = blob.get("iv_spread") or {}
    panels: list = []

    def g(key):
        return gx.get(key) if gx.get(key) is not None else v1.get(key)

    lv = []
    for key, en, zh in (("call_wall", "Call wall", "看涨期权墙"), ("put_wall", "Put wall", "看跌期权墙"),
                        ("gamma_flip", "Gamma flip", "伽玛翻转位"), ("magnet_up", "Upside magnet", "上方磁吸位"),
                        ("magnet_down", "Downside magnet", "下方磁吸位")):
        v = g(key)
        if v is not None:
            try:
                lv.append({"k_en": en, "k_zh": zh, "v": f"${float(v):,.0f}", "v_en": "", "v_zh": ""})
            except (TypeError, ValueError):
                pass
    ng = g("net_gex_bn")
    if ng is not None:
        try:
            f = float(ng)
            lv.append({"k_en": "Net dealer gamma", "k_zh": "做市商净伽玛", "v": f"${f:+.1f}B", "v_en": "", "v_zh": "",
                       "cls": "pos" if f > 0 else "neg"})
        except (TypeError, ValueError):
            pass
    if g("dist_to_flip_pct") is not None:
        lv.append({"k_en": "Distance to flip", "k_zh": "距翻转位", "v": _fmt_pct(g("dist_to_flip_pct"), 1, sign=True), "v_en": "", "v_zh": ""})
    if lv:
        panels.append({"kind": "kv", "title_en": "Dealer positioning map", "title_zh": "做市商持仓地图", "rows": lv,
                       "foot_en": "Walls and magnets are strikes with heavy open interest — price often slows or gravitates there.",
                       "foot_zh": "期权墙与磁吸位是未平仓集中的行权价 — 价格常在附近减速或被吸引。"})

    vol = []
    if g("iv30") is not None:
        vol.append({"k_en": "Implied volatility (30d)", "k_zh": "隐含波动率（30天）", "v": _fmt_pct(g("iv30"), 0), "v_en": "", "v_zh": ""})
    ivr = (v1.get("iv_rank") or {}).get("rank_pct") if isinstance(v1.get("iv_rank"), dict) else None
    if ivr is not None:
        vol.append({"k_en": "IV rank (1 year)", "k_zh": "IV历史分位", "v": f"{float(ivr):.0f}/100", "v_en": "", "v_zh": ""})
    if gx.get("rr_25d") is not None:
        try:
            rr = float(gx["rr_25d"])
            vol.append({"k_en": "25-delta risk reversal", "k_zh": "25-delta风险逆转", "v": f"{rr:+.1f}%", "v_en": "", "v_zh": "",
                        "cls": "neg" if rr < 0 else "pos"})
        except (TypeError, ValueError):
            pass
    if ivs.get("ivspread") is not None:
        try:
            vol.append({"k_en": "Call-put IV spread", "k_zh": "看涨-看跌IV价差", "v": f"{float(ivs['ivspread']):+.1f}pp", "v_en": "", "v_zh": ""})
        except (TypeError, ValueError):
            pass
    if vol:
        panels.append({"kind": "kv", "title_en": "Volatility pricing", "title_zh": "波动率定价", "rows": vol})

    return _mk_dialog("options", "Options — full detail", "期权持仓 — 完整明细", panels)


def _deep_ownership(blob: dict) -> dict | None:
    sm = blob.get("smart_money") or {}
    pos = blob.get("positioning") or {}
    ins = pos.get("insider") or {}
    sh = pos.get("short") or {}
    flows = blob.get("fund_flows") or []
    panels: list = []

    hrows = []
    for h in (sm.get("holders") or [])[:15]:
        act = _clean_str(h.get("action"))
        act_en = {"new": "New position", "add": "Adding", "trim": "Trimming", "exit": "Exited", "hold": "Holding"}.get(act, act.title() if act else "—")
        act_zh = {"new": "新建仓", "add": "增持", "trim": "减持", "exit": "清仓", "hold": "持有"}.get(act, act or "—")
        pctb = h.get("pct_portfolio")
        hrows.append([_clean_str(h.get("fund_name") or h.get("fund")),
                      _clean_str(h.get("fund_grade")) or "—",
                      {"en": act_en, "zh": act_zh},
                      _fmt_pct(pctb, 1) if pctb is not None else "—",
                      _fmt_bn(h.get("value_usd")) or "—"])
    if hrows:
        panels.append({"kind": "table", "title_en": "Tracked funds holding it", "title_zh": "跟踪基金持仓",
                       "head": [["Fund", "基金"], ["Grade", "评级"], ["Latest move", "最新动作"], ["% of book", "组合占比"], ["Position", "市值"]],
                       "rows": hrows})

    conc = []
    if sm.get("n_holders") is not None:
        conc.append({"k_en": "Tracked funds in the name", "k_zh": "持有该股的跟踪基金", "v": str(int(sm["n_holders"])), "v_en": "", "v_zh": ""})
    nb, ns = sm.get("n_buying"), sm.get("n_selling")
    if nb is not None and ns is not None:
        cls = "pos" if nb > ns else ("neg" if ns > nb else "")
        conc.append({"k_en": "Buying vs selling", "k_zh": "买入vs卖出", "v": f"{int(nb)} : {int(ns)}", "v_en": "", "v_zh": "", "cls": cls})
    if sm.get("trend"):
        tr = _clean_str(sm.get("trend"))
        tr_en = {"accumulating": "accumulating", "distributing": "distributing", "stable": "stable"}.get(tr, tr)
        tr_zh = {"accumulating": "持续增持", "distributing": "持续减持", "stable": "稳定"}.get(tr, tr)
        conc.append({"k_en": "Quarterly trend", "k_zh": "季度趋势", "v": "", "v_en": tr_en, "v_zh": tr_zh})
    if conc:
        panels.append({"kind": "kv", "title_en": "Fund positioning", "title_zh": "基金持仓概览", "rows": conc})

    other = []
    if ins.get("net_usd_mn") is not None:
        try:
            f = float(ins["net_usd_mn"])
            sign = "-" if f < 0 else "+"
            other.append({"k_en": "Insider net buying (6 months)", "k_zh": "内部人净买入（6个月）",
                          "v": f"{sign}${abs(f):,.1f}M", "v_en": "", "v_zh": "", "cls": "pos" if f > 0 else ("neg" if f < 0 else "")})
        except (TypeError, ValueError):
            pass
    if ins.get("n_buyers") is not None and ins.get("n_sellers") is not None:
        other.append({"k_en": "Insider buyers vs sellers", "k_zh": "内部人买家vs卖家",
                      "v": f"{int(ins['n_buyers'])} : {int(ins['n_sellers'])}", "v_en": "", "v_zh": ""})
    if sh.get("pct_float") is not None:
        other.append({"k_en": "Short interest", "k_zh": "空头占流通盘", "v": _fmt_pct(sh["pct_float"], 1), "v_en": "", "v_zh": ""})
    if sh.get("days_to_cover") is not None:
        other.append({"k_en": "Days to cover", "k_zh": "回补天数", "v": f"{float(sh['days_to_cover']):.1f}", "v_en": "", "v_zh": ""})
    if sh.get("si_change_pct") is not None:
        other.append({"k_en": "Short interest change", "k_zh": "空头变化", "v": _fmt_pct(sh["si_change_pct"], 1, sign=True), "v_en": "", "v_zh": ""})
    if other:
        panels.append({"kind": "kv", "title_en": "Insiders & shorts", "title_zh": "内部人与空头", "rows": other})

    frows = []
    for f in flows[:8]:
        if not isinstance(f, dict):
            continue
        d = _clean_str(f.get("direction"))
        d_en = {"in": "flowing in", "out": "flowing out", "buy": "buying", "sell": "selling"}.get(d, d)
        d_zh = {"in": "流入", "out": "流出", "buy": "买入", "sell": "卖出"}.get(d, d)
        frows.append({"k_en": _clean_str(f.get("fund_name") or f.get("fund")), "k_zh": _clean_str(f.get("fund_name") or f.get("fund")),
                      "v": "", "v_en": d_en, "v_zh": d_zh, "cls": "pos" if d in ("in", "buy") else ("neg" if d in ("out", "sell") else "")})
    if frows:
        panels.append({"kind": "kv", "title_en": "Recent fund flows", "title_zh": "近期基金流向", "rows": frows})

    return _mk_dialog("ownership", "Ownership — full detail", "持仓 — 完整明细", panels)


def _deep_seasonality(monthly: list | None, season_this: str, season_this_zh: str) -> dict | None:
    if not monthly:
        return None
    panels: list = []
    mrows = []
    best = None
    worst = None
    for mi, m in enumerate(monthly):
        wr = m.get("win_rate")
        med = m.get("median_pct")
        n = m.get("n") or 0
        if wr is None:
            continue
        if best is None or wr > best[1]:
            best = (m["month"], wr)
        if worst is None or wr < worst[1]:
            worst = (m["month"], wr)
        mrows.append([{"en": m["month"], "zh": f"{mi + 1}月"}, f"{wr:.0f}%",
                      f"{'+' if (med or 0) > 0 else ''}{med:.1f}%" if med is not None else "—",
                      str(int(n))])
    if mrows:
        panels.append({"kind": "table", "title_en": "Month by month", "title_zh": "逐月统计",
                       "head": [["Month", "月份"], ["Closed higher", "收涨占比"], ["Median move", "中位涨跌"], ["Years", "年数"]],
                       "rows": mrows,
                       "foot_en": "History is a tendency, not a promise — small samples wobble.",
                       "foot_zh": "历史规律只是倾向而非保证 — 样本少时波动大。"})
    cards = []
    if best:
        cards.append({"k_en": "Strongest month", "k_zh": "最强月份", "v": f"{best[0]} · {best[1]:.0f}%", "cls": "pos"})
    if worst:
        cards.append({"k_en": "Weakest month", "k_zh": "最弱月份", "v": f"{worst[0]} · {worst[1]:.0f}%", "cls": "neg"})
    if cards:
        panels.insert(0, {"kind": "cards", "title_en": "", "title_zh": "", "cards": cards})
    if season_this:
        panels.append({"kind": "notes", "title_en": "", "title_zh": "",
                       "lines": [{"en": season_this, "zh": season_this_zh or season_this, "cls": "mut"}]})
    return _mk_dialog("seasonality", "Seasonality — full detail", "季节性 — 完整明细", panels)


def _build_deep(blob: dict | None, per: dict, agg: dict, ticker: str,
                performance: list | None, stats: dict | None,
                monthly: list | None, season_this: str, season_this_zh: str) -> dict | None:
    """Assemble the popup-dashboard dialogs (list — never a dict the template
    would trip over via Jinja attribute lookup)."""
    if not blob:
        return None
    ts_row = (agg.get("tech_screener") or {}).get(ticker)
    dialogs = [d for d in (
        _deep_stats(blob, performance, stats),
        _deep_financials(blob),
        _deep_technicals(blob, ts_row),
        _deep_earnings(blob),
        _deep_options(blob, per.get("gex_v1")),
        _deep_ownership(blob),
        _deep_seasonality(monthly, season_this, season_this_zh),
    ) if d]
    return {"dialogs": dialogs} if dialogs else None


# ---------------------------------------------------------------------------
# Section builders (pure; one per context key)
# ---------------------------------------------------------------------------

def _build_meta(
    ticker: str, name: str, blob: dict | None, stance_en: str,
    freshness: str, stale: bool, generated_utc: str,
) -> dict:
    price = None
    if blob:
        tech = blob.get("tech") or {}
        price = tech.get("price")
    profile = (blob or {}).get("profile") or {}
    sector = _clean_str(profile.get("sector"))
    desc_short = _clean_str(profile.get("description") or "")
    # truncate description to ~40 words
    words = desc_short.split()
    desc_trunc = " ".join(words[:40]) + ("..." if len(words) > 40 else "")

    price_str = f"${price:.2f}" if price else ""
    meta_desc = f"{ticker} ({name}) — {stance_en}."
    if price_str:
        meta_desc += f" Price: {price_str}."
    if sector:
        meta_desc += f" Sector: {sector}."
    meta_desc += " Signals, options positioning, factor profile updated nightly."

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{ticker} — {name}: signals, options & factor profile",
        "datePublished": freshness,
        "dateModified": freshness,
        "author": {"@type": "Organization", "name": "Mastermind"},
        "publisher": {"@type": "Organization", "name": "Mastermind"},
        "about": {"@type": "Corporation", "name": name, "tickerSymbol": ticker},
        "url": f"{CANONICAL_BASE}/stocks/{ticker}.html",
    }
    jsonld_str = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")

    return {
        "ticker": ticker,
        "name": name,
        "canonical": f"{CANONICAL_BASE}/stocks/{ticker}.html",
        "meta_desc": meta_desc,
        "jsonld_str": jsonld_str,
        "freshness": freshness,
        "stale": stale,
        "generated_utc": generated_utc,
    }


def _lvl_float(v: Any) -> float | None:
    """Normalize an engine level that may be a scalar or a {low,high,...} dict."""
    if isinstance(v, dict):
        lo, hi = v.get("low"), v.get("high")
        try:
            if lo is not None and hi is not None:
                return (float(lo) + float(hi)) / 2.0
            return float(lo if lo is not None else hi)
        except (TypeError, ValueError):
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _px(v: float) -> str:
    return f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"


def _bar_close(bar: Any) -> float | None:
    try:
        return float(bar[4]) if len(bar) >= 6 else float(bar[1])
    except (TypeError, ValueError, IndexError):
        return None


def _day_change(bars: list) -> dict | None:
    """Last close vs previous close → hero day-change pill."""
    try:
        if not bars or len(bars) < 2:
            return None
        last, prev = _bar_close(bars[-1]), _bar_close(bars[-2])
        if last is None or prev is None or prev <= 0:
            return None
        diff = last - prev
        pct = diff / prev * 100.0
        sign = "+" if diff >= 0 else "-"
        return {
            "abs": f"{sign}${abs(diff):,.2f}",
            "pct": f"{sign}{abs(pct):.2f}%",
            "pos": diff >= 0,
        }
    except Exception:  # noqa: BLE001 — decorative, never fatal
        return None


def _range52(price: Any, bars: list) -> dict | None:
    """52-week low/high + position of the current price for the hero range bar."""
    try:
        p = _lvl_float(price)
        if not p or not bars:
            return None
        lows: list[float] = []
        highs: list[float] = []
        for bar in bars[-252:]:
            try:
                if len(bar) >= 6:
                    lows.append(float(bar[3])); highs.append(float(bar[2]))
                else:
                    c = float(bar[1]); lows.append(c); highs.append(c)
            except (TypeError, ValueError, IndexError):
                continue
        if len(lows) < 60:
            return None
        lo, hi = min(lows + [p]), max(highs + [p])
        if hi <= lo:
            return None
        pos = max(0.0, min(100.0, (p - lo) / (hi - lo) * 100.0))
        return {"lo": _px(lo), "hi": _px(hi), "pos_pct": round(pos, 1)}
    except Exception:  # noqa: BLE001
        return None


# Plain-word note per ladder row kind (Tier-1 vocabulary, no jargon)
_LADDER_NOTES = {
    "wall_call": ("rallies tend to stall here", "上攻常在此受阻"),
    "wall_put": ("first option support below", "下方期权支撑位"),
    "chase": ("wait for price to come back", "等待价格回落"),
    "buy": ("where patience gets paid", "耐心者的进场区"),
    "stop": ("the engine walks away", "引擎就此离场"),
}
_LADDER_PRICE_NOTES = {
    "pos": ("in a healthy trend", "趋势健康"),
    "warn": ("stretched — be patient", "偏高，耐心等待"),
    "neg": ("downtrend — stand aside", "下行，暂且观望"),
    "neu": ("no strong signal", "暂无明确信号"),
}


def _build_ladder(price: Any, blob: dict | None, walls: dict | None = None,
                  signals: dict | None = None, stance_class: str = "neu") -> dict | None:
    """Trade-levels ladder: the engine's working levels as a vertical list
    sorted by price (structurally collision-free — supersedes the 52-week
    axis rail). ONE source per number: trail stop > entry stop; walls come
    from the same gex artifact the Options section renders."""
    try:
        p = _lvl_float(price)
        if not p:
            return None
        blob = blob or {}
        es = blob.get("entry_signal") or {}
        sig = signals or {}
        gx = walls or {}
        # sanity window: ignore levels wildly away from price (junk data guard)
        lo_ok, hi_ok = p * 0.4, p * 2.5

        def _dist(v: float) -> str:
            d = (v / p - 1.0) * 100.0
            return f"{'+' if d >= 0 else '-'}{abs(d):.1f}%"

        rows: list[dict] = []

        def _row(v: float | None, cls: str, label_en: str, label_zh: str, note_key: str | None) -> None:
            if v is None or not (lo_ok < v < hi_ok):
                return
            note_en, note_zh = _LADDER_NOTES.get(note_key or "", ("", ""))
            rows.append({
                "kind": "row", "sort": v, "price": _px(v), "cls": cls,
                "label_en": label_en, "label_zh": label_zh,
                "note_en": note_en, "note_zh": note_zh, "dist": _dist(v),
            })

        _row(_lvl_float(gx.get("call_wall")), "wall", "Call wall", "看涨期权墙", "wall_call")
        chase = _lvl_float(es.get("chase_above") or es.get("dont_chase_line"))
        _row(chase, "chase", "Don't chase above", "勿追高线", "chase")
        _row(_lvl_float(gx.get("put_wall")), "wall", "Put wall", "看跌期权墙", "wall_put")
        # ONE stop: the trailing stop the hero invalidation line quotes wins.
        # A stop at/above the current price is stale (already triggered) — a
        # misleading row, so it is dropped rather than displayed.
        stop = _lvl_float(sig.get("trail_stop")) or _lvl_float(es.get("stop"))
        if stop is not None and stop >= p:
            stop = None
        _row(stop, "stop", "Exit if broken", "跌破离场", "stop")

        # Buy zone: dict → band item; scalar → plain row
        band_item = None
        bz = es.get("buy_zone")
        if isinstance(bz, dict):
            b_lo, b_hi = _lvl_float(bz.get("low")), _lvl_float(bz.get("high"))
            if b_lo and b_hi and b_lo < b_hi and lo_ok < b_hi < hi_ok:
                band_item = {"kind": "band", "sort": b_hi,
                             "price": f"{_px(b_lo)} – {_px(b_hi)}"}
        elif (bzv := _lvl_float(bz)) is not None:
            _row(bzv, "buy", "Buy zone", "买入区", "buy")

        if not rows and not band_item:
            return None

        note_en, note_zh = _LADDER_PRICE_NOTES.get(stance_class, _LADDER_PRICE_NOTES["neu"])
        rows.append({
            "kind": "row", "sort": p, "price": _px(p), "cls": "now",
            "label_en": "Price now", "label_zh": "当前价格",
            "note_en": note_en, "note_zh": note_zh, "dist": "",
        })
        items = rows + ([band_item] if band_item else [])
        items.sort(key=lambda r: r["sort"], reverse=True)
        return {
            "levels": items,
            "headline_en": _clean_str(es.get("headline") or ""),
            "headline_zh": _clean_str(es.get("headline_zh") or ""),
        }
    except Exception:  # noqa: BLE001 — decorative module, never fatal
        return None


def _build_hero(
    ticker: str, name: str, blob: dict | None,
    stance_en: str, stance_zh: str, stance_key: str,
    inv_en: str, inv_zh: str,
    factor_betas: dict,
) -> dict:
    if not blob:
        return {
            "stance_en": stance_en, "stance_zh": stance_zh,
            "stance_key": stance_key, "stance_class": _STANCE_CLASS.get(stance_key, "neu"),
            "inv_en": inv_en, "inv_zh": inv_zh,
            "desc_en": "", "desc_zh": "",
        }

    profile = blob.get("profile") or {}
    tech = blob.get("tech") or {}
    conv = blob.get("conviction") or {}
    ladder = blob.get("ladder") or {}

    price = tech.get("price")
    chg_pct: str = ""
    bars = []  # filled in run() via ohlc
    desc_en = _clean_str(profile.get("description") or "")
    words = desc_en.split()
    desc_en = " ".join(words[:40]) + ("..." if len(words) > 40 else "")
    desc_zh = _trunc_words(_clean_str(profile.get("description_zh") or ""), 120)

    sector = _clean_str(profile.get("sector"))
    mktcap_tier = profile.get("mktcap_tier") or {}
    mktcap_label_en = _clean_str(mktcap_tier.get("label") or "")
    mktcap_label_zh = _clean_str(mktcap_tier.get("label_zh") or mktcap_label_en)

    archetype = profile.get("archetype") or {}
    arch_label_en = _clean_str(archetype.get("label") or "")
    arch_label_zh = _clean_str(archetype.get("label_zh") or arch_label_en)

    return {
        "stance_en": stance_en,
        "stance_zh": stance_zh,
        "stance_key": stance_key,
        "stance_class": _STANCE_CLASS.get(stance_key, "neu"),
        "inv_en": inv_en,
        "inv_zh": inv_zh,
        "desc_en": desc_en,
        "desc_zh": desc_zh,
        "sector": _sector_display(sector),
        "arch_label_en": arch_label_en,
        "arch_label_zh": arch_label_zh,
        "mktcap_label_en": mktcap_label_en,
        "mktcap_label_zh": mktcap_label_zh,
        "price": f"{price:.2f}" if price else "",
    }


def _build_stats(ticker: str, blob: dict | None, factor_betas: dict) -> dict | None:
    if not blob:
        return None
    tech = blob.get("tech") or {}
    profile = blob.get("profile") or {}
    analyst = blob.get("analyst") or {}
    earnings = blob.get("earnings") or {}
    positioning = blob.get("positioning") or {}
    short_pos = positioning.get("short") or {}
    fin = blob.get("financials") or {}
    fin_raw = fin.get("raw") or {}

    price = tech.get("price")
    sma50 = tech.get("sma50")
    sma200 = tech.get("sma200")
    off_52w_high_pct = tech.get("off_52w_high_pct")
    rel_vol = tech.get("rel_volume")
    hv_pctile = tech.get("hv_pctile")
    rsi = tech.get("rsi14")

    mktcap_bn = profile.get("mktcap_bn")
    mktcap_str = ""
    if mktcap_bn is not None:
        try:
            f = float(mktcap_bn)
            mktcap_str = f"${f:.0f}B" if f >= 1 else f"${f*1000:.0f}M"
        except (TypeError, ValueError):
            pass

    # 52w range
    range_52w_en = ""
    if off_52w_high_pct is not None:
        try:
            pct = float(off_52w_high_pct)
            range_52w_en = f"{abs(pct):.1f}% below 52-week high"
        except (TypeError, ValueError):
            pass

    # EPS
    shares = fin_raw.get("shares")
    ni = fin_raw.get("ni")
    eps_str = ""
    if ni is not None and shares and float(shares) > 0:
        try:
            eps = float(ni) / float(shares)
            eps_str = f"${eps:.2f}"
        except (TypeError, ValueError):
            pass

    # Trailing P/E from valuation block
    val = blob.get("valuation") or {}
    tpe = (val.get("trailing_pe") or {}).get("v")
    tpe_med = (val.get("trailing_pe") or {}).get("med")
    tpe_str = f"{tpe:.1f}x" if tpe else ""
    tpe_med_str = f"{tpe_med:.1f}x sector median" if tpe_med else ""

    # Forward P/E
    fpe = analyst.get("forward_pe")
    fpe_str = f"{fpe:.1f}x" if fpe else ""

    # Dividend yield
    div_yield = analyst.get("div_yield")
    div_str = f"{div_yield:.2f}%" if div_yield else ""

    # Beta
    beta_row = factor_betas.get(ticker) or {}
    mkt_beta = beta_row.get("mkt")
    beta_str = f"{mkt_beta:.2f}" if mkt_beta is not None else ""
    beta_en = f"Moves about {mkt_beta:.1f}x the market" if mkt_beta is not None else ""
    beta_zh = f"波动幅度约为市场的 {mkt_beta:.1f} 倍" if mkt_beta is not None else ""

    # Next earnings
    next_date = _clean_str(earnings.get("next_date"))
    days_to_next = earnings.get("days_to_next")
    if days_to_next is None and next_date:
        try:
            nd = date.fromisoformat(next_date)
            days_to_next = (nd - date.today()).days
        except (ValueError, TypeError):
            pass
    earnings_str = f"{next_date} ({days_to_next}d)" if next_date and days_to_next is not None else next_date

    # Short interest
    short_pct = short_pos.get("pct_float")
    short_str = f"{short_pct:.1f}% of float" if short_pct else ""

    # Relative volume plain word
    rv_en, rv_zh = _rel_vol_word(rel_vol)

    return {
        "price": f"{price:.2f}" if price else "",
        "range_52w_en": range_52w_en,
        "range_52w_zh": f"低于52周高点 {abs(float(off_52w_high_pct)):.1f}%" if off_52w_high_pct else "",
        "volume_en": rv_en,
        "volume_zh": rv_zh,
        "mktcap": mktcap_str,
        "trailing_pe": tpe_str,
        "trailing_pe_med": tpe_med_str,
        "forward_pe": fpe_str,
        "eps": eps_str,
        "div_yield": div_str,
        "beta": beta_str,
        "beta_en": beta_en,
        "beta_zh": beta_zh,
        "next_earnings": earnings_str,
        "short_pct_float": short_str,
        "hv_pctile": f"{hv_pctile:.0f}th pctile" if hv_pctile else "",
        "hv_pctile_num": f"{hv_pctile:.0f}" if hv_pctile else "",
        "rsi": f"{rsi:.0f}" if rsi else "",
        "rsi_zone_en": _rsi_zone(rsi)[0],
        "rsi_zone_zh": _rsi_zone(rsi)[1],
    }


def _build_gauges(ticker: str, blob: dict | None, factor_betas: dict) -> dict | None:
    if not blob:
        return None

    val = blob.get("valuation") or {}
    fin = blob.get("financials") or {}
    my = fin.get("multiyear") or {}
    pio = my.get("piotroski") or {}
    alt = my.get("altman") or {}
    analyst = blob.get("analyst") or {}

    # Valuation gauge: mean of available cheap pctiles
    cheap_pcts = []
    for k in ("trailing_pe", "price_to_book", "price_to_sales", "fcf_yield_true", "ev_to_ebitda"):
        mv = val.get(k)
        if isinstance(mv, dict) and mv.get("cheap") is not None:
            try:
                cheap_pcts.append(float(mv["cheap"]))
            except (TypeError, ValueError):
                pass
    val_gauge: dict | None = None
    if cheap_pcts:
        avg_cheap = sum(cheap_pcts) / len(cheap_pcts)
        if avg_cheap >= 55:
            vd_en, vd_zh = "Looks cheap vs sector", "相对行业偏便宜"
        elif avg_cheap <= 30:
            vd_en, vd_zh = "Expensive vs sector", "相对行业偏贵"
        else:
            vd_en, vd_zh = "Roughly fair vs sector", "相对行业估值合理"
        val_gauge = {
            "pct": round(avg_cheap, 0),
            "verdict_en": vd_en,
            "verdict_zh": vd_zh,
            "sub_en": f"Cheaper than {avg_cheap:.0f}% of its sector on blended multiples",
            "sub_zh": f"综合估值倍数低于行业内 {avg_cheap:.0f}% 的公司",
        }

    # Beta gauge
    beta_row = factor_betas.get(ticker) or {}
    mkt_beta = beta_row.get("mkt")
    beta_gauge: dict | None = None
    if mkt_beta is not None:
        if mkt_beta < 0:
            _beta_label_en = "Has tended to move opposite the market (factor-adjusted)"
            _beta_label_zh = "经因子调整后常与大盘反向波动"
            _beta_gauge_pct = 0
        elif mkt_beta < 0.2:
            _beta_label_en = f"Moves about {mkt_beta:.1f}× the market"
            _beta_label_zh = f"波动幅度约为市场的 {mkt_beta:.1f} 倍"
            _beta_gauge_pct = 0  # clamp visual only
        else:
            _beta_label_en = f"Moves about {mkt_beta:.1f}× the market"
            _beta_label_zh = f"波动幅度约为市场的 {mkt_beta:.1f} 倍"
            _beta_gauge_pct = None  # template computes normally
        beta_gauge = {
            "beta": f"{mkt_beta:.2f}",
            "label_en": _beta_label_en,
            "label_zh": _beta_label_zh,
            "gauge_pct_override": _beta_gauge_pct,
        }

    # Health gauge
    health_gauge: dict | None = None
    pio_score = pio.get("score")
    pio_of = pio.get("of")
    alt_zone = _clean_str(alt.get("zone") or "")
    alt_z = alt.get("z")
    if pio_score is not None:
        if pio_score >= 7:
            h_en, h_zh = "Strong financial health", "财务健康状况良好"
        elif pio_score >= 5:
            h_en, h_zh = "Adequate financial health", "财务健康状况一般"
        else:
            h_en, h_zh = "Weak financial health", "财务健康状况偏弱"
        health_gauge = {
            "piotroski": f"{pio_score}/{pio_of}" if pio_of else str(pio_score),
            "altman_zone": alt_zone,
            "altman_z": f"{alt_z:.1f}" if alt_z else "",
            "verdict_en": h_en,
            "verdict_zh": h_zh,
        }

    # Dividend card
    div_card: dict | None = None
    div_yield = analyst.get("div_yield")
    if div_yield:
        div_card = {
            "yield_str": f"{div_yield:.2f}%",
            "verdict_en": f"Pays a dividend ({div_yield:.2f}% yield)",
            "verdict_zh": f"有分红（收益率 {div_yield:.2f}%）",
        }

    return {
        "valuation": val_gauge,
        "beta": beta_gauge,
        "health": health_gauge,
        "dividend": div_card,
    }


def _build_performance(
    ticker: str, trailing_returns: dict,
) -> list | None:
    """Build performance rows from precomputed trailing returns."""
    if not trailing_returns:
        return None

    period_labels: dict[str, tuple[str, str]] = {
        "1w":  ("1 Week", "近1周"),
        "1m":  ("1 Month", "近1月"),
        "3m":  ("3 Months", "近3月"),
        "6m":  ("6 Months", "近6月"),
        "YTD": ("Year to date", "年初至今"),
        "1y":  ("1 Year", "近1年"),
        "3y":  ("3 Years", "近3年"),
        "5y":  ("5 Years", "近5年"),
    }

    rows = []
    for period in ("1w", "1m", "3m", "6m", "YTD", "1y", "3y", "5y"):
        rec = trailing_returns.get(period)
        if not rec:
            continue
        t_ret = rec.get("ticker")
        s_ret = rec.get("spy")
        if t_ret is None:
            continue
        label_en, label_zh = period_labels[period]

        if s_ret is not None:
            diff = t_ret - s_ret
            if diff > 1:
                v_en = f"Beat the index by {diff:.1f} points"
                v_zh = f"跑赢指数 {diff:.1f} 个百分点"
            elif diff < -1:
                v_en = f"Lagged the index by {abs(diff):.1f} points"
                v_zh = f"落后指数 {abs(diff):.1f} 个百分点"
            else:
                v_en = "In line with the index"
                v_zh = "与指数基本持平"
        else:
            v_en = ""
            v_zh = ""

        rows.append({
            "label_en": label_en,
            "label_zh": label_zh,
            "ticker_ret": f"{'+' if t_ret >= 0 else ''}{t_ret:.1f}%",
            "spy_ret": f"{'+' if s_ret >= 0 else ''}{s_ret:.1f}%" if s_ret is not None else "",
            "verdict_en": v_en,
            "verdict_zh": v_zh,
            "positive": t_ret >= 0,
        })
    return rows or None


def _build_financials(blob: dict | None) -> dict | None:
    if not blob:
        return None
    fin = blob.get("financials") or {}
    my = fin.get("multiyear") or {}
    fin_raw = fin.get("raw") or {}
    aq = blob.get("accounting_quality") or {}
    lr = blob.get("leverage_ratios") or {}
    ca = blob.get("capital_allocation") or {}

    years = my.get("years") or []
    rev = my.get("revenue") or []
    ni_arr = my.get("eps") or []  # per-share
    fcf = my.get("fcf") or []
    net_margin = my.get("net_margin") or []
    gross_margin = my.get("gross_margin") or []
    rev_cagr = my.get("rev_cagr")
    eps_cagr = my.get("eps_cagr")

    # Piotroski + altman
    pio = my.get("piotroski") or {}
    alt = my.get("altman") or {}

    margins = {
        "gross_margin": fin.get("gross_margin"),
        "net_margin": fin.get("net_margin"),
        "fcf_margin": fin.get("fcf_margin"),
        "op_margin": fin.get("op_margin"),
    }

    # Leverage
    lev_rows = []
    for k, label_en, label_zh in [
        ("net_debt_to_ebitda", "Net debt / EBITDA", "净债务/EBITDA"),
        ("current_ratio",      "Current ratio",    "流动比率"),
    ]:
        v = lr.get(k)
        if v is not None:
            lev_rows.append({"label_en": label_en, "label_zh": label_zh, "value": f"{v:.2f}"})

    # Capital allocation
    repurch = ca.get("repurch_ttm")
    sbc = ca.get("sbc_ttm")
    shares_yoy = ca.get("shares_yoy_change_pct")
    bby = ca.get("buyback_yield")
    cap_rows = []
    if repurch is not None:
        cap_rows.append({
            "label_en": "Buybacks (TTM)", "label_zh": "回购（TTM）",
            "value": _humanize_number(repurch),
        })
    if sbc is not None:
        cap_rows.append({
            "label_en": "Stock-based comp", "label_zh": "股权薪酬",
            "value": _humanize_number(sbc),
        })
    if shares_yoy is not None:
        cap_rows.append({
            "label_en": "Share count change (1y)", "label_zh": "股数变化（1年）",
            "value": f"{'+' if float(shares_yoy) >= 0 else ''}{shares_yoy:.1f}%",
        })

    # Accounting quality headline
    aq_headline_en = _clean_str(aq.get("headline") or "")
    aq_headline_zh = _clean_str(aq.get("headline_zh") or "")

    # Guard: return None if there's nothing substantive to show
    _has_years = bool(years)
    _has_margins = any(v is not None for v in margins.values())
    _has_returns = fin.get("roe") is not None or fin.get("roa") is not None
    _has_leverage = bool(lev_rows)
    _has_cap = bool(cap_rows)
    if not _has_years and not _has_margins and not _has_returns and not _has_leverage and not _has_cap:
        return None

    return {
        "years": years,
        "revenue": [_humanize_number(v) for v in rev],
        "eps": [f"{float(v):.2f}" if v is not None else "" for v in ni_arr],
        "fcf": [_humanize_number(v) for v in fcf],
        "net_margin": [f"{float(v):.1f}%" if v is not None else "" for v in net_margin],
        "gross_margin": [f"{float(v):.1f}%" if v is not None else "" for v in gross_margin],
        "rev_cagr": f"{rev_cagr:.1f}%" if rev_cagr is not None else "",
        "eps_cagr": f"{eps_cagr:.1f}%" if eps_cagr is not None else "",
        "margins": margins,
        "piotroski": pio.get("score"),
        "piotroski_of": pio.get("of"),
        "altman_zone": _clean_str(alt.get("zone") or ""),
        "altman_z": alt.get("z"),
        "leverage_rows": lev_rows,
        "cap_rows": cap_rows,
        "aq_headline_en": aq_headline_en,
        "aq_headline_zh": aq_headline_zh,
        "roe": fin.get("roe"),
        "roa": fin.get("roa"),
    }


def _build_valuation(blob: dict | None) -> list | None:
    if not blob:
        return None
    val = blob.get("valuation") or {}
    rows = []
    for key, (label_en, label_zh) in _VAL_LABELS.items():
        if key == "forward_pe":
            # forward_pe is a scalar in valuation, not a dict
            fpe = val.get("forward_pe")
            if fpe is not None:
                rows.append({
                    "label_en": label_en, "label_zh": label_zh,
                    "value": f"{fpe:.1f}x",
                    "sector_med": "",
                    "cheap_pct": "",
                    "cheap": None,
                })
            continue
        mv = val.get(key)
        if not isinstance(mv, dict):
            continue
        v = mv.get("v")
        med = mv.get("med")
        cheap = mv.get("cheap")
        if v is None:
            continue
        rows.append({
            "label_en": label_en,
            "label_zh": label_zh,
            "value": f"{v:.2f}x" if "yield" not in key else f"{v:.2f}%",
            "sector_med": f"{med:.2f}" if med is not None else "",
            "cheap_pct": f"{cheap:.0f}" if cheap is not None else "",
            "cheap": cheap,
        })
    return rows or None


def _build_earnings(blob: dict | None) -> dict | None:
    if not blob:
        return None
    earns = blob.get("earnings") or {}
    revs = blob.get("revisions") or {}
    es = blob.get("expectation_state") or {}

    next_date = _clean_str(earns.get("next_date"))
    days_to = earns.get("days_to_next")
    if days_to is None and next_date:
        try:
            nd = date.fromisoformat(next_date)
            days_to = (nd - date.today()).days
        except (ValueError, TypeError):
            pass

    summary = earns.get("summary") or {}
    beats = summary.get("beats")
    total = summary.get("total")
    avg_surp = summary.get("avg_surprise")
    streak = summary.get("streak", 0)

    sue_streak = es.get("sue_streak", 0)
    pead_drift = es.get("pead_drift_20d")

    # plain beat description
    sue_en, sue_zh = "", ""
    if beats is not None and total:
        if beats == total and streak and streak >= 2:
            sue_en = f"Beat expectations {streak} quarters in a row"
            sue_zh = f"连续 {streak} 季度超预期"
        elif beats > total // 2:
            sue_en = f"Beat in {beats} of last {total} quarters"
            sue_zh = f"近 {total} 季中 {beats} 季超预期"
        else:
            sue_en = f"Mixed — beat {beats} of last {total} quarters"
            sue_zh = f"表现不稳 — 近 {total} 季中 {beats} 季超预期"

    # revision direction
    rev_breadth = revs.get("breadth")
    n_analysts = revs.get("n_analysts")
    rev_en, rev_zh = "", ""
    if rev_breadth is not None:
        if rev_breadth >= 0.6:
            rev_en = f"Estimates being raised — {int(n_analysts)} analysts" if n_analysts else "Estimates being raised"
            rev_zh = f"预期上调 — {int(n_analysts)} 位分析师" if n_analysts else "预期上调"
        elif rev_breadth <= 0.4:
            rev_en = "Estimates being cut"
            rev_zh = "预期下调"
        else:
            rev_en = "Estimates roughly stable"
            rev_zh = "预期基本稳定"

    # pead drift
    pead_en, pead_zh = "", ""
    if pead_drift is not None:
        try:
            pf = float(pead_drift) * 100
            if abs(pf) > 2:
                if pf > 0:
                    pead_en = f"Post-earnings drift: +{pf:.1f}% (20d)"
                    pead_zh = f"财报后漂移：+{pf:.1f}%（20日）"
                else:
                    pead_en = f"Post-earnings drift: {pf:.1f}% (20d)"
                    pead_zh = f"财报后漂移：{pf:.1f}%（20日）"
        except (TypeError, ValueError):
            pass

    surprises = (earns.get("surprises") or [])[:4]

    return {
        "next_date": next_date,
        "days_to_next": days_to,
        "last_date": _clean_str(earns.get("last_date") or ""),
        "eps_forecast": earns.get("eps_forecast"),
        "sue_en": sue_en,
        "sue_zh": sue_zh,
        "rev_en": rev_en,
        "rev_zh": rev_zh,
        "pead_en": pead_en,
        "pead_zh": pead_zh,
        "surprises": surprises,
        "avg_surprise_pct": f"{avg_surp:.1f}%" if avg_surp else "",
    }


def _build_technicals(ticker: str, blob: dict | None, tech_screener: dict) -> dict | None:
    if not blob:
        return None
    tech = blob.get("tech") or {}
    vs = blob.get("vol_squeeze") or {}
    es = blob.get("entry_signal") or {}

    rsi = tech.get("rsi14")
    adx = tech.get("adx14")
    hv_pctile = tech.get("hv_pctile")
    above50 = bool(tech.get("above50"))
    above200 = bool(tech.get("above200"))
    pct_vs_50 = tech.get("pct_vs_50dma")
    pct_vs_200 = tech.get("pct_vs_200dma")

    # price vs MA deltas — language-neutral values (the row label carries context)
    ma50_en = f"{'+' if pct_vs_50 >= 0 else ''}{pct_vs_50:.1f}%" if pct_vs_50 is not None else ""
    ma200_en = f"{'+' if pct_vs_200 >= 0 else ''}{pct_vs_200:.1f}%" if pct_vs_200 is not None else ""

    # vol squeeze
    sq_state = _clean_str(vs.get("state") or "")
    sq_en, sq_zh = "", ""
    if sq_state == "on":
        sq_en = "Volatility squeeze — compressed range, breakout possible"
        sq_zh = "波动压缩中，可能出现突破"
    elif sq_state == "off":
        sq_en = "Squeeze just fired — momentum released"
        sq_zh = "压缩刚刚释放，动能已出"

    # entry signal levels (framed as engine levels, not advice)
    # buy_zone may be a dict {low, high, pct_from_spot} or a scalar float
    def _extract_level(v: Any) -> float | None:
        if v is None:
            return None
        if isinstance(v, dict):
            # prefer midpoint of low/high; fallback to first non-None value
            lo = v.get("low")
            hi = v.get("high")
            if lo is not None and hi is not None:
                try:
                    return (float(lo) + float(hi)) / 2
                except (TypeError, ValueError):
                    pass
            for k in ("low", "high", "value", "price"):
                val = v.get(k)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        pass
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    buy_zone = _extract_level(es.get("buy_zone"))
    chase_above = _extract_level(es.get("chase_above") or es.get("dont_chase_line"))
    stop = _extract_level(es.get("stop"))
    entry_headline_en = _clean_str(es.get("headline") or "")
    entry_headline_zh = _clean_str(es.get("headline_zh") or "")

    # tech screener active signals (top 5 by recency)
    ts_row = tech_screener.get(ticker) or {}
    ts_signals = ts_row.get("signals") or []
    active_signals = [
        s["display_en"] for s in ts_signals
        if s.get("state") == 1 and s.get("display_en")
    ][:5]

    return {
        "rsi": f"{rsi:.0f}" if rsi else "",
        "rsi_zone_en": _rsi_zone(rsi)[0],
        "rsi_zone_zh": _rsi_zone(rsi)[1],
        "adx": f"{adx:.0f}" if adx else "",
        "adx_word_en": _adx_word(adx)[0],
        "adx_word_zh": _adx_word(adx)[1],
        "hv_pctile": f"{hv_pctile:.0f}th" if hv_pctile else "",
        "hv_pctile_num": f"{hv_pctile:.0f}" if hv_pctile else "",
        "above50": above50,
        "above200": above200,
        "ma50_en": ma50_en,
        "ma200_en": ma200_en,
        "squeeze_en": sq_en,
        "squeeze_zh": sq_zh,
        "buy_zone": f"${buy_zone:.2f}" if buy_zone else "",
        "chase_above": f"${chase_above:.2f}" if chase_above else "",
        "stop": f"${stop:.2f}" if stop else "",
        "entry_headline_en": entry_headline_en,
        "entry_headline_zh": entry_headline_zh,
        "active_signals": active_signals,
    }


def _build_options(blob: dict | None, gex_v1: dict | None, flow: dict | None) -> dict | None:
    """Build options section from blob.gex (primary) + v1 gex artifact (supplement)."""
    gex_blob = (blob or {}).get("gex") or {}
    gex_v1_sum = (gex_v1 or {}).get("summary") or {}

    # regime from blob.gex.regime
    regime_raw = _clean_str(gex_blob.get("regime") or gex_v1_sum.get("regime") or "")
    regime_key = regime_raw.lower()
    regime_en = _REGIME_PLAIN_EN.get(regime_key, "")
    regime_zh = _REGIME_PLAIN_ZH.get(regime_key, "")

    # Expected move from v1 gex artifact (richer)
    em = (gex_v1 or {}).get("expected_move") or {}
    em_daily = _safe_float(em.get("daily_pct"), 2)
    em_weekly = _safe_float(em.get("weekly_pct"), 2)

    # Walls from blob first, v1 second
    call_wall = gex_blob.get("call_wall") or gex_v1_sum.get("call_wall")
    put_wall = gex_blob.get("put_wall") or gex_v1_sum.get("put_wall")
    flip = gex_blob.get("gamma_flip") or gex_v1_sum.get("gamma_flip")
    iv30 = gex_blob.get("iv30") or gex_v1_sum.get("iv30")

    # IV rank from v1
    iv_rank_rec = (gex_v1_sum.get("iv_rank") or {})
    iv_rank_pct = _safe_float(iv_rank_rec.get("rank_pct"), 0) if isinstance(iv_rank_rec, dict) else ""

    # Skew
    skew = gex_v1_sum.get("skew") or {}
    skew_tone = _clean_str(skew.get("tone") if isinstance(skew, dict) else "")
    rr_25d = gex_blob.get("rr_25d")

    # PC ratio
    pc_ratio_v1 = (gex_v1 or {}).get("put_call_oi_ratio")
    max_pain_v1 = (gex_v1 or {}).get("max_pain")

    # Flow verdict
    flow_en, flow_zh, flow_tone = "", "", ""
    if flow and flow.get("verdict"):
        verdict = flow.get("verdict") or {}
        flow_en = _clean_str(verdict.get("en"))
        flow_zh = _clean_str(verdict.get("zh"))
        flow_tone = _clean_str(verdict.get("tone"))

    if not regime_en and not flow_en:
        return None

    return {
        "regime_en": regime_en,
        "regime_zh": regime_zh,
        "em_daily_pct": em_daily,
        "em_weekly_pct": em_weekly,
        "call_wall": _safe_float(call_wall, 0),
        "put_wall": _safe_float(put_wall, 0),
        "gamma_flip": _safe_float(flip, 0),
        "iv30": _safe_float(iv30, 0),
        "iv_rank_pct": iv_rank_pct,
        "skew_tone": skew_tone,
        "rr_25d": f"{rr_25d:.1f}%" if rr_25d is not None else "",
        "pc_ratio": _safe_float(pc_ratio_v1, 2),
        "max_pain": _safe_float(max_pain_v1, 0),
        "flow_en": flow_en,
        "flow_zh": flow_zh,
        "flow_tone": flow_tone,
    }


def _build_why_moving(
    ticker: str, blob: dict | None,
    news_rec: dict | None, intel: dict | None,
) -> list | None:
    """§7.4 structured checklist of active drivers."""
    if not blob:
        return None
    rows = []

    # News
    n_recent = 0
    sentiment_lean = ""
    if news_rec:
        headlines = news_rec.get("top") or []
        n_recent = len(headlines)
        sentiments = [h.get("sentiment", "") for h in headlines if h.get("sentiment")]
        pos = sum(1 for s in sentiments if s in ("positive", "bullish"))
        neg = sum(1 for s in sentiments if s in ("negative", "bearish"))
        if pos > neg:
            sentiment_lean = "positive lean"
        elif neg > pos:
            sentiment_lean = "negative lean"
        else:
            sentiment_lean = "mixed"
    if n_recent > 0:
        _lean_zh = {"positive lean": "偏正面", "negative lean": "偏负面", "mixed": "多空参半"}.get(sentiment_lean, sentiment_lean)
        rows.append({
            "category_en": "News", "category_zh": "新闻",
            "state": "active",
            "line_en": f"{n_recent} recent stories — {sentiment_lean}",
            "line_zh": f"{n_recent} 篇最新报道，{_lean_zh}",
        })

    # Sector
    sp = blob.get("sector_pulse") or {}
    if sp.get("heat") is not None:
        heat = sp.get("heat")
        label = _clean_str(sp.get("label") or "")
        rank = sp.get("rank")
        n = sp.get("n_themes")
        theme_name = _clean_str(sp.get("theme_name") or "")
        theme_name_zh = _clean_str(sp.get("theme_name_zh") or theme_name)
        # heat may be a float 0-1 or a string label ("hot","heating","cooling","cold")
        try:
            state = "active" if heat and float(heat) >= 0.5 else "quiet"
        except (TypeError, ValueError):
            state = "active" if heat in ("hot", "heating", "rising") else "quiet"
        if theme_name and rank and n:
            line_en = f"{theme_name} theme — #{rank} of {n} themes"
            line_zh = f"「{theme_name_zh}」主题 — {n} 个主题中第 {rank} 位"
        else:
            line_en = f"Sector heat: {heat}"
            line_zh = f"板块热度：{heat}"
        rows.append({
            "category_en": "Sector / Theme", "category_zh": "行业/主题",
            "state": state,
            "line_en": line_en,
            "line_zh": line_zh,
        })

    # Macro
    ms = blob.get("macro_sensitivity") or {}
    hw = ms.get("headline") or {}
    line_en_macro = _clean_str(hw.get("en") if isinstance(hw, dict) else hw)
    line_zh_macro = _clean_str(hw.get("zh")) if isinstance(hw, dict) else ""
    if not line_zh_macro:
        line_zh_macro = line_en_macro
    if line_en_macro:
        rows.append({
            "category_en": "Macro", "category_zh": "宏观",
            "state": "active",
            "line_en": line_en_macro,
            "line_zh": line_zh_macro,
        })

    # Positioning
    pos_blob = blob.get("positioning") or {}
    short = pos_blob.get("short") or {}
    si_chg = short.get("si_change_pct")
    insider = pos_blob.get("insider") or {}
    cluster = insider.get("cluster")
    state = "quiet"
    line_en = "Quiet — no confirmed driver"
    line_zh = "平静 — 无明确驱动"
    if si_chg and abs(float(si_chg)) >= 10:
        state = "active"
        line_en = f"Short interest changed {si_chg:+.1f}%"
        line_zh = f"空头仓位变动 {float(si_chg):+.1f}%"
    elif cluster:
        state = "active"
        line_en = "Insider cluster activity"
        line_zh = "内部人集中交易"
    rows.append({
        "category_en": "Positioning", "category_zh": "持仓",
        "state": state,
        "line_en": line_en,
        "line_zh": line_zh,
    })

    # Technical
    tech = blob.get("tech") or {}
    alerts_obj = blob.get("alerts") or {}
    timeline = alerts_obj.get("timeline") or []
    recent_alerts_en = []
    recent_alerts_zh = []
    for day_obj in timeline[:3]:  # check 3 most recent days
        for ev in (day_obj.get("events") or []):
            h_en = _clean_str(ev.get("headline") or "")
            h_zh = _clean_str(ev.get("headline_zh") or "")
            if h_en:
                recent_alerts_en.append(h_en)
                recent_alerts_zh.append(h_zh if h_zh else h_en)
    vs = blob.get("vol_squeeze") or {}
    sq_state = _clean_str(vs.get("state") or "")
    tech_active = bool(recent_alerts_en) or sq_state in ("on", "off")
    if recent_alerts_en:
        tech_line_en = recent_alerts_en[0]
        tech_line_zh = recent_alerts_zh[0]
    elif sq_state == "on":
        tech_line_en = "Volatility squeeze active"
        tech_line_zh = "波动率挤压中"
    else:
        tech_line_en = "Quiet"
        tech_line_zh = "平静"
    rows.append({
        "category_en": "Technical", "category_zh": "技术面",
        "state": "active" if tech_active else "quiet",
        "line_en": tech_line_en,
        "line_zh": tech_line_zh,
    })

    return rows or None


def _build_ownership(ticker: str, blob: dict | None, alt_agg: dict | None) -> dict | None:
    if not blob:
        return None
    sm = blob.get("smart_money") or {}
    holders = sm.get("holders") or []
    hhi = sm.get("ownership_hhi")
    trend = _clean_str(sm.get("trend") or "")
    n_buying = sm.get("n_buying")
    n_selling = sm.get("n_selling")

    pos_blob = blob.get("positioning") or {}
    insider = pos_blob.get("insider") or {}
    net_usd = insider.get("net_usd_mn")
    n_b = insider.get("n_buyers", 0)
    n_s = insider.get("n_sellers", 0)
    insider_en = ""
    insider_zh = ""
    if net_usd is not None:
        _net_abs = abs(float(net_usd))
        _net_sign = "+" if net_usd >= 0 else "-"
        insider_en = f"{_net_sign}${_net_abs:.1f}M net ({n_b} buyers, {n_s} sellers)"
        insider_zh = f"{_net_sign}${_net_abs:.1f}M 净值（{n_b} 买家，{n_s} 卖家）"

    holder_rows = []
    for h in holders[:8]:
        action = _clean_str(h.get("action") or "")
        holder_rows.append({
            "fund_name": _clean_str(h.get("fund_name") or ""),
            "fund_grade": _clean_str(h.get("fund_grade") or ""),
            "action_en": _SM_ACTION_EN.get(action, action),
            "action_zh": _SM_ACTION_ZH.get(action, action),
            "shares_pct": f"{h.get('pct_portfolio', 0):.1f}%" if h.get("pct_portfolio") is not None else "",
            "period_end": _clean_str(h.get("period_end") or ""),
        })

    if not holder_rows and not insider_en:
        return None

    hhi_en = ""
    if hhi is not None:
        try:
            hf = float(hhi)
            if hf >= 0.15:
                hhi_en = "Concentrated ownership"
            else:
                hhi_en = "Dispersed ownership"
        except (TypeError, ValueError):
            pass

    return {
        "holders": holder_rows,
        "hhi_en": hhi_en,
        "hhi_zh": "集中持仓" if "Concentrated" in hhi_en else ("分散持仓" if hhi_en else ""),
        "insider_en": insider_en,
        "insider_zh": insider_zh,
        "trend_en": trend,
    }


def _build_peers(
    ticker: str, sector: str,
    factors_map: dict, baskets_map: dict,
    factors_blob: dict | None,
    self_cap_hint: float | None = None,
) -> list | None:
    """Build peers from same-sector tickers in the factors.json table
    (has name/sector/mktcap_bn). Sort by log-cap proximity.
    """
    if not sector or not factors_map:
        return None

    # Get self mktcap_bn for log-cap proximity (factors row, else blob profile hint)
    self_row = factors_map.get(ticker) or {}
    self_cap = self_row.get("mktcap_bn") or self_cap_hint

    candidates = []
    for t, row in factors_map.items():
        if t == ticker:
            continue
        if row.get("sector") != sector:
            continue
        peer_cap = row.get("mktcap_bn")
        if not peer_cap:
            continue
        name = row.get("name") or t
        # Log-cap proximity distance
        if self_cap and self_cap > 0 and peer_cap > 0:
            try:
                dist = abs(math.log(peer_cap) - math.log(self_cap))
            except (ValueError, TypeError):
                dist = float("inf")
        else:
            dist = float("inf")
        candidates.append((dist, t, name, peer_cap))

    # Sort by proximity; with no self-cap, fall back to biggest sector names
    if self_cap:
        candidates.sort(key=lambda x: x[0])
    else:
        candidates.sort(key=lambda x: -(x[3] or 0))
    peers = candidates[:6]
    if not peers:
        return None

    rows = []
    for dist, t, name, cap in peers:
        cap_str = ""
        if cap:
            try:
                cf = float(cap)
                cap_str = f"${cf:.0f}B" if cf >= 1 else f"${cf*1000:.0f}M"
            except (TypeError, ValueError):
                pass
        rows.append({
            "ticker": t,
            "name": name,
            "href": f"/stocks/{t}.html",
            "mktcap": cap_str,
        })
    return rows or None


def _build_themes(blob: dict | None, member_ctx_list: list, baskets_map: dict) -> list | None:
    if not blob and not member_ctx_list:
        return None
    rows = []

    # From blob.baskets_membership (direct basket membership)
    bm = (blob or {}).get("baskets_membership") or []
    for b in bm[:5]:
        slug = _clean_str(b.get("slug") or "")
        name = _clean_str(b.get("name") or slug)
        name_zh = _clean_str(b.get("name_zh") or name)
        rows.append({
            "id": slug,
            "name_en": name,
            "name_zh": name_zh,
            "theme": _clean_str(b.get("theme") or ""),
            "rationale": _clean_str(b.get("rationale") or ""),
            "band_en": "",
            "band_zh": "",
        })

    # Augment with member_context for band/tone info
    for mc in member_ctx_list[:5]:
        bid = _clean_str(mc.get("basket_id") or "")
        # Avoid dup
        if any(r["id"] == bid for r in rows):
            # Update band
            for r in rows:
                if r["id"] == bid:
                    r["band_en"] = _clean_str(mc.get("band_en") or "")
                    r["band_zh"] = _clean_str(mc.get("band_zh") or "")
            continue
        basket_info = baskets_map.get(bid) or {}
        bname = _clean_str(mc.get("basket") or basket_info.get("name") or bid)
        bname_zh = _clean_str(basket_info.get("name_zh") or bname)
        rows.append({
            "id": bid,
            "name_en": bname,
            "name_zh": bname_zh,
            "theme": "",
            "rationale": "",
            "band_en": _clean_str(mc.get("band_en") or ""),
            "band_zh": _clean_str(mc.get("band_zh") or ""),
        })

    # Basket alloc
    ba = (blob or {}).get("basket_alloc") or {}
    basket_alloc = None
    if ba.get("rank") is not None:
        _ba_label_en = _clean_str(ba.get("label") or "")
        # Try to find a ZH label from baskets_map by matching name, else fall back to EN
        _ba_name = _clean_str(ba.get("name") or "")
        _ba_label_zh = ""
        for bid, binfo in baskets_map.items():
            if isinstance(binfo, dict) and binfo.get("name") == _ba_name:
                _ba_label_zh = _clean_str(binfo.get("name_zh") or "")
                break
        if not _ba_label_zh:
            _ba_label_zh = _ba_label_en
        basket_alloc = {
            "rank": ba.get("rank"),
            "label_en": _ba_label_en,
            "label_zh": _ba_label_zh,
            "reco_en": _clean_str(ba.get("reco") or ""),
            "name_en": _ba_name,
            "name_zh": _clean_str(ba.get("name_zh") or ""),
        }

    # Sector pulse
    sp = (blob or {}).get("sector_pulse") or {}
    sector_pulse = None
    if sp.get("theme_name"):
        sector_pulse = {
            "theme_name": _clean_str(sp.get("theme_name") or ""),
            "theme_name_zh": _clean_str(sp.get("theme_name_zh") or ""),
            "heat": sp.get("heat"),
            "label": _clean_str(sp.get("label") or ""),
            "rank": sp.get("rank"),
            "n_themes": sp.get("n_themes"),
        }

    if not rows and not basket_alloc and not sector_pulse:
        return None

    return {
        "baskets": rows,
        "basket_alloc": basket_alloc,
        "sector_pulse": sector_pulse,
    }


def _build_signal_history(blob: dict | None) -> dict | None:
    if not blob:
        return None
    alerts_obj = blob.get("alerts") or {}
    timeline = alerts_obj.get("timeline") or []
    pinned = alerts_obj.get("pinned")
    ladder = blob.get("ladder") or {}

    # Recent events: flatten the timeline
    recent_events = []
    for day_obj in timeline[:7]:
        for ev in (day_obj.get("events") or []):
            recent_events.append({
                "date": _clean_str(day_obj.get("daylabel") or ""),
                "date_zh": _clean_str(day_obj.get("daylabel_zh") or ""),
                "headline": _clean_str(ev.get("headline") or ""),
                "headline_zh": _clean_str(ev.get("headline_zh") or ""),
                "detail": _clean_str(ev.get("detail") or ""),
                "detail_zh": _clean_str(ev.get("detail_zh") or ""),
                "dir": _clean_str(ev.get("dir") or ""),
                "type": _clean_str(ev.get("type") or ""),
            })

    if not recent_events and not pinned:
        return None

    return {
        "pinned": pinned,
        "events": recent_events[:15],
        "n_total": alerts_obj.get("n_total", 0),
        "ladder_state": _clean_str(ladder.get("state") or ""),
        "ladder_label": _clean_str(ladder.get("label") or ""),
        "ladder_label_zh": _clean_str(ladder.get("why_zh") or ladder.get("why") or ""),
    }


def _build_seasonality_section(
    season_this: str, season_this_zh: str,
    season_next: str, season_next_zh: str,
    monthly_data: list | None,
) -> dict | None:
    if not season_this and not monthly_data:
        return None
    return {
        "this_label": season_this,
        "this_label_zh": season_this_zh,
        "next_label": season_next,
        "next_label_zh": season_next_zh,
        "monthly": monthly_data,
        # Window caption pairs — label the two different data sources
        "blob_window_en": "Full history",
        "blob_window_zh": "完整历史",
        "computed_window_en": "Last ~5 years of daily data",
        "computed_window_zh": "近约5年日线数据",
    }


def _build_profile_extras(blob: dict | None) -> dict | None:
    if not blob:
        return None
    pers = blob.get("personality") or {}
    base = pers.get("base") or {}
    dc = blob.get("demand_chain") or {}
    mf = blob.get("moat_falsifiers") or {}

    # Personality
    arch = _clean_str(base.get("archetype") or "")
    dna = _clean_str(base.get("dna_class") or "")
    chart_pers = _clean_str(base.get("chart_personality") or "")
    habitat = _clean_str(base.get("ownership_habitat") or "")

    # Demand chain — headline and read may be {'en','zh'} dicts
    dc_hl_raw = dc.get("headline") or dc.get("read") or {}
    if isinstance(dc_hl_raw, dict):
        dc_headline = _clean_str(dc_hl_raw.get("en") or "")
        dc_headline_zh = _clean_str(dc_hl_raw.get("zh") or "")
    else:
        dc_headline = _clean_str(dc_hl_raw)
        dc_headline_zh = ""
    if not dc_headline_zh:
        dc_headline_zh = dc_headline

    # Moat falsifiers — active only
    sensors = mf.get("sensors") or {}
    active_falsifiers = []
    if isinstance(sensors, dict):
        for key, sv in sensors.items():
            if isinstance(sv, dict) and sv.get("fired"):
                active_falsifiers.append(key.replace("_", " ").capitalize())

    if not arch and not dc_headline and not active_falsifiers:
        return None

    return {
        "archetype": arch,
        "dna_class": dna,
        "chart_personality": chart_pers,
        "ownership_habitat": habitat,
        "demand_chain_en": dc_headline,
        "demand_chain_zh": dc_headline_zh,
        "active_falsifiers": active_falsifiers[:4],
    }


def _build_brief(brief: dict | None) -> dict | None:
    if not brief:
        return None
    return {
        "summary": _clean_str(brief.get("summary") or ""),
        "drivers": brief.get("drivers") or [],
        "risks": brief.get("risks") or [],
        "catalysts": brief.get("catalysts") or [],
        "zh_summary": _clean_str((brief.get("zh") or {}).get("summary") if brief.get("zh") else ""),
        "confidence": brief.get("confidence"),
        "disclaimer": _clean_str(brief.get("disclaimer") or "AI-generated research context — not advice."),
        "as_of": _clean_str(brief.get("asof") or brief.get("generated_at") or ""),
    }


def _build_factors_section(blob: dict | None) -> dict | None:
    if not blob:
        return None
    fac = blob.get("factors") or {}
    legs = fac.get("legs") or {}
    radar = fac.get("radar") or []
    composite = fac.get("composite")

    rows = []
    for key, (label_en, label_zh) in _FACTOR_LABELS.items():
        z = legs.get(key)
        if z is None:
            continue
        # accruals/short_interest: high z = bad direction
        is_inverse = key in ("accruals", "short_interest")
        positive = (z >= 0.5 and not is_inverse) or (z <= -0.5 and is_inverse)
        rows.append({
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "z": round(z, 2),
            "positive": positive,
        })

    if not rows:
        return None

    fund_score = fac.get("fundamental_score")
    return {
        "rows": rows,
        "composite": round(composite, 2) if composite is not None else None,
        "fundamental_score": fund_score,
    }


def sections_available(blob: dict | None, per: dict, agg: dict, ticker: str) -> int:
    """Count available substantive sections for the min-info gate (≥3 required)."""
    count = 0
    if blob:
        count += 1
    if (blob or {}).get("valuation"):
        count += 1
    if (blob or {}).get("financials"):
        count += 1
    gex_v1 = per.get("gex_v1")
    if gex_v1 and (gex_v1.get("summary") or gex_v1.get("gamma_regime")):
        count += 1
    if (blob or {}).get("factors"):
        count += 1
    if agg["intel_map"].get(ticker):
        count += 1
    flow = per.get("flow")
    if flow and flow.get("verdict"):
        count += 1
    news = agg["news_map"].get(ticker)
    if news and news.get("top"):
        count += 1
    if (blob or {}).get("smart_money"):
        count += 1
    return count


# ---------------------------------------------------------------------------
# Main context builder
# ---------------------------------------------------------------------------

def build_page_context(
    ticker: str,
    name: str,
    sector: str,
    per: dict,
    agg: dict,
    generated_utc: str,
) -> dict:
    """Build the full v2 context dict for one ticker. Pure — no I/O."""
    blob = per.get("blob")
    ohlc_bars = per.get("ohlc_bars") or []
    is_candle = per.get("ohlc_is_candle", False)
    gex_v1 = per.get("gex_v1")
    flow = per.get("flow")
    signals = per.get("signals")
    brief = per.get("brief")
    intel = agg["intel_map"].get(ticker)
    news_rec = agg["news_map"].get(ticker)
    member_ctx_list = agg["member_ctx_map"].get(ticker) or []
    factor_betas = agg["factor_betas"]
    tech_screener = agg["tech_screener"]
    baskets_map = agg["baskets_map"]

    # --- Stance ---
    stance_en, stance_zh, stance_key, inv_en, inv_zh = compute_stance(blob, signals, intel)
    # Tier-1 copy carries no machine reads (operator order 2026-07-20)
    inv_en, inv_zh = _scrub_machine(inv_en), _scrub_machine_zh(inv_zh)

    # --- Freshness ---
    freshness_dates = [
        per.get("blob_asof"),
        per.get("gex_as_of"),
        per.get("signals_as_of"),
        per.get("flow_as_of"),
        agg.get("intel_as_of"),
        agg.get("news_as_of"),
        per.get("brief_as_of"),
    ]
    freshness = page_freshness(freshness_dates) or date.today().isoformat()
    stale = is_stale(freshness)

    # --- Trailing returns + seasonality from ohlc ---
    trailing_returns: dict = {}
    monthly_data: list | None = None
    if ohlc_bars:
        try:
            trailing_returns = compute_trailing_returns(ohlc_bars, agg.get("spy_bars") or [])
        except Exception as e:  # noqa: BLE001
            log.debug("trailing returns failed for %s: %s", ticker, e)
        try:
            monthly_data = compute_seasonality(ohlc_bars)
        except Exception as e:  # noqa: BLE001
            log.debug("seasonality failed for %s: %s", ticker, e)

    # --- Chart: rendered by the Terminal /embed/chart iframe (v6) — no SSR SVG.

    # --- Profile fields for meta ---
    profile = (blob or {}).get("profile") or {}
    sector_disp = _sector_display(profile.get("sector") or sector)

    # --- Seasonality from blob (precomputed plain strings) ---
    season_this = _clean_str((blob or {}).get("season_this") or "")
    season_this_zh = _clean_str((blob or {}).get("season_this_zh") or "")
    season_next = _clean_str((blob or {}).get("season_next") or "")
    season_next_zh = _clean_str((blob or {}).get("season_next_zh") or "")

    # --- Build all sections ---
    meta = _build_meta(ticker, name, blob, stance_en, freshness, stale, generated_utc)
    hero = _build_hero(ticker, name, blob, stance_en, stance_zh, stance_key, inv_en, inv_zh, factor_betas)
    hero["chg"] = _day_change(ohlc_bars)
    hero["range52"] = _range52(((blob or {}).get("tech") or {}).get("price"), ohlc_bars)
    ladder = _build_ladder(
        ((blob or {}).get("tech") or {}).get("price"),
        blob,
        walls=(per.get("gex_v1") or {}).get("summary") or {},
        signals=per.get("signals"),
        stance_class=_STANCE_CLASS.get(stance_key, "neu"),
    )
    stats = _build_stats(ticker, blob, factor_betas)
    gauges = _build_gauges(ticker, blob, factor_betas)
    performance = _build_performance(ticker, trailing_returns)
    financials = _build_financials(blob)
    valuation = _build_valuation(blob)
    earnings = _build_earnings(blob)
    technicals = _build_technicals(ticker, blob, tech_screener)
    options = _build_options(blob, gex_v1, flow)
    why_moving = _build_why_moving(ticker, blob, news_rec, intel)
    ownership = _build_ownership(ticker, blob, agg.get("alt_map", {}).get(ticker))
    peers = _build_peers(
        ticker, profile.get("sector") or sector,
        agg.get("factors_map") or {}, baskets_map,
        (blob or {}).get("factors"),
        self_cap_hint=profile.get("mktcap_bn"),
    )
    themes_raw = _build_themes(blob, member_ctx_list, baskets_map)
    signal_history = _build_signal_history(blob)
    seasonality = _build_seasonality_section(season_this, season_this_zh, season_next, season_next_zh, monthly_data)
    profile_extras = _build_profile_extras(blob)
    brief_section = _build_brief(brief)
    factors_section = _build_factors_section(blob)
    deep = _build_deep(blob, per, agg, ticker, performance, stats,
                       monthly_data, season_this, season_this_zh)

    # News section (raw for template)
    news_section: list | None = None
    if news_rec:
        headlines = news_rec.get("top") or []
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
        ] or None

    return {
        "meta": meta,
        "hero": hero,
        "stats": stats,
        "ladder": ladder,
        "chart": {
            "embed": True,
            "has_candles": is_candle,
        },
        "gauges": gauges,
        "performance": performance,
        "financials": financials,
        "valuation": valuation,
        "earnings": earnings,
        "technicals": technicals,
        "options": options,
        "why_moving": why_moving,
        "ownership": ownership,
        "peers": peers,
        "themes": themes_raw,
        "signal_history": signal_history,
        "seasonality": seasonality,
        "profile_extras": profile_extras,
        "brief": brief_section,
        "factors": factors_section,
        "deep": deep,
        "news": news_section,
        "placeholders": {
            "analyst_targets": True,
            "transcripts": True,
            "dividend_calendar": True,
        },
        # Flat fields for backward compat / index page
        "ticker": ticker,
        "name": name,
        "sector": sector_disp,
        "canonical_url": meta["canonical"],
        "meta_desc": meta["meta_desc"],
        "jsonld_str": meta["jsonld_str"],
        "freshness": freshness,
        "stale": stale,
        "stance_en": stance_en,
        "stance_zh": stance_zh,
        "stance_key": stance_key,
        "stance_class": _STANCE_CLASS.get(stance_key, "neu"),
        "generated_utc": generated_utc,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    out: Path,
    sitemap_out: Path | None = None,
    site: Path | None = None,
    context_only: bool = False,
    dump_context: Path | None = None,
    only_tickers: set[str] | None = None,
) -> int:
    """Main entrypoint. Returns exit code 0 always (non-fatal).

    only_tickers: when provided, restrict the loop to those tickers only and skip
    sitemap merge (for fast spot-verification of specific tickers via --only flag).
    """
    if site is None:
        site = SITE

    out.mkdir(parents=True, exist_ok=True)
    if dump_context:
        dump_context.mkdir(parents=True, exist_ok=True)

    # --- Load templates (skip in context_only mode) ---
    tmpl_page = None
    tmpl_index = None
    if not context_only:
        try:
            from jinja2 import Environment, FileSystemLoader
            env = Environment(
                loader=FileSystemLoader(str(TEMPLATES_DIR)),
                autoescape=True,
            )
            try:
                tmpl_page = env.get_template("ticker.html.j2")
            except Exception:  # noqa: BLE001
                log.warning("::warning::ticker.html.j2 template not found — switching to context-only mode")
                context_only = True
            try:
                tmpl_index = env.get_template("ticker_index.html.j2")
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:
            log.error("::error::failed to load templates: %s — switching to context-only mode", e)
            context_only = True

    # --- Load membership ---
    try:
        import pandas as pd
        df = pd.read_parquet(str(_ROOT / "data" / "universe" / "membership.parquet"))
        active = df[df["active"] == True].copy()  # noqa: E712
        active = active.dropna(subset=["ticker"])
        # v2: sp500 + sp400 + sp600
        universe_groups = {"sp500", "sp400", "sp600"}
        if "group" in active.columns:
            active = active[active["group"].isin(universe_groups)]
        log.info("Loaded %d active universe members", len(active))
    except Exception as e:
        log.error("::error::failed to load membership.parquet: %s", e)
        return 1

    # --- Load shared aggregates ---
    agg = load_all_aggregates(site)

    # Build stockdata universe: tickers with blobs
    stockdata_dir = site / "stockdata"
    stockdata_tickers: set[str] = set()
    if stockdata_dir.exists():
        for f in stockdata_dir.glob("*.json"):
            if f.stem != "index":
                stockdata_tickers.add(f.stem)

    n_rendered = 0
    n_skipped = 0
    n_noindexed = 0
    n_limited = 0
    sitemap_entries: list[dict] = []
    index_rows: list[dict] = []

    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Share-card counters (per-run)
    _sc_rendered = 0
    _sc_skipped = 0
    _sc_logo_fetches = 0
    _sc_fetch_skipped_recent = 0
    import time as _time
    _sc_t0 = _time.perf_counter()

    # Negative logo-fetch cache: {ticker: "YYYY-MM-DD"} — skip re-fetching recently
    # attempted logos (both successes and failures) for _LOGO_NEGATIVE_CACHE_DAYS days.
    _logo_attempts: dict[str, str] = {}
    try:
        if _LOGO_ATTEMPTS_PATH.exists():
            _logo_attempts = json.loads(_LOGO_ATTEMPTS_PATH.read_text(encoding="utf-8"))
            if not isinstance(_logo_attempts, dict):
                _logo_attempts = {}
    except Exception as _lae:  # noqa: BLE001
        log.warning("::warning::logo_attempts load failed (fail-soft): %s", _lae)
        _logo_attempts = {}
    _today_iso = date.today().isoformat()

    for _, row in active.iterrows():
        ticker = _clean_str(row.get("ticker"))
        if not ticker:
            continue
        # --only filter: skip tickers not in the requested set
        if only_tickers is not None and ticker not in only_tickers:
            continue
        name = _clean_str(row.get("name") or ticker)
        sector = _clean_str(row.get("sector") or "")
        group = _clean_str(row.get("group") or "sp500")

        # v2 gate: must have a stockdata blob
        if ticker not in stockdata_tickers:
            n_skipped += 1
            continue

        try:
            per = load_per_ticker(site, ticker)
            blob = per.get("blob")

            # Skip profile-limited blobs
            if blob and blob.get("limited"):
                n_limited += 1
                continue

            # Min-info gate
            n_sec = sections_available(blob, per, agg, ticker)
            if n_sec < 3:
                log.debug("skip %s: only %d sections (gate=3)", ticker, n_sec)
                n_skipped += 1
                continue

            ctx = build_page_context(ticker, name, sector, per, agg, generated_utc)

            # ── Share card (og:image) ─────────────────────────────────────
            # Fingerprint-gated: only re-renders when ticker/name/sector/
            # industry/logo/CARD_VERSION changes. Never kills a dossier render.
            og_image_url: str | None = None
            if _SHARE_CARDS is not None and not context_only:
                try:
                    _og_out = OG_DIR / f"{ticker}.png"
                    # Industry from blob profile (not in membership.parquet)
                    _profile = (blob or {}).get("profile") or {}
                    _industry = _profile.get("industry") or None

                    # Logo: check cache first, then attempt one CDN fetch per run.
                    # Negative cache: skip tickers attempted within the last
                    # _LOGO_NEGATIVE_CACHE_DAYS days (recorded regardless of outcome).
                    _logo_path: Path | None = LOGO_DIR / f"{ticker}_white.png"
                    if not (_logo_path and _logo_path.exists()):
                        _logo_path = None
                        _last_attempt = _logo_attempts.get(ticker)
                        _recently_attempted = False
                        if _last_attempt:
                            try:
                                from datetime import timedelta
                                _delta = date.today() - date.fromisoformat(_last_attempt)
                                _recently_attempted = _delta.days < _LOGO_NEGATIVE_CACHE_DAYS
                            except (ValueError, TypeError):
                                pass
                        if _recently_attempted:
                            _sc_fetch_skipped_recent += 1
                        elif _LOGO_CACHE is not None and _sc_logo_fetches < MAX_LOGO_FETCH_PER_RUN:
                            _logo_attempts[ticker] = _today_iso
                            try:
                                _LOGO_CACHE.white_logo_datauri(ticker, _ROOT, fetch=True)
                                _sc_logo_fetches += 1
                            except Exception:  # noqa: BLE001
                                pass
                            _candidate = LOGO_DIR / f"{ticker}_white.png"
                            if _candidate.exists():
                                _logo_path = _candidate

                    _sector_disp = ctx.get("sector") or _sector_display(sector)
                    _sc_payload = {
                        "type": "ticker",
                        "ticker": ticker,
                        "name": name,
                        "sector": _sector_disp,
                        "industry": _industry,
                        "logo": _logo_path.name if _logo_path else None,
                    }
                    _sc_rendered_flag = _SHARE_CARDS.save_card_if_changed(
                        payload=_sc_payload,
                        out_path=_og_out,
                        render=lambda _t=ticker, _n=name, _s=_sector_disp, _i=_industry, _lp=_logo_path: (
                            _SHARE_CARDS.render_ticker_card(
                                ticker=_t, name=_n, sector=_s, industry=_i, logo_path=_lp
                            )
                        ),
                        root=_ROOT,
                    )
                    if _sc_rendered_flag:
                        _sc_rendered += 1
                    else:
                        _sc_skipped += 1
                    # Only pass og_image_url if PNG actually exists
                    if _og_out.exists():
                        og_image_url = f"{CANONICAL_BASE}/og/stocks/{ticker}.png"
                except Exception as _sc_err:  # noqa: BLE001
                    log.debug("share card failed for %s: %s", ticker, _sc_err)
                    og_image_url = None
            # Inject into context for template
            ctx["og_image_url"] = og_image_url

            # Dump context JSON if requested
            if dump_context:
                try:
                    ctx_json = dict(ctx)
                    (dump_context / f"{ticker}.json").write_text(
                        json.dumps(ctx_json, ensure_ascii=False, default=str, indent=2)
                    )
                except Exception as e:  # noqa: BLE001
                    log.debug("ctx dump failed for %s: %s", ticker, e)

            # Render HTML
            if not context_only and tmpl_page:
                html = tmpl_page.render(**ctx)
                write_page(out / f"{ticker}.html", html)
            n_rendered += 1

            # Sitemap
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

            stance_key = ctx["stance_key"]
            state_chip = {
                "uptrend": "Uptrend", "bottoming": "Basing", "recovering": "Recovering",
                "extended": "Extended", "protect": "Protect", "topping": "Topping",
                "aside": "Aside", "downtrend": "Downtrend", "mixed": "Mixed", "watch": "Watch",
            }.get(stance_key, "Watch")
            state_chip_zh = {
                "uptrend": "上涨", "bottoming": "筑底", "recovering": "复苏",
                "extended": "偏高", "protect": "保护", "topping": "见顶",
                "aside": "观望", "downtrend": "下跌", "mixed": "混杂", "watch": "关注",
            }.get(stance_key, "关注")

            # Pull price + YTD for the index grid
            _hero = ctx.get("hero") or {}
            _price_raw = _hero.get("price") if isinstance(_hero, dict) else None
            try:
                _price_f = float(str(_price_raw).replace(",", "")) if _price_raw is not None else None
            except (ValueError, TypeError):
                _price_f = None
            _ytd_row = next(
                (r for r in (ctx.get("performance") or [])
                 if any(k in (r.get("label_en") or "") for k in ("YTD", "Year to date", "year to date"))),
                None,
            )
            _ytd = _ytd_row.get("ticker_ret") if _ytd_row else None
            _ytd_pos = _ytd_row.get("positive") if _ytd_row else None

            index_rows.append({
                "ticker": ticker,
                "name": name,
                "sector": _sector_display(sector),
                "state_chip": state_chip,
                "state_chip_zh": state_chip_zh,
                "stance_class": ctx["stance_class"],
                "price": f"${_price_f:,.2f}" if _price_f is not None else None,
                "ytd": _ytd,
                "ytd_pos": _ytd_pos,
            })

        except Exception as e:  # noqa: BLE001
            log.warning("::warning title=%s::page render failed: %s", ticker, e)
            n_skipped += 1
            continue

    # --- Index page ---
    if not context_only and tmpl_index:
        try:
            index_rows_sorted = sorted(index_rows, key=lambda r: r["ticker"])
            index_html = tmpl_index.render(
                rows=index_rows_sorted,
                n_total=len(index_rows_sorted),
                generated_utc=generated_utc,
                canonical_url=f"{CANONICAL_BASE}/stocks/index.html",
            )
            write_page(out / "index.html", index_html)
            sitemap_entries.insert(0, {
                "loc": f"{CANONICAL_BASE}/stocks/index.html",
                "lastmod": date.today().isoformat(),
                "changefreq": "daily",
                "priority": 0.7,
            })
        except Exception as e:  # noqa: BLE001
            log.warning("::warning title=index::index page render failed: %s", e)

    # --- Share-card summary ---
    _sc_elapsed = _time.perf_counter() - _sc_t0
    log.info(
        "[share_cards] ticker cards rendered=%d skipped=%d logo_fetches=%d fetch_skipped_recent=%d in %.1fs",
        _sc_rendered, _sc_skipped, _sc_logo_fetches, _sc_fetch_skipped_recent, _sc_elapsed,
    )

    # Persist logo negative-cache atomically (temp file + os.replace).
    if _logo_attempts:
        try:
            _LOGO_ATTEMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            import tempfile as _tempfile
            _tmp_fd, _tmp_name = _tempfile.mkstemp(
                dir=str(_LOGO_ATTEMPTS_PATH.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(_tmp_fd, "w", encoding="utf-8") as _fh:
                    json.dump(_logo_attempts, _fh, ensure_ascii=False, indent=2)
                os.replace(_tmp_name, str(_LOGO_ATTEMPTS_PATH))
            except Exception:  # noqa: BLE001
                try:
                    os.unlink(_tmp_name)
                except OSError:
                    pass
                raise
        except Exception as _persist_err:  # noqa: BLE001
            log.warning("::warning::logo_attempts persist failed: %s", _persist_err)

    # --- Sitemap update --- (skipped when --only restricts to a subset)
    real_sitemap = site / "sitemap.xml"
    is_production = (out.resolve() == (site / "stocks").resolve())

    if (sitemap_out or is_production) and only_tickers is None:
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
        "::notice title=ticker_pages::rendered=%d skipped=%d limited=%d noindexed=%d",
        n_rendered, n_skipped, n_limited, n_noindexed,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build static per-ticker stock dossier pages (v2).")
    parser.add_argument("--out", default=None, help="Output directory (default: site/stocks)")
    parser.add_argument("--sitemap-out", default=None, help="Sitemap output path")
    parser.add_argument("--context-only", action="store_true",
                        help="Skip HTML rendering; only compute context dicts")
    parser.add_argument("--dump-context", default=None,
                        help="Directory to write per-ticker ctx JSON files (contract for template builder)")
    parser.add_argument("--only", default=None,
                        help="Comma-separated list of tickers to render (skips sitemap merge when used)")
    args = parser.parse_args(argv)

    out = Path(args.out) if args.out else (SITE / "stocks")
    sitemap_out = Path(args.sitemap_out) if args.sitemap_out else None
    dump_context = Path(args.dump_context) if args.dump_context else None
    only_tickers: set[str] | None = (
        {t.strip().upper() for t in args.only.split(",") if t.strip()}
        if args.only else None
    )

    rc = run(
        out=out,
        sitemap_out=sitemap_out,
        context_only=args.context_only,
        dump_context=dump_context,
        only_tickers=only_tickers,
    )
    return rc


if __name__ == "__main__":
    from lib.procutil import hard_exit
    rc = main()
    hard_exit(rc)
