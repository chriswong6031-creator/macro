from __future__ import annotations

import gzip
import json
import os

import pytest

import collectors.edgar_forensics as edgar_forensics
from collectors.edgar_forensics import (
    SecForensicsCollector,
    SecResponseTooLarge,
    endpoint_url,
    historical_submissions_url,
    persist_response,
)


def test_endpoint_urls_are_canonical_and_closed_set():
    assert endpoint_url(320193, "companyfacts").endswith("/CIK0000320193.json")
    assert endpoint_url("0000320193", "submissions").endswith("/CIK0000320193.json")
    with pytest.raises(ValueError):
        endpoint_url(320193, "filing_html")


def test_historical_submissions_url_is_canonical_and_cik_bound():
    name = "CIK0000320193-submissions-001.json"
    assert historical_submissions_url(320193, name) == (
        "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    )
    with pytest.raises(ValueError, match="does not bind CIK"):
        historical_submissions_url(1, name)
    with pytest.raises(ValueError, match="does not bind CIK"):
        historical_submissions_url(320193, "../CIK0000320193-submissions-001.json")


def test_content_addressed_persistence_is_immutable_and_idempotent(tmp_path):
    body = json.dumps({"cik": 320193, "facts": {}}, separators=(",", ":")).encode()
    kwargs = dict(
        raw_root=tmp_path,
        cik=320193,
        endpoint="companyfacts",
        url=endpoint_url(320193, "companyfacts"),
        content=body,
        retrieved_at="2026-08-01T12:00:00+00:00",
    )
    first = persist_response(**kwargs)
    second = persist_response(**kwargs)

    assert first.sha256 == second.sha256
    assert first.object_path == second.object_path
    objects = list(tmp_path.glob("**/*.json.gz"))
    assert len(objects) == 1
    with gzip.open(objects[0], "rb") as fh:
        assert fh.read() == body
    receipt = json.loads(objects[0].with_suffix(".receipt.json").read_text())
    assert receipt["schema"] == "fundamental_forensics_retrieval.v1"
    assert receipt["sha256"] == first.sha256


def test_changed_source_creates_new_object_and_latest_pointer(tmp_path):
    base = dict(
        raw_root=tmp_path,
        cik=320193,
        endpoint="submissions",
        url=endpoint_url(320193, "submissions"),
        retrieved_at="2026-08-01T12:00:00+00:00",
    )
    one = persist_response(content=b'{"version":1}', **base)
    two = persist_response(content=b'{"version":2}', **base)

    assert one.sha256 != two.sha256
    assert len(list(tmp_path.glob("**/*.json.gz"))) == 2
    latest = json.loads((tmp_path / "0000320193" / "submissions" / "latest.json").read_text())
    assert latest["sha256"] == two.sha256


def test_historical_submissions_persistence_never_repoints_current_latest(tmp_path):
    current = persist_response(
        raw_root=tmp_path,
        cik=320193,
        endpoint="submissions",
        url=endpoint_url(320193, "submissions"),
        content=b'{"cik":"0000320193","filings":{"files":[]}}',
        retrieved_at="2026-08-01T12:00:00+00:00",
    )
    older = persist_response(
        raw_root=tmp_path,
        cik=320193,
        endpoint="submissions",
        url=historical_submissions_url(
            320193, "CIK0000320193-submissions-001.json"
        ),
        content=b'{"accessionNumber":[]}',
        retrieved_at="2026-08-01T12:00:01+00:00",
        publish_latest=False,
    )

    latest = json.loads(
        (tmp_path / "0000320193" / "submissions" / "latest.json").read_text()
    )
    assert latest["sha256"] == current.sha256
    assert older.sha256 != current.sha256
    assert (tmp_path / older.object_path).exists()


def test_persistence_rejects_invalid_pointer_policy_before_any_write(tmp_path):
    with pytest.raises(TypeError, match="publish_latest must be a boolean"):
        persist_response(
            raw_root=tmp_path,
            cik=320193,
            endpoint="submissions",
            url=endpoint_url(320193, "submissions"),
            content=b'{}',
            retrieved_at="2026-08-01T12:00:00+00:00",
            publish_latest="false",
        )
    assert list(tmp_path.rglob("*")) == []


def test_corrupt_existing_object_and_receipt_are_atomically_repaired(tmp_path):
    body = b'{"cik":320193,"facts":{"x":1}}'
    kwargs = dict(
        raw_root=tmp_path,
        cik=320193,
        endpoint="companyfacts",
        url=endpoint_url(320193, "companyfacts"),
        content=body,
        retrieved_at="2026-08-01T12:00:00+00:00",
    )
    receipt = persist_response(**kwargs)
    target = tmp_path / receipt.object_path
    sidecar = target.with_suffix(".receipt.json")
    target.write_bytes(b"truncated-gzip")
    sidecar.write_bytes(b'{"torn":')

    repaired = persist_response(**kwargs)

    assert repaired.sha256 == receipt.sha256
    with gzip.open(target, "rb") as fh:
        assert fh.read() == body
    assert json.loads(sidecar.read_text())["sha256"] == receipt.sha256
    assert not list(tmp_path.rglob("*.tmp"))


def test_interrupted_latest_replace_retains_previous_complete_pointer(tmp_path, monkeypatch):
    base = dict(
        raw_root=tmp_path,
        cik=320193,
        endpoint="submissions",
        url=endpoint_url(320193, "submissions"),
        retrieved_at="2026-08-01T12:00:00+00:00",
    )
    first = persist_response(content=b'{"version":1}', **base)
    latest = tmp_path / "0000320193" / "submissions" / "latest.json"
    before = latest.read_bytes()
    real_replace = os.replace

    def fail_latest(source, destination):
        if str(destination).endswith("latest.json"):
            raise OSError("simulated interruption")
        return real_replace(source, destination)

    monkeypatch.setattr("collectors.edgar_forensics.os.replace", fail_latest)
    with pytest.raises(OSError, match="simulated interruption"):
        persist_response(content=b'{"version":2}', **base)

    assert latest.read_bytes() == before
    assert json.loads(latest.read_text())["sha256"] == first.sha256
    assert not list(tmp_path.rglob("*.tmp"))


def test_content_addressed_gzip_bytes_are_reproducible_across_roots(tmp_path):
    body = b'{"cik":320193,"facts":{}}'
    common = dict(
        cik=320193,
        endpoint="companyfacts",
        url=endpoint_url(320193, "companyfacts"),
        content=body,
        retrieved_at="2026-08-01T12:00:00+00:00",
    )
    one = persist_response(raw_root=tmp_path / "one", **common)
    two = persist_response(raw_root=tmp_path / "two", **common)

    assert (tmp_path / "one" / one.object_path).read_bytes() == (
        tmp_path / "two" / two.object_path
    ).read_bytes()


class _Response:
    def __init__(
        self,
        url: str,
        *,
        body: bytes = b'{"facts":{}}',
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
        close_error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers if headers is not None else {"ETag": '"abc"'}
        self._body = body
        self._chunks = chunks
        self._close_error = close_error
        self._events = events
        self.closed = False
        self.stream_chunk_sizes: list[int] = []

    @property
    def content(self) -> bytes:
        raise AssertionError("bounded collector must not read response.content")

    def iter_content(self, *, chunk_size: int):
        self.stream_chunk_sizes.append(chunk_size)
        if self._chunks is not None:
            yield from self._chunks
            return
        for offset in range(0, len(self._body), chunk_size):
            yield self._body[offset : offset + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self) -> None:
        self.closed = True
        if self._events is not None:
            self._events.append("close")
        if self._close_error is not None:
            raise self._close_error


class _Session:
    def __init__(self, response_factory=None):
        self.calls = []
        self.response_factory = response_factory
        self.responses: list[_Response] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = (
            self.response_factory(url) if self.response_factory is not None else _Response(url)
        )
        self.responses.append(response)
        return response


def test_collector_uses_contact_user_agent_and_writes_receipt(tmp_path):
    session = _Session()
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )
    receipt = collector.fetch(320193, "companyfacts", retrieved_at="2026-08-01T12:00:00+00:00")

    assert receipt.http_etag == '"abc"'
    assert session.calls[0][1]["headers"]["User-Agent"] == "MastermindX research@example.com"
    assert session.calls[0][1]["stream"] is True
    assert session.calls[0][1]["allow_redirects"] is False
    assert session.responses[0].closed is True
    assert (tmp_path / receipt.object_path).exists()


def test_collector_fetches_historical_submissions_without_moving_latest(tmp_path):
    session = _Session()
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )
    current = collector.fetch(
        320193, "submissions", retrieved_at="2026-08-01T12:00:00+00:00"
    )
    historical = collector.fetch_historical_submissions_file(
        320193,
        "CIK0000320193-submissions-001.json",
        retrieved_at="2026-08-01T12:00:01+00:00",
    )

    latest = json.loads(
        (tmp_path / "0000320193" / "submissions" / "latest.json").read_text()
    )
    assert latest["sha256"] == current.sha256
    assert historical.url.endswith("/CIK0000320193-submissions-001.json")
    assert session.calls[-1][0] == historical.url
    assert session.calls[-1][1]["stream"] is True
    assert session.calls[-1][1]["allow_redirects"] is False


