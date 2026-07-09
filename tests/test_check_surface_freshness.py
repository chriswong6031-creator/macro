"""Tests for scripts/check_surface_freshness.py — FT-R8 surface freshness sentinel.

Mirrors the test pattern from tests/test_check_price_store_freshness.py:
artifacts are monkeypatched via a temp root, the calendar is pinned to known dates,
and the sentinel's warn-only contract is verified (always exits 0).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.check_surface_freshness as sentinel
from scripts.check_surface_freshness import _ARTIFACTS, ArtifactSpec


# Reference time: 03:00 UTC on 2026-07-09 (well before the close-plus-settle window)
# so expected_last_session returns 2026-07-08.
REF_NOW = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)
EXPECTED = "2026-07-08"   # the expected NYSE session at REF_NOW


@pytest.fixture
def tmp_root(tmp_path):
    """Temp tree with all artifacts set fresh."""
    for spec in _ARTIFACTS:
        p = tmp_path / spec.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"as_of": EXPECTED}))
    return tmp_path


def test_all_fresh_exits_zero(tmp_root):
    rc = sentinel.run(now=REF_NOW, root=tmp_root)
    assert rc == 0


def test_all_fresh_no_warnings(tmp_root, capsys):
    sentinel.run(now=REF_NOW, root=tmp_root)
    out = capsys.readouterr().out
    assert "::warning::" not in out


def test_stale_artifact_emits_warning_but_exits_zero(tmp_root, capsys):
    spec = _ARTIFACTS[0]   # data/allocation/latest_us.json
    (tmp_root / spec.path).write_text(json.dumps({"as_of": "2026-07-06"}))
    rc = sentinel.run(now=REF_NOW, root=tmp_root)
    assert rc == 0, "warn-only sentinel must always exit 0"
    out = capsys.readouterr().out
    assert "::warning::SURFACE STALE:" in out
    assert spec.path in out
    assert "2026-07-06" in out
    assert EXPECTED in out


def test_missing_artifact_emits_warning_but_exits_zero(tmp_root, capsys):
    spec = _ARTIFACTS[0]
    (tmp_root / spec.path).unlink()
    rc = sentinel.run(now=REF_NOW, root=tmp_root)
    assert rc == 0
    out = capsys.readouterr().out
    assert "::warning::SURFACE STALE:" in out
    assert "MISSING" in out


def test_multiple_stale_artifacts_each_get_warning(tmp_root, capsys):
    for spec in _ARTIFACTS[:3]:
        (tmp_root / spec.path).write_text(json.dumps({"as_of": "2020-01-01"}))
    sentinel.run(now=REF_NOW, root=tmp_root)
    out = capsys.readouterr().out
    count = out.count("::warning::SURFACE STALE:")
    assert count == 3


def test_oracle_state_asof_fallback(tmp_root):
    """oracle_state.json may use 'asof' instead of 'as_of' in some builds."""
    spec = next(s for s in _ARTIFACTS if "oracle_state" in s.path)
    # Write with 'asof' key (the oracle variation)
    (tmp_root / spec.path).write_text(json.dumps({"asof": EXPECTED}))
    rc = sentinel.run(now=REF_NOW, root=tmp_root)
    assert rc == 0


def test_selftest_passes():
    assert sentinel.selftest() == 0
