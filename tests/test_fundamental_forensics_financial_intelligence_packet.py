"""FIF-1 golden financial intelligence packet: independent filing-package fixture."""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path
import socket
import subprocess
import sys
import types
import urllib.request

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.fundamental_forensics import financial_intelligence_packet as packet_module
from engine.fundamental_forensics.financial_intelligence_packet import (
    FORBIDDEN_COMPANYFACTS_MARKERS,
    PACKET_SCHEMA,
    PacketBuildContext,
    PacketEvidenceDigests,
    PacketQueryRequest,
    all_packet_cells,
    assemble_financial_intelligence_packet,
    assert_formula_evidence_closed,
    build_financial_intelligence_packet_from_repo,
    canonical_packet_bytes,
    default_packet_periods,
    digest_builder_source,
    formula_leaves,
    load_core_registry,
    load_filing_package_fixture,
    load_packet_schema,
    packet_cell_index,
    packet_digest,
    sha256_file,
    validate_packet,
)
from engine.fundamental_forensics.synthetic_filing_package import (
    SYNTHETIC_ENTITY_ID,
    build_synthetic_filing_package_fixture,
    filing as synthetic_filing,
    usd_fact,
    _USD,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.raw_ledger import (
    FactContext,
    FactEventType,
    RawFactLedger,
    canonical_json,
    make_raw_fact,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
LEDGER_PATH = FIXTURES / "filing_package_raw_ledger_v1.json"
GOLDEN_PATH = FIXTURES / "expected_financial_intelligence_packet_v1.json"
COMPANYFACTS_WITNESS = FIXTURES / "companyfacts_versions.json"
SUBMISSIONS_WITNESS = FIXTURES / "submissions_versions.json"
SCHEMA_PATH = ROOT / "contracts" / "financial_intelligence_packet.schema.json"
BUILDER_PATH = ROOT / "engine" / "fundamental_forensics" / "financial_intelligence_packet.py"
CLI = ROOT / "scripts" / "build_financial_intelligence_packet.py"
PYTHON = sys.executable
FORBIDDEN_PACKET_MARKERS = (
    "/Users/",
    "/home/",
    "AKIA",
    "BEGIN PRIVATE",
    "aws_secret",
    "AWS_SECRET",
    ".ssh/",
    str(LEDGER_PATH),
    str(ROOT),
)


def _cell(packet: dict, metric_id: str, label: str, *, plane: str = "cells") -> dict:
    matches = [
        cell
        for cell in packet[plane]
        if cell["metric_id"] == metric_id and cell["period"].get("label") == label
    ]
    assert len(matches) == 1, (plane, metric_id, label, len(matches))
    return matches[0]


def _find_cell(packet: dict, metric_id: str, label: str) -> dict:
    matches = [
        cell
        for cell in all_packet_cells(packet)
        if cell["metric_id"] == metric_id and cell["period"].get("label") == label
    ]
    assert len(matches) == 1, (metric_id, label, len(matches))
    return matches[0]


def _input_digests() -> PacketEvidenceDigests:
    return PacketEvidenceDigests(
        filing_package_fixture_sha256=sha256_file(LEDGER_PATH),
        companyfacts_witness_sha256=sha256_file(COMPANYFACTS_WITNESS),
        submissions_witness_sha256=sha256_file(SUBMISSIONS_WITNESS),
    )


def _context() -> PacketBuildContext:
    return PacketBuildContext(
        packet_builder_digest=digest_builder_source(BUILDER_PATH.read_bytes()),
        packet_schema=load_packet_schema(SCHEMA_PATH),
    )


def _build(
    *,
    policy: str = "latest_known_as_of",
    source_event_cutoff: str = "2025-12-31T23:59:59Z",
    system_recorded_cutoff: str = "2026-08-05T12:00:02Z",
    built_at: str | None = None,
    metrics: tuple[str, ...] | None = None,
    periods: tuple[PeriodRequest, ...] | None = None,
    fixture=None,
    input_digests: PacketEvidenceDigests | None = None,
) -> dict:
    loaded = fixture if fixture is not None else load_filing_package_fixture(LEDGER_PATH)
    return assemble_financial_intelligence_packet(
        entity=loaded.entity,
        ledger=loaded.ledger,
        filing_metadata=loaded.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=source_event_cutoff,
                recorded_at=system_recorded_cutoff,
                selection=policy,
            ),
            metrics=metrics or packet_module.DEFAULT_REQUESTED_METRICS,
            periods=periods or default_packet_periods(),
        ),
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        built_at=built_at,
        input_digests=input_digests if input_digests is not None else _input_digests(),
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
    assert revenue_rev["root_value"] == "1050"
    assert revenue_rev["prior_value"] == "1050"
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
    assert revision["root_accession"] == "0000999999-24-000010"
    assert revision["prior_accession"] == "0000999999-24-000010"
    assert revision["revised_accession"] == "0000999999-25-000010"
    assert revision["uses_later_reported_revision"] is True
    assert packet["query"]["policy"] == "latest_restated"
    assert packet["query"]["evaluation_mode"] == "historical_replay"


def test_law7_receivables_follow_the_same_temporal_rule() -> None:
    known_2024 = _build(policy="latest_known_as_of", source_event_cutoff="2024-12-31T23:59:59Z")
    known_2025 = _build(policy="latest_known_as_of", source_event_cutoff="2025-12-31T23:59:59Z")
    assert _cell(known_2024, "accounts_receivable_net", "2023-12-31")["value"] == "120"
    assert _cell(known_2025, "accounts_receivable_net", "2023-12-31")["value"] == "121"
    revision = next(
        item for item in known_2025["revisions"] if item["metric_id"] == "accounts_receivable_net"
    )
    assert revision["root_value"] == "120"
    assert revision["prior_value"] == "120"
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
    index = packet_cell_index(packet)
    resolved = [index[dep_id] for dep_id in cell["dependency_cell_ids"]]
    by_metric = {item["metric_id"]: item for item in resolved}
    assert set(by_metric) == {"gross_profit", "revenue"}
    assert by_metric["revenue"]["cell_id"] == revenue["cell_id"]
    assert by_metric["gross_profit"]["cell_id"] not in {item["cell_id"] for item in packet["cells"]}
    assert by_metric["gross_profit"] in packet["evidence_cells"]
    assert by_metric["gross_profit"]["value"] == "500"
    assert by_metric["gross_profit"]["provenance_kind"] == "direct"
    assert by_metric["gross_profit"]["source_occurrence_ids"]
    assert "gross_profit" not in packet["query"]["requested_metrics"]
    assert all(item["metric_id"] != "gross_profit" for item in packet["cells"])


def test_law10_every_valued_cell_is_reversible() -> None:
    packet = _build()
    assert_formula_evidence_closed(packet["cells"], packet["evidence_cells"])
    valued = [cell for cell in all_packet_cells(packet) if cell["value"] is not None]
    assert valued
    for cell in valued:
        assert cell["non_value_state"] is None
        assert cell["cell_id"]
        if cell["provenance_kind"] == "direct":
            assert cell["source_occurrence_ids"]
            assert cell["accession"]
            assert cell["source_digest"]
            assert cell["mapping_rule_id"]
            assert cell["mapping_rule_digest"]
        elif cell["provenance_kind"] == "formula":
            assert cell["dependency_cell_ids"]
            assert cell["formula_rule_id"]
            assert cell["formula_rule_digest"]
            leaves = formula_leaves(packet, cell)
            assert leaves
            assert all(leaf["provenance_kind"] == "direct" for leaf in leaves)
            assert all(leaf["source_occurrence_ids"] and leaf["source_digest"] for leaf in leaves)
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
    validate_packet(packet, load_packet_schema(SCHEMA_PATH))
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


def _income_fixture(*, revenue: str, gross_profit: str, decimals: str = "0"):
    fixture = build_synthetic_filing_package_fixture()
    fy2024 = FactContext(
        context_id="c-fy2024-numeric",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2024-01-01",
        end="2024-12-31",
    )
    filing = synthetic_filing(
        accession="0000999999-26-000010",
        document_id="fip1-numeric.htm",
        accepted_at="2026-02-15T16:00:00Z",
        recorded_at="2026-02-15T16:05:00Z",
        filed_at="2026-02-15",
    )

    def _fact(concept: str, value: str, key: str, span: tuple[int, int]):
        return make_raw_fact(
            source=filing["source"],
            concept_qname=concept,
            context=fy2024,
            unit=_USD,
            raw_token=value,
            parsed_value=value,
            dimensions_known=True,
            decimals=decimals,
            source_span=span,
            source_occurrence_key=key,
            accepted_at=filing["accepted_at"],
            recorded_at=filing["recorded_at"],
            event_type=FactEventType.FILED,
        )

    events = (
        _fact("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", revenue, "num-rev", (0, 4)),
        _fact("us-gaap:GrossProfit", gross_profit, "num-gp", (8, 11)),
    )
    metadata = {
        event.occurrence_id: {
            "accession": event.source.accession,
            "document_id": event.source.document_id,
            "source_body_sha256": event.source.body_sha256,
            "available_at": filing["recorded_at"],
            "form": "10-K",
            "filed_at": filing["filed_at"],
        }
        for event in events
    }
    return packet_module.FilingPackageFixture(
        entity=fixture.entity,
        ledger=RawFactLedger(events),
        filing_metadata=metadata,
    )


def test_nested_formula_net_debt_closes_through_total_debt() -> None:
    packet = _build(
        metrics=("net_debt",),
        periods=(PeriodRequest.instant("2024-12-31", label="2024-12-31"),),
    )
    assert [cell["metric_id"] for cell in packet["cells"]] == ["net_debt"]
    net_debt = _cell(packet, "net_debt", "2024-12-31")
    assert net_debt["value"] == "85"
    assert net_debt["provenance_kind"] == "formula"
    assert net_debt["formula_rule_id"] == "formula.net_debt/v1"
    evidence_ids = {cell["metric_id"] for cell in packet["evidence_cells"]}
    assert evidence_ids == {
        "total_debt",
        "short_term_debt",
        "long_term_debt_current",
        "long_term_debt",
        "cash_and_cash_equivalents",
    }
    assert "net_debt" not in evidence_ids
    total_debt = _find_cell(packet, "total_debt", "2024-12-31")
    assert total_debt["value"] == "100"
    assert total_debt["provenance_kind"] == "formula"
    assert total_debt in packet["evidence_cells"]
    leaves = formula_leaves(packet, net_debt)
    by_metric = {leaf["metric_id"]: leaf for leaf in leaves}
    assert by_metric["short_term_debt"]["value"] == "10"
    assert by_metric["long_term_debt_current"]["value"] == "20"
    assert by_metric["long_term_debt"]["value"] == "70"
    assert by_metric["cash_and_cash_equivalents"]["value"] == "15"
    assert all(leaf["provenance_kind"] == "direct" for leaf in leaves)
    assert_formula_evidence_closed(packet["cells"], packet["evidence_cells"])


def test_pure_kernel_does_not_touch_filesystem_env_network_or_object_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = load_filing_package_fixture(LEDGER_PATH)
    registry = load_core_registry(ROOT)
    context = _context()
    digests = _input_digests()
    request = PacketQueryRequest(
        policy=QueryPolicy(
            source_snapshot_at="2025-12-31T23:59:59Z",
            recorded_at="2026-08-05T12:00:02Z",
            selection="latest_known_as_of",
        ),
        metrics=packet_module.DEFAULT_REQUESTED_METRICS,
        periods=default_packet_periods(),
    )

    def explode(*_args, **_kwargs):
        raise AssertionError("pure kernel I/O is forbidden")

    monkeypatch.setattr("builtins.open", explode)
    monkeypatch.setattr(Path, "read_bytes", explode)
    monkeypatch.setattr(Path, "read_text", explode)
    monkeypatch.setattr(Path, "open", explode)
    monkeypatch.setattr(os, "getenv", explode)
    monkeypatch.setattr(os, "environ", {"get": explode, "__getitem__": explode})
    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(urllib.request, "urlopen", explode)
    fake_boto = types.SimpleNamespace(client=explode, resource=explode)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto)
    packet = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=request,
        metric_registry=registry,
        context=context,
        input_digests=digests,
    )
    assert packet["schema"] == PACKET_SCHEMA
    assert packet["content_sha256"] == packet_digest(packet)