def test_collector_retrieves_historical_submissions_exact_bytes_without_persistence(tmp_path):
    source_name = "CIK0000320193-submissions-001.json"
    expected_url = historical_submissions_url(320193, source_name)
    body = b'{"accessionNumber":["0000320193-24-000001"]}'
    session = _Session(
        lambda url: _Response(
            url,
            body=body,
            headers={"ETag": '"historic"', "Last-Modified": "Thu, 01 Aug 2024 00:00:00 GMT"},
        )
    )
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    content, metadata = collector.retrieve_historical_submissions_file(
        320193,
        source_name,
        max_response_bytes=len(body),
    )

    assert content == body
    assert metadata == {
        "url": expected_url,
        "http_etag": '"historic"',
        "http_last_modified": "Thu, 01 Aug 2024 00:00:00 GMT",
    }
    assert session.calls == [
        (
            expected_url,
            {
                "headers": {
                    "User-Agent": "MastermindX research@example.com",
                    "Accept-Encoding": "gzip, deflate",
                },
                "timeout": collector.timeout_seconds,
                "stream": True,
                "allow_redirects": False,
            },
        )
    ]
    assert session.responses[0].stream_chunk_sizes == [len(body) + 1]
    assert session.responses[0].closed is True
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.parametrize(
    "cik,source_name",
    [
        (1, "CIK0000320193-submissions-001.json"),
        (320193, "../CIK0000320193-submissions-001.json"),
        (320193, "CIK0000320193-submissions-01.json"),
    ],
)
def test_historical_retrieval_rejects_unbound_or_malformed_name_before_network(
    tmp_path, cik, source_name
):
    session = _Session()
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    with pytest.raises(ValueError, match="does not bind CIK"):
        collector.retrieve_historical_submissions_file(cik, source_name)

    assert session.calls == []
    assert list(tmp_path.rglob("*")) == []


