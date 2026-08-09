"""Adversarial tests for the manual institutional 13F R2 provider proof."""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from engine.research_vault.r2_store import LocalStore, VersionedBytes
from scripts import institutional_13f_r2_conformance as proof


ROOT = Path(__file__).resolve().parents[1]
NONCE = "0123456789abcdef0123456789abcdef"
NOW = "2026-08-08T20:00:00Z"
# Redaction canary: must never appear raw in a receipt (only its sha256).
# Deliberately NOT the production bucket name — the org slug
# mastermindx-market-intelligence/macro sits in provenance by design, so a
# bare-"mastermindx" probe would collide with legitimate receipt content.
BUCKET = "mastermindx-redaction-canary"
PROVENANCE = {
    "repository": "mastermindx-market-intelligence/macro",
    "workflow_ref": (
        "mastermindx-market-intelligence/macro/.github/workflows/"
        "smart-money-13f-r2-conformance.yml@refs/heads/main"
    ),
    "run_id": "123456789",
    "run_attempt": 2,
    "commit_sha": "a" * 40,
    "event_name": "workflow_dispatch",
    "actor": "operator-test",
}


def _run(store):
    return proof.run_conformance(
        store,
        run_nonce=NONCE,
        observed_at=NOW,
        provenance=PROVENANCE,
        bucket_name=BUCKET,
    )


class _RecordingStore:
    """Strict-store proxy that fails if the witness invokes broad capabilities."""

    def __init__(self, inner: LocalStore) -> None:
        self.inner = inner
        self.conditional_calls: list[tuple[str, bytes, str | None, str]] = []
        self.versioned_reads: list[tuple[str, int, VersionedBytes]] = []

    def get_bytes(self, key):
        raise AssertionError("fail-open get_bytes is outside the proof")

    def get_bytes_strict(self, key):
        raise AssertionError("unbounded get_bytes_strict is outside the proof")

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        raise AssertionError("non-versioned bounded reads are outside the proof")

    def get_bytes_strict_bounded_versioned(self, key, maximum_bytes):
        result = self.inner.get_bytes_strict_bounded_versioned(key, maximum_bytes)
        self.versioned_reads.append((key, maximum_bytes, result))
        return result

    def validate_strict_conditional_write_capability(self):
        return self.inner.validate_strict_conditional_write_capability()

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        self.conditional_calls.append((key, data, expected_version, content_type))
        return self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        raise AssertionError("unconditional writes are outside the proof")

    def list_prefix(self, prefix):
        raise AssertionError("listing is outside the proof")

    def exists(self, key):
        raise AssertionError("fail-open existence checks are outside the proof")

    def upload_time(self, key):
        raise AssertionError("upload-time discovery is outside the proof")


class _BrokenStore(_RecordingStore):
    def __init__(
        self,
        inner: LocalStore,
        *,
        reject_successor: bool = False,
        accept_stale: bool = False,
        malformed_first_read: bool = False,
        capability_error: bool = False,
    ) -> None:
        super().__init__(inner)
        self.reject_successor = reject_successor
        self.accept_stale = accept_stale
        self.malformed_first_read = malformed_first_read
        self.capability_error = capability_error

    def validate_strict_conditional_write_capability(self):
        if self.capability_error:
            raise RuntimeError("SDK model lacks conditional headers")
        return super().validate_strict_conditional_write_capability()

    def get_bytes_strict_bounded_versioned(self, key, maximum_bytes):
        result = super().get_bytes_strict_bounded_versioned(key, maximum_bytes)
        if self.malformed_first_read and len(self.versioned_reads) == 1:
            return VersionedBytes(data=b"wrong", version=result.version)
        return result

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        call_number = len(self.conditional_calls) + 1
        if self.reject_successor and call_number == 3:
            self.conditional_calls.append((key, data, expected_version, content_type))
            return False
        if self.accept_stale and call_number == 4:
            self.conditional_calls.append((key, data, expected_version, content_type))
            current = self.inner.get_bytes_strict_bounded_versioned(
                key, proof.MAX_CONFORMANCE_OBJECT_BYTES
            )
            return self.inner.put_bytes_strict_conditional(
                key,
                data,
                expected_version=current.version,
                content_type=content_type,
            )
        return super().put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )


def test_happy_path_proves_exact_protocol_and_emits_canonical_redacted_receipt(
    tmp_path: Path,
) -> None:
    store = _RecordingStore(LocalStore(tmp_path / "store"))
    receipt = _run(store)

    proof.validate_receipt(receipt)
    encoded = proof.canonical_receipt_bytes(receipt)
    assert encoded.endswith(b"\n") and b"\n" not in encoded[:-1]
    assert receipt["status"] == "passed"
    assert receipt["manual_only"] is True
    assert receipt["nonclaims"]["not_a_concurrent_linearizability_proof"] is True
    assert receipt["evidence"]["no_list_or_delete_performed"] is True
    assert BUCKET not in encoded.decode("utf-8")
    assert proof.conformance_key(
        run_id=PROVENANCE["run_id"],
        run_attempt=PROVENANCE["run_attempt"],
        run_nonce=NONCE,
    ) not in encoded.decode("utf-8")

    assert len(store.conditional_calls) == 4
    assert len(store.versioned_reads) == 4
    version_a = store.versioned_reads[0][2].version
    version_b = store.versioned_reads[2][2].version
    assert [item[2] for item in store.conditional_calls] == [
        None,
        None,
        version_a,
        version_a,
    ]
    assert version_b != version_a
    assert all(item[3] == "application/json" for item in store.conditional_calls)
    assert all(
        maximum == proof.MAX_CONFORMANCE_OBJECT_BYTES
        for _, maximum, _ in store.versioned_reads
    )
    assert store.versioned_reads[-1][2] == store.versioned_reads[2][2]


