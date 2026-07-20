"""tests/test_key_pool_mm_state.py — Mastermind bot key-pool HEALTH join (MM federation).

Covers the additive per-key bot-state fields on usage_snapshot() rows:
    mm_cooling, mm_cool_kind, mm_reset_hint, mm_last_outcome, mm_last_ts

Derivation preference (spec):
  (a) fresh (<48h) schema-valid data/mastermind/key_pool_status.json -> use directly
  (b) else reconstruct from data/mastermind/key_events.jsonl tail:
      a key is mm_cooling if its most-recent cooling row is newer than its most
      recent `ok` row AND reset_hint is in the future.

Cases:
  1. status-file present (cooling window key) -> fields from status.
  2. status-file absent + events-derived cooling (window) -> reconstructed.
  3. auth-dead (cool_kind=auth) from both status and events.
  4. stale status file (ts > 48h) -> ignored, falls back to events.
  5. status preferred over events when both present + disagree.
  6. both absent -> all fields default (False / None).
  7. events: cooling row OLDER than a later ok row -> not cooling.
  8. events: cooling row newer than ok but reset_hint in the PAST -> not cooling.
  9. existing fields unchanged shape (additive only).
 10. corrupt / wrong-schema status file -> fail-soft to events.

All fixtures live under tmp_path with the data root monkeypatched via the
`root=` param that key_pool threads through every reader. NEVER writes repo data/.
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

_VALID_SCHEMA = "metabolism.key_ledger.v1"
_STATUS_SCHEMA = "mastermind.key_pool_status.v1"


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
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def _write_mm_events(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "data" / "mastermind" / "key_events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def _write_mm_status(tmp_path: Path, payload: dict | str) -> None:
    p = tmp_path / "data" / "mastermind" / "key_pool_status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload), encoding="utf-8")


def _ledger_row(key_id: str, offset: int = -60, outcome: str = "ok") -> dict:
    return {
        "schema": _VALID_SCHEMA,
        "ts": _ts(offset),
        "key_id": key_id,
        "cycle_id": "test-cycle",
        "stage": "dispatch",
        "est_tokens": 5000,
        "outcome": outcome,
    }


def _mm_ok(key_id: str, offset: int = -60) -> dict:
    return {
        "schema": _VALID_SCHEMA,
        "ts": _ts(offset),
        "key_id": key_id,
        "cycle_id": "mm-cycle",
        "stage": "mm_dispatch",
        "est_tokens": 8000,
        "outcome": "ok",
    }


def _mm_cool(
    key_id: str,
    offset: int = -60,
    cool_kind: str = "window",
    reset_offset: int = 3600,
) -> dict:
    """A Mastermind cooling row. outcome auth_failed for auth, else rate_limited."""
    return {
        "schema": _VALID_SCHEMA,
        "ts": _ts(offset),
        "key_id": key_id,
        "cycle_id": "",
        "stage": "cooling",
        "est_tokens": 0,
        "outcome": "auth_failed" if cool_kind == "auth" else "rate_limited",
        "cool_kind": cool_kind,
        "reset_hint": _ts(reset_offset),
    }


def _status_entry(
    key_id: str,
    cooling: bool = False,
    cool_kind: str | None = None,
    reset_hint: str | None = None,
    last_outcome: str | None = "ok",
    last_ts: str | None = None,
) -> dict:
    return {
        "key_id": key_id,
        "enabled": True,
        "cooling": cooling,
        "cool_kind": cool_kind,
        "reset_hint": reset_hint,
        "last_outcome": last_outcome,
        "last_ts": last_ts or _ts(-30),
    }


def _snapshot(tmp_path: Path) -> dict[str, dict]:
    from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
    rows = usage_snapshot(root=tmp_path)
    return {r["key_id"]: r for r in rows}


# The five additive fields under test.
_MM_STATE_FIELDS = (
    "mm_cooling", "mm_cool_kind", "mm_reset_hint", "mm_last_outcome", "mm_last_ts",
)


# ── 1. status file present (cooling window) → used directly ──────────────────

class TestStatusFilePreferred:
    def test_status_cooling_window(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        reset = _ts(2 * 3600)
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-60),
            "keys": [
                _status_entry(
                    "claude_code_oauth_1", cooling=True, cool_kind="window",
                    reset_hint=reset, last_outcome="rate_limited",
                ),
            ],
        })
        by_key = _snapshot(tmp_path)
        k = by_key["claude_code_oauth_1"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "window"
        assert k["mm_reset_hint"] == reset
        assert k["mm_last_outcome"] == "rate_limited"

    def test_status_not_cooling(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_2")])
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-60),
            "keys": [_status_entry("claude_code_oauth_2", cooling=False)],
        })
        k = _snapshot(tmp_path)["claude_code_oauth_2"]
        assert k["mm_cooling"] is False
        assert k["mm_cool_kind"] is None
        assert k["mm_last_outcome"] == "ok"

    def test_status_keys_absent_from_status_default(self, tmp_path: Path) -> None:
        """A pool key with no entry in the status file gets defaults (not an error)."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-60),
            "keys": [_status_entry("claude_code_oauth_1", cooling=True,
                                   cool_kind="window", reset_hint=_ts(3600))],
        })
        by_key = _snapshot(tmp_path)
        # oauth_3 has no status entry → defaults
        other = by_key["claude_code_oauth_3"]
        assert other["mm_cooling"] is False
        assert other["mm_cool_kind"] is None
        assert other["mm_reset_hint"] is None
        assert other["mm_last_outcome"] is None
        assert other["mm_last_ts"] is None


