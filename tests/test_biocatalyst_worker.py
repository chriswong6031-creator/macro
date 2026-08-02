"""Hermetic regression tests for the dark-by-default BioCatalyst B1 worker."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Callable

import fcntl
import pytest

from engine.biocatalyst.publication import PublicationError, PublicGenerationPublisher
from engine.biocatalyst.storage import (
    DedicatedR2Config,
    StorageError,
    mirror_bytes_verified,
    mirror_tree_verified,
)
from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    ctgov_query_manifest_sha256,
    receipt_payloads_sha256,
)
from collectors.biocatalyst.clinicaltrials_v2 import current_b1_code_version
import scripts.biocatalyst_worker as worker


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUN = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
FIXTURE_RECEIPT = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "source_page_receipt.v1.valid.json"
FIXTURE_RAW = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "source_page_response.after.raw.json"
FIXTURE_SNAPSHOT = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "trial_source_snapshot.after.v1.valid.json"
NOW = datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc)


class MemoryStore:
    """Conditional-create fake; no real credentials or boto3 required."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_attempts: list[str] = []
        self.fail_create = False

    def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
        self.objects[key] = data
        return True

    def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
        self.put_attempts.append(key)
        if self.fail_create or key in self.objects:
            return False
        self.objects[key] = data
        return True


