"""Tests for engine/oracle/tape_outcomes.py — PR-A3 operator-tape outcome resolver.

Covers:
  A. Resolver determinism — same inputs → same outputs
  B. Unresolvable-pre-capture honesty — tape row pre-dates any ledger stamp
  C. Append-only law — outcomes ledger only grows, never shrinks
  D. Maturity gating — pending rows stay pending until window matures
  E. Override flag — operator vs system state direction comparison
  F. Scorecard builder — basic structure + Wilson CI prints n
  G. Nightly step wiring — oracle_nightly imports and calls the step

All fixtures are SYNTHETIC — no real data files, no network.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent


def _oracle_dir(tmp_path: Path) -> Path:
    d = tmp_path / "oracle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_tape(oracle_dir: Path, rows: list[dict]) -> None:
    tape = oracle_dir / "operator_tape.jsonl"
    header = {"type": "schema_note", "note": "test header"}
    all_rows = [header] + rows
    tape.write_text("\n".join(json.dumps(r) for r in all_rows) + "\n", encoding="utf-8")


def _write_ledger(oracle_dir: Path, rows: list[dict]) -> None:
    ledger = oracle_dir / "forward_ledger.jsonl"
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_outcomes(oracle_dir: Path, rows: list[dict]) -> None:
    out = oracle_dir / "operator_tape_outcomes.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _load_outcomes(oracle_dir: Path) -> list[dict]:
    out = oracle_dir / "operator_tape_outcomes.jsonl"
    if not out.exists():
        return []
    rows = []
    for line in out.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _make_tape_row(
    tape_id: str = "tape::2026-07-01T10-00-00",
    pit_stamp: str = "2026-07-01T10:00:00Z",
    nodes: list[str] | None = None,
    direction: str = "in",
    conviction: int | None = None,
) -> dict:
    return {
        "id": tape_id,
        "type": "operator_tape",
        "pit_stamp": pit_stamp,
        "nodes": nodes or ["XLK"],
        "direction": direction,
        "note": "Test observation",
        "tickers": [],
        "invalidation": None,
        "conviction": conviction,
        "converted": None,
    }


def _make_ledger_row(
    node: str = "XLK",
    direction: str = "in",
    pit_stamp: str = "2026-07-01",
) -> dict:
    return {
        "episode_id": f"{node}::{direction}::2026-06-20",
        "node": node,
        "direction": direction,
        "tier": "onset",
        "onset_date": "2026-06-20",
        "confirmed_date": None,
        "pit_stamp": pit_stamp,
        "registered_at": "2026-07-01T00:00:00+00:00",
        "cell_tags": {},
    }


def _write_price_parquet(data_dir: Path, ticker: str, prices: list[float],
                         start_date: str = "2026-01-02") -> None:
    """Write a synthetic price parquet for a ticker in data/yahoo/."""
    yahoo_dir = data_dir / "yahoo"
    yahoo_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start_date, periods=len(prices))
    df = pd.DataFrame({"close": prices}, index=idx)
    df.to_parquet(yahoo_dir / f"{ticker}.parquet")


def _write_panel_parquet(data_dir: Path, node: str, rets: list[float],
                          start_date: str = "2026-01-02") -> None:
    """Write a synthetic panel_s.parquet with one node."""
    oracle_dir = data_dir / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    panel_path = oracle_dir / "panel_s.parquet"
    idx = pd.bdate_range(start_date, periods=len(rets))
    tuples = [(d, node) for d in idx]
    mi = pd.MultiIndex.from_tuples(tuples, names=["date", "node"])
    df = pd.DataFrame({"ret": rets}, index=mi)

    if panel_path.exists():
        existing = pd.read_parquet(panel_path)
        df = pd.concat([existing, df])
        df = df[~df.index.duplicated(keep="first")]

    df.to_parquet(panel_path)


# ---------------------------------------------------------------------------
# A. Resolver determinism
# ---------------------------------------------------------------------------

def test_resolver_determinism(tmp_path: Path) -> None:
    """Same inputs → same outputs on two consecutive calls."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        tape_id="tape::2026-07-01T10-00-00",
        pit_stamp="2026-07-01T10:00:00Z",
        nodes=["XLK"],
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    # First call
    summary1 = resolve_tape_outcomes(tmp_path, dry_run=True)
    # Second call (dry_run=True so no file written)
    summary2 = resolve_tape_outcomes(tmp_path, dry_run=True)

    assert summary1 == summary2, "Resolver must be deterministic"


