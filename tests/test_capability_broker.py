"""tests/test_capability_broker.py — F3 capability broker tests.

Five test groups (per spec):
  1. resolve() returns ref-name-only + allowed bool, NEVER a secret value
  2. lane-not-allowed → allowed False
  3. audit() appends + is append-only
  4. NEVER-RAISE on missing manifest
  5. Redline scanner flags planted fake secret; passes on clean real manifest
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

# Reset the module-level manifest cache between tests
import engine.neuralweb.capability_broker as broker_module
from engine.neuralweb.capability_broker import resolve, audit
from scripts.check_capability_redline import scan as redline_scan, selftest as redline_selftest


_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_manifest(tmp: Path, capabilities: list[dict]) -> None:
    """Write a test capability manifest to tmp/config/capability_manifest.yml."""
    (tmp / "config").mkdir(exist_ok=True)
    manifest = {
        "schema": "capability_manifest.v1",
        "generated_at": "2026-07-09",
        "owner_program": "test",
        "capabilities": capabilities,
    }
    (tmp / "config" / "capability_manifest.yml").write_text(
        yaml.dump(manifest, default_flow_style=False, allow_unicode=True)
    )


def _clear_cache():
    """Reset the module-level cache so each test gets a fresh load."""
    broker_module._manifest_cache = None


# ── 1. resolve() returns ref-name-only, NEVER a secret value ─────────────────

def test_resolve_returns_ref_name_only():
    """resolve() must return the env-var name, not the secret value."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        _write_manifest(tmp, [
            {
                "capability_id": "test_llm_oauth",
                "kind": "llm_oauth",
                "secret_ref": "MY_FAKE_SECRET_NAME",
                "storage_locus": "gh-secret",
                "kill_state": "active",
                "allowed_lanes": ["test-lane"],
                "allowed_tiers": ["T0"],
                "rotation_state": "active",
                "notes": "test",
            }
        ])

        result = resolve("test_llm_oauth", lane="test-lane", root=tmp)

        assert result["allowed"] is True
        assert result["ref_name"] == "MY_FAKE_SECRET_NAME"

        # CRITICAL: the secret value must NOT appear in the result
        # Inject a fake value into env and verify it is not in the result
        secret_value = "sk-THIS_IS_A_FAKE_SECRET_VALUE_abc123def456"
        old_env = os.environ.get("MY_FAKE_SECRET_NAME")
        try:
            os.environ["MY_FAKE_SECRET_NAME"] = secret_value
            result2 = resolve("test_llm_oauth", lane="test-lane", root=tmp)
            result_str = json.dumps(result2)
            assert secret_value not in result_str, (
                "SECRET VALUE must never appear in resolve() output. "
                "The broker returns ref names only; callers read os.environ[ref_name]."
            )
        finally:
            if old_env is None:
                os.environ.pop("MY_FAKE_SECRET_NAME", None)
            else:
                os.environ["MY_FAKE_SECRET_NAME"] = old_env
        _clear_cache()


def test_resolve_allowed_true_for_allowed_lane():
    """resolve() returns allowed=True for a lane in the allowed_lanes list."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        _write_manifest(tmp, [
            {
                "capability_id": "cap_a",
                "kind": "llm_oauth",
                "secret_ref": "TOKEN_A",
                "storage_locus": "gh-secret",
                "kill_state": "active",
                "allowed_lanes": ["allowed-lane", "another-lane"],
                "allowed_tiers": ["T0"],
                "rotation_state": "active",
                "notes": "test",
            }
        ])
        result = resolve("cap_a", lane="allowed-lane", root=tmp)
        assert result["allowed"] is True
        assert result["ref_name"] == "TOKEN_A"
        _clear_cache()


# ── 2. lane-not-allowed → allowed False ──────────────────────────────────────

def test_resolve_denied_for_unlisted_lane():
    """resolve() returns allowed=False when the lane is not in allowed_lanes."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        _write_manifest(tmp, [
            {
                "capability_id": "cap_b",
                "kind": "vps_deploy",
                "secret_ref": "VPS_KEY",
                "storage_locus": "gh-secret",
                "kill_state": "active",
                "allowed_lanes": ["render", "engine-render"],
                "allowed_tiers": ["T0"],
                "rotation_state": "active",
                "notes": "test",
            }
        ])
        result = resolve("cap_b", lane="metabolism-propose", root=tmp)
        assert result["allowed"] is False, (
            "Lane 'metabolism-propose' is not in allowed_lanes for cap_b — "
            "must be denied."
        )
        assert result["ref_name"] is not None, (
            "ref_name may be returned even when denied (for diagnostic purposes)"
        )
        _clear_cache()


