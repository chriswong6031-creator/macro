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

import json
import logging
import re
from datetime import date, datetime, timezone

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_news.v1"

# Chinese macro-theme keyword buckets — used to gate + TAG each flash headline
# (deterministic classification; first bucket with a hit wins). Tuned for the
# Eastmoney 全球财经快讯 tape.
MACRO_THEMES: dict[str, list[str]] = {
    "monetary": ["央行", "人民银行", "降准", "降息", "加息", "利率", "LPR", "MLF",
                 "逆回购", "流动性", "货币政策", "公开市场"],
    "inflation": ["CPI", "PPI", "物价", "通胀", "通缩", "通货膨胀"],
    "growth": ["GDP", "经济增长", "PMI", "制造业", "工业增加值", "复苏", "放缓",
               "衰退", "增速", "经济数据"],
    "credit": ["社融", "社会融资", "信贷", "贷款", "债券", "国债", "收益率", "违约",
               "信用", "城投"],
    "fiscal": ["财政", "专项债", "减税", "退税", "关税", "贸易", "出口", "进口",
               "制裁", "财政部"],
    "policy": ["国常会", "政治局", "发改委", "稳增长", "稳经济", "房地产", "楼市",
               "监管", "改革", "政策", "国务院"],
    "markets": ["A股", "股市", "沪深", "上证", "创业板", "北交所", "证监会", "退市",
                "IPO", "北向", "外资", "南向"],
}
# theme display labels (EN, ZH)
THEME_LABEL: dict[str, tuple[str, str]] = {
    "monetary": ("PBoC", "央行"), "inflation": ("Inflation", "物价"),
    "growth": ("Growth", "增长"), "credit": ("Credit", "信用"),
    "fiscal": ("Fiscal/Trade", "财政/贸易"), "policy": ("Policy", "政策"),
    "markets": ("Markets", "市场"), "macro": ("Macro", "宏观"),
}

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
def _tone_stats(series, window: int, smooth: int) -> dict | None:
    """Smooth the sparse daily tone, z-score the latest vs a trailing window. PURE
    (takes a pandas Series). None if there's nothing usable."""
    try:
        import pandas as pd
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return None
        sm = s.rolling(max(int(smooth), 1), min_periods=1).mean()
        latest = float(sm.iloc[-1])
        win = sm.tail(max(int(window), 2))
        mu = float(win.mean())
        sd = float(win.std(ddof=0))
        z = (latest - mu) / sd if sd and not pd.isna(sd) and sd > 1e-9 else 0.0
        return {"value": round(latest, 3), "mean": round(mu, 3),
                "z": round(float(z), 2), "n": int(len(s))}
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
    """Official policy-tone read from data/china_news/cctv_tone.parquet. Returns the
    display dict (value/z/band/asof) or None when no tone history exists yet. Never
    raises."""
    try:
        df = store.read("china_news", "cctv_tone")
        if df is None or df.empty or "tone" not in df.columns:
            return None
        cfg = _cfg()
        stats = _tone_stats(df["tone"], cfg.get("tone_window", 90), cfg.get("tone_smooth", 5))
        if not stats:
            return None
        band, lab_en, lab_zh = _tone_band(stats)
        return {
            "schema": SCHEMA, "is_context_only": True,
            "value": stats["value"], "z": stats["z"], "n_days": stats["n"],
            "band": band, "label_en": lab_en, "label_zh": lab_zh,
            "asof": str(df.index.max().date()),
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
    for theme, kws in MACRO_THEMES.items():
        if any(k in blob for k in kws):
            return theme
    return None


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", "", (t or ""))[:40]


def filter_flashes(items: list[dict], cfg: dict | None = None) -> list[dict]:
    """Deterministic pipeline over raw flashes: macro-theme relevance gate + tag ->
    dedup -> recency rank -> top-N. PURE (takes {title,summary,url,time} dicts)."""
    cfg = cfg or {}
    top_n = int(cfg.get("max_show", 12))
    kept: list[dict] = []
    seen: set[str] = set()
    for a in items:
        title = (a.get("title") or "").strip()
        summary = (a.get("summary") or "").strip()
        theme = classify_theme(title + " " + summary)
        if theme is None:
            continue                                   # non-macro flash -> dropped
        key = _norm_title(title)
        if not key or key in seen:
            continue                                   # dedup
        seen.add(key)
        kept.append({"title": title, "summary": summary, "url": a.get("url", ""),
                     "time": a.get("time", ""), "theme": theme})
    kept.sort(key=lambda h: h.get("time", ""), reverse=True)   # newest first
    return kept[:top_n]


def _cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("cache_dir", "data/china_news/flash_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"flash_{d.isoformat()}.json"


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


def flash_headlines(today: date | None = None) -> dict | None:
    """Filtered, theme-tagged, deduped recent macro flashes. None when the master
    switch is off. Never raises."""
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    raw, reason = _fetch_flashes(cfg, today)
    kept = filter_flashes(raw, cfg)
    return {"schema": SCHEMA, "is_context_only": True, "source": "eastmoney_global_em",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "headlines": kept, "n_raw": len(raw), "n_kept": len(kept),
            "degraded_reason": reason if not kept else None}


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