def test_resolver_writes_new_rows(tmp_path: Path) -> None:
    """Non-dry-run appends new outcome rows to the ledger."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(nodes=["XLK"])
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    summary = resolve_tape_outcomes(tmp_path, dry_run=False)
    assert summary["n_new"] == 1

    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["tape_id"] == tape_row["id"]


# ---------------------------------------------------------------------------
# B. Unresolvable-pre-capture honesty
# ---------------------------------------------------------------------------

def test_unresolvable_pre_capture_when_no_ledger(tmp_path: Path) -> None:
    """When forward_ledger.jsonl is absent, system_state='unresolvable_pre_capture'."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(pit_stamp="2025-01-15T09:00:00Z")
    _write_tape(oracle_dir, [tape_row])
    # No ledger file written

    from engine.oracle.tape_outcomes import (
        UNRESOLVABLE_PRE_CAPTURE, resolve_tape_outcomes,
    )

    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["system_state_at_stamp"] == UNRESOLVABLE_PRE_CAPTURE


def test_unresolvable_pre_capture_when_tape_predates_ledger(tmp_path: Path) -> None:
    """Tape row from 2025-01-01 but ledger starts 2026-06-01 → unresolvable."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(pit_stamp="2025-01-01T12:00:00Z")
    _write_tape(oracle_dir, [tape_row])
    # Ledger only has entries AFTER the tape stamp
    _write_ledger(oracle_dir, [
        _make_ledger_row(node="XLK", direction="in", pit_stamp="2026-06-01"),
    ])

    from engine.oracle.tape_outcomes import (
        UNRESOLVABLE_PRE_CAPTURE, resolve_tape_outcomes,
    )

    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["system_state_at_stamp"] == UNRESOLVABLE_PRE_CAPTURE


def test_resolvable_when_ledger_predates_tape(tmp_path: Path) -> None:
    """Tape row from 2026-07-05, ledger has entry from 2026-07-01 → resolvable."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-07-05T09:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [
        _make_ledger_row(node="XLK", direction="in", pit_stamp="2026-07-01"),
    ])

    from engine.oracle.tape_outcomes import (
        UNRESOLVABLE_PRE_CAPTURE, resolve_tape_outcomes,
    )

    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["system_state_at_stamp"] != UNRESOLVABLE_PRE_CAPTURE
    assert outcomes[0]["system_state_at_stamp"] == "in"


# ---------------------------------------------------------------------------
# C. Append-only law
# ---------------------------------------------------------------------------

