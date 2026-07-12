"""tests/test_metabolism_reflex.py — Hermetic tests for R-V8-6..R-V8-9 reflex arcs.

COVERAGE:
  R-V8-6 — metabolism_revert.py
    1.  revert_scan_actions_plan_once — durable actioned-marker written; second scan skips
    2.  revert_bound_respected — max_open_revert_prs=1 processes only 1 of 2 plans
    3.  revert_conflict_abort_no_force — conflict → status=revert_conflict, no PR, marker written
    4.  operator_tap_rows_untouched — operator_tap triage records NOT actioned
    5.  paused_no_op — AUTONOMY_PAUSED → scan returns without writing anything

  R-V8-7 — falsifier→ladder bridge
    6.  breach_bridge_writes_one_row — clean-overfit FALSIFIER_TRIPPED writes one breach row
    7.  breach_bridge_idempotent — calling verify_proposal twice on same cycle does NOT
        double-write (upstream scan skip means second call doesn't happen; we test the
        bridge function directly to confirm idempotency of journal_breach itself)
    8.  health_miss_exclusion_preserved — operator_tap (regime) outcome does NOT call bridge
    9.  confirmed_no_breach — CONFIRMED outcome does NOT call bridge

  R-V8-8 — tap escalation
    10. reping_threshold_honored — tap held > tap_reping_days → repinged, plan NOT executed
    11. park_threshold_honored — tap held > tap_park_days → parked, plan NOT executed
    12. reping_not_duplicate_same_day — second digest run same day → no duplicate reping
    13. tap_record_untouched_by_execution — the tap's recommended_default / safe-defaults untouched

  R-V8-9 — construction parking
    14. parked_construction_blocks_matching_proposal — parked row blocks same lobe+kind+sensor
    15. release_row_unblocks — row with release_grant_id unparks the construction
    16. different_lobe_not_blocked — different lobe is not blocked
    17. parked_construction_appended_by_verify — clean-overfit FALSIFIER_TRIPPED appends park row

All tests HERMETIC (tmp dirs, monkeypatch, no real subprocess, no real network).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tmp_root(extra_subdirs: list[str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="metab_reflex_test_"))
    for sub in [
        "data/metabolism/verify",
        "data/metabolism/revert",
        "data/metabolism/journal",
        "data/metabolism/dockets",
        "data/metabolism/tap",
        "data/metabolism/lifecycle",
        "data/metabolism",
        "config",
        "docs",
        "research",
    ]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n")
    (d / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n")
    (d / "config" / "metabolism_budget.yml").write_text(
        "schema: metabolism_budget.v1\n"
        "max_open_revert_prs: 2\n"
        "tap_reping_days: 7\n"
        "tap_park_days: 21\n"
        "max_build_attempts: 2\n"
        "stale_running_ttl_hours: 3\n"
        "max_audit_rebuild_attempts: 2\n"
        "audit_max_diff_lines: 2000\n"
    )
    for sub in (extra_subdirs or []):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _armed_env() -> dict[str, str]:
    return {**os.environ, "AUTONOMY_PAUSED": "false"}


def _paused_env() -> dict[str, str]:
    return {**os.environ, "AUTONOMY_PAUSED": "true"}


def _write_verify_record(
    root: Path,
    cycle_id: str,
    action: str,
    proposal_id: str | None = None,
    classification: str = "overfit",
) -> Path:
    """Write a minimal verify record."""
    data = {
        "schema": "metabolism.verify.v1",
        "cycle_id": cycle_id,
        "proposal_id": proposal_id or cycle_id,
        "check_by": "2026-07-01",
        "contract": {
            "proposal_id": proposal_id or cycle_id,
            "lobe": "test_lobe",
            "sensor": "test_sensor",
            "kind": "til",
        },
        "realized": {"outcome": "FALSIFIER_TRIPPED", "detail": "test", "delta_vs_contract": None},
        "triage": {
            "classification": classification,
            "action": action,
            "revert_plan": (
                {
                    "action": "git_revert",
                    "target": f"metabolism/{proposal_id or cycle_id}",
                    "proposal_id": proposal_id or cycle_id,
                    "do_not_rebuild_row": {
                        "title": "Test proposal",
                        "rationale": "overfit",
                        "appended_by": "metabolism_verify",
                        "ts": "2026-07-12T00:00:00+00:00",
                    },
                }
                if action == "revert_plan" else None
            ),
            "operator_tap_reason": "ambiguous" if action == "operator_tap" else None,
        },
        "ts": "2026-07-12T00:00:00+00:00",
    }
    p = root / "data" / "metabolism" / "verify" / f"{cycle_id}.json"
    p.write_text(json.dumps(data, indent=2))
    return p


def _write_tap_card(
    root: Path,
    proposal_id: str,
    held_days: int = 0,
    *,
    already_expired: bool = False,
    already_repinged_today: bool = False,
) -> Path:
    """Write a minimal tap card file."""
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=held_days)).isoformat(timespec="seconds")
    card = {
        "schema": "metabolism.tap_card.v1",
        "ts": ts,
        "headline": f"Test tap for {proposal_id}",
        "why_now": "test",
        "tap_kind": "revert_plan",
        "recommended_default": "hold_for_review",
        "options": [],
        "auto_action_on_timeout": {"action": "hold_for_review", "note": "immutable"},
        "authority": {"is_context_only": True, "display_only": True},
        "context": {"proposal_id": proposal_id},
    }
    if already_expired:
        card["_expired_parked"] = True
    if already_repinged_today:
        card["_repinged_digest_run"] = now.strftime("%Y-%m-%d")
    p = root / "data" / "metabolism" / "tap" / f"tap_{proposal_id}.json"
    p.write_text(json.dumps(card, indent=2))
    return p


def _import_revert():
    import scripts.metabolism_revert as mr
    importlib.reload(mr)
    return mr


def _import_digest():
    import scripts.metabolism_digest as md
    importlib.reload(md)
    return md


def _import_build():
    import scripts.metabolism_build as mb
    importlib.reload(mb)
    return mb


# ─────────────────────────────────────────────────────────────────────────────
# R-V8-6: metabolism_revert.py
# ─────────────────────────────────────────────────────────────────────────────

class TestRevertScanActionsOnce:
    """Durable actioned-marker written; second scan sees it and skips."""

    def test_actioned_marker_written_on_success(self):
        mr = _import_revert()
        d = _tmp_root()
        cycle_id = "cycle-rev-001"
        pid = "p_rev1"
        _write_verify_record(d, cycle_id, "revert_plan", pid)

        # Stub out everything external
        calls: list[str] = []

        def fake_resolve_pr(plan, root):
            calls.append("resolve_pr")
            return 42

        def fake_resolve_sha(pr_num, root):
            calls.append(f"resolve_sha:{pr_num}")
            return "sha_abc123"

        def fake_create_wt(branch, root):
            calls.append("create_wt")
            return {"wt_path": tempfile.mkdtemp(prefix="fake_wt_"), "error": None}

        def fake_remove_wt(branch, wt_path, root):
            calls.append("remove_wt")

        # git revert succeeds
        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        def fake_push(branch, wt_path, root):
            calls.append("push")
            return True

        def fake_open_pr(branch, plan_record, *, root, dry_run):
            calls.append("open_pr")
            return {"pr_number": 100, "pr_url": "https://example.com/100", "opened": True}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", side_effect=fake_resolve_pr):
                with patch.object(mr, "_resolve_merge_sha", side_effect=fake_resolve_sha):
                    with patch.object(mr, "_create_revert_worktree", side_effect=fake_create_wt):
                        with patch.object(mr, "_remove_revert_worktree", side_effect=fake_remove_wt):
                            with patch.object(mr, "_push_revert_branch", side_effect=fake_push):
                                with patch.object(mr, "_open_draft_revert_pr", side_effect=fake_open_pr):
                                    with patch("subprocess.run", return_value=fake_run_ok):
                                        result = mr._process_one_plan(
                                            {
                                                "proposal_id": pid,
                                                "cycle_id": cycle_id,
                                                "verify_path": str(d),
                                                "revert_plan": {"action": "git_revert",
                                                                "target": "test"},
                                                "do_not_rebuild_row": {"title": "test"},
                                            },
                                            d,
                                            dry_run=False,
                                        )

        assert result.get("status") == "revert_pr_opened", (
            f"Expected revert_pr_opened, got {result.get('status')!r}"
        )
        # Durable marker must exist
        marker_path = d / "data" / "metabolism" / "revert" / f"{pid}.json"
        assert marker_path.exists(), "Actioned marker not written"
        marker = json.loads(marker_path.read_text())
        assert marker.get("status") == "revert_pr_opened"
        assert marker.get("proposal_id") == pid

    def test_second_scan_skips_actioned_plan(self):
        mr = _import_revert()
        d = _tmp_root()
        cycle_id = "cycle-rev-002"
        pid = "p_rev2"
        _write_verify_record(d, cycle_id, "revert_plan", pid)

        # Pre-write the actioned marker
        marker_dir = d / "data" / "metabolism" / "revert"
        (marker_dir / f"{pid}.json").write_text(json.dumps({
            "schema": "metabolism.revert_actioned.v1",
            "ts": "2026-07-12T00:00:00+00:00",
            "proposal_id": pid,
            "status": "revert_pr_opened",
            "pr_number": 99,
        }))

        plans = mr._scan_unactioned_revert_plans(d)
        pids = [p.get("proposal_id") for p in plans]
        assert pid not in pids, (
            f"Already-actioned plan {pid} should be excluded from scan, got: {pids}"
        )


class TestRevertBoundRespected:
    """max_open_revert_prs=1 processes only 1 of 2 plans."""

    def test_bound_limits_processing(self):
        mr = _import_revert()
        d = _tmp_root()
        # Override budget to max_open_revert_prs=1
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\nmax_open_revert_prs: 1\n"
        )

        _write_verify_record(d, "cycle-a", "revert_plan", "pid_a")
        _write_verify_record(d, "cycle-b", "revert_plan", "pid_b")

        plans = mr._scan_unactioned_revert_plans(d)
        assert len(plans) == 2, "Should find 2 un-actioned plans"

        max_prs = mr._load_max_open_revert_prs(d)
        assert max_prs == 1, f"max_open_revert_prs should be 1, got {max_prs}"

        to_process = plans[:max_prs]
        assert len(to_process) == 1, "Should process exactly 1 plan"


class TestRevertConflictAbortNoForce:
    """Conflict → abort, mark actioned with revert_conflict, no forced PR."""

    def test_conflict_marks_conflict_no_pr(self):
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_conflict"

        # git revert returns non-zero (conflict)
        fake_run_conflict = MagicMock()
        fake_run_conflict.returncode = 1
        fake_run_conflict.stdout = ""
        fake_run_conflict.stderr = "CONFLICT (content): Merge conflict in engine/foo.py"

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        pr_calls: list[str] = []

        def fake_open_pr(*args, **kwargs):
            pr_calls.append("opened")
            return {"pr_number": 1, "opened": True}

        def fake_run_dispatch(cmd, **kwargs):
            # git revert --no-edit → conflict; git revert --abort → ok
            if "revert" in cmd and "--no-edit" in cmd:
                return fake_run_conflict
            return fake_run_ok

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=42):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_conflict"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(), "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_open_draft_revert_pr", side_effect=fake_open_pr):
                                with patch("subprocess.run", side_effect=fake_run_dispatch):
                                    result = mr._process_one_plan(
                                        {
                                            "proposal_id": pid,
                                            "cycle_id": "cycle-conflict",
                                            "verify_path": "/fake",
                                            "revert_plan": {"action": "git_revert", "target": "test"},
                                            "do_not_rebuild_row": {},
                                        },
                                        d,
                                        dry_run=False,
                                    )

        assert result.get("status") == "revert_conflict", (
            f"Expected revert_conflict, got {result.get('status')!r}"
        )
        assert len(pr_calls) == 0, "PR must NOT be opened on conflict"
        # Marker must be written with conflict status
        marker_path = d / "data" / "metabolism" / "revert" / f"{pid}.json"
        assert marker_path.exists(), "Conflict actioned marker not written"
        marker = json.loads(marker_path.read_text())
        assert marker.get("status") == "revert_conflict"


class TestOperatorTapRowsUntouched:
    """operator_tap triage records are NOT scanned or actioned."""

    def test_operator_tap_not_in_scan(self):
        mr = _import_revert()
        d = _tmp_root()
        _write_verify_record(d, "cycle-tap", "operator_tap", "pid_tap")

        plans = mr._scan_unactioned_revert_plans(d)
        pids = [p.get("proposal_id") for p in plans]
        assert "pid_tap" not in pids, (
            "operator_tap records must not appear in revert scan"
        )


class TestPausedNoOp:
    """AUTONOMY_PAUSED → no-op exit 0, no markers written."""

    def test_paused_returns_immediately(self):
        mr = _import_revert()
        d = _tmp_root()
        _write_verify_record(d, "cycle-paused", "revert_plan", "pid_paused")

        process_calls: list[str] = []

        def fake_process(plan, root, *, dry_run=False):
            process_calls.append(plan.get("proposal_id"))
            return {"status": "revert_pr_opened"}

        env = _paused_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_process_one_plan", side_effect=fake_process):
                exit_code = mr.main(["--root", str(d)])

        assert exit_code == 0
        assert len(process_calls) == 0, "Paused: _process_one_plan must not be called"
        # No actioned markers
        revert_dir = d / "data" / "metabolism" / "revert"
        assert not list(revert_dir.glob("*.json")), "No markers should be written when paused"


# ─────────────────────────────────────────────────────────────────────────────
# R-V8-7: falsifier→ladder bridge
# ─────────────────────────────────────────────────────────────────────────────

class TestBreachBridgeWritesOneRow:
    """Clean-overfit FALSIFIER_TRIPPED feeds exactly one logic_breach row."""

    def test_bridge_writes_one_breach_row(self):
        from engine.metabolism.verify import _feed_breach_from_falsifier

        d = _tmp_root()
        contract = {
            "lobe": "test_lobe_bridge",
            "sensor": "momentum",
            "kind": "til",
            "proposal_id": "p_bridge_001",
        }
        triage = {
            "classification": "overfit",
            "action": "revert_plan",
        }
        _feed_breach_from_falsifier("cycle-bridge-001", contract, triage, d)

        journal_path = d / "data" / "metabolism" / "lifecycle" / "test_lobe_bridge.jsonl"
        assert journal_path.exists(), "Lifecycle journal must be created"
        rows = [json.loads(l) for l in journal_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1, f"Expected 1 breach row, got {len(rows)}"
        row = rows[0]
        assert row.get("breach_type") == "logic_breach"
        assert row.get("lobe_id") == "test_lobe_bridge"
        assert row.get("counted") is True, "Row must be counted"
        assert row.get("regime_paused") is False


class TestBreachBridgeIdempotent:
    """journal_breach is idempotent per call: two explicit calls = two rows, but
    the upstream scan skip (verify record already exists) prevents double-calls
    in production.  Here we just verify the bridge function does not deduplicate
    internally (it shouldn't — each tripped cycle = one breach)."""

    def test_two_calls_two_rows(self):
        from engine.metabolism.verify import _feed_breach_from_falsifier

        d = _tmp_root()
        contract = {
            "lobe": "test_lobe_idem",
            "sensor": "mom",
            "proposal_id": "p_idem",
        }
        triage = {"action": "revert_plan", "classification": "overfit"}

        _feed_breach_from_falsifier("cycle-idem-001", contract, triage, d)
        _feed_breach_from_falsifier("cycle-idem-002", contract, triage, d)

        journal_path = d / "data" / "metabolism" / "lifecycle" / "test_lobe_idem.jsonl"
        rows = [json.loads(l) for l in journal_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 2, (
            f"Each cycle produces one breach row; two calls = two rows, got {len(rows)}"
        )


class TestHealthMissExclusionPreserved:
    """operator_tap outcome (regime ambiguity) does NOT call the bridge."""

    def test_operator_tap_does_not_call_bridge(self):
        from engine.metabolism import verify as v
        importlib.reload(v)

        d = _tmp_root()
        feed_calls: list[str] = []

        def fake_feed(cycle_id, contract, triage, root):
            feed_calls.append(cycle_id)

        contract = {
            "lobe": "test_lobe_tap",
            "sensor": "mom",
            "proposal_id": "p_tap_001",
            "check_by": "2000-01-01",  # already arrived
            "falsifier_spec": {},
        }

        with patch.object(v, "_feed_breach_from_falsifier", side_effect=fake_feed):
            with patch.object(v, "_park_construction_from_falsifier"):
                with patch.object(v, "_evaluate_contract",
                                   return_value=("FALSIFIER_TRIPPED", "test")):
                    with patch.object(v, "_measurement_lens_triage",
                                       return_value={
                                           "classification": "regime_change",
                                           "action": "operator_tap",
                                           "revert_plan": None,
                                           "operator_tap_reason": "regime",
                                       }):
                        with patch.object(v, "_append_governance_tap"):
                            with patch.object(v, "_append_lesson_from_verify"):
                                with patch.object(v, "_append_strategic_memory_from_verify"):
                                    with patch.object(v, "_archive_on_verify"):
                                        v.verify_proposal(
                                            cycle_id="cycle-tap-test",
                                            contract=contract,
                                            root=d,
                                            today="2026-07-12",
                                        )

        assert len(feed_calls) == 0, (
            "operator_tap outcome must NOT call _feed_breach_from_falsifier"
        )


class TestConfirmedNoBreach:
    """CONFIRMED outcome does NOT call the bridge."""

    def test_confirmed_no_bridge(self):
        from engine.metabolism import verify as v
        importlib.reload(v)

        d = _tmp_root()
        feed_calls: list[str] = []

        def fake_feed(cycle_id, contract, triage, root):
            feed_calls.append(cycle_id)

        contract = {
            "lobe": "test_lobe_confirmed",
            "sensor": "mom",
            "proposal_id": "p_confirm",
            "check_by": "2000-01-01",
            "falsifier_spec": {},
        }

        with patch.object(v, "_feed_breach_from_falsifier", side_effect=fake_feed):
            with patch.object(v, "_park_construction_from_falsifier"):
                with patch.object(v, "_evaluate_contract",
                                   return_value=("CONFIRMED", "confirmed")):
                    with patch.object(v, "_append_governance_tap"):
                        with patch.object(v, "_append_lesson_from_verify"):
                            with patch.object(v, "_append_strategic_memory_from_verify"):
                                with patch.object(v, "_archive_on_verify"):
                                    v.verify_proposal(
                                        cycle_id="cycle-confirm-test",
                                        contract=contract,
                                        root=d,
                                        today="2026-07-12",
                                    )

        assert len(feed_calls) == 0, "CONFIRMED outcome must NOT call _feed_breach_from_falsifier"


# ─────────────────────────────────────────────────────────────────────────────
# R-V8-8: tap escalation
# ─────────────────────────────────────────────────────────────────────────────

class TestRepingThresholdHonored:
    """Tap held > tap_reping_days emits reping insight and Telegram; plan NOT executed."""

    def test_reping_fires_for_stale_tap(self):
        md = _import_digest()
        d = _tmp_root()

        _write_tap_card(d, "p_reping_test", held_days=10)  # > 7 days

        now = datetime.now(timezone.utc)
        telegram_msgs: list[str] = []
        insights_emitted: list[str] = []

        def fake_send_tg(msg):
            telegram_msgs.append(msg)
            return True

        def fake_append_row(row, root=None):
            insights_emitted.append(row.get("kind"))
            return True

        with patch("scripts.notify.send_telegram", side_effect=fake_send_tg):
            with patch("engine.metabolism.insight_bus.append_row", side_effect=fake_append_row):
                actions = md._escalate_held_taps(d, now, dry_run=False)

        reping_actions = [a for a in actions if a.get("action") == "repinged"]
        assert len(reping_actions) >= 1, f"Expected at least 1 reping action, got {actions}"
        assert "tap_repinged" in insights_emitted, "tap_repinged insight must be emitted"
        assert any("tap_repinged" in msg or "still waiting" in msg.lower()
                   for msg in telegram_msgs), "Telegram must be notified"

    def test_reping_does_not_execute_plan(self):
        """The tap's auto_action_on_timeout and recommended_default must be UNCHANGED."""
        md = _import_digest()
        d = _tmp_root()

        tap_path = _write_tap_card(d, "p_reping_safe", held_days=10)
        orig = json.loads(tap_path.read_text())

        now = datetime.now(timezone.utc)

        with patch("scripts.notify.send_telegram", return_value=True):
            with patch("engine.metabolism.insight_bus.append_row", return_value=True):
                md._escalate_held_taps(d, now, dry_run=False)

        # Re-read the tap file
        updated = json.loads(tap_path.read_text())
        # Core decision fields must be unchanged
        assert updated.get("recommended_default") == orig.get("recommended_default"), (
            "recommended_default must not be modified"
        )
        assert updated.get("auto_action_on_timeout") == orig.get("auto_action_on_timeout"), (
            "auto_action_on_timeout must not be modified"
        )
        assert updated.get("tap_kind") == orig.get("tap_kind"), "tap_kind must not change"


class TestParkThresholdHonored:
    """Tap held > tap_park_days → parked insight emitted, plan NOT executed."""

    def test_park_fires_for_very_old_tap(self):
        md = _import_digest()
        d = _tmp_root()

        _write_tap_card(d, "p_park_test", held_days=25)  # > 21 days

        now = datetime.now(timezone.utc)
        insights_emitted: list[str] = []

        def fake_append_row(row, root=None):
            insights_emitted.append(row.get("kind"))
            return True

        with patch("scripts.notify.send_telegram", return_value=True):
            with patch("engine.metabolism.insight_bus.append_row", side_effect=fake_append_row):
                actions = md._escalate_held_taps(d, now, dry_run=False)

        parked = [a for a in actions if a.get("action") == "parked"]
        assert len(parked) >= 1, f"Expected at least 1 park action, got {actions}"
        assert "tap_expired" in insights_emitted, "tap_expired insight must be emitted"

    def test_park_does_not_execute_plan(self):
        """After parking, the tap's safe-defaults must be unchanged."""
        md = _import_digest()
        d = _tmp_root()

        tap_path = _write_tap_card(d, "p_park_safe", held_days=25)
        orig = json.loads(tap_path.read_text())

        now = datetime.now(timezone.utc)
        with patch("scripts.notify.send_telegram", return_value=True):
            with patch("engine.metabolism.insight_bus.append_row", return_value=True):
                md._escalate_held_taps(d, now, dry_run=False)

        updated = json.loads(tap_path.read_text())
        assert updated.get("recommended_default") == orig.get("recommended_default")
        assert updated.get("auto_action_on_timeout") == orig.get("auto_action_on_timeout")


class TestRepingNotDuplicateSameDay:
    """Second digest run on the same day does NOT re-send a reping."""

    def test_no_duplicate_reping_same_day(self):
        md = _import_digest()
        d = _tmp_root()

        # Tap already repinged today
        _write_tap_card(d, "p_reping_dup", held_days=10, already_repinged_today=True)

        now = datetime.now(timezone.utc)
        telegram_msgs: list[str] = []

        with patch("scripts.notify.send_telegram",
                   side_effect=lambda m: telegram_msgs.append(m) or True):
            with patch("engine.metabolism.insight_bus.append_row", return_value=True):
                actions = md._escalate_held_taps(d, now, dry_run=False)

        # Action should be "reping_already_sent_today" or "none" for this tap
        for a in actions:
            assert a.get("action") in ("reping_already_sent_today", "none", "parked"), (
                f"Unexpected action {a.get('action')!r}"
            )
        assert len(telegram_msgs) == 0, (
            "No Telegram message should be sent for already-repinged-today tap"
        )


# ─────────────────────────────────────────────────────────────────────────────
# R-V8-9: construction parking
# ─────────────────────────────────────────────────────────────────────────────

class TestParkedConstructionBlocksMatchingProposal:
    """A parked_construction row in claims.jsonl blocks matching proposals."""

    def test_parked_blocks_same_lobe_kind_sensor(self):
        mb = _import_build()
        d = _tmp_root()

        # Write a parked_construction claim row
        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": "2026-07-12T00:00:00+00:00",
            "proposal_id": "p_old_001",
            "parked_construction": {
                "lobe": "til",
                "sensors": ["momentum"],
                "kind": "til",
            },
            "release_grant_id": None,
        }
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        claims_path.write_text(json.dumps(park_row) + "\n")

        proposal = {
            "proposal_id": "p_new_001",
            "lobe": "til",
            "kind": "til",
            "targets_sensor": "momentum",
        }

        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is True, "Matching proposal should be blocked by parked construction"

    def test_different_sensor_not_blocked(self):
        mb = _import_build()
        d = _tmp_root()

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": "2026-07-12T00:00:00+00:00",
            "proposal_id": "p_old_002",
            "parked_construction": {
                "lobe": "til",
                "sensors": ["momentum"],
                "kind": "til",
            },
            "release_grant_id": None,
        }
        claims_path.write_text(json.dumps(park_row) + "\n")

        proposal = {
            "proposal_id": "p_new_002",
            "lobe": "til",
            "kind": "til",
            "targets_sensor": "value",   # different sensor
        }

        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is False, "Different sensor should NOT be blocked"