@dataclass
class FakeCollectorFactory:
    source_timestamp: str = "2026-08-01T09:00:00"
    watermark_after: str = "2026-08-01T15:00:05Z"
    run_id_override: str | None = None
    run_mutator: Callable[[dict], None] | None = None
    calls: list[dict] | None = None

    def __post_init__(self) -> None:
        self.calls = [] if self.calls is None else self.calls

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        outer = self

        class FakeCollector:
            def collect(self, *, watermark_before: str | None = None):
                run = json.loads(FIXTURE_RUN.read_text(encoding="utf-8"))
                receipt = json.loads(FIXTURE_RECEIPT.read_text(encoding="utf-8"))
                snapshot = json.loads(FIXTURE_SNAPSHOT.read_text(encoding="utf-8"))
                raw_payload = json.loads(FIXTURE_RAW.read_text(encoding="utf-8"))
                raw_payload["totalCount"] = len(raw_payload["studies"])
                raw_page = canonical_json_bytes(raw_payload)
                raw_digest = sha256(raw_page).hexdigest()
                source_study = raw_payload["studies"][0]
                watermark = datetime.fromisoformat(outer.watermark_after.replace("Z", "+00:00"))
                started = watermark - timedelta(seconds=5)
                finished = watermark - timedelta(seconds=1)
                started_at = started.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
                stamp = started_at.replace("-", "").replace(":", "").replace(".", "")
                run_id = f"ctgov_run_{stamp}_{'x' * 12}"
                receipt_id = f"ctgov_receipt_{run_id.removeprefix('ctgov_run_')}_0"
                run["started_at"] = started_at
                run["finished_at"] = finished.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
                run["transaction_from"] = outer.watermark_after
                run["watermark_before"] = watermark_before
                run["watermark_after"] = outer.watermark_after
                run["source_dataset_timestamp_before_raw"] = outer.source_timestamp
                run["source_dataset_timestamp_after_raw"] = outer.source_timestamp
                run["source_api_version"] = "2.0.5"
                run["source_api_version_after"] = "2.0.5"
                manifest = run["query_manifest"]
                manifest["api_root"] = "https://clinicaltrials.gov/api/v2"
                manifest["request_path"] = "/studies"
                manifest["base_query_params"] = {
                    "query.id": "NCT00000001",
                    "format": "json",
                    "pageSize": str(manifest["page_size"]),
                    "countTotal": "true",
                }
                manifest["query_sha256"] = ctgov_query_manifest_sha256(manifest)
                run_id = f"ctgov_run_{stamp}_{manifest['query_sha256'][:12]}"
                if outer.run_id_override is not None and outer.run_id_override != run_id:
                    raise AssertionError("run_id_override must match the canonical B1 identity")
                run["run_id"] = run_id
                receipt_id = f"ctgov_receipt_{run_id.removeprefix('ctgov_run_')}_0"
                source_hash = canonical_json_sha256(source_study)
                source_ref = f"src:ctgov:NCT00000001:sha256:{source_hash}"
                run["published_source_record_refs"] = [source_ref]
                receipt["receipt_id"] = receipt_id
                receipt["run_id"] = run_id
                receipt["receipt_object_key"] = (
                    f"biocatalyst/receipts/clinicaltrials/2026/08/{run_id}/0.json"
                )
                receipt["request"]["query_sha256"] = manifest["query_sha256"]
                receipt["request"]["headers"] = {
                    "accept": "application/json",
                    "accept-encoding": "identity",
                    "user-agent": kwargs["user_agent"],
                }
                receipt_received_at = (started + timedelta(seconds=2)).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
                receipt["response"]["received_at"] = receipt_received_at
                receipt["transaction_from"] = receipt_received_at
                receipt["response"]["exact_response_sha256"] = raw_digest
                receipt["response"]["byte_count"] = len(raw_page)
                receipt["response"]["study_count"] = len(raw_payload["studies"])
                receipt["response"]["headers"]["content-length"] = str(len(raw_page))
                receipt["response"]["raw_response_object_key"] = (
                    "biocatalyst/raw/clinicaltrials/v2/pages/"
                    f"2026/08/{run_id}/0/{raw_digest}.json"
                )
                receipt["source_dataset_timestamp_raw"] = outer.source_timestamp
                receipt["source_api_version"] = "2.0.5"
                run["receipt_refs"] = [receipt_id]
                run["terminal_receipt_ref"] = receipt_id
                run["receipt_payloads_sha256"] = receipt_payloads_sha256([receipt])
                run["code_version"] = current_b1_code_version()
                snapshot_id = (
                    f"ctgov_snapshot_NCT00000001_"
                    f"{run_id.removeprefix('ctgov_run_')}_{source_hash}"
                )
                snapshot.update(
                    {
                        "source_snapshot_id": snapshot_id,
                        "source_record_ref": source_ref,
                        "run_ref": run_id,
                        "page_receipt_ref": receipt_id,
                        "raw_object_key": (
                            f"biocatalyst/raw/clinicaltrials/v2/NCT00000001/{source_hash}.json"
                        ),
                        "exact_response_sha256": raw_digest,
                        "canonical_content_sha256": source_hash,
                        "canonical_study": source_study,
                        "source_dataset_timestamp_raw": outer.source_timestamp,
                        "retrieved_at": receipt["response"]["received_at"],
                        "first_seen_at": receipt["response"]["received_at"],
                        "transaction_from": run["finished_at"],
                    }
                )
                if outer.run_mutator is not None:
                    outer.run_mutator(run)

                state = {
                    "contract_id": "biocatalyst_trial_source_state.v1",
                    "schema_version": "1.0.0",
                    "nct_id": "NCT00000001",
                    "source_snapshot_id": snapshot["source_snapshot_id"],
                    "source_record_ref": source_ref,
                    "canonical_content_sha256": source_hash,
                    "source_uri": "https://clinicaltrials.gov/study/NCT00000001",
                    "source_dataset_timestamp_raw": outer.source_timestamp,
                    "source_last_update_posted_at": snapshot["source_last_update_posted_at"],
                    "source_published_at": snapshot["source_published_at"],
                    "retrieved_at": snapshot["retrieved_at"],
                    "coverage_class": "current_only",
                    "license_class": "us_government_source_facts",
                    "source_attribution": "ClinicalTrials.gov",
                    "modification_disclosure": "BioCatalyst parsed and normalized this source-state reference.",
                }
                public_entry = {
                    "nct_id": "NCT00000001",
                    "source_snapshot_id": state["source_snapshot_id"],
                    "source_record_ref": source_ref,
                    "public_state_sha256": canonical_json_sha256(state),
                }
                public_manifest = {
                    "manifest_version": "biocatalyst_publication.v1",
                    "hash_scope": "canonical_manifest_excluding_manifest_sha256",
                    "run_id": run_id,
                    "query_sha256": run["query_manifest"]["query_sha256"],
                    "source_dataset_timestamp_raw": outer.source_timestamp,
                    "entries": [public_entry],
                }
                public_manifest["manifest_sha256"] = canonical_json_sha256(public_manifest)

                private_root = kwargs["private_root"]
                public_root = kwargs["public_root"]
                year, month = f"{started.year:04d}", f"{started.month:02d}"
                version_raw = canonical_json_bytes(
                    {"apiVersion": "2.0.5", "dataTimestamp": outer.source_timestamp}
                )

                def version_receipt(phase: str, received_at: datetime) -> dict:
                    digest = sha256(version_raw).hexdigest()
                    return {
                        "receipt_id": f"ctgov_version_receipt_{run_id.removeprefix('ctgov_run_')}_{phase}",
                        "run_id": run_id,
                        "source_id": "clinicaltrials_gov_v2",
                        "phase": phase,
                        "receipt_object_key": (
                            "biocatalyst/receipts/clinicaltrials/version/"
                            f"{year}/{month}/{run_id}/{phase}.json"
                        ),
                        "request": {
                            "method": "GET",
                            "path": "/version",
                            "headers": {
                                "accept": "application/json",
                                "accept-encoding": "identity",
                                "user-agent": kwargs["user_agent"],
                            },
                        },
                        "response": {
                            "status_code": 200,
                            "headers": {"content-type": "application/json", "content-length": str(len(version_raw))},
                            "exact_response_sha256": digest,
                            "raw_response_object_key": (
                                "biocatalyst/raw/clinicaltrials/v2/version/"
                                f"{year}/{month}/{run_id}/{phase}/{digest}.json"
                            ),
                            "byte_count": len(version_raw),
                            "received_at": received_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                        },
                        "source_dataset_timestamp_raw": outer.source_timestamp,
                        "source_api_version": "2.0.5",
                        "sanitization": {
                            "raw_pagination_tokens_stored_in_receipt": False,
                            "credentials_stored_in_receipt": False,
                            "rejected_header_names": ["authorization", "cookie", "proxy-authorization", "set-cookie", "x-api-key"],
                        },
                        "transaction_from": received_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                        "transaction_to": None,
                    }

                version_before = version_receipt("before", started + timedelta(seconds=1))
                version_after = version_receipt("after", finished)
                run["version_evidence"] = {
                    "hash_scope": "canonical_version_receipts_before_after",
                    "version_receipt_payloads_sha256": canonical_json_sha256([version_before, version_after]),
                    "before": version_before,
                    "after": version_after,
                }
                run_path = private_root / "biocatalyst" / "runs" / "clinicaltrials" / year / month / f"{run_id}.json"
                run_path.parent.mkdir(parents=True, exist_ok=True)
                run_path.write_bytes(canonical_json_bytes(run) + b"\n")
                raw_path = private_root / Path(*PurePosixPath(receipt["response"]["raw_response_object_key"]).parts)
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(raw_page)
                receipt_path = private_root / Path(*PurePosixPath(receipt["receipt_object_key"]).parts)
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                receipt_path.write_bytes(canonical_json_bytes(receipt) + b"\n")
                for version in (version_before, version_after):
                    version_raw_path = private_root / Path(*PurePosixPath(version["response"]["raw_response_object_key"]).parts)
                    version_raw_path.parent.mkdir(parents=True, exist_ok=True)
                    version_raw_path.write_bytes(version_raw)
                    version_receipt_path = private_root / Path(*PurePosixPath(version["receipt_object_key"]).parts)
                    version_receipt_path.parent.mkdir(parents=True, exist_ok=True)
                    version_receipt_path.write_bytes(canonical_json_bytes(version) + b"\n")
                canonical_path = private_root / Path(*PurePosixPath(snapshot["raw_object_key"]).parts)
                canonical_path.parent.mkdir(parents=True, exist_ok=True)
                canonical_path.write_bytes(canonical_json_bytes(source_study))
                snapshot_path = private_root / "biocatalyst" / "source_snapshots" / "clinicaltrials" / "NCT00000001" / f"{snapshot_id}.json"
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                snapshot_path.write_bytes(canonical_json_bytes(snapshot) + b"\n")
                generation = public_root / "generations" / run_id
                generation.mkdir(parents=True)
                (generation / "NCT00000001.json").write_bytes(canonical_json_bytes(state) + b"\n")
                (generation / "publication_manifest.json").write_bytes(canonical_json_bytes(public_manifest) + b"\n")
                return SimpleNamespace(run_id=run_id, run_path=run_path, generation_path=generation)

        return FakeCollector()


