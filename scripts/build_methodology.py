"""Build the methodology page -> site/methodology.html.

Mostly-static documentation of how the Factor Lab / Baskets / Seasonality pages are
constructed (our actual free-data methodology + honest limits), with a few live stats
pulled from the already-built JSONs (IC scorecard, factor series, baskets). Additive —
any missing input falls back to a sensible default so it can never break the build.

Usage: python -m scripts.build_methodology
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_methodology")


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    site = config.ROOT / "site"
    ic = _load(site / "factordata" / "ic_scorecard.json") or _load(config.data_dir() / "edgar" / "ic_scorecard.json")
    fs = _load(site / "factordata" / "factor_series.json")
    bk = _load(site / "basketdata" / "baskets.json")

    facs = (ic.get("factors") or {})
    meth = {
        "as_of": fs.get("as_of") or bk.get("as_of") or "—",
        "n_factors": len(fs.get("factors") or []) or 8,
        "n_baskets": len(bk.get("baskets") or []) or 14,
        "n_categories": len(bk.get("categories") or []) or 7,
        "n_sectors": len((fs.get("chart_data") or {}).get("sector") or {}) or 11,
        "ic_span": ic.get("span") or "the free-data window",
        "ic_rebalances": ic.get("rebalances") or 11,
        "ic_universe": ic.get("median_universe") or 1300,
        "ic_any_survive": any(v.get("survives_fdr") for v in facs.values()) if facs else False,
    }
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("methodology.html.j2").render(meth=meth, generated_utc=built)
    write_page(site / "methodology.html", html)
    log.info("wrote %s/methodology.html (%d KB)", site, len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
