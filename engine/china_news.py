"""China macro news & official policy tone — the China sibling of macro_news.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS · DEFAULT-OFF for the LLM. Honest CONTEXT,
never a scoring input. Imports only lib.config + lib.store (+ a LAZY akshare
inside the build-time fetch); nothing in the China scoring core imports it, and
every public function returns plain data or None and NEVER raises into the build.

Two independent legs, either of which may be absent:

  1. OFFICIAL POLICY TONE — the CCTV 新闻联播 (Xinwen Lianbo) daily broadcast tone
     accrued by collectors/china_news.py into data/china_news/cctv_tone.parquet.
     This engine smooths the sparse daily series (tone_smooth) and z-scores it over
     a trailing window (tone_window) into a supportive / steady / cautious lean.
     The collector owns the raw lexicon proxy; the engine owns the z-score — read
     RELATIVE, never as an absolute sentiment. Degrades to None before the
     collector has accrued any history (e.g. on a fresh deploy).

  2. FILTERED FLASH HEADLINES — Eastmoney 全球财经快讯 flash wire (ak.stock_info_
     global_em), fetched at BUILD time and cached (flash_cache, cache_ttl_hours).
     Deterministically theme-gated against a Chinese macro keyword lexicon (each
     kept flash tagged by theme) + deduped + recency-ranked; top `max_show`. No AI
     in the filter. akshare is imported LAZILY so a missing/broken dep degrades to
     "no headlines" instead of taking the panel (or the whole build) down.

  3. OPTIONAL AI BRIEF — the ONLY AI: a gated, default-off, degrade-to-keyless
     1-paragraph narration of the already-filtered flashes + the policy-tone state.
     Labeled context, never scored. Off unless enabled AND llm_brief AND a key.

Nothing here ever feeds a score, signal, regime or allocation. See the
`china_news` block in config.yml.
"""
from __future__ import annotations

import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_news.v1"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Chinese macro-theme keyword buckets — used to gate + TAG each flash headline
# (deterministic classification; first bucket with a hit wins). Tuned for the
# Eastmoney 全球财经快讯 tape.
MACRO_THEMES: dict[str, list[str]] = {
    "monetary": ["央行", "人民银行", "降准", "降息", "加息", "利率", "LPR", "MLF",
                 "逆回购", "流动性", "货币政策", "公开市场", "PBOC", "People's Bank",
                 "central bank", "monetary policy", "reserve requirement", "RRR",
                 "open market", "loan prime rate"],
    "inflation": ["CPI", "PPI", "物价", "通胀", "通缩", "通货膨胀",
                  "inflation", "consumer price", "producer price", "deflation"],
    "growth": ["GDP", "经济增长", "PMI", "制造业", "工业增加值", "复苏", "放缓",
               "衰退", "增速", "经济数据", "China economy", "economic growth",
               "retail sales", "industrial output", "fixed asset", "Caixin PMI",
               "official PMI", "slowdown", "recovery"],
    "credit": ["社融", "社会融资", "信贷", "贷款", "债券", "国债", "收益率", "违约",
               "信用", "城投", "credit", "new loans", "aggregate financing",
               "total social financing", "bond", "yield", "LGFV", "debt"],
    "fiscal": ["财政", "专项债", "减税", "退税", "关税", "贸易", "出口", "进口",
               "制裁", "财政部", "fiscal", "special bond", "exports", "imports",
               "tariff", "trade", "sanction", "Ministry of Finance", "MOFCOM"],
    "policy": ["国常会", "政治局", "发改委", "稳增长", "稳经济", "房地产", "楼市",
               "监管", "改革", "政策", "国务院", "State Council", "Politburo",
               "stimulus", "property support", "real estate policy", "NDRC",
               "reform", "policy support"],
    "politics": ["习近平", "总书记", "中央", "中美", "外交", "地缘", "台海", "台湾",
                 "国安", "一带一路", "反腐", "人大", "两会", "拜登", "特朗普", "白宫",
                 "出口管制", "实体清单"],
    "tech": ["科技", "半导体", "芯片", "人工智能", "算力", "软件", "互联网", "新能源车",
             "电动车", "光伏", "锂电", "5G", "大模型", "国产替代", "华为", "数据中心",
             "云计算", "机器人", "智能驾驶"],
    "markets": ["A股", "股市", "沪深", "上证", "创业板", "科创板", "北交所", "证监会",
                "退市", "IPO", "北向", "外资", "南向", "板块", "龙头", "涨停", "跌停",
                "业绩", "财报", "回购", "减持", "增持", "券商", "基金", "新股",
                "A-shares", "A shares",
                "Chinese stocks", "CSI 300", "Shanghai Composite", "CSRC",
                "capital market", "yuan", "renminbi", "上市公司", "个股", "股票",
                "公司公告", "停牌", "复牌", "并购", "重组", "研报"],
}
# theme display labels (EN, ZH)
THEME_LABEL: dict[str, tuple[str, str]] = {
    "monetary": ("PBoC", "央行"), "inflation": ("Inflation", "物价"),
    "growth": ("Growth", "增长"), "credit": ("Credit", "信用"),
    "fiscal": ("Fiscal/Trade", "财政/贸易"), "policy": ("Policy", "政策"),
    "politics": ("Politics", "政治/地缘"), "tech": ("Tech", "科技"),
    "markets": ("Markets", "市场"), "macro": ("Macro", "宏观"),
}

OFFICIAL_PAGES = [
    {"name": "PBoC", "url": "https://www.pbc.gov.cn/en/3688006/index.html", "theme": "monetary", "tier": "official"},
    {"name": "NBS", "url": "https://www.stats.gov.cn/english/PressRelease/", "theme": "growth", "tier": "official"},
    {"name": "MOF", "url": "https://www.mof.gov.cn/en/news/", "theme": "fiscal", "tier": "official"},
    {"name": "State Council", "url": "https://english.www.gov.cn/policies/latestreleases/", "theme": "policy", "tier": "official"},
    {"name": "SCIO", "url": "https://english.scio.gov.cn/pressroom/index.htm", "theme": "policy", "tier": "official"},
    {"name": "NDRC", "url": "https://en.ndrc.gov.cn/news/pressreleases/", "theme": "policy", "tier": "official"},
    {"name": "CSRC", "url": "https://www.csrc.gov.cn/csrc_en/", "theme": "markets", "tier": "official"},
    {"name": "SAFE", "url": "https://www.safe.gov.cn/en/SAFENews/index.html", "theme": "markets", "tier": "official"},
    {"name": "MOFCOM", "url": "https://english.mofcom.gov.cn/", "theme": "fiscal", "tier": "official"},
]

WIRE_SOURCES = [
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com",
    "scmp.com", "caixinglobal.com", "nikkei.com", "asia.nikkei.com",
    "apnews.com", "marketwatch.com", "barrons.com", "spglobal.com",
    "yicaiglobal.com", "chinadaily.com.cn", "cgtn.com", "english.news.cn",
    "globaltimes.cn",
]

