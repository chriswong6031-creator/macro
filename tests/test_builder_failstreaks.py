"""Tests for consecutive-failure escalation — scripts/check_builder_failstreaks.py.

Guards:
1. First failure creates streak=1; no escalation below threshold.
2. Second consecutive night → streak=2 + escalation fires (::error:: annotation).
3. Success (rc=0) resets the entry (removed from ledger).
4. Same-UTC-day rerun does NOT double-increment the streak.
5. Gap > max-gap-days starts a fresh streak (streak resets to 1).
6. Prune drops entries with last_run_utc older than prune-days.
7. Off-lane (not 'nightly') does NOT write the ledger but still escalates.
8. Corrupt ledger JSON → fail-open, treated as empty; exit code 0.
9. push_ops_alert is monkeypatched; called once when breached, not called when clear.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import check_builder_failstreaks as M


# ── shared constants ──────────────────────────────────────────────────────

_D1 = datetime(2026, 7, 16, 8, 0, 0, tzinfo=timezone.utc)  # first failure day
_D2 = datetime(2026, 7, 17, 8, 0, 0, tzinfo=timezone.utc)  # second (consecutive) day
_D3 = datetime(2026, 7, 18, 8, 0, 0, tzinfo=timezone.utc)  # third day


# ── fixtures ──────────────────────────────────────────────────────────────


def _make_art(tmp_path: Path, builders: dict[str, int], labels: dict[str, str] | None = None) -> Path:
    """Create a band art dir with <slug>.rc and <slug>.log for each slug.

    builders = {slug: rc_int}
    labels   = {slug: label_string}  (optional; defaults to slug)
    """
    art = tmp_path / "band"
    art.mkdir(parents=True, exist_ok=True)
    labels = labels or {}
    for slug, rc in builders.items():
        (art / f"{slug}.rc").write_text(str(rc))
        label = labels.get(slug, f"{slug} label")
        (art / f"{slug}.log").write_text(f"{label}\nsome output line\n")
    return art


def _make_ledger(tmp_path: Path, builders: dict) -> Path:
    """Write a builder_failstreaks.json under tmp_path/data/ci/."""
    p = tmp_path / "data" / "ci"
    p.mkdir(parents=True, exist_ok=True)
    ledger_path = p / "builder_failstreaks.json"
    ledger_path.write_text(
        json.dumps({
            "schema": "builder_failstreaks.v1",
            "updated_utc": None,
            "builders": builders,
        })
    )
    return ledger_path


def _seed_ledger(tmp_path: Path) -> Path:
    """Seed ledger with empty builders dict."""
    return _make_ledger(tmp_path, {})


class _Dispatch:
    """Records calls to push_ops_alert and returns True (dispatched)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, *, source, type_, message, severity, lane, root=None, _now=None, **kw):
        self.calls.append(dict(source=source, type_=type_, message=message,
                               severity=severity, lane=lane))
        return True


# ── 1. First failure creates streak=1, no escalation below threshold ──────

class TestFirstFailure:
    def test_first_failure_streak_one(self, tmp_path):
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _seed_ledger(tmp_path)

        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )

        assert breached == [], "streak=1 is below threshold=2, must not escalate"
        data = json.loads(ledger_path.read_text())
        assert data["builders"]["cycle"]["streak"] == 1
        assert data["builders"]["cycle"]["first_fail_utc"] == "2026-07-16"
        assert dispatch.calls == [], "no alert below threshold"

    def test_first_failure_no_annotation(self, tmp_path, capsys):
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _seed_ledger(tmp_path)

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )

        out = capsys.readouterr().out
        assert "::error" not in out, "no annotation expected below threshold"


# ── 2. Second consecutive night → streak=2 + escalation fires ─────────────

