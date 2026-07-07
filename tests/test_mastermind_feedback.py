"""Tests for engine.neuralweb.mastermind_feedback (Mastermind → NW reverse bridge).

Test list (mirrors mastermind_context.py test style):
1. v1 fixture → present summary with correct totals.
2. v2 fixture (decision_flow/outcome_mix/context_audit) → passthrough counts present.
3. POISONED fixture → none of the private strings reach the output (leak test).
4. Missing file → state absent, no fabricated totals.
5. generated_at 10 days old → state stale.
6. Schema identity + authority booleans all false + is_context_only true.
7. Unknown schema string → absent + gap note.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.mastermind_feedback import (  # noqa: E402
    SCHEMA,
    ARTIFACT_ID,
    build_summary,
    build_and_write,
    read_feedback,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_NOW_UTC = datetime.now(timezone.utc)
_FRESH_TS = _NOW_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")
_STALE_TS = (_NOW_UTC - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_feedback(tmp_path: Path, obj: dict) -> Path:
    """Write a nw_feedback.json fixture."""
    dest = tmp_path / "site" / "mastermind"
    dest.mkdir(parents=True, exist_ok=True)
    p = dest / "nw_feedback.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def _v1_fixture(generated_at: str = _FRESH_TS) -> dict:
    """Minimal valid v1 source fixture."""
    return {
        "schema": "mastermind_nw_feedback.v1",
        "generated_at": generated_at,
        "window_days": 14,
        "thesis_counts": {
            "open": 2,
            "closed_or_rebuilt": 0,
            "total": 2,
        },
        "run_counts": {
            "macro_refresh": {"ok": 4, "error": 0, "other": 0},
            "derisk_us_intraday": {"ok": 13, "error": 0, "other": 0},
        },
        "books": [
            {
                "book_id": "flagship",
                "gate_failures": {"by_severity": {"FREEZE": 12}, "by_guard": {}, "total": 12},
                "rejected_decision_count": 133,
                "lock_conflict_count": 0,
                "stale_freeze_count": 12,
            },
            {
                "book_id": "heavyweight",
                "gate_failures": {"by_severity": {}, "by_guard": {}, "total": 0},
                "rejected_decision_count": 0,
                "lock_conflict_count": 0,
                "stale_freeze_count": 0,
            },
        ],
        "note": "counts only",
    }


def _v2_fixture(generated_at: str = _FRESH_TS) -> dict:
    """v2 source fixture with additive blocks."""
    base = _v1_fixture(generated_at)
    base["schema"] = "mastermind_nw_feedback.v2"
    base["decision_flow"] = {
        "packet_accepted": 45,
        "packet_rejected": 22,
        "top_error_classes": {
            "stale_anchor": 7,
            "peer_expectation": 5,
        },
    }
    base["outcome_mix"] = {
        "n_resolved": 30,
        "n_open": 5,
        "by_band": {
            "gain_gt_10pct": 8,
            "gain_0_10pct": 12,
            "loss_0_10pct": 6,
            "loss_gt_10pct": 4,
        },
    }
    base["context_audit"] = {
        "n_present": 25,
        "n_stale": 3,
        "n_absent": 2,
        "n_total": 30,
        "context_seen_rate": 0.8333,
    }
    return base


def _poisoned_fixture(generated_at: str = _FRESH_TS) -> dict:
    """v1 fixture with private strings planted at multiple levels."""
    base = _v1_fixture(generated_at)
    # Plant private strings at top level
    base["ticker"] = "NVDA"
    base["fill_id"] = "fill_abc123"
    base["ledger_path"] = "/Users/x/secret/data/operator/fills.jsonl"
    base["notional"] = "$12,345"
    # Plant in books list
    base["books"][0]["ticker"] = "AAPL"
    base["books"][0]["fill_id"] = "fill_xyz789"
    base["books"][0]["cost_basis"] = "$45.12"
    base["books"][0]["ledger_path"] = "/Users/x/secret/fills.csv"
    # Plant inside nested gate_failures object
    base["books"][0]["gate_failures"]["secret_ticker"] = "MSFT"
    base["books"][0]["gate_failures"]["fill_ref"] = "fill_abc"
    # Plant in thesis_counts (also private path)
    base["thesis_counts"]["ledger_path"] = "/Users/x/fills.jsonl"
    # Plant in run_counts
    base["run_counts"]["macro_refresh"]["ticker"] = "NVDA"
    return base


# ---------------------------------------------------------------------------
# 1. v1 fixture → present summary with correct totals
# ---------------------------------------------------------------------------

class TestV1Fixture:
    def test_state_present(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "present"

    def test_schema_field(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["schema"] == SCHEMA

    def test_totals_correct(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        totals = summary["totals"]
        assert isinstance(totals, dict)
        assert totals["n_books"] == 2
        # flagship: gate_failures_total=12, rejected=133, lock=0, stale=12
        # heavyweight: gate_failures_total=0, rejected=0, lock=0, stale=0
        assert totals["gate_failures_total"] == 12
        assert totals["rejected_decisions_total"] == 133
        assert totals["lock_conflicts_total"] == 0
        assert totals["stale_freezes_total"] == 12

    def test_thesis_counts(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        totals = summary["totals"]
        assert totals["theses_open"] == 2
        assert totals["theses_total"] == 2

    def test_run_counts(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        totals = summary["totals"]
        # macro_refresh ok=4, derisk_us_intraday ok=13 → total ok=17
        assert totals["runs_ok_total"] == 17
        assert totals["runs_error_total"] == 0

    def test_per_book_count(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert isinstance(summary["per_book"], list)
        assert len(summary["per_book"]) == 2

    def test_per_book_ids(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        ids = [b["book_id"] for b in summary["per_book"]]
        assert "flagship" in ids
        assert "heavyweight" in ids

    def test_per_book_flagship_counts(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        flagship = next(b for b in summary["per_book"] if b["book_id"] == "flagship")
        assert flagship["gate_failures_total"] == 12
        assert flagship["rejected_decision_count"] == 133
        assert flagship["lock_conflict_count"] == 0
        assert flagship["stale_freeze_count"] == 12

    def test_source_schema_field(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["source_schema"] == "mastermind_nw_feedback.v1"

    def test_window_days(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["window_days"] == 14

    def test_asof_field(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        # asof should be the date portion of generated_at
        assert isinstance(summary.get("asof"), str)
        assert len(summary["asof"]) == 10  # YYYY-MM-DD

    def test_no_gap_notes_on_clean_v1(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["gap_notes"] == [], f"Unexpected gaps: {summary['gap_notes']}"

    def test_v1_no_v2_blocks(self, tmp_path):
        """v1 source must NOT produce decision_flow/outcome_mix/context_audit."""
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert "decision_flow" not in summary
        assert "outcome_mix" not in summary
        assert "context_audit" not in summary


# ---------------------------------------------------------------------------
# 2. v2 fixture → passthrough counts present
# ---------------------------------------------------------------------------

class TestV2Fixture:
    def test_state_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "present"

    def test_source_schema_v2(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["source_schema"] == "mastermind_nw_feedback.v2"

    def test_decision_flow_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert "decision_flow" in summary
        df = summary["decision_flow"]
        assert df["packet_accepted"] == 45
        assert df["packet_rejected"] == 22

    def test_decision_flow_top_error_classes(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        df = summary["decision_flow"]
        assert "top_error_classes" in df
        assert df["top_error_classes"]["stale_anchor"] == 7
        assert df["top_error_classes"]["peer_expectation"] == 5

    def test_outcome_mix_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert "outcome_mix" in summary
        om = summary["outcome_mix"]
        assert om["n_resolved"] == 30
        assert om["n_open"] == 5

    def test_outcome_mix_by_band(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        om = summary["outcome_mix"]
        assert "by_band" in om
        assert om["by_band"]["gain_gt_10pct"] == 8

    def test_context_audit_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert "context_audit" in summary
        ca = summary["context_audit"]
        assert ca["n_present"] == 25
        assert ca["n_stale"] == 3
        assert ca["n_absent"] == 2
        assert ca["n_total"] == 30
        assert abs(ca["context_seen_rate"] - 0.8333) < 1e-4

    def test_v2_still_has_correct_totals(self, tmp_path):
        """v2 must still produce the same book totals as v1."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        totals = summary["totals"]
        assert totals["n_books"] == 2
        assert totals["gate_failures_total"] == 12
        assert totals["rejected_decisions_total"] == 133


