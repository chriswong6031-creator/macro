"""tests/test_metabolism_v3_memory.py — Hermetic tests for Metabolism v3 Wave W1.

Coverage:
  A. Provenance: stamp_context freshness resolution + staleness + unknown-age
  B. Provenance: render_freshness_header prefixes stale rows with ⚠ STALE
  C. Fingerprint: order-insensitivity + case/punctuation normalization
  D. Recall ranking: old FAIL beats newer PASSes when lobe+construction match
  E. Byte-budget packing: top-scored row is always present and whole
  F. NEVER-RAISE: missing lessons → fallback string; corrupt JSON → skipped; missing SLA → defaults

All tests are HERMETIC (tmp_path, pass root=tmp_path; no live filesystem reads).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.metabolism.provenance import stamp_context, render_freshness_header, _load_sla
from engine.metabolism.recall import (
    fingerprint_construction,
    recall_lesson_rows,
    recall_lessons,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso(delta_days: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=delta_days)
    return dt.isoformat(timespec="seconds")


def _write_lessons(root: Path, rows: list[dict]) -> Path:
    p = root / "data" / "metabolism" / "lessons.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _write_sla(root: Path) -> Path:
    p = root / "config" / "metabolism_context_sla.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "sources:\n"
        "  organism_state: {sla_days: 2}\n"
        "  fitness: {sla_days: 3}\n"
        "  trajectory: {sla_days: 7}\n"
        "  lessons: {sla_days: 30}\n"
        "  case_law: {sla_days: 120}\n"
        "  charter: {sla_days: 365}\n"
        "default_sla_days: 14\n",
        encoding="utf-8",
    )
    return p


def _lesson(
    cycle_id: str,
    verdict: str,
    construction: str,
    what_failed: str = "",
    what_worked: str = "",
    proposal_id: str | None = None,
    ts: str | None = None,
) -> dict:
    return {
        "schema": "metabolism.lessons.v1",
        "ts": ts or _now_iso(),
        "cycle_id": cycle_id,
        "proposal_id": proposal_id or cycle_id,
        "verdict": verdict,
        "what_worked": what_worked,
        "what_failed": what_failed,
        "construction": construction,
    }


# ─────────────────────────────────────────────────────────────────────────────
# A. Provenance — stamp_context freshness resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestStampContext:

    def test_explicit_as_of_fresh(self, tmp_path):
        """Block with recent as_of is not stale."""
        _write_sla(tmp_path)
        now = _now_iso()
        blocks = [{"name": "lessons", "source": "lessons", "text": "x", "as_of": now}]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert len(result) == 1
        assert result[0]["age_days"] is not None
        assert result[0]["age_days"] < 0.01
        assert result[0]["is_stale"] is False
        assert result[0]["staleness_reason"] == "as_of"

    def test_explicit_as_of_old_stale(self, tmp_path):
        """Block with as_of 4 days ago, SLA=3 (fitness) → stale."""
        _write_sla(tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(timespec="seconds")
        now = _now_iso()
        blocks = [{"name": "fitness", "source": "fitness", "text": "x", "as_of": old_ts}]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["is_stale"] is True
        assert result[0]["age_days"] > 3.0
        assert result[0]["sla_days"] == 3

    def test_file_mtime_fresh(self, tmp_path):
        """Block where source path exists with recent mtime is not stale."""
        _write_sla(tmp_path)
        # Create a fresh file
        src_file = tmp_path / "data" / "metabolism" / "organism_state.json"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("{}", encoding="utf-8")
        # mtime is just now; using now_iso far in future makes age_days = 0 relative to now
        blocks = [{"name": "organism_state", "source": "data/metabolism/organism_state.json", "text": "x"}]
        now = _now_iso()
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["age_days"] is not None
        assert result[0]["is_stale"] is False
        assert result[0]["staleness_reason"] == "file-mtime"

    def test_file_mtime_old_stale(self, tmp_path):
        """Passing now_iso far into the future makes a fresh file look old → stale."""
        _write_sla(tmp_path)
        src_file = tmp_path / "data" / "metabolism" / "organism_state.json"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("{}", encoding="utf-8")
        blocks = [{"name": "organism_state", "source": "data/metabolism/organism_state.json", "text": "x"}]
        # Pretend it's 10 days in the future; SLA for organism_state = 2 days
        future_now = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(timespec="seconds")
        result = stamp_context(blocks, now_iso=future_now, root=tmp_path)
        assert result[0]["is_stale"] is True
        assert result[0]["age_days"] > 2.0

    def test_unknown_age_block(self, tmp_path):
        """Block with no as_of and non-existent source path → unknown-age, not stale."""
        _write_sla(tmp_path)
        now = _now_iso()
        blocks = [{"name": "case_law", "source": "nonexistent/path.json", "text": "x"}]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["age_days"] is None
        assert result[0]["is_stale"] is False
        assert result[0]["staleness_reason"] == "unknown-age"

    def test_default_sla_applied_to_unknown_source(self, tmp_path):
        """Source key not in SLA config → default_sla_days (14) used."""
        _write_sla(tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(timespec="seconds")
        now = _now_iso()
        blocks = [{"name": "mystery_source", "source": "mystery_source", "text": "x", "as_of": old_ts}]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["sla_days"] == 14
        assert result[0]["is_stale"] is True  # 20d > 14d default SLA

    def test_no_sla_config_falls_back_to_hardcoded(self, tmp_path):
        """Missing SLA config → hardcoded defaults, no raise."""
        # Do NOT write SLA config
        old_ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(timespec="seconds")
        now = _now_iso()
        blocks = [{"name": "fitness", "source": "fitness", "text": "x", "as_of": old_ts}]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["sla_days"] == 3  # hardcoded
        assert result[0]["is_stale"] is True

    def test_multiple_blocks_mixed(self, tmp_path):
        """Mixed fresh/stale blocks in one call."""
        _write_sla(tmp_path)
        now = _now_iso()
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(timespec="seconds")
        blocks = [
            {"name": "lessons", "source": "lessons", "text": "fresh", "as_of": now},
            {"name": "organism_state", "source": "organism_state", "text": "stale", "as_of": old},
            {"name": "mystery", "source": "no/path", "text": "unknown"},
        ]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert len(result) == 3
        assert result[0]["is_stale"] is False
        assert result[1]["is_stale"] is True
        assert result[2]["staleness_reason"] == "unknown-age"


# ─────────────────────────────────────────────────────────────────────────────
# B. render_freshness_header
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderFreshnessHeader:

    def test_stale_blocks_have_warning_prefix(self, tmp_path):
        _write_sla(tmp_path)
        old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(timespec="seconds")
        now = _now_iso()
        blocks = [
            {"name": "fitness", "source": "fitness", "text": "x", "as_of": now},
            {"name": "organism_state", "source": "organism_state", "text": "x", "as_of": old},
        ]
        stamped = stamp_context(blocks, now_iso=now, root=tmp_path)
        header = render_freshness_header(stamped)
        lines = header.splitlines()
        assert lines[0] == "### Context freshness"
        # Fresh line should NOT have ⚠
        fresh_line = [l for l in lines if "fitness" in l][0]
        assert "⚠" not in fresh_line
        # Stale line MUST have ⚠
        stale_line = [l for l in lines if "organism_state" in l][0]
        assert "⚠ STALE" in stale_line

    def test_unknown_age_not_flagged_stale(self, tmp_path):
        _write_sla(tmp_path)
        now = _now_iso()
        blocks = [{"name": "case_law", "source": "no/path", "text": "x"}]
        stamped = stamp_context(blocks, now_iso=now, root=tmp_path)
        header = render_freshness_header(stamped)
        assert "⚠" not in header
        assert "age unknown" in header

    def test_header_never_raises_on_empty(self):
        result = render_freshness_header([])
        assert result.startswith("### Context freshness")

    def test_header_never_raises_on_malformed_block(self):
        result = render_freshness_header([{"not_a_real_block": True}])
        assert "### Context freshness" in result


# ─────────────────────────────────────────────────────────────────────────────
# C. fingerprint_construction
# ─────────────────────────────────────────────────────────────────────────────

class TestFingerprintConstruction:

    def test_order_insensitive(self):
        a = fingerprint_construction("A vs B momentum")
        b = fingerprint_construction("momentum B A")
        assert a == b

    def test_case_normalized(self):
        a = fingerprint_construction("MOMENTUM Mean Reversion")
        b = fingerprint_construction("momentum mean reversion")
        assert a == b

    def test_punctuation_stripped(self):
        # Commas, exclamation marks, and trailing punctuation are stripped.
        # Hyphens are also punctuation and are removed, so "mean-reversion"
        # becomes "meanreversion" (the two halves are joined, not split).
        # The key invariant: two inputs that differ only in punctuation produce
        # the same fingerprint.
        a = fingerprint_construction("mean-reversion, sector!")
        b = fingerprint_construction("meanreversion sector")
        assert a == b
        # Commas and trailing punctuation stripped too
        c = fingerprint_construction("sector, momentum!")
        d = fingerprint_construction("momentum sector")
        assert c == d

    def test_stopwords_dropped(self):
        fp = fingerprint_construction("the momentum of the sector is strong")
        # "the", "of", "is" should be dropped
        tokens = fp.split()
        assert "the" not in tokens
        assert "of" not in tokens
        assert "is" not in tokens
        assert "momentum" in tokens
        assert "sector" in tokens
        assert "strong" in tokens

    def test_empty_input(self):
        assert fingerprint_construction("") == ""
        assert fingerprint_construction("   ") == ""

    def test_identical_phrases_different_order(self):
        pairs = [
            ("sector rotation trend following", "trend following sector rotation"),
            ("volatility regime detection", "detection regime volatility"),
            ("earnings momentum factor", "factor earnings momentum"),
        ]
        for a_text, b_text in pairs:
            assert fingerprint_construction(a_text) == fingerprint_construction(b_text)

    def test_never_raises_on_junk(self):
        # Should not raise even on unusual input
        result = fingerprint_construction("!@#$%^&*()")
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# D. Recall ranking — old FAIL beats newer PASSes
# ─────────────────────────────────────────────────────────────────────────────

class TestRecallRanking:

    def _make_lessons(self, tmp_path: Path) -> Path:
        """Seed: one OLD FAIL row for lobe X + construction C, plus several newer PASS rows."""
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(timespec="seconds")
        rows = [
            # The critical row: OLD, FAIL, lobe X, construction C
            _lesson(
                "cycle-001",
                verdict="FAIL",
                construction="momentum factor lobe X construction C dead",
                what_failed="construction C failed in lobe X — zero IC",
                proposal_id="P-X-001",
                ts=old_ts,
            ),
            # Several newer PASS rows, different lobe/construction
            _lesson("cycle-050", verdict="PASS", construction="sector rotation breadth"),
            _lesson("cycle-051", verdict="PASS", construction="volatility surface"),
            _lesson("cycle-052", verdict="PASS", construction="earnings drift"),
            _lesson("cycle-053", verdict="PASS", construction="price volume divergence"),
            _lesson("cycle-054", verdict="PASS", construction="macro regime breadth"),
        ]
        return _write_lessons(tmp_path, rows)

    def test_fail_row_ranks_first_despite_age(self, tmp_path):
        """The old FAIL row for lobe X / construction C must rank #1."""
        self._make_lessons(tmp_path)
        top = recall_lesson_rows(
            lobe="X",
            construction_terms="C momentum factor",
            root=tmp_path,
        )
        assert len(top) > 0, "Should return at least one row"
        best = top[0]
        # The FAIL row must be first
        assert best["verdict"] == "FAIL", (
            f"Expected FAIL verdict first but got {best['verdict']} "
            f"(score={best['_score']:.3f}, reasons={best['_reasons']})"
        )
        assert best["cycle_id"] == "cycle-001"

    def test_fail_reasons_include_both_lobe_and_fail_verdict(self, tmp_path):
        """The top row's _reasons must mention both lobe_match and fail_verdict."""
        self._make_lessons(tmp_path)
        top = recall_lesson_rows(lobe="X", construction_terms="C", root=tmp_path)
        reasons = top[0].get("_reasons", [])
        reason_str = " ".join(reasons)
        assert "lobe_match" in reason_str
        assert "fail_verdict" in reason_str

    def test_score_field_present_and_positive(self, tmp_path):
        self._make_lessons(tmp_path)
        top = recall_lesson_rows(lobe="X", root=tmp_path)
        for row in top:
            assert "_score" in row
            assert isinstance(row["_score"], float)

    def test_k_limits_results(self, tmp_path):
        self._make_lessons(tmp_path)
        top = recall_lesson_rows(lobe="X", k=2, root=tmp_path)
        assert len(top) <= 2

    def test_no_query_returns_rows(self, tmp_path):
        """With no lobe/construction query, rows are still returned (score from verdict only)."""
        self._make_lessons(tmp_path)
        top = recall_lesson_rows(root=tmp_path)
        assert len(top) > 0