def test_resolve_denied_for_killed_capability():
    """A capability with kill_state != 'active' is denied regardless of lane."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        _write_manifest(tmp, [
            {
                "capability_id": "cap_killed",
                "kind": "llm_oauth",
                "secret_ref": "KILLED_TOKEN",
                "storage_locus": "gh-secret",
                "kill_state": "killed",
                "allowed_lanes": ["any-lane"],
                "allowed_tiers": ["T0"],
                "rotation_state": "active",
                "notes": "test",
            }
        ])
        result = resolve("cap_killed", lane="any-lane", root=tmp)
        assert result["allowed"] is False, "Killed capability must be denied"
        _clear_cache()


def test_resolve_denied_for_unknown_capability():
    """resolve() returns allowed=False for a capability not in the manifest."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        _write_manifest(tmp, [])
        result = resolve("nonexistent_cap", lane="test-lane", root=tmp)
        assert result["allowed"] is False
        assert result["ref_name"] is None
        _clear_cache()


# ── 3. audit() appends + is append-only ──────────────────────────────────────

def test_audit_appends_row():
    """audit() writes a row to capability_audit.jsonl."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "data" / "neuralweb").mkdir(parents=True)

        ok = audit("test_cap", lane="test-lane", workflow="test-workflow", root=tmp)
        assert ok is True

        audit_path = tmp / "data" / "neuralweb" / "capability_audit.jsonl"
        assert audit_path.exists(), "Audit file must be created"

        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["capability_id"] == "test_cap"
        assert row["lane"] == "test-lane"
        assert row["workflow"] == "test-workflow"
        assert "ts" in row
        assert "event_id" in row


def test_audit_is_append_only():
    """audit() appends new rows without truncating existing ones."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "data" / "neuralweb").mkdir(parents=True)

        # Write three rows
        for i in range(3):
            audit(f"cap_{i}", lane="test-lane", workflow="wf", root=tmp)

        audit_path = tmp / "data" / "neuralweb" / "capability_audit.jsonl"
        lines = [l for l in audit_path.read_text().strip().splitlines() if l.strip()]
        assert len(lines) == 3, f"Expected 3 rows, got {len(lines)}"

        # Each row must be valid JSON
        for line in lines:
            row = json.loads(line)
            assert "schema" in row
            assert "ts" in row


def test_audit_row_contains_no_secret_value():
    """audit() must not capture or log any secret value."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "data" / "neuralweb").mkdir(parents=True)

        secret_value = "sk-FAKE_SECRET_DO_NOT_COMMIT_abc123"
        old_env = os.environ.get("FAKE_AUDIT_SECRET")
        try:
            os.environ["FAKE_AUDIT_SECRET"] = secret_value
            audit("test_cap", lane="test-lane", workflow="wf", root=tmp)
        finally:
            if old_env is None:
                os.environ.pop("FAKE_AUDIT_SECRET", None)
            else:
                os.environ["FAKE_AUDIT_SECRET"] = old_env

        audit_path = tmp / "data" / "neuralweb" / "capability_audit.jsonl"
        content = audit_path.read_text()
        assert secret_value not in content, (
            "audit() must not write secret VALUES to the audit tape. "
            "Only ref names (env-var names) may appear."
        )


# ── 4. NEVER-RAISE on missing manifest ───────────────────────────────────────

def test_resolve_never_raises_on_missing_manifest():
    """resolve() must not raise even when the manifest file is absent."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        # No config/ directory, no manifest — should return safely
        result = resolve("any_cap", lane="any-lane", root=tmp)
        assert isinstance(result, dict)
        assert result["allowed"] is False
        assert result["ref_name"] is None
        _clear_cache()


