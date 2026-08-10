"""Adversarial tests for prospective symbol-directory completion receipts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

import collectors.symbol_directory as collector
import lib.symbol_directory_receipts as receipts

_DATE = "2026-08-10"
_COLLECTOR_START = f"{_DATE}T00:00:00.000000Z"
_NASDAQ_START = f"{_DATE}T00:00:01.000000Z"
_NASDAQ_DONE = f"{_DATE}T00:00:01.100000Z"
_OTHER_START = f"{_DATE}T00:00:02.000000Z"
_OTHER_DONE = f"{_DATE}T00:00:02.100000Z"
_SEC_START = f"{_DATE}T00:00:03.000000Z"
_SEC_DONE = f"{_DATE}T00:00:03.100000Z"
_COLLECTOR_DONE = f"{_DATE}T00:00:04.000000Z"


def _listing_frame() -> pd.DataFrame:
    ordinary_rows = 7_999
    return pd.DataFrame(
        {
            "date": [_DATE] * 8_000,
            "symbol": [f"N{index:07d}" for index in range(ordinary_rows)] + ["SPY"],
            "security_name": [f"Synthetic {index}" for index in range(ordinary_rows)]
            + ["SPDR S&P 500 ETF Trust"],
            "exchange": ["NASDAQ"] * ordinary_rows + ["P"],
            "etf": [False] * ordinary_rows + [True],
            "test_issue": [False] * 8_000,
            "is_preferred": [False] * 8_000,
            "source": ["nasdaqlisted"] * ordinary_rows + ["otherlisted"],
        }
    )


def _cik_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "AAPL", "cik": 320193, "title": "Apple Inc."},
            {"ticker": "SPY", "cik": 884394, "title": "SPDR S&P 500 ETF Trust"},
        ]
    )


def _listing_absent_frame() -> pd.DataFrame:
    frame = _listing_frame()
    frame.loc[frame.index[-1], "symbol"] = "IWM"
    frame.loc[frame.index[-1], "security_name"] = "iShares Russell 2000 ETF"
    return frame


def _canonical_receipt_body(value: dict) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def _recompute_receipt_id(value: dict) -> None:
    core = copy.deepcopy(value)
    core["receipt_id"] = ""
    value["receipt_id"] = (
        "sdreceipt_" + hashlib.sha256(_canonical_receipt_body(core)[:-1]).hexdigest()
    )


def _listing_fetches() -> tuple[
    tuple[str, receipts.SourceFetch[str]], tuple[str, receipts.SourceFetch[str]]
]:
    return (
        (
            receipts.NASDAQ_LISTED_SOURCE_ID,
            receipts.SourceFetch(
                value="decoded Nasdaq body",
                content=b"exact-nasdaq-response\x00\xff",
                requested_url=collector._NASDAQ_LISTED_URL,
                started_at=_NASDAQ_START,
                completed_at=_NASDAQ_DONE,
            ),
        ),
        (
            receipts.OTHER_LISTED_SOURCE_ID,
            receipts.SourceFetch(
                value="decoded other body",
                content=b"exact-other-response\r\n",
                requested_url=collector._OTHER_LISTED_URL,
                started_at=_OTHER_START,
                completed_at=_OTHER_DONE,
            ),
        ),
    )


def _listing_receipt(tmp_path: Path) -> tuple[Path, Path, dict]:
    root = tmp_path / "symbol_directory"
    artifact = root / "snapshots" / f"{_DATE}.parquet"
    receipts.durable_atomic_write_parquet(_listing_frame(), artifact)
    value = receipts.build_symbol_directory_completion_receipt(
        kind="listing_snapshot",
        observation_date=_DATE,
        artifact_path=artifact,
        source_fetches=_listing_fetches(),
        collector_started_at=_COLLECTOR_START,
        collector_completed_at=_COLLECTOR_DONE,
        pre_dedupe_rows=8_000,
        duplicate_occurrences=0,
        duplicate_key_count=0,
        source_row_counts=(
            (receipts.NASDAQ_LISTED_SOURCE_ID, 7_999),
            (receipts.OTHER_LISTED_SOURCE_ID, 1),
        ),
        pre_dedupe_spy_occurrences=(
            {
                "source_id": receipts.OTHER_LISTED_SOURCE_ID,
                "symbol": "SPY",
                "security_name": "SPDR S&P 500 ETF Trust",
                "exchange": "P",
                "etf": True,
                "test_issue": False,
                "is_preferred": False,
            },
        ),
        non_authoritative_footers=(
            receipts.footer_diagnostic(
                source_id=receipts.NASDAQ_LISTED_SOURCE_ID,
                text="File Creation Time: 8/10/2026 00:00:00",
            ),
            receipts.footer_diagnostic(
                source_id=receipts.OTHER_LISTED_SOURCE_ID,
                text="File Creation Time: 8/10/2026 00:00:01",
            ),
        ),
    )
    sidecar = receipts.completion_receipt_path(
        root,
        kind="listing_snapshot",
        observation_date=_DATE,
    )
    receipts.write_symbol_directory_completion_receipt(
        sidecar,
        value,
        artifact,
        expected_kind="listing_snapshot",
    )
    return artifact, sidecar, value


def _listing_absent_receipt(tmp_path: Path) -> tuple[Path, dict]:
    artifact = tmp_path / "symbol_directory" / "snapshots" / f"{_DATE}.parquet"
    receipts.durable_atomic_write_parquet(_listing_absent_frame(), artifact)
    value = receipts.build_symbol_directory_completion_receipt(
        kind="listing_snapshot",
        observation_date=_DATE,
        artifact_path=artifact,
        source_fetches=_listing_fetches(),
        collector_started_at=_COLLECTOR_START,
        collector_completed_at=_COLLECTOR_DONE,
        pre_dedupe_rows=8_000,
        duplicate_occurrences=0,
        duplicate_key_count=0,
        source_row_counts=(
            (receipts.NASDAQ_LISTED_SOURCE_ID, 7_999),
            (receipts.OTHER_LISTED_SOURCE_ID, 1),
        ),
        pre_dedupe_spy_occurrences=(),
        non_authoritative_footers=(
            receipts.footer_diagnostic(
                source_id=receipts.NASDAQ_LISTED_SOURCE_ID,
                text="File Creation Time: 8/10/2026 00:00:00",
            ),
            receipts.footer_diagnostic(
                source_id=receipts.OTHER_LISTED_SOURCE_ID,
                text="File Creation Time: 8/10/2026 00:00:01",
            ),
        ),
    )
    return artifact, value


def _nasdaq_text() -> str:
    header = (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
        "Round Lot Size|ETF|NextShares"
    )
    rows = [f"N{index:07d}|Synthetic {index}|Q|N|N|100|N|N" for index in range(7_999)]
    return "\n".join([header, *rows, "File Creation Time: 8/10/2026 00:00:00"])


def _other_text() -> str:
    return (
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
        "Test Issue|NASDAQ Symbol\n"
        "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\n"
        "File Creation Time: 8/10/2026 00:00:01"
    )


def _operational_fetches() -> tuple[
    receipts.SourceFetch[str], receipts.SourceFetch[str], receipts.SourceFetch[dict]
]:
    nasdaq = _nasdaq_text()
    other = _other_text()
    sec = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {
            "cik_str": 884394,
            "ticker": "SPY",
            "title": "SPDR S&P 500 ETF Trust",
        },
    }
    return (
        receipts.SourceFetch(
            value=nasdaq,
            content=nasdaq.encode(),
            requested_url=collector._NASDAQ_LISTED_URL,
            started_at=_NASDAQ_START,
            completed_at=_NASDAQ_DONE,
        ),
        receipts.SourceFetch(
            value=other,
            content=other.encode(),
            requested_url=collector._OTHER_LISTED_URL,
            started_at=_OTHER_START,
            completed_at=_OTHER_DONE,
        ),
        receipts.SourceFetch(
            value=sec,
            content=json.dumps(sec, separators=(",", ":")).encode(),
            requested_url=collector._TICKERS_URL,
            started_at=_SEC_START,
            completed_at=_SEC_DONE,
        ),
    )


def test_contract_is_valid_draft_2020_12() -> None:
    schema = json.loads(
        (
            Path(__file__).resolve().parent.parent
            / "contracts"
            / "symbol_directory"
            / "symbol_directory_completion_receipt.v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)


def test_fetch_api_is_backward_compatible_and_keeps_exact_response_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(
        status_code=200,
        text="decoded-text",
        content=b"raw-content-\xff",
    )
    response.raise_for_status.return_value = None
    monkeypatch.setattr(collector.requests, "get", Mock(return_value=response))

    assert collector._fetch_text(collector._NASDAQ_LISTED_URL) == "decoded-text"
    fetched = collector._fetch_text(collector._NASDAQ_LISTED_URL, with_evidence=True)

    assert isinstance(fetched, receipts.SourceFetch)
    assert fetched.value == "decoded-text"
    assert fetched.content == b"raw-content-\xff"

    sec_value = {"0": {"cik_str": 884394, "ticker": "SPY", "title": "SPY Trust"}}
    sec_response = Mock(
        status_code=200,
        content=b'{ "0" : { "ticker" : "SPY" } }\r\n',
    )
    sec_response.raise_for_status.return_value = None
    sec_response.json.return_value = sec_value
    monkeypatch.setattr(collector.requests, "get", Mock(return_value=sec_response))
    sec_fetched = collector._fetch_sec_json(collector._TICKERS_URL, with_evidence=True)
    assert isinstance(sec_fetched, receipts.SourceFetch)
    assert sec_fetched.value == sec_value
    assert sec_fetched.content == sec_response.content


def test_new_artifact_transactions_emit_separate_receipts_last(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nasdaq, other, sec = _operational_fetches()
    events: list[tuple[str, str]] = []
    real_artifact_write = collector.durable_atomic_write_parquet
    real_receipt_write = collector.write_symbol_directory_completion_receipt

    def record_artifact(frame: pd.DataFrame, path: Path) -> None:
        events.append(("artifact", path.parent.name))
        real_artifact_write(frame, path)

    def record_receipt(
        path: Path,
        value: dict,
        artifact: Path,
        *,
        expected_kind: receipts.CompletionKind,
    ) -> None:
        assert artifact.exists()
        events.append(("receipt", expected_kind))
        real_receipt_write(path, value, artifact, expected_kind=expected_kind)

    monkeypatch.setattr(collector.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(collector, "_fetch_text", Mock(side_effect=[nasdaq, other]))
    monkeypatch.setattr(collector, "_fetch_sec_json", Mock(return_value=sec))
    monkeypatch.setattr(
        collector,
        "canonical_utc_now",
        Mock(side_effect=[_COLLECTOR_START, _COLLECTOR_DONE, _COLLECTOR_DONE]),
    )
    monkeypatch.setattr(collector, "durable_atomic_write_parquet", record_artifact)
    monkeypatch.setattr(
        collector,
        "write_symbol_directory_completion_receipt",
        record_receipt,
    )

    result = collector.SymbolDirectoryAdapter().fetch()

    assert events == [
        ("artifact", "snapshots"),
        ("receipt", "listing_snapshot"),
        ("artifact", "cik_map"),
        ("receipt", "sec_registrant_map"),
    ]
    assert list(result) == ["symbol_directory__ingest"]
    assert list(result["symbol_directory__ingest"].columns) == [
        "n_symbols",
        "n_etf",
        "n_preferred",
        "n_common_estimate",
        "n_cik_rows",
        "snapshot_written",
        "cik_written",
    ]
    listing_artifact = tmp_path / "symbol_directory" / "snapshots" / f"{_DATE}.parquet"
    listing_sidecar = (
        tmp_path / "symbol_directory" / "receipts" / "snapshots" / f"{_DATE}.json"
    )
    listing = receipts.load_symbol_directory_completion_receipt(
        listing_sidecar,
        listing_artifact,
        expected_kind="listing_snapshot",
    )
    assert listing["artifact"]["rows"] == 8_000
    assert listing["diagnostics"]["pre_dedupe_spy_occurrence_count"] == 1
    assert [source["response_sha256"] for source in listing["sources"]] == [
        hashlib.sha256(nasdaq.content).hexdigest(),
        hashlib.sha256(other.content).hexdigest(),
    ]
    assert [source["response_bytes"] for source in listing["sources"]] == [
        len(nasdaq.content),
        len(other.content),
    ]
    assert all(not source["response_bytes_retained"] for source in listing["sources"])

    cik_artifact = tmp_path / "symbol_directory" / "cik_map" / f"{_DATE}.parquet"
    cik_sidecar = (
        tmp_path / "symbol_directory" / "receipts" / "cik_map" / f"{_DATE}.json"
    )
    cik = receipts.load_symbol_directory_completion_receipt(
        cik_sidecar,
        cik_artifact,
        expected_kind="sec_registrant_map",
    )
    assert cik["authority"]["listing_identity_observation_eligible"] is False
    assert cik["authority"]["sec_registrant_reference_eligible"] is True
    assert (
        cik["sources"][0]["response_sha256"] == hashlib.sha256(sec.content).hexdigest()
    )


def test_existing_legacy_files_never_retro_mint_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "symbol_directory"
    receipts.durable_atomic_write_parquet(
        _listing_frame(), root / "snapshots" / f"{_DATE}.parquet"
    )
    receipts.durable_atomic_write_parquet(
        _cik_frame(), root / "cik_map" / f"{_DATE}.parquet"
    )
    monkeypatch.setattr(collector.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(collector, "canonical_utc_now", lambda: _COLLECTOR_START)
    monkeypatch.setattr(
        collector,
        "_fetch_text",
        Mock(side_effect=AssertionError("legacy snapshot must not be fetched")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_sec_json",
        Mock(side_effect=AssertionError("legacy CIK map must not be fetched")),
    )

    result = collector.SymbolDirectoryAdapter().fetch()

    assert result["symbol_directory__ingest"].iloc[0]["snapshot_written"] == 0
    assert result["symbol_directory__ingest"].iloc[0]["cik_written"] == 0
    assert not (root / "receipts" / "snapshots" / f"{_DATE}.json").exists()
    assert not (root / "receipts" / "cik_map" / f"{_DATE}.json").exists()


def test_listing_parse_cannot_claim_complete_after_skipping_a_source_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nasdaq = _nasdaq_text().replace(
        "File Creation Time:",
        "|Missing symbol|Q|N|N|100|N|N\nFile Creation Time:",
    )
    monkeypatch.setattr(
        collector, "_fetch_text", Mock(side_effect=[nasdaq, _other_text()])
    )
    adapter = collector.SymbolDirectoryAdapter()
    adapter._SNAPSHOT_MIN_ROWS = 0

    assert adapter._collect_symbol_snapshot() is None


def test_cik_parse_cannot_claim_complete_after_skipping_a_malformed_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = {
        "0": {"cik_str": 884394, "ticker": "SPY", "title": "SPY Trust"},
        "1": {"ticker": "BROKEN", "title": "Missing CIK"},
    }
    monkeypatch.setattr(collector, "_fetch_sec_json", Mock(return_value=malformed))

    assert collector.SymbolDirectoryAdapter()._collect_cik_map() is None


def test_crash_before_receipt_leaves_only_untrusted_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nasdaq, other, _ = _operational_fetches()
    monkeypatch.setattr(collector.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(collector, "_fetch_text", Mock(side_effect=[nasdaq, other]))
    monkeypatch.setattr(
        collector,
        "canonical_utc_now",
        Mock(side_effect=[_COLLECTOR_START, _COLLECTOR_DONE]),
    )
    monkeypatch.setattr(
        collector,
        "write_symbol_directory_completion_receipt",
        Mock(side_effect=RuntimeError("simulated crash before receipt publication")),
    )

    with pytest.raises(RuntimeError, match="simulated crash"):
        collector.SymbolDirectoryAdapter().fetch()

    root = tmp_path / "symbol_directory"
    assert (root / "snapshots" / f"{_DATE}.parquet").exists()
    assert not (root / "receipts" / "snapshots" / f"{_DATE}.json").exists()


def test_loader_rejects_receipt_without_artifact(tmp_path: Path) -> None:
    artifact, sidecar, _ = _listing_receipt(tmp_path)
    artifact.unlink()

    with pytest.raises(
        receipts.ReceiptValidationError, match="artifact is not a regular file"
    ):
        receipts.load_symbol_directory_completion_receipt(
            sidecar,
            artifact,
            expected_kind="listing_snapshot",
        )


def test_in_memory_validator_accepts_exact_stable_read_bytes(tmp_path: Path) -> None:
    artifact, sidecar, value = _listing_receipt(tmp_path)

    loaded = receipts.validate_symbol_directory_completion_receipt_bytes(
        value,
        sidecar.read_bytes(),
        artifact.read_bytes(),
        expected_kind="listing_snapshot",
    )

    assert loaded == value
    assert loaded["evidence_policy"] == {
        "evidence_basis": "live_captured_source_response",
        "artifact_integrity": "sha256_bytes_rows_ordered_schema.v1",
        "source_response_integrity": "sha256_bytes_commitment_at_capture.v1",
        "source_response_bytes_retained": False,
        "source_response_replay_verifiable": False,
        "filename_git_mtime_authoritative": False,
        "prospective_only": True,
        "historical_continuity_inferred": False,
    }


def test_in_memory_validator_rejects_mapping_body_disagreement(tmp_path: Path) -> None:
    artifact, sidecar, value = _listing_receipt(tmp_path)
    different_mapping = copy.deepcopy(value)
    different_mapping["profile"] = "symbol_directory.operational_capture.v999"

    with pytest.raises(receipts.ReceiptValidationError, match="does not equal"):
        receipts.validate_symbol_directory_completion_receipt_bytes(
            different_mapping,
            sidecar.read_bytes(),
            artifact.read_bytes(),
            expected_kind="listing_snapshot",
        )


@pytest.mark.parametrize(
    "body_transform",
    [
        lambda value: _canonical_receipt_body(value)[:-1],
        lambda value: json.dumps(value, indent=2, sort_keys=True).encode() + b"\n",
    ],
    ids=["missing-terminal-newline", "noncanonical-whitespace"],
)
def test_in_memory_validator_rejects_noncanonical_receipt_bytes(
    tmp_path: Path,
    body_transform,
) -> None:
    artifact, _, value = _listing_receipt(tmp_path)

    with pytest.raises(receipts.ReceiptValidationError, match="not canonical JSON"):
        receipts.validate_symbol_directory_completion_receipt_bytes(
            value,
            body_transform(value),
            artifact.read_bytes(),
            expected_kind="listing_snapshot",
        )


def test_in_memory_validator_rejects_duplicate_fields_in_exact_body(
    tmp_path: Path,
) -> None:
    artifact, _, value = _listing_receipt(tmp_path)
    canonical = _canonical_receipt_body(value)
    duplicate = b'{"schema":"duplicate",' + canonical[1:]

    with pytest.raises(receipts.ReceiptValidationError, match="duplicate JSON field"):
        receipts.validate_symbol_directory_completion_receipt_bytes(
            value,
            duplicate,
            artifact.read_bytes(),
            expected_kind="listing_snapshot",
        )


def test_in_memory_validator_rejects_exact_artifact_byte_tamper(tmp_path: Path) -> None:
    artifact, sidecar, value = _listing_receipt(tmp_path)
    tampered = bytearray(artifact.read_bytes())
    tampered[-1] ^= 1

    with pytest.raises(receipts.ReceiptValidationError, match="SHA-256"):
        receipts.validate_symbol_directory_completion_receipt_bytes(
            value,
            sidecar.read_bytes(),
            bytes(tampered),
            expected_kind="listing_snapshot",
        )


def test_recomputed_receipt_id_cannot_widen_authority(tmp_path: Path) -> None:
    artifact, _, value = _listing_receipt(tmp_path)
    widened = copy.deepcopy(value)
    widened["authority"]["context_only"] = False
    widened["authority"]["may_trade"] = True
    _recompute_receipt_id(widened)

    with pytest.raises(receipts.ReceiptValidationError, match="schema violation"):
        receipts.validate_symbol_directory_completion_receipt_bytes(
            widened,
            _canonical_receipt_body(widened),
            artifact.read_bytes(),
            expected_kind="listing_snapshot",
        )


def test_complete_spy_absent_listing_is_valid_operational_evidence(
    tmp_path: Path,
) -> None:
    artifact, value = _listing_absent_receipt(tmp_path)

    loaded = receipts.validate_symbol_directory_completion_receipt_bytes(
        value,
        _canonical_receipt_body(value),
        artifact.read_bytes(),
        expected_kind="listing_snapshot",
    )

    assert loaded["diagnostics"]["pre_dedupe_spy_occurrence_count"] == 0
    assert loaded["diagnostics"]["pre_dedupe_spy_occurrences"] == []
    assert loaded["evidence_policy"]["historical_continuity_inferred"] is False


def test_spy_absent_artifact_rejects_recomputed_present_diagnostic(
    tmp_path: Path,
) -> None:
    artifact, value = _listing_absent_receipt(tmp_path)
    false_present = copy.deepcopy(value)
    false_present["diagnostics"]["pre_dedupe_spy_occurrence_count"] = 1
    false_present["diagnostics"]["pre_dedupe_spy_occurrences"] = [
        {
            "source_id": receipts.OTHER_LISTED_SOURCE_ID,
            "symbol": "SPY",
            "security_name": "SPDR S&P 500 ETF Trust",
            "exchange": "P",
            "etf": True,
            "test_issue": False,
            "is_preferred": False,
        }
    ]
    _recompute_receipt_id(false_present)

    with pytest.raises(receipts.ReceiptValidationError, match="SPY-absent"):
        receipts.validate_symbol_directory_completion_receipt_bytes(
            false_present,
            _canonical_receipt_body(false_present),
            artifact.read_bytes(),
            expected_kind="listing_snapshot",
        )


def test_receipt_id_uses_market_memory_empty_identity_field_basis(
    tmp_path: Path,
) -> None:
    _, _, value = _listing_receipt(tmp_path)
    core = copy.deepcopy(value)
    core["receipt_id"] = ""
    identity_bytes = json.dumps(
        core,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    expected = "sdreceipt_" + hashlib.sha256(identity_bytes).hexdigest()

    assert value["receipt_id"] == expected


def test_loader_rejects_same_size_artifact_hash_mismatch(tmp_path: Path) -> None:
    artifact, sidecar, _ = _listing_receipt(tmp_path)
    body = bytearray(artifact.read_bytes())
    body[-1] ^= 1
    artifact.write_bytes(body)

    with pytest.raises(receipts.ReceiptValidationError, match="SHA-256"):
        receipts.load_symbol_directory_completion_receipt(
            sidecar,
            artifact,
            expected_kind="listing_snapshot",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["artifact"].pop("sha256"), "schema violation"),
        (lambda value: value.update({"unknown": True}), "schema violation"),
        (
            lambda value: value["clocks"].update(
                {"collector_started_at": f"{_DATE}T00:00:00Z"}
            ),
            "schema violation",
        ),
        (
            lambda value: value["diagnostics"]["pre_dedupe_spy_occurrences"].append(
                copy.deepcopy(value["diagnostics"]["pre_dedupe_spy_occurrences"][0])
            ),
            "schema violation",
        ),
        (
            lambda value: value["sources"].__setitem__(
                1, copy.deepcopy(value["sources"][0])
            ),
            "schema violation",
        ),
        (
            lambda value: value["authority"].update(
                {"sec_registrant_reference_eligible": True}
            ),
            "schema violation",
        ),
    ],
    ids=[
        "partial",
        "unknown",
        "noncanonical-clock",
        "duplicate-spy",
        "duplicate-source",
        "lane-mix",
    ],
)
def test_strict_validator_rejects_malformed_receipts(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    artifact, _, value = _listing_receipt(tmp_path)
    malformed = copy.deepcopy(value)
    mutation(malformed)

    with pytest.raises(receipts.ReceiptValidationError, match=message):
        receipts.validate_symbol_directory_completion_receipt(
            malformed,
            artifact,
            expected_kind="listing_snapshot",
        )


def test_loader_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    artifact = tmp_path / "symbol_directory" / "snapshots" / f"{_DATE}.parquet"
    receipts.durable_atomic_write_parquet(_listing_frame(), artifact)
    sidecar = tmp_path / "duplicate.json"
    sidecar.write_text('{"schema":"one","schema":"two"}')

    with pytest.raises(receipts.ReceiptValidationError, match="duplicate JSON field"):
        receipts.load_symbol_directory_completion_receipt(
            sidecar,
            artifact,
            expected_kind="listing_snapshot",
        )


def test_expected_kind_prevents_cik_listing_authority_mix(tmp_path: Path) -> None:
    artifact, sidecar, _ = _listing_receipt(tmp_path)

    with pytest.raises(receipts.ReceiptValidationError, match="does not match"):
        receipts.load_symbol_directory_completion_receipt(
            sidecar,
            artifact,
            expected_kind="sec_registrant_map",
        )


def test_artifact_publication_fsyncs_file_before_atomic_link_and_parent_after(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    real_fsync = receipts.os.fsync
    real_link = receipts.os.link

    def record_fsync(descriptor: int) -> None:
        events.append(
            "parent_fsync"
            if stat.S_ISDIR(os.fstat(descriptor).st_mode)
            else "file_fsync"
        )
        real_fsync(descriptor)

    def record_link(source: Path, destination: Path) -> None:
        events.append("atomic_absent_only_link")
        real_link(source, destination)

    monkeypatch.setattr(receipts.os, "fsync", record_fsync)
    monkeypatch.setattr(receipts.os, "link", record_link)

    artifact = tmp_path / "artifact" / "sample.parquet"
    receipts.durable_atomic_write_parquet(_cik_frame(), artifact)

    assert events == ["file_fsync", "atomic_absent_only_link", "parent_fsync"]
    assert artifact.exists()


def test_receipt_publication_fsyncs_file_before_atomic_link_and_parent_after(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    real_fsync = receipts.os.fsync
    real_link = receipts.os.link

    def record_fsync(descriptor: int) -> None:
        events.append(
            "parent_fsync"
            if stat.S_ISDIR(os.fstat(descriptor).st_mode)
            else "file_fsync"
        )
        real_fsync(descriptor)

    def record_link(source: Path, destination: Path) -> None:
        events.append("atomic_absent_only_link")
        real_link(source, destination)

    monkeypatch.setattr(receipts.os, "fsync", record_fsync)
    monkeypatch.setattr(receipts.os, "link", record_link)

    sidecar = tmp_path / "receipts" / "sample.json"
    receipts._durable_absent_only_write(sidecar, b"{}\n")

    assert events == ["file_fsync", "atomic_absent_only_link", "parent_fsync"]
    assert sidecar.read_bytes() == b"{}\n"


def test_artifact_publication_is_absent_only(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact" / "sample.parquet"
    receipts.durable_atomic_write_parquet(_cik_frame(), artifact)
    original = artifact.read_bytes()

    with pytest.raises(FileExistsError):
        receipts.durable_atomic_write_parquet(
            pd.DataFrame([{"ticker": "SPY", "cik": 1, "title": "Wrong"}]),
            artifact,
        )

    assert artifact.read_bytes() == original


def test_receipt_publication_is_absent_only(tmp_path: Path) -> None:
    artifact, sidecar, value = _listing_receipt(tmp_path)
    original = sidecar.read_bytes()

    with pytest.raises(receipts.ReceiptValidationError, match="refusing to overwrite"):
        receipts.write_symbol_directory_completion_receipt(
            sidecar,
            value,
            artifact,
            expected_kind="listing_snapshot",
        )

    assert sidecar.read_bytes() == original
