"""Build the subsector-rotation feed.

Reads the committed Finviz themes snapshot (``data/themes_heatmap/*.json``,
refreshed by ``scripts/fetch_finviz_themes.py``) and writes
``site/marketdata/subsector_rotation.json`` consumed by
``site/subsector_rotation.html``. Offline-safe — the snapshot is the source.

    python -m scripts.build_subsector_rotation
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import subsector_rotation as sr  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_subsector_rotation")


def _data(*parts: str) -> Path:
    return config.data_dir().joinpath(*parts)


def build(site: Path | None = None, *, generated_utc: str | None = None) -> dict:
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    tree = json.loads(_data("themes_heatmap", "themes_tree.json").read_text())
    snap = json.loads(_data("themes_heatmap", "perf_snapshot.json").read_text())

    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    payload = sr.compute_rotation(
        tree,
        snap.get("subsector_perf") or {},
        snap.get("member_perf") or {},
        generated_utc=generated_utc,
        asof=snap.get("asof") or "",
    )

    outdir = site / "marketdata"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "subsector_rotation.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s — %d subsectors, %d themes (emerging: %s)",
             out, payload["n_subsectors"], payload["n_themes"],
             ", ".join(payload["highlights"]["emerging"][:4]))

    # Change-detection alerts: ping when a subsector rotates in/out (additive).
    try:
        from engine import subsector_rotation_alerts
        fired = subsector_rotation_alerts.rebuild(payload)
        if fired:
            log.info("rotation alerts: %d fired (%s)", len(fired),
                     ", ".join(e["asset"] for e in fired[:5]))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("rotation alerts failed: %s", e)
    return payload


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