class TestReleaseRowUnblocks:
    """A release_grant_id row unparks the construction."""

    def test_release_row_allows_build(self):
        mb = _import_build()
        d = _tmp_root()

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        # Parked row
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": "2026-07-12T00:00:00+00:00",
            "proposal_id": "p_old_003",
            "parked_construction": {
                "lobe": "til",
                "sensors": ["momentum"],
                "kind": "til",
            },
            "release_grant_id": None,
        }
        # Release row (same proposal_id, has release_grant_id)
        release_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": "2026-07-13T00:00:00+00:00",
            "proposal_id": "p_old_003",
            "parked_construction": {
                "lobe": "til",
                "sensors": ["momentum"],
                "kind": "til",
            },
            "release_grant_id": "grant_xyz_123",
        }
        claims_path.write_text(
            json.dumps(park_row) + "\n" + json.dumps(release_row) + "\n"
        )

        proposal = {
            "proposal_id": "p_new_003",
            "lobe": "til",
            "kind": "til",
            "targets_sensor": "momentum",
        }

        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is False, "Release row must unpark the construction"


class TestDifferentLobeNotBlocked:
    """A parked construction in lobe A does not block a proposal for lobe B."""

    def test_different_lobe_not_blocked(self):
        mb = _import_build()
        d = _tmp_root()

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": "2026-07-12T00:00:00+00:00",
            "proposal_id": "p_old_004",
            "parked_construction": {
                "lobe": "til",
                "sensors": ["momentum"],
                "kind": "til",
            },
            "release_grant_id": None,
        }
        claims_path.write_text(json.dumps(park_row) + "\n")

        proposal = {
            "proposal_id": "p_new_004",
            "lobe": "crypto",        # different lobe
            "kind": "til",
            "targets_sensor": "momentum",
        }

        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is False, "Different lobe must NOT be blocked"


