"""Build the standalone China News powerhouse page + machine-readable feeds.

Runs the multi-source ingest (akshare flash wires + state RSS → PIT event bus), then
renders site/china_news.html and emits site/chinanews/{sentiment,feed,by_ticker}.json.
Callable standalone (`python -m scripts.build_china_news`) and importable (build()).
CONTEXT-ONLY · never raises into the site build. See research/CHINA_INTEL_POWERHOUSE.md §1.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config

log = logging.getLogger(__name__)

# theme.css / theme.js power the shared chrome (nav, dark mode, lang toggle)
ASSETS = ("theme.css", "theme.js")


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _by_ticker(feed: dict | None) -> dict:
    """Group recent headlines by the cn_* baskets they reference (the future bot join)."""
    out: dict[str, list] = {}
    for it in (feed or {}).get("items", []):
        for bid in it.get("baskets", []):
            out.setdefault(bid, []).append(
                {"title": it["title"], "theme": it["theme"], "url": it.get("url", "")})
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

    # 2) assemble the page view-model
    news = ni.panel()

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)

    # 3) render the standalone page
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china_news.html.j2").render(news=news)
    (site / "china_news.html").write_text(html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            (site / a).write_text(src.read_text())
    log.info("wrote %s/china_news.html (%d KB)", site, len(html) // 1024)

    # 4) machine-readable feeds (for the intel bus + future China Mastermind)
    cndir = site / "chinanews"
    cndir.mkdir(parents=True, exist_ok=True)
    sent = ni.sentiment()
    feed = ni.feed()
    (cndir / "sentiment.json").write_text(
        json.dumps(sent or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (cndir / "feed.json").write_text(
        json.dumps(feed or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (cndir / "by_ticker.json").write_text(json.dumps(
        {"schema": "china_news_intel.by_ticker.v1", "is_context_only": True,
         "by_basket": _by_ticker(feed)},
        ensure_ascii=False, separators=(",", ":"), default=str))
    log.info("wrote %s/chinanews/{sentiment,feed,by_ticker}.json", site)

    return news


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