# ---------------------------------------------------------------------------
# 3. POISONED fixture → no private strings in serialized output
# ---------------------------------------------------------------------------

class TestPoisonedFixture:
    def test_no_private_strings_in_output(self, tmp_path):
        """None of the private strings from the poisoned fixture may reach the output."""
        _write_feedback(tmp_path, _poisoned_fixture())
        summary = build_summary(root=tmp_path)
        serialized = json.dumps(summary, default=str)

        private_strings = [
            "NVDA",
            "AAPL",
            "MSFT",
            "fill_abc123",
            "fill_xyz789",
            "fill_abc",
            "fill_ref",
            "/Users/x/secret",
            "/Users/x/fills.jsonl",
            "ledger_path",
            "$12,345",
            "$45.12",
            "cost_basis",
            "notional",
        ]
        leaked = [s for s in private_strings if s in serialized]
        assert not leaked, (
            f"LEAK: private strings found in output: {leaked}\n"
            f"Serialized output (first 2000 chars):\n{serialized[:2000]}"
        )

    def test_poison_state_is_present(self, tmp_path):
        """Poisoned fixture has valid schema/date so state should be present,
        proving the whitelist correctly strips the poison rather than aborting."""
        _write_feedback(tmp_path, _poisoned_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "present"

    def test_poison_totals_still_correct(self, tmp_path):
        """Private strings must be stripped but legitimate counts must be correct."""
        _write_feedback(tmp_path, _poisoned_fixture())
        summary = build_summary(root=tmp_path)
        totals = summary["totals"]
        # flagship: gate=12, rejected=133, lock=0, stale=12
        assert totals["gate_failures_total"] == 12
        assert totals["rejected_decisions_total"] == 133

    def test_poison_no_ticker_key_in_per_book(self, tmp_path):
        _write_feedback(tmp_path, _poisoned_fixture())
        summary = build_summary(root=tmp_path)
        for book in (summary.get("per_book") or []):
            assert "ticker" not in book, f"ticker key in per_book entry: {book}"
            assert "fill_id" not in book, f"fill_id key in per_book entry: {book}"
            assert "cost_basis" not in book, f"cost_basis key in per_book entry: {book}"
            assert "ledger_path" not in book, f"ledger_path key in per_book entry: {book}"

    def test_poison_no_top_level_ticker(self, tmp_path):
        _write_feedback(tmp_path, _poisoned_fixture())
        summary = build_summary(root=tmp_path)
        assert "ticker" not in summary
        assert "fill_id" not in summary
        assert "ledger_path" not in summary
        assert "notional" not in summary


# ---------------------------------------------------------------------------
# 4. Missing file → state absent, no fabricated totals
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_state_absent(self, tmp_path):
        # No nw_feedback.json written
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "absent"

    def test_no_fabricated_totals(self, tmp_path):
        summary = build_summary(root=tmp_path)
        assert summary["totals"] is None

    def test_no_fabricated_per_book(self, tmp_path):
        summary = build_summary(root=tmp_path)
        assert summary["per_book"] is None

    def test_gap_note_present(self, tmp_path):
        summary = build_summary(root=tmp_path)
        gap_str = " ".join(summary["gap_notes"])
        assert "absent" in gap_str.lower() or "nw_feedback" in gap_str.lower()

    def test_schema_still_present(self, tmp_path):
        """Even when absent, the output schema identifier must be correct."""
        summary = build_summary(root=tmp_path)
        assert summary["schema"] == SCHEMA

    def test_no_asof_when_absent(self, tmp_path):
        """asof must not be fabricated when absent."""
        summary = build_summary(root=tmp_path)
        assert "asof" not in summary


# ---------------------------------------------------------------------------
# 5. generated_at 10 days old → state stale
# ---------------------------------------------------------------------------

class TestStaleness:
    def test_state_stale(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "stale"

    def test_no_totals_when_stale(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        summary = build_summary(root=tmp_path)
        assert summary["totals"] is None

    def test_no_per_book_when_stale(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        summary = build_summary(root=tmp_path)
        assert summary["per_book"] is None

    def test_gap_note_mentions_stale(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        summary = build_summary(root=tmp_path)
        gap_str = " ".join(summary["gap_notes"])
        assert "stale" in gap_str.lower()

    def test_schema_still_present_when_stale(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        summary = build_summary(root=tmp_path)
        assert summary["schema"] == SCHEMA

    def test_no_asof_when_stale(self, tmp_path):
        """asof must not be fabricated when stale."""
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        summary = build_summary(root=tmp_path)
        assert "asof" not in summary


# ---------------------------------------------------------------------------
# 6. Schema identity + authority booleans all false + is_context_only true
# ---------------------------------------------------------------------------

class TestSchemaAndAuthority:
    def test_output_schema(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["schema"] == "neuralweb.mastermind_feedback_summary.v1"

    def test_is_context_only_true(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["is_context_only"] is True

    def test_is_context_only_true_when_absent(self, tmp_path):
        """is_context_only must be True even when source is absent."""
        summary = build_summary(root=tmp_path)
        assert summary["is_context_only"] is True

    def test_authority_all_false(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        auth = summary["authority"]
        for key in (
            "can_add_candidates",
            "can_raise_size",
            "can_lower_size",
            "can_block_entry",
            "can_force_exit",
        ):
            assert auth[key] is False, f"authority.{key} should be False, got {auth[key]}"

    def test_authority_all_false_when_absent(self, tmp_path):
        """Authority booleans must be False even when source is absent."""
        summary = build_summary(root=tmp_path)
        auth = summary["authority"]
        for key in (
            "can_add_candidates",
            "can_raise_size",
            "can_lower_size",
            "can_block_entry",
            "can_force_exit",
        ):
            assert auth[key] is False, f"authority.{key} should be False when absent"

    def test_metric_families_present(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        assert "metric_families" in summary
        assert isinstance(summary["metric_families"], list)
        assert len(summary["metric_families"]) >= 3

    def test_metric_families_include_blocked(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        statuses = {mf["family"]: mf["status"] for mf in summary["metric_families"]}
        # fill_slippage_by_context must be blocked, not faked
        assert statuses.get("fill_slippage_by_context") == "blocked"
        assert statuses.get("warning_outcome_delta") == "blocked"

    def test_metric_families_live_families(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        statuses = {mf["family"]: mf["status"] for mf in summary["metric_families"]}
        assert statuses.get("context_engagement") == "live"
        assert statuses.get("decision_flow") == "live"
        assert statuses.get("outcome_mix") == "live"

    def test_artifact_id_constant(self):
        assert ARTIFACT_ID == "mastermind-feedback-summary"

    def test_generated_utc_is_iso(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        summary = build_summary(root=tmp_path)
        ts = summary.get("generated_utc", "")
        # Should be YYYY-MM-DDTHH:MM:SSZ
        assert "T" in ts and ts.endswith("Z"), f"Bad generated_utc: {ts!r}"


# ---------------------------------------------------------------------------
# 7. Unknown schema string → absent + gap note
# ---------------------------------------------------------------------------

class TestUnknownSchema:
    def test_unknown_schema_state_absent(self, tmp_path):
        obj = _v1_fixture()
        obj["schema"] = "mastermind_nw_feedback.v99"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "absent"

    def test_unknown_schema_gap_note_names_schema(self, tmp_path):
        obj = _v1_fixture()
        obj["schema"] = "mastermind_nw_feedback.v99"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        gap_str = " ".join(summary["gap_notes"])
        assert "v99" in gap_str or "unknown schema" in gap_str.lower(), (
            f"Expected gap note to name unknown schema; got: {summary['gap_notes']}"
        )

    def test_unknown_schema_no_totals(self, tmp_path):
        obj = _v1_fixture()
        obj["schema"] = "some_other.schema.v3"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        assert summary["totals"] is None

    def test_missing_schema_field_treated_as_absent(self, tmp_path):
        """Source with no schema field at all must be treated as absent."""
        obj = _v1_fixture()
        del obj["schema"]
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "absent"

    def test_source_schema_recorded_in_output(self, tmp_path):
        """source_schema field must record what was seen even for unknown schemas."""
        obj = _v1_fixture()
        obj["schema"] = "mastermind_nw_feedback.v99"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        assert summary.get("source_schema") == "mastermind_nw_feedback.v99"


# ---------------------------------------------------------------------------
# 8. build_and_write integration test
# ---------------------------------------------------------------------------

class TestBuildAndWrite:
    def test_writes_artifact(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        payload = build_and_write(root=tmp_path)
        out = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
        assert out.exists(), "build_and_write did not create the output file"

    def test_artifact_is_valid_json(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        build_and_write(root=tmp_path)
        out = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["schema"] == SCHEMA

    def test_artifact_is_counts_only(self, tmp_path):
        """Serialized artifact must not contain private-looking strings."""
        _write_feedback(tmp_path, _poisoned_fixture())
        build_and_write(root=tmp_path)
        out = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
        text = out.read_text(encoding="utf-8")
        for bad in ("NVDA", "fill_abc", "/Users/", "$12,345", "ledger_path", "ticker"):
            assert bad not in text, f"Private string {bad!r} found in written artifact"

    def test_absent_source_still_writes(self, tmp_path):
        """Even with absent source, build_and_write must write a valid artifact."""
        payload = build_and_write(root=tmp_path)
        out = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
        assert out.exists()
        assert payload["state"] == "absent"

    def test_return_value_matches_written(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        payload = build_and_write(root=tmp_path)
        out = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["schema"] == payload["schema"]
        assert written["state"] == payload["state"]


# ---------------------------------------------------------------------------
# 9. read_feedback unit tests
# ---------------------------------------------------------------------------

class TestReadFeedback:
    def test_present(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        result = read_feedback(root=tmp_path)
        assert result["state"] == "present"
        assert result["raw"] is not None

    def test_absent_no_file(self, tmp_path):
        result = read_feedback(root=tmp_path)
        assert result["state"] == "absent"
        assert result["raw"] is None

    def test_absent_invalid_json(self, tmp_path):
        dest = tmp_path / "site" / "mastermind"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "nw_feedback.json").write_text("not json!", encoding="utf-8")
        result = read_feedback(root=tmp_path)
        assert result["state"] == "absent"

    def test_stale(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture(generated_at=_STALE_TS))
        result = read_feedback(root=tmp_path)
        assert result["state"] == "stale"
        assert result["raw"] is None  # stale → raw is None

    def test_schema_returned(self, tmp_path):
        _write_feedback(tmp_path, _v1_fixture())
        result = read_feedback(root=tmp_path)
        assert result["source_schema"] == "mastermind_nw_feedback.v1"


# ---------------------------------------------------------------------------
# 10. Real-artifact smoke test (if nw_feedback.json exists in-tree)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRealArtifactSmoke:
    def test_real_build_runs_without_crash(self):
        """Real build from the worktree must complete without raising."""
        summary = build_summary(root=_REPO_ROOT)
        assert "schema" in summary
        assert summary["schema"] == SCHEMA
        assert summary["state"] in ("present", "stale", "absent")
        # Authority must always be all-false regardless of source state
        auth = summary["authority"]
        for key in (
            "can_add_candidates",
            "can_raise_size",
            "can_lower_size",
            "can_block_entry",
            "can_force_exit",
        ):
            assert auth[key] is False

    def test_real_artifact_counts_only(self):
        """Real output must contain no private-looking strings."""
        summary = build_summary(root=_REPO_ROOT)
        serialized = json.dumps(summary, default=str)
        # These string patterns must never appear in a counts-only artifact
        forbidden = ["/Users/", "fill_id", "avg_cost", "shares", "notional"]
        found = [f for f in forbidden if f in serialized]
        assert not found, (
            f"Private strings found in real summary output: {found}\n"
            f"(first 2000 chars): {serialized[:2000]}"
        )