def wrap_collector_factory(
    base: Callable[..., object],
    mutate: Callable[[SimpleNamespace, dict], None],
) -> Callable[..., object]:
    """Mutate a completed fake attempt to exercise the outer worker boundary."""

    def factory(**kwargs):
        inner = base(**kwargs)

        class WrappedCollector:
            def collect(self, *, watermark_before: str | None = None):
                result = inner.collect(watermark_before=watermark_before)
                mutate(result, kwargs)
                return result

        return WrappedCollector()

    return factory


def config(tmp_path: Path) -> worker.WorkerConfig:
    return worker.WorkerConfig(
        state_root=tmp_path / "state",
        public_root=tmp_path / "public",
        nct_ids=("NCT00000001",),
        user_agent="MastermindX test contact@example.com",
        r2=DedicatedR2Config(
            endpoint="https://r2.example.test",
            bucket="biocatalyst-private",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
    )


def test_success_mirrors_every_private_artifact_then_promotes_one_sanitized_generation(tmp_path):
    cfg = config(tmp_path)
    collector = FakeCollectorFactory()
    store = MemoryStore()

    result = worker.run_once(
        cfg,
        collector_factory=collector,
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.exit_code == worker.EXIT_SUCCESS
    assert result.status == "success"
    assert collector.calls[0]["public_root"] != cfg.public_root
    assert collector.calls[0]["public_root"].parent.parent == cfg.state_root / "staging"

    publisher = PublicGenerationPublisher(cfg.public_root)
    committed = publisher.read_committed()
    assert committed is not None
    assert committed.generation_id == result.generation_id
    generation = cfg.public_root / "generations" / committed.generation_id
    assert {path.relative_to(generation).as_posix() for path in generation.rglob("*") if path.is_file()} == {
        "manifest.json",
        "source_manifest.json",
        "health.json",
        "trials/NCT00000001.json",
        "trial_snapshots/NCT00000001.json",
    }
    projection = publisher.read_trial_projection()
    assert projection is not None
    assert projection.generation == committed
    assert projection.trials[0]["facts"]["brief_title"]["value"] == "Synthetic Phase 2 Study"
    assert projection.trials[0]["authority"]["decision_authority"] is False
    assert any(key.startswith("biocatalyst/runs/") for key in store.objects)
    assert any(key.startswith("biocatalyst/raw/") for key in store.objects)
    assert f"biocatalyst/mirror_receipts/{committed.generation_id}.json" in store.objects
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in generation.rglob("*.json"))
    assert str(cfg.state_root) not in public_text
    assert "test-secret" not in public_text
    assert '"canonical_study"' not in public_text
    assert '"raw_object_key"' not in public_text


def test_disabled_and_misconfigured_environment_never_calls_collector_or_store(tmp_path, monkeypatch):
    calls = {"collector": 0, "store": 0}
    state_root = tmp_path / "macro-biocatalyst" / "state"
    public_root = tmp_path / "macro-biocatalyst" / "public"
    monkeypatch.setattr(worker, "_SERVICE_STATE_ROOT", state_root)
    monkeypatch.setattr(worker, "_SERVICE_PUBLIC_ROOT", public_root)
    base = {
        "BIOCATALYST_STATE_ROOT": str(state_root),
        "BIOCATALYST_PUBLIC_ROOT": str(public_root),
    }

    disabled = worker.run_from_environment(
        base,
        collector_factory=lambda **_: calls.__setitem__("collector", calls["collector"] + 1),
        store_factory=lambda _: calls.__setitem__("store", calls["store"] + 1),
        now_fn=lambda: NOW,
    )
    assert disabled.exit_code == worker.EXIT_SUCCESS
    assert disabled.status == "disabled"
    assert calls == {"collector": 0, "store": 0}

    invalid = worker.run_from_environment(
        {**base, "BIOCATALYST_ENABLED": "1"},
        collector_factory=lambda **_: calls.__setitem__("collector", calls["collector"] + 1),
        store_factory=lambda _: calls.__setitem__("store", calls["store"] + 1),
        now_fn=lambda: NOW,
    )
    assert invalid.exit_code == worker.EXIT_MISCONFIGURED
    assert invalid.status == "misconfigured"
    assert calls == {"collector": 0, "store": 0}
    health = json.loads((public_root / "health.json").read_text(encoding="utf-8"))
    assert health["state"] == "disabled"
    assert health["last_error_code"] == "BIOCATALYST_RUNTIME_PATH_INVALID" or health["last_error_code"] == "BIOCATALYST_CANARY_NCTS_INVALID"


def test_nonblocking_lock_coalesces_a_second_timer_tick(tmp_path):
    cfg = config(tmp_path)
    cfg.state_root.mkdir(parents=True)
    lock_path = cfg.state_root / "biocatalyst_worker.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = worker.run_once(
            cfg,
            collector_factory=lambda **_: pytest.fail("collector must not start while locked"),
            store_factory=lambda _: pytest.fail("store must not start while locked"),
            now_fn=lambda: NOW,
        )
    assert result == worker.WorkerResult(worker.EXIT_SUCCESS, "locked")


