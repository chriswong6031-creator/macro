"""Flagship-2 Reversion Desk — pure composition function (spec §4).

Computes the daily Reversion Desk top-12 from the CN snapshot DataFrame.

Rank = reversal depth (deepest quintile, ranked by rev_3m_sector_rank ascending).
Bonuses (rank-order only, additive on top of the depth rank):
  +0.5   washout_2w
  +0.25  coiled
  +0.15  star
  -0.5×extension_score  (anti-chase penalty)

Executability screens (applied before ranking, not signals):
  - drop fillable == False
  - drop is_st == True

Chips (display context, never gates):
  d1_macd_xup_bars, d1_kd_xup_bars, d1_from_os,
  d2_macd_xup_bars, d2_kd_xup_bars,
  cycle_phase, participation_regime, chase_veto, t_plus_one_risk,
  coiled, star, washout_2w, extension_extended

Output schema (site/factordata/china_reversion_desk.json):
  schema: "china_reversion_desk.v1"
  as_of:  str
  rows:   list of {
    ticker, name, name_zh, rank, score, rev_depth, bonuses, chips, close, sector
  }

Max 12 rows.

CNPL-R1: authority = "display_only" on every row.
CNPL-R4: fillable == False excluded (executability screen).
CN kill law: no momentum ranks, no subsector-state gates, no northbound.
"validated" word: NOT used anywhere in this module (CI-enforced).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

_MAX_ROWS = 12


# --------------------------------------------------------------------------- #
# Bonus arithmetic (spec §4, CN-validated vocabulary)                         #
# --------------------------------------------------------------------------- #

def _compute_score(row: "pd.Series[Any]") -> float:
    """Compute the rank score for a single snapshot row.

    Score = reversal depth rank score (depth, negated so deeper = higher) +
            bonuses/penalties.

    depth_component: we invert rev_3m_sector_rank so the deepest rank (1)
    gets the highest component.  When rev_3m_sector_rank is None, the name
    is still eligible (deepest-quintile flag was set) but ranks last in the
    depth component.
    """
    # Depth component: deeper (lower rank) → higher score
    rank = row.get("rev_3m_sector_rank")
    sector_n = row.get("rev_sector_n") or 1
    if rank is not None and not _is_null(rank):
        # Normalize: depth = 1 - (rank - 1) / sector_n → 1 for rank=1, ~0 for last
        depth_score = 1.0 - (float(rank) - 1.0) / max(float(sector_n), 1.0)
    else:
        depth_score = 0.0

    # Bonuses (additive, CN-validated vocabulary only)
    bonus = 0.0
    if bool(row.get("washout_2w")):
        bonus += 0.5
    if bool(row.get("coiled")):
        bonus += 0.25
    elif bool(row.get("star")):
        bonus += 0.15

    # Anti-chase penalty
    ext_score = row.get("extension_score")
    if ext_score is not None and not _is_null(ext_score):
        bonus -= 0.5 * float(ext_score)

    return round(depth_score + bonus, 6)


def _is_null(v: Any) -> bool:
    """True if v is None or NaN."""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except Exception:
        return False


def _bonus_dict(row: "pd.Series[Any]") -> dict:
    """Return a dict describing applied bonuses (for the 'bonuses' field in output)."""
    out: dict = {}
    if bool(row.get("washout_2w")):
        out["washout_2w"] = 0.5
    if bool(row.get("coiled")):
        out["coiled"] = 0.25
    elif bool(row.get("star")):
        out["star"] = 0.15
    ext_score = row.get("extension_score")
    if ext_score is not None and not _is_null(ext_score) and float(ext_score) > 0:
        out["extension_penalty"] = round(-0.5 * float(ext_score), 4)
    return out


def _chips(row: "pd.Series[Any]") -> dict:
    """Extract display chips from a snapshot row (never gates)."""
    chips: dict = {}
    for key in (
        "d1_macd_xup_bars", "d1_kd_xup_bars", "d1_from_os",
        "d2_macd_xup_bars", "d2_kd_xup_bars",
        "cycle_phase", "participation_regime",
        "chase_veto", "t_plus_one_risk",
        "coiled", "star", "washout_2w", "extension_extended",
    ):
        v = row.get(key)
        if not _is_null(v):
            chips[key] = v
    return chips


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def compute_reversion_desk(
    snap: pd.DataFrame,
    *,
    as_of: str,
    max_rows: int = _MAX_ROWS,
) -> list[dict]:
    """Compute the Flagship-2 Reversion Desk rows from a CN snapshot DataFrame.

    Parameters
    ----------
    snap : pd.DataFrame
        Index = ticker.  Must contain CN_SNAPSHOT_COLUMNS (or a superset).
        Columns that are absent default to None / False during scoring.
    as_of : str
        Date string for the as_of stamp on the output.
    max_rows : int
        Maximum number of rows to return (default 12, spec §4).

    Returns
    -------
    list[dict]  — ordered by score descending; up to max_rows entries.
    Each row:
      ticker, name, name_zh, rank, score, rev_depth, bonuses, chips, close, sector
      authority: "display_only"  (CNPL-R1)

    Returns empty list (never raises) on any failure.
    """
    if snap is None or (hasattr(snap, "empty") and snap.empty):
        return []

    try:
        return _compute(snap, as_of=as_of, max_rows=max_rows)
    except Exception as exc:
        log.error("reversion_desk.compute_reversion_desk failed: %s", exc, exc_info=True)
        return []


def _compute(
    snap: pd.DataFrame,
    *,
    as_of: str,
    max_rows: int,
) -> list[dict]:
    df = snap.copy()

    # 1. Executability screens (not signals, CNPL-R4)
    #    Drop is_st == True
    if "is_st" in df.columns:
        df = df[~df["is_st"].eq(True).fillna(False)]
    if df.empty:
        return []

    #    Drop fillable == False
    if "fillable" in df.columns:
        df = df[df["fillable"].ne(False).fillna(True)]
    if df.empty:
        return []

    # 2. Must be in the deepest reversal quintile (the flat validated construction)
    if "rev_deepest_quintile" in df.columns:
        df = df[df["rev_deepest_quintile"].eq(True).fillna(False)]
    else:
        log.warning("reversion_desk: rev_deepest_quintile column absent — empty desk")
        return []
    if df.empty:
        return []

    # 3. Score and rank
    df = df.copy()
    df["_score"] = df.apply(_compute_score, axis=1)
    df = df.sort_values("_score", ascending=False).head(max_rows)

    # 4. Build output rows
    rows: list[dict] = []
    for rank, (ticker, row) in enumerate(df.iterrows(), 1):
        rev_rank = row.get("rev_3m_sector_rank")
        sector_n = row.get("rev_sector_n")
        rows.append({
            "ticker": ticker,
            "name": row.get("name"),
            "name_zh": row.get("name_zh"),
            "rank": rank,
            "score": round(float(row["_score"]), 4),
            "rev_depth": {
                "rev_z": row.get("rev_z"),
                "rev_3m": row.get("rev_3m"),
                "sector_rank": int(rev_rank) if not _is_null(rev_rank) else None,
                "sector_n": int(sector_n) if not _is_null(sector_n) else None,
            },
            "bonuses": _bonus_dict(row),
            "chips": _chips(row),
            "close": row.get("close"),
            "sector": row.get("sector"),
            "authority": "display_only",
        })
    return rows


# --------------------------------------------------------------------------- #
# JSON artifact wrapper (convenience for the build caller)                    #
# --------------------------------------------------------------------------- #

def build_reversion_desk_artifact(
    snap: pd.DataFrame,
    *,
    as_of: str,
    max_rows: int = _MAX_ROWS,
) -> dict:
    """Build the full china_reversion_desk.json artifact dict.

    Returns a dict with schema/as_of/rows, suitable for json.dumps.
    Never raises; on failure returns the schema shell with rows=[].
    """
    try:
        rows = compute_reversion_desk(snap, as_of=as_of, max_rows=max_rows)
    except Exception as exc:
        log.error("reversion_desk artifact build failed: %s", exc, exc_info=True)
        rows = []
    return {
        "schema": "china_reversion_desk.v1",
        "as_of": as_of,
        "rows": rows,
        "n_rows": len(rows),
        "authority": "display_only",
    }
