"""Macro news & catalysts — ANNOTATION layer for macro.html.

DEFERRED · GATED · ANNOTATION-ONLY · DEFAULT-OFF for the LLM. Honest CONTEXT,
never a scoring input. LEAF module: imports nothing from the mechanical core
(conditions/regime/run/inputs/equity_alloc) and nothing in the scoring path
imports it. Every public function returns plain data or None and NEVER raises
into the build — all network/parse/LLM failures degrade gracefully.

HOW "useful vs useless" news is decided — almost entirely WITHOUT AI:
  1. SOURCE ALLOWLIST  — keep only reputable macro/financial outlets (drops SEO
     spam, tabloids, foreign-language re-prints). Deterministic.
  2. MACRO-THEME GATE  — GDELT is queried with a macro OR-clause AND each kept
     headline must match a macro keyword bucket (Fed / inflation / labor /
     growth / credit / fiscal); non-macro headlines are dropped and each kept
     one is TAGGED with its theme. Deterministic keyword classification.
  3. DEDUP + RECENCY    — near-duplicate titles collapsed; ranked newest-first.
  4. QUANT SENTIMENT    — the dashboard already surfaces the SF-Fed Daily News
     Sentiment Index (peer-reviewed, daily since 1980, z-scored in
     engine/conditions.py); this panel reuses it, NOT per-headline LLM "vibes".
  5. OPTIONAL AI BRIEF  — the ONLY AI: a gated, default-off, degrade-to-keyless
     narrator that writes a 1-paragraph "what's the macro story" from the
     ALREADY-FILTERED headlines + the regime/sentiment state. Labeled context,
     never scored. Off unless macro_news.enabled AND llm_brief AND a key present.

GDELT gotchas honored: ~3-month history, >=6s pacing, 200+json content-type
guard, seendate=%Y%m%dT%H%M%SZ.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from lib import config

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# macro themes -> keyword buckets. Used BOTH to build the GDELT query AND to
# tag/relevance-gate each returned headline (deterministic classification).
MACRO_THEMES: dict[str, list[str]] = {
    "monetary":  ["federal reserve", "fomc", "rate cut", "rate hike", "interest rate",
                  "powell", "central bank", "monetary policy", "rate decision"],
    "inflation": ["inflation", "cpi", "pce", "consumer price", "deflation",
                  "price pressure", "core prices"],
    "labor":     ["jobs report", "payroll", "nonfarm", "unemployment", "labor market",
                  "jobless claims", "hiring", "layoff"],
    "growth":    ["gdp", "recession", "economic growth", "slowdown", "manufacturing",
                  "ism ", "soft landing", "hard landing", "contraction"],
    "credit":    ["bond yield", "treasury yield", "credit spread", "corporate bond",
                  "yield curve", "default rate"],
    "fiscal":    ["debt ceiling", "government shutdown", "fiscal", "tariff", "trade war",
                  "sanction", "budget deal"],
}
# theme display labels (EN, ZH)
THEME_LABEL = {
    "monetary": ("Fed", "美联储"), "inflation": ("Inflation", "通胀"),
    "labor": ("Labor", "就业"), "growth": ("Growth", "增长"),
    "credit": ("Credit/Rates", "信用/利率"), "fiscal": ("Fiscal/Trade", "财政/贸易"),
}

# reputable macro/financial outlets — the source allowlist (substring match on the
# article domain, so finance.yahoo.com matches yahoo.com). Tune in config.
_DEFAULT_SOURCES = [
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com", "cnbc.com",
    "marketwatch.com", "economist.com", "barrons.com", "nytimes.com",
    "washingtonpost.com", "forbes.com", "businessinsider.com", "yahoo.com",
    "investing.com", "axios.com", "thehill.com", "politico.com", "fortune.com",
    "morningstar.com", "seekingalpha.com", "kitco.com", "spglobal.com",
]

DISCLAIMER_TEXT = (
    "Context only — not a signal. These headlines are filtered (reputable sources, "
    "macro themes only) and shown as background; the “sentiment” gauge is the SF-Fed "
    "Daily News Sentiment Index (a quantitative series), NOT a per-headline AI judgement. "
    "Nothing here is an input to any score, signal or allocation, and the mechanical "
    "model never sees it. Upcoming-catalyst dates are scheduling information, not forecasts."
)
DISCLAIMER_TEXT_ZH = (
    "仅作背景，非信号。以下头条已经过筛选（仅可靠来源、仅宏观主题）；“情绪”指标采用旧金山联储"
    "每日新闻情绪指数（一个量化序列），并非逐条新闻的 AI 判断。这里没有任何内容会进入任何评分、"
    "信号或配置，机械模型也从不读取它们。即将到来的催化日期为日程信息，而非预测。"
)


def _cfg() -> dict:
    return config.load().get("macro_news", {}) or {}


def enabled() -> bool:
    """Master switch for the GDELT fetch + LLM brief. The catalyst calendar and the
    (already-computed) sentiment gauge are keyless and surface regardless."""
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# deterministic filtering
# --------------------------------------------------------------------------- #
def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def classify_theme(title: str) -> str | None:
    """Return the macro theme a headline matches (first bucket with a keyword hit),
    or None if it matches no macro keyword (-> irrelevant, dropped). PURE."""
    low = " " + (title or "").lower() + " "
    for theme, kws in MACRO_THEMES.items():
        if any(k in low for k in kws):
            return theme
    return None


def filter_headlines(articles: list[dict], cfg: dict | None = None) -> list[dict]:
    """Apply the deterministic pipeline to raw GDELT articles: source allowlist ->
    macro-theme relevance gate + tag -> dedup -> recency rank -> top-N. PURE (takes
    a list of {title,url,domain,seendate,...} dicts). This is the 'useful vs
    useless' filter; no AI involved."""
    cfg = cfg or {}
    allow = [s.lower() for s in (cfg.get("sources") or _DEFAULT_SOURCES)]
    top_n = int(cfg.get("max_show", 10))
    kept: list[dict] = []
    seen: set[str] = set()
    for a in articles:
        dom = (a.get("domain") or "").lower()
        if allow and not any(s in dom for s in allow):
            continue                                   # (1) source allowlist
        theme = classify_theme(a.get("title", ""))
        if theme is None:
            continue                                   # (2) macro relevance gate
        key = _norm_title(a.get("title", ""))[:60]
        if not key or key in seen:
            continue                                   # (3) dedup
        seen.add(key)
        kept.append({"title": a.get("title", ""), "url": a.get("url", ""),
                     "domain": dom, "seendate": a.get("seendate", ""), "theme": theme})
    kept.sort(key=lambda h: h.get("seendate", ""), reverse=True)  # (4) newest first
    return kept[:top_n]


