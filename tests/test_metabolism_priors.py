"""tests/test_metabolism_priors.py — Meta-learning spine (R-V8-10/R-V8-11/R-V8-12).

COVERAGE:
  P1  ledger append: new closed row appended to outcome_priors.jsonl
  P2  idempotent dedup: appending the same proposal_id twice is a no-op
  P3  backfill once: existing verify records land in ledger; second call adds zero
  P4  prior survives trial_ledger rotation: after clearing trial_ledger, prior is
      computed from outcome_priors.jsonl (not trial_ledger)
  P5  demote fires at n>=5 AND hit_rate<0.25 (by_kind bucket)
  P6  demote does NOT fire when n<5 (even if hit_rate is terrible)
  P7  demote does NOT fire when hit_rate>=0.25 (even if n is large)
  P8  demoted items at bottom BUT present with prior_demoted:true + prior_bucket
  P9  never-promote: a high-hit bucket (hit_rate=1.0, n=10) does NOT move items up
  P10 (lobe,sensor) bucket fires independently of kind bucket
  P11 recall parity wire: agenda._build_agenda_inner calls recall.recall_lessons

All tests are HERMETIC (tmp dirs, no network, no real LLM calls).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Fixtures / helpers ─────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    """Create a minimal metabolism directory tree in a temp dir."""
    d = Path(tempfile.mkdtemp())
    for sub in [
        "data/metabolism/verify",
        "data/metabolism/journal",
        "data/metabolism/agenda",
        "data/metabolism/lessons",
        "config",
    ]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _write_verify_record(
    root: Path,
    proposal_id: str,
    cycle_id: str = "cycle-001",
    outcome: str = "CONFIRMED",
    triage_class: str = "confirmed",
    kind: str = "test",
    tier: str = "T1",
    lobe: str = "til",
    sensors: list[str] | None = None,
) -> Path:
    """Write a minimal verify record to data/metabolism/verify/."""
    sensors = sensors or ["ic_sharpe"]
    record = {
        "schema": "metabolism.verify.v1",
        "cycle_id": cycle_id,
        "proposal_id": proposal_id,
        "check_by": "2026-01-01",
        "contract": {
            "kind": kind,
            "tier": tier,
            "lobe": lobe,
            "fitness_sensors": sensors,
            "targets_sensor": sensors[0] if sensors else "",
        },
        "realized": {"outcome": outcome, "detail": "", "delta_vs_contract": None},
        "triage": {
            "classification": triage_class,
            "action": "keep" if outcome == "CONFIRMED" else "revert_plan",
        },
        "ts": "2026-01-01T00:00:00+00:00",
    }
    p = root / "data" / "metabolism" / "verify" / f"{cycle_id}.json"
    p.write_text(json.dumps(record), encoding="utf-8")
    return p


def _write_trial_ledger(
    root: Path,
    contracts: list[dict[str, Any]],
) -> None:
    """Write a trial_ledger.jsonl with the given contracts."""
    p = root / "data" / "trial_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(c) for c in contracts]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _priors_path(root: Path) -> Path:
    return root / "data" / "metabolism" / "outcome_priors.jsonl"


def _read_priors(root: Path) -> list[dict[str, Any]]:
    p = _priors_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


# ── P1: ledger append ──────────────────────────────────────────────────────────

def test_p1_ledger_append():
    """_append_outcome_prior_row writes a row to outcome_priors.jsonl."""
    from engine.metabolism.dream import _append_outcome_prior_row
    root = _tmp_root()
    row = {
        "proposal_id": "p-001",
        "kind": "test",
        "tier": "T1",
        "lobe": "til",
        "sensors": ["ic_sharpe"],
        "outcome": "CONFIRMED",
        "triage": "confirmed",
        "ts": "2026-01-01T00:00:00+00:00",
    }
    _append_outcome_prior_row(root, row)
    rows = _read_priors(root)
    assert len(rows) == 1
    assert rows[0]["proposal_id"] == "p-001"
    assert rows[0]["outcome"] == "CONFIRMED"


# ── P2: idempotent dedup ───────────────────────────────────────────────────────

def test_p2_idempotent_dedup():
    """Appending the same proposal_id twice: _load_outcome_prior_ids deduplicates."""
    from engine.metabolism.dream import _append_outcome_prior_row, _load_outcome_prior_ids
    root = _tmp_root()
    row = {
        "proposal_id": "p-dup",
        "kind": "test",
        "tier": "T1",
        "lobe": "til",
        "sensors": [],
        "outcome": "CONFIRMED",
        "triage": "confirmed",
        "ts": "2026-01-01T00:00:00+00:00",
    }
    # First append
    _append_outcome_prior_row(root, row)
    # Simulate the dedup check (as done in _accrue_new_outcome_rows)
    seen = _load_outcome_prior_ids(root)
    assert "p-dup" in seen
    # Second append only happens if not in seen — simulate the guard
    if "p-dup" not in seen:
        _append_outcome_prior_row(root, row)
    rows = _read_priors(root)
    assert len(rows) == 1, "dedup guard prevents double-append"


def test_p2b_accrue_dedup():
    """_accrue_new_outcome_rows does not append duplicate proposal_ids."""
    from engine.metabolism.dream import (
        _append_outcome_prior_row,
        _accrue_new_outcome_rows,
    )
    root = _tmp_root()
    # Pre-populate ledger with p-001
    existing = {
        "proposal_id": "p-001",
        "kind": "test",
        "tier": "T1",
        "lobe": "til",
        "sensors": [],
        "outcome": "CONFIRMED",
        "triage": "confirmed",
        "ts": "2026-01-01T00:00:00+00:00",
    }
    _append_outcome_prior_row(root, existing)

    # closed_contracts has p-001 and p-002
    closed = [
        {
            "proposal_id": "p-001",
            "kind": "test",
            "tier": "T1",
            "outcome": "CONFIRMED",
        },
        {
            "proposal_id": "p-002",
            "kind": "engine",
            "tier": "T1",
            "outcome": "FALSIFIER_TRIPPED",
        },
    ]
    added = _accrue_new_outcome_rows(root, closed, [], "2026-01-01T00:00:00+00:00")
    assert added == 1, "only p-002 should be added (p-001 already in ledger)"
    rows = _read_priors(root)
    assert len(rows) == 2
    pids = {r["proposal_id"] for r in rows}
    assert "p-001" in pids and "p-002" in pids


# ── P3: backfill once ─────────────────────────────────────────────────────────

def test_p3_backfill_once():
    """_backfill_outcome_priors: existing verify records land in ledger; second call adds 0."""
    from engine.metabolism.dream import _backfill_outcome_priors
    root = _tmp_root()
    _write_verify_record(root, "bp-001", cycle_id="cycle-bp1", outcome="CONFIRMED")
    _write_verify_record(root, "bp-002", cycle_id="cycle-bp2", outcome="FALSIFIER_TRIPPED")

    added1 = _backfill_outcome_priors(root)
    rows = _read_priors(root)
    assert added1 == 2, f"expected 2 rows backfilled, got {added1}"
    assert len(rows) == 2

    # Second call: no new rows
    added2 = _backfill_outcome_priors(root)
    rows2 = _read_priors(root)
    assert added2 == 0, "second backfill should add nothing (all already present)"
    assert len(rows2) == 2


# ── P4: prior survives trial_ledger rotation ──────────────────────────────────

def test_p4_prior_survives_trial_ledger_rotation():
    """Preference prior is computed from outcome_priors.jsonl, not trial_ledger.jsonl.

    After clearing trial_ledger (simulating a rotation), the dream cycle should
    still produce a prior with data because the durable ledger survives.
    """
    from engine.metabolism import dream as _dream

    root = _tmp_root()
    # Write 12 verify records so we exceed MIN_CLOSED_CONTRACTS (10)
    for i in range(12):
        _write_verify_record(
            root,
            f"prior-{i:03d}",
            cycle_id=f"cycle-{i:03d}",
            outcome="CONFIRMED" if i % 2 == 0 else "FALSIFIER_TRIPPED",
        )

    # First dream cycle — populates outcome_priors.jsonl via backfill
    with patch("scripts.metabolism_guard.is_paused", return_value=False):
        # Patch the guard import
        pass

    import os
    os.environ["AUTONOMY_PAUSED"] = "false"
    try:
        # Run with dry_run=False so ledger is written
        result1 = _dream.run_dream_cycle(root=root, today="2026-12-01", dry_run=False)
    finally:
        del os.environ["AUTONOMY_PAUSED"]

    rows = _read_priors(root)
    assert len(rows) >= 12, f"expected >=12 prior rows, got {len(rows)}"
    assert result1.get("status") != "insufficient_data", (
        f"expected calibration, got {result1.get('status')}"
    )

    # NOW rotate trial_ledger (clear it)
    trial_path = root / "data" / "trial_ledger.jsonl"
    trial_path.write_text("", encoding="utf-8")

    # Second dream cycle — must still compute from durable ledger
    os.environ["AUTONOMY_PAUSED"] = "false"
    try:
        result2 = _dream.run_dream_cycle(root=root, today="2026-12-01", dry_run=False)
    finally:
        del os.environ["AUTONOMY_PAUSED"]

    assert result2.get("status") != "insufficient_data", (
        "prior should survive trial_ledger rotation — computed from outcome_priors.jsonl"
    )
    assert result2.get("calibration") is not None


# ── P5: demote fires at n>=5 AND hit_rate<0.25 ────────────────────────────────

def test_p5_demote_fires_at_threshold():
    """_demote_prior_buckets fires for kind with n=5, hit_rate=0.0."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            "test": {"total": 5, "confirmed": 0, "hit_rate": 0.0},
        },
        "by_lobe_sensor": {},
    }
    items = [
        {"title": "A", "bucket": "test", "target_lobe": None},
        {"title": "B", "bucket": "NOVEL_BUILD", "target_lobe": None},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # "A" (bucket=test) should be demoted to bottom
    assert result[-1]["title"] == "A"
    assert result[-1]["prior_demoted"] is True
    assert "kind:test" in result[-1]["prior_bucket"]

    # "B" should NOT be demoted
    assert result[0]["title"] == "B"
    assert not result[0].get("prior_demoted")


# ── P6: demote does NOT fire when n<5 ────────────────────────────────────────

def test_p6_demote_no_fire_small_n():
    """_demote_prior_buckets does NOT fire when n=4 even if hit_rate=0.0."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            "test": {"total": 4, "confirmed": 0, "hit_rate": 0.0},
        },
        "by_lobe_sensor": {},
    }
    items = [
        {"title": "A", "bucket": "test", "target_lobe": None},
        {"title": "B", "bucket": "NOVEL_BUILD", "target_lobe": None},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # Neither item should be demoted (n=4 < 5)
    for item in result:
        assert not item.get("prior_demoted"), f"item {item['title']} incorrectly demoted"


# ── P7: demote does NOT fire when hit_rate>=0.25 ─────────────────────────────

def test_p7_demote_no_fire_good_hit_rate():
    """_demote_prior_buckets does NOT fire when hit_rate=0.25 (exactly at threshold)."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            "test": {"total": 8, "confirmed": 2, "hit_rate": 0.25},
        },
        "by_lobe_sensor": {},
    }
    items = [
        {"title": "A", "bucket": "test", "target_lobe": None},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)
    assert not result[0].get("prior_demoted"), "hit_rate=0.25 is NOT below threshold (strict <)"


