"""BD-AVOID-1 Phase-1 Stamper — Mac-side off-render ops lane.

SINGLE WRITER DECLARATION: This script is the ONLY writer of
  data/research/bd_avoid1_ledger.parquet
No other script, engine module, or CI job writes to this path.
Parallel runs are prevented by a file lock (data/research/.bd_avoid1_stamper.lock).

Authority:
  research/short_side/BD_AVOID1_PHASE1_PREREG.md (pre-registered 2026-07-06;
  frozen gates; thresholds are read from dump_breakdown_events.py, NOT redefined here).
  research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md §6.3 (Fable-frozen spec).
  research/short_side/BD_PHASE0_PREREG.md (event definitions frozen here).

What this script does:
  1. Reads the existing ledger (if any) to find the last stamped date.
  2. Detects NEW BD-2 and BD-3 events since last stamp (PIT: only data knowable
     at stamp date — replay_boarded is current; prices from massive_stock_day).
  3. Writes 3 seeded PIT random-bar control rows per new event (is_control=True).
  4. Appends new event + control rows to data/research/bd_avoid1_ledger.parquet.
  5. Grades matured rows (h21=21 bars, h126=126 bars) in the same pass.
  6. After writing, performs a narrow git commit:
       git add data/research/bd_avoid1_ledger.parquet
       git commit -m "data(short_side): bd_avoid1 ledger stamp {date}"

This script NEVER runs in CI. It is invoked:
  - By ops/launchd/com.macro.bd_avoid1_stamper.plist (weekday post-close 17:00 ET).
  - Manually: python -m scripts.research.bd_avoid1_stamper [--dry-run]

Derives events by IMPORTING detect_bd2, detect_bd3, and their frozen constants
from scripts.research.dump_breakdown_events — never re-implementing them.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap (canonical pattern from scripts/replay_standout_pipeline.py)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]  # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Imports from Phase-0 — FROZEN event detectors and their constants
# ---------------------------------------------------------------------------
from scripts.research.dump_breakdown_events import (  # noqa: E402
    detect_bd2,
    detect_bd3,
    _collapse_episodes,
    _liq_ok_at,
    _read_massive_ticker,
    _read_massive_ohlcv,
    build_universe,
    ERA_START,
    ERA_PRIOR_BARS_REQUIRED,
    LIQ_MIN_ADV_DOLLAR,
    LIQ_MIN_PRICE,
    EPISODE_COLLAPSE_BARS,
    CANONICAL_DATA,
    REPLAY_BOARDED,
    YAHOO_DIR,
)
from engine.grading import (  # noqa: E402
    fill_index,
    forward_metrics,
    terminal_state,
    terminal_state_short,
    TerminalState,
    TerminalStateShort,
    LIFTOFF_8,
    LIFTOFF_HORIZON_21,
    LIFTOFF_15,
    LIFTOFF_HORIZON_126,
    SHORT_ADVERSE_MULT,
    SHORT_FAVORABLE_MULT_21,
    SHORT_FAVORABLE_MULT_126,
)
from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.vintage_stamp import vintage_stamp  # noqa: E402

try:
    from scripts.replay_standout_pipeline import split_adjust, MASSIVE_DIR  # noqa: E402
except ImportError:
    from replay_standout_pipeline import split_adjust, MASSIVE_DIR  # noqa: E402

log = logging.getLogger("bd_avoid1_stamper")

# ---------------------------------------------------------------------------
# Paths (Mac-local only — never on CI)
# ---------------------------------------------------------------------------
DATA_DIR      = CANONICAL_DATA
RESEARCH_DIR  = DATA_DIR / "research"
LEDGER_PATH   = RESEARCH_DIR / "bd_avoid1_ledger.parquet"
LOCK_PATH     = RESEARCH_DIR / ".bd_avoid1_stamper.lock"
EDGAR_DEAD_COV = DATA_DIR / "edgar" / "_dead_name_coverage.json"

# Registration date — no events before this date feed the forward verdict.
REGISTRATION_DATE = pd.Timestamp("2026-07-06")

# Grading horizons
GRADE_HORIZONS = (21, 126)

# Control ratio (prereg §4)
CONTROL_RATIO = 3

# Definitions processed by this stamper (BD-1 is excluded — Phase-0 only)
ACTIVE_DEFINITIONS = ("BD-2", "BD-3")


# ===========================================================================
# 1. Ledger I/O
# ===========================================================================

def _load_ledger(path: Path | None = None) -> pd.DataFrame:
    """Load existing ledger or return empty DataFrame with correct schema."""
    p = path or LEDGER_PATH
    if not p.exists():
        return _empty_ledger()
    try:
        df = pd.read_parquet(p)
        return df
    except Exception as e:
        log.warning("Failed to read existing ledger: %s — starting from empty", e)
        return _empty_ledger()


def _empty_ledger() -> pd.DataFrame:
    """Empty DataFrame with the ledger schema (prereg §9)."""
    cols = [
        "event_id", "ticker", "definition", "event_date", "fill_date",
        "entry_price", "is_control", "control_seed",
        "stamped_at", "pit_stamp_date",
        "long_state_clean8_21", "long_state_clean15_126",
        "short_state_short21", "short_state_short126",
        "fwd_ret_21", "fwd_mdd_21", "fwd_mfe_21",
        "fwd_ret_126", "fwd_mdd_126", "fwd_mfe_126",
        "censored", "survivorship_biased", "vintage_stamp",
    ]
    return pd.DataFrame(columns=cols)


def _existing_event_ids(df: pd.DataFrame) -> set[str]:
    """Return set of event_ids already in the ledger."""
    if "event_id" not in df.columns or len(df) == 0:
        return set()
    return set(df["event_id"].dropna().astype(str).tolist())


def _last_stamp_date(df: pd.DataFrame) -> pd.Timestamp:
    """Return the last pit_stamp_date in the ledger, or REGISTRATION_DATE - 1 day."""
    if "pit_stamp_date" not in df.columns or len(df) == 0:
        # Start from day before registration so first run captures registration-day events
        return REGISTRATION_DATE - pd.Timedelta(days=1)
    dates = pd.to_datetime(df["pit_stamp_date"].dropna(), errors="coerce").dropna()
    if dates.empty:
        return REGISTRATION_DATE - pd.Timedelta(days=1)
    return dates.max()


# ===========================================================================
# 2. Event ID construction (stable, unique per prereg §9)
# ===========================================================================

def _make_event_id(ticker: str, definition: str, event_date: pd.Timestamp) -> str:
    return f"{ticker}|{definition}|{event_date.date().isoformat()}"


# ===========================================================================
# 3. Seeded control sampling (prereg §4 — seed derived from event_id)
# ===========================================================================

def _seed_for_event(event_id: str) -> int:
    """Deterministic seed from event_id: md5 first 8 hex chars → int mod 2^31."""
    return int(hashlib.md5(event_id.encode()).hexdigest()[:8], 16) % (2 ** 31)


def _sample_control_dates(
    ticker: str,
    close: pd.Series,
    raw_df: pd.DataFrame | None,
    event_ts: pd.Timestamp,
    existing_event_dates: set[pd.Timestamp],
    seed: int,
    used_control_dates: set[pd.Timestamp] | None = None,
) -> list[pd.Timestamp]:
    """Sample CONTROL_RATIO random non-event bars for one event (year-stratified).

    Matching: same ticker, same calendar year as the event, non-event bars,
    passing the same liquidity + ERA gates.  Seed is derived from event_id.

    ``used_control_dates`` excludes dates already chosen as controls in this
    run, preventing two events from independently sampling the same bar and
    producing a duplicate control event_id.
    """
    rng = np.random.default_rng(seed)
    yr = event_ts.year
    excluded = existing_event_dates | (used_control_dates or set())

    eligible: list[int] = []
    for i, ts in enumerate(close.index):
        if ts < ERA_START:
            continue
        if i < ERA_PRIOR_BARS_REQUIRED:
            continue
        if ts.year != yr:
            continue
        if ts in excluded:
            continue
        if raw_df is not None and not _liq_ok_at(close, raw_df, i):
            continue
        eligible.append(i)

    if not eligible:
        # Fall back to ±1 year
        for i, ts in enumerate(close.index):
            if ts < ERA_START or i < ERA_PRIOR_BARS_REQUIRED:
                continue
            if abs(ts.year - yr) > 1:
                continue
            if ts in excluded:
                continue
            if raw_df is not None and not _liq_ok_at(close, raw_df, i):
                continue
            eligible.append(i)

    if not eligible:
        return []

    n_draw = min(CONTROL_RATIO, len(eligible))
    chosen_indices = rng.choice(eligible, size=n_draw, replace=False)
    return [close.index[i] for i in chosen_indices]


# ===========================================================================
# 4. Grading one event row
# ===========================================================================

def _grade_row(
    ticker: str,
    event_ts: pd.Timestamp,
    close: pd.Series,
    definition: str,
    is_control: bool,
    control_seed: int | None,
    stamp_date: str,
    vstamp: dict,
) -> dict[str, Any]:
    """Build one ledger row for an event or control bar.

    Grades both long-side (verdict-feeding: clean8_21) and short-side (quarantined)
    at horizons 21 and 126 if price plane has sufficient bars.
    """
    event_id = _make_event_id(ticker, definition if not is_control else "CONTROL", event_ts)
    row: dict[str, Any] = {
        "event_id":       event_id,
        "ticker":         ticker,
        "definition":     definition,
        "event_date":     str(event_ts.date()),
        "fill_date":      None,
        "entry_price":    None,
        "is_control":     is_control,
        "control_seed":   control_seed,
        "stamped_at":     datetime.now(timezone.utc).isoformat(),
        "pit_stamp_date": stamp_date,
        "long_state_clean8_21":    None,
        "long_state_clean15_126":  None,
        "short_state_short21":     None,
        "short_state_short126":    None,
        "fwd_ret_21":  None,
        "fwd_mdd_21":  None,
        "fwd_mfe_21":  None,
        "fwd_ret_126": None,
        "fwd_mdd_126": None,
        "fwd_mfe_126": None,
        "censored":          False,
        "survivorship_biased": True,
        "vintage_stamp":   json.dumps(vstamp, default=str),
    }

    # Fill bar
    fi = fill_index(close, event_ts)
    if fi is None:
        row["censored"] = True
        return row

    row["fill_date"]   = str(close.index[fi].date())
    row["entry_price"] = float(close.iloc[fi])

    # Long-side (clean8_21 is verdict-feeding; clean15_126 is recorded)
    for lm, lh, col in (
        (LIFTOFF_8,  LIFTOFF_HORIZON_21,  "long_state_clean8_21"),
        (LIFTOFF_15, LIFTOFF_HORIZON_126, "long_state_clean15_126"),
    ):
        try:
            ts_long = terminal_state(close, event_ts, liftoff_mult=lm, liftoff_horizon=lh)
            row[col] = ts_long["state"]
        except Exception:
            pass

    # Short-side (quarantined — no verdict criteria, RUL-3)
    for sh_horiz, sh_fav_mult, col in (
        (21,  SHORT_FAVORABLE_MULT_21,  "short_state_short21"),
        (126, SHORT_FAVORABLE_MULT_126, "short_state_short126"),
    ):
        try:
            ts_short = terminal_state_short(
                close, event_ts,
                adverse_mult=SHORT_ADVERSE_MULT,
                favorable_mult=sh_fav_mult,
                horizon=sh_horiz,
            )
            row[col] = ts_short["state"]
        except Exception:
            pass

    # Forward metrics
    try:
        fm = forward_metrics(close, event_ts, horizons=list(GRADE_HORIZONS))
        for h in GRADE_HORIZONS:
            row[f"fwd_ret_{h}"]  = fm.get(f"fwd_ret_{h}")
            row[f"fwd_mdd_{h}"]  = fm.get(f"fwd_mdd_{h}")
            row[f"fwd_mfe_{h}"]  = fm.get(f"fwd_mfe_{h}")
    except Exception:
        row["censored"] = True

    return row


# ===========================================================================
# 5. Re-grade matured rows in the existing ledger
# ===========================================================================

def _regrade_ungraded_rows(
    df: pd.DataFrame,
    stamp_date: str,
    vstamp: dict,
) -> pd.DataFrame:
    """Fill in grades for rows where long_state_clean8_21 is still None.

    Returns the updated DataFrame (in-place modification).
    """
    if len(df) == 0:
        return df

    ungraded_mask = df["long_state_clean8_21"].isna()
    if not ungraded_mask.any():
        return df

    log.info("Re-grading %d ungraded rows...", int(ungraded_mask.sum()))

    # Group by ticker for efficiency
    ungr = df[ungraded_mask].copy()
    updated = 0
    for ticker, grp in ungr.groupby("ticker"):
        close = _read_massive_ticker(str(ticker))
        if close is None:
            continue
        for idx in grp.index:
            event_date_str = df.at[idx, "event_date"]
            try:
                event_ts = pd.Timestamp(event_date_str)
            except Exception:
                continue

            defn = df.at[idx, "definition"]
            is_ctrl = bool(df.at[idx, "is_control"])
            ctrl_seed = df.at[idx, "control_seed"]

            # Long-side terminal states
            for lm, lh, col in (
                (LIFTOFF_8,  LIFTOFF_HORIZON_21,  "long_state_clean8_21"),
                (LIFTOFF_15, LIFTOFF_HORIZON_126, "long_state_clean15_126"),
            ):
                try:
                    ts_long = terminal_state(close, event_ts, liftoff_mult=lm, liftoff_horizon=lh)
                    if ts_long["state"] is not None:
                        df.at[idx, col] = ts_long["state"]
                except Exception:
                    pass

            # Short-side
            for sh_horiz, sh_fav_mult, col in (
                (21,  SHORT_FAVORABLE_MULT_21,  "short_state_short21"),
                (126, SHORT_FAVORABLE_MULT_126, "short_state_short126"),
            ):
                try:
                    ts_short = terminal_state_short(
                        close, event_ts,
                        adverse_mult=SHORT_ADVERSE_MULT,
                        favorable_mult=sh_fav_mult,
                        horizon=sh_horiz,
                    )
                    if ts_short["state"] is not None:
                        df.at[idx, col] = ts_short["state"]
                except Exception:
                    pass

            # Forward metrics
            try:
                fm = forward_metrics(close, event_ts, horizons=list(GRADE_HORIZONS))
                for h in GRADE_HORIZONS:
                    for metric in ("fwd_ret", "fwd_mdd", "fwd_mfe"):
                        col = f"{metric}_{h}"
                        v = fm.get(col)
                        if v is not None:
                            df.at[idx, col] = v
            except Exception:
                pass

            updated += 1

    log.info("Re-grading complete: %d rows updated", updated)
    return df


# ===========================================================================
# 6. Per-ticker event detection (new events only, post-registration)
# ===========================================================================

def _detect_new_events(
    ticker: str,
    close: pd.Series,
    raw_df: pd.DataFrame | None,
    existing_event_ids: set[str],
    last_stamp: pd.Timestamp,
) -> dict[str, list[pd.Timestamp]]:
    """Detect new BD-2 and BD-3 events for one ticker since last_stamp.

    PIT constraint: only events after last_stamp AND after REGISTRATION_DATE.
    The detector functions are imported from dump_breakdown_events (frozen thresholds).
    """
    # PIT lower bound: the later of registration date and last stamp
    pit_lower = max(REGISTRATION_DATE, last_stamp)

    events_by_def: dict[str, list[pd.Timestamp]] = {}

    for defn, detect_fn in (("BD-2", detect_bd2), ("BD-3", detect_bd3)):
        try:
            raw_events = detect_fn(ticker, close, raw_df)
        except Exception as e:
            log.debug("detect_%s(%s) failed: %s", defn, ticker, e)
            events_by_def[defn] = []
            continue

        # Episode collapse (same as Phase-0)
        collapsed = _collapse_episodes(raw_events, close)

        # Filter: new events only (after PIT lower bound, not already in ledger)
        new_events: list[pd.Timestamp] = []
        for ts in collapsed:
            if ts <= pit_lower:
                continue
            eid = _make_event_id(ticker, defn, ts)
            if eid in existing_event_ids:
                continue
            new_events.append(ts)

        events_by_def[defn] = new_events

    return events_by_def


# ===========================================================================
# 7. Vintage stamp builder
# ===========================================================================

def _build_vintage_stamp(n_universe: int) -> dict:
    """Build the 8-field vintage stamp for this stamper run."""
    dead_name_pct: float | None = None
    degraded = False
    try:
        if EDGAR_DEAD_COV.exists():
            cov = json.loads(EDGAR_DEAD_COV.read_text())
            for frac_key in ("price_coverage_frac", "coverage_frac"):
                if frac_key in cov and cov[frac_key] is not None:
                    dead_name_pct = float(cov[frac_key]) * 100.0
                    break
            if dead_name_pct is None:
                v = cov.get("coverage_pct")
                dead_name_pct = float(v) if v is not None else None
    except Exception:
        degraded = True

    return vintage_stamp(
        price_plane_id="massive_stock_day_v2",
        adjustment_mode="split_adjust_price_only",
        universe_as_of=date.today().isoformat(),
        frame="era_law_2021-07-06_plus",
        survivorship_biased=True,
        coverage_frac=1.0,
        dead_name_coverage_pct=dead_name_pct,
        era_law_cohort="forward_oos_2026-07-06_plus",
    )


# ===========================================================================
# 8. TrialLedger registration
# ===========================================================================

def _ensure_trial_ledger(data_dir: Path) -> None:
    """Log declared budget for BD-AVOID-1 Phase-1 forward trials to the family ledger.

    2 trials: BD-2 and BD-3 forward avoid-long verdicts.
    Idempotent (TrialLedger deduplicates by content hash).
    Must be called BEFORE any ledger write.
    """
    ledger_path = data_dir / "trial_ledger.jsonl"
    tl = TrialLedger(path=ledger_path)
    tl.log_declared_budget(
        2,
        family="short_side",
        reason=(
            "BD-AVOID-1 Phase-1 forward: 2 trials (BD-2 and BD-3 forward avoid-long verdicts); "
            "compensating gate >=8pp; derived_from_surface=bd_phase0; "
            "prereg: research/short_side/BD_AVOID1_PHASE1_PREREG.md"
        ),
    )
    log.info("TrialLedger: declared_budget(2, family='short_side') logged (idempotent)")


# ===========================================================================
# 9. Narrow git commit
# ===========================================================================

def _narrow_commit(ledger_path: Path, stamp_date: str, dry_run: bool) -> bool:
    """Narrow git add + commit for the ledger (single-file commit per sentinel-gap law).

    Runs from the repo root (not a worktree-relative path).
    Returns True on success.
    """
    if dry_run:
        log.info("DRY RUN: would commit %s", ledger_path)
        return True

    repo_root = str(_ROOT)
    rel_path = str(ledger_path.relative_to(_ROOT))

    try:
        # Stage only the ledger
        result = subprocess.run(
            ["git", "add", rel_path],
            cwd=repo_root, capture_output=True, text=True,
        )
        if result.returncode != 0:
            log.warning("git add failed: %s", result.stderr[:400])
            return False

        # Check if there is anything to commit
        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_root, capture_output=True,
        )
        if diff_result.returncode == 0:
            log.info("No changes to commit (ledger unchanged)")
            return True

        # Narrow commit
        msg = f"data(short_side): bd_avoid1 ledger stamp {stamp_date}"
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_root, capture_output=True, text=True,
        )
        if result.returncode != 0:
            log.warning("git commit failed: %s", result.stderr[:400])
            return False

        log.info("Narrow commit OK: %s", msg)
        return True

    except Exception as e:
        log.warning("git commit exception: %s", e)
        return False


# ===========================================================================
# 10. Main stamper run
# ===========================================================================

def run(
    data_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Main stamper entry point.

    Returns a summary dict with n_new_events, n_new_controls, n_regraded.
    """
    if data_dir is None:
        data_dir = DATA_DIR
    research_dir = data_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = research_dir / "bd_avoid1_ledger.parquet"
    lock_path   = research_dir / ".bd_avoid1_stamper.lock"

    t0 = time.time()
    stamp_date = date.today().isoformat()

    # File lock (single-writer enforcement)
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        raise RuntimeError(
            "bd_avoid1_stamper: another instance is running (lock held). Aborting."
        )

    try:
        # ----------------------------------------------------------------
        # Step 0: Register trial budget BEFORE any ledger write (prereg §1)
        # ----------------------------------------------------------------
        _ensure_trial_ledger(data_dir)

        # ----------------------------------------------------------------
        # Step 1: Load existing ledger
        # ----------------------------------------------------------------
        existing_df = _load_ledger(ledger_path)
        existing_ids = _existing_event_ids(existing_df)
        last_stamp = _last_stamp_date(existing_df)
        log.info(
            "Ledger: %d existing rows, %d event ids, last_stamp=%s",
            len(existing_df), len(existing_ids), last_stamp.date(),
        )

        # ----------------------------------------------------------------
        # Step 2: Build vintage stamp
        # ----------------------------------------------------------------
        universe = build_universe()
        vstamp = _build_vintage_stamp(len(universe))

        # ----------------------------------------------------------------
        # Step 3: Detect new events per ticker
        # ----------------------------------------------------------------
        new_rows: list[dict[str, Any]] = []
        n_new_events = 0
        n_new_controls = 0
        # Tracks control bar dates chosen within this run (across all tickers /
        # definitions) so that _sample_control_dates can exclude them, preventing
        # two events from independently sampling the same date and producing a
        # duplicate control event_id.  Per-ticker exclusion (not globally keyed by
        # ticker) is intentionally conservative: it avoids same-date controls even
        # across different tickers, which is acceptable given the large bar pool.
        used_ctrl_dates: set[pd.Timestamp] = set()

        tickers = sorted(universe)
        log.info("Processing %d tickers for new events since %s...", len(tickers), last_stamp.date())

        for ticker in tickers:
            close = _read_massive_ticker(ticker)
            if close is None or len(close) < ERA_PRIOR_BARS_REQUIRED:
                continue
            raw_df = _read_massive_ohlcv(ticker)

            events_by_def = _detect_new_events(
                ticker, close, raw_df, existing_ids, last_stamp
            )

            # Collect all event timestamps for this ticker (across both definitions)
            all_event_ts: set[pd.Timestamp] = set()
            for defn in ACTIVE_DEFINITIONS:
                all_event_ts.update(events_by_def.get(defn, []))

            for defn in ACTIVE_DEFINITIONS:
                for event_ts in events_by_def.get(defn, []):
                    # Event row
                    event_id = _make_event_id(ticker, defn, event_ts)
                    row = _grade_row(
                        ticker=ticker,
                        event_ts=event_ts,
                        close=close,
                        definition=defn,
                        is_control=False,
                        control_seed=None,
                        stamp_date=stamp_date,
                        vstamp=vstamp,
                    )
                    row["event_id"] = event_id
                    new_rows.append(row)
                    existing_ids.add(event_id)
                    n_new_events += 1

                    # 3 seeded control rows per event
                    ctrl_seed = _seed_for_event(event_id)
                    ctrl_dates = _sample_control_dates(
                        ticker, close, raw_df, event_ts,
                        existing_event_dates=all_event_ts,
                        seed=ctrl_seed,
                        used_control_dates=used_ctrl_dates,
                    )
                    for k, ctrl_ts in enumerate(ctrl_dates):
                        # Globally-unique control id: parent_event_id|ctrl_{k}
                        # Ties the control to exactly one parent event, preventing
                        # collisions when two events sample the same calendar date.
                        ctrl_eid = f"{event_id}|ctrl_{k}"
                        ctrl_row = _grade_row(
                            ticker=ticker,
                            event_ts=ctrl_ts,
                            close=close,
                            definition=defn,
                            is_control=True,
                            control_seed=ctrl_seed,
                            stamp_date=stamp_date,
                            vstamp=vstamp,
                        )
                        ctrl_row["event_id"] = ctrl_eid
                        new_rows.append(ctrl_row)
                        existing_ids.add(ctrl_eid)
                        used_ctrl_dates.add(ctrl_ts)
                        n_new_controls += 1

        log.info(
            "Detection complete: %d new events, %d new controls across %d tickers",
            n_new_events, n_new_controls, len(tickers),
        )

        # ----------------------------------------------------------------
        # Step 4: Re-grade ungraded rows in existing ledger
        # ----------------------------------------------------------------
        n_regraded = 0
        if len(existing_df) > 0:
            before = int(existing_df["long_state_clean8_21"].isna().sum())
            existing_df = _regrade_ungraded_rows(existing_df, stamp_date, vstamp)
            after = int(existing_df["long_state_clean8_21"].isna().sum())
            n_regraded = before - after
            log.info("Re-graded %d rows (was %d ungraded, now %d)", n_regraded, before, after)

        # ----------------------------------------------------------------
        # Step 5: Append new rows and write
        # ----------------------------------------------------------------
        if not dry_run:
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                combined = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined = existing_df

            if len(combined) > 0 or not ledger_path.exists():
                # Safety dedup: should be a no-op when the controls are generated
                # correctly, but guards against any residual collision path.
                before_dedup = len(combined)
                combined = combined.drop_duplicates(subset="event_id", keep="first")
                n_dropped = before_dedup - len(combined)
                if n_dropped:
                    log.warning(
                        "drop_duplicates removed %d duplicate event_id rows — "
                        "investigate upstream collision",
                        n_dropped,
                    )
                combined.to_parquet(ledger_path, index=False)
                log.info(
                    "Wrote %s (%d total rows = %d existing + %d new)",
                    ledger_path, len(combined), len(existing_df), len(new_rows),
                )
            else:
                log.info("No new rows and no re-grades; ledger unchanged")

            # ----------------------------------------------------------------
            # Step 6: Narrow git commit
            # ----------------------------------------------------------------
            if new_rows or n_regraded > 0:
                _narrow_commit(ledger_path, stamp_date, dry_run=False)
            else:
                log.info("No changes to commit")

        else:
            log.info(
                "DRY RUN: would append %d new rows (%d events, %d controls), "
                "re-grade %d rows",
                len(new_rows), n_new_events, n_new_controls, n_regraded,
            )

        elapsed = time.time() - t0
        summary = {
            "stamp_date": stamp_date,
            "n_new_events": n_new_events,
            "n_new_controls": n_new_controls,
            "n_regraded": n_regraded,
            "n_existing_rows": len(existing_df),
            "n_total_rows": len(existing_df) + len(new_rows),
            "runtime_seconds": round(elapsed, 1),
            "dry_run": dry_run,
            "vintage": vstamp,
        }

        # Print summary
        print(f"\n=== BD-AVOID-1 Phase-1 Stamper — {stamp_date} ===")
        print(f"New events stamped : {n_new_events}")
        print(f"New control rows   : {n_new_controls}")
        print(f"Rows re-graded     : {n_regraded}")
        print(f"Total ledger rows  : {summary['n_total_rows']}")
        print(f"Runtime            : {elapsed:.1f}s")
        if dry_run:
            print("(DRY RUN — no files written)")

        return summary

    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        try:
            os.unlink(lock_path)
        except OSError:
            pass


# ===========================================================================
# 11. CLI entry point
# ===========================================================================

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="BD-AVOID-1 Phase-1 Stamper (Mac-side ops lane)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Detect and grade but do not write files or commit",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=None,
        help="Override the canonical data directory (default: Mac-local CANONICAL_DATA)",
    )
    args = parser.parse_args()

    try:
        summary = run(data_dir=args.data_dir, dry_run=args.dry_run)
        return 0
    except RuntimeError as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
