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
    idio_break              excess vs peer_board_deviation <= IDIO_BREAK_PP
    peer_board_deviation    (secondary context flag — within-board relative strength vs
                             same-tier peers; honest name: NOT a sector proxy)
    sector_rotated_out      DEGRADED: 'mixed' with note 'no_sector_leg' until a genuine
                             industry/sector grouping column is available in the ledger.
                             Peer-board deviation is self-referential by construction and
                             cannot detect sector rotation (F3 adjudicated ruling).
    macro_headwind          benchmark <= MACRO_FALL_PCT over horizon
                             AND pick idio within ±IDIO_BAND_PP of peer deviation
    idio_alpha              excess vs peer deviation >= IDIO_ALPHA_PP
    beta_tailwind           DEGRADED: 'mixed' with note 'no_sector_leg' — same rationale
                             as sector_rotated_out (no genuine sector proxy available).
    mixed                   residual (nothing tiles)

  Precedence (failure): idio_break > macro_headwind
  Precedence (success): idio_alpha

  Axis 2 (process fault):
    signaled_too_late   ticks > FRESH_TICKS (confluence_tiers.FRESH_TICKS=2) when ticks
                        is non-null; OR ext_score >= ext_score 85th-percentile threshold
                        (EXT_SCORE_LATE_PCT=0.70 legacy fallback).  timing_basis field
                        lists which clauses are live for each row.
    gate_suppressed     near-miss not implemented yet — degrades to clean
    premature_stop_noise  UNIMPLEMENTED — requires a stop-date column + post-stop window
                          not derivable from the current ledger (PREMATURE_STOP_IMPLEMENTED=False).
                          CN rows never emit this code.  The fitness card carries an
                          'unimplemented' note for this axis-2 code.
    data_fault          staleness flags at entry (not yet available in CN ledger — data_gap)
    clean               default

See SA-R2: thresholds in _TAXONOMY_CONSTANTS block; taxonomy_version='v2'.
SA-W2 review fixes applied: F1 sequencing, F2 window-unit Wilson, F3 peer-board rename +
honest sector degrade, F4 missed-mover None on zero episodes, F5 premature-stop stub,
F6 ticks-based timing, F7 fwd_excess_map plumbing.
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
    "IDIO_BREAK_PP":      -0.04,   # excess vs peer_board_deviation <= -4pp → idio_break
    "IDIO_ALPHA_PP":      +0.04,   # excess vs peer_board_deviation >= +4pp → idio_alpha
    "IDIO_BAND_PP":        0.02,   # ±2pp idio-within-peer band
    # F3: SECTOR_OUT_PP and BETA_STRONG_PCT are defined but NOT used for outcome assignment
    # until a genuine industry/sector grouping column is available in the ledger.
    # sector_rotated_out and beta_tailwind degrade to 'mixed' with note 'no_sector_leg'.
    "SECTOR_OUT_PP":      -0.025,  # reserved — not used until sector_leg available
    "MACRO_FALL_PCT":     -0.03,   # benchmark return <= -3% → macro_headwind
    "BETA_STRONG_PCT":    +0.02,   # reserved — not used until sector_leg available
    # Axis-2 thresholds
    # F6: signaled_too_late is based on ticks > FRESH_TICKS (primary) or ext_score (fallback).
    # FRESH_TICKS = 2 (from confluence_tiers; a cross is fresh only while <= 2 ticks old).
    # EXT_SCORE_LATE_PCT is retained as a fallback for rows where ticks is null.
    "FRESH_TICKS":         2,      # ticks > 2 on own TF → cross aged, signaled_too_late
    "EXT_SCORE_LATE_PCT":  0.70,   # ext_score >= 0.70 → signaled_too_late (fallback when ticks null)
    # F5: PREMATURE_STOP_IMPLEMENTED=False.  The ledger has no stop-date column, so there is no
    # post-stop window to measure.  Detecting 'stopped AND peaked somewhere in the same 21-session
    # entry window' is NOT the same construct.  This code is stubbed until a stop-date column exists.
    "PREMATURE_STOP_MFE_PP": 0.04, # threshold reserved for future implementation
}
_TAXONOMY_VERSION = "v2"

