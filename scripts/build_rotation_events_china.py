"""scripts/build_rotation_events_china.py — RC-R14 China rotation-event detector (nightly).

Mirrors ``scripts/build_rotation_events.py`` for the China region.  Resolves
``config/sector_legs_china.json`` → curated basket close series (from
``site/chinabasketdata/baskets.json`` — no new data dependency) → runs the
same ``engine.rotation_events`` detector pipeline → writes:

  • site/marketdata/rotation_events_china.json     — display payload (active events)
  • data/rotation_events_china/events.jsonl        — append-only ledger (RC-R2 law)
  • data/rotation_events_china/state.json          — lifecycle state (TTL/lapse/lockout)

DISPLAY/CONTEXT TIER only — no rank, gate, size, or stance change.
Registered in the asia-close.yml lane after build_subsector_rotation_china.

Alerts: the shared ``subsector_rotation_alerts`` store has no China region routing
in ``engine/alert_triage.py`` — China rotation alerts are NOT wired here to avoid
half-wired plumbing.  This is disclosed in the PR body (RC-R14).

    python -m scripts.build_rotation_events_china
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

from engine import rotation_events, sector_legs_china  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_rotation_events_china")


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

    sectors = sector_legs_china.sector_closes(site_dir=site)
    n_legs = sum(len(s["legs"]) for s in sectors.values())
    log.info("cn sector legs resolved: %d sectors, %d legs", len(sectors), n_legs)

    if not sectors:
        log.warning("build_rotation_events_china: no sectors resolved — skipped")
        return {"sectors": 0, "legs": 0, "active_events": 0, "created": [], "as_of": None}

    payload = rotation_events.run_nightly(
        sectors, config.data_dir(),
        generated_utc=generated_utc,
        data_subdir="rotation_events_china",
    )

    # NOTE: No fragmentation step for China — sector_fragmentation.compute() uses
    # ETF closes (unavailable for China baskets) and is a US-specific construct.
    # The payload ships without fragmented_sectors.

    _write_json(site / "marketdata" / "rotation_events_china.json", payload)

    # NOTE: Alerts intentionally skipped — alert_triage.py has no China routing for
    # rotation_event type.  Disclosed in PR body (RC-R14).

    log.info("cn rotation events: %d active (%s), %d created, %d closed — as_of %s",
             len(payload["active"]),
             ", ".join(e["id"] for e in payload["active"][:4]) or "none",
             len(payload["created_tonight"]), len(payload["closed_tonight"]),
             payload["as_of"])
    return {"sectors": len(sectors), "legs": n_legs,
            "active_events": len(payload["active"]),
            "created": payload["created_tonight"],
            "as_of": payload["as_of"]}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
