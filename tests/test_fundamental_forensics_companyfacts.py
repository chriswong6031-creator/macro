from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path

import pytest

import collectors.fundamental_forensics_companyfacts as companyfacts
from collectors.fundamental_forensics_companyfacts import (
    COMPANYFACTS_MANIFEST_ROOT,
    COMPANYFACTS_RAW_NAMESPACE,
    OPERATOR_CONSTRAINTS,
    CompanyFactsAcquisitionError,
    CompanyFactsResponseTooLarge,
    acquire_companyfacts,
    companyfacts_capture_from_json_bytes,
    companyfacts_capture_storage_key,
    companyfacts_manifest_storage_key,
    companyfacts_url,
    iter_companyfacts_occurrences,
    manifest_id_for,
    parse_companyfacts_response_exact_numbers,
    persist_companyfacts_manifest,
    publish_verified_manifest_pointer,
    read_companyfacts_manifest,
    read_latest_companyfacts_manifest,
    read_verified_companyfacts,
    validate_companyfacts_response_bytes,
)
from engine.fundamental_forensics.models import canonical_json


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
USER_AGENT = "MastermindX research@example.com"


@pytest.mark.parametrize("cik", ("0", "0000000000", "١", "１２", "1\u0662", "1e2", "-1"))
def test_companyfacts_url_rejects_non_ascii_cik_identifiers(cik: str):
    with pytest.raises(CompanyFactsAcquisitionError, match="invalid CIK"):
        companyfacts_url(cik)


def _clock(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
        reject_content_property: bool = False,
    ) -> None:
        self._body = body
        self._chunks = chunks
        self._reject_content_property = reject_content_property
        self.status_code = status_code
        self.headers = headers or {
            "ETag": '"fixture"',
            "Last-Modified": "Sat, 01 Aug 2026 12:00:00 GMT",
        }
        self.content_touched = False
        self.closed = False
        self.stream_chunk_sizes: list[int] = []

    @property
    def content(self) -> bytes:
        self.content_touched = True
        if self._reject_content_property:
            raise AssertionError("bounded collector must not read response.content")
        return self._body

    def iter_content(self, *, chunk_size: int):
        self.stream_chunk_sizes.append(chunk_size)
        if self._chunks is not None:
            yield from self._chunks
            return
        for offset in range(0, len(self._body), max(1, min(chunk_size, 97))):
            yield self._body[offset : offset + max(1, min(chunk_size, 97))]

    def close(self) -> None:
        self.closed = True


class _Fetcher:
    def __init__(
        self,
        bodies: dict[str, bytes] | bytes,
        *,
        response_headers: dict[str, str] | None = None,
        response_factory=None,
    ) -> None:
        self.bodies = bodies
        self.response_headers = response_headers
        self.response_factory = response_factory
        self.calls: list[tuple[str, dict[str, str], float, bool]] = []
        self.responses: list[_Response] = []

    def __call__(self, url: str, *, headers: dict[str, str], timeout: float, stream: bool):
        self.calls.append((url, dict(headers), timeout, stream))
        body = self.bodies[url] if isinstance(self.bodies, dict) else self.bodies
        response = (
            self.response_factory(body, url)
            if self.response_factory is not None
            else _Response(body, headers=self.response_headers)
        )
        self.responses.append(response)
        return response


def _payload(
    cik: str = "0000000001", *, val: int | float = 100, filed: str = "2025-02-15"
) -> dict:
    duplicate = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "val": val,
        "accn": "0000000001-25-000001",
        "fy": 2024,
        "fp": "FY",
        "form": "10-K",
        "filed": filed,
        "frame": "CY2024",
    }
    return {
        "cik": int(cik),
        "entityName": "Fixture Company",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            duplicate,
                            dict(duplicate),
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 30,
                                "accn": "0000000001-25-000002",
                                "fy": 2025,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2025-05-01",
                                "frame": "CY2025Q1",
                            },
                        ]
                    },
                }
            }
        },
    }


def _body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _run(tmp_path: Path, fetcher: _Fetcher, *, now: datetime = NOW, **overrides):
    return acquire_companyfacts(
        targets=overrides.pop("targets", ("FXT=1",)),
        raw_root=overrides.pop("raw_root", tmp_path / "raw"),
        archive_root=overrides.pop("archive_root", tmp_path / "archive"),
        user_agent=overrides.pop("user_agent", USER_AGENT),
        source_snapshot_at=overrides.pop("source_snapshot_at", _clock(now)),
        recorded_at=overrides.pop("recorded_at", _clock(now)),
        fetcher=fetcher,
        utc_now=overrides.pop("utc_now", lambda: now),
        **overrides,
    )


def _run_receipt(result: dict) -> dict:
    assert set(result) == {"run", "run_key"}
    return result["run"]


def _capture_for(tmp_path: Path, manifest: dict) -> dict:
    key = manifest["source"]["capture_receipt_key"]
    return json.loads((tmp_path / "raw" / key).read_text(encoding="utf-8"))