# F3: no genuine sector/industry grouping in the current ledger.
# narr_theme is a basket display name, not an industry classification; it is 89% null.
# tier is a rank-quality band (T1-T4), not a sector.
# Until a real sector store lands, sector_rotated_out and beta_tailwind emit 'mixed'
# with note 'no_sector_leg'.  peer_board_deviation (same-tier mean excess) is retained
# as a secondary context flag (honest within-board relative strength), NOT as a sector proxy.
_NO_SECTOR_LEG_NOTE = (
    "no_sector_leg: sector_rotated_out/beta_tailwind require a genuine industry grouping "
    "column (e.g. CITIC level-1 industry). narr_theme is 89% null and is a basket theme, "
    "not an industry classification. tier is a rank-quality band, not a sector. "
    "Degrades to mixed until a real sector store is joinable at append time."
)

# F5: premature_stop_noise is NOT implemented in the CN ledger.
# Requires: stop-date column on the board row + post-stop return window.
# fwd_mfe_21 and terminal_state_clean8_21 are measured over the SAME 21-session entry
# window — detecting 'peaked somewhere AND ended stopped' is not the same as
# 'stopped AND then recovered'.  This code will never fire until the data model changes.
PREMATURE_STOP_IMPLEMENTED = False
_PREMATURE_STOP_NOTE = (
    "unimplemented: premature_stop_noise requires a stop-date column + post-stop window "
    "not derivable from the current ledger (fwd_mfe_21 and terminal_state_clean8_21 share "
    "the same 21-session entry window; no post-stop observation is possible). "
    "PREMATURE_STOP_IMPLEMENTED=False. CN rows never emit this code."
)

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
    """Wilson score confidence interval.

    F2 defensive guard: if k > n (units mismatch — e.g. row-count k vs window-count n)
    this would produce a negative variance → complex sqrt → TypeError.  Clamp and return
    an error sentinel (1.0, 0.0) so callers can detect the condition; never a complex.
    """
    if n <= 0:
        return 0.0, 0.0
    if k > n:
        # Sentinel: upper < lower signals caller that the input units are inconsistent.
        # This should never occur after the F2 window-unit collapse fix; retained as a
        # belt-and-suspenders guard so the function never raises.
        return 1.0, 0.0
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


def _window_unit_k(dates: list[str], outcome_positive: list[bool]) -> int:
    """SA-R10 F2 fix: collapse to window-level k for Wilson CI.

    For each non-overlapping 30-day window, compute the entry-date-collapsed mean
    excess positivity within that window.  k = number of windows where the mean
    excess is positive (mean > 0 across all entries whose dates fall in that window).

    This ensures k <= n (both are window counts) — _wilson_ci can never receive
    k > n from this function.

    dates: list of entry date strings (same length as outcome_positive)
    outcome_positive: per-row bool (True if fwd_excess > 0)

    Returns k (number of positive-mean windows) where 0 <= k <= _effective_n(dates).
    """
    if not dates:
        return 0
    pairs = list(zip(dates, outcome_positive))
    # Group by date first (equal-weight across same-day entries)
    date_means: dict[str, float] = {}
    date_groups: dict[str, list[bool]] = {}
    for d, pos in pairs:
        d = str(d)
        date_groups.setdefault(d, []).append(bool(pos))
    for d, vals in date_groups.items():
        date_means[d] = sum(vals) / len(vals)

    # Bin unique dates into non-overlapping 30-day windows; for each window compute mean positivity
    sorted_dates = sorted(date_means.keys())
    if not sorted_dates:
        return 0
    ts_list = [(pd.Timestamp(d), date_means[d]) for d in sorted_dates]
    k = 0
    window_start: pd.Timestamp | None = None
    window_vals: list[float] = []
    for t, mean_pos in ts_list:
        if window_start is None or (t - window_start).days >= 30:
            # Close out prior window
            if window_vals:
                if sum(window_vals) / len(window_vals) > 0:
                    k += 1
                window_vals = []
            window_start = t
        window_vals.append(mean_pos)
    # Close final window
    if window_vals:
        if sum(window_vals) / len(window_vals) > 0:
            k += 1
    return k


# ---------------------------------------------------------------------------
# Axis-1: outcome cause
# ---------------------------------------------------------------------------

