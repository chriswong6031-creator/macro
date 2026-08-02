from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest
import requests

from collectors.biocatalyst.clinicaltrials_history import (
    ClinicalTrialsHistoryCollector,
    ClinicalTrialsHistoryConfig,
    CollectionError,
    _strict_json_object,
    canonical_nct_id,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "data/biocatalyst/fixtures/clinicaltrials_history"
)
NCT_ID = "NCT03456024"


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        status_code: int = 200,
        *,
        content_type: str = "application/json",
        content_length: str | None = None,
        content_encoding: str | None = None,
        retry_after: str | None = None,
        location: str | None = None,
    ) -> None:
        self.content = payload
        self.status_code = status_code
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": content_length or str(len(payload)),
            "ETag": '"origin-version-not-content"',
            "Set-Cookie": "must-not-survive",
        }
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after
        if location is not None:
            self.headers["Location"] = location

    def iter_content(self, *, chunk_size: int):
        del chunk_size
        midpoint = max(1, len(self.content) // 2)
        yield self.content[:midpoint]
        yield self.content[midpoint:]


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"unexpected HTTP call: {url}")
        return self.responses.pop(0)


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _index_payload() -> dict:
    return json.loads(_fixture("NCT03456024.history.index.synthetic.json"))


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _config(**overrides: object) -> ClinicalTrialsHistoryConfig:
    values: dict[str, object] = {
        "nct_ids": (NCT_ID,),
        "user_agent": "MastermindX-BioCatalyst-test/1.0",
        "min_request_interval_seconds": 0.25,
        "retry_backoff_seconds": 0.5,
    }
    values.update(overrides)
    return ClinicalTrialsHistoryConfig(**values)  # type: ignore[arg-type]


def _collector(
    tmp_path: Path,
    responses: list[FakeResponse],
    *,
    config: ClinicalTrialsHistoryConfig | None = None,
    sleeps: list[float] | None = None,
    now: datetime | None = None,
) -> tuple[ClinicalTrialsHistoryCollector, FakeSession]:
    session = FakeSession(responses)
    collector = ClinicalTrialsHistoryCollector(
        private_root=tmp_path / "private",
        config=config or _config(),
        session=session,
        now_fn=lambda: now or datetime(2026, 8, 2, 3, 0, tzinfo=timezone.utc),
        sleep_fn=sleeps.append if sleeps is not None else lambda _: None,
        monotonic_fn=lambda: 0.0,
    )
    return collector, session


def _normal_responses() -> list[FakeResponse]:
    index = _fixture("NCT03456024.history.index.synthetic.json")
    return [
        FakeResponse(index),
        FakeResponse(_fixture("NCT03456024.history.version-0.synthetic.json")),
        FakeResponse(_fixture("NCT03456024.history.version-1.synthetic.json")),
        FakeResponse(index),
    ]


def test_collects_private_history_evidence_with_exact_bound_requests(tmp_path: Path) -> None:
    sleeps: list[float] = []
    collector, session = _collector(tmp_path, _normal_responses(), sleeps=sleeps)

    result = collector.collect_nct("nct03456024")

    assert result.nct_id == NCT_ID
    assert len(result.history_version_receipts) == 2
    assert len(result.source_snapshots) == 2
    assert result.run_path.is_file()
    assert [call["url"] for call in session.calls] == [
        "https://clinicaltrials.gov/api/int/studies/NCT03456024?history=true",
        "https://clinicaltrials.gov/api/int/studies/NCT03456024/history/0",
        "https://clinicaltrials.gov/api/int/studies/NCT03456024/history/1",
        "https://clinicaltrials.gov/api/int/studies/NCT03456024?history=true",
    ]
    for call in session.calls:
        assert call["allow_redirects"] is False
        assert call["stream"] is True
        assert call["headers"]["Accept-Encoding"] == "identity"
        assert "If-None-Match" not in call["headers"]
    assert sleeps == [0.25, 0.25, 0.25]

    run = json.loads(result.run_path.read_text())
    assert run["run_state"] == "complete"
    assert run["completeness_state"] == "history_complete"
    assert run["history_index_post_receipt_ref"] == result.history_index_roundtrip_receipt["receipt_id"]
    assert run["history_index_post_receipt_ref"] != run["history_index_receipt_ref"]
    ordered_receipts = (
        result.history_index_receipt,
        *result.history_version_receipts,
        result.history_index_roundtrip_receipt,
    )
    received_at = [receipt["response"]["received_at"] for receipt in ordered_receipts]
    assert received_at == sorted(received_at)
    assert len(received_at) == len(set(received_at))
    assert run["started_at"] < received_at[0] < received_at[-1] < run["finished_at"]
    assert all(
        receipt["response"]["received_at"] < receipt["transaction_from"] <= run["finished_at"]
        for receipt in ordered_receipts
    )
    assert run["finished_at"] < run["transaction_from"]
    assert run["version_manifest"] == [
        {
            "source_version": 0,
            "display_version": 1,
            "source_submitted_at": "2018-02-28",
            "source_last_update_submit_qc_at": "2018-02-28",
            "module_labels": [],
        },
        {
            "source_version": 1,
            "display_version": 2,
            "source_submitted_at": "2018-03-07",
            "source_last_update_submit_qc_at": "2018-03-07",
            "module_labels": ["Study Status", "Outcome Measures"],
        },
    ]
    for receipt in (*result.history_version_receipts, result.history_index_receipt):
        raw_path = tmp_path / "private" / receipt["response"]["raw_response_object_key"]
        assert raw_path.is_file()
        assert receipt["response"]["exact_response_sha256"] == hashlib.sha256(raw_path.read_bytes()).hexdigest()
        assert receipt["response"]["headers"]["etag"] == '"origin-version-not-content"'
    assert result.history_index_roundtrip_receipt["receipt_id"].endswith("index_post")
    for snapshot, path in zip(result.source_snapshots, result.source_snapshot_paths, strict=True):
        assert path.is_file()
        assert snapshot["coverage_class"] == "record_history_complete"
        assert snapshot["authority"]["decision_authority"] is False
        assert snapshot["canonical_study"]["protocolSection"]["identificationModule"]["nctId"] == NCT_ID
    private_text = "\n".join(path.read_text() for path in (tmp_path / "private").glob("**/*.json"))
    assert "set-cookie" not in private_text.lower()
    assert "@" not in private_text
    fixture_text = "\n".join(path.read_text() for path in FIXTURE_ROOT.glob("*.json"))
    assert "contact" not in fixture_text.lower()
    assert "phone" not in fixture_text.lower()
    assert "email" not in fixture_text.lower()


