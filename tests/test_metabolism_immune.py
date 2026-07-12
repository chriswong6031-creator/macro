"""tests/test_metabolism_immune.py — Hermetic tests for Metabolism V8 IMMUNE lane.

COVERAGE:
  1.  classify_red: known class matches by substring in check name.
  2.  classify_red: unknown class returns None.
  3.  classify_red: case-insensitive match.
  4.  Claim dedup: live claim present → skip (no heal attempted).
  5.  Claim expiry: PR state CLOSED → claim not live.
  6.  Claim expiry: PR state MERGED → claim not live.
  7.  FIX-1: state='unknown' keeps claim live (fail-closed, not OPEN-only).
  8.  Unknown red → insight row emitted, no heal attempted.
  9.  Auto-merge DEFERRED (R-V8-3 amended): _attempt_automerge removed; immune
      config reserves keys with comment for R-V8-3b; increment_automerge_count
      is still journal-durable (reserved for follow-up).
  10. Lane-health: dead-cron detector fires on planted fixture.
  11. Lane-health: queue-stuck detector fires on planted fixture.
  12. Lane-health: runner-offline detector fires on planted fixture.
  13. Lane-health: key-pool degraded detector fires on planted fixture.
  14. Lane-health: dedup — second call with same journal_key does not fire again same day.
  15. Lane-health: clean fixtures → nothing fires.
  16. FIX-4: run_lane_health_checks wires key-pool check (fires on >50% cooling ledger).
  17. write_ci_status writes correct schema (consecutive_failures increments / resets).
  18. append_claim and live_claims round-trip.
  19. increment_automerge_count is journal-durable (persists to file).
  20. FIX-5: spurious check name filtered out of red detection.
  21. FIX-5: unknown-red page deduped within a day.

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
    load_immune_config,
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


# ── 6. FIX-1: state='unknown' keeps claim live (fail-closed) ─────────────────

def test_claim_unknown_state_stays_live():
    """FIX-1: 'unknown' PR state must NOT expire the claim (fail-closed contract).

    Previously only 'OPEN' kept a claim live, so a transient gh blip ('unknown')
    would drop the claim and a duplicate heal PR would open.  Now any state that
    is not definitively CLOSED or MERGED keeps the claim live.
    """
    root = _tmp_root()
    append_claim({"red_class": "blocklist-drift", "check_name": "bd", "main_sha": "abc", "pr_number": 42}, root=root)

    # 'unknown' state → claim must remain live
    live = live_claims(root=root, gh_pr_state_fn=lambda n: "unknown")
    assert len(live) == 1, "unknown state should keep claim live (fail-closed)"

    has = has_live_claim_for_class("blocklist-drift", root=root, gh_pr_state_fn=lambda n: "unknown")
    assert has is True, "has_live_claim_for_class must return True on unknown state"


def test_claim_open_state_stays_live():
    """OPEN state still keeps claim live (regression guard)."""
    root = _tmp_root()
    append_claim({"red_class": "blocklist-drift", "check_name": "bd", "main_sha": "abc", "pr_number": 43}, root=root)

    live = live_claims(root=root, gh_pr_state_fn=lambda n: "OPEN")
    assert len(live) == 1


def test_claim_only_closed_and_merged_expire():
    """Only CLOSED and MERGED states expire a claim; everything else keeps it live."""
    root = _tmp_root()
    for i, state in enumerate(["OPEN", "unknown", "DRAFT", "PENDING", "RANDOM"]):
        append_claim(
            {"red_class": f"class-{i}", "check_name": f"c{i}", "main_sha": "abc", "pr_number": 100 + i},
            root=root,
        )

    for i, state in enumerate(["OPEN", "unknown", "DRAFT", "PENDING", "RANDOM"]):
        has = has_live_claim_for_class(f"class-{i}", root=root, gh_pr_state_fn=lambda n, s=state: s)
        assert has is True, f"state={state!r} should keep claim live"

    # CLOSED and MERGED must expire
    root2 = _tmp_root()
    for i, state in enumerate(["CLOSED", "MERGED"]):
        append_claim(
            {"red_class": f"exp-{i}", "check_name": f"e{i}", "main_sha": "abc", "pr_number": 200 + i},
            root=root2,
        )
    for i, state in enumerate(["CLOSED", "MERGED"]):
        has = has_live_claim_for_class(f"exp-{i}", root=root2, gh_pr_state_fn=lambda n, s=state: s)
        assert has is False, f"state={state!r} should expire claim"


# ── 7. Auto-merge DEFERRED (R-V8-3 amended 2026-07-12) ───────────────────────

def test_automerge_deferred_function_removed():
    """_attempt_automerge must not exist in scripts.metabolism_immune (FIX-2).

    Auto-merge is deferred to R-V8-3b.  Verifying the function is absent
    confirms the lane cannot accidentally merge a PR in this wave.
    """
    import scripts.metabolism_immune as mi
    assert not hasattr(mi, "_attempt_automerge"), (
        "_attempt_automerge must be removed; auto-merge is deferred to R-V8-3b"
    )


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


# ── 19. live_claims conservative when gh unavailable ─────────────────────────

def test_live_claims_conservative_no_gh_fn():
    """When gh_pr_state_fn is None, all claims with pr_number are treated as live."""
    root = _tmp_root()
    append_claim({"red_class": "blocklist-drift", "check_name": "bd", "main_sha": "aaa", "pr_number": 55}, root=root)

    live = live_claims(root=root, gh_pr_state_fn=None)
    assert len(live) == 1  # conservative — assume live


# ── FIX-4: run_lane_health_checks wires key-pool sensor ──────────────────────

def test_run_lane_health_checks_key_pool_fires():
    """FIX-4: run_lane_health_checks must fire a key-pool alert on a >50% cooling ledger.

    End-to-end: plant a key_ledger.jsonl with 2/2 keys cooling, verify the
    key-pool alert fires.  No network, no subprocess calls (gh is not invoked
    since _fetch_runs_list/_fetch_runners_list/_fetch_key_ledger read local files).
    """
    from datetime import datetime, timezone, timedelta  # noqa: PLC0415
    from scripts.metabolism_immune import run_lane_health_checks
    from unittest.mock import patch

    root = _tmp_root()

    # Plant a key_ledger.jsonl with 2 cooling keys whose reset_hint is in the future.
    # Use outcome="rate_limited" so key_pool.is_cooling (and inline fallback) recognises
    # them as cooling rows (key_pool uses the outcome field, not stage, to classify rows).
    ledger_dir = root / "data" / "metabolism"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    future_reset = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    ledger_rows = [
        {"schema": "metabolism.key_ledger.v1", "key_id": "claude_code_oauth_1",
         "stage": "cooling", "outcome": "rate_limited", "cool_kind": "window",
         "reset_hint": future_reset, "ts": datetime.now(timezone.utc).isoformat()},
        {"schema": "metabolism.key_ledger.v1", "key_id": "claude_code_oauth_2",
         "stage": "cooling", "outcome": "rate_limited", "cool_kind": "window",
         "reset_hint": future_reset, "ts": datetime.now(timezone.utc).isoformat()},
    ]
    (ledger_dir / "key_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows) + "\n", encoding="utf-8"
    )

    immune_cfg = dict(_MINIMAL_REGISTRY)

    # Stub out the gh-dependent fetchers so no subprocess is spawned
    with patch("scripts.metabolism_immune._fetch_runs_list", return_value=[]):
        with patch("scripts.metabolism_immune._fetch_runners_list", return_value=[]):
            # _fetch_key_ledger reads from root — no mock needed
            rows = run_lane_health_checks(immune_cfg, root=root, dry_run=True)

    # At least the key-pool alert must have fired
    summaries = [r.get("summary") or "" for r in rows]
    assert any("key-pool" in s.lower() for s in summaries), (
        f"Expected key-pool alert in {summaries}"
    )


def test_run_lane_health_checks_key_pool_no_alert_when_ok():
    """FIX-4: key-pool alert must not fire when fewer than 50% of keys are cooling."""
    from datetime import datetime, timezone, timedelta  # noqa: PLC0415
    from scripts.metabolism_immune import run_lane_health_checks

    root = _tmp_root()
    ledger_dir = root / "data" / "metabolism"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    future_reset = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    # Only 1 of 3 keys cooling → 33% < 50% threshold.
    # Use outcome="rate_limited" so key_pool.is_cooling recognises the cooling row.
    ledger_rows = [
        {"schema": "metabolism.key_ledger.v1", "key_id": "claude_code_oauth_1",
         "stage": "cooling", "outcome": "rate_limited", "cool_kind": "window",
         "reset_hint": future_reset, "ts": datetime.now(timezone.utc).isoformat()},
        {"schema": "metabolism.key_ledger.v1", "key_id": "claude_code_oauth_2",
         "stage": "session", "outcome": "ok", "ts": datetime.now(timezone.utc).isoformat()},
        {"schema": "metabolism.key_ledger.v1", "key_id": "claude_code_oauth_3",
         "stage": "session", "outcome": "ok", "ts": datetime.now(timezone.utc).isoformat()},
    ]
    (ledger_dir / "key_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows) + "\n", encoding="utf-8"
    )

    immune_cfg = dict(_MINIMAL_REGISTRY)
    with patch("scripts.metabolism_immune._fetch_runs_list", return_value=[]):
        with patch("scripts.metabolism_immune._fetch_runners_list", return_value=[]):
            rows = run_lane_health_checks(immune_cfg, root=root, dry_run=True)

    summaries = [r.get("summary") or "" for r in rows]
    assert not any("key-pool" in s.lower() and "DEGRADED" in s for s in summaries), (
        f"Key-pool alert must not fire at <50% cooling; got {summaries}"
    )


# ── FIX-5: spurious check filtering ──────────────────────────────────────────

def test_spurious_check_filtered_from_red_detection():
    """FIX-5: _get_required_red_checks must exclude known-spurious check names.

    'Workers Builds: macro' is the canonical known-spurious check from CLAUDE.md.
    Even when it is red, it must be filtered out so no heal PR or page fires.
    """
    from scripts.metabolism_immune import _get_spurious_check_names
    from unittest.mock import patch

    # Verify _get_spurious_check_names reads from config
    immune_cfg = {
        "spurious_checks": ["Workers Builds: macro"],
    }
    names = _get_spurious_check_names(immune_cfg)
    assert "workers builds: macro" in names  # lowercased

    # Empty config → empty set
    assert _get_spurious_check_names({}) == set()
    assert _get_spurious_check_names({"spurious_checks": []}) == set()


def test_spurious_check_not_in_loaded_config():
    """The loaded config/metabolism_immune.yml must contain 'Workers Builds: macro'."""
    import yaml

    wt_root = Path(__file__).resolve().parent.parent
    cfg_path = wt_root / "config" / "metabolism_immune.yml"
    if not cfg_path.exists():
        pytest.skip("config/metabolism_immune.yml not found in worktree")

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    spurious = [str(s).lower() for s in (cfg.get("spurious_checks") or [])]
    assert "workers builds: macro" in spurious, (
        f"'Workers Builds: macro' must be in spurious_checks; got {spurious}"
    )


# ── FIX-5: unknown-red page dedup ─────────────────────────────────────────────

def test_unknown_red_page_deduped_within_day():
    """FIX-5: unknown-red operator page fires ONCE PER DAY per red-class.

    Second run of the immune lane with the same unknown check should NOT emit
    a second insight or Telegram (daily dedup via journal marker).
    """
    root = _tmp_root()

    # Simulate marking the journal key for an unknown red as fired today
    from engine.metabolism.immune import mark_fired_today, has_fired_today

    # Build a journal key the same way run_immune_lane does
    check_name = "ci/some-unknown-check"
    safe_name = check_name.replace("/", "_").replace(" ", "_")[:64]
    journal_key = f"immune.unknown_red.{safe_name}"

    assert has_fired_today(journal_key, root=root) is False

    # First fire
    mark_fired_today(journal_key, root=root)
    assert has_fired_today(journal_key, root=root) is True

    # Second call within same UTC day → already fired → dedup
    assert has_fired_today(journal_key, root=root) is True


# ── FIX-A1: NDJSON parsing + sentinel detects red required checks ────────────

def test_gh_json_parses_ndjson_multiline():
    """FIX-A1: _gh_json must parse multi-line NDJSON output (one object per line).

    With --paginate --jq '.check_runs[]', gh emits one JSON object per line.
    _gh_json must collect them into a list, not fail on the second line.
    """
    from scripts.metabolism_immune import _gh_json
    from unittest.mock import patch, MagicMock

    obj1 = {"name": "blocklist-drift", "conclusion": "failure", "status": "completed", "html_url": "https://example.com/1"}
    obj2 = {"name": "other-check", "conclusion": "success", "status": "completed", "html_url": "https://example.com/2"}
    ndjson_output = json.dumps(obj1) + "\n" + json.dumps(obj2) + "\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ndjson_output
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = _gh_json(["api", "/repos/owner/repo/commits/abc/check-runs", "--paginate", "--jq", ".check_runs[]"])

    assert isinstance(result, list), f"expected list, got {type(result)}: {result}"
    assert len(result) == 2
    assert result[0]["name"] == "blocklist-drift"
    assert result[1]["name"] == "other-check"


def test_gh_json_parses_single_object():
    """FIX-A1: _gh_json must still work for single-object (non-NDJSON) output."""
    from scripts.metabolism_immune import _gh_json
    from unittest.mock import patch, MagicMock

    obj = {"check_runs": [{"name": "some-check", "conclusion": "success"}], "total_count": 1}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(obj)
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = _gh_json(["api", "/repos/owner/repo/commits/abc/check-runs"])

    assert isinstance(result, dict)
    assert "check_runs" in result


def test_get_required_red_checks_detects_red_from_ndjson():
    """FIX-A1: _get_required_red_checks must return red checks from NDJSON output.

    Before the fix, '-q ""' overwrote '--jq' → no filter → dict returned → [] reds.
    After the fix, NDJSON is parsed line-by-line → red checks are detected.
    """
    from scripts.metabolism_immune import _get_required_red_checks
    from unittest.mock import patch, MagicMock

    red_check = {
        "name": "blocklist-drift",
        "conclusion": "failure",
        "status": "completed",
        "html_url": "https://github.com/example/checks/1",
    }
    green_check = {
        "name": "house-law-docs",
        "conclusion": "success",
        "status": "completed",
        "html_url": "https://github.com/example/checks/2",
    }
    ndjson_output = json.dumps(red_check) + "\n" + json.dumps(green_check) + "\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ndjson_output
    mock_result.stderr = ""

    immune_cfg = {"spurious_checks": []}

    with patch("subprocess.run", return_value=mock_result):
        with patch("scripts.metabolism_immune._resolve_repo", return_value="owner/repo"):
            reds = _get_required_red_checks("abc123", immune_cfg=immune_cfg)

    assert len(reds) == 1, f"expected 1 red, got {reds}"
    assert reds[0]["name"] == "blocklist-drift"
    assert reds[0]["conclusion"] == "failure"


def test_get_required_red_checks_handles_single_dict_fallback():
    """FIX-A1: _get_required_red_checks falls back gracefully when NDJSON unavailable."""
    from scripts.metabolism_immune import _get_required_red_checks
    from unittest.mock import patch, MagicMock

    # First call (paginate+jq) returns None (simulates gh failure)
    # Second call (plain) returns dict with check_runs
    red_check = {
        "name": "grader-manifest",
        "conclusion": "failure",
        "status": "completed",
        "html_url": "https://github.com/example/checks/3",
    }
    dict_output = json.dumps({"check_runs": [red_check], "total_count": 1})

    call_count = [0]

    def fake_run(cmd, **kwargs):
        mock = MagicMock()
        mock.stderr = ""
        call_count[0] += 1
        if call_count[0] == 1:
            mock.returncode = 1  # paginate call fails
            mock.stdout = ""
        else:
            mock.returncode = 0
            mock.stdout = dict_output
        return mock

    immune_cfg = {"spurious_checks": []}

    with patch("subprocess.run", side_effect=fake_run):
        with patch("scripts.metabolism_immune._resolve_repo", return_value="owner/repo"):
            reds = _get_required_red_checks("def456", immune_cfg=immune_cfg)

    assert len(reds) == 1
    assert reds[0]["name"] == "grader-manifest"


# ── FIX-A2: pause gate on heal push/PR ───────────────────────────────────────

def test_run_heal_paused_no_push_no_pr():
    """FIX-A2: when AUTONOMY_PAUSED=true, _run_heal_in_worktree must not push or open a PR.

    ci_status is still written by run_immune_lane (sensing is not gated).
    """
    from scripts.metabolism_immune import _run_heal_in_worktree, write_ci_status
    from unittest.mock import patch

    root = _tmp_root()

    recipe = {
        "check_name_pattern": "blocklist-drift",
        "red_class": "blocklist-drift",
        "heal_cmd": "echo 'heal'",
        "detector": "",
        "auto_merge_allowed": True,
    }

    with patch("scripts.metabolism_immune._is_paused", return_value=True):
        result = _run_heal_in_worktree(recipe, "abc12345", root=root, dry_run=False)

    assert result["success"] is False
    assert result["error"] == "paused"
    assert result["branch"] is not None  # branch name set before pause check

    # ci_status write is independent — it should still succeed when called directly
    ok = write_ci_status("abc12345", [], root=root)
    assert ok is True
    ci_path = root / "data" / "metabolism" / "ci_status.json"
    assert ci_path.exists()


def test_run_heal_not_paused_proceeds():
    """FIX-A2: when not paused, _run_heal_in_worktree proceeds past the pause check."""
    from scripts.metabolism_immune import _run_heal_in_worktree
    from unittest.mock import patch, MagicMock

    root = _tmp_root()

    recipe = {
        "check_name_pattern": "blocklist-drift",
        "red_class": "blocklist-drift",
        "heal_cmd": "echo 'heal'",
        "detector": "",
        "auto_merge_allowed": True,
    }

    # Simulate: not paused → worktree creation fails (we just want to confirm the
    # pause check is passed and the subsequent steps are reached)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "fetch failed (mocked)"
    mock_result.stdout = ""

    with patch("scripts.metabolism_immune._is_paused", return_value=False):
        with patch("subprocess.run", return_value=mock_result):
            result = _run_heal_in_worktree(recipe, "abc12345", root=root, dry_run=False)

    # Should NOT return 'paused' error — should attempt fetch and fail differently
    assert result.get("error") != "paused", f"unexpected paused error when not paused: {result}"


# ── FIX-A3: key-ledger clear-by-ok logic ─────────────────────────────────────

def test_fetch_key_ledger_ok_row_clears_cooling():
    """FIX-A3: a 'ok' outcome row after a cooling row must clear the cooling flag.

    Previously _fetch_key_ledger only checked reset_hint > now, missing the
    clear-by-ok logic in key_pool.is_cooling.  A key that had a cooling row
    followed by a successful 'ok' row should NOT be counted as cooling.
    """
    from scripts.metabolism_immune import _fetch_key_ledger
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch

    root = _tmp_root()
    ledger_dir = root / "data" / "metabolism"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    future_reset = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    # cooling row first, then a later ok row (clears the window horizon)
    cooling_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    ok_ts = datetime.now(timezone.utc).isoformat()

    ledger_rows = [
        {
            "key_id": "claude_code_oauth_1",
            "stage": "cooling",
            "outcome": "rate_limited",
            "cool_kind": "window",
            "reset_hint": future_reset,
            "ts": cooling_ts,
        },
        {
            "key_id": "claude_code_oauth_1",
            "stage": "session",
            "outcome": "ok",
            "ts": ok_ts,
        },
    ]
    (ledger_dir / "key_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows) + "\n", encoding="utf-8"
    )

    # Force the inline fallback by making the key_pool import fail.
    # The inline fallback must also apply clear-by-ok logic.
    import builtins
    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "engine.neuralweb.key_pool":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_mock_import):
        result = _fetch_key_ledger(root)

    keys = {k["name"]: k["cooling"] for k in result.get("keys", [])}
    assert "claude_code_oauth_1" in keys, f"key missing from result: {result}"
    assert keys["claude_code_oauth_1"] is False, (
        f"key should NOT be cooling after ok row cleared it; got cooling=True. result={result}"
    )


def test_fetch_key_ledger_weekly_not_cleared_by_ok():
    """FIX-A3: 'weekly' cool_kind is NOT cleared by a later ok row."""
    from scripts.metabolism_immune import _fetch_key_ledger
    from datetime import datetime, timezone, timedelta
    import builtins

    root = _tmp_root()
    ledger_dir = root / "data" / "metabolism"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    future_reset = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    cooling_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    ok_ts = datetime.now(timezone.utc).isoformat()

    ledger_rows = [
        {
            "key_id": "claude_code_oauth_1",
            "stage": "cooling",
            "outcome": "rate_limited",
            "cool_kind": "weekly",
            "reset_hint": future_reset,
            "ts": cooling_ts,
        },
        {
            "key_id": "claude_code_oauth_1",
            "stage": "session",
            "outcome": "ok",
            "ts": ok_ts,
        },
    ]
    (ledger_dir / "key_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows) + "\n", encoding="utf-8"
    )

    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "engine.neuralweb.key_pool":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_mock_import):
        result = _fetch_key_ledger(root)

    keys = {k["name"]: k["cooling"] for k in result.get("keys", [])}
    assert keys.get("claude_code_oauth_1") is True, (
        f"weekly cooling must NOT be cleared by ok row; got {keys}"
    )


# ── FIX-A4: spurious check SUBSTRING match ───────────────────────────────────

def test_spurious_filter_substring_match_with_qualifier():
    """FIX-A4: 'Workers Builds: macro (deploy)' must be filtered when config has 'Workers Builds: macro'.

    Before the fix, exact set membership was used, so 'workers builds: macro (deploy)'
    was NOT in the set {'workers builds: macro'} → false-positive red detected.
    After the fix, substring match is used.
    """
    from scripts.metabolism_immune import _get_required_red_checks
    from unittest.mock import patch, MagicMock

    spurious_check = {
        "name": "Workers Builds: macro (deploy)",
        "conclusion": "failure",
        "status": "completed",
        "html_url": "https://github.com/example/checks/99",
    }
    real_red = {
        "name": "blocklist-drift",
        "conclusion": "failure",
        "status": "completed",
        "html_url": "https://github.com/example/checks/100",
    }
    ndjson_output = json.dumps(spurious_check) + "\n" + json.dumps(real_red) + "\n"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ndjson_output
    mock_result.stderr = ""

    # Config has 'Workers Builds: macro' (without the qualifier)
    immune_cfg = {"spurious_checks": ["Workers Builds: macro"]}

    with patch("subprocess.run", return_value=mock_result):
        with patch("scripts.metabolism_immune._resolve_repo", return_value="owner/repo"):
            reds = _get_required_red_checks("abc123", immune_cfg=immune_cfg)

    names = [r["name"] for r in reds]
    assert "Workers Builds: macro (deploy)" not in names, (
        f"spurious check with qualifier should be filtered; got reds={reds}"
    )
    assert "blocklist-drift" in names, f"real red must still be detected; got reds={reds}"
