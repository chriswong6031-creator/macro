"""The membership-snapshot freshness tripwire — three axes, three verdicts.

THE INCIDENT IT IS SHAPED AGAINST
--------------------------------
The THS point-in-time membership store held two snapshots — 2026-06-30 and
2026-07-08 — for six weeks, while ``build_baskets_china_ths --snapshot`` ran
green ~35 nights in a row.  Nothing was broken in that step: it is
content-deduped, it hashed today's ``membership.json`` against the newest
side-car, matched, and skipped.  The INPUT was frozen, because the scraper and
the seeder that refresh ``membership.json`` were in no workflow at all.

A deduping writer and an unwired writer leave the identical trace on disk:
nothing.  So the guard cannot be "is the newest snapshot recent" — that reads
healthy in both cases.  It has to ask three separate questions, and the tests
below are organised as one class per question, ending with the case that needs
all three (``test_a_live_writer_on_a_frozen_source_still_breaches``).

Fixture-only: every evaluator takes its inputs and its clock as arguments, so
nothing here reads live ``data/`` and nothing spells a wall-clock literal that
today's date could invalidate.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from lib import config
from scripts import check_membership_snapshot_freshness as guard

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _stamp(days_ago: float) -> dict:
    return {"checked_at": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _receipt(days_ago: float, *, complete: bool = True) -> dict:
    return {"date": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
            "complete": complete, "concepts_fetched": 373 if complete else 200,
            "concepts_attempted": 373}


# ===========================================================================
# axis 1 — cadence: did the WRITER run at all
# ===========================================================================

class TestCadenceAxis:
    def test_a_recent_run_is_fresh(self):
        assert guard.evaluate_cadence(_stamp(1), NOW)[0] == guard.FRESH

    def test_a_writer_that_stopped_running_is_a_breach(self):
        verdict, detail = guard.evaluate_cadence(_stamp(43), NOW)
        assert verdict == guard.BREACH
        assert "budget" in detail, "the annotation must say what budget was blown"

    def test_the_boundary_is_inclusive_of_the_budget(self):
        """Exactly at budget is still fresh; a nightly that lands late on day 4 of a
        long weekend must not page anyone."""
        assert guard.evaluate_cadence(_stamp(guard.CADENCE_MAX_DAYS), NOW)[0] == guard.FRESH
        assert guard.evaluate_cadence(
            _stamp(guard.CADENCE_MAX_DAYS + 0.5), NOW)[0] == guard.BREACH

    def test_a_missing_stamp_is_indeterminate_never_a_breach(self):
        """Sparse agent checkouts carry no data/, and a suite's first run has no stamp
        by construction. Calling either a breach trains every reader to ignore this."""
        assert guard.evaluate_cadence(None, NOW)[0] == guard.INDETERMINATE
        assert guard.evaluate_cadence({}, NOW)[0] == guard.INDETERMINATE

    def test_an_unreadable_stamp_is_a_breach_not_indeterminate(self):
        """The file EXISTS, so the writer is wired — it is the stamp that is wrong. A
        guard that reads a malformed date as 'no information' lets a broken writer stay
        quiet forever."""
        assert guard.evaluate_cadence({"checked_at": "not-a-date"}, NOW)[0] == guard.BREACH
        assert guard.evaluate_cadence({"checked_at": ""}, NOW)[0] == guard.BREACH


# ===========================================================================
# axis 2 — source: has a COMPLETE scrape landed (THS only)
# ===========================================================================

class TestSourceAxis:
    def test_a_recent_complete_scrape_is_fresh(self):
        assert guard.evaluate_scrape([_receipt(2)], NOW)[0] == guard.FRESH

    def test_a_complete_scrape_older_than_the_budget_is_a_breach(self):
        assert guard.evaluate_scrape([_receipt(51)], NOW)[0] == guard.BREACH

    def test_attempts_that_never_complete_are_a_breach(self):
        """A run of complete:false receipts means the scrape is being attempted and
        failing — nothing is promoted, so the membership input is frozen even though
        the lane looks busy. The detail must distinguish it from 'no receipts'."""
        verdict, detail = guard.evaluate_scrape(
            [_receipt(1, complete=False), _receipt(8, complete=False)], NOW)
        assert verdict == guard.BREACH
        assert "NONE complete" in detail

    def test_one_complete_receipt_rescues_a_pile_of_failures(self):
        assert guard.evaluate_scrape(
            [_receipt(1, complete=False), _receipt(3), _receipt(2, complete=False)],
            NOW)[0] == guard.FRESH

    def test_no_receipts_is_indeterminate(self):
        assert guard.evaluate_scrape([], NOW)[0] == guard.INDETERMINATE

    def test_only_the_ths_suite_is_source_audited(self):
        """The US membership.json is hand-curated, so 'the source has not moved this
        month' is its normal state, not a fault."""
        assert guard.SOURCE_AUDITED == frozenset({guard.SUITE_THS})


# ===========================================================================
# axis 3 — coherence: did the side-cars reach the queryable store
# ===========================================================================

