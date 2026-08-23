"""FIF-3A1: golden AAPL as-reported statement reconstruction and service."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.fundamental_forensics.financial_intelligence_packet import load_core_registry
from engine.fundamental_forensics.packet_service import execute_financial_packet
from engine.fundamental_forensics.query_service import (
    FinancialQueryAdmissionError,
    execute_financial_query,
    fip1_fixture_dataset,
)
from engine.fundamental_forensics.revision_service import (
    execute_financial_revisions,
    fip1_packet_dataset,
)
from engine.fundamental_forensics.statement_graph import (
    PRIMARY_STATEMENT_ROLES,
    STATEMENT_TITLES,
    StatementGraphError,
    _cell_from_facts,
    admit_golden_aapl_package,
    load_golden_aapl_package,
    mint_fixture_recorded_at,
    parse_calculations,
    reconstruct_primary_statements,
)
from engine.fundamental_forensics.statement_service import (
    GoldenAaplStatementProvider,
    UnavailableFinancialStatementProvider,
    bind_canonical_identity,
    execute_financial_statements,
)
from lib.dataos.identity import IssuerMaster

ROOT = Path(__file__).resolve().parents[1]
_REQUEST_SCHEMA = "fundamental_forensics.financial_statement_request/v1"
_GOLDEN_ENTITY = "ISS:US-XNAS-AAPL"
_GOLDEN_ACCESSION = "0000320193-25-000079"
_INDEX_SHA = "d61dde83df2dde7d63041e443321eab963b245e4c0090ba6240ce1711329de83"
_PRIMARY_SHA = "548ae59778cf08ee0f2ee088e7ece20d947076c3c01f74d2d65db4c2777e436a"
_RESPONSE_SHA = "1a489e46698e99f83518f18def89c381a29f63960a979d9de82caa29bcc3198e"
_RESPONSE_BYTES = 196358
_WITNESS_SHA = "6449489eef577b096abeb79f5375b7df9c95c23e4765a075222a765a19124d83"
_WITNESS_BYTES = 364
_FIXTURE_RECORDED_AT = "2026-08-23T00:32:31Z"

_HASH_AS_REPORTED_T1_T2 = "358d44741632d74ff76dd8771bb78b34295a08d62d2a0a8566a6abe5feac1442"
_HASH_LATEST_KNOWN_T1_T2 = "191c49a37998052f17eec78113b5bd8bf0dcaaa52239c406cdb4c27cda5ad1a7"
_HASH_LATEST_KNOWN_T3 = "83df03e99f570bacfab94fc9373861f14c1895c9aa9435b7dd7249a13c1e67fa"
_HASH_LATEST_RESTATED_T3 = "c1095c7994c67f11ed602d15c2956bc24271cdce4d39d7869ed642713a6ed549"
_HASH_MIXED_T3 = "5513f17260f98d261920d658be25bf319ace90a0580ad8f2e94931c518c5a20b"
_RICH_PACKET_ID = "fip_49718dcaf4c6855592b6ba0a"
_RICH_CONTENT_SHA = "49718dcaf4c6855592b6ba0a160851c608b4733b44f8ac9a6cf7d907df7565e5"
_RICH_RESPONSE_SHA = "310f6579ab0014e6af16a3341f005078eab3fdcc70ebe67ec83cf138b9e6c23a"
_GOLDEN_FIP1_PACKET_ID = "fip_18e2f725f6ba20678d0612bb"

T1_SOURCE = "2024-12-31T23:59:59Z"
T2_SOURCE = "2025-12-31T23:59:59Z"
T2_RECORDED = "2026-08-03T12:00:00Z"
T3_SOURCE = "2025-12-31T23:59:59Z"
T3_RECORDED = "2026-08-05T12:00:02Z"
FY2023 = {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}
AR_INSTANT = {"kind": "instant", "start": None, "end": "2023-12-31", "label": "2023-12-31"}

_FROZEN_FIF1 = (
    "contracts/financial_intelligence_packet.schema.json",
    "engine/fundamental_forensics/financial_intelligence_packet.py",
    "engine/fundamental_forensics/synthetic_filing_package.py",
    "tests/fixtures/fundamental_forensics/expected_financial_intelligence_packet_v1.json",
)


def _statement_body(
    *,
    schema: str = _REQUEST_SCHEMA,
    entity_id: str = _GOLDEN_ENTITY,
    accession: str = _GOLDEN_ACCESSION,
    extra: dict | None = None,
) -> bytes:
    payload = {"schema": schema, "entity_id": entity_id, "accession": accession}
    if extra:
        payload.update(extra)
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _query_hash(*, selection: str, source: str, recorded: str, metric_ids: list, periods: list) -> str:
    class _P:
        def resolve(self, entity_id: str):
            return fip1_fixture_dataset(ROOT)

    body = json.dumps(
        {
            "schema": "fundamental_forensics.financial_query_request/v1",
            "entity_id": "mmx.issuer.fip1",
            "policy": {
                "selection": selection,
                "source_snapshot_at": source,
                "recorded_at": recorded,
            },
            "metric_ids": metric_ids,
            "periods": periods,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    result = execute_financial_query(body=body, provider=_P())
    return result.envelope["receipt"]["query_hash"]


def _execute(body: bytes | None = None, *, provider=None, issuer_master=None, issuer_metadata=None):
    return execute_financial_statements(
        body=body if body is not None else _statement_body(),
        repo_root=ROOT,
        provider=provider or GoldenAaplStatementProvider(ROOT),
        issuer_master=issuer_master,
        issuer_metadata=issuer_metadata,
    )


def _row(tree: dict, statement_type: str, label: str) -> dict:
    statement = next(s for s in tree["statements"] if s["statement_type"] == statement_type)
    matches = [row for row in statement["rows"] if row["as_reported_label"] == label]
    assert matches, label
    return matches[0]


def test_package_manifest_digest_and_member_counts() -> None:
    package = load_golden_aapl_package(ROOT)
    assert package.manifest["index_sha256"] == _INDEX_SHA
    assert package.manifest["member_count"] == 93
    assert package.manifest["retained_count"] == 6
    members = package.manifest["members"]
    assert len(members) == 93
    stored = [item for item in members if item["state"] == "stored"]
    skipped = [item for item in members if item["state"] == "not_requested"]
    assert len(stored) == 6
    assert len(skipped) == 87
    assert {item["name"] for item in stored} == {
        "aapl-20250927.htm",
        "aapl-20250927.xsd",
        "aapl-20250927_pre.xml",
        "aapl-20250927_cal.xml",
        "aapl-20250927_def.xml",
        "aapl-20250927_lab.xml",
    }
    primary = next(item for item in stored if item["name"] == "aapl-20250927.htm")
    assert primary["content_sha256"] == _PRIMARY_SHA
    assert hashlib.sha256(package.members["aapl-20250927.htm"]).hexdigest() == _PRIMARY_SHA
    witness = package.manifest["acceptance_witness"]
    assert witness["content_sha256"] == _WITNESS_SHA
    assert witness["byte_length"] == _WITNESS_BYTES
    assert package.manifest["source_accepted_at"] == "2025-10-31T10:01:26.000Z"
    assert package.manifest["fixture_recorded_at"] == _FIXTURE_RECORDED_AT
    witness_bytes = (
        ROOT
        / "tests"
        / "fixtures"
        / "fundamental_forensics"
        / "aapl_10k_2025"
        / "sec_submissions_witness.json"
    ).read_bytes()
    assert hashlib.sha256(witness_bytes).hexdigest() == _WITNESS_SHA
    assert len(witness_bytes) == _WITNESS_BYTES


def test_reconstruct_three_primary_statements_filing_native() -> None:
    tree = reconstruct_primary_statements(
        package=load_golden_aapl_package(ROOT),
        registry=load_core_registry(ROOT),
    )
    assert tree["parsed_document_kind"] == "inline_xbrl"
    assert tree["fact_count"] == 1131
    by_type = {item["statement_type"]: item for item in tree["statements"]}
    assert set(by_type) == {"income_statement", "balance_sheet", "cash_flow"}
    assert by_type["income_statement"]["row_count"] == 24
    assert by_type["balance_sheet"]["row_count"] == 35
    assert by_type["cash_flow"]["row_count"] == 35
    for kind, statement in by_type.items():
        assert statement["role_uri"] == PRIMARY_STATEMENT_ROLES[kind]
        assert statement["title"] == STATEMENT_TITLES[kind]
        assert [row["order"] for row in statement["rows"]] == list(range(statement["row_count"]))
    assert [col["label"] for col in by_type["income_statement"]["columns"]] == [
        "2025-09-27",
        "2024-09-28",
        "2023-09-30",
    ]
    assert [col["start"] for col in by_type["income_statement"]["columns"]] == [
        "2024-09-29",
        "2023-10-01",
        "2022-09-25",
    ]
    assert [col["label"] for col in by_type["balance_sheet"]["columns"]] == [
        "2025-09-27",
        "2024-09-28",
    ]
    assert by_type["balance_sheet"]["columns"][0]["kind"] == "instant"
    assert by_type["income_statement"]["columns"][0]["kind"] == "duration"
    income_labels = [row["as_reported_label"] for row in by_type["income_statement"]["rows"]]
    assert income_labels[:4] == ["Net sales:", "Products", "Services", "Total net sales"]
    assert not any("Table" in label or "Axis" in label or "Line Items" in label for label in income_labels)
    assert not any("[Table]" in label or "[Axis]" in label or "[Line Items]" in label for label in income_labels)


def test_income_duration_reverses_to_aapl_xbrl_occurrence() -> None:
    package = load_golden_aapl_package(ROOT)
    tree = reconstruct_primary_statements(package=package, registry=load_core_registry(ROOT))
    sales = _row(tree, "income_statement", "Total net sales")
    cell = sales["cells"][0]
    assert cell["value"] == "416161000000"
    assert cell["scale"] == 6
    assert cell["quality_state"] == "available"
    receipt = cell["source_receipt"]
    assert receipt["document_name"] == "aapl-20250927.htm"
    assert receipt["content_sha256"] == _PRIMARY_SHA
    assert receipt["context_ref"]
    frag = package.members["aapl-20250927.htm"][
        receipt["source_span"]["start"] : receipt["source_span"]["end"]
    ].decode("utf-8")
    assert "416,161" in frag
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in frag
    assert 'scale="6"' in frag
    assert sales["standardized_metric_id"] == "revenue"


def test_balance_sheet_instant_reverses() -> None:
    package = load_golden_aapl_package(ROOT)
    tree = reconstruct_primary_statements(package=package, registry=load_core_registry(ROOT))
    ar = _row(tree, "balance_sheet", "Accounts receivable, net")
    cell = ar["cells"][0]
    assert cell["value"] == "39777000000"
    assert cell["period"]["kind"] == "instant"
    assert cell["period"]["end"] == "2025-09-27"
    frag = package.members["aapl-20250927.htm"][
        cell["source_receipt"]["source_span"]["start"] : cell["source_receipt"]["source_span"]["end"]
    ].decode("utf-8")
    assert "39,777" in frag
    assert "AccountsReceivableNetCurrent" in frag
    assert ar["standardized_metric_id"] == "accounts_receivable_net"


def test_cash_flow_order_is_filing_native_and_splits_beginning_ending_cash() -> None:
    tree = reconstruct_primary_statements(
        package=load_golden_aapl_package(ROOT),
        registry=load_core_registry(ROOT),
    )
    cf = next(item for item in tree["statements"] if item["statement_type"] == "cash_flow")
    labels = [row["as_reported_label"] for row in cf["rows"]]
    begin = next(row for row in cf["rows"] if "beginning balances" in row["as_reported_label"])
    end = next(row for row in cf["rows"] if "ending balances" in row["as_reported_label"])
    assert begin["concept"] == end["concept"]
    assert begin["as_reported_label"] != end["as_reported_label"]
    assert begin["order"] < end["order"]
    assert begin["cells"][0]["value"] == "29943000000"
    assert end["cells"][0]["value"] == "35934000000"
    operating = next(
        idx for idx, label in enumerate(labels) if label == "Cash generated by operating activities"
    )
    investing = next(
        idx for idx, label in enumerate(labels) if label == "Cash generated by investing activities"
    )
    financing = next(
        idx for idx, label in enumerate(labels) if label == "Cash used in financing activities"
    )
    assert operating < investing < financing


def test_unmapped_sga_row_survives() -> None:
    tree = reconstruct_primary_statements(
        package=load_golden_aapl_package(ROOT),
        registry=load_core_registry(ROOT),
    )
    sga = _row(tree, "income_statement", "Selling, general and administrative")
    assert sga["mapping_state"] == "unmapped"
    assert sga["standardized_metric_id"] is None
    assert sga["cells"][0]["value"] == "27601000000"
    assert sga["cells"][0]["quality_state"] == "available"


def test_nil_commitments_row_is_typed_not_zero() -> None:
    tree = reconstruct_primary_statements(
        package=load_golden_aapl_package(ROOT),
        registry=load_core_registry(ROOT),
    )
    row = _row(tree, "balance_sheet", "Commitments and contingencies")
    assert row["cells"][0]["quality_state"] == "nil"
    assert row["cells"][0]["value"] is None


def test_duplicate_disagreeing_facts_are_ambiguous_not_first_row_wins() -> None:
    column = {"kind": "duration", "start": "2024-09-29", "end": "2025-09-27", "label": "2025-09-27"}
    facts = [
        {
            "fact_id": "a",
            "normalized_value": "100",
            "nil": False,
            "source_span": {"start": 1, "end": 2},
            "concept_qname": "{http://fasb.org/us-gaap/2025}RevenueFromContractWithCustomerExcludingAssessedTax",
            "context_ref": "c-1",
            "unit_ref": "usd",
            "scale": 6,
            "decimals": -6,
        },
        {
            "fact_id": "b",
            "normalized_value": "999",
            "nil": False,
            "source_span": {"start": 9, "end": 10},
            "concept_qname": "{http://fasb.org/us-gaap/2025}RevenueFromContractWithCustomerExcludingAssessedTax",
            "context_ref": "c-1",
            "unit_ref": "usd",
            "scale": 6,
            "decimals": -6,
        },
    ]
    cell = _cell_from_facts(
        facts=facts,
        column=column,
        units={"usd": {"numerator_measures": ["iso4217:USD"], "denominator_measures": []}},
        document_name="aapl-20250927.htm",
        content_sha256=_PRIMARY_SHA,
        abstract=False,
    )
    assert cell["quality_state"] == "ambiguous"
    assert cell["value"] is None
    assert cell["source_receipt"]["competing_values"] == ["100", "999"]
    assert cell["source_receipt"]["competing_fact_ids"] == ["a", "b"]


def test_data_os_issuer_binding_keeps_source_native_cik() -> None:
    result = _execute()
    entity = result.envelope["entity"]
    assert entity["entity_id"] == "ISS:US-XNAS-AAPL"
    assert entity["cik"] == "0000320193"
    assert entity["source_entity_id"] == "0000320193"
    assert entity["entity_id"] != entity["cik"]
    assert entity["security_id"] == "SEC:US-XNAS-AAPL"
    assert entity["listing_key"] == "US-XNAS-AAPL"
    assert entity["legal_name"] == "Apple Inc."


def test_ticker_or_cik_entity_id_is_unknown() -> None:
    for entity_id in ("AAPL", "0000320193", "mmx.issuer.aapl"):
        with pytest.raises(FinancialQueryAdmissionError) as exc:
            _execute(_statement_body(entity_id=entity_id))
        assert exc.value.status_code == 400
        assert exc.value.detail == "unknown entity"


def test_provider_is_not_opened_before_admission() -> None:
    calls: list[str] = []

    class _P(GoldenAaplStatementProvider):
        def resolve(self, entity_id: str, accession: str):
            calls.append(entity_id)
            return super().resolve(entity_id, accession)

    with pytest.raises(FinancialQueryAdmissionError):
        execute_financial_statements(
            body=b"{not-json",
            repo_root=ROOT,
            provider=_P(ROOT),
        )
    assert calls == []
    with pytest.raises(FinancialQueryAdmissionError):
        execute_financial_statements(
            body=_statement_body(extra={"ticker": "AAPL"}),
            repo_root=ROOT,
            provider=_P(ROOT),
        )
    assert calls == []


def test_execute_is_deterministic_and_pinned() -> None:
    first = _execute()
    second = _execute()
    assert first.body == second.body
    assert first.sha256 == second.sha256 == _RESPONSE_SHA
    assert len(first.body) == _RESPONSE_BYTES
    assert hashlib.sha256(first.body).hexdigest() == _RESPONSE_SHA
    assert first.envelope["schema"] == "fundamental_forensics.financial_statement_response/v1"
    assert first.envelope["filing"]["source_accepted_at"] == "2025-10-31T10:01:26.000Z"
    assert first.envelope["filing"]["fixture_recorded_at"] == _FIXTURE_RECORDED_AT
    assert first.envelope["delivery"] == {
        "kind": "committed_golden_fixture",
        "attested": False,
        "production_issuer_service": False,
        "authority": "context_display_only",
    }
    assert "now" not in json.dumps(first.envelope)


def test_no_request_time_network_or_attested_write(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("FIF-3A1 requested the network")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    writes: list[str] = []
    original = Path.write_bytes

    def _track(self: Path, data: bytes) -> int:
        writes.append(str(self))
        return original(self, data)

    monkeypatch.setattr(Path, "write_bytes", _track)
    result = _execute()
    assert result.sha256 == _RESPONSE_SHA
    assert writes == []
    import engine.fundamental_forensics.statement_service as service_mod
    import engine.fundamental_forensics.statement_graph as graph_mod

    assert "urllib" not in Path(service_mod.__file__).read_text(encoding="utf-8")
    assert "source_sync" not in Path(graph_mod.__file__).read_text(encoding="utf-8")


def test_unavailable_provider_is_503() -> None:
    with pytest.raises(Exception) as exc:
        _execute(provider=UnavailableFinancialStatementProvider())
    from engine.fundamental_forensics.query_service import FinancialQueryUnavailableError

    assert isinstance(exc.value, FinancialQueryUnavailableError)


def test_fif2a_query_hashes_unchanged() -> None:
    metrics = ["revenue", "gross_margin"]
    fy = [FY2023]
    assert (
        _query_hash(
            selection="as_reported",
            source=T1_SOURCE,
            recorded=T2_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_AS_REPORTED_T1_T2
    )
    assert (
        _query_hash(
            selection="latest_known_as_of",
            source=T1_SOURCE,
            recorded=T2_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_LATEST_KNOWN_T1_T2
    )
    assert (
        _query_hash(
            selection="latest_known_as_of",
            source=T3_SOURCE,
            recorded=T3_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_LATEST_KNOWN_T3
    )
    assert (
        _query_hash(
            selection="latest_restated",
            source=T3_SOURCE,
            recorded=T3_RECORDED,
            metric_ids=metrics,
            periods=fy,
        )
        == _HASH_LATEST_RESTATED_T3
    )
    mixed = _query_hash(
        selection="latest_known_as_of",
        source=T3_SOURCE,
        recorded=T3_RECORDED,
        metric_ids=["revenue", "accounts_receivable_net"],
        periods=[FY2023, AR_INSTANT],
    )
    assert mixed == _HASH_MIXED_T3


def test_fif2b_and_fif2c_accepted_packet_behavior_unchanged() -> None:
    class _Packet:
        def resolve(self, entity_id: str):
            return fip1_packet_dataset(ROOT)

    t2 = execute_financial_revisions(
        body=json.dumps(
            {
                "schema": "fundamental_forensics.financial_revision_request/v1",
                "entity_id": "mmx.issuer.fip1",
                "policy": {
                    "selection": "latest_known_as_of",
                    "source_snapshot_at": T2_SOURCE,
                    "recorded_at": T2_RECORDED,
                },
                "metric_ids": ["revenue"],
                "periods": [FY2023],
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        provider=_Packet(),
    )
    assert t2.envelope["revisions"] == []
    rich = execute_financial_packet(
        body=json.dumps(
            {
                "schema": "fundamental_forensics.financial_packet_request/v1",
                "entity_id": "mmx.issuer.fip1",
                "policy": {
                    "selection": "latest_known_as_of",
                    "source_snapshot_at": T3_SOURCE,
                    "recorded_at": T3_RECORDED,
                },
                "metric_ids": ["revenue", "accounts_receivable_net", "gross_margin", "CustomerCount"],
                "periods": [FY2023, AR_INSTANT],
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        provider=_Packet(),
    )
    assert rich.packet["packet_id"] == _RICH_PACKET_ID
    assert rich.packet["content_sha256"] == _RICH_CONTENT_SHA
    assert rich.response_sha256 == _RICH_RESPONSE_SHA
    assert len(rich.body) == 18270


def test_frozen_fif1_paths_are_empty_diff() -> None:
    dirty = subprocess.run(
        ["git", "diff", "--exit-code", "--", *_FROZEN_FIF1],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert dirty.returncode == 0, dirty.stdout.decode("utf-8", "replace")
    against_main = subprocess.run(
        ["git", "diff", "--exit-code", "origin/main...HEAD", "--", *_FROZEN_FIF1],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert against_main.returncode == 0, against_main.stdout.decode("utf-8", "replace")
    golden = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "fundamental_forensics"
            / "expected_financial_intelligence_packet_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert golden["packet_id"] == _GOLDEN_FIP1_PACKET_ID


def test_issuer_master_selects_active_membership_not_superseded_duplicate() -> None:
    fixture = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "fundamental_forensics"
            / "issuer_master_adversarial_duplicate_mint.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture["securities"][0]["security_state"] == "SUPERSEDED_DUPLICATE_MINT"
    assert fixture["securities"][0]["security_id"] == "SEC:US-XNAS-AAPL-DUP"
    master = IssuerMaster.from_records(fixture["securities"])
    assert master.securities_of_issuer("ISS:US-XNAS-AAPL") == ("SEC:US-XNAS-AAPL",)
    assert master.security_state_of("SEC:US-XNAS-AAPL-DUP") == "SUPERSEDED_DUPLICATE_MINT"
    binding = bind_canonical_identity(
        "ISS:US-XNAS-AAPL",
        issuer_master=master,
        issuer_metadata=fixture["issuer_metadata"],
    )
    assert binding["security_id"] == "SEC:US-XNAS-AAPL"
    assert binding["listing_key"] == "US-XNAS-AAPL"
    result = _execute(
        issuer_master=master,
        issuer_metadata=fixture["issuer_metadata"],
    )
    assert result.envelope["entity"]["security_id"] == "SEC:US-XNAS-AAPL"
    assert result.envelope["entity"]["listing_key"] == "US-XNAS-AAPL"
    assert result.envelope["entity"]["entity_id"] == "ISS:US-XNAS-AAPL"
    assert result.envelope["entity"]["cik"] == "0000320193"


def test_products_and_services_are_displayed_under_net_sales_with_dimensions() -> None:
    package = load_golden_aapl_package(ROOT)
    tree = reconstruct_primary_statements(package=package, registry=load_core_registry(ROOT))
    statement = next(item for item in tree["statements"] if item["statement_type"] == "income_statement")
    labels = [row["as_reported_label"] for row in statement["rows"]]
    assert labels[:4] == ["Net sales:", "Products", "Services", "Total net sales"]
    products = next(
        row
        for row in statement["rows"]
        if row["as_reported_label"] == "Products"
        and "RevenueFromContractWithCustomerExcludingAssessedTax" in (row["concept"] or "")
    )
    services = next(
        row
        for row in statement["rows"]
        if row["as_reported_label"] == "Services"
        and "RevenueFromContractWithCustomerExcludingAssessedTax" in (row["concept"] or "")
    )
    total = _row(tree, "income_statement", "Total net sales")
    assert products["depth"] == 1
    assert services["depth"] == 1
    assert products["cells"][0]["value"] == "307003000000"
    assert services["cells"][0]["value"] == "109158000000"
    assert total["cells"][0]["value"] == "416161000000"
    assert total["cells"][0]["dimensions"] == []
    product_dims = products["cells"][0]["dimensions"]
    assert product_dims
    assert any("ProductOrServiceAxis" in (item.get("dimension_qname") or "") for item in product_dims)
    assert any("ProductMember" in (item.get("member_qname") or "") for item in product_dims)
    assert any("ServiceMember" in (item.get("member_qname") or "") for item in services["cells"][0]["dimensions"])
    receipt = products["cells"][0]["source_receipt"]
    frag = package.members["aapl-20250927.htm"][
        receipt["source_span"]["start"] : receipt["source_span"]["end"]
    ].decode("utf-8")
    assert "307,003" in frag
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in frag
    assert products["formula_dependencies"] is None
    assert products["cells"][0]["direct_or_calculated"] == "direct"


def test_agreeing_duplicate_occurrences_retain_count() -> None:
    tree = reconstruct_primary_statements(
        package=load_golden_aapl_package(ROOT),
        registry=load_core_registry(ROOT),
    )
    total = _row(tree, "income_statement", "Total net sales")
    assert total["cells"][0]["quality_state"] == "available"
    assert total["cells"][0]["value"] == "416161000000"
    assert total["cells"][0]["source_receipt"]["occurrence_count"] > 1


def _cloned_package(tmp_path: Path) -> Path:
    dest = tmp_path / "aapl_10k_2025"
    shutil.copytree(ROOT / "tests" / "fixtures" / "fundamental_forensics" / "aapl_10k_2025", dest)
    return dest


def _rewrite_manifest(dest: Path, mutate) -> None:
    path = dest / "package_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_hostile_index_digest_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)
    index = dest / "index.json"
    index.write_bytes(index.read_bytes() + b"\n")
    with pytest.raises(StatementGraphError, match="index digest"):
        admit_golden_aapl_package(dest)


def test_hostile_index_duplicate_member_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)
    index_path = dest / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["directory"]["item"].append(index["directory"]["item"][0])
    raw = json.dumps(index).encode("utf-8")
    index_path.write_bytes(raw)

    def _align(manifest: dict) -> None:
        manifest["index_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["index_byte_length"] = len(raw)

    _rewrite_manifest(dest, _align)
    with pytest.raises(StatementGraphError, match="duplicate members"):
        admit_golden_aapl_package(dest)


def test_hostile_inventory_extra_member_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)
    def _extra(manifest: dict) -> None:
        manifest["members"].append(
            {
                "name": "not-in-the-archive.fake",
                "state": "not_requested",
                "role": "archive",
            }
        )
        manifest["member_count"] = 94
    _rewrite_manifest(dest, _extra)
    with pytest.raises(StatementGraphError, match="inventory does not match"):
        admit_golden_aapl_package(dest)


def test_hostile_inventory_missing_member_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)

    def _missing(manifest: dict) -> None:
        manifest["members"] = [item for item in manifest["members"] if item["name"] != "FilingSummary.xml"]
        manifest["member_count"] = 92

    _rewrite_manifest(dest, _missing)
    with pytest.raises(StatementGraphError, match="inventory does not match"):
        admit_golden_aapl_package(dest)


def test_hostile_inventory_duplicate_member_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)

    def _dup(manifest: dict) -> None:
        manifest["members"].append(dict(manifest["members"][0]))
        manifest["member_count"] = 94

    _rewrite_manifest(dest, _dup)
    with pytest.raises(StatementGraphError, match="duplicate members"):
        admit_golden_aapl_package(dest)


def test_hostile_acceptance_witness_digest_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)
    witness = dest / "sec_submissions_witness.json"
    witness.write_bytes(witness.read_bytes() + b" ")
    with pytest.raises(StatementGraphError, match="witness digest"):
        admit_golden_aapl_package(dest)


def test_hostile_acceptance_witness_unbind_is_refused(tmp_path: Path) -> None:
    dest = _cloned_package(tmp_path)
    _rewrite_manifest(dest, lambda manifest: manifest.update({"source_accepted_at": "1999-01-01T00:00:00.000Z"}))
    with pytest.raises(StatementGraphError, match="source_accepted_at is not bound"):
        admit_golden_aapl_package(dest)


def test_capture_process_mints_fixture_recorded_at() -> None:
    stamp = mint_fixture_recorded_at(datetime(2026, 8, 23, 0, 32, 31, tzinfo=timezone.utc))
    assert stamp == "2026-08-23T00:32:31Z"
    with pytest.raises(StatementGraphError):
        mint_fixture_recorded_at(datetime(2026, 8, 23, 0, 32, 31))
    capture = (ROOT / "scripts" / "capture_fif3a1_aapl_package.py").read_text(encoding="utf-8")
    assert "mint_fixture_recorded_at" in capture
    assert "hand-edit" not in capture.lower()


def test_calculation_relationships_are_role_local() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended" xlink:role="http://example.com/role/IS">
    <link:loc xlink:type="locator" xlink:label="parent" xlink:href="a.xsd#us-gaap_GrossProfit"/>
    <link:loc xlink:type="locator" xlink:label="is-child" xlink:href="a.xsd#us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax"/>
    <link:calculationArc xlink:type="arc" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" xlink:from="parent" xlink:to="is-child" weight="1"/>
  </link:calculationLink>
  <link:calculationLink xlink:type="extended" xlink:role="http://example.com/role/CF">
    <link:loc xlink:type="locator" xlink:label="parent" xlink:href="a.xsd#us-gaap_GrossProfit"/>
    <link:loc xlink:type="locator" xlink:label="cf-child" xlink:href="a.xsd#us-gaap_NetIncomeLoss"/>
    <link:calculationArc xlink:type="arc" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" xlink:from="parent" xlink:to="cf-child" weight="-1"/>
  </link:calculationLink>
</link:linkbase>
""".encode("utf-8")
    by_role = parse_calculations(xml)
    parent = "us-gaap:GrossProfit"
    is_children = dict(by_role["http://example.com/role/IS"][parent])
    cf_children = dict(by_role["http://example.com/role/CF"][parent])
    assert is_children == {"us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "1"}
    assert cf_children == {"us-gaap:NetIncomeLoss": "-1"}
    assert "us-gaap:NetIncomeLoss" not in is_children
    assert "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" not in cf_children
    tree = reconstruct_primary_statements(
        package=load_golden_aapl_package(ROOT),
        registry=load_core_registry(ROOT),
    )
    gross = _row(tree, "income_statement", "Gross margin")
    deps = {item["concept"] for item in (gross["formula_dependencies"] or [])}
    assert "us-gaap:NetIncomeLoss" not in deps
    missing_role = b"""<?xml version="1.0" encoding="UTF-8"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended">
    <link:loc xlink:type="locator" xlink:label="parent" xlink:href="a.xsd#us-gaap_GrossProfit"/>
  </link:calculationLink>
</link:linkbase>
"""
    with pytest.raises(StatementGraphError, match="xlink:role"):
        parse_calculations(missing_role)