# --------------------------------------------------------------------------- #
# GDELT fetch (free, keyless) — recent macro headlines
# --------------------------------------------------------------------------- #
def _query(cfg: dict) -> str:
    # Strongest, shortest macro terms (GDELT caps query length). The query MATCHES
    # full article text, so the title-level theme gate in filter_headlines is the
    # precision step.
    core = ['"federal reserve"', "fomc", "inflation", "cpi", '"interest rates"',
            "recession", '"jobs report"', "payrolls", "gdp", '"treasury yield"',
            "tariffs", '"debt ceiling"']
    q = "(" + " OR ".join(core) + ")"
    # sourcecountry:US removes the flood of foreign local papers at source; the
    # reputable-source allowlist + title theme-gate then run in filter_headlines.
    q += f" sourcecountry:US sourcelang:{cfg.get('lang', 'eng')}"
    return q


def _cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("cache_dir", "data/macro/news_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"macro_{d.isoformat()}.json"


def _fetch_gdelt(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Recent macro articles from GDELT (last `window_days` ending today). Returns
    (raw_articles, degraded_reason). Cached; never raises."""
    today = today or date.today()
    cache = _cache_path(cfg, today)
    ttl = cfg.get("cache_ttl_hours", 12) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("articles", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass

    win = int(cfg.get("window_days", 2))
    end = datetime(today.year, today.month, today.day, 23, 59, 59)
    start = end - timedelta(days=win)
    params = {"query": _query(cfg), "mode": "artlist", "format": "json",
              "maxrecords": str(cfg.get("max_records", 60)), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    articles: list[dict] = []
    reason: str | None = None
    try:
        import time

        import requests
        r = None
        for attempt in range(3):
            r = requests.get(GDELT_URL, params=params, timeout=30,
                             headers={"User-Agent": "macro-dashboard/1.0 (research)"})
            if r.status_code == 429 and attempt < 2:
                time.sleep(max(6, cfg.get("min_request_interval_s", 6)) * (attempt + 1))
                continue
            break
        if r is None or r.status_code != 200 or "json" not in r.headers.get("Content-Type", ""):
            reason = "rate_limited" if (r is not None and r.status_code == 429) else "fetch_error"
        else:
            for a in (r.json().get("articles", []) or []):
                sd = a.get("seendate", "")
                try:
                    iso = datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=timezone.utc).isoformat()
                except (ValueError, TypeError):
                    iso = sd
                articles.append({"title": a.get("title", ""), "url": a.get("url", ""),
                                 "domain": a.get("domain", ""), "seendate": iso})
            if not articles:
                reason = "no_headlines"
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("gdelt macro fetch failed (%s)", e)
        reason = "fetch_error"
    try:
        cache.write_text(json.dumps({"articles": articles, "degraded_reason": reason}))
    except Exception:  # noqa: BLE001
        pass
    return articles, reason


# --------------------------------------------------------------------------- #
# public: filtered macro headlines
# --------------------------------------------------------------------------- #
def macro_headlines(today: date | None = None) -> dict | None:
    """Filtered, theme-tagged, deduped recent macro headlines. None when the
    master switch is off. Never raises."""
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    raw, reason = _fetch_gdelt(cfg, today)
    kept = filter_headlines(raw, cfg)
    return {"schema": "macro_news.v1", "is_context_only": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(), "source": "gdelt_doc_2.0",
            "headlines": kept, "n_raw": len(raw), "n_kept": len(kept),
            "degraded_reason": reason if not kept else None,
            "disclaimer": DISCLAIMER_TEXT}


# --------------------------------------------------------------------------- #
# public: upcoming macro catalysts (keyless, always available)
# --------------------------------------------------------------------------- #
# Fed-published 2026 FOMC schedule. * (SEP) = meeting with projections/dot-plot.
_FOMC = [("2026-01-28", " (SEP)"), ("2026-03-18", ""), ("2026-04-29", " (SEP)"),
         ("2026-06-17", ""), ("2026-07-29", " (SEP)"), ("2026-09-16", ""),
         ("2026-10-28", " (SEP)"), ("2026-12-09", "")]


def _first_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)   # weekday 4 == Friday


def upcoming_catalysts(today: date | None = None, horizon_days: int = 14) -> list[dict]:
    """Forward macro-event watch list (FOMC + monthly jobs report, computed
    reliably) plus any config `extra_catalysts` (official CPI/GDP dates the user
    supplies). Scheduling info, context-only."""
    today = today or date.today()
    end = today + timedelta(days=horizon_days)
    out: list[dict] = []

    for d, tag in _FOMC:
        dd = date.fromisoformat(d)
        if today <= dd <= end:
            out.append({"type": "FOMC", "date": d, "time_et": "14:00",
                        "label": f"FOMC rate decision{tag}", "is_context_only": True})
    # Nonfarm payrolls — first Friday of each month, 08:30 ET (computed)
    for mo in (today.month, today.month % 12 + 1):
        yr = today.year + (1 if mo == 1 and today.month == 12 else 0)
        ff = _first_friday(yr, mo)
        if today <= ff <= end:
            out.append({"type": "NFP", "date": ff.isoformat(), "time_et": "08:30",
                        "label": "Jobs report (nonfarm payrolls)", "is_context_only": True})
    # user-supplied official dates (CPI/GDP/Jackson Hole/etc.) — {type,date,label,time_et?}
    for c in (_cfg().get("extra_catalysts") or []):
        try:
            dd = date.fromisoformat(c["date"])
        except Exception:  # noqa: BLE001
            continue
        if today <= dd <= end:
            out.append({"type": c.get("type", "EVENT"), "date": c["date"],
                        "time_et": c.get("time_et", ""), "label": c.get("label", ""),
                        "is_context_only": True})
    out.sort(key=lambda c: c["date"])
    return out


# --------------------------------------------------------------------------- #
# optional LLM brief (gated on flag AND key; provider-agnostic; default OFF)
# --------------------------------------------------------------------------- #
BRIEF_SYSTEM = (
    "You write a 2-3 sentence plain-English summary of the current US macro backdrop "
    "for a dashboard, using ONLY the provided filtered headlines and the regime/sentiment "
    "context. This is background narration — it NEVER feeds any score, signal or trade. "
    "Be factual and neutral; do NOT give advice, price targets, or predictions. If the "
    "headlines are thin or off-topic, say the macro tape is quiet rather than inventing a story."
)


def _llm_ready(cfg: dict) -> bool:
    if not cfg.get("enabled", False) or not cfg.get("llm_brief", False):
        return False
    return bool(config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))


def macro_brief(headlines: list[dict] | None, regime_line: str = "",
                sentiment_line: str = "") -> dict | None:
    """OPTIONAL one-paragraph narration of the filtered headlines + regime/sentiment.
    Default-off, gated on key, provider-agnostic (DeepSeek/Anthropic), degrade to
    None. Labeled context; never scored."""
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
        lines = "\n".join(f"- [{h.get('theme','')}] {h['title']} ({h['domain']})"
                          for h in headlines[:12])
        user = (f"Regime: {regime_line or 'n/a'}\nNews sentiment: {sentiment_line or 'n/a'}\n"
                f"Filtered macro headlines:\n{lines}")
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-chat"), max_tokens=220,
            system=BRIEF_SYSTEM, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            return None
        return {"text": text, "model": cfg.get("llm_model", "deepseek-chat"),
                "is_context_only": True}
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("macro brief failed (%s)", e)
        return None