def _axis1_outcome(
    pick_excess: float | None,              # pick vs benchmark (CSI300)
    peer_deviation_vs_bench: float | None,  # F3: peer_board_deviation (same-tier mean), NOT sector
    bench_return: float | None,             # benchmark return over horizon
) -> str:
    """Assign one outcome-cause code.

    pick_excess = pick_return - bench_return (already CSI300-relative)
    peer_deviation_vs_bench = mean same-tier board peer excess vs benchmark (context only, not sector)
    bench_return = benchmark return over the grading horizon

    F3 ADJUDICATED: sector_rotated_out and beta_tailwind are NOT assigned because no genuine
    industry/sector grouping is available (peer_deviation_vs_bench is same-TIER board peers,
    not a sector proxy — tier = rank-quality band, not industry).  Those branches degrade to
    'mixed' with the no_sector_leg note.  The idio_break, macro_headwind, and idio_alpha codes
    remain valid using peer_board_deviation as a secondary context proxy.

    All values are fractions (not %).  Returns 'mixed' on any None input
    (missing peer data degrades gracefully — never fabricated).
    """
    c = _TAXONOMY_CONSTANTS

    if pick_excess is None:
        return "mixed"

    # Compute idiosyncratic component vs peer deviation (context proxy, not sector)
    idio_vs_peer: float | None = None
    if peer_deviation_vs_bench is not None:
        idio_vs_peer = pick_excess - peer_deviation_vs_bench

    # ── Failures ──────────────────────────────────────────────────────────
    if idio_vs_peer is not None and idio_vs_peer <= c["IDIO_BREAK_PP"]:
        return "idio_break"

    # sector_rotated_out: SUPPRESSED — no genuine sector leg (F3 ruling)
    # Would require: genuine industry grouping column + >= 3 peers in that industry.
    # Degrades to 'mixed' (via the residual return below).

    if (bench_return is not None
            and bench_return <= c["MACRO_FALL_PCT"]
            and idio_vs_peer is not None
            and abs(idio_vs_peer) <= c["IDIO_BAND_PP"]):
        return "macro_headwind"

    # ── Successes ─────────────────────────────────────────────────────────
    if idio_vs_peer is not None and idio_vs_peer >= c["IDIO_ALPHA_PP"]:
        return "idio_alpha"

    # beta_tailwind: SUPPRESSED — no genuine sector leg (F3 ruling)
    # Would require: sector_excess_vs_bench from a real sector ETF/index (not board peers).
    # Degrades to 'mixed' (via the residual return below).

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
    ticks: float | None = None,
) -> tuple[str, list[str]]:
    """Assign one process-fault code and return (code, timing_basis).

    F5: premature_stop_noise is NEVER assigned (PREMATURE_STOP_IMPLEMENTED=False).
        Requires a stop-date column + post-stop window not available in the current ledger.
        The premature_stop_mature / terminal_state / fwd_mfe_21 parameters are retained
        for API stability and future use; they are not checked here.

    F6: signaled_too_late is based on:
        Primary: ticks > FRESH_TICKS (=2) when ticks is non-null.
        Fallback: ext_score >= EXT_SCORE_LATE_PCT (=0.70) when ticks is null.
        Legacy board_rank clause REMOVED (was a tenure proxy that mislabeled ~25% of board).
        timing_basis: list of the clauses that fired (for disclosure).

    stage == 'RAN_LATE' overrides both (lifecycle label is the most direct evidence).

    Returns (fault_code, timing_basis_list).
    """
    c = _TAXONOMY_CONSTANTS
    timing_basis: list[str] = []

    # signaled_too_late: stage override (most direct evidence)
    if stage == "RAN_LATE":
        timing_basis.append("stage==RAN_LATE")
        return "signaled_too_late", timing_basis

    # F6: primary — ticks-based (faithful: ticks-since-cross on the signal's own TF)
    if ticks is not None:
        timing_basis.append(f"ticks={ticks:.0f}>FRESH_TICKS={c['FRESH_TICKS']}")
        if ticks > c["FRESH_TICKS"]:
            return "signaled_too_late", timing_basis
    else:
        # F6: fallback — ext_score (covers rows where ticks is null)
        if ext_score is not None and ext_score >= c["EXT_SCORE_LATE_PCT"]:
            timing_basis.append(f"ext_score={ext_score:.3f}>=EXT_SCORE_LATE_PCT={c['EXT_SCORE_LATE_PCT']}")
            return "signaled_too_late", timing_basis
        timing_basis.append("ticks=null,ext_score_fallback")

    # F5: premature_stop_noise — UNIMPLEMENTED in CN; never fires
    # (kept as a no-op so callers that pass premature_stop_mature=True don't crash)
    if not PREMATURE_STOP_IMPLEMENTED:
        pass  # deliberately empty — see _PREMATURE_STOP_NOTE

    # data_fault: not yet derivable from CN ledger columns (no staleness flags at entry)
    # degrades to clean rather than fabricating a fault attribution

    return "clean", timing_basis


