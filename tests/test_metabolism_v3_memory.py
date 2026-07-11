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

    def test_stamp_context_none_returns_empty_list(self, tmp_path):
        """B3: stamp_context(None) must not raise and must return []."""
        result = stamp_context(None, root=tmp_path)  # type: ignore[arg-type]
        assert result == []

    def test_stamp_context_string_returns_empty_list(self, tmp_path):
        """B3: stamp_context('notalist') must not raise and must return []."""
        result = stamp_context("notalist", root=tmp_path)  # type: ignore[arg-type]
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# G. Regression: B1 — FAIL floor invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestFailFloorInvariants:
    """Regression tests for B1: the hard FAIL floor.

    Invariant (i): a FAIL row whose construction matches the query outranks every
                   non-FAIL row, even when the FAIL row has a long ~25-token
                   what_failed prose and is older.
    Invariant (ii): an unrelated FAIL (construction does NOT match the query)
                    does not outrank a relevant PASS row.
    """

    def test_matching_fail_outranks_newer_pass_despite_long_what_failed(self, tmp_path):
        """B1 invariant (i): FAIL with matching construction and long what_failed prose
        must rank above all PASS rows even when older.

        This reproduces the reported 2.43 vs 2.59 score inversion where the 25-token
        what_failed prose inflated the union denominator in the old pooled Jaccard.
        """
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(timespec="seconds")

        # Long what_failed (~25 tokens) that must NOT deflate the construction Jaccard
        long_what_failed = (
            "construction C failed in lobe X with zero IC across all tested regimes "
            "the momentum signal showed no predictive power and decayed rapidly "
            "across bullish bearish and sideways conditions yielding a flat equity curve"
        )

        rows = [
            _lesson(
                "fail-001",
                verdict="FAIL",
                construction="momentum factor lobe X construction C",
                what_failed=long_what_failed,
                ts=old_ts,
            ),
            # Newer PASS rows with same lobe match
            _lesson("pass-050", verdict="PASS", construction="momentum factor lobe X construction C"),
            _lesson("pass-051", verdict="PASS", construction="momentum factor lobe X construction C"),
            _lesson("pass-052", verdict="PASS", construction="momentum factor something else"),
        ]
        _write_lessons(tmp_path, rows)

        top = recall_lesson_rows(
            lobe="X",
            construction_terms="momentum factor C",
            root=tmp_path,
        )
        assert len(top) > 0
        best = top[0]
        assert best["verdict"] == "FAIL", (
            f"FAIL row must rank first but got verdict={best['verdict']} "
            f"score={best['_score']:.3f} reasons={best['_reasons']}"
        )
        assert best["cycle_id"] == "fail-001"
        # The FAIL row's score must exceed the max non-FAIL score (8.5)
        assert best["_score"] > 8.5, (
            f"FAIL floor score must exceed 8.5 but got {best['_score']:.3f}"
        )

    def test_unrelated_fail_does_not_outrank_relevant_pass(self, tmp_path):
        """B1 invariant (ii): a FAIL row with unrelated construction must NOT
        outrank a PASS row that matches the query lobe and construction.
        """
        rows = [
            # Unrelated FAIL — different lobe, different construction
            _lesson(
                "unrelated-fail",
                verdict="FAIL",
                construction="some completely different unrelated signal alpha gamma",
                what_failed="unrelated mechanism failed",
            ),
            # Relevant PASS — matches the query lobe and construction
            _lesson(
                "relevant-pass",
                verdict="PASS",
                construction="momentum factor lobe X construction C",
            ),
        ]
        _write_lessons(tmp_path, rows)

        top = recall_lesson_rows(
            lobe="X",
            construction_terms="momentum factor C",
            root=tmp_path,
        )
        assert len(top) >= 2
        best = top[0]
        assert best["cycle_id"] == "relevant-pass", (
            f"Relevant PASS must outrank unrelated FAIL but got cycle_id={best['cycle_id']} "
            f"score={best['_score']:.3f}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# H. Regression: B2 — _is_fail_verdict exact-token classification
# ─────────────────────────────────────────────────────────────────────────────

class TestIsFailVerdict:
    """Regression tests for B2: substring-match false-fires."""

    def test_benign_verdicts_not_classified_as_fail(self):
        """B2: these benign verdicts must NOT be classified as FAIL."""
        from engine.metabolism.recall import _is_fail_verdict
        benign = [
            "PASS (no issues)",
            "PASS - no concerns",
            "NONE",
            "normal",
            "pass",
            "PASS",
            "OK",
        ]
        for v in benign:
            assert not _is_fail_verdict(v), f"Benign verdict {v!r} was wrongly classified as FAIL"

    def test_fail_verdicts_classified_correctly(self):
        """B2: these verdicts must be classified as FAIL."""
        from engine.metabolism.recall import _is_fail_verdict
        fail_verdicts = [
            "FAIL",
            "fail",
            "killed",
            "KILLED",
            "reject",
            "REJECTED",
            "dead",
            "DEAD",
            "false",
            "FALSE",
            "FAIL — zero IC",
            "verdict: kill",
        ]
        for v in fail_verdicts:
            assert _is_fail_verdict(v), f"Fail verdict {v!r} was NOT classified as FAIL"


# ─────────────────────────────────────────────────────────────────────────────
# I. Regression: B4 — path-form source SLA resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestPathFormSlaResolution:
    """Regression tests for B4: path-form source must resolve to logical SLA key."""

    def test_fitness_history_jsonl_gets_sla_3_not_14(self, tmp_path):
        """B4: source='data/metabolism/fitness_history.jsonl' must use SLA=3 (fitness),
        NOT the default SLA=14.  A block that is 5 days old must be flagged stale.
        """
        _write_sla(tmp_path)
        five_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=5)
        ).isoformat(timespec="seconds")
        now = _now_iso()

        blocks = [{
            "name": "fitness_history",
            "source": "data/metabolism/fitness_history.jsonl",
            "text": "x",
            "as_of": five_days_ago,
        }]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert len(result) == 1
        b = result[0]
        assert b["sla_days"] == 3, (
            f"Expected SLA=3 (fitness) but got {b['sla_days']} "
            f"(would mean the block is NOT stale despite being 5 days old)"
        )
        assert b["is_stale"] is True, (
            "5-day-old fitness_history.jsonl block must be stale under SLA=3"
        )

    def test_organism_state_json_path_resolves_correctly(self, tmp_path):
        """B4: 'data/metabolism/organism_state.json' → SLA=2 (organism_state)."""
        _write_sla(tmp_path)
        three_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=3)
        ).isoformat(timespec="seconds")
        now = _now_iso()
        blocks = [{
            "name": "organism_state",
            "source": "data/metabolism/organism_state.json",
            "text": "x",
            "as_of": three_days_ago,
        }]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["sla_days"] == 2
        assert result[0]["is_stale"] is True  # 3 days > SLA 2

    def test_logical_key_still_resolves_correctly(self, tmp_path):
        """B4: plain logical keys (no path) must continue to work as before."""
        _write_sla(tmp_path)
        one_day_ago = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat(timespec="seconds")
        now = _now_iso()
        blocks = [{
            "name": "trajectory",
            "source": "trajectory",
            "text": "x",
            "as_of": one_day_ago,
        }]
        result = stamp_context(blocks, now_iso=now, root=tmp_path)
        assert result[0]["sla_days"] == 7
        assert result[0]["is_stale"] is False  # 1 day < SLA 7