def test_packet_bytes_are_independent_of_absolute_paths_and_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = canonical_packet_bytes(_build())
    monkeypatch.setenv("TZ", "America/New_York")
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    monkeypatch.setenv("PYTHONHASHSEED", "1")
    assert canonical_packet_bytes(_build()) == expected
    out_a = tmp_path / "nested" / "a.json"
    out_b = tmp_path / "other-root" / "b.json"
    cmd = [
        PYTHON,
        str(CLI.resolve()),
        "--ledger",
        str(LEDGER_PATH.resolve()),
        "--companyfacts-witness",
        str(COMPANYFACTS_WITNESS.resolve()),
        "--submissions-witness",
        str(SUBMISSIONS_WITNESS.resolve()),
        "--policy",
        "latest_known_as_of",
        "--source-event-cutoff",
        "2025-12-31T23:59:59Z",
        "--system-recorded-cutoff",
        "2026-08-05T12:00:02Z",
        "--repo-root",
        str(ROOT.resolve()),
    ]
    subprocess.run([*cmd, "--output", str(out_a)], check=True, cwd=tmp_path, capture_output=True, text=True)
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    subprocess.run([*cmd, "--output", str(out_b)], check=True, cwd=other_cwd, capture_output=True, text=True)
    assert out_a.read_bytes().strip() == out_b.read_bytes().strip() == expected


