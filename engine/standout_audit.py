"""engine.standout_audit — SA-W1: US two-axis attribution organ.

Deterministic attribution over matured rows in data/us_board_ledger/retro_grades.parquet.
NEVER raises into callers (SA-R16).  One-grader law: reads graded columns, never
recomputes forward returns (SA-R14).

Input stores:
  - data/us_board_ledger/retro_grades.parquet   (committed; graded columns present)
  - data/us_board_ledger/snapshots.jsonl         (committed; buy-lane history)
  - data/signal_archive/track_record.parquet     (committed; near-miss rows)

Output artifacts (all committed by standout_audit_us daily.yml job):
  - data/standout_audit/us_attribution.parquet
  - data/standout_audit/us_evidence.jsonl
  - site/factordata/us_audit_scoreboard.json
  - data/metabolism/fitness/standouts_us.json
  - data/standout_audit/us_audit_state.json

Column mapping (retro_grades.parquet schema as of 2026-07-12, 80 cols):
  Axis-1 inputs: excess_spy, excess_sector, spy_ret, etf_ret, ret
  Axis-2 inputs: board_tenure_days, terminal_state_clean8_21, staleness_hours
  Regime stamps: quad_hard_label, vol_regime, risk_radar_state
  Identity: as_of, ticker, lane, horizon, sector, position
  Grading columns: ret, spy_ret, excess_spy, etf_ret, excess_sector

All thresholds are in the TAXONOMY_CONSTANTS block and are LOOP-IMMUTABLE (SA-R2).
The taxonomy_version constant governs keep-first dedup on the sidecar.

Public API:
  build_us(root=None) -> dict   NEVER-RAISE; absent store -> {status:'data_gap'}

Sensor unit contract (SA-R3 — no mixed-unit composites):
  Every sensor that feeds the fitness card must carry a value in [0, 1] (or null).
  Sensors whose natural unit is a raw count or days CANNOT be honestly normalized
  to [0, 1] without an external baseline, so they set value=null and store the raw
  reading in a 'reading' field.  The metabolism composite reader
  (organism_state._extract_composite_fitness) skips null-value sensors, so no
  mixed-unit averaging can occur.
    hit_quality      — Wilson-LB in [0, 1]          value=float
    upside_capture   — ratio (can exceed 1)          value=float (clamped to [0, 1] if > 1)
    coverage_health  — trailing-4wk unique tickers   value=null; reading=count (raw count)
    missed_mover_rate— miss rate in [0, 1]           value=float (inverted: 1 - rate)
    timing_quality   — median tenure in days         value=null; reading=days (raw days)
    process_integrity— data_fault share in [0, 1]    value=float (inverted: 1 - rate)

gate_suppressed data_gap contract (B2):
  track_record near_miss rows have no excess_spy column (only fwd_ret_20 raw).
  One-grader law forbids recomputing SPY excess from prices.  When the near_miss
  store lacks an already-graded excess column, _check_gate_suppressed returns
  (False, 'data_gap') and the scoreboard/evidence packs emit a visible sentinel
  rather than a silent all-False.

signaled_too_late timing_basis disclosure (M3):
  Only board_tenure_days > A2_SIGNALED_TOO_LATE_TENURE is wired.  The spec's
  extension-percentile and ticks-since-cross clauses require graded extension/
  freshness columns that do not exist in the current retro_grades schema.  The
  scoreboard and card carry a 'timing_basis' field listing which clauses are active.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TAXONOMY CONSTANTS — LOOP-IMMUTABLE (SA-R2).  Operator PR required to change.
# Do NOT modify these constants from any automated pipeline.
# ---------------------------------------------------------------------------

TAXONOMY_VERSION = "v2"

# Axis-1: outcome-cause thresholds (pp = percentage points, expressed as decimals)
# Losers (in precedence order — highest-specificity first)
A1_IDIO_BREAK_THRESHOLD = -0.04          # excess vs sector <= -4pp
A1_SECTOR_ROTATED_SECTOR_THRESH = -0.025  # sector-ETF excess vs SPY <= -2.5pp
A1_SECTOR_ROTATED_IDIO_BAND = 0.02        # idio within ±2pp of sector
A1_MACRO_SPY_THRESH = -0.03              # SPY return <= -3% over horizon
A1_MACRO_IDIO_BAND = 0.02               # idio within ±2pp of sector

# Winners (in precedence order)
A1_IDIO_ALPHA_THRESHOLD = 0.04           # excess vs sector >= +4pp
A1_BETA_TAILWIND_IDIO_BAND = 0.02        # idio within ±2pp of sector

# Axis-2: process-fault thresholds
A2_SIGNALED_TOO_LATE_TENURE = 7          # board_tenure_days > 7 at first buy-lane appearance
A2_PREMATURE_STOP_MFE_THRESH = 0.04      # post-window MFE >= +4pp above stop within 21 sessions
A2_PREMATURE_STOP_SESSIONS = 21          # session window for MFE check
A2_GATE_SUPPRESSED_EXCESS_THRESH = 0.04  # realized 21d excess >= +4pp (near-miss winner)

# Sensors / maturity floors (SA-R10)
SENSOR_MIN_MATURED_ROWS = 25
SENSOR_MIN_ENTRY_DATES = 10
SENSOR_MIN_NONOVERLAPPING_WINDOWS = 3
SENSOR_MIN_CALENDAR_MONTHS = 3

# Missed-mover census
MISSED_MOVER_EPISODE_EXCESS_THRESH = 0.12  # 21d forward excess vs SPY >= +12pp
MISSED_MOVER_EPISODE_WINDOW = 30           # sessions
MISSED_MOVER_BUY_WINDOW = 10              # buy-lane must appear within 10 sessions of episode start

# Scoreboard
WILSON_Z = 1.96   # 95% CI

# Schema tag
OUTPUT_SCHEMA = "standout_audit.v1"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _retro_path(root: Path) -> Path:
    return root / "data" / "us_board_ledger" / "retro_grades.parquet"


def _snapshots_path(root: Path) -> Path:
    return root / "data" / "us_board_ledger" / "snapshots.jsonl"


def _track_record_path(root: Path) -> Path:
    return root / "data" / "signal_archive" / "track_record.parquet"


def _attribution_path(root: Path) -> Path:
    p = root / "data" / "standout_audit" / "us_attribution.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _evidence_path(root: Path) -> Path:
    p = root / "data" / "standout_audit" / "us_evidence.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _scoreboard_path(root: Path) -> Path:
    p = root / "site" / "factordata" / "us_audit_scoreboard.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fitness_path(root: Path) -> Path:
    p = root / "data" / "metabolism" / "fitness" / "standouts_us.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _state_path(root: Path) -> Path:
    p = root / "data" / "standout_audit" / "us_audit_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Effective-N computation (SA-R10)
# ---------------------------------------------------------------------------

def _effective_n(
    dates: list[str],
    horizon_days: int = 21,
    session_dates: list[str] | None = None,
) -> int:
    """Count non-overlapping horizon-length windows from a list of entry dates.

    m2 fix: when session_dates is provided, windows are measured in SESSION ORDINALS
    (rank of date in the ledger's sorted unique trading-date list) rather than
    calendar days.  21 calendar days ≈ 15 sessions; using calendar days is
    anti-conservative (over-counts independent windows for overlapping session windows).

    Steps:
    1. Collapse to unique entry-dates (deduplicate rows from the same date).
    2. Sort dates ascending.
    3. Greedily count non-overlapping windows of `horizon_days` session ordinals
       (or calendar days when session_dates is None).

    This is the 'cluster unit' for Wilson CI computation (SA-R10).
    Returns 0 on empty input or errors.
    """
    if not dates:
        return 0
    try:
        unique_dates = sorted(set(
            pd.Timestamp(d).normalize()
            for d in dates
            if pd.notna(d) and str(d).strip()
        ))
        if not unique_dates:
            return 0

        if session_dates is not None:
            # Build session-ordinal index from the full ledger's trading-date list
            all_sessions = sorted(set(
                pd.Timestamp(d).normalize()
                for d in session_dates
                if pd.notna(d) and str(d).strip()
            ))
            session_idx: dict[pd.Timestamp, int] = {d: i for i, d in enumerate(all_sessions)}

            # For dates not in the session index (e.g. non-trading days), find nearest
            def _to_session_ord(ts: pd.Timestamp) -> int:
                if ts in session_idx:
                    return session_idx[ts]
                # Fall back: count how many session dates are <= ts
                return sum(1 for s in all_sessions if s <= ts) - 1

            count = 1
            last_ord = _to_session_ord(unique_dates[0])
            for d in unique_dates[1:]:
                ord_ = _to_session_ord(d)
                if ord_ - last_ord >= horizon_days:
                    count += 1
                    last_ord = ord_
        else:
            # Legacy: calendar-day window (conservative-enough for short-window tests)
            count = 1
            last_start = unique_dates[0]
            for d in unique_dates[1:]:
                if (d - last_start).days >= horizon_days:
                    count += 1
                    last_start = d
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("_effective_n: %s", exc)
        return 0


def _wilson_ci(hits: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson CI on cluster-unit. Returns (lo, hi). 'hi' is the Wilson-LB (conservative)."""
    if n <= 0:
        return 0.0, 0.0
    p_hat = hits / n
    denom = 1.0 + z ** 2 / n
    center = (p_hat + z ** 2 / (2 * n)) / denom
    spread = z * ((p_hat * (1 - p_hat) / n + z ** 2 / (4 * n ** 2)) ** 0.5) / denom
    lo = max(0.0, center - spread)
    hi = min(1.0, center + spread)
    return round(lo, 4), round(hi, 4)


# ---------------------------------------------------------------------------
# Axis-1: outcome cause attribution
# ---------------------------------------------------------------------------

def _outcome_cause(row: dict) -> tuple[str, list[str]]:
    """Assign the primary outcome cause and secondary flags.

    Returns (primary_code, secondary_flags_list).
    Precedence for losers: idio_break > sector_rotated_out > macro_headwind.
    Precedence for winners: idio_alpha > beta_tailwind.
    Residual: mixed.
    """
    exc_spy = _fval(row.get("excess_spy"))    # excess vs SPY
    exc_sec = _fval(row.get("excess_sector")) # excess vs sector ETF
    spy_ret = _fval(row.get("spy_ret"))
    ret = _fval(row.get("ret"))

    # sector return proxy: ret - excess_sector ≈ sector return
    # (excess_sector = ret - etf_ret so etf_ret = ret - excess_sector)
    if exc_sec is not None and ret is not None:
        sec_ret = ret - exc_sec
    else:
        sec_ret = None

    # sector vs benchmark excess (sector - SPY)
    if sec_ret is not None and spy_ret is not None:
        sec_vs_spy = sec_ret - spy_ret
    else:
        sec_vs_spy = None

    if exc_spy is None or exc_sec is None:
        return "mixed", []

    candidates = {}

    # --- Losers ---
    # idio_break: excess vs sector <= -4pp
    if exc_sec <= A1_IDIO_BREAK_THRESHOLD:
        candidates["idio_break"] = 1

    # sector_rotated_out: sector vs benchmark <= -2.5pp AND idio within ±2pp of sector
    if (sec_vs_spy is not None
            and sec_vs_spy <= A1_SECTOR_ROTATED_SECTOR_THRESH
            and abs(exc_sec) <= A1_SECTOR_ROTATED_IDIO_BAND):
        candidates["sector_rotated_out"] = 2

    # macro_headwind: SPY <= -3% AND idio within ±2pp of sector
    if (spy_ret is not None
            and spy_ret <= A1_MACRO_SPY_THRESH
            and abs(exc_sec) <= A1_MACRO_IDIO_BAND):
        candidates["macro_headwind"] = 3

    # --- Winners ---
    # idio_alpha: excess vs sector >= +4pp
    if exc_sec >= A1_IDIO_ALPHA_THRESHOLD:
        candidates["idio_alpha"] = 4

    # beta_tailwind: positive return, idio within ±2pp of sector, sector/market strongly positive
    if (ret is not None and ret > 0
            and abs(exc_sec) <= A1_BETA_TAILWIND_IDIO_BAND
            and spy_ret is not None and spy_ret > 0):
        candidates["beta_tailwind"] = 5

    if not candidates:
        return "mixed", []

    # Sort by precedence: lower number = higher precedence
    # For winner and loser families, use precedence numbers as-is
    # (idio_break=1, sector_rotated_out=2, macro_headwind=3, idio_alpha=4, beta_tailwind=5)
    # Primary is the lowest precedence number (most specific)
    sorted_codes = sorted(candidates.keys(), key=lambda c: candidates[c])
    primary = sorted_codes[0]
    secondary = [c for c in sorted_codes[1:]]
    return primary, secondary


def _fval(v: Any) -> float | None:
    """Coerce to float or None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f  # noqa: PLR0124 (NaN check)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Axis-2: process fault attribution
# ---------------------------------------------------------------------------

def _process_fault(row: dict) -> str:
    """Assign the primary process fault code.

    Precedence (first match wins):
    1. signaled_too_late  — board_tenure_days > 7 at first buy-lane appearance
    2. premature_stop_noise — terminal_state STOPPED AND fwd_mfe_21 shows post-stop recovery
       grade_us_board.py writes fwd_mfe_{h} only on each row's own horizon, so for 21d
       rows the relevant column is fwd_mfe_21 (not fwd_mfe_5).  Terminal state values
       from engine/grading.py are uppercase: STOPPED, DEAD_MONEY, CUSHIONED, CLEAN_LIFTOFF.
    3. data_fault — staleness flag present
    4. clean — default
    """
    # signaled_too_late: board_tenure_days > A2_SIGNALED_TOO_LATE_TENURE
    tenure = _fval(row.get("board_tenure_days"))
    if tenure is not None and tenure > A2_SIGNALED_TOO_LATE_TENURE:
        return "signaled_too_late"

    # premature_stop_noise: terminal_state was STOPPED AND fwd_mfe_21 shows post-stop recovery
    # Uses terminal_state_clean8_21 (uppercase enum from engine.grading.TerminalState).
    # Must read fwd_mfe_21 — the column populated by grade_us_board.py for 21d-horizon rows.
    # fwd_mfe_5 is null on 21d rows (each row carries only its own horizon's MFE column).
    term_state = row.get("terminal_state_clean8_21")
    if term_state is not None and str(term_state).upper() == "STOPPED":
        mfe = _fval(row.get("fwd_mfe_21"))
        if mfe is not None and mfe >= A2_PREMATURE_STOP_MFE_THRESH:
            return "premature_stop_noise"

    # data_fault: staleness_hours present and high (>30h = SLA breach at entry)
    stale = _fval(row.get("staleness_hours"))
    if stale is not None and stale > 30:
        return "data_fault"

    return "clean"


# ---------------------------------------------------------------------------
# Near-miss join for gate_suppressed
# ---------------------------------------------------------------------------

def _load_near_misses(root: Path) -> pd.DataFrame:
    """Load near-miss rows from track_record.parquet. Returns empty df on any error."""
    try:
        p = _track_record_path(root)
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_parquet(p)
        if df.empty:
            return pd.DataFrame()
        # Filter to near_miss type
        if "type" in df.columns:
            df = df[df["type"] == "near_miss"]
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("_load_near_misses: %s", exc)
        return pd.DataFrame()


def _check_gate_suppressed(row: dict, near_miss_df: pd.DataFrame) -> tuple[bool, str | None]:
    """Check whether this (as_of, ticker) was gate-suppressed.

    Returns (is_suppressed: bool, gap_reason: str | None).

    One-grader law: track_record near_miss rows have no excess_spy column — only raw
    fwd_ret_20.  Recomputing SPY excess from prices is forbidden (SA-R14).  When the
    near_miss store lacks an already-graded excess column, the check cannot be performed
    honestly and returns (False, 'data_gap: near_miss store lacks excess_spy column').
    The scoreboard and evidence packs expose this sentinel so the gap is NEVER silent.
    """
    if near_miss_df.empty:
        return False, None
    try:
        # B2 fix: verify excess_spy column exists in near_miss store before reading it.
        # track_record.parquet near_miss rows carry fwd_ret_20 (raw) but no excess_spy.
        # One-grader law (SA-R14): we must NOT recompute excess from prices here.
        if "excess_spy" not in near_miss_df.columns:
            return False, "data_gap: near_miss store lacks excess_spy column"

        ticker = row.get("ticker")
        asof = row.get("as_of")
        if not ticker or not asof:
            return False, None

        # Match near misses: date=as_of (or entry_date), ticker
        mask = near_miss_df["ticker"] == ticker
        if "date" in near_miss_df.columns:
            mask = mask & (near_miss_df["date"].astype(str) == str(asof))

        nm_rows = near_miss_df[mask]
        if nm_rows.empty:
            return False, None

        # Check if any near_miss row has excess_spy >= +4pp at 21d horizon
        for _, nm in nm_rows.iterrows():
            exc = _fval(nm.get("excess_spy"))
            if exc is not None and exc >= A2_GATE_SUPPRESSED_EXCESS_THRESH:
                return True, None
        return False, None
    except Exception as exc:  # noqa: BLE001
        log.warning("_check_gate_suppressed: %s", exc)
        return False, None


# ---------------------------------------------------------------------------
# Two-axis attribution on 21d rows
# ---------------------------------------------------------------------------

def _attribute_rows(
    df21: pd.DataFrame, near_miss_df: pd.DataFrame
) -> tuple[list[dict], str | None]:
    """Run two-axis attribution on all 21d-horizon rows.

    Returns (attribution_rows, gate_suppressed_gap_reason).
    gate_suppressed_gap_reason is non-None when the near_miss store lacks the excess_spy
    column — the gap sentinel must be propagated to the scoreboard and evidence packs
    so it is never silent (B2 fix).
    """
    results = []
    gate_suppressed_gap: str | None = None  # B2: capture data_gap from first check

    for _, row in df21.iterrows():
        r = row.to_dict()

        # Axis 1
        outcome_cause, secondary_flags = _outcome_cause(r)

        # Axis 2
        process_fault = _process_fault(r)
        if process_fault == "clean":
            # Check gate_suppressed from near-miss store
            suppressed, gap_reason = _check_gate_suppressed(r, near_miss_df)
            if gap_reason and gate_suppressed_gap is None:
                gate_suppressed_gap = gap_reason  # record gap once
            if suppressed:
                process_fault = "gate_suppressed"

        attr = {
            "as_of": r.get("as_of"),
            "ticker": r.get("ticker"),
            "lane": r.get("lane"),
            "horizon": int(r.get("horizon", 21)),
            "taxonomy_version": TAXONOMY_VERSION,
            "outcome_cause": outcome_cause,
            "secondary_flags": json.dumps(secondary_flags),
            "process_fault": process_fault,
            # preserve key context columns
            "sector": r.get("sector"),
            "excess_spy": _fval(r.get("excess_spy")),
            "excess_sector": _fval(r.get("excess_sector")),
            "spy_ret": _fval(r.get("spy_ret")),
            "board_tenure_days": _fval(r.get("board_tenure_days")),
            "quad_hard_label": r.get("quad_hard_label"),
            "vol_regime": r.get("vol_regime"),
            "risk_radar_state": r.get("risk_radar_state"),
            "terminal_state_clean8_21": r.get("terminal_state_clean8_21"),
            "staleness_hours": _fval(r.get("staleness_hours")),
            "entry_date": r.get("entry_date"),
        }
        results.append(attr)
    return results, gate_suppressed_gap


# ---------------------------------------------------------------------------
# Attribution sidecar: keep-first dedup
# ---------------------------------------------------------------------------

def _merge_attribution_sidecar(existing: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """Merge new attribution rows into existing sidecar, keep-first on dedup key.

    Dedup key: (as_of, ticker, lane, horizon, taxonomy_version).
    """
    if not new_rows:
        return existing

    new_df = pd.DataFrame(new_rows)

    # Ensure key columns are strings for merge
    KEY_COLS = ["as_of", "ticker", "lane", "horizon", "taxonomy_version"]
    for col in KEY_COLS:
        if col in new_df.columns:
            new_df[col] = new_df[col].astype(str)

    if existing.empty:
        return new_df

    for col in KEY_COLS:
        if col in existing.columns:
            existing[col] = existing[col].astype(str)

    # Build existing key set
    existing_keys = set(
        tuple(r[c] for c in KEY_COLS if c in r)
        for r in existing.to_dict("records")
    )

    filtered_new = [
        r for r in new_rows
        if tuple(str(r.get(c, "")) for c in KEY_COLS) not in existing_keys
    ]

    if not filtered_new:
        return existing

    return pd.concat([existing, pd.DataFrame(filtered_new)], ignore_index=True)


# ---------------------------------------------------------------------------
# Evidence packs (append-only, keep-first on as_of+ticker+lane)
# ---------------------------------------------------------------------------

def _load_existing_evidence(path: Path) -> set[tuple[str, str, str]]:
    """Return set of (as_of, ticker, lane) keys already in evidence JSONL."""
    seen: set[tuple[str, str, str]] = set()
    if not path.exists():
        return seen
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                k = (str(r.get("as_of", "")), str(r.get("ticker", "")), str(r.get("lane", "")))
                seen.add(k)
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("_load_existing_evidence: %s", exc)
    return seen


def _build_evidence_pack(row_dict: dict, attr: dict) -> dict:
    """Build one evidence pack row from a graded retro row and its attribution."""
    return {
        "as_of": row_dict.get("as_of"),
        "ticker": row_dict.get("ticker"),
        "lane": row_dict.get("lane"),
        "entry_date": row_dict.get("entry_date"),
        "sector": row_dict.get("sector"),
        "horizon": int(row_dict.get("horizon", 21)),
        # Entry-time context stamps
        "quad_hard_label": row_dict.get("quad_hard_label"),
        "vol_regime": row_dict.get("vol_regime"),
        "risk_radar_state": row_dict.get("risk_radar_state"),
        "fused_risk_label": row_dict.get("fused_risk_label"),
        "board_tenure_days": _fval(row_dict.get("board_tenure_days")),
        "staleness_hours": _fval(row_dict.get("staleness_hours")),
        "species_id": row_dict.get("species_id"),
        "archetype": row_dict.get("archetype"),
        # Outcome numbers
        "ret": _fval(row_dict.get("ret")),
        "spy_ret": _fval(row_dict.get("spy_ret")),
        "excess_spy": _fval(row_dict.get("excess_spy")),
        "excess_sector": _fval(row_dict.get("excess_sector")),
        # Attribution
        "outcome_cause": attr["outcome_cause"],
        "secondary_flags": attr.get("secondary_flags", "[]"),
        "process_fault": attr["process_fault"],
        "taxonomy_version": TAXONOMY_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Stratified scoreboard helpers
# ---------------------------------------------------------------------------

def _hit(row: dict) -> bool:
    """A buy-lane row is a hit if excess_spy > 0."""
    exc = _fval(row.get("excess_spy"))
    return exc is not None and exc > 0


def _entry_date_collapse(rows: list[dict]) -> list[dict]:
    """Collapse to one observation per unique entry_date (mean excess_spy per date)."""
    if not rows:
        return []
    from collections import defaultdict
    by_date: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        ed = str(r.get("entry_date") or r.get("as_of") or "")
        exc = _fval(r.get("excess_spy"))
        if ed and exc is not None:
            by_date[ed].append(exc)
    collapsed = []
    for ed, vals in by_date.items():
        mean_exc = float(np.mean(vals))
        collapsed.append({
            "entry_date": ed,
            "excess_spy": mean_exc,
            "hit": mean_exc > 0,
        })
    return collapsed


def _cell_stats(rows: list[dict], session_dates: list[str] | None = None) -> dict:
    """Compute cell statistics: raw_n, effective_n, hit_rate, wilson_ci.

    session_dates: full sorted unique trading-date list from the ledger, used for
    session-ordinal effective_n (m2 fix — calendar days are anti-conservative).
    """
    if not rows:
        return {"raw_n": 0, "effective_n": 0, "state": "ACCRUING"}

    raw_n = len(rows)
    entry_dates = [str(r.get("entry_date") or r.get("as_of") or "") for r in rows]
    effective_n = _effective_n(entry_dates, horizon_days=21, session_dates=session_dates)

    if effective_n < 3:
        return {"raw_n": raw_n, "effective_n": effective_n, "state": "ACCRUING"}

    # Collapse to entry-date unit
    collapsed = _entry_date_collapse(rows)
    n_clust = len(collapsed)
    n_hits = sum(1 for r in collapsed if r.get("hit"))
    hit_rate = n_hits / n_clust if n_clust > 0 else 0.0
    lo, hi = _wilson_ci(n_hits, n_clust)
    mean_excess = float(np.mean([r["excess_spy"] for r in collapsed]))

    return {
        "raw_n": raw_n,
        "effective_n": effective_n,
        "state": "DATA",
        "hit_rate": round(hit_rate, 4),
        "wilson_lo": lo,
        "wilson_hi": hi,
        "mean_excess_spy": round(mean_excess, 4),
    }


def _build_scoreboard(
    attr_rows: list[dict],
    df_all: pd.DataFrame | None = None,
    gate_suppressed_gap: str | None = None,
) -> dict:
    """Build the stratified scoreboard from attribution rows.

    Stratifies by: regime cell (quad_hard_label, vol_regime, risk_radar_state),
    lane, outcome_cause, process_fault, sector.

    gate_suppressed_gap: when non-None, the near_miss store lacks the excess_spy column
    needed to compute gate_suppressed.  This sentinel is emitted in the scoreboard
    so the data gap is never silent (B2 fix; one-grader law SA-R14).
    """
    gate_suppressed_note = (
        {"gate_suppressed": {"state": "data_gap", "reason": gate_suppressed_gap}}
        if gate_suppressed_gap else {}
    )
    if not attr_rows:
        return {
            "schema": "standout_audit.scoreboard.v1",
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "note": (
                "CIs are cluster-unit (entry-date-collapsed) and descriptive only. "
                "No significance claims. Cells with effective_n<3 print state='ACCRUING'."
            ),
            "timing_basis": ["board_tenure"],
            "timing_basis_note": (
                "signaled_too_late fires only on board_tenure_days > A2_SIGNALED_TOO_LATE_TENURE. "
                "Extension-percentile and ticks-since-cross clauses NOT wired (columns absent)."
            ),
            "buy_lane_rows": 0,
            "all_lanes_rows": 0,
            "strata": {},
            "coverage_monitor": _build_coverage_monitor(df_all),
            **gate_suppressed_note,
        }

    buy_rows = [r for r in attr_rows if r.get("lane") == "buy"]

    # Extract session trading dates from the full ledger for session-ordinal effective_n (m2)
    _session_dates: list[str] | None = None
    if df_all is not None and not df_all.empty and "as_of" in df_all.columns:
        _session_dates = [str(d) for d in df_all["as_of"].dropna().unique().tolist()]

    def _stratify(rows: list[dict], key_fn) -> dict:
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        for r in rows:
            groups[str(key_fn(r))].append(r)
        return {k: _cell_stats(v, session_dates=_session_dates) for k, v in sorted(groups.items())}

    strata: dict[str, Any] = {}

    # By lane
    strata["by_lane"] = _stratify(attr_rows, lambda r: r.get("lane", "unknown"))

    # Buy-lane only strata (main signal)
    strata["by_quad_hard_label"] = _stratify(
        buy_rows, lambda r: r.get("quad_hard_label") or "unknown")
    strata["by_vol_regime"] = _stratify(
        buy_rows, lambda r: r.get("vol_regime") or "unknown")
    strata["by_risk_radar_state"] = _stratify(
        buy_rows, lambda r: r.get("risk_radar_state") or "unknown")
    strata["by_outcome_cause"] = _stratify(
        buy_rows, lambda r: r.get("outcome_cause", "unknown"))
    strata["by_process_fault"] = _stratify(
        buy_rows, lambda r: r.get("process_fault", "unknown"))
    strata["by_sector"] = _stratify(
        buy_rows, lambda r: r.get("sector") or "unknown")

    # Upstream concordance: per-column discordance rates
    strata["upstream_concordance"] = _upstream_concordance(buy_rows, session_dates=_session_dates)

    return {
        "schema": "standout_audit.scoreboard.v1",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "note": (
            "CIs are cluster-unit (entry-date-collapsed) and descriptive only. "
            "No significance claims. Cells with effective_n<3 print state='ACCRUING'."
        ),
        # M3: disclose which timing clauses are wired
        "timing_basis": ["board_tenure"],
        "timing_basis_note": (
            "signaled_too_late fires only on board_tenure_days > A2_SIGNALED_TOO_LATE_TENURE. "
            "Spec's extension-percentile (>=85th) and ticks-since-cross clauses are NOT wired "
            "— the required graded extension/freshness columns are absent from retro_grades schema."
        ),
        "buy_lane_rows": len(buy_rows),
        "all_lanes_rows": len(attr_rows),
        "strata": strata,
        "coverage_monitor": _build_coverage_monitor(df_all),
        **gate_suppressed_note,
    }


def _upstream_concordance(
    buy_rows: list[dict], session_dates: list[str] | None = None
) -> dict:
    """Per-organ discordance rates (SA-R8).

    For each stamped context column, measure: state_at_entry said X,
    realized outcome was discordant.

    Discordance definitions (display-tier, SA-W1 — no insight_bus emission yet):
    - quad_hard_label: calm/risk-on but SPY fell <= -3% over horizon => discordant
    - risk_radar_state: no_risk_off but outcome was idio_break or macro_headwind => discordant
    - sector stamped as tailwind but realized excess_sector < 0 => discordant
    """
    if not buy_rows:
        return {}

    organs = {}

    # quad_hard_label concordance
    ql_rows = [r for r in buy_rows if r.get("quad_hard_label") and r.get("spy_ret") is not None]
    if ql_rows:
        calm_risk_on = [r for r in ql_rows if str(r.get("quad_hard_label", "")).lower() in
                        ("calm", "risk_on", "calm/risk-on", "calm_risk_on")]
        if calm_risk_on:
            discordant = [r for r in calm_risk_on
                          if _fval(r.get("spy_ret")) is not None
                          and _fval(r.get("spy_ret")) <= A1_MACRO_SPY_THRESH]
            n_total = len(calm_risk_on)
            n_disc = len(discordant)
            entry_dates = [str(r.get("entry_date") or "") for r in calm_risk_on]
            eff_n = _effective_n(entry_dates, session_dates=session_dates)
            organs["quad_hard_label"] = {
                "organ": "quad_hard_label",
                "description": "calm/risk-on stamped but SPY fell >=-3% over horizon",
                "n_concordant_cells": n_total - n_disc,
                "n_discordant": n_disc,
                "raw_n": n_total,
                "effective_n": eff_n,
                "discordance_rate": round(n_disc / n_total, 4) if n_total > 0 else 0,
                "state": "ACCRUING" if eff_n < 3 else "DATA",
            }

    # risk_radar_state concordance
    rr_rows = [r for r in buy_rows if r.get("risk_radar_state") and r.get("outcome_cause")]
    if rr_rows:
        quiet_rows = [r for r in rr_rows if str(r.get("risk_radar_state", "")).lower() not in
                      ("risk_off", "risk-off")]
        if quiet_rows:
            discordant = [r for r in quiet_rows
                          if r.get("outcome_cause") in ("idio_break", "macro_headwind")]
            n_total = len(quiet_rows)
            n_disc = len(discordant)
            entry_dates = [str(r.get("entry_date") or "") for r in quiet_rows]
            eff_n = _effective_n(entry_dates, session_dates=session_dates)
            organs["risk_radar_state"] = {
                "organ": "risk_radar_state",
                "description": "no risk-off stamped but outcome was break/macro-headwind",
                "n_concordant_cells": n_total - n_disc,
                "n_discordant": n_disc,
                "raw_n": n_total,
                "effective_n": eff_n,
                "discordance_rate": round(n_disc / n_total, 4) if n_total > 0 else 0,
                "state": "ACCRUING" if eff_n < 3 else "DATA",
            }

    return organs


# ---------------------------------------------------------------------------
# Coverage monitor
# ---------------------------------------------------------------------------

def _build_coverage_monitor(df: pd.DataFrame | None) -> dict:
    """Build the coverage monitor from all retro_grades rows (snapshots.jsonl).

    Trailing 4-week buy-lane surfaced count, 8-week history, frozen_baseline placeholder.
    """
    monitor: dict[str, Any] = {
        "frozen_baseline": None,  # placeholder — frozen at first sensor maturity (SA-R4)
        "frozen_baseline_note": "Not yet frozen. Will be anchored at first sensor-maturity date.",
        "trailing_4wk_buy_count": None,
        "weekly_history": [],
        "data_gap": None,
    }

    if df is None or df.empty:
        monitor["data_gap"] = "retro_grades not loaded"
        return monitor

    try:
        buy_df = df[df["lane"] == "buy"].copy()
        if buy_df.empty:
            monitor["data_gap"] = "no buy-lane rows"
            return monitor

        buy_df["_asof_dt"] = pd.to_datetime(buy_df["as_of"], errors="coerce")
        buy_df = buy_df.dropna(subset=["_asof_dt"])
        if buy_df.empty:
            return monitor

        max_date = buy_df["_asof_dt"].max()
        cutoff_4wk = max_date - pd.Timedelta(weeks=4)
        cutoff_8wk = max_date - pd.Timedelta(weeks=8)

        trailing_4wk = buy_df[buy_df["_asof_dt"] >= cutoff_4wk]
        monitor["trailing_4wk_buy_count"] = int(len(trailing_4wk["ticker"].unique()))

        # Weekly bins for 8-week history
        weekly = buy_df[buy_df["_asof_dt"] >= cutoff_8wk].copy()
        weekly["_week"] = weekly["_asof_dt"].dt.to_period("W").astype(str)
        week_counts = weekly.groupby("_week")["ticker"].nunique().to_dict()
        monitor["weekly_history"] = [
            {"week": w, "unique_tickers": int(c)}
            for w, c in sorted(week_counts.items())
        ]

    except Exception as exc:  # noqa: BLE001
        log.warning("_build_coverage_monitor: %s", exc)
        monitor["data_gap"] = f"error: {exc}"

    return monitor


# ---------------------------------------------------------------------------
# Missed-mover census (buy-lane credit only)
# ---------------------------------------------------------------------------

def _missed_mover_census(df: pd.DataFrame | None) -> dict:
    """Missed-mover census: big-winner episodes not reached by the buy lane.

    Universe: tickers in retro_grades scope.
    Episode: first day in a 30-session window where 21d forward excess vs SPY >= +12pp.
    Missed: ticker never appeared on BUY lane within 10 sessions of episode start.
    pipeline_recall: appeared on watch/ripening but not buy.

    If retro_grades has no 21d rows, this returns data_gap.
    """
    if df is None or df.empty:
        return {"data_gap": "retro_grades not loaded", "missed_mover_rate": None,
                "pipeline_recall": None, "n_episodes": None, "n_missed": None}

    df21 = df[df["horizon"] == 21].copy()
    if df21.empty:
        return {
            "data_gap": "no_21d_rows_yet",
            "note": "21d-horizon rows not yet matured. Census will populate as ledger accrues.",
            "missed_mover_rate": None,
            "pipeline_recall": None,
            "n_episodes": None,
            "n_missed": None,
        }

    try:
        # Convert as_of to datetime for ordering
        df21["_asof_dt"] = pd.to_datetime(df21["as_of"], errors="coerce")
        df21 = df21.dropna(subset=["_asof_dt"])

        # Episodes: a ticker's first as_of in any 30-session window with excess_spy >= +12pp
        winners = df21[df21["excess_spy"].apply(lambda x: _fval(x) is not None and
                        (_fval(x) or 0.0) >= MISSED_MOVER_EPISODE_EXCESS_THRESH)].copy()

        if winners.empty:
            return {
                "n_episodes": 0,
                "n_missed": 0,
                "missed_mover_rate": 0.0,
                "pipeline_recall": 0.0,
                "note": "No episodes found at current maturity level.",
            }

        # Build buy-lane presence map: {ticker -> set of as_of dates}
        buy_df = df[df["lane"] == "buy"]
        watch_df = df[df["lane"] == "watch"]

        buy_presence: dict[str, set[str]] = {}
        for _, r in buy_df.iterrows():
            tkr = str(r.get("ticker", ""))
            asof = str(r.get("as_of", ""))
            if tkr and asof:
                buy_presence.setdefault(tkr, set()).add(asof)

        watch_presence: dict[str, set[str]] = {}
        for _, r in watch_df.iterrows():
            tkr = str(r.get("ticker", ""))
            asof = str(r.get("as_of", ""))
            if tkr and asof:
                watch_presence.setdefault(tkr, set()).add(asof)

        # For each winner episode, check buy-lane within 10 sessions
        # (using as_of date order as a session proxy)
        all_dates = sorted(df21["_asof_dt"].unique())
        date_idx: dict[pd.Timestamp, int] = {d: i for i, d in enumerate(all_dates)}

        n_episodes = 0
        n_missed = 0
        n_pipeline_recall = 0

        # Deduplicate episodes: one per ticker per 30-session window
        processed: dict[str, int] = {}  # ticker -> last episode date_idx

        for _, row in winners.sort_values("_asof_dt").iterrows():
            tkr = str(row.get("ticker", ""))
            ep_idx = date_idx.get(row["_asof_dt"], -1)

            if tkr in processed and ep_idx - processed[tkr] < MISSED_MOVER_EPISODE_WINDOW:
                continue  # within the same 30-session window

            processed[tkr] = ep_idx
            n_episodes += 1

            # Was ticker on buy lane within MISSED_MOVER_BUY_WINDOW sessions?
            # m3 fix: use pre-built date_idx dict instead of O(n) list.index()
            window_dates = [
                d for d in all_dates
                if 0 <= (date_idx[d] - ep_idx) <= MISSED_MOVER_BUY_WINDOW
            ]
            window_date_strs = {d.strftime("%Y-%m-%d") for d in window_dates}

            tkr_buy_dates = buy_presence.get(tkr, set())
            if not tkr_buy_dates.intersection(window_date_strs):
                n_missed += 1
                # Check pipeline_recall: was it on watch?
                tkr_watch_dates = watch_presence.get(tkr, set())
                if tkr_watch_dates.intersection(window_date_strs):
                    n_pipeline_recall += 1

        missed_rate = n_missed / n_episodes if n_episodes > 0 else 0.0
        pipeline_recall = n_pipeline_recall / n_missed if n_missed > 0 else 0.0

        return {
            "n_episodes": n_episodes,
            "n_missed": n_missed,
            "n_pipeline_recall": n_pipeline_recall,
            "missed_mover_rate": round(missed_rate, 4),
            "pipeline_recall": round(pipeline_recall, 4),
            "note": (
                "Buy-lane credit only. pipeline_recall = missed episodes that appeared "
                "on watch lane within the window (capped diagnostic, not credit)."
            ),
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("_missed_mover_census: %s", exc)
        return {"data_gap": f"error: {exc}", "missed_mover_rate": None,
                "pipeline_recall": None, "n_episodes": None, "n_missed": None}


# ---------------------------------------------------------------------------
# US fitness card (SA-R10 §4)
# ---------------------------------------------------------------------------

AUTHORITY_BLOCK: dict[str, Any] = {
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


def _maturity_floors_met(attr_rows: list[dict]) -> bool:
    """Check SA-R10 maturity floors: >=25 rows, >=10 entry dates, >=3 non-overlapping windows."""
    buy_rows = [r for r in attr_rows if r.get("lane") == "buy"]
    if len(buy_rows) < SENSOR_MIN_MATURED_ROWS:
        return False

    entry_dates = list({str(r.get("entry_date") or r.get("as_of") or "") for r in buy_rows})
    if len(entry_dates) < SENSOR_MIN_ENTRY_DATES:
        return False

    eff_n = _effective_n(entry_dates, horizon_days=21)
    if eff_n < SENSOR_MIN_NONOVERLAPPING_WINDOWS:
        return False

    # Check calendar months span
    try:
        dates = sorted([pd.Timestamp(d) for d in entry_dates if d.strip()])
        if not dates:
            return False
        first_month = (dates[0].year, dates[0].month)
        last_month = (dates[-1].year, dates[-1].month)
        months_span = (last_month[0] - first_month[0]) * 12 + (last_month[1] - first_month[1]) + 1
        if months_span < SENSOR_MIN_CALENDAR_MONTHS:
            return False
    except Exception:  # noqa: BLE001
        return False

    return True


def _build_fitness_card(attr_rows: list[dict], scoreboard: dict, df_all: pd.DataFrame | None) -> dict:
    """Build the US standout fitness card matching the metabolism.til_fitness.v1 shape.

    M1 fix — per-sensor maturity stamps and unit-safe values:
      Every sensor has its own 'maturity' field.  Sensors that cannot be honestly
      normalized to [0, 1] (coverage_health = raw ticker count; timing_quality = days)
      set value=null and store the raw reading in a 'reading' field so the metabolism
      composite reader (_extract_composite_fitness averages the 'value' field of all
      'ready' sensors) never mixes units.  Only sensors with an honest 0-1 value emit
      a non-null value.

    M2 fix — coverage_health.value is always null:
      The frozen_baseline required to normalize the trailing-4wk count has not yet been
      anchored (SA-R4).  Without a baseline, any raw count would be incoherent as a
      fitness value.  The raw count rides in 'reading' and a scoreboard diagnostic note.
    """
    buy_rows = [r for r in attr_rows if r.get("lane") == "buy"]
    raw_n = len(buy_rows)

    # Session trading dates for session-ordinal effective_n (m2 fix)
    _session_dates: list[str] | None = None
    if df_all is not None and not df_all.empty and "as_of" in df_all.columns:
        _session_dates = [str(d) for d in df_all["as_of"].dropna().unique().tolist()]

    entry_dates = [str(r.get("entry_date") or r.get("as_of") or "") for r in buy_rows]
    effective_n = _effective_n(entry_dates, horizon_days=21, session_dates=_session_dates)
    floors_met = _maturity_floors_met(attr_rows)

    def _sensor(
        sensor_id: str,
        value: float | None,
        raw_n: int,
        eff_n: int,
        maturity: str,
        note: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Build a sensor dict.  value must be in [0, 1] or null (M1 contract)."""
        d: dict[str, Any] = {
            "id": sensor_id,
            "value": value,
            "raw_n": raw_n,
            "effective_n": eff_n,
            "maturity": maturity,
            "note": note,
            "store": "data/standout_audit/us_attribution.parquet",
        }
        if extra:
            d.update(extra)
        return d

    # --- hit_quality ---
    # Wilson-LB of P(excess_spy>0), buy lane, entry-date-collapsed.
    # Matures when: floors_met (depends on matured 21d rows). [0, 1] honest.
    hit_quality_val = None
    hit_quality_note = None
    hit_maturity = "ready" if floors_met and effective_n >= 3 else "accruing"
    if floors_met and effective_n >= 3:
        collapsed = _entry_date_collapse(buy_rows)
        n_c = len(collapsed)
        n_hits = sum(1 for r in collapsed if r.get("hit"))
        _, wilson_lb = _wilson_ci(n_hits, n_c)
        hit_quality_val = wilson_lb
    else:
        hit_quality_note = f"accruing: {raw_n}/{SENSOR_MIN_MATURED_ROWS} matured rows"

    # --- upside_capture ---
    # mean buy-lane excess / top-decile universe mean. [0, ∞) in principle but
    # clamped to [0, 1] at emission (reading preserved in 'reading' field if > 1).
    # Matures when: floors_met + df_all has >=10 universe rows. [0, 1] after clamp.
    upside_capture_val = None
    upside_capture_note = None
    upside_reading: float | None = None
    uc_maturity = "accruing"
    if df_all is not None and not df_all.empty and floors_met:
        try:
            all21 = df_all[df_all["horizon"] == 21].copy()
            if not all21.empty:
                all_excess = all21["excess_spy"].dropna().apply(_fval).dropna()
                if len(all_excess) >= 10:
                    top_decile_cutoff = all_excess.quantile(0.90)
                    top_decile_mean = float(all_excess[all_excess >= top_decile_cutoff].mean())
                    if top_decile_mean > 0.02:  # +2pp floor
                        buy_excess = [_fval(r.get("excess_spy")) for r in buy_rows
                                      if _fval(r.get("excess_spy")) is not None]
                        if buy_excess:
                            mean_buy = float(np.mean(buy_excess))
                            raw_ratio = round(mean_buy / top_decile_mean, 4)
                            upside_reading = raw_ratio
                            upside_capture_val = round(min(max(raw_ratio, 0.0), 1.0), 4)
                            uc_maturity = "ready"
                    else:
                        upside_capture_note = "no_read: top-decile universe excess <= +2pp (flat-tape guard)"
        except Exception as exc:  # noqa: BLE001
            upside_capture_note = f"error: {exc}"
    else:
        if not floors_met:
            upside_capture_note = f"accruing: {raw_n}/{SENSOR_MIN_MATURED_ROWS} matured rows"

    # --- coverage_health ---
    # M1/M2: trailing-4wk unique tickers is a raw count; cannot normalize to [0, 1]
    # without a frozen baseline (SA-R4).  value=null, reading=count.  Sensor matures
    # only when the frozen_baseline is anchored (future SA-R4 PR).
    cov_mon = scoreboard.get("coverage_monitor", {})
    t4wk = cov_mon.get("trailing_4wk_buy_count")
    cov_note = (
        "M2: value=null until frozen_baseline anchored (SA-R4). "
        "Raw trailing-4wk count in 'reading'. "
        "Scoreboard coverage_monitor carries pre-maturity all-horizon diagnostic count."
    )
    if t4wk is None:
        cov_note = cov_mon.get("data_gap", "no data") or cov_note
    cov_maturity = "accruing"  # null until baseline frozen

    # --- missed_mover_rate ---
    # miss rate in [0, 1]; inverted to 1-rate so higher = better (orientation consistent).
    # Matures when: df_all has >=1 21d-horizon row with excess qualifying as episode.
    mmc = _missed_mover_census(df_all)
    mm_raw_rate = mmc.get("missed_mover_rate")  # higher = worse
    mm_val: float | None = None
    mm_maturity = "accruing"
    if mm_raw_rate is not None:
        mm_val = round(1.0 - mm_raw_rate, 4)  # invert: higher value = fewer misses = better
        mm_maturity = "ready"
    mm_note = mmc.get("data_gap") or mmc.get("note")

    # --- timing_quality ---
    # M1: median board_tenure_days is in days (raw count); cannot normalize to [0, 1]
    # without a reference distribution.  value=null, reading=median_days.
    timing_val = None
    timing_reading: float | None = None
    timing_note = None
    timing_maturity = "accruing"
    if floors_met and buy_rows:
        tenures = [_fval(r.get("board_tenure_days")) for r in buy_rows
                   if _fval(r.get("board_tenure_days")) is not None]
        n_late = sum(1 for r in buy_rows if r.get("process_fault") == "signaled_too_late")
        late_share = n_late / raw_n if raw_n > 0 else 0.0
        if tenures:
            timing_reading = round(float(np.median(tenures)), 2)
        timing_note = (
            f"M1: value=null (median tenure in days, not normalizable to [0,1] without "
            f"reference distribution). Raw reading in 'reading'. "
            f"late_share={late_share:.2%} ({n_late}/{raw_n} rows). "
            f"timing_basis: ['board_tenure'] (extension/ticks-since-cross clauses absent "
            f"from retro_grades schema — see M3 disclosure)."
        )
        timing_maturity = "ready"
    else:
        timing_note = (
            f"accruing: {raw_n}/{SENSOR_MIN_MATURED_ROWS} matured rows. "
            f"timing_basis: ['board_tenure']."
        )

    # --- process_integrity ---
    # Share of data_fault rows, inverted to (1 - fault_rate) so higher = better.
    # [0, 1] honest. Matures when: floors_met.
    pi_val = None
    pi_note = None
    pi_maturity = "accruing"
    if floors_met and raw_n > 0:
        n_data_fault = sum(1 for r in buy_rows if r.get("process_fault") == "data_fault")
        fault_rate = n_data_fault / raw_n
        pi_val = round(1.0 - fault_rate, 4)  # invert: higher = cleaner
        pi_maturity = "ready"
    else:
        pi_note = f"accruing: {raw_n}/{SENSOR_MIN_MATURED_ROWS} matured rows"

    sensors = {
        "hit_quality": _sensor("hit_quality", hit_quality_val, raw_n, effective_n,
                               maturity=hit_maturity, note=hit_quality_note),
        "upside_capture": _sensor("upside_capture", upside_capture_val, raw_n, effective_n,
                                  maturity=uc_maturity, note=upside_capture_note,
                                  extra=({"reading": upside_reading} if upside_reading is not None else {})),
        "coverage_health": _sensor(
            "coverage_health", None, raw_n, effective_n,
            maturity=cov_maturity, note=cov_note,
            extra={"reading": t4wk,  # raw count in reading (M1/M2 unit contract)
                   "trailing_4wk_buy_count": t4wk,
                   "frozen_baseline": cov_mon.get("frozen_baseline")}),
        "missed_mover_rate": _sensor("missed_mover_rate", mm_val, raw_n, effective_n,
                                     maturity=mm_maturity, note=mm_note,
                                     extra={"n_episodes": mmc.get("n_episodes"),
                                            "n_missed": mmc.get("n_missed"),
                                            "pipeline_recall": mmc.get("pipeline_recall"),
                                            "raw_miss_rate": mm_raw_rate}),
        "timing_quality": _sensor(
            "timing_quality", None, raw_n, effective_n,
            maturity=timing_maturity, note=timing_note,
            extra=({"reading": timing_reading,
                    "timing_basis": ["board_tenure"]}  # M3: only board_tenure_days wired
                   if timing_reading is not None else
                   {"reading": None, "timing_basis": ["board_tenure"]})),
        "process_integrity": _sensor("process_integrity", pi_val, raw_n, effective_n,
                                     maturity=pi_maturity, note=pi_note),
    }

    # Overall maturity: derived from per-sensor maturity (M1: each sensor matures independently)
    all_mat = {s["maturity"] for s in sensors.values()}
    if all_mat == {"ready"}:
        overall_maturity = "ready"
    elif "accruing" in all_mat and "ready" not in all_mat:
        overall_maturity = "accruing"
    else:
        overall_maturity = "partial"

    return {
        "schema": "metabolism.standout_fitness.v1",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "lobe": "site-us-standouts",
        "maturity": overall_maturity,
        "sensors": sensors,
        "authority": AUTHORITY_BLOCK,
        "notes": (
            f"US standout board fitness card. {raw_n}/{SENSOR_MIN_MATURED_ROWS} matured 21d rows. "
            f"Floors require {SENSOR_MIN_MATURED_ROWS} rows + {SENSOR_MIN_ENTRY_DATES} entry dates + "
            f"{SENSOR_MIN_NONOVERLAPPING_WINDOWS} non-overlapping windows spanning "
            f"{SENSOR_MIN_CALENDAR_MONTHS} calendar months. "
            f"Expected first-maturity read: ~2026-09-15. "
            f"All sensors display-context only; no signal-path authority. "
            f"M3 timing_basis=['board_tenure']: extension-percentile and ticks-since-cross "
            f"clauses cannot be computed (columns absent from retro_grades schema)."
        ),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_us(root: Path | None = None) -> dict:
    """Build US attribution artifacts. NEVER-RAISE. Returns status dict.

    Returns:
        {status: 'ok', ...}       — success
        {status: 'data_gap', ...} — input store absent
        {status: 'error', reason} — unexpected error, prior artifacts untouched
    """
    root = _root(root)

    # Check input store
    retro_path = _retro_path(root)
    if not retro_path.exists():
        log.warning("build_us: retro_grades.parquet not found at %s", retro_path)
        return {"status": "data_gap", "reason": "retro_grades.parquet absent"}

    try:
        return _build_us_impl(root, retro_path)
    except Exception as exc:  # noqa: BLE001
        log.exception("build_us: unexpected error: %s", exc)
        return {"status": "error", "reason": str(exc)}


def _build_us_impl(root: Path, retro_path: Path) -> dict:
    """Implementation — called only from build_us() which wraps all exceptions."""
    # Load retro_grades
    df_all = pd.read_parquet(retro_path)
    log.info("build_us: loaded %d retro_grades rows", len(df_all))

    # Filter to 21d horizon (primary ruler)
    df21 = df_all[df_all["horizon"] == 21].copy()
    log.info("build_us: %d rows at 21d horizon", len(df21))

    # Load near-miss store (degrade gracefully if absent)
    near_miss_df = _load_near_misses(root)
    log.info("build_us: loaded %d near-miss rows", len(near_miss_df))

    # Two-axis attribution
    new_attr_rows: list[dict] = []
    gate_suppressed_gap: str | None = None
    if not df21.empty:
        new_attr_rows, gate_suppressed_gap = _attribute_rows(df21, near_miss_df)
    elif not near_miss_df.empty:
        # No 21d rows to attribute, but check whether near_miss store has excess_spy
        # so we can surface the data_gap sentinel even before 21d rows mature (B2).
        _, gate_suppressed_gap = _check_gate_suppressed(
            {"ticker": None, "as_of": None}, near_miss_df
        )
    log.info("build_us: attributed %d rows", len(new_attr_rows))

    # Load existing sidecar (keep-first)
    attr_path = _attribution_path(root)
    existing_attr = pd.DataFrame()
    if attr_path.exists():
        try:
            existing_attr = pd.read_parquet(attr_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("build_us: could not read existing attribution sidecar: %s", exc)

    merged_attr = _merge_attribution_sidecar(existing_attr, new_attr_rows)

    # Write attribution sidecar
    if not merged_attr.empty:
        merged_attr.to_parquet(attr_path, index=False)
        log.info("build_us: wrote %d rows to %s", len(merged_attr), attr_path)

    # All attributed rows (new + existing) for scoreboard
    all_attr_rows = merged_attr.to_dict("records") if not merged_attr.empty else []

    # Evidence packs (append-only, keep-first)
    ev_path = _evidence_path(root)
    existing_ev_keys = _load_existing_evidence(ev_path)

    new_ev_count = 0
    if new_attr_rows and not df21.empty:
        # Build lookup from retro rows
        retro_lookup: dict[tuple[str, str, str], dict] = {}
        for _, row in df21.iterrows():
            key = (str(row.get("as_of", "")), str(row.get("ticker", "")),
                   str(row.get("lane", "")))
            retro_lookup[key] = row.to_dict()

        try:
            with ev_path.open("a", encoding="utf-8") as f:
                for attr in new_attr_rows:
                    key = (str(attr.get("as_of", "")), str(attr.get("ticker", "")),
                           str(attr.get("lane", "")))
                    if key in existing_ev_keys:
                        continue
                    retro_row = retro_lookup.get(key, {})
                    pack = _build_evidence_pack(retro_row, attr)
                    f.write(json.dumps(pack, default=str) + "\n")
                    new_ev_count += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("build_us: evidence pack write error: %s", exc)

    # Scoreboard (B2: pass gate_suppressed_gap so sentinel is visible when near_miss store lacks excess_spy)
    scoreboard = _build_scoreboard(all_attr_rows, df_all, gate_suppressed_gap=gate_suppressed_gap)
    sb_path = _scoreboard_path(root)
    sb_path.write_text(json.dumps(scoreboard, indent=2, default=str), encoding="utf-8")

    # Fitness card
    fitness_card = _build_fitness_card(all_attr_rows, scoreboard, df_all)
    fit_path = _fitness_path(root)
    fit_path.write_text(json.dumps(fitness_card, indent=2, default=str), encoding="utf-8")

    # State stamp
    state = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "last_graded_asof": str(df_all["as_of"].max()) if not df_all.empty else None,
        "rows_matured_total": len(df21),
        "rows_attributed_total": len(all_attr_rows),
        "new_attributed_this_run": len(new_attr_rows),
        "new_evidence_packs_this_run": new_ev_count,
        "schema": "standout_audit.state.v1",
    }
    state_path = _state_path(root)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    log.info("build_us: done. %d attributed rows, %d new evidence packs", len(all_attr_rows), new_ev_count)
    return {
        "status": "ok",
        "rows_matured_total": len(df21),
        "rows_attributed_total": len(all_attr_rows),
        "new_attributed_this_run": len(new_attr_rows),
        "fitness_maturity": fitness_card.get("maturity", "unknown"),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from lib.procutil import hard_exit

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description="SA-W1 standout audit organ")
    parser.add_argument("--us", action="store_true", help="Run US attribution build")
    parser.add_argument("--root", default=None, help="Repo root override")
    args = parser.parse_args()

    if args.us or not args.us:  # --us is the only mode; default to US
        result = build_us(root=args.root)
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") == "error":
            hard_exit(1)
        hard_exit(0)
