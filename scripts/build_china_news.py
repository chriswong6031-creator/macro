"""Emit machine-readable China News intel artifacts (site/chinanews/*.json).

Runs the multi-source ingest (akshare flash wires + state RSS → PIT event bus), then
writes site/chinanews/{sentiment,feed,by_ticker}.json.  The page site/china_news.html
is rendered separately by build_china.py using engine/china_news.py's view model —
this script owns ONLY the intel JSON artifacts.
Callable standalone (`python -m scripts.build_china_news`) and importable (build()).
CONTEXT-ONLY · never raises into the site build. See research/CHINA_INTEL_POWERHOUSE.md §1.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _by_basket(feed: dict | None) -> dict:
    """Group recent headlines by the cn_* baskets they reference (back-compat)."""
    out: dict[str, list] = {}
    for it in (feed or {}).get("items", []):
        for bid in it.get("baskets", []):
            out.setdefault(bid, []).append(
                {"title": it["title"], "theme": it["theme"], "url": it.get("url", "")})
    return out


def _by_ticker_index(feed: dict | None) -> dict:
    """TRUE ticker-keyed index — the named Mastermind hand-off (was basket-keyed before)."""
    out: dict[str, list] = {}
    for it in (feed or {}).get("items", []):
        for tk in it.get("tickers", []):
            out.setdefault(tk, []).append(
                {"title": it["title"], "theme": it["theme"], "score": it.get("score"),
                 "importance_en": it.get("importance_en"), "url": it.get("url", "")})
    return out


def build() -> dict | None:
    from engine import china_news_intel as ni

    # 1) ingest the multi-source wire + RSS into the PIT event bus (best-effort)
    try:
        summary = ni.ingest()
        if summary:
            log.info("china_news_intel ingest: %s new / %s total",
                     summary.get("n_new"), summary.get("n_total"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china news ingest failed (%s); rendering from accrued store", e)

    # 2) assemble the intel view-model
    news = ni.panel()

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)

    # 3) machine-readable feeds — written FIRST so data artifacts never freeze because
    #    a downstream render fails (site/china_news.html is rendered by build_china.py
    #    with engine/china_news.py's view model; this script owns ONLY the
    #    site/chinanews/*.json intel artifacts).
    cndir = site / "chinanews"
    cndir.mkdir(parents=True, exist_ok=True)
    sent = ni.sentiment()
    feed = ni.feed()
    (cndir / "sentiment.json").write_text(
        json.dumps(sent or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (cndir / "feed.json").write_text(
        json.dumps(feed or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (cndir / "by_ticker.json").write_text(json.dumps(
        {"schema": "china_news_intel.by_ticker.v2", "is_context_only": True,
         "by_basket": _by_basket(feed), "by_ticker": _by_ticker_index(feed)},
        ensure_ascii=False, separators=(",", ":"), default=str))
    log.info("wrote %s/chinanews/{sentiment,feed,by_ticker}.json", site)

    return news


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