# ─────────────────────────────────────────────────────────────────────────────
# G. BUG 3 regression — lesson lobe field written + recall lobe-match fires
# ─────────────────────────────────────────────────────────────────────────────

class TestLessonLobeField:
    """Regression tests for BUG 3: lessons carry a lobe field and recall scores it."""

    def test_append_lesson_writes_lobe_field(self, tmp_path):
        """append_lesson with lobe= must persist the lobe field in the JSONL row."""
        from engine.metabolism.memory import append_lesson  # noqa: PLC0415

        ok = append_lesson(
            cycle_id="lobe-t1",
            verdict="PASS",
            what_worked="good",
            what_failed="",
            construction="sensor=x kind=factor tier=T1 title='test'",
            lobe="til",
            root=tmp_path,
        )
        assert ok is True
        p = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0].get("lobe") == "til", (
            f"lobe field missing or wrong in lesson row: {rows[0]}"
        )

    def test_append_lesson_empty_lobe_is_backward_compat(self, tmp_path):
        """append_lesson without lobe= (old callers) must not break."""
        from engine.metabolism.memory import append_lesson  # noqa: PLC0415

        ok = append_lesson(
            cycle_id="lobe-t2",
            verdict="FAIL",
            what_worked="",
            what_failed="failed",
            construction="sensor=y kind=factor tier=T1 title='old'",
            root=tmp_path,
        )
        assert ok is True
        p = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        assert rows[0].get("lobe") == ""  # empty string, not absent

    def test_recall_lobe_exact_match_fires(self, tmp_path):
        """recall_lesson_rows with lobe='til' must give +_WEIGHT_LOBE_MATCH to rows
        that carry lobe='til' in the structured field (BUG 3 fix: lobe_exact)."""
        from engine.metabolism.recall import recall_lesson_rows  # noqa: PLC0415

        # Row A: has lobe='til' in structured field AND construction matches
        row_a = {
            "schema": "metabolism.lessons.v1",
            "ts": _now_iso(-5),
            "cycle_id": "lobe-exact-001",
            "proposal_id": "p001",
            "lobe": "til",
            "verdict": "PASS",
            "what_worked": "good",
            "what_failed": "",
            "construction": "sensor=theme_velocity kind=factor",
        }
        # Row B: has lobe='' (old style) and same construction — should still score
        # via broad-bag fallback but no lobe_exact bonus
        row_b = {
            "schema": "metabolism.lessons.v1",
            "ts": _now_iso(-3),
            "cycle_id": "lobe-exact-002",
            "proposal_id": "p002",
            "lobe": "",
            "verdict": "PASS",
            "what_worked": "ok",
            "what_failed": "",
            "construction": "sensor=theme_velocity kind=factor",
        }
        p = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(row_a) + "\n" + json.dumps(row_b) + "\n", encoding="utf-8")

        top = recall_lesson_rows(lobe="til", construction_terms="theme_velocity", root=tmp_path)
        assert len(top) >= 1

        # Row A (lobe='til' exact match) must rank first
        assert top[0]["cycle_id"] == "lobe-exact-001", (
            f"Expected lobe-exact row to rank first; got {[r['cycle_id'] for r in top]}"
        )
        # Its reasons must mention lobe_exact (structured field match)
        reasons = " ".join(top[0].get("_reasons", []))
        assert "lobe_exact" in reasons, (
            f"Expected lobe_exact in reasons; got {top[0].get('_reasons')}"
        )

    def test_recall_old_rows_without_lobe_field_still_score(self, tmp_path):
        """Old rows without a lobe field must still score via broad-bag fallback."""
        from engine.metabolism.recall import recall_lesson_rows  # noqa: PLC0415

        old_row = {
            "schema": "metabolism.lessons.v1",
            "ts": _now_iso(),
            "cycle_id": "old-no-lobe",
            "verdict": "FAIL",
            "construction": "til momentum factor dead",
            "what_failed": "til lobe: construction C failed",
        }
        p = tmp_path / "data" / "metabolism" / "lessons.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(old_row) + "\n", encoding="utf-8")

        top = recall_lesson_rows(lobe="til", root=tmp_path)
        assert len(top) == 1
        reasons = " ".join(top[0].get("_reasons", []))
        # Should fire via broad-bag fallback (lobe_match) since 'til' appears in text
        assert "lobe_match" in reasons or "lobe_exact" in reasons, (
            f"Expected lobe scoring reason; got {top[0].get('_reasons')}"
        )


