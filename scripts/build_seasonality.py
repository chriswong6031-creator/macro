"""Build the factor-seasonality page -> site/seasonality.html (+ factordata/factor_seasonality.json).

Standalone (clones build_discovery.py): reads data/french/factors.parquet via
engine.factor_seasonality.compute_factor_seasonality() and renders the per-factor
calendar-month seasonality grid (full history + trailing 30y). UNSCORED display
context with a definition-mismatch disclosure (academic total-US-market factors,
not our S&P-1500 z quintiles). Additive — any failure logs and returns 0 so it can
never break the rest of the site.

Usage: python -m scripts.build_seasonality
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
log = logging.getLogger("build_seasonality")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.factor_seasonality import compute_factor_seasonality
        seas = compute_factor_seasonality()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("factor seasonality failed: %s", e)
        return 0
    if not seas:
        log.warning("no Ken French data (run `python -m scripts.collect --only french`) — skipping")
        return 0

    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "factor_seasonality.json").write_text(json.dumps(seas, separators=(",", ":"), default=str))

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr, zip=zip)
    html = env.get_template("seasonality.html.j2").render(seas=seas, built=built)
    write_page(site / "seasonality.html", html)
    log.info("wrote %s/seasonality.html (%d factors, %d KB)",
             site, len(seas["factors"]), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