class TestSecondConsecutiveNight:
    def _run_second_night(self, tmp_path, threshold=2):
        """Helper: set up a ledger with streak=1 from D1, run on D2."""
        art = _make_art(tmp_path, {"cycle": 1}, {"cycle": "cycle intelligence page (build_cycle)"})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle intelligence page (build_cycle)",
            }
        })
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=threshold,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )
        return breached, dispatch, ledger_path

    def test_streak_increments_to_2(self, tmp_path):
        _, _, ledger_path = self._run_second_night(tmp_path)
        data = json.loads(ledger_path.read_text())
        assert data["builders"]["cycle"]["streak"] == 2

    def test_breached_list_contains_slug(self, tmp_path):
        breached, _, _ = self._run_second_night(tmp_path)
        assert len(breached) == 1
        assert breached[0]["slug"] == "cycle"
        assert breached[0]["streak"] == 2

    def test_annotation_emitted_on_breach(self, tmp_path, capsys):
        art = _make_art(tmp_path, {"cycle": 1}, {"cycle": "cycle intelligence page (build_cycle)"})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle intelligence page (build_cycle)",
            }
        })
        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )
        # Emit annotations for breached builders
        for b in breached:
            M._emit_annotation(
                slug=b["slug"],
                streak=b["streak"],
                first_fail_utc=b["first_fail_utc"],
                label=b["label"],
                last_rc=b["last_rc"],
            )
        out = capsys.readouterr().out
        assert "::error title=BUILDER cycle failed 2 consecutive nightlies" in out

    def test_ops_alert_dispatched_once(self, tmp_path):
        # process_band returns breached list; alert dispatched by _dispatch_ops_alert (as in main())
        breached, _, ledger_path = self._run_second_night(tmp_path)
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M._dispatch_ops_alert(breached, tmp_path)
        assert len(dispatch.calls) == 1
        assert dispatch.calls[0]["source"] == "builder_failstreak"

    def test_ops_alert_not_called_below_threshold(self, tmp_path):
        # With threshold=3, a streak of 2 should not fire — breached list is empty
        breached, _, _ = self._run_second_night(tmp_path, threshold=3)
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M._dispatch_ops_alert(breached, tmp_path)
        assert dispatch.calls == []


# ── 3. Success resets the entry ───────────────────────────────────────────

class TestSuccessReset:
    def test_rc_zero_removes_entry(self, tmp_path):
        art = _make_art(tmp_path, {"cycle": 0})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 3,
                "first_fail_utc": "2026-07-14",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle intelligence page (build_cycle)",
            }
        })
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        assert breached == [], "recovered builder must not appear in breached"
        data = json.loads(ledger_path.read_text())
        assert "cycle" not in data["builders"], "recovered builder entry must be removed"
        assert dispatch.calls == [], "no alert after recovery"


# ── 4. Same-UTC-day rerun does NOT double-increment ───────────────────────

class TestSameDayRerun:
    def test_same_day_rerun_no_increment(self, tmp_path):
        # ledger already has streak=1 from today (D1)
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",  # same as today
                "last_rc": 1,
                "label": "cycle intelligence page (build_cycle)",
            }
        })
        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,  # same day as last_run_utc
            )
        data = json.loads(ledger_path.read_text())
        assert data["builders"]["cycle"]["streak"] == 1, "same-day rerun must not increment streak"


# ── 5. Gap > max-gap-days starts a fresh streak ───────────────────────────

class TestGapReset:
    def test_large_gap_resets_streak(self, tmp_path):
        # ledger has streak=3 from 2026-07-10, max_gap=4 days; running on 07-17 = 7d gap
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 3,
                "first_fail_utc": "2026-07-08",
                "last_fail_utc": "2026-07-10",
                "last_run_utc": "2026-07-10",
                "last_rc": 1,
                "label": "cycle intelligence page (build_cycle)",
            }
        })
        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,  # 2026-07-17, gap from 07-10 = 7 days > max_gap=4
            )

        data = json.loads(ledger_path.read_text())
        assert data["builders"]["cycle"]["streak"] == 1, "gap > max_gap_days must reset streak to 1"
        assert data["builders"]["cycle"]["first_fail_utc"] == "2026-07-17"
        assert breached == [], "streak=1 is below threshold=2"

    def test_gap_within_max_continues_streak(self, tmp_path):
        # ledger has streak=1 from 2026-07-14 (gap from 07-17 = 3 days, within max_gap=4)
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-14",
                "last_fail_utc": "2026-07-14",
                "last_run_utc": "2026-07-14",
                "last_rc": 1,
                "label": "cycle label",
            }
        })
        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,  # 2026-07-17, gap from 07-14 = 3 days <= max_gap=4
            )

        data = json.loads(ledger_path.read_text())
        assert data["builders"]["cycle"]["streak"] == 2, "gap within max must continue streak"
        assert len(breached) == 1


# ── 6. Prune drops stale entries ──────────────────────────────────────────

