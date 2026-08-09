from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from botocore.exceptions import ClientError

from engine.capital_structure import share_count_r2_concurrency as core


def _client_error(code: str, status: int, *, retry_attempts: int = 0) -> ClientError:
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status, "RetryAttempts": retry_attempts}},
        "PutObject",
    )


class _Body:
    def __init__(self, payload: bytes) -> None:
        self.payload, self.offset, self.closed = payload, 0, False

    def read(self, amount: int) -> bytes:
        chunk = self.payload[self.offset:self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class _BrokenCloseBody(_Body):
    def close(self) -> None:
        raise OSError("synthetic close failure")


class _NonBytesBody(_Body):
    def read(self, amount: int) -> str:
        return "not-bytes"


class _Verifier:
    def __init__(self, *, stale: str = "conflict", readback: str = "pass") -> None:
        self.objects: dict[str, tuple[bytes, str, dict[str, str]]] = {}
        self.serial = 0
        self.stale, self.readback = stale, readback
        self.stale_evidence = core.VerifierPutAttempt(1, 1, (1,), 0, True, None)

    def _etag(self) -> str:
        self.serial += 1
        return f'"etag-{self.serial}"'

    def write(self, key: str, body: bytes, *, preserve_etag: bool = False) -> None:
        etag = self.objects[key][1] if preserve_etag and key in self.objects else self._etag()
        self.objects[key] = (body, etag, {"sha256": sha256(body).hexdigest()})

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key not in self.objects:
            raise _client_error("NoSuchKey", 404)
        body, etag, metadata = self.objects[key]
        if self.readback == "bad_head_metadata":
            metadata = {"sha256": "0" * 64}
        return {"ResponseMetadata": {"HTTPStatusCode": 200}, "ContentLength": len(body), "ContentType": "application/json", "ETag": etag, "Metadata": metadata}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        body, etag, metadata = self.objects[kwargs["Key"]]
        assert kwargs["IfMatch"] == etag
        streamed = b"x" * len(body) if self.readback == "mismatch" else body
        if self.readback == "extra_bytes":
            streamed += b"x"
        if self.readback == "close":
            stream: _Body = _BrokenCloseBody(streamed)
        elif self.readback == "non_bytes":
            stream = _NonBytesBody(streamed)
        else:
            stream = _Body(streamed)
        content_range = "bytes 1-2/3" if self.readback == "bad_range" else f"bytes 0-{len(body) - 1}/{len(body)}"
        if self.readback == "bad_get_metadata":
            metadata = {"sha256": "0" * 64}
        return {"ResponseMetadata": {"HTTPStatusCode": 206}, "ContentLength": len(body), "ContentType": "application/json", "ETag": etag, "ContentRange": content_range, "Metadata": metadata, "Body": stream}

    def reset_put_attempt_evidence(self) -> None:
        self.stale_evidence = core.VerifierPutAttempt(0, 0, (), None, False, None)

    def take_put_attempt_evidence(self) -> core.VerifierPutAttempt:
        return self.stale_evidence

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.stale_evidence = core.VerifierPutAttempt(1, 1, (1,), 0, True, None)
        key, body = kwargs["Key"], kwargs["Body"]
        if self.stale == "success":
            self.write(key, body)
            return {"ResponseMetadata": {"HTTPStatusCode": 200, "RetryAttempts": 0}}
        if self.stale == "lookalike":
            class Lookalike(ClientError):
                pass
            raise Lookalike({"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412, "RetryAttempts": 0}}, "PutObject")
        if self.stale == "wrong409":
            raise _client_error("ConditionalRequestConflict", 409)
        if self.stale == "rewrite":
            self.write(key, body)
            raise _client_error("PreconditionFailed", 412)
        if self.stale == "retag":
            current_body = self.objects[key][0]
            self.write(key, current_body)
            raise _client_error("PreconditionFailed", 412)
        raise _client_error("PreconditionFailed", 412)


class _Workers:
    def __init__(self, verifier: _Verifier, *, mode: str = "pass") -> None:
        self.verifier, self.mode = verifier, mode
        self.identities = (
            core.WorkerIdentity("left", 101, "1" * 64, "2" * 64, "standard", 1, True, True),
            core.WorkerIdentity("right", 202, "3" * 64, "4" * 64, "standard", 1, True, True),
        )

    def race(self, **kwargs: Any) -> tuple[core.WorkerAttempt, core.WorkerAttempt]:
        round_id, phase, key = kwargs["round_id"], kwargs["phase"], kwargs["key"]
        left, right = kwargs["left_body"], kwargs["right_body"]
        if self.mode == "both_success":
            self.verifier.write(key, right)
        elif self.mode == "loser_final":
            self.verifier.write(key, right)
        elif self.mode == "unchanged_etag" and phase == "successor":
            self.verifier.write(key, left, preserve_etag=True)
        else:
            self.verifier.write(key, left)
        start = round_id * 10_000 + (0 if phase == "genesis" else 4_000)
        left_attempt = core.WorkerAttempt("left", 101, 1, 1, (1,), start, start + 600, 200, None, None, 0, False, None, "success")
        right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 100, start + 700, None, "PreconditionFailed", 412, 0, True, None, "conflict")
        if self.mode == "sequential":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 601, start + 700, None, "PreconditionFailed", 412, 0, True, None, "conflict")
        elif self.mode == "hidden_retry":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1, 2), start + 100, start + 700, None, "PreconditionFailed", 412, 1, True, None, "conflict")
        elif self.mode == "wrong409":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 100, start + 700, None, "ConditionalRequestConflict", 409, 0, True, None, "error")
        elif self.mode == "untyped412":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 100, start + 700, None, "PreconditionFailed", 412, 0, False, None, "error")
        elif self.mode == "unexpected201":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 100, start + 700, 201, None, None, 0, False, None, "unknown")
        elif self.mode == "both_success":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 100, start + 700, 200, None, None, 0, False, None, "success")
        elif self.mode == "two_refusals":
            left_attempt = core.WorkerAttempt("left", 101, 1, 1, (1,), start, start + 600, None, "PreconditionFailed", 412, 0, True, None, "conflict")
        elif self.mode == "lost_response":
            right_attempt = core.WorkerAttempt("right", 202, 1, 1, (1,), start + 100, start + 700, None, None, None, None, False, None, "transport")
        elif self.mode == "duplicate_put":
            right_attempt = core.WorkerAttempt("right", 202, 2, 2, (1,), start + 100, start + 700, None, "PreconditionFailed", 412, 0, True, None, "conflict")
        return left_attempt, right_attempt