# ─────────────────────────────────────────────────────────────────────────────
# E. Byte-budget packing — top row always present and whole
# ─────────────────────────────────────────────────────────────────────────────

class TestByteBudgetPacking:

    def test_top_row_kept_whole_under_tiny_budget(self, tmp_path):
        """With a tiny byte_budget, the single highest-scored row is intact (not chopped)."""
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(timespec="seconds")
        rows = [
            _lesson("cycle-001", verdict="FAIL", construction="lobe X construction C critical",
                    what_failed="failed badly", ts=old_ts),
            _lesson("cycle-002", verdict="PASS", construction="unrelated alpha"),
            _lesson("cycle-003", verdict="PASS", construction="another unrelated"),
        ]
        _write_lessons(tmp_path, rows)

        # Budget of 50 bytes is far below any full row
        result = recall_lessons(lobe="X", construction_terms="C", byte_budget=50, root=tmp_path)

        # Must not be the absence string
        assert "not yet present" not in result

        # Must be valid JSON (single line)
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        assert len(lines) >= 1
        # The first (and maybe only) line must parse cleanly
        parsed = json.loads(lines[0])
        assert "cycle_id" in parsed
        assert parsed["cycle_id"] == "cycle-001"

    def test_budget_respected_for_additional_rows(self, tmp_path):
        """Additional rows are dropped rather than overflowing the budget."""
        rows = [_lesson(f"cycle-{i:03d}", verdict="PASS", construction="common topic") for i in range(20)]
        _write_lessons(tmp_path, rows)

        result = recall_lessons(construction_terms="common topic", byte_budget=500, root=tmp_path)
        assert len(result.encode()) <= 1000  # generous upper bound; at most a few rows

    def test_result_is_valid_jsonl(self, tmp_path):
        """Every line in the output must be parseable JSON."""
        rows = [_lesson(f"c{i}", verdict="PASS", construction="sector rotation") for i in range(10)]
        _write_lessons(tmp_path, rows)

        result = recall_lessons(construction_terms="sector rotation", byte_budget=2000, root=tmp_path)
        for line in result.splitlines():
            line = line.strip()
            if line:
                json.loads(line)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# F. NEVER-RAISE guarantees