class TestPrune:
    def test_old_entry_pruned(self, tmp_path):
        # Entry with last_run_utc 40 days ago; prune_days=30.
        # Supply one active rc file so the nightly lane does not early-return
        # (empty rc set → ledger preserved; prune runs only when rc set is non-empty).
        art = _make_art(tmp_path, {"activebuilder": 0})  # rc=0 → recovered; triggers prune path
        ledger_path = _make_ledger(tmp_path, {
            "oldbuilder": {
                "streak": 5,
                "first_fail_utc": "2026-06-01",
                "last_fail_utc": "2026-06-07",
                "last_run_utc": "2026-06-07",  # 40 days before 2026-07-17
                "last_rc": 1,
                "label": "some old builder",
            }
        })
        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,  # 2026-07-17
            )
        data = json.loads(ledger_path.read_text())
        assert "oldbuilder" not in data["builders"], "stale entry must be pruned"

    def test_recent_entry_not_pruned(self, tmp_path):
        # Entry with last_run_utc 10 days ago; prune_days=30.
        # The entry continues to fail this run (rc=1), so it is present in rc_slugs
        # and the prune age-check (not stale) must keep it.
        art = _make_art(tmp_path, {"recentbuilder": 1})
        ledger_path = _make_ledger(tmp_path, {
            "recentbuilder": {
                "streak": 2,
                "first_fail_utc": "2026-07-07",
                "last_fail_utc": "2026-07-07",
                "last_run_utc": "2026-07-07",  # 10 days before 2026-07-17
                "last_rc": 1,
                "label": "recent builder",
            }
        })
        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )
        data = json.loads(ledger_path.read_text())
        assert "recentbuilder" in data["builders"], "recent entry must NOT be pruned"


# ── 7. Off-lane: no ledger write, still escalates ─────────────────────────

class TestOffLane:
    def _run_off_lane(self, tmp_path, lane):
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle intelligence page",
            }
        })
        # Record ledger mtime before
        mtime_before = ledger_path.stat().st_mtime

        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane=lane,
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        mtime_after = ledger_path.stat().st_mtime
        return breached, dispatch, mtime_before, mtime_after

    def test_empty_lane_no_ledger_write(self, tmp_path):
        _, _, mtime_before, mtime_after = self._run_off_lane(tmp_path, "")
        assert mtime_after == mtime_before, "off-lane must NOT write the ledger"

    def test_closingbell_lane_no_ledger_write(self, tmp_path):
        _, _, mtime_before, mtime_after = self._run_off_lane(tmp_path, "closingbell")
        assert mtime_after == mtime_before, "closingbell lane must NOT write the ledger"

    def test_off_lane_still_reports_breached(self, tmp_path):
        # Existing ledger already has streak=1 from 07-16; off-lane re-reads existing
        # ledger and sees already-breached entries without writing (streak from ledger).
        # But process_band reads the existing ledger and checks entries against threshold.
        # With streak=1 already in the ledger but today we'd increment to 2 —
        # the increment is in-memory even if we don't write.
        breached, _, _, _ = self._run_off_lane(tmp_path, "")
        assert len(breached) == 1, "off-lane must still detect and return breached builders"

    def test_off_lane_still_dispatches_alert(self, tmp_path):
        # process_band returns breached list even off-lane; main() calls _dispatch_ops_alert
        breached, _, _, _ = self._run_off_lane(tmp_path, "closingbell")
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M._dispatch_ops_alert(breached, tmp_path)
        assert len(dispatch.calls) == 1, "off-lane must still dispatch the alert"


# ── 8. Corrupt ledger JSON → fail-open ───────────────────────────────────

class TestCorruptLedger:
    def test_corrupt_json_treated_as_empty(self, tmp_path):
        p = tmp_path / "data" / "ci"
        p.mkdir(parents=True, exist_ok=True)
        (p / "builder_failstreaks.json").write_text("not valid json {{{{")
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = p / "builder_failstreaks.json"

        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )

        # Should start fresh — streak=1, no breach
        assert breached == [], "corrupt ledger must be treated as empty (streak=1, below threshold)"

    def test_corrupt_ledger_exit_zero(self, tmp_path):
        """main() must exit 0 even with a corrupt ledger."""
        p = tmp_path / "data" / "ci"
        p.mkdir(parents=True, exist_ok=True)
        (p / "builder_failstreaks.json").write_text("{bad json")
        art = _make_art(tmp_path, {})
        root = tmp_path

        result = M.main([
            "--art-dir", str(art),
            "--ledger", str(p / "builder_failstreaks.json"),
            "--lane", "nightly",
            "--root", str(root),
        ])
        assert result == 0

    def test_missing_art_dir_exit_zero(self, tmp_path):
        """main() must exit 0 even when art-dir doesn't exist."""
        art = tmp_path / "nonexistent_band"
        ledger_path = _seed_ledger(tmp_path)

        result = M.main([
            "--art-dir", str(art),
            "--ledger", str(ledger_path),
            "--lane", "nightly",
            "--root", str(tmp_path),
        ])
        assert result == 0


