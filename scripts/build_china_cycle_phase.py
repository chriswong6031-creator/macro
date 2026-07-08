"""W3 — Cycle-phase lobe builder (nightly + historical backfill).

On first run (tape absent or ``--backfill`` flag) this script builds the full
historical phase tape from all available input tapes and stamps every row
``backfill=True``.  Subsequent nightly runs append only the new market day(s),
stamped ``backfill=False``.

Outputs
-------
  data/china_cycle_phase/phase_tape.parquet    — §5 schema
  data/china_cycle_phase/falsifier_ledger.parquet — §5 schema (empty-but-schema on first run)
  site/chinastatedata/cycle_phase.json         — latest-row snapshot

Sanity print (always)
---------------------
Prints phase distributions for key historical periods:
  - 2015-06→08 (should show EUPHORIA → DISTRIBUTION → DELEVERAGING)
  - 2024-09→10 (should show POLICY_PUT → LIQUIDITY_IGNITION)
  - 2018-01→12 (should show GRINDING_BEAR / DELEVERAGING)

These are descriptive checks; if they fail the script prints a WARNING (not an error)
and documents what it actually found.  We do NOT tune thresholds to manufacture a
'pass' — the output is honest.

Run
---
  python -m scripts.build_china_cycle_phase [--backfill] [--smoke]

Flags
-----
  --backfill  Force full historical rebuild (overwrites tape).
  --smoke     Run end-to-end then exit 0 (for CI / local verification).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_china_cycle_phase")

_ROOT = Path(__file__).resolve().parent.parent
_PHASE_TAPE_PATH = _ROOT / "data" / "china_cycle_phase" / "phase_tape.parquet"
_LEDGER_PATH     = _ROOT / "data" / "china_cycle_phase" / "falsifier_ledger.parquet"
_JSON_PATH       = _ROOT / "site" / "chinastatedata" / "cycle_phase.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_existing_tape() -> pd.DataFrame | None:
    if _PHASE_TAPE_PATH.exists():
        try:
            df = pd.read_parquet(_PHASE_TAPE_PATH)
            df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            log.warning("Could not read existing phase tape (%s) — rebuilding", e)
    return None


def _load_existing_ledger() -> pd.DataFrame | None:
    if _LEDGER_PATH.exists():
        try:
            return pd.read_parquet(_LEDGER_PATH)
        except Exception as e:
            log.warning("Could not read existing falsifier ledger (%s)", e)
    return None


def _empty_ledger() -> pd.DataFrame:
    """Return a schema-correct empty falsifier ledger (§5)."""
    return pd.DataFrame(columns=[
        "printed_date", "falsifier_id", "expr", "due_date", "outcome", "graded_date"
    ])


def _save_tape(tape: pd.DataFrame) -> None:
    _PHASE_TAPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Convert list columns to JSON strings for parquet compatibility
    tape_save = tape.copy()
    for col in ["evidence", "contradictions", "falsifiers", "_data_gaps"]:
        if col in tape_save.columns:
            tape_save[col] = tape_save[col].apply(
                lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x
            )
    tape_save.to_parquet(_PHASE_TAPE_PATH, index=True)
    log.info("Phase tape saved → %s (%d rows)", _PHASE_TAPE_PATH, len(tape_save))


def _save_ledger(ledger: pd.DataFrame) -> None:
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(_LEDGER_PATH, index=False)
    log.info("Falsifier ledger saved → %s (%d rows)", _LEDGER_PATH, len(ledger))


def _save_json(payload: dict) -> None:
    _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _JSON_PATH.open("w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("cycle_phase.json saved → %s", _JSON_PATH)


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------

def _sanity_check(tape: pd.DataFrame) -> None:
    """Print phase distributions for key historical periods and warn if unexpected."""
    if tape.empty:
        log.warning("SANITY: tape is empty — cannot run sanity checks")
        return

    periods = [
        ("2015-06 to 2015-08", "2015-06-01", "2015-08-31",
         ["EUPHORIA", "DISTRIBUTION", "DELEVERAGING", "CAPITULATION"],
         "should traverse EUPHORIA→DISTRIBUTION→DELEVERAGING"),
        ("2024-09 to 2024-10", "2024-09-24", "2024-10-31",
         ["POLICY_PUT", "LIQUIDITY_IGNITION"],
         "should show POLICY_PUT / LIQUIDITY_IGNITION after Politburo stimulus"),
        ("2018 full year", "2018-01-01", "2018-12-31",
         ["GRINDING_BEAR", "DELEVERAGING", "REPAIR"],
         "should be mostly GRINDING_BEAR / DELEVERAGING"),
    ]

    tape_phase = tape["phase"]

    print("\n" + "=" * 70)
    print("DESCRIPTIVE SANITY CHECK — phase distributions (not a study)")
    print("=" * 70)

    for label, start, end, expected_phases, expectation in periods:
        mask = (tape_phase.index >= start) & (tape_phase.index <= end)
        subset = tape_phase.loc[mask]
        if subset.empty:
            print(f"  [{label}] — NO DATA IN RANGE (tape coverage gap)")
            continue
        counts = subset.value_counts()
        dominant = counts.index[0] if not counts.empty else "N/A"
        dominant_pct = 100 * counts.iloc[0] / len(subset) if not counts.empty else 0
        found_expected = [p for p in expected_phases if p in counts.index]
        print(f"\n  [{label}] — {expectation}")
        print(f"  Expected phase families: {expected_phases}")
        print(f"  Distribution ({len(subset)} sessions):")
        for phase, cnt in counts.items():
            flag = " ← EXPECTED" if phase in expected_phases else ""
            print(f"    {phase:<22} {cnt:>4} ({100*cnt/len(subset):4.0f}%){flag}")
        if found_expected:
            print(f"  STATUS: PLAUSIBLE — found expected phases {found_expected}")
        else:
            print(
                f"  STATUS: WARNING — none of {expected_phases} are the dominant phases "
                f"(dominant={dominant} at {dominant_pct:.0f}%). "
                f"This may indicate data gaps or threshold sensitivity. Documenting honestly."
            )

    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main build functions
# ---------------------------------------------------------------------------

def _run_backfill() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Build the full historical phase tape from scratch."""
    from engine.china_cycle_phase import build_feature_frame, classify_history, grade_falsifiers

    log.info("Building feature frame from all available inputs...")
    feature_df, data_gaps = build_feature_frame(root=_ROOT)
    log.info("Feature frame: %d rows, %d columns; data_gaps=%s",
             len(feature_df), len(feature_df.columns), data_gaps)

    if feature_df.empty:
        log.warning("Feature frame is empty — tape will be empty")
        tape = pd.DataFrame()
    else:
        log.info("Classifying phases (backfill)...")
        tape = classify_history(feature_df, data_gaps, apply_hysteresis=True)
        log.info("Phase tape: %d rows", len(tape))

    # Grade falsifiers (will be mostly indeterminate on first run — no future data yet)
    grading_date = pd.Timestamp.now()
    ledger = grade_falsifiers(tape, grading_date, existing_ledger=None)

    return tape, ledger, data_gaps