def test_p7b_demote_fires_just_below_threshold():
    """_demote_prior_buckets fires when hit_rate=0.249 (strictly below 0.25)."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            "test": {"total": 8, "confirmed": 1, "hit_rate": 0.124},
        },
        "by_lobe_sensor": {},
    }
    items = [
        {"title": "A", "bucket": "test", "target_lobe": None},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)
    assert result[0].get("prior_demoted") is True


# ── P8: demoted items at bottom but present with flag ────────────────────────

def test_p8_demoted_items_present_at_bottom():
    """Demoted items appear at the bottom with prior_demoted:true — never dropped."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            "bad_kind": {"total": 10, "confirmed": 1, "hit_rate": 0.1},
        },
        "by_lobe_sensor": {},
    }
    items = [
        {"title": "Good A", "bucket": "NOVEL_BUILD", "target_lobe": None},
        {"title": "Bad B", "bucket": "bad_kind", "target_lobe": None},
        {"title": "Good C", "bucket": "URGENT_FIX", "target_lobe": None},
        {"title": "Bad D", "bucket": "bad_kind", "target_lobe": None},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # All 4 items must be present
    assert len(result) == 4

    # Demoted items at the end
    demoted = [it for it in result if it.get("prior_demoted")]
    non_demoted = [it for it in result if not it.get("prior_demoted")]

    assert len(demoted) == 2
    assert len(non_demoted) == 2

    # The last 2 items are the demoted ones
    assert result[-2]["prior_demoted"] is True
    assert result[-1]["prior_demoted"] is True

    # Non-demoted items come first
    non_dem_titles = {it["title"] for it in non_demoted}
    assert "Good A" in non_dem_titles
    assert "Good C" in non_dem_titles

    # Order among demoted is stable (Bad B before Bad D)
    dem_titles = [it["title"] for it in result if it.get("prior_demoted")]
    assert dem_titles == ["Bad B", "Bad D"]


# ── P9: never-promote ────────────────────────────────────────────────────────

def test_p9_never_promote():
    """A high-hit bucket (hit_rate=1.0) does NOT move items up in the agenda."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            "great_kind": {"total": 10, "confirmed": 10, "hit_rate": 1.0},
        },
        "by_lobe_sensor": {},
    }
    # Items ordered with great_kind at position 2 (not first)
    items = [
        {"title": "A", "bucket": "NOVEL_BUILD", "target_lobe": None},
        {"title": "B", "bucket": "URGENT_FIX", "target_lobe": None},
        {"title": "C", "bucket": "great_kind", "target_lobe": None},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # Order must be unchanged (no promotion)
    assert [it["title"] for it in result] == ["A", "B", "C"]
    # C not demoted (good hit rate)
    assert not result[2].get("prior_demoted")


# ── P10: (lobe, sensor) bucket independent of kind ───────────────────────────

def test_p10_lobe_sensor_bucket_independent():
    """(lobe, sensor) bucket can fire even if kind bucket is healthy."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            # kind "engine" has a GOOD hit rate → kind bucket should NOT fire
            "engine": {"total": 10, "confirmed": 8, "hit_rate": 0.8},
        },
        "by_lobe_sensor": {
            # lobe=til, sensor=ic_sharpe has a BAD hit rate → should demote
            "til:ic_sharpe": {"total": 6, "confirmed": 0, "hit_rate": 0.0},
        },
    }
    items = [
        {"title": "Good", "bucket": "engine", "target_lobe": "other_lobe"},
        {"title": "Weak sensor", "bucket": "engine", "target_lobe": "til"},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # "Weak sensor" item (lobe=til) should be demoted by lobe_sensor bucket
    til_item = next(it for it in result if it["title"] == "Weak sensor")
    assert til_item.get("prior_demoted") is True
    assert "lobe_sensor:til:ic_sharpe" in til_item.get("prior_bucket", "")

    # "Good" item (lobe=other_lobe, no matching lobe_sensor bucket) should NOT be demoted
    good_item = next(it for it in result if it["title"] == "Good")
    assert not good_item.get("prior_demoted")


def test_p10b_lobe_sensor_bucket_from_calibration():
    """_build_calibration_from_priors produces by_lobe_sensor buckets correctly."""
    from engine.metabolism.dream import _build_calibration_from_priors

    prior_rows = [
        {"proposal_id": "a", "kind": "test", "tier": "T1", "lobe": "til",
         "sensors": ["ic_sharpe"], "outcome": "CONFIRMED", "triage": "confirmed"},
        {"proposal_id": "b", "kind": "test", "tier": "T1", "lobe": "til",
         "sensors": ["ic_sharpe"], "outcome": "FALSIFIER_TRIPPED", "triage": "overfit"},
        {"proposal_id": "c", "kind": "test", "tier": "T1", "lobe": "til",
         "sensors": ["ic_sharpe"], "outcome": "FALSIFIER_TRIPPED", "triage": "overfit"},
        {"proposal_id": "d", "kind": "engine", "tier": "T1", "lobe": "nw",
         "sensors": ["breadth"], "outcome": "CONFIRMED", "triage": "confirmed"},
        {"proposal_id": "e", "kind": "engine", "tier": "T1", "lobe": "nw",
         "sensors": ["breadth"], "outcome": "CONFIRMED", "triage": "confirmed"},
    ]
    cal = _build_calibration_from_priors(prior_rows)

    assert "by_lobe_sensor" in cal
    # til:ic_sharpe: 1 confirmed / 3 total = 0.333
    key_til = "til:ic_sharpe"
    assert key_til in cal["by_lobe_sensor"]
    til_stats = cal["by_lobe_sensor"][key_til]
    assert til_stats["total"] == 3
    assert til_stats["confirmed"] == 1

    # nw:breadth: 2 confirmed / 2 total = 1.0
    key_nw = "nw:breadth"
    assert key_nw in cal["by_lobe_sensor"]
    nw_stats = cal["by_lobe_sensor"][key_nw]
    assert nw_stats["total"] == 2
    assert nw_stats["confirmed"] == 2
    assert nw_stats["hit_rate"] == 1.0

    # by_kind: test has 1/3, engine has 2/2
    assert cal["by_kind"]["test"]["hit_rate"] == round(1 / 3, 3)
    assert cal["by_kind"]["engine"]["hit_rate"] == 1.0


# ── P11: recall parity wire ──────────────────────────────────────────────────

def test_p11_recall_parity_wire():
    """agenda._build_agenda_inner calls recall.recall_lessons (parity with propose.py)."""
    import engine.metabolism.agenda as agenda_mod

    root = _tmp_root()

    recall_call_log = []

    def _mock_recall_lessons(**kwargs):
        recall_call_log.append(kwargs)
        return "(no lessons)"

    # Patch the recall import inside the agenda module and disable LLM + guard
    with (
        patch.object(
            agenda_mod,
            "_build_orchestrator_system",
            return_value="sys-prompt",
        ),
        patch.object(
            agenda_mod,
            "get_open_rows",
            return_value=[],
        ),
        patch.object(
            agenda_mod,
            "build_organism_state",
            return_value={},
        ),
        patch("engine.metabolism.recall.recall_lessons", side_effect=_mock_recall_lessons),
    ):
        result = agenda_mod.build_agenda(
            cycle_id="recall-test",
            root=root,
            providers=None,  # no LLM call
            model=None,
        )

    # The recall call should have been attempted (wire is present)
    # NOTE: if lessons.jsonl is absent, the mock still gets called
    assert len(recall_call_log) >= 1, (
        "agenda.build_agenda must call recall.recall_lessons (R-V8-12 parity)"
    )
    assert result.get("schema") == "metabolism.agenda.v1"


# ── P11b: recall failure is non-fatal ────────────────────────────────────────

def test_p11b_recall_failure_nonfatal():
    """If recall_lessons raises, agenda still returns a valid artifact."""
    import engine.metabolism.agenda as agenda_mod

    root = _tmp_root()

    with (
        patch.object(agenda_mod, "_build_orchestrator_system", return_value="sys"),
        patch.object(agenda_mod, "get_open_rows", return_value=[]),
        patch.object(agenda_mod, "build_organism_state", return_value={}),
        patch("engine.metabolism.recall.recall_lessons", side_effect=RuntimeError("boom")),
    ):
        result = agenda_mod.build_agenda(
            cycle_id="recall-fail",
            root=root,
            providers=None,
            model=None,
        )

    assert result.get("schema") == "metabolism.agenda.v1"
    assert isinstance(result.get("items"), list)


# ── P12: _build_calibration_from_priors handles empty ────────────────────────

def test_p12_calibration_empty_priors():
    """_build_calibration_from_priors with empty input returns valid empty structure."""
    from engine.metabolism.dream import _build_calibration_from_priors

    cal = _build_calibration_from_priors([])
    assert cal["by_kind"] == {}
    assert cal["by_lobe_sensor"] == {}
    assert cal["overall"]["total"] == 0
    assert cal["overall"]["hit_rate"] is None


# ── P13: get_calibration_from_priors public API ───────────────────────────────

def test_p13_get_calibration_from_priors():
    """get_calibration_from_priors returns {} when ledger is absent."""
    from engine.metabolism.dream import get_calibration_from_priors
    root = _tmp_root()
    cal = get_calibration_from_priors(root=root)
    assert cal == {}


# ── P14: demote flag in agenda output ────────────────────────────────────────

def test_p14_demote_flag_in_agenda():
    """Prior de-rank result flows through build_agenda and appears in the agenda artifact."""
    import engine.metabolism.agenda as agenda_mod
    from engine.metabolism.dream import _append_outcome_prior_row

    root = _tmp_root()

    # Write 5 prior rows all FALSIFIER_TRIPPED for kind "NOVEL_BUILD"
    for i in range(5):
        _append_outcome_prior_row(root, {
            "proposal_id": f"demote-{i}",
            "kind": "NOVEL_BUILD",
            "tier": "T1",
            "lobe": "til",
            "sensors": [],
            "outcome": "FALSIFIER_TRIPPED",
            "triage": "overfit",
            "ts": "2026-01-01T00:00:00+00:00",
        })

    # Write budget config with demote thresholds
    budget_yml = (
        "schema: metabolism_budget.v1\n"
        "per_cycle_usd_cap: 25\n"
        "per_cycle_token_cap: 25000000\n"
        "max_docket_size: 5\n"
        "circuit_breaker_trip: 3\n"
        "prior_demote_min_n: 5\n"
        "prior_demote_hit_rate: 0.25\n"
    )
    (root / "config" / "metabolism_budget.yml").write_text(budget_yml, encoding="utf-8")

    # Fabricate one LLM-returned item with bucket=NOVEL_BUILD
    raw_items = [
        {
            "title": "Build a weak sensor",
            "bucket": "NOVEL_BUILD",
            "severity": "low",
            "target_lobe": "til",
            "rationale": "test",
        }
    ]

    with (
        patch.object(agenda_mod, "_build_orchestrator_system", return_value="sys"),
        patch.object(agenda_mod, "get_open_rows", return_value=[]),
        patch.object(agenda_mod, "build_organism_state", return_value={}),
        patch.object(agenda_mod, "_call_llm", return_value=(
            json.dumps({"items": raw_items}), None, "test-provider"
        )),
        patch("engine.metabolism.recall.recall_lessons", return_value="(none)"),
    ):
        result = agenda_mod.build_agenda(
            cycle_id="demote-test",
            root=root,
            providers=[{"model": "test"}],
            model=None,
        )

    items = result.get("items") or []
    assert len(items) == 1
    item = items[0]
    assert item.get("prior_demoted") is True, (
        "NOVEL_BUILD bucket with 0/5 hit rate should be demoted"
    )
    assert item.get("prior_bucket") is not None
