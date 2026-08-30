from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from openpyxl import Workbook

from engine.biocatalyst.jv_snapshot import (
    AUTHORIZED_INPUTS,
    SnapshotIdentityResolver,
    SnapshotError,
    admit_files,
    build_snapshot_manifest,
    canonical_json_bytes,
    classify_workbook_bytes,
    identity_resolver_from_parquet_bytes,
    normalize_corpus,
    repair_historical_fda,
)
from lib.dataos.identity import IssuerMaster, VendorAliasTable


def _workbook_bytes(*sheets: tuple[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets:
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _history_csv(rows: list[list[str]]) -> bytes:
    header = (
        "row,ticker,name,catalyst_price_movement,price_at_catalyst_date,drug,"
        "indication,stage,catalyst_date,catalyst,conference,company_url,catalyst_url\r\n"
    )
    return (header + "\r\n".join(",".join(row) for row in rows) + "\r\n").encode()


def test_authorized_corpus_is_w4_plus_four_csvs() -> None:
    assert set(AUTHORIZED_INPUTS) == {
        "workbook_w4",
        "all_companies",
        "historical_fda",
        "mergers_acquisitions",
        "hedge_funds",
    }
    assert AUTHORIZED_INPUTS["workbook_w4"].sha256 == "946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535"
    assert all("w1" not in key for key in AUTHORIZED_INPUTS)


def test_admission_fails_closed_on_missing_or_wrong_bytes(tmp_path: Path) -> None:
    paths = {key: tmp_path / spec.safe_name for key, spec in AUTHORIZED_INPUTS.items()}
    with pytest.raises(SnapshotError, match="AUTHORIZED_INPUT_MISSING"):
        admit_files(paths)
    for path in paths.values():
        path.write_bytes(b"wrong")
    with pytest.raises(SnapshotError, match="AUTHORIZED_INPUT_HASH_MISMATCH"):
        admit_files(paths)


def test_workbook_classifier_detects_additive_and_mutated_common_content() -> None:
    older = _workbook_bytes(("A", [["x"], [1]]))
    newer = _workbook_bytes(("A", [["x"], [1]]), ("B", [["y"], [2]]))
    changed = _workbook_bytes(("A", [["x"], [9]]), ("B", [["y"], [2]]))
    assert classify_workbook_bytes(older, newer) == "ADDITIVE_SHEET_EXPORT_IDENTICAL_COMMON_CONTENT"
    assert classify_workbook_bytes(older, changed) == "COMMON_SHEET_CONTENT_CHANGED"


def test_historical_fda_repair_keeps_raw_bytes_and_unshifts_only_missing_index() -> None:
    raw = _history_csv([
        ["1", "ABC", "Alpha", "+5%", "$10", "Drug A", "Cancer", "Approved", "01/02/2020 ET", "Approved.", "", "https://private/company", ""],
        ["XYZ", "Beta", "", "$8", "Drug B", "Rare", "CRL", "03/04/2021 ET", "CRL issued.", "", "https://private/company", ""],
    ])
    result = repair_historical_fda(raw, expected_rows=2, expected_shifted=1)
    assert raw.endswith(b"\r\n")
    assert result.row_count == 2
    assert result.repaired_count == 1
    assert result.rows[1]["ticker"] == "XYZ"
    assert result.rows[1]["stage"] == "CRL"
    assert result.rows[1]["catalyst_date"] == "03/04/2021 ET"
    assert result.rows[1]["_repair"] == "missing_row_index_unshifted"


def test_normalization_is_fixed_point_and_excludes_poison_and_private_urls() -> None:
    workbook = _workbook_bytes(
        ("Device History", [["Ticker", "Name", "Catalyst Price Movement", "Price at Catalyst Date", "Device", "Indication", "Device Stage", "Catalyst Date", "Catalyst"], ["DEV", "Device Co", "+4%", "$12", "Device X", "Cardiology", "510(k)", "05/06/2022 ET", "Clearance"]]),
        ("Device Pipeline", [["Ticker", "Name", "Price", "30 Day Price Change", "Device", "Indication", "Stage", "Catalyst Date", "Catalyst", "Options", "No Of Shares", "Market Cap", "Volume", "Average Daily Volume", "Relative Volume", "Price to Book", "Open", "Previous close"], ["DEV", "Device Co", "$99", "+30%", "Device Y", "Surgery", "Approved", "01/02/2020 ET", "Approval", "View", "1", "$1B", "5", "6", "7", "8", "9", "10"]]),
    )
    history = _history_csv([["1", "ABC", "Alpha", "+5%", "$10", "Drug A", "Cancer", "Approved", "01/02/2020 ET", "Approved.", "", "https://private/company", "https://private/catalyst"]])
    first = normalize_corpus(workbook, history, observed_at="2026-08-17T07:55:47Z", expected_fda_rows=1, expected_fda_shifted=0)
    second = normalize_corpus(workbook, history, observed_at="2026-08-17T07:55:47Z", expected_fda_rows=1, expected_fda_shifted=0)
    assert first.jsonl == second.jsonl
    assert len(first.events) == 3
    rendered = first.jsonl.decode()
    for forbidden in ("company_url", "catalyst_url", "30 Day Price Change", "Market Cap", "Relative Volume", "Options", "https://private"):
        assert forbidden not in rendered
    assert canonical_json_bytes(first.events[0]).endswith(b"}")


def test_history_omits_future_due_rows_and_normalizes_missing_market_sentinels() -> None:
    workbook = _workbook_bytes(
        ("Device Pipeline", [["Ticker", "Name", "Price", "30 Day Price Change", "Device", "Indication", "Stage", "Catalyst Date", "Catalyst", "Options"], ["DEV", "Device Co", "$99", "+30%", "Future Device", "Surgery", "Submission", "01/02/2027 ET", "Clearance due", "View"]]),
    )
    history = _history_csv([["1", "ABC", "Alpha", "—", "—", "Drug A", "Cancer", "Approved", "01/02/2020 ET", "Approved.", "", "", ""]])
    corpus = normalize_corpus(workbook, history, observed_at="2026-08-17T07:55:47Z", expected_fda_rows=1, expected_fda_shifted=0)
    assert len(corpus.events) == 1
    assert corpus.events[0]["historical_market"] == {"price_at_event": None, "price_movement": None}
    assert corpus.coverage["family_source_rows"]["device_pipeline_history"] == 1
    assert corpus.coverage["families"] == {"historical_fda": 1}


def test_description_url_is_redacted_before_projection_validation() -> None:
    workbook = _workbook_bytes(("Device History", [["Ticker", "Name", "Catalyst Price Movement", "Price at Catalyst Date", "Device", "Indication", "Device Stage", "Catalyst Date", "Catalyst"]]))
    history = _history_csv([["1", "ABC", "Alpha", "+5%", "$10", "Drug A", "Cancer", "Approved", "01/02/2020 ET", "Details at https://private.example/path and confirmed.", "", "", ""]])
    corpus = normalize_corpus(workbook, history, observed_at="2026-08-17T07:55:47Z", expected_fda_rows=1, expected_fda_shifted=0)
    row = corpus.events[0]
    assert row["event"]["description"] == "Details at [source link omitted] and confirmed."
    assert "licensed_description_urls_redacted" in row["unsafe_fields"]
    assert "https://" not in corpus.jsonl.decode()


def test_normalization_collapses_exact_duplicate_source_rows() -> None:
    workbook = _workbook_bytes(("Device History", [["Ticker", "Name", "Catalyst Price Movement", "Price at Catalyst Date", "Device", "Indication", "Device Stage", "Catalyst Date", "Catalyst"]]))
    duplicate = ["1", "ABC", "Alpha", "+5%", "$10", "Drug A", "Cancer", "Approved", "01/02/2020 ET", "Approved.", "", "", ""]
    history = _history_csv([duplicate, duplicate])
    corpus = normalize_corpus(workbook, history, observed_at="2026-08-17T07:55:47Z", expected_fda_rows=2, expected_fda_shifted=0)
    assert len(corpus.events) == 1
    assert corpus.coverage["duplicates_collapsed"] == 1


def test_identity_resolution_uses_existing_alias_and_marks_current_only() -> None:
    aliases = VendorAliasTable.from_records([
        {"vendor": "store", "vendor_symbol": "ABC", "security_id": "SEC:US-XNAS-ABC", "valid_from": None, "valid_to": None},
        {"vendor": "yahoo", "vendor_symbol": "ABC", "security_id": "SEC:US-XNAS-ABC", "valid_from": "2020-01-01", "valid_to": None},
    ])
    issuers = IssuerMaster.from_records([
        {"security_id": "SEC:US-XNAS-ABC", "issuer_id": "ISS:US-XNAS-ABC", "effective_at": "2026-08-17"}
    ])
    resolver = SnapshotIdentityResolver(aliases, issuers)
    resolved = resolver("ABC", __import__("datetime").date(2024, 1, 1))
    assert resolved == {
        "resolution_state": "resolved",
        "security_id": "SEC:US-XNAS-ABC",
        "issuer_id": "ISS:US-XNAS-ABC",
        "resolution_basis": "time_scoped_alias",
        "issuer_relationship_state": "current_only",
    }


def test_identity_resolution_refuses_cross_vendor_ambiguity() -> None:
    aliases = VendorAliasTable.from_records([
        {"vendor": "store", "vendor_symbol": "ABC", "security_id": "SEC:US-XNAS-ABC", "valid_from": None, "valid_to": None},
        {"vendor": "theme_graph_native", "vendor_symbol": "ABC", "security_id": "SEC:US-XNYS-ABC", "valid_from": None, "valid_to": None},
    ])
    resolver = SnapshotIdentityResolver(aliases, IssuerMaster(()))
    assert resolver("ABC", __import__("datetime").date(2024, 1, 1))["resolution_state"] == "ambiguous"


def test_identity_resolver_loads_the_existing_parquet_contracts() -> None:
    import pandas as pd

    aliases = BytesIO()
    pd.DataFrame([{"vendor": "store", "vendor_symbol": "ABC", "security_id": "SEC:US-XNAS-ABC", "valid_from": None, "valid_to": None, "ingested_at": None}]).to_parquet(aliases, index=False)
    master = BytesIO()
    pd.DataFrame([{"security_id": "SEC:US-XNAS-ABC", "issuer_id": "ISS:US-XNAS-ABC", "issuer_state": "RESOLVED", "listing_key": "US-XNAS-ABC", "security_state": None, "superseded_by": None}]).to_parquet(master, index=False)
    resolver = identity_resolver_from_parquet_bytes(master.getvalue(), aliases.getvalue())
    assert resolver("ABC", __import__("datetime").date(2024, 1, 1))["security_id"] == "SEC:US-XNAS-ABC"


def test_snapshot_manifest_is_closed_and_content_addressed(tmp_path: Path) -> None:
    specs = {
        key: type(spec)(spec.input_id, spec.safe_name, __import__("hashlib").sha256(key.encode()).hexdigest(), len(key), spec.media_type, spec.role)
        for key, spec in AUTHORIZED_INPUTS.items()
    }
    paths = {}
    for key, spec in specs.items():
        path = tmp_path / spec.safe_name
        path.write_bytes(key.encode())
        paths[key] = path
    admitted = admit_files(paths, specs=specs)
    manifest = build_snapshot_manifest(
        admitted,
        families=[{"family": "historical_fda", "source_rows": 2, "normalized_rows": 2, "repaired_rows": 1, "publication_state": "projected"}],
        observed_at="2026-08-17T07:55:47Z",
    )
    assert manifest["source_id"] == "biopharmcatalyst_jv_snapshot"
    schema = __import__("json").loads(
        (
            Path(__file__).resolve().parents[1]
            / "contracts/biocatalyst/biocatalyst_jv_snapshot_manifest.v1.schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(manifest)
    digest = manifest.pop("manifest_sha256")
    assert digest == __import__("hashlib").sha256(canonical_json_bytes(manifest)).hexdigest()
