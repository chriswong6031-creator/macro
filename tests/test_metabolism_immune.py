"""tests/test_metabolism_immune.py — Hermetic tests for Metabolism V8 IMMUNE lane.

COVERAGE:
  1.  classify_red: known class matches by substring in check name.
  2.  classify_red: unknown class returns None.
  3.  classify_red: case-insensitive match.
  4.  Claim dedup: live claim present → skip (no heal attempted).
  5.  Claim expiry: PR state CLOSED → claim not live.
  6.  Claim expiry: PR state MERGED → claim not live.
  7.  Unknown red → insight row emitted, no heal attempted.
  8.  Paused → auto-merge not attempted (sensing allowed).
  9.  Auto-merge blocked: class not allowlisted.
  10. Auto-merge blocked: daily cap exhausted.
  11. Auto-merge blocked: CI not green at fresh SHA.
  12. Lane-health: dead-cron detector fires on planted fixture.
  13. Lane-health: queue-stuck detector fires on planted fixture.
  14. Lane-health: runner-offline detector fires on planted fixture.
  15. Lane-health: key-pool degraded detector fires on planted fixture.
  16. Lane-health: dedup — second call with same journal_key does not fire again same day.
  17. Lane-health: clean fixtures → nothing fires.
  18. write_ci_status writes correct schema (consecutive_failures increments / resets).
  19. append_claim and live_claims round-trip.
  20. increment_automerge_count is journal-durable (persists to file).

All tests HERMETIC — no network, no git, no subprocess except where explicitly mocked.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    d = Path(tempfile.mkdtemp(prefix="test_immune_"))
    (d / "data" / "metabolism" / "immune").mkdir(parents=True)
    (d / "data" / "metabolism").mkdir(parents=True, exist_ok=True)
    (d / "config").mkdir(parents=True)
    return d


_MINIMAL_REGISTRY = {
    "recipes": [
        {
            "check_name_pattern": "blocklist-drift",
            "detector": "python3 scripts/check_blocklist_drift.py",
            "heal_cmd": "python3 scripts/compile_loop_blocklists.py",
            "auto_merge_allowed": True,
        },
        {
            "check_name_pattern": "grader-manifest",
            "detector": "python3 scripts/check_grader_manifest.py",
            "heal_cmd": "python3 scripts/check_grader_manifest.py --regen",
            "auto_merge_allowed": False,
        },
        {
            "check_name_pattern": "house-law-docs",
            "detector": "python3 scripts/check_house_law_registry.py",
            "heal_cmd": "python3 scripts/check_house_law_registry.py --emit-docs",
            "auto_merge_allowed": True,
        },
        {
            "check_name_pattern": "template-site-sync",
            "detector": "python -m scripts.check_template_site_sync",
            "heal_cmd": "python -m scripts.check_template_site_sync --fix",
            "auto_merge_allowed": True,
        },
    ],
    "lane_health": {
        "queue_stuck_min": 40,
        "immune_max_automerge_per_day": 2,
        "runner_offline_threshold_days": 0,
        "key_pool_degraded_fraction": 0.5,
        "dead_cron_conclusions": ["cancelled", "timed_out"],
    },
    "cooldown": {
        "dead_cron_journal_key": "immune.lane_health.dead_cron",
        "queue_stuck_journal_key": "immune.lane_health.queue_stuck",
        "runner_offline_journal_key": "immune.lane_health.runner_offline",
        "key_pool_degraded_journal_key": "immune.lane_health.key_pool_degraded",
    },
}


# ── Imports ────────────────────────────────────────────────────────────────────

from engine.metabolism.immune import (
    classify_red,
    append_claim,
    live_claims,
    has_live_claim_for_class,
    check_dead_cron,
    check_queue_stuck,
    check_runner_offline,
    check_key_pool_degraded,
    has_fired_today,
    mark_fired_today,
    get_automerge_count_today,
    increment_automerge_count,
)


# ── 1. classify_red: known class ───────────────────────────────────────────────

def test_classify_known_exact():
    result = classify_red("blocklist-drift", _MINIMAL_REGISTRY)
    assert result is not None
    assert result["red_class"] == "blocklist-drift"
    assert result["auto_merge_allowed"] is True


def test_classify_known_substring():
    """Pattern match is a substring — 'grader-manifest (Metabolism F1)' should match."""
    result = classify_red("check grader-manifest (Metabolism F1)", _MINIMAL_REGISTRY)
    assert result is not None
    assert result["red_class"] == "grader-manifest"
    assert result["auto_merge_allowed"] is False


def test_classify_known_case_insensitive():
    """Match is case-insensitive."""
    result = classify_red("BLOCKLIST-DRIFT check failed", _MINIMAL_REGISTRY)
    assert result is not None
    assert result["red_class"] == "blocklist-drift"


# ── 2. classify_red: unknown class ────────────────────────────────────────────

def test_classify_unknown_returns_none():
    result = classify_red("some-random-ci-check", _MINIMAL_REGISTRY)
    assert result is None


def test_classify_empty_check_name():
    result = classify_red("", _MINIMAL_REGISTRY)
    assert result is None


def test_classify_empty_registry():
    result = classify_red("blocklist-drift", {})
    assert result is None


# ── 3. Claims round-trip ──────────────────────────────────────────────────────

def test_append_and_live_claims():
    root = _tmp_root()
    claim = {"red_class": "blocklist-drift", "check_name": "blocklist-drift", "main_sha": "abc123", "pr_number": 42}
    ok = append_claim(claim, root=root)
    assert ok is True

    # PR is open → claim is live
    def gh_open(pr_num):
        return "OPEN"

    live = live_claims(root=root, gh_pr_state_fn=gh_open)
    assert len(live) == 1
    assert live[0]["red_class"] == "blocklist-drift"
    assert live[0]["pr_number"] == 42


def test_claim_dedup_live_claim_blocks_heal():
    """has_live_claim_for_class returns True when PR is open — caller must skip."""
    root = _tmp_root()
    append_claim({"red_class": "blocklist-drift", "check_name": "blocklist-drift", "main_sha": "abc", "pr_number": 55}, root=root)

    has = has_live_claim_for_class("blocklist-drift", root=root, gh_pr_state_fn=lambda n: "OPEN")
    assert has is True


# ── 4. Claim expiry on closed PR ─────────────────────────────────────────────

def test_claim_expires_closed_pr():
    root = _tmp_root()
    append_claim({"red_class": "blocklist-drift", "check_name": "bc", "main_sha": "abc", "pr_number": 10}, root=root)

    live = live_claims(root=root, gh_pr_state_fn=lambda n: "CLOSED")
    assert len(live) == 0

    has = has_live_claim_for_class("blocklist-drift", root=root, gh_pr_state_fn=lambda n: "CLOSED")
    assert has is False


def test_claim_expires_merged_pr():
    root = _tmp_root()
    append_claim({"red_class": "house-law-docs", "check_name": "hld", "main_sha": "def", "pr_number": 20}, root=root)

    live = live_claims(root=root, gh_pr_state_fn=lambda n: "MERGED")
    assert len(live) == 0


# ── 5. Unknown red → insight only ────────────────────────────────────────────

def test_unknown_red_no_class_match():
    """Classify returns None for unknown red — caller emits insight, no heal."""
    check_name = "ci/build-something-completely-custom"
    result = classify_red(check_name, _MINIMAL_REGISTRY)
    assert result is None
    # No heal_cmd present — the caller (scripts/metabolism_immune.py) emits an insight.
    # Here we just verify classify returns None (insight emission is the script's concern).


# ── 6. Paused → no merge ──────────────────────────────────────────────────────

def test_paused_no_merge():
    """When AUTONOMY_PAUSED is not 'false', _attempt_automerge skips merging."""
    from scripts.metabolism_immune import _attempt_automerge

    root = _tmp_root()
    recipe = _MINIMAL_REGISTRY["recipes"][0]  # blocklist-drift, auto_merge_allowed=True
    immune_cfg = _MINIMAL_REGISTRY

    with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}):
        result = _attempt_automerge(
            pr_number=99,
            red_class="blocklist-drift",
            recipe=recipe,
            immune_cfg=immune_cfg,
            root=root,
            dry_run=False,
        )

    assert result["merged"] is False
    assert result["skip_reason"] == "paused"


# ── 7. Auto-merge blocked: class not allowlisted ──────────────────────────────

def test_automerge_blocked_not_allowlisted():
    from scripts.metabolism_immune import _attempt_automerge

    root = _tmp_root()
    recipe = _MINIMAL_REGISTRY["recipes"][1]  # grader-manifest, auto_merge_allowed=False
    immune_cfg = _MINIMAL_REGISTRY

    with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}):
        result = _attempt_automerge(
            pr_number=88,
            red_class="grader-manifest",
            recipe=recipe,
            immune_cfg=immune_cfg,
            root=root,
            dry_run=False,
        )

    assert result["merged"] is False
    assert "auto_merge not allowed" in (result["skip_reason"] or "")


# ── 8. Auto-merge blocked: daily cap exhausted ────────────────────────────────

def test_automerge_blocked_cap_exhausted():
    from scripts.metabolism_immune import _attempt_automerge

    root = _tmp_root()
    # Exhaust the cap (default 2)
    increment_automerge_count(root=root)
    increment_automerge_count(root=root)

    recipe = _MINIMAL_REGISTRY["recipes"][0]  # blocklist-drift, allowlisted
    immune_cfg = _MINIMAL_REGISTRY

    with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}):
        # Mock CI green to pass that gate
        with patch("scripts.metabolism_immune._pr_ci_green_at_sha", return_value=(True, "abc123")):
            result = _attempt_automerge(
                pr_number=77,
                red_class="blocklist-drift",
                recipe=recipe,
                immune_cfg=immune_cfg,
                root=root,
                dry_run=False,
            )

    assert result["merged"] is False
    assert "daily cap exhausted" in (result["skip_reason"] or "")


# ── 9. Auto-merge blocked: CI not green at fresh SHA ──────────────────────────

def test_automerge_blocked_ci_not_green():
    from scripts.metabolism_immune import _attempt_automerge

    root = _tmp_root()
    recipe = _MINIMAL_REGISTRY["recipes"][0]  # blocklist-drift, allowlisted
    immune_cfg = _MINIMAL_REGISTRY

    with patch.dict(os.environ, {"AUTONOMY_PAUSED": "false"}):
        with patch("scripts.metabolism_immune._pr_ci_green_at_sha", return_value=(False, "abc123")):
            result = _attempt_automerge(
                pr_number=66,
                red_class="blocklist-drift",
                recipe=recipe,
                immune_cfg=immune_cfg,
                root=root,
                dry_run=False,
            )

    assert result["merged"] is False
    assert "CI not green" in (result["skip_reason"] or "")


# ── 10. Lane-health: dead-cron detector ──────────────────────────────────────

def test_lane_health_dead_cron_fires():
    runs = [
        {"name": "nightly-render", "event": "schedule", "conclusion": "cancelled", "status": "completed"},
        {"name": "metabolism-heartbeat", "event": "schedule", "conclusion": "success", "status": "completed"},
    ]
    result = check_dead_cron(runs, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is True
    assert "nightly-render" in result["dead_lanes"]
    assert "metabolism-heartbeat" not in result["dead_lanes"]


def test_lane_health_dead_cron_timed_out():
    runs = [
        {"name": "asia-collect", "event": "schedule", "conclusion": "timed_out", "status": "completed"},
    ]
    result = check_dead_cron(runs, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is True
    assert "asia-collect" in result["dead_lanes"]


def test_lane_health_dead_cron_clean():
    runs = [
        {"name": "daily-data", "event": "schedule", "conclusion": "success", "status": "completed"},
    ]
    result = check_dead_cron(runs, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is False


# ── 11. Lane-health: queue-stuck detector ─��──────────────────────────────────

def test_lane_health_queue_stuck_fires():
    # created_at 60 minutes ago — should fire for threshold=40
    long_ago = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    runs = [
        {"name": "slow-job", "event": "push", "status": "queued", "created_at": long_ago},
    ]
    result = check_queue_stuck(runs, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is True
    assert result["stuck_count"] == 1


def test_lane_health_queue_stuck_not_fires_recent():
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    runs = [
        {"name": "fast-job", "event": "push", "status": "queued", "created_at": recent},
    ]
    result = check_queue_stuck(runs, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is False


def test_lane_health_queue_stuck_ignores_non_queued():
    long_ago = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    runs = [
        {"name": "running-job", "event": "push", "status": "in_progress", "created_at": long_ago},
    ]
    result = check_queue_stuck(runs, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is False


# ── 12. Lane-health: runner-offline detector ─────────────────────────────────

def test_lane_health_runner_offline_fires():
    runners = [
        {"name": "macstudio-1", "status": "offline"},
        {"name": "macstudio-2", "status": "online"},
    ]
    result = check_runner_offline(runners, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is True
    assert "macstudio-1" in result["offline_runners"]
    assert "macstudio-2" not in result["offline_runners"]


def test_lane_health_runner_offline_clean():
    runners = [
        {"name": "macstudio-1", "status": "online"},
    ]
    result = check_runner_offline(runners, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is False


# ── 13. Lane-health: key-pool degradation detector ───────────────────────────

def test_lane_health_key_pool_degraded_fires():
    """3 of 4 keys cooling = 75% > 50% threshold."""
    key_ledger = {
        "keys": [
            {"name": "KEY_1", "cooling": True},
            {"name": "KEY_2", "cooling": True},
            {"name": "KEY_3", "cooling": True},
            {"name": "KEY_4", "cooling": False},
        ]
    }
    result = check_key_pool_degraded(key_ledger, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is True
    assert result["cooling_count"] == 3
    assert result["total_count"] == 4
    # Names are reported, never values
    assert "KEY_1" in result["summary"]
    assert "KEY_4" not in result["summary"] or "KEY_4" not in str(result.get("cooling_names", []))


def test_lane_health_key_pool_not_degraded():
    """1 of 4 keys cooling = 25% < 50% threshold."""
    key_ledger = {
        "keys": [
            {"name": "KEY_1", "cooling": True},
            {"name": "KEY_2", "cooling": False},
            {"name": "KEY_3", "cooling": False},
            {"name": "KEY_4", "cooling": False},
        ]
    }
    result = check_key_pool_degraded(key_ledger, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is False


def test_lane_health_key_pool_exactly_threshold():
    """2 of 4 keys cooling = 50% — exactly at threshold → should fire (>= check)."""
    key_ledger = {
        "keys": [
            {"name": "KEY_1", "cooling": True},
            {"name": "KEY_2", "cooling": True},
            {"name": "KEY_3", "cooling": False},
            {"name": "KEY_4", "cooling": False},
        ]
    }
    result = check_key_pool_degraded(key_ledger, _MINIMAL_REGISTRY["lane_health"])
    assert result["found"] is True  # fraction >= threshold


# ── 14. Lane-health dedup: second call same day ───────────────────────────────

def test_lane_health_dedup_same_day():
    root = _tmp_root()
    key = "immune.lane_health.test_dedup"

    # First call: has not fired
    assert has_fired_today(key, root=root) is False

    # Mark fired
    ok = mark_fired_today(key, root=root)
    assert ok is True

    # Second call same UTC date: already fired
    assert has_fired_today(key, root=root) is True


# ── 15. write_ci_status schema and consecutive_failures ──────────────────────

def test_write_ci_status_green_resets_consecutive():
    from scripts.metabolism_immune import write_ci_status

    root = _tmp_root()
    ok = write_ci_status("abc123", [], root=root, prev_consecutive=5)
    assert ok is True

    p = root / "data" / "metabolism" / "ci_status.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["green"] is True
    assert data["consecutive_failures"] == 0
    assert data["main_sha"] == "abc123"
    assert isinstance(data["red_required"], list)
    assert "ts" in data


def test_write_ci_status_red_increments_consecutive():
    from scripts.metabolism_immune import write_ci_status

    root = _tmp_root()
    red = [{"name": "blocklist-drift", "conclusion": "failure"}]
    ok = write_ci_status("def456", red, root=root, prev_consecutive=2)
    assert ok is True

    p = root / "data" / "metabolism" / "ci_status.json"
    data = json.loads(p.read_text())
    assert data["green"] is False
    assert data["consecutive_failures"] == 3  # prev 2 + 1
    assert len(data["red_required"]) == 1


# ── 16. Automerge counter is journal-durable ─────────────────────────────────

def test_automerge_count_journal_durable():
    root = _tmp_root()

    assert get_automerge_count_today(root=root) == 0
    n1 = increment_automerge_count(root=root)
    assert n1 == 1
    n2 = increment_automerge_count(root=root)
    assert n2 == 2

    # Verify the file actually exists (durable)
    from datetime import datetime, timezone  # noqa: PLC0415
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = root / "data" / "metabolism" / "immune" / f"automerge_count.{today}.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["count"] == 2


# ── 17. Multiple live claims — only matching class blocks ─────────────────────

def test_live_claims_only_matching_class_blocks():
    root = _tmp_root()
    append_claim({"red_class": "house-law-docs", "check_name": "hld", "main_sha": "111", "pr_number": 100}, root=root)
    append_claim({"red_class": "blocklist-drift", "check_name": "bd", "main_sha": "111", "pr_number": 101}, root=root)

    # PR 101 is CLOSED, PR 100 is OPEN
    def state_fn(n):
        return "OPEN" if n == 100 else "CLOSED"

    assert has_live_claim_for_class("house-law-docs", root=root, gh_pr_state_fn=state_fn) is True
    assert has_live_claim_for_class("blocklist-drift", root=root, gh_pr_state_fn=state_fn) is False
    assert has_live_claim_for_class("grader-manifest", root=root, gh_pr_state_fn=state_fn) is False


# ── 18. classify_red NEVER raises on bad input ───────────────────────────────

def test_classify_red_never_raises():
    assert classify_red(None, None) is None  # type: ignore[arg-type]
    assert classify_red("x", None) is None
    assert classify_red(None, {}) is None


# ─��� 19. live_claims conservative when gh unavailable ─────────────────────────

def test_live_claims_conservative_no_gh_fn():
    """When gh_pr_state_fn is None, all claims with pr_number are treated as live."""
    root = _tmp_root()
    append_claim({"red_class": "blocklist-drift", "check_name": "bd", "main_sha": "aaa", "pr_number": 55}, root=root)

    live = live_claims(root=root, gh_pr_state_fn=None)
    assert len(live) == 1  # conservative — assume live
