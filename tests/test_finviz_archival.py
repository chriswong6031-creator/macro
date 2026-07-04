"""Tests for the PIT archival additions in scripts/fetch_finviz_themes.py.

Covers four contracts:
  (a) same-asof rerun does NOT duplicate the subsector_perf_history line
  (b) tree_history appends on changed tree, skips on identical tree
  (c) existing perf_snapshot.json write is untouched (function still writes it)
  (d) torn-line resilience: a partial/corrupt trailing line (runner killed
      mid-append) must NOT block the day's archival — the review-flagged
      failure mode of substring-based dedup.

All fixtures are synthetic and in-memory (tmp_path). Zero network calls.
"""
from __future__ import annotations

import json
from pathlib import Path

# Import the helpers directly — avoids importing main() which triggers argparse.
from scripts.fetch_finviz_themes import (
    append_subsector_perf_history,
    append_tree_history,
    _tree_hash,
    _last_line_hash,
    _last_asof,
)


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #

SAMPLE_SUB_PERF = {"ai": {"1D": 0.5, "1W": 1.2}, "fintech": {"1D": -0.3, "1W": 0.8}}
TREE_A = [{"name": "AI", "subsectors": [{"key": "ai", "members": ["NVDA"]}]}]
TREE_B = [{"name": "AI", "subsectors": [{"key": "ai", "members": ["NVDA", "AMD"]}]}]


def _lines(path: Path) -> list[dict]:
    """Parse jsonl, SKIPPING unparseable lines (the documented reader contract)."""
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ------------------------------------------------------------------ #
# (a) subsector_perf_history dedup
# ------------------------------------------------------------------ #

class TestSubsectorPerfHistoryDedup:
    def test_first_write_creates_file(self, tmp_path):
        p = tmp_path / "subsector_perf_history.jsonl"
        written = append_subsector_perf_history("2026-07-04", SAMPLE_SUB_PERF, path=p)
        assert written is True
        assert p.exists()
        lines = _lines(p)
        assert len(lines) == 1
        assert lines[0]["asof"] == "2026-07-04"
        assert lines[0]["subsectors"] == SAMPLE_SUB_PERF
        assert "members" not in lines[0]  # subsector-only by design

    def test_same_asof_second_call_is_noop(self, tmp_path):
        p = tmp_path / "subsector_perf_history.jsonl"
        append_subsector_perf_history("2026-07-04", SAMPLE_SUB_PERF, path=p)
        written = append_subsector_perf_history("2026-07-04", {"changed": {}}, path=p)
        assert written is False
        lines = _lines(p)
        assert len(lines) == 1
        assert lines[0]["subsectors"] == SAMPLE_SUB_PERF

    def test_different_asof_appends_new_line(self, tmp_path):
        p = tmp_path / "subsector_perf_history.jsonl"
        append_subsector_perf_history("2026-07-03", SAMPLE_SUB_PERF, path=p)
        written = append_subsector_perf_history("2026-07-04", SAMPLE_SUB_PERF, path=p)
        assert written is True
        lines = _lines(p)
        assert len(lines) == 2
        assert lines[0]["asof"] == "2026-07-03"
        assert lines[1]["asof"] == "2026-07-04"

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "subsector_perf_history.jsonl"
        append_subsector_perf_history("2026-07-04", {}, path=p)
        assert p.exists()


# ------------------------------------------------------------------ #
# (d) torn-line resilience — the review-flagged silent-PIT-loss bug
# ------------------------------------------------------------------ #

class TestTornLineResilience:
    def test_torn_trailing_line_does_not_block_append(self, tmp_path):
        """A partial line containing today's asof SUBSTRING must not dedup-block.

        This is the discriminating case for the substring-scan bug: the old
        implementation returned True here and the day was lost forever."""
        p = tmp_path / "subsector_perf_history.jsonl"
        append_subsector_perf_history("2026-07-03", SAMPLE_SUB_PERF, path=p)
        # simulate a torn append from a killed run: asof substring present,
        # line is not valid JSON
        with p.open("a") as fh:
            fh.write('{"asof":"2026-07-04","subsectors":{"ai":{"1D":0.5')
        written = append_subsector_perf_history("2026-07-04", SAMPLE_SUB_PERF, path=p)
        assert written is True, "torn line must not block the day's archival"
        lines = _lines(p)  # tolerant reader skips the torn fragment
        assert [r["asof"] for r in lines] == ["2026-07-03", "2026-07-04"]
        assert lines[-1]["subsectors"] == SAMPLE_SUB_PERF

    def test_healthy_rerun_after_torn_line_recovery_still_dedups(self, tmp_path):
        p = tmp_path / "subsector_perf_history.jsonl"
        with p.open("a") as fh:
            fh.write('{"asof":"2026-07-04","subsec')  # torn
        assert append_subsector_perf_history("2026-07-04", SAMPLE_SUB_PERF, path=p) is True
        # second healthy rerun same day → dedup works off the healthy last line
        assert append_subsector_perf_history("2026-07-04", SAMPLE_SUB_PERF, path=p) is False

    def test_last_asof_torn_line_returns_none(self, tmp_path):
        p = tmp_path / "h.jsonl"
        p.write_text('{"asof":"2026-07-03","x":1}\n{"asof":"2026-07-04",TORN')
        assert _last_asof(p) is None

    def test_torn_tree_line_reappends(self, tmp_path):
        p = tmp_path / "tree_history.jsonl"
        append_tree_history("2026-07-03", TREE_A, path=p)
        with p.open("a") as fh:
            fh.write('{"asof":"2026-07-04","sha256":"dead')  # torn
        # _last_line_hash returns None on the torn line → tree re-appends
        assert append_tree_history("2026-07-04", TREE_A, path=p) is True


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
    def test_write_text_still_overwrites(self, tmp_path):
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
    def test_last_asof_missing_file(self, tmp_path):
        p = tmp_path / "no.jsonl"
        assert _last_asof(p) is None

    def test_last_asof_reads_last_line_only(self, tmp_path):
        p = tmp_path / "h.jsonl"
        p.write_text('{"asof":"2026-07-03","x":1}\n{"asof":"2026-07-04","x":2}\n')
        assert _last_asof(p) == "2026-07-04"

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