def test_repeated_complete_collection_mints_run_specific_snapshot_ids(tmp_path: Path) -> None:
    first, _ = _collector(
        tmp_path,
        _normal_responses(),
        now=datetime(2026, 8, 2, 3, 0, tzinfo=timezone.utc),
    )
    second, _ = _collector(
        tmp_path,
        _normal_responses(),
        now=datetime(2026, 8, 2, 4, 0, tzinfo=timezone.utc),
    )

    first_result = first.collect_nct(NCT_ID)
    second_result = second.collect_nct(NCT_ID)

    assert first_result.run_id != second_result.run_id
    assert {
        snapshot["canonical_content_sha256"] for snapshot in first_result.source_snapshots
    } == {
        snapshot["canonical_content_sha256"] for snapshot in second_result.source_snapshots
    }
    assert {
        snapshot["source_snapshot_id"] for snapshot in first_result.source_snapshots
    }.isdisjoint(
        snapshot["source_snapshot_id"] for snapshot in second_result.source_snapshots
    )
    assert all(path.is_file() for path in (*first_result.source_snapshot_paths, *second_result.source_snapshot_paths))


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"study":{},"study":{}}', "INVALID_SOURCE_JSON"),
        (b'{"study":{}} trailing', "INVALID_SOURCE_JSON"),
        (b"\xff", "INVALID_SOURCE_JSON"),
    ],
)
def test_strict_json_rejects_ambiguous_or_nonexact_bodies(raw: bytes, code: str) -> None:
    with pytest.raises(CollectionError) as exc:
        _strict_json_object(raw, "fixture")
    assert exc.value.code == code


@pytest.mark.parametrize(
    ("value", "expected"),
    [("nct03456024", NCT_ID), ("NCT03456024", NCT_ID)],
)
def test_nct_identifiers_are_canonicalized_before_any_request(value: str, expected: str) -> None:
    assert canonical_nct_id(value) == expected


@pytest.mark.parametrize("value", ["NCT0345602", "NCT034560240", "http://example.invalid", 1])
def test_invalid_nct_identifiers_fail_closed(value: object) -> None:
    with pytest.raises(CollectionError, match="INVALID_NCT_ID"):
        canonical_nct_id(value)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda payload: payload["history"].update({"changes": [payload["history"]["changes"][0], payload["history"]["changes"][0]]}), "DUPLICATE_HISTORY_VERSION"),
        (lambda payload: payload["history"]["changes"].__setitem__(1, {**payload["history"]["changes"][1], "version": 2}), "HISTORY_VERSION_GAP"),
        (lambda payload: payload["history"]["changes"].__setitem__(1, {**payload["history"]["changes"][1], "version": True}), "INVALID_HISTORY_VERSION"),
    ],
)
def test_index_version_shape_must_be_complete_unique_integer_chain(
    tmp_path: Path, mutation, code: str
) -> None:
    index = _index_payload()
    mutation(index)
    collector, _ = _collector(tmp_path, [FakeResponse(_json_bytes(index))])

    with pytest.raises(CollectionError) as exc:
        collector.collect_nct(NCT_ID)
    assert exc.value.code == code
    assert not list((tmp_path / "private").glob("**/runs/**/*.json"))