def test_run_unique_key_collision_refuses_to_overwrite_existing_witness(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    key = proof.conformance_key(
        run_id=PROVENANCE["run_id"],
        run_attempt=PROVENANCE["run_attempt"],
        run_nonce=NONCE,
    )
    assert store.put_bytes_strict_conditional(
        key,
        b"preexisting",
        expected_version=None,
        content_type="application/json",
    )

    with pytest.raises(proof.Institutional13FR2ConformanceError, match="already exists"):
        _run(store)
    assert store.get_bytes_strict(key) == b"preexisting"


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"reject_successor": True}, "exact predecessor CAS was rejected"),
        ({"accept_stale": True}, "stale predecessor CAS was accepted"),
        ({"malformed_first_read": True}, "exact readback failed"),
        ({"capability_error": True}, "capability validation failed"),
    ],
)
def test_incomplete_or_broken_conditional_semantics_never_pass(
    tmp_path: Path,
    options: dict,
    message: str,
) -> None:
    store = _BrokenStore(LocalStore(tmp_path / "store"), **options)
    with pytest.raises(proof.Institutional13FR2ConformanceError, match=message):
        _run(store)


def test_receipt_identity_and_provenance_are_fail_closed(tmp_path: Path) -> None:
    receipt = _run(LocalStore(tmp_path / "store"))
    tampered = deepcopy(receipt)
    tampered["evidence"]["stale_predecessor_rejected"] = False
    with pytest.raises(proof.Institutional13FR2ConformanceError):
        proof.validate_receipt(tampered)

    bad_ref = dict(PROVENANCE)
    bad_ref["workflow_ref"] = bad_ref["workflow_ref"].replace("main", "feature")
    with pytest.raises(proof.Institutional13FR2ConformanceError, match="main-branch"):
        proof.run_conformance(
            LocalStore(tmp_path / "other-store"),
            run_nonce=NONCE,
            observed_at=NOW,
            provenance=bad_ref,
            bucket_name=BUCKET,
        )


def test_cli_uses_dedicated_store_factory_and_writes_one_local_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalStore(tmp_path / "store")
    calls: list[tuple[tuple, dict]] = []

    def build_store(*args, **kwargs):
        calls.append((args, kwargs))
        return store

    monkeypatch.setattr(proof, "build_institutional_13f_store", build_store)
    monkeypatch.setattr(proof.secrets, "token_hex", lambda count: NONCE)
    environment = {
        "GITHUB_REPOSITORY": PROVENANCE["repository"],
        "GITHUB_WORKFLOW_REF": PROVENANCE["workflow_ref"],
        "GITHUB_RUN_ID": PROVENANCE["run_id"],
        "GITHUB_RUN_ATTEMPT": str(PROVENANCE["run_attempt"]),
        "GITHUB_SHA": PROVENANCE["commit_sha"],
        "GITHUB_EVENT_NAME": PROVENANCE["event_name"],
        "GITHUB_ACTOR": PROVENANCE["actor"],
        "INSTITUTIONAL_13F_R2_BUCKET": BUCKET,
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    output = tmp_path / "artifact" / proof.RECEIPT_FILENAME

    assert proof.main(["--output", str(output)]) == 0

    assert calls == [((), {})]
    payload = output.read_bytes()
    receipt = json.loads(payload.decode("utf-8"))
    proof.validate_receipt(receipt)
    assert payload == proof.canonical_receipt_bytes(receipt)
    assert len(store.list_prefix(proof.CONFORMANCE_KEY_PREFIX)) == 1


def test_workflow_is_manual_read_only_noncancelling_and_maps_existing_secrets() -> None:
    path = ROOT / ".github/workflows/smart-money-13f-r2-conformance.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    job = workflow["jobs"]["provider-proof"]
    assert "refs/heads/main" in job["if"]
    run_step = next(
        item for item in job["steps"] if item.get("name") == "run retained-object conditional provider proof"
    )
    assert run_step["env"] == {
        "INSTITUTIONAL_13F_R2_ENDPOINT": "${{ secrets.R2_ENDPOINT }}",
        "INSTITUTIONAL_13F_R2_ACCESS_KEY_ID": "${{ secrets.R2_ACCESS_KEY_ID }}",
        "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY": "${{ secrets.R2_SECRET_ACCESS_KEY }}",
        "INSTITUTIONAL_13F_R2_BUCKET": "${{ secrets.R2_BUCKET }}",
    }
    assert "schedule:" not in text and "push:" not in text and "pull_request:" not in text
    assert "git push" not in text and "delete_object" not in text and "list_prefix" not in text


def test_script_has_no_r2_list_or_delete_capability() -> None:
    path = ROOT / "scripts/institutional_13f_r2_conformance.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert attributes.isdisjoint(
        {"delete_object", "delete_objects", "list_objects", "list_objects_v2", "list_prefix"}
    )
