"""FIF-1 golden financial intelligence packet: independent filing-package fixture."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import subprocess
import sys

import pytest

from engine.fundamental_forensics import financial_intelligence_packet as packet_module
from engine.fundamental_forensics.financial_intelligence_packet import (
    FORBIDDEN_COMPANYFACTS_MARKERS,
    PACKET_SCHEMA,
    PacketQueryRequest,
    build_financial_intelligence_packet,
    build_synthetic_filing_package_fixture,
    canonical_packet_bytes,
    default_packet_periods,
    default_packet_query,
    load_core_registry,
    load_filing_package_fixture,
    packet_digest,
    sha256_file,
)
from engine.fundamental_forensics.query import QueryPolicy
from engine.fundamental_forensics.raw_ledger import canonical_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
LEDGER_PATH = FIXTURES / "filing_package_raw_ledger_v1.json"
GOLDEN_PATH = FIXTURES / "expected_financial_intelligence_packet_v1.json"
COMPANYFACTS_WITNESS = FIXTURES / "companyfacts_versions.json"
SUBMISSIONS_WITNESS = FIXTURES / "submissions_versions.json"
CLI = ROOT / "scripts" / "build_financial_intelligence_packet.py"
PYTHON = sys.executable


def _cell(packet: dict, metric_id: str, label: str) -> dict:
    matches = [
        cell
        for cell in packet["cells"]
        if cell["metric_id"] == metric_id and cell["period"].get("label") == label
    ]
    assert len(matches) == 1, (metric_id, label, len(matches))
    return matches[0]


def _input_digests() -> dict[str, str]:
    return {
        "filing_package_fixture_sha256": sha256_file(LEDGER_PATH),
        "companyfacts_witness_sha256": sha256_file(COMPANYFACTS_WITNESS),
        "submissions_witness_sha256": sha256_file(SUBMISSIONS_WITNESS),
    }


def _build(
    *,
    policy: str = "latest_known_as_of",
    source_event_cutoff: str = "2025-12-31T23:59:59Z",
    system_recorded_cutoff: str = "2026-08-05T12:00:02Z",
    built_at: str | None = None,
) -> dict:
    fixture = load_filing_package_fixture(LEDGER_PATH)
    return build_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=source_event_cutoff,
                recorded_at=system_recorded_cutoff,
                selection=policy,
            ),
            metrics=packet_module.DEFAULT_REQUESTED_METRICS,
            periods=default_packet_periods(),
        ),
        metric_registry=load_core_registry(ROOT),
        built_at=built_at,
        input_digests=_input_digests(),
    )


def test_committed_ledger_matches_independent_constructor() -> None:
    constructed = canonical_json(build_synthetic_filing_package_fixture().to_dict())
    committed = LEDGER_PATH.read_text(encoding="utf-8").strip()
    assert committed == constructed
    for marker in FORBIDDEN_COMPANYFACTS_MARKERS:
        assert marker not in committed
    payload = json.loads(committed)
    assert payload["identity"]["identity_basis"] == "synthetic_filing_package_fixture_v1"
    assert payload["identity"]["authority"] == "filing_package_authoritative"
    assert payload["identity"]["ticker"] == "FIP1"


def test_companyfacts_fixture_remains_a_separate_witness() -> None:
    companyfacts = COMPANYFACTS_WITNESS.read_text(encoding="utf-8")
    assert "0000000001-24-000001" in companyfacts
    assert "0000000001-25-000001" in companyfacts
    packet = _build()
    blob = canonical_packet_bytes(packet).decode("utf-8")
    assert "0000000001-24-000001" not in blob
    assert "0000000001-25-000001" not in blob
    assert packet["receipts"]["companyfacts_witness_sha256"] == sha256_file(COMPANYFACTS_WITNESS)
    assert packet["receipts"]["submissions_witness_sha256"] == sha256_file(SUBMISSIONS_WITNESS)
    assert packet["receipts"]["filing_package_fixture_sha256"] == sha256_file(LEDGER_PATH)


def test_law1_original_fy2023_revenue_is_1050_as_reported() -> None:
    packet = _build(policy="as_reported", source_event_cutoff="2024-12-31T23:59:59Z")
    cell = _cell(packet, "revenue", "FY2023")
    assert cell["value"] == "1050"
    assert cell["non_value_state"] is None
    assert cell["accession"] == "0000999999-24-000010"


def test_law2_and_law3_later_revision_does_not_leak_before_2025_filing() -> None:
    known_2025 = _build(policy="latest_known_as_of", source_event_cutoff="2025-12-31T23:59:59Z")
    known_2024 = _build(policy="latest_known_as_of", source_event_cutoff="2024-12-31T23:59:59Z")
    assert _cell(known_2025, "revenue", "FY2023")["value"] == "1060"
    assert _cell(known_2025, "revenue", "FY2023")["accession"] == "0000999999-25-000010"
    assert _cell(known_2024, "revenue", "FY2023")["value"] == "1050"
    assert _cell(known_2024, "revenue", "FY2023")["accession"] == "0000999999-24-000010"
    assert known_2024["revisions"] == []
    revenue_rev = next(item for item in known_2025["revisions"] if item["metric_id"] == "revenue")
    assert revenue_rev["original_value"] == "1050"
    assert revenue_rev["revised_value"] == "1060"
    assert revenue_rev["used_as_selected_value"] is True


def test_law4_pre_original_cutoff_is_explicit_absence() -> None:
    packet = _build(policy="as_reported", source_event_cutoff="2024-01-01T00:00:00Z")
    cell = _cell(packet, "revenue", "FY2023")
    assert cell["value"] is None
    assert cell["non_value_state"] == "missing"
    assert cell["reason"]


def test_law5_duplicate_fy2022_revenue_is_not_double_counted() -> None:
    packet = _build()
    cell = _cell(packet, "revenue", "FY2022")
    assert cell["value"] == "1000"
    assert cell["non_value_state"] is None
    assert cell["accession"] == "0000999999-23-000010"
    assert len(cell["source_occurrence_ids"]) == 2
    assert cell["source_occurrence_ids"] == sorted(cell["source_occurrence_ids"])
    assert canonical_packet_bytes(packet) == canonical_packet_bytes(_build())


def test_law6_latest_restated_is_labeled_hindsight() -> None:
    packet = _build(policy="latest_restated", source_event_cutoff="2025-12-31T23:59:59Z")
    cell = _cell(packet, "revenue", "FY2023")
    assert cell["value"] == "1060"
    revision = next(item for item in packet["revisions"] if item["metric_id"] == "revenue")
    assert revision["original_accession"] == "0000999999-24-000010"
    assert revision["revised_accession"] == "0000999999-25-000010"
    assert revision["uses_later_restatement"] is True
    assert packet["query"]["policy"] == "latest_restated"
    assert packet["query"]["evaluation_mode"] == "retrospective_research"


def test_law7_receivables_follow_the_same_temporal_rule() -> None:
    known_2024 = _build(policy="latest_known_as_of", source_event_cutoff="2024-12-31T23:59:59Z")
    known_2025 = _build(policy="latest_known_as_of", source_event_cutoff="2025-12-31T23:59:59Z")
    assert _cell(known_2024, "accounts_receivable_net", "2023-12-31")["value"] == "120"
    assert _cell(known_2025, "accounts_receivable_net", "2023-12-31")["value"] == "121"
    revision = next(
        item for item in known_2025["revisions"] if item["metric_id"] == "accounts_receivable_net"
    )
    assert revision["original_value"] == "120"
    assert revision["revised_value"] == "121"


def test_law8_customer_count_stays_unmapped() -> None:
    packet = _build()
    unsupported = [
        cell for cell in packet["cells"] if cell["metric_id"] == "CustomerCount"
    ]
    assert unsupported
    assert all(cell["non_value_state"] == "unsupported" for cell in unsupported)
    assert packet["coverage"]["unmapped_extension_concept_count"] == 1
    assert packet["coverage"]["unmapped_extension_concepts"][0]["concept_qname"] == "custom:CustomerCount"
    assert packet["coverage"]["unmapped_extension_concepts"][0]["mapped"] is False
    assert "CustomerCount" in packet["coverage"]["unsupported_metrics"]


def test_law9_formula_gross_margin_carries_dependency_receipts() -> None:
    packet = _build()
    cell = _cell(packet, "gross_margin", "FY2023")
    assert cell["value"] is not None
    assert cell["provenance_kind"] == "formula"
    assert cell["formula_rule_id"] == "formula.gross_margin/v1"
    assert cell["formula_rule_digest"]
    assert len(cell["dependency_cell_ids"]) == 2
    revenue = _cell(packet, "revenue", "FY2023")
    assert revenue["value"] == "1060"
    assert revenue["source_occurrence_ids"]
    assert cell["accession"] == revenue["accession"]


def test_law10_every_valued_cell_is_reversible() -> None:
    packet = _build()
    valued = [cell for cell in packet["cells"] if cell["value"] is not None]
    assert valued
    for cell in valued:
        assert cell["non_value_state"] is None
        assert cell["cell_id"]
        if cell["provenance_kind"] == "direct":
            assert cell["source_occurrence_ids"]
            assert cell["accession"]
            assert cell["source_digest"]
        elif cell["provenance_kind"] == "formula":
            assert cell["dependency_cell_ids"]
            assert cell["formula_rule_id"]
            assert cell["formula_rule_digest"]
        else:
            raise AssertionError(cell["provenance_kind"])


def test_law11_same_input_same_bytes_in_process_and_across_processes(tmp_path: Path) -> None:
    first = canonical_packet_bytes(_build())
    second = canonical_packet_bytes(_build())
    assert first == second
    expected = GOLDEN_PATH.read_bytes().strip()
    assert first == expected

    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    cmd = [
        PYTHON,
        str(CLI),
        "--ledger",
        str(LEDGER_PATH),
        "--companyfacts-witness",
        str(COMPANYFACTS_WITNESS),
        "--submissions-witness",
        str(SUBMISSIONS_WITNESS),
        "--policy",
        "latest_known_as_of",
        "--source-event-cutoff",
        "2025-12-31T23:59:59Z",
        "--system-recorded-cutoff",
        "2026-08-05T12:00:02Z",
        "--repo-root",
        str(ROOT),
    ]
    first_run = subprocess.run(
        [*cmd, "--output", str(out_a)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    second_run = subprocess.run(
        [*cmd, "--output", str(out_b)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out_a.read_bytes().strip() == out_b.read_bytes().strip() == expected
    assert "packet_id=" in first_run.stdout
    assert "digest=" in second_run.stdout
    assert COMPANYFACTS_WITNESS.name not in json.loads(out_a.read_text())["entity"]["name"]


def test_law12_implicit_current_clock_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            raise AssertionError("datetime.now called")

        @classmethod
        def utcnow(cls):
            raise AssertionError("datetime.utcnow called")

    monkeypatch.setattr(packet_module.datetime_module, "datetime", _BoomDateTime)
    monkeypatch.setattr(packet_module, "datetime", _BoomDateTime)
    packet = _build()
    assert packet["schema"] == PACKET_SCHEMA
    assert "built_at" not in packet


def test_built_at_does_not_change_packet_identity() -> None:
    plain = _build()
    stamped = _build(built_at="2026-08-16T18:00:00Z")
    assert stamped["built_at"] == "2026-08-16T18:00:00.000000Z"
    assert stamped["packet_id"] == plain["packet_id"]
    assert stamped["content_sha256"] == plain["content_sha256"]
    assert packet_digest(stamped) == packet_digest(plain)
    assert canonical_packet_bytes(stamped) != canonical_packet_bytes(plain)


def test_authority_is_display_only_and_cutoffs_have_no_now_default() -> None:
    packet = _build()
    assert packet["authority"] == {"class": "context_only", "display_only": True}
    assert packet["disclosure_changes"] == []
    help_text = subprocess.run(
        [PYTHON, str(CLI), "--help"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    assert "--source-event-cutoff" in help_text
    assert "--system-recorded-cutoff" in help_text
    missing = subprocess.run(
        [PYTHON, str(CLI), "--ledger", str(LEDGER_PATH), "--policy", "latest_known_as_of"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0


def test_golden_packet_is_schema_valid_and_content_addressed() -> None:
    packet = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert packet["packet_id"] == f"fip_{packet['content_sha256'][:24]}"
    assert packet["content_sha256"] == packet_digest(packet)
    rebuilt = _build()
    assert canonical_packet_bytes(rebuilt) == GOLDEN_PATH.read_bytes().strip()


def test_constructor_fixture_round_trips_through_loader() -> None:
    fixture = load_filing_package_fixture(LEDGER_PATH)
    assert fixture.entity.ticker == "FIP1"
    assert all(event.dimensions_known is True for event in fixture.ledger.events)
    assert all(event.source.source == "sec-edgar" for event in fixture.ledger.events)
    restatements = [event for event in fixture.ledger.events if event.revision_of]
    assert len(restatements) >= 2
    duplicates = [
        event
        for event in fixture.ledger.events
        if event.source_occurrence_key and event.source_occurrence_key.startswith("fy2022-revenue-span-")
    ]
    assert len(duplicates) == 2
    assert {str(event.parsed_value) for event in duplicates} == {"1000"}
