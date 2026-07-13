"""tests/test_key_pool_seven.py — Pool size == 7 correctness.

Verifies that the multi-key OAuth pool was correctly expanded from 3 to 7
slots without breaking any generic parsing logic:

  1. POOL_CAPABILITY_IDS contains exactly the 7 expected capability ids.
  2. discover_present_keys with only _2 and _6 present returns exactly those two.
  3. enabled_key_ids("5,7") maps correctly to {oauth_5, oauth_7}.
  4. usage_snapshot includes 7 pool rows + 1 legacy row (8 total).
  5. METAB_KEYS_ENABLED="1,2,3,4,5,6,7" full-set roundtrip.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_EXPECTED_POOL_IDS = [
    "claude_code_oauth_1",
    "claude_code_oauth_2",
    "claude_code_oauth_3",
    "claude_code_oauth_4",
    "claude_code_oauth_5",
    "claude_code_oauth_6",
    "claude_code_oauth_7",
]

# ── helpers ───────────────────────────────────────────────────────────────────

def _ts(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds"
    )


def _make_manifest_for_ids(ids: list[str]) -> dict:
    """Build a minimal manifest covering only the given capability ids."""
    return {
        "schema": "capability_manifest.v1",
        "capabilities": [
            {
                "capability_id": cap_id,
                "kind": "llm_oauth",
                "secret_ref": f"CLAUDE_CODE_OAUTH_TOKEN_{cap_id.split('_')[-1]}",
                "allowed_lanes": ["metabolism-dispatch"],
                "allowed_tiers": ["T1"],
                "rotation_state": "active",
                "kill_state": "active",
            }
            for cap_id in ids
        ],
    }


def _write_manifest(tmp_path: Path, ids: list[str] | None = None) -> None:
    import yaml  # noqa: PLC0415
    manifest = _make_manifest_for_ids(ids if ids is not None else _EXPECTED_POOL_IDS)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "capability_manifest.yml").write_text(yaml.dump(manifest))


def _write_ledger(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "data" / "metabolism" / "key_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# ── 1. POOL_CAPABILITY_IDS == exactly 7 expected ids ─────────────────────────

class TestPoolIds:
    def test_pool_has_exactly_seven_entries(self):
        from engine.neuralweb.key_pool import POOL_CAPABILITY_IDS  # noqa: PLC0415
        assert len(POOL_CAPABILITY_IDS) == 7, (
            f"Expected 7 pool entries, got {len(POOL_CAPABILITY_IDS)}: {POOL_CAPABILITY_IDS}"
        )

    def test_pool_ids_match_expected(self):
        from engine.neuralweb.key_pool import POOL_CAPABILITY_IDS  # noqa: PLC0415
        assert list(POOL_CAPABILITY_IDS) == _EXPECTED_POOL_IDS, (
            f"Pool ids mismatch.\n  Expected: {_EXPECTED_POOL_IDS}\n  Got:      {list(POOL_CAPABILITY_IDS)}"
        )

    def test_all_ids_follow_numeric_suffix_convention(self):
        """Each id ends in _1 through _7 and the suffix is the digit only."""
        from engine.neuralweb.key_pool import POOL_CAPABILITY_IDS  # noqa: PLC0415
        for i, cap_id in enumerate(POOL_CAPABILITY_IDS, start=1):
            assert cap_id == f"claude_code_oauth_{i}", (
                f"Position {i}: expected claude_code_oauth_{i}, got {cap_id}"
            )


# ── 2. discover_present_keys with only _2 and _6 present ─────────────────────

class TestDiscoverSevenPool:
    def test_only_two_and_six_present(self, tmp_path: Path, monkeypatch) -> None:
        """With only _2 and _6 set in env, discover_present_keys returns exactly those."""
        _write_manifest(tmp_path)
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        # Null out all 7 pool slots, then set only _2 and _6
        for i in range(1, 8):
            monkeypatch.setenv(f"CLAUDE_CODE_OAUTH_TOKEN_{i}", "")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN_2", "fake-token-2")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN_6", "fake-token-6")

        from engine.neuralweb.key_pool import discover_present_keys  # noqa: PLC0415
        result = discover_present_keys(root=tmp_path)
        assert set(result) == {"claude_code_oauth_2", "claude_code_oauth_6"}, (
            f"Expected {{oauth_2, oauth_6}}, got {result}"
        )
        assert len(result) == 2

    def test_no_keys_present_returns_empty(self, tmp_path: Path, monkeypatch) -> None:
        _write_manifest(tmp_path)
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        for i in range(1, 8):
            monkeypatch.setenv(f"CLAUDE_CODE_OAUTH_TOKEN_{i}", "")
        from engine.neuralweb.key_pool import discover_present_keys  # noqa: PLC0415
        assert discover_present_keys(root=tmp_path) == []

    def test_all_seven_present(self, tmp_path: Path, monkeypatch) -> None:
        _write_manifest(tmp_path)
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        for i in range(1, 8):
            monkeypatch.setenv(f"CLAUDE_CODE_OAUTH_TOKEN_{i}", f"tok-{i}")
        from engine.neuralweb.key_pool import discover_present_keys  # noqa: PLC0415
        result = discover_present_keys(root=tmp_path)
        assert set(result) == set(_EXPECTED_POOL_IDS), (
            f"Expected all 7 ids, got {result}"
        )
        assert len(result) == 7


# ── 3. enabled_key_ids("5,7") maps correctly ─────────────────────────────────

class TestEnabledKeyIdsSeven:
    def test_five_and_seven(self, monkeypatch) -> None:
        monkeypatch.setenv("METAB_KEYS_ENABLED", "5,7")
        from engine.neuralweb.key_pool import enabled_key_ids  # noqa: PLC0415
        result = enabled_key_ids()
        assert result == {"claude_code_oauth_5", "claude_code_oauth_7"}, (
            f"Expected {{oauth_5, oauth_7}}, got {result}"
        )

    def test_four_six(self, monkeypatch) -> None:
        monkeypatch.setenv("METAB_KEYS_ENABLED", "4,6")
        from engine.neuralweb.key_pool import enabled_key_ids  # noqa: PLC0415
        result = enabled_key_ids()
        assert result == {"claude_code_oauth_4", "claude_code_oauth_6"}

    def test_is_enabled_for_new_ids(self, monkeypatch) -> None:
        monkeypatch.setenv("METAB_KEYS_ENABLED", "4,5,6,7")
        from engine.neuralweb.key_pool import is_enabled  # noqa: PLC0415
        for i in range(4, 8):
            assert is_enabled(f"claude_code_oauth_{i}") is True, (
                f"claude_code_oauth_{i} should be enabled"
            )
        for i in range(1, 4):
            assert is_enabled(f"claude_code_oauth_{i}") is False, (
                f"claude_code_oauth_{i} should be disabled"
            )

    def test_is_enabled_digit_generic_parsing(self, monkeypatch) -> None:
        """enabled_key_ids must handle digits 1..7 generically (not hardcoded 1-3)."""
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,2,3,4,5,6,7")
        from engine.neuralweb.key_pool import enabled_key_ids  # noqa: PLC0415
        result = enabled_key_ids()
        assert result == set(_EXPECTED_POOL_IDS), (
            f"Full-set parse failed: {result}"
        )


# ── 4. usage_snapshot includes 7 pool rows + legacy (8 total) ────────────────

class TestUsageSnapshotSeven:
    def test_snapshot_has_eight_rows(self, tmp_path: Path, monkeypatch) -> None:
        """usage_snapshot must return 7 pool rows + 1 legacy = 8 rows."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        snap = usage_snapshot(root=tmp_path)

        assert len(snap) == 8, (
            f"Expected 8 rows (7 pool + 1 legacy), got {len(snap)}.\n"
            f"key_ids present: {[r['key_id'] for r in snap]}"
        )

    def test_snapshot_contains_all_pool_ids_and_legacy(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        snap = usage_snapshot(root=tmp_path)
        snap_ids = {r["key_id"] for r in snap}

        for cap_id in _EXPECTED_POOL_IDS:
            assert cap_id in snap_ids, f"{cap_id} missing from usage_snapshot"
        assert "legacy" in snap_ids

    def test_snapshot_row_for_key_six(self, tmp_path: Path, monkeypatch) -> None:
        """Spot-check: key 6 appears in the snapshot with correct structure."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: ["claude_code_oauth_6"],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        snap = usage_snapshot(root=tmp_path)
        row6 = next((r for r in snap if r["key_id"] == "claude_code_oauth_6"), None)
        assert row6 is not None, "claude_code_oauth_6 row missing from snapshot"
        assert row6["present"] is True
        assert "window_5h_est_tokens" in row6
        assert "weekly_est_tokens" in row6


# ── 5. METAB_KEYS_ENABLED "1,2,3,4,5,6,7" full-set roundtrip ─────────────────

class TestFullSetRoundtrip:
    def test_full_set_enabled_ids(self, monkeypatch) -> None:
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,2,3,4,5,6,7")
        from engine.neuralweb.key_pool import enabled_key_ids  # noqa: PLC0415
        result = enabled_key_ids()
        assert result == set(_EXPECTED_POOL_IDS)

    def test_full_set_is_enabled_all_true(self, monkeypatch) -> None:
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,2,3,4,5,6,7")
        from engine.neuralweb.key_pool import is_enabled  # noqa: PLC0415
        for cap_id in _EXPECTED_POOL_IDS:
            assert is_enabled(cap_id) is True, f"{cap_id} should be enabled"

    def test_full_set_discover_all_present(self, tmp_path: Path, monkeypatch) -> None:
        """With all 7 keys both present AND enabled, discover_present_keys returns all 7."""
        _write_manifest(tmp_path)
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,2,3,4,5,6,7")
        for i in range(1, 8):
            monkeypatch.setenv(f"CLAUDE_CODE_OAUTH_TOKEN_{i}", f"tok-{i}")

        from engine.neuralweb.key_pool import discover_present_keys  # noqa: PLC0415
        result = discover_present_keys(root=tmp_path)
        assert set(result) == set(_EXPECTED_POOL_IDS), (
            f"Full-set discover failed: {result}"
        )
        assert len(result) == 7