def test_private_store_failure_and_timestamp_regression_preserve_last_good_pointer(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = FakeCollectorFactory()
    first_result = worker.run_once(cfg, collector_factory=first, store_factory=lambda _: store, now_fn=lambda: NOW)
    assert first_result.status == "success"
    original = json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8"))

    broken_store = MemoryStore()
    broken_store.fail_create = True
    second = FakeCollectorFactory(watermark_after="2026-08-02T15:00:05Z")
    failed = worker.run_once(cfg, collector_factory=second, store_factory=lambda _: broken_store, now_fn=lambda: NOW)
    assert failed.status == "failed"
    assert json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8")) == original
    retained_health = json.loads((cfg.public_root / "health.json").read_text(encoding="utf-8"))
    assert retained_health["generation_id"] == first_result.generation_id
    assert retained_health["configured_nct_count"] == 1
    assert retained_health["observed_nct_count"] == 1

    regression = FakeCollectorFactory(
        source_timestamp="2026-07-31T09:00:00",
        watermark_after="2026-08-02T15:00:05Z",
    )
    regressed = worker.run_once(cfg, collector_factory=regression, store_factory=lambda _: store, now_fn=lambda: NOW)
    assert regressed.error_code == "SOURCE_TIMESTAMP_REGRESSION"
    assert json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8")) == original


def test_cross_host_conditional_create_never_overwrites_a_divergent_immutable_object():
    class RacingStore(MemoryStore):
        def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
            self.objects[key] = b"other writer"
            return False

    store = RacingStore()
    with pytest.raises(StorageError, match="IMMUTABLE_OBJECT_COLLISION"):
        mirror_bytes_verified(store, object_key="biocatalyst/raw/test.json", payload=b"candidate")
    assert store.objects["biocatalyst/raw/test.json"] == b"other writer"


def test_corrupt_or_extra_public_generation_is_never_trusted_as_a_watermark(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    collector = FakeCollectorFactory()
    assert worker.run_once(cfg, collector_factory=collector, store_factory=lambda _: store, now_fn=lambda: NOW).status == "success"
    current = json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8"))
    generation = cfg.public_root / "generations" / current["generation_id"]
    (generation / "extra.json").write_text("{}", encoding="utf-8")

    with pytest.raises(PublicationError):
        PublicGenerationPublisher(cfg.public_root).read_committed()
    calls_before = len(collector.calls)
    result = worker.run_once(cfg, collector_factory=collector, store_factory=lambda _: store, now_fn=lambda: NOW)
    assert result.error_code == "PUBLIC_GENERATION_INVALID"
    assert len(collector.calls) == calls_before


def test_post_replace_pointer_fault_rolls_back_and_cleanup_does_not_reclassify_commit(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = FakeCollectorFactory()
    assert worker.run_once(cfg, collector_factory=first, store_factory=lambda _: store, now_fn=lambda: NOW).status == "success"
    before = json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8"))

    def faulting_publisher(path: Path) -> PublicGenerationPublisher:
        return PublicGenerationPublisher(path, pointer_after_replace_hook=lambda _: (_ for _ in ()).throw(OSError("fsync fault")))

    second = FakeCollectorFactory(watermark_after="2026-08-02T15:00:05Z")
    result = worker.run_once(
        cfg,
        collector_factory=second,
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
        publisher_factory=faulting_publisher,
    )
    assert result.error_code == "POINTER_WRITE_FAILED"
    assert json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8")) == before


def _rehash_query_manifest(run: dict) -> None:
    run["query_manifest"]["query_sha256"] = ctgov_query_manifest_sha256(run["query_manifest"])


@pytest.mark.parametrize(
    ("mutate", "code"),
    (
        (
            lambda run: (
                run["query_manifest"].pop("api_root"),
                run["query_manifest"].pop("request_path"),
                run["query_manifest"].pop("base_query_params"),
                _rehash_query_manifest(run),
            ),
            "CTGOV_WIRE_BINDING_INVALID",
        ),
        (
            lambda run: (
                run["query_manifest"].pop("api_root"),
                _rehash_query_manifest(run),
            ),
            "RUN_CONTRACT_INVALID",
        ),
        (
            lambda run: (
                run["query_manifest"]["base_query_params"].__setitem__("pageSize", "999"),
                _rehash_query_manifest(run),
            ),
            "RUN_CONTRACT_INVALID",
        ),
    ),
)
def test_wire_binding_omission_partial_and_mutation_fail_before_private_mirror(tmp_path, mutate, code):
    cfg = config(tmp_path)
    store = MemoryStore()

    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(run_mutator=mutate),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.error_code == code
    assert not store.put_attempts
    assert not (cfg.public_root / "current.json").exists()


@pytest.mark.parametrize(
    ("mutate", "code"),
    (
        (lambda run: run.__setitem__("mode", "full_reconcile"), "WORKER_MODE_BINDING_MISMATCH"),
        (
            lambda run: (
                run["query_manifest"].__setitem__("configured_nct_ids", ["NCT00000002"]),
                run["query_manifest"]["base_query_params"].__setitem__("query.id", "NCT00000002"),
                _rehash_query_manifest(run),
            ),
            "WORKER_CANARY_BINDING_MISMATCH",
        ),
        (
            lambda run: (
                run["query_manifest"].__setitem__(
                    "configured_nct_ids", ["NCT00000001", "NCT00000002"]
                ),
                run["query_manifest"]["base_query_params"].__setitem__(
                    "query.id", "NCT00000001,NCT00000002"
                ),
                run["counts"].__setitem__("configured", 2),
                _rehash_query_manifest(run),
            ),
            "WORKER_CANARY_BINDING_MISMATCH",
        ),
    ),
)
def test_worker_authority_rejects_mode_and_canary_substitution_before_mirror(tmp_path, mutate, code):
    cfg = config(tmp_path)
    store = MemoryStore()

    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(run_mutator=mutate),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.error_code == code
    assert not store.put_attempts
    assert not (cfg.public_root / "current.json").exists()


def test_raw_private_extra_and_public_snapshot_mismatch_fail_before_r2_or_pointer(tmp_path):
    cfg = config(tmp_path)
    extra_store = MemoryStore()

    def add_extra(_: SimpleNamespace, kwargs: dict) -> None:
        extra = kwargs["private_root"] / "biocatalyst" / "unexpected.json"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("{}", encoding="utf-8")

    extra = worker.run_once(
        cfg,
        collector_factory=wrap_collector_factory(FakeCollectorFactory(), add_extra),
        store_factory=lambda _: extra_store,
        now_fn=lambda: NOW,
    )
    assert extra.error_code == "RAW_EVIDENCE_INVALID"
    assert not extra_store.put_attempts
    assert not (cfg.public_root / "current.json").exists()


@pytest.mark.parametrize("mutation", ("version_raw_binding", "headers", "status", "snapshot_path", "missing_versions"))
def test_worker_rejects_adversarial_live_evidence_identity_before_r2(tmp_path, mutation):
    """The worker, not the collector, owns the final wire/provenance gate."""

    cfg = config(tmp_path)
    store = MemoryStore()

    def tamper(result: SimpleNamespace, kwargs: dict) -> None:
        run_path = result.run_path
        run = json.loads(run_path.read_text(encoding="utf-8"))
        private_root = kwargs["private_root"]
        if mutation == "version_raw_binding":
            altered_timestamp = "2026-08-01T10:00:00"
            altered_version = "2.0.6"
            run["source_dataset_timestamp_before_raw"] = altered_timestamp
            run["source_dataset_timestamp_after_raw"] = altered_timestamp
            run["source_api_version"] = altered_version
            run["source_api_version_after"] = altered_version
            for phase in ("before", "after"):
                receipt = run["version_evidence"][phase]
                receipt["source_dataset_timestamp_raw"] = altered_timestamp
                receipt["source_api_version"] = altered_version
            evidence = run["version_evidence"]
            evidence["version_receipt_payloads_sha256"] = canonical_json_sha256(
                [evidence["before"], evidence["after"]]
            )
            run_path.write_bytes(canonical_json_bytes(run) + b"\n")
            return
        if mutation == "missing_versions":
            run.pop("version_evidence")
            run_path.write_bytes(canonical_json_bytes(run) + b"\n")
            return
        if mutation in {"headers", "status"}:
            receipt_key = f"biocatalyst/receipts/clinicaltrials/2026/08/{run['run_id']}/0.json"
            receipt_path = private_root / Path(*PurePosixPath(receipt_key).parts)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if mutation == "headers":
                receipt["request"]["headers"].pop("accept-encoding")
            else:
                receipt["response"]["status_code"] = 201
            receipt_path.write_bytes(canonical_json_bytes(receipt) + b"\n")
            return
        snapshot_path = next((private_root / "biocatalyst" / "source_snapshots").rglob("*.json"))
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["raw_object_key"] = "biocatalyst/raw/clinicaltrials/v2/NCT00000001/" + "0" * 64 + ".json"
        snapshot_path.write_bytes(canonical_json_bytes(snapshot) + b"\n")

    result = worker.run_once(
        cfg,
        collector_factory=wrap_collector_factory(FakeCollectorFactory(), tamper),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.error_code == "RAW_EVIDENCE_INVALID"
    assert not store.put_attempts
    assert not (cfg.public_root / "current.json").exists()


def test_worker_rejects_unsupported_parser_contract_digest_before_r2(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()

    def alter_digest(result: SimpleNamespace, _: dict) -> None:
        run = json.loads(result.run_path.read_text(encoding="utf-8"))
        run["code_version"] = "biocatalyst_b1_sha256:" + "0" * 64
        result.run_path.write_bytes(canonical_json_bytes(run) + b"\n")

    result = worker.run_once(
        cfg,
        collector_factory=wrap_collector_factory(FakeCollectorFactory(), alter_digest),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.error_code == "UNSUPPORTED_CODE_VERSION"
    assert not store.put_attempts

    projection_store = MemoryStore()

    def tamper_public_state(result: SimpleNamespace, _: dict) -> None:
        state_path = result.generation_path / "NCT00000001.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["source_published_at"] = "2020-01-01"
        state_path.write_bytes(canonical_json_bytes(state) + b"\n")
        manifest_path = result.generation_path / "publication_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"][0]["public_state_sha256"] = canonical_json_sha256(state)
        manifest["manifest_sha256"] = canonical_json_sha256(
            {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        )
        manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")

    mismatch = worker.run_once(
        cfg,
        collector_factory=wrap_collector_factory(FakeCollectorFactory(), tamper_public_state),
        store_factory=lambda _: projection_store,
        now_fn=lambda: NOW,
    )
    assert mismatch.error_code == "PUBLIC_SNAPSHOT_BINDING_MISMATCH"
    assert not projection_store.put_attempts
    assert not (cfg.public_root / "current.json").exists()


def test_future_source_timestamp_cannot_poison_initial_or_prior_generation(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    future = FakeCollectorFactory(source_timestamp="2099-01-01T00:00:00")

    initial = worker.run_once(cfg, collector_factory=future, store_factory=lambda _: store, now_fn=lambda: NOW)
    assert initial.error_code == "SOURCE_TIMESTAMP_FUTURE"
    assert not store.put_attempts
    assert not (cfg.public_root / "current.json").exists()

    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    pointer = json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8"))
    later = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2099-01-01T00:00:00",
            watermark_after="2026-08-02T15:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert later.error_code == "SOURCE_TIMESTAMP_FUTURE"
    assert json.loads((cfg.public_root / "current.json").read_text(encoding="utf-8")) == pointer


def test_post_archive_mirror_failure_leaves_bounded_private_incident(tmp_path):
    class MirrorReceiptFailureStore(MemoryStore):
        def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
            if key.startswith("biocatalyst/mirror_receipts/"):
                return False
            return super().put_if_absent(key, data, content_type=content_type)

    cfg = config(tmp_path)
    store = MirrorReceiptFailureStore()
    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.error_code == "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED"
    incident_paths = list((cfg.state_root / "committed").rglob("incidents/*.json"))
    assert len(incident_paths) == 1
    incident = json.loads(incident_paths[0].read_text(encoding="utf-8"))
    assert incident["failure_code"] == result.error_code
    assert incident["private_archive_state"] == "retained"
    assert incident["r2_mirror_state"] == "objects_verified"
    assert incident["dead_letter_ref"].startswith("dead-letter/attempt_")
    assert str(cfg.state_root) not in incident_paths[0].read_text(encoding="utf-8")
    assert not (cfg.public_root / "current.json").exists()


def test_same_run_recovery_reuses_deterministic_private_mirror_receipt(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    collector = FakeCollectorFactory()

    def faulting_publisher(path: Path) -> PublicGenerationPublisher:
        return PublicGenerationPublisher(path, pointer_after_replace_hook=lambda _: (_ for _ in ()).throw(OSError("fsync fault")))

    failed = worker.run_once(
        cfg,
        collector_factory=collector,
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
        publisher_factory=faulting_publisher,
    )
    assert failed.error_code == "POINTER_WRITE_FAILED"
    mirror_keys = [key for key in store.objects if key.startswith("biocatalyst/mirror_receipts/")]
    assert len(mirror_keys) == 1
    mirror_key = mirror_keys[0]
    run_id = mirror_key.removeprefix("biocatalyst/mirror_receipts/").removesuffix(".json")
    receipt_before = store.objects[mirror_key]

    recovered = worker.run_once(
        cfg,
        collector_factory=collector,
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert recovered.status == "success"
    assert store.objects[mirror_key] == receipt_before
    assert PublicGenerationPublisher(cfg.public_root).read_committed().generation_id == run_id


def test_generation_health_semantic_binding_rejects_a_rehashed_tamper(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    assert worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    ).status == "success"
    pointer_path = cfg.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = cfg.public_root / "generations" / pointer["generation_id"]
    health_path = generation / "health.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    health["observed_nct_count"] = 2
    health_bytes = canonical_json_bytes(health) + b"\n"
    health_path.write_bytes(health_bytes)
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        if artifact["name"] == "health.json":
            artifact["sha256"] = sha256(health_bytes).hexdigest()
            artifact["byte_count"] = len(health_bytes)
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    manifest_path.write_bytes(manifest_bytes)
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")

    with pytest.raises(PublicationError, match="GENERATION_HEALTH_BINDING_MISMATCH"):
        PublicGenerationPublisher(cfg.public_root).read_committed()


def test_generation_manifest_counts_must_match_validated_projection(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    assert worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    ).status == "success"
    pointer_path = cfg.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = cfg.public_root / "generations" / pointer["generation_id"]
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["configured_nct_count"] = 2
    manifest["observed_nct_count"] = 2
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")

    with pytest.raises(PublicationError, match="GENERATION_HEALTH_BINDING_MISMATCH"):
        PublicGenerationPublisher(cfg.public_root).read_committed()


@pytest.mark.parametrize(
    "code",
    ("PAGINATION_CYCLE", "PAGE_CAP_EXHAUSTED", "DIVERGENT_DUPLICATE", "COUNT_MISMATCH", "SOURCE_CHANGED_MID_RUN"),
)
def test_collector_integrity_codes_remain_quarantined_at_worker_boundary(tmp_path, code):
    class CollectorIncident(RuntimeError):
        def __init__(self) -> None:
            self.code = code
            super().__init__(code)

    class FailingCollector:
        def collect(self, *, watermark_before: str | None = None):
            raise CollectorIncident()

    cfg = config(tmp_path)
    result = worker.run_once(
        cfg,
        collector_factory=lambda **_: FailingCollector(),
        store_factory=lambda _: pytest.fail("store must not initialize on collector incident"),
        now_fn=lambda: NOW,
    )
    assert result.error_code == code
    health = json.loads((cfg.public_root / "health.json").read_text(encoding="utf-8"))
    assert health["state"] == "quarantined"
    assert health["last_error_code"] == code


def test_environment_paths_never_write_health_outside_the_fixed_service_pair(tmp_path, monkeypatch):
    calls = {"collector": 0, "store": 0}

    def no_collector(**_):
        calls["collector"] += 1
        pytest.fail("collector must not start")

    def no_store(_):
        calls["store"] += 1
        pytest.fail("store must not start")

    arbitrary_public = tmp_path / "arbitrary-public"
    invalid = worker.run_from_environment(
        {
            "BIOCATALYST_ENABLED": "1",
            "BIOCATALYST_STATE_ROOT": str(tmp_path / "arbitrary-state"),
            "BIOCATALYST_PUBLIC_ROOT": str(arbitrary_public),
        },
        collector_factory=no_collector,
        store_factory=no_store,
        now_fn=lambda: NOW,
    )
    assert invalid.error_code == "BIOCATALYST_RUNTIME_PATH_INVALID"
    assert not (arbitrary_public / "health.json").exists()

    for state_value, public_value in (
        ("relative/state", str(tmp_path / "public")),
        (str(tmp_path / "same"), str(tmp_path / "same")),
        (str(tmp_path / "ancestor"), str(tmp_path / "ancestor" / "public")),
    ):
        monkeypatch.setattr(worker, "_SERVICE_STATE_ROOT", Path(state_value))
        monkeypatch.setattr(worker, "_SERVICE_PUBLIC_ROOT", Path(public_value))
        plan = worker.load_environment(
            {
                "BIOCATALYST_ENABLED": "1",
                "BIOCATALYST_STATE_ROOT": state_value,
                "BIOCATALYST_PUBLIC_ROOT": public_value,
            }
        )
        assert plan.state == "invalid"
        assert plan.public_root is None
    assert calls == {"collector": 0, "store": 0}


def test_private_mirror_rejects_a_symlink_before_the_first_r2_put(tmp_path):
    root = tmp_path / "private"
    payload = root / "biocatalyst" / "raw.json"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"{}")
    (root / "biocatalyst" / "linked.json").symlink_to(payload)
    store = MemoryStore()

    with pytest.raises(StorageError, match="UNSAFE_PRIVATE_ARTIFACT"):
        mirror_tree_verified(store, root=root)
    assert not store.put_attempts
