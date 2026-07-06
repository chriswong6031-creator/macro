"""Tests for engine/cycle_pattern/truths.py — Market Truth Registry v0.

Covers:
1. Schema round-trip: a valid truth survives validate_truth + load.
2. Transition immutability: old line untouched, new line has version+1.
3. evidence_ref existence check fires on bogus path.
4. Seeding is idempotent: re-run does not duplicate.
5. active_truths() filters retired/superseded correctly.
6. status='scored' gate: rejects absent gate artifact.
7. No sklearn/statsmodels import in truths.py.
8. falsifiers non-empty enforced.
9. monitoring missing-key enforced.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.cycle_pattern.truths import (  # noqa: E402
    TRUTHS_PATH,
    active_truths,
    append_truth,
    load_truths,
    transition_truth,
    validate_truth,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_truth(tmp_path: Path) -> dict:
    """Return a minimal valid truth dict with evidence_refs pointing to real paths."""
    # Use a real repo file so the existence check passes
    real_ref = "research/cycle_masterplan/W04_KEYSTONE_VERDICT.md"
    assert (_REPO / real_ref).exists(), f"real_ref must exist for tests: {real_ref}"
    return {
        "truth_id": "TEST-001",
        "version": 1,
        "status": "candidate",
        "owner_program": "cycle-intelligence",
        "statement": "Test: cycle position does not predict returns (synthetic).",
        "effect_class": "null",
        "scope": {
            "families": ["us_sector"],
            "regions": ["US"],
            "sample": "synthetic test sample",
        },
        "target": "forward_ret at 63d",
        "evidence_refs": [real_ref],
        "n_summary": "n=100 synthetic",
        "ci_summary": "CI [−1%, +1%] straddles zero",
        "era_stability": "unknown",
        "pit_class": "pit_pure",
        "allowed_consumers": ["measurement_surface"],
        "forbidden_consumers": ["position_sizing"],
        "falsifiers": ["If CI excludes zero, null is refuted."],
        "monitoring": {
            "metric": "test_metric",
            "cadence": "monthly",
            "auto_demote_rule": None,
        },
        "created": "2026-07-06",
        "last_reviewed": "2026-07-06",
        "next_review_due": "2026-10-06",
        "notes": "synthetic test truth",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_roundtrip(tmp_path):
    """A valid truth can be validated, appended, and loaded back intact."""
    p = tmp_path / "truths.jsonl"
    truth = _minimal_truth(tmp_path)
    validate_truth(truth, check_refs_exist=True)
    append_truth(truth, p)

    rows = load_truths(p)
    assert len(rows) == 1
    assert rows[0]["truth_id"] == "TEST-001"
    assert rows[0]["version"] == 1
    assert rows[0]["status"] == "candidate"
    assert rows[0]["effect_class"] == "null"
    assert rows[0]["owner_program"] == "cycle-intelligence"
    assert isinstance(rows[0]["falsifiers"], list)
    assert len(rows[0]["falsifiers"]) == 1
    assert isinstance(rows[0]["scope"]["families"], list)
    assert rows[0]["monitoring"]["cadence"] == "monthly"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Transition immutability
# ─────────────────────────────────────────────────────────────────────────────

def test_transition_immutability(tmp_path):
    """Old line is untouched after transition; new line has version+1."""
    p = tmp_path / "truths.jsonl"
    truth = _minimal_truth(tmp_path)
    append_truth(truth, p)

    new_row = transition_truth(
        "TEST-001",
        new_status="display",
        actor="test_agent",
        reason="Evidence confirmed",
        path=p,
    )

    rows = load_truths(p)
    assert len(rows) == 2, "must have exactly 2 rows (original + transition)"

    # original is untouched
    v1 = next(r for r in rows if r["version"] == 1)
    assert v1["status"] == "candidate"
    assert v1["truth_id"] == "TEST-001"

    # new row has incremented version and new status
    v2 = next(r for r in rows if r["version"] == 2)
    assert v2["status"] == "display"
    assert v2["truth_id"] == "TEST-001"
    assert "Evidence confirmed" in v2["notes"]

    # transition return matches what's written
    assert new_row["version"] == 2
    assert new_row["status"] == "display"


def test_transition_version_monotone(tmp_path):
    """Multiple transitions increment version strictly."""
    p = tmp_path / "truths.jsonl"
    truth = _minimal_truth(tmp_path)
    append_truth(truth, p)

    transition_truth("TEST-001", "display", "a", "step1", path=p)
    transition_truth("TEST-001", "retired", "a", "step2", path=p)

    rows = load_truths(p)
    versions = sorted(r["version"] for r in rows if r["truth_id"] == "TEST-001")
    assert versions == [1, 2, 3]

    # original v1 still has original status
    v1 = next(r for r in rows if r["version"] == 1)
    assert v1["status"] == "candidate"


def test_transition_unknown_id_raises(tmp_path):
    """transition_truth raises KeyError for unknown truth_id."""
    p = tmp_path / "truths.jsonl"
    with pytest.raises(KeyError):
        transition_truth("NONEXISTENT", "retired", "a", "r", path=p)


# ─────────────────────────────────────────────────────────────────────────────
# 3. evidence_ref existence check
# ─────────────────────────────────────────────────────────────────────────────

def test_evidence_ref_bogus_path_raises(tmp_path):
    """validate_truth raises ValueError when evidence_ref does not exist on disk."""
    truth = _minimal_truth(tmp_path)
    truth["evidence_refs"] = ["data/cycle_pattern/NONEXISTENT_FILE_12345.json"]
    with pytest.raises(ValueError, match="evidence_refs paths not found"):
        validate_truth(truth, check_refs_exist=True)


def test_evidence_ref_skip_check(tmp_path):
    """validate_truth with check_refs_exist=False does NOT check paths."""
    truth = _minimal_truth(tmp_path)
    truth["evidence_refs"] = ["data/cycle_pattern/NONEXISTENT_FILE.json"]
    # Should not raise
    validate_truth(truth, check_refs_exist=False)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Seeding is idempotent
# ─────────────────────────────────────────────────────────────────────────────

def test_seeding_idempotent(tmp_path):
    """Appending the same (truth_id, version) twice and then filtering gives one entry."""
    p = tmp_path / "truths.jsonl"
    truth = _minimal_truth(tmp_path)

    # Simulate idempotent seeder: check before append
    from engine.cycle_pattern.truths import load_truths as _load  # noqa: PLC0415

    def _seed_once(t, path):
        existing = {(r["truth_id"], r["version"]) for r in _load(path)}
        if (t["truth_id"], t["version"]) not in existing:
            append_truth(t, path)

    _seed_once(truth, p)
    _seed_once(truth, p)  # second call should be no-op

    rows = load_truths(p)
    assert len(rows) == 1, "idempotent seed must not duplicate"


def test_seeding_script_idempotent():
    """Running seed_cycle_truths twice leaves truths.jsonl without duplicates."""
    import importlib
    import scripts.seed_cycle_truths as seeder  # noqa: E402

    # Run once (may already be seeded on disk — that's fine)
    seeder.main()

    rows_after_first = load_truths(TRUTHS_PATH)
    ids_v1_first = [(r["truth_id"], r["version"]) for r in rows_after_first if r["version"] == 1]

    # Run again
    seeder.main()

    rows_after_second = load_truths(TRUTHS_PATH)
    ids_v1_second = [(r["truth_id"], r["version"]) for r in rows_after_second if r["version"] == 1]

    # No duplicate v1 rows
    assert len(ids_v1_second) == len(set(ids_v1_second)), (
        "idempotent re-run must not create duplicate (truth_id, version=1) rows"
    )
    # Count of v1 rows did not increase on second run (already all present)
    assert len(ids_v1_second) == len(ids_v1_first)


# ─────────────────────────────────────────────────────────────────────────────
# 5. active_truths() filters correctly
# ─────────────────────────────────────────────────────────────────────────────

def test_active_truths_excludes_retired_superseded(tmp_path):
    """active_truths() returns latest-version rows excluding retired/superseded."""
    p = tmp_path / "truths.jsonl"

    # truth A: candidate → retired
    a = _minimal_truth(tmp_path)
    a["truth_id"] = "A-001"
    append_truth(a, p)
    transition_truth("A-001", "retired", "a", "done", path=p)

    # truth B: candidate (active)
    b = _minimal_truth(tmp_path)
    b["truth_id"] = "B-001"
    append_truth(b, p)

    # truth C: candidate → superseded
    c = _minimal_truth(tmp_path)
    c["truth_id"] = "C-001"
    append_truth(c, p)
    transition_truth("C-001", "superseded", "a", "replaced", path=p)

    active = active_truths(p)
    active_ids = {r["truth_id"] for r in active}

    assert "A-001" not in active_ids, "retired truth must not appear in active_truths"
    assert "C-001" not in active_ids, "superseded truth must not appear in active_truths"
    assert "B-001" in active_ids, "candidate truth must appear in active_truths"


def test_active_truths_returns_latest_version(tmp_path):
    """active_truths returns only the highest version per truth_id."""
    p = tmp_path / "truths.jsonl"
    truth = _minimal_truth(tmp_path)
    append_truth(truth, p)
    transition_truth("TEST-001", "display", "a", "r", path=p)

    active = active_truths(p)
    active_test = [r for r in active if r["truth_id"] == "TEST-001"]
    assert len(active_test) == 1
    assert active_test[0]["version"] == 2
    assert active_test[0]["status"] == "display"


def test_active_truths_empty_file(tmp_path):
    """active_truths returns [] on missing file."""
    p = tmp_path / "nonexistent.jsonl"
    assert active_truths(p) == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. status='scored' gate
# ─────────────────────────────────────────────────────────────────────────────

def test_scored_status_requires_gate_artifact(tmp_path):
    """validate_truth raises ValueError for status='scored' without gate artifact ref."""
    truth = _minimal_truth(tmp_path)
    truth["status"] = "scored"
    # evidence_refs only has a .md doc — no gate artifact json
    with pytest.raises(ValueError, match="gate artifact"):
        validate_truth(truth, check_refs_exist=False)


def test_scored_status_passes_with_gate_artifact(tmp_path):
    """validate_truth accepts status='scored' when a gate artifact path is in evidence_refs."""
    truth = _minimal_truth(tmp_path)
    truth["status"] = "scored"
    # Add a gate artifact ref that matches the pattern
    truth["evidence_refs"] = [
        "research/cycle_masterplan/W04_KEYSTONE_VERDICT.md",
        "data/hazard/model_price_c4414dcb.json",  # real path, contains 'model' in name
    ]
    # Should not raise (refs exist on disk — validated above)
    validate_truth(truth, check_refs_exist=True)


# ─────────────────────────────────────────────────────────────────────────────
# 7. No sklearn/statsmodels import in truths.py
# ─────────────────────────────────────────────────────────────────────────────

def test_no_forbidden_imports_in_truths():
    """truths.py must not import sklearn, statsmodels, or scipy.stats."""
    import ast

    truths_path = _REPO / "engine" / "cycle_pattern" / "truths.py"
    tree = ast.parse(truths_path.read_text())

    forbidden = {"sklearn", "statsmodels", "scipy"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in forbidden, (
                    f"truths.py imports forbidden library: {name}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# 8. falsifiers non-empty enforced
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_falsifiers_raises(tmp_path):
    """validate_truth raises ValueError when falsifiers is empty."""
    truth = _minimal_truth(tmp_path)
    truth["falsifiers"] = []
    with pytest.raises(ValueError, match="falsifiers"):
        validate_truth(truth, check_refs_exist=False)


def test_missing_falsifiers_raises(tmp_path):
    """validate_truth raises ValueError when falsifiers key is missing."""
    truth = _minimal_truth(tmp_path)
    del truth["falsifiers"]
    with pytest.raises(ValueError, match="missing fields"):
        validate_truth(truth, check_refs_exist=False)


# ─────────────────────────────────────────────────────────────────────────────
# 9. monitoring missing-key enforced
# ─────────────────────────────────────────────────────────────────────────────

def test_monitoring_missing_key_raises(tmp_path):
    """validate_truth raises ValueError when monitoring dict is missing required keys."""
    truth = _minimal_truth(tmp_path)
    truth["monitoring"] = {"metric": "x"}  # missing cadence and auto_demote_rule
    with pytest.raises(ValueError, match="monitoring missing keys"):
        validate_truth(truth, check_refs_exist=False)


def test_monitoring_nullable_values_ok(tmp_path):
    """monitoring values may be None — only keys are required."""
    truth = _minimal_truth(tmp_path)
    truth["monitoring"] = {
        "metric": None,
        "cadence": None,
        "auto_demote_rule": None,
    }
    # should not raise
    validate_truth(truth, check_refs_exist=False)


# ─────────────────────────────────────────────────────────────────────────────
# 10. load_truths handles empty file gracefully
# ─────────────────────────────────────────────────────────────────────────────

def test_load_truths_missing_file(tmp_path):
    """load_truths returns [] for nonexistent file."""
    p = tmp_path / "missing.jsonl"
    assert load_truths(p) == []


def test_load_truths_empty_lines_skipped(tmp_path):
    """load_truths skips blank lines without error."""
    p = tmp_path / "truths.jsonl"
    p.write_text("\n\n\n")
    assert load_truths(p) == []


# ─────────────────────────────────────────────────────────────────────────────
# 11. Seeded data integrity (post-seed checks)
# ─────────────────────────────────────────────────────────────────────────────

def test_seeded_truths_all_valid():
    """All seeded truths in data/cycle_pattern/truths.jsonl pass schema validation."""
    rows = load_truths(TRUTHS_PATH)
    assert len(rows) >= 15, f"Expected >= 15 seeded truths, got {len(rows)}"

    for row in rows:
        # skip version>1 rows (transitions) — they may not have new evidence_refs
        validate_truth(row, check_refs_exist=(row["version"] == 1))


def test_seeded_active_count():
    """After seeding, active_truths returns at least 15 entries (one per seed truth)."""
    active = active_truths(TRUTHS_PATH)
    # All 15 seeded truths are active (none retired/superseded initially)
    assert len(active) >= 15, f"Expected >= 15 active truths, got {len(active)}"


def test_seeded_promoted_nulls():
    """Seeded truths with promoted_null status all have effect_class null or structural."""
    rows = load_truths(TRUTHS_PATH)
    for row in rows:
        if row["status"] == "promoted_null":
            assert row["effect_class"] in ("null", "structural"), (
                f"{row['truth_id']}: promoted_null must have effect_class null or structural"
            )


def test_seeded_forbidden_consumers_non_empty():
    """Every seeded truth has at least one forbidden_consumer."""
    rows = load_truths(TRUTHS_PATH)
    for row in rows:
        if row["version"] == 1:  # check only seed rows
            assert len(row["forbidden_consumers"]) > 0, (
                f"{row['truth_id']}: forbidden_consumers must not be empty"
            )
