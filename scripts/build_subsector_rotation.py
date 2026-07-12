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


def _inject_megacap_node(tree: list, snap: dict) -> None:
    """RC-R4 (Rotation Command): the mega-cap generals cohort has no Finviz group, so
    the 06-25 rotate-IN had no home in this taxonomy — semis' breakdown ranked 255-268
    while the Mag-7 bid could only surface via adjacent proxies. Inject ONE synthetic
    node whose perf comes from the local equal-weight Mag-7 composite (members from
    data/baskets/membership.json — never re-curated here). Quadrant math unchanged;
    the node rides the same cross-sectional metrics as every Finviz group. In-memory
    only; the committed snapshot files are not touched. Degrade-safe."""
    from engine import sector_legs
    members = (sector_legs.load_membership().get("mag7") or {}).get("members") or []
    tickers = [m["ticker"] for m in members if m.get("ticker")]
    if not tickers:
        raise ValueError("mag7 membership empty")
    close, meta = sector_legs._ew_close(tickers)
    if close is None:
        raise ValueError(f"mag7 composite unavailable ({meta})")
    perf = sr.perf_from_close(close, asof=snap.get("asof") or None)
    if not perf:
        raise ValueError("mag7 composite too thin for horizon returns")
    tree.append({"theme": "Mega-Cap", "key": "megacap", "subsectors": [
        {"key": "megacapgenerals", "name": "Mag 7 Generals",
         "description": "Local equal-weight Mag-7 composite (Rotation Command RC-R4) — "
                        "our own store, not a Finviz group",
         "members": tickers}]})
    snap.setdefault("subsector_perf", {})["megacapgenerals"] = perf


def build(site: Path | None = None, *, generated_utc: str | None = None) -> dict:
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    tree = json.loads(_data("themes_heatmap", "themes_tree.json").read_text())
    snap = json.loads(_data("themes_heatmap", "perf_snapshot.json").read_text())

    # RC-R4: synthetic mega-cap node (additive, never fatal — a failed injection
    # leaves the desk exactly as it was before Rotation Command).
    try:
        _inject_megacap_node(tree, snap)
    except Exception as e:  # noqa: BLE001
        log.warning("mega-cap node injection failed: %s", e)

    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    payload = sr.compute_rotation(
        tree,
        snap.get("subsector_perf") or {},
        snap.get("member_perf") or {},
        generated_utc=generated_utc,
        asof=snap.get("asof") or "",
    )

    # Forward TRACK-RECORD (additive, degrade-safe): log today's calls with their
    # FROZEN member baskets, then grade every matured past call. The read becomes
    # falsifiable — context-only, never sizes; verdict stays 'accruing' for months.
    try:
        from engine import subsector_track_record as strk
        member_map = {sub.get("key"): (sub.get("members") or [])
                      for th in tree for sub in th.get("subsectors", [])}
        asof_date = snap.get("asof") or datetime.now(timezone.utc).date().isoformat()
        n_logged = strk.snapshot(payload, member_map, today=asof_date)
        tr = strk.compute(today=asof_date)
        payload["track_record"] = tr
        _data("subsector_rotation", "track_record.json").write_text(json.dumps(tr, indent=2))
        log.info("track record: +%d snapshots, %d days logged, verdict=%s",
                 n_logged, tr.get("n_days"), tr.get("verdict"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("track record failed: %s", e)

    # Sector ETF cross-section (additive — degrade-safe).
    try:
        sector_perf = sr.compute_sector_etf_perf(_data("yahoo"))
        if sector_perf:
            sector_metrics = sr._rotation_metrics(sector_perf)
            sectors_array = sr.build_sectors_array(sector_metrics)
            payload["sectors"] = sectors_array
            payload["n_sectors"] = len(sectors_array)
            log.info("sector ETFs: %d rows, quadrants=%s",
                     len(sectors_array),
                     {s["quadrant"] for s in sectors_array})
        else:
            log.warning("sector ETF perf empty — omitting sectors from payload")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector ETF build failed: %s", e)

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
