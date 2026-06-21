"""International special-situations collectors (Phase 4) — UK RNS + Canada, gated.

The non-US majority is the digest's moat. SEDAR+ direct scraping is ToS/CAPTCHA-barred and
TDnet/EDINET needs Japanese ingest, so this Phase-4 increment takes the cheap, English,
structured slice: UK (LSE/RNS) and Canada (TSX) announcements via the existing news_rss
reader, routed through the deterministic intl classifier. Each market is GATED behind its
own config flag (default OFF) until verified in CI; keeps only items with an explicit
exchange-tagged ticker, and stores a separate cross-border lane the desk merges.

The classify + ticker-extraction logic is pure and tested; the network fetch degrades to a
no-op when gated off or unreachable.
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

# exchange tag in a headline -> ticker suffix, e.g. "(LSE: BARC)" -> BARC.L
_EXCH_SUFFIX = {
    "LSE": "L", "LON": "L", "AIM": "L", "TSX": "TO", "TSXV": "V", "TSX-V": "V",
    "HKEX": "HK", "SEHK": "HK", "ASX": "AX", "NSE": "NS", "BSE": "BO",
}
_INTL_TICKER_RE = re.compile(
    r"\(\s*(LSE|LON|AIM|TSXV|TSX-V|TSX|HKEX|SEHK|ASX|NSE|BSE)\s*[:\s]\s*([A-Z0-9]{1,6})\s*\)",
    re.I)

# per-market gate flag + targeted queries (Google-News RSS via engine.news_rss)
MARKETS: dict[str, dict] = {
    "uk": {"flag": "intl_uk", "queries": [
        "RNS \"Rule 2.7\" offer", "RNS \"scheme of arrangement\" cancellation listing",
        "RNS \"strategic review\" OR \"formal sale process\" plc"]},
    "canada": {"flag": "intl_canada", "queries": [
        "TSX \"plan of arrangement\" acquire", "SEDAR \"early warning report\"",
        "TSX \"take-over bid\" OR \"normal course issuer bid\""]},
}


def extract_intl_ticker(text: str | None) -> str | None:
    """Suffixed ticker from an exchange-tagged headline ('(LSE: BARC)' -> 'BARC.L'); None
    if absent. Strict — the desk is ticker-keyed, a bare name is too noisy."""
    if not text:
        return None
    m = _INTL_TICKER_RE.search(str(text))
    if not m:
        return None
    suf = _EXCH_SUFFIX.get(m.group(1).upper())
    return f"{m.group(2).upper()}.{suf}" if suf else None


def _company_of(title: str, ticker: str | None) -> str:
    t = str(title).split("(")[0] if ticker else str(title)
    t = re.split(r"\s+(?:announces|to |agrees|enters|completes|launches|RNS)", t, 1, flags=re.I)[0]
    return t.strip(" ,—-:") or str(title)[:60]


def _cfg() -> dict:
    return config.load().get("special_situations", {}) or {}


def _path():
    p = config.data_dir() / GROUP / "intl.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch_intl_situations(window_days: int = 4, per_query: int = 30) -> pd.DataFrame:
    """Pull UK/Canada announcements for the enabled markets, keep exchange-tagged +
    classifiable items, append (keyed by url) to data/special_situations/intl.parquet.
    Gated per-market; no-op on outage. Cross-border by construction."""
    cfg = _cfg()
    p = _path()
    old = pd.read_parquet(p) if p.exists() else None
    markets = [m for m, spec in MARKETS.items() if cfg.get("enabled") and cfg.get(spec["flag"])]
    if not markets:
        log.info("special_situations intl lane: all markets gated off")
        return old if old is not None else pd.DataFrame()
    try:
        from engine import news_rss
        from engine import intl_special_situations as isi
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations intl: deps unavailable: %s", e)
        return old if old is not None else pd.DataFrame()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows: list[dict] = []
    for m in markets:
        for q in MARKETS[m]["queries"]:
            try:
                items = news_rss.query(q, window_days=window_days, min_tier=2)[:per_query]
            except Exception as e:  # noqa: BLE001
                log.warning("special_situations intl query failed (%s): %s", q, e)
                continue
            for it in items:
                tkr = extract_intl_ticker(it.get("title"))
                if not tkr:
                    continue
                cat, stage = isi.classify_intl(f"{it.get('title','')} {it.get('summary','')}")
                if not cat:
                    continue
                url = it.get("url") or ""
                rows.append({
                    "id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:16],
                    "ticker": tkr, "company": _company_of(it.get("title", ""), tkr),
                    "category": cat, "stage": stage or "announced", "market": m,
                    "country": isi.country_for(ticker=tkr),
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
    log.info("special_situations intl lane: +%d items, %d total", len(new), len(merged))
    return merged