def _provenance() -> tuple[dict[str, Any], dict[str, str]]:
    return (
        {"repository": "mastermindx-market-intelligence/macro", "workflow_ref": "mastermindx-market-intelligence/macro/.github/workflows/capital-share-count-r2-concurrency.yml@refs/heads/main", "run_id": "12", "run_attempt": 1, "commit_sha": "a" * 40, "event_name": "workflow_dispatch", "actor": "reviewer"},
        {"source_archive_sha256": "b" * 64, "dependency_lock_sha256": "c" * 64, "dependency_lock_name": core.DEPENDENCY_LOCK_NAME},
    )


def _run(*, worker_mode: str = "pass", stale: str = "conflict", readback: str = "pass", monotonic: Any | None = None) -> dict[str, Any]:
    verifier = _Verifier(stale=stale, readback=readback)
    github, execution = _provenance()
    return core.run_concurrency_witness(
        workers=_Workers(verifier, mode=worker_mode), verifier=verifier,
        bucket="concurrency-witness", endpoint_host="d" * 32 + ".r2.cloudflarestorage.com",
        rounds=core.build_precommitted_plan(run_nonce="e" * 32), github_provenance=github,
        execution_provenance=execution, observed_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        **({"monotonic": monotonic} if monotonic is not None else {}),
    )


def test_eight_round_witness_is_closed_redacted_and_canonical() -> None:
    result = _run()
    assert result["status"] == "passed"
    receipt = result["receipt"]
    core.validate_concurrency_receipt(receipt)
    assert len(receipt["rounds"]) == 8
    assert all(round_item["genesis"]["worker_attempts"]["left"]["http_status"] == 200 for round_item in receipt["rounds"])
    assert all(round_item["genesis"]["worker_attempts"]["right"]["error_code"] == "PreconditionFailed" for round_item in receipt["rounds"])
    encoded = json.dumps(receipt, sort_keys=True)
    assert "capital_structure/share_counts/concurrency-witness/" not in encoded
    assert "e" * 32 not in encoded
    assert '"etag-' not in encoded
    assert core.canonical_receipt_bytes(receipt).endswith(b"\n")
    schema = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "capital_structure_share_count_r2_concurrency_receipt.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(receipt)


