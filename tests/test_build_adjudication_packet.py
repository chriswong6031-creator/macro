"""
tests/test_build_adjudication_packet.py — Hermetic pytest suite for
scripts/build_adjudication_packet.py and scripts/build_ruling_index.py.

All tests are hermetic: they use tmp_path fixtures or tempdir, never read
from the real data/ tree, and do not depend on sibling scripts
(check_adjudication_packet.py, config/adjudication_rubrics.yml) that may not
exist yet.

Test coverage
-------------
1. Correct tier stamped for t1 and t2 decision classes.
2. t2: requested_decision lands in blocked_outcomes.
3. t2: allowed_outcomes == {"defer", "send_to_review"}.
4. t1: allowed_outcomes contains requested_decision (deduplicated when "defer").
5. Idempotent re-append replaces, not duplicates.
6. build_ruling_index --selftest exits 0 (subprocess).
7. Keyword autofill against a synthetic ruling_index.json.
8. Schema field present in every generated packet.
9. packet_id format: adj-<as_of>-<slug>.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the modules under test
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR.parent))  # add repo root to path

from scripts.build_adjudication_packet import (  # noqa: E402
    _T1_CLASSES,
    _T2_CLASSES,
    _append_to_queue,
    _autofill_rulings,
    _build_packet,
    _load_queue,
    _tier_for_class,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AS_OF = "2026-07-06"


def _sample_t1_packet(**overrides) -> dict:
    kwargs = dict(
        title="Sample t1 packet",
        decision_class="scoped_build",
        requested_decision="scoped_build",
        as_of=_AS_OF,
        owner_program="test-program",
    )
    kwargs.update(overrides)
    return _build_packet(**kwargs)


def _sample_t2_packet(**overrides) -> dict:
    kwargs = dict(
        title="New lobe charter test",
        decision_class="new_lobe_charter",
        requested_decision="charter",
        as_of=_AS_OF,
    )
    kwargs.update(overrides)
    return _build_packet(**kwargs)


# ---------------------------------------------------------------------------
# Test 1: Tier stamping
# ---------------------------------------------------------------------------


class TestTierStamping:
    """Verify tier assignment for t1 and t2 classes."""

    def test_t1_classes_produce_tier_1(self):
        for cls in sorted(_T1_CLASSES):
            packet = _build_packet(
                title="t1 check",
                decision_class=cls,
                requested_decision="scoped_build",
                as_of=_AS_OF,
            )
            assert packet["tier"] == 1, f"{cls} should produce tier=1"

    def test_t2_classes_produce_tier_2(self):
        for cls in sorted(_T2_CLASSES):
            packet = _build_packet(
                title="t2 check",
                decision_class=cls,
                requested_decision="charter",
                as_of=_AS_OF,
            )
            assert packet["tier"] == 2, f"{cls} should produce tier=2"

    def test_unknown_class_raises(self):
        with pytest.raises(ValueError, match="Unknown decision class"):
            _tier_for_class("not_a_real_class")


# ---------------------------------------------------------------------------
# Test 2 & 3: t2 outcome rules
# ---------------------------------------------------------------------------


class TestT2OutcomeRules:
    """t2 packets block requested_decision; allow only defer and send_to_review."""

    def test_requested_decision_in_blocked_outcomes(self):
        packet = _sample_t2_packet()
        assert "charter" in packet["blocked_outcomes"], (
            f"requested 'charter' should be in blocked_outcomes: {packet['blocked_outcomes']}"
        )

    def test_allowed_outcomes_are_defer_and_send_to_review(self):
        packet = _sample_t2_packet()
        assert set(packet["allowed_outcomes"]) == {"defer", "send_to_review"}, (
            f"t2 allowed_outcomes should be {{defer, send_to_review}}, got {packet['allowed_outcomes']}"
        )

    def test_nondelegable_is_true(self):
        packet = _sample_t2_packet()
        assert packet["authority"]["nondelegable"] is True

    def test_authority_ceiling_is_operator(self):
        packet = _sample_t2_packet()
        assert packet["authority"]["current_ceiling"] == "operator"


# ---------------------------------------------------------------------------
# Test 4: t1 outcome rules (including dedup when requested_decision == "defer")
# ---------------------------------------------------------------------------


class TestT1OutcomeRules:
    """t1 packets allow requested_decision, defer, and reject (deduplicated)."""

    def test_requested_decision_in_allowed_outcomes(self):
        packet = _sample_t1_packet(requested_decision="scoped_build")
        assert "scoped_build" in packet["allowed_outcomes"]

    def test_blocked_outcomes_empty(self):
        packet = _sample_t1_packet()
        assert packet["blocked_outcomes"] == []

    def test_defer_deduplicated_when_requested_decision_is_defer(self):
        packet = _build_packet(
            title="Defer test",
            decision_class="comeback_clock_move_gt_90d",
            requested_decision="defer",
            as_of=_AS_OF,
        )
        # allowed_outcomes should not contain "defer" twice
        assert packet["allowed_outcomes"].count("defer") == 1, (
            f"'defer' duplicated in allowed_outcomes: {packet['allowed_outcomes']}"
        )
        assert "defer" in packet["allowed_outcomes"]
        assert "reject" in packet["allowed_outcomes"]

    def test_authority_ceiling_is_opus(self):
        packet = _sample_t1_packet()
        assert packet["authority"]["current_ceiling"] == "opus"

    def test_nondelegable_is_false(self):
        packet = _sample_t1_packet()
        assert packet["authority"]["nondelegable"] is False


# ---------------------------------------------------------------------------
# Test 5: Idempotent queue append
# ---------------------------------------------------------------------------


class TestIdempotentQueueAppend:
    """Re-appending with the same packet_id replaces, not duplicates."""

    def test_first_append_not_replaced(self):
        q = _load_queue(Path("/nonexistent/queue.json"))  # fresh skeleton
        packet = _sample_t1_packet()
        q, replaced = _append_to_queue(q, packet, _AS_OF)
        assert not replaced
        assert len(q["packets"]) == 1

    def test_second_append_replaces(self):
        q = _load_queue(Path("/nonexistent/queue.json"))
        packet = _sample_t1_packet()
        q, _ = _append_to_queue(q, packet, _AS_OF)
        q, replaced = _append_to_queue(q, packet, _AS_OF)
        assert replaced
        assert len(q["packets"]) == 1, (
            f"queue should have exactly 1 packet after idempotent re-append; got {len(q['packets'])}"
        )

    def test_different_ids_both_kept(self):
        q = _load_queue(Path("/nonexistent/queue.json"))
        p1 = _sample_t1_packet(title="Packet one")
        p2 = _sample_t1_packet(title="Packet two")
        q, _ = _append_to_queue(q, p1, _AS_OF)
        q, _ = _append_to_queue(q, p2, _AS_OF)
        assert len(q["packets"]) == 2

    def test_write_then_load_roundtrip(self, tmp_path):
        qpath = tmp_path / "queue.json"
        q = _load_queue(qpath)
        packet = _sample_t1_packet()
        q, _ = _append_to_queue(q, packet, _AS_OF)
        with open(qpath, "w", encoding="utf-8") as fh:
            json.dump(q, fh, indent=2)

        # Load again
        q2 = _load_queue(qpath)
        assert len(q2["packets"]) == 1
        assert q2["packets"][0]["packet_id"] == packet["packet_id"]


# ---------------------------------------------------------------------------
# Test 6: build_ruling_index --selftest via subprocess
# ---------------------------------------------------------------------------


class TestRulingIndexSelftest:
    """Verify build_ruling_index --selftest exits 0."""

    def test_selftest_exit_0(self):
        script = _SCRIPTS_DIR / "build_ruling_index.py"
        result = subprocess.run(
            [sys.executable, str(script), "--as-of", _AS_OF, "--selftest"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"build_ruling_index --selftest failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "selftest PASSED" in result.stdout


# ---------------------------------------------------------------------------
# Test 7: Keyword autofill against synthetic ruling_index.json
# ---------------------------------------------------------------------------


class TestKeywordAutofill:
    """Autofill matches ruling IDs via context line keyword search."""

    def _write_synthetic_index(self, path: Path) -> None:
        synthetic = {
            "schema": "neuralweb.ruling_index.v1",
            "built_from": "research/**/*.md",
            "as_of": _AS_OF,
            "n_rulings": 4,
            "rulings": [
                {
                    "id": "RUL-SUCC-1",
                    "files": [
                        {
                            "path": "research/doc.md",
                            "first_line_no": 1,
                            "context": "macro context rail ownership adjudication bench",
                        }
                    ],
                    "n_mentions": 2,
                    "truncated": False,
                },
                {
                    "id": "DT-R14",
                    "files": [
                        {
                            "path": "research/doc.md",
                            "first_line_no": 5,
                            "context": "era-split law ratified for entry signals",
                        }
                    ],
                    "n_mentions": 1,
                    "truncated": False,
                },
                {
                    "id": "LH-R11",
                    "files": [
                        {
                            "path": "research/doc.md",
                            "first_line_no": 9,
                            "context": "long hold thesis ratified accrual mode",
                        }
                    ],
                    "n_mentions": 1,
                    "truncated": False,
                },
                {
                    "id": "RO-9",
                    "files": [
                        {
                            "path": "research/doc.md",
                            "first_line_no": 12,
                            "context": "signed options flow forbidden oracle rotation",
                        }
                    ],
                    "n_mentions": 1,
                    "truncated": False,
                },
            ],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(synthetic, fh)

    def test_keyword_matches_context(self, tmp_path):
        idx_path = tmp_path / "ruling_index.json"
        self._write_synthetic_index(idx_path)
        hits = _autofill_rulings(["macro"], idx_path)
        assert "RUL-SUCC-1" in hits, f"'macro' should match RUL-SUCC-1; got {hits}"

    def test_keyword_case_insensitive(self, tmp_path):
        idx_path = tmp_path / "ruling_index.json"
        self._write_synthetic_index(idx_path)
        hits = _autofill_rulings(["ERA-SPLIT"], idx_path)
        assert "DT-R14" in hits, f"case-insensitive 'ERA-SPLIT' should match DT-R14; got {hits}"

    def test_no_match_returns_empty(self, tmp_path):
        idx_path = tmp_path / "ruling_index.json"
        self._write_synthetic_index(idx_path)
        hits = _autofill_rulings(["xyznonexistent999"], idx_path)
        assert hits == [], f"no-match keyword should return []; got {hits}"

    def test_multiple_keywords_union(self, tmp_path):
        idx_path = tmp_path / "ruling_index.json"
        self._write_synthetic_index(idx_path)
        # "macro" matches RUL-SUCC-1; "era-split" matches DT-R14
        hits = _autofill_rulings(["macro", "era-split"], idx_path)
        assert "RUL-SUCC-1" in hits
        assert "DT-R14" in hits

    def test_missing_index_file_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        hits = _autofill_rulings(["macro"], missing)
        assert hits == []

    def test_result_sorted(self, tmp_path):
        idx_path = tmp_path / "ruling_index.json"
        self._write_synthetic_index(idx_path)
        # Use a keyword that matches multiple rulings
        hits = _autofill_rulings(["ratified"], idx_path)
        assert hits == sorted(hits), f"hits should be sorted; got {hits}"


# ---------------------------------------------------------------------------
# Test 8: Schema field present in every generated packet
# ---------------------------------------------------------------------------


class TestSchemaField:
    """Every packet must carry the schema declaration."""

    def test_t1_packet_has_schema(self):
        packet = _sample_t1_packet()
        assert packet.get("schema") == "neuralweb.adjudication_packet.v1"

    def test_t2_packet_has_schema(self):
        packet = _sample_t2_packet()
        assert packet.get("schema") == "neuralweb.adjudication_packet.v1"

    def test_required_top_level_keys(self):
        packet = _sample_t1_packet()
        required = {
            "schema", "packet_id", "tier", "created_at", "created_by",
            "request", "scope", "case_law", "authority", "privacy",
            "statistics", "clocks", "build_collision", "review",
            "allowed_outcomes", "blocked_outcomes", "escalation", "decision",
        }
        missing = required - set(packet.keys())
        assert not missing, f"packet missing keys: {missing}"


# ---------------------------------------------------------------------------
# Test 9: packet_id format
# ---------------------------------------------------------------------------


class TestPacketIdFormat:
    """packet_id must follow adj-<as_of>-<slug> convention."""

    def test_packet_id_starts_with_adj_and_date(self):
        packet = _sample_t1_packet(title="My Test Title")
        assert packet["packet_id"].startswith(f"adj-{_AS_OF}-"), (
            f"packet_id should start with adj-{_AS_OF}-; got {packet['packet_id']}"
        )

    def test_packet_id_slug_lowercase(self):
        packet = _sample_t1_packet(title="UPPER CASE TITLE")
        pid = packet["packet_id"]
        slug_part = pid[len(f"adj-{_AS_OF}-"):]
        assert slug_part == slug_part.lower(), (
            f"slug part of packet_id should be lowercase; got {slug_part!r}"
        )

    def test_packet_id_no_special_chars(self):
        import re
        packet = _sample_t1_packet(title="Title with (parens) and #hashes!")
        pid = packet["packet_id"]
        assert re.match(r"^[a-z0-9-]+$", pid), (
            f"packet_id should only contain [a-z0-9-]; got {pid!r}"
        )

    def test_escalation_opened_on_equals_as_of(self):
        packet = _sample_t1_packet()
        assert packet["escalation"]["opened_on"] == _AS_OF
