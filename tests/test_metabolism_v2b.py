"""tests/test_metabolism_v2b.py — Hermetic tests for Metabolism Phase V2-B.

COVERAGE:
  1. key_pool.discover_present_keys:
       - 1 present key → returns that key (works with 1)
       - 0 present keys → honest empty list (no crash)
       - Key with kill_state != active → excluded
  2. window_load / weekly_load math on synthetic ledger.
  3. record_session: appends a row; row contains key_id (not a token value).
  4. mark_cooling / is_cooling: mark → is_cooling True; after reset_hint
     expires → is_cooling False; subsequent ok row clears auth cooling only
     (#2469 F4: window/weekly clear by reset_hint passage, never by ok).
  5. REDLINE: no token value in output.  get_secret_ref() returns env-var
     NAME only.  record_session row does NOT contain the token value.
  6. dispatcher.pick_key:
       - picks lowest-load non-cooling present key
       - skips cooling key
       - all cooling → returns None + emits freeze journal
  7. all-cooling freeze: produces exactly one notify call (dedup guard via
     mock), journal entry written, earliest_reset computed.
  8. schedule table parse: stages respect utc_hours windows.
  9. redline selftest covers new artifacts (planted fake token in
     key_ledger fixture is caught).
 10. is_paused no-op on every new entrypoint (mutation-proof: booby-trap
     the worker so a removed pause gate ERRORS).
 11. metabolism_schedule.yml is in the immutable fence.
 12. check_capability_redline --selftest passes.
 13. check_self_mod_fence covers metabolism_schedule.yml.
 14. check_grader_manifest passes (metabolism_schedule.yml registered).
 15. check_validated_claims: 'validated' never in V2-B user-facing text.
 16. Synapse count >= 349 after new entries.

All tests are HERMETIC (tmp dirs, in-process, no real network).
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

# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_tmp(extra_env: dict | None = None):
    """Return (tmpdir Path, environ-patcher context-manager)."""
    d = Path(tempfile.mkdtemp(prefix="metab_v2b_test_"))
    (d / "config").mkdir()
    (d / "data" / "metabolism").mkdir(parents=True)
    return d


MINIMAL_MANIFEST = {
    "schema": "capability_manifest.v1",
    "capabilities": [
        {
            "capability_id": "claude_code_oauth_1",
            "kind": "llm_oauth",
            "secret_ref": "CLAUDE_CODE_OAUTH_TOKEN_1",
            "allowed_lanes": ["metabolism-dispatch"],
            "allowed_tiers": ["T1"],
            "rotation_state": "active",
            "kill_state": "active",
        },
        {
            "capability_id": "claude_code_oauth_2",
            "kind": "llm_oauth",
            "secret_ref": "CLAUDE_CODE_OAUTH_TOKEN_2",
            "allowed_lanes": ["metabolism-dispatch"],
            "allowed_tiers": ["T1"],
            "rotation_state": "active",
            "kill_state": "active",
        },
        {
            "capability_id": "claude_code_oauth_3",
            "kind": "llm_oauth",
            "secret_ref": "CLAUDE_CODE_OAUTH_TOKEN_3",
            "allowed_lanes": ["metabolism-dispatch"],
            "allowed_tiers": ["T1"],
            "rotation_state": "active",
            "kill_state": "active",
        },
    ],
}


def _write_manifest(d: Path, manifest: dict | None = None) -> None:
    import yaml
    data = manifest or MINIMAL_MANIFEST
    (d / "config" / "capability_manifest.yml").write_text(yaml.dump(data))


def _write_ledger(d: Path, rows: list[dict]) -> None:
    p = d / "data" / "metabolism" / "key_ledger.jsonl"
    with p.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _ts_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _ts_future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


# Reload key_pool fresh for each test (avoids manifest cache contamination)
def _fresh_pool(root: Path):
    """Return the key_pool module with its cache cleared."""
    import engine.neuralweb.key_pool as kp
    # Force-clear the manifest cache (uses the broker's _manifest_cache)
    try:
        import engine.neuralweb.capability_broker as cb
        cb._manifest_cache = None
    except Exception:
        pass
    kp._MANIFEST_REL = "config/capability_manifest.yml"
    return kp


# ── 1. discover_present_keys ─────────────────────────────────────────────────

class TestDiscoverPresentKeys:
    def test_one_key_present_returns_it(self):
        d = _make_tmp()
        _write_manifest(d)
        env = {"CLAUDE_CODE_OAUTH_TOKEN_1": "some-non-empty-value"}
        with patch.dict(os.environ, env, clear=False):
            kp = _fresh_pool(d)
            keys = kp.discover_present_keys(root=d)
        assert keys == ["claude_code_oauth_1"]

    def test_zero_keys_present_returns_empty(self):
        d = _make_tmp()
        _write_manifest(d)
        # Remove all three from env
        safe_env = {k: "" for k in [
            "CLAUDE_CODE_OAUTH_TOKEN_1",
            "CLAUDE_CODE_OAUTH_TOKEN_2",
            "CLAUDE_CODE_OAUTH_TOKEN_3",
        ]}
        with patch.dict(os.environ, safe_env, clear=False):
            kp = _fresh_pool(d)
            keys = kp.discover_present_keys(root=d)
        assert keys == []

    def test_killed_key_excluded(self):
        d = _make_tmp()
        manifest = {
            "schema": "capability_manifest.v1",
            "capabilities": [
                {
                    "capability_id": "claude_code_oauth_1",
                    "kind": "llm_oauth",
                    "secret_ref": "CLAUDE_CODE_OAUTH_TOKEN_1",
                    "allowed_lanes": ["metabolism-dispatch"],
                    "allowed_tiers": ["T1"],
                    "rotation_state": "active",
                    "kill_state": "killed",  # <-- killed
                },
            ],
        }
        _write_manifest(d, manifest)
        env = {"CLAUDE_CODE_OAUTH_TOKEN_1": "some-non-empty-value"}
        with patch.dict(os.environ, env, clear=False):
            kp = _fresh_pool(d)
            keys = kp.discover_present_keys(root=d)
        assert keys == []

    def test_missing_manifest_returns_empty_no_crash(self):
        d = _make_tmp()
        # No manifest written
        kp = _fresh_pool(d)
        keys = kp.discover_present_keys(root=d)
        assert keys == []

    def test_discover_never_returns_token_value(self):
        """REDLINE: discover_present_keys must never return a token value."""
        d = _make_tmp()
        _write_manifest(d)
        secret_value = "super-secret-token-value-xyz-1234"
        env = {"CLAUDE_CODE_OAUTH_TOKEN_1": secret_value}
        with patch.dict(os.environ, env, clear=False):
            kp = _fresh_pool(d)
            keys = kp.discover_present_keys(root=d)
        # The result must contain capability_ids (strings like 'claude_code_oauth_1')
        # and NEVER the actual secret value
        assert secret_value not in keys
        for k in keys:
            assert k != secret_value
            assert "super-secret" not in k

    def test_all_three_present(self):
        d = _make_tmp()
        _write_manifest(d)
        env = {
            "CLAUDE_CODE_OAUTH_TOKEN_1": "tok1",
            "CLAUDE_CODE_OAUTH_TOKEN_2": "tok2",
            "CLAUDE_CODE_OAUTH_TOKEN_3": "tok3",
        }
        with patch.dict(os.environ, env, clear=False):
            kp = _fresh_pool(d)
            keys = kp.discover_present_keys(root=d)
        assert set(keys) == {
            "claude_code_oauth_1",
            "claude_code_oauth_2",
            "claude_code_oauth_3",
        }


# ── 2. window_load / weekly_load math ────────────────────────────────────────

class TestLoadMath:
    def test_window_load_counts_recent_rows(self):
        d = _make_tmp()
        _write_manifest(d)
        # 3 rows within 5h, 1 row older than 5h
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(200),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(300),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            # Older than 5h window (5*3600 = 18000s)
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(20000),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
        ]
        _write_ledger(d, rows)
        kp = _fresh_pool(d)
        assert kp.window_load("claude_code_oauth_1", root=d) == 3

    def test_window_load_excludes_other_keys(self):
        d = _make_tmp()
        _write_manifest(d)
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(200),
             "key_id": "claude_code_oauth_2", "est_tokens": 1000, "outcome": "ok"},
        ]
        _write_ledger(d, rows)
        kp = _fresh_pool(d)
        assert kp.window_load("claude_code_oauth_1", root=d) == 1
        assert kp.window_load("claude_code_oauth_2", root=d) == 1

    def test_weekly_load_counts_7day_rows(self):
        d = _make_tmp()
        _write_manifest(d)
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            # 5 days ago — within weekly window
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(5 * 86400),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            # 8 days ago — outside weekly window
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(8 * 86400),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
        ]
        _write_ledger(d, rows)
        kp = _fresh_pool(d)
        assert kp.weekly_load("claude_code_oauth_1", root=d) == 2

    def test_empty_ledger_returns_zero(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        assert kp.window_load("claude_code_oauth_1", root=d) == 0
        assert kp.weekly_load("claude_code_oauth_1", root=d) == 0

    def test_absent_ledger_returns_zero_no_crash(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        assert kp.window_load("claude_code_oauth_1", root=d) == 0


# ── 3. record_session ─────────────────────────────────────────────────────────

class TestRecordSession:
    def test_record_session_appends_row(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        result = kp.record_session(
            "claude_code_oauth_1", est_tokens=5000, cycle_id="cycle-001",
            stage="sense", outcome="ok", root=d
        )
        assert result is True
        ledger = d / "data" / "metabolism" / "key_ledger.jsonl"
        assert ledger.exists()
        rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row["key_id"] == "claude_code_oauth_1"
        assert row["est_tokens"] == 5000
        assert row["outcome"] == "ok"
        assert row["cycle_id"] == "cycle-001"
        assert row["stage"] == "sense"

    def test_record_session_never_stores_token_value(self):
        """REDLINE: the appended row must not contain a token value."""
        d = _make_tmp()
        _write_manifest(d)
        secret_value = "my-actual-secret-token-xyz"
        env = {"CLAUDE_CODE_OAUTH_TOKEN_1": secret_value}
        with patch.dict(os.environ, env, clear=False):
            kp = _fresh_pool(d)
            kp.record_session("claude_code_oauth_1", est_tokens=100, root=d)

        ledger = d / "data" / "metabolism" / "key_ledger.jsonl"
        content = ledger.read_text()
        assert secret_value not in content, (
            f"Token value found in key_ledger.jsonl — REDLINE VIOLATION\n{content}"
        )

    def test_record_session_appends_idempotently(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        kp.record_session("claude_code_oauth_1", est_tokens=100, root=d)
        kp.record_session("claude_code_oauth_1", est_tokens=200, root=d)
        ledger = d / "data" / "metabolism" / "key_ledger.jsonl"
        rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        assert len(rows) == 2


# ── 4. mark_cooling / is_cooling ─────────────────────────────────────────────

class TestCooling:
    def test_mark_cooling_sets_cooling(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        kp.mark_cooling("claude_code_oauth_1", cool_kind="window", root=d)
        assert kp.is_cooling("claude_code_oauth_1", root=d) is True

    def test_is_cooling_false_when_reset_past(self):
        d = _make_tmp()
        _write_manifest(d)
        # Write a cooling row with a reset_hint in the past
        rows = [{
            "schema": "metabolism.key_ledger.v1",
            "ts": _ts_ago(7300),
            "key_id": "claude_code_oauth_1",
            "est_tokens": 0,
            "outcome": "rate_limited",
            "cool_kind": "window",
            "reset_hint": _ts_ago(100),  # reset_hint is in the PAST
        }]
        _write_ledger(d, rows)
        kp = _fresh_pool(d)
        assert kp.is_cooling("claude_code_oauth_1", root=d) is False

    def test_is_cooling_true_when_reset_future(self):
        d = _make_tmp()
        _write_manifest(d)
        rows = [{
            "schema": "metabolism.key_ledger.v1",
            "ts": _ts_ago(100),
            "key_id": "claude_code_oauth_1",
            "est_tokens": 0,
            "outcome": "rate_limited",
            "cool_kind": "window",
            "reset_hint": _ts_future(3600),  # reset_hint is in the FUTURE
        }]
        _write_ledger(d, rows)
        kp = _fresh_pool(d)
        assert kp.is_cooling("claude_code_oauth_1", root=d) is True

    def test_subsequent_ok_clears_auth_cooling(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        # Mark as auth-cooling first (revoked/expired token)
        kp.mark_cooling("claude_code_oauth_1", cool_kind="auth", root=d)
        # Then record a successful session — proves the operator rotated the
        # secret, so the auth cooling clears (ok ts >= cooling ts)
        kp.record_session("claude_code_oauth_1", outcome="ok", root=d)
        # Should no longer be cooling
        assert kp.is_cooling("claude_code_oauth_1", root=d) is False

    def test_subsequent_ok_does_not_clear_window_cooling(self):
        # #2469 F4: an ok row does NOT restore a 429-exhausted window quota —
        # a window cooling holds until its reset_hint passes.
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        kp.mark_cooling("claude_code_oauth_1", cool_kind="window", root=d)
        kp.record_session("claude_code_oauth_1", outcome="ok", root=d)
        assert kp.is_cooling("claude_code_oauth_1", root=d) is True

    def test_no_cooling_row_returns_false(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        assert kp.is_cooling("claude_code_oauth_1", root=d) is False

    def test_weekly_cooling_kind(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        kp.mark_cooling("claude_code_oauth_1", cool_kind="weekly", root=d)
        assert kp.is_cooling("claude_code_oauth_1", root=d) is True
        # Ledger should have the weekly kind
        ledger = d / "data" / "metabolism" / "key_ledger.jsonl"
        rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        cooling_rows = [r for r in rows if r.get("cool_kind") == "weekly"]
        assert len(cooling_rows) >= 1

    def test_cooling_missing_ledger_returns_false_no_crash(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        # No ledger file → is_cooling must not crash, must return False
        assert kp.is_cooling("claude_code_oauth_1", root=d) is False


# ── 5. REDLINE: get_secret_ref returns name only ──────────────────────────────

class TestRedlineRefNameOnly:
    def test_get_secret_ref_returns_name_not_value(self):
        d = _make_tmp()
        _write_manifest(d)
        secret_value = "my-actual-oauth-token"
        env = {"CLAUDE_CODE_OAUTH_TOKEN_1": secret_value}
        with patch.dict(os.environ, env, clear=False):
            kp = _fresh_pool(d)
            ref = kp.get_secret_ref("claude_code_oauth_1", root=d)
        # Must return the env-var NAME, not the value
        assert ref == "CLAUDE_CODE_OAUTH_TOKEN_1"
        assert ref != secret_value

    def test_get_secret_ref_unknown_capability_returns_none(self):
        d = _make_tmp()
        _write_manifest(d)
        kp = _fresh_pool(d)
        ref = kp.get_secret_ref("nonexistent_cap", root=d)
        assert ref is None


# ── 6. dispatcher.pick_key ────────────────────────────────────────────────────

def _make_dispatch_env(d: Path, present_keys: list[str] | None = None) -> dict:
    """Set up env so the given keys appear present, all others absent."""
    env = {
        "CLAUDE_CODE_OAUTH_TOKEN_1": "",
        "CLAUDE_CODE_OAUTH_TOKEN_2": "",
        "CLAUDE_CODE_OAUTH_TOKEN_3": "",
        "AUTONOMY_PAUSED": "false",  # armed for dispatch tests
    }
    all_caps = {
        "claude_code_oauth_1": "CLAUDE_CODE_OAUTH_TOKEN_1",
        "claude_code_oauth_2": "CLAUDE_CODE_OAUTH_TOKEN_2",
        "claude_code_oauth_3": "CLAUDE_CODE_OAUTH_TOKEN_3",
    }
    for cap_id, ref in all_caps.items():
        if present_keys and cap_id in present_keys:
            env[ref] = "nonempty"
    return env


class TestDispatcher:
    def _dispatch(self, d: Path):
        """Fresh-import the dispatcher with cleared caches."""
        import engine.neuralweb.key_pool as kp
        try:
            import engine.neuralweb.capability_broker as cb
            cb._manifest_cache = None
        except Exception:
            pass
        import scripts.metabolism_dispatch as md
        # Reload to avoid module-level state
        importlib.reload(kp)
        importlib.reload(md)
        return md

    def test_picks_only_present_key(self):
        d = _make_tmp()
        _write_manifest(d)
        env = _make_dispatch_env(d, ["claude_code_oauth_1"])
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        assert chosen == "claude_code_oauth_1"

    def test_picks_lowest_load_key(self):
        d = _make_tmp()
        _write_manifest(d)
        # key_1 has 3 sessions in window; key_2 has 1 — dispatcher must pick key_2
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(200),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(300),
             "key_id": "claude_code_oauth_1", "est_tokens": 1000, "outcome": "ok"},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(400),
             "key_id": "claude_code_oauth_2", "est_tokens": 1000, "outcome": "ok"},
        ]
        _write_ledger(d, rows)
        env = _make_dispatch_env(d, ["claude_code_oauth_1", "claude_code_oauth_2"])
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        assert chosen == "claude_code_oauth_2"

    def test_skips_cooling_key(self):
        d = _make_tmp()
        _write_manifest(d)
        # Mark key_1 as cooling (reset in future)
        rows = [{
            "schema": "metabolism.key_ledger.v1",
            "ts": _ts_ago(100),
            "key_id": "claude_code_oauth_1",
            "est_tokens": 0,
            "outcome": "rate_limited",
            "cool_kind": "window",
            "reset_hint": _ts_future(3600),
        }]
        _write_ledger(d, rows)
        env = _make_dispatch_env(d, ["claude_code_oauth_1", "claude_code_oauth_2"])
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        # Must pick key_2 (key_1 is cooling)
        assert chosen == "claude_code_oauth_2"

    def test_all_cooling_returns_none(self):
        d = _make_tmp()
        _write_manifest(d)
        # Both keys cooling
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 0,
             "outcome": "rate_limited", "cool_kind": "window",
             "reset_hint": _ts_future(3600)},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_2", "est_tokens": 0,
             "outcome": "rate_limited", "cool_kind": "window",
             "reset_hint": _ts_future(7200)},
        ]
        _write_ledger(d, rows)
        env = _make_dispatch_env(d, ["claude_code_oauth_1", "claude_code_oauth_2"])
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        assert chosen is None

    def test_all_cooling_writes_freeze_journal(self):
        d = _make_tmp()
        _write_manifest(d)
        (d / "data" / "metabolism" / "journal").mkdir(parents=True, exist_ok=True)
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 0,
             "outcome": "rate_limited", "cool_kind": "window",
             "reset_hint": _ts_future(3600)},
        ]
        _write_ledger(d, rows)
        env = _make_dispatch_env(d, ["claude_code_oauth_1"])
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            md.pick_key(root=d, notify_on_freeze=False)
        # Check freeze journal was written
        journal_dir = d / "data" / "metabolism" / "journal"
        freeze_files = list(journal_dir.glob("freeze_*.json"))
        assert len(freeze_files) >= 1
        entry = json.loads(freeze_files[0].read_text())
        assert entry["event"] == "all_keys_cooling"
        assert "earliest_reset" in entry

    def test_paused_returns_none(self):
        d = _make_tmp()
        _write_manifest(d)
        env = _make_dispatch_env(d, ["claude_code_oauth_1"])
        env["AUTONOMY_PAUSED"] = "true"  # PAUSED — must be a no-op
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        assert chosen is None

    def test_no_keys_present_returns_none(self):
        d = _make_tmp()
        _write_manifest(d)
        env = _make_dispatch_env(d, [])  # no keys present
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        assert chosen is None

    def test_chosen_key_is_capability_id_not_token_value(self):
        """REDLINE: pick_key must return a capability_id, not a token value."""
        d = _make_tmp()
        _write_manifest(d)
        secret_value = "super-secret-token-must-not-appear-in-output"
        env = _make_dispatch_env(d, ["claude_code_oauth_1"])
        env["CLAUDE_CODE_OAUTH_TOKEN_1"] = secret_value
        with patch.dict(os.environ, env, clear=False):
            md = self._dispatch(d)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        if chosen is not None:
            assert chosen != secret_value
            assert "super-secret" not in chosen


# ── 7. all-cooling freeze notify dedup ────────────────────────────────────────

class TestFreezeNotify:
    def test_freeze_notify_called_once(self):
        """all_cooling_freeze_info triggers exactly one notify (dedup guard)."""
        d = _make_tmp()
        _write_manifest(d)
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 0,
             "outcome": "rate_limited", "cool_kind": "window",
             "reset_hint": _ts_future(3600)},
        ]
        _write_ledger(d, rows)
        env = _make_dispatch_env(d, ["claude_code_oauth_1"])
        notify_calls = []
        with patch.dict(os.environ, env, clear=False):
            import scripts.metabolism_dispatch as md
            importlib.reload(md)
            original_notify = md._notify_freeze
            md._notify_freeze = lambda *a, **kw: notify_calls.append(1)
            md.pick_key(root=d, notify_on_freeze=True)
            md._notify_freeze = original_notify  # restore
        # Exactly one notify call
        assert len(notify_calls) == 1

    def test_earliest_reset_is_minimum(self):
        d = _make_tmp()
        _write_manifest(d)
        rows = [
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_1", "est_tokens": 0,
             "outcome": "rate_limited", "cool_kind": "window",
             "reset_hint": _ts_future(3600)},
            {"schema": "metabolism.key_ledger.v1", "ts": _ts_ago(100),
             "key_id": "claude_code_oauth_2", "est_tokens": 0,
             "outcome": "rate_limited", "cool_kind": "window",
             "reset_hint": _ts_future(7200)},
        ]
        _write_ledger(d, rows)
        kp = _fresh_pool(d)
        freeze = kp.all_cooling_freeze_info(
            ["claude_code_oauth_1", "claude_code_oauth_2"], root=d
        )
        assert freeze["all_cooling"] is True
        earliest = freeze["earliest_reset"]
        # earliest_reset should be closer to +3600, not +7200
        parsed = datetime.fromisoformat(earliest).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        # Should be 3000..5400s in the future (within 1.5x of 3600)
        diff = (parsed - now).total_seconds()
        assert 2000 < diff < 6000, f"earliest_reset offset={diff}s expected ~3600s"


# ── 8. Schedule table parse ────────────────────────────────────────────────────

class TestScheduleParse:
    def _write_schedule(self, d: Path) -> None:
        import yaml
        schedule = {
            "schema": "metabolism_schedule.v1",
            "dispatch_windows": [
                {"id": "slot_a", "utc_hours": [0, 1, 2],
                 "stages": ["organism_state", "agenda"]},
                {"id": "slot_b", "utc_hours": [8, 9, 10],
                 "stages": ["sense", "propose"]},
            ],
        }
        (d / "config" / "metabolism_schedule.yml").write_text(yaml.dump(schedule))

    def test_stage_allowed_in_window(self):
        d = _make_tmp()
        _write_manifest(d)
        self._write_schedule(d)
        import scripts.metabolism_dispatch as md
        importlib.reload(md)
        schedule = md._load_schedule(root=d)
        # Patch datetime.now to be hour=1 (UTC)
        with patch("scripts.metabolism_dispatch.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
            allowed = md._stage_allowed_now("organism_state", schedule)
        assert allowed is True

    def test_stage_not_allowed_outside_window(self):
        d = _make_tmp()
        _write_manifest(d)
        self._write_schedule(d)
        import scripts.metabolism_dispatch as md
        importlib.reload(md)
        schedule = md._load_schedule(root=d)
        # Hour=5, sense is only in slot_b (hours 8-10)
        with patch("scripts.metabolism_dispatch.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 5, 0, 0, tzinfo=timezone.utc)
            allowed = md._stage_allowed_now("sense", schedule)
        assert allowed is False

    def test_unknown_stage_allowed_by_default(self):
        d = _make_tmp()
        _write_manifest(d)
        self._write_schedule(d)
        import scripts.metabolism_dispatch as md
        importlib.reload(md)
        schedule = md._load_schedule(root=d)
        with patch("scripts.metabolism_dispatch.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            allowed = md._stage_allowed_now("unknown_stage", schedule)
        assert allowed is True  # fail-open for unknown stages

    def test_real_schedule_parseable(self):
        """The real config/metabolism_schedule.yml must parse without error."""
        schedule_path = _ROOT / "config" / "metabolism_schedule.yml"
        if not schedule_path.exists():
            pytest.skip("metabolism_schedule.yml not yet present")
        import yaml
        data = yaml.safe_load(schedule_path.read_text())
        assert data.get("schema") == "metabolism_schedule.v1"
        assert "dispatch_windows" in data


# ── 9. Redline selftest covers new artifacts ──────────────────────────────────

class TestRedlineSelftest:
    def test_redline_selftest_passes(self):
        """check_capability_redline --selftest must exit 0."""
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        result = cr.selftest()
        assert result == 0, "check_capability_redline selftest failed"

    def test_planted_token_in_key_ledger_is_caught(self):
        """Planted fake token in key_ledger fixture is caught by SCAN_IF_PRESENT."""
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "config").mkdir()
            (tmp / "engine" / "neuralweb").mkdir(parents=True)
            (tmp / "engine" / "metabolism").mkdir(parents=True)
            (tmp / "scripts").mkdir(parents=True)
            (tmp / "data" / "metabolism").mkdir(parents=True)
            # Stub all SCAN_PATHS as clean
            for rel in cr.SCAN_PATHS:
                p = tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("# clean stub\n")
            # Plant a fake 40-char hex token in key_ledger.jsonl
            fake_tok = "a" * 5 + "1" + "b" * 34
            row = json.dumps({"schema": "metabolism.key_ledger.v1",
                              "key_id": "x", "token_value": fake_tok})
            (tmp / "data" / "metabolism" / "key_ledger.jsonl").write_text(row + "\n")
            findings = cr.scan(root=tmp)
        hex_found = any(f["kind"] == "high_entropy_hex40" for f in findings)
        assert hex_found, (
            "Planted fake token in key_ledger.jsonl was NOT caught — "
            "SCAN_IF_PRESENT may not cover data/metabolism/key_ledger.jsonl"
        )

    def test_clean_key_ledger_passes_redline(self):
        """A clean key_ledger (no token values) must pass redline scan."""
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "config").mkdir()
            (tmp / "engine" / "neuralweb").mkdir(parents=True)
            (tmp / "engine" / "metabolism").mkdir(parents=True)
            (tmp / "scripts").mkdir(parents=True)
            (tmp / "data" / "metabolism").mkdir(parents=True)
            # Stub all SCAN_PATHS as clean
            for rel in cr.SCAN_PATHS:
                p = tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("# clean stub — names only\n")
            # Write a clean key_ledger (cap_id + counts, no token values)
            row = json.dumps({"schema": "metabolism.key_ledger.v1",
                              "key_id": "claude_code_oauth_1",
                              "cycle_id": "cycle-001", "est_tokens": 5000,
                              "outcome": "ok"})
            (tmp / "data" / "metabolism" / "key_ledger.jsonl").write_text(row + "\n")
            findings = cr.scan(root=tmp)
        assert findings == [], f"Clean ledger produced false positives: {findings}"


# ── 10. is_paused no-op on every new entrypoint (mutation-proof) ──────────────

class TestIsPausedNoOp:
    def test_dispatch_is_paused_by_default(self):
        """pick_key must return None when AUTONOMY_PAUSED is not set."""
        d = _make_tmp()
        _write_manifest(d)
        env = {
            "CLAUDE_CODE_OAUTH_TOKEN_1": "nonempty",
            # AUTONOMY_PAUSED not set (unset = paused)
        }
        # Remove AUTONOMY_PAUSED from env entirely
        clean_env = {k: v for k, v in os.environ.items() if k != "AUTONOMY_PAUSED"}
        clean_env.update(env)
        with patch.dict(os.environ, clean_env, clear=True):
            import scripts.metabolism_dispatch as md
            importlib.reload(md)
            chosen = md.pick_key(root=d, notify_on_freeze=False)
        assert chosen is None

    def test_dispatch_booby_trap(self):
        """Mutation-proof: if is_paused() is removed, the worker call below errors."""
        d = _make_tmp()
        _write_manifest(d)
        env = {"CLAUDE_CODE_OAUTH_TOKEN_1": "nonempty",
               "AUTONOMY_PAUSED": "true"}
        with patch.dict(os.environ, env, clear=False):
            import scripts.metabolism_dispatch as md
            importlib.reload(md)
            # Simulate a booby-trapped worker: if pick_key proceeds past is_paused,
            # it would call discover_present_keys; we patch it to raise so we can
            # assert the pause gate fired BEFORE the worker.
            with patch("engine.neuralweb.key_pool.discover_present_keys",
                       side_effect=RuntimeError("booby-trap: pause gate was bypassed")):
                # Should NOT raise — pause gate should fire before the worker
                try:
                    chosen = md.pick_key(root=d, notify_on_freeze=False)
                except RuntimeError:
                    pytest.fail(
                        "pick_key called discover_present_keys before is_paused() check — "
                        "pause gate must fire FIRST"
                    )
        assert chosen is None


# ── 11. metabolism_schedule.yml in immutable fence ────────────────────────────

class TestScheduleImmutableFence:
    def test_schedule_in_self_mod_fence(self):
        """config/metabolism_schedule.yml must be in check_self_mod_fence IMMUTABLE_PATTERNS."""
        import scripts.check_self_mod_fence as smf
        importlib.reload(smf)
        assert "config/metabolism_schedule.yml" in smf.IMMUTABLE_PATTERNS, (
            "config/metabolism_schedule.yml not in IMMUTABLE_PATTERNS — "
            "the loop could modify its own schedule (R-V2-8 violation)"
        )

    def test_loop_pr_touching_schedule_is_blocked(self):
        """A loop-authored PR that touches metabolism_schedule.yml must be blocked."""
        import scripts.check_self_mod_fence as smf
        importlib.reload(smf)
        code, msg = smf.check(
            branch="metabolism/test-branch",
            changed_files=["config/metabolism_schedule.yml"],
        )
        assert code == 1, f"Loop PR touching schedule should be blocked but got: {msg}"

    def test_human_pr_touching_schedule_is_allowed(self):
        """A human PR touching metabolism_schedule.yml must pass the fence."""
        import scripts.check_self_mod_fence as smf
        importlib.reload(smf)
        code, msg = smf.check(
            branch="feature/update-schedule",
            changed_files=["config/metabolism_schedule.yml"],
        )
        assert code == 0, f"Human PR touching schedule should pass but got: {msg}"


# ── 12. check_capability_redline --selftest passes ────────────────────────────

class TestRedlineChecks:
    def test_check_capability_redline_selftest(self):
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        assert cr.selftest() == 0

    def test_key_pool_in_scan_paths(self):
        """engine/neuralweb/key_pool.py must be in SCAN_PATHS."""
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        assert "engine/neuralweb/key_pool.py" in cr.SCAN_PATHS

    def test_dispatch_in_scan_paths(self):
        """scripts/metabolism_dispatch.py must be in SCAN_PATHS."""
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        assert "scripts/metabolism_dispatch.py" in cr.SCAN_PATHS

    def test_key_ledger_in_scan_if_present(self):
        """data/metabolism/key_ledger.jsonl must be in SCAN_IF_PRESENT."""
        import scripts.check_capability_redline as cr
        importlib.reload(cr)
        assert "data/metabolism/key_ledger.jsonl" in cr.SCAN_IF_PRESENT


# ── 13. check_self_mod_fence covers metabolism_schedule.yml ──────────────────
# (already covered in TestScheduleImmutableFence above)


# ── 14. check_grader_manifest passes ─────────────────────────────────────────

class TestGraderManifest:
    def test_grader_manifest_passes(self):
        """check_grader_manifest.py must exit 0 with the updated manifest."""
        import scripts.check_grader_manifest as gm
        importlib.reload(gm)
        result = gm.check(root=_ROOT)
        assert result == 0, (
            "check_grader_manifest failed — metabolism_schedule.yml hash may "
            "have drifted or not been registered"
        )

    def test_schedule_registered_in_grader_manifest(self):
        """config/metabolism_schedule.yml must appear in grader_manifest.yml."""
        import yaml
        manifest_path = _ROOT / "config" / "grader_manifest.yml"
        if not manifest_path.exists():
            pytest.skip("grader_manifest.yml not present")
        data = yaml.safe_load(manifest_path.read_text())
        paths = [f.get("path") for f in data.get("files", [])]
        assert "config/metabolism_schedule.yml" in paths, (
            "config/metabolism_schedule.yml not registered in grader_manifest.yml"
        )


# ── 15. 'validated' never in V2-B user-facing text ───────────────────────────

class TestValidatedBan:
    """'validated' must never appear in user-facing text in new V2-B files."""

    _V2B_FILES = [
        _ROOT / "engine" / "neuralweb" / "key_pool.py",
        _ROOT / "scripts" / "metabolism_dispatch.py",
        _ROOT / "config" / "metabolism_schedule.yml",
    ]

    def test_no_validated_in_v2b_files(self):
        for path in self._V2B_FILES:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            # Case-insensitive: 'validated' (any case) is forbidden in user-facing text
            lower = content.lower()
            assert "validated" not in lower, (
                f"Word 'validated' found in {path.relative_to(_ROOT)} — "
                "this word is CI-enforced banned from user-facing text"
            )


# ── 16. Synapse count >= 349 ──────────────────────────────────────────────────

class TestSynapseCount:
    def test_synapse_count_geq_348(self):
        """synapse.yml must have at least 348 artifacts after V2-B additions.

        Note: metabolism-dispatch-freeze is NOT a separate artifact entry —
        its journal writes go to data/metabolism/journal/ (owned by
        metabolism-journal, with metabolism_dispatch.py as an extra_writer).
        Only metabolism-key-ledger is a new top-level artifact, hence 348.
        """
        import yaml
        synapse_path = _ROOT / "config" / "synapse.yml"
        if not synapse_path.exists():
            pytest.skip("synapse.yml not present")
        data = yaml.safe_load(synapse_path.read_text())
        count = len(data.get("artifacts", {}))
        assert count >= 348, (
            f"Expected >= 348 synapse artifacts, got {count}. "
            "Verify that metabolism-key-ledger was added."
        )

    def test_new_artifacts_registered(self):
        """metabolism-key-ledger must be present; freeze writes go to metabolism-journal."""
        import yaml
        synapse_path = _ROOT / "config" / "synapse.yml"
        if not synapse_path.exists():
            pytest.skip("synapse.yml not present")
        data = yaml.safe_load(synapse_path.read_text())
        artifacts = data.get("artifacts", {})
        assert "metabolism-key-ledger" in artifacts, (
            "metabolism-key-ledger not in synapse.yml"
        )
        # metabolism-dispatch-freeze writes to metabolism-journal/ as an extra_writer
        # Verify metabolism_dispatch.py appears in metabolism-journal's extra_writers
        journal_entry = artifacts.get("metabolism-journal", {})
        extra_writers = journal_entry.get("known_extra_writers", [])
        assert any("metabolism_dispatch" in str(w) for w in extra_writers), (
            "scripts/metabolism_dispatch.py not in metabolism-journal known_extra_writers"
        )


# ===========================================================================
# R-V5-3 — Cooling horizon: weekly vs window/auth clear semantics
# ===========================================================================

class TestCoolingHorizonSemantics:
    """R-V5-3 + #2469 F4: weekly and window coolings must NOT be cleared by a
    later ok row (only reset_hint passage clears them); auth cooling IS cleared
    by a later ok row (operator rotated the secret);
    'launched' rows never clear any cooling."""

    def _make_ledger(self, root: Path, rows: list[dict]) -> None:
        """Write synthetic ledger rows to the key_ledger.jsonl."""
        import json
        p = root / "data" / "metabolism" / "key_ledger.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def _cooling_row(self, key_id: str, cool_kind: str,
                      started_offset_s: float = -10,
                      reset_offset_s: float = 3600) -> dict:
        """Return a cooling ledger row."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        ts = (now + timedelta(seconds=started_offset_s)).isoformat(timespec="seconds")
        reset = (now + timedelta(seconds=reset_offset_s)).isoformat(timespec="seconds")
        return {
            "schema": "metabolism.key_ledger.v1",
            "ts": ts,
            "key_id": key_id,
            "cycle_id": "",
            "stage": "cooling",
            "est_tokens": 0,
            "outcome": "auth_failed" if cool_kind == "auth" else "rate_limited",
            "cool_kind": cool_kind,
            "reset_hint": reset,
        }

    def _session_row(self, key_id: str, outcome: str, offset_s: float = 0) -> dict:
        """Return a session ledger row."""
        from datetime import datetime, timezone, timedelta
        ts = (datetime.now(timezone.utc) + timedelta(seconds=offset_s)
              ).isoformat(timespec="seconds")
        return {
            "schema": "metabolism.key_ledger.v1",
            "ts": ts,
            "key_id": key_id,
            "cycle_id": "test",
            "stage": "build",
            "est_tokens": 0,
            "outcome": outcome,
        }

    def test_weekly_cooling_not_cleared_by_ok_row(self):
        """A 'weekly' cooling must NOT be cleared by a subsequent ok row (R-V5-3)."""
        from engine.neuralweb.key_pool import is_cooling
        d = _make_tmp()
        key_id = "claude_code_oauth_1"
        rows = [
            self._cooling_row(key_id, cool_kind="weekly", started_offset_s=-10,
                               reset_offset_s=7 * 24 * 3600),  # resets in 7 days
            self._session_row(key_id, outcome="ok", offset_s=5),  # ok AFTER cooling
        ]
        self._make_ledger(d, rows)
        # Despite the ok row, weekly cooling must still be active
        assert is_cooling(key_id, root=d) is True, (
            "Weekly cooling must NOT be cleared by a subsequent ok row"
        )

    def test_window_cooling_not_cleared_by_ok_row(self):
        """A 'window' (429) cooling is NOT cleared by a subsequent ok row (#2469 F4).

        A successful call after the 429 does not restore the exhausted quota
        window — the cooling holds until reset_hint passes."""
        from engine.neuralweb.key_pool import is_cooling
        d = _make_tmp()
        key_id = "claude_code_oauth_1"
        rows = [
            self._cooling_row(key_id, cool_kind="window", started_offset_s=-10,
                               reset_offset_s=5 * 3600),  # resets in 5h
            self._session_row(key_id, outcome="ok", offset_s=5),  # ok AFTER cooling
        ]
        self._make_ledger(d, rows)
        # Window cooling persists despite the ok row
        assert is_cooling(key_id, root=d) is True, (
            "Window cooling must NOT be cleared by a subsequent ok row (#2469 F4)"
        )

    def test_auth_cooling_cleared_by_ok_row(self):
        """An 'auth' cooling IS cleared by a subsequent ok row."""
        from engine.neuralweb.key_pool import is_cooling
        d = _make_tmp()
        key_id = "claude_code_oauth_1"
        rows = [
            self._cooling_row(key_id, cool_kind="auth", started_offset_s=-10,
                               reset_offset_s=24 * 3600),  # resets in 24h
            self._session_row(key_id, outcome="ok", offset_s=5),
        ]
        self._make_ledger(d, rows)
        assert is_cooling(key_id, root=d) is False, (
            "Auth cooling must be cleared by a subsequent ok row"
        )

    def test_launched_row_does_not_clear_window_cooling(self):
        """A 'launched' outcome row must NOT clear window cooling."""
        from engine.neuralweb.key_pool import is_cooling
        d = _make_tmp()
        key_id = "claude_code_oauth_1"
        rows = [
            self._cooling_row(key_id, cool_kind="window", started_offset_s=-10,
                               reset_offset_s=5 * 3600),
            self._session_row(key_id, outcome="launched", offset_s=5),  # launched, not ok
        ]
        self._make_ledger(d, rows)
        assert is_cooling(key_id, root=d) is True, (
            "'launched' row must not clear window cooling"
        )

    def test_weekly_cooling_clears_after_reset_hint_passes(self):
        """A weekly cooling whose reset_hint is in the past must be resolved."""
        from engine.neuralweb.key_pool import is_cooling
        d = _make_tmp()
        key_id = "claude_code_oauth_1"
        rows = [
            self._cooling_row(key_id, cool_kind="weekly",
                               started_offset_s=-7 * 24 * 3600 - 10,  # > 7 days ago
                               reset_offset_s=-60),  # reset_hint 60s in the past
        ]
        self._make_ledger(d, rows)
        assert is_cooling(key_id, root=d) is False, (
            "Weekly cooling whose reset_hint has passed must resolve"
        )
