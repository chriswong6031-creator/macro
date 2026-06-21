"""Special Situations newswire lane (P2.1) — the form-absent categories.

EDGAR has no trigger form for Strategic Reviews (the #2 stable category), out-of-court
Capital Returns, Deal Terminations, or sub-threshold Divestitures (recon §D4); these are
announced via press release / newswire. This lane reuses engine.news_rss to pull those
categories from quality wires, keeps ONLY items carrying an explicit exchange-tagged ticker
(precision over recall — the desk is ticker-keyed), classifies them with the engine's
keyword rules, and stores them as a separate low-confidence lane the desk merges.

GATED behind config special_situations.newswire (default OFF) until verified in CI; the
network fetch degrades to a no-op. The classify + ticker-extract logic is pure and tested.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

GROUP = "special_situations"
# categories EDGAR has no clean trigger form for -> this lane's remit (recon §D4).
# M&A / SPAC / Spin-Off / Rights stay EDGAR-owned (structural forms), never news-guessed.
_NEWS_CATEGORIES = {"Strategic Reviews", "Capital Returns", "Deal Terminations",
                    "Divestitures", "Restructuring"}

# the search queries per remit category (Google-News RSS via engine.news_rss)
NEWS_QUERIES: dict[str, str] = {
    "Strategic Reviews": "\"strategic alternatives\" OR \"strategic review\" shareholders",
    "Capital Returns": "\"special dividend\" OR \"share repurchase program\" announces",
    "Deal Terminations": "\"terminates merger\" OR \"mutually agreed to terminate\"",
    "Divestitures": "\"agreement to sell\" business OR divest unit",
}

# explicit exchange-tagged ticker, e.g. "(NASDAQ: ABCD)" / "(NYSE American: XY)".
_TICKER_RE = re.compile(
    r"\(\s*(?:NYSE(?:\s*American|\s*Arca)?|NASDAQ|NYSEMKT|AMEX|OTCQX|OTCQB|OTC|CBOE)\s*[:\s]\s*"
    r"([A-Z]{1,5})\s*\)", re.I)


def extract_ticker(text: str | None) -> str | None:
    """Pull an explicit exchange-tagged US ticker from a headline; None if not present.
    Strict by design — a bare '(ABC)' is too noisy to key the desk on."""
    if not text:
        return None
    m = _TICKER_RE.search(str(text))
    return m.group(1).upper() if m else None


def _company_of(title: str, ticker: str | None) -> str:
    """Best-effort issuer name: the headline text before the ticker / first clause."""
    t = str(title)
    if ticker:
        t = t.split("(")[0]
    t = re.split(r"\s+(?:announces|to |agrees|enters|completes|terminates|reports|will )", t, 1,
                 flags=re.I)[0]
    return t.strip(" ,—-:") or str(title)[:60]


def classify_news(text: str | None) -> tuple[str | None, str | None]:
    """Keyword-classify a news headline+summary into a form-absent category, or (None, None).
    Reuses the engine's text rules but accepts ONLY this lane's remit categories."""
    from engine import special_situations as sse
    cat, stage = sse.classify_text(text)
    if cat in _NEWS_CATEGORIES:
        return cat, stage
    return None, None


def _path() -> "object":
    p = config.data_dir() / GROUP / "news.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _cfg() -> dict:
    return config.load().get("special_situations", {}) or {}


def fetch_news_situations(window_days: int = 3, per_cat: int = 40) -> pd.DataFrame:
    """Pull the remit categories from quality wires, keep ticker-tagged + classifiable items,
    and append (keyed by url) to data/special_situations/news.parquet. Gated + no-op on outage."""
    cfg = _cfg()
    p = _path()
    old = pd.read_parquet(p) if p.exists() else None
    if not cfg.get("enabled") or not cfg.get("newswire"):
        log.info("special_situations newswire lane: gated off")
        return old if old is not None else pd.DataFrame()
    try:
        from engine import news_rss
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations newswire: news_rss unavailable: %s", e)
        return old if old is not None else pd.DataFrame()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows: list[dict] = []
    for _cat, q in NEWS_QUERIES.items():
        try:
            items = news_rss.query(q, window_days=window_days, min_tier=2)[:per_cat]
        except Exception as e:  # noqa: BLE001
            log.warning("special_situations newswire query failed (%s): %s", _cat, e)
            continue
        for it in items:
            tkr = extract_ticker(it.get("title"))
            if not tkr:
                continue
            cat, stage = classify_news(f"{it.get('title','')} {it.get('summary','')}")
            if not cat:
                continue
            url = it.get("url") or ""
            rows.append({
                "id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:16],
                "ticker": tkr, "company": _company_of(it.get("title", ""), tkr),
                "category": cat, "stage": stage or "announced",
                "date": (it.get("seendate") or "")[:10] or now[:10],
                "url": url, "summary": it.get("title"), "source": it.get("source"),
                "confidence": "low", "first_seen": now,
            })
    new = pd.DataFrame(rows)
    if new.empty:
        return old if old is not None else new
    merged = pd.concat([old, new], ignore_index=True) if old is not None and not old.empty else new
    merged = merged.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)
    merged.to_parquet(p, index=False)
    log.info("special_situations newswire lane: +%d items, %d total", len(new), len(merged))
    return merged
