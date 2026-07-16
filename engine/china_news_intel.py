"""China News powerhouse — multi-source wire + PIT event bus + importance scoring + tickers.

LEAF · CONTEXT-ONLY · KEYLESS · LLM-DEFAULT-OFF. The China sibling of engine/news_vector.py
and the richer successor to engine/china_news.py's single-wire flash panel. Nothing in the
China scoring core imports it; every public function returns plain data or None and NEVER
raises into the build. See research/CHINA_INTEL_POWERHOUSE.md §1.

Legs:
  1. PIT EVENT BUS — first-print, keep-FIRST append-only headline log across several free
     Chinese flash wires + English state RSS, theme-gated (China-narrative buckets),
     basket-tagged, A-share-TICKER-tagged, scheduled_ref-stamped, and scored at accrual time
     for IMPORTANCE (source tier × theme × high-impact keywords × event proximity × novelty,
     time-decayed) and per-item SENTIMENT. Stored at data/china_news_vector/events.parquet.
  2. MEDIA-SENTIMENT INDEX — CCTV 新闻联播 tone blended with a daily multi-source wire tone,
     z-scored over a trailing window (the SF-Fed Daily News Sentiment analog).
  3. OPTIONAL AI BRIEF — gated, default-off, degrade-to-keyless 中文 narration.

Importance/sentiment/ticker are display/context reads (word-bands on the UI, never a bare
number); they never feed a score, regime or allocation.

W2 migration (spec §2.5):
  • _norm_title / event_id / source_tier delegate to engine.qkernel (single source of truth).
  • tag_tickers delegates to engine.entity_resolver.resolve_cn (GENERIC_NOUNS single copy).
  • ingest() emits qbus rows (data/qbus/items.parquet) with _crawled_at, timestamp_quality,
    lang=zh for every new accrued event.
  • Missing-Tape baseline: TIER1 sources (official/state) carry body_sha256 on their qbus
    row so W4 can diff future body changes against the first-seen hash.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_news_intel.v1"

# Reuse the established Chinese macro buckets and PREPEND the distinctive narrative buckets;
# DEMOTE non-China geopolitics so Mid-East/Ukraine noise stops dominating. Order matters
# (first hit wins): China-relevant policy/geo/trade first, macro next, global geo LAST.
try:
    from engine.china_news import MACRO_THEMES as _BASE_THEMES, THEME_LABEL as _BASE_LABELS
except Exception:  # noqa: BLE001
    _BASE_THEMES, _BASE_LABELS = {}, {}

CHINA_NARRATIVE_THEMES: dict[str, list[str]] = {
    "china_geo": ["台海", "台湾", "南海", "解放军", "中美", "对华", "涉华"],
    "trade": ["关税", "贸易战", "出口管制", "反制", "脱钩", "实体清单", "反倾销",
              "WTO", "贸易摩擦", "加征"],
    "industrial_policy": ["国产替代", "信创", "自主可控", "产业政策", "大基金",
                          "新质生产力", "卡脖子", "补贴", "专精特新", "国产化"],
    **(_BASE_THEMES or {}),
    "global_geo": ["中东", "以色列", "伊朗", "俄乌", "俄罗斯", "加沙", "黎巴嫩",
                   "冲突", "战争", "局势", "停火"],
}
THEME_LABEL: dict[str, tuple[str, str]] = {
    "china_geo": ("China geo", "中国地缘"), "global_geo": ("Global geo", "全球地缘"),
    "trade": ("Trade", "贸易"), "industrial_policy": ("Industrial policy", "产业政策"),
    **(_BASE_LABELS or {}),
}

# Light entity map: cn_* baskets (ids MUST match data/baskets_china/membership.json — 22 ids,
# no cn_property). (id, en, zh, keywords). cn_defense keywords are AMBIGUOUS (军工/导弹/航天
# also fire on foreign-war headlines) so cn_defense is gated behind a China anchor below.
CN_BASKETS: list[tuple] = [
    ("cn_semis", "Semiconductors", "半导体", ["半导体", "芯片", "晶圆", "光刻", "存储芯片", "晶圆代工"]),
    ("cn_ai_compute", "AI Compute & Optics", "AI算力与光模块", ["算力", "人工智能", "大模型", "光模块", "AI芯片", "智算"]),
    ("cn_consumer_elec", "Consumer Electronics", "消费电子", ["消费电子", "手机", "面板", "果链", "立讯", "歌尔"]),
    ("cn_software", "Software & AI Apps", "软件与AI应用", ["软件", "SaaS", "云计算", "操作系统", "数据库", "应用软件"]),
    ("cn_battery", "Battery & Lithium", "锂电池", ["锂电", "电池", "动力电池", "储能", "正极", "负极", "电解液"]),
    ("cn_solar", "Solar & PV", "光伏", ["光伏", "硅料", "组件", "风电", "逆变器"]),
    ("cn_autos", "Autos", "汽车整车", ["汽车", "整车", "乘用车", "新能源车", "车企", "比亚迪"]),
    ("cn_defense", "Defense", "军工", ["军工", "国防", "航天", "导弹", "兵器"]),
    ("cn_robotics", "Robotics", "机器人", ["机器人", "人形机器人", "自动化", "减速器"]),
    ("cn_baijiu", "Baijiu", "白酒", ["白酒", "茅台", "五粮液", "酒企"]),
    ("cn_appliances", "Appliances", "家电", ["家电", "空调", "白电", "美的", "格力", "海尔"]),
    ("cn_food_bev", "Food & Beverage", "食品饮料", ["食品", "饮料", "乳业", "调味品", "食品饮料"]),
    ("cn_pharma_cxo", "Innovative Pharma & CXO", "创新药与CXO", ["创新药", "医药", "CXO", "生物医药", "药企"]),
    ("cn_med_devices", "Med Devices & TCM", "医疗器械与中药", ["医疗器械", "器械", "中药", "IVD", "医械"]),
    ("cn_banks", "Banks", "银行", ["银行", "信贷", "息差", "国有大行"]),
    ("cn_brokers", "Brokers", "券商", ["券商", "证券", "投行", "经纪"]),
    ("cn_insurers", "Insurers", "保险", ["保险", "险企", "保费", "寿险"]),
    ("cn_soe_value", "SOE Value 中特估", "中特估·央企", ["中特估", "央企", "国企改革", "市值管理"]),
    ("cn_gold", "Gold", "黄金", ["黄金", "金价", "贵金属", "金矿"]),
    ("cn_metals", "Nonferrous Metals", "有色金属", ["有色", "铜", "铝", "锌", "镍", "金属价格"]),
    ("cn_rare_earth", "Rare Earth & Magnets", "稀土永磁", ["稀土", "永磁", "磁材", "镨钕"]),
    ("cn_coal", "Coal", "煤炭", ["煤炭", "动力煤", "焦煤", "煤价"]),
]
BASKET_LABEL: dict[str, tuple[str, str]] = {bid: (en, zh) for (bid, en, zh, _kw) in CN_BASKETS}
_AMBIGUOUS_BASKETS = {"cn_defense"}   # require a China anchor word to tag

# China-relevance anchor — gates ambiguous tags + (optionally) trims off-China flashes.
CN_ANCHOR = ("中国", "中方", "A股", "沪", "深", "央行", "人民银行", "人民币", "中美", "北京",
             "商务部", "台海", "南海", "解放军", "出口管制", "实体清单", "证监会", "国务院",
             "发改委", "财政部", "工信部")

# importance model
HIGH_IMPACT_KW = ("降准", "降息", "RRR", "LPR", "MLF", "逆回购", "关税", "制裁", "出口管制",
                  "实体清单", "增持", "回购", "重组", "业绩预增", "业绩预亏", "中标", "停牌",
                  "退市", "定增", "并购", "国常会", "政治局")
THEME_WEIGHT = {"monetary": 1.0, "trade": 1.0, "industrial_policy": 1.0, "china_geo": 0.9,
                "credit": 0.9, "policy": 0.8, "growth": 0.7, "inflation": 0.7,
                "markets": 0.5, "fiscal": 0.5, "global_geo": 0.2}
TIER_W = {1: 1.0, 2: 0.6, 3: 0.3}
HALF_LIFE_H = 48.0

_TIER1 = ["news.cn", "xinhua", "chinadaily", "gov.cn", "pbc.gov.cn", "ndrc",
          "mofcom", "csrc", "stats.gov.cn", "cctv"]
_TIER2_SRC = ["em", "sina", "ths", "futu", "cls", "jin10", "yicai", "caixin",
              "eastmoney", "wallstreet", "gelonghui"]

_HIGH_IMPACT_CAL = {"LPR", "MLF", "PMI", "CPI", "PPI", "CREDIT", "GDP", "FXRES", "ACTIVITY"}

DISCLAIMER = (
    "Context only — not a signal. A first-print, point-in-time log of filtered China "
    "policy/market headlines (several free wires + state RSS, China-narrative themes only), "
    "importance-scored, ticker-tagged, plus a media-sentiment index (a z-score of a crude "
    "CCTV + wire tone proxy, read RELATIVE). Nothing here is an input to any score, signal, "
    "regime or allocation."
)
DISCLAIMER_ZH = (
    "仅作背景，非信号。这是经筛选的中国政策／市场头条的首次出现时间点日志（多个免费快讯源＋"
    "官方RSS，仅中国叙事主题），并附重要性评分、个股标记，以及媒体情绪指数（对央视＋快讯粗略基调"
    "代理的 z 标准化，按相对值解读）。其中没有任何内容会进入任何评分、信号、区制或配置。"
)

_COLUMNS = ("event_id", "first_seen_utc", "seendate", "title", "summary", "url", "domain",
            "source", "theme", "source_tier", "baskets", "tickers", "score", "sentiment",
            "scheduled_ref", "wire_important")


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    return config.load().get("china_news_intel", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _events_path() -> Path:
    p = config.data_dir() / "china_news_vector" / "events.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------- #
# W2 qkernel import (lazy, degrade to local fallbacks if unavailable).
# --------------------------------------------------------------------------- #
try:
    from engine import qkernel as _qk
    _HAS_QKERNEL = True
except Exception:  # noqa: BLE001
    _qk = None  # type: ignore[assignment]
    _HAS_QKERNEL = False


# --------------------------------------------------------------------------- #
# pure helpers (no network / no clock) — independently unit-tested
# --------------------------------------------------------------------------- #
def _norm_title(t: str) -> str:
    """Delegate to qkernel.norm_title (CJK path, 60-char cap). Falls back to the
    local implementation when qkernel is unavailable (leaf-import safety)."""
    if _HAS_QKERNEL:
        return _qk.norm_title(t, lang="zh")
    # local fallback (byte-compatible with qkernel CJK path)
    s = re.sub(r"[\s　]+", "", (t or "").lower())
    s = re.sub(r"[^\w一-鿿]", "", s)
    return s[:60]


def event_id(title: str, domain: str) -> str:
    """Delegate to qkernel.event_id (CJK, source=domain). Falls back to the local
    sha1(norm_title|domain) that was the pre-W2 implementation."""
    if _HAS_QKERNEL:
        return _qk.event_id(source=(domain or "").lower().strip(), url="",
                            title=title, lang="zh")
    basis = _norm_title(title) + "|" + (domain or "").lower().strip()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def classify_theme(text: str) -> str | None:
    blob = text or ""
    for theme, kws in CHINA_NARRATIVE_THEMES.items():
        if any(k in blob for k in kws):
            return theme
    return None


def tag_baskets(text: str) -> list[str]:
    """cn_* basket ids a headline references. Ambiguous baskets (cn_defense) require a China
    anchor word so foreign-war headlines stop false-tagging defense."""
    blob = text or ""
    anchored = any(a in blob for a in CN_ANCHOR)
    out = []
    for (bid, _en, _zh, kws) in CN_BASKETS:
        if any(k in blob for k in kws):
            if bid in _AMBIGUOUS_BASKETS and not anchored:
                continue
            out.append(bid)
    return out


@lru_cache(maxsize=1)
def _name_to_ticker() -> dict[str, str]:
    """中文 company name -> A-share ticker. Curated membership (288) wins over the broad
    analyst map (2,373). Names < 2 chars dropped. Cached, degrade-to-empty."""
    out: dict[str, str] = {}
    try:
        p = config.data_dir() / "baskets_china" / "membership.json"
        baskets = json.loads(p.read_text()).get("baskets", {})
        for b in baskets.values():
            for m in b.get("members", []):
                nm = str(m.get("name_zh") or "").strip()
                t = m.get("ticker")
                if t and len(nm) >= 2:
                    out.setdefault(nm, str(t))
    except Exception:  # noqa: BLE001
        pass
    try:
        from engine.china_altdata import _name_map
        for t, nm in (_name_map() or {}).items():
            nm = str(nm).strip()
            if nm and len(nm) >= 2:
                out.setdefault(nm, str(t))
    except Exception:  # noqa: BLE001
        pass
    return out


@lru_cache(maxsize=1)
def _names_by_len() -> list[str]:
    return sorted(_name_to_ticker().keys(), key=len, reverse=True)


# Chinese company names that are ALSO common nouns — they produce near-100% false
# positive tags when the name appears generically in a headline (e.g. "机器人" in
# "全球机器人产业大会开幕" tags 300024.SZ on every robotics-sector story).
# A blocklisted name is only allowed to tag when a 6-digit exchange code appears
# adjacent (within ~6 chars) in the title, e.g. "机器人(300024)一季度净利增长".
#
# Seeded from audit finding §ticker-generic-noun (机器人 measured 22/22 FP).
# Review other short/common 3-char names (e.g. 中芯, 天合, 海控) for addition.
#
# W2: the canonical copy now lives in engine.entity_resolver.GENERIC_NOUNS (spec
# §2.5) — this is a re-export so this module's tag_tickers keeps working while the
# blocklist has ONE source of truth. Degrade to the local seed if the shared module
# is unavailable (leaf import safety).
try:
    from engine.entity_resolver import GENERIC_NOUNS as _GENERIC_NOUN_NAMES
except Exception:  # noqa: BLE001
    _GENERIC_NOUN_NAMES = frozenset({"机器人"})

# Matches a 6-digit A-share exchange code in close proximity to the name match.
_ADJACENT_CODE_RE = re.compile(r"\d{6}")


def _has_adjacent_code(blob: str, name: str) -> bool:
    """Return True if a 6-digit exchange code appears within 10 characters of `name`
    in `blob`.  The window is intentionally generous to cover patterns like
    ``机器人(300024)`` where a bracket sits between the name and the code.
    This is the only override that allows a generic-noun name to tag."""
    idx = 0
    while True:
        pos = blob.find(name, idx)
        if pos == -1:
            return False
        window_start = max(0, pos - 10)
        window_end = min(len(blob), pos + len(name) + 10)
        window = blob[window_start:window_end]
        if _ADJACENT_CODE_RE.search(window):
            return True
        idx = pos + 1


def tag_tickers(text: str) -> list[str]:
    """A-share tickers a headline names. Delegates to entity_resolver.resolve_cn (the W2
    canonical resolver) so the GENERIC_NOUNS blocklist has one source of truth and the
    longest-match-first / subsumed-name suppression logic lives in one place.

    Falls back to the local longest-match loop when entity_resolver is unavailable.
    Returns ticker strings (sorted by confidence desc, deduped), preserving the existing
    list-of-ticker-strings contract. PURE. Never raises."""
    blob = text or ""
    if not blob:
        return []
    try:
        from engine.entity_resolver import resolve_cn
        hits = resolve_cn(blob)
        # resolve_cn returns sorted by confidence desc; extract just the ticker strings.
        return [h["ticker"] for h in hits]
    except Exception:  # noqa: BLE001
        pass
    # --- local fallback (pre-W2 path) ---
    nm2t = _name_to_ticker()
    out: list[str] = []
    seen_t: set[str] = set()
    matched: list[str] = []
    for nm in _names_by_len():
        if nm in blob:
            if any(nm in mm for mm in matched):   # subsumed by a longer match
                continue
            if nm in _GENERIC_NOUN_NAMES and not _has_adjacent_code(blob, nm):
                continue
            matched.append(nm)
            t = nm2t[nm]
            if t not in seen_t:
                seen_t.add(t)
                out.append(t)
    return out


def source_tier(source: str, domain: str) -> int:
    """Delegate to qkernel.source_tier (merged CN+EN table). Falls back to the
    local _TIER1/_TIER2_SRC lists when qkernel is unavailable."""
    if _HAS_QKERNEL:
        return _qk.source_tier(domain or "", source or "")
    key = (source or "").lower() + " " + (domain or "").lower()
    if any(s in key for s in _TIER1):
        return 1
    if any(s in key for s in _TIER2_SRC):
        return 2
    return 3


def is_surprise(scheduled_ref: str, seendate: str) -> bool:
    """True when the headline lands ON a scheduled high-impact event day (scheduled_ref tail)."""
    if not scheduled_ref or "@" not in scheduled_ref:
        return False
    ref_day = scheduled_ref.split("@", 1)[1][:10]
    return bool(ref_day) and ref_day == (seendate or "")[:10]


def importance_score(tier, scheduled_ref, seendate, theme, n_baskets, blob, hours_since) -> float:
    """Deterministic per-headline importance. PURE (hours injected). Higher = more important."""
    s = TIER_W.get(int(tier or 3), 0.3)
    s += 0.30 if scheduled_ref else 0.0
    s += 0.40 if is_surprise(scheduled_ref, seendate) else 0.0
    s += 0.50 if any(k in (blob or "") for k in HIGH_IMPACT_KW) else 0.0
    s += (THEME_WEIGHT.get(theme, 0.5) - 0.5)
    s += min(0.30, 0.10 * int(n_baskets or 0))
    s *= math.exp(-max(0.0, float(hours_since or 0.0)) / HALF_LIFE_H)
    return round(s, 3)


def importance_band(score: float) -> tuple[str, str]:
    if score >= 1.6:
        return "High", "重磅"
    if score >= 0.9:
        return "Elevated", "重要"
    return "Routine", "一般"


def _item_sentiment(blob: str) -> float:
    """Signed [-1,1] tone from the CCTV policy-tone lexicon. PURE."""
    try:
        from collectors.china_news import _NEG, _POS
        b = blob or ""
        pos = sum(b.count(w) for w in _POS)
        neg = sum(b.count(w) for w in _NEG)
        if pos + neg == 0:
            return 0.0
        return round((pos - neg) / (pos + neg), 3)
    except Exception:  # noqa: BLE001
        return 0.0


# Release TYPE -> the narrative themes an article can plausibly be ABOUT when it
# reacts to that release: the release's own macro channel, plus the rate-path
# (monetary) and market-reaction (markets) buckets. tech/geo/politics/… never get
# stamped — those are the headline-shock themes that must stay UNstamped (the
# MN-06 leak stamped ACTIVITY on 461 same-window articles incl. Mid-East wires,
# and here the stamp feeds importance_score at accrual: +0.30/+0.40 baked into
# the PIT store). Fail-closed: a type missing here stamps nothing (test-enforced
# to cover _HIGH_IMPACT_CAL). Mirrors news_vector._SCHEDULED_REF_THEMES.
_SCHEDULED_REF_THEMES: dict[str, frozenset[str]] = {
    "LPR":      frozenset({"monetary", "markets"}),
    "MLF":      frozenset({"monetary", "markets"}),
    "FXRES":    frozenset({"monetary", "markets"}),
    "CPI":      frozenset({"inflation", "monetary", "markets"}),
    "PPI":      frozenset({"inflation", "monetary", "markets"}),
    "PMI":      frozenset({"growth", "monetary", "markets"}),
    "GDP":      frozenset({"growth", "monetary", "markets"}),
    "ACTIVITY": frozenset({"growth", "monetary", "markets"}),
    "CREDIT":   frozenset({"credit", "monetary", "markets"}),
}


def _scheduled_ref_for(seendate_iso: str, scheduled: dict[str, str],
                       theme: str = "") -> str:
    """'TYPE@YYYY-MM-DD' when the article is plausibly the calendar-explained flow
    of a high-impact release: the release fell ON the article date or the DAY
    BEFORE (reaction window — a release tomorrow cannot explain today's flow), AND
    the article's theme sits in that release's macro channel. Else ''. PURE.
    Forward-only: accrual is keep-FIRST, so already-accrued rows keep their
    historical stamps and importance scores — never rewritten."""
    try:
        d = date.fromisoformat((seendate_iso or "")[:10])
    except (ValueError, TypeError):
        return ""
    for delta in (0, -1):
        key = (d + timedelta(days=delta)).isoformat()
        rtype = scheduled.get(key)
        if rtype and theme in _SCHEDULED_REF_THEMES.get(rtype, frozenset()):
            return f"{rtype}@{key}"
    return ""


def _hours_since(seendate, now) -> float:
    try:
        import pandas as pd
        sd = pd.to_datetime(seendate, errors="coerce", utc=True)
        nw = pd.to_datetime(now, errors="coerce", utc=True)
        if pd.isna(sd) or pd.isna(nw):
            return 0.0
        return max(0.0, (nw - sd).total_seconds() / 3600.0)
    except Exception:  # noqa: BLE001
        return 0.0


# A publish timestamp must never carry the headline or the article URL — some
# native CN wires concatenate "<title> … <href>" into the date field.
_TIME_URLISH = re.compile(r"https?://|www\.", re.I)


def _clean_time(value: str, title: str = "") -> str:
    """Guard: a clean publish timestamp, or '' when the field is contaminated with
    the article URL or the headline text. Whitespace-collapsed; leaves genuine
    timestamps (ISO / 'YYYY-MM-DD HH:MM' / RFC822 / 'MM-DD') untouched."""
    s = " ".join(str(value or "").split())
    if not s or _TIME_URLISH.search(s):
        return ""
    t = " ".join(str(title or "").split())
    if len(t) >= 8 and t[:8] in s:
        return ""
    return s


def build_records(articles: list[dict], scheduled: dict[str, str],
                  first_seen_utc: str) -> list[dict]:
    """Raw flashes/RSS items -> theme-gated, basket+ticker-tagged, importance+sentiment-scored
    event records. PURE (no network/clock; first_seen_utc injected).

    No low-value junk gate here (unlike news_vector MN-05): assessed 2026-07-16 —
    CN format-junk (午评 recaps / 涨停复盘 / listicles) is ~1% of the accrued store
    because the theme gate + curated flash wires already filter it, and
    news_common's EN patterns don't transfer to CJK (substring traps, e.g.
    集中签约 ⊃ 中签). Revisit only if a junk class measurably grows."""
    out: list[dict] = []
    seen: set[str] = set()
    for a in articles:
        title = (a.get("title") or "").strip()
        summary = (a.get("summary") or "").strip()
        blob = title + " " + summary
        theme = classify_theme(blob)
        if theme is None:
            continue
        dom = (a.get("domain") or "").lower()
        eid = event_id(title, dom or (a.get("source") or ""))
        if not title or eid in seen:
            continue
        seen.add(eid)
        seendate = _clean_time(a.get("seendate") or a.get("time") or "", title)
        tier = source_tier(a.get("source", ""), dom)
        baskets = tag_baskets(blob)
        sref = _scheduled_ref_for(str(seendate), scheduled, theme)
        hrs = _hours_since(seendate, first_seen_utc)
        out.append({
            "event_id": eid, "first_seen_utc": first_seen_utc, "seendate": str(seendate),
            "title": title, "summary": summary[:280], "url": a.get("url", ""), "domain": dom,
            "source": a.get("source", ""), "theme": theme, "source_tier": tier,
            "baskets": ",".join(baskets), "tickers": ",".join(tag_tickers(blob)),
            "score": importance_score(tier, sref, str(seendate), theme, len(baskets), blob, hrs),
            "sentiment": _item_sentiment(blob),
            "scheduled_ref": sref,
            # vendor red-flag from the JSON wires (金十 important==1 / 华尔街见闻
            # score>=2); False for sources without the concept. Display/context only.
            "wire_important": bool(a.get("wire_important")),
        })
    return out


def accrue(existing, new_records: list[dict]):
    """Append-only merge, keep-FIRST on event_id. PURE."""
    import pandas as pd
    new_df = pd.DataFrame(new_records, columns=list(_COLUMNS))
    if existing is None or len(existing) == 0:
        merged = new_df
    else:
        merged = pd.concat([existing.reindex(columns=list(_COLUMNS)), new_df],
                           ignore_index=True)
    merged = merged.drop_duplicates(subset=["event_id"], keep="first")
    merged = merged.sort_values(["first_seen_utc", "event_id"]).reset_index(drop=True)
    # wire_important arrived with the W-flags migration: pre-migration rows carry
    # NaN after the reindex — normalize to a clean bool column (unknown = False)
    # so the parquet dtype stays stable instead of object-with-NaN.
    if "wire_important" in merged.columns:
        merged["wire_important"] = merged["wire_important"].fillna(False).astype(bool)
    return merged


# --------------------------------------------------------------------------- #
# near-duplicate clustering (same story across multiple wires)
# --------------------------------------------------------------------------- #
def _shingles(title: str) -> set:
    n = _norm_title(title)
    return {n[i:i + 2] for i in range(len(n) - 1)} if len(n) >= 2 else ({n} if n else set())


def cluster_events(rows: list[dict], thresh: float = 0.6) -> list[dict]:
    """Collapse near-duplicate headlines (Jaccard ≥ thresh, same theme + publish-day). Each
    representative = lowest source_tier then earliest first_seen; carries dup_count. PURE."""
    clusters: list[dict] = []
    sigs: list[tuple] = []
    for r in rows:
        sh = _shingles(r.get("title", ""))
        day = str(r.get("seendate", ""))[:10] or str(r.get("first_seen_utc", ""))[:10]
        theme = r.get("theme")
        placed = False
        for i, c in enumerate(clusters):
            csh, cday, ctheme = sigs[i]
            if theme == ctheme and day == cday and sh and csh:
                j = len(sh & csh) / len(sh | csh)
                if j >= thresh:
                    c["_members"].append(r)
                    placed = True
                    break
        if not placed:
            clusters.append({"_members": [r]})
            sigs.append((sh, day, theme))
    out: list[dict] = []
    for c in clusters:
        members = c["_members"]
        rep = sorted(members, key=lambda m: (int(m.get("source_tier") or 3),
                                             str(m.get("first_seen_utc") or "")))[0]
        rep = dict(rep)
        rep["dup_count"] = len(members)
        out.append(rep)
    return out


# --------------------------------------------------------------------------- #
# scheduled-release map (reuses the China event calendar — sibling LEAF)
# --------------------------------------------------------------------------- #
def _scheduled_map(today: date, back: int = 3, fwd: int = 3) -> dict[str, str]:
    try:
        from engine import china_event_calendar as cec
        evs = cec.china_macro_events(asof=today - timedelta(days=back),
                                     horizon_days=back + fwd)
        out: dict[str, str] = {}
        for ev in evs:
            if ev.get("type") in _HIGH_IMPACT_CAL:
                out.setdefault(ev["date"], ev["type"])
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("china scheduled map unavailable (%s)", e)
        return {}


# --------------------------------------------------------------------------- #
# build-time fetch — multi-source wires (akshare) + state RSS (stdlib). Cached.
# --------------------------------------------------------------------------- #
def _row_to_item(row: dict) -> dict:
    def pick(*names):
        for n in names:
            for k, v in row.items():
                if str(k) == n or n in str(k):
                    return v
        return ""
    return {"title": str(pick("标题", "title") or ""),
            "summary": str(pick("摘要", "内容", "summary", "content") or ""),
            "time": str(pick("发布时间", "时间", "time", "datetime") or ""),
            "url": str(pick("链接", "url", "link") or "")}


def _fetch_wires(cfg: dict) -> list[dict]:
    items: list[dict] = []
    try:
        import akshare as ak
    except Exception as e:  # noqa: BLE001
        log.warning("china_news_intel: akshare unavailable (%s)", e)
        return items
    cap = int(cfg.get("max_per_source", 60))
    for fn_name in (cfg.get("wire_sources") or ["stock_info_global_em"]):
        fn = getattr(ak, fn_name, None)
        if fn is None:
            continue
        try:
            raw = fn()
        except Exception as e:  # noqa: BLE001
            log.debug("china_news_intel wire %s failed: %s", fn_name, e)
            continue
        if raw is None or len(raw) == 0:
            continue
        src = fn_name.replace("stock_info_global_", "")
        for r in raw.head(cap).to_dict("records"):
            it = _row_to_item(r)
            it["source"] = src
            it["domain"] = ""
            items.append(it)
    return items


def _fetch_json_wires(cfg: dict) -> list[dict]:
    """Native CN JSON wires (华尔街见闻/金十/格隆汇) via the shared cn_newswires
    fetcher — one cached fetch serves this bus AND the china_news page panel.
    Degrade-to-empty; leaf-import safety."""
    if not cfg.get("use_json_wires", True):
        return []
    try:
        from engine import cn_newswires
        return cn_newswires.fetch_all()
    except Exception as e:  # noqa: BLE001
        log.warning("china_news_intel: cn_newswires unavailable (%s)", e)
        return []


def _fetch_rss(cfg: dict) -> list[dict]:
    import xml.etree.ElementTree as ET
    items: list[dict] = []
    for url in (cfg.get("rss_sources") or []):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "macro-dashboard/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                xml = resp.read()
            root = ET.fromstring(xml)
            host = urllib.parse.urlparse(url).netloc
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = (it.findtext("description") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                if not title:
                    continue
                items.append({"title": title, "summary": desc, "url": link,
                              "time": pub, "source": "rss", "domain": host})
        except Exception as e:  # noqa: BLE001
            log.debug("china_news_intel rss %s failed: %s", url, e)
            continue
    return items


def _cache_path(cfg: dict, d: date) -> Path:
    cdir = config.ROOT / cfg.get("cache_dir", "data/china_news/intel_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"intel_{d.isoformat()}.json"


def _fetch_all(cfg: dict, today: date) -> tuple[list[dict], str | None]:
    cache = _cache_path(cfg, today)
    ttl = int(cfg.get("cache_ttl_hours", 6)) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("items", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass
    items = _fetch_wires(cfg) + _fetch_json_wires(cfg) + _fetch_rss(cfg)
    reason = None if items else "no_headlines"
    try:
        cache.write_text(json.dumps({"items": items, "degraded_reason": reason},
                                    ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return items, reason


# --------------------------------------------------------------------------- #
# helpers: timestamp_quality classification and qbus row builder
# --------------------------------------------------------------------------- #
def _timestamp_quality(seendate: str, source: str) -> str:
    """Map a seendate + source to a qbus TIMESTAMP_QUALITY enum value.

    Rules (spec §2.5 / probe P2):
      • Empty / corrupted seendate (caught by _clean_time) → CRAWL_BOUNDED
      • RSS pubDate is a full RFC-822 timestamp (sub-day precision) → PUBLISHER_STATED
      • cn_newswires JSON wires carry the vendor's sub-minute publish stamp
        (unix epoch / Beijing wall clock, normalized to tz-aware ISO) → PUBLISHER_STATED
      • akshare wires provide a date at day-or-hour resolution → SNAPSHOT_DATE
        (day-level accuracy; we don't assert the exact publication minute)
    PURE."""
    if not seendate:
        return "CRAWL_BOUNDED"
    # RSS carries sub-day pubDate (RFC-822 / ISO); akshare dates are typically
    # "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" at best, so treat wire sources as SNAPSHOT.
    if (source or "").lower() in {"rss", "wallstreetcn", "jin10", "gelonghui"}:
        return "PUBLISHER_STATED"
    return "SNAPSHOT_DATE"


def _build_qbus_rows(records: list[dict], raw_articles: list[dict],
                     crawled_at: str) -> list[dict]:
    """Build qbus rows for a batch of scored CN events.

    - lang=zh (all items from this desk are Chinese)
    - _crawled_at injected from the ingest boundary (never read from clock here)
    - body_sha256 captured for TIER1 sources (Missing-Tape baseline: W4 will diff
      future bodies against this first-seen hash; the capture starts from now so
      the baseline accumulates without a recrawler)
    - timestamp_quality per _timestamp_quality()
    PURE given injected crawled_at. Never raises.
    """
    # Build a url→body index from the raw articles for the Missing-Tape hash capture.
    url_to_body: dict[str, str] = {}
    for a in (raw_articles or []):
        url = str(a.get("url") or "").strip()
        body = str(a.get("summary") or a.get("content") or "").strip()
        if url and body:
            url_to_body[url] = body

    qbus_rows: list[dict] = []
    for rec in records:
        tier = int(rec.get("source_tier") or 3)
        url = str(rec.get("url") or "")
        # Missing-Tape: capture body hash for official/state (tier 1) sources only.
        # body_sha256 is empty string when no body is available (non-blocking).
        bhash = ""
        if tier == 1:
            body = url_to_body.get(url, "") or str(rec.get("summary") or "")
            try:
                from engine.qbus import body_sha256 as _sha256
                bhash = _sha256(body) if body else ""
            except Exception:  # noqa: BLE001
                pass

        tq = _timestamp_quality(str(rec.get("seendate") or ""),
                                str(rec.get("source") or ""))
        qbus_rows.append({
            "desk": "china_news_intel",
            "source": str(rec.get("source") or ""),
            "source_tier": tier,
            "lang": "zh",
            "url": url,
            "title": str(rec.get("title") or ""),
            "body_sha256": bhash,
            "seendate": str(rec.get("seendate") or ""),
            "_crawled_at": crawled_at,
            "timestamp_quality": tq,
            "entities": [t for t in str(rec.get("tickers") or "").split(",") if t],
            "themes": [th for th in [rec.get("theme")] if th],
            "importance_raw": float(rec.get("score") or 0.0),
        })
    return qbus_rows


# --------------------------------------------------------------------------- #
# public: daily ingest (fetch -> gate -> score -> keep-FIRST accrue + qbus emit)
# --------------------------------------------------------------------------- #
def ingest(today: date | None = None) -> dict | None:
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    try:
        import pandas as pd
        today = today or date.today()
        raw, reason = _fetch_all(cfg, today)
        scheduled = _scheduled_map(today)
        # _crawled_at is stamped once at the ingest boundary (spec PIT discipline).
        crawled_at = datetime.now(timezone.utc).isoformat()
        records = build_records(raw, scheduled, crawled_at)
        path = _events_path()
        existing = pd.read_parquet(path) if path.exists() else None
        before = 0 if existing is None else len(existing)
        merged = accrue(existing, records)
        merged.to_parquet(path, index=False)
        n_new = len(merged) - before

        # Emit to the unified qbus item store. Only new records (not already
        # present via keep-FIRST) are emitted; qbus itself is also keep-FIRST
        # on item_id, so re-emitting the full batch is safe and idempotent.
        n_bus = 0
        if records:
            try:
                from engine import qbus
                qbus_rows = _build_qbus_rows(records, raw, crawled_at)
                qbus.append_items(qbus_rows, assign_keys=True)
                n_bus = len(qbus_rows)
                log.debug("china_news_intel: emitted %d rows to qbus", n_bus)
            except Exception as e:  # noqa: BLE001
                log.warning("china_news_intel: qbus emit failed (%s) — continuing", e)

        log.info("china_news_intel: %d raw -> %d gated -> %d new (%d total) %d→qbus",
                 len(raw), len(records), n_new, len(merged), n_bus)
        return {"schema": SCHEMA, "is_context_only": True, "asof": today.isoformat(),
                "n_raw": len(raw), "n_gated": len(records), "n_new": n_new,
                "n_total": int(len(merged)), "n_qbus": n_bus,
                "degraded_reason": reason if not records else None}
    except Exception as e:  # noqa: BLE001
        log.error("china_news_intel ingest failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# media-sentiment index — CCTV tone blended with the multi-source wire tone
# --------------------------------------------------------------------------- #
def _blended_tone_series():
    try:
        import pandas as pd
        cols = []
        for name in ("cctv_tone", "wire_tone"):
            df = store.read("china_news", name)
            if df is not None and not df.empty and "tone" in df.columns:
                cols.append(pd.to_numeric(df["tone"], errors="coerce").rename(name))
        if not cols:
            return None
        joined = pd.concat(cols, axis=1).sort_index()
        return joined.mean(axis=1).dropna()
    except Exception as e:  # noqa: BLE001
        log.debug("china_news_intel blended tone failed (%s)", e)
        return None


def _publish_ts(df):
    """Publish timestamp per row (seendate, fallback first_seen_utc) as tz-aware Series."""
    import pandas as pd
    sd = pd.to_datetime(df.get("seendate"), errors="coerce", utc=True) if "seendate" in df else None
    fs = pd.to_datetime(df["first_seen_utc"], errors="coerce", utc=True)
    return fs if sd is None else sd.fillna(fs)


def _n_events(days: int = 7) -> int | None:
    try:
        import pandas as pd
        path = _events_path()
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return 0
        ts = _publish_ts(df)
        cutoff = pd.Timestamp(date.today() - timedelta(days=days), tz="UTC")
        return int((ts >= cutoff).sum())
    except Exception:  # noqa: BLE001
        return None


def sentiment(asof: date | str | None = None) -> dict | None:
    try:
        from engine import china_news as cn
        s = _blended_tone_series()
        if s is None or len(s) == 0:
            return None
        cfg = _cfg()
        stats = cn._tone_stats(s, cfg.get("sentiment_window", 90),
                               cfg.get("sentiment_smooth", 5))
        if not stats:
            return None
        band, en, zh = cn._tone_band(stats)
        return {"schema": SCHEMA, "is_context_only": True,
                "value": stats["value"], "z": stats["z"], "n_days": stats["n"],
                "band": band, "label_en": en, "label_zh": zh,
                "n_events_7d": _n_events(7),
                "asof": (str(asof) if asof else str(s.index.max().date()))}
    except Exception as e:  # noqa: BLE001
        log.error("china_news_intel.sentiment failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# display reads — feed (importance-ranked, clustered, ticker-tagged) + scheduled-ahead
# --------------------------------------------------------------------------- #
def _f(row, key, default=None):
    """Safe field read from an itertuples row OR dict (old parquet may lack new cols)."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def feed(today: date | None = None, days: int = 7, top_n: int | None = None) -> dict | None:
    """Recent accrued events: near-dup clustered, importance-ranked, basket+ticker tagged,
    with a scheduled-ahead strip. CONTEXT-ONLY. None if nothing accrued yet. Never raises."""
    try:
        import pandas as pd
        today = today or date.today()
        cfg = _cfg()
        top_n = int(top_n or cfg.get("max_show", 14))
        path = _events_path()
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return None
        df = df.reindex(columns=[c for c in _COLUMNS])  # tolerate old schema
        ts = _publish_ts(df)
        cutoff = pd.Timestamp(today - timedelta(days=days), tz="UTC")
        recent = df[ts >= cutoff]
        if recent.empty:
            recent = df.sort_values("first_seen_utc").tail(top_n * 4)
        rows = recent.to_dict("records")
        # near-dup clustering
        clustered = cluster_events(rows)
        # tallies from DISTINCT clusters; exclude global_geo from headline tallies
        by_theme: dict[str, int] = {}
        basket_ct: dict[str, int] = {}
        for r in clustered:
            th = r.get("theme")
            if th and th != "global_geo":
                by_theme[th] = by_theme.get(th, 0) + 1
            for bid in [x for x in str(r.get("baskets") or "").split(",") if x]:
                basket_ct[bid] = basket_ct.get(bid, 0) + 1
        by_theme = dict(sorted(by_theme.items(), key=lambda kv: -kv[1]))
        # rank items by importance score, then recency
        def _score(r):
            s = r.get("score")
            try:
                return float(s) if s is not None and not pd.isna(s) else -1.0
            except (TypeError, ValueError):
                return -1.0
        clustered.sort(key=lambda r: (_score(r), str(r.get("first_seen_utc") or "")), reverse=True)
        items = []
        for r in clustered[:top_n]:
            th = r.get("theme")
            tl = THEME_LABEL.get(th, (th, th))
            sc = _score(r)
            ib = importance_band(sc) if sc >= 0 else ("Routine", "一般")
            items.append({
                "title": r.get("title"), "url": r.get("url"), "domain": r.get("domain"),
                "source": r.get("source"), "theme": th, "theme_en": tl[0], "theme_zh": tl[1],
                "tier": int(r.get("source_tier") or 3),
                "baskets": [x for x in str(r.get("baskets") or "").split(",") if x],
                "tickers": [x for x in str(r.get("tickers") or "").split(",") if x],
                "score": round(sc, 2) if sc >= 0 else None,
                "importance_en": ib[0], "importance_zh": ib[1],
                "surprise": bool(r.get("scheduled_ref") and is_surprise(str(r.get("scheduled_ref")), str(r.get("seendate") or ""))),
                "wire_important": (False if r.get("wire_important") is None
                                   or (isinstance(r.get("wire_important"), float) and pd.isna(r.get("wire_important")))
                                   else bool(r.get("wire_important"))),
                "sentiment": (None if r.get("sentiment") is None or (isinstance(r.get("sentiment"), float) and pd.isna(r.get("sentiment"))) else round(float(r.get("sentiment")), 2)),
                "dup_count": int(r.get("dup_count") or 1),
                "scheduled_ref": r.get("scheduled_ref") or "",
            })
        scheduled_ahead = []
        try:
            from engine import china_event_calendar as cec
            for ev in cec.high_impact_strip(horizon_days=14)[:5]:
                md_zh = ev.get("md")
                try:
                    dd = date.fromisoformat(ev.get("date"))
                    md_zh = f"{dd.month}月{dd.day}日"
                except (ValueError, TypeError):
                    pass
                scheduled_ahead.append({"type": ev.get("type"), "date": ev.get("date"),
                                        "name_en": ev.get("name_en"), "name_zh": ev.get("name_zh"),
                                        "md": ev.get("md"), "md_zh": md_zh})
        except Exception:  # noqa: BLE001
            pass
        return {"schema": SCHEMA, "is_context_only": True, "asof": today.isoformat(),
                "window_days": days, "n_recent": int(len(clustered)),
                "top_themes": list(by_theme.keys())[:6],
                "by_theme": {k: int(v) for k, v in by_theme.items()},
                "by_basket": {k: int(v) for k, v in
                              sorted(basket_ct.items(), key=lambda kv: -kv[1])},
                "scheduled_ahead": scheduled_ahead, "items": items,
                "theme_label": {k: list(v) for k, v in THEME_LABEL.items()},
                "basket_label": {k: list(v) for k, v in BASKET_LABEL.items()},
                "disclaimer": DISCLAIMER, "disclaimer_zh": DISCLAIMER_ZH}
    except Exception as e:  # noqa: BLE001
        log.error("china_news_intel.feed failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# optional LLM brief (gated on flag AND key; provider-agnostic; default OFF)
# --------------------------------------------------------------------------- #
_BRIEF_SYSTEM = (
    "You write a 2-3 sentence plain-中文 summary of the current China macro/policy backdrop "
    "for a dashboard, using ONLY the provided filtered headlines and the media-sentiment "
    "state. This is background narration — it NEVER feeds any score, signal, regime or trade. "
    "Be factual and neutral; no advice, price targets or predictions. If the headlines are "
    "thin or off-topic, say the tape is quiet rather than inventing a story."
)


def _llm_ready(cfg: dict) -> bool:
    if not (cfg.get("enabled") and cfg.get("llm_brief")):
        return False
    try:
        return bool(config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))
    except Exception:  # noqa: BLE001
        return False


def news_brief(items: list[dict] | None, sentiment_line: str = "") -> dict | None:
    cfg = _cfg()
    if not _llm_ready(cfg) or not items:
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
        lines = "\n".join(f"- [{i.get('theme', '')}] {i.get('title', '')}" for i in items[:12])
        user = f"Media sentiment: {sentiment_line or 'n/a'}\nFiltered headlines:\n{lines}"
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-chat"), max_tokens=220,
            system=_BRIEF_SYSTEM, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", "") == "text").strip()
        if not text:
            return None
        return {"text": text, "model": cfg.get("llm_model", "deepseek-chat"),
                "is_context_only": True}
    except Exception as e:  # noqa: BLE001
        log.warning("china_news_intel brief failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# public: the combined panel view-model for the china_news page
# --------------------------------------------------------------------------- #
def panel(asof: date | str | None = None) -> dict | None:
    try:
        sent = sentiment(asof)
        fd = feed()
        if sent is None and (fd is None or not fd.get("items")):
            return None
        sline = ""
        if sent:
            sline = f"{sent['label_en']} (z {sent['z']:+.2f}, {sent['n_days']}d)"
        brief = news_brief((fd or {}).get("items"), sline) if fd else None
        return {"schema": SCHEMA, "is_context_only": True,
                "asof": (str(asof) if asof else str(date.today())),
                "built": datetime.now(timezone.utc).isoformat(),
                "sentiment": sent, "feed": fd, "brief": brief,
                "disclaimer": DISCLAIMER, "disclaimer_zh": DISCLAIMER_ZH}
    except Exception as e:  # noqa: BLE001
        log.error("china_news_intel.panel failed (%s)", e)
        return None