def test_append_only_existing_rows_untouched(tmp_path: Path) -> None:
    """Pre-existing resolved rows in outcomes ledger are not re-written."""
    oracle_dir = _oracle_dir(tmp_path)

    existing_row = {
        "schema": "operator_tape_outcomes.v1",
        "tape_id": "tape::2026-06-01T10-00-00",
        "pit_stamp": "2026-06-01T10:00:00Z",
        "nodes": ["XLE"],
        "direction": "out",
        "outcome_status": "resolved",
        "realized_return_mean": -0.03,
        "operator_correct": True,
    }
    _write_outcomes(oracle_dir, [existing_row])

    # New tape row
    new_tape_row = _make_tape_row(
        tape_id="tape::2026-07-01T10-00-00",
        pit_stamp="2026-07-01T10:00:00Z",
        nodes=["XLK"],
    )
    _write_tape(oracle_dir, [new_tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes = _load_outcomes(oracle_dir)

    # Must have at least 2 rows (existing + new)
    assert len(outcomes) >= 2

    # Old row must still be present verbatim
    old_rows = [r for r in outcomes if r.get("tape_id") == existing_row["tape_id"]]
    assert len(old_rows) >= 1

    # Outcome status of old row must still be resolved
    assert old_rows[0].get("outcome_status") == "resolved"


def test_already_resolved_rows_skipped(tmp_path: Path) -> None:
    """Resolved rows in outcomes ledger are not re-processed (n_new stays 0)."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(nodes=["XLK"])
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    # First run
    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_first = _load_outcomes(oracle_dir)

    # Manually mark the row as resolved
    outcomes_resolved = []
    for r in outcomes_first:
        r["outcome_status"] = "resolved"
        outcomes_resolved.append(r)
    _write_outcomes(oracle_dir, outcomes_resolved)

    # Second run — should skip the already-resolved row
    summary2 = resolve_tape_outcomes(tmp_path, dry_run=False)
    assert summary2["n_skipped"] == 1
    assert summary2["n_new"] == 0


# ---------------------------------------------------------------------------
# D. Maturity gating — pending rows stay pending
# ---------------------------------------------------------------------------

def test_pending_when_window_not_matured(tmp_path: Path) -> None:
    """If price series ends before h=21 bars, outcome_status='pending'."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-07-01T10:00:00Z",
        nodes=["XLK"],
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    # Write only 5 bars of price data after the stamp — not enough for h=21
    # Stamp date is 2026-07-01; bdate_range("2026-07-02", periods=5) gives 5 bars
    _write_panel_parquet(
        tmp_path, "XLK",
        rets=[0.01, -0.005, 0.008, 0.002, -0.003],
        start_date="2026-07-02",
    )

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["outcome_status"] == "pending"
    assert outcomes[0]["realized_return_mean"] is None


def test_resolved_when_window_matured(tmp_path: Path) -> None:
    """With 25+ bars after stamp, node outcome resolves to a float."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-01-05T10:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in", pit_stamp="2026-01-05")])

    # 30 upward bars after the stamp date
    rets = [0.01] * 30
    _write_panel_parquet(tmp_path, "XLK", rets=rets, start_date="2026-01-06")

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["outcome_status"] in ("resolved", "partial")
    mean_ret = outcomes[0].get("realized_return_mean")
    assert mean_ret is not None
    assert isinstance(mean_ret, float)
    assert mean_ret > 0, "Upward bars should produce a positive return"


def test_operator_correct_flag_in_direction(tmp_path: Path) -> None:
    """Direction='in' + positive realized return → operator_correct=True."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-01-05T10:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in", pit_stamp="2026-01-05")])

    # Positive returns → operator_correct=True for direction="in"
    _write_panel_parquet(tmp_path, "XLK", rets=[0.01] * 30, start_date="2026-01-06")

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert outcomes[0]["operator_correct"] is True


def test_operator_correct_flag_out_direction(tmp_path: Path) -> None:
    """Direction='out' + negative realized return → operator_correct=True."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-01-05T10:00:00Z",
        nodes=["XLE"],
        direction="out",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLE", direction="out", pit_stamp="2026-01-05")])

    # Negative returns → operator_correct=True for direction="out"
    _write_panel_parquet(tmp_path, "XLE", rets=[-0.01] * 30, start_date="2026-01-06")

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert outcomes[0]["operator_correct"] is True


# ---------------------------------------------------------------------------
# E. Override flag
# ---------------------------------------------------------------------------

def test_override_flag_true_when_disagree(tmp_path: Path) -> None:
    """Operator direction='in' but system showed 'out' → override_flag=True."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-07-05T09:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    # System had XLK as "out" rotation at pit_stamp
    _write_ledger(oracle_dir, [
        _make_ledger_row(node="XLK", direction="out", pit_stamp="2026-07-01"),
    ])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["override_flag"] is True


