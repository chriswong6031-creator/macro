from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
import requests

from collectors.biocatalyst.clinicaltrials_v2 import (
    ClinicalTrialsV2Collector,
    ClinicalTrialsV2Config,
    CollectionError,
)
import collectors.biocatalyst.clinicaltrials_v2 as collector_module
import engine.sector_intelligence.contracts as contracts


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        status_code: int = 200,
        *,
        content_encoding: str | None = None,
        retry_after: str | None = None,
        location: str | None = None,
    ) -> None:
        self.content = payload
        self.status_code = status_code
        self.headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
            "Set-Cookie": "must-not-survive",
        }
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after
        if location is not None:
            self.headers["Location"] = location

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"unexpected HTTP call: {url}")
        return self.responses.pop(0)


class IncrementingClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ConsumingSession(FakeSession):
    def __init__(
        self,
        responses: list[FakeResponse],
        monotonic: FakeMonotonic,
        request_seconds: list[float],
    ) -> None:
        super().__init__(responses)
        self.monotonic = monotonic
        self.request_seconds = list(request_seconds)

    def get(self, url: str, **kwargs):
        response = super().get(url, **kwargs)
        self.monotonic.advance(self.request_seconds.pop(0))
        return response


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()


def _study(nct_id: str, title: str) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": "2026-08-01", "type": "ACTUAL"},
            },
        }
    }


@pytest.fixture
def two_page_fixture() -> tuple[bytes, bytes, bytes]:
    version = _json_bytes(
        {"apiVersion": "2.0.5", "dataTimestamp": "2026-08-01T09:00:00"}
    )
    first = _json_bytes(
        {
            "studies": [_study("NCT00000001", "One")],
            "nextPageToken": "secret-token",
            "totalCount": 2,
        }
    )
    second = _json_bytes(
        {"studies": [_study("NCT00000002", "Two")], "totalCount": 2}
    )
    return version, first, second


def _config(*nct_ids: str, max_attempts: int = 3) -> ClinicalTrialsV2Config:
    return ClinicalTrialsV2Config(
        nct_ids=tuple(nct_ids),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        page_size=1,
        page_cap=3,
        max_attempts=max_attempts,
        retry_backoff_seconds=0.25,
    )


@pytest.mark.parametrize(
    "invalid_override",
    [
        {"connect_timeout_seconds": 0.0},
        {"read_timeout_seconds": 0.0},
        {"retry_budget_seconds": 0.0},
    ],
)
def test_request_timeouts_and_retry_budget_must_be_positive(
    invalid_override: dict[str, float],
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ClinicalTrialsV2Config(
            nct_ids=("NCT00000001",),
            user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
            **invalid_override,
        )


def test_zero_retry_delays_are_explicitly_supported() -> None:
    config = ClinicalTrialsV2Config(
        nct_ids=("NCT00000001",),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        retry_backoff_seconds=0.0,
        max_retry_delay_seconds=0.0,
    )

    assert config.retry_backoff_seconds == 0.0
    assert config.max_retry_delay_seconds == 0.0


def _collector(
    tmp_path: Path,
    responses: list[FakeResponse],
    config: ClinicalTrialsV2Config,
    *,
    start: datetime | None = None,
    sleeps: list[float] | None = None,
) -> tuple[ClinicalTrialsV2Collector, FakeSession]:
    session = FakeSession(responses)
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=config,
        session=session,
        now_fn=IncrementingClock(
            start or datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)
        ),
        sleep_fn=(sleeps.append if sleeps is not None else lambda _: None),
    )
    return collector, session


@pytest.mark.parametrize(
    ("private_parts", "public_parts"),
    [
        (("same",), ("same",)),
        (("private",), ("private", "public")),
        (("public", "private"), ("public",)),
    ],
)
def test_private_and_public_roots_must_be_disjoint(
    tmp_path: Path,
    private_parts: tuple[str, ...],
    public_parts: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="disjoint"):
        ClinicalTrialsV2Collector(
            private_root=tmp_path.joinpath(*private_parts),
            public_root=tmp_path.joinpath(*public_parts),
            config=_config("NCT00000001"),
            session=FakeSession([]),
        )


