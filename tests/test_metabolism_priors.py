"""tests/test_metabolism_priors.py — Meta-learning spine (R-V8-10/R-V8-11/R-V8-12).

COVERAGE:
  P1  ledger append: new closed row appended to outcome_priors.jsonl
  P2  idempotent dedup: appending the same proposal_id twice is a no-op
  P3  backfill once: existing verify records land in ledger; second call adds zero
  P4  prior survives trial_ledger rotation: after clearing trial_ledger, prior is
      computed from outcome_priors.jsonl (not trial_ledger)
  P5  demote fires at n>=5 AND hit_rate<0.25 (lobe,sensor bucket ONLY — FIX-2)
  P6  demote does NOT fire when n<5 (even if hit_rate is terrible)
  P7  demote does NOT fire when hit_rate>=0.25 (even if n is large)
  P8  demoted items at bottom BUT present with prior_demoted:true + prior_bucket
  P9  never-promote: a high-hit (lobe,sensor) bucket does NOT move items up
  P10 (lobe,sensor) bucket fires — sensor name must appear in item text (FIX-3)
  P11 recall parity wire: agenda._build_agenda_inner calls recall.recall_lessons
  P15 FIX-3 construction-scoped: item naming sensor Y not demoted by bad record on X
  P16 FIX-4 UNVERIFIABLE excluded from calibration denominator
  P17 FIX-4 confirmed requires triage=='confirmed' conjunction
  P18 FIX-5 demoted items survive docket-cap trim

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


# ── P5: demote fires at n>=5 AND hit_rate<0.25 (lobe,sensor) ─────────────────

def test_p5_demote_fires_at_threshold():
    """_demote_prior_buckets fires for (lobe,sensor) with n=5, hit_rate=0.0.

    FIX-2: kind-based de-rank is removed; only (lobe,sensor) buckets fire.
    FIX-3: item title must contain the sensor name for the demote to fire.
    """
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {
            # kind bucket is present but must NOT trigger demote (FIX-2)
            "NOVEL_BUILD": {"total": 5, "confirmed": 0, "hit_rate": 0.0},
        },
        "by_lobe_sensor": {
            "til:weak_signal": {"total": 5, "confirmed": 0, "hit_rate": 0.0},
        },
    }
    items = [
        # item names the bad sensor → should be demoted
        {
            "title": "Improve weak_signal for til lobe",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "",
        },
        # item has same bucket but different lobe/no sensor match → should NOT be demoted
        {"title": "B", "bucket": "NOVEL_BUILD", "target_lobe": None, "rationale": ""},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # "Improve weak_signal..." (lobe=til, names weak_signal) should be demoted to bottom
    assert result[-1]["title"].startswith("Improve weak_signal")
    assert result[-1]["prior_demoted"] is True
    assert "lobe_sensor:til:weak_signal" in result[-1]["prior_bucket"]

    # "B" should NOT be demoted (no lobe, no sensor name match)
    assert result[0]["title"] == "B"
    assert not result[0].get("prior_demoted")


# ── P6: demote does NOT fire when n<5 ────────────────────────────────────────

def test_p6_demote_no_fire_small_n():
    """_demote_prior_buckets does NOT fire for (lobe,sensor) when n=4 even if hit_rate=0.0."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            "til:weak_signal": {"total": 4, "confirmed": 0, "hit_rate": 0.0},
        },
    }
    items = [
        {
            "title": "Improve weak_signal in til",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "",
        },
        {"title": "B", "bucket": "NOVEL_BUILD", "target_lobe": None, "rationale": ""},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # Neither item should be demoted (n=4 < 5)
    for item in result:
        assert not item.get("prior_demoted"), f"item {item['title']} incorrectly demoted"


# ── P7: demote does NOT fire when hit_rate>=0.25 ─────────────────────────────

def test_p7_demote_no_fire_good_hit_rate():
    """_demote_prior_buckets does NOT fire for (lobe,sensor) when hit_rate=0.25 (exactly)."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            "til:weak_signal": {"total": 8, "confirmed": 2, "hit_rate": 0.25},
        },
    }
    items = [
        {
            "title": "Improve weak_signal in til",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "",
        },
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)
    assert not result[0].get("prior_demoted"), "hit_rate=0.25 is NOT below threshold (strict <)"


def test_p7b_demote_fires_just_below_threshold():
    """_demote_prior_buckets fires for (lobe,sensor) when hit_rate=0.124 (strictly below 0.25)."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            "til:weak_signal": {"total": 8, "confirmed": 1, "hit_rate": 0.124},
        },
    }
    items = [
        {
            "title": "Improve weak_signal in til",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "",
        },
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)
    assert result[0].get("prior_demoted") is True


