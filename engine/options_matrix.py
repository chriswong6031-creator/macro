"""engine/options_matrix.py — strike × expiration matrix builder (Package E).

build_matrix(root, store, asof=None) → options_structure.matrix/v1 dict.

DISPLAY-ONLY — authority_tier='display' (no forward ledger gate has passed).
No "validated" wording in user-facing strings (CI-enforced).

GEX SIGN CONVENTION (dealer-short assumption, matching prism_spec §1 + §2):
  calls → POSITIVE gex  (dealer long call → positive delta → buy stock on move up)
  puts  → NEGATIVE gex  (dealer short put → negative delta → sell stock on move down)
  The assumption is robust for indices, fragile for single names.  See reliability dict.

GEX FORMULA per prism_spec §2:
  gex_dollar = oi[t-1] * gamma * S² * 0.01 * 100
  where S = spot, gamma = per-contract gamma (BS if raw gamma absent/zero),
  S² * 0.01 = converts raw gamma to $-P&L for a 1% spot move,
  100 = contract multiplier (standard equity option).

OI TIMING LAW (absolute):
  Only OI[t-1] is ever used.  Same-day OI is a lookahead bug.
  delta_oi = OI[t-1] − OI[t-2] (both lagged; fully PIT-safe).

DEFERRED (no implementation in v1):
  VEX lens — requires greeks-path stability verification across the ThetaData store.
  UNUSUAL lens — requires 30d per-strike volume baseline not yet in the EOD store.
  These are documented here so the next package stage has a clear gap list.

SCHEDULING NOTE:
  This script is NOT wired into any nightly schedule.  Scheduling follows once
  the flow-ops lane settles and the PRISM tab is ready to consume the artifact.
"""
from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from engine.greeks import npdf, bs_greeks
from engine.thetadata_store import _load_parquets, _normalise_date
from engine.options_structure import validate_matrix

log = logging.getLogger(__name__)

# ── contract constants ────────────────────────────────────────────────────────
_CONTRACT_MULT = 100       # standard equity option
_VOL_PCT       = 0.01      # "per 1% spot move" scalar
_R             = 0.05      # risk-free rate (matches prism_spec §1)
_MIN_IV        = 0.005     # below this, BS gamma 1/sigma factor explodes — treat as zero gamma
_FALLBACK_IV   = 0.30      # default median IV when no valid IVs exist

# ── matrix window constraints ─────────────────────────────────────────────────
_STRIKE_PCT    = 0.20      # ±20% around spot
_MAX_DTE       = 90        # ≤ 90 days to expiry
_MIN_DTE_FLOOR = 0.5       # DTE penalty threshold (prism_spec §5)

# ── heat-seeker gates (from prism_spec §5) ────────────────────────────────────
_MIN_TOTAL_OI  = 5000      # chain must have at least this much OI
# Per-lens standout ratios (prism_spec §5, LENS_GATES):
# GEX: 1.5×, OI: 1.5× (spec exact); VOL: 1.5× (spec exact); default: 1.2×
_STANDOUT_RATIO = {
    "GEX": 1.5,
    "OI":  1.5,
    "VOL": 1.5,
}
_STANDOUT_RATIO_DEFAULT = 1.2   # OURS (prism_spec lists 1.2 as default floor)
_MIN_CONFIDENCE = 0.15          # spec explicit


# ============================================================================ #
# helpers
# ============================================================================ #