def test_public_capture_and_response_validators_bind_canonical_source_paths(tmp_path: Path):
    payload = _payload()
    response = _body(payload)
    run = _run_receipt(_run(tmp_path, _Fetcher(response)))
    manifest = read_companyfacts_manifest(
        tmp_path / "archive", run["ticker_receipts"][0]["manifest_key"]
    )
    capture_record = _capture_for(tmp_path, manifest)
    capture_bytes = canonical_json(capture_record).encode("utf-8")

    capture = companyfacts_capture_from_json_bytes(capture_bytes)
    decoded, logical, occurrence_count, occurrence_sha = validate_companyfacts_response_bytes(
        response, expected_cik="1"
    )

    assert capture.to_dict() == capture_record
    assert companyfacts_capture_storage_key("1", capture.capture_id) == manifest["source"][
        "capture_receipt_key"
    ]
    assert companyfacts_manifest_storage_key(manifest) == run["ticker_receipts"][0][
        "manifest_key"
    ]
    assert decoded == payload
    assert sha256(logical).hexdigest() == manifest["source"]["logical_sha256"]
    assert occurrence_count == manifest["source"]["fact_occurrence_count"]
    assert occurrence_sha == manifest["source"]["fact_occurrence_sha256"]

    with pytest.raises(CompanyFactsAcquisitionError, match="duplicate JSON key"):
        validate_companyfacts_response_bytes(
            b'{"cik":1,"cik":1,"facts":{}}', expected_cik="1"
        )

    noncanonical_capture = json.dumps(capture_record, indent=2).encode("utf-8")
    with pytest.raises(CompanyFactsAcquisitionError, match="canonically encoded"):
        companyfacts_capture_from_json_bytes(noncanonical_capture)


def test_exact_number_projection_parse_never_collapses_distinct_sec_decimals():
    response = (
        b'{"cik":1,"entityName":"Fixture","facts":{"us-gaap":{"Metric":{"units":'
        b'{"USD":[{"accn":"0000000001-25-000001","end":"2024-12-31",'
        b'"val":1.0000000000000000000000000001}]}}}}}'
    )
    legacy, _, _, _ = validate_companyfacts_response_bytes(response, expected_cik="1")
    exact = parse_companyfacts_response_exact_numbers(response, expected_cik="1")

    legacy_value = legacy["facts"]["us-gaap"]["Metric"]["units"]["USD"][0]["val"]
    exact_value = exact["facts"]["us-gaap"]["Metric"]["units"]["USD"][0]["val"]
    assert legacy_value == 1.0
    assert exact_value == Decimal("1.0000000000000000000000000001")
    assert exact_value != Decimal("1")

    exponent_bomb = response.replace(
        b"1.0000000000000000000000000001", b"1e999999999"
    )
    with pytest.raises(CompanyFactsAcquisitionError, match="exponent"):
        parse_companyfacts_response_exact_numbers(exponent_bomb, expected_cik="1")

    too_deep = b'{"cik":1,"facts":' + b"[" * 70 + b"0" + b"]" * 70 + b"}"
    with pytest.raises(CompanyFactsAcquisitionError, match="depth safety limit"):
        validate_companyfacts_response_bytes(too_deep, expected_cik="1")
    with pytest.raises(CompanyFactsAcquisitionError, match="depth safety limit"):
        parse_companyfacts_response_exact_numbers(too_deep, expected_cik="1")

    huge_integer = response.replace(
        b"1.0000000000000000000000000001", b"9" * 257
    )
    with pytest.raises(CompanyFactsAcquisitionError, match="integer token"):
        parse_companyfacts_response_exact_numbers(huge_integer, expected_cik="1")