def test_override_flag_false_when_agree(tmp_path: Path) -> None:
    """Operator direction='in' and system also showed 'in' → override_flag=False."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        pit_stamp="2026-07-05T09:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [
        _make_ledger_row(node="XLK", direction="in", pit_stamp="2026-07-01"),
    ])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["override_flag"] is False


def test_override_flag_none_when_unresolvable(tmp_path: Path) -> None:
    """When system state is unresolvable_pre_capture, override_flag=None."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(pit_stamp="2020-01-15T09:00:00Z")
    _write_tape(oracle_dir, [tape_row])
    # No ledger

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    assert outcomes[0]["override_flag"] is None


# ---------------------------------------------------------------------------
# F. Scorecard builder
# ---------------------------------------------------------------------------

def test_scorecard_structure(tmp_path: Path) -> None:
    """Scorecard has required keys and n is always printed."""
    oracle_dir = _oracle_dir(tmp_path)

    # Write some synthetic resolved outcome rows
    outcome_rows = [
        {
            "tape_id": "tape::2026-07-01T10-00-00",
            "direction": "in",
            "conviction": 4,
            "outcome_status": "resolved",
            "realized_return_mean": 0.05,
            "operator_correct": True,
            "override_flag": False,
            "system_state_at_stamp": "in",
        },
        {
            "tape_id": "tape::2026-07-02T10-00-00",
            "direction": "out",
            "conviction": 3,
            "outcome_status": "resolved",
            "realized_return_mean": -0.02,
            "operator_correct": True,
            "override_flag": True,
            "system_state_at_stamp": "in",
        },
        {
            "tape_id": "tape::2026-07-03T10-00-00",
            "direction": "in",
            "conviction": None,
            "outcome_status": "pending",
            "realized_return_mean": None,
            "operator_correct": None,
            "override_flag": None,
            "system_state_at_stamp": "in",
        },
    ]
    _write_outcomes(oracle_dir, outcome_rows)

    from engine.oracle.tape_outcomes import build_operator_scorecard
    scorecard = build_operator_scorecard(tmp_path)

    # Required keys
    assert "schema" in scorecard
    assert scorecard["schema"] == "operator_scorecard.v1"
    assert "overall" in scorecard
    assert "by_direction" in scorecard
    assert "override_analysis" in scorecard
    assert "n_resolved" in scorecard
    assert "n_pending" in scorecard

    # n must be printed in every rate block
    overall = scorecard["overall"]["operator"]
    assert "n" in overall
    assert isinstance(overall["n"], int)

    # Wilson CI present when n > 0
    if overall["n"] > 0:
        assert overall.get("wilson_ci_95") is not None


def test_scorecard_no_validated_string(tmp_path: Path) -> None:
    """The word 'validated' must not appear in any scorecard value (CI-enforced)."""
    oracle_dir = _oracle_dir(tmp_path)
    _write_outcomes(oracle_dir, [])

    from engine.oracle.tape_outcomes import build_operator_scorecard
    scorecard = build_operator_scorecard(tmp_path)
    scorecard_str = json.dumps(scorecard)
    # Case-insensitive check — the CI check is on user-facing strings
    assert "validated" not in scorecard_str.lower(), (
        "The word 'validated' must not appear in scorecard output (CI-enforced law)"
    )


# ---------------------------------------------------------------------------
# G. Nightly step wiring
# ---------------------------------------------------------------------------

def test_nightly_step_operator_tape_outcomes_exists() -> None:
    """oracle_nightly.py must define _step_operator_tape_outcomes function."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "oracle_nightly",
        ROOT / "scripts" / "oracle_nightly.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert hasattr(mod, "_step_operator_tape_outcomes"), (
        "_step_operator_tape_outcomes not found in oracle_nightly.py"
    )


def test_nightly_step_registered_in_failures(tmp_path: Path) -> None:
    """oracle_nightly main() includes tape_outcomes in the failures tracking list."""
    nightly_path = ROOT / "scripts" / "oracle_nightly.py"
    content = nightly_path.read_text(encoding="utf-8")
    assert "tape_outcomes" in content, (
        "'tape_outcomes' not found in oracle_nightly.py — step may not be wired"
    )
    assert "_step_operator_tape_outcomes" in content, (
        "Step function call not found in oracle_nightly.py main()"
    )
    # Step 18 must appear AFTER Step 17
    pos_17 = content.find("Step 17")
    pos_18 = content.find("Step 18")
    assert pos_17 != -1 and pos_18 != -1, "Step 17 or Step 18 not found in oracle_nightly.py"
    assert pos_18 > pos_17, "Step 18 must appear AFTER Step 17 (additive at END)"


def test_tape_outcomes_dry_run(tmp_path: Path) -> None:
    """dry_run=True runs all logic but writes no files."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(nodes=["XLK"])
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    resolve_tape_outcomes(tmp_path, dry_run=True)

    outcomes_path = oracle_dir / "operator_tape_outcomes.jsonl"
    assert not outcomes_path.exists(), "dry_run must not write any files"