# ── 2. status absent + events-derived cooling (window) ───────────────────────

class TestEventsDerivedCooling:
    def test_events_window_cooling(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        # ok at -300, then a window cooling at -100 (newer) with reset in future
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_1", -300),
            _mm_cool("claude_code_oauth_1", -100, "window", reset_offset=3600),
        ])
        # deliberately NO status file
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "window"
        assert k["mm_last_outcome"] == "rate_limited"  # latest row overall

    def test_events_weekly_cooling(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_2")])
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_2", -500),
            _mm_cool("claude_code_oauth_2", -100, "weekly", reset_offset=5 * 86400),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_2"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "weekly"

    def test_events_last_outcome_reflects_tail_when_not_cooling(self, tmp_path: Path) -> None:
        """When a later ok clears an earlier cooling, last_outcome tracks the ok."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_3")])
        _write_mm_events(tmp_path, [
            _mm_cool("claude_code_oauth_3", -300, "window", reset_offset=3600),
            _mm_ok("claude_code_oauth_3", -50),  # newer ok → recovered
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_3"]
        assert k["mm_cooling"] is False
        assert k["mm_last_outcome"] == "ok"
        assert k["mm_cool_kind"] is None


# ── 3. auth-dead ─────────────────────────────────────────────────────────────

class TestAuthDead:
    def test_status_auth_dead(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-60),
            "keys": [_status_entry("claude_code_oauth_1", cooling=True,
                                   cool_kind="auth", reset_hint=_ts(24 * 3600),
                                   last_outcome="auth_failed")],
        })
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "auth"
        assert k["mm_last_outcome"] == "auth_failed"

    def test_events_auth_dead(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_2")])
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_2", -400),
            _mm_cool("claude_code_oauth_2", -80, "auth", reset_offset=24 * 3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_2"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "auth"


# ── 4. stale status file falls back to events ────────────────────────────────

class TestStaleStatusFallsBack:
    def test_stale_status_uses_events(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        # Stale status says NOT cooling ...
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-(49 * 3600)),  # 49h old → stale (> 48h cutoff)
            "keys": [_status_entry("claude_code_oauth_1", cooling=False)],
        })
        # ... but the events tail shows a live window cooling.
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_1", -600),
            _mm_cool("claude_code_oauth_1", -120, "window", reset_offset=3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True, "stale status must be ignored; events win"
        assert k["mm_cool_kind"] == "window"

    def test_fresh_status_boundary_just_inside(self, tmp_path: Path) -> None:
        """A status file ~47h old is still fresh and is used over events."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-(47 * 3600)),  # inside 48h → fresh
            "keys": [_status_entry("claude_code_oauth_1", cooling=False,
                                   last_outcome="ok")],
        })
        # events would say cooling, but fresh status (not cooling) wins
        _write_mm_events(tmp_path, [
            _mm_cool("claude_code_oauth_1", -60, "window", reset_offset=3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is False, "fresh status must win over events tail"


# ── 5. status preferred over events when both present + disagree ─────────────

class TestStatusOverEvents:
    def test_status_wins_over_events(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        # Fresh status: cooling weekly
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-30),
            "keys": [_status_entry("claude_code_oauth_1", cooling=True,
                                   cool_kind="weekly", reset_hint=_ts(5 * 86400))],
        })
        # Events: a plain ok (would derive not-cooling)
        _write_mm_events(tmp_path, [_mm_ok("claude_code_oauth_1", -60)])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "weekly"


# ── 6. both absent → all defaults ────────────────────────────────────────────

class TestBothAbsent:
    def test_both_absent_defaults(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        # no status, no mm events
        by_key = _snapshot(tmp_path)
        for row in by_key.values():
            assert row["mm_cooling"] is False
            assert row["mm_cool_kind"] is None
            assert row["mm_reset_hint"] is None
            assert row["mm_last_outcome"] is None
            assert row["mm_last_ts"] is None

    def test_no_ledger_no_status_no_events(self, tmp_path: Path) -> None:
        """Nothing written at all — still returns rows with defaults, never raises."""
        by_key = _snapshot(tmp_path)
        assert by_key, "snapshot should still cover POOL + legacy"
        for row in by_key.values():
            for f in _MM_STATE_FIELDS:
                assert f in row, f"{f} missing from row {row['key_id']}"
            assert row["mm_cooling"] is False


# ── 7 & 8. events reconstruction edges ───────────────────────────────────────

class TestEventsEdges:
    def test_cooling_older_than_ok_not_cooling(self, tmp_path: Path) -> None:
        """Cooling row OLDER than the latest ok row → not cooling (rule)."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [
            _mm_cool("claude_code_oauth_1", -200, "window", reset_offset=3600),
            _mm_ok("claude_code_oauth_1", -100),  # newer → not cooling
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is False

    def test_cooling_newer_but_reset_in_past_not_cooling(self, tmp_path: Path) -> None:
        """Cooling newer than ok but reset_hint already elapsed → not cooling."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_1", -400),
            _mm_cool("claude_code_oauth_1", -100, "window", reset_offset=-60),  # past
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is False
        # last_outcome still reflects the latest row (the expired cooling)
        assert k["mm_last_outcome"] == "rate_limited"

    def test_no_ok_row_cooling_counts(self, tmp_path: Path) -> None:
        """A cooling row with no prior ok row still counts as cooling."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_5")])
        _write_mm_events(tmp_path, [
            _mm_cool("claude_code_oauth_5", -60, "window", reset_offset=3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_5"]
        assert k["mm_cooling"] is True


# ── 9. existing fields unchanged shape (additive only) ───────────────────────

class TestAdditiveOnly:
    def test_existing_fields_unchanged(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [_mm_ok("claude_code_oauth_1", -60)])
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            "ts": _ts(-30),
            "keys": [_status_entry("claude_code_oauth_1", cooling=False)],
        })
        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        assert rows
        expected_fields = {
            "key_id", "present", "enabled", "cooling", "cool_kind", "reset_hint",
            "window_5h_est_tokens", "weekly_est_tokens",
            "window_5h_sessions", "weekly_sessions",
            "last_outcome", "last_ts",
            "ratelimit_headers", "headers_ts",
            "mm_sessions",
            "mm_cooling", "mm_cool_kind", "mm_reset_hint",
            "mm_last_outcome", "mm_last_ts",
        }
        for row in rows:
            assert set(row.keys()) == expected_fields, (
                f"Field-set drift for {row.get('key_id')}: "
                f"missing={expected_fields - set(row.keys())} "
                f"extra={set(row.keys()) - expected_fields}"
            )

    def test_mm_sessions_still_works_alongside_state(self, tmp_path: Path) -> None:
        """The pre-existing mm_sessions count is unaffected by the new state fields."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_1", -60),
            _mm_ok("claude_code_oauth_1", -120),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_sessions"] == 2
        assert k["mm_cooling"] is False