def test_acquires_current_byte_faithful_snapshot_with_verified_pointer(tmp_path: Path):
    payload = _payload(filed="2030-01-15")
    fetcher = _Fetcher(_body(payload))
    result = _run(tmp_path, fetcher)
    run = _run_receipt(result)

    companyfacts._validate_run(run)
    assert json.loads((tmp_path / "archive" / result["run_key"]).read_text()) == run
    assert run["status"] == "complete"
    assert "as_of" not in run["clocks"]
    assert run["clocks"] == {
        "source_snapshot_at": "2026-08-01T12:00:00.000000Z",
        "recorded_at": "2026-08-01T12:00:00.000000Z",
        "acquisition_started_at": "2026-08-01T12:00:00.000000Z",
    }
    assert run["operator_constraints"] == list(OPERATOR_CONSTRAINTS)

    receipt = run["ticker_receipts"][0]
    assert receipt["status"] == "complete"
    assert receipt["bytes_retained"] == len(_body(payload))
    manifest = read_companyfacts_manifest(tmp_path / "archive", receipt["manifest_key"])
    assert manifest["issuer"] == {
        "ticker": "FXT",
        "cik": "0000000001",
        "entity_name": "Fixture Company",
    }
    assert manifest["temporal_scope"] == {
        "kind": "current_sec_companyfacts_snapshot",
        "point_in_time_eligible": False,
        "acceptance_joined": False,
        "fact_filed_dates_preserved": True,
    }
    assert manifest["source"]["fact_occurrence_count"] == 3
    assert _capture_for(tmp_path, manifest)["logical"]["occurrence_fields"] == [
        "accn",
        "filed",
        "form",
        "fy",
        "fp",
        "frame",
        "end",
        "start",
    ]

    restored, verified_manifest = read_verified_companyfacts(
        tmp_path / "raw", tmp_path / "archive", 1
    )
    assert restored == payload
    assert verified_manifest == manifest
    # A fact filed after the snapshot label is retained, but the manifest says
    # this source cannot be used as a point-in-time dataset.
    assert restored["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]["units"]["USD"][0]["filed"] == "2030-01-15"
    assert (tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT / "0000000001" / "latest.json").exists()
    assert (tmp_path / "raw" / "0000000001" / COMPANYFACTS_RAW_NAMESPACE).exists()
    assert fetcher.calls == [
        (
            companyfacts_url(1),
            {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            30.0,
            True,
        )
    ]


def test_persisted_canonical_ticker_and_run_receipts_validate_after_json_key_sorting(
    tmp_path: Path,
):
    result = _run(tmp_path, _Fetcher(_body(_payload())))
    run = _run_receipt(result)
    archive = tmp_path / "archive"
    persisted_ticker = json.loads(
        (archive / run["ticker_receipt_keys"][0]).read_text(encoding="utf-8")
    )
    persisted_run = json.loads(
        (archive / result["run_key"]).read_text(encoding="utf-8")
    )

    # Immutable files are canonical JSON with sort_keys=True, so nested clock
    # order is alphabetical rather than construction order. Object order is
    # not semantic; both persisted receipts must remain independently valid.
    assert tuple(persisted_ticker["clocks"]) == tuple(
        sorted(persisted_ticker["clocks"])
    )
    assert tuple(persisted_run["clocks"]) == tuple(sorted(persisted_run["clocks"]))
    companyfacts._validate_ticker_receipt(persisted_ticker)
    companyfacts._validate_run(persisted_run)

    # Receipt IDs bind canonical JSON, not incidental dict insertion order.
    # A caller deserializing through a differently ordered mapping must get the
    # same valid immutable receipt rather than a false integrity failure.
    shuffled_ticker = deepcopy(persisted_ticker)
    shuffled_ticker["clocks"] = {
        key: persisted_ticker["clocks"][key]
        for key in reversed(tuple(persisted_ticker["clocks"]))
    }
    shuffled_run = deepcopy(persisted_run)
    shuffled_run["clocks"] = {
        key: persisted_run["clocks"][key]
        for key in reversed(tuple(persisted_run["clocks"]))
    }
    assert shuffled_ticker["ticker_receipt_id"] == persisted_ticker["ticker_receipt_id"]
    assert shuffled_run["run_id"] == persisted_run["run_id"]
    companyfacts._validate_ticker_receipt(shuffled_ticker)
    companyfacts._validate_run(shuffled_run)


def test_occurrence_iterator_retains_duplicate_rows_and_sec_vintage_metadata():
    payload = _payload()
    occurrences = list(iter_companyfacts_occurrences(payload))

    assert len(occurrences) == 3
    assert [item["entry_index"] for item in occurrences[:2]] == [0, 1]
    assert occurrences[0]["sec_fact"] == occurrences[1]["sec_fact"]
    assert occurrences[0]["sec_fact"] == {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "val": 100,
        "accn": "0000000001-25-000001",
        "fy": 2024,
        "fp": "FY",
        "form": "10-K",
        "filed": "2025-02-15",
        "frame": "CY2024",
    }


def test_new_raw_namespace_cannot_overwrite_generic_edgar_companyfacts_pointer(tmp_path: Path):
    generic_latest = tmp_path / "raw" / "0000000001" / "companyfacts" / "latest.json"
    generic_latest.parent.mkdir(parents=True)
    original = b'{"schema":"fundamental_forensics_retrieval.v1","sentinel":true}\n'
    generic_latest.write_bytes(original)

    run = _run_receipt(_run(tmp_path, _Fetcher(_body(_payload()))))

    assert run["status"] == "complete"
    assert generic_latest.read_bytes() == original
    assert list((tmp_path / "raw" / "0000000001" / COMPANYFACTS_RAW_NAMESPACE / "objects").rglob("*.json.gz"))
    assert not list((tmp_path / "raw" / "0000000001" / "companyfacts").rglob("*.tmp"))


def test_rejects_historical_or_future_snapshot_labels_and_legacy_as_of(tmp_path: Path):
    fetcher = _Fetcher(_body(_payload()))
    with pytest.raises(CompanyFactsAcquisitionError, match="source_snapshot_at must be contemporaneous"):
        _run(
            tmp_path,
            fetcher,
            source_snapshot_at=_clock(NOW - timedelta(seconds=6)),
        )
    with pytest.raises(CompanyFactsAcquisitionError, match="recorded_at must be contemporaneous"):
        _run(
            tmp_path,
            fetcher,
            source_snapshot_at=_clock(NOW + timedelta(seconds=6)),
            recorded_at=_clock(NOW + timedelta(seconds=6)),
        )
    with pytest.raises(CompanyFactsAcquisitionError, match="source_snapshot_at must be contemporaneous"):
        _run(
            tmp_path,
            fetcher,
            source_snapshot_at=_clock(NOW + timedelta(seconds=6)),
        )
    with pytest.raises(TypeError, match="unexpected keyword argument 'as_of'"):
        acquire_companyfacts(
            targets=("FXT=1",),
            raw_root=tmp_path / "legacy-raw",
            archive_root=tmp_path / "legacy-archive",
            user_agent=USER_AGENT,
            source_snapshot_at=_clock(NOW),
            recorded_at=_clock(NOW),
            as_of=_clock(NOW),
        )
    assert fetcher.calls == []


def test_caller_clock_sampled_just_before_acquisition_is_normalized_truthfully(
    tmp_path: Path,
):
    fetcher = _Fetcher(_body(_payload()))
    observed = iter(
        (
            NOW + timedelta(microseconds=1),
            NOW + timedelta(microseconds=2),
            NOW + timedelta(microseconds=3),
        )
    )
    run = _run_receipt(
        _run(tmp_path, fetcher, utc_now=lambda: next(observed))
    )
    receipt = run["ticker_receipts"][0]
    manifest = read_companyfacts_manifest(
        tmp_path / "archive", receipt["manifest_key"]
    )

    assert run["status"] == "complete"
    assert run["clocks"] == {
        "source_snapshot_at": "2026-08-01T12:00:00.000001Z",
        "recorded_at": "2026-08-01T12:00:00.000003Z",
        "acquisition_started_at": "2026-08-01T12:00:00.000001Z",
    }
    assert receipt["clocks"]["captured_at"] == (
        "2026-08-01T12:00:00.000002Z"
    )
    assert receipt["clocks"]["recorded_at"] == "2026-08-01T12:00:00.000002Z"
    assert manifest["clocks"]["recorded_at"] == manifest["clocks"]["captured_at"]


def test_contemporaneous_caller_snapshot_cannot_backdate_current_acquisition(
    tmp_path: Path,
):
    observed = iter(
        (
            NOW + timedelta(seconds=2),
            NOW + timedelta(seconds=3),
            NOW + timedelta(seconds=4),
        )
    )
    run = _run_receipt(
        _run(
            tmp_path,
            _Fetcher(_body(_payload())),
            utc_now=lambda: next(observed),
        )
    )

    assert run["clocks"] == {
        "source_snapshot_at": "2026-08-01T12:00:02.000000Z",
        "recorded_at": "2026-08-01T12:00:04.000000Z",
        "acquisition_started_at": "2026-08-01T12:00:02.000000Z",
    }
    assert run["ticker_receipts"][0]["clocks"]["captured_at"] == (
        "2026-08-01T12:00:03.000000Z"
    )
    assert run["ticker_receipts"][0]["clocks"]["recorded_at"] == (
        "2026-08-01T12:00:03.000000Z"
    )

    manifest = read_companyfacts_manifest(
        tmp_path / "archive",
        run["ticker_receipts"][0]["manifest_key"],
    )
    forged = deepcopy(manifest)
    forged["clocks"]["source_snapshot_at"] = (
        "2026-08-01T12:00:01.000000Z"
    )
    forged["manifest_id"] = manifest_id_for(forged)
    with pytest.raises(CompanyFactsAcquisitionError, match="acquisition-normalized"):
        companyfacts.validate_companyfacts_manifest(forged)


def test_public_retention_clocks_follow_durable_capture_on_slow_or_future_bounded_runs(
    tmp_path: Path,
):
    slow_observed = iter(
        (
            NOW,
            NOW + timedelta(seconds=60),
            NOW + timedelta(seconds=61),
        )
    )
    slow_run = _run_receipt(
        _run(
            tmp_path / "slow",
            _Fetcher(_body(_payload())),
            utc_now=lambda: next(slow_observed),
        )
    )
    slow_receipt = slow_run["ticker_receipts"][0]
    slow_manifest = read_companyfacts_manifest(
        tmp_path / "slow" / "archive", slow_receipt["manifest_key"]
    )
    slow_capture = _capture_for(tmp_path / "slow", slow_manifest)
    slow_pointer = json.loads(
        (
            tmp_path
            / "slow"
            / "archive"
            / COMPANYFACTS_MANIFEST_ROOT
            / "0000000001"
            / "latest.json"
        ).read_text(encoding="utf-8")
    )

    retained_at = "2026-08-01T12:01:00.000000Z"
    assert slow_capture["clocks"]["captured_at"] == retained_at
    assert slow_capture["clocks"]["recorded_at"] == retained_at
    assert slow_manifest["clocks"]["recorded_at"] == retained_at
    assert slow_pointer["recorded_at"] == retained_at
    assert slow_receipt["clocks"]["recorded_at"] == retained_at
    assert slow_run["clocks"]["recorded_at"] == "2026-08-01T12:01:01.000000Z"

    forged_early = deepcopy(slow_manifest)
    forged_early["clocks"]["recorded_at"] = "2026-08-01T12:00:00.000000Z"
    forged_early["manifest_id"] = manifest_id_for(forged_early)
    with pytest.raises(CompanyFactsAcquisitionError, match="predates durable"):
        companyfacts.validate_companyfacts_manifest(forged_early)

    future_observed = iter(
        (
            NOW,
            NOW + timedelta(seconds=1),
            NOW + timedelta(seconds=2),
        )
    )
    future_run = _run_receipt(
        _run(
            tmp_path / "future-lower-bound",
            _Fetcher(_body(_payload())),
            source_snapshot_at=_clock(NOW + timedelta(seconds=4)),
            recorded_at=_clock(NOW + timedelta(seconds=4)),
            utc_now=lambda: next(future_observed),
        )
    )
    future_manifest = read_companyfacts_manifest(
        tmp_path / "future-lower-bound" / "archive",
        future_run["ticker_receipts"][0]["manifest_key"],
    )
    # A bounded caller future sample can only make public replay later; it
    # cannot bring recorded_at forward before the durable response exists.
    assert future_manifest["clocks"]["captured_at"] == "2026-08-01T12:00:01.000000Z"
    assert future_manifest["clocks"]["recorded_at"] == "2026-08-01T12:00:04.000000Z"
    assert future_manifest["clocks"]["recorded_at"] >= future_manifest["clocks"]["captured_at"]


def test_recorded_at_outside_symmetric_tolerance_is_rejected_before_network(
    tmp_path: Path,
):
    fetcher = _Fetcher(_body(_payload()))
    with pytest.raises(
        CompanyFactsAcquisitionError,
        match="recorded_at must be contemporaneous",
    ):
        _run(
            tmp_path,
            fetcher,
            recorded_at=_clock(NOW - timedelta(seconds=6)),
        )
    assert fetcher.calls == []


def test_streaming_cap_never_reads_content_property_or_persists_oversize_body(tmp_path: Path):
    body = _body(_payload())
    fetcher = _Fetcher(
        body,
        response_factory=lambda returned_body, _url: _Response(
            returned_body,
            chunks=[returned_body],
            reject_content_property=True,
        ),
    )
    run = _run_receipt(
        _run(
            tmp_path,
            fetcher,
            max_response_bytes=len(body) - 1,
            max_ticker_bytes=len(body) - 1,
            max_total_bytes=len(body) - 1,
        )
    )

    receipt = run["ticker_receipts"][0]
    response = fetcher.responses[0]
    assert run["status"] == "partial"
    assert receipt["status"] == "failed"
    assert receipt["failures"][0]["error_type"] == CompanyFactsResponseTooLarge.__name__
    assert response.content_touched is False
    assert response.stream_chunk_sizes == [64 * 1024]
    assert response.closed is True
    assert fetcher.calls[0][3] is True
    assert not list((tmp_path / "raw").rglob("*.json.gz"))


def test_raw_object_is_exact_response_bytes_and_logical_hash_is_separate(tmp_path: Path):
    payload = _payload(val=1.23)
    compact = _body(payload)
    body = b"\n  " + compact.replace(b'"val":1.23', b'"val":1.2300', 1) + b" \n"
    run = _run_receipt(_run(tmp_path, _Fetcher(body)))
    manifest = read_companyfacts_manifest(tmp_path / "archive", run["ticker_receipts"][0]["manifest_key"])
    source = manifest["source"]

    with gzip.open(tmp_path / "raw" / source["response_object_path"], "rb") as handle:
        assert handle.read() == body
    assert source["response_sha256"] == sha256(body).hexdigest()
    assert source["logical_sha256"] == sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    assert source["response_sha256"] != source["logical_sha256"]
    assert read_verified_companyfacts(tmp_path / "raw", tmp_path / "archive", 1)[0] == payload


def test_manifest_failure_never_publishes_unverified_latest_pointer(tmp_path: Path, monkeypatch):
    def fail_manifest(*_args, **_kwargs):
        raise OSError("forced immutable-manifest write failure")

    monkeypatch.setattr(companyfacts, "persist_companyfacts_manifest", fail_manifest)
    run = _run_receipt(_run(tmp_path, _Fetcher(_body(_payload()))))

    assert run["status"] == "partial"
    receipt = run["ticker_receipts"][0]
    assert receipt["status"] == "failed"
    assert receipt["bytes_retained"] == len(_body(_payload()))
    assert run["bytes_retained"] == receipt["bytes_retained"]
    assert receipt["capture_id"] is not None
    assert receipt["capture_receipt_key"] is not None
    assert receipt["manifest_key"] is None
    assert receipt["clocks"]["captured_at"] is not None
    latest = tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT / "0000000001" / "latest.json"
    assert not latest.exists()
    with pytest.raises(CompanyFactsAcquisitionError, match="missing or invalid verified"):
        read_verified_companyfacts(tmp_path / "raw", tmp_path / "archive", 1)


def test_retained_bytes_survive_manifest_failure_and_exhaust_run_budget(
    tmp_path: Path, monkeypatch
):
    first_body = _body(_payload("0000000001"))
    second_body = _body(_payload("0000000002"))
    assert len(first_body) == len(second_body)
    fetcher = _Fetcher(
        {
            companyfacts_url(1): first_body,
            companyfacts_url(2): second_body,
        }
    )

    def fail_manifest(*_args, **_kwargs):
        raise OSError("forced immutable-manifest write failure")

    monkeypatch.setattr(companyfacts, "persist_companyfacts_manifest", fail_manifest)
    run = _run_receipt(
        _run(
            tmp_path,
            fetcher,
            targets=("ONE=1", "TWO=2"),
            max_response_bytes=len(first_body),
            max_ticker_bytes=len(first_body),
            max_total_bytes=len(first_body),
        )
    )

    companyfacts._validate_run(run)
    first, second = run["ticker_receipts"]
    assert run["bytes_retained"] == len(first_body)
    assert first["bytes_retained"] == len(first_body)
    assert first["capture_id"] is not None
    assert first["manifest_key"] is None
    assert second["bytes_retained"] == 0
    assert second["capture_id"] is None
    assert "budget exhausted" in second["failures"][0]["message"]
    assert len(fetcher.calls) == 1
    assert len(list((tmp_path / "raw").rglob("*.json.gz"))) == 1
    assert not list((tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT).rglob("latest.json"))


def test_durable_object_readback_failure_is_charged_and_exhausts_run_budget(
    tmp_path: Path, monkeypatch
):
    first_body = _body(_payload("0000000001"))
    second_body = _body(_payload("0000000002"))
    assert len(first_body) == len(second_body)
    fetcher = _Fetcher(
        {
            companyfacts_url(1): first_body,
            companyfacts_url(2): second_body,
        }
    )

    def fail_postwrite_readback(*_args, **_kwargs):
        raise CompanyFactsAcquisitionError("forced post-write object readback failure")

    # The first response has already passed the atomic raw-object write when
    # this read-back is attempted. It must consume the only run-sized budget
    # even though no capture/manifest/pointer is allowed to claim success.
    monkeypatch.setattr(companyfacts, "_read_gzip_limited", fail_postwrite_readback)
    run = _run_receipt(
        _run(
            tmp_path,
            fetcher,
            targets=("ONE=1", "TWO=2"),
            max_response_bytes=len(first_body),
            max_ticker_bytes=len(first_body),
            max_total_bytes=len(first_body),
        )
    )

    companyfacts._validate_run(run)
    first, second = run["ticker_receipts"]
    assert run["status"] == "partial"
    assert run["bytes_retained"] == len(first_body)
    assert first["status"] == "failed"
    assert first["bytes_retained"] == len(first_body)
    assert first["capture_id"] is None
    assert first["manifest_key"] is None
    assert second["bytes_retained"] == 0
    assert "budget exhausted" in second["failures"][0]["message"]
    assert len(fetcher.calls) == 1
    assert len(list((tmp_path / "raw").rglob("*.json.gz"))) == 1
    assert not list((tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT).rglob("latest.json"))


def test_post_replace_write_error_is_charged_when_exact_raw_object_survived(
    tmp_path: Path, monkeypatch
):
    first_body = _body(_payload("0000000001"))
    second_body = _body(_payload("0000000002"))
    assert len(first_body) == len(second_body)
    fetcher = _Fetcher(
        {
            companyfacts_url(1): first_body,
            companyfacts_url(2): second_body,
        }
    )
    original_atomic_write = companyfacts._atomic_write

    def write_then_report_failure(path: Path, content: bytes):
        original_atomic_write(path, content)
        if path.suffix == ".gz":
            # Simulates a filesystem error surfaced after os.replace().
            raise OSError("forced post-replace write error")

    monkeypatch.setattr(companyfacts, "_atomic_write", write_then_report_failure)
    run = _run_receipt(
        _run(
            tmp_path,
            fetcher,
            targets=("ONE=1", "TWO=2"),
            max_response_bytes=len(first_body),
            max_ticker_bytes=len(first_body),
            max_total_bytes=len(first_body),
        )
    )

    companyfacts._validate_run(run)
    first, second = run["ticker_receipts"]
    assert first["status"] == "failed"
    assert first["bytes_retained"] == len(first_body)
    assert first["capture_id"] is None
    assert first["capture_receipt_key"] is None
    assert first["manifest_key"] is None
    assert second["bytes_retained"] == 0
    assert "budget exhausted" in second["failures"][0]["message"]
    assert len(fetcher.calls) == 1
    assert len(list((tmp_path / "raw").rglob("*.json.gz"))) == 1
    assert not list((tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT).rglob("latest.json"))


def test_manifest_clock_forgery_cannot_be_read_as_its_capture(tmp_path: Path):
    result = _run(tmp_path, _Fetcher(_body(_payload())))
    run = _run_receipt(result)
    original = read_companyfacts_manifest(
        tmp_path / "archive", run["ticker_receipts"][0]["manifest_key"]
    )
    forged = deepcopy(original)
    shifted = NOW + timedelta(seconds=2)
    forged["clocks"] = {
        "source_snapshot_at": "2026-08-01T12:00:02.000000Z",
        "recorded_at": "2026-08-01T12:00:02.000000Z",
        "acquisition_started_at": "2026-08-01T12:00:02.000000Z",
        "captured_at": "2026-08-01T12:00:02.000000Z",
    }
    assert shifted == NOW + timedelta(seconds=2)  # keeps the forged delta explicit
    forged["manifest_id"] = manifest_id_for(forged)
    forged_key = persist_companyfacts_manifest(tmp_path / "archive", forged)
    publish_verified_manifest_pointer(tmp_path / "archive", forged_key)

    with pytest.raises(CompanyFactsAcquisitionError, match="clocks or CIK differ"):
        read_verified_companyfacts(tmp_path / "raw", tmp_path / "archive", 1)


def test_pointer_postwrite_failure_rolls_back_prior_verified_latest(tmp_path: Path, monkeypatch):
    first_result = _run(tmp_path, _Fetcher(_body(_payload(val=100))))
    first_run = _run_receipt(first_result)
    first_manifest = read_companyfacts_manifest(
        tmp_path / "archive", first_run["ticker_receipts"][0]["manifest_key"]
    )
    latest = tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT / "0000000001" / "latest.json"
    prior_pointer = latest.read_bytes()
    original_reader = companyfacts.read_latest_companyfacts_manifest

    def fail_only_new_pointer(archive_root: Path, cik: int | str):
        pointer = json.loads(latest.read_text(encoding="utf-8"))
        if pointer["manifest_id"] != first_manifest["manifest_id"]:
            raise CompanyFactsAcquisitionError("forced post-write pointer verification failure")
        return original_reader(archive_root, cik)

    monkeypatch.setattr(companyfacts, "read_latest_companyfacts_manifest", fail_only_new_pointer)
    second = _run(
        tmp_path,
        _Fetcher(_body(_payload(val=101))),
        now=NOW + timedelta(seconds=1),
    )
    assert _run_receipt(second)["status"] == "partial"
    assert latest.read_bytes() == prior_pointer

    monkeypatch.setattr(companyfacts, "read_latest_companyfacts_manifest", original_reader)
    assert read_latest_companyfacts_manifest(tmp_path / "archive", 1) == first_manifest
    assert read_verified_companyfacts(tmp_path / "raw", tmp_path / "archive", 1)[0] == _payload(val=100)


def test_pointer_postwrite_failure_removes_new_pointer_when_no_prior_pointer(tmp_path: Path, monkeypatch):
    result = _run(tmp_path, _Fetcher(_body(_payload())))
    run = _run_receipt(result)
    manifest_key = run["ticker_receipts"][0]["manifest_key"]
    latest = tmp_path / "archive" / COMPANYFACTS_MANIFEST_ROOT / "0000000001" / "latest.json"
    latest.unlink()

    def fail_readback(*_args, **_kwargs):
        raise CompanyFactsAcquisitionError("forced post-write pointer verification failure")

    monkeypatch.setattr(companyfacts, "read_latest_companyfacts_manifest", fail_readback)
    with pytest.raises(CompanyFactsAcquisitionError, match="forced post-write"):
        publish_verified_manifest_pointer(tmp_path / "archive", manifest_key)
    assert not latest.exists()


def test_later_publisher_cannot_rewind_verified_latest_to_older_capture(tmp_path: Path):
    older = _run(tmp_path, _Fetcher(_body(_payload(val=100))), now=NOW)
    newer = _run(
        tmp_path,
        _Fetcher(_body(_payload(val=200))),
        now=NOW + timedelta(seconds=2),
    )
    older_run = _run_receipt(older)
    newer_run = _run_receipt(newer)
    older_key = older_run["ticker_receipts"][0]["manifest_key"]
    newer_manifest = read_companyfacts_manifest(
        tmp_path / "archive", newer_run["ticker_receipts"][0]["manifest_key"]
    )

    published = publish_verified_manifest_pointer(tmp_path / "archive", older_key)
    assert published["manifest_id"] == newer_manifest["manifest_id"]
    assert read_latest_companyfacts_manifest(tmp_path / "archive", 1) == newer_manifest
    assert read_verified_companyfacts(tmp_path / "raw", tmp_path / "archive", 1)[0] == _payload(val=200)


def test_capture_ticker_and_run_receipts_are_append_only_when_headers_or_body_change(tmp_path: Path):
    first = _run(
        tmp_path,
        _Fetcher(_body(_payload(val=100)), response_headers={"ETag": '"first"'}),
    )
    second = _run(
        tmp_path,
        _Fetcher(_body(_payload(val=100)), response_headers={"ETag": '"second"'}),
    )
    third = _run(
        tmp_path,
        _Fetcher(_body(_payload(val=300)), response_headers={"ETag": '"third"'}),
        now=NOW + timedelta(seconds=1),
    )
    receipts = [_run_receipt(item) for item in (first, second, third)]
    ticker_receipts = [item["ticker_receipts"][0] for item in receipts]
    manifests = [
        read_companyfacts_manifest(tmp_path / "archive", receipt["manifest_key"])
        for receipt in ticker_receipts
    ]

    assert len({receipt["run_id"] for receipt in receipts}) == 3
    assert len({item["ticker_receipt_id"] for item in ticker_receipts}) == 3
    assert len({manifest["source"]["capture_id"] for manifest in manifests}) == 3
    assert manifests[0]["source"]["response_sha256"] == manifests[1]["source"]["response_sha256"]
    assert manifests[0]["source"]["response_sha256"] != manifests[2]["source"]["response_sha256"]
    for result, run, receipt, manifest in zip((first, second, third), receipts, ticker_receipts, manifests):
        assert (tmp_path / "archive" / result["run_key"]).exists()
        assert (tmp_path / "archive" / run["ticker_receipt_keys"][0]).exists()
        assert (tmp_path / "raw" / manifest["source"]["capture_receipt_key"]).exists()
        assert (tmp_path / "archive" / receipt["manifest_key"]).exists()


def test_corrupt_response_object_is_repaired_without_rewriting_prior_capture(tmp_path: Path):
    body = _body(_payload())
    first = _run(tmp_path, _Fetcher(body))
    first_manifest = read_companyfacts_manifest(
        tmp_path / "archive", _run_receipt(first)["ticker_receipts"][0]["manifest_key"]
    )
    response_path = tmp_path / "raw" / first_manifest["source"]["response_object_path"]
    response_path.write_bytes(gzip.compress(b"corrupt", mtime=0))

    second = _run(tmp_path, _Fetcher(body), now=NOW + timedelta(seconds=1))
    second_manifest = read_companyfacts_manifest(
        tmp_path / "archive", _run_receipt(second)["ticker_receipts"][0]["manifest_key"]
    )
    first_capture = _capture_for(tmp_path, first_manifest)
    second_capture = _capture_for(tmp_path, second_manifest)

    assert second_capture["object_repaired"] is True
    assert first_capture["object_repaired"] is False
    assert first_capture["capture_id"] != second_capture["capture_id"]
    assert read_verified_companyfacts(tmp_path / "raw", tmp_path / "archive", 1)[0] == _payload()


def test_pacing_floor_and_scheduler_constraint_are_explicit(tmp_path: Path):
    fetcher = _Fetcher(
        {
            companyfacts_url(1): _body(_payload("0000000001")),
            companyfacts_url(2): _body(_payload("0000000002")),
        }
    )
    sleeps: list[float] = []
    result = _run(
        tmp_path,
        fetcher,
        targets=("FXT=1", "TWO=2"),
        min_interval_seconds=0.001,
        monotonic=lambda: 0.0,
        sleeper=sleeps.append,
    )
    run = _run_receipt(result)

    assert run["status"] == "complete"
    assert sleeps == [0.1]
    assert "aggregate per-IP limit" in run["operator_constraints"][0]
    assert [call[1]["User-Agent"] for call in fetcher.calls] == [USER_AGENT, USER_AGENT]


def test_rejects_weak_user_agent_before_network_and_contradictory_failed_receipts(tmp_path: Path):
    fetcher = _Fetcher(_body(_payload()))
    with pytest.raises(CompanyFactsAcquisitionError, match="contact email"):
        _run(tmp_path, fetcher, user_agent="MastermindX somebody@example")
    assert fetcher.calls == []

    oversized = _run(
        tmp_path,
        _Fetcher(_body(_payload())),
        max_response_bytes=1,
        max_ticker_bytes=1,
        max_total_bytes=1,
    )
    failed = deepcopy(_run_receipt(oversized)["ticker_receipts"][0])
    assert failed["status"] == "failed"
    failed["capture_id"] = "ffseccfc_" + "0" * 64
    failed["ticker_receipt_id"] = companyfacts._ticker_receipt_id(failed)
    with pytest.raises(CompanyFactsAcquisitionError, match="capture evidence"):
        companyfacts._validate_ticker_receipt(failed)

    failed = deepcopy(_run_receipt(oversized)["ticker_receipts"][0])
    failed["bytes_retained"] = -1
    failed["ticker_receipt_id"] = companyfacts._ticker_receipt_id(failed)
    with pytest.raises(CompanyFactsAcquisitionError, match="bytes are invalid"):
        companyfacts._validate_ticker_receipt(failed)


@pytest.mark.parametrize(
    "mutation",
    (
        "request_id",
        "target",
        "clock_drift",
        "empty_capture_clock",
        "limits",
        "failure_schema",
        "bytes_cap",
    ),
)
def test_ticker_receipt_validator_rejects_readdressed_contract_mutations(
    tmp_path: Path, mutation: str
):
    run = _run_receipt(_run(tmp_path, _Fetcher(_body(_payload()))))
    receipt = deepcopy(run["ticker_receipts"][0])

    if mutation == "request_id":
        receipt["request_id"] = "ffseccfq_" + "g" * 64
    elif mutation == "target":
        receipt["target"] = {"ticker": "fxt", "cik": "0000000001"}
    elif mutation == "clock_drift":
        receipt["clocks"]["source_snapshot_at"] = _clock(
            NOW + timedelta(seconds=10)
        )
    elif mutation == "empty_capture_clock":
        receipt["clocks"]["captured_at"] = ""
    elif mutation == "limits":
        receipt["limits"]["max_tickers"] = 0
    elif mutation == "failure_schema":
        receipt["failures"] = [
            {"stage": "companyfacts", "error_type": "Broken"}
        ]
    else:
        receipt["bytes_retained"] = receipt["limits"]["max_response_bytes"] + 1
    receipt["ticker_receipt_id"] = companyfacts._ticker_receipt_id(receipt)

    with pytest.raises(CompanyFactsAcquisitionError):
        companyfacts._validate_ticker_receipt(receipt)


def test_manifest_pointer_key_is_exactly_bound_to_pointer_cik_and_manifest_id(
    tmp_path: Path,
):
    bodies = {
        companyfacts_url(1): _body(_payload("0000000001")),
        companyfacts_url(2): _body(_payload("0000000002")),
    }
    run = _run_receipt(
        _run(tmp_path, _Fetcher(bodies), targets=("ONE=1", "TWO=2"))
    )
    first_key, second_key = (
        receipt["manifest_key"] for receipt in run["ticker_receipts"]
    )
    first_manifest = read_companyfacts_manifest(
        tmp_path / "archive", first_key
    )
    pointer = companyfacts._build_manifest_pointer(
        first_manifest,
        manifest_key=first_key,
    )
    pointer["manifest_key"] = second_key
    pointer["pointer_id"] = companyfacts._pointer_id(pointer)

    with pytest.raises(CompanyFactsAcquisitionError, match="pointer key"):
        companyfacts._validate_manifest_pointer(pointer)


@pytest.mark.parametrize(
    "mutation",
    (
        "run_request",
        "run_limits",
        "receipt_order",
        "child_request",
        "child_limits",
        "child_clocks",
        "receipt_key",
        "byte_sum",
        "negative_bytes",
        "status",
    ),
)
def test_run_validator_rejects_readdressed_parent_child_mutations(
    tmp_path: Path, mutation: str
):
    bodies = {
        companyfacts_url(1): _body(_payload("0000000001")),
        companyfacts_url(2): _body(_payload("0000000002")),
    }
    run = deepcopy(
        _run_receipt(
            _run(
                tmp_path,
                _Fetcher(bodies),
                targets=("ONE=1", "TWO=2"),
            )
        )
    )

    if mutation == "run_request":
        run["request_id"] = "ffseccfq_" + "0" * 64
    elif mutation == "run_limits":
        run["limits"]["max_tickers"] = 0
    elif mutation == "receipt_order":
        run["ticker_receipts"].reverse()
        run["ticker_receipt_keys"].reverse()
    elif mutation == "child_request":
        child = run["ticker_receipts"][0]
        child["request_id"] = "ffseccfq_" + "0" * 64
        child["ticker_receipt_id"] = companyfacts._ticker_receipt_id(child)
        run["ticker_receipt_keys"][0] = companyfacts._ticker_receipt_key(child)
    elif mutation == "child_limits":
        child = run["ticker_receipts"][0]
        child["limits"]["max_response_bytes"] -= 1
        child["ticker_receipt_id"] = companyfacts._ticker_receipt_id(child)
        run["ticker_receipt_keys"][0] = companyfacts._ticker_receipt_key(child)
    elif mutation == "child_clocks":
        child = run["ticker_receipts"][0]
        child["clocks"]["source_snapshot_at"] = _clock(
            NOW + timedelta(seconds=1)
        )
        child["ticker_receipt_id"] = companyfacts._ticker_receipt_id(child)
        run["ticker_receipt_keys"][0] = companyfacts._ticker_receipt_key(child)
    elif mutation == "receipt_key":
        run["ticker_receipt_keys"][0] += ".wrong"
    elif mutation == "byte_sum":
        run["bytes_retained"] += 1
    elif mutation == "negative_bytes":
        run["bytes_retained"] = -1
    else:
        run["status"] = "partial"
    run["run_id"] = companyfacts._run_id(run)

    with pytest.raises(CompanyFactsAcquisitionError):
        companyfacts._validate_run(run)
