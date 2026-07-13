"""tests/test_key_pool.py — key_pool cooling-window correctness.

F4 regression: a 429-triggered 'window' cooling must NOT be cleared early
by a later 'ok' row.  Only 'auth' cooling is cleared by a later ok row.
A 'weekly' cooling is cleared only by reset_hint passage (pre-existing behaviour,
not changed).
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _write_ledger(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a synthetic key_ledger.jsonl to tmp_path and return its path."""
    ledger = tmp_path / "data" / "metabolism" / "key_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    return ledger


def _ts(offset_seconds: int = 0) -> str:
    """Return an ISO-8601 UTC timestamp offset_seconds from now."""
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds"
    )


class TestWindowCoolingNotClearedByOk:
    """F4 regression suite: window-cooling persists despite later ok rows."""

    def test_window_cooling_not_cleared_by_later_ok(self, tmp_path: Path) -> None:
        """F4: a 'window' (429) cooling row must NOT be cleared by a later 'ok' row.

        Pre-fix behaviour: any 'ok' row after the cooling row cleared window cooling,
        causing the key to be re-selected before its quota window elapsed.
        Post-fix: only 'auth' cooling is cleared by a later ok row.
        """
        from engine.neuralweb.key_pool import is_cooling  # type: ignore[import]

        key_id = "claude_code_oauth_1"
        reset_future = _ts(offset_seconds=3600)  # reset 1h from now

        rows = [
            # window cooling 10 minutes ago
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-600),
                "key_id": key_id,
                "outcome": "rate_limited",
                "cool_kind": "window",
                "reset_hint": reset_future,
            },
            # successful call 5 minutes ago (AFTER the cooling row)
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-300),
                "key_id": key_id,
                "outcome": "ok",
                "cool_kind": None,
                "reset_hint": None,
            },
        ]
        _write_ledger(tmp_path, rows)

        result = is_cooling(key_id, root=tmp_path)
        assert result is True, (
            "F4 regression: window cooling should persist despite later 'ok' row; "
            f"is_cooling returned {result}"
        )

    def test_auth_cooling_cleared_by_later_ok(self, tmp_path: Path) -> None:
        """auth cooling IS cleared by a later 'ok' row (operator rotated secret)."""
        from engine.neuralweb.key_pool import is_cooling  # type: ignore[import]

        key_id = "claude_code_oauth_1"
        reset_future = _ts(offset_seconds=86400)  # reset 24h from now

        rows = [
            # auth cooling 10 minutes ago
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-600),
                "key_id": key_id,
                "outcome": "auth_failed",
                "cool_kind": "auth",
                "reset_hint": reset_future,
            },
            # successful call 5 minutes ago — secret was rotated
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-300),
                "key_id": key_id,
                "outcome": "ok",
                "cool_kind": None,
                "reset_hint": None,
            },
        ]
        _write_ledger(tmp_path, rows)

        result = is_cooling(key_id, root=tmp_path)
        assert result is False, (
            "auth cooling should be cleared by later 'ok' row; "
            f"is_cooling returned {result}"
        )

    def test_window_cooling_expires_by_reset_hint(self, tmp_path: Path) -> None:
        """window cooling expires when reset_hint is in the past (no ok row needed)."""
        from engine.neuralweb.key_pool import is_cooling  # type: ignore[import]

        key_id = "claude_code_oauth_1"
        reset_past = _ts(offset_seconds=-60)  # reset was 1 minute ago

        rows = [
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-7200),
                "key_id": key_id,
                "outcome": "rate_limited",
                "cool_kind": "window",
                "reset_hint": reset_past,
            },
        ]
        _write_ledger(tmp_path, rows)

        result = is_cooling(key_id, root=tmp_path)
        assert result is False, (
            "window cooling should expire when reset_hint is in the past; "
            f"is_cooling returned {result}"
        )

    def test_no_cooling_row_returns_false(self, tmp_path: Path) -> None:
        """No cooling row at all → not cooling."""
        from engine.neuralweb.key_pool import is_cooling  # type: ignore[import]

        key_id = "claude_code_oauth_1"
        rows = [
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-300),
                "key_id": key_id,
                "outcome": "ok",
                "cool_kind": None,
                "reset_hint": None,
            },
        ]
        _write_ledger(tmp_path, rows)

        result = is_cooling(key_id, root=tmp_path)
        assert result is False

    def test_weekly_cooling_not_cleared_by_ok(self, tmp_path: Path) -> None:
        """weekly cooling is NEVER cleared by an ok row (pre-existing behaviour preserved)."""
        from engine.neuralweb.key_pool import is_cooling  # type: ignore[import]

        key_id = "claude_code_oauth_1"
        reset_future = _ts(offset_seconds=7 * 24 * 3600)

        rows = [
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-600),
                "key_id": key_id,
                "outcome": "rate_limited",
                "cool_kind": "weekly",
                "reset_hint": reset_future,
            },
            {
                "schema": "metabolism.key_ledger.v1",
                "ts": _ts(-300),
                "key_id": key_id,
                "outcome": "ok",
                "cool_kind": None,
                "reset_hint": None,
            },
        ]
        _write_ledger(tmp_path, rows)

        result = is_cooling(key_id, root=tmp_path)
        assert result is True, (
            "weekly cooling must not be cleared by ok row; "
            f"is_cooling returned {result}"
        )