# ── 10. corrupt / wrong-schema status → fail-soft to events ──────────────────

class TestCorruptStatusFailSoft:
    def test_wrong_schema_status_falls_back(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_status(tmp_path, {
            "schema": "some.other.schema.v9",
            "ts": _ts(-30),
            "keys": [_status_entry("claude_code_oauth_1", cooling=False)],
        })
        _write_mm_events(tmp_path, [
            _mm_ok("claude_code_oauth_1", -400),
            _mm_cool("claude_code_oauth_1", -80, "window", reset_offset=3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True, "wrong-schema status ignored; events win"

    def test_corrupt_json_status_falls_back(self, tmp_path: Path) -> None:
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_status(tmp_path, "{not valid json ][")
        _write_mm_events(tmp_path, [
            _mm_cool("claude_code_oauth_1", -80, "auth", reset_offset=24 * 3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True
        assert k["mm_cool_kind"] == "auth"

    def test_status_missing_ts_falls_back(self, tmp_path: Path) -> None:
        """A status file with no parseable ts cannot be judged fresh → fall back."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_status(tmp_path, {
            "schema": _STATUS_SCHEMA,
            # no ts
            "keys": [_status_entry("claude_code_oauth_1", cooling=False)],
        })
        _write_mm_events(tmp_path, [
            _mm_cool("claude_code_oauth_1", -80, "window", reset_offset=3600),
        ])
        k = _snapshot(tmp_path)["claude_code_oauth_1"]
        assert k["mm_cooling"] is True

    def test_read_mm_status_absent_returns_none(self, tmp_path: Path) -> None:
        from engine.neuralweb.key_pool import _read_mm_status  # noqa: PLC0415
        assert _read_mm_status(root=tmp_path) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