def test_collector_rejects_oversize_stream_without_content_length(tmp_path):
    limit = 32
    session = _Session(
        lambda url: _Response(
            url,
            body=b"x" * (limit + 1),
            headers={"ETag": '"no-length"'},
        )
    )
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        max_response_bytes=limit,
        session=session,
    )

    with pytest.raises(SecResponseTooLarge, match="33 > 32"):
        collector.fetch(320193, "submissions")

    assert session.responses[0].closed is True
    assert session.responses[0].stream_chunk_sizes == [limit + 1]
    assert not list(tmp_path.rglob("*.json.gz"))


def test_collector_caps_retained_bytes_when_stream_ignores_requested_chunk_size(tmp_path):
    limit = 17
    giant_chunk = b"x" * (limit + 512 * 1024)
    session = _Session(
        lambda url: _Response(
            url,
            chunks=[giant_chunk],
            headers={"ETag": '"lying-length"', "Content-Length": "1"},
        )
    )
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        max_response_bytes=limit,
        session=session,
    )

    with pytest.raises(SecResponseTooLarge, match="18 > 17"):
        collector.fetch(320193, "submissions")

    # The stream adapter asks for only limit + 1 bytes and reports that
    # retained bound rather than accepting the producer's giant chunk.
    assert session.responses[0].stream_chunk_sizes == [limit + 1]
    assert session.responses[0].closed is True
    assert not list(tmp_path.rglob("*.json.gz"))