def test_audit_never_raises_on_missing_directory():
    """audit() must not raise even when the data directory doesn't exist."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        # data/neuralweb/ doesn't exist yet — audit must create it
        ok = audit("test_cap", lane="test-lane", root=tmp)
        # Should return True (dir auto-created) or False (some other error) — never raises
        assert isinstance(ok, bool)


def test_resolve_never_raises_on_corrupted_manifest():
    """resolve() returns a safe denial dict on corrupted YAML — never raises."""
    with tempfile.TemporaryDirectory(prefix="broker_test_") as tmpdir:
        tmp = Path(tmpdir)
        _clear_cache()
        (tmp / "config").mkdir()
        # Write syntactically broken YAML
        (tmp / "config" / "capability_manifest.yml").write_text(
            "schema: [\ncapabilities: {{{ BROKEN YAML\n"
        )
        result = resolve("any_cap", lane="any-lane", root=tmp)
        assert isinstance(result, dict)
        assert result["allowed"] is False
        _clear_cache()


# ── 5. Redline scanner tests ──────────────────────────────────────────────────

def test_redline_scanner_passes_on_real_files():
    """The redline scanner finds no violations in the real manifest + broker."""
    try:
        findings = redline_scan(root=_REPO_ROOT)
    except RuntimeError as e:
        pytest.skip(f"Real files not available: {e}")
    assert len(findings) == 0, (
        f"Redline scanner found {len(findings)} violation(s) in real files: "
        + "; ".join(f"{f['file']}:{f['line_no']} [{f['kind']}]" for f in findings[:5])
    )


def test_redline_scanner_flags_planted_fake_secret():
    """The redline scanner catches a planted fake secret in a fixture manifest."""
    with tempfile.TemporaryDirectory(prefix="broker_redline_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()
        (tmp / "engine" / "neuralweb").mkdir(parents=True)

        # Plant a 40-char hex fake secret
        fake_secret = "d" * 5 + "1" * 35  # 40-char hex-like with digits
        (tmp / "config" / "capability_manifest.yml").write_text(
            f"schema: capability_manifest.v1\n"
            f"some_planted_secret: {fake_secret}\n"
        )
        # Clean broker
        (tmp / "engine" / "neuralweb" / "capability_broker.py").write_text(
            "# clean broker\ndef resolve(id, lane): return {'ref_name': 'NAME', 'allowed': True}\n"
        )

        findings = redline_scan(root=tmp)
        assert any(f["kind"] in ("high_entropy_hex40", "high_entropy_base64") for f in findings), (
            "Redline scanner must detect the planted fake secret. "
            f"Got findings: {findings}"
        )


def test_redline_scanner_flags_secrets_reference():
    """The redline scanner catches 'secrets.MY_SECRET' value references."""
    with tempfile.TemporaryDirectory(prefix="broker_redline_test_") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "config").mkdir()
        (tmp / "engine" / "neuralweb").mkdir(parents=True)

        (tmp / "config" / "capability_manifest.yml").write_text(
            "schema: capability_manifest.v1\n"
            "token: ${{ secrets.OAUTH_TOKEN }}\n"
        )
        (tmp / "engine" / "neuralweb" / "capability_broker.py").write_text(
            "# clean broker\ndef resolve(id, lane): return {'ref_name': 'NAME', 'allowed': True}\n"
        )

        findings = redline_scan(root=tmp)
        assert any(f["kind"] == "secrets_value_reference" for f in findings), (
            "Redline scanner must detect secrets.* value references."
        )


def test_redline_selftest_passes():
    """The redline scanner's built-in selftest passes."""
    rc = redline_selftest()
    assert rc == 0, "check_capability_redline selftest must pass"
