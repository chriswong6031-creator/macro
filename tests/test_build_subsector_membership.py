"""tests/test_build_subsector_membership.py — preserve-through-rebuild tests.

Covers the fix for the nasdaq archetype_groups key being clobbered on each
nightly rebuild (frozen lobe since 2026-07-07).

Tests
-----
1. archetype_groups_preserved  — when the existing membership.json has an
                                  archetype_groups key and the new payload does
                                  not, _write() re-injects it so the key survives.
2. archetype_groups_not_clobbered_if_already_present
                               — when the new payload already carries its own
                                  archetype_groups value, the existing file's value
                                  is NOT substituted (payload wins).
3. no_existing_file            — when the output file does not yet exist, _write()
                                  writes without error (no archetype_groups to copy).
4. existing_file_malformed     — when the existing file is not valid JSON, _write()
                                  logs a warning and writes the new payload without
                                  raising.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_subsector_membership import _write


# ---------------------------------------------------------------------------
#  Minimal payload factory helpers
# ---------------------------------------------------------------------------

def _minimal_payload() -> dict:
    """Return a payload that mirrors what build_nasdaq() emits (no archetype_groups)."""
    return {
        "version": 1,
        "region": "nasdaq",
        "index": "Nasdaq-100",
        "benchmark": "QQQ",
        "benchmark_label": "Nasdaq-100 (QQQ)",
        "as_of": "2026-07-12",
        "source": "finviz",
        "subsectors": {
            "semiconductors": {
                "name": "Semiconductors",
                "sector": "Technology",
                "members": [{"ticker": "NVDA", "name": "NVIDIA"}],
            }
        },
        "amalgamations": {
            "technology": {
                "name": "Technology",
                "members": [{"ticker": "NVDA", "name": "NVIDIA"}],
            }
        },
    }


def _archetype_groups_fixture() -> dict:
    return {
        "notes": "Union semantics — tickers may appear in multiple groups.",
        "groups": {
            "ai_compute_supply": {
                "label_en": "AI Compute Supply Chain",
                "label_zh": "AI 算力供应链",
                "members": [{"ticker": "NVDA"}, {"ticker": "AMD"}],
            }
        },
    }


# ---------------------------------------------------------------------------
#  Test 1: archetype_groups survives a rebuild when not in the new payload
# ---------------------------------------------------------------------------

def test_archetype_groups_preserved(tmp_path):
    """_write() re-injects archetype_groups from the existing file when the
    new payload lacks it."""
    region = "nasdaq"
    out_dir = tmp_path / f"baskets_{region}"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "membership.json"

    # Write an existing membership.json that contains archetype_groups.
    existing = _minimal_payload()
    existing["archetype_groups"] = _archetype_groups_fixture()
    out_file.write_text(json.dumps(existing, indent=1), encoding="utf-8")

    # New payload from a fresh rebuild — no archetype_groups key.
    new_payload = _minimal_payload()
    assert "archetype_groups" not in new_payload

    with mock.patch("scripts.build_subsector_membership.config") as mock_cfg:
        mock_cfg.data_dir.return_value = tmp_path
        _write(region, new_payload)

    result = json.loads(out_file.read_text(encoding="utf-8"))
    assert "archetype_groups" in result, (
        "archetype_groups key should have been re-injected from the existing file"
    )
    assert result["archetype_groups"] == _archetype_groups_fixture()
    # Other keys should survive unchanged.
    assert result["subsectors"] == new_payload["subsectors"]
    assert result["as_of"] == "2026-07-12"


# ---------------------------------------------------------------------------
#  Test 2: payload's own archetype_groups wins over existing file's value
# ---------------------------------------------------------------------------

def test_archetype_groups_not_clobbered_if_already_present(tmp_path):
    """If the new payload already has archetype_groups, the existing file's
    value is NOT substituted."""
    region = "nasdaq"
    out_dir = tmp_path / f"baskets_{region}"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "membership.json"

    existing_ag = {"notes": "old value", "groups": {}}
    existing = _minimal_payload()
    existing["archetype_groups"] = existing_ag
    out_file.write_text(json.dumps(existing, indent=1), encoding="utf-8")

    new_ag = {"notes": "new value from operator", "groups": {"new_group": {}}}
    new_payload = _minimal_payload()
    new_payload["archetype_groups"] = new_ag

    with mock.patch("scripts.build_subsector_membership.config") as mock_cfg:
        mock_cfg.data_dir.return_value = tmp_path
        _write(region, new_payload)

    result = json.loads(out_file.read_text(encoding="utf-8"))
    assert result["archetype_groups"] == new_ag, (
        "payload's own archetype_groups should not be overridden by existing file"
    )


# ---------------------------------------------------------------------------
#  Test 3: no existing file — write succeeds without archetype_groups
# ---------------------------------------------------------------------------

def test_no_existing_file(tmp_path):
    """_write() works correctly when no prior membership.json exists."""
    region = "nasdaq"
    out_dir = tmp_path / f"baskets_{region}"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "membership.json"

    assert not out_file.exists()

    new_payload = _minimal_payload()
    with mock.patch("scripts.build_subsector_membership.config") as mock_cfg:
        mock_cfg.data_dir.return_value = tmp_path
        _write(region, new_payload)

    result = json.loads(out_file.read_text(encoding="utf-8"))
    assert result["version"] == 1
    assert "archetype_groups" not in result


# ---------------------------------------------------------------------------
#  Test 4: malformed existing file — warning logged, write proceeds
# ---------------------------------------------------------------------------

def test_existing_file_malformed(tmp_path):
    """_write() tolerates a malformed existing file: logs a warning and writes
    the new payload without re-injecting archetype_groups (safe degradation)."""
    region = "nasdaq"
    out_dir = tmp_path / f"baskets_{region}"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "membership.json"
    out_file.write_text("NOT VALID JSON {{{{", encoding="utf-8")

    new_payload = _minimal_payload()
    with mock.patch("scripts.build_subsector_membership.config") as mock_cfg:
        mock_cfg.data_dir.return_value = tmp_path
        # Must not raise.
        _write(region, new_payload)

    result = json.loads(out_file.read_text(encoding="utf-8"))
    assert result["version"] == 1
    assert "archetype_groups" not in result