# ── P8: demoted items at bottom but present with flag ────────────────────────

def test_p8_demoted_items_present_at_bottom():
    """Demoted items appear at the bottom with prior_demoted:true — never dropped.

    FIX-2: uses (lobe,sensor) bucket only; item titles contain sensor name (FIX-3).
    """
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            "nw:bad_sensor": {"total": 10, "confirmed": 1, "hit_rate": 0.1},
        },
    }
    items = [
        {"title": "Good A", "bucket": "NOVEL_BUILD", "target_lobe": None, "rationale": ""},
        # names bad_sensor → demoted
        {"title": "Improve bad_sensor in nw", "bucket": "NOVEL_BUILD", "target_lobe": "nw", "rationale": ""},
        {"title": "Good C", "bucket": "URGENT_FIX", "target_lobe": None, "rationale": ""},
        # names bad_sensor → demoted
        {"title": "Re-test bad_sensor for nw lobe", "bucket": "NOVEL_BUILD", "target_lobe": "nw", "rationale": ""},
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

    # Order among demoted is stable
    dem_titles = [it["title"] for it in result if it.get("prior_demoted")]
    assert dem_titles[0].startswith("Improve bad_sensor")
    assert dem_titles[1].startswith("Re-test bad_sensor")


# ── P9: never-promote ────────────────────────────────────────────────────────

def test_p9_never_promote():
    """A high-hit (lobe,sensor) bucket does NOT move items up in the agenda.

    FIX-2: kind bucket removed; test uses (lobe,sensor) with high hit rate.
    """
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            # great_sensor has excellent hit rate → should NOT cause any demotion
            "nw:great_sensor": {"total": 10, "confirmed": 10, "hit_rate": 1.0},
        },
    }
    # Items ordered with great_sensor item at position 2 (not first)
    items = [
        {"title": "A", "bucket": "NOVEL_BUILD", "target_lobe": None, "rationale": ""},
        {"title": "B", "bucket": "URGENT_FIX", "target_lobe": None, "rationale": ""},
        # names great_sensor but hit rate is good → should NOT be demoted
        {"title": "Improve great_sensor for nw", "bucket": "NOVEL_BUILD", "target_lobe": "nw", "rationale": ""},
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # Order must be unchanged (no promotion, no demotion)
    assert [it["title"] for it in result] == ["A", "B", "Improve great_sensor for nw"]
    # C not demoted (good hit rate)
    assert not result[2].get("prior_demoted")


# ── P10: (lobe, sensor) bucket independent of kind ───────────────────────────

def test_p10_lobe_sensor_bucket_independent():
    """(lobe, sensor) bucket can fire even if kind bucket is healthy.

    R-V8-12 / FIX-3: sensor name must appear in item title or rationale.
    """
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
        # item names a different sensor → should NOT be demoted (FIX-3: no false demote)
        {"title": "Good", "bucket": "engine", "target_lobe": "other_lobe", "rationale": ""},
        # item title contains the bad sensor name → should be demoted
        {
            "title": "improve ic_sharpe scoring in til lobe",
            "bucket": "engine",
            "target_lobe": "til",
            "rationale": "",
        },
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    # "improve ic_sharpe ..." item (lobe=til, names ic_sharpe) should be demoted
    til_item = next(it for it in result if "ic_sharpe" in it["title"])
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

    # Write 5 prior rows all FALSIFIER_TRIPPED for lobe=til sensor=ic_sharpe
    for i in range(5):
        _append_outcome_prior_row(root, {
            "proposal_id": f"demote-{i}",
            "kind": "NOVEL_BUILD",
            "tier": "T1",
            "lobe": "til",
            "sensors": ["ic_sharpe"],
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

    # Fabricate one LLM-returned item naming the bad sensor ic_sharpe in its title (FIX-3)
    raw_items = [
        {
            "title": "Improve ic_sharpe scoring in til lobe",
            "bucket": "NOVEL_BUILD",
            "severity": "low",
            "target_lobe": "til",
            "rationale": "ic_sharpe has weak signal",
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
        "til:ic_sharpe bucket with 0/5 hit rate should demote item naming ic_sharpe"
    )
    assert item.get("prior_bucket") is not None
    assert "lobe_sensor:til:ic_sharpe" in item.get("prior_bucket", "")


# ── P15: FIX-3 construction-scoped sensor matching ───────────────────────────

def test_p15_construction_scoped_sensor_match():
    """R-V8-12 / FIX-3: bad record on sensor X must NOT demote item naming sensor Y.

    Spec from brief: by_lobe_sensor={'til:weak':{n:6,hr:0}, 'til:strong':{n:10,hr:1}}
      - item titled 'improve til strong' → NOT demoted (strong has good hit rate)
      - item titled 'improve til weak' → demoted with prior_bucket='lobe_sensor:til:weak'
    """
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            "til:weak": {"total": 6, "confirmed": 0, "hit_rate": 0.0},
            "til:strong": {"total": 10, "confirmed": 10, "hit_rate": 1.0},
        },
    }
    items = [
        # names 'strong' which has a GOOD hit rate → NOT demoted
        {
            "title": "improve til strong sensor scoring",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "",
        },
        # names 'weak' which has a BAD hit rate → demoted
        {
            "title": "improve til weak sensor scoring",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "",
        },
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)

    strong_item = next(it for it in result if "strong" in it["title"])
    weak_item = next(it for it in result if "weak" in it["title"])

    # 'strong' item must NOT be demoted (good hit rate)
    assert not strong_item.get("prior_demoted"), (
        "item naming sensor 'strong' (good hit rate) must NOT be demoted"
    )

    # 'weak' item must be demoted
    assert weak_item.get("prior_demoted") is True, (
        "item naming sensor 'weak' (bad hit rate) must be demoted"
    )
    assert weak_item.get("prior_bucket") == "lobe_sensor:til:weak"


def test_p15b_no_sensor_in_text_no_demote():
    """FIX-3: item naming no sensor at all is NOT demoted even if lobe has bad buckets."""
    from engine.metabolism.agenda import _demote_prior_buckets

    calibration = {
        "by_kind": {},
        "by_lobe_sensor": {
            "til:bad_sensor": {"total": 6, "confirmed": 0, "hit_rate": 0.0},
        },
    }
    items = [
        # lobe matches but item text does not mention bad_sensor → must NOT demote
        {
            "title": "Refactor til lobe datastore",
            "bucket": "NOVEL_BUILD",
            "target_lobe": "til",
            "rationale": "improve til performance generally",
        },
    ]
    result = _demote_prior_buckets(items, calibration, demote_min_n=5, demote_hit_rate=0.25)
    assert not result[0].get("prior_demoted"), (
        "item naming no specific sensor must NOT be demoted (conservative: no false demote)"
    )


# ── P16: FIX-4 UNVERIFIABLE excluded from calibration denominator ─────────────

def test_p16_unverifiable_excluded_from_calibration():
    """_build_calibration_from_priors excludes UNVERIFIABLE from both num and denom."""
    from engine.metabolism.dream import _build_calibration_from_priors

    rows = [
        # CONFIRMED + confirmed-triage → count as 1 hit, 1 total
        {
            "proposal_id": "a",
            "kind": "engine",
            "lobe": "til",
            "sensors": ["ic"],
            "outcome": "CONFIRMED",
            "triage": "confirmed",
        },
        # FALSIFIER_TRIPPED → 0 hit, 1 total
        {
            "proposal_id": "b",
            "kind": "engine",
            "lobe": "til",
            "sensors": ["ic"],
            "outcome": "FALSIFIER_TRIPPED",
            "triage": "overfit",
        },
        # UNVERIFIABLE → excluded from BOTH num and denom
        {
            "proposal_id": "c",
            "kind": "engine",
            "lobe": "til",
            "sensors": ["ic"],
            "outcome": "UNVERIFIABLE",
            "triage": "unverifiable",
        },
    ]
    cal = _build_calibration_from_priors(rows)

    # Only 2 rows should be in denominator (UNVERIFIABLE excluded)
    kind_stats = cal["by_kind"]["engine"]
    assert kind_stats["total"] == 2, (
        f"UNVERIFIABLE must be excluded from denominator, got total={kind_stats['total']}"
    )
    assert kind_stats["confirmed"] == 1
    assert kind_stats["hit_rate"] == 0.5

    # Lobe-sensor bucket for til:ic also should have total=2
    ls_stats = cal["by_lobe_sensor"]["til:ic"]
    assert ls_stats["total"] == 2, (
        f"UNVERIFIABLE must be excluded from lobe_sensor denom, got total={ls_stats['total']}"
    )
    assert ls_stats["confirmed"] == 1


# ── P17: FIX-4 confirmed requires triage=='confirmed' conjunction ─────────────

def test_p17_confirmed_requires_triage_conjunction():
    """_build_calibration_from_priors: CONFIRMED outcome with non-confirmed triage is NOT a hit."""
    from engine.metabolism.dream import _build_calibration_from_priors

    rows = [
        # CONFIRMED outcome + confirmed triage → hit
        {
            "proposal_id": "x",
            "kind": "engine",
            "lobe": "til",
            "sensors": [],
            "outcome": "CONFIRMED",
            "triage": "confirmed",
        },
        # CONFIRMED outcome + NON-confirmed triage → NOT a hit
        {
            "proposal_id": "y",
            "kind": "engine",
            "lobe": "til",
            "sensors": [],
            "outcome": "CONFIRMED",
            "triage": "regime_ambiguity",
        },
    ]
    cal = _build_calibration_from_priors(rows)

    kind_stats = cal["by_kind"]["engine"]
    assert kind_stats["total"] == 2
    assert kind_stats["confirmed"] == 1, (
        "CONFIRMED outcome with non-confirmed triage must NOT count as a hit"
    )
    assert kind_stats["hit_rate"] == 0.5


# ── P18: FIX-5 demoted items survive docket-cap trim ─────────────────────────

def test_p18_demoted_items_survive_docket_cap():
    """Demoted items are not the silent casualty of max_docket_size trim (FIX-5).

    When regular items + demoted items exceed the cap, regular items are trimmed first.
    Demoted items must always appear in the final list (visibility law).
    """
    import engine.metabolism.agenda as agenda_mod
    from engine.metabolism.dream import _append_outcome_prior_row

    root = _tmp_root()

    # Write 5 prior rows FALSIFIER_TRIPPED for til:ic_sharpe → bad bucket
    for i in range(5):
        _append_outcome_prior_row(root, {
            "proposal_id": f"cap-{i}",
            "kind": "NOVEL_BUILD",
            "tier": "T1",
            "lobe": "til",
            "sensors": ["ic_sharpe"],
            "outcome": "FALSIFIER_TRIPPED",
            "triage": "overfit",
            "ts": "2026-01-01T00:00:00+00:00",
        })

    # Budget: cap at 3 items
    budget_yml = (
        "schema: metabolism_budget.v1\n"
        "per_cycle_usd_cap: 25\n"
        "per_cycle_token_cap: 25000000\n"
        "max_docket_size: 3\n"
        "circuit_breaker_trip: 3\n"
        "prior_demote_min_n: 5\n"
        "prior_demote_hit_rate: 0.25\n"
    )
    (root / "config" / "metabolism_budget.yml").write_text(budget_yml, encoding="utf-8")

    # 4 LLM items: 3 regular + 1 demoted-candidate (names ic_sharpe, lobe=til)
    raw_items = [
        {"title": "Regular item alpha", "bucket": "NOVEL_BUILD", "severity": "low",
         "target_lobe": None, "rationale": ""},
        {"title": "Regular item beta", "bucket": "NOVEL_BUILD", "severity": "low",
         "target_lobe": None, "rationale": ""},
        {"title": "Regular item gamma", "bucket": "NOVEL_BUILD", "severity": "low",
         "target_lobe": None, "rationale": ""},
        # names ic_sharpe → will be demoted; must survive despite cap=3
        {"title": "Investigate ic_sharpe regression in til", "bucket": "NOVEL_BUILD",
         "severity": "low", "target_lobe": "til", "rationale": "ic_sharpe has weak signal"},
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
            cycle_id="cap-test",
            root=root,
            providers=[{"model": "test"}],
            model=None,
        )

    items = result.get("items") or []
    titles = [it["title"] for it in items]

    # The demoted item MUST be present (visibility law)
    assert any("ic_sharpe" in t for t in titles), (
        "Demoted item must survive docket-cap trim (FIX-5 visibility law)"
    )

    # Total must not exceed cap
    assert len(items) <= 3, f"Expected <=3 items, got {len(items)}: {titles}"

    # Demoted item must have prior_demoted=True
    demoted = [it for it in items if it.get("prior_demoted")]
    assert len(demoted) == 1, "Exactly the ic_sharpe item should be demoted"
