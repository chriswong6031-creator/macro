"""engine/commodity_cycle_state.py — inbound cycle → commodity bridge (P3 data bridge).

Runs the structural-cycle engine for each of the 7 registered commodity cycles
(gold, silver, copper, oil, natural-gas, pgms, agriculture) and writes per-member
structural-clock records to data/commodity/cycle_positions.json.

The file is read by engine/commodity_confluence.py (build_confluence) to activate
the cycle conditions (cycle_bottom / cycle_top) for each member.

Public API
----------
build_cycle_positions() -> dict
    Returns {member_name: CycleEntry} for every member that maps to a cycle.
    Members without a cycle map (softs, cattle, gasoline, heating_oil) are absent.
    Never raises; returns {} on outer failure.

write_cycle_positions(data_dir=None) -> dict
    build + write data/commodity/cycle_positions.json; return the dict.

CycleEntry schema (all fields JSON-safe — no numpy scalars, no NaN → None):
    cycle_ref    : str            # e.g. "gold", "pgms"
    pos          : float | None   # 0-100 oscillator position
    phase        : str | None     # "Trough"|"Recovery"|"Expansion"|"Peak"|"Downturn"
    phase_v2     : str | None
    overdue      : bool | None
    overdue_frac : float | None
    hazard_1m    : float | None   # P(turn ≤ 1 month)
    hazard_3m    : float | None
    hazard_6m    : float | None
    asof         : str            # YYYY-MM-DD
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Cycle → member fanout map
# --------------------------------------------------------------------------- #
CYCLE_TO_MEMBERS: dict[str, list[str]] = {
    "gold":        ["gold"],
    "silver":      ["silver"],
    "copper":      ["copper"],
    "oil":         ["oil"],
    "natural-gas": ["natgas"],
    "pgms":        ["platinum", "palladium"],
    "agriculture": ["corn", "wheat", "soybeans"],
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _safe_float(v: Any) -> float | None:
    """Convert to float, returning None for None/NaN/inf."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    import math
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _run_cycle(cid: str) -> dict | None:
    """Run record_series for the primary measured band of cid.

    Returns a dict with raw now/proj/hz, or None if the tape is unavailable.
    Mirrors build_cycle.py:_measured_record lines 89-168.
    """
    from engine import cycle_proxies as cp
    from engine import sector_cycles as sc

    entry = cp.REGISTRY.get(cid)
    if entry is None:
        log.warning("commodity_cycle_state: cycle %r not in REGISTRY", cid)
        return None
    bands = entry.get("bands") or []
    if not bands:
        log.warning("commodity_cycle_state: cycle %r has no bands", cid)
        return None

    band = bands[0]
    # Only run on measured bands (frame bands have no tape to record_series from)
    if band.get("tier") != "measured" or band.get("series") is None:
        log.debug("commodity_cycle_state: band[0] for %r is frame-only — skipping", cid)
        return None

    try:
        s = cp.load_series(band)
    except Exception as e:  # noqa: BLE001
        log.warning("commodity_cycle_state: load_series failed for %r: %s", cid, e)
        return None

    kernel = band.get("kernel") or {}
    zz_pct = kernel.get("zz_pct")
    zz_abs = kernel.get("zz_abs")
    if zz_pct is None and zz_abs is None:
        zz_pct = sc._zz_pct_for(s) if band["freq"] == "D" else sc._zz_pct_for_monthly(s)

    try:
        rec = sc.record_series(
            s, win_start=s.index.min(), last_ts=s.index[-1],
            freq=band["freq"], invert=band["invert"],
            zz_pct=zz_pct, zz_abs=zz_abs,
            zz_standardize=bool(kernel.get("zz_standardize")),
            trend_span=kernel.get("trend_span"), stoch_win=kernel.get("stoch_win"),
            basis_label=band["basis"], family="flagship",
            series_id=f"{cid}:{band['band']}",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("commodity_cycle_state: record_series failed for %r: %s", cid, e)
        return None

    if rec is None:
        log.debug("commodity_cycle_state: record_series returned None for %r", cid)
        return None

    now = rec.get("now") or {}

    # Hazard P(turn ≤ 1m/3m/6m)
    hz: dict | None = None
    hf = now.get("hazard_features")
    if hf:
        try:
            from engine.hazard_score import score as _hz_score, _UP_PHASES
            direction = "up" if (now.get("phase") or "") in _UP_PHASES else "down"
            hz = _hz_score(hf, direction, family="flagship")
        except Exception as _hz_exc:  # noqa: BLE001
            log.debug("commodity_cycle_state: hazard score failed for %r: %s", cid, _hz_exc)

    return {"now": now, "proj": rec.get("proj"), "hz": hz, "series_last": s.index[-1]}


def _extract_entry(cid: str, cycle_data: dict) -> dict:
    """Build one CycleEntry from a _run_cycle() result dict."""
    now = cycle_data.get("now") or {}
    proj = cycle_data.get("proj") or {}
    hz = cycle_data.get("hz") or {}
    series_last = cycle_data.get("series_last")

    # asof: date of last bar in the tape
    if series_last is not None:
        try:
            asof = series_last.strftime("%Y-%m-%d")
        except AttributeError:
            asof = str(series_last)[:10]
    else:
        from datetime import datetime, timezone
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # hazard keys in hazard_score output are "1m", "3m", "6m"
    def _hz_p(h: str) -> float | None:
        cell = hz.get(h) if hz else None
        if isinstance(cell, dict):
            return _safe_float(cell.get("p"))
        return None

    return {
        "cycle_ref":    cid,
        "pos":          _safe_float(now.get("pos")),
        "phase":        now.get("phase"),
        "phase_v2":     now.get("phase_v2"),
        "overdue":      bool(proj["overdue"]) if "overdue" in proj and proj["overdue"] is not None else None,
        "overdue_frac": _safe_float(proj.get("overdue_frac")),
        "hazard_1m":    _hz_p("1m"),
        "hazard_3m":    _hz_p("3m"),
        "hazard_6m":    _hz_p("6m"),
        "asof":         asof,
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def build_cycle_positions() -> dict[str, dict]:
    """Return {member_name: CycleEntry} for every member with a registered cycle.

    Each cycle is computed ONCE and fanned out to its member(s).
    Never raises — returns {} on any outer failure.
    Members not in CYCLE_TO_MEMBERS (e.g. coffee, cattle, gasoline) are absent.
    """
    try:
        return _build_cycle_positions_inner()
    except Exception:  # noqa: BLE001
        log.warning("commodity_cycle_state.build_cycle_positions failed", exc_info=True)
        return {}


def _build_cycle_positions_inner() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cid, members in CYCLE_TO_MEMBERS.items():
        cycle_data = _run_cycle(cid)
        if cycle_data is None:
            log.debug("commodity_cycle_state: no data for cycle %r — skipping members %s", cid, members)
            continue
        entry = _extract_entry(cid, cycle_data)
        for member in members:
            out[member] = entry
    return out


def write_cycle_positions(data_dir: Path | None = None) -> dict[str, dict]:
    """Build cycle positions and write data/commodity/cycle_positions.json.

    Returns the dict (same as build_cycle_positions()).
    Never raises — logs warning and returns {} on failure.
    """
    try:
        from lib import config
        if data_dir is None:
            data_dir = config.data_dir()
        outdir = Path(data_dir) / "commodity"
        outdir.mkdir(parents=True, exist_ok=True)
        positions = build_cycle_positions()
        (outdir / "cycle_positions.json").write_text(
            json.dumps(positions, indent=2, default=str),
            encoding="utf-8",
        )
        log.info(
            "commodity_cycle_state: wrote cycle_positions.json (%d members)",
            len(positions),
        )
        return positions
    except Exception:  # noqa: BLE001
        log.warning("commodity_cycle_state.write_cycle_positions failed", exc_info=True)
        return {}