# ── 9. push_ops_alert monkeypatched; called/not-called correctly ──────────

class TestOpsAlertDispatch:
    def test_alert_called_once_when_breached(self, tmp_path):
        art = _make_art(tmp_path, {"cycle": 1, "sectorcyc": 1})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle label",
            },
            "sectorcyc": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "sectorcyc label",
            },
        })
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )
            # Simulate the dispatch call that main() would do
            if breached:
                M._dispatch_ops_alert(breached, tmp_path)

        # ONE combined alert, not one per builder
        assert len(dispatch.calls) == 1
        assert dispatch.calls[0]["source"] == "builder_failstreak"
        assert dispatch.calls[0]["type_"] == "fail_streak"

    def test_alert_not_called_when_nothing_breached(self, tmp_path):
        art = _make_art(tmp_path, {"cycle": 0})  # rc=0 → recovery
        ledger_path = _seed_ledger(tmp_path)
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )
            if breached:
                M._dispatch_ops_alert(breached, tmp_path)

        assert dispatch.calls == [], "no alert when nothing breached"

    def test_push_ops_alert_failure_is_swallowed(self, tmp_path):
        """push_ops_alert raising must not propagate — main() must still exit 0."""
        art = _make_art(tmp_path, {"cycle": 1})
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle label",
            }
        })

        def _raise(*a, **kw):
            raise RuntimeError("simulated transport failure")

        with patch("engine.alert_triage.push_ops_alert", _raise):
            result = M.main([
                "--art-dir", str(art),
                "--ledger", str(ledger_path),
                "--lane", "nightly",
                "--root", str(tmp_path),
            ])

        assert result == 0, "push_ops_alert failure must not fail the step"


# ── 10. Annotation shape ──────────────────────────────────────────────────

class TestAnnotationShape:
    def test_annotation_contains_error_title_builder(self, capsys):
        M._emit_annotation(
            slug="cycle",
            streak=2,
            first_fail_utc="2026-07-16",
            label="cycle intelligence page (build_cycle)",
            last_rc=1,
        )
        out = capsys.readouterr().out
        assert "::error title=BUILDER cycle failed 2 consecutive nightlies" in out
        assert "page frozen since 2026-07-16" in out
        assert "rc=1" in out

    def test_annotation_mentions_frozen_since(self, capsys):
        M._emit_annotation(
            slug="sectorcyc",
            streak=3,
            first_fail_utc="2026-07-15",
            label="sector cycles",
            last_rc=2,
        )
        out = capsys.readouterr().out
        assert "frozen since 2026-07-15" in out

    def test_annotation_references_ledger_path(self, capsys):
        M._emit_annotation(
            slug="cycle",
            streak=2,
            first_fail_utc="2026-07-16",
            label="cycle label",
            last_rc=1,
        )
        out = capsys.readouterr().out
        assert "data/ci/builder_failstreaks.json" in out


# ── 11. Unparseable rc file skipped ──────────────────────────────────────

class TestUnparseableRc:
    def test_empty_rc_file_skipped(self, tmp_path):
        art = tmp_path / "band"
        art.mkdir()
        (art / "cycle.rc").write_text("")  # empty
        (art / "cycle.log").write_text("cycle label\n")
        ledger_path = _seed_ledger(tmp_path)

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )
        # Empty rc → skipped entirely; no entry created
        data = json.loads(ledger_path.read_text())
        assert "cycle" not in data["builders"]
        assert breached == []

    def test_non_integer_rc_file_skipped(self, tmp_path):
        art = tmp_path / "band"
        art.mkdir()
        (art / "cycle.rc").write_text("notanumber\n")
        (art / "cycle.log").write_text("cycle label\n")
        ledger_path = _seed_ledger(tmp_path)

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )
        data = json.loads(ledger_path.read_text())
        assert "cycle" not in data["builders"]


# ── 12. Label fallback — unreadable/absent .log → slug used ──────────────

