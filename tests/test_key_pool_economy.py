"""tests/test_key_pool_economy.py — key economy additions from V10.

Covers:
  - enabled_key_ids() parsing (csv -> set, garbage ignored, absent -> None)
  - is_enabled() semantics (all-enabled when None, membership otherwise)
  - discover_present_keys() enabled-set filtering + R-V10-3 empty-filter fallback
  - record_usage_headers() header filter, jsonl append, never-raise on bad path
  - usage_snapshot() 5h/7d windows, headers merge, legacy row
  - llm_auth legacy-skip when disabled; fail-open on import error
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── helpers ───────────────────────────────────────────────────────────────────

def _ts(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds"
    )


def _write_ledger(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "data" / "metabolism" / "key_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _write_usage_ledger(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "data" / "metabolism" / "key_usage.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _read_usage_rows(tmp_path: Path) -> list[dict]:
    p = tmp_path / "data" / "metabolism" / "key_usage.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# ── enabled_key_ids() ─────────────────────────────────────────────────────────

class TestEnabledKeyIds:
    def test_absent_env_returns_none(self, monkeypatch):
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        from engine.neuralweb.key_pool import enabled_key_ids
        assert enabled_key_ids() is None

    def test_empty_env_returns_none(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "")
        from engine.neuralweb.key_pool import enabled_key_ids
        assert enabled_key_ids() is None

    def test_numeric_ids_parsed(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,3")
        from engine.neuralweb.key_pool import enabled_key_ids
        result = enabled_key_ids()
        assert result == {"claude_code_oauth_1", "claude_code_oauth_3"}

    def test_legacy_and_numeric(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "legacy,2")
        from engine.neuralweb.key_pool import enabled_key_ids
        result = enabled_key_ids()
        assert result == {"legacy", "claude_code_oauth_2"}

    def test_garbage_tokens_ignored(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,foobar,xyz,2")
        from engine.neuralweb.key_pool import enabled_key_ids
        result = enabled_key_ids()
        assert result == {"claude_code_oauth_1", "claude_code_oauth_2"}

    def test_all_garbage_returns_none(self, monkeypatch):
        # All tokens garbage -> treated as absent -> fail-open -> None
        monkeypatch.setenv("METAB_KEYS_ENABLED", "foo,bar")
        from engine.neuralweb.key_pool import enabled_key_ids
        assert enabled_key_ids() is None

    def test_whitespace_around_tokens(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", " 1 , legacy , 3 ")
        from engine.neuralweb.key_pool import enabled_key_ids
        result = enabled_key_ids()
        assert result == {"claude_code_oauth_1", "legacy", "claude_code_oauth_3"}

    def test_single_token_all_three(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,2,3")
        from engine.neuralweb.key_pool import enabled_key_ids
        result = enabled_key_ids()
        assert result == {
            "claude_code_oauth_1",
            "claude_code_oauth_2",
            "claude_code_oauth_3",
        }


# ── is_enabled() ─────────────────────────────────────────────────────────────

class TestIsEnabled:
    def test_absent_env_all_enabled(self, monkeypatch):
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        from engine.neuralweb.key_pool import is_enabled
        assert is_enabled("claude_code_oauth_1") is True
        assert is_enabled("claude_code_oauth_2") is True
        assert is_enabled("legacy") is True

    def test_key_in_set_is_enabled(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,3")
        from engine.neuralweb.key_pool import is_enabled
        assert is_enabled("claude_code_oauth_1") is True
        assert is_enabled("claude_code_oauth_3") is True

    def test_key_not_in_set_is_disabled(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,3")
        from engine.neuralweb.key_pool import is_enabled
        assert is_enabled("claude_code_oauth_2") is False
        assert is_enabled("legacy") is False

    def test_legacy_enabled(self, monkeypatch):
        monkeypatch.setenv("METAB_KEYS_ENABLED", "legacy")
        from engine.neuralweb.key_pool import is_enabled
        assert is_enabled("legacy") is True
        assert is_enabled("claude_code_oauth_1") is False


# ── discover_present_keys() with filtering ────────────────────────────────────

class TestDiscoverPresentKeysFiltering:
    def _patch_present(self, monkeypatch, present_ids: list[str]):
        """Patch _get_capability_row to report the given ids as present."""
        def _fake_row(cap_id, root=None):
            if cap_id in present_ids:
                return {"secret_ref": f"FAKE_{cap_id.upper()}", "kill_state": "active"}
            return None

        monkeypatch.setattr(
            "engine.neuralweb.key_pool._get_capability_row", _fake_row
        )
        for cap_id in present_ids:
            monkeypatch.setenv(f"FAKE_{cap_id.upper()}", "tok")

    def test_filter_to_enabled_subset(self, monkeypatch):
        self._patch_present(monkeypatch, ["claude_code_oauth_1", "claude_code_oauth_2"])
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1")
        from engine.neuralweb.key_pool import discover_present_keys
        result = discover_present_keys()
        assert result == ["claude_code_oauth_1"]

    def test_all_enabled_when_env_absent(self, monkeypatch):
        self._patch_present(monkeypatch, ["claude_code_oauth_1", "claude_code_oauth_2"])
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        from engine.neuralweb.key_pool import discover_present_keys
        result = discover_present_keys()
        assert "claude_code_oauth_1" in result
        assert "claude_code_oauth_2" in result

    def test_r_v10_3_empty_filter_fallback(self, monkeypatch):
        """R-V10-3: if enabled-set filter yields empty while keys are present, fall back."""
        self._patch_present(monkeypatch, ["claude_code_oauth_1", "claude_code_oauth_2"])
        # Set enabled set to key 3 only — not present
        monkeypatch.setenv("METAB_KEYS_ENABLED", "3")
        from engine.neuralweb.key_pool import discover_present_keys
        result = discover_present_keys()
        # Must return the unfiltered present keys (fallback)
        assert set(result) == {"claude_code_oauth_1", "claude_code_oauth_2"}, (
            f"R-V10-3 fallback failed — got {result}"
        )

    def test_r_v10_3_fallback_logged(self, monkeypatch, caplog):
        """R-V10-3 fallback logs a warning."""
        import logging
        self._patch_present(monkeypatch, ["claude_code_oauth_1"])
        monkeypatch.setenv("METAB_KEYS_ENABLED", "3")  # key 3 not present
        from engine.neuralweb.key_pool import discover_present_keys
        with caplog.at_level(logging.WARNING, logger="engine.neuralweb.key_pool"):
            discover_present_keys()
        assert "R-V10-3" in caplog.text or "falling back" in caplog.text.lower()

    def test_no_present_keys_returns_empty(self, monkeypatch):
        """No keys present -> [] regardless of enabled set."""
        monkeypatch.setattr(
            "engine.neuralweb.key_pool._get_capability_row", lambda cap_id, root=None: None
        )
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,2,3")
        from engine.neuralweb.key_pool import discover_present_keys
        assert discover_present_keys() == []


# ── record_usage_headers() ────────────────────────────────────────────────────

class TestRecordUsageHeaders:
    def test_filters_non_ratelimit_headers(self, tmp_path):
        from engine.neuralweb.key_pool import record_usage_headers
        headers = {
            "content-type": "application/json",
            "anthropic-ratelimit-requests-limit": "50",
            "anthropic-ratelimit-tokens-reset": "2026-07-12T10:00:00Z",
            "x-request-id": "abc123",
        }
        record_usage_headers("claude_code_oauth_1", headers, 200, root=tmp_path)
        rows = _read_usage_rows(tmp_path)
        assert len(rows) == 1
        stored_hdrs = rows[0]["headers"]
        assert "anthropic-ratelimit-requests-limit" in stored_hdrs
        assert "anthropic-ratelimit-tokens-reset" in stored_hdrs
        assert "content-type" not in stored_hdrs
        assert "x-request-id" not in stored_hdrs

    def test_appends_valid_jsonl(self, tmp_path):
        from engine.neuralweb.key_pool import record_usage_headers
        record_usage_headers("claude_code_oauth_2", {"anthropic-ratelimit-foo": "bar"}, 429, root=tmp_path)
        record_usage_headers("legacy", {}, 200, root=tmp_path)
        rows = _read_usage_rows(tmp_path)
        assert len(rows) == 2
        assert rows[0]["key_id"] == "claude_code_oauth_2"
        assert rows[0]["status"] == 429
        assert rows[0]["schema"] == "metabolism.key_usage.v1"
        assert rows[1]["key_id"] == "legacy"

    def test_never_raises_on_unwritable_root(self, tmp_path):
        """Passing a root under /dev/null should not raise."""
        from engine.neuralweb.key_pool import record_usage_headers
        # Use a path that definitely can't be written to
        bad_root = Path("/dev/null/impossible_dir")
        # Must not raise
        record_usage_headers("claude_code_oauth_1", {"anthropic-ratelimit-x": "y"}, 200, root=bad_root)

    def test_empty_headers_writes_row(self, tmp_path):
        from engine.neuralweb.key_pool import record_usage_headers
        record_usage_headers("legacy", {}, 200, root=tmp_path)
        rows = _read_usage_rows(tmp_path)
        assert len(rows) == 1
        assert rows[0]["headers"] == {}

    def test_key_id_stored_correctly(self, tmp_path):
        from engine.neuralweb.key_pool import record_usage_headers
        record_usage_headers("claude_code_oauth_3", {"anthropic-ratelimit-a": "b"}, 200, root=tmp_path)
        rows = _read_usage_rows(tmp_path)
        assert rows[0]["key_id"] == "claude_code_oauth_3"


# ── usage_snapshot() ─────────────────────────────────────────────────────────

class TestUsageSnapshot:
    def _make_session_row(self, key_id: str, offset_sec: int, est_tokens: int, outcome: str = "ok") -> dict:
        return {
            "schema": "metabolism.key_ledger.v1",
            "ts": _ts(offset_sec),
            "key_id": key_id,
            "est_tokens": est_tokens,
            "outcome": outcome,
        }

    def test_5h_window_sum(self, tmp_path, monkeypatch):
        """Tokens within 5h window are aggregated; older ones are not."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        kid = "claude_code_oauth_1"
        rows = [
            self._make_session_row(kid, -3600, 10_000),   # 1h ago → inside 5h
            self._make_session_row(kid, -7200, 5_000),    # 2h ago → inside 5h
            self._make_session_row(kid, -20000, 3_000),   # ~5.5h ago → outside 5h
        ]
        _write_ledger(tmp_path, rows)
        # patch discover_present_keys to return kid
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [kid],
        )
        # patch legacy check
        monkeypatch.setattr(
            "lib.config.secret", lambda name: None
        )
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        row = next((r for r in snap if r["key_id"] == kid), None)
        assert row is not None
        assert row["window_5h_est_tokens"] == 15_000
        assert row["window_5h_sessions"] == 2

    def test_7d_window_sum(self, tmp_path, monkeypatch):
        """Tokens within 7d are aggregated; older tokens are not."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        kid = "claude_code_oauth_2"
        _7d_sec = 7 * 24 * 3600
        rows = [
            self._make_session_row(kid, -1000, 8_000),          # recent → inside 7d
            self._make_session_row(kid, -(_7d_sec - 60), 4_000),  # 7d-1min → inside 7d
            self._make_session_row(kid, -(_7d_sec + 60), 2_000),  # 7d+1min → outside 7d
        ]
        _write_ledger(tmp_path, rows)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [kid],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        row = next((r for r in snap if r["key_id"] == kid), None)
        assert row is not None
        assert row["weekly_est_tokens"] == 12_000
        assert row["weekly_sessions"] == 2

    def test_headers_merged(self, tmp_path, monkeypatch):
        """Latest ratelimit_headers from key_usage.jsonl are merged into snapshot."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        kid = "claude_code_oauth_1"
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [kid],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)
        # Write two usage rows; latest should win
        usage_rows = [
            {"schema": "metabolism.key_usage.v1", "ts": _ts(-3600), "key_id": kid,
             "status": 200, "headers": {"anthropic-ratelimit-requests-limit": "40"}},
            {"schema": "metabolism.key_usage.v1", "ts": _ts(-60), "key_id": kid,
             "status": 200, "headers": {"anthropic-ratelimit-requests-limit": "50"}},
        ]
        _write_usage_ledger(tmp_path, usage_rows)
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        row = next((r for r in snap if r["key_id"] == kid), None)
        assert row is not None
        assert row["ratelimit_headers"].get("anthropic-ratelimit-requests-limit") == "50"
        assert row["headers_ts"] is not None

    def test_legacy_row_present(self, tmp_path, monkeypatch):
        """Snapshot always includes a 'legacy' row."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        legacy = next((r for r in snap if r["key_id"] == "legacy"), None)
        assert legacy is not None
        assert "present" in legacy
        assert "enabled" in legacy

    def test_legacy_present_when_env_set(self, tmp_path, monkeypatch):
        """Legacy row has present=True when CLAUDE_CODE_OAUTH_TOKEN is set."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: "fake-tok" if name == "CLAUDE_CODE_OAUTH_TOKEN" else None)
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        legacy = next((r for r in snap if r["key_id"] == "legacy"), None)
        assert legacy is not None
        assert legacy["present"] is True

    def test_enabled_field_reflects_enabled_set(self, tmp_path, monkeypatch):
        """Snapshot enabled field uses enabled_key_ids()."""
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1")
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: ["claude_code_oauth_1", "claude_code_oauth_2"],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        k1 = next(r for r in snap if r["key_id"] == "claude_code_oauth_1")
        k2 = next(r for r in snap if r["key_id"] == "claude_code_oauth_2")
        assert k1["enabled"] is True
        assert k2["enabled"] is False

    def test_empty_ledger_returns_rows_with_zeros(self, tmp_path, monkeypatch):
        """Snapshot with empty ledgers returns rows with zero counters."""
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: ["claude_code_oauth_1"],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)
        from engine.neuralweb.key_pool import usage_snapshot
        snap = usage_snapshot(root=tmp_path)
        k1 = next(r for r in snap if r["key_id"] == "claude_code_oauth_1")
        assert k1["window_5h_est_tokens"] == 0
        assert k1["weekly_est_tokens"] == 0
        assert k1["window_5h_sessions"] == 0
        assert k1["weekly_sessions"] == 0

    def test_never_raises_on_corrupt_ledger(self, tmp_path, monkeypatch):
        """usage_snapshot does not raise on a corrupt ledger file."""
        (tmp_path / "data" / "metabolism").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "metabolism" / "key_ledger.jsonl").write_text("not json\n{bad}\n")
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)
        monkeypatch.setattr(
            "engine.neuralweb.key_pool.discover_present_keys",
            lambda root=None: [],
        )
        monkeypatch.setattr("lib.config.secret", lambda name: None)
        from engine.neuralweb.key_pool import usage_snapshot
        result = usage_snapshot(root=tmp_path)
        # Should still return rows (with zeros), not raise
        assert isinstance(result, list)