@pytest.mark.parametrize(
    "location",
    [
        "https://clinicaltrials.gov/api/v2/version/",
        "https://example.invalid/capture",
    ],
)
def test_redirects_are_rejected_without_following(
    tmp_path: Path, location: str
) -> None:
    session = FakeSession([FakeResponse(b"", 302, location=location)])
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=_config("NCT00000001"),
        session=session,
    )

    with pytest.raises(CollectionError, match="UNEXPECTED_HTTP_STATUS"):
        collector._get("/version")

    assert len(session.calls) == 1
    assert session.calls[0]["allow_redirects"] is False


def test_owned_session_disables_ambient_proxy_inheritance(tmp_path: Path) -> None:
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=_config("NCT00000001"),
    )
    try:
        assert isinstance(collector.session, requests.Session)
        assert collector.session.trust_env is False
    finally:
        collector.session.close()


def test_injected_session_preserves_caller_proxy_policy(tmp_path: Path) -> None:
    session = requests.Session()
    session.trust_env = True
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=_config("NCT00000001"),
        session=session,
    )
    try:
        assert collector.session is session
        assert collector.session.trust_env is True
    finally:
        session.close()


def test_multi_page_collection_archives_exact_bytes_and_replays_without_http(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, first, second = two_page_fixture
    collector, session = _collector(
        tmp_path,
        [
            FakeResponse(version),
            FakeResponse(first),
            FakeResponse(second),
            FakeResponse(version),
        ],
        _config("NCT00000001", "NCT00000002"),
    )

    result = collector.collect()

    assert result.source_snapshot_count == 2
    studies_calls = [call for call in session.calls if call["url"].endswith("/studies")]
    assert studies_calls[0]["params"] == [
        ("query.id", "NCT00000001,NCT00000002"),
        ("format", "json"),
        ("pageSize", "1"),
        ("countTotal", "true"),
    ]
    assert studies_calls[0]["headers"]["Accept-Encoding"] == "identity"
    assert studies_calls[1]["params"][-1] == ("pageToken", "secret-token")
    receipts = sorted((tmp_path / "private").glob("**/receipts/**/*.json"))
    page_receipts = [path for path in receipts if "/version/" not in path.as_posix()]
    version_receipts = [path for path in receipts if "/version/" in path.as_posix()]
    assert len(page_receipts) == 2
    assert len(version_receipts) == 2
    first_receipt = json.loads(page_receipts[0].read_text())
    assert "secret-token" not in page_receipts[0].read_text()
    assert "set-cookie" not in first_receipt["response"]["headers"]
    raw_path = tmp_path / "private" / first_receipt["response"]["raw_response_object_key"]
    assert raw_path.read_bytes() == first
    run = json.loads(result.run_path.read_text())
    assert run["version_evidence"]["before"]["response"]["exact_response_sha256"] == run["version_evidence"]["after"]["response"]["exact_response_sha256"]
    for phase in ("before", "after"):
        receipt = run["version_evidence"][phase]
        assert (tmp_path / "private" / receipt["response"]["raw_response_object_key"]).read_bytes() == version
    public_state = json.loads(
        (result.generation_path / "NCT00000001.json").read_text()
    )
    assert "canonical_study" not in public_state
    assert "raw_object_key" not in public_state
    assert "page_receipt_ref" not in public_state
    assert "run_ref" not in public_state
    pointer_before = result.current_pointer_path.read_bytes()

    offline = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=_config("NCT00000001", "NCT00000002"),
        session=FakeSession([]),
    )
    replayed = offline.replay(result.run_path)

    assert replayed.generation_path != result.generation_path
    assert {
        path.name: path.read_bytes() for path in replayed.generation_path.iterdir()
    } == {path.name: path.read_bytes() for path in result.generation_path.iterdir()}
    assert replayed.current_pointer_path is None
    assert result.current_pointer_path.read_bytes() == pointer_before


