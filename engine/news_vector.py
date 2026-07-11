"""News-vector PIT event bus — Stage 1 of the narrative-quantification pipeline.

LEAF · GATED · CONTEXT-ONLY · LLM-DEFAULT-OFF. This is the keystone substrate of
the narrative framework (memory narrative-quant-framework): a first-print,
point-in-time, append-only event store that EVERY later stage reads. Its value is
MEASUREMENT INTEGRITY, not alpha — it makes no forward-return claim, so it cannot
be falsified by one; its bar is a data-quality bar (see tests/test_news_vector.py).

WHAT IT DOES (deterministic, no AI in P0):
  1. FETCH a NARRATIVE-scope GDELT slice (trade/tariffs, geopolitics/conflict,
     industrial-policy, plus the core macro terms) — broader than engine.macro_news,
     because the manufactured-volatility backdrop the dashboard must read (tariff
     scares, Iran/Israel headlines, government stakes in chipmakers) is exactly the
     policy/geo flow macro_news filters OUT. The term list goes out as MULTIPLE
     sub-queries, each under GDELT's server-side query-length limit (_MAX_QUERY_LEN;
     the limit TIGHTENED ~2026-06-20 and rejected the old single query for 3 weeks),
     through engine.gdelt_client's shared cross-process per-IP pace gate.
  2. GATE deterministically — reputable-source allowlist + a narrative-theme keyword
     gate (reuses engine.macro_news.filter primitives where they overlap), dedup.
  3. KEY each kept headline by a stable content hash (event_id) and ACCRUE it
     append-only with **keep-FIRST** semantics: the FIRST time we saw an event_id is
     recorded as first_seen_utc and is NEVER overwritten on re-ingest. This single
     decision defeats the framework's #1 look-ahead failure mode (news APIs restamp
     on republish); it is the deliberate INVERSE of the prediction-markets snapshot
     accrual (which keeps-LAST, because odds genuinely revise).
  4. STAMP each event with scheduled_ref — whether a HIGH-impact scheduled US macro
     release (FOMC/CPI/NFP/GDP/PCE/PPI, via engine.event_calendar) falls on/near the
     article date. This is the deterministic "is this move explainable by the
     calendar, or is it a headline shock?" flag the surprise-decomposition needs.

DISCIPLINE (enforced, not aspirational):
  • LEAF — imports nothing from the mechanical core (conditions/regime/run/inputs/
    cycles/equity_alloc/*_signals/calibrate); only lib.config and the sibling LEAF
    modules macro_news + event_calendar. Nothing in any scoring path imports this.
  • Every public function returns plain data or None and NEVER raises into the build.
  • The LLM structured-extraction stage is STUBBED OFF in P0 (enabled:false AND
    llm_extract:false). When later enabled it must reuse engine.catalyst_tone's
    citation-verified gates and write its fields as CONTEXT only — never a score.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SCHEMA = "news_vector.v1"

# Narrative-scope theme taxonomy. ORDER MATTERS — the distinctive policy/geo buckets
# are checked BEFORE the generic macro ones so "tariff"/"sanction" classify as
# trade/geopolitics rather than the catch-all fiscal bucket. Deterministic, no AI.
NARRATIVE_THEMES: dict[str, list[str]] = {
    "geopolitics": ["iran", "israel", "ukraine", "russia", "gaza", "houthi", "hezbollah",
                    "missile", "airstrike", "air strike", "ceasefire", "cease-fire",
                    "strait of hormuz", "nuclear", "war", "conflict", "invasion",
                    "military strike", "drone attack", "escalation"],
    "trade": ["tariff", "trade war", "trade deal", "export control", "export ban",
              "sanction", "import tax", "customs duty", "decoupling", "entity list",
              "section 301", "trade talks"],
    "industrial_policy": ["chips act", "government stake", "nationaliz", "bailout",
                          "subsidy", "subsidies", "strategic reserve", "semiconductor",
                          "ai investment", "export curb", "stockpile", "reshoring"],
    "monetary": ["federal reserve", "fomc", "rate cut", "rate hike", "interest rate",
                 "powell", "central bank", "monetary policy", "rate decision"],
    "inflation": ["inflation", "cpi", "pce", "consumer price", "deflation"],
    "labor": ["jobs report", "payroll", "nonfarm", "unemployment", "jobless claims",
              "layoff", "labor market"],
    "growth": ["gdp", "recession", "economic growth", "slowdown", "manufacturing",
               "soft landing", "hard landing", "contraction"],
    "fiscal": ["debt ceiling", "government shutdown", "fiscal", "budget deal", "default"],
    "ai_tech": ["artificial intelligence", " ai ", "data center", "data centre",
                "large language model", "openai", "anthropic", "nvidia", "gpu",
                "cloud computing", "chip", "antitrust"],
    "energy": ["opec", "crude oil", "oil price", "natural gas", "lng", "power grid",
               "electricity demand", "uranium", "nuclear power"],
    "markets": ["stock market", "wall street", "s&p 500", "nasdaq", "selloff",
                "record high", "bear market", "bull market", "credit spread", "ipo"],
}

# top-tier wire services -> source_tier 1 (a deterministic credibility proxy; the
# allowlist itself lives in config / engine.macro_news). NOT a score.
_TIER1 = ["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com",
          "economist.com", "barrons.com", "spglobal.com"]

# high-impact scheduled release types used for the scheduled_ref "explainable by the
# calendar?" stamp (the surprise-decomposition spine).
_HIGH_IMPACT = {"FOMC", "CPI", "PPI", "NFP", "GDP", "PCE"}

DISCLAIMER_TEXT = (
    "Context only — not a signal. This is a first-print, point-in-time log of "
    "filtered policy/geopolitical/macro headlines (reputable sources, narrative "
    "themes only), kept to MEASURE the news flow honestly over time — never to "
    "predict direction. Nothing here is an input to any score, signal or "
    "allocation, and the mechanical model never reads it. The “scheduled” tag means "
    "a high-impact release fell on/near that date (so the move may be calendar-"
    "explained rather than a headline shock); it is context, not a forecast."
)
DISCLAIMER_TEXT_ZH = (
    "仅作背景，非信号。这是经过筛选的政策／地缘／宏观头条的首次出现时间点日志（仅可靠来源、"
    "仅叙事主题），用于诚实地长期度量新闻流，而非预测方向。这里没有任何内容会进入任何评分、"
    "信号或配置，机械模型也从不读取它们。“已排程”标签表示当日附近有高影响数据发布"
    "（因此走势可能由日历解释，而非头条冲击），仅为背景，而非预测。"
)


def _cfg() -> dict:
    return config.load().get("news_vector", {}) or {}


def enabled() -> bool:
    """Master switch for the GDELT fetch + accrual. The display read degrades to the
    already-accrued store when off, so history persists either way."""
    return bool(_cfg().get("enabled", False))


def _events_path() -> Path:
    p = config.data_dir() / "news_vector" / "events.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------- #
# pure helpers (no network, no clock) — independently unit-tested
# --------------------------------------------------------------------------- #
def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def event_id(title: str, domain: str) -> str:
    """Stable content hash for dedup + keep-FIRST accrual. PURE & deterministic:
    the same (title, domain) always yields the same id, across runs and machines."""
    basis = _norm_title(title)[:120] + "|" + (domain or "").lower().strip()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def classify_theme(title: str) -> str | None:
    """First narrative theme a headline matches, or None (-> off-narrative, dropped).
    PURE. Order favors the distinctive policy/geo buckets over generic macro."""
    low = " " + (title or "").lower() + " "
    for theme, kws in NARRATIVE_THEMES.items():
        if any(k in low for k in kws):
            return theme
    return None


def source_tier(domain: str) -> int:
    dom = (domain or "").lower()
    return 1 if any(s in dom for s in _TIER1) else 2


def build_records(articles: list[dict], scheduled: dict[str, str],
                  allow: list[str], first_seen_utc: str) -> list[dict]:
    """Turn raw GDELT articles into deterministic event records. PURE (no network,
    no clock — `first_seen_utc` is injected so accrual/idempotency is testable).

    scheduled: {date_iso -> "TYPE"} of high-impact scheduled releases, used to stamp
    scheduled_ref when an article's own date lands within ±1 day of one.
    """
    allow = [s.lower() for s in (allow or [])]
    out: list[dict] = []
    seen: set[str] = set()
    for a in articles:
        dom = (a.get("domain") or "").lower()
        if allow and not any(s in dom for s in allow):
            continue                                          # source allowlist
        title = a.get("title", "")
        theme = classify_theme(title)
        if theme is None:
            continue                                          # narrative relevance gate
        eid = event_id(title, dom)
        if eid in seen:
            continue                                          # in-batch dedup
        seen.add(eid)
        seendate = a.get("seendate", "") or ""
        out.append({
            "event_id": eid,
            "first_seen_utc": first_seen_utc,
            "seendate": seendate,
            "title": title,
            "url": a.get("url", ""),
            "domain": dom,
            "theme": theme,
            "source_tier": source_tier(dom),
            "scheduled_ref": _scheduled_ref_for(seendate, scheduled),
        })
    return out


def _scheduled_ref_for(seendate_iso: str, scheduled: dict[str, str]) -> str:
    """'TYPE@YYYY-MM-DD' if a high-impact release falls within ±1 day of the article
    date, else ''. PURE."""
    try:
        d = date.fromisoformat((seendate_iso or "")[:10])
    except (ValueError, TypeError):
        return ""
    for delta in (0, -1, 1):
        key = (d + timedelta(days=delta)).isoformat()
        if key in scheduled:
            return f"{scheduled[key]}@{key}"
    return ""


def accrue(existing, new_records: list[dict]):
    """Append-only merge with **keep-FIRST** on event_id. PURE.

    `existing` is the prior DataFrame (or None); `new_records` the freshly-built
    rows. Concatenates OLD-then-NEW and drops duplicate event_ids keeping the FIRST
    occurrence — so a re-seen event retains its ORIGINAL first_seen_utc and is never
    restamped. Returns the merged, deterministically-sorted DataFrame."""
    import pandas as pd
    new_df = pd.DataFrame(new_records, columns=list(_COLUMNS))
    if existing is None or len(existing) == 0:
        merged = new_df
    else:
        merged = pd.concat([existing[list(_COLUMNS)], new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["event_id"], keep="first")
    # deterministic, content-defined ordering (NOT ingest order) so re-runs are stable
    merged = merged.sort_values(["first_seen_utc", "event_id"]).reset_index(drop=True)
    return merged


_COLUMNS = ("event_id", "first_seen_utc", "seendate", "title", "url",
            "domain", "theme", "source_tier", "scheduled_ref")


# --------------------------------------------------------------------------- #
# scheduled-release map (reuses the unified event calendar — sibling LEAF)
# --------------------------------------------------------------------------- #
def _scheduled_map(today: date, back: int = 3, fwd: int = 3,
                   use_fred: bool = True) -> dict[str, str]:
    """{date_iso -> TYPE} for HIGH-impact US releases in [today-back, today+fwd].
    Degrades to {} on any failure. Reuses engine.event_calendar (LEAF)."""
    try:
        from engine import event_calendar as ec
        start = today - timedelta(days=back)
        evs = ec.us_macro_events(start, horizon_days=back + fwd, use_fred=use_fred)
        out: dict[str, str] = {}
        for ev in evs:
            if ev.get("type") in _HIGH_IMPACT:
                out.setdefault(ev["date"], ev["type"])
        return out
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.debug("scheduled map unavailable (%s)", e)
        return {}


# --------------------------------------------------------------------------- #
# GDELT fetch (free, keyless) — narrative-scope slice. Self-contained (own cache /
# query) so this stays an independent leaf; mirrors macro_news's GDELT discipline.
# --------------------------------------------------------------------------- #
_QUERY_CORE = ['tariffs', '"trade war"', 'sanctions', 'iran', 'israel', 'ukraine',
               'ceasefire', '"export controls"', 'semiconductor', '"federal reserve"',
               'inflation', 'recession', '"artificial intelligence"', '"data center"',
               '"stock market"', '"oil price"', 'antitrust']


# GDELT rejects long queries with HTTP 200 + text/html "Your query was too short
# or too long." — a STRUCTURAL failure retries can never heal. The limit is
# server-side and has TIGHTENED before: ~2026-06-20 it dropped below this
# module's original single 288-char query and silently stalled the accrual for
# three weeks (probed 2026-07-10: 246 chars accepted, 288 rejected). 230 leaves
# headroom; _queries() splits the term list into as many sub-queries as needed.
_MAX_QUERY_LEN = 230


def _queries(cfg: dict) -> list[str]:
    """Split the narrative term list into OR-group sub-queries whose FULL query
    strings (terms + source filters) each stay under _MAX_QUERY_LEN. PURE."""
    core = cfg.get("query_terms") or _QUERY_CORE
    suffix = f" sourcecountry:US sourcelang:{cfg.get('lang', 'eng')}"
    budget = _MAX_QUERY_LEN - len(suffix) - 2          # 2 for the wrapping parens
    groups: list[list[str]] = [[]]
    for term in core:
        if groups[-1] and len(" OR ".join(groups[-1] + [term])) > budget:
            groups.append([term])
        else:
            groups[-1].append(term)
    return ["(" + " OR ".join(g) + ")" + suffix for g in groups if g]


def _cache_path(cfg: dict, d: date) -> Path:
    cdir = config.ROOT / cfg.get("cache_dir", "data/news_vector/fetch_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"nv_{d.isoformat()}.json"


# degraded_reason severity: a structural rejection outranks everything (it will
# never self-heal), then transient failures, then the benign "window was quiet".
_REASON_PRIORITY = ("query_rejected", "rate_limited", "fetch_error", "no_headlines")


def fetch_range(cfg: dict, start: datetime, end: datetime,
                max_records: int | None = None) -> tuple[list[dict], str | None]:
    """Raw narrative-scope articles for [start, end] — the ONE fetch path shared
    by the daily ingest and the date-ranged backfill (scripts/backfill_news_vector).
    No cache. Never raises.

    The term list goes out as MULTIPLE sub-queries (_queries, each under GDELT's
    server-side length limit) through engine.gdelt_client (single cross-process
    pacing lock + honest failure labels); articles are merged and deduped on
    (title, domain) — the event_id basis. degraded_reason surfaces the WORST
    sub-query outcome (_REASON_PRIORITY) so a structural query_rejected stays
    loud even when the other sub-queries succeeded; it is None only when every
    sub-query returned usable JSON and at least one article arrived (all-quiet
    -> no_headlines)."""
    from engine import gdelt_client as _gc

    articles: list[dict] = []
    seen: set[tuple[str, str]] = set()
    reasons: list[str] = []
    for q in _queries(cfg):
        params = {"query": q, "mode": "artlist", "format": "json",
                  "maxrecords": str(max_records or cfg.get("max_records", 120)),
                  "sort": "datedesc",
                  "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                  "enddatetime": end.strftime("%Y%m%d%H%M%S")}
        try:
            got, why = _gc.get_articles(
                params, timeout=30,
                min_interval=max(0, int(cfg.get("min_request_interval_s", 6))))
        except Exception as e:  # noqa: BLE001 — degrade, never raise
            log.warning("news_vector gdelt fetch failed (%s)", e)
            got, why = None, "fetch_error"
        if why == "query_rejected":
            log.error("news_vector: GDELT REJECTED sub-query (len=%d) — STRUCTURAL, "
                      "retries cannot heal; shorten query_terms/_QUERY_CORE or "
                      "_MAX_QUERY_LEN: %r", len(q), q)
        if got is None:
            reasons.append(why or "fetch_error")
            continue
        for a in got:
            key = ((a.get("title") or "").strip(), (a.get("domain") or "").lower())
            if key in seen:
                continue                     # same story matched two sub-queries
            seen.add(key)
            articles.append(a)
    reason = next((lvl for lvl in _REASON_PRIORITY if lvl in reasons), None)
    if not articles and reason is None:
        reason = "no_headlines"
    return articles, reason


def _fetch_gdelt(cfg: dict, today: date) -> tuple[list[dict], str | None]:
    """Recent narrative-scope articles from GDELT (last window_days). Returns
    (raw_articles, degraded_reason). Cached 12h; never raises.

    The day-cache sits HERE (one blob spanning all sub-queries), not inside
    gdelt_client — fetch_range fans out to several sub-queries and the daily
    result is only meaningful as their merged union."""
    cache = _cache_path(cfg, today)
    ttl = int(cfg.get("cache_ttl_hours", 12)) * 3600
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
    articles, reason = fetch_range(cfg, start, end)
    # Only cache SUCCESSFUL responses (articles present).  A failed/empty response
    # (rate_limited, fetch_error, no_headlines) must NOT be cached — caching it would
    # suppress retries for the full 12-hour TTL and silently stall the accrual store.
    if articles:
        try:
            cache.write_text(json.dumps({"articles": articles, "degraded_reason": reason}))
        except Exception:  # noqa: BLE001
            pass
    return articles, reason


def _allowlist(cfg: dict) -> list[str]:
    """Reuse engine.macro_news's reputable-source default list (sibling leaf), or the
    config override. Keeps one source-of-truth for 'reputable outlet'."""
    src = cfg.get("sources")
    if src:
        return src
    try:
        from engine import macro_news as mn
        return list(mn._DEFAULT_SOURCES)
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------- #
# public: daily ingest (Action-step) — fetch -> gate -> keep-FIRST accrue
# --------------------------------------------------------------------------- #
_FRESHNESS_WARN_DAYS = 3   # warn when newest event is older than this
_FRESHNESS_ERROR_DAYS = 7  # escalate WARNING -> ERROR: a week-plus stall is
                           # structural (query_rejected / persistent rate-limit),
                           # not a bad day — it needs a human/agent, not a retry


def _check_freshness(path: "Path", today: date) -> dict:
    """Return a freshness dict {age_days, newest_event, warn}.
    Broken ≠ quiet: always logs a WARNING when the store is stale (age > threshold).
    PURE-ish (reads parquet but no network). Never raises."""
    try:
        import pandas as pd
        if not path.exists():
            log.warning("news_vector freshness: events.parquet missing — store never written")
            return {"age_days": None, "newest_event": None, "warn": True, "reason": "missing"}
        df = pd.read_parquet(path)
        if df.empty:
            log.warning("news_vector freshness: events.parquet is empty")
            return {"age_days": None, "newest_event": None, "warn": True, "reason": "empty"}
        newest_str = str(df["first_seen_utc"].max())[:10]
        try:
            newest = date.fromisoformat(newest_str)
        except (ValueError, TypeError):
            log.warning("news_vector freshness: cannot parse newest date %r", newest_str)
            return {"age_days": None, "newest_event": newest_str, "warn": True,
                    "reason": "unparseable_date"}
        age = (today - newest).days
        warn = age > _FRESHNESS_WARN_DAYS
        escalated = age > _FRESHNESS_ERROR_DAYS
        if escalated:
            log.error(
                "news_vector freshness ERROR: newest event %s is %d days old "
                "(warn threshold %d, error threshold %d) — the accrual is STALLED, "
                "not merely late. Check this run's degraded_reason: query_rejected "
                "means GDELT rejected the query (structural — fix the query, "
                "retries cannot heal); rate_limited means the shared per-IP GDELT "
                "budget is exhausted (engine.gdelt_client). After fixing, close the "
                "gap with scripts/backfill_news_vector.py --start %s",
                newest_str, age, _FRESHNESS_WARN_DAYS, _FRESHNESS_ERROR_DAYS,
                newest_str,
            )
        elif warn:
            log.warning(
                "news_vector freshness WARNING: newest event %s is %d days old "
                "(threshold %d) — accrual may be stalled (check GDELT rate-limit "
                "or fetch_cache for cached failures)",
                newest_str, age, _FRESHNESS_WARN_DAYS,
            )
        return {"age_days": age, "newest_event": newest_str, "warn": warn,
                "escalated": escalated}
    except Exception as e:  # noqa: BLE001
        log.warning("news_vector freshness check failed (%s)", e)
        return {"age_days": None, "newest_event": None, "warn": True, "reason": str(e)}


def ingest(today: date | None = None) -> dict | None:
    """Fetch the narrative slice, build event records, and accrue them append-only
    (keep-FIRST). Returns a small summary; None when the master switch is off.
    NEVER raises into the pipeline.

    Freshness check is ALWAYS run (even when fetch degrades) so a stale store is
    never quiet — a WARNING is logged when newest event exceeds _FRESHNESS_WARN_DAYS.
    """
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    try:
        import pandas as pd
        today = today or date.today()
        raw, reason = _fetch_gdelt(cfg, today)
        scheduled = _scheduled_map(today, use_fred=cfg.get("use_fred", True))
        now_iso = datetime.now(timezone.utc).isoformat()
        records = build_records(raw, scheduled, _allowlist(cfg), now_iso)
        path = _events_path()
        existing = pd.read_parquet(path) if path.exists() else None
        before = 0 if existing is None else len(existing)
        merged = accrue(existing, records)
        merged.to_parquet(path, index=False)
        n_new = len(merged) - before
        log.info("news_vector: %d raw -> %d gated -> %d new events (%d total)",
                 len(raw), len(records), n_new, len(merged))
        freshness = _check_freshness(path, today)
        # degraded_reason is ALWAYS surfaced (not only when zero records landed):
        # a partial fetch where one sub-query was rejected or rate-limited is
        # still degraded coverage, and query_rejected in particular must stay
        # loud — it is structural and never self-heals.
        return {"schema": SCHEMA, "is_context_only": True, "asof": today.isoformat(),
                "n_raw": len(raw), "n_gated": len(records), "n_new": n_new,
                "n_total": int(len(merged)), "degraded_reason": reason,
                "freshness": freshness}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("news_vector ingest failed (%s)", e)
        return None


def ingest_to_qbus(today: date | None = None) -> dict | None:
    """Wire all accrued news_vector events into qbus (append_items, keep-FIRST).
    Reads from the local events.parquet store (populated by `ingest()`), maps to
    the qbus schema with ``timestamp_quality=CRAWL_BOUNDED`` (news_vector events
    are bounded only by our crawl time, not publisher-stated), and calls
    ``qbus.append_items``.  Returns a summary dict; None on any failure.

    This is a LEAF boundary call — it stamps ``_crawled_at`` at call time and
    passes it down; qbus library code never touches the clock."""
    try:
        import pandas as pd
        from engine import qbus

        path = _events_path()
        if not path.exists():
            log.debug("news_vector.ingest_to_qbus: events.parquet not found; skipping")
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return {"desk": "news_vector", "n_wired": 0}

        today = today or date.today()
        crawled_at = datetime.now(timezone.utc).isoformat()

        rows: list[dict] = []
        for r in df.itertuples(index=False):
            rows.append({
                "desk": "news_vector",
                "source": str(r.domain or ""),
                "url": str(r.url or ""),
                "title": str(r.title or ""),
                "seendate": str(r.first_seen_utc or ""),
                "_crawled_at": crawled_at,
                "timestamp_quality": "CRAWL_BOUNDED",
                "lang": "en",
                "entities": [],
                "themes": [str(r.theme)] if r.theme else [],
                "importance_raw": float(2 - r.source_tier) if r.source_tier in (1, 2) else 0.0,
            })

        result = qbus.append_items(rows, assign_keys=True)
        n_wired = len(result) if result is not None else 0
        log.info("news_vector.ingest_to_qbus: wired %d rows into qbus", n_wired)
        return {"desk": "news_vector", "n_wired": n_wired, "asof": today.isoformat()}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("news_vector.ingest_to_qbus failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# public: display read — recent events + the uncertainty-regime context
# --------------------------------------------------------------------------- #
def _pct_rank(series, value) -> float | None:
    """Percentile rank (0-100) of `value` within `series`. PURE-ish helper."""
    try:
        import pandas as pd
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) < 30 or value is None or pd.isna(value):
            return None
        return round(float((s <= float(value)).mean()) * 100, 1)
    except Exception:  # noqa: BLE001
        return None


def uncertainty_regime() -> dict | None:
    """Latest EPU / GPR readings as percentile-of-history CONTEXT, incl. the GPR
    THREAT/ACT split (threat-led = reversible-scare candidate; act-led = regime
    break). Reads the collectors/uncertainty_indices store. None if absent."""
    try:
        from lib import store
        out: dict = {}
        epu = store.read("uncertainty", "epu_us")
        if epu is not None and not epu.empty and "epu" in epu.columns:
            v = float(epu["epu"].dropna().iloc[-1])
            out["epu"] = {"value": round(v, 1), "pct": _pct_rank(epu["epu"], v),
                          "asof": str(epu.index.max().date())}
        gpr = store.read("uncertainty", "gpr")
        if gpr is not None and not gpr.empty and "gpr" in gpr.columns:
            last = gpr.dropna(subset=["gpr"]).iloc[-1]
            g = {"value": round(float(last["gpr"]), 1),
                 "pct": _pct_rank(gpr["gpr"], float(last["gpr"])),
                 "asof": str(gpr.index.max().date())}
            if "gpr_threat" in gpr.columns and "gpr_act" in gpr.columns:
                t, a = float(last.get("gpr_threat")), float(last.get("gpr_act"))
                g["threat"] = round(t, 1)
                g["act"] = round(a, 1)
                # which component leads (display tag only; not a score)
                g["lean"] = "threat" if t > a else ("act" if a > t else "balanced")
            out["gpr"] = g
        return out or None
    except Exception as e:  # noqa: BLE001
        log.warning("uncertainty_regime read failed (%s)", e)
        return None


def recent_panel(today: date | None = None, days: int = 7, top_n: int = 8) -> dict | None:
    """Display read for macro.html: recent accrued events grouped by theme + the
    uncertainty-regime context. CONTEXT-ONLY, neutral. None if nothing accrued yet.
    NEVER raises."""
    try:
        import pandas as pd
        today = today or date.today()
        path = _events_path()
        events_block: dict | None = None
        if path.exists():
            df = pd.read_parquet(path)
            if not df.empty:
                cutoff = (today - timedelta(days=days)).isoformat()
                recent = df[df["first_seen_utc"].astype(str) >= cutoff]
                if recent.empty:                       # nothing fresh; show newest anyway
                    recent = df.sort_values("first_seen_utc").tail(top_n * 2)
                by_theme = (recent.groupby("theme").size()
                            .sort_values(ascending=False).to_dict())
                rows = []
                for r in recent.sort_values("first_seen_utc", ascending=False).head(top_n).itertuples():
                    rows.append({"title": r.title, "domain": r.domain, "theme": r.theme,
                                 "tier": int(r.source_tier),
                                 "scheduled_ref": r.scheduled_ref, "url": r.url})
                events_block = {
                    "n_recent": int(len(recent)),
                    "by_theme": {k: int(v) for k, v in by_theme.items()},
                    "unscheduled_share": (round(float((recent["scheduled_ref"].astype(str) == "").mean()), 2)
                                          if len(recent) else None),
                    "items": rows,
                }
        unc = uncertainty_regime()
        if not events_block and not unc:
            return None
        return {"schema": SCHEMA, "is_context_only": True, "asof": today.isoformat(),
                "window_days": days, "events": events_block, "uncertainty": unc,
                "disclaimer": DISCLAIMER_TEXT, "disclaimer_zh": DISCLAIMER_TEXT_ZH}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("news_vector recent_panel failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# LLM structured-extraction stage — STUBBED OFF in P0 (Stage C of the pipeline).
# When enabled later it must reuse engine.catalyst_tone's citation-verified gates
# and write CONTEXT fields only. Left here as the explicit, gated extension point.
# --------------------------------------------------------------------------- #
def extract_structured(record: dict) -> dict:
    """P0 NO-OP: returns the deterministic record unchanged with neutral placeholders
    for the future LLM fields. Gated on news_vector.enabled AND llm_extract; both
    default false, so this never calls a model in P0. Documented extension point."""
    cfg = _cfg()
    neutral = {"category_llm": "unknown", "scope": "unknown",
               "direction_claimed": "unknown", "surprise": None,
               "reversibility": "unknown", "llm_extracted": False}
    if not (cfg.get("enabled", False) and cfg.get("llm_extract", False)):
        return {**record, **neutral}
    # Future: reuse engine.catalyst_tone.digest_document on the PUBLIC headline text,
    # citation-gate every field, collapse to neutral on any failure. Not in P0.
    return {**record, **neutral}