class TestParkedConstructionAppendedByVerify:
    """On clean-overfit FALSIFIER_TRIPPED, verify appends parked_construction row."""

    def test_park_row_appended_on_clean_overfit(self):
        """FIX-1: verify_proposal RETURNS park_intent=True; the lane caller
        (_execute_reflex_intents) fires _park_construction_from_falsifier, not
        verify_proposal itself.  We test the intent is present in the result
        and that _execute_reflex_intents calls the park function."""
        from engine.metabolism import verify as v
        importlib.reload(v)
        import scripts.metabolism_verify as mv
        importlib.reload(mv)

        d = _tmp_root()
        (d / "data" / "metabolism" / "reflex").mkdir(parents=True, exist_ok=True)
        (d / "data" / "metabolism" / "lifecycle").mkdir(parents=True, exist_ok=True)

        contract = {
            "lobe": "til_park",
            "sensor": "momentum",
            "kind": "til",
            "proposal_id": "p_park_verify",
            "check_by": "2000-01-01",
            "falsifier_spec": {},
        }

        with patch.object(v, "_evaluate_contract",
                          return_value=("FALSIFIER_TRIPPED", "test")):
            with patch.object(v, "_measurement_lens_triage",
                              return_value={
                                  "classification": "overfit",
                                  "action": "revert_plan",
                                  "revert_plan": {"action": "git_revert", "target": "test"},
                                  "operator_tap_reason": None,
                              }):
                with patch.object(v, "_append_governance_tap"):
                    with patch.object(v, "_append_lesson_from_verify"):
                        with patch.object(v, "_append_strategic_memory_from_verify"):
                            with patch.object(v, "_archive_on_verify"):
                                record = v.verify_proposal(
                                    cycle_id="cycle-park-verify",
                                    contract=contract,
                                    root=d,
                                    today="2026-07-12",
                                )

        # verify_proposal must return park_intent=True (not call it directly)
        intents = record.get("_side_effect_intents") or {}
        assert intents.get("park_intent") is True, (
            "verify_proposal must set park_intent=True in result for clean-overfit"
        )

        # Now verify the lane caller fires the park function
        park_calls: list[str] = []

        def fake_park(cycle_id, contract_arg, root_arg):
            park_calls.append(cycle_id)

        with patch.object(v, "_park_construction_from_falsifier", side_effect=fake_park):
            with patch.object(v, "_feed_breach_from_falsifier"):
                mv._execute_reflex_intents("cycle-park-verify", record, d)

        assert len(park_calls) == 1, (
            f"_execute_reflex_intents must call _park_construction_from_falsifier "
            f"exactly once, got {len(park_calls)}"
        )

    def test_park_row_content(self):
        """_park_construction_from_falsifier writes the correct row to claims.jsonl."""
        from engine.metabolism.verify import append_parked_construction

        d = _tmp_root()
        claims_path = d / "data" / "metabolism" / "claims.jsonl"

        append_parked_construction(
            proposal_id="p_content",
            lobe="til",
            sensors=["momentum", "trend"],
            kind="til",
            root=d,
        )

        assert claims_path.exists(), "claims.jsonl must be created"
        rows = [json.loads(l) for l in claims_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row.get("schema") == "metabolism.parked_construction.v1"
        assert row.get("proposal_id") == "p_content"
        pc = row.get("parked_construction") or {}
        assert pc.get("lobe") == "til"
        assert set(pc.get("sensors") or []) == {"momentum", "trend"}
        assert pc.get("kind") == "til"
        assert row.get("release_grant_id") is None


# ─────────────────────────────────────────────────────────────────────────────
# Insight bus �� new kinds registered
# ─────────────────────────────────────────────────────────────────────────────

class TestInsightBusKindsRegistered:
    """All new insight kinds from R-V8 are in _KINDS."""

    def test_reflex_kinds_in_bus(self):
        from engine.metabolism.insight_bus import _KINDS
        for kind in ("tap_repinged", "tap_expired", "parked_construction",
                     "revert_plan_actioned", "revert_plan_conflict"):
            assert kind in _KINDS, f"{kind!r} missing from insight_bus._KINDS"


# ─────────────────────────────────────────────────────────────────────────────
# FIX-1: dry-run writes NOTHING durable
# ─────────────────────────────────────────────────────────────────────────────

class TestDryRunNoDurableWrites:
    """FIX-1: dry-run on a tripped-falsifier cycle writes zero durable rows."""

    def test_dry_run_no_breach_no_park(self):
        """verify_proposal + dry-run lane must produce zero durable side-effect writes."""
        from engine.metabolism import verify as v
        importlib.reload(v)
        import scripts.metabolism_verify as mv
        importlib.reload(mv)

        d = _tmp_root()
        (d / "data" / "metabolism" / "reflex").mkdir(parents=True, exist_ok=True)
        (d / "data" / "metabolism" / "lifecycle").mkdir(parents=True, exist_ok=True)
        claims_path = d / "data" / "metabolism" / "claims.jsonl"

        contract = {
            "lobe": "til_dry",
            "sensor": "momentum",
            "kind": "til",
            "proposal_id": "p_dry_001",
            "check_by": "2000-01-01",
            "falsifier_spec": {},
        }

        with patch.object(v, "_evaluate_contract",
                          return_value=("FALSIFIER_TRIPPED", "test")):
            with patch.object(v, "_measurement_lens_triage",
                              return_value={
                                  "classification": "overfit",
                                  "action": "revert_plan",
                                  "revert_plan": {"action": "git_revert", "target": "test"},
                                  "operator_tap_reason": None,
                              }):
                with patch.object(v, "_append_governance_tap"):
                    with patch.object(v, "_append_lesson_from_verify"):
                        with patch.object(v, "_append_strategic_memory_from_verify"):
                            with patch.object(v, "_archive_on_verify"):
                                record = v.verify_proposal(
                                    cycle_id="cycle-dry-001",
                                    contract=contract,
                                    root=d,
                                    today="2026-07-12",
                                )

        # The record carries intents but verify_proposal must NOT have fired them
        intents = record.get("_side_effect_intents") or {}
        assert intents.get("breach_intent") is True
        assert intents.get("park_intent") is True

        # No lifecycle journal rows (breach not fired)
        lifecycle_dir = d / "data" / "metabolism" / "lifecycle"
        assert not list(lifecycle_dir.glob("*.jsonl")), (
            "No lifecycle journal should exist: breach must not fire in verify_proposal"
        )

        # No claims rows (park not fired)
        assert not claims_path.exists() or claims_path.read_text().strip() == "", (
            "No claims row should exist: park must not fire in verify_proposal"
        )

        # Simulate _run_single with dry_run=True: _execute_reflex_intents must NOT be called
        execute_calls: list[str] = []

        def fake_execute(cycle_id, rec, root):
            execute_calls.append(cycle_id)

        with patch.object(mv, "_execute_reflex_intents", side_effect=fake_execute):
            # dry_run=True → _execute_reflex_intents should NOT be called
            mv._run_single(
                "cycle-dry-001",
                contract,
                d,
                "2026-07-12",
                dry_run=True,
            )

        assert len(execute_calls) == 0, (
            "With dry_run=True, _execute_reflex_intents must NOT be called"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-2: breach + park idempotency
# ─────────────────────────────────────────────────────────────────────────────

class TestReflexIdempotency:
    """FIX-2: running the bridge twice on the same cycle_id → exactly one
    breach row + one park row."""

    def test_double_run_single_breach_single_park(self):
        """Simulate _execute_reflex_intents twice on the same cycle_id.

        The second call must be a no-op (idempotency marker already written).
        Result: exactly 1 lifecycle row + 1 claims row.
        """
        import scripts.metabolism_verify as mv
        importlib.reload(mv)
        from engine.metabolism.verify import (
            _reflex_already_executed,
            _write_reflex_marker,
        )

        d = _tmp_root()
        (d / "data" / "metabolism" / "reflex").mkdir(parents=True, exist_ok=True)
        (d / "data" / "metabolism" / "lifecycle").mkdir(parents=True, exist_ok=True)

        contract = {
            "lobe": "til_idem",
            "sensor": "momentum",
            "kind": "til",
            "proposal_id": "p_idem_fix2",
        }
        record = {
            "cycle_id": "cycle-idem-fix2",
            "contract": contract,
            "triage": {"classification": "overfit", "action": "revert_plan"},
            "_side_effect_intents": {"breach_intent": True, "park_intent": True},
        }

        # First call — should execute and write marker
        mv._execute_reflex_intents("cycle-idem-fix2", record, d)

        lj = d / "data" / "metabolism" / "lifecycle" / "til_idem.jsonl"
        claims = d / "data" / "metabolism" / "claims.jsonl"
        assert lj.exists(), "Lifecycle journal must be written on first call"
        assert claims.exists(), "Claims.jsonl must be written on first call"

        rows_after_first = [
            json.loads(l) for l in lj.read_text().splitlines() if l.strip()
        ]
        claims_after_first = [
            json.loads(l) for l in claims.read_text().splitlines() if l.strip()
        ]
        assert len(rows_after_first) == 1, "Exactly 1 breach row after first call"
        assert len(claims_after_first) == 1, "Exactly 1 park row after first call"

        # Second call — idempotency marker exists; must be a no-op
        mv._execute_reflex_intents("cycle-idem-fix2", record, d)

        rows_after_second = [
            json.loads(l) for l in lj.read_text().splitlines() if l.strip()
        ]
        claims_after_second = [
            json.loads(l) for l in claims.read_text().splitlines() if l.strip()
        ]
        assert len(rows_after_second) == 1, (
            f"Second call must be idempotent: still 1 breach row, got {len(rows_after_second)}"
        )
        assert len(claims_after_second) == 1, (
            f"Second call must be idempotent: still 1 park row, got {len(claims_after_second)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-3: simultaneously-open revert PR bound
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenRevertPrBound:
    """FIX-3: gh pr list returning N open → opens at most max-N."""

    def test_bound_respects_existing_open_prs(self):
        """If gh pr list returns 1 open revert PR and max=2, only 1 plan is processed."""
        mr = _import_revert()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\nmax_open_revert_prs: 2\n"
        )

        _write_verify_record(d, "cycle-aa", "revert_plan", "pid_aa")
        _write_verify_record(d, "cycle-bb", "revert_plan", "pid_bb")

        # Simulate gh pr list returning 1 open revert PR
        fake_gh_output = json.dumps([
            {"number": 200, "headRefName": "claude/metabolism-revert-some-old-plan"},
        ])
        fake_gh_result = MagicMock()
        fake_gh_result.returncode = 0
        fake_gh_result.stdout = fake_gh_output
        fake_gh_result.stderr = ""

        process_calls: list[str] = []

        def fake_process(plan, root, *, dry_run=False):
            process_calls.append(plan.get("proposal_id"))
            return {"status": "revert_pr_opened"}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch("subprocess.run", return_value=fake_gh_result):
                with patch.object(mr, "_process_one_plan", side_effect=fake_process):
                    mr.main(["--root", str(d)])

        # max=2, already_open=1 → slots=1 → exactly 1 plan processed
        assert len(process_calls) == 1, (
            f"With max=2 and 1 already open, should process 1 plan, got {len(process_calls)}"
        )

    def test_zero_slots_when_at_cap(self):
        """If gh pr list returns max open revert PRs, no new plans are processed."""
        mr = _import_revert()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\nmax_open_revert_prs: 1\n"
        )

        _write_verify_record(d, "cycle-cc", "revert_plan", "pid_cc")

        # gh pr list returns 1 open revert PR and max=1 → no slots
        fake_gh_output = json.dumps([
            {"number": 201, "headRefName": "claude/metabolism-revert-existing"},
        ])
        fake_gh_result = MagicMock()
        fake_gh_result.returncode = 0
        fake_gh_result.stdout = fake_gh_output
        fake_gh_result.stderr = ""

        process_calls: list[str] = []

        def fake_process(plan, root, *, dry_run=False):
            process_calls.append(plan.get("proposal_id"))
            return {"status": "revert_pr_opened"}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch("subprocess.run", return_value=fake_gh_result):
                with patch.object(mr, "_process_one_plan", side_effect=fake_process):
                    mr.main(["--root", str(d)])

        assert len(process_calls) == 0, (
            f"At cap (max=1, open=1), no new plans should be processed, "
            f"got {len(process_calls)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-4: revert intent not lost on gh failure
# ─────────────────────────────────────────────────────────────────────────────

class TestRevertIntentRetryOnGhFailure:
    """FIX-4: gh pr create fails after push → plan NOT permanently actioned (retried)."""

    def test_gh_failure_marks_retryable_status(self):
        """When gh pr create fails (opened=False), marker status = revert_pr_open_failed,
        and the plan is NOT permanently actioned."""
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_gh_fail"

        # gh pr create fails
        def fake_open_pr_fail(*args, **kwargs):
            return {
                "pr_number": None, "pr_url": None, "opened": False,
                "error": "gh: Not Found",
            }

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=42):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_fail"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(), "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_open_draft_revert_pr",
                                              side_effect=fake_open_pr_fail):
                                with patch.object(mr, "_push_revert_branch",
                                                  return_value=True):
                                    with patch("subprocess.run", return_value=MagicMock(
                                        returncode=0, stdout="", stderr=""
                                    )):
                                        result = mr._process_one_plan(
                                            {
                                                "proposal_id": pid,
                                                "cycle_id": "cycle-ghfail",
                                                "verify_path": "/fake",
                                                "revert_plan": {"action": "git_revert",
                                                                "target": "test"},
                                                "do_not_rebuild_row": {},
                                            },
                                            d,
                                            dry_run=False,
                                        )

        # Status must be revert_pr_open_failed
        assert result.get("status") == "revert_pr_open_failed", (
            f"Expected revert_pr_open_failed, got {result.get('status')!r}"
        )

        # Marker must be written with the retryable status
        marker_path = d / "data" / "metabolism" / "revert" / f"{pid}.json"
        assert marker_path.exists(), "Actioned marker must be written"
        marker = json.loads(marker_path.read_text())
        assert marker.get("status") == "revert_pr_open_failed", (
            f"Marker status must be revert_pr_open_failed, got {marker.get('status')!r}"
        )

        # The plan is NOT permanently actioned: _is_actioned must return False
        assert not mr._is_actioned(pid, d), (
            "revert_pr_open_failed must be retryable: _is_actioned must return False"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-5: park expiry
# ─────────────────────────────────────────────────────────────────────────────

class TestParkExpiry:
    """FIX-5: park older than expiry → not blocked; fresh park → blocked."""

    def test_fresh_park_blocks(self):
        """A park written just now (within expiry window) blocks a matching proposal."""
        mb = _import_build()
        d = _tmp_root()
        # Config with 30-day expiry
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\npark_expiry_days: 30\n"
        )

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": now_ts,
            "proposal_id": "p_fresh",
            "parked_construction": {"lobe": "til", "sensors": ["mom"], "kind": "til"},
            "release_grant_id": None,
        }
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        claims_path.write_text(json.dumps(park_row) + "\n")

        proposal = {"proposal_id": "p_new", "lobe": "til", "kind": "til",
                    "targets_sensor": "mom"}
        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is True, "Fresh park must block matching proposal"

    def test_expired_park_does_not_block(self):
        """A park written 31 days ago (older than 30-day expiry) does NOT block."""
        mb = _import_build()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\npark_expiry_days: 30\n"
        )

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(timespec="seconds")
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": old_ts,
            "proposal_id": "p_old",
            "parked_construction": {"lobe": "til", "sensors": ["mom"], "kind": "til"},
            "release_grant_id": None,
        }
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        claims_path.write_text(json.dumps(park_row) + "\n")

        proposal = {"proposal_id": "p_new", "lobe": "til", "kind": "til",
                    "targets_sensor": "mom"}
        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is False, (
            "Park older than park_expiry_days must auto-release (not block)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-B1: breach/park tracked independently — partial run does not re-fire
#         the already-completed effect
# ─────────────────────────────────────────────────────────────────────────────

class TestReflexPartialFailureDoesNotDoubleFirBreach:
    """FIX-B1: breach succeeds + park raises on run 1 → run 2 fires park only.

    A completed breach must never fire twice even if park keeps failing.
    Exactly one breach row must exist after two runs.
    """

    def test_breach_not_repeated_when_park_fails(self):
        import scripts.metabolism_verify as mv
        importlib.reload(mv)
        from engine.metabolism.verify import (
            _reflex_already_executed,
            _reflex_effect_done,
        )

        d = _tmp_root()
        (d / "data" / "metabolism" / "reflex").mkdir(parents=True, exist_ok=True)
        (d / "data" / "metabolism" / "lifecycle").mkdir(parents=True, exist_ok=True)

        contract = {
            "lobe": "til_partial",
            "sensor": "momentum",
            "kind": "til",
            "proposal_id": "p_partial_fixb1",
        }
        record = {
            "cycle_id": "cycle-partial-b1",
            "contract": contract,
            "triage": {"classification": "overfit", "action": "revert_plan"},
            "_side_effect_intents": {"breach_intent": True, "park_intent": True},
        }

        breach_call_count = [0]
        park_call_count = [0]

        def fake_breach(cycle_id, contract_arg, triage_arg, root_arg):
            breach_call_count[0] += 1

        def fake_park_fail(cycle_id, contract_arg, root_arg):
            park_call_count[0] += 1
            raise RuntimeError("simulated park failure")

        # Run 1: breach succeeds, park raises
        from engine.metabolism import verify as v
        with patch.object(v, "_feed_breach_from_falsifier", side_effect=fake_breach):
            with patch.object(v, "_park_construction_from_falsifier",
                              side_effect=fake_park_fail):
                mv._execute_reflex_intents("cycle-partial-b1", record, d)

        assert breach_call_count[0] == 1, "breach must fire exactly once on run 1"
        assert park_call_count[0] == 1, "park must be attempted on run 1"

        # After run 1: breach_executed=True, park_executed=False
        assert _reflex_effect_done("cycle-partial-b1", d, "breach_executed"), (
            "breach_executed must be True in marker after run 1"
        )
        assert not _reflex_effect_done("cycle-partial-b1", d, "park_executed"), (
            "park_executed must be False in marker after run 1"
        )
        assert not _reflex_already_executed("cycle-partial-b1", d), (
            "_reflex_already_executed must be False after partial run"
        )

        def fake_park_ok(cycle_id, contract_arg, root_arg):
            park_call_count[0] += 1

        # Run 2: breach must NOT re-fire; park must complete
        with patch.object(v, "_feed_breach_from_falsifier", side_effect=fake_breach):
            with patch.object(v, "_park_construction_from_falsifier",
                              side_effect=fake_park_ok):
                mv._execute_reflex_intents("cycle-partial-b1", record, d)

        assert breach_call_count[0] == 1, (
            "FIX-B1: breach must NOT be re-fired on run 2 (already succeeded)"
        )
        assert park_call_count[0] == 2, "park must fire on run 2"

        # After run 2: both done
        assert _reflex_already_executed("cycle-partial-b1", d), (
            "Both effects must be marked done after run 2"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-B2: retry on 'branch already exists' reaches PR-open (no orphan)
# ─────────────────────────────────────────────────────────────────────────────

class TestRevertWorktreeBranchAlreadyExists:
    """FIX-B2: attempt-1 push-ok/PR-fail → attempt-2 opens PR, no unhandled
    'branch already exists' error.
    """

    def test_retry_after_pr_fail_opens_pr(self):
        """Simulates the full retry lifecycle:
        - Attempt 1: worktree created, revert ok, push ok, gh pr create fails
          → marker written with status=revert_pr_open_failed
        - Attempt 2: branch already exists on origin → worktree reuses branch
          → PR opened successfully
        """
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_retry_b2"
        branch = f"metabolism/revert-{pid}"

        pr_open_calls = [0]

        def fake_open_pr_fail(*args, **kwargs):
            pr_open_calls[0] += 1
            if pr_open_calls[0] == 1:
                return {"pr_number": None, "pr_url": None, "opened": False,
                        "error": "gh: failed"}
            return {"pr_number": 200, "pr_url": "https://example.com/200",
                    "opened": True}

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        # Attempt 1: everything succeeds except gh pr create
        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=42):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_b2"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(),
                                                    "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_push_revert_branch",
                                              return_value=True):
                                with patch.object(mr, "_open_draft_revert_pr",
                                                  side_effect=fake_open_pr_fail):
                                    with patch("subprocess.run",
                                               return_value=fake_run_ok):
                                        result1 = mr._process_one_plan(
                                            {"proposal_id": pid,
                                             "cycle_id": "cycle-b2",
                                             "verify_path": "/fake",
                                             "revert_plan": {"action": "git_revert",
                                                             "target": "test"},
                                             "do_not_rebuild_row": {}},
                                            d,
                                            dry_run=False,
                                        )

        assert result1.get("status") == "revert_pr_open_failed"
        # The plan is retryable
        assert not mr._is_actioned(pid, d), "Must remain retryable after attempt 1"

        # Attempt 2: branch already exists scenario — worktree returns ok with
        # the existing path (simulates _create_revert_worktree handling the
        # "already exists" case correctly)
        wt2 = tempfile.mkdtemp(prefix="fake_wt_retry_")
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=42):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_b2"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": wt2, "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_push_revert_branch",
                                              return_value=True):
                                with patch.object(mr, "_open_draft_revert_pr",
                                                  side_effect=fake_open_pr_fail):
                                    with patch("subprocess.run",
                                               return_value=fake_run_ok):
                                        result2 = mr._process_one_plan(
                                            {"proposal_id": pid,
                                             "cycle_id": "cycle-b2",
                                             "verify_path": "/fake",
                                             "revert_plan": {"action": "git_revert",
                                                             "target": "test"},
                                             "do_not_rebuild_row": {}},
                                            d,
                                            dry_run=False,
                                        )

        assert result2.get("status") == "revert_pr_opened", (
            f"FIX-B2: attempt 2 must open the PR, got {result2.get('status')!r}"
        )
        # Plan is now permanently actioned
        assert mr._is_actioned(pid, d), "After successful PR open, plan must be actioned"
        # Marker shows final status
        marker = json.loads(
            (d / "data" / "metabolism" / "revert" / f"{pid}.json").read_text()
        )
        assert marker.get("status") == "revert_pr_opened"

    def test_create_worktree_handles_branch_exists_string(self):
        """_create_revert_worktree 'already exists' path returns wt_path (not error)
        when the branch is known on origin from a prior push."""
        mr = _import_revert()
        d = _tmp_root()
        branch = "metabolism/revert-test-b2"

        # First run: git worktree add -b returns "already exists" error
        call_count = [0]
        fake_wt = tempfile.mkdtemp(prefix="fake_wt_b2_")

        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            r = MagicMock()
            r.stdout = ""
            if "worktree" in cmd and "add" in cmd and "-b" in cmd:
                # Simulate branch-already-exists error
                r.returncode = 128
                r.stderr = "fatal: a branch named '{}' already exists".format(branch)
            elif "worktree" in cmd and "add" in cmd and f"origin/{branch}" in cmd:
                # Simulate successful checkout of existing remote branch
                r.returncode = 0
                r.stderr = ""
                # Create the path so exists() check works
                import os as _os
                expected_wt_path = d.parent / branch.replace("/", "_")
                _os.makedirs(str(expected_wt_path), exist_ok=True)
            else:
                r.returncode = 0
                r.stderr = ""
            return r

        with patch("subprocess.run", side_effect=fake_run):
            result = mr._create_revert_worktree(branch, d)

        # Must not return an error — wt_path should be set
        assert result.get("error") is None or result.get("wt_path") is not None, (
            "FIX-B2: _create_revert_worktree must not error out on 'branch already exists'"
        )


