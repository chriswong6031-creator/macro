"""engine/oracle/tape_outcomes.py — Operator-tape outcome resolver (PR-A3).

Deterministic nightly join between operator_tape.jsonl decisions and:
  1. system_state_at_stamp  — what Oracle showed at the operator's PIT stamp
  2. realized_outcome       — forward return of nodes/tickers at stated horizon
  3. override_flag          — did operator's direction disagree with system state?

CONSTITUTION COMPLIANCE
-----------------------
- Every computed field is deterministic (no LLM anywhere).
- No confidence-class escalation; this is display-only infrastructure.
- The word "validated" must not appear in user-facing strings (CI-enforced).
- Nightly is the sole advancer of forward ledgers; this module is invoked from
  oracle_nightly.py as Step 18 (additive at END, Constitution §V).
- Append-only: operator_tape_outcomes.jsonl grows nightly; existing rows are
  never mutated.
- operator_scorecard.json is display-only: prints n with every rate; small-n
  expected and honest; Wilson bounds from engine/grading_stats.py; no confidence
  claims beyond the CI math.

HONESTY RULES FOR SYSTEM STATE
-------------------------------
- If the historical state CAN be reconstructed from forward_ledger.jsonl
  (episodes that were PIT-stamped on/before the pit_stamp), use it.
- If it cannot (row pre-dates any forward_ledger capture), write
  'unresolvable_pre_capture' — never guess.

FORWARD RETURN CONVENTION
--------------------------
- FIRST close strictly AFTER pit_stamp entry bar (grading_stats.CONVENTION).
  No partial windows — a row stays 'pending' until all horizon bars exist.
- Default horizon: 21 trading days.
- Nodes: resolved from oracle/panel_s.parquet 'ret' series.
- Tickers: resolved from data/yahoo/<TICKER>.parquet 'close' series.
  If a ticker has no parquet, it is skipped; the mean is taken over available
  tickers only.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_HORIZON = 21               # trading days
_OUTCOMES_FILENAME = "operator_tape_outcomes.jsonl"
_SCORECARD_FILENAME = "operator_scorecard.json"
_TAPE_FILENAME = "operator_tape.jsonl"
_FWD_LEDGER_FILENAME = "forward_ledger.jsonl"

# Schema version for the outcomes ledger rows.
_OUTCOMES_SCHEMA = "operator_tape_outcomes.v1"

# System-state resolution sentinel for pre-capture rows.
UNRESOLVABLE_PRE_CAPTURE = "unresolvable_pre_capture"

# Direction tokens (matching operator_tape schema)
DIR_IN = "in"
DIR_OUT = "out"

# Node → panel "ret" column direction convention
# Oracle uses direction="in" to mean "rotating INTO" (bullish for the node)
# and "out" to mean "rotating OUT" (bearish for the node).
# A realized return > 0 for direction="in" is a WIN; < 0 for "out" is a WIN.


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file (torn-line tolerant, returns [] if absent)."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    """Append rows to a JSONL file (creates parent dirs; append mode)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")


# ---------------------------------------------------------------------------
# System-state resolution from forward_ledger.jsonl
# ---------------------------------------------------------------------------

def _build_pit_state_index(
    ledger_rows: list[dict],
) -> dict[str, dict[str, list[str]]]:
    """Build a PIT-indexed state map: date → node → [direction, ...].

    A forward_ledger row records the Oracle's detection at `pit_stamp` (the
    asof date when the nightly ran). For a tape row stamped at pit_stamp T,
    we look for ledger rows with pit_stamp <= T (the system's known state at
    that moment).

    Returns:
        {pit_stamp_date: {node: [direction_list]}}
    The pit_stamp_date key is the ISO date string (first 10 chars).
    """
    index: dict[str, dict[str, list[str]]] = {}
    for row in ledger_rows:
        ps = str(row.get("pit_stamp", ""))[:10]
        if not ps:
            continue
        node = str(row.get("node", ""))
        direction = str(row.get("direction", ""))
        if not node or not direction:
            continue
        index.setdefault(ps, {}).setdefault(node, []).append(direction)
    return index


