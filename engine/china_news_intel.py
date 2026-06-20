"""China News powerhouse — multi-source wire + PIT event bus + media-sentiment.

LEAF · CONTEXT-ONLY · KEYLESS · LLM-DEFAULT-OFF. The China sibling of
engine/news_vector.py, and the richer successor to engine/china_news.py's single-wire
flash panel. Nothing in the China scoring core imports it; every public function returns
plain data or None and NEVER raises into the build. See research/CHINA_INTEL_POWERHOUSE.md §1.

Three legs, any of which may be absent:

  1. PIT EVENT BUS — a first-print, point-in-time, append-only headline log accrued with
     keep-FIRST semantics (the same look-ahead defence as news_vector) across several free
     Chinese flash wires (akshare stock_info_global_em/sina/ths/futu) plus keyless English
     state-wire RSS (Xinhua / China Daily, stdlib XML). Each kept headline is theme-gated
     (Chinese narrative buckets), source-tiered, basket-tagged, and scheduled_ref-stamped
     against the China macro/policy calendar. Stored at data/china_news_vector/events.parquet.

  2. MEDIA-SENTIMENT INDEX — the SF-Fed Daily News Sentiment analog for China: the CCTV
     新闻联播 policy tone (collectors/china_news.py) BLENDED with a daily multi-source wire
     tone (collectors/china_news_wire.py), smoothed and z-scored over a trailing window.
     Read RELATIVE, never as an absolute sentiment.

  3. OPTIONAL AI BRIEF — gated, default-off, degrade-to-keyless one-paragraph 中文 narration
     of the filtered feed + sentiment state. The only AI; labeled context, never scored.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_news_intel.v1"

# Reuse the established Chinese macro buckets and PREPEND the distinctive narrative
# (policy/geo/trade) buckets so a 关税/制裁/台海 headline classifies there rather than the
# catch-all fiscal/markets buckets. Order matters (first hit wins).
try:
    from engine.china_news import MACRO_THEMES as _BASE_THEMES, THEME_LABEL as _BASE_LABELS
except Exception:  # noqa: BLE001 — keep the engine importable even if sibling moves
    _BASE_THEMES, _BASE_LABELS = {}, {}

CHINA_NARRATIVE_THEMES: dict[str, list[str]] = {
    "geopolitics": ["台海", "台湾", "地缘", "冲突", "战争", "军事", "俄乌", "俄罗斯",
                    "中东", "以色列", "伊朗", "南海", "局势"],
    "trade": ["关税", "贸易战", "出口管制", "反制", "脱钩", "实体清单", "反倾销",
              "WTO", "贸易摩擦", "加征"],
    "industrial_policy": ["国产替代", "信创", "自主可控", "产业政策", "大基金",
                          "新质生产力", "卡脖子", "补贴", "专精特新", "国产化"],
    **(_BASE_THEMES or {}),
}
THEME_LABEL: dict[str, tuple[str, str]] = {
    "geopolitics": ("Geopolitics", "地缘"), "trade": ("Trade", "贸易"),
    "industrial_policy": ("Industrial policy", "产业政策"),
    **(_BASE_LABELS or {}),
}

# Light entity map: tag a headline to the most newsworthy cn_* baskets/themes (free,
# deterministic). Not exhaustive — a display join, never a score. (id, en, zh, keywords)
CN_BASKETS: list[tuple] = [
    ("cn_semis", "Semiconductors", "半导体", ["半导体", "芯片", "晶圆", "光刻", "存储芯片"]),
    ("cn_ai_compute", "AI compute", "AI算力", ["算力", "人工智能", "大模型", "光模块", "AI"]),
    ("cn_battery", "Battery / NEV", "锂电/新能源", ["锂电", "电池", "新能源车", "动力电池", "储能"]),
    ("cn_solar", "Solar", "光伏", ["光伏", "硅料", "组件", "风电"]),
    ("cn_defense", "Defense", "军工", ["军工", "国防", "航天", "导弹"]),
    ("cn_robotics", "Robotics", "机器人", ["机器人", "人形机器人", "自动化"]),
    ("cn_property", "Property", "地产", ["地产", "楼市", "房地产", "房企", "保交楼"]),
    ("cn_banks", "Banks", "银行", ["银行", "信贷", "息差"]),
    ("cn_brokers", "Brokers", "券商", ["券商", "证券", "投行"]),
    ("cn_baijiu", "Baijiu", "白酒", ["白酒", "茅台", "五粮液"]),
    ("cn_pharma_cxo", "Innovative pharma", "创新药", ["创新药", "医药", "CXO", "生物医药"]),
    ("cn_gold", "Gold", "黄金", ["黄金", "金价", "贵金属"]),
    ("cn_soe_value", "SOE value 中特估", "中特估", ["中特估", "央企", "国企改革", "市值管理"]),
]

# source tiering — official state wire (1) > pro financial wire (2) > aggregator (3).
_TIER1 = ["news.cn", "xinhua", "chinadaily", "gov.cn", "pbc.gov.cn", "ndrc",
          "mofcom", "csrc", "stats.gov.cn", "cctv"]
_TIER2_SRC = ["em", "sina", "ths", "futu", "cls", "jin10", "yicai", "caixin",
              "eastmoney", "wallstreet"]

_HIGH_IMPACT_CAL = {"LPR", "MLF", "PMI", "CPI", "PPI", "CREDIT", "GDP", "FXRES", "ACTIVITY"}

DISCLAIMER = (
    "Context only — not a signal. A first-print, point-in-time log of filtered China "
    "policy/market headlines (several free wires + state RSS, narrative themes only) plus a "
    "media-sentiment index (a z-score of a crude CCTV + wire tone proxy, read RELATIVE). "
    "Nothing here is an input to any score, signal, regime or allocation."
)
DISCLAIMER_ZH = (
    "仅作背景，非信号。这是经筛选的中国政策／市场头条的首次出现时间点日志（多个免费快讯源＋"
    "官方RSS，仅叙事主题），并附媒体情绪指数（对央视＋快讯粗略基调代理的 z 标准化，按相对值解读）。"
    "其中没有任何内容会进入任何评分、信号、区制或配置。"
)

_COLUMNS = ("event_id", "first_seen_utc", "seendate", "title", "url", "domain",
            "source", "theme", "source_tier", "baskets", "scheduled_ref")


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
# pure helpers (no network / no clock) — independently unit-tested
# --------------------------------------------------------------------------- #
def _norm_title(t: str) -> str:
    """CJK-safe normalization: drop whitespace + punctuation, keep CJK + alnum, lowercase."""
    s = re.sub(r"[\s　]+", "", (t or "").lower())
    s = re.sub(r"[^\w一-鿿]", "", s)
    return s[:60]


def event_id(title: str, domain: str) -> str:
    basis = _norm_title(title) + "|" + (domain or "").lower().strip()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def classify_theme(text: str) -> str | None:
    """First China narrative theme a headline matches, else None (off-narrative -> drop)."""
    blob = text or ""
    for theme, kws in CHINA_NARRATIVE_THEMES.items():
        if any(k in blob for k in kws):
            return theme
    return None


def tag_baskets(text: str) -> list[str]:
    """cn_* basket ids a headline plausibly references (deterministic keyword map)."""
    blob = text or ""
    out = [bid for (bid, _en, _zh, kws) in CN_BASKETS if any(k in blob for k in kws)]
    return out


def source_tier(source: str, domain: str) -> int:
    key = (source or "").lower() + " " + (domain or "").lower()
    if any(s in key for s in _TIER1):
        return 1
    if any(s in key for s in _TIER2_SRC):
        return 2
    return 3


def _scheduled_ref_for(seendate_iso: str, scheduled: dict[str, str]) -> str:
    try:
        d = date.fromisoformat((seendate_iso or "")[:10])
    except (ValueError, TypeError):
        return ""
    for delta in (0, -1, 1):
        key = (d + timedelta(days=delta)).isoformat()
        if key in scheduled:
            return f"{scheduled[key]}@{key}"
    return ""


def build_records(articles: list[dict], scheduled: dict[str, str],
                  first_seen_utc: str) -> list[dict]:
    """Raw flashes/RSS items -> deterministic, theme-gated, basket-tagged event records.
    PURE (no network/clock; first_seen_utc injected so accrual is testable)."""
    out: list[dict] = []
    seen: set[str] = set()
    for a in articles:
        title = (a.get("title") or "").strip()
        summary = (a.get("summary") or "").strip()
        theme = classify_theme(title + " " + summary)
        if theme is None:
            continue
        dom = (a.get("domain") or "").lower()
        eid = event_id(title, dom or (a.get("source") or ""))
        if not title or eid in seen:
            continue
        seen.add(eid)
        seendate = a.get("seendate") or a.get("time") or ""
        out.append({
            "event_id": eid, "first_seen_utc": first_seen_utc, "seendate": str(seendate),
            "title": title, "url": a.get("url", ""), "domain": dom,
            "source": a.get("source", ""), "theme": theme,
            "source_tier": source_tier(a.get("source", ""), dom),
            "baskets": ",".join(tag_baskets(title + " " + summary)),
            "scheduled_ref": _scheduled_ref_for(str(seendate), scheduled),
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
    return merged


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
    except Exception as e:  # noqa: BLE001 — degrade, never raise
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
        except Exception as e:  # noqa: BLE001 — per-source isolation
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


def _fetch_rss(cfg: dict) -> list[dict]:
    """Keyless English state-wire RSS via stdlib XML (no feedparser dep). Best-effort."""
    import xml.etree.ElementTree as ET
    items: list[dict] = []
    for url in (cfg.get("rss_sources") or []):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "macro-dashboard/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — fixed allowlist
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
        except Exception as e:  # noqa: BLE001 — per-feed isolation, never raise
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
    items = _fetch_wires(cfg) + _fetch_rss(cfg)
    reason = None if items else "no_headlines"
    try:
        cache.write_text(json.dumps({"items": items, "degraded_reason": reason},
                                    ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return items, reason


# --------------------------------------------------------------------------- #
# public: daily ingest (fetch -> gate -> keep-FIRST accrue)
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
        now_iso = datetime.now(timezone.utc).isoformat()
        records = build_records(raw, scheduled, now_iso)
        path = _events_path()
        existing = pd.read_parquet(path) if path.exists() else None
        before = 0 if existing is None else len(existing)
        merged = accrue(existing, records)
        merged.to_parquet(path, index=False)
        n_new = len(merged) - before
        log.info("china_news_intel: %d raw -> %d gated -> %d new (%d total)",
                 len(raw), len(records), n_new, len(merged))
        return {"schema": SCHEMA, "is_context_only": True, "asof": today.isoformat(),
                "n_raw": len(raw), "n_gated": len(records), "n_new": n_new,
                "n_total": int(len(merged)),
                "degraded_reason": reason if not records else None}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_news_intel ingest failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# media-sentiment index — CCTV tone blended with the multi-source wire tone
# --------------------------------------------------------------------------- #
def _blended_tone_series():
    """Mean of available daily tones (CCTV + wire), outer-joined on date. None if neither."""
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


def _n_events(days: int = 7) -> int | None:
    try:
        import pandas as pd
        path = _events_path()
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return 0
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return int((df["first_seen_utc"].astype(str) >= cutoff).sum())
    except Exception:  # noqa: BLE001
        return None


def sentiment(asof: date | str | None = None) -> dict | None:
    """Media-sentiment index = z-score of the blended (CCTV + wire) tone. None until
    history exists. Reuses china_news._tone_stats / _tone_band. Never raises."""
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
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_news_intel.sentiment failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# display reads — feed (themes + items + baskets) and the scheduled-ahead strip
# --------------------------------------------------------------------------- #
def feed(today: date | None = None, days: int = 7, top_n: int | None = None) -> dict | None:
    """Recent accrued events grouped by theme + basket, with a scheduled-ahead strip.
    CONTEXT-ONLY. None if nothing accrued yet. Never raises."""
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
        cutoff = (today - timedelta(days=days)).isoformat()
        recent = df[df["first_seen_utc"].astype(str) >= cutoff]
        if recent.empty:
            recent = df.sort_values("first_seen_utc").tail(top_n * 3)
        by_theme = (recent.groupby("theme").size().sort_values(ascending=False).to_dict())
        # basket tallies (explode the comma-joined basket ids)
        basket_ct: dict[str, int] = {}
        for b in recent["baskets"].astype(str):
            for bid in [x for x in b.split(",") if x]:
                basket_ct[bid] = basket_ct.get(bid, 0) + 1
        rows = []
        for r in recent.sort_values("first_seen_utc", ascending=False).head(top_n).itertuples():
            tl = THEME_LABEL.get(r.theme, (r.theme, r.theme))
            rows.append({"title": r.title, "url": r.url, "domain": r.domain,
                         "source": r.source, "theme": r.theme,
                         "theme_en": tl[0], "theme_zh": tl[1], "tier": int(r.source_tier),
                         "baskets": [x for x in str(r.baskets).split(",") if x],
                         "scheduled_ref": r.scheduled_ref})
        # scheduled-ahead strip from the calendar (next high-impact prints)
        scheduled_ahead = []
        try:
            from engine import china_event_calendar as cec
            for ev in cec.high_impact_strip(horizon_days=14)[:5]:
                scheduled_ahead.append({"type": ev.get("type"), "date": ev.get("date"),
                                        "name_en": ev.get("name_en"),
                                        "name_zh": ev.get("name_zh"),
                                        "md": ev.get("md")})
        except Exception:  # noqa: BLE001
            pass
        return {"schema": SCHEMA, "is_context_only": True, "asof": today.isoformat(),
                "window_days": days, "n_recent": int(len(recent)),
                "top_themes": list(by_theme.keys())[:6],
                "by_theme": {k: int(v) for k, v in by_theme.items()},
                "by_basket": {k: int(v) for k, v in
                              sorted(basket_ct.items(), key=lambda kv: -kv[1])},
                "scheduled_ahead": scheduled_ahead, "items": rows,
                "theme_label": {k: list(v) for k, v in THEME_LABEL.items()},
                "disclaimer": DISCLAIMER, "disclaimer_zh": DISCLAIMER_ZH}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
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
    """OPTIONAL one-paragraph 中文 narration of the feed + sentiment. Default-off, gated on
    key, provider-agnostic (DeepSeek/Anthropic), degrade-to-None. Context, never scored."""
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
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("china_news_intel brief failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# public: the combined panel view-model for the china_news page
# --------------------------------------------------------------------------- #
def panel(asof: date | str | None = None) -> dict | None:
    """Assemble the china_news.html view-model: {sentiment, feed, brief?, disclaimer}.
    None when there's nothing to show. Never raises."""
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
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_news_intel.panel failed (%s)", e)
        return None
