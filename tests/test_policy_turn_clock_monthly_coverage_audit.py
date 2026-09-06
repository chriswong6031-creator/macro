"""Outcome-blind contract tests for the policy-turn-clock R0 coverage audit.

The production change these tests catch is any audit that silently counts daily
rows as episodes, accepts a filesystem timestamp as a decision clock, substitutes
a longer source history, backfills a forward-only source, or emits decision/outcome
vocabulary.  Fixtures are intentionally synthetic and contain metadata only.
"""
from __future__ import annotations

import json
import unittest

import scripts.policy_turn_clock_monthly_coverage_audit as audit


def record(owner: str, cycles: list[str], **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "owner": owner,
        "path": f"/metadata/{owner}.json",
        "schema": "source.metadata.v1",
        "version": "1",
        "rights": "internal-metadata-only",
        "observed_at": "2026-08-01T00:00:00+00:00",
        "available_at": "2026-08-02T09:30:00+00:00",
        "correction_id": None,
        "correction_at": None,
        "row_count": 3,
        "entity_count": 1,
        "root_count": 1,
        "cycle_ids": cycles,
        "classification": "historical",
        "missingness": "present",
    }
    value.update(overrides)
    return value


class PolicyTurnClockMonthlyCoverageAuditTests(unittest.TestCase):
    def test_uses_unique_monthly_cycles_not_daily_rows(self) -> None:
        report = audit.build_report(
            [record("calendar", ["2024-01", "2024-01", "2024-02"])],
            {"H1": ["calendar"]},
        )
        cell = report["hypotheses"][0]
        self.assertEqual(cell["cycle_count"], 2)
        self.assertEqual(cell["cycles_by_era"]["0DTE_current"], 2)

    def test_rejects_non_explicit_or_filesystem_availability(self) -> None:
        for bad in (
            record("calendar", ["2024-01"], available_at=None),
            record("calendar", ["2024-01"], available_at="2024-01-03"),
            record("calendar", ["2024-01"], mtime="2026-09-03T00:00:00+00:00"),
        ):
            with self.assertRaises(ValueError):
                audit.validate_record(bad)

    def test_requires_the_exact_intersection_and_never_uses_longest_source(self) -> None:
        report = audit.build_report(
            [
                record("calendar", ["2023-01", "2023-02", "2023-03"]),
                record("options", ["2023-02"]),
            ],
            {"H2": ["calendar", "options"]},
        )
        cell = report["hypotheses"][0]
        self.assertEqual(cell["cycle_count"], 1)
        self.assertEqual(cell["availability"], "BELOW_FLOOR")

    def test_missing_required_owner_is_unavailable_not_zero(self) -> None:
        report = audit.build_report(
            [record("calendar", ["2023-01"])],
            {"H1": ["calendar", "treasury"]},
        )
        cell = report["hypotheses"][0]
        self.assertEqual(cell["availability"], "UNAVAILABLE")
        self.assertIsNone(cell["cycle_count"])
        self.assertEqual(cell["missing_owners"], ["treasury"])

    def test_forward_only_source_cannot_be_retrofitted_as_history(self) -> None:
        report = audit.build_report(
            [
                record("calendar", ["2024-01", "2024-02"]),
                record("flow", ["2024-01", "2024-02"], classification="forward_only"),
            ],
            {"H5": ["calendar", "flow"]},
        )
        cell = report["hypotheses"][0]
        self.assertEqual(cell["availability"], "UNAVAILABLE")
        self.assertIn("forward_only", cell["reason"])

    def test_report_is_stably_serializable_and_has_no_decision_fields(self) -> None:
        records = [record("calendar", ["2023-01"]), record("options", ["2023-01"])]
        first = audit.build_report(records, {"H2": ["calendar", "options"]})
        second = audit.build_report(list(reversed(records)), {"H2": ["calendar", "options"]})
        self.assertEqual(audit.canonical_digest(first), audit.canonical_digest(second))
        payload = json.dumps(first).lower()
        for fragment in audit.FORBIDDEN_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, payload)

    def test_unknown_availability_is_preserved_without_inventing_a_clock(self) -> None:
        item = record("calendar", ["2024-01"], available_at=None, missingness="unknown")
        report = audit.build_report([item], {"H1": ["calendar"]})
        self.assertEqual(report["sources"][0]["available_at"], None)
        self.assertEqual(report["sources"][0]["row_count"], 3)
        self.assertEqual(report["hypotheses"][0]["availability"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