def _resolve_system_state(
    tape_row: dict,
    pit_index: dict[str, dict[str, list[str]]],
) -> tuple[str | None, str]:
    """Return (state_token, source) for what the Oracle showed at pit_stamp.

    Resolution strategy (PIT-correct source preferred):
    1. PREFER the write-time system_state_snapshot if present on the tape row —
       it is the most PIT-correct source (captured at tape-add time by oracle_tape.py).
    2. FALL BACK to forward_ledger reconstruction if the snapshot is absent/null.

    source token:
        'snapshot'              — state read from tape row's system_state_snapshot field
        'ledger_reconstruction' — state reconstructed from forward_ledger.jsonl

    state_token:
        'in'                     — all nodes showed rotation-in at stamp
        'out'                    — all nodes showed rotation-out at stamp
        'mixed'                  — nodes had conflicting state
        'absent'                 — no active episode for these nodes at that time
        UNRESOLVABLE_PRE_CAPTURE — forward_ledger pre-dates the tape row (ledger path only)
        None                     — structural error (malformed tape row)
    """
    pit_stamp = str(tape_row.get("pit_stamp", ""))
    if not pit_stamp:
        return None, "ledger_reconstruction"

    nodes = tape_row.get("nodes") or []
    if not nodes:
        return None, "ledger_reconstruction"

    # --- Path 1: use write-time snapshot if present ---
    snapshot = tape_row.get("system_state_snapshot")
    if snapshot and isinstance(snapshot, dict):
        node_states = snapshot.get("node_states", {})
        if node_states:
            node_directions_snap = [
                str(node_states.get(node, ""))
                for node in nodes
            ]
            non_empty_snap = [d for d in node_directions_snap if d and d != "absent"]
            if not non_empty_snap:
                return "absent", "snapshot"
            unique_dirs_snap = set(non_empty_snap)
            if len(unique_dirs_snap) == 1:
                return unique_dirs_snap.pop(), "snapshot"
            return "mixed", "snapshot"

    # --- Path 2: forward_ledger reconstruction ---
    tape_date = pit_stamp[:10]
    available_dates = sorted(d for d in pit_index if d <= tape_date)
    if not available_dates:
        return UNRESOLVABLE_PRE_CAPTURE, "ledger_reconstruction"

    node_directions: list[str] = []
    for node in nodes:
        found = False
        for ps_date in reversed(available_dates):
            node_map = pit_index.get(ps_date, {})
            if node in node_map:
                dirs = node_map[node]
                # Take the first direction listed (onset takes precedence)
                node_directions.append(dirs[0] if dirs else "")
                found = True
                break
        if not found:
            node_directions.append("")

    # Summarise
    non_empty = [d for d in node_directions if d]
    if not non_empty:
        return "absent", "ledger_reconstruction"

    unique_dirs = set(non_empty)
    if len(unique_dirs) == 1:
        return unique_dirs.pop(), "ledger_reconstruction"
    return "mixed", "ledger_reconstruction"


# ---------------------------------------------------------------------------
# Realized outcome via price series
# ---------------------------------------------------------------------------

def _load_price_series(
    data_dir: Path,
    ticker: str,
) -> "pd.Series | None":  # type: ignore[name-defined]
    """Load close price series for a ticker from data/yahoo/<TICKER>.parquet."""
    try:
        import pandas as pd
        p = data_dir / "yahoo" / f"{ticker}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        return df["close"].sort_index()
    except Exception as e:  # noqa: BLE001
        log.debug("tape_outcomes: could not load ticker %s: %s", ticker, e)
        return None


def _load_node_return_series(
    data_dir: Path,
    node: str,
) -> "pd.Series | None":  # type: ignore[name-defined]
    """Load cumulative price level from oracle/panel_s.parquet for a node.

    Returns a close-equivalent price-level series (cumulative product of returns).
    """
    try:
        import numpy as np
        import pandas as pd
        panel_path = data_dir / "oracle" / "panel_s.parquet"
        if not panel_path.exists():
            return None
        panel = pd.read_parquet(panel_path)
        try:
            node_data = panel.xs(node, level="node")
        except KeyError:
            return None
        if "ret" not in node_data.columns:
            return None
        ret = node_data["ret"].sort_index().fillna(0)
        price_level = (1 + ret).cumprod()
        return price_level
    except Exception as e:  # noqa: BLE001
        log.debug("tape_outcomes: could not load node %s from panel: %s", node, e)
        return None


def _compute_forward_return(
    px: "pd.Series",  # type: ignore[name-defined]
    stamp_date: str,
    horizon: int,
) -> float | None:
    """Compute h-day forward return anchored at first close STRICTLY AFTER stamp_date.

    Returns None if the window has not yet matured (no partial windows).
    """
    try:
        import pandas as pd
        stamp_ts = pd.Timestamp(stamp_date)
        idx = px.index

        # Entry bar: first bar STRICTLY after stamp (grading_stats.CONVENTION)
        j = int(idx.searchsorted(stamp_ts, side="right"))
        if j >= len(idx):
            return None  # no bar after stamp

        exit_j = j + horizon
        if exit_j >= len(idx):
            return None  # window not matured

        entry_price = float(px.iloc[j])
        exit_price = float(px.iloc[exit_j])
        if entry_price == 0 or entry_price != entry_price:  # nan check
            return None
        return round(float(exit_price / entry_price - 1), 6)
    except Exception as e:  # noqa: BLE001
        log.debug("tape_outcomes: forward return error: %s", e)
        return None