def test_collector_refuses_redirect_responses_before_streaming_or_persistence(tmp_path):
    session = _Session(lambda url: _Response(url, status_code=302))
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    with pytest.raises(RuntimeError, match="redirects are refused"):
        collector.fetch(320193, "submissions")

    assert len(session.calls) == 1
    assert session.responses[0].stream_chunk_sizes == []
    assert session.responses[0].closed is True
    assert not list(tmp_path.rglob("*.json.gz"))


def test_collector_requires_exact_response_url_before_streaming_or_persistence(tmp_path):
    session = _Session(
        lambda _url: _Response("https://www.sec.gov/submissions/CIK0000320193.json")
    )
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    with pytest.raises(RuntimeError, match="URL does not match"):
        collector.fetch(320193, "submissions")

    assert len(session.calls) == 1
    assert session.responses[0].stream_chunk_sizes == []
    assert session.responses[0].closed is True
    assert not list(tmp_path.rglob("*.json.gz"))


def test_collector_requires_streaming_response_interface(tmp_path):
    response = _Response(endpoint_url(320193, "submissions"))
    response.iter_content = None
    session = _Session(lambda _url: response)
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    with pytest.raises(RuntimeError, match="bounded streamed responses"):
        collector.fetch(320193, "submissions")

    assert response.closed is True
    assert not list(tmp_path.rglob("*.json.gz"))


def test_collector_fails_closed_when_response_close_fails(tmp_path, monkeypatch):
    response = _Response(
        endpoint_url(320193, "submissions"),
        close_error=OSError("socket close fault"),
    )
    session = _Session(lambda _url: response)
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    def clock_after_failed_close():
        raise AssertionError("retrieval clock must not run after a failed close")

    monkeypatch.setattr(edgar_forensics, "_utc_now", clock_after_failed_close)
    with pytest.raises(RuntimeError, match="response close failed") as exc_info:
        collector.fetch(320193, "submissions")

    assert isinstance(exc_info.value.__cause__, OSError)
    assert response.closed is True
    assert not list(tmp_path.rglob("*.json.gz"))


def test_collector_samples_retrieval_clock_only_after_response_close(tmp_path, monkeypatch):
    events: list[str] = []
    response = _Response(endpoint_url(320193, "submissions"), events=events)
    session = _Session(lambda _url: response)
    collector = SecForensicsCollector(
        tmp_path,
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=session,
    )

    def clock_after_close() -> str:
        assert response.closed is True
        events.append("clock")
        return "2026-08-01T12:00:00+00:00"

    monkeypatch.setattr(edgar_forensics, "_utc_now", clock_after_close)
    receipt = collector.fetch(320193, "submissions")

    assert receipt.retrieved_at == "2026-08-01T12:00:00+00:00"
    assert events == ["close", "clock"]


def test_collector_rejects_anonymous_user_agent(tmp_path):
    with pytest.raises(ValueError):
        SecForensicsCollector(tmp_path, user_agent="anonymous")
