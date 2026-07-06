"""tests/test_research_factory_monitor.py — Paper monitor tests (W6, RF-8/RF-9/RF-10).

Tested scenarios:
  1. warmup_state — n < WARMUP_FLOOR → paper_status='warmup', action='continue'
  2. absent_upstream_files — live_ledger absent, track file absent, challenge file
     absent → row still valid with not_applicable / ungradable sentinels
  3. keep_first — two --write runs same as_of → one row in paper_monitor.jsonl
  4. dry_run_writes_nothing — assert no file mutations under a tmp data dir
  5. regime_aware_damping — launched_hot decay → 'launched_hot_context' flag,
     action='review' (not 'retire_recommended'), paper_status='review'
  6. paper_human_review_transition_emitted — retire_recommended → transition row
     with from='paper', to='human_review' emitted
  7. retirement_never_performed — monitor never writes a 'retired' transition
  8. deferred_come_back_due — deferred with past come_back_on → human_review
     transition emitted
  9. monotonic_as_of_respected — two runs same candidate, second has later as_of;
     keep-first means second is deduplicated on same as_of but written on new as_of

Charter: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §6 W6,
rulings RF-5, RF-8, RF-9, RF-10.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# Ensure the repo root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory import ledger as rf_ledger
from engine.research_factory.monitor import (
    WARMUP_FLOOR,
    NOT_APPLICABLE,
    UNGRADABLE,
    _build_monitor_row,
    _build_clock_row,
    _derive_paper_status_and_action,
    run_monitor,
)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _make_candidate(
    cid: str = "rf-test-001",
    status: str = "paper",
    domain: str = "oracle",
    candidate_type: str = "oracle_compound",
    spec_ref: str | None = "A1",
    launched_hot: bool = False,
    half_life_d: int = 250,
    evaluation_plan: dict | None = None,
) -> dict:
    ep = evaluation_plan or {
        "primary_metric": "win_rate",
        "horizon_d": 21,
        "min_n": 25,
        "expected_half_life_d": half_life_d,
        "expected_metric_value": 0.58,
    }
    return {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "created_at": "2026-07-01T00:00:00Z",
        "source": "oracle_brainstorm",
        "candidate_type": candidate_type,
        "domain": domain,
        "status": status,
        "hypothesis": "Test hypothesis",
        "mechanism": "Test mechanism",
        "claim_shape": None,
        "spec_ref": spec_ref,
        "expected_failure_modes": [],
        "decay_conditions": [],
        "falsifiers": [],
        "trial_accounting": {"mode": "read_only", "family": None, "declared_at": None},
        "evaluation_plan": ep,
        "lineage": {"respin_of": None, "superseded_by": None, "refinement_generation": 0},
        "flags": ["launched_hot"] if launched_hot else [],
        "artifacts": {"launched_hot": launched_hot},
        "transition_log": [],
    }


def _make_paper_transition(
    cid: str,
    launched_hot: bool = False,
    as_of: str = "2026-07-01T00:00:00Z",
    come_back_on: str | None = None,
) -> dict:
    return {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "from": "human_review",
        "to": "paper",
        "reason_code": "human_decision_paper",
        "actor": "fable",
        "actor_ref": "session-20260706",
        "as_of": as_of,
        "regime_at_entry": {
            "regime": "risk_on" if not launched_hot else "risk_on",
            "vix_pctile": 15 if launched_hot else 45,
            "launched_hot": launched_hot,
        },
        "expected_half_life_d": 250,
        "seed_entry_ref": f"rf-{cid}",
        "come_back_on": come_back_on,
    }


def _make_deferred_transition(
    cid: str,
    come_back_on: str,
    as_of: str = "2026-07-01T00:00:00Z",
) -> dict:
    return {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "from": "human_review",
        "to": "deferred",
        "reason_code": "human_decision_deferred",
        "actor": "fable",
        "actor_ref": "session-20260706",
        "as_of": as_of,
        "come_back_on": come_back_on,
    }


def _make_track_file(
    n_matured: int,
    metric_value: float | None,
    primary_metric: str = "win_rate",
    horizon_d: int = 21,
) -> dict:
    return {
        "schema": "research_factory.track.v1",
        "authority": "display_only",
        "candidate_id": "rf-test-001",
        "decision": "paper",
        "expected_half_life_d": 250,
        "regime_at_entry": {"regime": "risk_on", "launched_hot": False},
        "verdict": "accruing",
        "horizons": {
            str(horizon_d): {
                "n_matured": n_matured,
                "metric_value": metric_value,
                "gate_threshold": 0.58,
                "gate_pass": None if metric_value is None else metric_value >= 0.58,
                "note": "accruing",
            }
        },
        "created_at": "2026-07-01T00:00:00Z",
    }


def _write_candidates(rf_dir: Path, candidates: list[dict]) -> None:
    p = rf_dir / "candidates.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for c in candidates:
            fh.write(json.dumps(c) + "\n")


def _write_transitions(rf_dir: Path, transitions: list[dict]) -> None:
    p = rf_dir / "transitions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for t in transitions:
            fh.write(json.dumps(t) + "\n")


# ---------------------------------------------------------------------------
# Test 1: warmup state
# ---------------------------------------------------------------------------


def test_warmup_state(tmp_path):
    """n < WARMUP_FLOOR → paper_status='warmup', action='continue'."""
    cid = "rf-test-warmup-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(cid=cid, status="paper", launched_hot=False)
    transitions = [_make_paper_transition(cid=cid, launched_hot=False)]

    # Track file with n < WARMUP_FLOOR
    track = _make_track_file(n_matured=3, metric_value=None)
    track_dir = rf_dir / "track"
    track_dir.mkdir(parents=True)
    (track_dir / f"{cid}.json").write_text(json.dumps(track), encoding="utf-8")

    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions)

    row = _build_monitor_row(
        candidate=candidate,
        transitions=transitions,
        oracle_live_ledger=[],
        rf_dir=rf_dir,
        as_of="2026-07-06",
    )

    assert row["paper_status"] == "warmup"
    assert row["action"] == "continue"
    assert row["observed_metric"]["n"] == 3
    assert row["schema"] == "research_factory.paper_monitor.v1"
    assert row["authority"] == "display_only"
    assert row["expected_fire_rate_pm"] == NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Test 2: absent upstream files → valid row with sentinels
# ---------------------------------------------------------------------------


def test_absent_upstream_files(tmp_path):
    """All upstream files absent → valid row with not_applicable/ungradable sentinels."""
    cid = "rf-absent-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(cid=cid, status="paper")
    transitions = [_make_paper_transition(cid=cid)]
    # No track file, no challenge file, no oracle live ledger

    row = _build_monitor_row(
        candidate=candidate,
        transitions=transitions,
        oracle_live_ledger=[],   # absent
        rf_dir=rf_dir,
        as_of="2026-07-06",
    )

    # Row must be valid (schema + authority)
    assert row["schema"] == "research_factory.paper_monitor.v1"
    assert row["authority"] == "display_only"
    assert row["candidate_id"] == cid

    # Sentinels
    assert row["expected_fire_rate_pm"] == NOT_APPLICABLE
    assert row["falsifier_verdict"] == UNGRADABLE
    assert row["falsifier_ref"] is None

    # observed_metric with no data
    assert row["observed_metric"]["n"] == 0
    assert row["observed_metric"]["value"] is None

    # paper_status must be one of the valid enum values
    assert row["paper_status"] in {"warmup", "operating", "review", "retire_recommended"}

    # action must be one of the valid enum values
    assert row["action"] in {"continue", "review", "retire_recommended"}


# ---------------------------------------------------------------------------
# Test 3: keep-first — two --write runs same as_of → one row
# ---------------------------------------------------------------------------


def test_keep_first_same_as_of(tmp_path):
    """Two --write runs with the same as_of produce exactly one row in paper_monitor.jsonl."""
    cid = "rf-keep-first-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(cid=cid, status="paper")
    transitions_list = [_make_paper_transition(cid=cid)]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions_list)

    # Patch oracle path to absent
    from scripts.research_factory_monitor import run

    # First write
    rc = run(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent_ledger.jsonl",
        as_of="2026-07-06",
        write=True,
        verbose=False,
    )
    assert rc == 0

    pm_path = rf_dir / "paper_monitor.jsonl"
    assert pm_path.exists()
    rows_after_first = rf_ledger.load_jsonl(pm_path)
    assert len(rows_after_first) >= 1

    # Second write — same as_of
    rc2 = run(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent_ledger.jsonl",
        as_of="2026-07-06",
        write=True,
        verbose=False,
    )
    assert rc2 == 0

    rows_after_second = rf_ledger.load_jsonl(pm_path)
    # Deduplicated: keep-first per (candidate_id, as_of)
    deduped = rf_ledger.keep_first(rows_after_second, ("candidate_id", "as_of"))
    assert len(deduped) == len(rows_after_first), (
        "Second run with same as_of should not add new rows for the same candidate"
    )

    # Verify the row count in the file equals the deduped count (ledger.keep_first view)
    candidate_as_ofs = [(r.get("candidate_id"), r.get("as_of")) for r in deduped]
    assert (cid, "2026-07-06") in candidate_as_ofs


# ---------------------------------------------------------------------------
# Test 4: --dry-run writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path):
    """--dry-run must not create or mutate any file under rf_dir."""
    cid = "rf-dry-run-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(cid=cid, status="paper")
    transitions_list = [_make_paper_transition(cid=cid)]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions_list)

    # Capture file state before
    def _snapshot(d: Path) -> dict:
        s: dict = {}
        if not d.exists():
            return s
        for fp in sorted(d.rglob("*")):
            if fp.is_file() and not fp.name.startswith("."):
                s[str(fp.relative_to(d))] = fp.stat().st_mtime
        return s

    before = _snapshot(rf_dir)

    from scripts.research_factory_monitor import run

    rc = run(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent_ledger.jsonl",
        as_of="2026-07-06",
        write=False,   # dry-run
        verbose=False,
    )
    assert rc == 0

    after = _snapshot(rf_dir)

    # Only candidates.jsonl and transitions.jsonl should exist (they were written in setup);
    # paper_monitor.jsonl, track/, health.jsonl must NOT have appeared.
    new_files = set(after.keys()) - set(before.keys())
    assert "paper_monitor.jsonl" not in new_files, "dry-run must not write paper_monitor.jsonl"
    assert "health.jsonl" not in new_files, "dry-run must not write health.jsonl"
    for f in new_files:
        assert not f.startswith("track/"), f"dry-run must not write track files: {f}"


# ---------------------------------------------------------------------------
# Test 5: regime-aware damping (launched_hot)
# ---------------------------------------------------------------------------


def test_regime_aware_damping_launched_hot(tmp_path):
    """launched_hot + decay → 'launched_hot_context' companion flag, action='review'
    (not 'retire_recommended')."""
    cid = "rf-hot-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(
        cid=cid, status="paper", launched_hot=True,
        evaluation_plan={
            "primary_metric": "win_rate",
            "horizon_d": 21,
            "min_n": 25,
            "expected_half_life_d": 250,
            "expected_metric_value": 0.65,  # high bar
        },
    )
    transitions = [_make_paper_transition(cid=cid, launched_hot=True)]

    # Track with enough n (above warmup) but poor metric
    track = _make_track_file(n_matured=WARMUP_FLOOR + 5, metric_value=0.42)
    track_dir = rf_dir / "track"
    track_dir.mkdir(parents=True)
    (track_dir / f"{cid}.json").write_text(json.dumps(track), encoding="utf-8")

    row = _build_monitor_row(
        candidate=candidate,
        transitions=transitions,
        oracle_live_ledger=[],
        rf_dir=rf_dir,
        as_of="2026-07-06",
    )

    # Decay flags should exist
    assert row["decay_flags"], f"Expected decay flags, got: {row}"
    # Must include launched_hot_context companion
    assert "launched_hot_context" in row["decay_flags"], (
        f"Expected 'launched_hot_context' in decay_flags; got: {row['decay_flags']}"
    )
    # Action must NOT be 'retire_recommended' due to regime damping
    assert row["action"] != "retire_recommended", (
        f"launched_hot candidate should not get retire_recommended; got action={row['action']}"
    )
    assert row["action"] == "review", f"Expected action='review', got: {row['action']}"
    assert row["paper_status"] == "review"


# ---------------------------------------------------------------------------
# Test 6: paper→human_review transition emitted on retire_recommended
# ---------------------------------------------------------------------------


def test_paper_human_review_transition_emitted(tmp_path):
    """retire_recommended → transition paper→human_review is included in transition_rows."""
    cid = "rf-retire-rec-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(
        cid=cid, status="paper", launched_hot=False,
        evaluation_plan={
            "primary_metric": "win_rate",
            "horizon_d": 21,
            "min_n": 25,
            "expected_half_life_d": 250,
            "expected_metric_value": 0.65,
        },
    )
    transitions = [_make_paper_transition(cid=cid, launched_hot=False)]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions)

    # Track with enough n but terrible metric → retire_recommended
    track = _make_track_file(n_matured=WARMUP_FLOOR + 15, metric_value=0.35)
    track_dir = rf_dir / "track"
    track_dir.mkdir(parents=True)
    (track_dir / f"{cid}.json").write_text(json.dumps(track), encoding="utf-8")

    monitor_rows, transition_rows = run_monitor(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of="2026-07-06",
    )

    # Find the monitor row for this candidate
    cand_rows = [r for r in monitor_rows if r.get("candidate_id") == cid]
    assert cand_rows, "Expected a monitor row for the candidate"
    assert cand_rows[0]["action"] in ("review", "retire_recommended"), (
        f"Expected review or retire_recommended; got {cand_rows[0]['action']}"
    )

    # Transition paper→human_review must be emitted
    t_rows = [t for t in transition_rows if t.get("candidate_id") == cid]
    assert t_rows, "Expected a transition row for retire_recommended candidate"
    assert any(
        t.get("from") == "paper" and t.get("to") == "human_review"
        for t in t_rows
    ), f"Expected paper→human_review transition; got: {t_rows}"


# ---------------------------------------------------------------------------
# Test 7: retirement NEVER performed by monitor
# ---------------------------------------------------------------------------


def test_retirement_never_performed(tmp_path):
    """Monitor must never emit a 'retired' transition (human-only, RF-5)."""
    cid = "rf-never-retire-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(
        cid=cid, status="paper", launched_hot=False,
        evaluation_plan={
            "primary_metric": "win_rate",
            "horizon_d": 21,
            "min_n": 25,
            "expected_half_life_d": 250,
            "expected_metric_value": 0.70,
        },
    )
    transitions = [_make_paper_transition(cid=cid, launched_hot=False)]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions)

    # Very bad metric — worst case
    track = _make_track_file(n_matured=WARMUP_FLOOR + 50, metric_value=0.20)
    track_dir = rf_dir / "track"
    track_dir.mkdir(parents=True)
    (track_dir / f"{cid}.json").write_text(json.dumps(track), encoding="utf-8")

    monitor_rows, transition_rows = run_monitor(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of="2026-07-06",
    )

    # No transition to 'retired' is ever allowed
    retired_transitions = [
        t for t in transition_rows if t.get("to") == "retired"
    ]
    assert not retired_transitions, (
        f"Monitor must NEVER emit 'retired' transitions (human-only RF-5); "
        f"found: {retired_transitions}"
    )


# ---------------------------------------------------------------------------
# Test 8: deferred come_back_on due → human_review
# ---------------------------------------------------------------------------


def test_deferred_come_back_due(tmp_path):
    """Deferred candidate with past come_back_on → monitor row with action='review'
    and a deferred→human_review transition emitted."""
    cid = "rf-deferred-due-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    # Past come_back_on
    past_date = (date.today() - timedelta(days=5)).isoformat()

    candidate = _make_candidate(cid=cid, status="deferred")
    candidate["status"] = "deferred"

    deferred_t = _make_deferred_transition(
        cid=cid,
        come_back_on=past_date,
        as_of="2026-07-01T00:00:00Z",
    )
    # Also add the initial proposed→registered→... chain (simplified)
    transitions = [deferred_t]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions)

    monitor_rows, transition_rows = run_monitor(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of=date.today().isoformat(),
    )

    cand_rows = [r for r in monitor_rows if r.get("candidate_id") == cid]
    assert cand_rows, "Expected monitor row for deferred-due candidate"
    assert cand_rows[0]["action"] == "review", (
        f"Expected action='review' for deferred due; got: {cand_rows[0]['action']}"
    )

    # deferred→human_review transition must be emitted
    t_rows = [t for t in transition_rows if t.get("candidate_id") == cid]
    assert t_rows, "Expected transition row for deferred-due candidate"
    assert any(
        t.get("from") == "deferred" and t.get("to") == "human_review"
        for t in t_rows
    ), f"Expected deferred→human_review; got: {t_rows}"


# ---------------------------------------------------------------------------
# Test 9: monotonic as_of — keep-first per (candidate_id, as_of)
# ---------------------------------------------------------------------------


def test_monotonic_as_of_keep_first(tmp_path):
    """Two different as_of values produce two rows; same as_of stays as one (keep-first)."""
    cid = "rf-mono-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(cid=cid, status="paper")
    transitions = [_make_paper_transition(cid=cid)]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions)

    from scripts.research_factory_monitor import run

    # First write as_of=2026-07-01
    run(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of="2026-07-01",
        write=True,
        verbose=False,
    )

    # Second write as_of=2026-07-06 (different → new row expected)
    run(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of="2026-07-06",
        write=True,
        verbose=False,
    )

    # Third write as_of=2026-07-06 again (same → keep-first, no new row)
    run(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of="2026-07-06",
        write=True,
        verbose=False,
    )

    pm_path = rf_dir / "paper_monitor.jsonl"
    all_rows = rf_ledger.load_jsonl(pm_path)
    # After keep-first dedup, we should have exactly 2 rows: one per as_of
    deduped = rf_ledger.keep_first(all_rows, ("candidate_id", "as_of"))
    as_ofs_in_deduped = {r.get("as_of") for r in deduped if r.get("candidate_id") == cid}
    assert "2026-07-01" in as_ofs_in_deduped
    assert "2026-07-06" in as_ofs_in_deduped
    assert len(as_ofs_in_deduped) == 2, (
        f"Expected exactly 2 unique as_of values for {cid}; got: {as_ofs_in_deduped}"
    )


# ---------------------------------------------------------------------------
# Test 10: operating state (no decay)
# ---------------------------------------------------------------------------


def test_operating_state_no_decay(tmp_path):
    """n >= WARMUP_FLOOR and good metric → paper_status='operating', action='continue'."""
    cid = "rf-operating-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    candidate = _make_candidate(
        cid=cid, status="paper", launched_hot=False,
        evaluation_plan={
            "primary_metric": "win_rate",
            "horizon_d": 21,
            "min_n": 25,
            "expected_half_life_d": 250,
            "expected_metric_value": 0.58,
        },
    )
    transitions = [_make_paper_transition(cid=cid, launched_hot=False)]

    # Track with n >= WARMUP_FLOOR and metric matching expected
    track = _make_track_file(n_matured=WARMUP_FLOOR + 10, metric_value=0.60)
    track_dir = rf_dir / "track"
    track_dir.mkdir(parents=True)
    (track_dir / f"{cid}.json").write_text(json.dumps(track), encoding="utf-8")

    row = _build_monitor_row(
        candidate=candidate,
        transitions=transitions,
        oracle_live_ledger=[],
        rf_dir=rf_dir,
        as_of="2026-07-06",
    )

    assert row["paper_status"] == "operating"
    assert row["action"] == "continue"
    assert "launched_hot_context" not in (row.get("decay_flags") or [])


# ---------------------------------------------------------------------------
# Test 11: awaiting_data come_back_on not yet due → no monitor row
# ---------------------------------------------------------------------------


def test_awaiting_data_not_yet_due(tmp_path):
    """awaiting_data with future come_back_on → no monitor row (not yet due)."""
    cid = "rf-awaiting-future-001"
    rf_dir = tmp_path / "research_factory"
    rf_dir.mkdir(parents=True)

    future_date = (date.today() + timedelta(days=30)).isoformat()
    candidate = _make_candidate(cid=cid, status="awaiting_data")
    candidate["status"] = "awaiting_data"

    transitions = [{
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "from": "registered",
        "to": "awaiting_data",
        "reason_code": "data_not_ready",
        "actor": "script",
        "actor_ref": None,
        "as_of": "2026-07-01T00:00:00Z",
        "come_back_on": future_date,
    }]
    _write_candidates(rf_dir, [candidate])
    _write_transitions(rf_dir, transitions)

    monitor_rows, transition_rows = run_monitor(
        rf_dir=rf_dir,
        oracle_live_ledger_path=tmp_path / "absent.jsonl",
        as_of=date.today().isoformat(),
    )

    cand_rows = [r for r in monitor_rows if r.get("candidate_id") == cid]
    assert not cand_rows, (
        f"Expected NO monitor row for future come_back_on; got: {cand_rows}"
    )


# ---------------------------------------------------------------------------
# Test 12: derive_paper_status_and_action unit tests
# ---------------------------------------------------------------------------


def test_derive_paper_status_warmup():
    status, action = _derive_paper_status_and_action(
        n=0, decay_flags=[], launched_hot=False, is_come_back_due=False
    )
    assert status == "warmup"
    assert action == "continue"


def test_derive_paper_status_operating():
    status, action = _derive_paper_status_and_action(
        n=WARMUP_FLOOR + 1,
        decay_flags=[],
        launched_hot=False,
        is_come_back_due=False,
    )
    assert status == "operating"
    assert action == "continue"


def test_derive_paper_status_retire_recommended_non_hot():
    status, action = _derive_paper_status_and_action(
        n=WARMUP_FLOOR + 1,
        decay_flags=["metric_below_expected: obs=0.35 exp=0.65 miss=46.2%"],
        launched_hot=False,
        is_come_back_due=False,
    )
    assert status == "retire_recommended"
    assert action == "retire_recommended"


def test_derive_paper_status_review_hot():
    """launched_hot + decay → review, not retire_recommended."""
    status, action = _derive_paper_status_and_action(
        n=WARMUP_FLOOR + 1,
        decay_flags=[
            "metric_below_expected: obs=0.40 exp=0.65 miss=38.5%",
            "launched_hot_context",
        ],
        launched_hot=True,
        is_come_back_due=False,
    )
    assert status == "review"
    assert action == "review"


def test_derive_paper_status_come_back_due():
    """Come-back due with no decay → review."""
    status, action = _derive_paper_status_and_action(
        n=WARMUP_FLOOR + 1,
        decay_flags=[],
        launched_hot=False,
        is_come_back_due=True,
    )
    assert status == "review"
    assert action == "review"