@pytest.mark.parametrize(
    "pages",
    [
        ({"studies": [_study("NCT00000001", "One")]},),
        ({"studies": [_study("NCT00000001", "One")], "totalCount": 2},),
        ({"studies": [_study("NCT00000001", "One")], "totalCount": "1"},),
        ({"studies": [_study("NCT00000001", "One")], "totalCount": -1},),
        ({"studies": [_study("NCT00000001", "One")], "totalCount": True},),
        (
            {
                "studies": [_study("NCT00000001", "One")],
                "nextPageToken": "next",
                "totalCount": 2,
            },
            {"studies": [_study("NCT00000002", "Two")], "totalCount": 1},
        ),
    ],
    ids=(
        "missing",
        "derived-mismatch",
        "string",
        "negative",
        "boolean",
        "later-page-mismatch",
    ),
)
def test_count_total_wire_claim_must_reconcile_with_terminal_raw_pages(
    tmp_path: Path, pages: tuple[dict, ...]
) -> None:
    version = _json_bytes(
        {"apiVersion": "2.0.5", "dataTimestamp": "2026-08-01T09:00:00"}
    )
    configured = tuple(
        f"NCT{ordinal:08d}" for ordinal in range(1, len(pages) + 1)
    )
    responses = [FakeResponse(version)]
    responses.extend(FakeResponse(_json_bytes(page)) for page in pages)
    responses.append(FakeResponse(version))
    collector, _ = _collector(tmp_path, responses, _config(*configured))

    with pytest.raises(contracts.ContractValidationError, match="raw_run.total_count"):
        collector.collect()

    assert not (tmp_path / "public" / "current.json").exists()
    run = json.loads(next((tmp_path / "private").glob("**/runs/**/*.json")).read_text())
    assert run["run_state"] == "quarantined"
    assert run["error_codes"] == ["CONTRACT_VALIDATION_FAILED"]


def test_retry_is_bounded_and_uses_exponential_backoff(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    only_page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    sleeps: list[float] = []
    collector, session = _collector(
        tmp_path,
        [
            FakeResponse(version),
            FakeResponse(b"{}", 503),
            FakeResponse(b"{}", 429),
            FakeResponse(only_page),
            FakeResponse(version),
        ],
        _config("NCT00000001"),
        sleeps=sleeps,
    )

    collector.collect()

    assert sleeps == [0.25, 0.5]
    assert len([call for call in session.calls if call["url"].endswith("/studies")]) == 3
    assert all(call["timeout"] == (10.0, 45.0) for call in session.calls)


@pytest.mark.parametrize(
    ("retry_after", "expected_delay"),
    [
        ("1", 1.0),
        ("Sat, 01 Aug 2026 15:00:01 GMT", 1.0),
        ("not-a-delay", 0.25),
    ],
)
def test_retry_after_is_parsed_and_bounded(
    tmp_path: Path,
    two_page_fixture: tuple[bytes, bytes, bytes],
    retry_after: str,
    expected_delay: float,
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    sleeps: list[float] = []
    session = FakeSession(
        [
            FakeResponse(version),
            FakeResponse(b"{}", 429, retry_after=retry_after),
            FakeResponse(page),
            FakeResponse(version),
        ]
    )
    config = ClinicalTrialsV2Config(
        nct_ids=("NCT00000001",),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        page_size=1,
        max_attempts=3,
        retry_backoff_seconds=0.25,
        max_retry_delay_seconds=2.0,
        retry_budget_seconds=5.0,
    )
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=config,
        session=session,
        now_fn=IncrementingClock(datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)),
        retry_now_fn=lambda: datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc),
        sleep_fn=sleeps.append,
    )

    collector.collect()

    assert sleeps == [expected_delay]


def test_retry_after_above_delay_cap_aborts_instead_of_retrying_early(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    session = FakeSession(
        [FakeResponse(version), FakeResponse(b"{}", 429, retry_after="10")]
    )
    config = ClinicalTrialsV2Config(
        nct_ids=("NCT00000001",),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        max_attempts=3,
        max_retry_delay_seconds=2.0,
        retry_budget_seconds=20.0,
    )
    sleeps: list[float] = []
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=config,
        session=session,
        sleep_fn=sleeps.append,
    )

    with pytest.raises(CollectionError, match="HTTP_REQUEST_FAILED"):
        collector.collect()

    assert sleeps == []
    assert len(session.calls) == 2


