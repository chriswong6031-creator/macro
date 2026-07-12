"""scripts/build_rotation_events_hk.py — RC-R14 HK rotation-event detector (nightly).

Mirrors ``scripts/build_rotation_events_china.py`` for the HK region.  Resolves
``config/sector_legs_hk.json`` → curated HK basket close series (from
``site/hkbasketdata/baskets.json`` — no new data dependency) → runs the
same ``engine.rotation_events`` detector pipeline → writes:

  • site/marketdata/rotation_events_hk.json     — display payload (active events)
  • data/rotation_events_hk/events.jsonl        — append-only ledger (RC-R2 law)
  • data/rotation_events_hk/state.json          — lifecycle state (TTL/lapse/lockout)

DISPLAY/CONTEXT TIER only — no rank, gate, size, or stance change.
No HKRV CONFIRMING TURN K-count feeds (HKRV-R5).
Registered in the asia-close.yml lane after build_hk.

Alerts: no HK routing in engine/alert_triage.py — HK rotation alerts NOT wired.
Southbound context (aggregate net z + n_adding) is fetched from
data/hk_southbound/summary.parquet at display time (template/JS only),
never as a detector input. Per-name southbound as a confirmer = NULL (HKRV-R2).

    python -m scripts.build_rotation_events_hk
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import rotation_events, sector_legs_hk  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_rotation_events_hk")


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

    sectors = sector_legs_hk.sector_closes(site_dir=site)
    n_legs = sum(len(s["legs"]) for s in sectors.values())
    log.info("hk sector legs resolved: %d sectors, %d legs", len(sectors), n_legs)

    if not sectors:
        log.warning("build_rotation_events_hk: no sectors resolved — skipped")
        return {"sectors": 0, "legs": 0, "active_events": 0, "created": [], "as_of": None}

    payload = rotation_events.run_nightly(
        sectors, config.data_dir(),
        generated_utc=generated_utc,
        data_subdir="rotation_events_hk",
    )

    # No fragmentation step — ETF closes unavailable for HK baskets (same as China).
    # No alerts — alert_triage.py has no HK routing for rotation_event type.

    # ── Southbound context (display receipt only — never a detector input) ──────
    # Bindings: per-name southbound as confirmer = NULL (HKRV-R2);
    #           southbound as timing leg = REJECTED (CHINA_ENGINE_REASSESSMENT).
    # Aggregate net z from china_connect/southbound.parquet (252d window).
    # Summary stats from data/hk_southbound/summary.parquet (n_adding, net_chg5_b).
    sb_ctx: dict | None = None
    try:
        sb_p = config.data_dir() / "china_connect" / "southbound.parquet"
        if sb_p.exists():
            sb = pd.read_parquet(sb_p)
            if "net" in sb.columns:
                net = sb["net"].dropna()
                if len(net) >= 30:
                    win = net.tail(252)
                    mu, sd = float(win.mean()), float(win.std() or 1.0)
                    latest_net = float(net.iloc[-1])
                    sb_ctx = {"net_z": round((latest_net - mu) / sd, 2)}
        summary_p = config.data_dir() / "hk_southbound" / "summary.parquet"
        if summary_p.exists():
            summ = pd.read_parquet(summary_p)
            if not summ.empty:
                row = summ.iloc[-1]
                if sb_ctx is None:
                    sb_ctx = {}
                if "n_adding" in row.index:
                    sb_ctx["n_adding"] = int(row["n_adding"]) if not pd.isna(row["n_adding"]) else None
                if "net_chg5_b" in row.index:
                    v = row["net_chg5_b"]
                    sb_ctx["net_chg5_b"] = round(float(v), 1) if not pd.isna(v) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("build_rotation_events_hk: southbound context read failed (%s) — context omitted", exc)
        sb_ctx = None

    if sb_ctx is not None:
        payload["southbound_ctx"] = sb_ctx

    _write_json(site / "marketdata" / "rotation_events_hk.json", payload)

    log.info("hk rotation events: %d active (%s), %d created, %d closed — as_of %s",
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
