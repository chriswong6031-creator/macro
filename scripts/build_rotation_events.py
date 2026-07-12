"""scripts/build_rotation_events.py — Rotation Command W1 nightly step (RC-R1 + RC-R6).

Resolves the sector-leg registry (config/sector_legs.json) to composite closes ONCE, then:

  • engine.sector_fragmentation → site/marketdata/sector_fragmentation.json
      (per-sector "is the aggregate representative?" board — the RC-R3/R6 chip feed)
  • engine.rotation_events     → site/marketdata/rotation_events.json
      (active first-class ROTATION events with receipts, EN/ZH copy, severity)
      + data/rotation_events/events.jsonl   (append-only ledger, expected-NULL)
      + data/rotation_events/state.json     (lifecycle: TTL / lapse / lockout)

DISPLAY/CONTEXT TIER, additive, never fatal. Registered in daily.yml cl_baskets.

    python -m scripts.build_rotation_events
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import rotation_events, sector_fragmentation, sector_legs  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_rotation_events")


def _clean(o):
    """numpy scalars → native; NaN/Inf → None (strict-JSON safe)."""
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False))


def build(site: Path | None = None, *, generated_utc: str | None = None) -> dict:
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    registry = sector_legs.load_registry()
    sectors = sector_legs.sector_closes(registry)
    n_legs = sum(len(s["legs"]) for s in sectors.values())
    log.info("sector legs resolved: %d sectors, %d legs", len(sectors), n_legs)

    frag = sector_fragmentation.compute(sectors, generated_utc=generated_utc)
    _write_json(site / "marketdata" / "sector_fragmentation.json", frag)
    log.info("fragmentation: %d/%d sectors flagged — %s",
             frag["n_fragmented"], len(frag["sectors"]),
             ", ".join(r["key"] for r in frag["sectors"] if r["fragmented"]) or "none")

    payload = rotation_events.run_nightly(sectors, config.data_dir(),
                                          generated_utc=generated_utc)
    payload["fragmented_sectors"] = [r["key"] for r in frag["sectors"] if r["fragmented"]]
    # RC-R10: the honest late-ruler (descriptive, from the RC-R8 replay census) — lets
    # the rail print "vs the median historical handoff run" instead of a binary 'late'.
    try:
        payload["ruler"] = json.loads(
            (config.data_dir() / "rotation_events" / "episode_ruler.json").read_text())
    except Exception:  # noqa: BLE001 — ruler absent → rail simply omits the line
        pass
    _write_json(site / "marketdata" / "rotation_events.json", payload)

    # RC-R5: creation alerts into the shared rotation alert store (same schema the
    # triage already reads; dedup by id, prune like subsector_rotation_alerts.rebuild).
    try:
        from engine import subsector_rotation_alerts as sra
        new_alerts = rotation_events.to_alerts(payload)
        if new_alerts:
            import pandas as pd
            by_id = {e["id"]: e for e in sra.load_events()}
            for e in new_alerts:
                by_id.setdefault(e["id"], e)
            merged = list(by_id.values())
            ref = max(pd.Timestamp(e["ts"]) for e in merged)
            merged = [e for e in merged if pd.Timestamp(e["ts"]) >= ref - pd.Timedelta(days=sra.KEEP_DAYS)]
            merged.sort(key=lambda e: e["ts"])
            sra.write_events(merged)
            log.info("rotation-event alerts: %d fired (%s)", len(new_alerts),
                     ", ".join(a["asset"] for a in new_alerts[:4]))
    except Exception as e:  # noqa: BLE001 — alerts are additive, never fatal
        log.warning("rotation-event alerts failed: %s", e)
    log.info("rotation events: %d active (%s), %d created, %d closed — as_of %s",
             len(payload["active"]),
             ", ".join(e["id"] for e in payload["active"][:4]) or "none",
             len(payload["created_tonight"]), len(payload["closed_tonight"]),
             payload["as_of"])
    return {"sectors": len(sectors), "legs": n_legs,
            "fragmented": frag["n_fragmented"],
            "active_events": len(payload["active"]),
            "created": payload["created_tonight"],
            "as_of": payload["as_of"]}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
