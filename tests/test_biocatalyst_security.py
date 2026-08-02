"""Adversarial B1 trust-boundary tests.

These tests intentionally exercise only public seams (and the worker's bounded
error taxonomy).  They use temporary roots and fake source/R2 clients so no
network, service path, or credential is required.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable

import pytest

from collectors.biocatalyst.clinicaltrials_v2 import (
    ClinicalTrialsV2Collector,
    ClinicalTrialsV2Config,
    CollectionError,
)
import engine.biocatalyst.publication as publication_module
from engine.biocatalyst.publication import (
    HistoryPublicationEvidence,
    PreparedGeneration,
    PublicationError,
    PublicGenerationPublisher,
    archive_private_stage,
)
from engine.biocatalyst.history import (
    build_history_exact_diff,
    build_history_read_model,
    derive_history_change_facts,
)
from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256
import scripts.biocatalyst_worker as worker
from tests.test_biocatalyst_worker import (
    FakeCollectorFactory,
    MemoryStore,
    NOW,
    config as worker_config,
)
from tests.test_biocatalyst_history import _history_chain


RUN_ID = "ctgov_run_20260801T160000000000Z_abcdef123456"


def _tree_fingerprint(root: Path) -> tuple[tuple[str, str, bytes | str], ...]:
    """Capture a target tree without following a hostile symlink."""

    items: list[tuple[str, str, bytes | str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            items.append((relative, "symlink", os.readlink(path)))
        elif stat.S_ISREG(mode):
            items.append((relative, "file", path.read_bytes()))
        elif stat.S_ISDIR(mode):
            items.append((relative, "directory", ""))
        else:
            items.append((relative, "nonregular", ""))
    return tuple(items)


@pytest.fixture
def committed_generation(tmp_path: Path):
    """Create one real worker-promoted generation through the normal seam."""

    config = worker_config(tmp_path)
    result = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )
    assert result.status == "success"
    return config, PublicGenerationPublisher(config.public_root)


def _generation_paths(publisher: PublicGenerationPublisher) -> tuple[Path, Path, dict[str, Any]]:
    pointer_path = publisher.pointer_path
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = publisher.public_root / "generations" / pointer["generation_id"]
    return pointer_path, generation, pointer


def _rehash_generation(
    *,
    pointer_path: Path,
    generation: Path,
    mutate: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    """Model a deliberate on-disk rehash attack, not an accidental corruption."""

    health_path = generation / "health.json"
    manifest_path = generation / "manifest.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(health, manifest)
    health_bytes = canonical_json_bytes(health) + b"\n"
    health_path.write_bytes(health_bytes)
    for artifact in manifest["artifacts"]:
        if artifact["name"] == "health.json":
            artifact["sha256"] = sha256(health_bytes).hexdigest()
            artifact["byte_count"] = len(health_bytes)
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


def _rehash_trial_projection(
    *,
    pointer_path: Path,
    generation: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Model a full-chain rehash attempt against one normalized trial DTO.

    This deliberately recomputes the projection's self-hash, its manifest
    artifact entry, the manifest hash, and the current-pointer manifest hash.
    The reader must therefore reject provenance rebinding on semantic grounds,
    not merely because an outer hash was left stale.
    """

    snapshot_path = generation / "trial_snapshots" / "NCT00000001.json"
    manifest_path = generation / "manifest.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(snapshot)
    snapshot["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in snapshot.items() if key != "projection_sha256"}
    )
    snapshot_bytes = canonical_json_bytes(snapshot) + b"\n"
    snapshot_path.write_bytes(snapshot_bytes)
    for artifact in manifest["artifacts"]:
        if artifact["name"] == "trial_snapshots/NCT00000001.json":
            artifact["sha256"] = sha256(snapshot_bytes).hexdigest()
            artifact["byte_count"] = len(snapshot_bytes)
            break
    else:  # A worker-promoted B1b generation must have this exact artifact.
        raise AssertionError("normalized trial projection artifact missing")
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


