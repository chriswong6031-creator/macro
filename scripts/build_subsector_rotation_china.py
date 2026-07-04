"""Build the China subsector-rotation feed.

Reads the committed China basket JSONs (``site/chinabasketdata/baskets_ths.json`` for the
同花顺 concept subsectors, ``baskets.json`` for the curated thematic themes) and writes
``site/marketdata/subsector_rotation_china.json`` consumed by ``subsector_rotation_china.html``.
Offline-safe — the basket JSONs are the source, so this runs after the China baskets build.

    python -m scripts.build_subsector_rotation_china
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine import subsector_rotation_china as srcn
from lib import config

log = logging.getLogger("build_subsector_rotation_china")


def build(site: Path | None = None, *, generated_utc: str | None = None) -> dict:
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    ths_p = site / "chinabasketdata" / "baskets_ths.json"
    cur_p = site / "chinabasketdata" / "baskets.json"
    if not ths_p.exists() or not cur_p.exists():
        log.warning("China basket JSONs missing (%s / %s) — skipped", ths_p, cur_p)
        return {}
    ths = json.loads(ths_p.read_text())
    cur = json.loads(cur_p.read_text())

    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    payload = srcn.compute_china_rotation(ths, cur, generated_utc=generated_utc)

    out = site / "marketdata" / "subsector_rotation_china.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s — %d subsectors, %d themes (emerging: %s)",
             out, payload.get("n_subsectors"), payload.get("n_themes"),
             ", ".join(payload.get("highlights", {}).get("emerging", [])[:4]))
    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
