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

Wave 2b additions (P1-D):
- Per-tier transmission lag as METADATA (transmission_lag_q 0/1/2 + lag_note): every tier
  shares ONE current pool band; the annual-shift approach was review-rejected (a 1-2 YEAR
  shift for a ~2-QUARTER lag re-read the 2023 capex dip as the power themes' current demand).
- Per-name divergence: theme demand read = share of members ahead-of-consensus (n_ahead /
  n_covered), min 3 covered. Reuses engine/demand_chain._divergence (import, not copy).
- Supplier-side RPO confirmer: reads data/edgar/rpo.parquet cache (read-only — no network
  fetch). Per theme: median YoY RPO growth + rpo_n. Degrades to None per theme; never raises.
- Sign honesty: buyer capex is CONTEXT (Cooper-Gulen-Schill: spender capex predicts negative
  spender returns; beneficiary-chain transmission is being validated forward by
  engine/demand_ledger.py). The live demand_ledger track record is surfaced as
  chain_track_record in the payload.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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


# Tier transmission lags in QUARTERS (hyperscaler capex leads beneficiary revenue
# ~2-4q; direct tiers feel it first, indirect last). The lag is METADATA — a timing
# note on when the current pool read arrives — NEVER a shift of the annual series:
# review finding — shifting the annual pool back "2 steps" for a ~2-QUARTER lag
# overstated it ~4x and re-read the 2023 capex-digestion dip as the power themes'
# CURRENT demand (CONTRACTING next to capex_yoy=+69 on the same card — the exact
# inverse of the truth for the themes whose bull case IS the live capex wave).
# All tiers therefore share ONE current pool band; per-name divergence + RPO carry
# the cross-theme discrimination. Quarterly capex (companyfacts fp=Q1..Q3) would
# enable a genuine per-quarter tier shift — a future collector wave, not this one.
_TRANSMISSION_LAG_Q = {"direct": 0, "lagged": 1, "indirect": 2}


def _tier_band(sig: dict, strength: str) -> tuple[str, int, str]:
    """One CURRENT pool band for every tier + the tier's transmission lag as metadata.

    Returns (band_str, transmission_lag_q, timing_note)."""
    trend = sig.get("trend", "unknown")
    band = _BAND.get(trend, "UNKNOWN")
    lag_q = _TRANSMISSION_LAG_Q.get(strength, 0)
    note = ("feels the pool now" if lag_q == 0
            else f"pool read arrives with ~{lag_q}q transmission lag")
    return band, lag_q, note


def _membership_map() -> dict[str, list[str]]:
    """Return {theme_slug: [ticker, ...]} for the AI capex themes from membership.json."""
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        baskets = data.get("baskets") or {}
    except Exception as e:  # noqa: BLE001
        log.warning("demand_capex: membership.json unreadable: %s", e)
        return {}
    out: dict[str, list[str]] = {}
    for theme in AI_CAPEX_THEMES:
        b = baskets.get(theme, {})
        members = [
            m["ticker"] for m in (b.get("members") or [])
            if not m.get("removed") and m.get("ticker")
        ]
        out[theme] = members
    return out


def _revisions_map() -> dict[str, dict]:
    """Return {ticker: {breadth, est_chg_30d, est_chg_90d}} from the latest revisions cache."""
    p = config.data_dir() / "revisions" / "latest.parquet"
    if not p.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("demand_capex: revisions unreadable: %s", e)
        return {}
    out: dict[str, dict] = {}
    for t in df.index:
        row = df.loc[t]
        out[str(t)] = {
            "breadth": _f(row.get("breadth")),
            "est_chg_30d": _f(row.get("est_chg_30d")),
            "est_chg_90d": _f(row.get("est_chg_90d")),
        }
    return out


def _f(x: Any) -> float | None:
    """Safe float conversion, returns None for NaN/inf."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _per_theme_divergence(
    theme: str,
    members: list[str],
    sig: dict,
    revisions: dict[str, dict],
) -> dict[str, Any]:
    """Compute per-name divergence for all members of a theme and aggregate.

    Reuses engine/demand_chain._divergence (imported, not copied).
    Returns dict with n_ahead, n_at_risk, n_covered, divergence_share.
    divergence_share = n_ahead / n_covered (None when < 3 covered members).
    """
    from engine.demand_chain import _divergence, _consensus_dir

    trend = sig.get("trend", "unknown")
    n_ahead = 0
    n_at_risk = 0
    n_covered = 0

    for ticker in members:
        rev = revisions.get(ticker)
        cons_dir = _consensus_dir(rev)
        if cons_dir == "none":
            # No revision data — counts as signal_only, not "covered" for divergence_share
            continue
        n_covered += 1
        div = _divergence(trend, cons_dir)
        if div == "ahead_of_consensus":
            n_ahead += 1
        elif div == "consensus_at_risk":
            n_at_risk += 1

    divergence_share: float | None = None
    if n_covered >= 3:
        divergence_share = round(n_ahead / n_covered, 3)

    return {
        "n_ahead": n_ahead,
        "n_at_risk": n_at_risk,
        "n_covered": n_covered,
        "divergence_share": divergence_share,
    }


def _rpo_cache() -> dict[str, list[dict]]:
    """Read the RPO parquet cache (read-only — no network fetch).
    Returns {ticker: [{fy, rpo, revenue}, ...]} sorted by fy ascending.
    Degrades to empty dict if cache is absent or unreadable; never raises.
    """
    p = config.data_dir() / "edgar" / "rpo.parquet"
    if not p.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        out: dict[str, list[dict]] = {}
        for t, g in df.groupby("ticker"):
            rows = sorted(
                [{"fy": int(r.fy), "rpo": float(r.rpo),
                  "revenue": float(r.revenue) if r.revenue == r.revenue else None}
                 for r in g.itertuples()],
                key=lambda r: r["fy"]
            )
            out[str(t)] = rows
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("demand_capex: rpo.parquet unreadable: %s", e)
        return {}


def _per_theme_rpo(members: list[str], rpo: dict[str, list[dict]]) -> dict[str, Any]:
    """Compute median YoY RPO growth for theme members present in the RPO cache.

    Supplier-side RPO confirmer: per-theme median YoY RPO growth + rpo_n.
    Many industrial filers don't tag RPO — degrades to None per theme; never raises.
    """
    yoy_values: list[float] = []
    for ticker in members:
        rows = rpo.get(ticker)
        if not rows or len(rows) < 2:
            continue
        rpo_now = rows[-1]["rpo"]
        rpo_prev = rows[-2]["rpo"]
        if rpo_prev and rpo_prev > 0:
            yoy = round((rpo_now / rpo_prev - 1.0) * 100.0, 1)
            yoy_values.append(yoy)

    if not yoy_values:
        return {"rpo_growth_yoy": None, "rpo_n": 0}

    # Median YoY RPO growth across members present in the cache
    yoy_values_sorted = sorted(yoy_values)
    n = len(yoy_values_sorted)
    mid = n // 2
    median_yoy = (
        yoy_values_sorted[mid]
        if n % 2 == 1
        else round((yoy_values_sorted[mid - 1] + yoy_values_sorted[mid]) / 2.0, 1)
    )
    return {"rpo_growth_yoy": median_yoy, "rpo_n": n}


def _chain_track_record() -> dict | None:
    """Read the demand_ledger's live track record if it exists.
    Returns the track_record dict or None.
    """
    p = config.data_dir() / "demand_chain" / "track_record.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("demand_capex: track_record.json unreadable: %s", e)
        return None


def compute_demand_capex() -> dict | None:
    """Per-theme customer-capex demand read (hyperscaler capex projected onto AI themes).
    DISPLAY-ONLY. Returns None when the demand signal can't be computed.

    Wave 2b enrichments (P1-D):
    - Per-tier transmission lag as metadata: transmission_lag_q (0/1/2) + lag_note; the
      band itself is the CURRENT pool read for every tier (see _tier_band).
    - Per-name divergence: n_ahead/n_at_risk/n_covered/divergence_share per theme.
    - RPO supplier confirmer: median YoY RPO growth per theme from cache (read-only).
    - Sign honesty: sign_note + chain_track_record from engine/demand_ledger.py.

    Output shape (cascade-compat): top-level keys themes {theme: {demand_band, strength,
    capex_yoy, ...}}, pool_bn, pool_yoy, pool_trend preserved. New per-theme keys:
    transmission_lag_q, lag_note, n_ahead, n_at_risk, n_covered, divergence_share,
    rpo_growth_yoy, rpo_n. New top-level keys: sign_note, chain_track_record.
    """
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

    cfg_themes = (config.load() or {}).get("themes") or {}
    membership = _membership_map()
    revisions = _revisions_map()
    rpo = _rpo_cache()

    themes: dict[str, dict] = {}
    for theme, strength in AI_CAPEX_THEMES.items():
        if theme not in cfg_themes:
            continue

        # One CURRENT pool band for every tier; the tier lag is timing METADATA
        # (see _tier_band — the annual-shift approach was review-rejected as an
        # inverted read). Discrimination comes from divergence_share + RPO below.
        demand_band, lag_q, lag_note = _tier_band(sig, strength)

        # Per-name divergence — reuses demand_chain._divergence (not copied)
        members = membership.get(theme, [])
        div_info = _per_theme_divergence(theme, members, sig, revisions)

        # Supplier-side RPO confirmer — cache read only, never fetches
        rpo_info = _per_theme_rpo(members, rpo)

        themes[theme] = {
            # --- existing keys (cascade-compat: preserved shape, enriched values) ---
            "name": cfg_themes[theme].get("name", theme),
            "demand_band": demand_band,        # NOW per-tier (not identical pool band)
            "strength": strength,
            "capex_yoy": sig.get("yoy_pct"),
            "capex_yoy_prev": sig.get("yoy_prev_pct"),
            "capex_trend": sig.get("trend"),
            "total_latest_bn": sig.get("total_latest_bn"),
            "fy_latest": sig.get("fy_latest"),
            "customers": sig.get("spenders"),
            # --- Wave 2b: per-tier transmission lag (metadata, never a band shift) ---
            "transmission_lag_q": lag_q,
            "lag_note": lag_note,
            # --- Wave 2b: per-name divergence ---
            "n_ahead": div_info["n_ahead"],
            "n_at_risk": div_info["n_at_risk"],
            "n_covered": div_info["n_covered"],
            "divergence_share": div_info["divergence_share"],
            # --- Wave 2b: RPO supplier confirmer ---
            "rpo_growth_yoy": rpo_info["rpo_growth_yoy"],
            "rpo_n": rpo_info["rpo_n"],
        }

    if not themes:
        return None

    # Sign honesty note (Cooper-Gulen-Schill)
    sign_note = (
        "CONTEXT ONLY — buyer capex as a bullish confirmer inverts Cooper-Gulen-Schill "
        "(high spender capex predicts negative forward returns FOR THE SPENDER). "
        "The beneficiary-chain transmission (hyperscaler capex leads chip revenue ~2-4q) "
        "is a claim being validated forward by engine/demand_ledger.py ±5%-vs-SPY theses "
        "— see chain_track_record for the live score. Until the ledger accumulates graded "
        "theses with BY-FDR significance, treat demand_band as directional context, "
        "not a confirmed edge."
    )

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
        # Wave 2b sign honesty
        "sign_note": sign_note,
        "chain_track_record": _chain_track_record(),
    }
