"""Per-theme physical fingerprint from members' own XBRL filings — W5a.

Backtest context (research/calibration/BACKTEST_FORESIGHT_CASCADE.md): the mapped
NAICS legs are NON-RESPONSIVE — the 3-bucket NAICS map cannot discriminate between
themes that share an industry code (MU/WDC inventories differ from AMAT/LRCX; both
are NAICS 3344, both get the same cap-U read). Member-level XBRL fingerprints supply
the missing discrimination: each theme now gets a physical read derived from its OWN
members' filed numbers.

THREE FINGERPRINT LEGS (all from cached parquets, no network in this engine):

  leg7_member_inventory
    Per-member inventory-days (inventory / (revenue / 365)) YoY change from
    data/edgar/statements.parquet. Falling inventory-days = tightening (positive leg,
    same direction as bottleneck leg2). Median across ≥MIN_MEMBERS reporting members.
    Basis: annual (fiscal year). Reports latest FY covered.

  leg8_member_backlog
    Median member RPO (Remaining Performance Obligation) YoY growth from
    data/edgar/rpo.parquet. Many industrials don't tag RPO → None is honest.
    Basis: annual. Reports latest FY covered.

  margin_trend (score-axis input, not a band leg)
    Already computed in engine/foresight_score.py (_gross_margin_trend). Imported
    and re-exposed in the fingerprint payload so it is visible alongside the other
    member-level legs, but it does NOT enter the bottleneck numeric_composite (it
    feeds the pricing_power axis in foresight_score.py).

CONTRACT:
  - Cache reads only (data/edgar/*.parquet). No network calls.
  - MIN_MEMBERS = 3 reporting members required per leg; fewer → None (never fabricated).
  - Returns fingerprint_tightness: z-ish score on [-2, +2] (None if both legs absent).
  - Returns components dict with each leg value and its basis/asof.
  - basis = "annual" always (filed XBRL, annual cadence).
  - Degrade to None per leg when parquet absent or insufficient members.
  - DISPLAY-ONLY. Provisional weights declared.

PER-THEME BY CONSTRUCTION: MU/WDC inventory data is different from AMAT/LRCX.
The 11 previously unmapped themes now get a real numeric path when ≥MIN_MEMBERS
members report (no NAICS map required).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Minimum members reporting to publish a leg (anti-fabrication gate)
MIN_MEMBERS = 3

# Clip bounds for the z-ish normalization (same clip as _language_z in bottleneck.py)
_CLIP = 2.0

# Module-level parquet cache (loaded once per process)
_STMTS_CACHE: dict = {}   # {"df": pd.DataFrame | None}
_RPO_CACHE: dict = {}     # {"df": pd.DataFrame | None}


def _load_statements(data_dir: Path) -> pd.DataFrame | None:
    """Load statements.parquet once per process. Returns None if absent."""
    global _STMTS_CACHE  # noqa: PLW0603
    if "df" not in _STMTS_CACHE:
        p = data_dir / "edgar" / "statements.parquet"
        if not p.exists():
            _STMTS_CACHE["df"] = None
        else:
            try:
                _STMTS_CACHE["df"] = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.debug("theme_fingerprint: statements.parquet load failed: %s", e)
                _STMTS_CACHE["df"] = None
    return _STMTS_CACHE.get("df")


def _load_rpo(data_dir: Path) -> pd.DataFrame | None:
    """Load rpo.parquet once per process. Returns None if absent."""
    global _RPO_CACHE  # noqa: PLW0603
    if "df" not in _RPO_CACHE:
        p = data_dir / "edgar" / "rpo.parquet"
        if not p.exists():
            _RPO_CACHE["df"] = None
        else:
            try:
                _RPO_CACHE["df"] = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.debug("theme_fingerprint: rpo.parquet load failed: %s", e)
                _RPO_CACHE["df"] = None
    return _RPO_CACHE.get("df")


def _inv_days_trend(
    members: list[str], df: pd.DataFrame
) -> tuple[float | None, int, int | None]:
    """Median YoY change in inventory-days across theme members.

    inventory_days = inventory / (revenue / 365).
    YoY = recent_FY − prior_FY in days.
    Falling inventory-days = tightening → positive leg (sign inverted before return).
    Returns (z_score, n_reporting, latest_fy | None).

    z_score: median_yoy_change clipped to ±CLIP and sign-inverted so that
    falling days → positive value (same direction as bottleneck leg2).
    """
    if df is None or df.empty or not members:
        return None, 0, None
    sub = df[df["ticker"].isin(members)].copy()
    if sub.empty:
        return None, 0, None

    # Need both inventory and revenue
    sub = sub[sub["inventory"].notna() & sub["revenue"].notna() & (sub["revenue"] != 0)]
    if sub.empty:
        return None, 0, None

    sub["inv_days"] = sub["inventory"] / (sub["revenue"] / 365.0)
    sub = sub.dropna(subset=["inv_days"])

    trends: list[float] = []
    latest_fy = None
    for tkr, grp in sub.groupby("ticker"):
        grp = grp.sort_values("fy")
        if len(grp) < 2:
            continue
        recent = float(grp["inv_days"].iloc[-1])
        prior = float(grp["inv_days"].iloc[-2])
        fy_val = int(grp["fy"].iloc[-1])
        if latest_fy is None or fy_val > latest_fy:
            latest_fy = fy_val
        trends.append(recent - prior)

    n_reporting = len(trends)
    if n_reporting < MIN_MEMBERS:
        return None, n_reporting, latest_fy

    median_yoy = float(np.median(trends))
    # Invert sign: falling days (negative yoy) = tightening = positive leg
    inverted = -median_yoy
    # Normalize into ±CLIP range: scale by 1/30 (a 30-day change ≈ ±1.0)
    normed = float(np.clip(inverted / 30.0, -_CLIP, _CLIP))
    return round(normed, 3), n_reporting, latest_fy


def _rpo_growth_trend(
    members: list[str], df: pd.DataFrame
) -> tuple[float | None, int, int | None]:
    """Median YoY RPO growth rate across theme members.

    RPO YoY = (rpo_recent / rpo_prior) − 1.0 (fractional growth).
    Rising RPO = more backlog = tightening → positive leg.
    Returns (z_score, n_reporting, latest_fy | None).

    z_score: median fractional YoY clipped to ±CLIP.
    (0.30 fractional = +30% YoY → ≈ +0.30 z; scaled so 100% YoY ≈ +1.0.)
    """
    if df is None or df.empty or not members:
        return None, 0, None
    sub = df[df["ticker"].isin(members)].copy()
    if sub.empty:
        return None, 0, None

    sub = sub[sub["rpo"].notna() & (sub["rpo"] > 0)]

    trends: list[float] = []
    latest_fy = None
    for tkr, grp in sub.groupby("ticker"):
        grp = grp.sort_values("fy")
        if len(grp) < 2:
            continue
        recent = float(grp["rpo"].iloc[-1])
        prior = float(grp["rpo"].iloc[-1 - 1])   # immediately prior year
        if prior == 0:
            continue
        fy_val = int(grp["fy"].iloc[-1])
        if latest_fy is None or fy_val > latest_fy:
            latest_fy = fy_val
        # Fractional YoY growth; cap at 200% to prevent massive outliers
        yoy = (recent - prior) / prior
        trends.append(float(np.clip(yoy, -1.0, 2.0)))

    n_reporting = len(trends)
    if n_reporting < MIN_MEMBERS:
        return None, n_reporting, latest_fy

    median_yoy = float(np.median(trends))
    # Scale: 100% RPO growth → z ≈ 1.0
    normed = float(np.clip(median_yoy, -_CLIP, _CLIP))
    return round(normed, 3), n_reporting, latest_fy


def compute_theme_fingerprint(
    theme_key: str,
    members: list[str],
    data_dir: Path,
) -> dict | None:
    """Compute the per-theme physical fingerprint from member XBRL filings.

    Returns a dict with:
      fingerprint_tightness: float | None — combined z-ish score
      components: dict — per-leg values, n_reporting, latest_fy
      leg7_member_inventory: float | None
      leg8_member_backlog: float | None
      n_legs_live: int — count of legs with a real value (0, 1, or 2)
      basis: "annual"
      provisional: True  — weights are PROVISIONAL pending shadow calibration

    Returns None only when BOTH legs are None (no fingerprint data at all).
    """
    if not members:
        return None

    stmts = _load_statements(data_dir)
    rpo = _load_rpo(data_dir)

    inv_z, inv_n, inv_fy = _inv_days_trend(members, stmts)
    rpo_z, rpo_n, rpo_fy = _rpo_growth_trend(members, rpo)

    n_legs_live = sum(1 for v in (inv_z, rpo_z) if v is not None)
    if n_legs_live == 0:
        return None

    # Combined tightness: equal-weight over available legs
    # (weights are PROVISIONAL — shadow calibration pending per §3.2 of the upgrade spec)
    # Future: promote via BY-FDR significance in foresight_shadow.py.
    available = [v for v in (inv_z, rpo_z) if v is not None]
    fingerprint_tightness = round(float(np.mean(available)), 3)

    return {
        "theme": theme_key,
        "fingerprint_tightness": fingerprint_tightness,
        "leg7_member_inventory": inv_z,
        "leg8_member_backlog": rpo_z,
        "n_legs_live": n_legs_live,
        "basis": "annual",
        "provisional": True,
        "components": {
            "leg7_member_inventory": {
                "value": inv_z,
                "n_reporting": inv_n,
                "latest_fy": inv_fy,
                "min_required": MIN_MEMBERS,
                "met_gate": inv_n >= MIN_MEMBERS,
                "description": (
                    "Median YoY change in inventory-days (inventory/(revenue/365)) "
                    "across theme members. Negative YoY (falling) → tightening → "
                    "positive value. Annual cadence; latest filed FY."
                ),
                "weight_provisional": 0.50,
            },
            "leg8_member_backlog": {
                "value": rpo_z,
                "n_reporting": rpo_n,
                "latest_fy": rpo_fy,
                "min_required": MIN_MEMBERS,
                "met_gate": rpo_n >= MIN_MEMBERS,
                "description": (
                    "Median YoY RPO (RevenueRemainingPerformanceObligation) growth "
                    "across theme members. Rising RPO → more backlog → tightening → "
                    "positive value. Annual cadence; latest filed FY."
                ),
                "weight_provisional": 0.50,
            },
        },
        # Shadow-grid registration note: these weights are candidates for the §3.2
        # shadow calibration loop once ≥30d of fingerprint-band forward-grading accrues.
        # Do NOT wire into stage grading until the calibration loop promotes them.
        "_shadow_candidates": {
            "leg7_weight": 0.50,
            "leg8_weight": 0.50,
            "note": "provisional equal-weight; shadow calibration pending (Wave 3a/3b)",
        },
    }


def reset_caches() -> None:
    """Reset module-level parquet caches. Useful for tests and cascade-level cache resets."""
    global _STMTS_CACHE, _RPO_CACHE  # noqa: PLW0603
    _STMTS_CACHE = {}
    _RPO_CACHE = {}
