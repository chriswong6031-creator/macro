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


# ── escalation: the annotation was never the gap, the reader was ──────────────
#
# 2026-08-04: this sentinel emitted EIGHT staleness annotations into a job summary
# and nothing consumed them. The US board stayed frozen at as_of=2026-07-31 until
# 08-06, when the operator noticed the prices were wrong — six days during which
# every night printed the diagnosis. Detection was never missing; a reader was.
#
# run() now pushes ONE digest to the ops spine when the worst surface is
# ESCALATE_SESSIONS_BEHIND sessions or more behind. The threshold matters in both
# directions: too low and a routine late render pages someone until they mute the
# channel, which reproduces the original failure with extra steps.


@pytest.fixture
def _captured_push(monkeypatch):
    """Capture push_ops_alert calls without touching Telegram/Discord."""
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return True

    import engine.alert_triage as at
    monkeypatch.setattr(at, "push_ops_alert", fake)
    return calls


def _set_as_of(root: Path, value: str) -> None:
    p = root / _ARTIFACTS[0].path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"as_of": value}))


def test_two_sessions_behind_escalates_once_not_per_surface(tmp_root, _captured_push):
    """Six stale surfaces describing one frozen board is ONE incident.

    Six pushes is how an operator learns to mute the channel.
    """
    for spec in _ARTIFACTS:
        (tmp_root / spec.path).write_text(json.dumps({"as_of": "2026-07-02"}))
    assert sentinel.run(now=REF_NOW, root=tmp_root) == 0
    assert len(_captured_push) == 1, "one digest, never one alert per surface"
    kw = _captured_push[0]
    assert kw["source"] == "surface_freshness"
    assert kw["severity"] == "major"
    assert "session(s) behind" in kw["message"]


def test_one_session_behind_annotates_but_does_not_page(tmp_root, _captured_push, capsys):
    """A single session behind is a late render, not an outage.

    The annotation still prints — this narrows who gets woken, not what gets seen.
    """
    _set_as_of(tmp_root, "2026-07-07")   # one session before EXPECTED 2026-07-08
    assert sentinel.run(now=REF_NOW, root=tmp_root) == 0
    assert "SURFACE STALE" in capsys.readouterr().out, "the annotation must still fire"
    assert _captured_push == [], "one session behind must not page"


def test_a_missing_artifact_always_escalates(tmp_root, _captured_push):
    """An artifact that is not there published nothing — there is no date to measure."""
    (tmp_root / _ARTIFACTS[0].path).unlink()
    assert sentinel.run(now=REF_NOW, root=tmp_root) == 0
    assert len(_captured_push) == 1


def test_a_broken_alert_channel_never_breaks_the_render(tmp_root, monkeypatch, capsys):
    """FT-R8's contract is exit 0 ALWAYS. Escalation may not weaken that."""
    import engine.alert_triage as at

    def boom(**kwargs):
        raise RuntimeError("telegram is down")

    monkeypatch.setattr(at, "push_ops_alert", boom)
    for spec in _ARTIFACTS:
        (tmp_root / spec.path).write_text(json.dumps({"as_of": "2026-07-02"}))
    assert sentinel.run(now=REF_NOW, root=tmp_root) == 0, "a dead channel must not fail the sentinel"
    assert "SURFACE STALE" in capsys.readouterr().out, "and the annotations must survive it"