# ── llm_auth legacy-skip when disabled ───────────────────────────────────────

class TestLlmAuthLegacySkip:
    def _fake_anthropic_module(self):
        import types
        mod = types.ModuleType("anthropic")

        class _FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        mod.Anthropic = _FakeClient
        mod.DEFAULT_TIMEOUT = 60.0
        mod.DefaultHttpxClient = _FakeClient
        return mod

    def test_legacy_skipped_when_disabled(self, monkeypatch):
        """Legacy provider is excluded when disabled — POOL-AWARE lanes only.

        The gate is scoped to callers that set oauth_pool_lane (metabolism);
        review NIT-4: shared non-metabolism callers (cortex, whitehouse, …)
        must be provably unaffected even if METAB_KEYS_ENABLED leaks into
        their environment (W2 scope).
        """
        import sys
        monkeypatch.setitem(sys.modules, "anthropic", self._fake_anthropic_module())
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-legacy")
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1")  # only key 1 enabled; "legacy" not in set

        # Patch _oauth_pool_candidates to return no pool keys so only legacy path runs
        from engine import llm_auth
        monkeypatch.setattr(llm_auth, "_oauth_pool_candidates", lambda lane: [])

        cfg = {
            "provider_order": ["oauth"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "oauth_pool_lane": "test-lane",  # pool-aware caller → gate applies
            "opus_model": "claude-opus-4-8",
        }

        with monkeypatch.context() as m:
            m.setattr("lib.config.secret", lambda name: "tok-legacy" if name == "CLAUDE_CODE_OAUTH_TOKEN" else None)
            provs = llm_auth.build_providers(cfg)

        # legacy should be skipped for the pool-aware lane
        assert provs == [], f"Expected empty (legacy disabled), got {provs}"

    def test_legacy_kept_for_non_pool_lanes_even_when_disabled(self, monkeypatch):
        """WITHOUT oauth_pool_lane the gate must NOT apply (cortex/whitehouse
        class callers keep the legacy token regardless of METAB_KEYS_ENABLED)."""
        import sys
        monkeypatch.setitem(sys.modules, "anthropic", self._fake_anthropic_module())
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-legacy")
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1")  # "legacy" not enabled

        from engine import llm_auth
        cfg = {
            "provider_order": ["oauth"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            # NO oauth_pool_lane — shared non-metabolism caller
            "opus_model": "claude-opus-4-8",
        }
        with monkeypatch.context() as m:
            m.setattr("lib.config.secret", lambda name: "tok-legacy" if name == "CLAUDE_CODE_OAUTH_TOKEN" else None)
            provs = llm_auth.build_providers(cfg)

        assert len(provs) == 1 and provs[0]["name"] == "oauth", (
            f"Non-pool lane must keep legacy provider, got {provs}"
        )

    def test_legacy_included_when_enabled(self, monkeypatch):
        """Legacy single-token provider is included when is_enabled('legacy') is True."""
        import sys
        monkeypatch.setitem(sys.modules, "anthropic", self._fake_anthropic_module())
        monkeypatch.setenv("METAB_KEYS_ENABLED", "1,legacy")

        from engine import llm_auth
        monkeypatch.setattr(llm_auth, "_oauth_pool_candidates", lambda lane: [])

        cfg = {
            "provider_order": ["oauth"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "opus_model": "claude-opus-4-8",
        }

        with monkeypatch.context() as m:
            m.setattr("lib.config.secret", lambda name: "tok-legacy" if name == "CLAUDE_CODE_OAUTH_TOKEN" else None)
            provs = llm_auth.build_providers(cfg)

        assert len(provs) == 1
        assert provs[0]["env_var"] == "CLAUDE_CODE_OAUTH_TOKEN"

    def test_legacy_included_when_no_metab_env(self, monkeypatch):
        """Legacy included (fail-open) when METAB_KEYS_ENABLED is absent."""
        import sys
        monkeypatch.setitem(sys.modules, "anthropic", self._fake_anthropic_module())
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)

        from engine import llm_auth
        monkeypatch.setattr(llm_auth, "_oauth_pool_candidates", lambda lane: [])

        cfg = {
            "provider_order": ["oauth"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "opus_model": "claude-opus-4-8",
        }

        with monkeypatch.context() as m:
            m.setattr("lib.config.secret", lambda name: "tok-legacy" if name == "CLAUDE_CODE_OAUTH_TOKEN" else None)
            provs = llm_auth.build_providers(cfg)

        assert len(provs) == 1

    def test_fail_open_on_import_error(self, monkeypatch):
        """If key_pool import fails, legacy is included (fail-open, R-V10-2)."""
        import sys
        monkeypatch.setitem(sys.modules, "anthropic", self._fake_anthropic_module())
        monkeypatch.delenv("METAB_KEYS_ENABLED", raising=False)

        # Poison engine.neuralweb.key_pool to simulate ImportError
        import types
        broken_mod = types.ModuleType("engine.neuralweb.key_pool")

        def _broken_is_enabled(key_id):
            raise ImportError("simulated import failure")

        broken_mod.is_enabled = _broken_is_enabled
        monkeypatch.setitem(sys.modules, "engine.neuralweb.key_pool", broken_mod)

        from engine import llm_auth
        monkeypatch.setattr(llm_auth, "_oauth_pool_candidates", lambda lane: [])

        cfg = {
            "provider_order": ["oauth"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "opus_model": "claude-opus-4-8",
        }

        with monkeypatch.context() as m:
            m.setattr("lib.config.secret", lambda name: "tok-legacy" if name == "CLAUDE_CODE_OAUTH_TOKEN" else None)
            # Must not raise; must include legacy
            provs = llm_auth.build_providers(cfg)

        # Even with broken key_pool, legacy provider must be included (fail-open)
        assert len(provs) == 1
        assert provs[0]["env_var"] == "CLAUDE_CODE_OAUTH_TOKEN"
