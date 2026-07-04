"""Hermetic unit tests for engine.neuralweb.envelope.

All tests use synthetic fixtures and inject registry/now to avoid any I/O or
date-based non-determinism.  No real market data is loaded.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.neuralweb.envelope import (
    ENVELOPE_KEYS,
    _compute_inputs_hash,
    read_sidecar,
    stamp,
    stamp_if_changed,
    strip_envelope,
    verify,
    write_sidecar,
)

# ---------------------------------------------------------------------------
# Minimal synthetic registry (avoids loading the real YAML in every test)
# ---------------------------------------------------------------------------
_REG = {
    "meta": {
        "schema_version": 1,
        "tier_vocabulary": [
            "display",
            "shadow",
            "confirmer",
            "scored",
            "infrastructure",
        ],
    },
    "artifacts": {
        "test-artifact": {
            "producer": "engine/test_producer.py",
            "tier": "shadow",
        },
        "regime-latest": {
            "producer": "engine/run.py",
            "tier": "infrastructure",
        },
    },
}

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
_NOW_STR = "2026-07-04T12:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_payload() -> dict:
    return {"state": "risk-off", "asof": "2026-07-04", "value": 42}


@pytest.fixture
def stamped(base_payload) -> dict:
    return stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)


# ---------------------------------------------------------------------------
# 1. Sibling-not-wrapper: stamped dict must have payload keys AND envelope keys
#    at the SAME level (never nested under "data" or "envelope").
# ---------------------------------------------------------------------------

class TestSiblingNotWrapper:
    def test_payload_keys_survive(self, stamped, base_payload):
        for k in base_payload:
            assert k in stamped, f"payload key {k!r} missing from stamped dict"

    def test_envelope_keys_present(self, stamped):
        for k in ENVELOPE_KEYS:
            assert k in stamped, f"envelope key {k!r} missing"

    def test_no_wrapper_nesting(self, stamped):
        # A wrapper would put payload under "data" or "envelope"
        assert "data" not in stamped
        assert "envelope" not in stamped

    def test_flat_shape(self, stamped, base_payload):
        # Every key in the stamped dict should be a leaf, not a container
        # wrapping the payload — i.e., the payload keys are at the root.
        expected_keys = set(base_payload) | set(ENVELOPE_KEYS)
        assert expected_keys == set(stamped.keys())

    def test_wrapper_would_break_extraction(self, base_payload):
        """Negative control: demonstrates why a wrapper is forbidden.

        build_feeds.py does ``rr = latest.get("risk_radar")``, then writes
        ``rr`` directly.  If the producer wraps the payload, ``rr.get("state")``
        returns None — exactly the 2026-07-02 incident.
        """
        # Simulate a wrapped shape (the WRONG pattern)
        wrapped = {"envelope": {"produced_by": "engine/run.py"}, "data": base_payload}
        # The build_feeds extraction reads .get("state") at the top level:
        assert wrapped.get("state") is None, (
            "A wrapper puts payload inside 'data'; top-level .get('state') is None — "
            "this is the incident pattern"
        )
        # The correct sibling-stamp keeps the key accessible:
        s = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        assert s.get("state") == "risk-off"


# ---------------------------------------------------------------------------
# 2. Hash stability under re-stamp
# ---------------------------------------------------------------------------

class TestHashStability:
    def test_same_hash_on_restamp(self, base_payload):
        s1 = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        # Re-stamp the already-stamped dict — inputs_hash must be the same.
        different_time = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
        s2 = stamp(s1, artifact_id="test-artifact", registry=_REG, now=different_time)
        assert s1["inputs_hash"] == s2["inputs_hash"], (
            "Re-stamping unchanged data should yield the same inputs_hash; "
            "produced_at is excluded from the hash."
        )

    def test_produced_at_changes_on_restamp(self, base_payload):
        s1 = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        later = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
        s2 = stamp(s1, artifact_id="test-artifact", registry=_REG, now=later)
        assert s1["produced_at"] != s2["produced_at"]

    def test_hash_changes_when_payload_changes(self, base_payload):
        s1 = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        changed = dict(base_payload, value=99)
        s2 = stamp(changed, artifact_id="test-artifact", registry=_REG, now=_NOW)
        assert s1["inputs_hash"] != s2["inputs_hash"]

    def test_hash_excludes_envelope_keys(self, base_payload):
        """inputs_hash is over payload-minus-envelope (order-insensitive via sort_keys)."""
        s = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        # Manually compute expected hash from the stripped payload.
        stripped = strip_envelope(base_payload)
        expected = _compute_inputs_hash(stripped)
        assert s["inputs_hash"] == expected

    def test_hash_sort_keys_independent(self):
        """Insertion order must not affect inputs_hash."""
        p1 = {"z": 1, "a": 2, "m": 3}
        p2 = {"a": 2, "m": 3, "z": 1}
        assert _compute_inputs_hash(p1) == _compute_inputs_hash(p2)

    def test_hash_prefix(self, base_payload):
        s = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        assert s["inputs_hash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# 3. stamp_if_changed byte-identity on unchanged payload
# ---------------------------------------------------------------------------

class TestStampIfChanged:
    def test_unchanged_preserves_envelope(self, base_payload):
        prev = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        later = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
        result = stamp_if_changed(
            base_payload, prev, artifact_id="test-artifact", registry=_REG, now=later
        )
        # produced_at must NOT change (byte-identity fast path)
        assert result["produced_at"] == prev["produced_at"], (
            "stamp_if_changed on unchanged data must preserve produced_at verbatim"
        )
        assert result["inputs_hash"] == prev["inputs_hash"]

    def test_unchanged_byte_identical(self, base_payload):
        prev = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        later = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
        result = stamp_if_changed(
            base_payload, prev, artifact_id="test-artifact", registry=_REG, now=later
        )
        # Serialize both — they should be identical dicts.
        assert result == prev

    def test_changed_payload_gets_new_stamp(self, base_payload):
        prev = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        changed = dict(base_payload, value=99)
        later = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
        result = stamp_if_changed(
            changed, prev, artifact_id="test-artifact", registry=_REG, now=later
        )
        assert result["produced_at"] == "2026-07-05T00:00:00Z"
        assert result["inputs_hash"] != prev["inputs_hash"]

    def test_none_prev_stamps_fresh(self, base_payload):
        result = stamp_if_changed(
            base_payload, None, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        assert result["produced_at"] == _NOW_STR
        assert "inputs_hash" in result


# ---------------------------------------------------------------------------
# 4. Collision guard on schema_version
# ---------------------------------------------------------------------------

class TestCollisionGuard:
    def test_existing_schema_version_respected(self):
        """If the payload already has schema_version, stamp takes max(existing, default)."""
        payload_with_sv = {"state": "ok", "schema_version": 3}
        s = stamp(
            payload_with_sv, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        # Registry default is 1; payload has 3 → max(3,1) = 3
        assert s["schema_version"] == 3

    def test_registry_default_wins_when_higher(self):
        """Registry default (e.g. 1) wins when the existing is lower (0)."""
        payload_with_sv = {"state": "ok", "schema_version": 0}
        s = stamp(
            payload_with_sv, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        assert s["schema_version"] == max(0, 1)  # == 1

    def test_produced_by_always_clobbered(self):
        payload_with_pb = {
            "state": "ok",
            "produced_by": "some/old/producer.py",
        }
        s = stamp(
            payload_with_pb, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        assert s["produced_by"] == "engine/test_producer.py"

    def test_tier_always_clobbered(self):
        payload_with_tier = {"state": "ok", "tier": "scored"}
        s = stamp(
            payload_with_tier, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        assert s["tier"] == "shadow"  # registry wins for test-artifact

    def test_non_int_schema_version_in_payload_ignored(self):
        """A non-int schema_version in the payload is not a collision."""
        payload = {"state": "ok", "schema_version": "v2"}
        s = stamp(payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        # String is not int → collision guard does not fire; registry default used.
        assert s["schema_version"] == 1


# ---------------------------------------------------------------------------
# 5. strip / verify round-trip
# ---------------------------------------------------------------------------

class TestStripVerify:
    def test_strip_removes_envelope_keys(self, base_payload):
        s = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        stripped = strip_envelope(s)
        for k in ENVELOPE_KEYS:
            assert k not in stripped
        for k in base_payload:
            assert k in stripped

    def test_strip_does_not_mutate(self, base_payload):
        s = stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        original_keys = set(s.keys())
        strip_envelope(s)
        assert set(s.keys()) == original_keys  # original unchanged

    def test_verify_clean_on_fresh_stamp(self, stamped):
        problems = verify(stamped, registry=_REG)
        assert problems == [], f"fresh stamp should have no problems; got {problems}"

    def test_verify_detects_missing_key(self, stamped):
        broken = dict(stamped)
        del broken["inputs_hash"]
        problems = verify(broken, registry=_REG)
        assert any("inputs_hash" in p for p in problems)

    def test_verify_detects_hash_mismatch(self, stamped):
        broken = dict(stamped, inputs_hash="sha256:deadbeef")
        problems = verify(broken, registry=_REG)
        assert any("mismatch" in p for p in problems)

    def test_verify_detects_unknown_tier(self, stamped):
        broken = dict(stamped, tier="legendary")
        problems = verify(broken, registry=_REG)
        assert any("tier" in p for p in problems)

    def test_verify_accepts_all_known_tiers(self, base_payload):
        for t in ["display", "shadow", "confirmer", "scored", "infrastructure"]:
            reg = {
                "meta": {"schema_version": 1, "tier_vocabulary": [t]},
                "artifacts": {"test-artifact": {"producer": "x.py", "tier": t}},
            }
            s = stamp(base_payload, artifact_id="test-artifact", registry=reg, now=_NOW)
            problems = verify(s, registry=reg)
            tier_problems = [p for p in problems if "tier" in p]
            assert not tier_problems, f"tier={t!r} should be accepted; problems={problems}"


# ---------------------------------------------------------------------------
# 6. Sidecar write / read
# ---------------------------------------------------------------------------

class TestSidecar:
    def test_write_creates_sidecar_file(self, tmp_path):
        artifact = tmp_path / "items.parquet"
        artifact.write_bytes(b"\x00\x01\x02\x03")
        sidecar_path = write_sidecar(
            artifact, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        assert sidecar_path.exists()
        assert sidecar_path.name == "items.parquet.envelope.json"

    def test_sidecar_has_all_envelope_keys(self, tmp_path):
        artifact = tmp_path / "items.parquet"
        artifact.write_bytes(b"hello")
        write_sidecar(artifact, artifact_id="test-artifact", registry=_REG, now=_NOW)
        sc = read_sidecar(artifact)
        assert sc is not None
        for k in ENVELOPE_KEYS:
            assert k in sc, f"sidecar missing {k!r}"

    def test_sidecar_has_artifact_path(self, tmp_path):
        artifact = tmp_path / "items.parquet"
        artifact.write_bytes(b"hello")
        write_sidecar(artifact, artifact_id="test-artifact", registry=_REG, now=_NOW)
        sc = read_sidecar(artifact)
        assert "artifact_path" in sc

    def test_sidecar_byte_sha256(self, tmp_path):
        data = b"test bytes"
        artifact = tmp_path / "data.parquet"
        artifact.write_bytes(data)
        write_sidecar(artifact, artifact_id="test-artifact", registry=_REG, now=_NOW)
        sc = read_sidecar(artifact)
        expected = "sha256:" + hashlib.sha256(data).hexdigest()
        assert sc["byte_sha256"] == expected

    def test_sidecar_payload_bytes_override(self, tmp_path):
        artifact = tmp_path / "data.parquet"
        # File doesn't exist yet — use payload_bytes
        custom = b"custom bytes"
        write_sidecar(
            artifact,
            artifact_id="test-artifact",
            registry=_REG,
            now=_NOW,
            payload_bytes=custom,
        )
        sc = read_sidecar(artifact)
        expected = "sha256:" + hashlib.sha256(custom).hexdigest()
        assert sc["byte_sha256"] == expected

    def test_read_sidecar_absent_returns_none(self, tmp_path):
        artifact = tmp_path / "ghost.parquet"
        assert read_sidecar(artifact) is None

    def test_sidecar_round_trip(self, tmp_path):
        artifact = tmp_path / "data.jsonl"
        artifact.write_bytes(b'{"a":1}\n')
        path = write_sidecar(
            artifact, artifact_id="test-artifact", registry=_REG, now=_NOW
        )
        sc = read_sidecar(artifact)
        assert sc is not None
        # Verify the sidecar is readable and consistent
        problems = [k for k in ENVELOPE_KEYS if k not in sc]
        assert not problems


# ---------------------------------------------------------------------------
# 7. produced_at format
# ---------------------------------------------------------------------------

class TestProducedAt:
    def test_produced_at_iso8601_utc(self, stamped):
        # Must be parseable as ISO-8601 and end with Z
        pa = stamped["produced_at"]
        assert pa.endswith("Z"), f"produced_at must end with Z; got {pa!r}"
        dt = datetime.fromisoformat(pa.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_produced_at_matches_injected_now(self, stamped):
        assert stamped["produced_at"] == _NOW_STR


# ---------------------------------------------------------------------------
# 8. stamp() does not mutate the original payload
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_original_not_mutated(self, base_payload):
        original_copy = dict(base_payload)
        stamp(base_payload, artifact_id="test-artifact", registry=_REG, now=_NOW)
        assert base_payload == original_copy
