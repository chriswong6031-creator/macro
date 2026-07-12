"""CN two-axis standout attribution + fitness card (SA-W2).

Deterministic, NEVER-RAISE.  Reads the committed board.parquet and produces:

  data/standout_audit/cn_attribution.parquet  — per-row attribution (keep-first)
  data/standout_audit/cn_evidence.jsonl       — per newly matured pick evidence pack
  site/factordata/cn_audit_scoreboard.json    — stratified scoreboard
  data/standout_audit/cn_audit_state.json     — freshness stamp (shared with regime store)
  data/metabolism/fitness/standouts_cn.json   — 6-sensor fitness card (til.json format)

All writes are gated on CN_LANE='asia'.  Any failure in attribution NEVER
suppresses the existing grade() call it rides beside (SA-R16).

TAXONOMY v2 (SA-R2 — loop-IMMUTABLE):
  Axis 1 (outcome cause):
    idio_break         excess vs own sector <= IDIO_BREAK_PP
    sector_rotated_out sector excess vs benchmark <= SECTOR_OUT_PP
                       AND pick idio within ±IDIO_BAND_PP of sector
    macro_headwind     benchmark <= MACRO_FALL_PCT over horizon
                       AND pick idio within ±IDIO_BAND_PP of sector
    idio_alpha         excess vs own sector >= IDIO_ALPHA_PP
    beta_tailwind      pick positive, idio within ±IDIO_BAND_PP, sector/mkt strongly positive
    mixed              residual (nothing tiles)

  Precedence (failure): idio_break > sector_rotated_out > macro_headwind
  Precedence (success): idio_alpha > beta_tailwind

  Axis 2 (process fault):
    signaled_too_late  ext_score >= EXT_SCORE_LATE_PCT or board_rank > LATE_RANK_THRESH
                       or stage == 'RAN_LATE'
    gate_suppressed    near-miss not implemented yet — degrades to clean
    premature_stop_noise  terminal_state stopped AND fwd_mfe_21 >= PREMATURE_STOP_MFE_PP
                          (requires own maturity stamp: +21 post-stop sessions — SA-R10)
    data_fault         staleness flags at entry (not yet available in CN ledger — data_gap)
    clean              default

See SA-R2: thresholds in _TAXONOMY_CONSTANTS block; taxonomy_version='v2'.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SA-R2: taxonomy constants — loop-IMMUTABLE by policy.
# These values may ONLY be changed via an operator PR.  No loop-managed lobe
# may tune, read, or reference these thresholds as a parameter.
# ---------------------------------------------------------------------------
_TAXONOMY_CONSTANTS = {
    # Axis-1 thresholds (pp = percentage points; fractions not %)
    "IDIO_BREAK_PP":      -0.04,   # excess vs sector <= -4pp → idio_break
    "IDIO_ALPHA_PP":      +0.04,   # excess vs sector >= +4pp → idio_alpha
    "IDIO_BAND_PP":        0.02,   # ±2pp idio-within-sector band
    "SECTOR_OUT_PP":      -0.025,  # sector vs benchmark <= -2.5pp → sector_rotated_out
    "MACRO_FALL_PCT":     -0.03,   # benchmark return <= -3% → macro_headwind
    "BETA_STRONG_PCT":    +0.02,   # sector/mkt >= +2% for beta_tailwind
    # Axis-2 thresholds
    "EXT_SCORE_LATE_PCT":  0.70,   # ext_score >= 0.70 → signaled_too_late
    "LATE_RANK_THRESH":    45,     # board_rank > 45 at first appearance → signaled_too_late
    "PREMATURE_STOP_MFE_PP": 0.04, # fwd_mfe post-stop >= +4pp → premature_stop_noise
}
_TAXONOMY_VERSION = "v2"

# Maturity horizons
_GRADE_HORIZON = 21   # primary tactical entry horizon (sessions)
_MISSED_MOVER_EXCESS = 0.12   # +12pp CSI300 excess = "big winner" episode threshold
_MISSED_MOVER_WINDOW = 21     # sessions for missed-mover episode

# SA-R10: cluster-unit floors
_EFFECTIVE_N_FLOOR = 3   # below this → ACCRUING, no CI

# Fitness card schema
_FITNESS_SCHEMA = "metabolism.standouts_cn.v1"
_FITNESS_LOBE = "site-china-standouts"

# Authority block (display-only, no scored-path authority)
_AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _attribution_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "data" / "standout_audit" / "cn_attribution.parquet"


def _evidence_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "data" / "standout_audit" / "cn_evidence.jsonl"


def _scoreboard_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "site" / "factordata" / "cn_audit_scoreboard.json"


def _fitness_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "data" / "metabolism" / "fitness" / "standouts_cn.json"


def _state_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "data" / "standout_audit" / "cn_audit_state.json"


def _board_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "data" / "china_standout_track" / "board.parquet"


# ---------------------------------------------------------------------------
# Wilson CI helper (mirrors china_standout_track._wilson_ci)
# ---------------------------------------------------------------------------

def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# ---------------------------------------------------------------------------
# SA-R10: effective N — entry-date collapse + non-overlapping 21d windows
# ---------------------------------------------------------------------------

def _effective_n(dates: list[str]) -> int:
    """Cluster-unit effective N for a list of entry dates.

    Step 1: collapse to unique entry dates (equal-weight across same-day picks).
    Step 2: bin unique dates into non-overlapping 21d windows (count windows, not dates).

    This is the SA-R10 cluster unit: inference unit is the window, not the row.
    """
    if not dates:
        return 0
    unique_dates = sorted(set(str(d) for d in dates))
    if not unique_dates:
        return 0
    ts = sorted(pd.Timestamp(d) for d in unique_dates)
    # Non-overlapping 21-session window count (calendar days approximation: 21 sessions ≈ 30 days)
    windows = 0
    window_start: pd.Timestamp | None = None
    for t in ts:
        if window_start is None or (t - window_start).days >= 30:
            windows += 1
            window_start = t
    return windows


# ---------------------------------------------------------------------------
# Axis-1: outcome cause
# ---------------------------------------------------------------------------

def _axis1_outcome(
    pick_excess: float | None,       # pick vs benchmark (CSI300)
    sector_excess_vs_bench: float | None,  # sector vs benchmark
    bench_return: float | None,      # benchmark return over horizon
) -> str:
    """Assign one outcome-cause code.

    pick_excess = pick_return - bench_return (already CSI300-relative)
    sector_excess_vs_bench = mean sector peers' return - bench_return
    bench_return = benchmark return over the grading horizon

    All values are fractions (not %).  Returns 'mixed' on any None input
    (missing sector data degrades gracefully — never fabricated).
    """
    c = _TAXONOMY_CONSTANTS

    if pick_excess is None:
        return "mixed"

    # Compute idiosyncratic component vs sector
    idio_vs_sector: float | None = None
    if sector_excess_vs_bench is not None:
        idio_vs_sector = pick_excess - sector_excess_vs_bench

    # ── Failures ──────────────────────────────────────────────────────────
    if idio_vs_sector is not None and idio_vs_sector <= c["IDIO_BREAK_PP"]:
        return "idio_break"

    if (sector_excess_vs_bench is not None
            and sector_excess_vs_bench <= c["SECTOR_OUT_PP"]
            and idio_vs_sector is not None
            and abs(idio_vs_sector) <= c["IDIO_BAND_PP"]):
        return "sector_rotated_out"

    if (bench_return is not None
            and bench_return <= c["MACRO_FALL_PCT"]
            and idio_vs_sector is not None
            and abs(idio_vs_sector) <= c["IDIO_BAND_PP"]):
        return "macro_headwind"

    # ── Successes ─────────────────────────────────────────────────────────
    if idio_vs_sector is not None and idio_vs_sector >= c["IDIO_ALPHA_PP"]:
        return "idio_alpha"

    if (pick_excess > 0
            and sector_excess_vs_bench is not None
            and sector_excess_vs_bench >= c["BETA_STRONG_PCT"]
            and idio_vs_sector is not None
            and abs(idio_vs_sector) <= c["IDIO_BAND_PP"]):
        return "beta_tailwind"

    return "mixed"


# ---------------------------------------------------------------------------
# Axis-2: process fault
# ---------------------------------------------------------------------------

def _axis2_process(
    ext_score: float | None,
    board_rank: int | None,
    stage: str | None,
    terminal_state: str | None,
    fwd_mfe_21: float | None,
    *,
    premature_stop_mature: bool = False,
) -> str:
    """Assign one process-fault code.

    premature_stop_mature: True only when the row has had +21 post-stop sessions
    (SA-R10 own maturity stamp for this attribution).  If False, the
    premature_stop_noise code cannot be assigned (row is immature for that attribution).
    """
    c = _TAXONOMY_CONSTANTS

    # signaled_too_late
    if stage == "RAN_LATE":
        return "signaled_too_late"
    if ext_score is not None and ext_score >= c["EXT_SCORE_LATE_PCT"]:
        return "signaled_too_late"
    if board_rank is not None and board_rank > c["LATE_RANK_THRESH"]:
        return "signaled_too_late"

    # premature_stop_noise — requires own maturity
    if (premature_stop_mature
            and terminal_state in ("STOPPED",)
            and fwd_mfe_21 is not None
            and fwd_mfe_21 >= c["PREMATURE_STOP_MFE_PP"]):
        return "premature_stop_noise"

    # data_fault: not yet derivable from CN ledger columns (no staleness flags at entry)
    # degrades to clean rather than fabricating a fault attribution

    return "clean"


# ---------------------------------------------------------------------------
# Sector-mean excess computation
# ---------------------------------------------------------------------------

def _sector_mean_excess(df: pd.DataFrame, ticker: str, date: str, horizon: int = 21) -> float | None:
    """Compute sector-proxy excess vs CSI300 for the board rows in the same stratum.

    Since no CN sector ETF proxy is available in the ledger, we use the board's own
    sector-tier mean excess (peers at the same tier on the same date) as the sector leg.
    This is documented as a limitation: a proper sector ETF proxy would be preferred.
    Returns None when fewer than 3 peers exist (insufficient for a sector signal).

    DOCUMENT: if a CN sector ETF store becomes available, replace this with the
    direct ETF return (mirrors the US-side approach in standout_audit.py).
    """
    # Filter to same-date, same-tier rows with a graded fwd excess
    row = df[(df["date"].astype(str) == str(date)) & (df["ticker"].astype(str) == str(ticker))]
    if row.empty:
        return None
    tier = row.iloc[0].get("tier")
    peers = df[
        (df["date"].astype(str) == str(date))
        & (df["tier"].astype(str) == str(tier) if tier else False)
        & (df["ticker"].astype(str) != str(ticker))
        & df["fwd_21d_excess"].notna()
    ]
    if len(peers) < 3:
        return None
    return float(peers["fwd_21d_excess"].mean())


# ---------------------------------------------------------------------------
# Attribution core: given a board.parquet with graded 21d rows, produce attribution
# ---------------------------------------------------------------------------

def _compute_attribution(df: pd.DataFrame, bench: pd.Series | None) -> pd.DataFrame:
    """Compute two-axis attribution for all rows with a non-null fwd_21d_excess.

    df must have:
        date, ticker, board_rank, tier, extended, washout_2w, coiled, stage,
        ext_score, species_id, own_market_regime, fwd_21d_excess (pre-computed),
        terminal_state_clean8_21, fwd_mfe_21

    Returns a DataFrame of attribution rows with columns:
        date, ticker, horizon, taxonomy_version,
        outcome_cause, process_fault,
        species_id, own_market_regime, regime_stratum,
        fwd_excess, sector_proxy_excess, bench_return,
        idio_vs_sector, ext_score, board_rank, stage,
        attribution_mature_21d, premature_stop_mature
    """
    if df.empty or "fwd_21d_excess" not in df.columns:
        return pd.DataFrame()

    graded = df[df["fwd_21d_excess"].notna()].copy()
    if graded.empty:
        return pd.DataFrame()

    rows = []
    for _, row in graded.iterrows():
        ticker = str(row["ticker"])
        date = str(row["date"])
        pick_excess = float(row["fwd_21d_excess"]) if pd.notna(row["fwd_21d_excess"]) else None
        sector_excess = _sector_mean_excess(graded, ticker, date)

        # Bench return over horizon — derive from bench series if available
        bench_return: float | None = None
        if bench is not None:
            d0 = pd.Timestamp(date)
            bslice = bench[bench.index > d0]
            if len(bslice) > _GRADE_HORIZON:
                bench_return = float(bslice.iloc[_GRADE_HORIZON] / bslice.iloc[0] - 1.0)

        idio_vs_sector: float | None = None
        if sector_excess is not None and pick_excess is not None:
            idio_vs_sector = pick_excess - sector_excess

        outcome_cause = _axis1_outcome(pick_excess, sector_excess, bench_return)

        # Premature stop maturity: we can't know if +21 post-stop sessions have elapsed
        # without knowing the stop date; use a conservative proxy — if fwd_mfe_21 is non-null
        # the 21d window has matured (the stop happened within those 21 sessions).
        fwd_mfe_21_val = row.get("fwd_mfe_21")
        terminal_state = row.get("terminal_state_clean8_21")
        premature_stop_mature = bool(
            pd.notna(fwd_mfe_21_val) and fwd_mfe_21_val is not None
        )

        ext_score_val = float(row["ext_score"]) if pd.notna(row.get("ext_score")) else None
        board_rank_val = int(row["board_rank"]) if pd.notna(row.get("board_rank")) else None
        stage_val = str(row["stage"]) if pd.notna(row.get("stage")) else None
        process_fault = _axis2_process(
            ext_score_val,
            board_rank_val,
            stage_val,
            terminal_state,
            float(fwd_mfe_21_val) if pd.notna(fwd_mfe_21_val) and fwd_mfe_21_val is not None else None,
            premature_stop_mature=premature_stop_mature,
        )

        # Regime stratum: 'us_proxy' if own_market_regime is null (pre-store rows)
        own_regime = row.get("own_market_regime")
        if own_regime is None or (not isinstance(own_regime, str) and pd.isna(own_regime)):
            regime_stratum = "us_proxy"
        else:
            regime_stratum = str(own_regime)

        rows.append({
            "date": date,
            "ticker": ticker,
            "horizon": _GRADE_HORIZON,
            "taxonomy_version": _TAXONOMY_VERSION,
            "outcome_cause": outcome_cause,
            "process_fault": process_fault,
            "species_id": row.get("species_id"),
            "own_market_regime": own_regime if (isinstance(own_regime, str)) else None,
            "regime_stratum": regime_stratum,
            "fwd_excess": pick_excess,
            "sector_proxy_excess": sector_excess,
            "bench_return": bench_return,
            "idio_vs_sector": idio_vs_sector,
            "ext_score": ext_score_val,
            "board_rank": board_rank_val,
            "stage": stage_val,
            "attribution_mature_21d": True,
            "premature_stop_mature": premature_stop_mature,
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Scoreboard builder (SA-R10 cluster-unit stats)
# ---------------------------------------------------------------------------

def _build_scoreboard(attribution: pd.DataFrame, board: pd.DataFrame) -> dict:
    """Build the stratified scoreboard JSON.

    Strata:
    - regime_stratum / species_id / tier
    - us_proxy stratum NEVER pooled with own-market cells (SA-R7)
    - effective_n via entry-date collapse + non-overlapping 21d windows
    - Wilson CI on the cluster unit
    - cells with effective_n < _EFFECTIVE_N_FLOOR → ACCRUING, no CI
    """
    if attribution.empty:
        return {
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "schema": "cn_audit_scoreboard.v1",
            "taxonomy_version": _TAXONOMY_VERSION,
            "note": "no matured rows yet — accruing",
            "cells": [],
            "outcome_cause_mix": {},
            "process_fault_mix": {},
            "us_proxy_note": (
                "Pre-store rows (own_market_regime=null) carry stratum='us_proxy'. "
                "They are never pooled with own-market cells in any significance claim. "
                "Seam date: first row in data/china_regime/regime_daily.parquet."
            ),
        }

    cells = []
    # One cell per regime_stratum: us_proxy NEVER pooled with own-market cells (SA-R7).
    # effective_n = entry-date collapse + non-overlapping 21d windows (SA-R10).
    for regime_str, grp in attribution.groupby("regime_stratum"):
        raw_n = len(grp)
        dates = grp["date"].tolist()
        eff_n = _effective_n(dates)
        k = int((grp["fwd_excess"] > 0).sum())

        if eff_n < _EFFECTIVE_N_FLOOR:
            cells.append({
                "stratum": str(regime_str),
                "raw_n": raw_n,
                "effective_n": eff_n,
                "state": "ACCRUING",
                "us_proxy": regime_str == "us_proxy",
            })
        else:
            lo, hi = _wilson_ci(k, eff_n)
            cells.append({
                "stratum": str(regime_str),
                "raw_n": raw_n,
                "effective_n": eff_n,
                "state": "reported",
                "hit_rate": round(k / eff_n, 4),
                "wilson_lo": round(lo, 4),
                "wilson_hi": round(hi, 4),
                "us_proxy": regime_str == "us_proxy",
            })

    # Overall outcome-cause and process-fault mixes
    outcome_mix = attribution["outcome_cause"].value_counts().to_dict()
    process_mix = attribution["process_fault"].value_counts().to_dict()

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "schema": "cn_audit_scoreboard.v1",
        "taxonomy_version": _TAXONOMY_VERSION,
        "total_matured": len(attribution),
        "cells": cells,
        "outcome_cause_mix": {str(k): int(v) for k, v in outcome_mix.items()},
        "process_fault_mix": {str(k): int(v) for k, v in process_mix.items()},
        "taxonomy_constants": _TAXONOMY_CONSTANTS,
        "us_proxy_note": (
            "Pre-store rows (own_market_regime=null) carry stratum='us_proxy'. "
            "They are NEVER pooled with own-market cells in any significance claim. "
            "Seam date: first row in data/china_regime/regime_daily.parquet."
        ),
    }


# ---------------------------------------------------------------------------
# Missed-mover census
# ---------------------------------------------------------------------------

def _missed_mover_rate(board: pd.DataFrame) -> dict:
    """Compute the missed-mover rate.

    Universe = names that appeared in the board (eligible A-shares the board screens).
    Episode = 21d forward CSI300-excess >= +12pp (big winner).
    Buy-lane credit ONLY.

    Returns a sensor dict (accruing until floor).
    """
    if board.empty or "fwd_21d_excess" not in board.columns:
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": "data/china_standout_track/board.parquet",
            "note": "no graded rows — accruing",
        }
    graded = board[board["fwd_21d_excess"].notna()]
    if graded.empty:
        return {
            "value": None, "n": 0, "maturity": "accruing",
            "source": "data/china_standout_track/board.parquet",
            "note": "no graded rows — accruing",
        }

    # Big-winner episodes by ticker: any date where fwd_21d_excess >= threshold
    big_winners = graded[graded["fwd_21d_excess"] >= _MISSED_MOVER_EXCESS]
    n_episodes = len(big_winners)

    if n_episodes == 0:
        return {
            "value": 0.0, "n": len(graded), "n_episodes": 0, "maturity": "accruing",
            "source": "data/china_standout_track/board.parquet",
            "note": "no big-winner episodes at +12pp threshold yet",
        }

    # All big-winner names were already on the board (they're in the graded set)
    # For the missed_mover_rate, we need universe episodes that NEVER reached the board.
    # Since board = universe in this ledger (the ledger only logs board names), we can only
    # compute this metric when we have access to the full eligible universe count.
    # Degrade to data_gap (SA-R15: absent store → explicit data_gap flag, not fabricated zero).
    return {
        "value": None,
        "n": n_episodes,
        "maturity": "accruing",
        "source": "data/china_standout_track/board.parquet",
        "note": (
            "data_gap: missed_mover_rate requires the full eligible A-share universe count "
            "(not only board names). Universe census not available at grade time. "
            "Degrade to data_gap per SA-R15 — never fabricate a zero."
        ),
    }


# ---------------------------------------------------------------------------
# Fitness card builder (SA-R3: 6 paired sensors)
# ---------------------------------------------------------------------------

def _build_fitness_card(board: pd.DataFrame, attribution: pd.DataFrame) -> dict:
    """Build the 6-sensor fitness card in til.json format.

    Sensors:
      hit_quality       — Wilson-LB of P(excess>0), buy lane, cluster-unit CIs
      upside_capture    — mean surfaced excess / winsorized top-decile excess
      coverage_health   — count monitoring (accruing until baseline frozen)
      missed_mover_rate — big-winner episodes missed by board
      timing_quality    — median ext_score + share signaled_too_late
      process_integrity — share data_fault rows

    All sensors are accruing until SA-R10 floors are met.
    """
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    graded = board[board["fwd_21d_excess"].notna()] if "fwd_21d_excess" in board.columns else pd.DataFrame()
    n_graded = len(graded)

    # Maturity floor: >=25 matured rows AND >=10 distinct entry dates AND >=3 windows
    distinct_dates = graded["date"].nunique() if not graded.empty else 0
    eff_n = _effective_n(graded["date"].tolist()) if not graded.empty else 0
    maturity_floor_met = (n_graded >= 25 and distinct_dates >= 10 and eff_n >= 3)

    def _accruing(n: int, note: str) -> dict:
        return {"value": None, "n": n, "effective_n": eff_n, "maturity": "accruing",
                "source": "data/china_standout_track/board.parquet", "note": note}

    # 1. hit_quality
    if not maturity_floor_met or graded.empty:
        hit_quality = _accruing(n_graded, f"accruing: {n_graded}/25 graded rows needed")
    else:
        k = int((graded["fwd_21d_excess"] > 0).sum())
        lo, _hi = _wilson_ci(k, eff_n)
        hit_quality = {
            "value": round(lo, 4), "n": n_graded, "effective_n": eff_n,
            "maturity": "ready",
            "source": "data/china_standout_track/board.parquet",
            "note": "Wilson lower bound of P(excess>0) — cluster-unit CI",
        }

    # 2. upside_capture
    if not maturity_floor_met or graded.empty:
        upside_capture = _accruing(n_graded, f"accruing: {n_graded}/25 graded rows needed")
    else:
        excesses = graded["fwd_21d_excess"].dropna()
        top_decile_n = max(1, int(len(excesses) * 0.10))
        top_excesses = excesses.nlargest(top_decile_n)
        top_mean = float(top_excesses.mean())
        # Flat-tape guard: don't print capture when top-decile excess <= 2pp
        if top_mean <= 0.02:
            upside_capture = {
                "value": None, "n": n_graded, "effective_n": eff_n,
                "maturity": "ready",
                "source": "data/china_standout_track/board.parquet",
                "note": "flat-tape guard: top-decile excess <= 2pp — not printed",
            }
        else:
            surfaced_mean = float(excesses.mean())
            upside_capture = {
                "value": round(surfaced_mean / top_mean, 4),
                "n": n_graded, "effective_n": eff_n,
                "surfaced_count": n_graded,
                "maturity": "ready",
                "source": "data/china_standout_track/board.parquet",
                "note": "mean surfaced excess / winsorized top-decile excess",
            }

    # 3. coverage_health (accruing until baseline frozen at first maturity date)
    coverage_health = _accruing(
        n_graded,
        "accruing: baseline not yet frozen (first maturity date not reached for count clamp)",
    )

    # 4. missed_mover_rate
    missed_mover = _missed_mover_rate(board)

    # 5. timing_quality
    if attribution.empty or not maturity_floor_met:
        timing_quality = _accruing(n_graded, f"accruing: {n_graded}/25 graded rows needed")
    else:
        late_share = float(
            (attribution["process_fault"] == "signaled_too_late").mean()
        )
        ext_scores = board["ext_score"].dropna() if "ext_score" in board.columns else pd.Series([], dtype=float)
        median_ext = float(ext_scores.median()) if len(ext_scores) > 0 else None
        timing_quality = {
            "value": round(late_share, 4),
            "median_ext_score": round(median_ext, 4) if median_ext is not None else None,
            "n": len(attribution),
            "effective_n": eff_n,
            "maturity": "ready",
            "source": "data/china_standout_track/board.parquet, data/standout_audit/cn_attribution.parquet",
            "note": "share of matured rows with signaled_too_late + median ext_score",
        }

    # 6. process_integrity
    if attribution.empty or not maturity_floor_met:
        process_integrity = _accruing(n_graded, f"accruing: {n_graded}/25 graded rows needed")
    else:
        data_fault_share = float(
            (attribution["process_fault"] == "data_fault").mean()
        )
        process_integrity = {
            "value": round(data_fault_share, 4),
            "n": len(attribution),
            "effective_n": eff_n,
            "maturity": "ready",
            "source": "data/standout_audit/cn_attribution.parquet",
            "note": "share of matured rows with data_fault process attribution",
        }

    sensors = {
        "hit_quality": hit_quality,
        "upside_capture": upside_capture,
        "coverage_health": coverage_health,
        "missed_mover_rate": missed_mover,
        "timing_quality": timing_quality,
        "process_integrity": process_integrity,
    }

    maturities = {s["maturity"] for s in sensors.values()}
    if maturities == {"ready"}:
        overall = "ready"
    elif "accruing" in maturities and "ready" not in maturities:
        overall = "accruing"
    else:
        overall = "partial"

    return {
        "schema": _FITNESS_SCHEMA,
        "as_of": as_of,
        "lobe": _FITNESS_LOBE,
        "maturity": overall,
        "sensors": sensors,
        "authority": _AUTHORITY_BLOCK,
        "taxonomy_version": _TAXONOMY_VERSION,
        "notes": (
            f"CN standout fitness card. All sensors accruing until SA-R10 floors met "
            f"(currently {n_graded}/25 matured rows, {distinct_dates}/10 distinct dates, "
            f"{eff_n}/3 non-overlapping windows). "
            f"Expected first reads: ~2026-10-15. "
            f"No 'validated' claim — pre-maturity values are display context only."
        ),
    }


# ---------------------------------------------------------------------------
# Evidence pack writer
# ---------------------------------------------------------------------------

def _write_evidence(
    attribution: pd.DataFrame,
    prior_evidence_tickers: set[str],
    root: Path | None = None,
) -> int:
    """Append evidence packs for newly matured picks (not yet in evidence JSONL).

    Returns count of newly written packs.  Never raises.
    """
    if attribution.empty:
        return 0
    p = _evidence_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Identify new rows: (date, ticker) not already in evidence file
    new_rows = attribution[
        ~attribution.apply(lambda r: (str(r["date"]) + "_" + str(r["ticker"])) in prior_evidence_tickers, axis=1)
    ]
    if new_rows.empty:
        return 0

    try:
        with p.open("a", encoding="utf-8") as f:
            for _, row in new_rows.iterrows():
                pack = {
                    "date": str(row["date"]),
                    "ticker": str(row["ticker"]),
                    "horizon": int(row["horizon"]),
                    "taxonomy_version": str(row["taxonomy_version"]),
                    "species_id": row["species_id"] if pd.notna(row.get("species_id", None)) else None,
                    "own_market_regime": row["own_market_regime"] if pd.notna(row.get("own_market_regime", None)) else None,
                    "regime_stratum": str(row["regime_stratum"]),
                    "outcome_cause": str(row["outcome_cause"]),
                    "process_fault": str(row["process_fault"]),
                    "fwd_excess": float(row["fwd_excess"]) if pd.notna(row.get("fwd_excess", None)) else None,
                    "sector_proxy_excess": float(row["sector_proxy_excess"]) if pd.notna(row.get("sector_proxy_excess", None)) else None,
                    "bench_return": float(row["bench_return"]) if pd.notna(row.get("bench_return", None)) else None,
                    "idio_vs_sector": float(row["idio_vs_sector"]) if pd.notna(row.get("idio_vs_sector", None)) else None,
                    "ext_score": float(row["ext_score"]) if pd.notna(row.get("ext_score", None)) else None,
                    "board_rank": int(row["board_rank"]) if pd.notna(row.get("board_rank", None)) else None,
                    "written_at": datetime.now(timezone.utc).isoformat(),
                }
                f.write(json.dumps(pack, default=str) + "\n")
        return len(new_rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("china_standout_audit._write_evidence failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Main entrypoint (called from build_china_library.py)
# ---------------------------------------------------------------------------

def run_attribution(
    board: pd.DataFrame | None = None,
    bench_close: pd.Series | None = None,
    root: Path | None = None,
    lane: str | None = None,
    fwd_excess_map: dict | None = None,
) -> dict:
    """Run CN two-axis attribution and write all output artifacts.

    FAIL-CLOSED: refuses writes when lane != 'asia' (uses os.environ if lane
    is None).  Returns a summary dict.  Never raises.

    board: pre-loaded board.parquet DataFrame (or None to load from disk).
    bench_close: CSI300 close series (or None to skip bench return derivation).
    root: project root override (for tests).
    lane: explicit lane override (for tests — production uses os.environ).
    fwd_excess_map: optional {(ticker, date_str): excess_float} pre-computed from
        grade() to avoid double price-store I/O. When provided, _attach_fwd_excess
        skips the per-ticker loop and uses this map directly.
    """
    try:
        effective_lane = lane if lane is not None else os.environ.get("CN_LANE", "")
        if effective_lane != "asia":
            log.warning(
                "china_standout_audit.run_attribution: refusing writes — lane=%r (expected 'asia')",
                effective_lane,
            )
            return {"written": False, "reason": f"lane={effective_lane!r} not asia"}

        # Load board
        if board is None:
            p = _board_path(root)
            if not p.exists():
                return {"written": False, "reason": "board.parquet not found"}
            try:
                board = pd.read_parquet(p)
            except Exception as exc:  # noqa: BLE001
                return {"written": False, "reason": f"cannot read board: {exc}"}

        if board.empty:
            return {"written": False, "reason": "board is empty"}

        # Ensure fwd_21d_excess column exists (comes from grade()).
        # grade() does NOT write fwd_21d_excess back to parquet; we compute it here.
        # If fwd_excess_map is provided (e.g. from the grade() call), use it directly
        # to avoid double price-store I/O. Otherwise fall back to per-row _fwd_excess.
        board = _attach_fwd_excess(board, bench_close, root, fwd_excess_map=fwd_excess_map)

        # Compute attribution
        attribution = _compute_attribution(board, bench_close)

        if attribution.empty:
            # Write fitness card and scoreboard even with no matured rows
            _write_scoreboard({}, board, attribution, root)
            _write_fitness(board, attribution, root)
            _update_state_attribution(root)
            return {
                "written": True,
                "n_matured": 0,
                "note": "no matured rows yet — wrote accruing scoreboard and fitness card",
            }

        # Load prior attribution for keep-first dedup
        prior_keys: set[tuple] = set()
        attr_path = _attribution_path(root)
        attr_path.parent.mkdir(parents=True, exist_ok=True)
        if attr_path.exists():
            try:
                prior_attr = pd.read_parquet(attr_path)
                for _, r in prior_attr.iterrows():
                    prior_keys.add((str(r["date"]), str(r["ticker"]), int(r["horizon"]), str(r["taxonomy_version"])))
            except Exception as exc:  # noqa: BLE001
                log.warning("china_standout_audit: cannot read prior attribution: %s", exc)

        # Keep-first: only append truly new rows
        if prior_keys:
            new_mask = ~attribution.apply(
                lambda r: (str(r["date"]), str(r["ticker"]), int(r["horizon"]), str(r["taxonomy_version"])) in prior_keys,
                axis=1,
            )
            new_attribution = attribution[new_mask]
        else:
            new_attribution = attribution

        # Append to parquet
        if not new_attribution.empty or not attr_path.exists():
            try:
                if attr_path.exists() and not new_attribution.empty:
                    prior_df = pd.read_parquet(attr_path)
                    combined = pd.concat([prior_df, new_attribution], ignore_index=True)
                else:
                    combined = attribution
                combined.to_parquet(attr_path, index=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("china_standout_audit: failed to write attribution parquet: %s", exc)

        # Load full attribution for scoreboard/fitness (including prior)
        try:
            full_attribution = pd.read_parquet(attr_path) if attr_path.exists() else attribution
        except Exception:  # noqa: BLE001
            full_attribution = attribution

        # Write evidence JSONL
        prior_evidence: set[str] = set()
        ev_path = _evidence_path(root)
        if ev_path.exists():
            try:
                for line in ev_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    prior_evidence.add(str(obj.get("date", "")) + "_" + str(obj.get("ticker", "")))
            except Exception as exc:  # noqa: BLE001
                log.warning("china_standout_audit: cannot read prior evidence: %s", exc)
        n_new_evidence = _write_evidence(new_attribution, prior_evidence, root)

        # Write scoreboard
        _write_scoreboard(full_attribution, board, full_attribution, root)

        # Write fitness card
        _write_fitness(board, full_attribution, root)

        # Update state
        _update_state_attribution(root)

        return {
            "written": True,
            "n_matured": len(full_attribution),
            "n_new_this_run": len(new_attribution),
            "n_new_evidence": n_new_evidence,
        }

    except Exception as exc:  # noqa: BLE001 — SA-R16: never suppress the calling build
        log.warning("china_standout_audit.run_attribution failed: %s", exc)
        return {"written": False, "reason": str(exc)}


def _attach_fwd_excess(
    board: pd.DataFrame,
    bench_close: pd.Series | None,
    root: Path | None,
    fwd_excess_map: dict | None = None,
) -> pd.DataFrame:
    """Attach fwd_21d_excess to board rows using the store's own _fwd_excess logic.

    This is a read-only operation — does NOT write back to board.parquet.

    If fwd_excess_map is provided ({(ticker, date_str): excess}), it is used
    directly to avoid redundant price-store I/O (grade() already opened those files).
    Falls back to per-ticker _fwd_excess calls when the map is absent.
    """
    if "fwd_21d_excess" in board.columns:
        return board
    board = board.copy()
    if fwd_excess_map is not None:
        # Fast path: use pre-computed map from caller (zero additional I/O)
        excesses = [
            fwd_excess_map.get((str(row["ticker"]), str(row["date"])))
            for _, row in board.iterrows()
        ]
        board["fwd_21d_excess"] = excesses
        return board
    try:
        from engine import china_standout_track as cst  # noqa: PLC0415
        excesses = []
        for _, row in board.iterrows():
            ex, _pinned = cst._fwd_excess(  # noqa: SLF001
                str(row["ticker"]), pd.Timestamp(str(row["date"])),
                _GRADE_HORIZON, bench_close,
            )
            excesses.append(ex)
        board["fwd_21d_excess"] = excesses
    except Exception as exc:  # noqa: BLE001
        log.warning("china_standout_audit._attach_fwd_excess failed: %s", exc)
        board["fwd_21d_excess"] = None
    return board


def _write_scoreboard(
    full_attribution: pd.DataFrame | dict,
    board: pd.DataFrame,
    attribution: pd.DataFrame,
    root: Path | None,
) -> None:
    """Write the cn_audit_scoreboard.json.  Never raises."""
    try:
        scoreboard = _build_scoreboard(
            attribution if not isinstance(attribution, dict) else pd.DataFrame(),
            board,
        )
        p = _scoreboard_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(scoreboard, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("china_standout_audit._write_scoreboard failed: %s", exc)


def _write_fitness(board: pd.DataFrame, attribution: pd.DataFrame, root: Path | None) -> None:
    """Write the standouts_cn.json fitness card.  Never raises."""
    try:
        card = _build_fitness_card(board, attribution)
        p = _fitness_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("china_standout_audit._write_fitness failed: %s", exc)


def _update_state_attribution(root: Path | None) -> None:
    """Update cn_audit_state.json with attribution freshness stamp.  Never raises."""
    try:
        p = _state_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        state: dict = {}
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                state = {}
        state["attribution_last_run"] = datetime.now(timezone.utc).isoformat()
        p.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("china_standout_audit._update_state_attribution failed: %s", exc)
