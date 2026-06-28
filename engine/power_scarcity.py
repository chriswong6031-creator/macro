"""Power scarcity — the physical bottleneck read for the POWER cluster
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md "physical-core hardening").

WHY. T1 bottleneck.py reads FRED capacity/inventory/PPI by NAICS for SEMIS / METALS — which
is the wrong physical for the power-demand themes (data_center_power, grid_electrification,
nuclear_power, solar, copper_steel_electrify). Those re-rate on a DIFFERENT scarcity: electricity
demand outrunning generation + grid capacity. So the cascade's physical gate was effectively
AWAITING for the whole power cluster, leaving the convergence web's most important 2026 theme
without a physical correlate. This engine supplies it from KEYLESS FRED electricity series
(auto-collected via config fred.series.power), so the power themes get a real, leading, testable
physical read — the desk's actual moat per the red-team.

Legs (each z-scored; positive = scarcity tightening): electricity-output demand GROWTH (YoY),
utility CAPACITY UTILIZATION, electricity PRICE momentum, and — if the keyless LBNL
interconnection-queue cache is present — the queued-capacity BUILDOUT pull (years of lead).
Bands LOOSE/NEUTRAL/TIGHTENING/TIGHT/SOLD_OUT mirror bottleneck.py. AWAITING_DATA until FRED
collects on a networked build. DISPLAY-ONLY; reuses bottleneck's _series/_z/_yoy/_band; None on
shortfall (the cascade/convergence run unchanged without it).
"""
from __future__ import annotations

import json
import logging

from engine.bottleneck import _band, _series, _yoy, _z
from lib import config

log = logging.getLogger(__name__)

POWER_THEMES = ("data_center_power", "grid_electrification", "nuclear_power",
                "solar", "copper_steel_electrify")

# keyless FRED electricity series — candidate ids per leg, first that resolves wins (FRED ids
# drift; the collector fetches every id in config fred.series.power, the engine uses what exists)
DEMAND_IDS = ("IPG2211S", "IPG2211A2N", "IPUTIL")        # electric-power output / utilities IP
CAPU_IDS = ("CAPUTLG2211S", "CAPUTLG2211A2S", "CAPUTLGMFS")  # utility capacity utilization
PRICE_IDS = ("WPU0543", "PCU221122221122", "APU000072610")  # electricity PPI / retail price


def _first(ids) -> object | None:
    for sid in ids:
        s = _series(sid)
        if s is not None:
            return s
    return None


def _queue_pull() -> float | None:
    """Interconnection-queue buildout pull: YoY growth in total queued capacity from the keyless
    LBNL queue cache (data/eia/interconnection_queue.json). A surging queue = demand for grid
    hardware + the multi-year buildout pipeline. None when the cache is absent (CI-collected)."""
    p = config.data_dir() / "eia" / "interconnection_queue.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None
    yoy = d.get("total_gw_yoy")
    if yoy is None:
        return None
    return round(min(2.0, max(-2.0, float(yoy) / 20.0)), 2)   # ~+20%/yr queue growth ≈ +1 z


def compute_power_scarcity(write_ledger: bool = True) -> dict | None:
    """Per-power-theme electricity-scarcity read. DISPLAY-ONLY. Returns None when no FRED
    electricity series have collected yet (engine degrades; the desk runs unchanged)."""
    demand = _yoy(_first(DEMAND_IDS))                   # demand GROWTH
    capu = _first(CAPU_IDS)                             # utilization LEVEL
    price = _yoy(_first(PRICE_IDS))                     # price momentum
    legs = {
        "demand_growth": _z(demand),
        "capacity_util": _z(capu),
        "price_momentum": _z(price),
        "queue_buildout": _queue_pull(),
    }
    present = {k: v for k, v in legs.items() if v is not None}
    if not present:
        return None                                    # nothing collected yet — AWAITING upstream
    composite = round(sum(present.values()) / len(present), 2)
    regime = all(v > 0 for v in present.values()) and len(present) >= 2
    band = _band(composite, len(present), regime)

    cfg_themes = (config.load() or {}).get("themes") or {}
    themes = {}
    for t in POWER_THEMES:
        if t not in cfg_themes:
            continue
        themes[t] = {
            "name": cfg_themes[t].get("name", t),
            "band": band, "tightness": composite, "regime": regime,
            "n_legs": len(present),
        }
    if not themes:
        return None
    payload = {
        "band": band, "tightness": composite, "regime": regime,
        "legs": {k: round(v, 2) for k, v in present.items()},
        "n_legs": len(present),
        "themes": themes,
        "note": ("display-only; PHYSICAL bottleneck for the power cluster from keyless FRED "
                 "electricity series — demand growth + utility capacity-utilization + price "
                 "momentum (+ LBNL interconnection-queue buildout when present). The physical "
                 "correlate the FRED semis/metals bottleneck cannot give power/grid/nuclear/solar."),
    }
    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("power_scarcity ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading ledger: one row per asof when the power cluster reads
    TIGHT/SOLD_OUT — graded forward (did the power basket outperform after a physical tighten?)."""
    if payload["band"] not in ("TIGHT", "SOLD_OUT"):
        return
    from datetime import date, datetime, timezone
    d = config.data_dir() / "power_scarcity"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    asof = str(date.today())
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                seen.add(json.loads(line).get("asof"))
            except Exception:  # noqa: BLE001
                continue
    if asof in seen:
        return
    with p.open("a") as fh:
        fh.write(json.dumps({"asof": asof, "ts": datetime.now(timezone.utc).isoformat(),
                             "band": payload["band"], "tightness": payload["tightness"],
                             "legs": payload["legs"]}, separators=(",", ":")) + "\n")