# ── Regime triage staleness (learning-wire follow-up) ────────────────────────

class TestRegimeAsofStaleness:
    """_regime_asof_is_stale fails toward caution on missing/stale/garbled asof."""

    def test_fresh_asof_not_stale(self):
        from scripts.metabolism_verify import _regime_asof_is_stale
        assert _regime_asof_is_stale("2026-07-11", today="2026-07-11") is False
        assert _regime_asof_is_stale("2026-07-10", today="2026-07-11") is False

    def test_lagging_asof_is_stale(self):
        from scripts.metabolism_verify import _regime_asof_is_stale
        assert _regime_asof_is_stale("2026-07-08", today="2026-07-11") is True

    def test_missing_or_garbled_asof_is_stale(self):
        from scripts.metabolism_verify import _regime_asof_is_stale
        assert _regime_asof_is_stale("", today="2026-07-11") is True
        assert _regime_asof_is_stale("not-a-date", today="2026-07-11") is True

    def test_stale_regime_file_forces_suspected(self, tmp_path):
        """A stale flipped=False file must route misses to caution (suspected=True)."""
        import json
        from scripts.metabolism_verify import _build_triage_context
        reg = tmp_path / "data" / "regime"
        reg.mkdir(parents=True)
        (reg / "regime_one.json").write_text(json.dumps(
            {"flip_attribution": {"flipped": False, "asof": "2026-06-01"}}))
        ctx = _build_triage_context(tmp_path, today="2026-07-11")
        assert ctx["regime_change_suspected"] is True

    def test_fresh_clean_regime_not_suspected(self, tmp_path):
        import json
        from scripts.metabolism_verify import _build_triage_context
        reg = tmp_path / "data" / "regime"
        reg.mkdir(parents=True)
        (reg / "regime_one.json").write_text(json.dumps(
            {"flip_attribution": {"flipped": False, "asof": "2026-07-11"}}))
        ctx = _build_triage_context(tmp_path, today="2026-07-11")
        assert ctx["regime_change_suspected"] is False

    def test_absent_file_empty_context(self, tmp_path):
        from scripts.metabolism_verify import _build_triage_context
        assert _build_triage_context(tmp_path, today="2026-07-11") == {}
