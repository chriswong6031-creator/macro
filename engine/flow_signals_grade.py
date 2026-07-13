"""engine/flow_signals_grade.py — Flow-event outcome grader (FS-R2, one-grader law).

Grades matured rows in data/flow_signals/ledger.parquet by computing underlying-
asset forward-return outcomes and writes them to data/flow_signals/grades.parquet.

ONE-GRADER LAW (FS-R2, masterplan):
  Imports and reuses engine/grading.py primitives (forward_metrics, fill_index,
  terminal_state, SPINE_HORIZONS). Does NOT re-implement triple-barrier.

HORIZON MAP (per FS-R2):
  dte_bucket      primary_horizon  secondary_horizon
  0d / 1_7d       5d               —
  8_30d / 31_90d  21d              —
  90p             63d              126d

DIVERGENCE FROM FIRE-LEDGER CONVENTION (documented per one-grader law):
  1. No "next-bar fill" offset correction for options-flow events: the event
     `session_date` is the trading day the flow was observed. We use the SAME
     session_date as the signal_date for grading.forward_metrics (which then
     finds the next available bar as the fill). This matches the fire-ledger
     fill convention (fill_index advances one bar past the signal bar).
  2. Direction-agnostic: the fire ledger stores raw forward returns WITHOUT
     conditioning on the soft `side` field. Direction semantics are decided at
     FS-3 prereg; the label is assigned there, not here.
  3. Premium-touch columns (prem_touch_50): nullable. Populated only if a
     usable EOD option-close source is trivially available. In the current
     implementation, no such source is available intraday, so these are always
     null. They are display columns only — never verdict currency (FS-R2).

SPLIT-SEAM GUARD:
  The price basis used (store.read("yahoo", ...) "close") is split+dividend-
  ADJUSTED. Real seams in this basis are from the stale-tail mixed-basis class:
  incremental append around a split leaves old rows unadjusted, causing a
  ratio jump at exactly the seam boundary. The guard targets this class.

  Detection: a bar-over-bar ratio r = close[t]/close[t-1] is a seam candidate
  iff (a) it is split-shaped: |log(r) - log(k)| < 0.03 OR |log(r) + log(k)| <
  0.03 for some integer split factor k ∈ {2,3,4,5,6,8,10,20} (i.e. ratio is
  within 3% log-distance of a known split fraction or its reciprocal), AND
  (b) it PERSISTS: the median of up to the 3 following bars stays within 10%
  multiplicative of close[t] (i.e. the move is not immediately reversed).

  Scan window starts at fill (the fill→fill+1 transition is included): slices
  close.iloc[fill : fill + max_h + 1] so that seams at the entry bar are caught.

  Genuine non-split-shaped gaps (e.g. a +45% earnings pop or a genuine large
  move) are NOT flagged — they grade normally. Accepted residual: a true
  persistent -50% price crash is indistinguishable from a missed 2:1 reverse-
  split seam and is conservatively nulled with reason_code='split_seam'.

  When a seam is detected, the outcome is nulled with reason_code='split_seam'.

PARTIAL-GRADE SEMANTICS (B1, 90p bucket):
  For the '90p' bucket, horizons are [63, 126]. If only the 63d horizon has
  matured, the row is written with graded_ok=False, reason_code='partial_matured'
  (retryable). The upsert loop in grade_matured() re-attempts non-ok rows on the
  next pass and overwrites them, eventually finalizing with 126d filled when
  graded_ok=True, reason_code='ok'.

SPY EXCESS:
  Excess-vs-SPY is computed as (ticker_fwd_ret - spy_fwd_ret) over the same
  horizon window. If SPY data is unavailable, spy_excess_* columns are null.

SINGLE WRITER LAW:
  Only this module writes data/flow_signals/grades.parquet. The build script
  (scripts/build_flow_signals.py) calls grade_matured() once per nightly run.
  Intraday lanes must not call this function (forward-ledger law).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.grading import (
    fill_index,
    forward_metrics,
    terminal_state,
    SPINE_HORIZONS,
    STOP_BARRIER,
    CUSHION_BARRIER,
    LIFTOFF_8,
    LIFTOFF_15,
    LIFTOFF_HORIZON_21,
    LIFTOFF_HORIZON_126,
    TerminalState,
)

log = logging.getLogger(__name__)

# ── horizon map ───────────────────────────────────────────────────────────────
# FS-R2: horizon anchored by dte_bucket; 90p gets a secondary 126d ruler.
_HORIZON_MAP: dict[str, list[int]] = {
    "0d":    [5],
    "1_7d":  [5],
    "8_30d": [21],
    "31_90d": [21],
    "90p":   [63, 126],
}
_PRIMARY_HORIZON_MAP: dict[str, int] = {k: v[0] for k, v in _HORIZON_MAP.items()}

# ── split-seam guard ──────────────────────────────────────────────────────────
# Known integer split factors whose ratio (or reciprocal) signals a stale-tail
# mixed-basis seam in the split+dividend-adjusted price store.
_SPLIT_FACTORS = [2, 3, 4, 5, 6, 8, 10, 20]
_LOG_SPLIT_FACTORS = [np.log(k) for k in _SPLIT_FACTORS]

# log-ratio proximity threshold for "split-shaped" classification (3%).
_SPLIT_LOG_TOL = 0.03

# Persistence check: median of up-to-3 following bars must stay within 10%
# multiplicatively of close[t] for the seam to count as persistent.
_PERSIST_FOLLOW_BARS = 3
_PERSIST_TOL = 0.10


def _has_split_seam(close: pd.Series, fill_iloc: int, max_h: int) -> bool:
    """Return True if the forward window [fill, fill+max_h] contains a suspected
    unrepaired stale-tail split seam.

    PRICE BASIS: store.read("yahoo") "close" is split+dividend-ADJUSTED.
    Seams in this basis arise from incremental append around a split that left
    old rows unadjusted — a stale-tail mixed-basis class.

    DETECTION (both conditions must hold):
      (a) Split-shaped: bar-over-bar log-ratio |log(r) - log(k)| < _SPLIT_LOG_TOL
          OR |log(r) + log(k)| < _SPLIT_LOG_TOL for some k ∈ _SPLIT_FACTORS.
          This matches the ratio being within 3% log-distance of a known split
          fraction (forward or reverse), WITHOUT flagging genuine non-split moves
          like a +45% earnings pop.
      (b) Persistent: median of up to _PERSIST_FOLLOW_BARS following bars
          stays within _PERSIST_TOL (10% multiplicative) of close[t].
          This filters brief spikes that self-correct.

    SCAN WINDOW: close.iloc[fill : fill + max_h + 1] — starts at fill so the
    fill→fill+1 transition is included (N6 fix: prior version started at fill+1).

    GENUINE GAPS PASS: non-split-shaped moves (e.g. +45% earnings) grade normally.
    ACCEPTED RESIDUAL: a true persistent -50% crash is indistinguishable from a
    missed 2:1 reverse-split seam and is conservatively nulled with 'split_seam'.
    """
    window = close.iloc[fill_iloc: fill_iloc + max_h + 1]
    if len(window) < 2:
        return False

    prices = window.values
    for i in range(1, len(prices)):
        p_prev = prices[i - 1]
        p_curr = prices[i]
        if p_prev <= 0 or p_curr <= 0:
            continue
        log_r = np.log(p_curr / p_prev)
        # (a) split-shaped check
        split_shaped = any(
            abs(log_r - lk) < _SPLIT_LOG_TOL or abs(log_r + lk) < _SPLIT_LOG_TOL
            for lk in _LOG_SPLIT_FACTORS
        )
        if not split_shaped:
            continue
        # (b) persistence check: following bars stay near p_curr
        follow = prices[i + 1: i + 1 + _PERSIST_FOLLOW_BARS]
        if len(follow) == 0:
            # At the edge of the window; treat as persistent (conservative).
            return True
        med = float(np.median(follow))
        if abs(med / p_curr - 1.0) <= _PERSIST_TOL:
            return True
    return False


# ── price series loader ───────────────────────────────────────────────────────

def _load_close(ticker: str) -> pd.Series | None:
    """Load close series for ticker from data/yahoo/{TICKER}.parquet.

    Returns a DatetimeIndex-indexed Series. None if unavailable.
    Catches all errors (INERT — missing store must not crash the grader).
    """
    try:
        from lib import store
        df = store.read("yahoo", ticker.upper())
        if df is None or df.empty or "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index()
        if s.empty:
            return None
        return s
    except Exception as e:  # noqa: BLE001
        log.debug("flow_signals_grade: load_close(%s) failed: %s", ticker, e)
        return None


_SPY_CLOSE_CACHE: pd.Series | None = None


def _spy_close() -> pd.Series | None:
    """Return cached SPY close series."""
    global _SPY_CLOSE_CACHE
    if _SPY_CLOSE_CACHE is None:
        _SPY_CLOSE_CACHE = _load_close("SPY")
    return _SPY_CLOSE_CACHE


# ── ledger / grades paths ─────────────────────────────────────────────────────

def _ledger_path() -> Path:
    from lib import config
    return config.data_dir() / "flow_signals" / "ledger.parquet"


def _grades_path() -> Path:
    from lib import config
    p = config.data_dir() / "flow_signals"
    p.mkdir(parents=True, exist_ok=True)
    return p / "grades.parquet"


# ── grade one event ───────────────────────────────────────────────────────────

def _grade_event(
    event_id: str,
    ticker: str,
    session_date: str,
    dte_bucket: str,
    close: pd.Series,
    spy_close: pd.Series | None,
    today: date | None = None,
) -> dict[str, Any]:
    """Grade one event. Returns a dict of outcome columns.

    Direction-agnostic: stores the raw underlying move; the `side` label
    semantics are decided at FS-3 prereg, not here.

    For '90p' bucket only: supports partial-grade semantics (B1). If only the
    primary (63d) horizon has matured, returns graded_ok=False,
    reason_code='partial_matured' — retryable; the upsert loop will overwrite
    on the next pass once 126d matures. When all horizons mature, returns
    graded_ok=True, reason_code='ok'.

    All outcome fields are None when the row is not yet matured or grading
    fails. Never raises (INERT).
    """
    horizons = _HORIZON_MAP.get(dte_bucket, [21])

    base: dict[str, Any] = {
        "event_id":    event_id,
        "graded_at":   datetime.now(timezone.utc).isoformat(),
        "graded_ok":   False,
        "reason_code": None,
        "entry_price": None,
        "fill_date":   None,
    }
    # Pre-populate all outcome columns with None
    for h in [5, 21, 63, 126]:
        for suffix in ("fwd_ret", "fwd_mfe", "fwd_mdd", "spy_excess"):
            base[f"{suffix}_{h}"] = None
    base["terminal_state_clean8_21"]  = None
    base["terminal_state_clean15_126"] = None
    base["prem_touch_50"] = None  # display-only; always null in FS-0

    # N5: PIT defense — truncate close to bars on or before today.
    if today is not None:
        cutoff = pd.Timestamp(today)
        close = close[close.index <= cutoff]
        if spy_close is not None:
            spy_close = spy_close[spy_close.index <= cutoff]

    # Fill index
    try:
        fill = fill_index(close, session_date)
    except Exception as e:  # noqa: BLE001
        base["reason_code"] = f"fill_error: {e}"
        return base

    if fill is None:
        base["reason_code"] = "not_yet_matured"
        return base

    # B1: compute which horizons have matured
    primary_h = _PRIMARY_HORIZON_MAP.get(dte_bucket, 21)
    matured = [h for h in horizons if fill + h < len(close)]

    if primary_h not in matured:
        # Primary horizon not yet reached → not yet matured
        base["reason_code"] = "not_yet_matured"
        return base

    # Split-seam guard: check the longest AVAILABLE matured horizon window.
    max_h = max(matured)
    if _has_split_seam(close, fill, max_h):
        base["reason_code"] = "split_seam"
        base["graded_ok"] = True  # intentional null; not a grading failure
        return base

    # Forward metrics only over matured horizons (absolute)
    try:
        metrics = forward_metrics(close, session_date, horizons=tuple(matured))
    except Exception as e:  # noqa: BLE001
        base["reason_code"] = f"forward_metrics_error: {e}"
        return base

    base["entry_price"] = metrics.get("entry_price")
    base["fill_date"] = metrics.get("fill_date")

    for h in matured:
        base[f"fwd_ret_{h}"]  = metrics.get(f"fwd_ret_{h}")
        base[f"fwd_mfe_{h}"]  = metrics.get(f"fwd_mfe_{h}")
        base[f"fwd_mdd_{h}"]  = metrics.get(f"fwd_mdd_{h}")

    # Excess vs SPY (only over matured horizons)
    if spy_close is not None:
        try:
            spy_metrics = forward_metrics(spy_close, session_date, horizons=tuple(matured))
            for h in matured:
                ticker_ret = metrics.get(f"fwd_ret_{h}")
                spy_ret = spy_metrics.get(f"fwd_ret_{h}")
                if ticker_ret is not None and spy_ret is not None:
                    base[f"spy_excess_{h}"] = ticker_ret - spy_ret
        except Exception:  # noqa: BLE001
            pass  # spy excess stays null; not fatal

    # Terminal state — clean8_21 (21d horizon, rotational); only if 21 matured
    if 21 in matured:
        try:
            ts21 = terminal_state(
                close, session_date,
                liftoff_mult=LIFTOFF_8,
                liftoff_horizon=LIFTOFF_HORIZON_21,
                stop_mult=STOP_BARRIER,
                cushion_mult=CUSHION_BARRIER,
            )
            if ts21.get("state") is not None:
                base["terminal_state_clean8_21"] = ts21["state"]
        except Exception:  # noqa: BLE001
            pass

    # Terminal state — clean15_126 (126d horizon, positional; only if 126 matured)
    if 126 in matured:
        try:
            ts126 = terminal_state(
                close, session_date,
                liftoff_mult=LIFTOFF_15,
                liftoff_horizon=LIFTOFF_HORIZON_126,
                stop_mult=STOP_BARRIER,
                cushion_mult=CUSHION_BARRIER,
            )
            if ts126.get("state") is not None:
                base["terminal_state_clean15_126"] = ts126["state"]
        except Exception:  # noqa: BLE001
            pass

    # B1: finalize graded_ok based on whether ALL horizons matured
    if set(matured) >= set(horizons):
        base["graded_ok"] = True
        base["reason_code"] = "ok"
    else:
        # Some horizons (e.g. 126d for 90p bucket) not yet matured
        base["graded_ok"] = False
        base["reason_code"] = "partial_matured"
    return base


# ── grade_matured ─────────────────────────────────────────────────────────────

def grade_matured(
    today: date | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Grade all ungraded + not-yet-matured ledger rows whose horizon has passed.

    Returns a summary dict: {n_ledger, n_already_graded, n_graded_ok,
                             n_split_seam, n_not_matured, n_errors, elapsed_sec}.

    Behavior:
      - Reads ledger.parquet; reads existing grades.parquet (if any).
      - For each ledger row not already graded with graded_ok=True,
        attempts to grade it.
      - Upserts: if a row was previously graded with reason_code='not_yet_matured'
        or similar transient reason, it is re-attempted and overwritten on success.
      - Split-seam rows are written with graded_ok=True and reason_code='split_seam'
        so they are not re-attempted (the seam is stable, not transient).
      - Appends / upserts into data/flow_signals/grades.parquet (single writer).
    """
    import time
    t0 = time.perf_counter()
    today = today or date.today()

    summary: dict[str, Any] = {
        "n_ledger": 0, "n_already_graded": 0,
        "n_graded_ok": 0, "n_split_seam": 0,
        "n_not_matured": 0, "n_errors": 0,
        "elapsed_sec": 0.0,
    }

    ledger_path = _ledger_path()
    grades_path = _grades_path()

    if not ledger_path.exists():
        log.info("flow_signals_grade: no ledger found — nothing to grade")
        return summary

    try:
        ledger = pd.read_parquet(ledger_path)
    except Exception as e:  # noqa: BLE001
        log.error("flow_signals_grade: ledger read failed: %s", e)
        return summary

    summary["n_ledger"] = len(ledger)

    # Load existing grades
    # Skip re-attempting rows that are already finalized (graded_ok=True).
    # 'partial_matured' rows (graded_ok=False) ARE re-attempted so their
    # secondary horizons (e.g. 126d for 90p) fill in on the next pass.
    graded_ids: set[str] = set()
    existing_grades: pd.DataFrame | None = None
    if grades_path.exists():
        try:
            existing_grades = pd.read_parquet(grades_path)
            # Only finalized rows (graded_ok=True) are excluded from re-attempts
            ok_mask = existing_grades["graded_ok"].astype(bool)
            graded_ids = set(existing_grades.loc[ok_mask, "event_id"].astype(str).tolist())
        except Exception as e:  # noqa: BLE001
            log.warning("flow_signals_grade: could not read existing grades: %s", e)

    summary["n_already_graded"] = len(graded_ids)

    # Determine rows to attempt
    to_grade = ledger[~ledger["event_id"].astype(str).isin(graded_ids)].copy()
    if max_rows is not None:
        to_grade = to_grade.head(max_rows)

    if to_grade.empty:
        log.info("flow_signals_grade: all %d rows already graded OK", len(graded_ids))
        summary["elapsed_sec"] = round(time.perf_counter() - t0, 2)
        return summary

    spy_close = _spy_close()

    # Cache close series per ticker
    close_cache: dict[str, pd.Series | None] = {}
    new_grade_rows: list[dict] = []

    for _, row in to_grade.iterrows():
        event_id = str(row.get("event_id", ""))
        ticker = str(row.get("root", "")).upper()
        session_date = str(row.get("session_date", ""))
        dte_bucket = str(row.get("dte_bucket", "8_30d"))
        # side field is intentionally not used here; direction semantics are
        # decided at FS-3 prereg (see direction-agnostic docstring in _grade_event)

        if not ticker or not session_date:
            summary["n_errors"] += 1
            continue

        if ticker not in close_cache:
            close_cache[ticker] = _load_close(ticker)
        close = close_cache[ticker]

        if close is None:
            grade_row = {
                "event_id": event_id,
                "graded_at": datetime.now(timezone.utc).isoformat(),
                "graded_ok": False,
                "reason_code": "no_price_data",
                **{f"{k}_{h}": None
                   for h in [5, 21, 63, 126]
                   for k in ["fwd_ret", "fwd_mfe", "fwd_mdd", "spy_excess"]},
                "terminal_state_clean8_21": None,
                "terminal_state_clean15_126": None,
                "prem_touch_50": None,
                "entry_price": None,
                "fill_date": None,
            }
            new_grade_rows.append(grade_row)
            summary["n_errors"] += 1
            continue

        grade_row = _grade_event(event_id, ticker, session_date, dte_bucket,
                                 close, spy_close, today=today)
        rc = grade_row.get("reason_code", "")
        if rc == "ok":
            summary["n_graded_ok"] += 1
        elif rc == "split_seam":
            summary["n_split_seam"] += 1
        elif rc in ("not_yet_matured", "partial_matured",
                    "fill_error: fill bar not found or no next bar"):
            summary["n_not_matured"] += 1
        elif grade_row.get("graded_ok") is False:
            summary["n_errors"] += 1
        new_grade_rows.append(grade_row)

    if new_grade_rows:
        _write_grades(grades_path, existing_grades, new_grade_rows)
        log.info("flow_signals_grade: graded %d rows (ok=%d seam=%d not_matured=%d err=%d)",
                 len(new_grade_rows), summary["n_graded_ok"],
                 summary["n_split_seam"], summary["n_not_matured"], summary["n_errors"])

    summary["elapsed_sec"] = round(time.perf_counter() - t0, 2)
    return summary


def _write_grades(grades_path: Path,
                  existing: pd.DataFrame | None,
                  new_rows: list[dict]) -> None:
    """Upsert new_rows into grades.parquet. event_id is the key; new rows win."""
    new_df = pd.DataFrame(new_rows)
    if existing is not None and not existing.empty:
        # Remove rows that are being overwritten (event_ids in new_rows)
        new_ids = set(new_df["event_id"].astype(str).tolist())
        keep = existing[~existing["event_id"].astype(str).isin(new_ids)]
        merged = pd.concat([keep, new_df], ignore_index=True)
    else:
        merged = new_df

    tmp = grades_path.with_suffix(".tmp.parquet")
    try:
        merged.to_parquet(tmp, index=False)
        tmp.rename(grades_path)
    except Exception as e:  # noqa: BLE001
        log.error("flow_signals_grade: grades write failed: %s", e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