# ---------------------------------------------------------------------------
# H. Fix (2) — duplicate pending rows prevention
# ---------------------------------------------------------------------------

def test_three_nightly_runs_on_unmatured_row_produce_exactly_one_pending_row(
    tmp_path: Path,
) -> None:
    """3 consecutive nightly runs on an unmatured tape row produce exactly 1 pending row.

    The ledger must be append-only, so readers take the LAST row per tape_id.
    An unmatured row must NOT re-append a duplicate pending row on runs 2 and 3.
    """
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        tape_id="tape::2026-07-01T10-00-00",
        pit_stamp="2026-07-01T10:00:00Z",
        nodes=["XLK"],
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])
    # NO price data written → outcome_status stays 'pending' on all runs

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    # Run 1 — writes first (and only) pending row
    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_after_run1 = _load_outcomes(oracle_dir)
    assert len(outcomes_after_run1) == 1
    assert outcomes_after_run1[0]["outcome_status"] == "pending"

    # Run 2 — window still unmatured; must NOT append another row
    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_after_run2 = _load_outcomes(oracle_dir)
    assert len(outcomes_after_run2) == 1, (
        f"Run 2 must not add a duplicate pending row; got {len(outcomes_after_run2)} rows"
    )

    # Run 3 — same expectation
    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_after_run3 = _load_outcomes(oracle_dir)
    assert len(outcomes_after_run3) == 1, (
        f"Run 3 must not add a duplicate pending row; got {len(outcomes_after_run3)} rows"
    )
    assert outcomes_after_run3[0]["tape_id"] == tape_row["id"]
    assert outcomes_after_run3[0]["outcome_status"] == "pending"


def test_maturation_after_pending_adds_exactly_one_final_row(tmp_path: Path) -> None:
    """After a pending row exists, maturation appends exactly 1 final resolution row.

    Total ledger rows = 2 (the original pending row + the maturation row).
    Readers take the LAST row per tape_id (the maturation row).
    """
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(
        tape_id="tape::2026-01-05T10-00-00",
        pit_stamp="2026-01-05T10:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in", pit_stamp="2026-01-05")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes

    # Run 1 — no price data yet; writes 1 pending row
    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_run1 = _load_outcomes(oracle_dir)
    assert len(outcomes_run1) == 1
    assert outcomes_run1[0]["outcome_status"] == "pending"

    # Now provide 30 bars of price data so the window matures
    _write_panel_parquet(tmp_path, "XLK", rets=[0.01] * 30, start_date="2026-01-06")

    # Run 2 — window now matured; appends 1 final resolution row
    resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_run2 = _load_outcomes(oracle_dir)
    assert len(outcomes_run2) == 2, (
        f"Expected 2 rows (pending + maturation); got {len(outcomes_run2)}"
    )
    # Last row must be the maturation row
    last_row = outcomes_run2[-1]
    assert last_row["tape_id"] == tape_row["id"]
    assert last_row["outcome_status"] in ("resolved", "partial")
    assert last_row["realized_return_mean"] is not None

    # Run 3 — already resolved; skipped entirely
    summary_run3 = resolve_tape_outcomes(tmp_path, dry_run=False)
    outcomes_run3 = _load_outcomes(oracle_dir)
    assert len(outcomes_run3) == 2, (
        "Run 3 must not append any more rows (tape_id is now resolved)"
    )
    assert summary_run3["n_skipped"] == 1


