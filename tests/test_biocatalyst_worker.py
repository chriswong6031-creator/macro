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
from engine.biocatalyst.history import build_history_exact_diff
from engine.biocatalyst.prospective import (
    build_coverage_epoch,
    build_public_event,
    build_public_model,
)
from collectors.biocatalyst.clinicaltrials_history import (
    ClinicalTrialsHistoryCollector,
    ClinicalTrialsHistoryConfig,
)
from collectors.biocatalyst.clinicaltrials_v2 import current_b1_code_version
import scripts.biocatalyst_worker as worker


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUN = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
FIXTURE_RECEIPT = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "source_page_receipt.v1.valid.json"
FIXTURE_RAW = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "source_page_response.after.raw.json"
FIXTURE_SNAPSHOT = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials" / "trial_source_snapshot.after.v1.valid.json"
HISTORY_FIXTURE_ROOT = ROOT / "data" / "biocatalyst" / "fixtures" / "clinicaltrials_history"
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
    study_mutator: Callable[[dict], None] | None = None
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
                if len(kwargs["nct_ids"]) != 1:
                    raise AssertionError("worker fake supports one explicit NCT per run")
                nct_id = kwargs["nct_ids"][0]
                source_study = raw_payload["studies"][0]
                source_study["protocolSection"]["identificationModule"]["nctId"] = nct_id
                snapshot["nct_id"] = nct_id
                if outer.study_mutator is not None:
                    outer.study_mutator(source_study)
                raw_payload["totalCount"] = len(raw_payload["studies"])
                raw_page = canonical_json_bytes(raw_payload)
                raw_digest = sha256(raw_page).hexdigest()
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
                manifest["configured_nct_ids"] = [nct_id]
                manifest["api_root"] = "https://clinicaltrials.gov/api/v2"
                manifest["request_path"] = "/studies"
                manifest["base_query_params"] = {
                    "query.id": nct_id,
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
                source_ref = f"src:ctgov:{nct_id}:sha256:{source_hash}"
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
                    f"ctgov_snapshot_{nct_id}_"
                    f"{run_id.removeprefix('ctgov_run_')}_{source_hash}"
                )
                snapshot.update(
                    {
                        "source_snapshot_id": snapshot_id,
                        "source_record_ref": source_ref,
                        "source_uri": f"https://clinicaltrials.gov/study/{nct_id}",
                        "run_ref": run_id,
                        "page_receipt_ref": receipt_id,
                        "raw_object_key": (
                            f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{source_hash}.json"
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
                    "nct_id": nct_id,
                    "source_snapshot_id": snapshot["source_snapshot_id"],
                    "source_record_ref": source_ref,
                    "canonical_content_sha256": source_hash,
                    "source_uri": f"https://clinicaltrials.gov/study/{nct_id}",
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
                    "nct_id": nct_id,
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
                snapshot_path = private_root / "biocatalyst" / "source_snapshots" / "clinicaltrials" / nct_id / f"{snapshot_id}.json"
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                snapshot_path.write_bytes(canonical_json_bytes(snapshot) + b"\n")
                generation = public_root / "generations" / run_id
                generation.mkdir(parents=True)
                (generation / f"{nct_id}.json").write_bytes(canonical_json_bytes(state) + b"\n")
                (generation / "publication_manifest.json").write_bytes(canonical_json_bytes(public_manifest) + b"\n")
                return SimpleNamespace(run_id=run_id, run_path=run_path, generation_path=generation)

        return FakeCollector()


@dataclass
class FakeHistoryCollectorFactory:
    """Drive the real B2 collector with static, non-live source bytes.

    The worker must replay the persisted artifacts from this collector rather
    than trust the result object it returns.  The modes deliberately corrupt
    either the post-index or the archived snapshot after collection to exercise
    that boundary without relying on a production ClinicalTrials.gov request.
    """

    mode: str = "complete"
    calls: list[dict] | None = None

    def __post_init__(self) -> None:
        self.calls = [] if self.calls is None else self.calls

    @staticmethod
    def _fixture_bytes(name: str) -> bytes:
        return (HISTORY_FIXTURE_ROOT / name).read_bytes().replace(b"NCT03456024", b"NCT00000001")

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        outer = self

        class Response:
            def __init__(self, payload: bytes) -> None:
                self.status_code = 200
                self.headers = {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                }
                self.content = payload

            def iter_content(self, *, chunk_size: int):
                del chunk_size
                yield self.content

        class Session:
            def __init__(self, responses: list[bytes]) -> None:
                self.responses = responses
                self.requested: list[str] = []

            def get(self, source_uri: str, **_kwargs):
                self.requested.append(source_uri)
                if not self.responses:
                    raise AssertionError("unexpected history source request")
                return Response(self.responses.pop(0))

        class FailingCollector:
            def collect_nct(self, _nct_id: str):
                raise RuntimeError("synthetic B2 availability incident")

        if outer.mode == "raise":
            return FailingCollector()

        index = outer._fixture_bytes("NCT03456024.history.index.synthetic.json")
        version_zero = outer._fixture_bytes("NCT03456024.history.version-0.synthetic.json")
        version_one = outer._fixture_bytes("NCT03456024.history.version-1.synthetic.json")
        post_index = index
        if outer.mode == "race":
            changed = json.loads(index)
            changed["history"]["changes"][1]["date"] = "2018-03-08"
            post_index = canonical_json_bytes(changed)
        session = Session([index, version_zero, version_one, post_index])
        real = ClinicalTrialsHistoryCollector(
            private_root=kwargs["private_root"],
            config=ClinicalTrialsHistoryConfig(
                nct_ids=kwargs["nct_ids"],
                user_agent=kwargs["user_agent"],
                min_request_interval_seconds=0,
            ),
            session=session,
            now_fn=kwargs["now_fn"],
            sleep_fn=lambda _: None,
        )

        class WrappedCollector:
            def collect_nct(self, nct_id: str):
                result = real.collect_nct(nct_id)
                if outer.mode == "fabricated_snapshot":
                    result.source_snapshot_paths[0].write_bytes(b'{"fabricated":true}\n')
                elif outer.mode in {"missing_post_ref", "mismatched_post_ref"}:
                    run = json.loads(result.run_path.read_text(encoding="utf-8"))
                    if outer.mode == "missing_post_ref":
                        del run["history_index_post_receipt_ref"]
                    else:
                        run["history_index_post_receipt_ref"] = run["history_index_receipt_ref"]
                    run["run_payload_sha256"] = canonical_json_sha256(
                        {key: value for key, value in run.items() if key != "run_payload_sha256"}
                    )
                    result.run_path.write_bytes(canonical_json_bytes(run) + b"\n")
                elif outer.mode == "forged_rehashed_raw":
                    original = result.history_version_receipts[0]
                    receipt_path = kwargs["private_root"] / Path(
                        *PurePosixPath(
                            "biocatalyst/receipts/clinicaltrials/history/"
                            f"2026/08/{result.run_id}/{original['receipt_id']}.json"
                        ).parts
                    )
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    raw_path = kwargs["private_root"] / Path(
                        *PurePosixPath(receipt["response"]["raw_response_object_key"]).parts
                    )
                    fabricated = json.loads(raw_path.read_text(encoding="utf-8"))
                    fabricated["study"]["protocolSection"]["identificationModule"]["briefTitle"] = "fabricated history value"
                    raw = canonical_json_bytes(fabricated)
                    digest = sha256(raw).hexdigest()
                    new_key = (
                        "biocatalyst/raw/clinicaltrials/history/NCT00000001/"
                        f"version-0/{digest}.json"
                    )
                    new_raw_path = kwargs["private_root"] / Path(*PurePosixPath(new_key).parts)
                    new_raw_path.parent.mkdir(parents=True, exist_ok=True)
                    new_raw_path.write_bytes(raw)
                    receipt["response"].update(
                        {
                            "exact_response_sha256": digest,
                            "raw_response_object_key": new_key,
                            "byte_count": len(raw),
                        }
                    )
                    receipt["receipt_payload_sha256"] = canonical_json_sha256(
                        {key: value for key, value in receipt.items() if key != "receipt_payload_sha256"}
                    )
                    receipt_path.write_bytes(canonical_json_bytes(receipt) + b"\n")
                elif outer.mode == "derived_collision":
                    snapshots = [
                        json.loads(path.read_text(encoding="utf-8"))
                        for path in result.source_snapshot_paths
                    ]
                    diff = build_history_exact_diff(
                        snapshots[0],
                        snapshots[1],
                        transaction_from=snapshots[1]["transaction_from"],
                    )
                    collision_path = kwargs["private_root"] / Path(
                        *PurePosixPath(
                            "biocatalyst/derived/clinicaltrials/history/NCT00000001/"
                            f"diffs/{diff['diff_payload_sha256']}.json"
                        ).parts
                    )
                    collision_path.parent.mkdir(parents=True, exist_ok=True)
                    collision_path.write_bytes(b'{"divergent":true}\n')
                return result

        return WrappedCollector()


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


def config(
    tmp_path: Path,
    *,
    history_enabled: bool = False,
    prospective_enabled: bool = True,
) -> worker.WorkerConfig:
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
        history_enabled=history_enabled,
        prospective_enabled=prospective_enabled,
        r2_retention_confirmed=prospective_enabled,
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
        "history/NCT00000001.json",
        "prospective/NCT00000001.json",
    }
    projection = publisher.read_trial_projection()
    assert projection is not None
    assert projection.generation == committed
    assert projection.trials[0]["facts"]["brief_title"]["value"] == "Synthetic Phase 2 Study"
    assert projection.trials[0]["authority"]["decision_authority"] is False
    assert projection.history_models_by_nct["NCT00000001"]["available"] is False
    assert projection.history_models_by_nct["NCT00000001"]["unavailable_reason"] == "disabled"
    prospective = projection.prospective_models_by_nct["NCT00000001"]
    assert prospective["available"] is True
    assert prospective["accrual_state"] == "baseline_established"
    assert prospective["observation_count"] == 1
    assert prospective["events"] == []
    assert any(key.startswith("biocatalyst/runs/") for key in store.objects)
    assert any(key.startswith("biocatalyst/raw/") for key in store.objects)
    assert f"biocatalyst/mirror_receipts/{committed.generation_id}.json" in store.objects
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in generation.rglob("*.json"))
    assert str(cfg.state_root) not in public_text
    assert "test-secret" not in public_text
    assert '"canonical_study"' not in public_text
    assert '"raw_object_key"' not in public_text


def test_prospective_first_success_is_a_private_baseline_with_zero_public_changes(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()

    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.status == "success"
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.prospective_models_by_nct["NCT00000001"]
    assert model["accrual_state"] == "baseline_established"
    assert model["observation_count"] == 1
    assert model["events"] == []
    private_root = cfg.state_root / "committed" / result.generation_id / "private"
    prospective_files = {
        path.relative_to(private_root).as_posix()
        for path in private_root.rglob("*")
        if path.is_file() and "/prospective/" in path.as_posix()
    }
    assert len([path for path in prospective_files if "/observations/" in path]) == 1
    assert len([path for path in prospective_files if "/epochs/" in path]) == 1
    assert not [path for path in prospective_files if "/diffs/" in path]
    assert any("/prospective/" in key and "/observations/" in key for key in store.objects)
    public_text = canonical_json_bytes(model).decode("utf-8")
    for forbidden in (
        "current_observation_ref",
        "diff_ref",
        "source_snapshot_ref",
        "content_sha256",
        "canonical_study",
        "raw_object_key",
    ):
        assert forbidden not in public_text


def test_prospective_default_off_publishes_v12_without_private_or_public_ledger(tmp_path):
    cfg = config(tmp_path, prospective_enabled=False)
    store = MemoryStore()

    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.status == "success"
    publisher = PublicGenerationPublisher(cfg.public_root)
    committed = publisher.read_committed()
    assert committed is not None
    assert committed.schema_version == "1.2.0"
    generation = cfg.public_root / "generations" / committed.generation_id
    assert not (generation / "prospective").exists()
    projection = publisher.read_trial_projection()
    assert projection is not None
    assert projection.prospective_models_by_nct["NCT00000001"] == {
        "available": False,
        "unavailable_reason": "baseline_not_established",
    }
    private_root = cfg.state_root / "committed" / result.generation_id / "private"
    assert not list(private_root.glob("**/prospective/**"))
    assert not any("/prospective/" in key for key in store.objects)


def test_disabling_prospective_after_v13_fails_before_collection_or_downgrade(tmp_path):
    enabled_cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        enabled_cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    pointer_before = (enabled_cfg.public_root / "current.json").read_bytes()
    disabled_cfg = config(tmp_path, prospective_enabled=False)
    calls = {"collector": 0, "store": 0}

    result = worker.run_once(
        disabled_cfg,
        collector_factory=lambda **_: calls.__setitem__(
            "collector", calls["collector"] + 1
        ),
        store_factory=lambda _: calls.__setitem__("store", calls["store"] + 1),
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert result.status == "failed"
    assert result.error_code == "BIOCATALYST_PROSPECTIVE_DOWNGRADE_FORBIDDEN"
    assert calls == {"collector": 0, "store": 0}
    assert (enabled_cfg.public_root / "current.json").read_bytes() == pointer_before
    health = json.loads(
        (enabled_cfg.public_root / "health.json").read_text(encoding="utf-8")
    )
    assert health["state"] == "quarantined"
    assert health["last_error_code"] == "BIOCATALYST_PROSPECTIVE_DOWNGRADE_FORBIDDEN"


def test_prospective_second_changed_poll_emits_bounded_event_and_private_exact_diff(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    first_projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert first_projection is not None
    first_model = first_projection.prospective_models_by_nct["NCT00000001"]

    def mutate(study: dict) -> None:
        study["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
        study["protocolSection"]["identificationModule"]["briefTitle"] = "Changed title"

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
            study_mutator=mutate,
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.status == "success", second
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.prospective_models_by_nct["NCT00000001"]
    assert model["coverage_epoch_id"] == first_model["coverage_epoch_id"]
    assert model["accrual_state"] == "accruing"
    assert model["observation_count"] == 2
    assert len(model["events"]) == 1
    event = model["events"][0]
    assert event["observed_interval"]["after"] == first_model["last_observed_at"]
    assert event["first_observed_at"] == event["observed_interval"]["at_or_before"]
    assert event["total_exact_operation_count"] >= 2
    assert event["display_change_count"] == 1
    assert event["omitted_operation_count"] == event["total_exact_operation_count"] - 1
    assert event["changes"] == [
        {
            "kind": "registry_status",
            "op": "replace",
            "before_state": "present",
            "before_value": "RECRUITING",
            "after_state": "present",
            "after_value": "COMPLETED",
        }
    ]
    assert event["evidence"] == {
        "source_name": "ClinicalTrials.gov",
        "source_uri": "https://clinicaltrials.gov/study/NCT00000001",
        "retrieved_at": event["first_observed_at"],
    }
    private_root = cfg.state_root / "committed" / second.generation_id / "private"
    diff_paths = list(private_root.glob("**/prospective/**/diffs/*.json"))
    assert len(diff_paths) == 1
    private_diff = json.loads(diff_paths[0].read_text(encoding="utf-8"))
    assert private_diff["after_observation_ref"]
    assert private_diff["after_content_sha256"]
    assert {operation["change_family"] for operation in private_diff["operations"]} >= {
        "registry_status",
        "other",
    }
    assert diff_paths[0].relative_to(private_root).as_posix() in store.objects
    public_text = canonical_json_bytes(model).decode("utf-8")
    assert "diff_ref" not in public_text
    assert "source_snapshot_ref" not in public_text
    assert "content_sha256" not in public_text


def test_prospective_unchanged_same_scope_poll_counts_observation_without_event_or_diff(
    tmp_path,
):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    first_projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert first_projection is not None
    first_model = first_projection.prospective_models_by_nct["NCT00000001"]

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.status == "success", second
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.prospective_models_by_nct["NCT00000001"]
    assert model["coverage_epoch_id"] == first_model["coverage_epoch_id"]
    assert model["baseline_established_at"] == first_model["baseline_established_at"]
    assert model["observation_count"] == 2
    assert model["events"] == []
    assert model["last_observed_at"] > first_model["last_observed_at"]
    private_root = cfg.state_root / "committed" / second.generation_id / "private"
    observation_paths = list(private_root.glob("**/prospective/**/observations/*.json"))
    assert len(observation_paths) == 1
    observation = json.loads(observation_paths[0].read_text(encoding="utf-8"))
    assert observation["same_content_as_prior"] is True
    assert observation["source_state_changed"] is False
    assert observation["observed_interval"] == {
        "after": first_model["last_observed_at"],
        "at_or_before": model["last_observed_at"],
    }
    assert not list(private_root.glob("**/prospective/**/diffs/*.json"))


def test_prospective_changed_then_reverted_poll_emits_second_legitimate_event(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"

    def complete(study: dict) -> None:
        study["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
            study_mutator=complete,
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )
    assert second.status == "success", second
    second_projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert second_projection is not None
    second_model = second_projection.prospective_models_by_nct["NCT00000001"]
    assert len(second_model["events"]) == 1

    third = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T11:00:00",
            watermark_after="2026-08-01T19:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=4),
    )

    assert third.status == "success", third
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.prospective_models_by_nct["NCT00000001"]
    assert model["observation_count"] == 3
    assert len(model["events"]) == 2
    assert model["events"][0]["change_id"] != model["events"][1]["change_id"]
    assert model["events"][1]["observed_interval"]["after"] == second_model["last_observed_at"]
    status_change = next(
        change
        for change in model["events"][1]["changes"]
        if change["kind"] == "registry_status"
    )
    assert status_change == {
        "kind": "registry_status",
        "op": "replace",
        "before_state": "present",
        "before_value": "COMPLETED",
        "after_state": "present",
        "after_value": "RECRUITING",
    }
    private_root = cfg.state_root / "committed" / third.generation_id / "private"
    diff_paths = list(private_root.glob("**/prospective/**/diffs/*.json"))
    assert len(diff_paths) == 1


def test_prospective_baseline_time_is_per_nct_when_one_run_observations_are_staggered():
    epoch = build_coverage_epoch(
        nct_ids=("NCT00000001", "NCT00000002"),
        current_run_ref="ctgov_run_20260801T150000000000Z_aaaaaaaaaaaa",
        prior_epoch=None,
        coverage_started_at="2026-08-01T15:00:01Z",
        last_observed_at="2026-08-01T15:00:09Z",
        transaction_from="2026-08-01T15:00:10Z",
    )
    generated_at = "2026-08-01T15:00:10Z"

    def baseline(nct_id: str, retrieved_at: str) -> dict:
        return build_public_model(
            nct_id=nct_id,
            epoch=epoch,
            observation={
                "nct_id": nct_id,
                "retrieved_at": retrieved_at,
                "source_state_changed": False,
                "prior_source_snapshot_ref": None,
            },
            exact_diff=None,
            generated_at=generated_at,
            prior_model=None,
        )

    first = baseline("NCT00000001", "2026-08-01T15:00:01Z")
    second = baseline("NCT00000002", "2026-08-01T15:00:09Z")

    assert first["coverage_started_at"] == second["coverage_started_at"]
    assert first["baseline_established_at"] == "2026-08-01T15:00:01Z"
    assert second["baseline_established_at"] == "2026-08-01T15:00:09Z"
    assert first["baseline_established_at"] != second["baseline_established_at"]


def test_prospective_same_scope_missing_prior_private_evidence_fails_closed(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    pointer_before = (cfg.public_root / "current.json").read_bytes()
    prior_private = cfg.state_root / "committed" / first.generation_id / "private"
    observation_path = next(prior_private.glob("**/prospective/**/observations/*.json"))
    observation_path.unlink()

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.status == "failed"
    assert second.error_code == "PROSPECTIVE_PRIOR_MIRROR_INVALID"
    assert (cfg.public_root / "current.json").read_bytes() == pointer_before


def test_prospective_same_scope_corrupt_prior_source_evidence_fails_closed(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    pointer_before = (cfg.public_root / "current.json").read_bytes()
    prior_private = cfg.state_root / "committed" / first.generation_id / "private"
    snapshot_path = next(
        path
        for path in prior_private.glob("**/source_snapshots/clinicaltrials/NCT*/*.json")
        if "/history/" not in path.as_posix()
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["canonical_study"]["protocolSection"]["identificationModule"][
        "briefTitle"
    ] = "forged prior value"
    snapshot_path.write_bytes(canonical_json_bytes(snapshot) + b"\n")

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.status == "failed"
    assert second.error_code == "PROSPECTIVE_PRIOR_MIRROR_INVALID"
    assert (cfg.public_root / "current.json").read_bytes() == pointer_before


def test_prospective_malformed_local_mirror_receipt_has_bounded_failure_code(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    pointer_before = (cfg.public_root / "current.json").read_bytes()
    receipt_path = (
        cfg.state_root
        / "committed"
        / first.generation_id
        / "mirror_receipt.json"
    )
    receipt_path.write_bytes(b"{")

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.status == "failed"
    assert second.error_code == "PROSPECTIVE_PRIOR_MIRROR_INVALID"
    assert (cfg.public_root / "current.json").read_bytes() == pointer_before


def test_prospective_scope_change_starts_new_inactive_superseding_epoch_without_diff(tmp_path):
    first_cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        first_cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    first_projection = PublicGenerationPublisher(first_cfg.public_root).read_trial_projection()
    assert first_projection is not None
    first_epoch = first_projection.prospective_models_by_nct["NCT00000001"]["coverage_epoch_id"]

    second_cfg = worker.WorkerConfig(
        state_root=first_cfg.state_root,
        public_root=first_cfg.public_root,
        nct_ids=("NCT00000002",),
        user_agent=first_cfg.user_agent,
        r2=first_cfg.r2,
        history_enabled=False,
        prospective_enabled=True,
        r2_retention_confirmed=True,
    )
    second = worker.run_once(
        second_cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.status == "success", second
    projection = PublicGenerationPublisher(second_cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.prospective_models_by_nct["NCT00000002"]
    assert model["coverage_epoch_id"] != first_epoch
    assert model["accrual_state"] == "baseline_established"
    assert model["observation_count"] == 1
    assert model["events"] == []
    private_root = second_cfg.state_root / "committed" / second.generation_id / "private"
    assert not list(private_root.glob("**/prospective/**/diffs/*.json"))
    old_private = first_cfg.state_root / "committed" / first.generation_id / "private"
    old_epoch_documents = list(old_private.glob("**/prospective/epochs/**/*.json"))
    assert len(old_epoch_documents) == 1
    assert json.loads(old_epoch_documents[0].read_text())["coverage_epoch_id"] == first_epoch


def test_prospective_private_writer_rejects_symlinked_ancestor_before_external_creation(tmp_path):
    private_root = tmp_path / "private"
    external = tmp_path / "external"
    (private_root / "biocatalyst").mkdir(parents=True)
    external.mkdir()
    (private_root / "biocatalyst" / "derived").symlink_to(external, target_is_directory=True)

    with pytest.raises(PublicationError, match="PROSPECTIVE_PRIVATE_ARCHIVE_INVALID"):
        worker._write_private_prospective_immutable(
            private_root,
            relative=(
                "biocatalyst/derived/clinicaltrials/prospective/epochs/"
                "ctgov_coverage_test/ctgov_run_test.json"
            ),
            document={"one": 1},
        )

    assert list(external.iterdir()) == []


def test_prospective_private_writer_rejects_divergent_immutable_collision(tmp_path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    relative = (
        "biocatalyst/derived/clinicaltrials/prospective/epochs/"
        "ctgov_coverage_test/ctgov_run_test.json"
    )
    path = worker._write_private_prospective_immutable(
        private_root,
        relative=relative,
        document={"one": 1},
    )

    with pytest.raises(PublicationError, match="IMMUTABLE_OBJECT_COLLISION"):
        worker._write_private_prospective_immutable(
            private_root,
            relative=relative,
            document={"one": 2},
        )

    assert path.read_bytes() == canonical_json_bytes({"one": 1}) + b"\n"


def test_prospective_public_event_omits_other_and_oversized_values_without_truncation():
    event = build_public_event(
        {
            "nct_id": "NCT00000001",
            "observed_interval": {
                "after": "2026-08-01T15:00:02Z",
                "at_or_before": "2026-08-01T17:00:02Z",
            },
            "operations": [
                {
                    "op": "replace",
                    "change_family": "registry_status",
                    "before_state": "present",
                    "before_value": "RECRUITING",
                    "after_state": "present",
                    "after_value": "COMPLETED",
                },
                {
                    "op": "replace",
                    "change_family": "other",
                    "before_state": "present",
                    "before_value": "private exact value",
                    "after_state": "present",
                    "after_value": "another exact value",
                },
                {
                    "op": "replace",
                    "change_family": "endpoint_record",
                    "before_state": "present",
                    "before_value": "x" * 2001,
                    "after_state": "present",
                    "after_value": "safe",
                },
                {
                    "op": "replace",
                    "change_family": "endpoint_record",
                    "before_state": "present",
                    "before_value": {"nested": {"ref": "private"}},
                    "after_state": "present",
                    "after_value": {"reference": "allowed clinical reference"},
                },
                {
                    "op": "replace",
                    "change_family": "endpoint_record",
                    "before_state": "present",
                    "before_value": {"reference": "Clinical reference A"},
                    "after_state": "present",
                    "after_value": {"references": ["Clinical reference B"]},
                },
            ],
        }
    )

    assert event["total_exact_operation_count"] == 5
    assert event["display_change_count"] == 2
    assert event["omitted_operation_count"] == 3
    assert event["changes"][0]["kind"] == "registry_status"
    rendered = canonical_json_bytes(event).decode("utf-8")
    assert "private exact value" not in rendered
    assert "x" * 2001 not in rendered
    assert '"ref"' not in rendered
    assert "Clinical reference A" in rendered
    assert "Clinical reference B" in rendered


@pytest.mark.parametrize(
    "private_key",
    (
        "payloadHash",
        "contentHash",
        "sourceHash",
        "payloadhash",
        "content_hash",
        "source-hash",
    ),
)
def test_prospective_public_event_omits_normalized_and_compact_hash_keys(
    private_key,
):
    event = build_public_event(
        {
            "nct_id": "NCT00000001",
            "observed_interval": {
                "after": "2026-08-01T15:00:02Z",
                "at_or_before": "2026-08-01T17:00:02Z",
            },
            "operations": [
                {
                    "op": "replace",
                    "change_family": "endpoint_record",
                    "before_state": "present",
                    "before_value": {"diagnosis": {"hashimotoDisease": "present"}},
                    "after_state": "present",
                    "after_value": {"diagnosis": {"hashimotoDisease": "stable"}},
                },
                {
                    "op": "replace",
                    "change_family": "endpoint_record",
                    "before_state": "present",
                    "before_value": {"summary": {"reference": "clinical text"}},
                    "after_state": "present",
                    "after_value": {"summary": {private_key: "internal-only"}},
                },
            ],
        }
    )

    assert event["total_exact_operation_count"] == 2
    assert event["display_change_count"] == 1
    assert event["omitted_operation_count"] == 1
    assert event["changes"][0]["after_value"] == {
        "diagnosis": {"hashimotoDisease": "stable"}
    }
    assert private_key not in canonical_json_bytes(event).decode("utf-8")


def test_prospective_site_set_projects_counts_and_countries_without_contacts():
    event = build_public_event(
        {
            "nct_id": "NCT00000001",
            "observed_interval": {
                "after": "2026-08-01T15:00:02Z",
                "at_or_before": "2026-08-01T17:00:02Z",
            },
            "operations": [
                {
                    "op": "replace",
                    "change_family": "site_set",
                    "before_state": "present",
                    "before_value": [
                        {
                            "facility": "Hospital A",
                            "country": "Canada",
                            "contacts": [{"name": "Private Contact"}],
                        }
                    ],
                    "after_state": "present",
                    "after_value": [
                        {"facility": "Hospital A", "country": "Canada"},
                        {"facility": "Hospital B", "country": "United States"},
                    ],
                }
            ],
        }
    )

    change = event["changes"][0]
    assert change["before_value"] == {
        "site_count": 1,
        "country_count": 1,
        "countries": ["Canada"],
        "countries_truncated": False,
    }
    assert change["after_value"] == {
        "site_count": 2,
        "country_count": 2,
        "countries": ["Canada", "United States"],
        "countries_truncated": False,
    }
    rendered = canonical_json_bytes(event).decode("utf-8")
    assert "Private Contact" not in rendered
    assert "Hospital A" not in rendered


def test_prospective_site_summary_caps_country_labels_without_omitting_counts():
    sites = [{"country": f"Country {index:02d}"} for index in range(40)]
    event = build_public_event(
        {
            "nct_id": "NCT00000001",
            "observed_interval": {
                "after": "2026-08-01T15:00:02Z",
                "at_or_before": "2026-08-01T17:00:02Z",
            },
            "operations": [
                {
                    "op": "add",
                    "change_family": "site_set",
                    "before_state": "missing",
                    "before_value": None,
                    "after_state": "present",
                    "after_value": sites,
                }
            ],
        }
    )

    assert event["display_change_count"] == 1
    summary = event["changes"][0]["after_value"]
    assert summary["site_count"] == 40
    assert summary["country_count"] == 40
    assert len(summary["countries"]) == 32
    assert summary["countries_truncated"] is True


@pytest.mark.parametrize("artifact_kind", ("epoch", "model"))
def test_prospective_rehashed_local_derived_tamper_cannot_cross_remote_mirror(
    tmp_path, artifact_kind
):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    private_root = cfg.state_root / "committed" / first.generation_id / "private"
    pattern = (
        "**/prospective/epochs/**/*.json"
        if artifact_kind == "epoch"
        else "**/prospective/**/models/*.json"
    )
    artifact_path = next(private_root.glob(pattern))
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact_kind == "epoch":
        payload["coverage_started_at"] = "2026-07-01T00:00:00Z"
    else:
        payload["generated_at"] = "2026-08-01T16:30:00Z"
        payload["model_payload_sha256"] = canonical_json_sha256(
            {key: value for key, value in payload.items() if key != "model_payload_sha256"}
        )
    artifact_path.write_bytes(canonical_json_bytes(payload) + b"\n")
    pointer_before = (cfg.public_root / "current.json").read_bytes()

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.error_code == "PROSPECTIVE_PRIOR_MIRROR_INVALID"
    assert (cfg.public_root / "current.json").read_bytes() == pointer_before


@pytest.mark.parametrize("target", ("receipt", "object"))
def test_prospective_missing_or_tampered_remote_mirror_fails_closed(tmp_path, target):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    if target == "receipt":
        del store.objects[f"biocatalyst/mirror_receipts/{first.generation_id}.json"]
    else:
        object_key = next(
            key for key in store.objects if "/prospective/" in key and "/models/" in key
        )
        store.objects[object_key] = b'{"self_consistent":false}\n'
    pointer_before = (cfg.public_root / "current.json").read_bytes()

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.error_code == "PROSPECTIVE_PRIOR_MIRROR_INVALID"
    assert (cfg.public_root / "current.json").read_bytes() == pointer_before


def test_prospective_rehashed_public_model_must_equal_private_mirrored_model(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    pointer_path = cfg.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = cfg.public_root / "generations" / first.generation_id
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_path = generation / "prospective" / "NCT00000001.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["generated_at"] = "2026-08-01T16:30:00Z"
    model["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in model.items() if key != "model_payload_sha256"}
    )
    model_bytes = canonical_json_bytes(model) + b"\n"
    model_path.write_bytes(model_bytes)
    for artifact in manifest["artifacts"]:
        if artifact["name"] == "prospective/NCT00000001.json":
            artifact["sha256"] = sha256(model_bytes).hexdigest()
            artifact["byte_count"] = len(model_bytes)
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")
    assert PublicGenerationPublisher(cfg.public_root).read_trial_projection() is not None
    pointer_before = pointer_path.read_bytes()

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )

    assert second.error_code == "PROSPECTIVE_MODEL_BINDING_INVALID"
    assert pointer_path.read_bytes() == pointer_before


def test_prospective_rehashed_prior_diff_cannot_cross_remote_mirror(tmp_path):
    cfg = config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"

    def mutate(study: dict) -> None:
        study["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
            study_mutator=mutate,
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=2),
    )
    assert second.status == "success"
    private_root = cfg.state_root / "committed" / second.generation_id / "private"
    diff_path = next(private_root.glob("**/prospective/**/diffs/*.json"))
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    diff["operations"][0]["after_value"] = "WITHDRAWN"
    diff["diff_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in diff.items() if key != "diff_payload_sha256"}
    )
    diff_path.write_bytes(canonical_json_bytes(diff) + b"\n")
    pointer_before = (cfg.public_root / "current.json").read_bytes()

    third = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T11:00:00",
            watermark_after="2026-08-01T19:00:05Z",
            study_mutator=mutate,
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=4),
    )

    assert third.error_code == "PROSPECTIVE_PRIOR_MIRROR_INVALID"
    assert (cfg.public_root / "current.json").read_bytes() == pointer_before


def test_history_success_replays_private_chain_before_exposing_a_complete_model(tmp_path):
    cfg = config(tmp_path, history_enabled=True)
    store = MemoryStore()
    history = FakeHistoryCollectorFactory()

    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        history_collector_factory=history,
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.status == "success"
    assert history.calls == [
        {
            "private_root": history.calls[0]["private_root"],
            "nct_ids": ("NCT00000001",),
            "user_agent": cfg.user_agent,
            "now_fn": history.calls[0]["now_fn"],
        }
    ]
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.history_models_by_nct["NCT00000001"]
    assert model["available"] is True
    assert model["coverage_class"] == "record_history_complete"
    assert [version["display_version"] for version in model["versions"]] == [1, 2]
    assert model["changes"]
    assert all(not key.startswith("canonical_") for key in model)
    assert any(key.startswith("biocatalyst/runs/clinicaltrials/history/") for key in store.objects)
    assert any(key.startswith("biocatalyst/receipts/clinicaltrials/history/") for key in store.objects)
    assert any(key.startswith("biocatalyst/source_snapshots/clinicaltrials/history/") for key in store.objects)
    assert any(key.startswith("biocatalyst/derived/clinicaltrials/history/NCT00000001/diffs/") for key in store.objects)
    assert any(key.startswith("biocatalyst/derived/clinicaltrials/history/NCT00000001/facts/") for key in store.objects)
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (cfg.public_root / "generations" / result.generation_id).rglob("*.json")
    )
    assert "biocatalyst/derived/" not in public_text


@pytest.mark.parametrize(
    "mode",
    (
        "race",
        "fabricated_snapshot",
        "missing_post_ref",
        "mismatched_post_ref",
        "forged_rehashed_raw",
        "derived_collision",
    ),
)
def test_history_partial_or_fabricated_evidence_never_replaces_b1_with_a_claim(tmp_path, mode):
    cfg = config(tmp_path, history_enabled=True)
    store = MemoryStore()
    b1 = FakeCollectorFactory()

    result = worker.run_once(
        cfg,
        collector_factory=b1,
        history_collector_factory=FakeHistoryCollectorFactory(mode=mode),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.status == "success"
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    assert projection.trials[0]["facts"]["brief_title"]["value"] == "Synthetic Phase 2 Study"
    model = projection.history_models_by_nct["NCT00000001"]
    assert model["available"] is False
    assert model["coverage_class"] == "unavailable"
    assert model["unavailable_reason"] in {"incomplete_chain", "source_shape_drift"}


def test_history_failure_carries_only_the_complete_pointer_bound_prior_while_b1_advances(tmp_path):
    cfg = config(tmp_path, history_enabled=True)
    store = MemoryStore()
    first = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        history_collector_factory=FakeHistoryCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    first_projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert first_projection is not None
    prior_model = first_projection.history_models_by_nct["NCT00000001"]
    assert prior_model["available"] is True

    second = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(watermark_after="2026-08-02T15:00:05Z"),
        history_collector_factory=FakeHistoryCollectorFactory(mode="raise"),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert second.status == "success"
    assert second.generation_id != first.generation_id
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    assert projection.generation.generation_id == second.generation_id
    assert projection.history_models_by_nct["NCT00000001"] == prior_model


def test_disabling_history_refresh_preserves_the_complete_pointer_bound_prior(tmp_path):
    enabled = config(tmp_path, history_enabled=True)
    store = MemoryStore()
    first = worker.run_once(
        enabled,
        collector_factory=FakeCollectorFactory(),
        history_collector_factory=FakeHistoryCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    first_generation = enabled.public_root / "generations" / first.generation_id
    previous_bytes = (first_generation / "history" / "NCT00000001.json").read_bytes()

    disabled = config(tmp_path, history_enabled=False)
    second = worker.run_once(
        disabled,
        collector_factory=FakeCollectorFactory(watermark_after="2026-08-02T15:00:05Z"),
        history_collector_factory=lambda **_: pytest.fail("disabled B2 collector must not start"),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert second.status == "success"
    next_generation = disabled.public_root / "generations" / second.generation_id
    assert (next_generation / "history" / "NCT00000001.json").read_bytes() == previous_bytes


def test_history_without_a_complete_prior_is_explicitly_unavailable(tmp_path):
    cfg = config(tmp_path, history_enabled=True)
    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        history_collector_factory=FakeHistoryCollectorFactory(mode="raise"),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )

    assert result.status == "success"
    projection = PublicGenerationPublisher(cfg.public_root).read_trial_projection()
    assert projection is not None
    model = projection.history_models_by_nct["NCT00000001"]
    assert model["available"] is False
    assert model["current_only"] is False
    assert model["coverage_class"] == "unavailable"
    assert model["unavailable_reason"] == "incomplete_chain"
    assert model["retrieved_at"] is None
    assert model["versions"] == []
    assert model["changes"] == []


def test_history_private_archive_r2_failure_never_advances_the_public_pointer(tmp_path):
    class FailHistoryRunStore(MemoryStore):
        def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
            if key.startswith("biocatalyst/runs/clinicaltrials/history/"):
                self.put_attempts.append(key)
                return False
            return super().put_if_absent(key, data, content_type=content_type)

    cfg = config(tmp_path, history_enabled=True)
    store = FailHistoryRunStore()
    result = worker.run_once(
        cfg,
        collector_factory=FakeCollectorFactory(),
        history_collector_factory=FakeHistoryCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )

    assert result.error_code == "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED"
    assert any(key.startswith("biocatalyst/derived/clinicaltrials/history/") for key in store.objects)
    assert any(key.startswith("biocatalyst/receipts/clinicaltrials/history/") for key in store.objects)
    assert any(key.startswith("biocatalyst/runs/clinicaltrials/history/") for key in store.put_attempts)
    assert not (cfg.public_root / "current.json").exists()


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


def test_history_environment_flag_is_default_off_and_rejects_nonbinary_input(tmp_path, monkeypatch):
    state_root = tmp_path / "macro-biocatalyst" / "state"
    public_root = tmp_path / "macro-biocatalyst" / "public"
    monkeypatch.setattr(worker, "_SERVICE_STATE_ROOT", state_root)
    monkeypatch.setattr(worker, "_SERVICE_PUBLIC_ROOT", public_root)
    base = {
        "BIOCATALYST_ENABLED": "1",
        "BIOCATALYST_STATE_ROOT": str(state_root),
        "BIOCATALYST_PUBLIC_ROOT": str(public_root),
        "BIOCATALYST_CANARY_NCTS": "NCT00000001",
        "BIOCATALYST_USER_AGENT": "MastermindX test contact@example.com",
        "BIOCATALYST_R2_ENDPOINT": "https://r2.example.test",
        "BIOCATALYST_R2_BUCKET": "biocatalyst-private",
        "BIOCATALYST_R2_ACCESS_KEY_ID": "test-access",
        "BIOCATALYST_R2_SECRET_ACCESS_KEY": "test-secret",
    }

    defaulted = worker.load_environment(base)
    assert defaulted.state == "enabled"
    assert defaulted.config is not None and defaulted.config.history_enabled is False
    blocked = worker.load_environment({**base, "BIOCATALYST_HISTORY_ENABLED": "1"})
    assert blocked.state == "invalid"
    assert blocked.error_code == "BIOCATALYST_HISTORY_SOURCE_NOT_APPROVED"

    approved_registry = tmp_path / "biocatalyst_sources.yml"
    approved_registry.write_text(
        "sources:\n"
        "  clinicaltrials_gov_record_history:\n"
        "    source_id: clinicaltrials_gov_record_history\n"
        "    production_ingest_allowed: true\n"
        "    source_shape_canary_required: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(worker, "_SOURCE_REGISTRY_PATH", approved_registry)
    enabled = worker.load_environment({**base, "BIOCATALYST_HISTORY_ENABLED": "1"})
    assert enabled.state == "enabled"
    assert enabled.config is not None and enabled.config.history_enabled is True
    invalid = worker.load_environment({**base, "BIOCATALYST_HISTORY_ENABLED": "true"})
    assert invalid.state == "invalid"
    assert invalid.error_code == "BIOCATALYST_HISTORY_ENABLED_INVALID"


def test_prospective_environment_requires_binary_opt_in_and_retention_attestation(
    tmp_path, monkeypatch
):
    state_root = tmp_path / "macro-biocatalyst" / "state"
    public_root = tmp_path / "macro-biocatalyst" / "public"
    monkeypatch.setattr(worker, "_SERVICE_STATE_ROOT", state_root)
    monkeypatch.setattr(worker, "_SERVICE_PUBLIC_ROOT", public_root)
    base = {
        "BIOCATALYST_ENABLED": "1",
        "BIOCATALYST_STATE_ROOT": str(state_root),
        "BIOCATALYST_PUBLIC_ROOT": str(public_root),
        "BIOCATALYST_CANARY_NCTS": "NCT00000001",
        "BIOCATALYST_USER_AGENT": "MastermindX test contact@example.com",
        "BIOCATALYST_R2_ENDPOINT": "https://r2.example.test",
        "BIOCATALYST_R2_BUCKET": "biocatalyst-private",
        "BIOCATALYST_R2_ACCESS_KEY_ID": "test-access",
        "BIOCATALYST_R2_SECRET_ACCESS_KEY": "test-secret",
    }

    defaulted = worker.load_environment(base)
    assert defaulted.state == "enabled"
    assert defaulted.config is not None
    assert defaulted.config.prospective_enabled is False
    assert defaulted.config.r2_retention_confirmed is False

    unattested = worker.load_environment(
        {**base, "BIOCATALYST_PROSPECTIVE_ENABLED": "1"}
    )
    assert unattested.state == "invalid"
    assert unattested.error_code == "BIOCATALYST_R2_RETENTION_NOT_CONFIRMED"

    enabled = worker.load_environment(
        {
            **base,
            "BIOCATALYST_PROSPECTIVE_ENABLED": "1",
            "BIOCATALYST_R2_RETENTION_CONFIRMED": "1",
        }
    )
    assert enabled.state == "enabled"
    assert enabled.config is not None
    assert enabled.config.prospective_enabled is True
    assert enabled.config.r2_retention_confirmed is True

    with pytest.raises(
        worker.WorkerConfigError,
        match="BIOCATALYST_R2_RETENTION_NOT_CONFIRMED",
    ):
        worker.WorkerConfig(
            state_root=state_root,
            public_root=public_root,
            nct_ids=("NCT00000001",),
            user_agent="MastermindX test contact@example.com",
            r2=enabled.config.r2,
            prospective_enabled=True,
            r2_retention_confirmed=False,
        )

    invalid_enabled = worker.load_environment(
        {**base, "BIOCATALYST_PROSPECTIVE_ENABLED": "true"}
    )
    assert invalid_enabled.state == "invalid"
    assert invalid_enabled.error_code == "BIOCATALYST_PROSPECTIVE_ENABLED_INVALID"

    invalid_attestation = worker.load_environment(
        {**base, "BIOCATALYST_R2_RETENTION_CONFIRMED": "true"}
    )
    assert invalid_attestation.state == "invalid"
    assert (
        invalid_attestation.error_code
        == "BIOCATALYST_R2_RETENTION_CONFIRMED_INVALID"
    )


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