def test_packet_bytes_never_contain_local_paths_or_credentials() -> None:
    blob = canonical_packet_bytes(_build()).decode("utf-8")
    for marker in FORBIDDEN_PACKET_MARKERS:
        assert marker not in blob
    home = os.environ.get("HOME")
    if home:
        assert home not in blob


def test_schema_rejects_both_null_and_both_set_cells() -> None:
    packet = _build()
    schema = load_packet_schema(SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valued = next(cell for cell in packet["cells"] if cell["value"] is not None)
    both_null = copy.deepcopy(valued)
    both_null["value"] = None
    both_null["non_value_state"] = None
    both_set = copy.deepcopy(valued)
    both_set["non_value_state"] = "missing"
    missing_accession = copy.deepcopy(valued)
    missing_accession["provenance_kind"] = "direct"
    missing_accession["accession"] = None
    missing_formula = copy.deepcopy(_cell(packet, "gross_margin", "FY2023"))
    missing_formula["formula_rule_id"] = None
    missing_formula["dependency_cell_ids"] = []
    malformed_authority = copy.deepcopy(packet)
    malformed_authority["authority"] = {"class": "tradeable", "display_only": False}
    malformed_root = copy.deepcopy(packet)
    del malformed_root["query"]
    cases = {
        "both_null": {**copy.deepcopy(packet), "cells": [both_null, *packet["cells"][1:]]},
        "both_set": {**copy.deepcopy(packet), "cells": [both_set, *packet["cells"][1:]]},
        "valued_direct_without_accession": {
            **copy.deepcopy(packet),
            "cells": [missing_accession, *packet["cells"][1:]],
        },
        "valued_formula_without_dependencies": {
            **copy.deepcopy(packet),
            "cells": [missing_formula, *packet["cells"][1:]],
        },
        "malformed_authority": malformed_authority,
        "missing_query": malformed_root,
    }
    for name, invalid in cases.items():
        errors = list(validator.iter_errors(invalid))
        assert errors, name


def test_validate_packet_requires_injected_schema() -> None:
    packet = _build()
    with pytest.raises(TypeError, match="injected"):
        validate_packet(packet, None)  # type: ignore[arg-type]


def test_zero_negative_and_high_precision_numeric_cells() -> None:
    zero = _build(
        fixture=_income_fixture(revenue="0", gross_profit="10"),
        metrics=("gross_margin", "revenue"),
        periods=(PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024"),),
        source_event_cutoff="2026-12-31T23:59:59Z",
        input_digests=PacketEvidenceDigests(),
    )
    zero_margin = _cell(zero, "gross_margin", "FY2024")
    assert zero_margin["value"] is None
    assert zero_margin["non_value_state"] == "not_evaluable"
    assert "division_by_zero" in (zero_margin["reason"] or "")
    assert_formula_evidence_closed(zero["cells"], zero["evidence_cells"])

    negative = _build(
        fixture=_income_fixture(revenue="-100", gross_profit="-40"),
        metrics=("gross_margin", "revenue"),
        periods=(PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024"),),
        source_event_cutoff="2026-12-31T23:59:59Z",
        input_digests=PacketEvidenceDigests(),
    )
    negative_margin = _cell(negative, "gross_margin", "FY2024")
    assert negative_margin["value"] == "0.4"
    assert negative_margin["non_value_state"] is None
    assert _cell(negative, "revenue", "FY2024")["value"] == "-100"

    precise = _build(
        fixture=_income_fixture(revenue="3", gross_profit="1", decimals="8"),
        metrics=("gross_margin",),
        periods=(PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024"),),
        source_event_cutoff="2026-12-31T23:59:59Z",
        input_digests=PacketEvidenceDigests(),
    )
    precise_margin = _cell(precise, "gross_margin", "FY2024")
    assert precise_margin["value"] is not None
    assert precise_margin["value"].startswith("0.3333333333333333333333333333333333")
    leaves = formula_leaves(precise, precise_margin)
    assert {leaf["metric_id"] for leaf in leaves} == {"gross_profit", "revenue"}


def test_repo_adapter_matches_pure_kernel() -> None:
    fixture = load_filing_package_fixture(LEDGER_PATH)
    request = PacketQueryRequest(
        policy=QueryPolicy(
            source_snapshot_at="2025-12-31T23:59:59Z",
            recorded_at="2026-08-05T12:00:02Z",
            selection="latest_known_as_of",
        ),
        metrics=packet_module.DEFAULT_REQUESTED_METRICS,
        periods=default_packet_periods(),
    )
    assembled = assemble_financial_intelligence_packet(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=request,
        metric_registry=load_core_registry(ROOT),
        context=_context(),
        input_digests=_input_digests(),
    )
    adapted = build_financial_intelligence_packet_from_repo(
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        query_request=request,
        repo_root=ROOT,
        metric_registry=load_core_registry(ROOT),
        input_digests=_input_digests(),
    )
    assert canonical_packet_bytes(assembled) == canonical_packet_bytes(adapted)
    assert assembled["coverage"]["formula_evidence_closed"] is True
    assert assembled["coverage"]["evidence_cells"] == len(assembled["evidence_cells"])