@pytest.mark.parametrize(
    ("worker_mode", "stale", "status", "stage", "category"),
    [
        ("sequential", "conflict", "inconclusive", "genesis_race", "sequential_transport_spans"),
        ("hidden_retry", "conflict", "inconclusive", "genesis_race", "missing_or_duplicate_attempt_evidence"),
        ("wrong409", "conflict", "inconclusive", "genesis_race", "wrong_conflict_response"),
        ("untyped412", "conflict", "inconclusive", "genesis_race", "wrong_conflict_response"),
        ("unexpected201", "conflict", "inconclusive", "genesis_race", "wrong_conflict_response"),
        ("both_success", "conflict", "failed", "genesis_race", "both_writers_succeeded"),
        ("pass", "success", "failed", "stale_put", "stale_write_succeeded"),
        ("pass", "wrong409", "inconclusive", "stale_put", "wrong_conflict_response"),
        ("pass", "lookalike", "inconclusive", "stale_put", "wrong_conflict_response"),
        ("two_refusals", "conflict", "inconclusive", "genesis_race", "wrong_conflict_response"),
        ("lost_response", "conflict", "inconclusive", "genesis_race", "lost_or_ambiguous_response"),
        ("duplicate_put", "conflict", "inconclusive", "genesis_race", "missing_or_duplicate_attempt_evidence"),
        ("loser_final", "conflict", "inconclusive", "genesis_verify", "malformed_response"),
        ("unchanged_etag", "conflict", "inconclusive", "successor_verify", "etag_not_new"),
        ("pass", "rewrite", "inconclusive", "stale_verify", "malformed_response"),
        ("pass", "retag", "inconclusive", "stale_verify", "post_hoc_rewrite"),
    ],
)
def test_hostile_transport_outcomes_are_fail_closed(worker_mode: str, stale: str, status: str, stage: str, category: str) -> None:
    with pytest.raises(core.R2ConcurrencyObservedFailure) as caught:
        _run(worker_mode=worker_mode, stale=stale)
    assert (caught.value.status, caught.value.failure_stage, caught.value.failure_category) == (status, stage, category)


def test_plan_cannot_swap_candidate_or_nonce_after_precommit() -> None:
    plan = list(core.build_precommitted_plan(run_nonce="f" * 32))
    plan[0] = core.RoundPlan(plan[0].round_id, plan[0].run_nonce, plan[0].key, plan[0].genesis_right, plan[0].genesis_left, plan[0].successor_left, plan[0].successor_right)
    with pytest.raises(core.R2ConcurrencyError):
        core.plan_commitment_sha256(plan)


def test_worker_identity_requires_both_instrumentation_hooks() -> None:
    verifier = _Verifier()
    workers = _Workers(verifier)
    workers.identities = (core.WorkerIdentity("left", 101, "1" * 64, "2" * 64, "standard", 1, True, False), workers.identities[1])
    github, execution = _provenance()
    with pytest.raises(core.R2ConcurrencyError):
        core.run_concurrency_witness(workers=workers, verifier=verifier, bucket="concurrency-witness", endpoint_host="d" * 32 + ".r2.cloudflarestorage.com", rounds=core.build_precommitted_plan(run_nonce="e" * 32), github_provenance=github, execution_provenance=execution, observed_at=datetime(2026, 8, 3, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    ("readback", "category"),
    [
        ("mismatch", "readback_mismatch"),
        ("extra_bytes", "readback_mismatch"),
        ("close", "close_failure"),
        ("non_bytes", "malformed_response"),
        ("bad_range", "malformed_response"),
        ("bad_head_metadata", "malformed_response"),
        ("bad_get_metadata", "malformed_response"),
    ],
)
def test_readback_and_stream_close_are_stage_specific(readback: str, category: str) -> None:
    with pytest.raises(core.R2ConcurrencyObservedFailure) as caught:
        _run(readback=readback)
    assert (caught.value.failure_stage, caught.value.failure_category) == ("genesis_verify", category)


def test_receipt_validator_detects_tampered_per_writer_response_evidence() -> None:
    receipt = _run()["receipt"]
    receipt["rounds"][0]["genesis"]["worker_attempts"]["left"]["http_status"] = 201
    with pytest.raises(core.R2ConcurrencyError):
        core.validate_concurrency_receipt(receipt)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda receipt: receipt["rounds"][0]["genesis"].__setitem__("verified_body_sha256", "f" * 64),
        lambda receipt: receipt["rounds"][0]["genesis"].__setitem__("loser_candidate_sha256", receipt["rounds"][0]["genesis"]["winner_candidate_sha256"]),
        lambda receipt: receipt["rounds"][0]["successor"].__setitem__("e0_etag_sha256", "f" * 64),
        lambda receipt: receipt["rounds"][0]["successor"].__setitem__("commitment_sha256", "f" * 64),
        lambda receipt: receipt["rounds"][0]["stale"].__setitem__("final_etag_sha256", "f" * 64),
        lambda receipt: receipt["rounds"][0]["stale"].__setitem__("final_body_sha256", "f" * 64),
        lambda receipt: receipt["rounds"][1].__setitem__("key_sha256", receipt["rounds"][0]["key_sha256"]),
        lambda receipt: receipt.__setitem__("plan_commitment_sha256", "f" * 64),
    ],
)
def test_rehashed_receipt_cannot_detach_semantic_chain(mutation: Any) -> None:
    receipt = deepcopy(_run()["receipt"])
    mutation(receipt)
    receipt["receipt_id"] = core._receipt_id(receipt)
    with pytest.raises(core.R2ConcurrencyError):
        core.validate_concurrency_receipt(receipt)


