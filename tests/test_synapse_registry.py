"""
tests/test_synapse_registry.py — Integrity tests for config/synapse.yml.

Tests
-----
1. yaml_parses          — config/synapse.yml loads without error.
2. validate_clean       — validate_registry(load_registry()) returns [].
3. producer_paths_exist — every non-pattern producer path exists on disk.
4. unique_paths         — no two artifacts share the same path.
5. enum_coverage        — tier, cadence, storage, format enums are all populated
                          (i.e. the registry exercises all declared vocab values or
                          a known subset, not that every value must appear).
6. validator_missing_field     — synthetic bad entry (missing path) is caught.
7. validator_bad_enum          — synthetic bad entry (invalid tier) is caught.
8. validator_dup_path          — synthetic dup-path entry is caught.
9. validator_hand_weights_no_notes — weights=hand without notes is caught.
10. validator_scored_no_evidence   — scored tier without qual_ladder_ref/notes is caught.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

# Repo root: two levels above tests/
REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "config" / "synapse.yml"

from engine.neuralweb.synapse import (  # noqa: E402
    artifact_for_path,
    artifacts_by_owner,
    load_registry,
    validate_registry,
)

_PLACEHOLDER_RE = re.compile(r"<[A-Z_]+>")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def reg():
    """Load the registry once for the entire module."""
    return load_registry(REPO_ROOT)


# ---------------------------------------------------------------------------
# Test 1: YAML parses
# ---------------------------------------------------------------------------

def test_yaml_parses():
    """config/synapse.yml must load without YAML parse error."""
    assert REGISTRY_PATH.exists(), f"synapse.yml not found at {REGISTRY_PATH}"
    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), "synapse.yml must parse to a dict"
    assert "meta" in data, "synapse.yml must have a meta block"
    assert "artifacts" in data, "synapse.yml must have an artifacts block"


# ---------------------------------------------------------------------------
# Test 2: validate_registry returns no violations
# ---------------------------------------------------------------------------

def test_validate_clean(reg):
    """validate_registry(load_registry()) must return an empty violations list."""
    violations = validate_registry(reg, root=REPO_ROOT)
    assert violations == [], (
        f"Registry has {len(violations)} violation(s):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 3: producer paths exist on disk
# ---------------------------------------------------------------------------

def test_producer_paths_exist(reg):
    """Every non-pattern, non-R2 producer must exist as a file in the repo."""
    missing = []
    artifacts = reg.get("artifacts") or {}
    for artifact_id, entry in artifacts.items():
        if not isinstance(entry, dict):
            continue
        producer = entry.get("producer", "")
        storage = entry.get("storage", "")
        if not producer or _PLACEHOLDER_RE.search(producer):
            continue
        if storage in ("r2",):
            continue
        # Strip inline comments / line references
        producer_path = producer.split(":")[0].strip()
        candidate = REPO_ROOT / producer_path
        if not candidate.exists():
            missing.append(f"{artifact_id}: {producer_path!r}")
    assert not missing, (
        f"{len(missing)} producer file(s) not found:\n"
        + "\n".join(f"  {m}" for m in missing)
    )


# ---------------------------------------------------------------------------
# Test 4: unique paths
# ---------------------------------------------------------------------------

def test_unique_paths(reg):
    """No two artifacts may share the same path value."""
    seen: dict[str, str] = {}
    duplicates = []
    for artifact_id, entry in (reg.get("artifacts") or {}).items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("path", "")
        if not path:
            continue
        if path in seen:
            duplicates.append(f"{artifact_id!r} duplicates {seen[path]!r} for path {path!r}")
        else:
            seen[path] = artifact_id
    assert not duplicates, "Duplicate paths found:\n" + "\n".join(duplicates)


# ---------------------------------------------------------------------------
# Test 5: enum coverage (registry exercises a valid subset)
# ---------------------------------------------------------------------------

_VALID_TIERS = {"display", "shadow", "confirmer", "scored", "infrastructure"}
_VALID_CADENCES = {
    "daily-engine", "collect", "asia-close", "intraday", "weekly", "on-demand",
    "nightly-cortex", "nightly-factor-panel",
    "theta-ops-nightly",  # theta-ops launchd lane (mirror of engine/neuralweb/synapse.py)
}
_VALID_STORAGES = {"git", "r2", "gitignored-local", "git+r2"}
_VALID_FORMATS = {"json", "parquet", "jsonl", "js", "other"}


def test_enum_coverage(reg):
    """All tier/cadence/storage/format values in the registry must be valid."""
    invalid = []
    for artifact_id, entry in (reg.get("artifacts") or {}).items():
        if not isinstance(entry, dict):
            continue
        tier = entry.get("tier")
        if tier and tier not in _VALID_TIERS:
            invalid.append(f"{artifact_id}: invalid tier={tier!r}")
        cadence = entry.get("cadence")
        if cadence and cadence not in _VALID_CADENCES:
            invalid.append(f"{artifact_id}: invalid cadence={cadence!r}")
        storage = entry.get("storage")
        if storage and storage not in _VALID_STORAGES:
            invalid.append(f"{artifact_id}: invalid storage={storage!r}")
        fmt = entry.get("format")
        if fmt and fmt not in _VALID_FORMATS:
            invalid.append(f"{artifact_id}: invalid format={fmt!r}")
    assert not invalid, "Invalid enum values:\n" + "\n".join(invalid)


# ---------------------------------------------------------------------------
# Synthetic-bad-entry tests (validator unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_reg(reg):
    return reg  # alias for clarity in synthetic tests


def _inject(base_reg: dict, artifact_id: str, entry: dict) -> dict:
    """Deep-copy base_reg and inject a synthetic artifact entry."""
    mutated = copy.deepcopy(base_reg)
    mutated["artifacts"][artifact_id] = entry
    return mutated


def _good_entry(**overrides) -> dict:
    """Return a minimal valid synthetic entry, with optional overrides."""
    base = {
        "path": "data/_selftest/synthetic.json",
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "display",
        "weights": "none",
        "horizon_role": "context",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 6: missing required field
# ---------------------------------------------------------------------------

def test_validator_missing_field(base_reg):
    """A synthetic entry missing 'path' must produce a violation."""
    entry = _good_entry()
    del entry["path"]
    mutated = _inject(base_reg, "_selftest_missing_path", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("missing required field" in v and "path" in v for v in violations), (
        f"Expected 'missing required field path' violation, got: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 7: invalid tier enum
# ---------------------------------------------------------------------------

def test_validator_bad_enum(base_reg):
    """A synthetic entry with an invalid tier must produce a violation."""
    entry = _good_entry(path="data/_selftest/bad_tier.json", tier="NOT_VALID_TIER")
    mutated = _inject(base_reg, "_selftest_bad_tier", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("tier" in v for v in violations), (
        f"Expected tier enum violation, got: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 8: duplicate path
# ---------------------------------------------------------------------------

def test_validator_dup_path(base_reg):
    """Two artifacts with the same path must produce a 'duplicate path' violation."""
    existing_path = next(
        e["path"]
        for e in base_reg["artifacts"].values()
        if isinstance(e, dict) and e.get("path") and not _PLACEHOLDER_RE.search(e.get("path", ""))
    )
    entry = _good_entry(path=existing_path)
    mutated = _inject(base_reg, "_selftest_dup_path", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("duplicate path" in v for v in violations), (
        f"Expected duplicate path violation, got: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 9: weights=hand without notes
# ---------------------------------------------------------------------------

def test_validator_hand_weights_no_notes(base_reg):
    """weights='hand' without a notes field must produce a violation."""
    entry = _good_entry(
        path="data/_selftest/hand_no_notes.json",
        weights="hand",
        # notes deliberately omitted
    )
    mutated = _inject(base_reg, "_selftest_hand_no_notes", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("hand" in v and "notes" in v for v in violations), (
        f"Expected hand-weights-without-notes violation, got: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 10: scored tier without qual_ladder_ref or notes
# ---------------------------------------------------------------------------

def test_validator_scored_no_evidence(base_reg):
    """A scored-tier entry without qual_ladder_ref or notes must produce a violation."""
    entry = _good_entry(
        path="data/_selftest/scored_no_evidence.json",
        tier="scored",
        weights="none",
        # neither qual_ladder_ref nor notes
    )
    mutated = _inject(base_reg, "_selftest_scored_no_evidence", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("scored" in v or "article 3" in v.lower() for v in violations), (
        f"Expected scored-without-evidence violation, got: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 11: helper functions
# ---------------------------------------------------------------------------

def test_artifacts_by_owner(reg):
    """artifacts_by_owner should return at least one entry for 'engine-fix'."""
    result = artifacts_by_owner(reg, "engine-fix")
    assert len(result) >= 1, "Expected at least one engine-fix artifact"
    # All returned entries should have 'engine-fix' in their owner_program
    for artifact_id, entry in result.items():
        assert "engine-fix" in (entry.get("owner_program") or "").lower(), (
            f"{artifact_id} owner_program={entry.get('owner_program')!r} doesn't match 'engine-fix'"
        )


def test_artifact_for_path(reg):
    """artifact_for_path should find regime-latest by its known path."""
    result = artifact_for_path(reg, "data/regime/latest.json")
    assert result is not None, "artifact_for_path should find data/regime/latest.json"
    artifact_id, entry = result
    assert artifact_id == "regime-latest"
    assert entry["tier"] == "infrastructure"


def test_artifact_for_path_not_found(reg):
    """artifact_for_path should return None for an unknown path."""
    result = artifact_for_path(reg, "data/does/not/exist.json")
    assert result is None


# ---------------------------------------------------------------------------
# Tests 12-14: horizon_role validation (LH-R1 firewall)
# ---------------------------------------------------------------------------

def test_all_artifacts_have_horizon_role(reg):
    """Every registered artifact must declare a horizon_role (LH-R1 firewall)."""
    missing = [
        aid
        for aid, entry in (reg.get("artifacts") or {}).items()
        if isinstance(entry, dict) and not entry.get("horizon_role")
    ]
    assert not missing, (
        f"{len(missing)} artifact(s) missing horizon_role:\n"
        + "\n".join(f"  {aid}" for aid in missing)
    )


def test_all_horizon_roles_are_valid(reg):
    """Every horizon_role value must be a member of the declared enum."""
    _VALID_HORIZON_ROLES = {"tactical_entry", "hold_thesis", "dual", "context"}
    invalid = [
        f"{aid}: {entry.get('horizon_role')!r}"
        for aid, entry in (reg.get("artifacts") or {}).items()
        if isinstance(entry, dict) and entry.get("horizon_role") not in _VALID_HORIZON_ROLES
    ]
    assert not invalid, (
        "Invalid horizon_role values found:\n" + "\n".join(invalid)
    )


def test_validator_missing_horizon_role(base_reg):
    """A synthetic entry missing 'horizon_role' must produce a violation."""
    entry = _good_entry()
    del entry["horizon_role"]
    mutated = _inject(base_reg, "_selftest_missing_horizon_role", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("horizon_role" in v for v in violations), (
        f"Expected horizon_role violation, got: {violations}"
    )


def test_validator_bad_horizon_role_enum(base_reg):
    """A synthetic entry with an invalid horizon_role must produce a violation."""
    entry = _good_entry(
        path="data/_selftest/bad_horizon_role.json",
        horizon_role="NOT_A_VALID_HORIZON_ROLE",
    )
    mutated = _inject(base_reg, "_selftest_bad_horizon_role", entry)
    violations = validate_registry(mutated, root=REPO_ROOT)
    assert any("horizon_role" in v for v in violations), (
        f"Expected horizon_role enum violation, got: {violations}"
    )