NEWS_FEEDS = [
    {"name": "SCMP - China Economy", "url": "https://www.scmp.com/rss/318421/feed", "domain": "scmp.com", "theme": "growth", "source": "news_rss", "tier": "global_wire"},
    {"name": "SCMP - China", "url": "https://www.scmp.com/rss/4/feed", "domain": "scmp.com", "theme": "macro", "source": "news_rss", "tier": "global_wire"},
    {"name": "SCMP - Business", "url": "https://www.scmp.com/rss/92/feed", "domain": "scmp.com", "theme": "markets", "source": "news_rss", "tier": "global_wire"},
    {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar", "domain": "asia.nikkei.com", "theme": "macro", "source": "news_rss", "tier": "global_wire"},
]

NEWS_PAGES = [
    {"name": "第一财经", "url": "https://www.yicai.com/news/", "domain": "yicai.com", "theme": "markets", "source": "cn_news_page", "tier": "china_native", "source_lang": "zh"},
    {"name": "证券时报", "url": "https://www.stcn.com/", "domain": "stcn.com", "theme": "markets", "source": "cn_news_page", "tier": "china_native", "source_lang": "zh"},
    {"name": "上海证券报", "url": "https://www.cnstock.com/", "domain": "cnstock.com", "theme": "markets", "source": "cn_news_page", "tier": "china_native", "source_lang": "zh"},
    {"name": "新浪财经股票", "url": "https://finance.sina.com.cn/stock/", "domain": "finance.sina.com.cn", "theme": "markets", "source": "cn_news_page", "tier": "china_native", "source_lang": "zh"},
    {"name": "东方财富股票", "url": "https://stock.eastmoney.com/", "domain": "stock.eastmoney.com", "theme": "markets", "source": "cn_news_page", "tier": "china_native", "source_lang": "zh"},
    {"name": "Caixin Global - Economy", "url": "https://www.caixinglobal.com/economy/", "theme": "growth", "source": "news_page", "tier": "global_wire"},
    {"name": "Caixin Global - Business", "url": "https://www.caixinglobal.com/business-and-tech/", "theme": "markets", "source": "news_page", "tier": "global_wire"},
    {"name": "Caixin Global - China", "url": "https://www.caixinglobal.com/china/", "theme": "macro", "source": "news_page", "tier": "global_wire"},
]

GDELT_QUERY_TERMS = [
    '"China economy"', '"Chinese economy"', "PBOC", '"People\'s Bank of China"',
    "yuan", "renminbi", '"China property"', '"China real estate"',
    '"China stimulus"', '"China exports"', '"China imports"', '"China inflation"',
    '"China CPI"', '"China PPI"', '"China PMI"', '"A-shares"', '"Chinese stocks"',
    '"CSI 300"', '"China credit"', '"total social financing"', '"new loans"',
    "NDRC", "CSRC", "MOFCOM",
]

CHANNEL_KEYWORDS: dict[str, list[str]] = {
    "pboc_liquidity": ["央行", "人民银行", "PBOC", "People's Bank", "逆回购", "MLF", "LPR", "降准", "降息", "open market", "liquidity"],
    "credit_impulse": ["社融", "社会融资", "信贷", "贷款", "credit", "financing", "financial statistics"],
    "property": ["房地产", "楼市", "房价", "commercial residential", "property", "real estate"],
    "consumer": ["消费", "零售", "CPI", "consumer", "retail"],
    "industrial": ["工业", "制造业", "PMI", "industrial", "manufacturing", "production"],
    "fiscal_trade": ["财政", "专项债", "出口", "进口", "关税", "trade", "tariff", "mof"],
    "markets": ["A股", "沪深", "上证", "创业板", "证监会", "IPO", "capital market", "securities"],
    "yuan": ["人民币", "汇率", "离岸", "中间价", "yuan", "renminbi", "rmb", "exchange rate"],
    "tech_policy": ["半导体", "芯片", "人工智能", "AI", "算力", "technology", "semiconductor"],
    "commodities": ["铜", "煤", "钢", "原油", "稀土", "commodity", "production materials"],
}

# channel slug -> (EN plain words, ZH) for user-facing chips — the doctrine bans
# raw slugs on glance surfaces, so the engine de-slugs at the source. Covers
# CHANNEL_KEYWORDS keys; unmapped slugs de-underscore via _slug_label.
CHANNEL_LABEL: dict[str, tuple[str, str]] = {
    "pboc_liquidity": ("PBOC & liquidity", "央行与流动性"),
    "credit_impulse": ("credit & financing", "信贷与社融"),
    "property": ("property", "房地产"),
    "consumer": ("consumer", "消费"),
    "industrial": ("industry & manufacturing", "工业与制造业"),
    "fiscal_trade": ("fiscal & trade", "财政与贸易"),
    "markets": ("equity market", "股票市场"),
    "yuan": ("yuan & FX", "人民币与汇率"),
    "tech_policy": ("tech policy", "科技政策"),
    "commodities": ("commodities", "大宗商品"),
}


def _slug_label(slug: str) -> tuple[str, str]:
    """(EN, ZH) display pair for a channel/theme slug; unmapped slugs de-underscore.
    THEME_LABEL fallback because channels back-fill from the theme when no channel
    keyword fires, so theme slugs reach the same user-facing surfaces."""
    return CHANNEL_LABEL.get(slug) or THEME_LABEL.get(slug) or (slug.replace("_", " "), slug.replace("_", " "))


# source_tier slug -> (EN plain words, ZH) for the synthesis `read` line.
TIER_LABEL: dict[str, tuple[str, str]] = {
    "official": ("official releases", "官方发布"),
    "wire": ("global wire", "国际通讯社"),
    "global_wire": ("global wire", "国际通讯社"),
    "domestic_wire": ("domestic wire", "国内财经快讯"),
    "china_native": ("Chinese financial press", "中国财经媒体"),
    "unknown": ("other", "其他"),
}


def _tier_label(slug: str) -> tuple[str, str]:
    """(EN, ZH) display pair for a source_tier slug; unmapped slugs de-underscore."""
    return TIER_LABEL.get(slug) or (slug.replace("_", " "), slug.replace("_", " "))


TICKER_RULES: list[tuple[str, list[str]]] = [
    ("510300.SS", ["沪深300", "csi 300", "a股", "a-share", "上证", "capital market"]),
    ("ASHR", ["a-share", "a shares", "a股", "沪深"]),
    ("CNYA", ["china a shares", "a-share", "a shares", "msci china a"]),
    ("MCHI", ["china equities", "chinese equities", "msci china"]),
    ("FXI", ["h-shares", "hong kong listed", "中国股票"]),
    ("2800.HK", ["hang seng", "hong kong stocks", "hsi"]),
    ("2822.HK", ["china a50", "ftse china a50", "a50"]),
    ("KWEB", ["互联网", "platform", "internet", "e-commerce"]),
    ("CNY", ["人民币", "yuan", "renminbi", "rmb", "汇率"]),
    ("CNH", ["离岸", "offshore yuan"]),
    ("CBON", ["china bond", "chinese bond", "government bond", "国债", "收益率"]),
    ("512800.SS", ["银行", "banks", "lending", "贷款"]),
    ("512880.SS", ["证券", "券商", "broker", "securities"]),
    ("512200.SS", ["房地产", "property", "real estate", "房价"]),
    ("512760.SS", ["半导体", "semiconductor", "chip"]),
    ("515030.SS", ["新能源车", "ev", "battery", "电池"]),
    ("512400.SS", ["有色", "metals", "copper", "rare earth", "稀土"]),
]

HIGH_IMPACT_TERMS = [
    "央行", "人民银行", "降准", "降息", "LPR", "MLF", "社融", "社会融资", "信贷",
    "GDP", "PMI", "CPI", "PPI", "政治局", "国常会", "财政", "专项债",
    "房地产", "房价", "证监会", "资本市场", "关税", "制裁",
    "pboc", "financial statistics", "gdp", "pmi", "consumer price", "producer price",
    "monetary policy", "fiscal", "property", "capital market",
]
MEDIUM_IMPACT_TERMS = [
    "出口", "进口", "制造业", "工业", "消费", "零售", "外资", "北向", "南向",
    "open market", "trade", "industrial", "retail", "production", "prices",
]

DISCLAIMER_TEXT = (
    "Context only — not a signal. The policy-tone read is a z-score of a crude "
    "lexicon proxy on the CCTV 新闻联播 broadcast (relative, never an absolute "
    "sentiment); the headlines are deterministically filtered (macro themes only, "
    "each tagged) Eastmoney flash-wire items. Nothing here is an input to any "
    "score, signal, regime or allocation, and the mechanical model never sees it."
)
DISCLAIMER_TEXT_ZH = (
    "仅作背景，非信号。政策基调读数是对央视《新闻联播》文本的粗略词典代理的 z 标准化"
    "（相对值，并非绝对情绪）；头条为东方财富快讯经确定性筛选（仅宏观主题，逐条标注）"
    "的条目。这里没有任何内容会进入任何评分、信号、区制或配置，机械模型也从不读取它们。"
)


def _cfg() -> dict:
    return config.load().get("china_news", {}) or {}


def enabled() -> bool:
    """Master switch for the Eastmoney flash fetch + LLM brief. The policy-tone leg
    is keyless (reads the stored series) and surfaces regardless."""
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# leg 1: official policy tone (CCTV 新闻联播) — keyless, from the stored series
# --------------------------------------------------------------------------- #

# Long-history baseline path (written by scripts/rebuild_cctv_tone_history.py
# after the W4 CCTV backfill completes).  When present it is used as the
# reference distribution for z-scoring; when absent we fall back to the rolling
# window (pre-backfill behaviour).  The tone_history file is small (<2 MB) and
# IS committed to the repo.
_TONE_HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "china_news" / "cctv_tone_history.parquet"


def _load_tone_history_baseline() -> "pd.Series | None":
    """Load the long-run CCTV tone series (from scripts/rebuild_cctv_tone_history.py).

    W4 baseline design — window-vs-long-history hybrid:
      • When cctv_tone_history.parquet exists with ≥ 60 rows of real data (n_items > 0)
        we use the FULL history mean/std as the z-score denominator.  This is the
        honest choice: 90 days of live data (≈ 19 obs to date) is not a reliable
        distribution; the 10-year series (≈ 3,800 days) IS.
      • We still apply a 5-day smoothing to the live series BEFORE computing z so
        that a single noisy day does not spike the z-score.
      • The history itself is also smoothed (5-day rolling mean) before computing
        baseline μ and σ — identical transformation applied to both distributions.
      • Fall-back: if the history file is absent or has fewer than 60 ok rows, we
        return None and the caller reverts to the rolling-window path.

    Returns the smoothed long-history tone Series (DatetimeIndex) or None.
    """
    try:
        if not _TONE_HISTORY_PATH.exists():
            return None
        import pandas as pd
        hist = pd.read_parquet(_TONE_HISTORY_PATH)
        if hist.empty or "tone" not in hist.columns:
            return None
        # Require at least 60 real broadcast days to trust the baseline
        n_items = hist.get("n_items", hist["tone"].notna().astype(int))
        if int((n_items > 0).sum()) < 60:
            return None
        s = pd.to_numeric(hist["tone"], errors="coerce")
        # NaN days (empty/stub) are interpolated so the smoother doesn't skip them
        s = s.interpolate(method="time", limit_direction="forward").dropna()
        if s.empty:
            return None
        return s.rolling(5, min_periods=1).mean()
    except Exception as e:  # noqa: BLE001
        log.debug("china_news._load_tone_history_baseline failed (%s)", e)
        return None


def _tone_stats(series, window: int, smooth: int,
                history_baseline: "pd.Series | None" = None) -> dict | None:
    """Smooth the sparse daily tone, z-score the latest vs the best available baseline.

    Baseline priority (W4 hybrid):
      1. long-history series from cctv_tone_history.parquet (history_baseline arg)
         — used when present and has ≥ 60 real days.
      2. trailing `window`-day window on the live series (pre-backfill fallback).

    PURE (takes a pandas Series + optional baseline). None if there's nothing usable.
    """
    try:
        import pandas as pd
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return None
        sm = s.rolling(max(int(smooth), 1), min_periods=1).mean()
        latest = float(sm.iloc[-1])

        if history_baseline is not None and len(history_baseline) >= 60:
            # Long-history path: μ and σ come from the full 10-year baseline
            mu = float(history_baseline.mean())
            sd = float(history_baseline.std(ddof=1)) if len(history_baseline) > 1 else 0.0
            baseline_source = "long_history"
            baseline_n = int(len(history_baseline))
        else:
            # Fallback: rolling window on the live series
            win = sm.tail(max(int(window), 2))
            mu = float(win.mean())
            sd = float(win.std(ddof=0))
            baseline_source = "rolling_window"
            baseline_n = int(len(s))

        z = (latest - mu) / sd if sd and not pd.isna(sd) and sd > 1e-9 else 0.0
        return {"value": round(latest, 3), "mean": round(mu, 3),
                "z": round(float(z), 2), "n": int(len(s)),
                "baseline_source": baseline_source, "baseline_n": baseline_n}
    except Exception:  # noqa: BLE001
        return None


def _tone_band(stats: dict | None) -> tuple[str, str, str]:
    """(band_key, label_en, label_zh). 'building' until there's enough history."""
    if not stats:
        return "unknown", "unknown", "未知"
    if stats["n"] < 10:
        return "building", "building", "积累中"
    z = stats["z"]
    if z >= 0.5:
        return "supportive", "supportive / pro-growth lean", "偏积极 / 稳增长"
    if z <= -0.5:
        return "cautious", "cautious / risk-tilted lean", "偏谨慎 / 防风险"
    return "steady", "steady / neutral", "平稳 / 中性"


def policy_tone(asof: date | str | None = None) -> dict | None:
    """Official policy-tone read from data/china_news/cctv_tone.parquet.

    Z-scores against the long-history CCTV baseline (cctv_tone_history.parquet)
    when available (W4 re-baseline), falling back to the rolling 90-day window
    when the history file hasn't been built yet (pre-backfill / fresh deploy).

    Returns the display dict (value/z/band/asof/baseline_source) or None when no
    tone history exists yet. Never raises.
    """
    try:
        df = store.read("china_news", "cctv_tone")
        if df is None or df.empty or "tone" not in df.columns:
            return None
        cfg = _cfg()
        history_baseline = _load_tone_history_baseline()
        stats = _tone_stats(df["tone"], cfg.get("tone_window", 90), cfg.get("tone_smooth", 5),
                            history_baseline=history_baseline)
        if not stats:
            return None
        band, lab_en, lab_zh = _tone_band(stats)
        return {
            "schema": SCHEMA, "is_context_only": True,
            "value": stats["value"], "z": stats["z"], "n_days": stats["n"],
            "band": band, "label_en": lab_en, "label_zh": lab_zh,
            "asof": str(df.index.max().date()),
            "baseline_source": stats.get("baseline_source", "rolling_window"),
            "baseline_n": stats.get("baseline_n", stats["n"]),
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_news.policy_tone failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# leg 2: filtered Eastmoney flash headlines — deterministic gate, no AI
# --------------------------------------------------------------------------- #
def classify_theme(text: str) -> str | None:
    """Macro theme a flash matches (first bucket with a keyword hit), or None when it
    matches no macro keyword (-> dropped). PURE."""
    blob = text or ""
    low = blob.lower()
    for theme, kws in MACRO_THEMES.items():
        if any(_has_term(blob, low, k) for k in kws):
            return theme
    return None


def _has_term(blob: str, low: str, term: str) -> bool:
    if not term:
        return False
    if any(ord(ch) > 127 for ch in term):
        return term in blob
    if term != term.lower() and term in blob:
        return True
    t = term.lower()
    if re.fullmatch(r"[a-z0-9]{1,3}", t):
        return re.search(rf"\b{re.escape(t)}\b", low) is not None
    return t in low


def _channels(text: str) -> list[str]:
    blob = text or ""
    low = blob.lower()
    out = []
    for ch, kws in CHANNEL_KEYWORDS.items():
        if any(_has_term(blob, low, k) for k in kws):
            out.append(ch)
    return out


def _ticker_hits(text: str) -> list[dict]:
    blob = text or ""
    low = blob.lower()
    out: list[dict] = []
    for tk, kws in TICKER_RULES:
        hit = next((k for k in kws if _has_term(blob, low, k)), "")
        if hit:
            out.append({"ticker": tk, "reason": hit})
    return out[:7]


def _tickers(text: str) -> list[str]:
    return [h["ticker"] for h in _ticker_hits(text)]


def _source_weight(source_tier: str = "", source_name: str = "", source: str = "") -> tuple[int, str]:
    blob = f"{source_tier} {source_name} {source}".lower()
    if source_tier == "official" or source == "official":
        return 18, "official policy source"
    if source_tier == "china_native" or source == "cn_news_page":
        return 24, "native Chinese financial source"
    if "reuters" in blob or "bloomberg" in blob or "ft.com" in blob or "caixin" in blob or "scmp" in blob:
        return 12, "tier-1 China wire"
    if source_tier in {"wire", "global_wire"} or source in {"gdelt", "news_rss", "news_page"}:
        return 9, "global wire source"
    if source_tier == "domestic_wire" or source == "eastmoney":
        return 7, "domestic flash wire"
    return 0, ""


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _freshness_points(value: str) -> int:
    dt = _parse_dt(value)
    if not dt:
        return 0
    age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    if age_h <= 8:
        return 7
    if age_h <= 24:
        return 5
    if age_h <= 72:
        return 3
    if age_h <= 168:
        return 1
    return 0


# A headline's `time` slot must hold ONLY a publish datetime. Some native CN page
# scrapers concatenate "<title> … <href>" into the date field (see _parse_dateish
# + _fetch_news_pages), which used to dump a whole headline+URL into .cn-when.
_TIME_URLISH = re.compile(r"https?://|www\.", re.I)


def _clean_time(value: str, title: str = "") -> str:
    """Guard: a clean publish timestamp, or '' when the field is contaminated.
    Collapses whitespace and rejects any value that carries the article URL or the
    headline text (never the title, never a link — just a date/time or nothing)."""
    s = " ".join(str(value or "").split())
    if not s or _TIME_URLISH.search(s):
        return ""
    t = " ".join(str(title or "").split())
    if len(t) >= 8 and t[:8] in s:          # headline leaked into the date field
        return ""
    return s


# Native CN news-page anchors (<a> on cnstock/stcn/yicai) fold the article's
# section breadcrumb and a relative-time suffix into the link text, e.g.
#   人民币资产"圈粉"全球 … 要闻 · 人民币资产 06-27
#   拟收购光通信公司，SpaceX获批 聚焦 · SpaceX
#   下周外盘看点 … OPEC+月度会议召开。 10分钟前
# get_text(" ") then concatenates that metadata onto the headline. The guards
# below strip ONLY the trailing relative-time / date suffix and a leading or
# trailing "section ·" breadcrumb — never mid-title text — so the rendered
# title (and its duplicated l-en/l-zh spans) stays clean.
_DOTCHARS = "·•・‧∙"
_TITLE_DOT = rf"[{_DOTCHARS}]"
# Known section labels — used only for the LEADING breadcrumb (whose tail is the
# real headline, so it must be gated to avoid eating a genuine "X · Y" title).
_TITLE_SECTION = (r"要闻|快讯|滚动|资讯|公告|头条|财经|新闻|宏观|评论|行情|国内|国际|"
                  r"深度|独家|原创|聚焦|基金|保险|券商|银行|公司|产业|产业资讯|科技|"
                  r"汽车|医药|地产|能源|消费|港股|美股|A股|市场|观点|专栏")
_TITLE_TIME_SUFFIX = re.compile(
    r"\s+(?:"
    r"刚刚|\d+\s*分钟前|\d+\s*小时前|\d+\s*天前|"
    r"前天\s*\d{1,2}:\d{2}|昨天\s*\d{1,2}:\d{2}|今天\s*\d{1,2}:\d{2}|"
    r"\d{4}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?|"
    r"\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?"
    r")$"
)
# Trailing breadcrumb: a short "<label> · <tail>" glued at the very end. Native
# pages use dozens of category names, so match any short non-space label/tail
# either side of the middot rather than enumerate them — the trailing ` · `
# between two short segments is the reliable breadcrumb signal.
_TITLE_BREADCRUMB_SUFFIX = re.compile(
    rf"\s+[^\s{_DOTCHARS}]{{2,8}}\s*{_TITLE_DOT}\s*[^\s{_DOTCHARS}]{{1,12}}$"
)
_TITLE_SECTION_PREFIX = re.compile(
    rf"^\s*(?:{_TITLE_SECTION})\s*{_TITLE_DOT}\s*"
)


def _clean_title(title: str) -> str:
    """A clean headline with native-page breadcrumb + relative-time metadata
    stripped. Conservative: removes only leading/trailing metadata, never
    mid-title content. Safe on English/official titles (CN tokens won't match)."""
    s = " ".join(str(title or "").split())
    prev = None
    while s and s != prev:                  # peel stacked suffixes (要闻 · X 06-27)
        prev = s
        s = _TITLE_TIME_SUFFIX.sub("", s)
        s = _TITLE_BREADCRUMB_SUFFIX.sub("", s)
        s = s.rstrip()
    return _TITLE_SECTION_PREFIX.sub("", s).strip()


def _importance(title: str, summary: str = "", theme: str = "macro", source_tier: str = "",
                source_name: str = "", source: str = "",
                wire_important: bool = False) -> tuple[int, str, list[str]]:
    blob = f"{title} {summary}"
    low = blob.lower()
    score = 22
    reasons: list[str] = []
    sw, source_reason = _source_weight(source_tier, source_name, source)
    if sw:
        score += sw
        reasons.append(source_reason)
    # 金十/华尔街见闻 red-flag their own market-moving flashes (important==1 /
    # score>=2) — a vendor editorial judgment worth a nudge, applied BEFORE the
    # off-China damp so a flagged foreign flash still ranks as context, not lead.
    if wire_important:
        score += 8
        reasons.append("wire-flagged high impact")
    hi = [k for k in HIGH_IMPACT_TERMS if _has_term(blob, low, k)]
    med = [k for k in MEDIUM_IMPACT_TERMS if _has_term(blob, low, k)]
    if hi:
        score += min(42, 14 * len(hi))
        reasons.append("tier-1 China macro term")
    if med:
        score += min(18, 6 * len(med))
        reasons.append("market-sensitive term")
    if theme in {"monetary", "credit", "policy", "markets", "growth", "inflation"}:
        score += 8
        reasons.append("dashboard core theme")
    if theme == "macro" and not hi and not med:
        score -= 8
        reasons.append("low title-level China macro specificity")
    # Global-macro relays on the high-volume CN wires (波兰央行/巴西CPI/英国FCA…)
    # are legitimate CONTEXT but must rank below on-the-ground China stories.
    # Multiplicative (not additive) so stacked generic terms (央行+降息 in a
    # Poland easing flash) can never out-rank an anchored China story.
    if source in _GATED_SOURCES and not _is_china_anchored(blob):
        score = int(score * 0.6)
        reasons.append("global macro relay (non-China)")
    score = max(0, min(100, score))
    band = "high" if score >= 68 else "medium" if score >= 48 else "low"
    return score, band, reasons or ["context"]


def enrich_item(h: dict) -> dict:
    title = h.get("title", "")
    summary = h.get("summary", "")
    theme = h.get("theme") or classify_theme(f"{title} {summary}") or "macro"
    source_tier = h.get("source_tier") or ("official" if h.get("source") == "official" else "wire")
    score, band, reasons = _importance(title, summary, theme, source_tier, h.get("source_name", ""), h.get("source", ""),
                                       wire_important=bool(h.get("wire_important")))
    text = f"{title} {summary} {h.get('source_name','')}"
    ticker_hits = _ticker_hits(text)
    channels = _channels(text) or ([theme] if theme != "macro" else [])
    native_bonus = 8 if h.get("source_lang") == "zh" or h.get("source") in {"eastmoney", "cn_news_page"} else 0
    intel = max(0, min(100, score + _freshness_points(h.get("time", "")) + native_bonus + (4 if len(channels) >= 2 else 0) + (3 if ticker_hits else 0)))
    out = dict(h)
    out.update({
        "theme": theme,
        "importance_score": score,
        "intelligence_score": intel,
        "importance": band,
        "importance_reasons": reasons,
        "channels": channels,
        "tickers": [hit["ticker"] for hit in ticker_hits],
        "ticker_reasons": {hit["ticker"]: hit["reason"] for hit in ticker_hits},
        "related_tickers": ticker_hits,
        "source_tier": source_tier,
        "source_lang": h.get("source_lang", "zh" if h.get("source") == "eastmoney" else "en"),
        "time": _clean_time(h.get("time", ""), title),
    })
    if out.get("source_lang") == "zh":
        out.setdefault("title_zh", title)
        if summary:
            out.setdefault("summary_zh", summary)
    return out


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", "", (t or ""))[:40]


# Newsletter/digest URLs are multi-story roundups (e.g. SCMP's /plus/ vertical:
# "Nvidia gets China boost, Iran ceasefire breaks, GDP release") — they stack
# high-impact terms from several unrelated stories, out-scoring every real
# headline, and must never be candidates (let alone the hero).
_DIGEST_URL_TOKENS = ("scmp.com/plus/",)

# High-volume realtime flash wires ALWAYS require a macro-theme keyword hit —
# their tier must not grant the trusted-context theme-gate bypass that the
# low-volume curated pages get (a wire pumps hundreds of off-topic flashes/day).
_GATED_SOURCES = {"eastmoney", "cn_wire"}

# China-relevance anchor for wire flashes. The native wires relay plenty of
# global macro (波兰央行/巴西CPI/英国FCA…) that legitimately passes the macro-theme
# gate as CONTEXT but must not lead the page or outrank on-the-ground China
# stories. 央行/证监会-style tokens only anchor when NOT prefixed by a foreign
# country (英国央行 is the Bank of England, not the PBoC).
_FOREIGN_CB = re.compile(
    r"(?:英国|美国|欧洲|欧元区|日本|韩国|澳洲|澳大利亚|新西兰|加拿大|波兰|俄罗斯|巴西|印度|"
    r"土耳其|瑞士|瑞典|挪威|丹麦|墨西哥|阿根廷|南非|泰国|印尼|菲律宾|越南|马来西亚|"
    r"哈萨克斯坦|沙特|以色列|伊朗|埃及)(?:央行|中央银行|证监会|财政部|统计局)")
# Unambiguously-Chinese anchors — safe in any context.
_CN_ANCHOR_STRONG = (
    "中国", "中方", "我国", "A股", "沪深", "上证", "深证", "科创板", "创业板",
    "北交所", "港股", "人民币", "人民银行", "中美", "北京", "上海", "深圳", "国务院",
    "国常会", "政治局", "证监会", "银保监", "金融监管总局", "发改委", "工信部",
    "商务部", "两会", "国资委", "中概", "沪指", "台海", "南海",
    "China", "Chinese", "PBOC", "PBoC", "yuan", "renminbi", "Beijing", "A-share")
# Institution tokens that DEFAULT to China's but get borrowed for foreign bodies
# in relayed copy (英国央行 / a UK story calling HM Treasury 财政部) — trusted only
# when NO foreign institution shares the story's context.
_CN_ANCHOR_WEAK = ("央行", "中央银行", "财政部", "统计局", "全国")


def _is_china_anchored(text: str) -> bool:
    """True when a headline is about China (vs a global-macro relay on a CN wire).
    Foreign-institution phrases (英国央行…) are neutralized before the scan; bare
    央行/财政部-class tokens only anchor when the story has NO foreign-institution
    context at all (a UK piece renders HM Treasury as plain 财政部). PURE."""
    blob = text or ""
    neut = _FOREIGN_CB.sub("", blob)
    if any(tok in neut for tok in _CN_ANCHOR_STRONG):
        return True
    if _FOREIGN_CB.search(blob):
        return False
    return any(tok in neut for tok in _CN_ANCHOR_WEAK)


def _is_digest_url(url: str) -> bool:
    u = (url or "").lower()
    return any(tok in u for tok in _DIGEST_URL_TOKENS)


def _shingles2(title: str) -> set:
    n = _norm_title(title)
    return {n[i:i + 2] for i in range(len(n) - 1)} if len(n) >= 2 else set()


def _promote_native_lead(kept: list[dict]) -> list[dict]:
    """Move the top-ranked CHINA-ANCHORED Chinese-native item to the hero slot
    (index 0), keeping the rest of the ranking stable. On-the-ground 中文 China
    coverage should lead the page whenever any is present; a global-macro relay on
    a CN wire (波兰央行…) or an English wire story never takes the hero on
    term-density alone. Falls back to the top zh item, then no-op. PURE."""
    pick = None
    for i, h in enumerate(kept):
        if h.get("source_lang") != "zh":
            continue
        if _is_china_anchored(f"{h.get('title', '')} {h.get('summary', '')}"):
            pick = i
            break
        if pick is None:
            pick = i                       # best zh fallback if none is anchored
    if pick:
        kept = [kept[pick]] + kept[:pick] + kept[pick + 1:]
    return kept


def filter_flashes(items: list[dict], cfg: dict | None = None) -> list[dict]:
    """Deterministic pipeline over raw flashes: macro-theme relevance gate + tag ->
    dedup -> recency rank -> top-N. PURE (takes {title,summary,url,time} dicts)."""
    cfg = cfg or {}
    top_n = int(cfg.get("max_show", 12))
    min_score = int(cfg.get("min_importance_score", 34))
    kept: list[dict] = []
    seen: set[str] = set()
    kept_sh: list[set] = []
    for a in items:
        title = (a.get("title") or "").strip()
        summary = (a.get("summary") or "").strip()
        if _is_digest_url(a.get("url", "")):
            continue                                   # multi-story roundup -> dropped
        theme = classify_theme(title + " " + summary)
        trusted_context = a.get("source_tier") in {"official", "wire", "global_wire", "china_native"} or a.get("source") in {"official", "gdelt", "news_rss", "news_page", "cn_news_page"}
        if a.get("source") in _GATED_SOURCES:
            trusted_context = False                    # wires never bypass the gate
        if theme is None and not trusted_context:
            continue                                   # non-macro flash -> dropped
        theme = theme or a.get("theme") or "macro"
        key = _norm_title(title)
        if not key or key in seen:
            continue                                   # dedup (exact normalized title)
        # cross-wire near-dup: the same story lands on several wires with small
        # title variants (波兰央行委员： vs 波兰央行委员Kotecki：) — collapse via
        # 2-gram Jaccard against already-kept titles (first wire in wins).
        sh = _shingles2(title)
        if sh and any(csh and (len(sh & csh) / len(sh | csh)) >= 0.75 for csh in kept_sh):
            continue
        source = a.get("source", "eastmoney")
        default_tier = "domestic_wire" if source == "eastmoney" else "china_native" if source == "cn_news_page" else "wire"
        enriched = enrich_item({"title": title, "summary": summary, "url": a.get("url", ""),
                     "time": a.get("time", ""), "theme": theme,
                     "source": source,
                     "source_name": a.get("source_name", "Eastmoney"),
                     "source_lang": a.get("source_lang", "zh" if source in {"eastmoney", "cn_news_page"} else "en"),
                     "source_tier": a.get("source_tier", default_tier),
                     "wire_important": bool(a.get("wire_important"))})
        if enriched.get("importance_score", 0) < min_score:
            continue
        seen.add(key)
        kept_sh.append(sh)
        kept.append(enriched)
    kept.sort(key=lambda h: (
        int(h.get("intelligence_score", h.get("importance_score", 0)) or 0),
        int(h.get("importance_score", 0) or 0),
        _parse_dt(h.get("time", "")) or datetime.min.replace(tzinfo=timezone.utc),
    ), reverse=True)
    return kept[:top_n]


def _synthesis(headlines: list[dict]) -> dict:
    """Holistic feed texture for the China dashboard/Mastermind hand-off. Pure
    summary of already-filtered context news; never a scoring input."""
    if not headlines:
        return {
            "high_impact_count": 0, "top_channels": [], "top_tickers": [],
            "top_themes": [], "source_mix": [], "dominant_channel": "",
            "read": "No high-signal China macro tape passed the current filter.",
            "read_zh": "当前过滤条件下无高信号中国宏观信息。",
        }
    channels = Counter(c for h in headlines for c in (h.get("channels") or []))
    tickers = Counter(t for h in headlines for t in (h.get("tickers") or []))
    themes = Counter(h.get("theme", "macro") for h in headlines)
    sources = Counter(h.get("source_tier", "unknown") for h in headlines)
    high = sum(1 for h in headlines if h.get("importance") == "high")
    dom_channel = channels.most_common(1)[0][0] if channels else ""
    dom_theme = themes.most_common(1)[0][0] if themes else "macro"
    # bilingual plain-word read line (no raw slugs — doctrine Law 2)
    ch_en, ch_zh = _slug_label(dom_channel or dom_theme)
    mix = [(_tier_label(k), v) for k, v in sources.most_common(3)]
    read = (f"{high} high-impact China items; dominant channel {ch_en}; sources "
            + ", ".join(f"{t[0]} {v}" for t, v in mix))
    read_zh = (f"{high} 条中国高影响信息；主导渠道：{ch_zh}；来源："
               + "、".join(f"{t[1]} {v}" for t, v in mix))
    # channel chips carry bilingual labels; `name` stays the raw slug for
    # machine consumers (additive — templates fall back to name on old artifacts)
    top_channels = []
    for k, v in channels.most_common(7):
        en, zh = _slug_label(k)
        top_channels.append({"name": k, "count": v, "label_en": en, "label_zh": zh})
    return {
        "high_impact_count": high,
        "avg_importance": round(sum(float(h.get("importance_score", 0) or 0) for h in headlines) / len(headlines), 1),
        "top_channels": top_channels,
        "top_tickers": [{"ticker": k, "count": v} for k, v in tickers.most_common(9)],
        "top_themes": [{"theme": k, "count": v} for k, v in themes.most_common(7)],
        "source_mix": [{"tier": k, "count": v} for k, v in sources.most_common(5)],
        "dominant_channel": dom_channel,
        "dominant_theme": dom_theme,
        "read": read,
        "read_zh": read_zh,
    }


def _attach_translations(headlines: list[dict], cfg: dict | None = None) -> list[dict]:
    """Bilingual spans for the kept feed: EN items gain title_zh/summary_zh, zh
    items gain title_en/summary_en (both directions cached; either degrades to
    the original text via the template's `or` fallback). Never raises."""
    if not headlines:
        return headlines
    try:
        from engine import news_translate
        titles = [h.get("title", "") for h in headlines]
        summaries = [h.get("summary", "") for h in headlines]
        title_zh = news_translate.translate_to_zh(titles)
        title_en = news_translate.translate_to_en(titles)
        nonempty_summaries = [s for s in summaries if s]
        summary_zh = news_translate.translate_to_zh(nonempty_summaries)
        summary_en = news_translate.translate_to_en(nonempty_summaries)
        si = 0
        out = []
        for h, tz, te, s in zip(headlines, title_zh, title_en, summaries, strict=False):
            hh = dict(h)
            if tz:
                hh["title_zh"] = tz
            elif hh.get("source_lang") == "zh":
                hh["title_zh"] = hh.get("title", "")
            if te and te != hh.get("title"):
                hh["title_en"] = te
            if s:
                sz = summary_zh[si] if si < len(summary_zh) else None
                se = summary_en[si] if si < len(summary_en) else None
                si += 1
                if sz:
                    hh["summary_zh"] = sz
                elif hh.get("source_lang") == "zh":
                    hh["summary_zh"] = s
                if se and se != s:
                    hh["summary_en"] = se
            out.append(hh)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("china news translation skipped: %s", e)
        return headlines


def _cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("cache_dir", "data/china_news/flash_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"flash_{d.isoformat()}.json"


def _official_cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("official_cache_dir", "data/china_news/official_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"official_v2_{d.isoformat()}.json"


def _wire_cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("wire_cache_dir", "data/china_news/wire_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"gdelt_v2_{d.isoformat()}.json"


def _news_cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("news_cache_dir", "data/china_news/news_rss_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"news_rss_v2_{d.isoformat()}.json"


def _local(tag: str) -> str:
    return tag.split("}")[-1].lower()


def _xml_text(el, *names: str) -> str:
    wanted = {n.lower() for n in names}
    for child in el:
        if _local(child.tag) in wanted and child.text:
            return html.unescape(child.text.strip())
    return ""


def _parse_feed_date(s: str) -> str:
    if not s:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return _parse_dateish(s) or s


def _parse_news_feed(xml_text: str, feed: dict) -> list[dict]:
    root = ET.fromstring(xml_text)
    nodes = [el for el in root.iter() if _local(el.tag) in {"item", "entry"}]
    out: list[dict] = []
    for it in nodes[:35]:
        title = _xml_text(it, "title")
        link = _xml_text(it, "link")
        if not link:
            for child in it:
                if _local(child.tag) == "link":
                    link = child.attrib.get("href", "")
                    break
        summary = _xml_text(it, "description", "summary")
        when = _parse_feed_date(_xml_text(it, "pubDate", "updated", "published", "date"))
        if not title:
            continue
        out.append({
            "title": title, "summary": summary, "url": urljoin(feed["url"], link),
            "time": when, "theme": classify_theme(f"{title} {summary}") or feed.get("theme") or "macro",
            "source": feed.get("source", "news_rss"),
            "source_name": feed.get("name", "News RSS"),
            "source_tier": feed.get("tier", "global_wire"),
            "source_lang": feed.get("source_lang", "en"),
        })
    return out


# akshare column -> our field (fuzzy; akshare occasionally renames)
def _row_to_item(row: dict) -> dict:
    def pick(*names):
        for n in names:
            for k, v in row.items():
                ks = str(k)
                if ks == n or n in ks:
                    return v
        return ""
    return {"title": str(pick("标题", "title") or ""),
            "summary": str(pick("摘要", "内容", "summary", "content") or ""),
            "time": str(pick("发布时间", "时间", "time", "datetime") or ""),
            "url": str(pick("链接", "url", "link") or "")}


def _fetch_flashes(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Recent Eastmoney 全球财经快讯 flashes. Returns (raw_items, degraded_reason).
    Cached with a TTL; akshare imported lazily; NEVER raises."""
    today = today or date.today()
    cache = _cache_path(cfg, today)
    ttl = cfg.get("cache_ttl_hours", 12) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("items", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass

    items: list[dict] = []
    reason: str | None = None
    try:
        import akshare as ak
        fn = getattr(ak, "stock_info_global_em", None)
        if fn is None:
            reason = "akshare_no_endpoint"
        else:
            raw = fn()
            if raw is None or len(raw) == 0:
                reason = "no_flashes"
            else:
                rows = raw.head(int(cfg.get("max_records", 60))).to_dict("records")
                items = [_row_to_item(r) for r in rows]
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("china_news flash fetch failed (%s)", e)
        reason = "fetch_error"
    try:
        cache.write_text(json.dumps({"items": items, "degraded_reason": reason},
                                    ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return items, reason


def _parse_dateish(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if not m:
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", text)
    if not m:
        return ""                          # no date -> '' (never echo the raw input)
    y, mo, da = [int(x) for x in m.groups()]
    try:
        return date(y, mo, da).isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _fetch_official_pages(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    today = today or date.today()
    cache = _official_cache_path(cfg, today)
    ttl = cfg.get("official_cache_ttl_hours", cfg.get("cache_ttl_hours", 12)) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("items", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass
    pages = cfg.get("official_pages") or OFFICIAL_PAGES
    items: list[dict] = []
    failures = 0
    try:
        import requests
        from bs4 import BeautifulSoup
        for page in pages:
            try:
                r = requests.get(page["url"], timeout=15,
                                 headers={"User-Agent": "macro-dashboard/1.0 (research)"})
                if r.status_code != 200:
                    failures += 1
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    raw_title = re.sub(r"^\s*\d+\.?", "", " ".join(a.get_text(" ", strip=True).split()))
                    title = _clean_title(raw_title)
                    if len(title) < 8:
                        continue
                    if title.lower() in {"latest releases", "release calendar", "international cooperation", "understanding statistics"}:
                        continue
                    href = urljoin(page["url"], a["href"])
                    nearby = " ".join([raw_title, a.parent.get_text(" ", strip=True) if a.parent else ""])
                    when = _parse_dateish(nearby)
                    has_iso_date = bool(when and re.match(r"20\d{2}-\d{2}-\d{2}", when))
                    if when and re.match(r"20\d{2}-\d{2}-\d{2}", when):
                        try:
                            if date.fromisoformat(when) < today - timedelta(days=int(cfg.get("official_window_days", 45))):
                                continue
                        except Exception:  # noqa: BLE001
                            pass
                    title_theme = classify_theme(title)
                    if not title_theme and not has_iso_date:
                        continue
                    theme = title_theme or page.get("theme") or "macro"
                    # Sanitise at write time so corrupted time fields (HTML page content
                    # concatenated into `when` by _parse_dateish) never persist in cache
                    # across TTL cycles.  See audit finding §PIT-write-guard.
                    items.append({"title": title, "summary": "", "url": href,
                                  "time": _clean_time(when or "", title),
                                  "theme": theme, "source": "official",
                                  "source_name": page.get("name", "Official"),
                                  "source_tier": page.get("tier", "official")})
            except Exception:  # noqa: BLE001
                failures += 1
    except Exception:  # noqa: BLE001
        failures = len(pages)
    reason = "official_fetch_error" if failures == len(pages) and not items else None
    try:
        cache.write_text(json.dumps({"items": items, "degraded_reason": reason}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return items, reason


# native CN portals (notably finance.sina.com.cn) serve `text/html` with NO charset
# in the HTTP header, so requests falls back to ISO-8859-1 and `r.text` mojibakes
# every CJK glyph (健康中国 -> "å¥åº·ä¸­å½"). Sniff the in-document <meta charset>
# instead and decode the raw bytes ourselves.
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.I)


def _decode_page(content: bytes, content_type: str = "") -> str:
    """Decode fetched HTML bytes honoring the page's real charset.

    Order of preference: an explicit HTTP `charset=`, else the document's
    `<meta charset>`/`Content-Type` declaration, else UTF-8. gb2312/gbk are decoded
    as their gb18030 superset so rare glyphs still resolve, and decoding always uses
    errors='replace' so a bad guess degrades to replacement chars, never an
    exception. PURE — no network, no requests/bs4 dependency."""
    enc = None
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        mm = _META_CHARSET_RE.search(content[:4096])
        if mm:
            enc = mm.group(1).decode("ascii", "ignore")
    enc = (enc or "utf-8").strip().lower()
    if enc in {"gb2312", "gbk", "gb-2312"}:
        enc = "gb18030"   # strict superset; ships with CPython
    try:
        return content.decode(enc, errors="replace")
    except (LookupError, TypeError):
        return content.decode("utf-8", errors="replace")


def _is_concept_nav_link(href: str) -> bool:
    """Sina concept-/sector-board navigation anchors
    (vip.stock.finance.sina.com.cn/mkt/#chgn_*, #gn_*) are board hubs, not news
    stories — their link text is a bare board name (健康中国 / 上海自贸). The page
    domain `finance.sina.com.cn` is a substring of the vip host, so they sail past
    the domain filter; drop them explicitly."""
    try:
        parts = urlsplit(href)
    except Exception:  # noqa: BLE001
        return False
    return (parts.netloc.lower().startswith("vip.stock.finance.sina.com.cn")
            and parts.path.rstrip("/").endswith("/mkt")
            and bool(parts.fragment))


def _fetch_news_pages(cfg: dict, today: date | None = None) -> tuple[list[dict], int]:
    today = today or date.today()
    pages = cfg.get("news_pages") or NEWS_PAGES
    items: list[dict] = []
    failures = 0
    window_days = int(cfg.get("news_window_days", cfg.get("wire_window_days", 5)))
    try:
        import requests
        from bs4 import BeautifulSoup
        for page in pages:
            try:
                r = requests.get(page["url"], timeout=12,
                                 headers={"User-Agent": "macro-dashboard/1.0 (research)"})
                if r.status_code != 200:
                    failures += 1
                    continue
                soup = BeautifulSoup(_decode_page(r.content, r.headers.get("Content-Type", "")), "html.parser")
                domain = page.get("domain") or re.sub(r"^www\.", "", re.sub(r"^https?://", "", page["url"]).split("/")[0]).lower()
                source_lang = page.get("source_lang", "en")
                added = 0
                for a in soup.find_all("a", href=True):
                    raw_title = " ".join(a.get_text(" ", strip=True).split())
                    title = _clean_title(raw_title)
                    if len(title) < 12:
                        continue
                    href = urljoin(page["url"], a["href"])
                    if domain and domain not in href:
                        continue
                    if _is_concept_nav_link(href):
                        continue
                    when = _parse_dateish(f"{raw_title} {href}")
                    if when:
                        try:
                            if date.fromisoformat(when) < today - timedelta(days=window_days):
                                continue
                        except Exception:  # noqa: BLE001
                            pass
                    theme = classify_theme(title) or page.get("theme") or "macro"
                    if source_lang != "zh" and theme == "macro" and "china" not in title.lower() and not when:
                        continue
                    # Sanitise at write time — same PIT-write-guard as _fetch_official_pages.
                    items.append({"title": title, "summary": "", "url": href,
                                  "time": _clean_time(when or "", title),
                                  "theme": theme, "source": page.get("source", "news_page"),
                                  "source_name": page.get("name", "News page"),
                                  "source_tier": page.get("tier", "global_wire"),
                                  "source_lang": source_lang})
                    added += 1
                    if added >= int(cfg.get("news_page_max_per_source", 45)):
                        break
            except Exception:  # noqa: BLE001
                failures += 1
    except Exception:  # noqa: BLE001
        failures = len(pages)
    return items, failures


def _fetch_news_feeds(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Direct China-focused media RSS/pages. This is the non-GDELT wire fallback:
    SCMP/Nikkei feeds and Caixin pages, still filtered by the deterministic gate."""
    today = today or date.today()
    cache = _news_cache_path(cfg, today)
    ttl = cfg.get("news_cache_ttl_hours", cfg.get("cache_ttl_hours", 12)) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("items", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass
    feeds = cfg.get("news_feeds") or NEWS_FEEDS
    items: list[dict] = []
    failures = 0
    window_days = int(cfg.get("news_window_days", cfg.get("wire_window_days", 5)))
    try:
        import requests
        for feed in feeds:
            try:
                r = requests.get(feed["url"], timeout=10,
                                 headers={"User-Agent": "macro-dashboard/1.0 (research)"})
                if r.status_code != 200:
                    failures += 1
                    continue
                for item in _parse_news_feed(r.text, feed):
                    dt = _parse_dt(item.get("time", ""))
                    if dt and dt.date() < today - timedelta(days=window_days):
                        continue
                    items.append(item)
            except Exception:  # noqa: BLE001
                failures += 1
    except Exception:  # noqa: BLE001
        failures = len(feeds)
    page_items, page_failures = _fetch_news_pages(cfg, today) if cfg.get("use_news_pages", True) else ([], 0)
    items.extend(page_items)
    failures += page_failures
    total_sources = len(feeds) + (len(cfg.get("news_pages") or NEWS_PAGES) if cfg.get("use_news_pages", True) else 0)
    reason = "news_rss_fetch_error" if failures == total_sources and not items else None
    try:
        cache.write_text(json.dumps({"items": items, "degraded_reason": reason}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return items, reason


def _fetch_cn_wires(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Native CN JSON wires (华尔街见闻/金十/格隆汇) via the shared engine/cn_newswires
    fetcher (its own per-day cache serves this panel AND the intel bus). Items map to
    the page candidate shape: china_native tier, zh lang, REAL publisher timestamps
    (so freshness ranking finally works for the native leg). Degrade-to-empty."""
    if not cfg.get("use_cn_json_wires", True):
        return [], None
    try:
        from engine import cn_newswires
        raw = cn_newswires.fetch_all(today=today)
    except Exception as e:  # noqa: BLE001
        log.warning("china_news: cn_newswires unavailable (%s)", e)
        return [], "cn_wire_fetch_error"
    items = []
    for a in raw:
        items.append({"title": a.get("title", ""), "summary": a.get("summary", ""),
                      "url": a.get("url", ""), "time": a.get("time", ""),
                      "source": "cn_wire",
                      "source_name": a.get("source_name", a.get("source", "CN wire")),
                      "source_tier": "china_native",
                      "source_lang": a.get("source_lang", "zh"),
                      "wire_important": bool(a.get("wire_important"))})
    return items, (None if items else "cn_wire_no_headlines")


def _gdelt_query(cfg: dict) -> str:
    terms = cfg.get("wire_query_terms") or GDELT_QUERY_TERMS
    # Query is intentionally broad; source allowlist + deterministic macro theme
    # gate below do the precision work.
    return "(" + " OR ".join(terms) + f") sourcelang:{cfg.get('wire_lang', 'eng')}"


def _fetch_wire_gdelt(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Global reputable-source China macro wire via GDELT. This fills the gap between
    official releases and Eastmoney flashes: Reuters/FT/SCMP/Caixin-style market
    interpretation. Best-effort, cached, never raises.

    Delegates HTTP, throttling, and retry handling to engine.gdelt_client so
    all GDELT callers share a single cross-process pacing lock (GDELT 5s/IP rule;
    nine callers without shared throttle caused a penalty-box incident 2026-06-20)."""
    from engine import gdelt_client as _gc
    today = today or date.today()
    cache = _wire_cache_path(cfg, today)
    ttl = int(cfg.get("wire_cache_ttl_hours", cfg.get("cache_ttl_hours", 12))) * 3600

    # cache read — china_news stores under key 'items', not 'articles'
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                cached = blob.get("items")
                if cached is not None:
                    return cached, blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass

    win = int(cfg.get("wire_window_days", cfg.get("window_days", 4)))
    end = datetime(today.year, today.month, today.day, 23, 59, 59)
    start = end - timedelta(days=win)
    params = {"query": _gdelt_query(cfg), "mode": "artlist", "format": "json",
              "maxrecords": str(cfg.get("wire_max_records", 160)), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    items: list[dict] = []
    reason: str | None = None
    allow = [s.lower() for s in (cfg.get("wire_sources") or WIRE_SOURCES)]
    timeout_s = max(5, int(cfg.get("wire_timeout_s", 12)))
    try:
        raw_articles, gc_reason = _gc.get_articles(params, timeout=timeout_s)
        if raw_articles is None:
            raw_articles = []
        # map gdelt_client reason tokens to china_news's own tokens
        if gc_reason == "rate_limited":
            reason = "wire_rate_limited"
        elif gc_reason in ("fetch_error",):
            reason = "wire_fetch_error"
        elif gc_reason == "no_articles":
            reason = "wire_no_headlines"
        else:
            reason = gc_reason

        for a in raw_articles:
            dom = (a.get("domain") or "").lower()
            if allow and not any(s in dom for s in allow):
                continue
            title = a.get("title", "")
            items.append({"title": title, "summary": "", "url": a.get("url", ""),
                          "time": a.get("seendate", ""),
                          "theme": classify_theme(title) or "macro",
                          "source": "gdelt", "source_name": dom or "GDELT",
                          "source_tier": "wire"})
        if raw_articles and not items:
            reason = "wire_no_headlines"
        elif not raw_articles and not items and reason is None:
            reason = "wire_no_headlines"
    except Exception as e:  # noqa: BLE001
        log.warning("china_news gdelt wire fetch failed (%s)", e)
        reason = "wire_fetch_error"

    # Cache only when items are non-empty (INTENTIONAL: empty-success is transient
    # and should re-fetch rather than serve stale silence for the full TTL; failures
    # must never be cached to preserve retry on next nightly cycle).
    if items:
        try:
            cache.write_text(json.dumps({"items": items, "degraded_reason": reason},
                                        ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
    return items, reason


def flash_headlines(today: date | None = None) -> dict | None:
    """Filtered, theme-tagged, deduped recent macro flashes. None when the master
    switch is off. Never raises."""
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    raw, reason = _fetch_flashes(cfg, today)
    official, official_reason = _fetch_official_pages(cfg, today) if cfg.get("use_official_pages", True) else ([], None)
    news_rss, news_reason = _fetch_news_feeds(cfg, today) if cfg.get("use_news_feeds", True) else ([], None)
    wire, wire_reason = _fetch_wire_gdelt(cfg, today) if cfg.get("use_wire_gdelt", True) else ([], None)
    cn_wire, cn_wire_reason = _fetch_cn_wires(cfg, today)
    kept = _attach_translations(filter_flashes(official + cn_wire + news_rss + wire + raw, cfg), cfg)
    if cfg.get("native_lead", True):
        kept = _promote_native_lead(kept)
    synth = _synthesis(kept)
    n_all = len(raw) + len(official) + len(news_rss) + len(wire) + len(cn_wire)
    return {"schema": SCHEMA, "is_context_only": True, "source": "official_pages+cn_json_wires+news_rss+gdelt_wire+eastmoney_global_em",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "headlines": kept, "n_raw": n_all, "n_eastmoney": len(raw),
            "n_official": len(official), "n_news_rss": len(news_rss), "n_wire": len(wire),
            "n_cn_wire": len(cn_wire),
            "n_total_candidates": n_all,
            "n_kept": len(kept),
            "n_high_impact": synth.get("high_impact_count", 0),
            "top_channels": synth.get("top_channels", []),
            "top_tickers": synth.get("top_tickers", []),
            "synthesis": synth,
            "degraded_reason": (reason or official_reason or news_reason or wire_reason or cn_wire_reason) if not kept else None}


# --------------------------------------------------------------------------- #
# optional LLM brief (gated on flag AND key; provider-agnostic; default OFF)
# --------------------------------------------------------------------------- #
BRIEF_SYSTEM = (
    "You write a 2-3 sentence plain-中文 summary of the current China macro backdrop "
    "for a dashboard, using ONLY the provided filtered headlines and the official "
    "policy-tone context. This is background narration — it NEVER feeds any score, "
    "signal, regime or trade. Be factual and neutral; do NOT give advice, price "
    "targets or predictions. If the headlines are thin or off-topic, say the macro "
    "tape is quiet rather than inventing a story."
)


def _llm_ready(cfg: dict) -> bool:
    if not cfg.get("enabled", False) or not cfg.get("llm_brief", False):
        return False
    try:
        return bool(config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))
    except Exception:  # noqa: BLE001
        return False


def news_brief(headlines: list[dict] | None, tone_line: str = "") -> dict | None:
    """OPTIONAL one-paragraph narration of the filtered flashes + the policy-tone
    state. Default-off, gated on key, provider-agnostic (DeepSeek/Anthropic), degrade
    to None. Labeled context; never scored."""
    cfg = _cfg()
    if not _llm_ready(cfg) or not headlines:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
        base = cfg.get("base_url")
        client = anthropic.Anthropic(api_key=key, base_url=base) if base \
            else anthropic.Anthropic(api_key=key)
        lines = "\n".join(f"- [{h.get('theme', '')}] {h['title']}" for h in headlines[:12])
        user = (f"Policy tone: {tone_line or 'n/a'}\n"
                f"Filtered macro flashes:\n{lines}")
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-chat"), max_tokens=220,
            system=BRIEF_SYSTEM, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", "") == "text").strip()
        if not text:
            return None
        return {"text": text, "model": cfg.get("llm_model", "deepseek-chat"),
                "is_context_only": True}
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("china news brief failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# public: the combined panel view-model consumed by build_china.py
# --------------------------------------------------------------------------- #
def panel(asof: date | str | None = None) -> dict | None:
    """Assemble the china.html "📰 Macro news & policy tone" panel view-model:
    {tone, headlines, brief?, disclaimer*}. Returns None when BOTH legs are empty
    (so the template hides the panel cleanly). Never raises."""
    try:
        tone = policy_tone(asof)
        news = flash_headlines() if enabled() else None
        heads = (news or {}).get("headlines") or []
        if tone is None and not heads:
            return None
        tone_line = ""
        if tone:
            tone_line = f"{tone['label_en']} (z {tone['z']:+.2f}, {tone['n_days']}d)"
        brief = news_brief(heads, tone_line) if heads else None
        return {
            "schema": SCHEMA, "is_context_only": True,
            "asof": (str(asof) if asof else str(date.today())),
            "built": datetime.now(timezone.utc).isoformat(),
            "tone": tone, "news": news, "brief": brief,
            "theme_label": THEME_LABEL,
            "disclaimer": DISCLAIMER_TEXT, "disclaimer_zh": DISCLAIMER_TEXT_ZH,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_news.panel failed (%s)", e)
        return None
