"""R4 contract drift checker tests (NW Rails PR-7).

Fixture-based: uses temp directories and temp manifests; no dependency on live artifact
data or network.  Covers:
  1. Clean pass — artifact fields exactly match contract.
  2. Extra fields in artifact (added, not in contract) → drift detected.
  3. Missing fields from artifact (removed, were in contract) → drift detected.
  4. Both added and removed simultaneously → drift detected, both printed.
  5. --warn-only flag exits 0 even on drift.
  6. Artifact absent (no live file) → skipped (no false positives on CI runners).
  7. Wildcard artifacts (per_stock_intel) → first file sampled.
  8. schema_fields absent from manifest entry → entry is skipped (no crash).
  9. ARTIFACT_MANIFEST in export_signal_contracts has schema_version + schema_fields.
 10. Manifest file round-trips through build_manifest() → schema_fields present.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is importable.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_contract_drift import _actual_fields, _diff_fields, check_drift


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _make_manifest(tmp_path: Path, entries: list[dict]) -> Path:
    m = {
        "schema": "artifact_manifest/v1",
        "as_of": "2026-07-05",
        "cadence_basis": "trading_calendar",
        "note": "test manifest",
        "artifacts": entries,
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m))
    return p


# ---------------------------------------------------------------------------
# unit: _diff_fields
# ---------------------------------------------------------------------------

def test_diff_fields_clean():
    added, removed = _diff_fields("a.json", ["foo", "bar"], ["bar", "foo"])
    assert added == []
    assert removed == []


def test_diff_fields_added():
    added, removed = _diff_fields("a.json", ["foo"], ["foo", "bar"])
    assert added == ["bar"]
    assert removed == []


def test_diff_fields_removed():
    added, removed = _diff_fields("a.json", ["foo", "bar"], ["foo"])
    assert added == []
    assert removed == ["bar"]


def test_diff_fields_both():
    added, removed = _diff_fields("a.json", ["foo", "bar"], ["foo", "baz"])
    assert added == ["baz"]
    assert removed == ["bar"]


# ---------------------------------------------------------------------------
# unit: _actual_fields
# ---------------------------------------------------------------------------

def test_actual_fields_sorted(tmp_path):
    p = tmp_path / "art.json"
    _write_json(p, {"z": 1, "a": 2, "m": 3})
    assert _actual_fields(p) == ["a", "m", "z"]


# ---------------------------------------------------------------------------
# integration: check_drift via patched MANIFEST_PATH
# ---------------------------------------------------------------------------

def _run_drift(monkeypatch, tmp_path: Path, entries: list[dict],
               warn_only: bool = False) -> int:
    """Run check_drift with a temp manifest and a temp ROOT."""
    manifest_path = _make_manifest(tmp_path, entries)
    import scripts.check_contract_drift as mod
    monkeypatch.setattr(mod, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    return mod.check_drift(warn_only=warn_only)


def test_clean_pass(monkeypatch, tmp_path):
    """Exact match between schema_fields and artifact → exit 0."""
    art = tmp_path / "site" / "factordata" / "thing.json"
    _write_json(art, {"alpha": 1, "beta": 2})
    entries = [
        {
            "artifact": "site/factordata/thing.json",
            "kind": "board",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha", "beta"],
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
        }
    ]
    assert _run_drift(monkeypatch, tmp_path, entries) == 0


def test_added_field_detected(monkeypatch, tmp_path, capsys):
    """Artifact has a new field not in contract → drift, exit 1."""
    art = tmp_path / "site" / "factordata" / "thing.json"
    _write_json(art, {"alpha": 1, "beta": 2, "gamma": 3})
    entries = [
        {
            "artifact": "site/factordata/thing.json",
            "kind": "board",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha", "beta"],
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
        }
    ]
    result = _run_drift(monkeypatch, tmp_path, entries)
    out = capsys.readouterr().out
    assert result == 1
    assert "gamma" in out
    assert "DRIFT" in out


def test_removed_field_detected(monkeypatch, tmp_path, capsys):
    """Artifact is missing a field that was in contract → drift, exit 1."""
    art = tmp_path / "site" / "factordata" / "thing.json"
    _write_json(art, {"alpha": 1})
    entries = [
        {
            "artifact": "site/factordata/thing.json",
            "kind": "board",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha", "beta"],
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
        }
    ]
    result = _run_drift(monkeypatch, tmp_path, entries)
    out = capsys.readouterr().out
    assert result == 1
    assert "beta" in out
    assert "DRIFT" in out


def test_both_added_and_removed(monkeypatch, tmp_path, capsys):
    """Artifact has new field AND missing field → drift, exit 1, both reported."""
    art = tmp_path / "site" / "factordata" / "thing.json"
    _write_json(art, {"alpha": 1, "gamma": 3})  # beta gone, gamma added
    entries = [
        {
            "artifact": "site/factordata/thing.json",
            "kind": "board",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha", "beta"],
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
        }
    ]
    result = _run_drift(monkeypatch, tmp_path, entries)
    out = capsys.readouterr().out
    assert result == 1
    assert "gamma" in out  # added
    assert "beta" in out   # removed


def test_warn_only_exits_zero_on_drift(monkeypatch, tmp_path):
    """--warn-only exits 0 even when drift is detected."""
    art = tmp_path / "site" / "factordata" / "thing.json"
    _write_json(art, {"alpha": 1, "extra": 99})
    entries = [
        {
            "artifact": "site/factordata/thing.json",
            "kind": "board",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha"],
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
        }
    ]
    assert _run_drift(monkeypatch, tmp_path, entries, warn_only=True) == 0


def test_absent_artifact_skipped(monkeypatch, tmp_path):
    """Artifact file not present → skipped, exit 0 (no false positive on CI runners)."""
    entries = [
        {
            "artifact": "site/factordata/missing.json",
            "kind": "board",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha"],
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
        }
    ]
    assert _run_drift(monkeypatch, tmp_path, entries) == 0


def test_no_schema_fields_skipped(monkeypatch, tmp_path):
    """Entry with no schema_fields key → skipped without error."""
    art = tmp_path / "site" / "factordata" / "thing.json"
    _write_json(art, {"alpha": 1})
    entries = [
        {
            "artifact": "site/factordata/thing.json",
            "kind": "board",
            "expected_max_age_td": 2,
            "as_of_field": "as_of",
            "consumers": ["bot:test"],
            # no schema_fields
        }
    ]
    assert _run_drift(monkeypatch, tmp_path, entries) == 0


def test_wildcard_artifact_sampled(monkeypatch, tmp_path):
    """Wildcard per_stock_intel artifact → first file in dir is sampled."""
    stockdata = tmp_path / "site" / "stockdata"
    stockdata.mkdir(parents=True)
    _write_json(stockdata / "AAPL.json", {"alpha": 1, "beta": 2})
    _write_json(stockdata / "NVDA.json", {"alpha": 1, "beta": 2})
    entries = [
        {
            "artifact": "site/stockdata/<SYM>.json",
            "kind": "per_stock_intel",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha", "beta"],
            "expected_max_age_td": 2,
            "as_of_field": "asof",
            "consumers": ["bot:conviction"],
        }
    ]
    assert _run_drift(monkeypatch, tmp_path, entries) == 0


def test_wildcard_artifact_drift_detected(monkeypatch, tmp_path, capsys):
    """Wildcard per_stock_intel artifact has extra field → drift, exit 1."""
    stockdata = tmp_path / "site" / "stockdata"
    stockdata.mkdir(parents=True)
    _write_json(stockdata / "AAPL.json", {"alpha": 1, "beta": 2, "new_field": 3})
    entries = [
        {
            "artifact": "site/stockdata/<SYM>.json",
            "kind": "per_stock_intel",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha", "beta"],
            "expected_max_age_td": 2,
            "as_of_field": "asof",
            "consumers": ["bot:conviction"],
        }
    ]
    result = _run_drift(monkeypatch, tmp_path, entries)
    out = capsys.readouterr().out
    assert result == 1
    assert "new_field" in out


def test_wildcard_absent_dir_skipped(monkeypatch, tmp_path):
    """Wildcard artifact with no directory present → skipped, no error."""
    entries = [
        {
            "artifact": "site/stockdata/<SYM>.json",
            "kind": "per_stock_intel",
            "schema_version": "1.0.0",
            "schema_fields": ["alpha"],
            "expected_max_age_td": 2,
            "as_of_field": "asof",
            "consumers": ["bot:conviction"],
        }
    ]
    assert _run_drift(monkeypatch, tmp_path, entries) == 0


# ---------------------------------------------------------------------------
# sanity: ARTIFACT_MANIFEST in producer script has schema_version + schema_fields
# ---------------------------------------------------------------------------

def test_artifact_manifest_has_schema_version_and_fields():
    """Every entry in ARTIFACT_MANIFEST must have schema_version and schema_fields."""
    from scripts.export_signal_contracts import ARTIFACT_MANIFEST
    for entry in ARTIFACT_MANIFEST:
        assert "schema_version" in entry, (
            f"Missing schema_version in entry: {entry['artifact']}"
        )
        assert "schema_fields" in entry, (
            f"Missing schema_fields in entry: {entry['artifact']}"
        )
        # schema_version must be semver-ish (x.y.z)
        parts = entry["schema_version"].split(".")
        assert len(parts) == 3, (
            f"schema_version must be x.y.z, got {entry['schema_version']!r} "
            f"in {entry['artifact']}"
        )
        # schema_fields must be a sorted list
        fields = entry["schema_fields"]
        assert isinstance(fields, list), (
            f"schema_fields must be a list in {entry['artifact']}"
        )
        assert fields == sorted(fields), (
            f"schema_fields must be sorted in {entry['artifact']}: "
            f"got {fields!r}"
        )
        assert len(fields) > 0, (
            f"schema_fields must be non-empty in {entry['artifact']}"
        )


def test_build_manifest_includes_schema_fields():
    """build_manifest() output must carry schema_fields for every entry."""
    from scripts.export_signal_contracts import build_manifest
    m = build_manifest()
    for entry in m["artifacts"]:
        assert "schema_version" in entry, (
            f"build_manifest() output missing schema_version: {entry['artifact']}"
        )
        assert "schema_fields" in entry, (
            f"build_manifest() output missing schema_fields: {entry['artifact']}"
        )