def _resolve_realized_outcome(
    tape_row: dict,
    data_dir: Path,
) -> dict[str, Any]:
    """Compute the realized outcome block for a tape row.

    Returns a dict with:
        horizon_days       int
        realized_return_mean  float | None  — mean over all resolvable instruments
        node_returns       {node: float | None}
        ticker_returns     {ticker: float | None}
        outcome_status     'pending' | 'partial' | 'resolved' | 'unresolvable'
    """
    pit_stamp = str(tape_row.get("pit_stamp", ""))[:10]
    nodes = tape_row.get("nodes") or []
    tickers = tape_row.get("tickers") or []

    # Parse horizon from invalidation text is not reliable; use 21d default.
    horizon = DEFAULT_HORIZON

    node_returns: dict[str, float | None] = {}
    ticker_returns: dict[str, float | None] = {}

    for node in nodes:
        px = _load_node_return_series(data_dir, node)
        if px is None:
            node_returns[node] = None
        else:
            node_returns[node] = _compute_forward_return(px, pit_stamp, horizon)

    for ticker in tickers:
        px = _load_price_series(data_dir, ticker)
        if px is None:
            ticker_returns[ticker] = None
        else:
            ticker_returns[ticker] = _compute_forward_return(px, pit_stamp, horizon)

    all_returns: list[float] = []
    for v in list(node_returns.values()) + list(ticker_returns.values()):
        if v is not None:
            all_returns.append(v)

    # Determine outcome_status
    total_instruments = len(nodes) + len(tickers)
    if total_instruments == 0:
        outcome_status = "unresolvable"
        realized_return_mean = None
    elif not all_returns:
        outcome_status = "pending"
        realized_return_mean = None
    elif len(all_returns) < total_instruments:
        outcome_status = "partial"
        realized_return_mean = round(float(sum(all_returns) / len(all_returns)), 6)
    else:
        outcome_status = "resolved"
        realized_return_mean = round(float(sum(all_returns) / len(all_returns)), 6)

    return {
        "horizon_days": horizon,
        "realized_return_mean": realized_return_mean,
        "node_returns": node_returns,
        "ticker_returns": ticker_returns,
        "outcome_status": outcome_status,
    }


# ---------------------------------------------------------------------------
# Override flag
# ---------------------------------------------------------------------------

def _compute_override_flag(
    tape_direction: str,
    system_state: str | None,
) -> bool | None:
    """True if operator's direction DISAGREES with system state.

    Returns:
        True    — operator went opposite to Oracle
        False   — operator agreed with Oracle
        None    — system state unresolvable or mixed/absent (no comparison possible)
    """
    if system_state in (None, UNRESOLVABLE_PRE_CAPTURE, "mixed", "absent", ""):
        return None
    if tape_direction == system_state:
        return False  # agreement
    return True       # override (operator vs system disagreement)


# ---------------------------------------------------------------------------
# Core resolver: process tape rows not yet in outcomes ledger
# ---------------------------------------------------------------------------