def test_version_nct_and_version_must_bind_to_the_index_manifest(tmp_path: Path) -> None:
    bad_version = json.loads(_fixture("NCT03456024.history.version-0.synthetic.json"))
    bad_version["studyVersion"] = 1
    collector, _ = _collector(
        tmp_path,
        [
            FakeResponse(_fixture("NCT03456024.history.index.synthetic.json")),
            FakeResponse(_json_bytes(bad_version)),
        ],
    )

    with pytest.raises(CollectionError) as exc:
        collector.collect_nct(NCT_ID)
    assert exc.value.code == "HISTORY_VERSION_BINDING"
    assert not list((tmp_path / "private").glob("**/runs/**/*.json"))


def test_partial_history_fetch_never_mints_a_complete_run(tmp_path: Path) -> None:
    collector, _ = _collector(
        tmp_path,
        [
            FakeResponse(_fixture("NCT03456024.history.index.synthetic.json")),
            FakeResponse(_fixture("NCT03456024.history.version-0.synthetic.json")),
            FakeResponse(b"not found", 404, content_type="text/plain"),
        ],
    )

    with pytest.raises(CollectionError) as exc:
        collector.collect_nct(NCT_ID)
    assert exc.value.code == "UNEXPECTED_HTTP_STATUS"
    assert not list((tmp_path / "private").glob("**/runs/**/*.json"))


def test_roundtrip_index_race_aborts_before_complete_run(tmp_path: Path) -> None:
    changed_index = _index_payload()
    changed_index["history"]["changes"].append(
        {
            "version": 2,
            "date": "2018-03-10",
            "status": "UNKNOWN",
            "studyType": "OBSERVATIONAL",
            "moduleLabels": ["Study Status"],
            "lastUpdateSubmitQcDate": "2018-03-10",
        }
    )
    responses = _normal_responses()
    responses[-1] = FakeResponse(_json_bytes(changed_index))
    collector, _ = _collector(tmp_path, responses)

    with pytest.raises(CollectionError) as exc:
        collector.collect_nct(NCT_ID)
    assert exc.value.code == "HISTORY_INDEX_RACE"
    assert not list((tmp_path / "private").glob("**/runs/**/*.json"))


def test_redirect_and_oversize_responses_never_become_receipts(tmp_path: Path) -> None:
    collector, session = _collector(tmp_path, [FakeResponse(b"", 302, location="https://example.invalid")])
    with pytest.raises(CollectionError) as redirect:
        collector.collect_nct(NCT_ID)
    assert redirect.value.code == "UNEXPECTED_HTTP_STATUS"
    assert session.calls[0]["allow_redirects"] is False

    collector, _ = _collector(
        tmp_path / "oversize",
        [FakeResponse(b"{}", content_length="3000001")],
    )
    with pytest.raises(CollectionError) as oversize:
        collector.collect_nct(NCT_ID)
    assert oversize.value.code == "RESPONSE_TOO_LARGE"
    assert not list((tmp_path / "oversize" / "private").glob("**/receipts/**/*.json"))


def test_retry_and_rate_caps_apply_to_the_fixed_source_only(tmp_path: Path) -> None:
    sleeps: list[float] = []
    responses = [FakeResponse(b"{}", 503, retry_after="1"), *_normal_responses()]
    collector, session = _collector(tmp_path, responses, sleeps=sleeps)

    result = collector.collect_nct(NCT_ID)

    assert result.run_path.is_file()
    assert len(session.calls) == 5
    assert 1.0 in sleeps
    assert all(call["url"].startswith("https://clinicaltrials.gov/api/int/studies/") for call in session.calls)


def test_noncanonical_or_injected_source_uris_are_rejected_before_http(tmp_path: Path) -> None:
    collector, session = _collector(tmp_path, [])
    with pytest.raises(CollectionError) as exc:
        collector._get("https://clinicaltrials.gov/api/int/studies/NCT03456024?history=true#fragment", "test")
    assert exc.value.code == "UNSAFE_SOURCE_URI"
    assert session.calls == []


def test_source_content_type_and_encoding_are_strict(tmp_path: Path) -> None:
    collector, _ = _collector(tmp_path, [FakeResponse(b"{}", content_type="text/html")])
    with pytest.raises(CollectionError) as content_type:
        collector.collect_nct(NCT_ID)
    assert content_type.value.code == "UNEXPECTED_CONTENT_TYPE"

    collector, _ = _collector(tmp_path / "encoding", [FakeResponse(b"{}", content_encoding="gzip")])
    with pytest.raises(CollectionError) as encoding:
        collector.collect_nct(NCT_ID)
    assert encoding.value.code == "UNSUPPORTED_CONTENT_ENCODING"
