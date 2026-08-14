"""Tests for engine/qledger_evidence_clock.py — the WRITE-ONCE record of each
qledger claim family's first prospective-registration instant (Eval OS P3).

THE PROPERTY UNDER TEST: `record_start` NEVER overwrites an existing family's
timestamp, no matter what a later call passes — a start timestamp that could
move forward would let a family's track record read as older/more-matured
than it honestly is. `test_second_call_never_overwrites_the_first` is that
property made executable; see this file's tail for the manual mutation-control
notes (paste-output requirement lives in the task report, not here — a
regression test cannot assert against code that isn't there).
"""
from __future__ import annotations

from engine import qledger_evidence_clock as qclock


def test_absent_family_reads_as_none(tmp_path):
    assert qclock.read_start("stock_desk", root=tmp_path) is None


def test_record_start_persists_and_reads_back(tmp_path):
    rec = qclock.record_start("stock_desk", horizon_d=20, horizon_unit="trading_days",
                              git_sha="abc123", root=tmp_path, now="2026-08-14T03:00:00+00:00")
    assert rec["claim_family"] == "stock_desk"
    assert rec["first_prospective_registration_utc"] == "2026-08-14T03:00:00+00:00"
    assert rec["declared_horizon_d"] == 20
    assert rec["horizon_unit"] == "trading_days"
    assert rec["git_sha"] == "abc123"
    reread = qclock.read_start("stock_desk", root=tmp_path)
    assert reread == rec


def test_second_call_never_overwrites_the_first(tmp_path):
    """THE write-once property. A second call — even with a LATER `now`, a
    DIFFERENT git_sha, and a DIFFERENT declared horizon — must return the
    ORIGINAL record byte-for-byte. This is the exact property CEO §evidence-
    clock requires: nothing may move a family's start timestamp forward."""
    first = qclock.record_start("stock_desk", horizon_d=20, horizon_unit="trading_days",
                                git_sha="sha-one", root=tmp_path, now="2026-08-14T03:00:00+00:00")
    second = qclock.record_start("stock_desk", horizon_d=999, horizon_unit="calendar_days",
                                 git_sha="sha-two", root=tmp_path, now="2027-01-01T00:00:00+00:00")
    assert second == first
    assert second["first_prospective_registration_utc"] == "2026-08-14T03:00:00+00:00"
    assert second["git_sha"] == "sha-one"
    assert second["declared_horizon_d"] == 20
    # the file on disk agrees — a caller who never called record_start again
    # and only re-read the file sees the same, unmoved timestamp.
    assert qclock.read_start("stock_desk", root=tmp_path) == first


def test_families_are_independent_files(tmp_path):
    qclock.record_start("stock_desk", horizon_d=20, horizon_unit="trading_days",
                        root=tmp_path, now="2026-08-14T03:00:00+00:00")
    assert qclock.read_start("thematic_desk", root=tmp_path) is None
    qclock.record_start("thematic_desk", horizon_d=20, horizon_unit="trading_days",
                        root=tmp_path, now="2026-08-15T03:00:00+00:00")
    stock = qclock.read_start("stock_desk", root=tmp_path)
    thematic = qclock.read_start("thematic_desk", root=tmp_path)
    assert stock["first_prospective_registration_utc"] == "2026-08-14T03:00:00+00:00"
    assert thematic["first_prospective_registration_utc"] == "2026-08-15T03:00:00+00:00"


def test_record_defaults_now_to_utc_wall_clock_when_not_supplied(tmp_path):
    rec = qclock.record_start("demand_chain", horizon_d=126, horizon_unit="trading_days",
                              root=tmp_path)
    assert rec["first_prospective_registration_utc"]
    # ISO-8601 with an explicit UTC offset (the CEO's exact requirement).
    ts = rec["first_prospective_registration_utc"]
    assert ts.endswith("+00:00") or ts.endswith("Z")


def test_git_sha_prefers_env_over_subprocess(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_SHA", "env-sha-value")
    assert qclock.git_sha(root=tmp_path) == "env-sha-value"


def test_git_sha_never_raises_on_a_non_repo_path(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    # tmp_path is not a git repo — `git rev-parse HEAD` fails; must return None,
    # never raise.
    assert qclock.git_sha(root=tmp_path) is None


def test_unreadable_clock_file_is_treated_as_absent_not_fatal(tmp_path):
    path = tmp_path.joinpath("data", "qledger", "evidence_clock_start")
    path.mkdir(parents=True)
    (path / "stock_desk.json").write_text("{ not json")
    assert qclock.read_start("stock_desk", root=tmp_path) is None
    # record_start on top of a corrupt file heals it (treated as absent -> writes fresh).
    rec = qclock.record_start("stock_desk", horizon_d=20, horizon_unit="trading_days",
                              root=tmp_path, now="2026-08-14T03:00:00+00:00")
    assert qclock.read_start("stock_desk", root=tmp_path) == rec