def test_retry_budget_refuses_oversized_delay(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    session = FakeSession(
        [FakeResponse(version), FakeResponse(b"{}", 429, retry_after="10")]
    )
    config = ClinicalTrialsV2Config(
        nct_ids=("NCT00000001",),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        max_attempts=3,
        retry_backoff_seconds=0.25,
        max_retry_delay_seconds=2.0,
        retry_budget_seconds=1.0,
    )
    sleeps: list[float] = []
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=config,
        session=session,
        sleep_fn=sleeps.append,
    )

    with pytest.raises(CollectionError, match="HTTP_REQUEST_FAILED"):
        collector.collect()

    assert sleeps == []
    assert len(session.calls) == 2


def test_request_timeouts_shrink_with_remaining_retry_budget(tmp_path: Path) -> None:
    monotonic = FakeMonotonic()
    session = ConsumingSession(
        [FakeResponse(b"{}", 503), FakeResponse(b"{}")],
        monotonic,
        [0.4, 0.1],
    )
    config = ClinicalTrialsV2Config(
        nct_ids=("NCT00000001",),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        max_attempts=2,
        retry_backoff_seconds=0.1,
        max_retry_delay_seconds=0.5,
        retry_budget_seconds=1.0,
    )
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=config,
        session=session,
        monotonic_fn=monotonic,
        sleep_fn=monotonic.advance,
    )

    collector._get("/version")

    assert session.calls[0]["timeout"] == pytest.approx((0.5, 0.5))
    assert session.calls[1]["timeout"] == pytest.approx((0.25, 0.25))


def test_retry_deadline_exhaustion_prevents_another_request(tmp_path: Path) -> None:
    monotonic = FakeMonotonic()
    session = ConsumingSession(
        [FakeResponse(b"{}", 503)], monotonic, [0.95]
    )
    config = ClinicalTrialsV2Config(
        nct_ids=("NCT00000001",),
        user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        max_attempts=3,
        retry_backoff_seconds=0.1,
        max_retry_delay_seconds=0.5,
        retry_budget_seconds=1.0,
    )
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=config,
        session=session,
        monotonic_fn=monotonic,
        sleep_fn=monotonic.advance,
    )

    with pytest.raises(CollectionError, match="HTTP_REQUEST_FAILED"):
        collector._get("/version")

    assert len(session.calls) == 1


def test_corrupt_archived_page_fails_replay_and_preserves_last_good_pointer(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, first, second = two_page_fixture
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(first), FakeResponse(second), FakeResponse(version)],
        _config("NCT00000001", "NCT00000002"),
    )
    result = collector.collect()
    pointer_before = result.current_pointer_path.read_bytes()
    receipt_path = next(
        path
        for path in sorted((tmp_path / "private").glob("**/receipts/**/*.json"))
        if "/version/" not in path.as_posix()
    )
    receipt = json.loads(receipt_path.read_text())
    raw_path = tmp_path / "private" / receipt["response"]["raw_response_object_key"]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")

    with pytest.raises(contracts.ContractValidationError, match="raw_response_hash"):
        collector.replay(result.run_path)

    assert result.current_pointer_path.read_bytes() == pointer_before


def test_partial_fetch_records_failed_run_and_never_promotes(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, first, second = two_page_fixture
    good, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(first), FakeResponse(second), FakeResponse(version)],
        _config("NCT00000001", "NCT00000002"),
    )
    result = good.collect()
    pointer_before = result.current_pointer_path.read_bytes()
    failing, _ = _collector(
        tmp_path,
        [
            FakeResponse(version),
            FakeResponse(first),
            FakeResponse(b"{}", 503),
            FakeResponse(b"{}", 503),
            FakeResponse(b"{}", 503),
        ],
        _config("NCT00000001", "NCT00000002"),
        start=datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(CollectionError, match="HTTP_REQUEST_FAILED"):
        failing.collect()

    assert result.current_pointer_path.read_bytes() == pointer_before
    failed_runs = [
        json.loads(path.read_text())
        for path in (tmp_path / "private").glob("**/runs/**/*.json")
        if "160000" in path.name
    ]
    assert len(failed_runs) == 1
    assert failed_runs[0]["run_state"] == "failed"
    assert failed_runs[0]["counts"]["pages_succeeded"] == 1


def test_batch_context_parses_each_page_once_not_once_per_study(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = _json_bytes(
        {"apiVersion": "2.0.5", "dataTimestamp": "2026-08-01T09:00:00"}
    )
    page = _json_bytes(
        {
            "studies": [
                _study("NCT00000001", "One"),
                _study("NCT00000002", "Two"),
                _study("NCT00000003", "Three"),
            ],
            "totalCount": 3,
        }
    )
    calls = 0
    original = contracts.validate_source_page_receipt_against_raw_response

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        contracts, "validate_source_page_receipt_against_raw_response", counted
    )
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001", "NCT00000002", "NCT00000003"),
    )

    collector.collect()

    assert calls == 1