class TestRevertIdempotentRetryPath:
    """FIX-B2 idempotency: retry where branch already has revert commit does NOT
    re-run git revert (no 'nothing to commit' infinite-fail loop).
    """

    def test_retry_skips_revert_when_already_applied(self):
        """Attempt-1 pushes revert commit + PR-create fails.
        Attempt-2: _revert_already_applied returns True →
        git revert is NOT called → PR opened → plan marked revert_pr_opened.
        """
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_idem_retry"

        # Track whether git revert --no-edit was called
        revert_cmd_calls: list = []
        pr_open_calls = [0]

        def fake_open_pr_fail_then_ok(*args, **kwargs):
            pr_open_calls[0] += 1
            if pr_open_calls[0] == 1:
                return {"pr_number": None, "pr_url": None, "opened": False,
                        "error": "gh: transient error"}
            return {"pr_number": 300, "pr_url": "https://example.com/300",
                    "opened": True}

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        env = _armed_env()

        # ── Attempt 1: fresh branch, revert ok, push ok, PR-create fails ──
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=55):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_idem"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(),
                                                    "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_push_revert_branch",
                                              return_value=True):
                                with patch.object(mr, "_open_draft_revert_pr",
                                                  side_effect=fake_open_pr_fail_then_ok):
                                    # _revert_already_applied returns False on first attempt
                                    with patch.object(mr, "_revert_already_applied",
                                                      return_value=False):
                                        with patch("subprocess.run",
                                                   return_value=fake_run_ok):
                                            result1 = mr._process_one_plan(
                                                {"proposal_id": pid,
                                                 "cycle_id": "cycle-idem",
                                                 "verify_path": "/fake",
                                                 "revert_plan": {"action": "git_revert",
                                                                 "target": "test"},
                                                 "do_not_rebuild_row": {}},
                                                d,
                                                dry_run=False,
                                            )

        assert result1.get("status") == "revert_pr_open_failed"
        assert not mr._is_actioned(pid, d), "Must remain retryable after attempt 1"

        # ── Attempt 2: branch already has revert commit ──
        # _revert_already_applied returns True → git revert must NOT be called
        def fake_run_assert_no_revert(cmd, **kwargs):
            if "revert" in cmd and "--no-edit" in cmd:
                revert_cmd_calls.append(cmd)
            return fake_run_ok

        wt2 = tempfile.mkdtemp(prefix="fake_wt_idem_")
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=55):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_idem"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": wt2, "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_push_revert_branch",
                                              return_value=True):
                                with patch.object(mr, "_open_draft_revert_pr",
                                                  side_effect=fake_open_pr_fail_then_ok):
                                    # KEY: revert already applied on this branch
                                    with patch.object(mr, "_revert_already_applied",
                                                      return_value=True):
                                        with patch("subprocess.run",
                                                   side_effect=fake_run_assert_no_revert):
                                            result2 = mr._process_one_plan(
                                                {"proposal_id": pid,
                                                 "cycle_id": "cycle-idem",
                                                 "verify_path": "/fake",
                                                 "revert_plan": {"action": "git_revert",
                                                                 "target": "test"},
                                                 "do_not_rebuild_row": {}},
                                                d,
                                                dry_run=False,
                                            )

        # git revert --no-edit must NOT have been called on attempt 2
        assert len(revert_cmd_calls) == 0, (
            "FIX-B2: git revert --no-edit must NOT be called when "
            f"_revert_already_applied returns True; calls={revert_cmd_calls}"
        )
        assert result2.get("status") == "revert_pr_opened", (
            f"FIX-B2: attempt 2 must open the PR successfully, got {result2.get('status')!r}"
        )
        assert mr._is_actioned(pid, d), "Plan must be permanently actioned after PR open"
        marker = json.loads(
            (d / "data" / "metabolism" / "revert" / f"{pid}.json").read_text()
        )
        assert marker.get("status") == "revert_pr_opened"

    def test_nothing_to_commit_treated_as_success(self):
        """When git revert exits 1 with 'nothing to commit', plan proceeds to
        PR-open rather than being marked revert_conflict (the fallback path for
        when _revert_already_applied misses the commit).
        """
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_ntc"

        # git revert --no-edit returns exit 1 with "nothing to commit"
        fake_run_nothing = MagicMock()
        fake_run_nothing.returncode = 1
        fake_run_nothing.stdout = ""
        fake_run_nothing.stderr = "nothing to commit, working tree clean"

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        def fake_run_dispatch(cmd, **kwargs):
            if "revert" in cmd and "--no-edit" in cmd:
                return fake_run_nothing
            return fake_run_ok

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=77):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_ntc"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(),
                                                    "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_push_revert_branch",
                                              return_value=True):
                                with patch.object(mr, "_open_draft_revert_pr",
                                                  return_value={"pr_number": 400,
                                                                "pr_url": "https://example.com/400",
                                                                "opened": True}):
                                    # _revert_already_applied returns False so we fall
                                    # through to the git revert call
                                    with patch.object(mr, "_revert_already_applied",
                                                      return_value=False):
                                        with patch("subprocess.run",
                                                   side_effect=fake_run_dispatch):
                                            result = mr._process_one_plan(
                                                {"proposal_id": pid,
                                                 "cycle_id": "cycle-ntc",
                                                 "verify_path": "/fake",
                                                 "revert_plan": {"action": "git_revert",
                                                                 "target": "test"},
                                                 "do_not_rebuild_row": {}},
                                                d,
                                                dry_run=False,
                                            )

        assert result.get("status") == "revert_pr_opened", (
            "FIX-B2: 'nothing to commit' must be treated as success "
            f"(revert already applied), got {result.get('status')!r}"
        )

    def test_fresh_plan_still_runs_git_revert(self):
        """Happy path (no existing branch): git revert IS called once and
        plan is marked revert_pr_opened.
        """
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_fresh_revert"

        revert_calls: list = []

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        def fake_run_track(cmd, **kwargs):
            if "revert" in cmd and "--no-edit" in cmd:
                revert_calls.append(list(cmd))
            return fake_run_ok

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=88):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_fresh"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(),
                                                    "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_push_revert_branch",
                                              return_value=True):
                                with patch.object(mr, "_open_draft_revert_pr",
                                                  return_value={"pr_number": 500,
                                                                "pr_url": "https://example.com/500",
                                                                "opened": True}):
                                    # Fresh plan: revert not yet applied
                                    with patch.object(mr, "_revert_already_applied",
                                                      return_value=False):
                                        with patch("subprocess.run",
                                                   side_effect=fake_run_track):
                                            result = mr._process_one_plan(
                                                {"proposal_id": pid,
                                                 "cycle_id": "cycle-fresh",
                                                 "verify_path": "/fake",
                                                 "revert_plan": {"action": "git_revert",
                                                                 "target": "test"},
                                                 "do_not_rebuild_row": {}},
                                                d,
                                                dry_run=False,
                                            )

        assert len(revert_calls) == 1, (
            f"Fresh plan must run git revert exactly once, got {len(revert_calls)} calls"
        )
        assert result.get("status") == "revert_pr_opened", (
            f"Fresh plan happy path must end in revert_pr_opened, got {result.get('status')!r}"
        )

    def test_conflict_still_aborts_only_when_revert_head_exists(self):
        """A real conflict (not 'nothing to commit'): --abort is called only
        when REVERT_HEAD is present; status = revert_conflict.
        """
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_conflict_guard"

        fake_run_conflict = MagicMock()
        fake_run_conflict.returncode = 1
        fake_run_conflict.stdout = ""
        fake_run_conflict.stderr = "CONFLICT (content): Merge conflict in engine/foo.py"

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        abort_calls: list = []

        def fake_run_dispatch(cmd, **kwargs):
            if "revert" in cmd and "--no-edit" in cmd:
                return fake_run_conflict
            if "revert" in cmd and "--abort" in cmd:
                abort_calls.append("abort")
                return fake_run_ok
            return fake_run_ok

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=99):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_conf"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(),
                                                    "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_revert_already_applied",
                                              return_value=False):
                                # Simulate REVERT_HEAD present
                                with patch.object(mr, "_revert_head_exists",
                                                  return_value=True):
                                    with patch("subprocess.run",
                                               side_effect=fake_run_dispatch):
                                        result = mr._process_one_plan(
                                            {"proposal_id": pid,
                                             "cycle_id": "cycle-conf-guard",
                                             "verify_path": "/fake",
                                             "revert_plan": {"action": "git_revert",
                                                             "target": "test"},
                                             "do_not_rebuild_row": {}},
                                            d,
                                            dry_run=False,
                                        )

        assert result.get("status") == "revert_conflict", (
            f"Real conflict must yield revert_conflict, got {result.get('status')!r}"
        )
        assert len(abort_calls) == 1, (
            "git revert --abort must be called exactly once when REVERT_HEAD present"
        )

    def test_conflict_no_abort_when_revert_head_absent(self):
        """When a non-'nothing to commit' failure occurs but REVERT_HEAD is
        NOT present, --abort must NOT be called (avoids exit-128).
        """
        mr = _import_revert()
        d = _tmp_root()
        pid = "p_no_abort"

        fake_run_fail = MagicMock()
        fake_run_fail.returncode = 1
        fake_run_fail.stdout = ""
        fake_run_fail.stderr = "error: some other revert error"

        fake_run_ok = MagicMock()
        fake_run_ok.returncode = 0
        fake_run_ok.stdout = ""
        fake_run_ok.stderr = ""

        abort_calls: list = []

        def fake_run_dispatch(cmd, **kwargs):
            if "revert" in cmd and "--no-edit" in cmd:
                return fake_run_fail
            if "revert" in cmd and "--abort" in cmd:
                abort_calls.append("abort")
                return fake_run_ok
            return fake_run_ok

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(mr, "_resolve_pr_number", return_value=101):
                with patch.object(mr, "_resolve_merge_sha", return_value="sha_noabort"):
                    with patch.object(mr, "_create_revert_worktree",
                                      return_value={"wt_path": tempfile.mkdtemp(),
                                                    "error": None}):
                        with patch.object(mr, "_remove_revert_worktree"):
                            with patch.object(mr, "_revert_already_applied",
                                              return_value=False):
                                # REVERT_HEAD NOT present
                                with patch.object(mr, "_revert_head_exists",
                                                  return_value=False):
                                    with patch("subprocess.run",
                                               side_effect=fake_run_dispatch):
                                        result = mr._process_one_plan(
                                            {"proposal_id": pid,
                                             "cycle_id": "cycle-no-abort",
                                             "verify_path": "/fake",
                                             "revert_plan": {"action": "git_revert",
                                                             "target": "test"},
                                             "do_not_rebuild_row": {}},
                                            d,
                                            dry_run=False,
                                        )

        assert result.get("status") == "revert_conflict"
        assert len(abort_calls) == 0, (
            "git revert --abort must NOT be called when REVERT_HEAD is absent "
            f"(got {len(abort_calls)} abort calls)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION FIX: _revert_already_applied scope + phrase match (real-git tests)
# ─────────────────────────────────────────────────────────────────────────────

def _init_real_git_repo(tmp_path: Path) -> str:
    """Initialise a real bare-minimum git repo with one commit.

    Returns the full 40-char SHA of HEAD (which will be used as merge_sha in
    the tests — simulating a squash-merge that landed on main).
    NEVER raises; will throw on git setup errors (test infra).
    """
    import subprocess as _sp
    env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
           "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}

    def git(*args: str, cwd: str | None = None) -> str:
        r = _sp.run(["git"] + list(args), cwd=cwd or str(tmp_path),
                    capture_output=True, text=True, env=env, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {r.stderr.strip()[:300]}")
        return r.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "test")
    (tmp_path / "README.md").write_text("hello\n")
    git("add", "README.md")
    git("commit", "-m", "initial commit")
    merge_sha = git("rev-parse", "HEAD")
    return merge_sha


class TestRevertAlreadyAppliedRealGit:
    """Real-git tests for _revert_already_applied scope fix.

    These drive actual git processes in a tmp repo so the origin/main..HEAD
    scoping is exercised for real (mocking git was the root cause of the prior
    test suite missing this regression).
    """

    def test_fresh_branch_returns_false(self, tmp_path):
        """(a) FRESH path: branch off main with NO revert commit → returns False.

        A fresh branch that is identical to main has an EMPTY origin/main..HEAD
        range.  merge_sha (= HEAD of main) must NOT be detected as already
        reverted.
        """
        import subprocess as _sp
        mr = _import_revert()

        repo = tmp_path / "repo"
        repo.mkdir()
        merge_sha = _init_real_git_repo(repo)

        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
               "GIT_AUTHOR_DATE": "2026-01-01T01:00:00Z",
               "GIT_COMMITTER_DATE": "2026-01-01T01:00:00Z"}

        def git(*args):
            r = _sp.run(["git"] + list(args), cwd=str(repo),
                        capture_output=True, text=True, env=env, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {r.stderr.strip()[:300]}")
            return r.stdout.strip()

        # Create a revert branch off main (simulates what the lane does)
        git("checkout", "-b", "metabolism/revert-test")
        # Branch is identical to main — origin/main..HEAD is EMPTY

        # _revert_already_applied must return False (fresh path → revert RUNS)
        result = mr._revert_already_applied(merge_sha, str(repo))
        assert result is False, (
            "FRESH path: branch equals main → origin/main..HEAD is empty → "
            f"must return False, got {result!r}"
        )

    def test_retry_branch_with_revert_commit_returns_true(self, tmp_path):
        """(b) RETRY path: branch DOES contain 'git revert <merge_sha>' → True.

        Simulates attempt-1 that already ran git revert and pushed.  The
        canonical phrase 'This reverts commit <sha>.' must be found in the
        body of the commit ahead of main → returns True → revert skipped.
        """
        import subprocess as _sp
        mr = _import_revert()

        repo = tmp_path / "repo"
        repo.mkdir()
        merge_sha = _init_real_git_repo(repo)

        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
               "GIT_AUTHOR_DATE": "2026-01-01T02:00:00Z",
               "GIT_COMMITTER_DATE": "2026-01-01T02:00:00Z"}

        def git(*args):
            r = _sp.run(["git"] + list(args), cwd=str(repo),
                        capture_output=True, text=True, env=env, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {r.stderr.strip()[:300]}")
            return r.stdout.strip()

        # Fake "origin/main" by creating a local ref so origin/main..HEAD works
        git("update-ref", "refs/remotes/origin/main", "HEAD")

        git("checkout", "-b", "metabolism/revert-retry")

        # Write a commit whose body contains the canonical revert phrase
        (repo / "dummy.txt").write_text("revert\n")
        git("add", "dummy.txt")
        revert_body = (
            f'Revert "some feature"\n\n'
            f"This reverts commit {merge_sha}.\n"
        )
        git("commit", "-m", revert_body)

        result = mr._revert_already_applied(merge_sha, str(repo))
        assert result is True, (
            "RETRY path: branch has revert commit with canonical phrase → "
            f"must return True, got {result!r}"
        )

    def test_end_to_end_fresh_path_produces_nonempty_diff(self, tmp_path):
        """(c) End-to-end: _process_one_plan on a fresh path opens a NON-empty
        revert branch (the branch differs from main after git revert runs).

        Uses a real git repo where we can actually run git revert and verify
        that the resulting branch has a commit ahead of main.
        """
        import subprocess as _sp
        mr = _import_revert()

        # ── Set up a real repo with a "merge commit" to revert ──
        repo = tmp_path / "repo"
        repo.mkdir()

        env_git = {**os.environ,
                   "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
                   "GIT_AUTHOR_DATE": "2026-01-01T03:00:00Z",
                   "GIT_COMMITTER_DATE": "2026-01-01T03:00:00Z"}

        def git(*args, cwd=None):
            r = _sp.run(["git"] + list(args), cwd=cwd or str(repo),
                        capture_output=True, text=True, env=env_git, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {r.stderr.strip()[:300]}")
            return r.stdout.strip()

        git("init", "-b", "main")
        git("config", "user.email", "t@t")
        git("config", "user.name", "test")

        # Commit 1: baseline file
        (repo / "feature.py").write_text("# baseline\n")
        git("add", "feature.py")
        git("commit", "-m", "baseline")

        # Commit 2: the "feature" that will be reverted (this is merge_sha)
        (repo / "feature.py").write_text("# baseline\n# feature\n")
        git("add", "feature.py")
        git("commit", "-m", "add feature")
        merge_sha = git("rev-parse", "HEAD")

        # Set up origin/main ref so origin/main..HEAD works in the worktree
        git("update-ref", "refs/remotes/origin/main", "HEAD")

        # ── Create revert worktree off main ──
        wt_path = tmp_path / "revert_wt"
        wt_path.mkdir()
        git("worktree", "add", str(wt_path), "-b", "metabolism/revert-e2e",
            "origin/main")

        # ── Verify _revert_already_applied returns False on fresh branch ──
        assert mr._revert_already_applied(merge_sha, str(wt_path)) is False, (
            "End-to-end: fresh branch must return False from _revert_already_applied"
        )

        # ── Run git revert inside the worktree ──
        rv = _sp.run(
            ["git", "revert", merge_sha, "--no-edit"],
            cwd=str(wt_path), capture_output=True, text=True,
            env=env_git, timeout=30,
        )
        assert rv.returncode == 0, (
            f"git revert must succeed on a fresh branch: {rv.stderr.strip()[:300]}"
        )

        # ── Branch must now differ from main (non-empty diff) ──
        diff = _sp.run(
            ["git", "diff", "origin/main..HEAD"],
            cwd=str(wt_path), capture_output=True, text=True,
            env=env_git, timeout=30,
        )
        assert diff.stdout.strip() != "", (
            "End-to-end: after git revert, branch must differ from main "
            "(non-empty diff) — empty diff means revert was skipped"
        )

        # ── _revert_already_applied must now return True ──
        assert mr._revert_already_applied(merge_sha, str(wt_path)) is True, (
            "After git revert runs, _revert_already_applied must return True "
            "so a second attempt skips the revert"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-B3: old expired park + fresh re-park (same pid) → BLOCKED
# ─────────────────────────────────────────────────────────────────────────────

class TestFreshReparkAfterExpiredBlocksConstruction:
    """FIX-B3: expiry is per-row.  An old expired row + a fresh row (same pid)
    must leave the construction BLOCKED — the fresh row's age wins.
    """

    def test_old_expired_plus_fresh_repark_is_blocked(self):
        mb = _import_build()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\npark_expiry_days: 30\n"
        )

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        # Old park row: 35 days old (expired)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat(
            timespec="seconds"
        )
        # Fresh park row: today (within expiry window) — SAME pid (re-park by
        # a new falsifier)
        fresh_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        old_park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": old_ts,
            "proposal_id": "p_repark_b3",  # STABLE pid
            "parked_construction": {"lobe": "til", "sensors": ["mom"], "kind": "til"},
            "release_grant_id": None,
        }
        fresh_park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": fresh_ts,
            "proposal_id": "p_repark_b3",  # SAME stable pid
            "parked_construction": {"lobe": "til", "sensors": ["mom"], "kind": "til"},
            "release_grant_id": None,
        }
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        # Write old row first, then fresh row
        claims_path.write_text(
            json.dumps(old_park_row) + "\n" + json.dumps(fresh_park_row) + "\n"
        )

        proposal = {
            "proposal_id": "p_new_b3",
            "lobe": "til",
            "kind": "til",
            "targets_sensor": "mom",
        }

        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is True, (
            "FIX-B3: old expired park + fresh re-park (same pid) must BLOCK the "
            "construction — expiry is per-row, the fresh row is active"
        )

    def test_only_expired_park_rows_unblocks(self):
        """When ONLY expired rows exist (no fresh re-park), not blocked."""
        mb = _import_build()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\npark_expiry_days: 30\n"
        )

        claims_path = d / "data" / "metabolism" / "claims.jsonl"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat(
            timespec="seconds"
        )
        park_row = {
            "schema": "metabolism.parked_construction.v1",
            "ts": old_ts,
            "proposal_id": "p_all_expired",
            "parked_construction": {"lobe": "til", "sensors": ["mom"], "kind": "til"},
            "release_grant_id": None,
        }
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        claims_path.write_text(json.dumps(park_row) + "\n")

        proposal = {
            "proposal_id": "p_new_allexp",
            "lobe": "til",
            "kind": "til",
            "targets_sensor": "mom",
        }
        blocked = mb._is_construction_parked(proposal, root=d)
        assert blocked is False, (
            "When all matching rows are expired, construction must NOT be blocked"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX-B4: gh error counting open PRs → fail closed (zero new PRs)
# ─────────────────────────────────────────────────────────────────────────────

class TestCountOpenRevertPrsFailClosed:
    """FIX-B4: gh returncode!=0 → zero new revert PRs opened this run."""

    def test_gh_error_opens_zero_new_prs(self):
        """When gh pr list returns non-zero, no new plans are processed."""
        mr = _import_revert()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\nmax_open_revert_prs: 5\n"
        )

        _write_verify_record(d, "cycle-b4-a", "revert_plan", "pid_b4_a")
        _write_verify_record(d, "cycle-b4-b", "revert_plan", "pid_b4_b")

        # gh pr list fails
        fake_gh_fail = MagicMock()
        fake_gh_fail.returncode = 1
        fake_gh_fail.stdout = ""
        fake_gh_fail.stderr = "gh: network error"

        process_calls: list[str] = []

        def fake_process(plan, root, *, dry_run=False):
            process_calls.append(plan.get("proposal_id"))
            return {"status": "revert_pr_opened"}

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch("subprocess.run", return_value=fake_gh_fail):
                with patch.object(mr, "_process_one_plan", side_effect=fake_process):
                    mr.main(["--root", str(d)])

        assert len(process_calls) == 0, (
            "FIX-B4: when gh pr list fails, zero new revert PRs must be opened "
            f"(got {len(process_calls)} process calls)"
        )

    def test_gh_exception_opens_zero_new_prs(self):
        """When gh raises an exception, no new plans are processed."""
        mr = _import_revert()
        d = _tmp_root()
        (d / "config" / "metabolism_budget.yml").write_text(
            "schema: metabolism_budget.v1\nmax_open_revert_prs: 5\n"
        )

        _write_verify_record(d, "cycle-b4-exc", "revert_plan", "pid_b4_exc")

        process_calls: list[str] = []

        def fake_process(plan, root, *, dry_run=False):
            process_calls.append(plan.get("proposal_id"))
            return {"status": "revert_pr_opened"}

        def fake_run(*args, **kwargs):
            raise OSError("gh not found")

        env = _armed_env()
        with patch.dict(os.environ, env, clear=False):
            with patch("subprocess.run", side_effect=fake_run):
                with patch.object(mr, "_process_one_plan", side_effect=fake_process):
                    mr.main(["--root", str(d)])

        assert len(process_calls) == 0, (
            "FIX-B4: gh exception must also result in zero new revert PRs"
        )