@pytest.mark.parametrize("field", ["process_id", "session_instance_sha256", "client_instance_sha256"])
def test_workers_must_not_share_process_session_or_client(field: str) -> None:
    verifier = _Verifier()
    workers = _Workers(verifier)
    left, right = workers.identities
    workers.identities = (left, core.WorkerIdentity("right", getattr(left, field) if field == "process_id" else right.process_id, getattr(left, field) if field == "session_instance_sha256" else right.session_instance_sha256, getattr(left, field) if field == "client_instance_sha256" else right.client_instance_sha256, "standard", 1, True, True))
    github, execution = _provenance()
    with pytest.raises(core.R2ConcurrencyError):
        core.run_concurrency_witness(workers=workers, verifier=verifier, bucket="concurrency-witness", endpoint_host="d" * 32 + ".r2.cloudflarestorage.com", rounds=core.build_precommitted_plan(run_nonce="e" * 32), github_provenance=github, execution_provenance=execution, observed_at=datetime(2026, 8, 3, tzinfo=timezone.utc))


def test_logical_deadline_never_becomes_a_passing_receipt() -> None:
    ticks = iter((0.0, 241.0))
    with pytest.raises(core.R2ConcurrencyObservedFailure) as caught:
        _run(monotonic=lambda: next(ticks))
    assert caught.value.status == "inconclusive"


@pytest.mark.parametrize("code", ["404", "NotFound", "NoSuchKey"])
def test_absence_preflight_accepts_only_closed_botocore_404_family(code: str) -> None:
    class AbsenceVerifier:
        def head_object(self, **_kwargs: Any) -> None:
            raise _client_error(code, 404)

    core._expect_typed_absence(
        deadline=core._Deadline(2.0, lambda: 1.0),
        verifier=AbsenceVerifier(),
        bucket="concurrency-witness",
        key=core.build_precommitted_plan(run_nonce="e" * 32)[0].key,
    )


@pytest.mark.parametrize(
    "error",
    [
        _client_error("ConditionalRequestConflict", 409),
        _client_error("NoSuchKey", 404, retry_attempts=1),
        RuntimeError("404 NoSuchKey"),
    ],
)
def test_absence_preflight_rejects_wrong_retry_status_and_untyped_lookalike(error: BaseException) -> None:
    class AbsenceVerifier:
        def head_object(self, **_kwargs: Any) -> None:
            raise error

    with pytest.raises(core.R2ConcurrencyError):
        core._expect_typed_absence(
            deadline=core._Deadline(2.0, lambda: 1.0),
            verifier=AbsenceVerifier(),
            bucket="concurrency-witness",
            key=core.build_precommitted_plan(run_nonce="e" * 32)[0].key,
        )


def test_failure_receipt_is_schema_valid_closed_and_self_hashed() -> None:
    github, execution = _provenance()
    receipt = core.build_failure_receipt(
        status="inconclusive",
        failure_stage="genesis_race",
        failure_category="lost_or_ambiguous_response",
        bucket="concurrency-witness",
        endpoint_host="d" * 32 + ".r2.cloudflarestorage.com",
        plan_commitment="a" * 64,
        github_provenance=github,
        execution_provenance=execution,
        observed_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        deadline_seconds=240,
        completed_rounds=(1, 2),
    )
    core.validate_concurrency_receipt(receipt)
    schema = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "capital_structure_share_count_r2_concurrency_receipt.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(receipt)
    receipt["rounds"]["completed_rounds"] = [1, 3]
    with pytest.raises(core.R2ConcurrencyError):
        core.validate_concurrency_receipt(receipt)