def test_identical_duplicate_across_pages_publishes_one_deterministic_snapshot(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    study = _study("NCT00000001", "One")
    first = _json_bytes(
        {"studies": [study], "nextPageToken": "next", "totalCount": 1}
    )
    second = _json_bytes({"studies": [study], "totalCount": 1})
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(first), FakeResponse(second), FakeResponse(version)],
        _config("NCT00000001"),
    )

    result = collector.collect()

    run = json.loads(result.run_path.read_text())
    assert run["counts"]["studies_fetched"] == 2
    assert run["counts"]["studies_unique"] == 1
    assert run["counts"]["studies_duplicate"] == 1
    assert result.source_snapshot_count == 1
    assert sorted(path.name for path in result.generation_path.iterdir()) == [
        "NCT00000001.json",
        "publication_manifest.json",
    ]
    public_state = json.loads(
        (result.generation_path / "NCT00000001.json").read_text()
    )
    receipts = sorted((tmp_path / "private").glob("**/receipts/**/*.json"))
    first_receipt = json.loads(receipts[0].read_text())
    first_digest = contracts.canonical_json_sha256(study)
    assert public_state["source_record_ref"] == (
        f"src:ctgov:NCT00000001:sha256:{first_digest}"
    )
    private_snapshots = list(
        (tmp_path / "private").glob("**/source_snapshots/**/*.json")
    )
    assert len(private_snapshots) == 1
    assert json.loads(private_snapshots[0].read_text())["page_receipt_ref"] == (
        first_receipt["receipt_id"]
    )


def test_context_defensively_owns_validated_inputs() -> None:
    fixture_root = Path(__file__).parents[1] / "data" / "biocatalyst" / "fixtures" / "clinicaltrials"
    run = json.loads((fixture_root / "ctgov_fetch_run.v1.valid.json").read_text())
    receipt = json.loads((fixture_root / "source_page_receipt.v1.valid.json").read_text())
    raw = (fixture_root / "source_page_response.after.raw.json").read_bytes()
    context = contracts.build_ctgov_publication_context(
        run, [receipt], {receipt["receipt_id"]: raw}
    )

    run["run_id"] = "ctgov_run_mutated"
    receipt["receipt_id"] = "ctgov_receipt_mutated"
    exposed = context.run
    exposed["run_id"] = "ctgov_run_also_mutated"

    assert context.run["run_id"] == "ctgov_run_fixture_20260801T150000Z"
    assert context.receipts[0]["receipt_id"] == "ctgov_receipt_fixture_20260801T150000Z_0"


def test_identical_second_poll_keeps_content_identity_but_not_observation_identity(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    first, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
    )
    first_result = first.collect()
    second, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
        start=datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc),
    )

    second_result = second.collect()

    first_state = json.loads(
        (first_result.generation_path / "NCT00000001.json").read_text()
    )
    second_state = json.loads(
        (second_result.generation_path / "NCT00000001.json").read_text()
    )
    assert first_state["source_record_ref"] == second_state["source_record_ref"]
    assert first_state["source_snapshot_id"] != second_state["source_snapshot_id"]


def test_publication_failure_keeps_pointer_and_writes_distinct_incident(
    tmp_path: Path,
    two_page_fixture: tuple[bytes, bytes, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    first, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
    )
    first_result = first.collect()
    pointer_before = first_result.current_pointer_path.read_bytes()
    second, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
        start=datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc),
    )

    def fail_promotion(*args, **kwargs):
        raise CollectionError("PUBLICATION_FAILED", "synthetic fault")

    monkeypatch.setattr(second, "_publish_generation", fail_promotion)
    with pytest.raises(CollectionError, match="PUBLICATION_FAILED"):
        second.collect()

    assert first_result.current_pointer_path.read_bytes() == pointer_before
    incidents = list((tmp_path / "private").glob("**/*.publication_failure.json"))
    assert len(incidents) == 1
    incident = json.loads(incidents[0].read_text())
    assert incident["current_pointer_state"] == "prior_generation"
    assert incident["current_pointer_generation"] == first_result.run_id