# ---------------------------------------------------------------------------
# I. Fix (3) — system_state_snapshot preferred over ledger reconstruction
# ---------------------------------------------------------------------------

def _make_tape_row_with_snapshot(
    tape_id: str = "tape::2026-07-05T10-00-00",
    pit_stamp: str = "2026-07-05T10:00:00Z",
    nodes: list | None = None,
    direction: str = "in",
    snapshot_direction: str = "in",
) -> dict:
    """Make a tape row that includes a write-time system_state_snapshot."""
    nodes = nodes or ["XLK"]
    return {
        "id": tape_id,
        "type": "operator_tape",
        "pit_stamp": pit_stamp,
        "nodes": nodes,
        "direction": direction,
        "note": "Test with snapshot",
        "tickers": [],
        "invalidation": None,
        "conviction": None,
        "converted": None,
        "system_state_snapshot": {
            "asof": pit_stamp[:10],
            "node_states": {node: snapshot_direction for node in nodes},
        },
    }


def test_snapshot_preferred_over_ledger(tmp_path: Path) -> None:
    """When system_state_snapshot is present, it is used instead of ledger reconstruction.

    The snapshot says 'out'; the ledger says 'in'. The resolver must use 'out'.
    system_state_source must be 'snapshot'.
    """
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row_with_snapshot(
        pit_stamp="2026-07-05T10:00:00Z",
        nodes=["XLK"],
        direction="in",
        snapshot_direction="out",  # snapshot says 'out'
    )
    _write_tape(oracle_dir, [tape_row])
    # Ledger says 'in' — snapshot must win
    _write_ledger(oracle_dir, [
        _make_ledger_row(node="XLK", direction="in", pit_stamp="2026-07-01"),
    ])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    row = outcomes[0]
    assert row["system_state_at_stamp"] == "out", (
        f"Expected snapshot-sourced 'out', got {row['system_state_at_stamp']!r}"
    )
    assert row["system_state_source"] == "snapshot", (
        f"Expected source='snapshot', got {row.get('system_state_source')!r}"
    )
    # operator direction='in' vs system='out' → override_flag=True
    assert row["override_flag"] is True


def test_ledger_fallback_when_no_snapshot(tmp_path: Path) -> None:
    """When system_state_snapshot is absent, falls back to ledger reconstruction.

    system_state_source must be 'ledger_reconstruction'.
    """
    oracle_dir = _oracle_dir(tmp_path)
    # Plain tape row with no system_state_snapshot field
    tape_row = _make_tape_row(
        tape_id="tape::2026-07-05T10-00-00",
        pit_stamp="2026-07-05T10:00:00Z",
        nodes=["XLK"],
        direction="in",
    )
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [
        _make_ledger_row(node="XLK", direction="in", pit_stamp="2026-07-01"),
    ])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    assert len(outcomes) == 1
    row = outcomes[0]
    assert row["system_state_source"] == "ledger_reconstruction", (
        f"Expected 'ledger_reconstruction', got {row.get('system_state_source')!r}"
    )
    assert row["system_state_at_stamp"] == "in"


def test_system_state_source_field_present_in_all_outcomes(tmp_path: Path) -> None:
    """Every resolved outcome row must have a system_state_source field."""
    oracle_dir = _oracle_dir(tmp_path)
    tape_row = _make_tape_row(nodes=["XLK"])
    _write_tape(oracle_dir, [tape_row])
    _write_ledger(oracle_dir, [_make_ledger_row(node="XLK", direction="in")])

    from engine.oracle.tape_outcomes import resolve_tape_outcomes
    resolve_tape_outcomes(tmp_path, dry_run=False)

    outcomes = _load_outcomes(oracle_dir)
    for row in outcomes:
        assert "system_state_source" in row, (
            f"Missing system_state_source in outcome row: {row}"
        )
        assert row["system_state_source"] in ("snapshot", "ledger_reconstruction"), (
            f"Unexpected system_state_source value: {row['system_state_source']!r}"
        )
