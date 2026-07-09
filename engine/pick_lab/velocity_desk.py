"""HK Pick Lab — Flagship-2 1D Velocity Desk (spec §4).

Pure composition function that computes the 1D Velocity Desk from the HK
snapshot DataFrame.  Mirrors reversion_desk.py for CN but uses HK-specific
1D-family membership predicates.

Two-pass contract
-----------------
The desk is written twice each nightly cycle:

1. Producer pass (build_hk_library.compute_hk_standouts):
   Only price-level columns are available (edge_z, rsi14, above_200, d1_*,
   washout_2w).  Organ columns (washout_state, adr_gap_pct, risk_state,
   sb_accum_z, cbbc_leverage_state) are null.  The desk is written as a
   price-only first pass — confluence conditions that depend on organ columns
   null-fail honestly (counted as 0 in confluence_n).

2. Runner pass (build_hk_pick_lab.py):
   After enrichment join, organ columns are populated.  The runner calls
   compute_velocity_desk() again with the enriched snapshot and re-writes
   site/factordata/hk_1d_velocity_desk.json.  The runner also fires the
   flagship2_mirror ledger entry from the enriched desk rows.

Membership — union of Family A (books 1–5) conditions:
  Any of:
    1. hklab_1d_pure:    d1_macd_xup_bars ≤ 2 AND d1_stoch_xup_bars ≤ 8 AND from_os AND rsi14<70
    2. hklab_1d_ignition: d1_macd_xup_bars ≤ 3 AND washout_state in {ignition,pullback_entry}
    3. hklab_1d_adr:     d1_macd_xup_bars ≤ 2 AND adr_gap_pct ≥ 0.5
    4. hklab_1d_blastoff: d1_macd_xup_bars ≤ 3 AND d3_macd_xup_bars is null AND above_200
    5. hklab_1d_regime:  d1_macd_xup_bars ≤ 3 AND risk_state="Risk-on"

Rank = confluence_n (how many of: from_os, washout_state active, adr_gap_pct≥0.5,
       risk_state Risk-on, above_200) DESC, then edge_z DESC.

Chips per spec §4:
  - Which 1D conditions fired (chip keys)
  - washout_state (if present)
  - adr_gap_pct (if ≥ 0.5 or present)
  - beta_role (context)
  - knife_risk warning chip (shown, NOT an exclusion — HK keeps knives visible)
  - extended warning chip (shown, NOT an exclusion)
  - cbbc_leverage_state (if present)

Max 8 rows (HKPL-R6).

Output schema (site/factordata/hk_1d_velocity_desk.json):
  schema: "hk_1d_velocity_desk.v1"
  as_of:  str
  rows:   list of {
    ticker, name, name_zh, rank, confluence_n, chips, close, sector,
    edge_z, authority
  }
  authority: "display_only"  (HKPL-R1)

HKPL-R1: authority = "display_only" on every row and the artifact.
HK kill law: no momentum ranks, no SB Δ-ranking, no COILED, no Connect events.
"validated" word: NOT used anywhere in this module (CI-enforced).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

_MAX_ROWS = 8   # HKPL-R6: max 8 picks/day


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _is_null(v: Any) -> bool:
    """True if v is None or NaN."""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except Exception:
        return False


def _get(row: "pd.Series[Any]", col: str, default: Any = None) -> Any:
    """Safe column access from a Series (None if missing or NaN)."""
    v = row.get(col)
    return default if _is_null(v) else v


# --------------------------------------------------------------------------- #
# 1D-family membership predicates — mirror the hk.py book conditions          #
# --------------------------------------------------------------------------- #

def _cond_1d_pure(row: "pd.Series[Any]") -> bool:
    """hklab_1d_pure: d1_macd_xup_bars≤2 AND d1_stoch_xup_bars≤8 AND from_os AND rsi14<70."""
    mx = _get(row, "d1_macd_xup_bars")
    sx = _get(row, "d1_stoch_xup_bars")
    from_os = _get(row, "d1_from_os")
    rsi = _get(row, "rsi14")
    return (
        mx is not None and float(mx) <= 2
        and sx is not None and float(sx) <= 8
        and from_os is True
        and rsi is not None and float(rsi) < 70
    )


def _cond_1d_ignition(row: "pd.Series[Any]") -> bool:
    """hklab_1d_ignition: d1_macd_xup_bars≤3 AND washout_state in {ignition_watch,pullback_entry_watch}."""
    mx = _get(row, "d1_macd_xup_bars")
    ws = _get(row, "washout_state")
    return (
        mx is not None and float(mx) <= 3
        and ws in ("ignition_watch", "pullback_entry_watch")
    )


def _cond_1d_adr(row: "pd.Series[Any]") -> bool:
    """hklab_1d_adr: d1_macd_xup_bars≤2 AND adr_gap_pct≥0.5."""
    mx = _get(row, "d1_macd_xup_bars")
    gap = _get(row, "adr_gap_pct")
    return (
        mx is not None and float(mx) <= 2
        and gap is not None and float(gap) >= 0.5
    )


def _cond_1d_blastoff(row: "pd.Series[Any]") -> bool:
    """hklab_1d_blastoff: d1_macd_xup_bars≤3 AND d3_macd_xup_bars is null AND above_200."""
    mx = _get(row, "d1_macd_xup_bars")
    d3 = _get(row, "d3_macd_xup_bars")
    above = _get(row, "above_200")
    return (
        mx is not None and float(mx) <= 3
        and d3 is None          # not yet crossed on 3D grid
        and above is True
    )


def _cond_1d_regime(row: "pd.Series[Any]") -> bool:
    """hklab_1d_regime: d1_macd_xup_bars≤3 AND risk_state='Risk-on'."""
    mx = _get(row, "d1_macd_xup_bars")
    rs = _get(row, "risk_state")
    return (
        mx is not None and float(mx) <= 3
        and rs == "Risk-on"
    )


def _is_1d_member(row: "pd.Series[Any]") -> bool:
    """True when the row satisfies any 1D-family (books 1–5) condition."""
    return (
        _cond_1d_pure(row)
        or _cond_1d_ignition(row)
        or _cond_1d_adr(row)
        or _cond_1d_blastoff(row)
        or _cond_1d_regime(row)
    )


# --------------------------------------------------------------------------- #
# Confluence count                                                             #
# --------------------------------------------------------------------------- #

def _confluence_n(row: "pd.Series[Any]") -> int:
    """Count of secondary confluence signals present (spec §4 rank key).

    Signals counted (each is 0 or 1):
      1. from_os         (d1_from_os == True)
      2. washout active  (washout_state in {washout_watch, ignition_watch, pullback_entry_watch})
      3. adr_gap         (adr_gap_pct >= 0.5)
      4. risk_on         (risk_state == "Risk-on")
      5. above_200       (above_200 == True)
    """
    n = 0
    if _get(row, "d1_from_os") is True:
        n += 1
    ws = _get(row, "washout_state")
    if ws in ("washout_watch", "ignition_watch", "pullback_entry_watch"):
        n += 1
    gap = _get(row, "adr_gap_pct")
    if gap is not None and float(gap) >= 0.5:
        n += 1
    if _get(row, "risk_state") == "Risk-on":
        n += 1
    if _get(row, "above_200") is True:
        n += 1
    return n


# --------------------------------------------------------------------------- #
# Chips                                                                       #
# --------------------------------------------------------------------------- #

def _build_chips(row: "pd.Series[Any]") -> dict:
    """Build display chips for a desk row (spec §4).

    Chips are context only — never gates.
    Knife/chase warnings are shown as chips, NOT exclusions (HK doctrine).
    """
    chips: dict = {}

    # Which 1D conditions fired
    if _cond_1d_pure(row):
        chips["1d_pure"] = True
    if _cond_1d_ignition(row):
        chips["1d_ignition"] = True
    if _cond_1d_adr(row):
        chips["1d_adr"] = True
    if _cond_1d_blastoff(row):
        chips["1d_blastoff"] = True
    if _cond_1d_regime(row):
        chips["1d_regime"] = True

    # Washout state (organ; None at producer time)
    ws = _get(row, "washout_state")
    if ws is not None:
        chips["washout_state"] = ws

    # ADR gap (organ; None at producer time)
    gap = _get(row, "adr_gap_pct")
    if gap is not None:
        chips["adr_gap_pct"] = round(float(gap), 2)

    # 1D oscillator context (always from snapshot)
    mx = _get(row, "d1_macd_xup_bars")
    if mx is not None:
        chips["d1_macd_xup_bars"] = float(mx)
    sx = _get(row, "d1_stoch_xup_bars")
    if sx is not None:
        chips["d1_stoch_xup_bars"] = float(sx)
    if _get(row, "d1_from_os") is True:
        chips["from_os"] = True

    # Beta role (context)
    br = _get(row, "beta_role")
    if br is not None:
        chips["beta_role"] = br

    # CBBC leverage state (organ; None at producer time)
    cbbc = _get(row, "cbbc_leverage_state")
    if cbbc is not None:
        chips["cbbc_leverage_state"] = cbbc

    # Knife warning — shown as chip, NOT an exclusion (HK keeps knives visible)
    kr = _get(row, "knife_risk")
    if kr is True:
        chips["knife_warning"] = True

    # Extended (chase) warning — shown as chip, NOT an exclusion
    ext = _get(row, "extended")
    if ext is True:
        chips["extended_warning"] = True

    return chips


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def compute_velocity_desk(
    snap: "pd.DataFrame",
    *,
    as_of: str,
    max_rows: int = _MAX_ROWS,
) -> list[dict]:
    """Compute the 1D Velocity Desk rows from an HK snapshot DataFrame.

    Parameters
    ----------
    snap : pd.DataFrame
        Index = ticker.  Must contain HK_SNAPSHOT_COLUMNS (or a superset).
        Organ columns may be null (producer first pass); membership and
        confluence scoring gracefully degrade — null conditions fail honestly.
    as_of : str
        Date string for the as_of stamp.
    max_rows : int
        Maximum number of rows (default 8, HKPL-R6).

    Returns
    -------
    list[dict] — ordered by (confluence_n DESC, edge_z DESC); up to max_rows.
    Each row:
      ticker, name, name_zh, rank, confluence_n, chips, close, sector,
      edge_z, authority: "display_only"

    Never raises (returns [] on any failure). HKPL-R1.
    """
    if snap is None or (hasattr(snap, "empty") and snap.empty):
        return []

    try:
        return _compute(snap, as_of=as_of, max_rows=max_rows)
    except Exception as exc:
        log.error("velocity_desk.compute_velocity_desk failed: %s", exc, exc_info=True)
        return []


def _compute(
    snap: "pd.DataFrame",
    *,
    as_of: str,
    max_rows: int,
) -> list[dict]:
    df = snap.copy()

    # 1. Membership filter: any 1D-family condition fires
    member_mask = df.apply(_is_1d_member, axis=1).fillna(False)
    df = df[member_mask].copy()
    if df.empty:
        return []

    # 2. Compute rank keys
    df["_confluence_n"] = df.apply(_confluence_n, axis=1)
    df["_edge_z"] = df.get("edge_z", pd.Series(0.0, index=df.index)).fillna(0.0)

    # 3. Sort: confluence_n DESC, edge_z DESC
    df = df.sort_values(["_confluence_n", "_edge_z"], ascending=[False, False])
    df = df.head(max_rows)

    # 4. Build output rows
    rows: list[dict] = []
    for rank, (ticker, row) in enumerate(df.iterrows(), 1):
        rows.append({
            "ticker": ticker,
            "name": _get(row, "name"),
            "name_zh": _get(row, "name_zh"),
            "rank": rank,
            "confluence_n": int(row["_confluence_n"]),
            "chips": _build_chips(row),
            "close": _get(row, "close"),
            "sector": _get(row, "sector"),
            "edge_z": (round(float(row["_edge_z"]), 4)
                       if not _is_null(row.get("edge_z")) else None),
            "authority": "display_only",
        })
    return rows


# --------------------------------------------------------------------------- #
# JSON artifact wrapper                                                        #
# --------------------------------------------------------------------------- #

def build_velocity_desk_artifact(
    snap: "pd.DataFrame",
    *,
    as_of: str,
    max_rows: int = _MAX_ROWS,
) -> dict:
    """Build the full hk_1d_velocity_desk.json artifact dict.

    Returns a dict with schema/as_of/rows/authority suitable for json.dumps.
    Never raises; on failure returns the schema shell with rows=[].

    Two-pass contract: this function is called twice:
      1. By build_hk_library (producer): organ columns null → honest null-fail.
      2. By build_hk_pick_lab (runner): organ columns enriched → full desk.
    The artifact path is site/factordata/hk_1d_velocity_desk.json.
    """
    try:
        rows = compute_velocity_desk(snap, as_of=as_of, max_rows=max_rows)
    except Exception as exc:
        log.error("velocity_desk artifact build failed: %s", exc, exc_info=True)
        rows = []
    return {
        "schema": "hk_1d_velocity_desk.v1",
        "as_of": as_of,
        "rows": rows,
        "n_rows": len(rows),
        "authority": "display_only",
    }