class TestLabelFallback:
    def test_missing_log_falls_back_to_slug(self, tmp_path):
        """When <slug>.log is absent, the label stored in the ledger is the slug."""
        art = tmp_path / "band"
        art.mkdir()
        (art / "mybuilder.rc").write_text("1")
        # NO mybuilder.log — label must fall back to slug
        ledger_path = _seed_ledger(tmp_path)

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )

        data = json.loads(ledger_path.read_text())
        assert data["builders"]["mybuilder"]["label"] == "mybuilder", (
            "absent .log must fall back to slug as label"
        )

    def test_empty_log_falls_back_to_slug(self, tmp_path):
        """When <slug>.log is empty (no first line), the label is the slug."""
        art = tmp_path / "band"
        art.mkdir()
        (art / "mybuilder.rc").write_text("1")
        (art / "mybuilder.log").write_text("")  # empty
        ledger_path = _seed_ledger(tmp_path)

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D1,
            )

        data = json.loads(ledger_path.read_text())
        assert data["builders"]["mybuilder"]["label"] == "mybuilder", (
            "empty .log must fall back to slug as label"
        )

    def test_annotation_uses_slug_as_label_when_log_absent(self, tmp_path, capsys):
        """Annotation body must use the slug as label when .log is missing."""
        # Set up a pre-existing streak=1 so we breach on D2
        art = tmp_path / "band"
        art.mkdir()
        (art / "mybuilder.rc").write_text("1")
        # No .log file
        ledger_path = _make_ledger(tmp_path, {
            "mybuilder": {
                "streak": 1,
                "first_fail_utc": "2026-07-16",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "mybuilder",  # slug as label (as stored from D1)
            }
        })

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        assert len(breached) == 1
        assert breached[0]["label"] == "mybuilder"

        M._emit_annotation(
            slug=breached[0]["slug"],
            streak=breached[0]["streak"],
            first_fail_utc=breached[0]["first_fail_utc"],
            label=breached[0]["label"],
            last_rc=breached[0]["last_rc"],
        )
        out = capsys.readouterr().out
        assert "::error" in out
        assert "mybuilder" in out


# ── 13. Absent-slug decay — nightly lane, non-empty rc set ───────────────

class TestAbsentSlugDecay:
    def test_absent_slug_dropped_on_nightly(self, tmp_path):
        """Ledger entry for a retired builder is dropped when absent from rc set."""
        # retired_builder has streak=2 in the ledger but produces NO rc file this run
        art = _make_art(tmp_path, {"activebuilder": 0})  # only activebuilder ran
        ledger_path = _make_ledger(tmp_path, {
            "retired_builder": {
                "streak": 2,
                "first_fail_utc": "2026-07-15",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "retired builder label",
            }
        })

        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        # Entry dropped; not in breached list
        assert all(b["slug"] != "retired_builder" for b in breached), (
            "absent slug must not appear in breached list"
        )
        data = json.loads(ledger_path.read_text())
        assert "retired_builder" not in data["builders"], (
            "absent slug must be removed from the ledger on nightly lane"
        )

    def test_absent_slug_no_ops_alert(self, tmp_path):
        """No ops alert fired for a builder dropped by decay (not in breached)."""
        art = _make_art(tmp_path, {"activebuilder": 0})
        ledger_path = _make_ledger(tmp_path, {
            "retired_builder": {
                "streak": 5,
                "first_fail_utc": "2026-07-10",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "retired builder label",
            }
        })

        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )
            if breached:
                M._dispatch_ops_alert(breached, tmp_path)

        assert dispatch.calls == [], "no ops alert for a retired/absent builder"


# ── 14. Empty art dir / no rc files — ledger preserved ───────────────────