def _history_model_for_security() -> dict[str, Any]:
    """One contract-valid public B2 history artifact with no private evidence."""

    model: dict[str, Any] = {
        "contract_id": "trial_history_read_model.v1",
        "schema_version": "1.0.0",
        "history_model_id": "trial_history_model_NCT00000001_security",
        "nct_id": "NCT00000001",
        "available": True,
        "source_name": "ClinicalTrials.gov",
        "source_history_url": "https://clinicaltrials.gov/study/NCT00000001?tab=history",
        "coverage_class": "record_history_complete",
        "current_only": False,
        "unavailable_reason": None,
        "retrieved_at": "2026-08-01T15:00:02.000000Z",
        "versions": [
            {
                "display_version": 1,
                "source_submitted_at": "2026-08-01",
                "url": "https://clinicaltrials.gov/study/NCT00000001?a=1&tab=history",
            }
        ],
        "changes": [],
        "authority": {
            "classification": "source_fact",
            "decision_authority": False,
            "allowed_uses": ["display", "context", "explain"],
            "forbidden_uses": [
                "originate_signal",
                "rank_security",
                "select_security",
                "size_position",
                "gate_decision",
                "execute_trade",
                "raise_authority",
            ],
        },
        "generated_at": "2026-08-01T15:00:02.000000Z",
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model["model_payload_sha256"] = canonical_json_sha256(model)
    return model


def _install_rehashed_v12_history_artifact(
    publisher: PublicGenerationPublisher,
    model: dict[str, Any],
) -> None:
    """Model an attacker who rehashes outer public files but not model identity."""

    pointer_path, generation, pointer = _generation_paths(publisher)
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = generation / "history" / "NCT00000001.json"
    artifact_path.parent.mkdir(exist_ok=True)
    artifact_bytes = canonical_json_bytes(model) + b"\n"
    artifact_path.write_bytes(artifact_bytes)
    prospective_dir = generation / "prospective"
    if prospective_dir.exists():
        for prospective_artifact in prospective_dir.iterdir():
            prospective_artifact.unlink()
        prospective_dir.rmdir()
    manifest["schema_version"] = "1.2.0"
    manifest["artifacts"] = [
        item
        for item in manifest["artifacts"]
        if not item["name"].startswith("prospective/")
    ]
    artifact_entry = {
        "name": "history/NCT00000001.json",
        "sha256": sha256(artifact_bytes).hexdigest(),
        "byte_count": len(artifact_bytes),
    }
    for index, existing in enumerate(manifest["artifacts"]):
        if existing["name"] == artifact_entry["name"]:
            manifest["artifacts"][index] = artifact_entry
            break
    else:
        manifest["artifacts"].append(artifact_entry)
    manifest["artifacts"].sort(key=lambda item: item["name"])
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


def test_operational_health_goes_stale_at_read_time_without_a_worker_run(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    config, publisher = committed_generation
    _, generation, _ = _generation_paths(publisher)
    immutable_health = json.loads((generation / "health.json").read_text(encoding="utf-8"))
    published_at = datetime.fromisoformat(
        publisher.read_committed().published_at.replace("Z", "+00:00")
    )
    health_before = publisher.health_path.read_bytes()

    fresh = publisher.read_operational_health(now=published_at)
    stale = publisher.read_operational_health(
        now=published_at + timedelta(seconds=immutable_health["freshness_budget_seconds"], microseconds=1)
    )

    assert fresh["state"] == "fresh"
    assert fresh["generation_id"] == publisher.read_committed().generation_id
    assert stale["state"] == "stale"
    assert stale["generation_id"] == fresh["generation_id"]
    # A read-time downgrade is observational only; no tick ran and no mutable
    # file may be rewritten merely because time passed.
    assert publisher.health_path.read_bytes() == health_before
    assert config.public_root.joinpath("health.json").read_bytes() == health_before


def test_fresh_operational_health_must_bind_the_current_immutable_generation(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    _, publisher = committed_generation
    mutable_health = json.loads(publisher.health_path.read_text(encoding="utf-8"))
    mutable_health["generation_id"] = RUN_ID
    publisher.health_path.write_bytes(canonical_json_bytes(mutable_health) + b"\n")

    with pytest.raises(PublicationError):
        publisher.read_operational_health(now=NOW)


def test_top_level_current_and_health_symlinks_are_not_trusted(
    committed_generation: tuple[Any, PublicGenerationPublisher], tmp_path: Path
) -> None:
    _, publisher = committed_generation
    pointer_bytes = publisher.pointer_path.read_bytes()
    health_bytes = publisher.health_path.read_bytes()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_pointer = outside / "current.json"
    outside_health = outside / "health.json"
    outside_pointer.write_bytes(pointer_bytes)
    outside_health.write_bytes(health_bytes)

    publisher.pointer_path.unlink()
    publisher.pointer_path.symlink_to(outside_pointer)
    with pytest.raises(PublicationError):
        publisher.read_committed()

    publisher.pointer_path.unlink()
    publisher.pointer_path.write_bytes(pointer_bytes)
    publisher.health_path.unlink()
    publisher.health_path.symlink_to(outside_health)
    with pytest.raises(PublicationError):
        publisher.read_operational_health(now=NOW)


def test_rehashed_history_artifact_without_its_own_hash_cannot_be_read(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    """The public manifest/pointer hash is insufficient for B2 history facts."""

    _, publisher = committed_generation
    model = _history_model_for_security()
    # Simulate a full outer-tree rehash after a semantic mutation while leaving
    # the public model's own content-address intact.  Both promotion-time and
    # request-time validation must reject it.
    model["generated_at"] = "2026-08-01T15:00:03.000000Z"
    _install_rehashed_v12_history_artifact(publisher, model)

    with pytest.raises(PublicationError) as exc:
        publisher.read_trial_projection()
    assert exc.value.code == "TRIAL_HISTORY_PROJECTION_INVALID"


def test_history_publication_replays_exact_facts_and_allows_only_byte_exact_carry_forward() -> None:
    """A self-rehashed public B2 model cannot substitute for private evidence."""

    _, _, snapshots = _history_chain()
    diff = build_history_exact_diff(
        *snapshots,
        transaction_from=snapshots[1]["transaction_from"],
    )
    facts = derive_history_change_facts(*snapshots, diff)
    model = build_history_read_model(
        snapshots,
        facts,
        generated_at="2026-08-02T00:00:14Z",
    )
    nct_id = model["nct_id"]
    fresh = HistoryPublicationEvidence(
        snapshots=tuple(snapshots),
        facts=tuple(facts),
    )

    publication_module._validate_history_publication_evidence(
        model,
        nct_id=nct_id,
        evidence=fresh,
        prior_model_bytes=None,
    )

    mismatched_fact = dict(facts[0])
    mismatched_fact["nct_id"] = "NCT99999999"
    with pytest.raises(PublicationError) as exc:
        publication_module._validate_history_publication_evidence(
            model,
            nct_id=nct_id,
            evidence=HistoryPublicationEvidence(
                snapshots=tuple(snapshots),
                facts=(mismatched_fact,),
            ),
            prior_model_bytes=None,
        )
    assert exc.value.code == "TRIAL_HISTORY_EVIDENCE_BINDING_MISMATCH"

    for mutate in (
        lambda candidate: candidate["changes"][0].__setitem__("kind", "forged_kind"),
        lambda candidate: candidate["changes"][0].__setitem__(
            "after_value", "forged registry value"
        ),
        lambda candidate: candidate["versions"][0].__setitem__(
            "source_submitted_at", "2025-12-31"
        ),
    ):
        forged = deepcopy(model)
        mutate(forged)
        forged["model_payload_sha256"] = canonical_json_sha256(
            {key: value for key, value in forged.items() if key != "model_payload_sha256"}
        )
        with pytest.raises(PublicationError) as exc:
            publication_module._validate_history_publication_evidence(
                forged,
                nct_id=nct_id,
                evidence=fresh,
                prior_model_bytes=None,
            )
        assert exc.value.code == "TRIAL_HISTORY_EVIDENCE_INVALID"

    carry = HistoryPublicationEvidence(carried_forward=True)
    canonical_bytes = canonical_json_bytes(model) + b"\n"
    publication_module._validate_history_publication_evidence(
        model,
        nct_id=nct_id,
        evidence=carry,
        prior_model_bytes=canonical_bytes,
    )
    forged_carry = deepcopy(model)
    forged_carry["generated_at"] = "2026-08-02T00:00:15Z"
    forged_carry["model_payload_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in forged_carry.items()
            if key != "model_payload_sha256"
        }
    )
    with pytest.raises(PublicationError) as exc:
        publication_module._validate_history_publication_evidence(
            forged_carry,
            nct_id=nct_id,
            evidence=carry,
            prior_model_bytes=canonical_bytes,
        )
    assert exc.value.code == "TRIAL_HISTORY_CARRY_FORWARD_MISMATCH"


@pytest.mark.parametrize("field", ("last_attempt_at", "last_success_at"))
def test_rehashed_immutable_generation_rejects_time_not_equal_to_publication(
    committed_generation: tuple[Any, PublicGenerationPublisher], field: str
) -> None:
    _, publisher = committed_generation
    pointer_path, generation, _ = _generation_paths(publisher)

    def mutate(health: dict[str, Any], manifest: dict[str, Any]) -> None:
        changed = "2026-08-01T16:00:01.000000Z"
        health[field] = changed
        manifest[field] = changed

    _rehash_generation(pointer_path=pointer_path, generation=generation, mutate=mutate)

    with pytest.raises(PublicationError):
        publisher.read_committed()


@pytest.mark.parametrize(
    ("attack", "mutate", "expected_code"),
    (
        (
            "source_snapshot_ref",
            lambda snapshot: snapshot.__setitem__(
                "source_snapshot_ref", "ctgov_snapshot_NCT00000001_rebound"
            ),
            "TRIAL_PROJECTION_BINDING_MISMATCH",
        ),
        (
            "source_record_ref",
            lambda snapshot: snapshot.__setitem__(
                "source_record_ref", "src:ctgov:NCT00000001:sha256:" + "0" * 64
            ),
            "TRIAL_PROJECTION_BINDING_MISMATCH",
        ),
        (
            "canonical_content_sha256",
            lambda snapshot: snapshot.__setitem__("canonical_content_sha256", "0" * 64),
            "TRIAL_PROJECTION_BINDING_MISMATCH",
        ),
        (
            "source_uri",
            lambda snapshot: snapshot["source_attribution"].__setitem__(
                "source_uri", "https://clinicaltrials.gov/study/NCT00000002"
            ),
            "TRIAL_PROJECTION_INVALID",
        ),
        (
            "source_version_ordinal",
            lambda snapshot: snapshot.__setitem__("source_version_ordinal", 2),
            "TRIAL_PROJECTION_BINDING_MISMATCH",
        ),
    ),
)
def test_rehashed_trial_projection_cannot_rebind_to_a_different_source_state(
    committed_generation: tuple[Any, PublicGenerationPublisher],
    attack: str,
    mutate: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    """A matching hash chain cannot bless a product DTO bound to another source."""

    _, publisher = committed_generation
    pointer_path, generation, _ = _generation_paths(publisher)
    _rehash_trial_projection(
        pointer_path=pointer_path,
        generation=generation,
        mutate=mutate,
    )

    with pytest.raises(PublicationError) as raised:
        publisher.read_trial_projection()

    assert raised.value.code == expected_code, attack


def test_rehashed_trial_projection_cannot_smuggle_private_provenance(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    """The product contract rejects private archive/object-store references."""

    _, publisher = committed_generation
    pointer_path, generation, _ = _generation_paths(publisher)
    _rehash_trial_projection(
        pointer_path=pointer_path,
        generation=generation,
        mutate=lambda snapshot: snapshot.__setitem__(
            "raw_object_key", "biocatalyst/raw/clinicaltrials/v2/NCT00000001/" + "0" * 64 + ".json"
        ),
    )

    with pytest.raises(PublicationError) as raised:
        publisher.read_trial_projection()

    assert raised.value.code == "TRIAL_PROJECTION_INVALID"


def test_worker_quarantines_a_rehashed_projection_that_disagrees_with_replayed_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The worker independently binds product facts to exact receipt/page evidence."""

    real_builder = publication_module.build_trial_snapshot

    def forged_builder(
        source_snapshot: dict[str, Any], *, source_version_ordinal: int = 1
    ) -> dict[str, Any]:
        projection = real_builder(
            source_snapshot, source_version_ordinal=source_version_ordinal
        )
        projection["facts"]["overall_status"]["value"] = "COMPLETED"
        projection["projection_sha256"] = canonical_json_sha256(
            {
                key: value
                for key, value in projection.items()
                if key != "projection_sha256"
            }
        )
        return projection

    monkeypatch.setattr(publication_module, "build_trial_snapshot", forged_builder)
    config = worker_config(tmp_path)
    result = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )

    assert result.status == "failed"
    assert result.error_code == "TRIAL_PROJECTION_INVALID"
    assert not (config.public_root / "current.json").exists()
    health = json.loads((config.public_root / "health.json").read_text(encoding="utf-8"))
    assert health["state"] == "quarantined"
    assert health["last_error_code"] == "TRIAL_PROJECTION_INVALID"


@pytest.mark.parametrize(
    "anchor",
    (
        "state/staging",
        "state/committed",
        "state/dead-letter",
        "public/generations",
        "state/biocatalyst_worker.lock",
    ),
)
def test_worker_rejects_symlink_runtime_anchors_before_any_attempt_or_external_write(
    tmp_path: Path, anchor: str
) -> None:
    state_root = tmp_path / "state"
    public_root = tmp_path / "public"
    state_root.mkdir()
    public_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"must not change")

    kind, relative = anchor.split("/", 1)
    link = (state_root if kind == "state" else public_root) / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    if relative == "biocatalyst_worker.lock":
        link.symlink_to(outside / "worker.lock")
    else:
        link.symlink_to(outside, target_is_directory=True)
    before = _tree_fingerprint(outside)
    calls = {"collector": 0, "store": 0}

    class FailingCollector:
        def collect(self, *, watermark_before: str | None = None):
            calls["collector"] += 1
            raise PublicationError("RAW_EVIDENCE_INVALID")

    config = worker.WorkerConfig(
        state_root=state_root,
        public_root=public_root,
        nct_ids=("NCT00000001",),
        user_agent="MastermindX test contact@example.com",
        r2=worker.DedicatedR2Config(
            endpoint="https://r2.example.test",
            bucket="biocatalyst-private",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
    )
    result = worker.run_once(
        config,
        collector_factory=lambda **_: FailingCollector(),
        store_factory=lambda _: calls.__setitem__("store", calls["store"] + 1),
        now_fn=lambda: NOW,
    )

    assert result.status == "failed"
    assert calls == {"collector": 0, "store": 0}
    assert _tree_fingerprint(outside) == before
    health = json.loads((public_root / "health.json").read_text(encoding="utf-8"))
    assert health["state"] == "quarantined"


def test_private_archive_rejects_a_nested_symlink_before_it_can_be_committed(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    private_stage = state_root / "staging" / "attempt_one" / "private"
    private_stage.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"must not change")
    (private_stage / "nested").symlink_to(outside, target_is_directory=True)
    before = _tree_fingerprint(outside)

    with pytest.raises(PublicationError):
        archive_private_stage(private_stage, state_root=state_root, run_id=RUN_ID)

    assert private_stage.exists()
    assert _tree_fingerprint(outside) == before
    assert not (state_root / "committed" / RUN_ID).exists()


def test_private_archive_rejects_a_nonregular_preexisting_immutable_tree(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    private_stage = state_root / "staging" / "attempt_one" / "private"
    private_stage.mkdir(parents=True)
    (private_stage / "evidence.json").write_bytes(b"{}")
    retained = state_root / "committed" / RUN_ID / "private"
    retained.mkdir(parents=True)
    (retained / "evidence.json").write_bytes(b"{}")
    fifo = retained / "unexpected.fifo"
    os.mkfifo(fifo)

    with pytest.raises(PublicationError):
        archive_private_stage(private_stage, state_root=state_root, run_id=RUN_ID)

    assert private_stage.exists()
    assert fifo.exists()


def test_generation_install_rejects_a_symlinked_generations_anchor_without_moving_stage(
    tmp_path: Path,
) -> None:
    public_root = tmp_path / "public"
    public_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"must not change")
    (public_root / "generations").symlink_to(outside, target_is_directory=True)
    stage = tmp_path / "candidate-stage"
    stage.mkdir()
    before = _tree_fingerprint(outside)
    prepared = PreparedGeneration(
        generation_id=RUN_ID,
        stage_path=stage,
        manifest_sha256="0" * 64,
        watermark_after="2026-08-01T16:00:00.000000Z",
        published_at="2026-08-01T16:00:00.000000Z",
        source_dataset_timestamp_raw="2026-08-01T09:00:00",
    )

    with pytest.raises(PublicationError):
        PublicGenerationPublisher(public_root).install_generation(prepared)

    assert stage.exists()
    assert _tree_fingerprint(outside) == before


class _ReplayResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.status_code = 200
        self.headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(self.content)),
        }


class _ReplaySession:
    def __init__(self, responses: list[_ReplayResponse]) -> None:
        self.responses = list(responses)

    def get(self, url: str, **kwargs: Any) -> _ReplayResponse:
        assert self.responses, f"unexpected request to {url}"
        return self.responses.pop(0)


def _complete_collector(tmp_path: Path) -> tuple[ClinicalTrialsV2Collector, Path, Path]:
    version = {"apiVersion": "2.0.5", "dataTimestamp": "2026-08-01T09:00:00"}
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "One"},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": "2026-08-01", "type": "ACTUAL"},
            },
        }
    }
    collector = ClinicalTrialsV2Collector(
        private_root=tmp_path / "private",
        public_root=tmp_path / "public",
        config=ClinicalTrialsV2Config(
            nct_ids=("NCT00000001",),
            user_agent="MastermindX-BioCatalyst/test (ops@example.invalid)",
        ),
        session=_ReplaySession(
            [
                _ReplayResponse(version),
                _ReplayResponse({"studies": [study], "totalCount": 1}),
                _ReplayResponse(version),
            ]
        ),
        now_fn=lambda: datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc),
    )
    result = collector.collect()
    return collector, result.run_path, tmp_path / "private"


@pytest.mark.parametrize("location", ("external", "symlink", "noncanonical"))
def test_replay_accepts_only_the_canonical_non_symlink_private_run_path(
    tmp_path: Path, location: str
) -> None:
    collector, canonical_run, private_root = _complete_collector(tmp_path)
    if location == "external":
        candidate = tmp_path / "outside" / "run.json"
        candidate.parent.mkdir()
        candidate.write_bytes(canonical_run.read_bytes())
    elif location == "symlink":
        candidate = private_root / "run-link.json"
        candidate.symlink_to(canonical_run)
    else:
        candidate = private_root / "biocatalyst" / "runs" / "alias.json"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(canonical_run.read_bytes())

    with pytest.raises(CollectionError) as raised:
        collector.replay(candidate)
    assert raised.value.code == "RUN_NOT_REPLAYABLE"


def test_replay_still_accepts_the_exact_canonical_run_path(tmp_path: Path) -> None:
    collector, canonical_run, _ = _complete_collector(tmp_path)
    replayed = collector.replay(canonical_run)
    assert replayed.run_path == canonical_run
    assert replayed.current_pointer_path is None


def test_only_explicit_transient_availability_codes_are_partial() -> None:
    expected_transient = frozenset(
        {
            "HTTP_REQUEST_FAILED",
            "UNEXPECTED_HTTP_STATUS",
            "BIOCATALYST_R2_READ_FAILED",
            "BIOCATALYST_R2_READBACK_FAILED",
            "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED",
            "POINTER_WRITE_FAILED",
        }
    )

    assert worker._TRANSIENT_AVAILABILITY_CODES == expected_transient
    assert worker._SAFE_ERROR_CODES - worker._QUARANTINE_CODES == expected_transient
    for code in worker._SAFE_ERROR_CODES:
        assert worker._failure_state(code) == (
            "partial" if code in expected_transient else "quarantined"
        )