def _run_increment(existing_tape: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Append only new market-day rows to the existing tape."""
    from engine.china_cycle_phase import build_feature_frame, classify_history, grade_falsifiers

    last_date = existing_tape.index.max()
    log.info("Incremental update from %s", last_date.date())

    feature_df, data_gaps = build_feature_frame(root=_ROOT)

    if feature_df.empty:
        log.warning("Feature frame empty — no new rows to append")
        return existing_tape, _empty_ledger(), data_gaps

    new_rows = feature_df[feature_df.index > last_date]
    if new_rows.empty:
        log.info("No new market days since %s", last_date.date())
        return existing_tape, _empty_ledger(), data_gaps

    log.info("New rows to classify: %d (from %s)", len(new_rows), new_rows.index.min().date())
    new_tape = classify_history(new_rows, data_gaps, apply_hysteresis=False)

    # Mark incremental rows as not backfill
    new_tape["backfill"] = False

    combined = pd.concat([existing_tape, new_tape])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.sort_index(inplace=True)

    # Grade due falsifiers
    grading_date = pd.Timestamp.now()
    existing_ledger = _load_existing_ledger()
    ledger = grade_falsifiers(combined, grading_date, existing_ledger=existing_ledger)

    return combined, ledger, data_gaps


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Build China cycle-phase tape (W3)")
    parser.add_argument("--backfill", action="store_true",
                        help="Force full historical rebuild")
    parser.add_argument("--smoke",    action="store_true",
                        help="Run end-to-end and exit 0 (CI mode)")
    args = parser.parse_args()

    from engine.china_cycle_phase import build_cycle_phase_json

    existing_tape = _load_existing_tape()

    if args.backfill or existing_tape is None:
        log.info("Running FULL BACKFILL")
        tape, ledger, data_gaps = _run_backfill()
    else:
        log.info("Running INCREMENTAL update")
        tape, ledger, data_gaps = _run_increment(existing_tape)

    if tape is not None and not tape.empty:
        _save_tape(tape)
        _sanity_check(tape)
    else:
        log.warning("Phase tape is empty — writing empty tape with correct schema")
        empty_tape = pd.DataFrame(columns=[
            "phase", "confidence", "evidence", "contradictions",
            "falsifiers", "backfill", "_data_gaps",
        ])
        _save_tape(empty_tape)

    # Save falsifier ledger (even if empty — ensures schema exists)
    if ledger is None:
        ledger = _empty_ledger()
    _save_ledger(ledger)

    # Build and save JSON
    read_tape = _load_existing_tape()  # re-read to get the saved-and-reloaded version
    if read_tape is None:
        read_tape = pd.DataFrame()

    json_payload = build_cycle_phase_json(
        phase_tape=read_tape,
        falsifier_ledger=ledger,
        data_gaps=data_gaps,
        built_at=datetime.now(timezone.utc).isoformat(),
    )
    _save_json(json_payload)

    log.info("Build complete. Tape rows=%d, Ledger rows=%d, Phase=%s",
             len(read_tape) if read_tape is not None else 0,
             len(ledger),
             json_payload.get("phase"))

    if args.smoke:
        log.info("--smoke: exiting 0")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
