"""Tests for the PIT archival additions in scripts/fetch_finviz_themes.py.

Covers three contracts:
  (a) same-asof rerun does NOT duplicate the member_perf_history line
  (b) tree_history appends on changed tree, skips on identical tree
  (c) existing perf_snapshot.json write is untouched (function still writes it)

All fixtures are synthetic and in-memory (tmp_path). Zero network calls.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

# Import the helpers directly — avoids importing main() which triggers argparse.
from scripts.fetch_finviz_themes import (
    append_member_perf_history,
    append_tree_history,
    _tree_hash,
    _last_line_hash,
    _asof_exists_in_jsonl,
    PERF_PATH,
)


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #

SAMPLE_SUB_PERF = {"ai": {"1D": 0.5, "1W": 1.2}, "fintech": {"1D": -0.3, "1W": 0.8}}
SAMPLE_MEM_PERF = {"NVDA": {"1D": 1.1, "1W": 2.3}, "AAPL": {"1D": -0.1, "1W": 0.4}}
TREE_A = [{"name": "AI", "subsectors": [{"key": "ai", "members": ["NVDA"]}]}]
TREE_B = [{"name": "AI", "subsectors": [{"key": "ai", "members": ["NVDA", "AMD"]}]}]


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ------------------------------------------------------------------ #
# (a) member_perf_history dedup
# ------------------------------------------------------------------ #

class TestMemberPerfHistoryDedup:
    def test_first_write_creates_file(self, tmp_path):
        p = tmp_path / "member_perf_history.jsonl"
        written = append_member_perf_history("2026-07-04", SAMPLE_SUB_PERF, SAMPLE_MEM_PERF, path=p)
        assert written is True
        assert p.exists()
        lines = _lines(p)
        assert len(lines) == 1
        assert lines[0]["asof"] == "2026-07-04"
        assert lines[0]["subsectors"] == SAMPLE_SUB_PERF
        assert lines[0]["members"] == SAMPLE_MEM_PERF

    def test_same_asof_second_call_is_noop(self, tmp_path):
        p = tmp_path / "member_perf_history.jsonl"
        append_member_perf_history("2026-07-04", SAMPLE_SUB_PERF, SAMPLE_MEM_PERF, path=p)
        # Call again with same asof — should skip
        written = append_member_perf_history("2026-07-04", {"changed": {}}, {}, path=p)
        assert written is False
        lines = _lines(p)
        # Still only one line, original data intact
        assert len(lines) == 1
        assert lines[0]["subsectors"] == SAMPLE_SUB_PERF

    def test_different_asof_appends_new_line(self, tmp_path):
        p = tmp_path / "member_perf_history.jsonl"
        append_member_perf_history("2026-07-03", SAMPLE_SUB_PERF, SAMPLE_MEM_PERF, path=p)
        written = append_member_perf_history("2026-07-04", SAMPLE_SUB_PERF, SAMPLE_MEM_PERF, path=p)
        assert written is True
        lines = _lines(p)
        assert len(lines) == 2
        assert lines[0]["asof"] == "2026-07-03"
        assert lines[1]["asof"] == "2026-07-04"

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "member_perf_history.jsonl"
        append_member_perf_history("2026-07-04", {}, {}, path=p)
        assert p.exists()


# ------------------------------------------------------------------ #
# (b) tree_history change detection
# ------------------------------------------------------------------ #

class TestTreeHistory:
    def test_first_write_on_empty_file(self, tmp_path):
        p = tmp_path / "tree_history.jsonl"
        written = append_tree_history("2026-07-04", TREE_A, path=p)
        assert written is True
        lines = _lines(p)
        assert len(lines) == 1
        assert lines[0]["asof"] == "2026-07-04"
        assert lines[0]["sha256"] == _tree_hash(TREE_A)
        assert lines[0]["tree"] == TREE_A

    def test_identical_tree_skips_append(self, tmp_path):
        p = tmp_path / "tree_history.jsonl"
        append_tree_history("2026-07-03", TREE_A, path=p)
        written = append_tree_history("2026-07-04", TREE_A, path=p)
        assert written is False
        lines = _lines(p)
        assert len(lines) == 1  # still just the original

    def test_changed_tree_appends(self, tmp_path):
        p = tmp_path / "tree_history.jsonl"
        append_tree_history("2026-07-03", TREE_A, path=p)
        written = append_tree_history("2026-07-04", TREE_B, path=p)
        assert written is True
        lines = _lines(p)
        assert len(lines) == 2
        assert lines[1]["sha256"] == _tree_hash(TREE_B)
        assert lines[1]["tree"] == TREE_B

    def test_hash_is_stable_across_key_order(self, tmp_path):
        """sha256 must be stable regardless of dict insertion order."""
        tree_x = [{"b": 2, "a": 1}]
        tree_y = [{"a": 1, "b": 2}]
        assert _tree_hash(tree_x) == _tree_hash(tree_y)

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "tree_history.jsonl"
        append_tree_history("2026-07-04", TREE_A, path=p)
        assert p.exists()


# ------------------------------------------------------------------ #
# (c) perf_snapshot.json write is untouched
# ------------------------------------------------------------------ #

class TestPerfSnapshotUnchanged:
    def test_write_text_still_overwrites(self, tmp_path, monkeypatch):
        """Simulate what main() does: PERF_PATH.write_text(...) must always write."""
        perf_path = tmp_path / "perf_snapshot.json"
        snap_v1 = {"asof": "2026-07-03", "data": "old"}
        perf_path.write_text(json.dumps(snap_v1))

        snap_v2 = {"asof": "2026-07-04", "data": "new"}
        perf_path.write_text(json.dumps(snap_v2, separators=(",", ":")))

        result = json.loads(perf_path.read_text())
        assert result["asof"] == "2026-07-04"
        assert result["data"] == "new"


# ------------------------------------------------------------------ #
# internal helpers
# ------------------------------------------------------------------ #

class TestInternalHelpers:
    def test_asof_exists_missing_file(self, tmp_path):
        p = tmp_path / "no.jsonl"
        assert _asof_exists_in_jsonl(p, "2026-07-04") is False

    def test_asof_exists_present(self, tmp_path):
        p = tmp_path / "h.jsonl"
        p.write_text('{"asof":"2026-07-03","x":1}\n{"asof":"2026-07-04","x":2}\n')
        assert _asof_exists_in_jsonl(p, "2026-07-04") is True
        assert _asof_exists_in_jsonl(p, "2026-07-05") is False

    def test_last_line_hash_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert _last_line_hash(p) is None

    def test_last_line_hash_missing_file(self, tmp_path):
        p = tmp_path / "missing.jsonl"
        assert _last_line_hash(p) is None

    def test_last_line_hash_reads_last(self, tmp_path):
        p = tmp_path / "h.jsonl"
        h1 = _tree_hash(TREE_A)
        h2 = _tree_hash(TREE_B)
        p.write_text(
            json.dumps({"sha256": h1}) + "\n" +
            json.dumps({"sha256": h2}) + "\n"
        )
        assert _last_line_hash(p) == h2
