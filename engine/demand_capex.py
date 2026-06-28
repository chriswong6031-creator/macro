"""Customer-capex demand leg — T2 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md). DISPLAY-ONLY adapter; reuses, does not duplicate.

The Demand Desk (engine/demand_chain.py) already computes the cleanest free forward-demand
signal there is: aggregate HYPERSCALER CAPEX (MSFT/GOOGL/AMZN/META/ORCL), which leads the
revenue of every AI beneficiary by ~2-4 quarters and is a number those beneficiaries cannot
manufacture. This module is a thin per-THEME projection of that one signal onto the foresight
cascade's tiers: the same capex pool, tagged by how DIRECTLY each theme benefits (memory/
silicon = direct; wafer-fab equipment = one step back; power/grid/nuclear = indirect).

Why this is the T2 leg and not the entry: capex guidance LEADS the supplier's revenue, which
LEADS the supplier's estimate revision. When hyperscaler capex accelerates (FY25 ≈ +69% YoY),
that is a pre-revision flag for memory/semis BEFORE the street fully re-models them — exactly
the "demand outrunning supply" the bottleneck leg (T1) reads from the supply side. Forward
grading of the underlying name-level theses lives in engine/demand_ledger.py; this adapter is
pure display context for the cascade. Returns None cleanly when statements aren't cached.
"""
from __future__ import annotations

import logging

from lib import config

log = logging.getLogger(__name__)

# config themes that benefit from the AI-datacenter (hyperscaler-capex) demand pool, tagged
# by directness. Mirrors engine/demand_chain.py's ai_datacenter tier strengths, plus
# memory_storage — the HBM headline beneficiary that is the desk's worked case.
AI_CAPEX_THEMES = {
    "memory_storage": "direct",        # HBM/DRAM — the 13D worked case
    "ai_semiconductors": "direct",     # AI accelerators / compute silicon
    "semicap_equipment": "lagged",     # wafer-fab equipment (one step upstream, longer lead)
    "data_center_power": "indirect",   # power & cooling
    "grid_electrification": "indirect",  # power & grid buildout
    "nuclear_power": "indirect",       # nuclear / SMR for data centers
}

_BAND = {
    "accelerating": "ACCELERATING",
    "expanding": "STEADY",
    "peaking": "COOLING",
    "contracting": "CONTRACTING",
    "flat": "FLAT",
    "unknown": "UNKNOWN",
}


def _statements():
    p = config.data_dir() / "edgar" / "statements.parquet"
    if not p.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("edgar statements unreadable: %s", e)
        return None
    return df if (df is not None and not df.empty) else None


def compute_demand_capex() -> dict | None:
    """Per-theme customer-capex demand read (hyperscaler capex projected onto AI themes).
    DISPLAY-ONLY. Returns None when the demand signal can't be computed."""
    df = _statements()
    if df is None:
        return None
    try:
        from engine import demand_chain as dc
        sig = (dc.compute_signals(df) or {}).get("ai_datacenter")
    except Exception as e:  # noqa: BLE001
        log.warning("demand_capex: demand_chain failed: %s", e)
        return None
    if not sig or sig.get("yoy_pct") is None:
        return None

    band = _BAND.get(sig.get("trend", "unknown"), "UNKNOWN")
    cfg_themes = (config.load() or {}).get("themes") or {}
    themes: dict[str, dict] = {}
    for theme, strength in AI_CAPEX_THEMES.items():
        if theme not in cfg_themes:
            continue
        themes[theme] = {
            "name": cfg_themes[theme].get("name", theme),
            "demand_band": band,
            "strength": strength,
            "capex_yoy": sig.get("yoy_pct"),
            "capex_yoy_prev": sig.get("yoy_prev_pct"),
            "capex_trend": sig.get("trend"),
            "total_latest_bn": sig.get("total_latest_bn"),
            "fy_latest": sig.get("fy_latest"),
            "customers": sig.get("spenders"),
        }
    if not themes:
        return None
    return {
        "asof": str(sig.get("fy_latest")) if sig.get("fy_latest") else None,
        "source": "hyperscaler_capex",
        "pool_bn": sig.get("total_latest_bn"),
        "pool_yoy": sig.get("yoy_pct"),
        "pool_trend": sig.get("trend"),
        "n_themes": len(themes),
        "themes": themes,
        "note": ("display-only; T2 LEADING demand leg — hyperscaler capex leads beneficiary "
                 "revenue ~2-4 quarters, i.e. a pre-revision flag. Name-level forward grading "
                 "lives in engine/demand_ledger.py."),
    }
