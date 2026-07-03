"""engine/regime_prior.py — single conditioning prior for all cycle pages (D5-W5 / W4.5).

Composes ONE artifact consumed by every cycle-family page (cycle.html, markets.html,
sector_cycles.html, country_cycles.html, sector_cycles_china.html, sector_central.html):

  • Quad + liquidity + cycle_tag + transition_state  (data/regime/latest.json)
  • Business-cycle phase + recession-signal state    (business_cycle_snapshot())
  • Market-state verdict + score                     (data/market_state/latest.json)
      DISPLAY-ONLY — not_a_model_input: True.  No PIT history exists; it cannot
      enter any backfilled model until archiving has run for ≥250 trading days.
  • Vol-regime label                                 (vol_regime.published_snapshot())
      DISPLAY-ONLY — US-index-only, no cross-family equivalent.

Contract:
  - Pure reads.  Never recomputes a signal.  No new data fetched.
  - Degrades per component: missing/unreadable source → status "unavailable" for
    that source; the merged result status degrades but never raises.
  - Every component carries its own as_of date and a staleness flag.
  - STALENESS RULE: any source whose as_of is more than 3 trading-day equivalents
    (= 5 calendar days) stale marks that source "stale" and degrades the merged
    status from "fresh" to "stale".

Artifacts:
  - Called by scripts/build_regime_prior.py to write site/regimedata/regime_prior.js
    (window.REGIME_PRIOR = {...}).  Script-tag data — NEVER fetch (ruling A11).
  - Called by scripts/build_regime_prior.py to APPEND one row to
    data/regime/market_state_history.parquet (keep-first per date) — the PIT accrual
    stub so market_state can become a model feature once n_days >= 250.

Reconciliation helper:
  - check_staleness(curated_as_of) → dict with keys {stale: bool, days: int|None,
    banner_en: str, banner_zh: str}.  Used by build_cycle and build_markets to render
    staleness banners when curated regime prose is > 30 days old.
  - The current curated cycle_data.js prose (regimeNote strings) carries NO machine-
    readable regime_claim fields, so contradiction-checking is not yet possible for
    cycle.html.  markets.html similarly has no regime_claim.  Both pages render
    staleness-only banners; this module records the honest check limit.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Staleness threshold (calendar days).  3 trading days ≈ 5 calendar days
# (covers a long weekend without false-positives on Monday builds).
_STALE_DAYS = 5
# Curated prose staleness threshold for reconciliation banner (days)
_PROSE_STALE_DAYS = 30


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_since(asof_str: str | None) -> int | None:
    """Calendar days from asof_str (YYYY-MM-DD) to today.  None if unparseable."""
    if not asof_str:
        return None
    try:
        d = datetime.strptime(asof_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except Exception:  # noqa: BLE001
        return None


def _source_status(asof_str: str | None) -> str:
    """'fresh' | 'stale' | 'unavailable' for a single source."""
    if asof_str is None:
        return "unavailable"
    days = _days_since(asof_str)
    if days is None:
        return "unavailable"
    return "stale" if days > _STALE_DAYS else "fresh"


# ---------------------------------------------------------------------------
# Component readers — each degrades to {} rather than raising.

def _read_regime_latest(data_dir: Path) -> dict[str, Any]:
    """Read data/regime/latest.json.  Returns {} on any failure."""
    try:
        p = data_dir / "regime" / "latest.json"
        if not p.exists():
            log.warning("regime_prior: data/regime/latest.json not found")
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("regime_prior: regime latest.json read failed: %s", e)
        return {}


def _read_market_state_latest(data_dir: Path) -> dict[str, Any]:
    """Read data/market_state/latest.json.  Returns {} on any failure."""
    try:
        p = data_dir / "market_state" / "latest.json"
        if not p.exists():
            log.warning("regime_prior: data/market_state/latest.json not found")
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("regime_prior: market_state latest.json read failed: %s", e)
        return {}


def _read_vol_regime(data_dir: Path, site_dir: Path | None = None) -> dict[str, Any]:
    """Call vol_regime.published_snapshot().  Returns {} on any failure."""
    try:
        from engine.vol_regime import published_snapshot
        return published_snapshot(data_dir=data_dir, site_dir=site_dir) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("regime_prior: vol_regime.published_snapshot failed: %s", e)
        return {}


def _read_business_cycle() -> dict[str, Any]:
    """Call business_cycle.business_cycle_snapshot().  Returns {} on any failure."""
    try:
        from engine.business_cycle import business_cycle_snapshot
        snap = business_cycle_snapshot()
        return snap if isinstance(snap, dict) else {}
    except Exception as e:  # noqa: BLE001
        log.warning("regime_prior: business_cycle_snapshot failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Main composer

def regime_prior(
    data_dir: Path | None = None,
    site_dir: Path | None = None,
) -> dict[str, Any]:
    """Compose and return the single conditioning prior for all cycle pages.

    Returns a JSON-safe dict with schema=1.  All sources degrade gracefully —
    missing data gives status='unavailable' for that source, but the function
    never raises.
    """
    from lib import config  # local import so the module is usable without config in tests
    if data_dir is None:
        data_dir = config.data_dir()
    if site_dir is None:
        cfg = config.load()
        site_dir = config.ROOT / cfg["storage"]["site_dir"]

    # --- 1. Regime quad + liquidity ---
    reg = _read_regime_latest(data_dir)
    quad = reg.get("quad")
    quad_names = {
        "Q1": ("Goldilocks", "金发姑娘"),
        "Q2": ("Reflation", "再通胀"),
        "Q3": ("Stagflation", "滞涨"),
        "Q4": ("Growth-scare", "增长恐慌"),
    }
    quad_name_en, quad_name_zh = quad_names.get(quad, ("Unknown", "未知")) if quad else ("Unknown", "未知")
    reg_asof = reg.get("asof") or reg.get("date")
    reg_status = _source_status(reg_asof) if reg else "unavailable"

    # --- 2. Market-state (display-only) ---
    ms = _read_market_state_latest(data_dir)
    ms_asof = ms.get("asof")
    ms_status = _source_status(ms_asof) if ms else "unavailable"

    # --- 3. Vol-regime (display-only) ---
    vol = _read_vol_regime(data_dir, site_dir)
    vol_regime_label = vol.get("regime")  # e.g. "normalizing", "backwardation-stress"
    vol_asof = vol.get("asof")
    vol_status = _source_status(vol_asof) if vol else "unavailable"

    # --- 4. Business cycle ---
    bc = _read_business_cycle()
    bc_asof = bc.get("asof")
    bc_status = _source_status(bc_asof) if bc else "unavailable"

    phase_block = bc.get("phase") or {}
    bc_phase_label = phase_block.get("label")
    bc_phase_zh = phase_block.get("label_zh")

    rec_sig = bc.get("recession_signal") or {}
    rec_state = rec_sig.get("state")   # "off" | "on" | "warning" etc.
    rec_label = rec_sig.get("label")
    rec_label_zh = rec_sig.get("label_zh")

    # --- Merged staleness ---
    source_statuses = [reg_status, ms_status, vol_status, bc_status]
    if all(s == "unavailable" for s in source_statuses):
        merged_status = "unavailable"
    elif any(s == "stale" for s in source_statuses):
        merged_status = "stale"
    elif any(s == "unavailable" for s in source_statuses):
        merged_status = "partial"
    else:
        merged_status = "fresh"

    return {
        "schema": 1,
        "wave": "W4.5",
        "asof": _today_str(),
        "status": merged_status,
        # --- quad block ---
        "quad": quad,
        "quad_name_en": quad_name_en,
        "quad_name_zh": quad_name_zh,
        "liquidity": reg.get("liquidity_overlay"),
        "cycle_tag": reg.get("cycle_tag"),
        "transition_state": reg.get("transition_state"),
        "transition_state_raw": reg.get("transition_state_raw"),
        "flip_condition": reg.get("flip_condition"),
        "growth_score": reg.get("growth_score"),
        "inflation_score": reg.get("inflation_score"),
        "confidence": reg.get("confidence"),
        # --- business cycle block ---
        "bc_phase": bc_phase_label,
        "bc_phase_zh": bc_phase_zh,
        "bc_recession_state": rec_state,
        "bc_recession_label": rec_label,
        "bc_recession_label_zh": rec_label_zh,
        "bc_honesty_note": (
            "LORO-calibrated; effective sample ~7 US recessions; recession probability is "
            "a risk timeline, not a crash oracle — see reports/business-cycle-validation.md"
        ),
        # --- market-state block (display-only) ---
        "market_state": {
            "verdict": ms.get("verdict"),
            "score": ms.get("score"),
            "label_en": ms.get("label_en"),
            "label_zh": ms.get("label_zh"),
            "color": ms.get("color"),
            "not_a_model_input": True,
            "honesty_note": (
                "Display-only: no PIT history exists; cannot be a model feature "
                "until market_state_history.parquet accrues ≥250 trading days."
            ),
        },
        # --- vol-regime block (display-only) ---
        "vol_regime": vol_regime_label,
        "vol_regime_honesty": "Display-only: US-index-only (VIX/VIX3M/MOVE); no cross-family vol equivalent.",
        # --- per-source as_of / freshness ---
        "sources": {
            "regime": {"asof": reg_asof, "status": reg_status},
            "market_state": {"asof": ms_asof, "status": ms_status},
            "vol_regime": {"asof": vol_asof, "status": vol_status},
            "business_cycle": {"asof": bc_asof, "status": bc_status},
        },
    }


# ---------------------------------------------------------------------------
# Reconciliation helper

def check_staleness(curated_as_of: str | None) -> dict[str, Any]:
    """Check whether curated regime prose is stale (>30d).

    Returns:
        stale (bool): True when curated_as_of is more than _PROSE_STALE_DAYS old.
        days (int|None): calendar days since curated_as_of.
        banner_en (str): English banner text (empty string when not stale).
        banner_zh (str): Simplified-Chinese banner text (empty string when not stale).
        checkable (bool): whether a machine-readable contradiction check was possible.
        contradiction_note (str): explains what is/isn't checkable.
    """
    days = _days_since(curated_as_of)
    is_stale = bool(days is not None and days > _PROSE_STALE_DAYS)
    if is_stale:
        banner_en = (
            f"Regime narrative last updated {curated_as_of} "
            f"({days}d ago) — may not reflect the live engine."
        )
        banner_zh = (
            f"体制叙述最后更新于 {curated_as_of}（{days} 天前）"
            f"——可能未反映实时引擎读数。"
        )
    else:
        banner_en = ""
        banner_zh = ""
    return {
        "stale": is_stale,
        "days": days,
        "banner_en": banner_en,
        "banner_zh": banner_zh,
        # Honest limit: the curated prose (regimeNote strings in cycle_data.js,
        # narratives in markets_data.js) carries no machine-readable regime_claim
        # fields.  Contradiction-checking (claimed quad vs engine quad) is not
        # possible until those fields are added to the curated data.  Only
        # staleness is checkable today.
        "checkable": False,
        "contradiction_note": (
            "Curated prose carries no machine-readable regime_claim fields; "
            "contradiction detection requires adding {\"regime_claim\": {\"quad\": \"QN\", "
            "\"as_of\": \"YYYY-MM-DD\"}} to the curated seed. "
            "Until then, only prose staleness (>30d) triggers the banner."
        ),
    }


def check_claims(narratives: list[dict] | None, prior: dict | None = None) -> list[dict]:
    """Check machine-readable regime_claim fields in narratives against the live prior.

    For each narrative that declares a ``regime_claim`` dict with a ``quad`` field,
    compare against ``prior["quad"]``.  Returns a list of disagreement dicts.

    If ``prior`` is None, calls regime_prior() to fetch it live.

    This function is a stub for the future — no current curated narrative declares
    regime_claim, so it will return [] in all current builds.  It is wired and tested
    so that when regime_claim fields are added, the guard activates automatically.
    """
    if not narratives:
        return []
    if prior is None:
        try:
            prior = regime_prior()
        except Exception as e:  # noqa: BLE001
            log.warning("regime_prior.check_claims: could not load prior: %s", e)
            return []
    engine_quad = (prior or {}).get("quad")
    engine_asof = ((prior or {}).get("sources") or {}).get("regime", {}).get("asof")
    disagreements = []
    for narr in narratives:
        claim = narr.get("regime_claim")
        if not isinstance(claim, dict):
            continue
        claimed_quad = claim.get("quad")
        if claimed_quad and engine_quad and claimed_quad != engine_quad:
            disagreements.append({
                "narrative_id": narr.get("id") or narr.get("name") or "unknown",
                "claimed_quad": claimed_quad,
                "engine_quad": engine_quad,
                "engine_asof": engine_asof,
                "claim_as_of": claim.get("as_of"),
                "banner_en": (
                    f"Narrative says {claimed_quad}; "
                    f"live regime engine reads {engine_quad} (as of {engine_asof})."
                ),
                "banner_zh": (
                    f"叙述指示 {claimed_quad}；"
                    f"实时体制引擎读数为 {engine_quad}（截至 {engine_asof}）。"
                ),
            })
    return disagreements
