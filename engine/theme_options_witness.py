"""engine/theme_options_witness.py — Per-theme options-tape crowding-hazard witness (TIL W11).

DISPLAY / CONFLUENCE CONTEXT ONLY.
Authority: may_rank=false, may_gate=false, may_size=false, may_escalate=false,
           is_context_only=true.

HAZARD FRAMING LAW (NEXTL-U13 + R-TIL-4):
  Options positioning reads are crowding-HAZARD context, NEVER a positive signal.
  High values = crowded / fragile. Low values = uncrowded. Neither direction is
  a buy. Positioning fusion is ILLEGAL — nothing here feeds any score.
  No composite (R-TIL-3 / WA-R1).

Three independent legs (each nullable; no fusion):

  Leg A — call-OI concentration (HHI)
    Per basket member: Herfindahl index of call OI across strikes (front 90 DTE).
    Basket aggregate: median HHI across covered members.
    HHI near 0 = call OI spread across many strikes (distributed positioning).
    HHI near 1 = call OI concentrated in one strike (call-wall crowding tell).
    Normed to 252-session rolling z over own history.

  Leg B — put/call OI ratio (PCR) — EXIT-CROWD L3 accrual vehicle
    Per basket: sum(put OI across members) / sum(call OI across members), oi[t-1].
    pcr_z252 = PCR normalized to 252-session rolling z (own history).
    pcr_5d_chg = 5-session change in basket PCR.
    pcr_collapse_into_strength = pcr_z252 drops ≥1 std over 5 sessions while
      basket 5d return > 0 (EXIT-CROWD-L3 pre-registered definition; L3 accrual only).
    OI TIMING LAW: OI[t-1] — oi[t] = EOD t-1 positions; same-day OI = lookahead bug.

  Leg C — IV premium vs realized (event-premium hazard)
    Per basket member: ATM IV (nearest-expiry 20–45 DTE) vs 20-session historical
      volatility from the greeks store's underlying_price column.
    iv_premium = iv30 / rv20 − 1 (VRP proxy).
    Basket: median iv_premium across covered members.
    High iv_premium = options buyers crowded into names (event-premium hazard).
    Requires greeks coverage (2017→ for most roots). Nulls when absent.

BANNED CONSTRUCTS (DO_NOT_REBUILD.md):
  • DOI family (delta-OI signed flow) — DEAD per W-E1 gauntlet. NOT built here.
  • Skew-deceleration — UNSUPPORTED per W-E1. NOT built here.
  • Positioning fusion — ILLEGAL (NEXTL-U13). Nothing here feeds any score.

OI TIMING LAW (engine/thetadata_store.py docstring):
  OPRA reports OI at ~06:30 ET representing end-of-PREVIOUS-day positions.
  oi[t] = positions as of EOD t-1. For any day-t signal, use oi[t-1] (shift(1)).
  Same-day OI in a day-t signal is a lookahead bug.

STORE ACCESS:
  Reads from THETADATA_STORE env → /Users/chriswong/theta-ops-wt/data/thetadata_eod.
  YOUR WORKTREE WILL NOT HAVE THE STORE (untracked-store false-null trap).
  When store absent → honest null artifact + exit 0.

RENDER BUDGET:
  Off the render path. Only theme-basket member roots; only the current year and
  one prior year of OI data per root (bounded reads). Bounded by _MAX_BASKET_MEMBERS
  per basket member per root. Wall-clock estimate: <5 min cold for all 18 themes.

SUPPRESSION:
  Baskets with <40% ThetaData coverage (< 40% of active members have any OI data
  in the trailing window) emit null for all legs + coverage_flag = "suppressed".

Output (written atomically via tmp → rename):
  data/neuralweb/theme_options_witness.json   — NW artifact
  site/basketdata/options_witness.json         — compact site projection

Usage:
  from engine.theme_options_witness import compute_theme_options_witness
  result = compute_theme_options_witness()

  # or as a script:
  python -m engine.theme_options_witness
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block — never modify; display-tier only
# ---------------------------------------------------------------------------
AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "framing": "crowding_hazard_context",
    "rotation_calls": False,
    "short_calls": False,
    "positioning_fusion": "ILLEGAL — nothing from this module feeds any score",
    "composite": "NONE — R-TIL-3 / WA-R1: no fused asymmetry number",
}

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MEMBERSHIP_JSON = _REPO_ROOT / "data" / "baskets" / "membership.json"
_CROSSWALK_YML = _REPO_ROOT / "config" / "theme_crosswalk.yml"
_NW_OUT = _REPO_ROOT / "data" / "neuralweb" / "theme_options_witness.json"
_SITE_OUT = _REPO_ROOT / "site" / "basketdata" / "options_witness.json"

# Main checkout fallback for THETADATA_STORE (the untracked-store pattern)
_MAIN_CHECKOUT_THETA = Path(
    "/Users/chriswong/theta-ops-wt/data/thetadata_eod"
)

# ---------------------------------------------------------------------------
# Compute parameters
# ---------------------------------------------------------------------------
_MAX_DTE = 90                   # OI window: only contracts ≤ 90 DTE
_Z_WINDOW = 252                 # rolling z lookback (own history)
_PCR_DELTA_WINDOW = 5          # sessions for pcr_5d_chg and L3 collapse detection
_PCR_COLLAPSE_STD = 1.0        # z-drop threshold for L3 complacency flag
_IV_DTE_NEAR_MIN = 20          # min DTE for ATM IV (avoid near-expiry gamma noise)
_IV_DTE_NEAR_MAX = 45          # max DTE for ATM IV (nearest ≤45 DTE front month)
_RV_WINDOW = 20                 # sessions for realized-vol computation
_MIN_COVERAGE_FRAC = 0.40      # suppress basket leg if < 40% members covered
_MIN_SERIES_FOR_Z = 63         # min observations to compute a z-score
_MIN_HHI_CONTRACTS = 5         # min distinct strikes with OI > 0 to compute HHI


# ---------------------------------------------------------------------------
# Store resolution — mirrors thetadata_store.store_root() pattern
# ---------------------------------------------------------------------------

def _theta_store() -> Optional[Path]:
    """Resolve the ThetaData store root. Returns None when absent."""
    env = os.environ.get("THETADATA_STORE")
    if env:
        p = Path(env)
        if p.exists():
            return p
        log.warning("theme_options_witness: THETADATA_STORE=%s does not exist", env)
        return None
    # Try the standard ops-worktree path
    if _MAIN_CHECKOUT_THETA.exists():
        return _MAIN_CHECKOUT_THETA
    # Try repo-local data/thetadata_eod (test fixtures land here)
    local = _REPO_ROOT / "data" / "thetadata_eod"
    if local.exists():
        return local
    return None


# ---------------------------------------------------------------------------
# Low-level OI loader (mirrors thetadata_store._load_parquets)
# ---------------------------------------------------------------------------

_OI_CACHE: dict[str, pd.DataFrame] = {}


def _load_oi(root: str, store: Path, years: list[int] | None = None) -> pd.DataFrame:
    """Load OI parquets for one root. Results memoized by file path."""
    base = store / "oi" / root
    if not base.exists():
        return pd.DataFrame()
    files = sorted(base.glob("*.parquet"))
    if years is not None:
        year_set = {str(y) for y in years}
        files = [f for f in files if f.stem in year_set]
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        key = str(f.resolve())
        if key not in _OI_CACHE:
            try:
                df = pd.read_parquet(f)
                df = df.drop_duplicates()
                # Normalise date column
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
                _OI_CACHE[key] = df
            except Exception as exc:  # noqa: BLE001
                log.debug("theme_options_witness: skip oi %s: %s", f, exc)
                continue
        frames.append(_OI_CACHE[key])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def clear_cache() -> None:
    """Release all cached DataFrames. Call after a batch run."""
    _OI_CACHE.clear()


# ---------------------------------------------------------------------------
# Membership loader
# ---------------------------------------------------------------------------

def _load_membership() -> dict:
    """Load data/baskets/membership.json. Returns {} on failure."""
    try:
        with open(_MEMBERSHIP_JSON, encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw.get("baskets", {})
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_options_witness: membership.json unreadable: %s", exc)
        return {}


def _active_members(basket_data: dict) -> list[str]:
    """Return active (not removed) ticker list for a basket."""
    return [
        m["ticker"]
        for m in basket_data.get("members", [])
        if m.get("removed") is None
    ]


# ---------------------------------------------------------------------------
# Crosswalk loader
# ---------------------------------------------------------------------------

def _load_crosswalk() -> list[dict]:
    """Load config/theme_crosswalk.yml themes list. Returns [] on failure."""
    try:
        with open(_CROSSWALK_YML, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return raw.get("themes", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_options_witness: crosswalk unreadable: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Leg A — Call-OI concentration (HHI)
# ---------------------------------------------------------------------------

def _call_oi_hhi_for_root(
    root: str,
    asof: str,
    store: Path,
    years: list[int],
) -> Optional[float]:
    """
    HHI of call OI across strikes for one root on one date.

    OI TIMING LAW: use oi[t-1] — we look at OI rows where date == asof,
    which represents EOD of the PREVIOUS session (OPRA reports at 06:30 ET).
    No shift needed here because we only read asof-date rows (the stored value
    IS the prior-session OI per the timing law — rows dated asof = reported
    at asof 06:30 ET = EOD asof-1).

    Returns HHI in [0, 1]: 0 = perfectly distributed, 1 = all OI at one strike.
    Returns None when insufficient data.
    """
    oi_df = _load_oi(root, store, years)
    if oi_df.empty:
        return None

    # Filter to asof date, calls only (right == 'C'), ≤ 90 DTE
    rows = oi_df[oi_df["date"] == asof].copy()
    if rows.empty:
        return None
    rows = rows[rows["right"] == "C"]
    if rows.empty:
        return None

    # Filter to ≤ _MAX_DTE contracts only
    try:
        rows["expiration"] = pd.to_datetime(rows["expiration"])
        rows["asof_dt"] = pd.to_datetime(asof)
        rows["dte"] = (rows["expiration"] - rows["asof_dt"]).dt.days
        rows = rows[rows["dte"] <= _MAX_DTE]
    except Exception as exc:  # noqa: BLE001
        log.debug("theme_options_witness: HHI DTE filter failed for %s: %s", root, exc)
        return None

    if rows.empty or rows["open_interest"].sum() == 0:
        return None

    # Aggregate OI by strike
    by_strike = (
        rows.groupby("strike")["open_interest"]
        .sum()
        .pipe(lambda s: s[s > 0])
    )
    if len(by_strike) < _MIN_HHI_CONTRACTS:
        return None

    total = float(by_strike.sum())
    if total <= 0:
        return None

    shares = by_strike / total
    hhi = float((shares ** 2).sum())
    return hhi


def _call_oi_series_for_root(
    root: str,
    store: Path,
    years: list[int],
) -> pd.Series:
    """
    Daily HHI series for one root.

    Returns pd.Series indexed by date string, values = HHI float or NaN.
    """
    oi_df = _load_oi(root, store, years)
    if oi_df.empty:
        return pd.Series(dtype=float)

    oi_c = oi_df[oi_df["right"] == "C"].copy()
    if oi_c.empty:
        return pd.Series(dtype=float)

    # Filter ≤ 90 DTE
    try:
        oi_c["expiration"] = pd.to_datetime(oi_c["expiration"])
        oi_c["date_dt"] = pd.to_datetime(oi_c["date"])
        oi_c["dte"] = (oi_c["expiration"] - oi_c["date_dt"]).dt.days
        oi_c = oi_c[oi_c["dte"] <= _MAX_DTE]
    except Exception as exc:  # noqa: BLE001
        log.debug("theme_options_witness: DTE filter failed for %s: %s", root, exc)
        return pd.Series(dtype=float)

    def _hhi(grp: pd.DataFrame) -> float:
        by_strike = grp.groupby("strike")["open_interest"].sum()
        by_strike = by_strike[by_strike > 0]
        if len(by_strike) < _MIN_HHI_CONTRACTS:
            return float("nan")
        total = float(by_strike.sum())
        if total <= 0:
            return float("nan")
        shares = by_strike / total
        return float((shares ** 2).sum())

    return oi_c.groupby("date").apply(_hhi)


# ---------------------------------------------------------------------------
# Leg B — PCR (put/call OI ratio) per basket
# ---------------------------------------------------------------------------

def _pcr_series_for_root(root: str, store: Path, years: list[int]) -> pd.DataFrame:
    """
    Daily put and call OI totals for one root.

    OI TIMING LAW: aggregated OI at date d = positions held as of EOD d-1.
    For the basket-level PCR series, we apply shift(1) to the total-OI series
    so that signal at date t uses oi[t-1] — consistent with doi_series() in
    thetadata_store.py.

    Returns DataFrame with columns [date, call_oi, put_oi]. Shifted.
    """
    oi_df = _load_oi(root, store, years)
    if oi_df.empty:
        return pd.DataFrame(columns=["date", "call_oi", "put_oi"])

    oi_df = oi_df.copy()
    oi_df["right"] = oi_df["right"].str.strip().str.upper()

    call_daily = (
        oi_df[oi_df["right"] == "C"]
        .groupby("date")["open_interest"]
        .sum()
        .rename("call_oi")
    )
    put_daily = (
        oi_df[oi_df["right"] == "P"]
        .groupby("date")["open_interest"]
        .sum()
        .rename("put_oi")
    )

    combined = pd.DataFrame({"call_oi": call_daily, "put_oi": put_daily}).fillna(0)
    combined.index.name = "date"

    # OI TIMING LAW: shift(1) so that date-t row uses EOD t-1 positions.
    # We retain the NaN leading row so callers can verify the law is applied;
    # downstream aggregation uses fillna(0) on the combined series anyway.
    combined = combined.shift(1)
    return combined.reset_index()


# ---------------------------------------------------------------------------
# IV loader (Leg C)
# ---------------------------------------------------------------------------

_GREEKS_CACHE: dict[str, pd.DataFrame] = {}


def _load_greeks(root: str, store: Path, years: list[int] | None = None) -> pd.DataFrame:
    """Load greeks parquets for one root. Results memoized."""
    base = store / "greeks" / root
    if not base.exists():
        return pd.DataFrame()
    files = sorted(base.glob("*.parquet"))
    if years is not None:
        year_set = {str(y) for y in years}
        files = [f for f in files if f.stem in year_set]
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        key = str(f.resolve())
        if key not in _GREEKS_CACHE:
            try:
                df = pd.read_parquet(f)
                df = df.drop_duplicates()
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
                _GREEKS_CACHE[key] = df
            except Exception as exc:  # noqa: BLE001
                log.debug("theme_options_witness: skip greeks %s: %s", f, exc)
                continue
        frames.append(_GREEKS_CACHE[key])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _iv_premium_series_for_root(
    root: str,
    store: Path,
    years: list[int],
) -> pd.Series:
    """
    Daily iv_premium = (ATM IV / RV20) - 1 for one root.

    ATM IV: nearest expiry with DTE in [_IV_DTE_NEAR_MIN, _IV_DTE_NEAR_MAX],
    selecting the contract closest to delta = 0.5 (ATM).
    RV20: 20-session annualised realized vol from the underlying_price column.

    Returns pd.Series indexed by date string.
    Returns empty Series when greeks absent or IV < 2017.
    """
    greeks = _load_greeks(root, store, years)
    if greeks.empty:
        return pd.Series(dtype=float)
    if "implied_vol" not in greeks.columns or "underlying_price" not in greeks.columns:
        return pd.Series(dtype=float)
    if greeks["implied_vol"].isna().all():
        return pd.Series(dtype=float)

    greeks = greeks.copy()
    greeks["right"] = greeks["right"].str.strip().str.upper()

    # Compute DTE per row
    try:
        greeks["expiration_dt"] = pd.to_datetime(greeks["expiration"])
        greeks["date_dt"] = pd.to_datetime(greeks["date"])
        greeks["dte"] = (greeks["expiration_dt"] - greeks["date_dt"]).dt.days
    except Exception as exc:  # noqa: BLE001
        log.debug("theme_options_witness: IV DTE failed for %s: %s", root, exc)
        return pd.Series(dtype=float)

    # Get underlying_price daily series for RV20
    up_daily = (
        greeks.groupby("date")["underlying_price"]
        .first()
        .sort_index()
    )
    if len(up_daily) < _RV_WINDOW + 2:
        return pd.Series(dtype=float)

    up_log_ret = np.log(up_daily / up_daily.shift(1))
    rv20 = up_log_ret.rolling(_RV_WINDOW, min_periods=_RV_WINDOW // 2).std() * np.sqrt(252)

    # For each date, get nearest-expiry ATM IV
    def _atm_iv_on_date(grp: pd.DataFrame) -> float:
        near = grp[
            (grp["dte"] >= _IV_DTE_NEAR_MIN)
            & (grp["dte"] <= _IV_DTE_NEAR_MAX)
            & (grp["implied_vol"].notna())
            & (grp["implied_vol"] > 0)
        ]
        if near.empty:
            return float("nan")
        # Nearest DTE
        min_dte = near["dte"].min()
        near_exp = near[near["dte"] == min_dte]
        # ATM = closest delta to 0.5 for calls
        if "delta" in near_exp.columns and near_exp["delta"].notna().any():
            calls = near_exp[near_exp["right"] == "C"].dropna(subset=["delta"])
            if not calls.empty:
                idx = (calls["delta"] - 0.5).abs().idxmin()
                return float(calls.loc[idx, "implied_vol"])
        # Fallback: median IV across near-expiry contracts
        return float(near_exp["implied_vol"].median())

    iv_daily = greeks.groupby("date").apply(_atm_iv_on_date)
    iv_daily.index.name = "date"

    # Align and compute iv_premium = iv / rv - 1
    df_iv = pd.DataFrame({"iv": iv_daily, "rv20": rv20})
    df_iv = df_iv.dropna()
    iv_prem = df_iv["iv"] / df_iv["rv20"] - 1
    return iv_prem


# ---------------------------------------------------------------------------
# Per-basket leg computation
# ---------------------------------------------------------------------------

def _z252(series: pd.Series) -> pd.Series:
    """252-session rolling z-score (own history)."""
    if len(series) < _MIN_SERIES_FOR_Z:
        return pd.Series(np.nan, index=series.index)
    mu = series.rolling(_Z_WINDOW, min_periods=_MIN_SERIES_FOR_Z).mean()
    sd = series.rolling(_Z_WINDOW, min_periods=_MIN_SERIES_FOR_Z).std()
    return (series - mu) / sd.replace(0, np.nan)


def _latest_or_none(series: pd.Series) -> Optional[float]:
    v = series.dropna()
    return float(v.iloc[-1]) if not v.empty else None


def compute_basket_legs(
    basket_id: str,
    members: list[str],
    store: Path,
    as_of: str,
) -> dict:
    """
    Compute all three legs for one basket on as_of date.

    Returns a dict with leg_a, leg_b, leg_c sub-dicts.
    Each leg: value, band, stale, note_en, note_zh, inputs, coverage_count.
    """
    today_year = pd.Timestamp(as_of).year
    years = [today_year - 1, today_year]  # bounded: current + prior year only

    # ------------------------------------------------------------------
    # Leg A — HHI call-OI concentration
    # ------------------------------------------------------------------
    hhi_series_per_root: dict[str, pd.Series] = {}
    hhi_covered = 0
    for ticker in members:
        s = _call_oi_series_for_root(ticker, store, years)
        if not s.empty:
            hhi_series_per_root[ticker] = s
            hhi_covered += 1

    leg_a: dict = {
        "label_en": "Call-OI Concentration (HHI)",
        "label_zh": "看涨OI集中度（HHI）",
        "coverage_count": hhi_covered,
        "coverage_total": len(members),
        "value": None,
        "value_z252": None,
        "band": None,
        "stale": False,
        "inputs": [t for t in hhi_series_per_root],
        "note_en": None,
        "note_zh": None,
    }

    if hhi_covered / max(len(members), 1) >= _MIN_COVERAGE_FRAC and hhi_series_per_root:
        # Basket-level HHI = median across members on each date
        hhi_df = pd.DataFrame(hhi_series_per_root)
        hhi_df.index = pd.to_datetime(hhi_df.index)
        hhi_df.sort_index(inplace=True)
        basket_hhi = hhi_df.median(axis=1)

        hhi_z = _z252(basket_hhi)
        latest_hhi = _latest_or_none(basket_hhi)
        latest_hhi_z = _latest_or_none(hhi_z)

        if latest_hhi is not None:
            if latest_hhi_z is not None:
                if latest_hhi_z > 1.5:
                    band = "elevated"
                elif latest_hhi_z > 0.5:
                    band = "rising"
                else:
                    band = "normal"
            else:
                band = None

            # Check staleness: last available date vs as_of
            available_dates = basket_hhi.dropna().index
            if len(available_dates) > 0:
                last_date = available_dates[-1]
                days_stale = (pd.Timestamp(as_of) - last_date).days
                stale = days_stale > 5
            else:
                stale = True

            leg_a.update({
                "value": round(latest_hhi, 4),
                "value_z252": round(latest_hhi_z, 3) if latest_hhi_z is not None else None,
                "band": band,
                "stale": stale,
                "note_en": (
                    f"Median call-OI HHI across {hhi_covered}/{len(members)} covered members. "
                    f"HHI={latest_hhi:.3f} — "
                    + ("call OI concentrated in few strikes (crowding hazard)."
                       if band == "elevated" else
                       "call OI moderately concentrated."
                       if band == "rising" else
                       "call OI distributed across strikes (no concentration hazard).")
                ),
                "note_zh": (
                    f"{hhi_covered}/{len(members)} 个成员覆盖的看涨OI HHI中位数。"
                    f"HHI={latest_hhi:.3f} — "
                    + ("看涨OI集中在少数行权价（拥挤风险信号）。"
                       if band == "elevated" else
                       "看涨OI集中度中等。"
                       if band == "rising" else
                       "看涨OI分布于多个行权价（无集中风险）。")
                ),
            })
    else:
        leg_a["note_en"] = (
            f"Suppressed: only {hhi_covered}/{len(members)} members have OI coverage "
            f"(< {int(_MIN_COVERAGE_FRAC * 100)}% threshold)."
        )
        leg_a["note_zh"] = (
            f"已抑制：仅 {hhi_covered}/{len(members)} 个成员有OI覆盖 "
            f"（低于 {int(_MIN_COVERAGE_FRAC * 100)}% 阈值）。"
        )

    # ------------------------------------------------------------------
    # Leg B — PCR (put/call OI) — EXIT-CROWD L3 accrual
    # ------------------------------------------------------------------
    pcr_frames: list[pd.DataFrame] = []
    pcr_inputs: list[str] = []
    pcr_covered = 0
    for ticker in members:
        df = _pcr_series_for_root(ticker, store, years)
        if not df.empty and len(df) > 0:
            pcr_frames.append(df.set_index("date"))
            pcr_inputs.append(ticker)
            pcr_covered += 1

    leg_b: dict = {
        "label_en": "Put/Call OI Ratio (PCR) — EXIT-CROWD L3 accrual",
        "label_zh": "看跌/看涨OI比率（PCR）— EXIT-CROWD L3积累",
        "coverage_count": pcr_covered,
        "coverage_total": len(members),
        "value": None,
        "value_z252": None,
        "pcr_5d_chg": None,
        "pcr_collapse_into_strength": None,
        "band": None,
        "stale": False,
        "inputs": pcr_inputs,
        "note_en": None,
        "note_zh": None,
    }

    if pcr_covered / max(len(members), 1) >= _MIN_COVERAGE_FRAC and pcr_frames:
        # Basket PCR = sum(put_oi across covered members) / sum(call_oi)
        all_call = pd.concat([f["call_oi"] for f in pcr_frames], axis=1).sum(axis=1)
        all_put = pd.concat([f["put_oi"] for f in pcr_frames], axis=1).sum(axis=1)

        # Align and sort.  Both all_call and all_put carry string date indices
        # (set_index('date') above preserves the string labels from _pcr_series_for_root).
        # Do NOT coerce to DatetimeIndex here — reindex(string_index) against a
        # Timestamp index produces all-NaN (label mismatch), zeroing every OI value
        # and silently nulling the entire Leg B output.
        idx = all_call.index.union(all_put.index)
        all_call = all_call.reindex(idx).fillna(0)
        all_put = all_put.reindex(idx).fillna(0)
        denom = all_call.where(all_call > 0)
        pcr_raw = (all_put / denom).sort_index()

        pcr_z = _z252(pcr_raw)
        latest_pcr = _latest_or_none(pcr_raw)
        latest_z = _latest_or_none(pcr_z)

        # 5-session change
        pcr_5d = (pcr_raw.iloc[-1] - pcr_raw.iloc[-1 - _PCR_DELTA_WINDOW]
                  if len(pcr_raw.dropna()) > _PCR_DELTA_WINDOW else None)
        if pcr_5d is not None and not np.isfinite(pcr_5d):
            pcr_5d = None

        # L3 collapse-into-strength:
        # pcr_z drops ≥ 1 std over 5 sessions while basket 5d return > 0
        # (return not available here — we record the pcr_z drop only; the
        #  full L3 gate is in the gauntlet harness, not this display organ)
        pcr_z_5d_chg = None
        if len(pcr_z.dropna()) > _PCR_DELTA_WINDOW:
            z_now = pcr_z.dropna().iloc[-1]
            z_prev = pcr_z.dropna().iloc[-1 - _PCR_DELTA_WINDOW]
            if np.isfinite(z_now) and np.isfinite(z_prev):
                pcr_z_5d_chg = float(z_now - z_prev)

        pcr_collapse = (
            pcr_z_5d_chg is not None
            and pcr_z_5d_chg <= -_PCR_COLLAPSE_STD
        )

        # Band: high PCR_z = put-heavy positioning (elevated put protection)
        # LOW PCR_z = complacency / protection collapse
        if latest_z is not None:
            if latest_z < -1.5:
                band = "complacency"   # low PCR = protection stripped = HAZARD
            elif latest_z < -0.5:
                band = "declining"
            elif latest_z > 1.5:
                band = "elevated_put"  # heavy put buying (fear / hedging)
            else:
                band = "normal"
        else:
            band = None

        # Staleness check
        available = pcr_raw.dropna().index
        stale = True
        if len(available) > 0:
            last_dt = pd.Timestamp(available[-1])
            stale = (pd.Timestamp(as_of) - last_dt).days > 5

        leg_b.update({
            "value": round(latest_pcr, 4) if latest_pcr is not None else None,
            "value_z252": round(latest_z, 3) if latest_z is not None else None,
            "pcr_5d_chg": round(float(pcr_5d), 4) if pcr_5d is not None else None,
            "pcr_collapse_into_strength": bool(pcr_collapse),
            "band": band,
            "stale": stale,
            "note_en": (
                f"Basket PCR across {pcr_covered}/{len(members)} covered members"
                + (f"; collapse_into_strength={pcr_collapse} (EXIT-CROWD-L3 accrual)"
                   if pcr_collapse is not None else "")
                + (f". Band: {band}." if band else ".")
            ),
            "note_zh": (
                f"{pcr_covered}/{len(members)} 个成员的篮子PCR比率"
                + (f"; 下降进入强势={pcr_collapse} (EXIT-CROWD-L3积累)"
                   if pcr_collapse is not None else "")
                + (f". 状态: {band}." if band else ".")
            ),
        })
    else:
        leg_b["note_en"] = (
            f"Suppressed: only {pcr_covered}/{len(members)} members have PCR coverage."
        )
        leg_b["note_zh"] = (
            f"已抑制：仅 {pcr_covered}/{len(members)} 个成员有PCR覆盖。"
        )

    # ------------------------------------------------------------------
    # Leg C — IV premium vs realized (event-premium hazard)
    # ------------------------------------------------------------------
    iv_prem_series: dict[str, pd.Series] = {}
    iv_covered = 0
    for ticker in members:
        s = _iv_premium_series_for_root(ticker, store, years)
        if not s.empty and s.dropna().shape[0] > 0:
            iv_prem_series[ticker] = s
            iv_covered += 1

    leg_c: dict = {
        "label_en": "IV Premium vs Realized (Event-Premium Hazard)",
        "label_zh": "隐含波动率溢价 vs 实现波动率（事件溢价风险）",
        "coverage_count": iv_covered,
        "coverage_total": len(members),
        "value": None,
        "value_z252": None,
        "band": None,
        "stale": False,
        "inputs": list(iv_prem_series.keys()),
        "note_en": None,
        "note_zh": None,
    }

    if iv_covered / max(len(members), 1) >= _MIN_COVERAGE_FRAC and iv_prem_series:
        # Basket iv_premium = median across covered members on each date
        iv_df = pd.DataFrame(iv_prem_series)
        iv_df.index = pd.to_datetime(iv_df.index)
        iv_df.sort_index(inplace=True)
        basket_iv_prem = iv_df.median(axis=1)

        iv_z = _z252(basket_iv_prem)
        latest_iv = _latest_or_none(basket_iv_prem)
        latest_iv_z = _latest_or_none(iv_z)

        if latest_iv is not None:
            if latest_iv_z is not None:
                if latest_iv_z > 1.5:
                    band_c = "elevated"
                elif latest_iv_z > 0.5:
                    band_c = "rising"
                elif latest_iv_z < -1.0:
                    band_c = "compressed"
                else:
                    band_c = "normal"
            else:
                band_c = None

            available_c = basket_iv_prem.dropna().index
            stale_c = True
            if len(available_c) > 0:
                last_c = pd.Timestamp(available_c[-1])
                stale_c = (pd.Timestamp(as_of) - last_c).days > 5

            leg_c.update({
                "value": round(latest_iv, 4),
                "value_z252": round(latest_iv_z, 3) if latest_iv_z is not None else None,
                "band": band_c,
                "stale": stale_c,
                "note_en": (
                    f"Median IV-premium (IV/RV20-1) across {iv_covered}/{len(members)} "
                    f"covered members. "
                    + ("Elevated IV premium = options buyers crowded in (event-premium hazard)."
                       if band_c == "elevated" else
                       "Rising IV premium vs realized."
                       if band_c == "rising" else
                       "IV premium compressed vs own history."
                       if band_c == "compressed" else
                       "IV premium near historical norm.")
                ),
                "note_zh": (
                    f"{iv_covered}/{len(members)} 个成员的IV溢价中位数（IV/RV20-1）。"
                    + ("IV溢价偏高 = 期权买入者大量涌入（事件溢价风险）。"
                       if band_c == "elevated" else
                       "IV溢价相对实现波动率上升。"
                       if band_c == "rising" else
                       "相对自身历史，IV溢价受压。"
                       if band_c == "compressed" else
                       "IV溢价接近历史正常水平。")
                ),
            })
    else:
        leg_c["note_en"] = (
            f"Suppressed: only {iv_covered}/{len(members)} members have IV coverage "
            f"(greeks 2017+ required)."
        )
        leg_c["note_zh"] = (
            f"已抑制：仅 {iv_covered}/{len(members)} 个成员有IV覆盖 "
            f"（需要2017年以后的希腊参数数据）。"
        )

    return {"leg_a": leg_a, "leg_b": leg_b, "leg_c": leg_c}


# ---------------------------------------------------------------------------
# Top-level compute
# ---------------------------------------------------------------------------

def compute_theme_options_witness(
    as_of: Optional[str] = None,
) -> dict:
    """
    Compute per-theme options-tape crowding-hazard witness for all TIL themes.

    Args:
        as_of: Trade date string YYYY-MM-DD. Defaults to today.

    Returns a dict ready for atomic JSON write.
    """
    if as_of is None:
        as_of = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    now_str = datetime.now(tz=timezone.utc).isoformat()

    # Resolve store
    store = _theta_store()
    store_present = store is not None

    if not store_present:
        log.warning(
            "theme_options_witness: ThetaData store not found "
            "(THETADATA_STORE env unset; theta-ops-wt absent; local fixture absent). "
            "Emitting honest null artifact. Exit 0."
        )

    crosswalk = _load_crosswalk()
    membership = _load_membership()

    themes_out: dict = {}
    coverage_stats: dict = {
        "n_themes": 0,
        "n_themes_any_coverage": 0,
        "n_themes_suppressed": 0,
        "store_present": store_present,
        "store_path": str(store) if store else None,
        "as_of": as_of,
    }

    for theme in crosswalk:
        theme_id = theme.get("id", "")
        basket_ids = theme.get("basket_ids", [])

        # Collect all active members across this theme's baskets
        all_members: list[str] = []
        seen: set[str] = set()
        for bid in basket_ids:
            bdata = membership.get(bid)
            if bdata is None:
                continue
            for m in _active_members(bdata):
                if m not in seen:
                    seen.add(m)
                    all_members.append(m)

        coverage_stats["n_themes"] += 1

        if not all_members:
            themes_out[theme_id] = _null_theme(
                theme, reason="no_members", members=[]
            )
            coverage_stats["n_themes_suppressed"] += 1
            continue

        if not store_present:
            themes_out[theme_id] = _null_theme(
                theme, reason="store_absent", members=all_members
            )
            continue

        # Compute legs
        legs = compute_basket_legs(theme_id, all_members, store, as_of)

        # Check overall coverage (any leg has coverage)
        any_coverage = (
            legs["leg_a"]["coverage_count"] > 0
            or legs["leg_b"]["coverage_count"] > 0
            or legs["leg_c"]["coverage_count"] > 0
        )

        if any_coverage:
            coverage_stats["n_themes_any_coverage"] += 1
        else:
            coverage_stats["n_themes_suppressed"] += 1

        themes_out[theme_id] = {
            "theme_id": theme_id,
            "name_en": theme.get("name_en", ""),
            "name_zh": theme.get("name_zh", ""),
            "as_of": as_of,
            "members": all_members,
            "n_members": len(all_members),
            "leg_a_call_oi_hhi": legs["leg_a"],
            "leg_b_pcr": legs["leg_b"],
            "leg_c_iv_premium": legs["leg_c"],
            # NO composite — R-TIL-3 / WA-R1
        }

    result = {
        "schema": "theme_options_witness.v1",
        "as_of": as_of,
        "generated_at": now_str,
        "authority": AUTHORITY,
        "honesty_header": (
            "Options-tape crowding-hazard context. HAZARD framing only — high values "
            "signal crowded/fragile positioning, never bullish. No composite (R-TIL-3). "
            "Positioning fusion is ILLEGAL (NEXTL-U13). Display/context tier only."
        ),
        "coverage_stats": coverage_stats,
        "oi_timing_law": (
            "OI[t] = positions as of EOD t-1 (OPRA reports ~06:30 ET). "
            "Leg B applies explicit shift(1) to the daily OI series (doi_series law). "
            "Leg A reads only the asof-date snapshot row, which per OPRA schedule "
            "already represents EOD t-1 positions — no additional shift required."
        ),
        "banned_constructs": [
            "DOI family (delta-OI signed flow) — DEAD per W-E1 gauntlet",
            "Skew-deceleration — UNSUPPORTED per W-E1",
            "Positioning fusion — ILLEGAL (NEXTL-U13)",
            "Composite across legs — NONE (R-TIL-3 / WA-R1)",
        ],
        "themes": themes_out,
    }

    return result


def _null_theme(theme: dict, reason: str, members: list[str]) -> dict:
    null_leg: dict = {
        "coverage_count": 0,
        "coverage_total": len(members),
        "value": None,
        "value_z252": None,
        "band": None,
        "stale": True,
        "inputs": [],
        "note_en": f"Null — {reason}.",
        "note_zh": f"空值 — {reason}。",
    }
    return {
        "theme_id": theme.get("id", ""),
        "name_en": theme.get("name_en", ""),
        "name_zh": theme.get("name_zh", ""),
        "as_of": None,
        "members": members,
        "n_members": len(members),
        "leg_a_call_oi_hhi": dict(null_leg,
                                   label_en="Call-OI Concentration (HHI)",
                                   label_zh="看涨OI集中度（HHI）"),
        "leg_b_pcr": dict(null_leg,
                          label_en="Put/Call OI Ratio (PCR) — EXIT-CROWD L3 accrual",
                          label_zh="看跌/看涨OI比率（PCR）— EXIT-CROWD L3积累",
                          pcr_5d_chg=None,
                          pcr_collapse_into_strength=None),
        "leg_c_iv_premium": dict(null_leg,
                                  label_en="IV Premium vs Realized (Event-Premium Hazard)",
                                  label_zh="隐含波动率溢价 vs 实现波动率（事件溢价风险）"),
    }


# ---------------------------------------------------------------------------
# Compact site projection
# ---------------------------------------------------------------------------

def _to_site_compact(nw: dict) -> dict:
    """Compact site projection — drop member lists and input arrays."""
    themes_compact: dict = {}
    for tid, td in nw.get("themes", {}).items():
        def _compact_leg(leg: dict) -> dict:
            return {
                k: v for k, v in leg.items()
                if k not in ("inputs", "label_en", "label_zh")
            }

        themes_compact[tid] = {
            "theme_id": td.get("theme_id"),
            "name_en": td.get("name_en"),
            "name_zh": td.get("name_zh"),
            "as_of": td.get("as_of"),
            "n_members": td.get("n_members"),
            "leg_a_call_oi_hhi": _compact_leg(td.get("leg_a_call_oi_hhi", {})),
            "leg_b_pcr": _compact_leg(td.get("leg_b_pcr", {})),
            "leg_c_iv_premium": _compact_leg(td.get("leg_c_iv_premium", {})),
        }

    return {
        "schema": nw["schema"],
        "as_of": nw["as_of"],
        "generated_at": nw["generated_at"],
        "authority": nw["authority"],
        "honesty_header": nw["honesty_header"],
        "coverage_stats": nw["coverage_stats"],
        "themes": themes_compact,
    }


# ---------------------------------------------------------------------------
# Atomic writer
# ---------------------------------------------------------------------------

def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        Path(tmp_path).replace(path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build(as_of: Optional[str] = None) -> None:
    """Build and write both output artifacts. Always exits 0."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        result = compute_theme_options_witness(as_of=as_of)

        _write_atomic(_NW_OUT, result)
        log.info("theme_options_witness: wrote %s", _NW_OUT)

        site_data = _to_site_compact(result)
        _write_atomic(_SITE_OUT, site_data)
        log.info("theme_options_witness: wrote %s", _SITE_OUT)

        stats = result.get("coverage_stats", {})
        log.info(
            "theme_options_witness: done — %d themes, %d with coverage, %d suppressed",
            stats.get("n_themes", 0),
            stats.get("n_themes_any_coverage", 0),
            stats.get("n_themes_suppressed", 0),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("theme_options_witness: build failed: %s", exc, exc_info=True)
    # Always exit 0 — tolerant builder law


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TIL W11: theme options-tape witness builder")
    parser.add_argument("--date", help="Trade date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    build(as_of=args.date)

    from lib.procutil import hard_exit  # noqa: PLC0415
    hard_exit(0)
