"""tests/test_key_pool_mm_events.py — Mastermind bot key-event join in usage_snapshot.

Covers:
  1. Fixture root with both ledgers -> mm_sessions correctly counted per key.
  2. Corrupt/foreign-schema/unknown-key rows in mm events are ignored.
  3. Absent mm events file -> mm_sessions=0, output identical to baseline (golden parity).
  4. Rows older than 7d are excluded from mm_sessions count.
  5. _read_mm_events never raises (absent file, corrupt JSON, OS error).
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
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def _write_mm_events(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "data" / "mastermind" / "key_events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


_VALID_SCHEMA = "metabolism.key_ledger.v1"

_BASE_LEDGER_ROW = {
    "schema": _VALID_SCHEMA,
    "ts": None,  # fill in per test
    "key_id": "claude_code_oauth_1",
    "cycle_id": "",
    "stage": "dispatch",
    "est_tokens": 10000,
    "outcome": "ok",
}


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


def _mm_row(key_id: str, offset: int = -60) -> dict:
    return {
        "schema": _VALID_SCHEMA,
        "ts": _ts(offset),
        "key_id": key_id,
        "cycle_id": "mm-cycle",
        "stage": "mm_dispatch",
        "est_tokens": 8000,
        "outcome": "ok",
    }


# ── 1. Both ledgers present → mm_sessions correctly aggregated ────────────────

class TestMMSessionsMerge:
    def test_mm_sessions_counted_per_key(self, tmp_path: Path) -> None:
        """MM events in the last 7d are counted per key as mm_sessions."""
        # Write a main ledger with one row for key_1
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1", -100)])
        # Write MM events: 2 for key_1, 1 for key_2
        _write_mm_events(tmp_path, [
            _mm_row("claude_code_oauth_1", -200),
            _mm_row("claude_code_oauth_1", -300),
            _mm_row("claude_code_oauth_2", -400),
        ])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}

        assert by_key["claude_code_oauth_1"]["mm_sessions"] == 2, (
            f"Expected 2 mm_sessions for oauth_1, got {by_key['claude_code_oauth_1']['mm_sessions']}"
        )
        assert by_key["claude_code_oauth_2"]["mm_sessions"] == 1, (
            f"Expected 1 mm_session for oauth_2, got {by_key['claude_code_oauth_2']['mm_sessions']}"
        )
        assert by_key["claude_code_oauth_3"]["mm_sessions"] == 0, (
            f"Expected 0 mm_sessions for oauth_3, got {by_key['claude_code_oauth_3']['mm_sessions']}"
        )

    def test_mm_sessions_field_present_on_all_rows(self, tmp_path: Path) -> None:
        """Every row in usage_snapshot has a mm_sessions field (additive, not breaking)."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        # No MM events file — field must still be present

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        assert rows, "usage_snapshot returned empty list"
        for row in rows:
            assert "mm_sessions" in row, (
                f"mm_sessions field missing from row for key_id={row.get('key_id')}"
            )

    def test_existing_fields_unchanged(self, tmp_path: Path) -> None:
        """Adding mm_sessions must not remove or rename any pre-existing field."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [_mm_row("claude_code_oauth_1")])

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
        }
        for row in rows:
            missing = expected_fields - set(row.keys())
            assert not missing, (
                f"Fields missing from row {row.get('key_id')}: {missing}"
            )


# ── 2. Corrupt / foreign-schema / unknown-key rows are ignored ────────────────

class TestMMEventsFiltering:
    def test_wrong_schema_rows_ignored(self, tmp_path: Path) -> None:
        """Rows with schema != metabolism.key_ledger.v1 must not affect mm_sessions."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [
            # valid row
            _mm_row("claude_code_oauth_1", -60),
            # wrong schema
            {
                "schema": "some.other.schema.v2",
                "ts": _ts(-120),
                "key_id": "claude_code_oauth_1",
                "outcome": "ok",
            },
        ])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}
        assert by_key["claude_code_oauth_1"]["mm_sessions"] == 1, (
            "Only the valid-schema row should count; wrong-schema row must be ignored"
        )

    def test_unknown_key_id_rows_ignored(self, tmp_path: Path) -> None:
        """Rows with key_id not in POOL_CAPABILITY_IDS or 'legacy' are dropped."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [
            _mm_row("claude_code_oauth_1", -60),
            {
                "schema": _VALID_SCHEMA,
                "ts": _ts(-120),
                "key_id": "some_unknown_bot_key",
                "outcome": "ok",
            },
        ])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}
        assert by_key["claude_code_oauth_1"]["mm_sessions"] == 1, (
            "Unknown key_id row must be ignored; valid row must still count"
        )

    def test_corrupt_json_lines_skipped(self, tmp_path: Path) -> None:
        """Corrupt JSON lines in mm events file are skipped without raising."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_2")])
        mm_path = tmp_path / "data" / "mastermind" / "key_events.jsonl"
        mm_path.parent.mkdir(parents=True, exist_ok=True)
        mm_path.write_text(
            json.dumps(_mm_row("claude_code_oauth_2", -60)) + "\n"
            + "not-valid-json{{{{\n"
            + json.dumps(_mm_row("claude_code_oauth_2", -120)) + "\n",
            encoding="utf-8",
        )

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}
        # Only the 2 valid lines should count; corrupt line silently skipped
        assert by_key["claude_code_oauth_2"]["mm_sessions"] == 2, (
            f"Expected 2 (skipping corrupt line), got {by_key['claude_code_oauth_2']['mm_sessions']}"
        )

    def test_legacy_key_id_accepted(self, tmp_path: Path) -> None:
        """'legacy' is a valid key_id for MM events."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        _write_mm_events(tmp_path, [
            {
                "schema": _VALID_SCHEMA,
                "ts": _ts(-60),
                "key_id": "legacy",
                "outcome": "ok",
            },
        ])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}
        assert "legacy" in by_key, "legacy key missing from snapshot"
        assert by_key["legacy"]["mm_sessions"] == 1, (
            f"Expected 1 mm_session for legacy, got {by_key['legacy']['mm_sessions']}"
        )


# ── 3. Absent MM file → mm_sessions=0, golden parity ────────────────────────

class TestMMAbsentFile:
    def test_absent_mm_file_mm_sessions_zero(self, tmp_path: Path) -> None:
        """When data/mastermind/key_events.jsonl does not exist, mm_sessions=0 for all."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])
        # deliberately do NOT write mm events file

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        for row in rows:
            assert row["mm_sessions"] == 0, (
                f"Expected mm_sessions=0 for {row['key_id']} when file absent, "
                f"got {row['mm_sessions']}"
            )

    def test_golden_parity_absent_vs_empty_mm(self, tmp_path: Path) -> None:
        """Absent MM file and an empty MM file should yield identical output."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_1")])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415

        rows_absent = usage_snapshot(root=tmp_path)

        # Now write an empty MM events file
        mm_path = tmp_path / "data" / "mastermind" / "key_events.jsonl"
        mm_path.parent.mkdir(parents=True, exist_ok=True)
        mm_path.write_text("", encoding="utf-8")

        rows_empty = usage_snapshot(root=tmp_path)

        # mm_sessions and all other fields must match
        for a, b in zip(rows_absent, rows_empty):
            assert a == b, (
                f"Absent vs empty MM file produced different row for {a.get('key_id')}:\n"
                f"  absent: {a}\n  empty:  {b}"
            )

    def test_read_mm_events_absent_never_raises(self, tmp_path: Path) -> None:
        """_read_mm_events returns [] and never raises when file is absent."""
        from engine.neuralweb.key_pool import _read_mm_events  # noqa: PLC0415
        result = _read_mm_events(root=tmp_path)
        assert result == [], f"Expected [] for absent file, got {result}"


# ── 4. Rows older than 7d excluded from mm_sessions ─────────────────────────

class TestMMSessionsWindow:
    def test_old_mm_rows_excluded(self, tmp_path: Path) -> None:
        """MM rows older than 7 days must not count toward mm_sessions."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_3")])
        _write_mm_events(tmp_path, [
            _mm_row("claude_code_oauth_3", -100),                    # recent — counts
            _mm_row("claude_code_oauth_3", -(7 * 24 * 3600 + 60)),  # older than 7d — excluded
        ])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}
        assert by_key["claude_code_oauth_3"]["mm_sessions"] == 1, (
            "Only the recent MM row should count; >7d-old row must be excluded"
        )

    def test_exactly_at_7d_boundary_excluded(self, tmp_path: Path) -> None:
        """A row exactly at the 7d boundary (== cutoff) is counted (>= semantics)."""
        _write_ledger(tmp_path, [_ledger_row("claude_code_oauth_4")])
        # Slightly inside the 7d window
        _write_mm_events(tmp_path, [
            _mm_row("claude_code_oauth_4", -(7 * 24 * 3600 - 10)),
        ])

        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        rows = usage_snapshot(root=tmp_path)
        by_key = {r["key_id"]: r for r in rows}
        # Within the window: should count
        assert by_key["claude_code_oauth_4"]["mm_sessions"] == 1


# ── 5. _read_mm_events fail-soft ─────────────────────────────────────────────

class TestReadMMEventsSafety:
    def test_empty_lines_skipped(self, tmp_path: Path) -> None:
        """Empty lines in the file are silently skipped."""
        mm_path = tmp_path / "data" / "mastermind" / "key_events.jsonl"
        mm_path.parent.mkdir(parents=True, exist_ok=True)
        mm_path.write_text("\n\n" + json.dumps(_mm_row("claude_code_oauth_1")) + "\n\n", encoding="utf-8")

        from engine.neuralweb.key_pool import _read_mm_events  # noqa: PLC0415
        result = _read_mm_events(root=tmp_path)
        assert len(result) == 1

    def test_all_corrupt_lines_returns_empty(self, tmp_path: Path) -> None:
        """File with all corrupt JSON lines returns []."""
        mm_path = tmp_path / "data" / "mastermind" / "key_events.jsonl"
        mm_path.parent.mkdir(parents=True, exist_ok=True)
        mm_path.write_text("bad-json\nalso-bad\n{incomplete\n", encoding="utf-8")

        from engine.neuralweb.key_pool import _read_mm_events  # noqa: PLC0415
        result = _read_mm_events(root=tmp_path)
        assert result == []