def _f(x, n: int = 2) -> float | None:
    """Round to n dp, None for NaN / inf / None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if math.isfinite(v) else None


def _load_oi(root: str, date_str: str, store) -> pd.DataFrame:
    """Load OI parquet for one specific date."""
    year = pd.Timestamp(date_str).year
    df = _load_parquets("oi", root, [year], store)
    if df.empty:
        return pd.DataFrame()
    df = _normalise_date(df)
    return df[df["date"] == date_str].copy()


def _prev_date(df: pd.DataFrame, asof: str) -> str | None:
    """Return the most recent date in `df["date"]` strictly before `asof`."""
    if df.empty or "date" not in df.columns:
        return None
    dates = sorted(df["date"].unique())
    before = [d for d in dates if d < asof]
    return before[-1] if before else None


def _bs_gamma_scalar(S: float, K: float, T_years: float,
                     iv: float, median_iv: float) -> float:
    """Per-contract gamma using BS, with fallback to median_iv.

    T_years = DTE / 365; floor at 0.001 (prism_spec §1).
    iv fallback = median_iv (prism_spec §2 IV fallback).
    """
    effective_iv = iv if iv > _MIN_IV else median_iv
    if effective_iv <= _MIN_IV:
        return 0.0
    T = max(T_years, 0.001)
    sqrtT = math.sqrt(T)
    try:
        d1 = (math.log(S / K) + (_R + 0.5 * effective_iv ** 2) * T) / (effective_iv * sqrtT)
        gamma = npdf(d1) / (S * effective_iv * sqrtT)
        return gamma if math.isfinite(gamma) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def _gex_dollar(oi: float, gamma: float, spot: float) -> float:
    """Dollar gamma per 1% spot move.

    Formula: oi * gamma * S^2 * 0.01 * 100
    Matches prism_spec §2 gexDollar.
    """
    return oi * gamma * spot * spot * _VOL_PCT * _CONTRACT_MULT


def _median_iv(ivs: list[float]) -> float:
    """Population median of valid IVs in range (0.01, 5.0)."""
    valid = [v for v in ivs if 0.01 < v < 5.0]
    return statistics.median(valid) if valid else _FALLBACK_IV


def _dte(expiry_str: str, asof_date: str) -> float:
    """Calendar days from asof_date to expiry_str.

    Returns:
      - Positive float for future expiries.
      - 0.5 for same-day expiry (intraday contracts; still live on asof).
      - Negative float for already-expired contracts (expiry < asof).

    Callers that need a positive floor for T_years (e.g. BS gamma) must
    apply max(dte, 0.001) themselves; _in_window excludes negatives so that
    expired contracts never enter the cell map.
    """
    try:
        exp_dt = pd.Timestamp(expiry_str)
        as_dt  = pd.Timestamp(asof_date)
        days = (exp_dt - as_dt).days
        if days > 0:
            return float(days)
        elif days == 0:
            return 0.5   # same-day expiry sentinel
        else:
            return float(days)   # negative — expired
    except Exception:  # noqa: BLE001
        return 0.5


def _to_iso_date(val) -> str:
    """Normalize an expiration value to plain ISO date string 'YYYY-MM-DD'.

    Handles pandas Timestamps ('2026-07-06 00:00:00'), date objects, and
    strings already in ISO format.
    """
    try:
        return pd.Timestamp(val).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return str(val)


# ============================================================================ #
# Max-pain (replicates gex_model._max_pain / prism_spec §8)
# ============================================================================ #

def _compute_max_pain(
    chain: pd.DataFrame,
    call_oi_col: str = "call_oi",
    put_oi_col: str = "put_oi",
    strike_col: str = "strike",
) -> float | None:
    """Max pain across all strikes.

    payout(K) = Σ_{s<K}(K-s)*callOI_s*100 + Σ_{s>K}(s-K)*putOI_s*100
    Returns argmin strike. Returns None on empty input.
    """
    if chain.empty:
        return None
    strikes = np.sort(chain[strike_col].unique())
    if not len(strikes):
        return None
    pain = []
    for P in strikes:
        cc = ((chain[call_oi_col] * (P - chain[strike_col]).clip(lower=0)).sum())
        pp = ((chain[put_oi_col]  * (chain[strike_col] - P).clip(lower=0)).sum())
        pain.append(cc + pp)
    idx = int(np.argmin(pain))
    return float(strikes[idx])


# ============================================================================ #
# Key level computation (per prism_spec §7)
# ============================================================================ #

def _compute_levels(
    by_strike: dict[float, dict],
    spot: float,
    asof_date: str,
    median_iv: float,
) -> dict:
    """Compute call_wall, put_support, hvl/magnet, gamma_flip, max_pain.

    by_strike: {strike: {call_oi, put_oi, call_gex, put_gex, ...}}
    """
    if not by_strike:
        return {
            "call_wall": None,
            "put_support": None,
            "hvl": None,
            "gamma_flip": None,
            "max_pain": None,
        }

    strikes = sorted(by_strike.keys())

    # ── call wall: strike above spot with max callOI × callGamma ─────────────
    # Replicate gex_model.strike_walls: heaviest POSITIVE gamma above spot
    # gex_model uses net sign for wall detection; here call_gex is always ≥0
    # and put_gex is always ≥0 (unsigned magnitudes), so we use call_gex above spot.
    call_wall = None
    call_wall_val = -1.0
    for k in strikes:
        if k > spot:
            cgex = by_strike[k].get("call_gex", 0.0) or 0.0
            if cgex > call_wall_val:
                call_wall_val = cgex
                call_wall = k

    # ── put support: strike below spot with max putOI × putGamma ─────────────
    put_support = None
    put_support_val = -1.0
    for k in strikes:
        if k < spot:
            pgex = by_strike[k].get("put_gex", 0.0) or 0.0
            if pgex > put_support_val:
                put_support_val = pgex
                put_support = k

    # ── HVL (gamma magnet): prism_spec §7 ────────────────────────────────────
    # score(s) = totalOI * avgGamma * proximity
    # proximity = 1 / (1 + |strike-spot| / (avgStep * 3))
    steps = [strikes[i+1] - strikes[i] for i in range(len(strikes)-1)]
    avg_step = statistics.median(steps) if steps else (spot * 0.01)

    hvl = None
    hvl_val = -1.0
    for k in strikes:
        total_oi = ((by_strike[k].get("call_oi") or 0) +
                    (by_strike[k].get("put_oi") or 0))
        total_gex = ((by_strike[k].get("call_gex") or 0) +
                     (by_strike[k].get("put_gex") or 0))
        avg_gamma = (total_gex / max(total_oi, 1)) if total_oi > 0 else 0.0
        prox = 1.0 / (1.0 + abs(k - spot) / max(avg_step * 3, 1e-6))
        score = total_oi * avg_gamma * prox
        if score > hvl_val:
            hvl_val = score
            hvl = k

    # ── gamma flip: cumulative net GEX zero-crossing (prism_spec §7) ─────────
    # net per strike = call_gex − put_gex (calls +, puts −, dealer-short assumption)
    cum_net = 0.0
    gamma_flip = None
    prev_k = None
    prev_cum = None
    for k in sorted(strikes):
        net_k = (by_strike[k].get("call_gex") or 0.0) - (by_strike[k].get("put_gex") or 0.0)
        cum_net += net_k
        if prev_cum is not None and (prev_cum < 0) != (cum_net < 0):
            # linear interpolation
            denom = abs(prev_cum) + abs(cum_net)
            if denom > 0:
                ratio = abs(prev_cum) / denom
                crossing = prev_k + ratio * (k - prev_k)
                # keep crossing nearest to spot
                if gamma_flip is None or abs(crossing - spot) < abs(gamma_flip - spot):
                    gamma_flip = crossing
        prev_k = k
        prev_cum = cum_net

    # ── max pain ──────────────────────────────────────────────────────────────
    rows = []
    for k, d in by_strike.items():
        rows.append({
            "strike":   k,
            "call_oi":  d.get("call_oi") or 0,
            "put_oi":   d.get("put_oi")  or 0,
        })
    mp_df = pd.DataFrame(rows)
    max_pain_val = _compute_max_pain(mp_df) if not mp_df.empty else None

    return {
        "call_wall":   _f(call_wall),
        "put_support": _f(put_support),
        "hvl":         _f(hvl),
        "gamma_flip":  _f(gamma_flip),
        "max_pain":    _f(max_pain_val),
    }


# ============================================================================ #
# Heat-seeker picker (prism_spec §5)
# ============================================================================ #

def _heat_seeker(
    cells: list[dict],
    spot: float,
    lens: str,
) -> dict | None:
    """Return the gated standout cell for `lens`, or None.

    Gates (per prism_spec §5):
      - total chain OI must exceed _MIN_TOTAL_OI (5000)
      - candidates: value > 0; exclude spot-adjacent row (nearest strike to spot)
      - DTE penalty applied for GEX (prism_spec §5: dte < 0.5 days)
      - standout ratio: top / second-best must beat per-lens threshold
      - confidence = min(1, (ratio-1)/3) must beat _MIN_CONFIDENCE (0.15)

    note field is hardcoded "descriptive — not a recommendation" (CI-enforced).
    """
    # total chain OI gate
    total_oi = sum((c.get("call_oi") or 0) + (c.get("put_oi") or 0) for c in cells)
    if total_oi < _MIN_TOTAL_OI:
        return None

    # identify the nearest-to-spot strike (one per underlying, across all cells)
    # prism_spec §5 excludeSpotRow: drop the strike closest to spot, not exact match
    all_strikes = [c.get("strike", 0.0) for c in cells if c.get("strike") is not None]
    nearest_strike: float | None = (
        min(all_strikes, key=lambda k: abs(k - spot)) if all_strikes else None
    )

    # build candidate list
    candidates: list[tuple[float, float, dict]] = []  # (scored_val, raw_val, cell)

    for c in cells:
        strike = c.get("strike", 0.0)
        expiry = c.get("expiry", "")
        dte_val = c.get("_dte", 1.0)

        # Exclude already-expired contracts — DTE must be > 0
        # (same-day sentinel 0.5 is retained; negative means past expiry)
        if dte_val < 0:
            continue

        # exclude nearest-to-spot strike (prism_spec §5 excludeSpotRow)
        if nearest_strike is not None and abs(strike - nearest_strike) < 1e-6:
            continue

        if lens == "GEX":
            raw_val = abs(c.get("gex") or 0.0)
            # DTE penalty (prism_spec §5)
            if dte_val < _MIN_DTE_FLOOR:
                scored_val = raw_val * math.sqrt(max(dte_val, 1e-6) / _MIN_DTE_FLOOR)
            else:
                scored_val = raw_val

        elif lens == "OI":
            # calls and puts evaluated separately
            call_val = c.get("call_oi") or 0
            put_val  = c.get("put_oi")  or 0
            # take the larger side
            raw_val    = float(max(call_val, put_val))
            scored_val = raw_val

        elif lens == "VOL":
            call_val = c.get("call_vol") or 0
            put_val  = c.get("put_vol")  or 0
            raw_val  = float(max(call_val, put_val))
            # proximity penalty (prism_spec §5)
            dist_pct = abs(strike - spot) / max(spot, 1e-6)
            prox_factor = 1.0 if dist_pct >= 0.02 else (0.6 + dist_pct / 0.02 * 0.4)
            scored_val = raw_val * prox_factor

        else:
            continue

        if raw_val <= 0 or not math.isfinite(scored_val):
            continue

        candidates.append((scored_val, raw_val, c))

    if len(candidates) < 2:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    top_scored, top_raw, top_cell = candidates[0]
    second_scored = candidates[1][0]

    if second_scored <= 0:
        ratio = 999.0
    else:
        ratio = top_scored / second_scored

    threshold = _STANDOUT_RATIO.get(lens, _STANDOUT_RATIO_DEFAULT)
    confidence = min(1.0, (ratio - 1.0) / 3.0)

    if ratio < threshold or confidence < _MIN_CONFIDENCE:
        return None

    return {
        "strike":       _f(top_cell.get("strike")),
        "expiry":       top_cell.get("expiry"),
        "lens":         lens,
        "standout_ratio": round(ratio, 2),
        "confidence":   round(confidence, 2),
        "note":         "descriptive — not a recommendation",
    }


# ============================================================================ #
# Main builder
# ============================================================================ #

def build_matrix(
    root: str,
    store,
    asof: Optional[str] = None,
) -> dict:
    """Build the options_structure.matrix/v1 payload for one underlying.

    Parameters
    ----------
    root:
        Option root symbol, e.g. "SPY".
    store:
        Path to the ThetaData EOD store root (string or Path), or None to use
        the env-default from thetadata_store.store_root().
    asof:
        Reference date "YYYY-MM-DD".  When None, the most recent date with OI
        data is used.

    Returns
    -------
    dict conforming to options_structure.matrix/v1, pre-validated.
    Raises ValueError if validate_matrix() returns errors.

    OI TIMING LAW:
      OI[t-1]: the OI parquet for `asof` (OPRA reports EOD of previous session).
      OI[t-2]: the OI parquet for the session before `asof`.
      delta_oi = OI[t-1] − OI[t-2] (both lagged — fully PIT-safe).
      Same-day OI is NEVER used.

    DEFERRED in v1:
      VEX lens: requires greeks-path stability verification.
      UNUSUAL lens: requires 30d per-strike volume baseline.
    """
    root = root.upper()
    asof_ts = datetime.now(tz=timezone.utc).isoformat()

    # ── resolve asof date ────────────────────────────────────────────────────
    # Load all OI to find the most recent date if asof not provided.
    oi_all = _load_parquets("oi", root, None, store)
    if not oi_all.empty:
        oi_all = _normalise_date(oi_all)

    if asof is None:
        if oi_all.empty or "date" not in oi_all.columns:
            log.warning("options_matrix: no OI data for %s — returning thin-chain null", root)
            return _null_payload(root, asof_ts, "no OI data in store")
        asof = str(sorted(oi_all["date"].unique())[-1])

    # ── OI[t-1]: the parquet dated `asof` ───────────────────────────────────
    oi_t1 = _load_oi(root, asof, store)

    if oi_t1.empty:
        log.warning("options_matrix: OI[t-1] empty for %s on %s", root, asof)
        return _null_payload(root, asof_ts, f"OI[t-1] empty on {asof}")

    # ── OI[t-2]: the session before `asof` ──────────────────────────────────
    t2_date = _prev_date(oi_all, asof)
    oi_t2: pd.DataFrame
    if t2_date:
        oi_t2 = _load_oi(root, t2_date, store)
    else:
        oi_t2 = pd.DataFrame()

    # ── EOD[t-1]: volume for latest session ─────────────────────────────────
    year = pd.Timestamp(asof).year
    eod_all = _load_parquets("eod", root, [year], store)
    if not eod_all.empty:
        eod_all = _normalise_date(eod_all)
    eod_t1 = eod_all[eod_all["date"] == asof].copy() if not eod_all.empty else pd.DataFrame()

    # ── greeks for IV ───────────────────────────────────────────────────────
    greeks_all = _load_parquets("greeks", root, [year], store)
    if not greeks_all.empty:
        greeks_all = _normalise_date(greeks_all)
    greeks_t1 = greeks_all[greeks_all["date"] == asof].copy() if not greeks_all.empty else pd.DataFrame()

    # ── spot ─────────────────────────────────────────────────────────────────
    spot = _extract_spot(greeks_t1, eod_t1)
    if spot is None or spot <= 0:
        log.warning("options_matrix: cannot determine spot for %s on %s", root, asof)
        return _null_payload(root, asof_ts, f"spot unavailable on {asof}")

    # ── filter to strike window ±20% and ≤90 DTE ────────────────────────────
    low_k  = spot * (1.0 - _STRIKE_PCT)
    high_k = spot * (1.0 + _STRIKE_PCT)

    def _in_window(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "strike" not in df.columns:
            return df
        df = df.copy()
        df["strike"] = df["strike"].astype(float)
        df = df[(df["strike"] >= low_k) & (df["strike"] <= high_k)]
        if "expiration" in df.columns:
            df = df[df["expiration"].notna()]
            # Normalize to plain ISO date ("YYYY-MM-DD") — parquets may store
            # pandas Timestamps which stringify as "2026-07-06 00:00:00".
            df["expiration"] = df["expiration"].apply(_to_iso_date)
            df["_dte"] = df["expiration"].apply(lambda e: _dte(e, asof))
            # Exclude already-expired contracts: DTE window is [0, +90], never negative.
            # Same-day expiries are retained (DTE == 0.5 sentinel) per prism_spec §5.
            df = df[(df["_dte"] > 0) & (df["_dte"] <= _MAX_DTE)]
        return df

    oi_t1_w  = _in_window(oi_t1)
    oi_t2_w  = _in_window(oi_t2) if not oi_t2.empty else pd.DataFrame()
    eod_w    = _in_window(eod_t1)
    greeks_w = _in_window(greeks_t1)

    if oi_t1_w.empty:
        log.warning("options_matrix: no OI rows in window for %s on %s", root, asof)
        return _null_payload(root, asof_ts, "no OI rows in ±20% / ≤90DTE window")

    # ── collect all IVs for median fallback ──────────────────────────────────
    all_ivs: list[float] = []
    if not greeks_w.empty and "implied_vol" in greeks_w.columns:
        all_ivs = greeks_w["implied_vol"].dropna().tolist()
    median_iv = _median_iv(all_ivs)

    # ── build cell map (strike, expiry) → accumulation dict ─────────────────
    # keyed by (strike_float, expiry_str)
    cell_map: dict[tuple, dict] = {}

    def _get_cell(k: float, exp: str) -> dict:
        key = (k, exp)
        if key not in cell_map:
            cell_map[key] = {
                "strike":   k,
                "expiry":   exp,
                "call_oi":  0,
                "put_oi":   0,
                "call_vol": 0,
                "put_vol":  0,
                "call_gex": 0.0,
                "put_gex":  0.0,
                "call_oi_t2": 0,
                "put_oi_t2":  0,
                "_dte":     _dte(exp, asof),
            }
        return cell_map[key]

    # ── OI[t-1] accumulation with GEX ────────────────────────────────────────
    for _, row in oi_t1_w.iterrows():
        k   = float(row["strike"])
        exp = _to_iso_date(row.get("expiration", ""))
        oi  = float(row.get("open_interest", 0) or 0)
        right = str(row.get("right", "")).upper()[:1]

        if oi <= 0 or not exp:
            continue

        # IV for this contract: prefer greeks, else median_iv
        iv_contract = _lookup_iv(greeks_w, k, exp, right)
        dte_days    = _dte(exp, asof)
        T_years     = dte_days / 365.0
        gamma       = _bs_gamma_scalar(spot, k, T_years, iv_contract, median_iv)
        gex         = _gex_dollar(oi, gamma, spot)

        cell = _get_cell(k, exp)
        if right == "C":
            cell["call_oi"]  += int(oi)
            cell["call_gex"] += gex      # positive (calls +)
        elif right == "P":
            cell["put_oi"]  += int(oi)
            cell["put_gex"] += gex       # magnitude (unsigned here; sign in net)

    # ── OI[t-2] accumulation for delta_oi ───────────────────────────────────
    if not oi_t2_w.empty:
        for _, row in oi_t2_w.iterrows():
            k   = float(row["strike"])
            exp = _to_iso_date(row.get("expiration", ""))
            oi  = float(row.get("open_interest", 0) or 0)
            right = str(row.get("right", "")).upper()[:1]
            if not exp:
                continue
            cell = _get_cell(k, exp)
            if right == "C":
                cell["call_oi_t2"] += int(oi)
            elif right == "P":
                cell["put_oi_t2"]  += int(oi)

    # ── volume accumulation (EOD latest session) ──────────────────────────────
    if not eod_w.empty and "volume" in eod_w.columns:
        for _, row in eod_w.iterrows():
            k   = float(row.get("strike", 0))
            exp = _to_iso_date(row.get("expiration", ""))
            vol = float(row.get("volume", 0) or 0)
            right = str(row.get("right", "")).upper()[:1]
            if not exp or k < low_k or k > high_k:
                continue
            cell = _get_cell(k, exp)
            if right == "C":
                cell["call_vol"] += int(vol)
            elif right == "P":
                cell["put_vol"]  += int(vol)

    # ── build strike-level aggregate for level computation ───────────────────
    by_strike: dict[float, dict] = {}
    for (k, _exp), c in cell_map.items():
        if k not in by_strike:
            by_strike[k] = {"call_oi": 0, "put_oi": 0, "call_gex": 0.0, "put_gex": 0.0}
        by_strike[k]["call_oi"]  += c["call_oi"]
        by_strike[k]["put_oi"]   += c["put_oi"]
        by_strike[k]["call_gex"] += c["call_gex"]
        by_strike[k]["put_gex"]  += c["put_gex"]

    # ── serialize cells ───────────────────────────────────────────────────────
    expiry_set: set[str] = set()
    strike_set: set[float] = set()
    cells_out: list[dict] = []

    for (k, exp), c in sorted(cell_map.items(), key=lambda x: (x[0][1], x[0][0])):
        # net GEX = call_gex − put_gex (dealer-short: calls +, puts −)
        net_gex = c["call_gex"] - c["put_gex"]

        # delta_oi = OI[t-1] − OI[t-2] (both lagged; PIT-safe)
        d_call = c["call_oi"] - c["call_oi_t2"]
        d_put  = c["put_oi"]  - c["put_oi_t2"]

        cells_out.append({
            "strike":   _f(k),
            "expiry":   exp,
            "gex":      _f(net_gex, 0),      # integer dollars is sufficient precision
            "call_oi":  c["call_oi"]  or None,
            "put_oi":   c["put_oi"]   or None,
            "call_vol": c["call_vol"] or None,
            "put_vol":  c["put_vol"]  or None,
            "delta_oi": {
                "call": d_call if c["call_oi"] > 0 or c["call_oi_t2"] > 0 else None,
                "put":  d_put  if c["put_oi"]  > 0 or c["put_oi_t2"]  > 0 else None,
            },
            "_dte":    c["_dte"],             # internal; stripped before validate
        })
        expiry_set.add(exp)
        strike_set.add(k)

    # ── key levels ───────────────────────────────────────────────────────────
    levels = _compute_levels(by_strike, spot, asof, median_iv)

    # ── heat-seeker ──────────────────────────────────────────────────────────
    # Try GEX first, then OI, then VOL
    heat_seeker = None
    for lens in ("GEX", "OI", "VOL"):
        hs = _heat_seeker(cells_out, spot, lens)
        if hs is not None:
            heat_seeker = hs
            break

    # ── strip internal _dte field from cells before output ───────────────────
    for cell in cells_out:
        cell.pop("_dte", None)

    # ── assemble payload ──────────────────────────────────────────────────────
    payload = {
        "schema":   "options_structure.matrix/v1",
        "asof":     asof_ts,
        "root":     root,
        "spot":     _f(spot),
        "expiries": sorted(expiry_set),
        "strikes":  sorted(strike_set),
        "cells":    cells_out,
        "levels":   levels,
        "heat_seeker": heat_seeker,
        "authority_tier": "display",
        "reliability": {
            "gex":       "assumption-signed — display-only until GEX→vol gate (~Sept 2026)",
            "delta_oi":  "reliable — signing-free OI change (OI[t-1] − OI[t-2], both lagged)",
            "vol":       "reliable magnitude",
            "call_oi":   "reliable — OI[t-1]",
            "put_oi":    "reliable — OI[t-1]",
            "note":      "Sign is an assumption, not a fact. Magnitude is the reliable read.",
        },
        "deferred": {
            "VEX":     "deferred — requires greeks-path stability verification across ThetaData store",
            "UNUSUAL": "deferred — requires 30d per-strike volume baseline not yet in EOD store",
        },
        "_build_meta": {
            "asof_date":    asof,
            "t2_date":      t2_date,
            "n_cells":      len(cells_out),
            "n_expiries":   len(expiry_set),
            "n_strikes":    len(strike_set),
            "median_iv":    round(median_iv, 4),
            "spot":         _f(spot),
        },
    }

    # ── validate ──────────────────────────────────────────────────────────────
    errors = validate_matrix(payload)
    if errors:
        raise ValueError(f"options_matrix validate_matrix failed for {root}: {errors}")

    log.info(
        "options_matrix: %s asof=%s cells=%d expiries=%d strikes=%d spot=%.2f",
        root, asof, len(cells_out), len(expiry_set), len(strike_set), spot,
    )
    return payload


# ============================================================================ #
# helpers
# ============================================================================ #

def _null_payload(root: str, asof_ts: str, reason: str) -> dict:
    """Minimal conforming payload when data is absent (thin-chain / null-safe)."""
    payload = {
        "schema":   "options_structure.matrix/v1",
        "asof":     asof_ts,
        "root":     root,
        "spot":     None,
        "expiries": [],
        "strikes":  [],
        "cells":    [],
        "levels": {
            "call_wall":   None,
            "put_support": None,
            "hvl":         None,
            "gamma_flip":  None,
            "max_pain":    None,
        },
        "heat_seeker": None,
        "authority_tier": "display",
        "reliability": {
            "gex":       "assumption-signed — display-only until GEX→vol gate (~Sept 2026)",
            "delta_oi":  "reliable — signing-free OI change",
            "vol":       "reliable magnitude",
            "note":      "Sign is an assumption, not a fact. Magnitude is the reliable read.",
        },
        "deferred": {
            "VEX":     "deferred — requires greeks-path stability verification",
            "UNUSUAL": "deferred — requires 30d per-strike volume baseline",
        },
        "_no_data_reason": reason,
    }
    errors = validate_matrix(payload)
    if errors:
        log.error("options_matrix: null payload validate error for %s: %s", root, errors)
    return payload


def _extract_spot(greeks_df: pd.DataFrame, eod_df: pd.DataFrame) -> float | None:
    """Extract spot price from greeks (underlying_price) or EOD close."""
    if not greeks_df.empty and "underlying_price" in greeks_df.columns:
        v = greeks_df["underlying_price"].dropna()
        if not v.empty:
            return float(v.iloc[0])
    if not eod_df.empty and "close" in eod_df.columns:
        # Use ATM close as proxy — pick highest-OI strike's close
        v = eod_df["close"].dropna()
        if not v.empty:
            return float(v.median())
    return None


def _lookup_iv(greeks_df: pd.DataFrame, strike: float, expiry: str, right: str) -> float:
    """Return IV for (strike, expiry, right) from greeks, or 0.0 if not found.

    Both sides normalized to plain ISO date to match regardless of parquet storage type.
    """
    if greeks_df.empty or "implied_vol" not in greeks_df.columns:
        return 0.0
    mask = (
        (greeks_df["strike"].astype(float) == strike) &
        (greeks_df["expiration"].apply(_to_iso_date) == expiry) &
        (greeks_df["right"].astype(str).str.upper().str[:1] == right[:1])
    )
    sub = greeks_df[mask]["implied_vol"].dropna()
    return float(sub.iloc[0]) if not sub.empty else 0.0