# ---------------------------------------------------------------------------
# Sector-mean excess computation
# ---------------------------------------------------------------------------

def _peer_board_deviation(df: pd.DataFrame, ticker: str, date: str, horizon: int = 21) -> float | None:
    """Compute within-board peer deviation: mean fwd excess of same-tier peers on the same date.

    F3 ADJUDICATED RULING: this is NOT a sector proxy.  The 'tier' column is a rank-quality
    band (T1-T4) derived from signal strength — it is NOT an industry or sector grouping.
    Peers are same-TIER board peers, not same-sector names.

    This function is retained as a secondary context flag (honest within-board relative
    strength) but is NEVER used to assign sector_rotated_out or beta_tailwind — those
    codes require a genuine industry/sector grouping column (see _NO_SECTOR_LEG_NOTE).

    Returns None when fewer than 3 peers exist (insufficient for a meaningful deviation).
    Returns None when tier is missing.

    When a genuine sector grouping is available (e.g. CITIC level-1 industry joined at
    append_board time as a new 'industry_group' column), replace this function with a
    direct industry-group mean excess (peers = same industry, >= 3 members).
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
        terminal_state_clean8_21, fwd_mfe_21, ticks (optional, for F6 timing)

    Returns a DataFrame of attribution rows with columns:
        date, ticker, horizon, taxonomy_version,
        outcome_cause, process_fault, timing_basis,
        species_id, own_market_regime, regime_stratum,
        fwd_excess, peer_board_deviation, bench_return,
        idio_vs_peer, ext_score, board_rank, ticks, stage,
        attribution_mature_21d, premature_stop_note,
        sector_note
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

        # F3: peer_board_deviation (NOT a sector proxy — secondary context flag only)
        peer_dev = _peer_board_deviation(graded, ticker, date)

        # Bench return over horizon — derive from bench series if available
        bench_return: float | None = None
        if bench is not None:
            d0 = pd.Timestamp(date)
            bslice = bench[bench.index > d0]
            if len(bslice) > _GRADE_HORIZON:
                bench_return = float(bslice.iloc[_GRADE_HORIZON] / bslice.iloc[0] - 1.0)

        idio_vs_peer: float | None = None
        if peer_dev is not None and pick_excess is not None:
            idio_vs_peer = pick_excess - peer_dev

        outcome_cause = _axis1_outcome(pick_excess, peer_dev, bench_return)

        fwd_mfe_21_val = row.get("fwd_mfe_21")
        terminal_state = row.get("terminal_state_clean8_21")

        ext_score_val = float(row["ext_score"]) if pd.notna(row.get("ext_score")) else None
        board_rank_val = int(row["board_rank"]) if pd.notna(row.get("board_rank")) else None
        stage_val = str(row["stage"]) if pd.notna(row.get("stage")) else None
        # F6: pass ticks for the primary timing clause
        ticks_val = float(row["ticks"]) if pd.notna(row.get("ticks")) else None
        process_fault, timing_basis = _axis2_process(
            ext_score_val,
            board_rank_val,
            stage_val,
            terminal_state,
            float(fwd_mfe_21_val) if pd.notna(fwd_mfe_21_val) and fwd_mfe_21_val is not None else None,
            ticks=ticks_val,
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
            "timing_basis": "|".join(timing_basis) if timing_basis else "",
            "species_id": row.get("species_id"),
            "own_market_regime": own_regime if (isinstance(own_regime, str)) else None,
            "regime_stratum": regime_stratum,
            "fwd_excess": pick_excess,
            # F3: renamed from sector_proxy_excess → peer_board_deviation; column name change
            "peer_board_deviation": peer_dev,
            "bench_return": bench_return,
            # F3: renamed from idio_vs_sector → idio_vs_peer
            "idio_vs_peer": idio_vs_peer,
            "ext_score": ext_score_val,
            "board_rank": board_rank_val,
            "ticks": ticks_val,
            "stage": stage_val,
            "attribution_mature_21d": True,
            # F5: premature_stop_noise never fires; carry the note for scoreboard transparency
            "premature_stop_note": _PREMATURE_STOP_NOTE,
            # F3: sector note for transparency
            "sector_note": _NO_SECTOR_LEG_NOTE,
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
    # F2 FIX: both k and n must be in WINDOW units (SA-R10).
    # k = windows with positive mean excess; n = eff_n (total non-overlapping windows).
    # This prevents k > n (which would cause negative Wilson variance → complex TypeError).
    for regime_str, grp in attribution.groupby("regime_stratum"):
        raw_n = len(grp)
        dates = grp["date"].tolist()
        eff_n = _effective_n(dates)
        # F2: collapse to window unit — k is number of windows with mean excess > 0
        outcome_positive = (grp["fwd_excess"] > 0).tolist()
        k = _window_unit_k(dates, outcome_positive)

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
            # Detect sentinel (k > n guard fired — should not occur after F2 fix)
            if lo > hi:
                log.warning(
                    "_build_scoreboard: Wilson sentinel (k=%d > n=%d) for stratum=%s — "
                    "units mismatch; reporting ACCRUING to avoid invalid CI",
                    k, eff_n, regime_str,
                )
                cells.append({
                    "stratum": str(regime_str),
                    "raw_n": raw_n,
                    "effective_n": eff_n,
                    "state": "ACCRUING",
                    "us_proxy": regime_str == "us_proxy",
                    "note": "wilson_sentinel: k>n detected; check unit alignment",
                })
            else:
                cells.append({
                    "stratum": str(regime_str),
                    "raw_n": raw_n,
                    "effective_n": eff_n,
                    "state": "reported",
                    "hit_rate_windows": round(k / eff_n, 4),
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
        # F4 FIX: SA-R15 forbids fabricating 0.0 when n_episodes == 0.
        # Zero episodes means we cannot compute missed_mover_rate at all —
        # value=None + data_gap note (mirrors the n_episodes>0 degrade below).
        return {
            "value": None,
            "n": len(graded),
            "n_episodes": 0,
            "maturity": "accruing",
            "source": "data/china_standout_track/board.parquet",
            "note": (
                "data_gap: no big-winner episodes at +12pp threshold yet — "
                "missed_mover_rate is undefined (not 0.0); accruing per SA-R15."
            ),
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
        # F2 FIX: window-unit Wilson — k = windows with positive mean excess, n = eff_n windows
        outcome_positive = (graded["fwd_21d_excess"] > 0).tolist()
        dates_list = graded["date"].tolist()
        k = _window_unit_k(dates_list, outcome_positive)
        lo, _hi = _wilson_ci(k, eff_n)
        if lo > _hi:  # sentinel: k > n (should not occur after F2 fix)
            hit_quality = _accruing(n_graded, "wilson_sentinel: k>n — check unit alignment")
        else:
            hit_quality = {
                "value": round(lo, 4), "n": n_graded, "effective_n": eff_n,
                "k_windows": k,
                "maturity": "ready",
                "source": "data/china_standout_track/board.parquet",
                "note": "Wilson lower bound of P(positive-mean-excess window) — cluster-unit CI (F2 window-unit)",
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
        "taxonomy_notes": {
            "premature_stop_noise": _PREMATURE_STOP_NOTE,
            "sector_leg": _NO_SECTOR_LEG_NOTE,
        },
        "notes": (
            f"CN standout fitness card. All sensors accruing until SA-R10 floors met "
            f"(currently {n_graded}/25 matured rows, {distinct_dates}/10 distinct dates, "
            f"{eff_n}/3 non-overlapping windows). "
            f"Expected first reads: ~2026-10-15. "
            f"No 'validated' claim — pre-maturity values are display context only. "
            f"premature_stop_noise: UNIMPLEMENTED (no stop-date column in ledger). "
            f"sector_rotated_out/beta_tailwind: DEGRADED to mixed (no genuine sector grouping)."
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
                    # F3: renamed from sector_proxy_excess → peer_board_deviation
                    "peer_board_deviation": float(row["peer_board_deviation"]) if pd.notna(row.get("peer_board_deviation", None)) else None,
                    "bench_return": float(row["bench_return"]) if pd.notna(row.get("bench_return", None)) else None,
                    # F3: renamed from idio_vs_sector → idio_vs_peer
                    "idio_vs_peer": float(row["idio_vs_peer"]) if pd.notna(row.get("idio_vs_peer", None)) else None,
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