def test_non_identity_response_encoding_fails_before_exact_byte_claim(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page, content_encoding="gzip")],
        _config("NCT00000001"),
    )

    with pytest.raises(CollectionError, match="UNSUPPORTED_CONTENT_ENCODING"):
        collector.collect()

    assert not (tmp_path / "public" / "current.json").exists()
    receipts = list((tmp_path / "private").glob("**/receipts/**/*.json"))
    assert [path for path in receipts if "/version/" not in path.as_posix()] == []
    assert len([path for path in receipts if "/version/" in path.as_posix()]) == 1
    failed_raw = list((tmp_path / "private").glob("**/failed-fetch/**/*.bin"))
    failed_incidents = list((tmp_path / "private").glob("**/*.failed_fetch_studies_*.json"))
    assert len(failed_raw) == len(failed_incidents) == 1
    assert failed_raw[0].read_bytes() == page


def test_duplicate_json_key_in_version_fails_closed(tmp_path: Path) -> None:
    duplicate_version = (
        b'{"apiVersion":"2.0.5","apiVersion":"2.0.6",'
        b'"dataTimestamp":"2026-08-01T09:00:00"}'
    )
    collector, _ = _collector(
        tmp_path, [FakeResponse(duplicate_version)], _config("NCT00000001")
    )

    with pytest.raises(CollectionError, match="duplicate JSON object key"):
        collector.collect()

    failed_raw = list((tmp_path / "private").glob("**/failed-fetch/**/*.bin"))
    failed_incidents = list((tmp_path / "private").glob("**/*.failed_fetch_version_*.json"))
    assert len(failed_raw) == len(failed_incidents) == 1
    assert failed_raw[0].read_bytes() == duplicate_version
    assert list((tmp_path / "private").glob("**/receipts/**/*.json")) == []


@pytest.mark.parametrize("nonfinite", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonfinite_json_number_in_version_fails_closed(
    tmp_path: Path, nonfinite: bytes
) -> None:
    invalid_version = (
        b'{"apiVersion":"2.0.5","dataTimestamp":"2026-08-01T09:00:00",'
        b'"unused":' + nonfinite + b"}"
    )
    collector, _ = _collector(
        tmp_path, [FakeResponse(invalid_version)], _config("NCT00000001")
    )

    with pytest.raises(CollectionError, match="non-finite JSON number"):
        collector.collect()

    assert len(list((tmp_path / "private").glob("**/failed-fetch/**/*.bin"))) == 1


def test_malformed_studies_200_retains_private_failed_fetch_without_page_receipt(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    malformed = b'{"studies":['
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(malformed)],
        _config("NCT00000001"),
    )

    with pytest.raises(CollectionError, match="INVALID_SOURCE_JSON"):
        collector.collect()

    receipts = list((tmp_path / "private").glob("**/receipts/**/*.json"))
    assert len([path for path in receipts if "/version/" in path.as_posix()]) == 1
    assert [path for path in receipts if "/version/" not in path.as_posix()] == []
    failed_raw = list((tmp_path / "private").glob("**/failed-fetch/**/*.bin"))
    incident = json.loads(next((tmp_path / "private").glob("**/*.failed_fetch_studies_*.json")).read_text())
    assert failed_raw[0].read_bytes() == malformed
    assert incident["status_code"] == 200
    assert incident["failure_code"] == "INVALID_SOURCE_JSON"


def test_replay_rejects_a_run_from_a_different_parser_contract_digest(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
    )
    result = collector.collect()
    run = json.loads(result.run_path.read_text())
    run["code_version"] = "biocatalyst_b1_sha256:" + "0" * 64
    result.run_path.write_bytes(collector_module.canonical_json_bytes(run) + b"\n")

    with pytest.raises(CollectionError, match="UNSUPPORTED_CODE_VERSION"):
        collector.replay(result.run_path)