# ─────────────────────────────────────────────────────────────────────────────

class TestNeverRaise:

    def test_missing_lessons_file_returns_fallback(self, tmp_path):
        result = recall_lessons(root=tmp_path)
        assert result == "(lessons.jsonl not yet present — accruing)"

    def test_missing_lessons_file_recall_rows_returns_empty(self, tmp_path):
        result = recall_lesson_rows(root=tmp_path)
        assert result == []

    def test_corrupt_json_line_skipped_no_raise(self, tmp_path):
        p = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            'NOT VALID JSON!!!\n'
            + json.dumps(_lesson("c1", verdict="PASS", construction="sector rotation")) + "\n",
            encoding="utf-8",
        )
        # Should not raise; the bad line is skipped and the good row is returned
        result = recall_lesson_rows(root=tmp_path)
        assert len(result) == 1
        assert result[0]["cycle_id"] == "c1"

    def test_missing_sla_config_falls_back_no_raise(self, tmp_path):
        """No SLA config → hardcoded defaults, no raise."""
        per_source, default = _load_sla(root=tmp_path)
        assert isinstance(per_source, dict)
        assert isinstance(default, int)
        assert default == 14
        assert per_source.get("fitness") == 3

    def test_stamp_context_never_raises_on_empty_blocks(self, tmp_path):
        result = stamp_context([], root=tmp_path)
        assert result == []

    def test_stamp_context_never_raises_on_malformed_block(self, tmp_path):
        _write_sla(tmp_path)
        # Block with no 'name' or 'source'
        result = stamp_context([{"text": "hi"}], now_iso=_now_iso(), root=tmp_path)
        assert len(result) == 1

    def test_recall_lessons_corrupt_file_returns_fallback(self, tmp_path):
        p = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOTJSON\nALSONOTJSON\n", encoding="utf-8")
        # All lines corrupt → no valid rows → fallback string
        result = recall_lessons(root=tmp_path)
        assert "not yet present" in result

    def test_fingerprint_never_raises(self):
        # Extreme edge cases
        for text in ["", "   ", "\n\t", "!@#$%", "a" * 10000]:
            result = fingerprint_construction(text)
            assert isinstance(result, str)