def resolve_tape_outcomes(
    data_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Resolve operator-tape outcomes and append new rows to outcomes ledger.

    Append-only ledger rules:
    - Resolved rows (by tape_id, last row per tape_id wins) are skipped entirely.
    - A pending row is written at most ONCE per tape_id (on first encounter).
    - Each subsequent nightly run re-checks pending rows; if the window has now
      matured, exactly ONE final resolution row is appended (status in resolved/partial).
    - If still pending: skip — no duplicate pending rows ever written.

    Returns summary counts dict.
    """
    tape_path = data_dir / "oracle" / _TAPE_FILENAME
    outcomes_path = data_dir / "oracle" / _OUTCOMES_FILENAME
    ledger_path = data_dir / "oracle" / _FWD_LEDGER_FILENAME

    # Load tape
    tape_rows = [
        r for r in _load_jsonl(tape_path)
        if r.get("type") == "operator_tape"
    ]
    if not tape_rows:
        log.info("tape_outcomes: no operator_tape rows found, nothing to resolve")
        return {"n_tape": 0, "n_new": 0, "n_skipped": 0, "n_resolved": 0, "n_pending": 0}

    # Load existing outcomes to find already-processed tape_ids.
    # Readers take the LAST row per tape_id (append-only ledger convention).
    # - already-resolved IDs: skip entirely (immutable).
    # - already-pending IDs: re-attempt each night; only append if now matured.
    existing_outcomes = _load_jsonl(outcomes_path)
    # Build last-seen status per tape_id (last row wins, per append-only convention)
    _last_status: dict[str, str] = {}
    for r in existing_outcomes:
        tid = r.get("tape_id", "")
        st = r.get("outcome_status", "")
        if tid and st:
            _last_status[tid] = st

    existing_resolved_ids: set[str] = {
        tid for tid, st in _last_status.items()
        if st not in ("pending", None)
    }
    # Pending IDs: will re-attempt each night, but only write a NEW row if
    # the window has now MATURED (status transitions out of 'pending').
    # If still pending, skip — do NOT write a duplicate pending row.
    existing_pending_ids: set[str] = {
        tid for tid, st in _last_status.items()
        if st == "pending"
    }

    # Build PIT state index from forward ledger
    ledger_rows = _load_jsonl(ledger_path)
    pit_index = _build_pit_state_index(ledger_rows)

    now_utc = datetime.now(timezone.utc).isoformat()
    new_rows: list[dict] = []
    updated_pending: list[dict] = []

    n_skipped = 0
    n_resolved = 0
    n_pending = 0

    for tape_row in tape_rows:
        tape_id = tape_row.get("id", "")
        if not tape_id:
            continue

        # Skip rows already fully resolved
        if tape_id in existing_resolved_ids:
            n_skipped += 1
            continue

        # System state resolution — returns (state_token, source)
        system_state, system_state_source = _resolve_system_state(tape_row, pit_index)

        # Realized outcome
        outcome_block = _resolve_realized_outcome(tape_row, data_dir)

        outcome_status = outcome_block["outcome_status"]

        if tape_id in existing_pending_ids:
            # This tape_id already has a pending row written.
            # ONLY append a new row if the window has now matured (status changed).
            # If still pending: skip — no duplicate pending rows.
            if outcome_status == "pending":
                n_pending += 1
                continue  # skip; pending row was already written on first encounter
            # Window matured: fall through to write the final resolution row.

        # Override flag
        override_flag = _compute_override_flag(
            tape_row.get("direction", ""),
            system_state,
        )

        # Did operator's direction match realized outcome?
        direction = tape_row.get("direction", "")
        rr_mean = outcome_block.get("realized_return_mean")
        operator_correct: bool | None = None
        if rr_mean is not None and direction:
            if direction == DIR_IN:
                operator_correct = rr_mean > 0
            elif direction == DIR_OUT:
                operator_correct = rr_mean < 0

        outcome_row: dict = {
            "schema": _OUTCOMES_SCHEMA,
            "tape_id": tape_id,
            "pit_stamp": tape_row.get("pit_stamp"),
            "nodes": tape_row.get("nodes"),
            "tickers": tape_row.get("tickers"),
            "direction": direction,
            "conviction": tape_row.get("conviction"),
            "system_state_at_stamp": system_state,
            "system_state_source": system_state_source,
            "override_flag": override_flag,
            "horizon_days": outcome_block["horizon_days"],
            "realized_return_mean": outcome_block["realized_return_mean"],
            "node_returns": outcome_block["node_returns"],
            "ticker_returns": outcome_block["ticker_returns"],
            "outcome_status": outcome_status,
            "operator_correct": operator_correct,
            "resolved_at": now_utc,
        }

        if tape_id in existing_pending_ids:
            # Previously pending; window matured → record the final resolution row
            updated_pending.append(outcome_row)
        else:
            new_rows.append(outcome_row)

        if outcome_status in ("resolved", "partial"):
            n_resolved += 1
        else:
            n_pending += 1

    all_new = new_rows + updated_pending
    if all_new and not dry_run:
        _append_jsonl(outcomes_path, all_new)
        log.info(
            "tape_outcomes: appended %d new rows (%d matured from pending)",
            len(all_new), len(updated_pending),
        )

    return {
        "n_tape": len(tape_rows),
        "n_new": len(all_new),
        "n_skipped": n_skipped,
        "n_resolved": n_resolved,
        "n_pending": n_pending,
    }


# ---------------------------------------------------------------------------
# Scorecard builder (display-only)
# ---------------------------------------------------------------------------

def build_operator_scorecard(data_dir: Path) -> dict:
    """Build display-only scorecard from outcomes ledger.

    Schema: operator_scorecard.v1
    Groups by regime direction and reports:
      - operator hit rate (proportion where operator_correct=True among resolved)
      - system hit rate (proportion where operator's direction matched system_state)
      - n printed; Wilson bounds included per CI
      - small-n expected and honest; no confidence claims beyond CI math

    DISPLAY ONLY — feeds no score, gate, or ranking surface.
    """
    from engine.grading_stats import wilson_ci

    outcomes_path = data_dir / "oracle" / _OUTCOMES_FILENAME
    rows = [
        r for r in _load_jsonl(outcomes_path)
        if r.get("outcome_status") in ("resolved", "partial")
    ]

    now_utc = datetime.now(timezone.utc).isoformat()

    def _rate_block(hits: int, n: int, label: str) -> dict:
        ci = wilson_ci(hits, n)
        return {
            "label": label,
            "n": n,
            "hits": hits,
            "rate": round(hits / n, 3) if n else None,
            "wilson_ci_95": list(ci) if ci else None,
            "note": "Small-n — print only, no confidence claims" if n < 20 else None,
        }

    # Overall operator hit rate
    resolved_rows = [r for r in rows if r.get("operator_correct") is not None]
    op_hits = sum(1 for r in resolved_rows if r["operator_correct"] is True)

    # System hit rate: operator's direction == system_state AND outcome correct
    # "Did the system call the same direction as the operator, and was it right?"
    sys_comparable = [
        r for r in resolved_rows
        if r.get("override_flag") is not None  # system state was resolvable
    ]
    sys_hits_no_override = sum(
        1 for r in sys_comparable
        if r.get("override_flag") is False  # operator agreed with system
        and r.get("operator_correct") is True
    )
    sys_override_rows = [r for r in sys_comparable if r.get("override_flag") is True]
    sys_override_correct = sum(1 for r in sys_override_rows if r.get("operator_correct") is True)

    # By direction
    in_rows = [r for r in resolved_rows if r.get("direction") == DIR_IN]
    out_rows = [r for r in resolved_rows if r.get("direction") == DIR_OUT]
    in_hits = sum(1 for r in in_rows if r.get("operator_correct") is True)
    out_hits = sum(1 for r in out_rows if r.get("operator_correct") is True)

    # By conviction (1-5 buckets, if available)
    conviction_rows: dict[str | int, list[dict]] = {}
    for r in resolved_rows:
        c = r.get("conviction")
        if c is None:
            c = "none"
        conviction_rows.setdefault(c, []).append(r)

    conviction_blocks = {}
    for c_val, c_rows in conviction_rows.items():
        c_hits = sum(1 for r in c_rows if r.get("operator_correct") is True)
        conviction_blocks[str(c_val)] = _rate_block(c_hits, len(c_rows), f"conviction={c_val}")

    scorecard = {
        "schema": "operator_scorecard.v1",
        "produced_at": now_utc,
        "note": (
            "DISPLAY-ONLY. Operator tape outcome resolution. "
            "No confidence claims; Wilson CI printed for information only. "
            "Small-n expected for new installs."
        ),
        "disclaimer": (
            "Realized returns are 21-trading-day forward returns on node/ticker series "
            "anchored at first close STRICTLY after pit_stamp. "
            "Partial windows (not yet matured) are excluded from rate calculations."
        ),
        "overall": {
            "operator": _rate_block(op_hits, len(resolved_rows), "operator_overall"),
        },
        "by_direction": {
            "in": _rate_block(in_hits, len(in_rows), "operator_direction_in"),
            "out": _rate_block(out_hits, len(out_rows), "operator_direction_out"),
        },
        "override_analysis": {
            "n_with_system_state": len(sys_comparable),
            "n_overrides": len(sys_override_rows),
            "overrides_correct": _rate_block(
                sys_override_correct, len(sys_override_rows),
                "operator_overrode_system_and_correct",
            ),
            "agreements_correct": _rate_block(
                sys_hits_no_override,
                len([r for r in sys_comparable if not r.get("override_flag")]),
                "operator_agreed_with_system_and_correct",
            ),
        },
        "by_conviction": conviction_blocks,
        "n_total_tape_rows": len(rows),
        "n_resolved": len(resolved_rows),
        "n_pending": len([r for r in _load_jsonl(outcomes_path)
                          if r.get("outcome_status") == "pending"]),
    }
    return scorecard


def write_operator_scorecard(scorecard: dict, data_dir: Path, *, dry_run: bool = False) -> None:
    """Write operator_scorecard.json (display-only, OVERWRITTEN nightly — not a ledger)."""
    path = data_dir / "oracle" / _SCORECARD_FILENAME
    if dry_run:
        log.info("DRY-RUN: would write %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scorecard, separators=(",", ":"), default=str), encoding="utf-8")
    log.info("tape_outcomes: scorecard written (%d resolved rows)", scorecard.get("n_resolved", 0))
