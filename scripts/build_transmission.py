"""Build the Rate & Inflation Transmission page -> site/transmission.html.

Standalone like build_bonds.py / build_crossasset.py (shares only the parquet store +
theme assets). Recomputes the display-only transmission read every build
(engine/rate_inflation_transmission.snapshot) and renders the cause -> first/second/
third-order -> per-asset headwind/tailwind cascade + conditional scenarios + the
inflation decomposition + the honest scored-leg gate result.

Returns 0 on any engine error so it can never break the rest of the site.
Usage: python -m scripts.build_transmission
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_transmission")

# shared Glassnode light palette (same as build_bonds for a consistent product)
C = {
    "blue": "#285FFF", "indigo": "#4559DC", "ink": "#0B1733", "text": "#344054",
    "muted": "#6F6F6F", "faint": "#A0A0A0", "red": "#D30B0B", "amber": "#F5AD42",
    "green": "#1a7f43", "grid": "#EAECF0", "card": "#FFFFFF", "bg": "#F7F8FA",
    "gold": "#C8A53B", "teal": "#1F8A70",
}


def main() -> int:
    try:
        from engine import inputs, rate_inflation_transmission as rit
        f = inputs.build_features()
        tx = rit.snapshot(f)
    except Exception as e:  # noqa: BLE001 — never break the site
        log.error("transmission engine failed: %s", e)
        return 0
    if not tx:
        log.warning("transmission snapshot empty (disabled?) — skipping page")
        return 0

    # YIELD-CURVE analytics block (engine/yield_curve.py) — the unified interest-rate read
    # rendered into the page's new Yield Curve section. Additive: a failure leaves yc=None
    # and the section simply omits, never breaking the page.
    try:
        from engine import yield_curve as ycmod
        yc = ycmod.snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("yield-curve engine failed: %s", e)
        yc = None

    cal = rit.load_calibration() or {}
    gate = cal.get("scored_gate") or {}
    as_of = tx.get("asof", str(f.index[-1].date()))
    span = f"{f.index.min().date()} → {f.index.max().date()}"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("transmission.html.j2").render(
        C=C, as_of=as_of, built=built, span=span, tx=tx, gate=gate, yc=yc)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)
    (site / "transmission.html").write_text(html)
    log.info("wrote %s/transmission.html (%d KB)", site, len(html) // 1024)

    # machine-readable hub contract (for the macro panel + LLM brief), mirrors the
    # latest.json block written by engine.run so the page and the brief never drift.
    outdir = config.data_dir() / "transmission"
    outdir.mkdir(parents=True, exist_ok=True)
    # the transmission contract carries the yield-curve block too, so downstream readers
    # (stock macro-sensitivity, the LLM brief) get the curve read from one file.
    contract = dict(tx)
    if yc is not None:
        contract["yield_curve"] = yc
    (outdir / "latest.json").write_text(json.dumps(contract, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
