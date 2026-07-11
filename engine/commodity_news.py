"""Commodity Vector — news/event ANNOTATION layer (Phase 6).

DEFERRED · GATED · ANNOTATION-ONLY · DEFAULT OFF. This is honest CONTEXT, never a
scoring input. It is a LEAF module: it imports nothing from the mechanical core
(commodity_signals/calibrate) and nothing in the scoring path imports it. Every
public function returns plain data or None and NEVER raises into the pipeline —
all network/parse/LLM failures degrade to "no annotation".

Two capabilities:
  1. annotate_event(asset, date, move_desc): fetch a few relevant headlines from
     GDELT (free, keyless) around a detected residual/shock date; OPTIONALLY label
     a likely cause with the Anthropic API IFF (config.llm_classify AND an API key
     present). Returns the annotation dict (headlines + optional likely_cause +
     a machine-readable is_context_only flag + the disclaimer), or None when the
     master switch is off.
  2. upcoming_catalysts(today): a forward-looking OPEC / FOMC / EIA watch list from
     a static 2026 skeleton (keyless, always available) — scheduling info, not a
     forecast, also context-only.

Design verified against research/ (GDELT DOC 2.0 + claude-api skill). See the
Phase-6 synthesis for the full spec; gotchas honored: GDELT ~3-month history,
≥6s pacing, 200+json content-type guard, seendate=%Y%m%dT%H%M%SZ.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from lib import config

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
COMMODITY_QUERY = {
    "gold":   '(gold OR bullion OR XAU)',
    "silver": '(silver OR XAG)',
    "oil":    '(oil OR crude OR WTI OR Brent OR OPEC)',
    "copper": '(copper OR "COMEX copper")',
}
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}

DISCLAIMER_TEXT = (
    "Context only — not a signal. Headlines and any “likely cause” shown here are "
    "background context, fetched after the fact from public news (GDELT) and, when enabled, "
    "summarized by an AI model. They are NOT inputs to any score, signal or allocation, and "
    "the mechanical model never sees them. AI-attributed causes can be wrong or incomplete — "
    "“unknown” means the evidence was insufficient, which is the honest answer. "
    "Upcoming-catalyst dates are scheduling information, not forecasts."
)

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence": {"type": "string"},
        "cause": {"type": "string", "enum": [
            "supply_disruption", "demand_shock", "geopolitical_conflict",
            "sanctions_or_trade_policy", "weather_or_natural_disaster",
            "inventory_or_production_data", "currency_or_macro",
            "ofac_opec_or_cartel_action", "unknown"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["evidence", "cause", "confidence"],
    "additionalProperties": False,
}
CLASSIFY_SYSTEM = (
    "You label the LIKELY CAUSE of an already-detected commodity price shock, using ONLY the "
    "provided news headlines. This is annotation metadata only — it never feeds any score, "
    "signal or trading decision. Guessing is harmful; abstaining is correct.\n"
    "Rules:\n- Choose exactly one cause from the allowed list, or \"unknown\".\n"
    "- Use \"unknown\" if the headlines do not clearly point to ONE dominant cause, contradict "
    "each other, or are not plainly about this commodity's move.\n"
    "- Quote the exact headline phrase that justifies your choice in \"evidence\". If you "
    "cannot quote a supporting phrase, the cause is \"unknown\".\n"
    "- Report \"confidence\". Prefer \"unknown\" over a low-confidence guess."
)


def _cfg() -> dict:
    return config.load().get("commodity_news", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# GDELT headline fetch (free, keyless)
# --------------------------------------------------------------------------- #
def _cache_path(asset: str, d: date, cfg: dict):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("cache_dir", "data/commodity/news_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"{asset}_{d.isoformat()}.json"


def _fetch_gdelt(asset: str, d: date, cfg: dict) -> tuple[list[dict], str | None]:
    """Return (headlines, degraded_reason). Never raises.

    Delegates HTTP, throttling, and retry handling to engine.gdelt_client so
    all GDELT callers share a single cross-process pacing lock (GDELT 5s/IP rule;
    nine callers without shared throttle caused a penalty-box incident 2026-06-20).

    The commodity caller needs two extra fields per article (language, sourcecountry)
    which are not present in the normalised gdelt_client output; we re-add them as
    empty strings to preserve the downstream dict shape exactly."""
    from engine import gdelt_client as _gc
    cache = _cache_path(asset, d, cfg)
    ttl = int(cfg.get("cache_ttl_hours", 24)) * 3600

    # cache read — commodity_news stores under key 'headlines', not 'articles'
    if cache.exists():
        try:
            age = datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime
            if age < ttl:
                blob = json.loads(cache.read_text())
                cached = blob.get("headlines")
                if cached is not None:
                    return cached, blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass

    win = cfg.get("window_days", 3)
    start = datetime(d.year, d.month, d.day) - timedelta(days=win)
    end = datetime(d.year, d.month, d.day) + timedelta(days=win, hours=23, minutes=59, seconds=59)
    query = f"{COMMODITY_QUERY.get(asset, asset)} sourcelang:{cfg.get('lang', 'eng')}"
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": str(cfg.get("max_records", 6)), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    headlines: list[dict] = []
    reason: str | None = None
    try:
        raw_articles, reason = _gc.get_articles(params, timeout=30)
        if raw_articles is None:
            raw_articles = []
        if reason == "no_articles":
            reason = "no_headlines"
        # gdelt_client now passes through language/sourcecountry from the raw GDELT article
        max_r = cfg.get("max_records", 6)
        for a in raw_articles[:max_r]:
            headlines.append({
                "title":         a.get("title", ""),
                "url":           a.get("url", ""),
                "domain":        a.get("domain", ""),
                "seendate":      a.get("seendate", ""),
                "language":      a.get("language", ""),
                "sourcecountry": a.get("sourcecountry", ""),
            })
        if raw_articles and not headlines:
            reason = "no_headlines"
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("gdelt fetch failed (%s)", e)
        reason = "fetch_error"

    # Cache only when headlines are non-empty (INTENTIONAL: empty-success is transient
    # and should re-fetch rather than serve stale silence for the full TTL; failures
    # must never be cached to preserve retry on next nightly cycle).
    if headlines:
        try:
            cache.write_text(json.dumps({"headlines": headlines, "degraded_reason": reason}))
        except Exception:  # noqa: BLE001
            pass
    return headlines, reason


# --------------------------------------------------------------------------- #
# optional LLM cause classifier (gated on flag AND key)
# --------------------------------------------------------------------------- #
def _classify_cause(asset: str, move_desc: str, headlines: list[dict],
                    cfg: dict) -> tuple[dict | None, str | None]:
    if not cfg.get("llm_classify", False):
        return None, None
    if not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DISABLE_COMMODITY_NEWS_LLM"):
        return None, None
    if not headlines:
        return None, None
    try:
        import anthropic
    except ImportError:
        return None, "llm_error"
    try:
        client = anthropic.Anthropic()
        lines = "\n".join(f"- {h['title']} ({h['domain']}, {h['seendate'][:10]})" for h in headlines)
        user = f"Commodity: {asset}\nDetected move: {move_desc}\nHeadlines:\n{lines}"
        resp = client.messages.create(
            model=cfg.get("llm_model", "claude-haiku-4-5"), max_tokens=256,
            system=CLASSIFY_SYSTEM, messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}})
        if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
            return None, "llm_refusal"
        text = next(b.text for b in resp.content if getattr(b, "type", "") == "text")
        parsed = json.loads(text)
        # auditable code-side confidence gate (not in the prompt)
        thr = cfg.get("llm_min_confidence", "high")
        if _CONF_RANK.get(parsed.get("confidence"), 0) < _CONF_RANK.get(thr, 2):
            parsed["cause"] = "unknown"
        parsed["model"] = cfg.get("llm_model", "claude-haiku-4-5")
        parsed["applied_threshold"] = thr
        return parsed, None
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("llm classify failed (%s)", e)
        return None, "llm_error"


# --------------------------------------------------------------------------- #
# public: annotate one detected event
# --------------------------------------------------------------------------- #
def annotate_event(asset: str, event_date: date, move_desc: str = "") -> dict | None:
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    ann = {"schema": "commodity_news.v1", "is_context_only": True, "asset": asset,
           "event_date": event_date.isoformat(),
           "fetched_at": datetime.now(timezone.utc).isoformat(), "source": "gdelt_doc_2.0",
           "source_query": f"{COMMODITY_QUERY.get(asset, asset)} sourcelang:{cfg.get('lang','eng')}",
           "headlines": [], "likely_cause": None, "degraded_reason": None,
           "disclaimer": DISCLAIMER_TEXT}
    # GDELT only covers a rolling ~3 months — don't pretend to back-annotate older shocks
    if (date.today() - event_date).days > 90:
        ann["degraded_reason"] = "outside_gdelt_window"
        return ann
    headlines, reason = _fetch_gdelt(asset, event_date, cfg)
    ann["headlines"] = headlines
    ann["degraded_reason"] = reason
    cause, lreason = _classify_cause(asset, move_desc, headlines, cfg)
    ann["likely_cause"] = cause
    if lreason and not reason:
        ann["degraded_reason"] = lreason
    return ann


# --------------------------------------------------------------------------- #
# public: upcoming catalysts (delegates to the shared engine.event_calendar)
# --------------------------------------------------------------------------- #
def upcoming_catalysts(today: date | None = None, horizon_days: int = 14) -> list[dict]:
    """Forward OPEC / FOMC / EIA-WPSR watch list (oil-centric), context-only. The
    schedule now lives in the unified engine.event_calendar (single source of truth
    shared with macro.html); this thin wrapper keeps the commodities-page contract."""
    from engine import event_calendar as _ec
    return _ec.commodity_events(today, horizon_days)
