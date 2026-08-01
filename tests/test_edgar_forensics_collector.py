from __future__ import annotations

import gzip
import json
import os

import pytest

from collectors.edgar_forensics import (
    SecForensicsCollector,
    endpoint_url,
    persist_response,
)


def test_endpoint_urls_are_canonical_and_closed_set():
    assert endpoint_url(320193, "companyfacts").endswith("/CIK0000320193.json")
    assert endpoint_url("0000320193", "submissions").endswith("/CIK0000320193.json")
    with pytest.raises(ValueError):
        endpoint_url(320193, "filing_html")


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
    status_code = 200
    headers = {"ETag": '"abc"'}
    content = b'{"facts":{}}'

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


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
    assert (tmp_path / receipt.object_path).exists()


def test_collector_rejects_anonymous_user_agent(tmp_path):
    with pytest.raises(ValueError):
        SecForensicsCollector(tmp_path, user_agent="anonymous")
