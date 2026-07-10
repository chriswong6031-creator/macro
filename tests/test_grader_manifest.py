"""tests/test_grader_manifest.py — F1 grader-immutability manifest tests.

Three test groups:
  1. Manifest coverage — all declared files exist and are covered.
  2. Hash drift detection — a simulated tamper is caught.
  3. Missing file — fail-closed on a file in the manifest that doesn't exist on disk.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
import yaml

from scripts.check_grader_manifest import check, selftest, MANIFEST_PATH, EXPECTED_SCHEMA

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ── 1. Manifest coverage ──────────────────────────────────────────────────────

def test_manifest_loads():
    """The manifest exists and has the expected schema."""
    manifest_path = _REPO_ROOT / MANIFEST_PATH
    assert manifest_path.exists(), f"Manifest not found at {MANIFEST_PATH}"
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)
    assert manifest.get("schema") == EXPECTED_SCHEMA, (
        f"Manifest schema must be '{EXPECTED_SCHEMA}', got '{manifest.get('schema')}'"
    )


def test_manifest_covers_declared_files():
    """Every file declared in the manifest exists on disk."""
    manifest_path = _REPO_ROOT / MANIFEST_PATH
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)
    files = manifest.get("files", [])
    assert files, "Manifest must declare at least one file"
    for entry in files:
        rel_path = entry.get("path")
        assert rel_path, f"Manifest entry missing 'path': {entry}"
        abs_path = _REPO_ROOT / rel_path
        assert abs_path.exists(), (
            f"Manifest declares '{rel_path}' but the file does not exist on disk. "
            f"Either the file was deleted or the manifest is stale."
        )


def test_manifest_check_passes_on_current_files():
    """check() returns 0 on the real current files (no drift)."""
    rc = check(root=_REPO_ROOT)
    assert rc == 0, (
        "check_grader_manifest.check() failed on the current files — hash drift detected. "
        "Run: python3 scripts/check_grader_manifest.py to see details."
    )


def test_manifest_has_sha256_for_every_entry():
    """Every manifest entry has a non-empty sha256 field."""
    manifest_path = _REPO_ROOT / MANIFEST_PATH
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)
    for entry in manifest.get("files", []):
        assert entry.get("sha256"), (
            f"Manifest entry for '{entry.get('path', '?')}' is missing 'sha256'"
        )


# ── 2. Hash drift detection ───────────────────────────────────────────────────

def test_hash_drift_is_detected():
    """A simulated hash drift (tampered file content) is caught as a hard failure."""
    with tempfile.TemporaryDirectory(prefix="grader_manifest_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "scripts").mkdir()
        (tmp / "config").mkdir()

        good_content = b"# grader original content\ndef grade(): pass\n"
        tampered_content = b"# TAMPERED - injected by adversarial loop\ndef grade(): return 1\n"

        good_hash = hashlib.sha256(good_content).hexdigest()

        # Write the ORIGINAL content (hash matches manifest)
        grader = tmp / "scripts" / "grade_thematic.py"
        grader.write_bytes(good_content)

        manifest = {
            "schema": "grader_manifest.v1",
            "generated_at": "2026-07-09",
            "owner_program": "test",
            "files": [
                {
                    "path": "scripts/grade_thematic.py",
                    "sha256": good_hash,
                    "role": "orchestrator",
                    "notes": "test",
                }
            ],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest, default_flow_style=False)
        )

        # Passes with original content
        assert check(root=tmp) == 0, "Should pass with original content"

        # Simulate tamper
        grader.write_bytes(tampered_content)
        rc = check(root=tmp)
        assert rc != 0, (
            "check() should return non-zero when file content has been tampered. "
            "Hash drift must be detected to prevent fitness scoreboard manipulation."
        )


def test_wrong_hash_in_manifest_is_detected():
    """A manifest with a wrong pre-registered hash is caught."""
    with tempfile.TemporaryDirectory(prefix="grader_manifest_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "scripts").mkdir()
        (tmp / "config").mkdir()

        real_content = b"# real grader\ndef grade(): pass\n"
        (tmp / "scripts" / "grade_thematic.py").write_bytes(real_content)

        # Register an intentionally wrong hash
        manifest = {
            "schema": "grader_manifest.v1",
            "generated_at": "2026-07-09",
            "owner_program": "test",
            "files": [
                {
                    "path": "scripts/grade_thematic.py",
                    "sha256": "0" * 64,  # wrong hash
                    "role": "orchestrator",
                    "notes": "test",
                }
            ],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest, default_flow_style=False)
        )
        rc = check(root=tmp)
        assert rc != 0, "Wrong hash in manifest must be detected"


# ── 3. Missing file — fail-closed ─────────────────────────────────────────────

def test_missing_file_is_fail_closed():
    """A manifest entry whose file does not exist on disk is a hard failure."""
    with tempfile.TemporaryDirectory(prefix="grader_manifest_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()

        manifest = {
            "schema": "grader_manifest.v1",
            "generated_at": "2026-07-09",
            "owner_program": "test",
            "files": [
                {
                    "path": "scripts/does_not_exist.py",
                    "sha256": "a" * 64,
                    "role": "sensor",
                    "notes": "test",
                }
            ],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest, default_flow_style=False)
        )
        rc = check(root=tmp)
        assert rc != 0, (
            "Missing file in manifest must be a hard failure (fail-closed). "
            "A manifest that references a non-existent file is invalid — "
            "either the file was deleted or the manifest is stale."
        )


def test_missing_manifest_is_fail_closed():
    """A missing manifest file itself is a hard failure."""
    with tempfile.TemporaryDirectory(prefix="grader_manifest_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()
        # Do NOT write the manifest — it is absent
        rc = check(root=tmp)
        assert rc != 0, (
            "Missing manifest must be a hard failure (fail-closed). "
            "The grader manifest is required for Phase 0."
        )


def test_empty_files_list_is_fail_closed():
    """A manifest with an empty files list is a hard failure."""
    with tempfile.TemporaryDirectory(prefix="grader_manifest_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()
        manifest = {
            "schema": "grader_manifest.v1",
            "generated_at": "2026-07-09",
            "owner_program": "test",
            "files": [],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest, default_flow_style=False)
        )
        rc = check(root=tmp)
        assert rc != 0, "Empty files list must be a hard failure"


# ── 4. Selftest ───────────────────────────────────────────────────────────────

def test_selftest_passes():
    """The script's built-in selftest passes."""
    rc = selftest()
    assert rc == 0, "check_grader_manifest selftest must pass"
