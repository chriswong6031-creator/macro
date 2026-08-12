"""Render five first-class international macro dashboards from one view contract.

Usage:
    python -m scripts.build_international_macro

The normal pipeline invokes this after ``engine.intl_run`` has refreshed
``data/intl/latest.json`` and the per-country history parquets.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.international_macro_dashboard import (
    REGIONS,
    build_country_view,
    load_history,
    validate_view,
)
from lib import config, site_assets
from lib.pages import write_page

log = logging.getLogger("build_international_macro")

ASSETS = (
    "theme.css",
    "product-nav-icons.css",
    "navigation-refresh.css",
    "theme.js",
)


def _load_latest() -> dict:
    path = config.data_dir() / "intl" / "latest.json"
    if not path.exists():
        raise FileNotFoundError(f"international engine output missing: {path}")
    return json.loads(path.read_text())


def _radar_display(record: dict) -> dict | None:
    """Normalize this market's nightly ``risk_radar_intl`` snapshot into the ``rd`` shape
    the shared .rrx Risk Radar card consumes (``engine/market_state._radar_to_rd`` — the
    one transform already used by the US modal and the China / HK / Canada boards, so the
    five international dashboards show the same radar layer, not a second dialect).

    Display-only: the transform reads what ``engine/intl_run.py`` already persisted on the
    record (``record["risk_radar"]``) and computes nothing new. Returns ``None`` — the page
    then renders with no card and keeps its own pullback tile — when the market carries no
    snapshot yet (a profile that raised inside intl_run, or a ``latest.json`` written before
    the radar was wired), so a missing radar can never fail or empty a dashboard.
    """
    radar = record.get("risk_radar") or {}
    if not radar.get("state"):
        return None
    if (radar.get("drawdown_prob") or {}).get("h21") is None:
        # No calibrated odds -> the card would carry less than the tile it replaces.
        return None
    try:
        from engine.market_state import _radar_to_rd

        return _radar_to_rd(radar)
    except Exception:  # noqa: BLE001 — additive display layer, never fatal
        log.warning(
            "risk radar card transform failed for %s; rendering without it",
            record.get("cc"),
        )
        return None


def build_all(latest: dict | None = None) -> list[Path]:
    latest = latest or _load_latest()
    records = {
        str(record.get("cc")): record
        for record in (latest.get("records") or [])
        if record.get("cc")
    }
    missing = sorted(set(REGIONS) - set(records))
    if missing:
        raise RuntimeError(
            f"international engine missing required markets: {', '.join(missing)}"
        )

    root = Path(config.ROOT)
    site = Path(config.load()["storage"]["site_dir"])
    site.mkdir(parents=True, exist_ok=True)
    data_out = config.data_dir() / "international_macro"
    data_out.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("international_macro.html.j2")
    outputs: list[Path] = []
    for cc, spec in REGIONS.items():
        view = build_country_view(records[cc], load_history(cc))
        validate_view(view)
        (data_out / f"{cc}_latest.json").write_text(
            json.dumps(view, indent=2, ensure_ascii=False, default=str) + "\n"
        )
        page = site / spec.route
        # RADAR is a render-time display variable, deliberately outside the
        # international_macro_dashboard.v1 payload written above: it is a re-shaping of
        # data/intl/latest.json for one card, not a new term of the data contract.
        write_page(page, template.render(D=view, RADAR=_radar_display(records[cc])))
        outputs.append(page)
        log.info("wrote %s (%s, score=%s)", page.name, cc, view["decision"]["score"])

    for asset in ASSETS:
        src = root / "templates" / asset
        if src.exists():
            site_assets.copy_asset(asset, src, site)
    return outputs


def main() -> int:
    try:
        outputs = build_all()
    except Exception as exc:
        print(
            f"::error title=international macro dashboards failed::{exc}",
            flush=True,
        )
        log.exception("international macro dashboard build failed")
        return 1
    log.info("international macro dashboards: %d routes rendered", len(outputs))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
