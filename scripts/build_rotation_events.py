"""scripts/build_rotation_events.py — Rotation Command W1 nightly step (RC-R1 + RC-R6).

Resolves the sector-leg registry (config/sector_legs.json) to composite closes ONCE, then:

  • engine.sector_fragmentation → site/marketdata/sector_fragmentation.json
      (per-sector "is the aggregate representative?" board — the RC-R3/R6 chip feed)
  • engine.rotation_events     → site/marketdata/rotation_events.json
      (active first-class ROTATION events with receipts, EN/ZH copy, severity)
      + data/rotation_events/events.jsonl   (append-only ledger, expected-NULL)
      + data/rotation_events/state.json     (lifecycle: TTL / lapse / lockout)

v2 EXTENSION (spec §4): when config/rotation_universe.json exists, also resolves the
cross-sector universe, loads sector breadth (data/breadth/sector_breadth.parquet), and
runs the v2 family B/C/D/E/F pass in run_nightly — additively over the v1 flow, same
output file. COLLECT_LANE is inherited from the job environment (cl_baskets, line ~1053
of daily.yml, env COLLECT_LANE=nightly).

DISPLAY/CONTEXT TIER, additive, never fatal. Registered in daily.yml cl_baskets.

    python -m scripts.build_rotation_events [--art-dir /tmp/rv2_scratch]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import rotation_events, sector_fragmentation, sector_legs  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_rotation_events")

# Mapping from rotation_universe.json series.sector short keys → GICS column prefix
# used in data/breadth/sector_breadth.parquet (columns: "{GICS}|pct_above_50").
_SECTOR_TO_GICS: dict[str, str] = {
    "xlk": "Information Technology",
    "xlv": "Health Care",
    "xlf": "Financials",
    "xlp": "Consumer Staples",
    "xlu": "Utilities",
    "xlc": "Communication Services",
    "xle": "Energy",
    "xlb": "Materials",
    "xli": "Industrials",
    "xlre": "Real Estate",
    "xly": "Consumer Discretionary",
}


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


def _load_sector_breadth() -> tuple[dict[str, float], dict[str, pd.Series]]:
    """Load data/breadth/sector_breadth.parquet and return two maps keyed by sector
    short key (e.g. 'xlk', 'xlv'):
      breadth_by_sector:        {sector_key: latest pct_above_50 as a 0-1 fraction}
      breadth_series_by_sector: {sector_key: pd.Series of pct_above_50 over time (0-1)}

    Returns empty dicts if the parquet is missing or unreadable (fail-open).
    """
    p = config.data_dir() / "breadth" / "sector_breadth.parquet"
    if not p.exists():
        log.warning("build_rotation_events: sector_breadth.parquet not found — breadth skipped")
        return {}, {}
    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_rotation_events: sector_breadth.parquet unreadable — %s", exc)
        return {}, {}

    breadth_by_sector: dict[str, float] = {}
    breadth_series_by_sector: dict[str, pd.Series] = {}

    for short_key, gics_name in _SECTOR_TO_GICS.items():
        col = f"{gics_name}|pct_above_50"
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty:
                # store as 0-1 fraction (parquet stores as percent 0-100)
                frac = s / 100.0
                breadth_by_sector[short_key] = float(frac.iloc[-1])
                breadth_series_by_sector[short_key] = frac

    return breadth_by_sector, breadth_series_by_sector


def build(site: Path | None = None, *, generated_utc: str | None = None,
          art_dir: Path | None = None) -> dict:
    """Main build function.

    art_dir: optional scratch override for the data_dir used by rotation_events
    (for repeatable local/test runs that must not write real data/).
    When not set, uses config.data_dir() (the production path).
    """
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data_dir = art_dir or config.data_dir()

    registry = sector_legs.load_registry()
    sectors = sector_legs.sector_closes(registry)
    n_legs = sum(len(s["legs"]) for s in sectors.values())
    log.info("sector legs resolved: %d sectors, %d legs", len(sectors), n_legs)

    frag = sector_fragmentation.compute(sectors, generated_utc=generated_utc)
    _write_json(site / "marketdata" / "sector_fragmentation.json", frag)
    log.info("fragmentation: %d/%d sectors flagged — %s",
             frag["n_fragmented"], len(frag["sectors"]),
             ", ".join(r["key"] for r in frag["sectors"] if r["fragmented"]) or "none")

    # ---- v2 universe resolution (spec §4) ----
    universe = None
    closes_v2 = None
    breadth_by_sector: dict = {}
    breadth_series_by_sector: dict = {}
    universe_path = config.ROOT / "config" / "rotation_universe.json"
    if universe_path.exists():
        try:
            from engine.rotation_universe import resolve_all, load_universe
            universe = load_universe(universe_path)
            closes_v2, meta = resolve_all(universe)
            n_resolved = sum(1 for v in closes_v2.values() if v is not None)
            log.info("rotation universe: %d/%d series resolved",
                     n_resolved, len(universe.get("series", [])) + 1)  # +1 for bench
            breadth_by_sector, breadth_series_by_sector = _load_sector_breadth()
            log.info("sector breadth: %d sectors loaded", len(breadth_by_sector))
        except Exception as exc:  # noqa: BLE001 — v2 universe is additive, v1 path continues
            log.warning("build_rotation_events: universe resolution failed (%s) — "
                        "running v1-only path", exc)
            universe = None
            closes_v2 = None

    payload = rotation_events.run_nightly(
        sectors, data_dir,
        generated_utc=generated_utc,
        universe=universe,
        closes=closes_v2,
        breadth_by_sector=breadth_by_sector,
        breadth_series_by_sector=breadth_series_by_sector,
    )
    payload["fragmented_sectors"] = [r["key"] for r in frag["sectors"] if r["fragmented"]]
    # RC-R10: the honest late-ruler (descriptive, from the RC-R8 replay census) — lets
    # the rail print "vs the median historical handoff run" instead of a binary 'late'.
    try:
        payload["ruler"] = json.loads(
            (data_dir / "rotation_events" / "episode_ruler.json").read_text())
    except Exception:  # noqa: BLE001 — ruler absent → rail simply omits the line
        pass
    _write_json(site / "marketdata" / "rotation_events.json", payload)

    # RC-R5: creation alerts into the shared rotation alert store (same schema the
    # triage already reads; dedup by id, prune like subsector_rotation_alerts.rebuild).
    try:
        from engine import subsector_rotation_alerts as sra
        new_alerts = rotation_events.to_alerts(payload)
        if new_alerts:
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

    n_cross = len(payload.get("contagion") or [])
    log.info("rotation events: %d active (%s), %d created, %d closed — as_of %s "
             "[contagion:%d cross_events:%d]",
             len(payload["active"]),
             ", ".join(e["id"] for e in payload["active"][:4]) or "none",
             len(payload["created_tonight"]), len(payload["closed_tonight"]),
             payload["as_of"], n_cross,
             payload.get("n_cross_pairs_scanned", 0))
    return {"sectors": len(sectors), "legs": n_legs,
            "fragmented": frag["n_fragmented"],
            "active_events": len(payload["active"]),
            "created": payload["created_tonight"],
            "as_of": payload["as_of"]}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="build_rotation_events")
    parser.add_argument(
        "--art-dir", dest="art_dir", default=None,
        help="Scratch override for data/ writes (default: config.data_dir()). "
             "Use for repeatable local test runs that must not advance the real ledger.",
    )
    args = parser.parse_args(argv)
    art_dir = Path(args.art_dir) if args.art_dir else None
    build(art_dir=art_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
