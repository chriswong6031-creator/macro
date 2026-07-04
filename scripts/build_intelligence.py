"""Build the unified per-ticker intelligence bundle → site/intelligence/by_ticker.json.

Merges two already-built per-ticker artifacts into ONE the Mastermind bot pulls:
  • site/news/by_ticker.json        (engine.financial_news — editorial news flow)
  • site/altdata/mastermind.json    (Signal Intelligence Desk — scored alt-data signal)
  • site/altdata/by_ticker.json     (alt-data v2 substrate, fallback for unscored names)

Single-writer fix (neural-web W0 PR5):
  Previously this module called _crosssurface_radar(), which mutated
  site/basketdata/radar.json in-place after build_baskets had already written it.
  That was second-writer rot (census-flagged).  The fix: build_intelligence now
  writes site/basketdata/radar_news.json as its OWN artifact (keyed by basket_id →
  {headlines: [...]}).  radar_panel.js fetches both radar.json and radar_news.json
  and merges headlines client-side.  radar.json is never touched here.

Run AFTER build_news + build_alt_data + the Alt-Data Brain (so both per-ticker
surfaces exist). Standalone, degrade-safe — missing inputs just yield empty
sub-objects; never breaks the build.

Run:  python -m scripts.build_intelligence
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import intelligence  # noqa: E402

log = logging.getLogger(__name__)


def _build_radar_news(site) -> None:
    """Write site/basketdata/radar_news.json: per-basket-id news headlines sourced
    from site/news/financial.json.  This is build_intelligence's OWN artifact —
    radar.json is NEVER touched here (single-writer discipline).
    Degrade-safe: missing inputs silently yield an empty output."""
    fin_p = site / "news" / "financial.json"
    out_p = site / "basketdata" / "radar_news.json"
    if not fin_p.exists():
        return
    try:
        baskets_news = (json.loads(fin_p.read_text()) or {}).get("baskets", {}) or {}
        radar_news: dict[str, dict] = {}
        for basket_id, bdata in baskets_news.items():
            hs = (bdata or {}).get("headlines", []) or []
            if hs:
                radar_news[basket_id] = {
                    "headlines": [
                        {"title": h.get("title"), "url": h.get("url"),
                         "source": h.get("source") or h.get("domain"),
                         "sentiment": h.get("sentiment")}
                        for h in hs[:3]
                    ]
                }
        (site / "basketdata").mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps({"baskets": radar_news}, default=str))
        log.info("radar_news.json written: %d baskets with headlines", len(radar_news))
    except Exception as e:  # noqa: BLE001
        log.warning("radar_news build failed (%s)", e)


def build(write: bool = True) -> dict:
    vm = intelligence.load_and_build()
    if write:
        site = config.ROOT / config.load()["storage"]["site_dir"]
        outdir = site / "intelligence"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "by_ticker.json").write_text(json.dumps(vm, default=str))
        log.info("built site/intelligence/by_ticker.json — %d tickers (%d with both news+alt)",
                 vm.get("n_tickers", 0), vm.get("n_with_both", 0))
        _build_radar_news(site)
    return vm


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_intelligence failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