class TestEmptyArtDirLedgerPreserved:
    def test_no_rc_files_ledger_unchanged(self, tmp_path):
        """On nightly with no .rc files, the ledger is NOT written (byte-identical)."""
        art = tmp_path / "band"
        art.mkdir()  # dir exists but contains no .rc files

        original_content = json.dumps({
            "schema": "builder_failstreaks.v1",
            "updated_utc": None,
            "builders": {
                "cycle": {
                    "streak": 3,
                    "first_fail_utc": "2026-07-14",
                    "last_fail_utc": "2026-07-16",
                    "last_run_utc": "2026-07-16",
                    "last_rc": 1,
                    "label": "cycle label",
                }
            },
        })
        p = tmp_path / "data" / "ci"
        p.mkdir(parents=True, exist_ok=True)
        ledger_path = p / "builder_failstreaks.json"
        ledger_path.write_text(original_content)

        mtime_before = ledger_path.stat().st_mtime
        content_before = ledger_path.read_text()

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        mtime_after = ledger_path.stat().st_mtime
        content_after = ledger_path.read_text()

        assert mtime_after == mtime_before, "ledger must NOT be written when rc set is empty"
        assert content_after == content_before, "ledger content must be byte-identical"
        assert breached == [], "no escalation from ledger-only state when rc set is empty"

    def test_no_rc_files_exit_zero(self, tmp_path):
        """main() exits 0 even when art dir has no .rc files."""
        art = tmp_path / "band"
        art.mkdir()
        ledger_path = _seed_ledger(tmp_path)

        result = M.main([
            "--art-dir", str(art),
            "--ledger", str(ledger_path),
            "--lane", "nightly",
            "--root", str(tmp_path),
        ])
        assert result == 0

    def test_no_rc_files_no_dispatch(self, tmp_path):
        """No ops alert dispatched when the band produced no rc files."""
        art = tmp_path / "band"
        art.mkdir()
        ledger_path = _make_ledger(tmp_path, {
            "cycle": {
                "streak": 5,
                "first_fail_utc": "2026-07-10",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "cycle label",
            }
        })
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="nightly",
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )
            if breached:
                M._dispatch_ops_alert(breached, tmp_path)

        assert dispatch.calls == [], "no dispatch when rc set is empty"


# ── 15. Off-lane + absent slug → entry retained ───────────────────────────

class TestOffLaneAbsentSlugRetained:
    def test_off_lane_absent_slug_retained_in_ledger(self, tmp_path):
        """Off-lane runs must NOT mutate the ledger — absent slugs are retained."""
        art = _make_art(tmp_path, {"activebuilder": 0})  # retired_builder absent
        ledger_path = _make_ledger(tmp_path, {
            "retired_builder": {
                "streak": 2,
                "first_fail_utc": "2026-07-15",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "retired builder label",
            }
        })

        mtime_before = ledger_path.stat().st_mtime

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="closingbell",  # off-lane
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        mtime_after = ledger_path.stat().st_mtime
        assert mtime_after == mtime_before, "off-lane must NOT write the ledger"

        # Ledger file is unchanged — entry still present in the on-disk file
        data = json.loads(ledger_path.read_text())
        assert "retired_builder" in data["builders"], (
            "off-lane must not drop absent slugs — no decay off-lane"
        )

    def test_off_lane_absent_slug_breached_in_memory(self, tmp_path):
        """Off-lane: in-memory increment still computes breach from absent slug's ledger state."""
        # The retired builder is at streak=1 in ledger; off-lane would increment to 2 in-memory
        # but since it's absent from rc set and we're off-lane, it goes through normal processing
        # (no absent-slug drop off-lane) and since it was at streak=1 — BUT it has no rc file,
        # so it won't be processed in the rc loop at all. The ledger entry won't be incremented.
        # Breached list: only builders with rc files in THIS run can be incremented;
        # retired_builder has no rc file → it stays at streak=1 (below threshold=2) in-memory.
        art = _make_art(tmp_path, {"activebuilder": 0})
        ledger_path = _make_ledger(tmp_path, {
            "retired_builder": {
                "streak": 2,  # already at streak=2 in ledger (above threshold)
                "first_fail_utc": "2026-07-15",
                "last_fail_utc": "2026-07-16",
                "last_run_utc": "2026-07-16",
                "last_rc": 1,
                "label": "retired builder label",
            }
        })

        with patch("engine.alert_triage.push_ops_alert", _Dispatch()):
            breached = M.process_band(
                art_dir=art,
                ledger_path=ledger_path,
                lane="closingbell",  # off-lane
                threshold=2,
                max_gap_days=4,
                prune_days=30,
                root=tmp_path,
                _now=_D2,
            )

        # Off-lane: no decay, ledger entry is loaded as-is.
        # retired_builder has streak=2 in ledger and no rc file this run →
        # it is not in rc_slugs → not processed in rc loop → stays at streak=2 in builders dict
        # → appears in breached list (existing ledger state drives it).
        breached_slugs = [b["slug"] for b in breached]
        assert "retired_builder" in breached_slugs, (
            "off-lane: existing ledger streak must still drive breach detection "
            "even for absent slugs"
        )
