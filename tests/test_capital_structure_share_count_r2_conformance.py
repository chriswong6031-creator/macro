"""Adversarial tests for the isolated manual R2 CAS conformance witness."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure import share_count_r2_conformance as conformance


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
BUCKET = "capital-structure-conformance"
KEY = "capital_structure/share_counts/conformance/v1/0123456789abcdef0123456789abcdef.json"
HOST = "0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
PROVENANCE = {
    "repository": "chriswong6031-creator/macro",
    "workflow_ref": "chriswong6031-creator/macro/.github/workflows/capital-share-count-r2-conformance.yml@refs/heads/main",
    "run_id": "123456789",
    "run_attempt": 1,
    "commit_sha": "a" * 40,
    "event_name": "workflow_dispatch",
    "actor": "operator-test",
}
EXECUTION_PROVENANCE = {
    "source_archive_sha256": "b" * 64,
    "dependency_lock_sha256": "c" * 64,
}


class ClientError(RuntimeError):
    def __init__(self, status: int, code: str = "PreconditionFailed") -> None:
        super().__init__(f"HTTP {status}")
        self.response = {
            "ResponseMetadata": {"HTTPStatusCode": status},
            "Error": {"Code": code},
        }


ClientError.__module__ = "botocore.exceptions"


class _Body:
    def __init__(self, body: bytes, *, chunk_size: int | None = None, extra: bytes = b"", close_error: bool = False) -> None:
        self._body, self._chunk_size, self._extra = body, chunk_size, extra
        self._position, self._close_error, self.closed = 0, close_error, False

    def read(self, size: int) -> bytes:
        assert size >= 0
        source = self._body + self._extra
        if self._position >= len(source):
            return b""
        wanted = size if self._chunk_size is None else min(size, self._chunk_size)
        value = source[self._position:self._position + wanted]
        self._position += len(value)
        return value

    def close(self) -> None:
        self.closed = True
        if self._close_error:
            raise OSError("body close failed")


class _R2:
    """In-memory narrow client that models only Head/Get/Put conditionals."""

    def __init__(
        self,
        *,
        conflict_status: int = 412,
        reuse_update_etag: bool = False,
        wrong_content_range: bool = False,
        wrong_get_etag: bool = False,
        body_extra: bytes = b"",
        close_error: bool = False,
        stale_put_mutates: bool = False,
        stale_get_succeeds: bool = False,
        create_error: Exception | None = None,
        empty_etag: bool = False,
        chunk_size: int | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.returned_bodies: list[_Body] = []
        self._body: bytes | None = None
        self._etag: str | None = None
        self._version = 0
        self.conflict_status = conflict_status
        self.reuse_update_etag = reuse_update_etag
        self.wrong_content_range = wrong_content_range
        self.wrong_get_etag = wrong_get_etag
        self.body_extra = body_extra
        self.close_error = close_error
        self.stale_put_mutates = stale_put_mutates
        self.stale_get_succeeds = stale_get_succeeds
        self.create_error = create_error
        self.empty_etag = empty_etag
        self.chunk_size = chunk_size

    def _response(self, status: int, **extra: Any) -> dict[str, Any]:
        return {"ResponseMetadata": {"HTTPStatusCode": status}, **extra}

    def _advance(self, body: bytes) -> None:
        self._body = body
        if not self.reuse_update_etag or self._etag is None:
            self._version += 1
            self._etag = "" if self.empty_etag else f'"opaque-etag-{self._version}"'

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("put_object", dict(kwargs)))
        if self.create_error is not None and self._body is None:
            raise self.create_error
        assert kwargs["ContentType"] == "application/json"
        if kwargs.get("IfNoneMatch") == "*":
            if self._body is not None:
                raise ClientError(self.conflict_status)
            self._advance(kwargs["Body"])
            return self._response(200)
        if "IfMatch" not in kwargs:
            raise AssertionError("conditional PutObject is required")
        if kwargs["IfMatch"] != self._etag:
            if self.stale_put_mutates:
                self._advance(kwargs["Body"])
            raise ClientError(self.conflict_status)
        self._advance(kwargs["Body"])
        return self._response(200)

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("head_object", dict(kwargs)))
        assert self._body is not None and self._etag is not None
        return self._response(
            200,
            ContentLength=len(self._body),
            ContentType="application/json",
            ETag=self._etag,
        )

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_object", dict(kwargs)))
        assert self._body is not None and self._etag is not None
        if kwargs.get("IfMatch") != self._etag and not self.stale_get_succeeds:
            raise ClientError(self.conflict_status)
        expected_range = f"bytes=0-{len(self._body) - 1}"
        assert kwargs["Range"] == expected_range
        response_etag = '"wrong-etag"' if self.wrong_get_etag else self._etag
        content_range = "bytes 0-0/1" if self.wrong_content_range else f"bytes 0-{len(self._body) - 1}/{len(self._body)}"
        stream = _Body(
            self._body,
            chunk_size=self.chunk_size,
            extra=self.body_extra,
            close_error=self.close_error,
        )
        self.returned_bodies.append(stream)
        return self._response(
            206,
            ContentLength=len(self._body),
            ContentType="application/json",
            ContentRange=content_range,
            ETag=response_etag,
            Body=stream,
        )


def _run(client: _R2, **kwargs: Any) -> dict[str, Any]:
    return conformance.run_conformance(
        client=client,
        bucket=BUCKET,
        key=KEY,
        endpoint_host=HOST,
        github_provenance=PROVENANCE,
        execution_provenance=EXECUTION_PROVENANCE,
        observed_at=NOW,
        **kwargs,
    )


def _schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "contracts" / "capital_structure_share_count_r2_conformance_receipt.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_schema(record: dict[str, Any]) -> None:
    errors = list(Draft202012Validator(_schema(), format_checker=FormatChecker()).iter_errors(record))
    assert not errors, "\n".join(error.message for error in errors)


def test_happy_path_proves_only_the_required_sequence_with_redacted_canonical_receipt() -> None:
    client = _R2(chunk_size=3)
    result = _run(client)
    receipt = result["receipt"]

    assert result["status"] == receipt["status"] == "passed"
    _assert_schema(receipt)
    conformance.validate_conformance_receipt(receipt)
    assert conformance.canonical_receipt_bytes(receipt).endswith(b"\n")
    assert b"\n" not in conformance.canonical_receipt_bytes(receipt)[:-1]
    encoded = json.dumps(receipt, sort_keys=True)
    assert BUCKET not in encoded and KEY not in encoded and "opaque-etag" not in encoded
    assert receipt["scope"] == {
        "admitted": True,
        "endpoint_host": HOST,
        "bucket_sha256": conformance._hash_text(BUCKET),
        "key_sha256": conformance._hash_text(KEY),
    }
    assert receipt["steps"]["head_a"] == receipt["steps"]["head_a_after_duplicate"]
    assert receipt["steps"]["get_a"] == receipt["steps"]["get_a_after_duplicate"]
    assert receipt["steps"]["head_a"]["etag_sha256"] != receipt["steps"]["head_b"]["etag_sha256"]
    assert receipt["steps"]["get_b"]["exact_range_verified"] is True
    assert receipt["output_authority"]["is_context_only"] is True
    assert all(value is False for key, value in receipt["output_authority"].items() if key != "is_context_only")
    assert all(value is True for value in receipt["nonclaims"].values())

    assert [method for method, _ in client.calls] == [
        "put_object", "head_object", "get_object", "put_object", "head_object",
        "get_object", "put_object", "head_object", "get_object", "put_object", "get_object",
    ]
    assert client.calls[0][1]["IfNoneMatch"] == "*"
    assert client.calls[3][1]["IfNoneMatch"] == "*"
    assert client.calls[3][1]["Body"] != client.calls[0][1]["Body"]
    assert client.calls[6][1]["IfMatch"] == '"opaque-etag-1"'
    assert client.calls[8][1]["IfMatch"] == '"opaque-etag-1"'
    assert client.calls[9][1]["IfMatch"] == '"opaque-etag-1"'
    assert client.calls[10][1]["IfMatch"] == '"opaque-etag-2"'


@pytest.mark.parametrize(
    "client",
    [
        _R2(conflict_status=500),
        _R2(conflict_status=409),
        _R2(reuse_update_etag=True),
        _R2(wrong_content_range=True),
        _R2(wrong_get_etag=True),
        _R2(body_extra=b"x"),
        _R2(close_error=True),
        _R2(stale_put_mutates=True),
        _R2(stale_get_succeeds=True),
        _R2(create_error=TimeoutError("ambiguous transport")),
        _R2(empty_etag=True),
    ],
)
def test_ambiguous_or_malformed_provider_behavior_never_returns_pass(client: _R2) -> None:
    with pytest.raises(conformance.R2CasConformanceError):
        _run(client)


def test_deadline_is_checked_before_and_after_every_sdk_call() -> None:
    pre_call = iter((0.0, 90.0))
    client = _R2()
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline"):
        _run(client, monotonic=lambda: next(pre_call))
    assert client.calls == []

    post_call = iter((0.0, 0.0, 90.0))
    client = _R2()
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline"):
        _run(client, monotonic=lambda: next(post_call))
    assert [method for method, _ in client.calls] == ["put_object"]


def test_deadline_and_malformed_success_paths_still_close_owned_streams() -> None:
    stream = _Body(b"payload")
    deadline = conformance._Deadline(deadline=1.0, monotonic=lambda: 2.0)
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline"):
        deadline.close("expired", stream)
    assert stream.closed is True

    post_call_stream = _Body(b"payload")
    ticks = iter((0.0, 2.0))
    post_call_deadline = conformance._Deadline(deadline=1.0, monotonic=lambda: next(ticks))
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline"):
        post_call_deadline.call(
            "post-call expiry",
            lambda: {"Body": post_call_stream},
        )
    assert post_call_stream.closed is True

    class ForeignDeadline(RuntimeError):
        conformance_deadline_exceeded = True

    class SignalDeadline(conformance._Deadline):
        def check(self, label):
            if label.startswith("after "):
                raise ForeignDeadline("outer SIGALRM")

    foreign_stream = _Body(b"payload")
    signal_deadline = SignalDeadline(deadline=10.0, monotonic=lambda: 0.0)
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline"):
        signal_deadline.call(
            "foreign deadline",
            lambda: {"Body": foreign_stream},
        )
    assert foreign_stream.closed is True

    class CloseSignalDeadline(conformance._Deadline):
        def check(self, label):
            if label.startswith("before ") and label.endswith(" close"):
                raise ForeignDeadline("outer SIGALRM")

    foreign_close_stream = _Body(b"payload")
    close_signal_deadline = CloseSignalDeadline(deadline=10.0, monotonic=lambda: 0.0)
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline"):
        close_signal_deadline.close("foreign deadline", foreign_close_stream)
    assert foreign_close_stream.closed is True

    for client in (_R2(wrong_content_range=True), _R2(stale_get_succeeds=True)):
        with pytest.raises(conformance.R2CasConformanceError):
            _run(client)
        assert client.returned_bodies
        assert all(body.closed for body in client.returned_bodies)


def test_nonpass_error_carries_closed_stage_category_and_completed_prefix() -> None:
    client = _R2(wrong_content_range=True)
    with pytest.raises(conformance.R2CasConformanceObservedFailure) as raised:
        _run(client)
    evidence = conformance.failure_receipt_evidence(raised.value)
    assert evidence == {
        "status": "inconclusive",
        "failure_stage": "get_a",
        "failure_category": "malformed_response",
        "completed_steps": ("create_a", "head_a"),
    }
    receipt = conformance.build_failure_receipt(
        **evidence,
        bucket=BUCKET,
        key=KEY,
        endpoint_host=HOST,
        github_provenance=PROVENANCE,
        execution_provenance=EXECUTION_PROVENANCE,
        observed_at=NOW,
    )
    _assert_schema(receipt)
    conformance.validate_conformance_receipt(receipt)


def test_typed_412_lookalike_is_not_authoritative() -> None:
    class Lookalike(RuntimeError):
        response = {
            "ResponseMetadata": {"HTTPStatusCode": 412},
            "Error": {"Code": "PreconditionFailed"},
        }

    deadline = conformance._Deadline(deadline=10.0, monotonic=lambda: 0.0)
    with pytest.raises(conformance.R2CasConformanceInconclusive, match="authoritative"):
        conformance._authoritative_conflict(
            deadline=deadline,
            call=lambda: (_ for _ in ()).throw(Lookalike()),
            label="typed lookalike",
        )

    class ForeignDeadline(RuntimeError):
        conformance_deadline_exceeded = True

    with pytest.raises(conformance.R2CasConformanceInconclusive, match="deadline") as raised:
        conformance._authoritative_conflict(
            deadline=deadline,
            call=lambda: (_ for _ in ()).throw(ForeignDeadline()),
            label="foreign deadline",
        )
    assert conformance._failure_category(raised.value) == "deadline"


def test_failure_receipts_are_closed_redacted_and_cannot_fabricate_completed_steps() -> None:
    receipt = conformance.build_failure_receipt(
        status="inconclusive",
        failure_stage="stale_get",
        failure_category="transport",
        bucket=BUCKET,
        key=KEY,
        endpoint_host=HOST,
        github_provenance=PROVENANCE,
        execution_provenance=EXECUTION_PROVENANCE,
        observed_at=NOW,
        completed_steps=(
            "create_a", "head_a", "get_a", "duplicate_create",
            "head_a_after_duplicate", "get_a_after_duplicate", "update_b", "head_b",
        ),
    )
    _assert_schema(receipt)
    assert receipt["failure"] == {"stage": "stale_get", "category": "transport"}
    assert "ambiguous transport" not in json.dumps(receipt)
    tampered = dict(receipt)
    tampered["steps"] = {"completed_steps": ["head_a"]}
    tampered["receipt_id"] = conformance._receipt_id(tampered)
    with pytest.raises(conformance.R2CasConformanceError, match="ordered prefix"):
        conformance.validate_conformance_receipt(tampered)


def test_schema_rejects_nonpass_without_failure_and_pass_without_full_evidence() -> None:
    failed = conformance.build_failure_receipt(
        status="failed",
        failure_stage="setup",
        failure_category="configuration",
        bucket=BUCKET,
        key=KEY,
        endpoint_host=HOST,
        github_provenance=PROVENANCE,
        execution_provenance=EXECUTION_PROVENANCE,
        observed_at=NOW,
    )
    missing_failure = dict(failed)
    missing_failure["failure"] = None
    errors = list(Draft202012Validator(_schema()).iter_errors(missing_failure))
    assert errors

    passed = _run(_R2())["receipt"]
    partial = dict(passed)
    partial["steps"] = {"completed_steps": []}
    errors = list(Draft202012Validator(_schema()).iter_errors(partial))
    assert errors

    failed_out_of_order = dict(failed)
    failed_out_of_order["steps"] = {"completed_steps": ["head_a"]}
    errors = list(Draft202012Validator(_schema()).iter_errors(failed_out_of_order))
    assert errors


def test_input_boundary_refuses_full_endpoint_nonfresh_namespace_and_longer_budget_before_calls() -> None:
    for changes in (
        {"endpoint_host": "https://example.r2.cloudflarestorage.com"},
        {"key": "capital_structure/share_counts/v2/current_head.json"},
        {"deadline_seconds": 90.001},
    ):
        client = _R2()
        arguments = {
            "client": client,
            "bucket": BUCKET,
            "key": KEY,
            "endpoint_host": HOST,
            "github_provenance": PROVENANCE,
            "execution_provenance": EXECUTION_PROVENANCE,
            "observed_at": NOW,
        }
        arguments.update(changes)
        with pytest.raises(conformance.R2CasConformanceError):
            conformance.run_conformance(**arguments)
        assert client.calls == []


def test_source_has_only_the_narrow_object_operations_and_no_hmac_or_publication_import() -> None:
    source_path = Path(conformance.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any("hmac" in name or "publication" in name for name in imports)
    source = source_path.read_text(encoding="utf-8")
    assert "list_object" not in source and "delete_object" not in source
    assert conformance.MAX_CONFORMANCE_OBJECT_BYTES == 4096