class TestCoherenceAxis:
    def test_a_parquet_that_covers_the_newest_side_car_is_fresh(self):
        assert guard.evaluate_coherence("2026-08-15", "2026-08-15")[0] == guard.FRESH

    def test_a_parquet_ahead_of_the_side_cars_is_fine(self):
        """The nightly also stamps membership.json directly, so the parquet legitimately
        runs ahead of the weekly raw side-cars."""
        assert guard.evaluate_coherence("2026-08-19", "2026-08-15")[0] == guard.FRESH

    def test_a_parquet_lagging_the_newest_side_car_is_a_breach(self):
        verdict, detail = guard.evaluate_coherence("2026-07-08", "2026-08-15")
        assert verdict == guard.BREACH
        assert "backfill" in detail

    def test_side_cars_with_no_parquet_at_all_is_a_breach(self):
        """The ingest is the thing under audit, so 'the store does not exist' is the
        strongest evidence it never ran — not an absence of evidence."""
        assert guard.evaluate_coherence(None, "2026-08-15")[0] == guard.BREACH

    def test_an_empty_plane_is_indeterminate(self):
        assert guard.evaluate_coherence(None, None)[0] == guard.INDETERMINATE


# ===========================================================================
# the composite case — why one axis was never going to be enough
# ===========================================================================

def test_a_live_writer_on_a_frozen_source_still_breaches():
    """THE incident, in one assertion. The writer ran last night (cadence FRESH) and
    the parquet matches the side-cars (coherence FRESH) — and the plane is still dead,
    because no complete scrape has landed in six weeks. Only the source axis sees it."""
    assert guard.evaluate_cadence(_stamp(1), NOW)[0] == guard.FRESH
    assert guard.evaluate_coherence("2026-07-08", "2026-07-08")[0] == guard.FRESH
    assert guard.evaluate_scrape([_receipt(51)], NOW)[0] == guard.BREACH


# ===========================================================================
# the run() shell — annotation SHAPE, verdict routing, and exit code
# ===========================================================================

@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


def _write_plane(root, suite, *, stamp=None, receipts=(), side_cars=(), parquet_dates=()):
    snaps = root / suite / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    if stamp is not None:
        (snaps / "_cadence.json").write_text(json.dumps(stamp), encoding="utf-8")
    for date in side_cars:
        (snaps / f"{date}.json").write_text("{}", encoding="utf-8")
    if receipts:
        rd = root / suite / "receipts"
        rd.mkdir(parents=True, exist_ok=True)
        for r in receipts:
            (rd / f"scrape_{r['date']}.json").write_text(json.dumps(r), encoding="utf-8")
    if parquet_dates:
        import pandas as pd

        pd.DataFrame({"snapshot_date": list(parquet_dates), "suite": suite,
                      "basket_id": "b", "ticker": "T"}).to_parquet(
            root / suite / "membership_history.parquet", index=False)


def _annotations(captured: str) -> list[str]:
    """Only lines that START with '::' are annotations GitHub will parse."""
    return [ln for ln in captured.splitlines() if ln.startswith("::")]


def test_a_breach_emits_a_line_start_warning_and_still_exits_zero(data_root, capsys,
                                                                 monkeypatch):
    """Advisory by contract: one cold membership plane must not red a collection lane
    that landed every other store. And the annotation must START the line — every
    builder here logs with a prefixing format, so a logger call would emit
    'WARNING ::warning ...' and GitHub would silently drop it."""
    monkeypatch.setattr(guard, "_push_alert", lambda _m: None)
    _write_plane(data_root, guard.SUITE_THS, stamp=_stamp(40),
                 receipts=[_receipt(60)], side_cars=["2026-07-08"],
                 parquet_dates=["2026-07-08"])
    _write_plane(data_root, guard.SUITE_US, stamp=_stamp(1),
                 side_cars=["2026-08-19"], parquet_dates=["2026-08-19"])

    assert guard.run(now=NOW) == 0
    anns = _annotations(capsys.readouterr().out)
    warnings = [a for a in anns if a.startswith("::warning ")]
    assert len(warnings) == 1, anns
    assert warnings[0].startswith("::warning title=membership snapshot cadence stalled::")
    assert "baskets_china_ths [cadence]" in warnings[0]
    assert "baskets_china_ths [source]" in warnings[0]
    assert "baskets [cadence]" not in warnings[0], "a healthy suite must not be named"


def test_a_healthy_plane_emits_no_annotation_at_all(data_root, capsys, monkeypatch):
    monkeypatch.setattr(guard, "_push_alert", lambda _m: None)
    _write_plane(data_root, guard.SUITE_THS, stamp=_stamp(1), receipts=[_receipt(3)],
                 side_cars=["2026-08-17"], parquet_dates=["2026-08-19"])
    _write_plane(data_root, guard.SUITE_US, stamp=_stamp(1),
                 side_cars=["2026-08-19"], parquet_dates=["2026-08-19"])

    assert guard.run(now=NOW) == 0
    assert _annotations(capsys.readouterr().out) == []


def test_an_absent_plane_is_one_notice_and_never_a_warning(data_root, capsys, monkeypatch):
    """The sparse-checkout / first-run case. Nothing on disk at all."""
    monkeypatch.setattr(guard, "_push_alert", lambda _m: None)
    assert guard.run(now=NOW) == 0
    anns = _annotations(capsys.readouterr().out)
    assert len(anns) == 1 and anns[0].startswith("::notice title=")
    assert not [a for a in anns if a.startswith("::warning")]


def test_the_ops_alert_push_is_fail_open(data_root, capsys, monkeypatch):
    """An unreachable alert spine must not silence the annotation, which is the
    guaranteed half of the teeth."""
    def boom(*_a, **_k):
        raise RuntimeError("triage unreachable")

    monkeypatch.setattr(guard, "_read_cadence", lambda _s: _stamp(40))
    monkeypatch.setattr("engine.alert_triage.push_ops_alert", boom, raising=False)
    assert guard.run(now=NOW) == 0
    assert [a for a in _annotations(capsys.readouterr().out) if a.startswith("::warning")]


def test_the_selftest_passes():
    assert guard.selftest() == 0