def test_query_manifest_binds_wire_parameters(tmp_path: Path) -> None:
    collector, _ = _collector(tmp_path, [], _config("NCT00000001", "NCT00000002"))
    manifest = collector._query_manifest()
    run = json.loads(
        (
            Path(__file__).parents[1]
            / "data"
            / "biocatalyst"
            / "fixtures"
            / "clinicaltrials"
            / "ctgov_fetch_run.v1.valid.json"
        ).read_text()
    )
    run["query_manifest"] = manifest
    run["counts"]["configured"] = 2
    run["published_source_record_refs"] = []
    run["counts"]["studies_published"] = 0
    run["run_state"] = "failed"
    run["completeness_state"] = "page_incomplete"
    run["watermark_after"] = run["watermark_before"]
    run["query_manifest"]["base_query_params"]["query.id"] = "NCT00000002,NCT00000001"
    run["query_manifest"]["query_sha256"] = contracts.ctgov_query_manifest_sha256(
        run["query_manifest"]
    )

    with pytest.raises(contracts.ContractValidationError, match="query_wire_binding"):
        contracts.validate_contract(run)


def test_terminal_page_version_drift_is_truthfully_quarantined(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    changed_version = _json_bytes(
        {"apiVersion": "2.0.6", "dataTimestamp": "2026-08-01T09:00:00"}
    )
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(changed_version)],
        _config("NCT00000001"),
    )

    with pytest.raises(CollectionError, match="SOURCE_CHANGED_MID_RUN"):
        collector.collect()

    run_path = next((tmp_path / "private").glob("**/runs/**/*.json"))
    run = json.loads(run_path.read_text())
    assert run["run_state"] == "quarantined"
    assert run["completeness_state"] == "source_changed_mid_run"
    assert run["terminal_receipt_ref"] == run["receipt_refs"][-1]
    assert run["counts"]["studies_fetched"] == 1
    assert run["counts"]["studies_unique"] == 1
    assert run["counts"]["studies_duplicate"] == 0
    details = json.loads(
        next((tmp_path / "private").glob("**/*.source_drift.json")).read_text()
    )
    assert details["source_api_version_before"] == "2.0.5"
    assert details["source_api_version_after"] == "2.0.6"


def test_terminal_missing_configured_nct_is_count_mismatch_quarantine(
    tmp_path: Path, two_page_fixture: tuple[bytes, bytes, bytes]
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    collector, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001", "NCT00000002"),
    )

    with pytest.raises(CollectionError, match="COUNT_MISMATCH"):
        collector.collect()

    run = json.loads(next((tmp_path / "private").glob("**/runs/**/*.json")).read_text())
    assert run["run_state"] == "quarantined"
    assert run["completeness_state"] == "count_mismatch"
    assert run["error_codes"] == ["COUNT_MISMATCH"]
    assert run["terminal_receipt_ref"] == run["receipt_refs"][-1]
    assert run["counts"]["studies_unique"] == 1
    assert run["counts"]["studies_duplicate"] == 0


def test_pointer_fsync_failure_restores_prior_pointer(
    tmp_path: Path,
    two_page_fixture: tuple[bytes, bytes, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version, _, _ = two_page_fixture
    page = _json_bytes(
        {"studies": [_study("NCT00000001", "One")], "totalCount": 1}
    )
    first, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
    )
    first_result = first.collect()
    pointer_before = first_result.current_pointer_path.read_bytes()
    second, _ = _collector(
        tmp_path,
        [FakeResponse(version), FakeResponse(page), FakeResponse(version)],
        _config("NCT00000001"),
        start=datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc),
    )
    original_fsync = collector_module._fsync_directory
    faulted = False

    def fail_once_after_pointer_replace(directory: Path) -> None:
        nonlocal faulted
        if directory == (tmp_path / "public").resolve() and not faulted:
            faulted = True
            raise OSError("synthetic directory fsync failure")
        original_fsync(directory)

    monkeypatch.setattr(collector_module, "_fsync_directory", fail_once_after_pointer_replace)
    with pytest.raises(OSError, match="synthetic directory fsync failure"):
        second.collect()

    assert first_result.current_pointer_path.read_bytes() == pointer_before
    incident = json.loads(
        next((tmp_path / "private").glob("**/*.publication_failure.json")).read_text()
    )
    assert incident["current_pointer_state"] == "prior_generation"
    assert incident["current_pointer_generation"] == first_result.run_id
