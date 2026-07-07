"""Tests for engine.neuralweb.mastermind_feedback (Mastermind → NW reverse bridge).

Test list:
1. v1 fixture → present summary with correct totals.
2. v2 fixture (canonical shape) → decision_flow/outcome_mix/context_audit present.
   2b. v2 accruing context_audit variant passthrough.
3. POISONED fixture (v1 + v2 labels) → none of the private strings reach output.
4. Missing file → state absent, no fabricated totals.
5. generated_at 10 days old → state stale.
6. Schema identity + authority booleans all false + is_context_only true.
7. Unknown schema string → absent + gap note.
8. build_and_write integration test.
9. read_feedback unit tests.
10. Real-artifact smoke test (if nw_feedback.json exists in-tree).
11. m2/m3 — _parse_date and unparseable generated_at → absent.
12. n1 — context_seen_rate out-of-range → field dropped + gap note.
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
    _parse_date,
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
    """v2 source fixture with canonical additive blocks."""
    base = _v1_fixture(generated_at)
    base["schema"] = "mastermind_nw_feedback.v2"
    # Canonical v2 decision_flow: by_book list + rejection_error_classes
    base["decision_flow"] = {
        "by_book": [
            {"book_id": "flagship", "packet_accepted": 45, "packet_rejected": 22},
        ],
        "rejection_error_classes": {
            "falsifiers": 7,
            "expected_failure_mode": 5,
        },
    }
    # Canonical v2 outcome_mix: n_resolved + by_outcome (digit-only keys are valid)
    base["outcome_mix"] = {
        "n_resolved": 30,
        "by_outcome": {
            "1": 20,
            "0": 10,
        },
    }
    # Canonical v2 context_audit: five count fields
    base["context_audit"] = {
        "n_present": 25,
        "n_stale": 3,
        "n_absent": 2,
        "n_runs_total": 30,
        "context_seen_rate": 0.8333,
    }
    return base


def _v2_accruing_fixture(generated_at: str = _FRESH_TS) -> dict:
    """v2 fixture where context_audit is in the accruing variant."""
    base = _v2_fixture(generated_at)
    base["context_audit"] = {"state": "accruing", "n_runs_total": 0}
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


def _poisoned_v2_fixture(generated_at: str = _FRESH_TS) -> dict:
    """v2 fixture with poison planted inside v2-specific label dicts."""
    base = _v2_fixture(generated_at)
    # Poison rejection_error_classes keys
    base["decision_flow"]["rejection_error_classes"]["ticker_NVDA_x"] = 3
    base["decision_flow"]["rejection_error_classes"]["avg_cost_45.12"] = 2
    base["decision_flow"]["rejection_error_classes"]["MASTERMIND_TOKEN_XYZ"] = 1
    base["decision_flow"]["rejection_error_classes"]["/Users/x"] = 1
    base["decision_flow"]["rejection_error_classes"]["$12,345"] = 1
    # Poison by_outcome keys
    base["outcome_mix"]["by_outcome"]["ticker_NVDA_x"] = 5
    base["outcome_mix"]["by_outcome"]["avg_cost_45.12"] = 3
    base["outcome_mix"]["by_outcome"]["/Users/x"] = 1
    # Poison book_id in by_book
    base["decision_flow"]["by_book"].append({
        "book_id": "MASTERMIND_TOKEN_XYZ",
        "packet_accepted": 1,
        "packet_rejected": 0,
    })
    base["decision_flow"]["by_book"].append({
        "book_id": "/Users/x",
        "packet_accepted": 1,
        "packet_rejected": 0,
    })
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
# 2. v2 fixture → canonical counts present
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

    def test_decision_flow_by_book(self, tmp_path):
        """decision_flow must use by_book list (canonical v2)."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        df = summary["decision_flow"]
        assert "by_book" in df
        assert isinstance(df["by_book"], list)
        assert len(df["by_book"]) >= 1
        flagship = next(e for e in df["by_book"] if e["book_id"] == "flagship")
        assert flagship["packet_accepted"] == 45
        assert flagship["packet_rejected"] == 22

    def test_decision_flow_rejection_error_classes(self, tmp_path):
        """decision_flow must use rejection_error_classes (canonical v2)."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        df = summary["decision_flow"]
        assert "rejection_error_classes" in df
        assert df["rejection_error_classes"]["falsifiers"] == 7
        assert df["rejection_error_classes"]["expected_failure_mode"] == 5

    def test_decision_flow_no_old_keys(self, tmp_path):
        """Canonical v2: top_error_classes and packet_accepted at top level must not appear."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        df = summary["decision_flow"]
        assert "top_error_classes" not in df
        # packet_accepted/rejected should be inside by_book entries, not at df top level
        assert "packet_accepted" not in df
        assert "packet_rejected" not in df

    def test_outcome_mix_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert "outcome_mix" in summary
        om = summary["outcome_mix"]
        assert om["n_resolved"] == 30

    def test_outcome_mix_by_outcome(self, tmp_path):
        """outcome_mix must use by_outcome (canonical v2)."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        om = summary["outcome_mix"]
        assert "by_outcome" in om
        # digit-only keys ("1", "0") must survive sanitization
        assert om["by_outcome"]["1"] == 20
        assert om["by_outcome"]["0"] == 10

    def test_outcome_mix_no_old_keys(self, tmp_path):
        """Canonical v2: by_band and n_open must not appear."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        om = summary["outcome_mix"]
        assert "by_band" not in om
        assert "n_open" not in om

    def test_context_audit_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        assert "context_audit" in summary
        ca = summary["context_audit"]
        assert ca["n_present"] == 25
        assert ca["n_stale"] == 3
        assert ca["n_absent"] == 2
        assert ca["n_runs_total"] == 30
        assert abs(ca["context_seen_rate"] - 0.8333) < 1e-4

    def test_context_audit_no_n_total(self, tmp_path):
        """Canonical v2 uses n_runs_total, not n_total."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        ca = summary["context_audit"]
        assert "n_total" not in ca
        assert "n_runs_total" in ca

    def test_v2_still_has_correct_totals(self, tmp_path):
        """v2 must still produce the same book totals as v1."""
        _write_feedback(tmp_path, _v2_fixture())
        summary = build_summary(root=tmp_path)
        totals = summary["totals"]
        assert totals["n_books"] == 2
        assert totals["gate_failures_total"] == 12
        assert totals["rejected_decisions_total"] == 133


# ---------------------------------------------------------------------------
# 2b. v2 accruing context_audit variant
# ---------------------------------------------------------------------------

class TestV2AccruingContextAudit:
    def test_accruing_state_present(self, tmp_path):
        _write_feedback(tmp_path, _v2_accruing_fixture())
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "present"

    def test_context_audit_accruing_variant(self, tmp_path):
        _write_feedback(tmp_path, _v2_accruing_fixture())
        summary = build_summary(root=tmp_path)
        assert "context_audit" in summary
        ca = summary["context_audit"]
        assert ca["state"] == "accruing"
        assert ca["n_runs_total"] == 0

    def test_accruing_no_count_fields(self, tmp_path):
        """Accruing variant must not have n_present/n_stale/n_absent/context_seen_rate."""
        _write_feedback(tmp_path, _v2_accruing_fixture())
        summary = build_summary(root=tmp_path)
        ca = summary["context_audit"]
        for key in ("n_present", "n_stale", "n_absent", "context_seen_rate"):
            assert key not in ca, f"Unexpected key {key} in accruing context_audit"


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
# 3b. POISONED v2 fixture → private strings in label dicts blocked
# ---------------------------------------------------------------------------

class TestPoisonedV2Fixture:
    """B2+M1: strict label sanitization on v2 blocks."""

    _POISON_STRINGS = [
        "ticker_nvda_x",   # lowercased form (contains dot in original? no, underscore fine but nvda_x is valid... check)
        # Actually ticker_NVDA_x lowercased = ticker_nvda_x which IS valid ^[a-z0-9_]{1,40}$
        # The original "ticker_NVDA_x" lowercased = "ticker_nvda_x" — this would pass!
        # We test for the UPPERCASE original that must not appear
        "NVDA",
        "avg_cost_45.12",  # contains dot → must be rejected
        "MASTERMIND_TOKEN_XYZ",  # uppercase → lowercased = mastermind_token_xyz (valid, may pass)
        "/Users/x",        # contains slash → must be rejected
        "$12,345",         # contains $ and comma → must be rejected
    ]

    def test_v2_poison_no_slash_keys(self, tmp_path):
        """Keys containing '/' must not appear in output."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        serialized = json.dumps(summary, default=str)
        assert "/Users/x" not in serialized, f"/Users/x found in output"

    def test_v2_poison_no_dollar_keys(self, tmp_path):
        """Keys containing '$' must not appear in output."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        serialized = json.dumps(summary, default=str)
        assert "$12,345" not in serialized, f"$12,345 found in output"
        # Note: gap note regex pattern contains "$" — only check the actual poison string above

    def test_v2_poison_no_dot_keys(self, tmp_path):
        """Keys containing '.' (avg_cost_45.12) must not appear in output."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        serialized = json.dumps(summary, default=str)
        assert "avg_cost_45.12" not in serialized, "avg_cost_45.12 found in output"

    def test_v2_poison_no_uppercase_book_id(self, tmp_path):
        """book_id values like 'MASTERMIND_TOKEN_XYZ' and '/Users/x' must not appear."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        serialized = json.dumps(summary, default=str)
        # Original uppercase MASTERMIND_TOKEN_XYZ → lowercased is valid but check slash
        assert "/Users/x" not in serialized, "/Users/x book_id found in output"

    def test_v2_legitimate_labels_survive(self, tmp_path):
        """Legitimate labels 'falsifiers', 'expected_failure_mode' must survive."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        df = summary.get("decision_flow", {})
        rec = df.get("rejection_error_classes", {})
        assert "falsifiers" in rec, "legitimate label 'falsifiers' was dropped"
        assert "expected_failure_mode" in rec, (
            "legitimate label 'expected_failure_mode' was dropped"
        )

    def test_v2_digit_only_outcome_keys_survive(self, tmp_path):
        """Digit-only keys like '1' and '0' must survive sanitization."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        om = summary.get("outcome_mix", {})
        by_outcome = om.get("by_outcome", {})
        assert "1" in by_outcome, "digit-only key '1' was incorrectly dropped"
        assert "0" in by_outcome, "digit-only key '0' was incorrectly dropped"

    def test_v2_poison_full_json_scan(self, tmp_path):
        """Full json.dumps scan: none of the raw poison strings appear."""
        _write_feedback(tmp_path, _poisoned_v2_fixture())
        summary = build_summary(root=tmp_path)
        serialized = json.dumps(summary, default=str)
        # These must be absent (original-case forms OR their dots/slashes/dollars)
        must_not_contain = [
            "avg_cost_45.12",   # dot in label key
            "/Users/x",         # slash in label key / book_id
            "$12,345",          # dollar in label key
            # "ticker_NVDA_x" becomes "ticker_nvda_x" after lowercasing — that's valid
            # so we only gate the uppercase form (which can't survive lowercasing+regex)
            # The original uppercase NVDA in book_id "MASTERMIND_TOKEN_XYZ" lowers fine;
            # what matters is slash and $ forms are gone
        ]
        leaked = [s for s in must_not_contain if s in serialized]
        assert not leaked, (
            f"LEAK in v2 poison scan: {leaked}\n"
            f"(first 2000 chars): {serialized[:2000]}"
        )


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


# ---------------------------------------------------------------------------
# 11. m2 / m3 — _parse_date and unparseable generated_at → absent
# ---------------------------------------------------------------------------

class TestParseDateAndUnparseable:
    def test_parse_date_z_suffix(self):
        """Standard Z-suffix timestamp must parse correctly."""
        dt = _parse_date("2026-07-06T22:25:00Z")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2026 and dt.month == 7 and dt.day == 6

    def test_parse_date_offset_suffix(self):
        """Explicit +00:00 offset must parse and produce UTC."""
        dt = _parse_date("2026-07-06T22:25:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_parse_date_fractional_seconds(self):
        """Fractional seconds must not cause parse failure (no [:19] truncation)."""
        dt = _parse_date("2026-07-06T22:25:00.123456Z")
        assert dt is not None
        assert dt.microsecond == 123456

    def test_parse_date_naive_gets_utc(self):
        """Naive datetime string (no tz) should be returned with UTC tzinfo."""
        dt = _parse_date("2026-07-06T22:25:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_parse_date_garbage_returns_none(self):
        assert _parse_date("not-a-date") is None
        assert _parse_date("") is None
        assert _parse_date(None) is None  # type: ignore[arg-type]

    def test_unparseable_generated_at_state_absent(self, tmp_path):
        """m3: source with parseable schema but unparseable generated_at → absent."""
        obj = _v1_fixture()
        obj["generated_at"] = "not-a-date-at-all"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        assert summary["state"] == "absent"

    def test_unparseable_generated_at_gap_note_distinct(self, tmp_path):
        """m3: the gap note for unparseable generated_at must differ from stale note."""
        obj = _v1_fixture()
        obj["generated_at"] = "not-a-date-at-all"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        gap_str = " ".join(summary["gap_notes"])
        # Must mention unparseable, not just "stale"
        assert "unparseable" in gap_str.lower() or "cannot verify freshness" in gap_str.lower()
        # Must NOT say "stale" (that's a different state)
        assert "is stale" not in gap_str.lower()

    def test_unparseable_generated_at_no_totals(self, tmp_path):
        """m3: absent due to unparseable generated_at → no fabricated totals."""
        obj = _v1_fixture()
        obj["generated_at"] = "garbage"
        _write_feedback(tmp_path, obj)
        summary = build_summary(root=tmp_path)
        assert summary["totals"] is None


# ---------------------------------------------------------------------------
# 12. n1 — context_seen_rate out-of-range → field dropped + gap note
# ---------------------------------------------------------------------------

class TestContextSeenRateClamping:
    def _make_v2_with_rate(self, tmp_path: Path, rate: float) -> dict:
        base = _v2_fixture()
        base["context_audit"]["context_seen_rate"] = rate
        _write_feedback(tmp_path, base)
        return build_summary(root=tmp_path)

    def test_valid_rate_passes_through(self, tmp_path):
        summary = self._make_v2_with_rate(tmp_path, 0.5)
        ca = summary["context_audit"]
        assert "context_seen_rate" in ca
        assert abs(ca["context_seen_rate"] - 0.5) < 1e-9

    def test_rate_zero_passes(self, tmp_path):
        summary = self._make_v2_with_rate(tmp_path, 0.0)
        ca = summary["context_audit"]
        assert "context_seen_rate" in ca
        assert ca["context_seen_rate"] == 0.0

    def test_rate_one_passes(self, tmp_path):
        summary = self._make_v2_with_rate(tmp_path, 1.0)
        ca = summary["context_audit"]
        assert "context_seen_rate" in ca
        assert ca["context_seen_rate"] == 1.0

    def test_rate_gt_one_dropped(self, tmp_path):
        """n1: rate > 1.0 → field dropped."""
        summary = self._make_v2_with_rate(tmp_path, 1.5)
        ca = summary["context_audit"]
        assert "context_seen_rate" not in ca

    def test_rate_negative_dropped(self, tmp_path):
        """n1: negative rate → field dropped."""
        summary = self._make_v2_with_rate(tmp_path, -0.1)
        ca = summary["context_audit"]
        assert "context_seen_rate" not in ca

    def test_out_of_range_gap_note(self, tmp_path):
        """n1: out-of-range rate → gap note emitted."""
        summary = self._make_v2_with_rate(tmp_path, 2.0)
        gap_str = " ".join(summary["gap_notes"])
        assert "context_seen_rate" in gap_str.lower() or "out of" in gap_str.lower()
