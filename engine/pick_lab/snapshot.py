"""Pick Lab snapshot schema, reader, and monthly-partition writer.

Snapshot of record: one row per ticker in the full scored universe for one asof date.
PIT by construction (PL-R7): written once per night; never backfilled.
Monthly parquet partitions: data/pick_lab/snapshots/<YYYY-MM>.parquet.

Public API:
  SNAPSHOT_COLUMNS  — ordered list of all expected columns (spec §5 full list)
  write_snapshot(df, asof) — append keep-first on (asof, ticker) to monthly parquet
  latest_snapshot() — (df_for_max_asof, asof) across all partitions
  build_core_rows(...) — PURE function assembling core rows from plain inputs (no I/O)
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SNAPSHOT_DIR = "data/pick_lab/snapshots"

# ------------------------------------------------------------------ Schema --
# Full column list per spec §5.
# Identity / price / technicals:
_IDENTITY_COLS = [
    "asof",
    "ticker",
    "sector",
    "close",
    "dollar_adv_20d",
    "vol_ratio_20d",
    "is_20d_high",
    "pct_vs_20dma",
    "above_200",
    "off_52w_high_pct",
    "rsi14",
    "ext_grade",
]
# Scores:
_SCORE_COLS = [
    "composite_z",
    "score",
    "axis_selection",
    "axis_entry",
    "axis_quality",
    "edge_insider",
    "edge_sue",
    "edge_revision",
    "edge_alpha",
]
# Oscillators per grid g ∈ {d1, d2, d3}:
_OSC_GRIDS = ("d1", "d2", "d3")
_OSC_SUFFIXES = ("macd", "sig", "macd_xup_bars", "k", "d", "kd_xup_bars", "from_os", "ob")
_OSCILLATOR_COLS = [f"{g}_{s}" for g in _OSC_GRIDS for s in _OSC_SUFFIXES] + ["weekly_bull"]
# Gate:
_GATE_COLS = ["tier", "t_ticks", "gate_state"]
# Context:
_CONTEXT_COLS = [
    "cycle_state",
    "urgency",
    "sector_phase",
    "sector_stage",
    "sector_rs_mom20",
    "sector_bucket",
    "coiled",
    "star",
    "washout_active",
    "dd_pct",
    "vol_squeeze_state",
    "archetype",
    "current_mode",
    "implied_upside_pct",
    "is_blackout",
    "dilution_events_365d",
    "days_since_shelf",
    "interest_coverage",
]
# Enrichment (added by runner's PL-R7b enrichment join; repeated on every row as scalar):
_ENRICHMENT_COLS = [
    "calm",
    "stress",
    "liquidity_overlay",
    "spy_close",
]

SNAPSHOT_COLUMNS: list[str] = (
    _IDENTITY_COLS
    + _SCORE_COLS
    + _OSCILLATOR_COLS
    + _GATE_COLS
    + _CONTEXT_COLS
    + _ENRICHMENT_COLS
)


# ------------------------------------------------------------------ I/O -----

def _partition_path(asof: str, base_dir: str = SNAPSHOT_DIR) -> str:
    """Monthly parquet file path for a given asof date string (YYYY-MM-DD)."""
    ym = str(asof)[:7]  # YYYY-MM
    return os.path.join(base_dir, f"{ym}.parquet")


def write_snapshot(
    df: pd.DataFrame,
    asof: str | pd.Timestamp,
    base_dir: str = SNAPSHOT_DIR,
    *,
    mode: str = "keep_first",
) -> int:
    """Append rows to the monthly parquet partition for `asof`.

    Parameters
    ----------
    mode : 'keep_first' (default) — dedup on (asof, ticker); a second write of the
           same (asof, ticker) is a no-op (PL-R10 / PL-R2 idempotent).
           'upsert' — replace any existing (asof, ticker) rows; use for the
           enrichment re-write in build_pick_lab (PL-R7) so the persisted snapshot
           carries the enriched frame, not the un-enriched core rows.

    Returns number of rows written (0 in keep_first when all rows already exist).

    Write is atomic: tempfile + os.replace, mirroring ledger.write_jsonl.
    """
    asof = str(pd.Timestamp(asof).date())
    df = df.copy()
    df["asof"] = asof

    # Ensure index is ticker
    if "ticker" in df.columns and df.index.name != "ticker":
        df = df.set_index("ticker")

    path = _partition_path(asof, base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        existing = pd.read_parquet(path)
        if mode == "upsert":
            # Replace existing (asof, ticker) rows; keep rows from other asof dates.
            incoming_keys = set(zip(df["asof"], df.index))
            kept = existing[[
                (existing.at[t, "asof"], t) not in incoming_keys
                for t in existing.index
            ]]
            combined = pd.concat([kept, df])
            n = len(df)
        else:
            # keep_first: exclude (asof, ticker) pairs already present
            existing_keys = set(zip(existing["asof"], existing.index))
            new_rows = df[[
                not (asof, t) in existing_keys
                for t in df.index
            ]]
            if new_rows.empty:
                log.debug("write_snapshot: all rows already present for asof=%s", asof)
                return 0
            combined = pd.concat([existing.set_index(
                existing.index if existing.index.name == "ticker" else existing.index
            ), new_rows])
            n = len(new_rows)
    else:
        combined = df
        n = len(df)

    # Atomic write: tempfile in same dir + os.replace (no torn writes)
    dir_path = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=dir_path, prefix=".tmp_snap_", suffix=".parquet")
    try:
        os.close(fd)
        combined.to_parquet(tmp)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    log.info("write_snapshot[%s]: wrote %d rows for asof=%s to %s", mode, n, asof, path)
    return n


def latest_snapshot(
    base_dir: str = SNAPSHOT_DIR,
) -> tuple[pd.DataFrame, str] | tuple[None, None]:
    """Return (df_for_max_asof, asof_str) across all monthly partitions.

    Returns (None, None) if no snapshots exist.
    The returned df has ticker as index.
    """
    base = Path(base_dir)
    if not base.exists():
        return None, None

    files = sorted(base.glob("*.parquet"))
    if not files:
        return None, None

    # Read only the latest partition to find max asof; then filter
    frames = []
    for f in files:
        try:
            frames.append(pd.read_parquet(f))
        except Exception as exc:
            log.warning("latest_snapshot: could not read %s: %s", f, exc)

    if not frames:
        return None, None

    combined = pd.concat(frames)
    if "asof" not in combined.columns:
        return None, None

    max_asof = combined["asof"].max()
    sub = combined[combined["asof"] == max_asof].copy()

    # Ensure ticker is index
    if sub.index.name != "ticker" and "ticker" in sub.columns:
        sub = sub.set_index("ticker")
    elif sub.index.name != "ticker":
        pass  # index is already ticker (written that way)

    sub.attrs["asof"] = max_asof
    return sub, str(max_asof)


# ------------------------------------------------------------------ Pure builder ----

def build_core_rows(
    *,
    profile_dicts: list[dict],
    board_rec_dicts: dict[str, dict] | None = None,
    technicals_dicts: dict[str, dict] | None = None,
    oscillator_dicts: dict[str, dict] | None = None,
    asof: str | pd.Timestamp,
) -> list[dict]:
    """Assemble producer-core rows from plain dicts/DataFrames.

    PURE function (no I/O, no side effects) — called by scripts/build_stock_library.py
    and unit-testable without the pipeline.

    Parameters
    ----------
    profile_dicts : list of dicts, each containing at minimum 'ticker' and
        any subset of SNAPSHOT_COLUMNS identity/score/context fields.
    board_rec_dicts : {ticker: dict} with gate (tier, t_ticks, gate_state) fields.
    technicals_dicts : {ticker: dict} with technical fields.
    oscillator_dicts : {ticker: dict} with oscillator fields (from compute_grids).
    asof : date for the snapshot rows.

    Returns
    -------
    list of dicts, one per ticker, with keys matching SNAPSHOT_COLUMNS.
    Missing fields are null-honest (None) — never fabricated.
    """
    asof_str = str(pd.Timestamp(asof).date())
    board_rec_dicts = board_rec_dicts or {}
    technicals_dicts = technicals_dicts or {}
    oscillator_dicts = oscillator_dicts or {}

    rows = []
    for prof in profile_dicts:
        ticker = prof.get("ticker")
        if not ticker:
            continue
        row: dict = {"asof": asof_str, "ticker": ticker}
        # Merge fields null-honestly — sources in priority order:
        # profile > board_rec > technicals > oscillators
        # A None from a higher-priority source does NOT block a real value from a
        # lower-priority source (e.g. profile seeds dd_pct=None; technicals has the
        # computed value — the real value must win).  False/0/empty-string are real
        # values and DO block lower-priority sources, so only None is overridable.
        for src in (
            prof,
            board_rec_dicts.get(ticker, {}),
            technicals_dicts.get(ticker, {}),
            oscillator_dicts.get(ticker, {}),
        ):
            for k, v in src.items():
                if k not in row or row[k] is None:  # keep-first; None is overridable
                    row[k] = v

        # Fill missing snapshot columns with None (null-honest)
        for col in SNAPSHOT_COLUMNS:
            if col not in row:
                row[col] = None

        rows.append(row)

    return rows
